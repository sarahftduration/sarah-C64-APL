"""On the real machine (VICE, real KERNAL): a scripted session through tokenizer, evaluator and
formatter onto the 40x25 screen, compared with the model; plus the charset and hardware state.

Needs the C64 ROMs in roms/ (git-ignored); skipped without them or without VICE.
"""
import os
import re
import subprocess
import sys

sys.path.insert(0, os.getcwd())
sys.path.insert(0, "tools")
import apl64
from glyphs import expected_charset
from harness import scratch
from test_vice import ROMS, run_vice

LINES = [
    "1", "1 2 3", "¯5", "0.1", "1÷3", "1e10", "¯1.5e¯20", "12345.678", "100000", "⍳10", "⍳25", "⍳50",
    "2 3⍴⍳6", "3 3⍴÷⍳9", "⍴2 3⍴⍳6", "2 2⍴1.5 ¯2 100 0.25", "'hello'", "'hello world'", "'a×b≠c'", "''", "'x'",
    "2 3⍴'abcdef'", "A←⍳5", "A×A", "A÷2", "+/A", "×/⍳10", "×/⍳20", "-/⍳4", "A=3", "A≤3", "A≥3", "1≠2", "10÷4",
    "B←⍬", "⍬", "⍴⍬", "0⍴5", "3 0⍴1", "'abc',' ','def'", "(⍳3),4 5", "1 2,3.5", "1 ¯1 0 1e5 1e¯5",
    "2 3⍴1e10 1 2 3 4 5", "1÷0", "Z", "1 2+1 2 3", "(", "⍳¯1", "2 3 4⍴1", "1 ⍴", "⍳2 3⍴1", "'a'+1", "1e38×10",
    "x←⍳3 ⋄ x", "⍳0", "5", "⍳100",
    "M←3 4⍴⍳12", "M[2;3]", "M[;2]", "M[1 3;2 4]", "A[2 4]", "A[6]", "M[1;5]", "M[1]", "'hello'[5 1]", "A[⍳0]", "A[(1;2)]",
    "A[2]←9", "A", "M[1;2]←0", "M", "M[;1]←7 8 9", "M", "A[1]←1.5", "A", "A[7]←1", "A[1]←'a'", "1+A[1]←2",
    "∇R←SQ X", "R←X×X", "∇", "SQ 7", "SQ ⍳5", "1+SQ 2", "∇R←A ADD B;T", "T←A+B", "T", "R←T×2", "∇", "1 ADD 2",
    "∇SHOW X", "X", "'done'", "∇", "SHOW 3", "1+SHOW 3", "∇R←BAD X", "R←X÷0", "∇", "BAD 1", "SQ", "∇1", "∇R←LOOP", "R←LOOP", "∇", "LOOP",
    "∇R←SUMTO N;I", "R←0", "I←1", "TOP:R←R+I", "I←I+1", "→TOP×⍳I≤N", "∇", "SUMTO 10", "SUMTO 100", "→1", "10 20 30⍳20 40", "'abc'⍳'cz'", "1 2 3∊2", "'ab'∊'b'", "⍋3 1 2", "⍒3 1 2 1", "⍋'hello'", "⍋⍳0", "⍋5", "⌽1 2 3", "2⌽⍳5", "⌽2 3⍴⍳6", "1⌽2 3⍴⍳6", "3↑1 2", "¯2↑⍳5", "2 2↑3 3⍴⍳9", "1↓⍳4", "1 1↓3 3⍴⍳9", "5↑'ab'", "⌽'abc'", "⍴3 0↑⍳4", "1∧0", "1 0 1∨0 0 0", "~1 0", "~2", "(3>2)∧(1<2)", "∧/1 1 0", "∨/0 0 1", "3⌈5", "1.5⌊¯2", "⌊2.5 ¯2.5", "⌈¯0.3", "|¯7 3", "3|10 ¯10", "1|2.75", "⌈/4 9 2", "⌊/⍳0", "|'a'", "1 0 1/4 5 6", "+\\⍳6", "-\\1 2 3 4", "+\\2 3⍴⍳6", "1 2 3∘.×1 2 3", "+/[1]2 3⍴⍳6", "A←⍳1500 ⋄ B←A+1 ⋄ C←B×2 ⋄ D←C-A ⋄ E←D+B ⋄ F←E+C ⋄ G←F-A", "+/A", "+/B", "+/C ⋄ +/D", "E[1 2 3 1500]", "F[1 2 1500]", "A[1500]←0 ⋄ +/A", "+/B×C", "+/D-E", "H←F,A ⋄ ⍴H", "+/H", "+/G", "*1", "*¯1 0 1", "!5", "!⍳6", "2!5", "!34", "○1", "1○○0.5", "2○0", "3○0.5", "¯3○1", "¯1○2", "5○1", "⍟10", "2*10", "2*0.5", "10⍟1000", "(⍳3)∘.*⍳3", "*100", "⍟0", "¯2*0.5", "(2 3⍴⍳6),(2 2⍴7 8 9 10)", "(2 2⍴1 2 3 4),[1]5 6", "1 2,[2]2 2⍴3 4 5 6", "1 0 1/2 3⍴⍳6", "1 0/[1]2 3⍴⍳6", "1 0 1\\2 2⍴7 8 9 10", "(2 3⍴1),(3 2⍴1)", "+\\[1]2 3⍴⍳6", "⌽[1]2 3⍴⍳6", "1⌽[2]2 3⍴⍳6", "+/[3]2 3⍴⍳6", "+/[1]⍳4", "⍉2 3⍴⍳6", "2 1⍉3 2⍴⍳6", "1 2 3 4~2 4", "1 0 1\\7 8", "'abc'~'b'", "0 1 0\\'x'", "1 2 3+.×4 5 6", "(2 3⍴⍳6)+.×3 2⍴⍳6", "(2 2⍴1 0 0 1)∧.=2 2⍴1 0 1 1", "1 2+.×2 3⍴1.5", "1 2 3+.×4 5", "(⍳4)∘.≤⍳4", "0.5 2∘.+1 2", "2 2⍴1∘.+1", "(2 2⍴1)∘.+1", "2 2⍴1 2\\3", "2/1 2", "(A>2)/A", "'abcd'/1", "∇R←FACT N", "R←1", "→0×⍳N<2",
    "R←N×FACT N-1", "∇", "FACT 5", "FACT 6", "∇F", "'a'", "→4", "'b'", "'c'", "∇", "F",
]


class Screen:
    """The screen driver's behaviour: wrap at column 40, $0a starts a new line, scroll at row 25."""

    def __init__(self):
        self.mem = bytearray(b" " * 1000)
        self.ptr = self.row = self.col = 0
        self.scrolls = 0

    def put(self, c):
        if c == 10:
            self.ptr += 40 - self.col
        else:
            self.mem[self.ptr] = c
            self.ptr += 1
            self.col += 1
            if self.col < 40:
                return
        self.col = 0
        self.row += 1
        if self.row >= 25:
            self.mem[0:960] = self.mem[40:1000]
            self.mem[960:1000] = b" " * 40
            self.ptr, self.row = 960, 24
            self.scrolls += 1

    def write(self, data):
        for b in data:
            self.put(b)

    def back(self):
        """One cell back (across a wrapped line), blanked; nothing at the top left."""
        if self.col > 0:
            self.col -= 1
        elif self.row > 0:
            self.row -= 1
            self.col = 39
        else:
            return
        self.ptr -= 1
        self.mem[self.ptr] = 0x20

    def clear(self):
        self.mem = bytearray(b" " * 1000)
        self.ptr = self.row = self.col = 0


def text_bytes(v):
    s = apl64.format_value(v)
    return bytes(ord(c) for c in s) if v.t == apl64.CHAR else s.replace('¯', '\x90').encode('latin-1')


def expected_screen(lines, with_scrolls=False):
    scr, model = Screen(), apl64.Interp()
    for line in lines:
        scr.write(apl64.encode_line(model.prompt()) + apl64.encode_line(line) + b"\n")
        try:
            for v in model.run_values(line):
                scr.write(text_bytes(v) + b"\n")
        except apl64.AplError as e:
            for v in getattr(e, "outs", []):
                scr.write(text_bytes(v) + b"\n")
            scr.write(e.kind.encode() + b"\n")
    return (bytes(scr.mem), scr.scrolls) if with_scrolls else bytes(scr.mem)


def checkpoints():
    """Prefixes of the session: the longest that never scrolls, one that has scrolled once, and all of it.

    Once the screen is full every newline scrolls, which resets the cursor exactly, so only the
    short sessions can see bugs in the ordinary newline and wrap arithmetic.
    """
    cuts = {}
    for n in range(1, len(LINES) + 1):
        _, k = expected_screen(LINES[:n], with_scrolls=True)
        cuts.setdefault(k, n)                       # the first prefix with k scrolls
    last_zero = max(n for n in range(1, len(LINES) + 1) if expected_screen(LINES[:n], with_scrolls=True)[1] == 0)
    return sorted({last_zero, cuts.get(1, len(LINES)), cuts.get(2, len(LINES)), len(LINES)})


def build_selftest(lines):
    data = ["selftest_data:", f"        .byte {len(lines)}"]
    for line in lines:
        enc = apl64.encode_line(line)
        assert len(enc) < 256
        data.append(f"        .byte {len(enc)}" + "".join(f", {b}" for b in enc))
    with open(scratch("selftest_data.inc"), "w") as f:
        f.write("\n".join(data) + "\n")
    r = subprocess.run(["64tass", "-D", "SELFTEST=1", "-D", "KEYTEST=0", "-I", os.path.dirname(scratch()),
                        "--labels=" + scratch("selftest.lbl"), "-o", scratch("selftest.prg"), "asm/eval.asm"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    labels = {}
    for line in open(scratch("selftest.lbl")):
        m = re.match(r"(\S+)\s*=\s*(\$[0-9a-fA-F]+|\d+)\s*$", line)
        if m:
            v = m.group(2)
            labels[m.group(1)] = int(v[1:], 16) if v[0] == "$" else int(v)
    return labels


def check_session(lines, full):
    L = build_selftest(lines)
    script = ['save "{DIR}/screen.bin" 0 cc00 cfe7', 'save "{DIR}/zp.bin" 0 0000 00ff',
              f'save "{{DIR}}/hth.bin" 0 {L["HTH"]:04x} {L["HTH"] + 255:04x}',
              'save "{DIR}/low.bin" 0 0280 03ff', 'bank ram', 'save "{DIR}/charset.bin" 0 d000 d7ff',
              'bank io', 'save "{DIR}/vic.bin" 0 d000 d02e', 'save "{DIR}/cia2.bin" 0 dd00 dd0f', 'bank cpu']
    _, files = _run_selftest(script, hex(L["selftest_done"]))
    screen = files["screen.bin"][2:]
    want = expected_screen(lines)
    if screen != want:
        for r in range(25):
            a, b = screen[r * 40:r * 40 + 40], want[r * 40:r * 40 + 40]
            if a != b:
                print(f"row {r}\n  vice  {a!r}\n  model {b!r}")
        raise AssertionError(f"screen differs from the model after {len(lines)} lines")
    if not full:
        return
    chargen = open("roms/chargen.bin", "rb").read()
    assert files["charset.bin"][2:] == expected_charset(chargen), "the charset RAM is not what the start-up code should build"
    vic, cia2, zp, low = files["vic.bin"][2:], files["cia2.bin"][2:], files["zp.bin"][2:], files["low.bin"][2:]
    assert vic[0x18] & 0xFE == 0x34, f"VIC $D018 = {vic[0x18]:02x}: screen at $CC00, charset at $D000 expected"   # bit 0 reads as 1
    assert vic[0x20] & 0x0F == L["COLOR_BORDER"] and vic[0x21] & 0x0F == L["COLOR_BG"], "VIC border/background colours"
    assert cia2[0] & 3 == 0, "CIA2: VIC bank is not 3"
    assert zp[1] & 7 == 6, f"CPU port {zp[1]:02x}: BASIC should be out, KERNAL and I/O in"
    assert zp[0xCC] == 1 and low[0x0291 - 0x0280] == 0x80, "KERNAL cursor blink / charset switching not disabled"
    nmi = low[0x0318 - 0x0280] | low[0x0319 - 0x0280] << 8
    assert nmi == L["nmi_handler"], "NMI vector not patched"
    assert zp[0xA2] > 0 or zp[0xA1] > 0, "the KERNAL interrupt is not running (jiffy clock stopped)"
    spilled = [h for h, v in enumerate(files["hth.bin"][2:]) if v == 0xFF]
    assert spilled, "the session holds more array data than the heap, so some array should be in the REU: none is"
    print(f"screen: {len(spilled)} arrays were in the REU at the end of the session (real DMA)")




EDGE_SESSIONS = [
    ["1"] * 12,                                   # fills rows 0-23 exactly, cursor on row 24
    ["1"] * 12 + ["2"],                           # the prompt is on row 24: the next newline scrolls
    ["1"] * 13,
    ["1"] * 14,
    ["'" + "x" * 32 + "'"],                       # the prompt line is exactly 40 columns
    ["'" + "x" * 31 + "'", "'" + "x" * 33 + "'", "'" + "x" * 34 + "'"],   # 39, 41 and 42 columns
    ["'" + "y" * 40 + "'", "'z'"],                # the output line is exactly 40 columns
    ["⍳13", "⍳14", "1 2 3"],                      # a value line of 39 and 40 characters
    ["1"] * 11 + ["'" + "q" * 60 + "'", "3"],     # wrapping at the bottom of the screen
]


def test_session():
    for lines in EDGE_SESSIONS:
        check_session(lines, full=False)
    cuts = checkpoints()
    for n in cuts:
        check_session(LINES[:n], full=(n == len(LINES)))
    print(f"screen: {len(EDGE_SESSIONS)} edge sessions (exact-fit rows, 40-column lines, scrolling once and twice) and the "
          f"{len(LINES)}-line session all match the model on the real machine; charset RAM, VIC bank 3, NMI patch and IRQ verified")


def _run_selftest(script, initbreak, prg=None):
    import tempfile
    prg = prg or scratch("selftest.prg")
    with tempfile.TemporaryDirectory() as d:
        mon = os.path.join(d, "mon.txt")
        with open(mon, "w") as f:
            f.write("\n".join(l.replace("{DIR}", d) for l in script) + "\nquit\n")
        cmd = ["x64sc", "-default", "+saveres", "-console", "-silent", "+sound", "-warp", "-kernal", "roms/kernal.bin", "-basic",
               "roms/basic.bin", "-chargen", "roms/chargen.bin", "-autostartprgmode", "1", "-initbreak", initbreak,
               "-limitcycles", "400000000", "-autostart", prg, "-moncommands", mon, "-reu", "-reusize", "4096"]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        files = {n: open(os.path.join(d, n), "rb").read() for n in os.listdir(d) if n != "mon.txt"}
        return r.stdout + r.stderr, files


if __name__ == "__main__":
    if not all(os.path.exists("roms/" + r) for r in ROMS):
        print("screen: skipped (no C64 ROMs in roms/)")
    elif subprocess.run(["which", "x64sc"], capture_output=True).returncode:
        print("screen: skipped (x64sc not installed)")
    else:
        test_session()
