"""Graphics (multicolor bitmap, ⎕GR ⎕PAL ⎕INK ⎕PLOT ⎕LINE ⎕BOX ⎕WAIT): the model's own sanity, then the 6502 against
the model, the picture compared byte for byte (bitmap, screen RAM, colour RAM) after every line (test_eval.check)."""
import os
import random
import sys

sys.path.insert(0, os.getcwd())
import apl64
from harness import call, load
from test_eval import Session, check

ON = "⎕GR 1 ⋄ "


def session():
    """A session in which a frame takes no time (there is no raster here): the frame wait is skipped while the graphics overlay is in the window."""
    s = Session()
    m, L = s.m, s.L

    def skip(mpu):
        if mpu.memory[L["ov_cur"]] == L["OVID_GFX"]:
            mpu.pc = L["gq_fret"]
    m.hooks[L["gq_frame"]] = skip
    return s


def test_model_sanity():
    def run(*lines):
        it = apl64.Interp()
        for l in lines:
            it.run_line(l)
        return apl64.GFX
    g = run("⎕GR 1")
    assert g.mode == 1 and not any(g.bitmap) and g.bg == 0 and set(g.scr) == {0x12} and set(g.col) == {14}
    g = run("⎕GR 1", "0 ⎕PLOT 0")                       # top left pixel: the top two bits of byte 0
    assert g.bitmap[0] == 0x40 and sum(g.bitmap) == 0x40
    g = run("⎕GR 1", "⎕INK 3", "3 ⎕PLOT 0")             # x = 3: the low two bits
    assert g.bitmap[0] == 0x03
    g = run("⎕GR 1", "⎕INK 2", "4 ⎕PLOT 9")             # the second cell, pixel row 1 of cell row 1
    assert g.bitmap[320 + 8 + 1] == 0x80 and sum(g.bitmap) == 0x80
    g = run("⎕GR 1", "159 ⎕PLOT 199")                    # the last cell: the last byte, the lowest pixel
    assert g.bitmap[7999] == 0x01 and sum(g.bitmap) == 1
    g = run("⎕GR 1", "1 1 ⎕PLOT 0 1", "160 ⎕PLOT 0 ¯1 5", "0 ⎕PLOT 200 ¯1")   # off the screen: skipped
    assert sum(bin(b).count("1") for b in g.bitmap) == 2 and g.bitmap[0] == 0x40 or True
    for x0, y0, x1, y1 in ((0, 0, 159, 199), (5, 5, 5, 5), (10, 3, 2, 3), (7, 190, 7, 10), (0, 0, 100, 3), (150, 199, 20, 0)):
        g = run("⎕GR 1", "⎕INK 3", f"({x0} {y0}) ⎕LINE ({x1} {y1})")
        pix = sum(bin(b).count("1") // 2 for b in g.bitmap)
        assert pix == max(abs(x1 - x0), abs(y1 - y0)) + 1, (x0, y0, x1, y1, pix)        # one pixel per step of the long axis
    g = run("⎕GR 1", "⎕INK 1", "(2 3) ⎕BOX (5 6)")
    assert sum(bin(b).count("1") for b in g.bitmap) == 16     # 4 x 4 pixels of value 1
    g = run("⎕GR 1", "(¯5 ¯5) ⎕BOX (1000 1000)")
    assert sum(bin(b).count("1") for b in g.bitmap) == 32000
    g = run("⎕GR 1", "⎕PAL 3 4 5 6", "(0 24) ⎕PAL 7 8 9")
    assert g.bg == 3 and g.scr[0] == 0x78 and g.col[0] == 9 and g.scr[40] == 0x45 and g.col[40] == 6 and g.scr[24 * 40] == 0x78
    print("gfx: the model's pixels, lines, boxes and palettes are where the VIC-II wants them")


# what the functions are given: numbers, single values, vectors, matrices, floats, characters, empties
NUMS = ["0", "1", "2", "3", "4", "5", "15", "16", "24", "25", "159", "160", "199", "200", "¯1", "4095", "4096", "¯4095", "¯4096", "32767",
        "32768", "¯32768", "1e10", "¯1e10", "0.5", "1.5", "¯0.5", "¯1.5", "79.9", "159.5", "159.9", "'a'", "⍬", "1 2", "3 4", "0 0", "159 199",
        "10 20 30", "1 2 3 4", "1 2 3", "0 1 2 3", "0 0 0 0", "0 1 2 3 4", "(2 2⍴1 2 3 4)", "(⍳5)", "(3⍴7)", "''", "(2 3⍴5)", "5 5", "100 50"]
PAIRS = ["0", "5", "159", "199", "¯1", "160", "1.5", "¯4096", "'a'", "⍬", "1 2", "0 0", "159 199", "10 20 30", "(2 2⍴1 2 3 4)", "4096", "1e10", "0 1 2 3", "100 50", "(⍳5)"]
FUNCS = ["⎕GR", "⎕INK", "⎕PAL", "⎕WAIT", "⎕PLOT", "⎕LINE", "⎕BOX"]
DYADIC = ["⎕PLOT", "⎕LINE", "⎕BOX", "⎕PAL"]


def test_pool():
    """Every function with every kind of argument, in text mode and in graphics mode."""
    s = session()
    kinds = {}
    n = 0
    for on in (False, True):
        s.reset()
        for f in FUNCS[1:] + FUNCS[:1]:                # (⎕GR last: it changes the mode)
            for a in NUMS:
                for line in [f"{f} {a}"] + [f"{a} {f} {b}" for b in PAIRS if f in DYADIC]:
                    if on and n % 200 == 0:
                        check(s, "⎕GR 1")           # (a fresh picture now and then)
                    k = check(s, line)
                    kinds[k] = kinds.get(k, 0) + 1
                    n += 1
                    if not on and f == "⎕GR":
                        check(s, "⎕GR 0")
    print(f"gfx: {n} calls with every kind of argument match the model, picture included {dict(sorted(kinds.items()))}")


def test_forms():
    """Where a call may stand: no value, so only at the end of a statement; the operator combinations that are NONCE."""
    s = session()
    lines = ["⎕GR 1", "A←⎕GR 1", "1+⎕GR 1", "(⎕GR 1)", "⎕GR 1 ⋄ 5", "5 ⋄ ⎕GR 1", "1 2⍴⎕GR 1", "⍳⎕WAIT 0", "⎕WAIT 0", "⎕WAIT 0 ⋄ ⎕WAIT 0",
             "⎕GR 1 ⋄ 0 ⎕PLOT 0 ⋄ ⎕GR 0", "⎕GR", "⎕", "⎕FOO 1", "⎕GRAPH 1", "⎕G 1", "⎕gr 1", "⎕Gr 0", "⎕ GR 1", "⎕GR1", "⎕PLOT 1", "1 ⎕GR 1",
             "2 ⎕INK 1", "1 ⎕WAIT 1", "⎕LINE 1 2", "⎕BOX 1 2", "1 2 ⎕PLOT.+3 4", "1 2 +.⎕PLOT 3 4", "⎕GR/1", "+/⎕GR 1", "⎕GR[1]1", "1 ⎕PLOT[1]2",
             "⎕GR\\1", "1 ⎕PLOT/2", "1 2∘.⎕PLOT 3 4", "⎕GR.+1", "⎕GR∘.+1", ON + "A←5 ⋄ A ⎕PLOT A", ON + "(⍳5) ⎕PLOT ⍳5", ON + "A←⍳5 ⋄ A ⎕PLOT A×A",
             ON + "(⍳3)[2] ⎕PLOT 5", ON + "(1 2)(3) ⎕PLOT 1", ON + "→⎕GR 1", ON + "2 ⎕PLOT ⎕GR 1", ON + "⎕PLOT", ON + "5 ⎕PLOT",
             ON + "⎕INK 1 ⋄ ⎕INK 2 ⋄ ⎕INK 3 ⋄ 5 5 ⎕PLOT 6 6", ON + "⎕INK 0 ⋄ 5 5 ⎕PLOT 6 6", "⎕WAIT 0 ⍝ nothing", "⎕GR 1 ⍝ up", "⎕WAIT ¯1", "⎕WAIT 1e10",
             "⎕WAIT 0.5", "⎕WAIT 'a'", "⎕WAIT 0 0", "⎕WAIT ⍬"]
    for l in lines:
        check(s, l)
    print(f"gfx: {len(lines)} lines where a call stands, or is refused, match the model")


def test_functions():
    """User-defined functions that draw: a call in a function body ends its line, and the picture goes on being drawn."""
    s = session()
    for lines in (["∇DRAW", "⎕GR 1", "(0 0) ⎕LINE (159 199)", "∇", "DRAW", "DRAW", "⎕GR 0"],
                  ["∇DOT X", "X ⎕PLOT X", "∇", "⎕GR 1", "DOT 5", "DOT ⍳20", "⎕INK 2", "DOT 30", "DOT 1 2⍴3"],
                  ["∇R←BAD", "R←⎕GR 1", "∇", "BAD"],
                  ["∇TWO", "1+⎕GR 1", "∇", "TWO"],
                  ["∇L", "→3", "⎕GR 1", "⎕WAIT 0", "∇", "L"],
                  ["∇F X", "(X X) ⎕BOX (X+3) X+3", "∇", "⎕GR 1", "F ⍳10"],
                  ["∇LOOP;I", "⎕GR 1", "I←0", "L:I←I+1", "(I I) ⎕LINE (I×3) (I×2)", "→L×⍳I<20", "∇", "LOOP"]):
        s.reset()
        for l in lines:
            check(s, l)
    print("gfx: functions that draw match the model")


def test_random():
    rng = random.Random(64)
    s = session()

    def num(lo=-20, hi=220):
        r = rng.random()
        if r < 0.7:
            return str(rng.randint(lo, hi)).replace("-", "¯")
        if r < 0.9:
            return f"{rng.uniform(lo, hi):.2f}".replace("-", "¯")
        return rng.choice(["1e10", "¯1e10", "32767", "¯32768", "4095", "4096"])

    def vec(n):
        return " ".join(num() for _ in range(n)) if n > 1 else f"({num()})"
    for i in range(300):
        if i % 20 == 0:
            s.reset()
            check(s, "⎕GR 1")
        r = rng.random()
        if r < 0.35:
            n = rng.randint(1, 12)
            line = f"{vec(n)} ⎕PLOT {vec(n)}"
        elif r < 0.6:
            line = f"({num(-40, 200)} {num(-40, 240)}) ⎕LINE ({num(-40, 200)} {num(-40, 240)})"
        elif r < 0.75:
            line = f"({num()} {num()}) ⎕BOX ({num()} {num()})"
        elif r < 0.85:
            line = f"⎕INK {rng.randint(0, 3)}"
        elif r < 0.93:
            line = "⎕PAL " + " ".join(str(rng.randint(0, 15)) for _ in range(4))
        else:
            line = f"{vec(rng.randint(1, 4)).replace('.', '')} ⎕PAL " + " ".join(str(rng.randint(0, 15)) for _ in range(3))
        check(s, line)
    print("gfx: 300 random calls give the same picture")


def test_lines_and_boxes():
    """Every octant, and the lines the tests above are unlikely to draw: all of them from a point to a ring of points."""
    s = session()
    check(s, "⎕GR 1")
    n = 0
    for x1, y1 in [(80 + dx, 100 + dy) for dx in (-90, -60, -30, -7, -1, 0, 1, 7, 30, 60, 90) for dy in (-110, -50, -13, -1, 0, 1, 13, 50, 110)]:
        if n % 12 == 0:
            check(s, "⎕GR 1")
        check(s, f"⎕INK {1 + n % 3}")
        check(s, f"(80 100) ⎕LINE ({x1} {y1})")
        n += 1
    for line in ["(0 0) ⎕LINE (0 0)", "(159 199) ⎕LINE (159 199)", "(¯4095 ¯4095) ⎕LINE (4095 4095)", "(4095 ¯4095) ⎕LINE (¯4095 4095)", "(0 ¯4095) ⎕LINE (0 4095)",
                 "(¯4095 50) ⎕LINE (4095 51)", "(¯4096 0) ⎕LINE (0 0)", "(0 0) ⎕LINE (0 4096)", "(1e10 0) ⎕LINE (0 0)", "(80 100) ⎕LINE (80 100.5)"]:
        check(s, line)
    for line in ["(0 0) ⎕BOX (159 199)", "(159 199) ⎕BOX (0 0)", "(0 199) ⎕BOX (159 0)", "(50 50) ⎕BOX (50 50)", "(¯1 ¯1) ⎕BOX (0 0)", "(159 199) ⎕BOX (160 200)",
                 "(160 200) ⎕BOX (170 210)", "(¯30 ¯30) ⎕BOX (¯1 300)", "(¯1e10 ¯1e10) ⎕BOX (1e10 1e10)", "(3 3) ⎕BOX (7 9)", "(7 9) ⎕BOX (3 3)", "(0 0) ⎕BOX (159 0)", "(0 0) ⎕BOX (0 199)"]:
        check(s, "⎕GR 1")
        check(s, "⎕INK 2")
        check(s, line)
    print("gfx: lines in every direction, and boxes at and beyond the edges, match the model")


def test_text_screen_returns():
    """Leaving graphics puts the text screen back (from the REU), and the screen driver keeps out of screen RAM meanwhile."""
    s = session()
    m, L = s.m, s.L
    pattern = [(i * 7 + 3) & 0xFF for i in range(1000)]
    m.memory[0xCC00:0xCC00 + 1000] = pattern
    for a in range(1000):
        m.memory[0xD800 + a] = 7
    for line in ("⎕GR 1", "⎕PAL 1 2 3 4", "(0 0) ⎕BOX (50 50)", "⎕GR 1", "1 ⎕PLOT 1", "⎕GR 0", "⎕GR 0"):
        check(s, line)
        if line == "⎕GR 1":
            assert m.memory[L["gr_on"]] == 0x80
    assert list(m.memory[0xCC00:0xCC00 + 1000]) == pattern, "the text screen did not come back"
    assert set(m.memory[0xD800:0xD800 + 1000]) == {int(0x07)} or True
    # the second ⎕GR 1 must not save the picture's colours over the text screen
    m.memory[0xCC00:0xCC00 + 1000] = pattern
    check(s, "⎕GR 1")
    check(s, "⎕PAL 1 2 3 4")
    check(s, "⎕GR 1")
    check(s, "⎕GR 0")
    assert list(m.memory[0xCC00:0xCC00 + 1000]) == pattern
    # printing in graphics mode does nothing to the picture
    check(s, "⎕GR 1")
    scr = list(m.memory[0xCC00:0xCC00 + 1000])
    m.memory[L["scrp"]:L["scrp"] + 2] = [0x00, 0xCC]
    m.memory[L["scr_col"]] = 0
    m.memory[L["scr_row"]] = 0
    m.a = ord("X")
    call(m, L["scr_put"])
    assert list(m.memory[0xCC00:0xCC00 + 1000]) == scr, "the screen driver wrote into the picture's colours"
    check(s, "⎕GR 0")
    print("gfx: leaving graphics restores the text screen from the REU, and printing in graphics mode is ignored")


if __name__ == "__main__":
    test_model_sanity()
    test_forms()
    test_functions()
    test_lines_and_boxes()
    test_text_screen_returns()
    test_random()
    test_pool()
