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

    def __init__(self):
        self.scr, self.model = Screen(), apl64.Interp()
        self.line, self.hist, self.prefix = [], [], False
        self.prompt()

    def prompt(self):
        self.scr.write(b" " * 6)

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
            try:
                for v in self.model.run_values(text):
                    s.write(text_bytes(v) + b"\n")
            except apl64.AplError as e:
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


def expected(keys):
    ed = EditorModel()
    for k in keys:
        ed.key(k)
    return ed.screen()


def build_keytest(keys):
    data = ["keytest_data:"]
    for i in range(0, len(keys), 24):
        data.append("        .byte " + ", ".join(str(k) for k in keys[i:i + 24]))
    data.append("        .byte 0")
    os.makedirs("build", exist_ok=True)
    with open("build/keytest_data.inc", "w") as f:
        f.write("\n".join(data) + "\n")
    r = subprocess.run(["64tass", "-D", "SELFTEST=0", "-D", "KEYTEST=1", "-I", "build", "--labels=build/keytest.lbl",
                        "-o", "build/keytest.prg", "asm/eval.asm"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    return labels("build/keytest.lbl")


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


def test_scripted():
    for text in SESSIONS:
        keys = petscii(text)
        L = build_keytest(keys)
        _, files = _run_selftest(['save "{DIR}/screen.bin" 0 cc00 cfe7'], hex(L["selftest_done"]),
                                 prg="build/keytest.prg")
        got, want = files["screen.bin"][2:], expected(keys)
        if got != want:
            show(got, want)
            raise AssertionError(f"screen differs from the model for keys {text!r}")
    print(f"keys: {len(SESSIONS)} scripted sessions (digraphs, backspace, recall, clear, wrapping, scrolling, "
          f"errors) match the editor model on the real machine")


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
