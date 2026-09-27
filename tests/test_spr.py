"""Sprites (⎕SPD ⎕SPR ⎕SPC): the 6502 against the model; the sprite registers, pointers and shapes compared after every line."""
import os
import random
import sys

sys.path.insert(0, os.getcwd())
import apl64
from test_eval import Session, check


class Sprites(Session):
    def __init__(self):
        super().__init__()
        self.check_spr = True
        L = self.L
        self.m.hooks[L["GQ_FRAME3"]] = lambda mpu: setattr(mpu, "pc", L["GQ_FRET3"]) if mpu.memory[L["ov_cur"]] == L["OVID_SPR"] else None     # (no raster here: a frame takes no time)
        self.reset()

    def reset(self):
        super().reset()
        if hasattr(self, "m"):
            m = self.m.memory
            m[0xD000:0xD030] = bytes(0x30)
            m[0xCFF8:0xD000] = bytes(range(96, 104))
            m[0xD800:0xD800 + 1792] = bytes(1792)


def test_model_sanity():
    it = apl64.Interp()
    apl64.gfx_reset()
    for l in ["0 ⎕SPD 21 24⍴1", "1 ⎕SPD 21 12⍴0 1 2 3", "2 ⎕SPD ⍳63", "0 ⎕SPR 0 0", "1 ⎕SPR 300 100 1 5 15", "⎕SPC 2 3"]:
        it.run_line(l)
    g = apl64.GFX
    assert g.shapes[:64] == bytes([255] * 63) + b"\0"
    assert g.shapes[64:67] == bytes([0b00011011] * 3)                   # 0 1 2 3 across a row, two bits each
    assert g.shapes[128:131] == bytes([1, 2, 3])
    assert g.vic[0:2] == bytes([24, 50]) and g.vic[2:4] == bytes([(300 + 24) & 255, 150]) and g.vic[0x10] == 2 and g.vic[0x15] == 3
    assert g.ptr[1] == 97 and g.vic[0x28] == 5 and g.vic[0x1C] == 2 and g.vic[0x1D] == 2 and g.vic[0x17] == 2 and g.vic[0x1B] == 2
    assert g.vic[0x25:0x27] == bytes([2, 3])
    print("spr: the model's shapes, positions and flags land in the VIC-II's registers")


NUMS = ["0", "1", "7", "8", "27", "28", "31", "¯1", "¯24", "¯25", "255", "256", "487", "488", "205", "206", "¯50", "¯51", "1.5", "2.0", "1e10", "'a'", "⍬", "1 2", "1 2 3", "1 2 3 4", "1 2 3 4 5",
        "1 2 3 4 5 6", "100 60 0 7 0", "300 200 27 15 15", "¯24 ¯50 3 1 1", "487 205 0 0 8", "0 0 0 16", "0 0 28", "0 0 0 0 16", "(2 2⍴1)", "40 40 1 2 3.5", "40.9 40.2"]
SHAPES = ["21 24⍴1", "21 24⍴0", "21 24⍴(24⍴1 0),24⍴0 0 1", "21 12⍴⍳4", "21 12⍴1", "21 12⍴4", "21 24⍴2", "63⍴255", "63⍴256", "63⍴¯1", "⍳63", "62⍴1", "64⍴1", "63⍴1.5", "63⍴'a'", "20 24⍴1", "21 23⍴1",
          "21 25⍴1", "24 21⍴1", "5", "⍬", "(21 24⍴1)+0.5", "21 24⍴1.0", "(63⍴3)×⍳63", "21 12⍴3 2 1 0", "21 24⍴0 1 1 0 1 0 0 1"]


def test_pool():
    s = Sprites()
    kinds, n = {}, 0
    for f, args in (("⎕SPR", NUMS), ("⎕SPC", NUMS)):
        for a in args:
            if n % 30 == 0:
                s.reset()
            k = check(s, f"{f} {a}")
            kinds[k] = kinds.get(k, 0) + 1
            n += 1
    for slot in ["0", "1", "27", "28", "31", "¯1", "1 2", "'a'", "1.5", "2.0", "⍬", "(1 1⍴3)"]:
        for sh in SHAPES:
            if n % 30 == 0:
                s.reset()
            k = check(s, f"{slot} ⎕SPD {sh}")
            kinds[k] = kinds.get(k, 0) + 1
            n += 1
    for a in ["0", "1", "7", "8", "¯1", "1 2", "'a'", "1.5", "2.0", "⍬"]:
        for b in NUMS:
            if n % 30 == 0:
                s.reset()
            k = check(s, f"{a} ⎕SPR {b}")
            kinds[k] = kinds.get(k, 0) + 1
            n += 1
    MOVES = ["0 0", "100 50", "1 2 3 4", "10 20 30 40 50 60", "¯24 ¯50", "487 205", "488 205", "¯25 0", "0 206", "0 ¯51", "300 200 310 190", "1.5 2.5", "1 2 3", "'ab'", "⍬", "(2 2⍴1 2 3 4)",
             "(⍳20),⍳20", "(100+⍳30),50+⍳30", "300 20 0 0", "1e10 0", "5 5 5 5 5 5 5 5"]
    for a in ["0", "1", "7", "8", "¯1", "1 2", "'a'", "⍬"]:
        for b in MOVES:
            if n % 30 == 0:
                s.reset()
            k = check(s, f"{a} ⎕MOVE {b}")
            kinds[k] = kinds.get(k, 0) + 1
            n += 1
    for a in ["0 1 2", "0 1 1", "0 2 1", "0 3 0", "0 1 0", "0 4 0", "0 0 1", "0 1 ¯1", "0 1 3", "0 2 3", "1 1", "8 1 1", "0 1.9 1.1", "0 'a' 1", "0 1", "0 1 1 1", "2 1 2", "7 3 1"]:
        for b in ["10 20 30 40 50 60", "1 2 3 4 5 6", "1 2", "⍬", "(¯30 5 300 400 2 3)", "1 2 3 4", "(⍳10),⍳10", "300 300 300 20 20 20", "1 2 3 4 5 6 7"]:
            if n % 30 == 0:
                s.reset()
            k = check(s, f"{a} ⎕MOVE {b}")
            kinds[k] = kinds.get(k, 0) + 1
            n += 1
    for line in ["⎕MOVE 1 2", "⎕MOVE", "1 ⎕MOVE", "A←1 ⎕MOVE 1 2", "1+2 ⎕MOVE 1 2", "(0 ⎕MOVE 1 2)", "0 ⎕MOVE.+1 2", "⎕MOVE/1", "0 ⎕MOVE[1]1 2", "0 ⎕MOVE (1.5 2.5),100.9 60.2", "0 ⎕MOVE (⍳3),⍳3", "3 ⎕SPR 5 5 ⋄ 3 ⎕MOVE 300 60",
                 "2 ⎕MOVE 0 1 0 1 ⋄ ⎕SPR 4"]:
        s.reset()
        k = check(s, line)
        kinds[k] = kinds.get(k, 0) + 1
        n += 1
    for line in ["⎕SPD 1", "⎕SPD", "1 ⎕SPC 2", "0 ⎕SPR", "⎕SPR", "⎕SPC", "A←⎕SPR 3", "1+⎕SPR 3", "(⎕SPC 1 2)", "⎕SPR 255 ⋄ ⎕SPR 0", "1 ⎕SPR.+2", "⎕SPR/1", "⎕SPD.+1", "⎕SPC[1]1 2",
                 "3 ⎕SPD ⎕SPR 1", "⎕SPD∘.+1"]:
        s.reset()
        k = check(s, line)
        kinds[k] = kinds.get(k, 0) + 1
        n += 1
    print(f"spr: {n} calls with every kind of argument match the model, registers, pointers and shapes included {dict(sorted(kinds.items()))}")


def test_streams():
    rng = random.Random(6569)
    s = Sprites()
    for i in range(300):
        if i % 30 == 0:
            s.reset()
        r = rng.random()
        if r < 0.5:
            nums = [rng.randint(-24, 487), rng.randint(-50, 205), rng.randint(0, 27), rng.randint(0, 15), rng.randint(0, 15)]
            line = f"{rng.randint(0, 7)} ⎕SPR " + " ".join(map(str, nums[:rng.randint(2, 5)])).replace("-", "¯")
        elif r < 0.6:
            line = f"⎕SPR {rng.randint(0, 255)}"
        elif r < 0.7:
            line = f"⎕SPC {rng.randint(0, 15)} {rng.randint(0, 15)}"
        else:
            slot = rng.randint(0, 27)
            kind = rng.randint(0, 2)
            if kind == 0:
                line = f"{slot} ⎕SPD 21 24⍴" + " ".join(str(rng.randint(0, 1)) for _ in range(rng.choice((1, 2, 7, 24, 100))))
            elif kind == 1:
                line = f"{slot} ⎕SPD 21 12⍴" + " ".join(str(rng.randint(0, 3)) for _ in range(rng.choice((1, 2, 5, 12, 60))))
            else:
                line = f"{slot} ⎕SPD 63⍴" + " ".join(str(rng.randint(0, 255)) for _ in range(rng.choice((1, 3, 9, 63))))
        check(s, line)
    print("spr: 300 random sprites, positions and shapes give the registers the model says")


if __name__ == "__main__":
    test_model_sanity()
    test_pool()
    test_streams()
