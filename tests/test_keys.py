"""Keyboard entry and the line editor on the real machine (VICE).

Scripted key sessions run through the whole editor and REPL in a test build (keys read from a list
instead of the keyboard); a second test pokes keys into the KERNAL's own keyboard buffer so GETIN and
the interrupt scan are exercised. Both compare screen RAM with a Python model of the editor.
Skipped without the C64 ROMs in roms/ or without VICE.
"""
import os
import re
import subprocess
import sys

sys.path.insert(0, os.getcwd())
sys.path.insert(0, "tools")
import apl64
import keys as K
from harness import scratch
from test_screen import Screen, _run_selftest, text_bytes
from test_vice import ROMS

INV = {v: k for k, v in apl64.GLYPH_CODES.items()}


def petscii(text):
    """'1+2{RET}' -> the PETSCII a keyboard would deliver. {RET} {DEL} {UP} {CLR} {P} (pound) {LA} (left arrow) {$xx}."""
    out, i = [], 0
    special = {"RET": K.RETURN, "DEL": K.DEL, "UP": K.UP, "CLR": K.CLR, "P": K.PREFIX, "LA": K.LARROW}
    while i < len(text):
        c = text[i]
        if c == "{":
            j = text.index("}", i)
            tag = text[i + 1:j]
            out.append(int(tag[1:], 16) if tag.startswith("$") else special[tag])
            i = j + 1
            continue
        o = ord(c)
        if "a" <= c <= "z":
            out.append(o - 0x20)              # unshifted letters arrive as $41-$5A
        elif "A" <= c <= "Z":
            out.append(o + 0x80)              # shifted: $C1-$DA
        else:
            out.append(o)
        i += 1
    return out


class EditorModel:
    """The editor's behaviour: what the screen shows after a series of keys."""

    def __init__(self, heap=None):
        self.scr, self.model = Screen(), apl64.Interp()
        self.line, self.hist, self.prefix = [], [], False
        self.heap = heap                      # (HEAP_BASE, HEAP_LIMIT), for )FREE
        self.wsname = ""
        self.prompt()

    def say(self, text):
        self.scr.write(text.encode() + b"\n")

    def syscmd(self, t):
        """The system commands (DESIGN.md, System commands): t is the text after the ')'."""
        i = 0
        while i < len(t) and t[i] != " ":
            i += 1
        word, arg = t[:i].upper(), t[i:].lstrip(" ")
        m = self.model
        if word in ("VARS", "FNS"):
            have = m.vars if word == "VARS" else m.funcs
            names = sorted((n for k, n in enumerate(m.names) if k in have), key=apl64.encode_line)
            for n in names:
                b = apl64.encode_line(n)
                if self.scr.col != 0:
                    self.scr.put(10 if len(b) >= 40 or self.scr.col + len(b) + 1 > 40 else 32)
                self.scr.write(b)
            if names:
                self.scr.put(10)
        elif word == "ERASE":
            try:
                toks = m.decode(m.tokenize(arg))
            except apl64.AplError as e:
                self.say(e.kind)
                return
            if any(c != 2 for c, _ in toks):
                self.say("BAD COMMAND")
                return
            for _, k in toks:
                m.vars.pop(k, None)
                m.funcs.pop(k, None)
        elif word == "CLEAR":
            self.model = apl64.Interp()
            self.wsname = ""
            self.say("CLEAR WS")
        elif word == "FREE":
            base, limit = self.heap
            seen = {id(v): v for v in m.vars.values() if v.rank > 0}
            live = sum(1 + len(v.to_bytes()) for v in seen.values())
            live += sum(1 + len(f.block_bytes()) for f in m.funcs.values())
            self.say(f"{limit - base - live} BYTES FREE")
        elif word == "WSID":
            if not arg:
                self.say(self.wsname or "CLEAR WS")
            else:
                name = arg.split(" ")[0].upper()
                if 1 <= len(name) <= 16 and all(c.isalnum() and c.isascii() or c in "-." for c in name):
                    self.wsname = name
                else:
                    self.say("BAD NAME")
        else:
            self.say("BAD COMMAND")

    def prompt(self):
        self.scr.write(apl64.encode_line(self.model.prompt()))

    def insert(self, c):
        if len(self.line) < 255:
            self.line.append(c)
            self.scr.put(c)

    def retype(self):
        for c in self.line:
            self.scr.put(c)

    def erase_line(self):
        while self.line:
            self.line.pop()
            self.scr.back()

    def key(self, k):
        s = self.scr
        if s.ptr < 1000:
            s.mem[s.ptr] = 0x20                 # the cursor block is erased before every key
        if self.prefix:
            self.prefix = False
            if k == K.PREFIX:
                self.insert(0x5C)
            else:
                t = K.translate(k)
                if t is not None and t in K.DIGRAPHS:
                    self.insert(K.DIGRAPHS[t])
            return
        if k == K.RETURN:
            if self.line:
                self.hist = list(self.line)
            s.put(10)
            text = "".join(INV.get(c, chr(c)) for c in self.line)
            self.line = []
            if text.lstrip(" ").startswith(")") and self.model.defining is None:
                self.syscmd(text.lstrip(" ")[1:])
                self.prompt()
                return
            try:
                for v in self.model.run_values(text):
                    s.write(text_bytes(v) + b"\n")
            except apl64.AplError as e:
                for v in getattr(e, "outs", []):
                    s.write(text_bytes(v) + b"\n")
                s.write(e.kind.encode() + b"\n")
            self.prompt()
        elif k == K.DEL:
            if self.line:
                self.line.pop()
                s.back()
        elif k == K.CLR:
            s.clear()
            self.prompt()
            self.retype()
        elif k == K.UP:
            self.erase_line()
            self.line = list(self.hist)
            self.retype()
        elif k == K.PREFIX:
            self.prefix = True
        else:
            t = K.translate(k)
            if t is not None:
                self.insert(t)

    def screen(self):
        mem = bytearray(self.scr.mem)
        if self.scr.ptr < 1000:
            mem[self.scr.ptr] = 0x7F               # the cursor block waits for the next key
        return bytes(mem)


def expected(keys, heap=None):
    ed = EditorModel(heap)
    for k in keys:
        ed.key(k)
    return ed.screen()


def build_keytest(keys):
    data = ["keytest_data:"]
    for i in range(0, len(keys), 24):
        data.append("        .byte " + ", ".join(str(k) for k in keys[i:i + 24]))
    data.append("        .byte 0")
    with open(scratch("keytest_data.inc"), "w") as f:
        f.write("\n".join(data) + "\n")
    r = subprocess.run(["64tass", "-D", "SELFTEST=0", "-D", "KEYTEST=1", "-I", os.path.dirname(scratch()),
                        "--labels=" + scratch("keytest.lbl"), "-o", scratch("keytest.prg"), "asm/eval.asm"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    return labels(scratch("keytest.lbl"))


def labels(path):
    L = {}
    for line in open(path):
        m = re.match(r"(\S+)\s*=\s*(\$[0-9a-fA-F]+|\d+)\s*$", line)
        if m:
            v = m.group(2)
            L[m.group(1)] = int(v[1:], 16) if v[0] == "$" else int(v)
    return L


def show(a, b):
    for r in range(25):
        x, y = a[r * 40:r * 40 + 40], b[r * 40:r * 40 + 40]
        if x != y:
            print(f"row {r}\n  vice  {x!r}\n  model {y!r}")


SESSIONS = [
    "1+2{RET}",
    "{P}i5{RET}",                                       # ⍳5 through the digraph
    "{P}r{P}i6{RET}",                                   # ⍴⍳6
    "2 3{P}r{P}i6{RET}",                                # 2 3⍴⍳6
    "a{LA}5{RET}a{P}-a{RET}",                           # a←5, then a×a (× via digraph)
    "x{LA}{P}i4{RET}x{P}={P}i4{RET}",                   # ÷ digraph
    "1{P}82{RET}3{P}44{RET}5{P}66{RET}",                # ≠ ≤ ≥ via digraphs
    "{P}2{P}25{RET}",                                   # ¯ ¯5 -> DOMAIN? (a syntax test of the glyph)
    "{P}'{RET}",                                        # ⍬
    "12{DEL}3{RET}",                                    # backspace
    "abc{DEL}{DEL}{DEL}{DEL}1{RET}",                    # backspace past the start does nothing
    "1+1{RET}{UP}{RET}",                                # recall
    "1+1{RET}2+2{RET}{UP}{DEL}5{RET}",                  # recall, edit, run
    "{UP}{RET}",                                        # recall with no history
    "3+{UP}4{RET}",                                     # recall over a partial line
    "1{RET}{CLR}2{RET}",                                # clear the screen
    "12{CLR}3{RET}",                                    # clear with text typed
    "{P}{P}{RET}",                                      # prefix twice: a backslash -> syntax? (typed \ )
    "{P}z{RET}",                                        # an unmapped digraph is ignored
    "a{P}[5{RET}a{RET}",                                # ← through the bracket digraph: a←5, then a
    "{P}]{RET}",                                        # → through the bracket digraph
    "1{$5b}2{$5d}3{$5e}4{RET}",                         # [ ] ^ typed bare (PETSCII $5B $5D $5E)
    "{P}{RET}1{RET}",                                   # RETURN cancels the prefix
    "Ab{LA}3{RET}Ab{RET}",                              # shifted letters: a variable named Ab
    "n{P}{LA}1{LA}2{RET}",                              # underscore digraph: n_1←2?
    "'hello'{RET}'it''s'{RET}",
    "1÷0{RET}" if False else "1{P}={RET}",              # a syntax error from a lone ÷
    "{$03}{$85}{$ff}{$1d}{$9d}{$11}{$13}{$1c}1{RET}",   # keys that do nothing (STOP, F1, cursor keys, HOME, colour)
    "1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20{RET}",          # a line wider than the screen
    "1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20{DEL}{DEL}{DEL}{DEL}{DEL}{DEL}{DEL}{DEL}{DEL}{DEL}{DEL}{DEL}{DEL}{DEL}{DEL}{DEL}{DEL}{DEL}{DEL}{DEL}{DEL}{DEL}{DEL}{DEL}{DEL}{DEL}{DEL}{DEL}{DEL}{DEL}{DEL}{DEL}{DEL}{DEL}{DEL}{DEL}{DEL}{DEL}{DEL}{DEL}{DEL}{DEL}{DEL}1{RET}",
    "1{RET}" * 13,                                     # scrolling while typing
    "{P}i9{RET}" * 4,
    "'" + "a" * 60 + "'{RET}{UP}{RET}",                # a long string, recalled
    "'" + "b" * 253 + "'" + "cccccc{RET}",              # more than 255 characters: the extra are ignored
    "a{LA}{P}i3{RET}{P}i3{RET}a{P}-a{RET}",
]

def typed_lines(*lines):
    """APL lines as the keys that type them: the glyphs are digraphs after the pound key."""
    keys = {"⍉": "{P}t", "∊": "{P}e", "⍋": "{P}7", "⍒": "{P}3", "⌽": "{P}a", "↑": "{P}y", "↓": "{P}u", "∧": "{P}w", "∨": "{P}v", "~": "{P}n", "⌈": "{P}s", "⌊": "{P}d", "|": "{P}l", "≤": "{P}4", "≥": "{P}6", "≠": "{P}8", "→": "{P}]", "←": "{LA}", "⍳": "{P}i", "⍴": "{P}r", "×": "{P}-", "÷": "{P}=", "∇": "{P}g", "⋄": "{P}."}
    return "".join("".join(keys.get(c, c) for c in ln) + "{RET}" for ln in lines)


CMD_SESSIONS = [
    typed_lines("∇R←SQ X", "R←X×X", "∇", "∇SHOW X", "X", "∇", "a←1") + ")fns{RET})vars{RET}",       # functions are not variables
    typed_lines("∇R←SQ X", "R←X×X", "∇", "∇R←ZED", "R←0", "∇", "b←SQ 5") + ")fns{RET})erase SQ{RET})fns{RET}SQ 2{RET})vars{RET}",
    typed_lines("∇R←F X", "R←X", "∇", "∇R←F X", "R←X+1", "∇", "F 1", "F←3") + ")free{RET})clear{RET})fns{RET})free{RET}",
    typed_lines("∇F", "1", "2", "∇", "F", "∇R←G", "R←F", "∇", "G", "1+G") + ")fns{RET}",                 # echoes inside functions
    typed_lines("∇R←F X", "R←X÷0", "∇", "F 1", "F 2", "∇G", "F 5", "∇", "G", "1") + ")fns{RET}",
    typed_lines("∇F", "1") + ")fns{RET})vars{RET}" + typed_lines("∇", ")fns"),
    typed_lines("10 20⍳20", "1 2∊2", "⍋3 1 2", "⍒3 1 2", "⌽1 2 3", "1⌽⍳4", "2↑⍳5", "1↓⍳4", "1∧0", "1 0∨0 0", "~1 0 1", "∧/1 1 0", "3⌈5", "3⌊5", "⌈2.5", "⌊¯2.5", "3|¯7", "|¯4", "⌈/2 9 4", "5|17", "⍉2 3⍴⍳6", "2 1⍉2 2⍴⍳4", "1 2 3~2") + ")vars{RET}",       # the new glyphs by digraph
    typed_lines("∇R←F N", "R←0", "L:R←R+N", "N←N-1", "→L×⍳N>0", "∇", "F 4", "→1", "F 100") + ")fns{RET}",     # labels, loops                            # ) lines are body lines
    ")fns{RET}  )FNS extra{RET})Fns{RET}",
    ")vars{RET}",                                                      # nothing defined: nothing printed
    "b{LA}1{RET}a{LA}2 3{RET}zz{LA}'x'{RET}Ab{LA}5{RET})vars{RET}",    # sorted: Ab a b zz
    "b{LA}1{RET}a{LA}2{RET})VARS{RET}  )Vars extra words{RET}",         # case, spaces, extra words
    "abcdefghijk{LA}1{RET}bcdefghijkl{LA}2{RET}cdefghijklm{LA}3{RET}defghijklmn{LA}4{RET})vars{RET}",  # wrapping at 40
    "a{LA}1{RET}b{LA}1{RET}c{LA}1{RET}d{LA}1{RET}e{LA}1{RET}f{LA}1{RET}g{LA}1{RET}h{LA}1{RET}i{LA}1{RET}j{LA}1{RET}k{LA}1{RET})vars{RET}",
    "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa{LA}1{RET}bbb{LA}2{RET})vars{RET}",   # a name of exactly 40 characters
    "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa{LA}1{RET}b{LA}2{RET})vars{RET}",   # longer than the screen
    "a{LA}1{RET}b{LA}2{RET}c{LA}3{RET})erase a c{RET})vars{RET}a{RET}b{RET}",     # erase, then VALUE ERROR
    ")erase ghost{RET}g{LA}1{RET})erase g ghost{RET})vars{RET}",       # unknown names are ignored
    "a{LA}1{RET})erase 1{RET})erase a 2{RET})erase {P}i{RET})vars{RET}",   # only names: BAD COMMAND
    ")erase 'abc{RET}a{LA}1{RET})erase{RET})vars{RET}",                # a tokenizer error, an empty argument
    "a{LA}1 2 3{RET}b{LA}a{RET})clear{RET})vars{RET}a{RET}c{LA}5{RET})vars{RET}",   # clear, VALUE ERROR, start again
    ")wsid{RET})wsid Test{RET})wsid{RET})wsid other-1.x extra{RET})wsid{RET})clear{RET})wsid{RET}",
    ")wsid ABCDEFGHIJKLMNOPQ{RET})wsid bad{P}name{RET})wsid 1234567890123456{RET})wsid{RET}",   # 17 characters, a bad character
    ")bogus{RET}){RET})abcdefghijklm{RET}) vars{RET}   ){RET}",
    ")free{RET}a{LA}{P}i100{RET})free{RET}b{LA}a{RET})free{RET}c{LA}a,a{RET})free{RET})erase a b c{RET})free{RET}",
    "a{LA}5{RET}b{LA}1.5{RET}c{LA}'hello'{RET})free{RET}d{LA}2 3{P}r{P}i6{RET})free{RET}",
    "a{LA}{P}i10{RET}a{LA}1{RET})free{RET}",                             # the array is garbage after reassigning
    ")vars{RET}1+1{RET})free{RET}",
    "ab{LA}1{RET}a{LA}1{RET}abc{LA}1{RET}b{LA}1{RET}aB{LA}1{RET}Z{LA}1{RET}z{LA}1{RET}_x{LA}1{RET})vars{RET}",   # prefixes, cases
    # words that end one column past the edge, exactly on it, and a name too long for a byte of arithmetic
    "aaaaaaaaaaa{LA}1{RET}bbbbbbbbbbb{LA}1{RET}ccccccccccc{LA}1{RET}ddddd{LA}1{RET})vars{RET}",
    "aaaaaaaaaaa{LA}1{RET}bbbbbbbbbbb{LA}1{RET}ccccccccccc{LA}1{RET}dddd{LA}1{RET})vars{RET}",
    "aaaaaaaaaaa{LA}1{RET}bbbbbbbbbbb{LA}1{RET}ccccccccccc{LA}1{RET}dddd{LA}1{RET}e{LA}1{RET})vars{RET}",
    "a{LA}1{RET}" + "b" * 250 + "{LA}1{RET})vars{RET}",
    "a{LA}1{RET}" + "b" * 215 + "{LA}1{RET}c{LA}1{RET})vars{RET}",
    "abcdefghij{LA}1{RET}" + "b" * 245 + "{LA}1{RET})vars{RET}",          # length + column + 1 = 256: a byte overflows
    ")wsid a{P}{LA}b{RET})wsid a*b{RET})wsid a,b{RET})wsid a:b{RET})wsid a@b{RET})wsid a?b{RET})wsid a$b{RET})wsid{RET}",
    # the symbol table is emptied by )CLEAR: 200 names, clear, 200 more (400 would not fit)
    "".join(f"n{i}{{LA}}1{{RET}}" for i in range(200)) + ")clear{RET}" + "".join(f"m{i}{{LA}}1{{RET}}" for i in range(200)) + ")vars{RET}",
]


def test_scripted():
    for text in SESSIONS:
        keys = petscii(text)
        L = build_keytest(keys)
        _, files = _run_selftest(['save "{DIR}/screen.bin" 0 cc00 cfe7'], hex(L["selftest_done"]),
                                 prg=scratch("keytest.prg"))
        got, want = files["screen.bin"][2:], expected(keys, (L["HEAP_BASE"], L["HEAP_LIMIT"]))
        if got != want:
            show(got, want)
            raise AssertionError(f"screen differs from the model for keys {text!r}")
    print(f"keys: {len(SESSIONS)} scripted sessions (digraphs, backspace, recall, clear, wrapping, scrolling, "
          f"errors) match the editor model on the real machine")


def test_commands():
    for text in CMD_SESSIONS:
        keys = petscii(text)
        L = build_keytest(keys)
        _, files = _run_selftest(['save "{DIR}/screen.bin" 0 cc00 cfe7'], hex(L["selftest_done"]),
                                 prg=scratch("keytest.prg"))
        got, want = files["screen.bin"][2:], expected(keys, (L["HEAP_BASE"], L["HEAP_LIMIT"]))
        if got != want:
            show(got, want)
            raise AssertionError(f"screen differs from the model for keys {text!r}")
    print(f"keys: {len(CMD_SESSIONS)} system command sessions ()VARS, )ERASE, )CLEAR, )FREE, )WSID, errors) match the "
          f"model on the real machine")


def test_real_keyboard():
    """Keys go into the KERNAL's own buffer; GETIN reads them while the interrupt keeps running."""
    keys = petscii("1+2{RET}{P}i3{RET}")
    assert len(keys) <= 10
    subprocess.run(["make", "build/apl.prg"], capture_output=True, check=True)
    L = labels("build/eval.lbl")
    poke = " ".join(f"{k:02x}" for k in keys)
    script = [f"> 0277 {poke}", f"> 00c6 {len(keys):02x}", f"break {L['kbd_idle']:04x}", "x",
              'save "{DIR}/screen.bin" 0 cc00 cfe7', 'save "{DIR}/zp.bin" 0 0000 00ff']
    _, files = _run_selftest(script, hex(L["start"]), prg="build/apl.prg")
    got, want = files["screen.bin"][2:], expected(keys)
    if got != want:
        show(got, want)
        raise AssertionError("screen differs from the model for keys typed through the KERNAL buffer")
    assert files["zp.bin"][2:][0xC6] == 0, "the KERNAL keyboard buffer was not emptied"
    print("keys: 8 keys typed through the KERNAL's keyboard buffer (GETIN + interrupt scan) give the model's screen")


if __name__ == "__main__":
    if not all(os.path.exists("roms/" + r) for r in ROMS):
        print("keys: skipped (no C64 ROMs in roms/)")
    elif subprocess.run(["which", "x64sc"], capture_output=True).returncode:
        print("keys: skipped (x64sc not installed)")
    else:
        test_real_keyboard()
        test_scripted()
        test_commands()
