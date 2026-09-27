"""Graphics on the real machine (VICE): a scripted session draws, and what the VIC-II shows is compared with the model.

The keys of a test build type the lines (the quad functions after the pound key, ⎕ = pound L). The run stops where the
REPL waits for the key that ends the picture; then the bitmap, screen RAM, colour RAM and VIC-II registers are saved
from VICE, and so is a screenshot: every pixel of the picture (as the model has it) must have the same colour on the screen
as every other pixel of its palette colour, and different colours must look different. A last session leaves graphics
mode and checks the text screen comes back. Skipped without the C64 ROMs in roms/ or without VICE.
"""
import os
import subprocess
import sys
import zlib

sys.path.insert(0, os.getcwd())
sys.path.insert(0, "tools")
import apl64
from harness import scratch
from test_keys import build_keytest, petscii
from test_screen import _run_selftest
from test_vice import ROMS

Q = "{P}L"


KEYS = {"⍉": "{P}t", "⎕": "{P}L", "⋄": "{P}.", "⍳": "{P}i", "○": "{P}o", "×": "{P}-", "÷": "{P}=", "⍴": "{P}r", "←": "{LA}", "⌊": "{P}d", "¯": "{P}2"}


def quad(text):
    """'⎕GR 1 ⋄ 5' -> the keys that type it: ⎕ is the pound key and L, ⋄ the pound key and a period."""
    return "".join(KEYS.get(c, c) for c in text)


def png_pixels(data):
    """(width, height, rows of RGB tuples) of a non-interlaced 8-bit PNG (VICE writes palette or truecolour images)."""
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    pos, chunks = 8, []
    while pos < len(data):
        n = int.from_bytes(data[pos:pos + 4], "big")
        chunks.append((data[pos + 4:pos + 8], data[pos + 8:pos + 8 + n]))
        pos += 12 + n
    ihdr = next(c for t, c in chunks if t == b"IHDR")
    w, h, depth, ctype, _, _, inter = int.from_bytes(ihdr[:4], "big"), int.from_bytes(ihdr[4:8], "big"), ihdr[8], ihdr[9], 0, 0, ihdr[12]
    assert depth == 8 and inter == 0 and ctype in (2, 3, 6), (depth, ctype, inter)
    plte = next((c for t, c in chunks if t == b"PLTE"), None)
    raw = zlib.decompress(b"".join(c for t, c in chunks if t == b"IDAT"))
    bpp = {2: 3, 3: 1, 6: 4}[ctype]
    stride, prev, rows, p = w * bpp, bytearray(w * bpp), [], 0
    for _ in range(h):
        f = raw[p]
        line = bytearray(raw[p + 1:p + 1 + stride])
        p += 1 + stride
        for i in range(stride):
            a = line[i - bpp] if i >= bpp else 0
            b = prev[i]
            c = prev[i - bpp] if i >= bpp else 0
            if f == 1:
                line[i] = (line[i] + a) & 255
            elif f == 2:
                line[i] = (line[i] + b) & 255
            elif f == 3:
                line[i] = (line[i] + ((a + b) >> 1)) & 255
            elif f == 4:
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                line[i] = (line[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        prev = line
        if ctype == 3:
            rows.append([tuple(plte[3 * v:3 * v + 3]) for v in line])
        else:
            rows.append([tuple(line[i:i + 3]) for i in range(0, stride, bpp)])
    return w, h, rows


def run(text, dump_screen=True):
    keys = petscii(text)
    L = build_keytest(keys)
    script = ['bank ram', 'save "{DIR}/bmp.bin" 0 e000 ff3f', 'bank default', 'save "{DIR}/vic.bin" 0 d000 d02e',
              'save "{DIR}/scr.bin" 0 cc00 cfe7', 'save "{DIR}/col.bin" 0 d800 dbe7', 'screenshot "{DIR}/shot.png" 2']
    out, files = _run_selftest(script, hex(L["selftest_done"]), prg=scratch("keytest.prg"))
    assert "shot.png" in files and "bmp.bin" in files, out[-400:]
    return {k: (v[2:] if k != "shot.png" else v) for k, v in files.items()}


def model_picture(lines):
    it = apl64.Interp()
    apl64.gfx_reset()
    for l in lines:
        it.run_line(l)
    return apl64.GFX


def colour_grid(g):
    """The colour number (0-15) the model's picture shows at each of its 160 x 200 pixels."""
    grid = []
    for y in range(200):
        row = []
        for x in range(160 if g.mode == 1 else 320):
            if g.mode == 1:
                v = g.bitmap[(y >> 3) * 320 + (x >> 2) * 8 + (y & 7)] >> (6 - 2 * (x & 3)) & 3
                cell = (y >> 3) * 40 + (x >> 2)
                row.append((g.bg, g.scr[cell] >> 4, g.scr[cell] & 15, g.col[cell] & 15)[v])
            else:
                v = g.bitmap[(y >> 3) * 320 + (x >> 3) * 8 + (y & 7)] >> (7 - (x & 7)) & 1
                cell = (y >> 3) * 40 + (x >> 3)
                row.append((g.scr[cell] & 15, g.scr[cell] >> 4)[v])
        grid.append(row)
    return grid


def check_picture(name, lines):
    assert len(" ⋄ ".join(lines)) < 250, "the line must fit the input buffer (255 characters)"
    text = quad(" ⋄ ".join(lines)) + "{RET}"
    files = run(text)
    g = model_picture(lines)
    assert g.mode in (1, 2)
    vic = files["vic.bin"]
    assert vic[0x11] & 0x20 and (vic[0x16] & 0x10 != 0) == (g.mode == 1) and vic[0x18] & 0x0F in (0x8, 0x9), (vic[0x11], vic[0x16], vic[0x18])
    assert vic[0x20] & 15 == g.bg and vic[0x21] & 15 == g.bg
    assert files["bmp.bin"] == bytes(g.bitmap), f"{name}: the bitmap differs from the model's"
    assert files["scr.bin"][:1000] == bytes(g.scr), f"{name}: screen RAM differs"
    if g.mode == 1:
        assert [b & 15 for b in files["col.bin"][:1000]] == list(g.col), f"{name}: colour RAM differs"
    w, h, rows = png_pixels(files["shot.png"])
    ox, oy = 32, 35          # where the 320 x 200 picture starts in VICE 3.9's 384 x 272 PAL screenshot (measured: it is not centred)
    assert (w, h) == (384, 272), (w, h)
    seen, bad = {}, 0
    for y, grow in enumerate(colour_grid(g)):
        for x, c in enumerate(grow):
            px = rows[oy + y][ox + (2 * x if g.mode == 1 else x)]
            if g.mode == 1:
                assert px == rows[oy + y][ox + 2 * x + 1], f"{name}: pixel {x},{y} is not double width"
            if seen.setdefault(c, px) != px:
                bad += 1
    assert not bad, f"{name}: {bad} pixels of the screenshot show the wrong colour"
    assert len(set(seen.values())) == len(seen), f"{name}: two palette colours look the same {seen}"
    return len(seen)


def test_pictures():
    n = 0
    n += check_picture("lines", ["⎕GR 1", "⎕PAL 0 1 2 3", "(0 0) ⎕LINE (159 199)", "(159 0) ⎕LINE (0 199)", "⎕INK 2", "(20 20) ⎕BOX (60 60)"])
    n += check_picture("colours", ["⎕GR 1", "⎕PAL 6 1 2 3", "(0 24) ⎕PAL 7 8 9", "(¯1+⍳25) ⎕PAL ⍉3 25⍴(25⍴15),(25⍴14),25⍴13", "⎕INK 1", "(0 0) ⎕BOX (39 199)",
                                     "⎕INK 2", "(40 0) ⎕BOX (79 199)", "⎕INK 3", "(80 0) ⎕BOX (119 199)"])
    n += check_picture("rows", ["⎕GR 1", "⎕PAL 6 1 2 3", "(5 10 11) ⎕PAL 15 14 13", "⎕INK 1", "(0 0) ⎕BOX (159 199)", "⎕INK 0", "(0 100) ⎕LINE (159 101)", "⎕INK 3",
                                "(10 20 30 40) ⎕PLOT 100 101 102 103", "⎕INK 2", "(50 50) ⎕BOX (70 150)"])
    n += check_picture("plot", ["⎕GR 1", "⎕PAL 0 5 10 3", "⎕INK 1", "(⍳150) ⎕PLOT 100+50×2○(⍳150)÷10", "⎕INK 2", "(⍳150) ⎕PLOT 100+50×1○(⍳150)÷10"])
    n += check_picture("hires", ["⎕GR 2", "⎕PAL 6 1", "(¯1+⍳25) ⎕PAL ⍉2 25⍴(25⍴2),(25⍴7)", "(0 0) ⎕LINE (319 199)", "(319 0) ⎕LINE (0 199)", "(100 50) ⎕BOX (219 150)", "⎕INK 0",
                                 "(120 60) ⎕BOX (199 140)", "⎕INK 1", "(⍳300) ⎕PLOT 100+90×1○(⍳300)÷20"])
    print(f"gfx vice: 5 pictures drawn by scripted keys match the model in the bitmap, screen RAM, colour RAM, VIC-II registers and the screenshot ({n} colours checked)")


def test_text_returns():
    """A picture ends at a key; the text screen is then as it was."""
    files = run("1+1{RET}" + quad("⎕GR 1 ⋄ (0 0) ⎕BOX (9 9)") + "{RET}{$20}")
    vic, scr = files["vic.bin"], files["scr.bin"][:1000]
    assert vic[0x11] & 0x20 == 0 and vic[0x16] & 0x10 == 0 and vic[0x18] & 0x0F in (0x4, 0x5), (vic[0x11], vic[0x16], vic[0x18])
    assert vic[0x20] & 15 == 6 and vic[0x21] & 15 == 6
    assert set(b & 15 for b in files["col.bin"][:1000]) == {7}, "the text colour did not come back"
    rows = [scr[r * 40:r * 40 + 40] for r in range(25)]
    text = [bytes(apl64.encode_line(t)).ljust(40, b" ") for t in ("      1+1", "2", "      ⎕GR 1 ⋄ (0 0) ⎕BOX (9 9)")]
    text.append(b"      \x7f".ljust(40, b" "))                                  # the prompt, with the cursor
    assert rows[:4] == text and all(r == b" " * 40 for r in rows[4:]), [r for r in rows[:6]]
    print("gfx vice: after the picture a key brings the text screen back, with its colours and the prompt")


def test_sound_and_keys():
    """⎕SND writes the SID's registers (VICE lets the monitor read them back), ⎕KEY takes the next key: here the scripted one."""
    lines = ["1 ⎕SND 4000 1 0 9 15 5 1000", "2 ⎕SND 300 8", "⎕SND 12", "A←⎕KEY 60", "A"]
    text = quad(" ⋄ ".join(lines)) + "{RET}Q"
    keys = petscii(text)
    L = build_keytest(keys)
    out, files = _run_selftest(['save "{DIR}/scr.bin" 0 cc00 cfe7', 'save "{DIR}/sid.bin" 0 d400 d418'], hex(L["selftest_done"]), prg=scratch("keytest.prg"))
    apl64.gfx_reset()
    it = apl64.Interp()
    for l in lines[:3]:
        it.run_line(l)
    assert files["sid.bin"][2:] == bytes(apl64.GFX.sid), (files["sid.bin"][2:].hex(), bytes(apl64.GFX.sid).hex())
    rows = [files["scr.bin"][2:][r * 40:r * 40 + 40] for r in range(4)]
    assert rows[2].rstrip() == b"209", rows          # the shifted Q, as GETIN gives it
    print("gfx vice: ⎕SND leaves the SID registers as the model says, and ⎕KEY returns the scripted key")


if __name__ == "__main__":
    if not all(os.path.exists("roms/" + r) for r in ROMS):
        print("gfx vice: skipped (no C64 ROMs in roms/)")
    elif subprocess.run(["which", "x64sc"], capture_output=True).returncode:
        print("gfx vice: skipped (x64sc not installed)")
    else:
        test_pictures()
        test_text_returns()
        test_sound_and_keys()
