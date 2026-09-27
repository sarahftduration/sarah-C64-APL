"""⎕SND (the SID's registers) and ⎕KEY (the keyboard): the 6502 against the model, the sound chip's registers compared after every line.

The keyboard is a list of key codes both sides take from: the model's own (apl64.GFX.keys) and, for the machine, KERNAL GETIN
replaced by a hook that pops them."""
import os
import random
import sys

sys.path.insert(0, os.getcwd())
import apl64
from test_eval import Session, check


class Keyed(Session):
    def __init__(self):
        super().__init__()
        m, L = self.m, self.L
        self.check_sid = True
        self.keys = []
        self.word("getkey_vec", L["kbd_getin"])

        def getin(mpu):
            mpu.a = self.keys.pop(0) if self.keys else 0
            mpu.pc = L["echo_none"]                     # (an rts)
        m.hooks[L["kbd_getin"]] = getin
        m.hooks[L["GQ_FRAME"]] = lambda mpu: setattr(mpu, "pc", L["GQ_FRET"]) if mpu.memory[L["ov_cur"]] == L["OVID_GFX"] else None

    def reset(self):
        super().reset()
        if hasattr(self, "m"):
            self.m.memory[0xD400:0xD400 + apl64.SID_REGS] = bytes(apl64.SID_REGS)
            self.set_keys([])

    def set_keys(self, keys):
        self.keys = list(keys)
        apl64.GFX.keys = list(keys)

    def run(self, line, keys=None):
        if keys is not None:
            self.set_keys(keys)
        r = check(self, line)
        assert self.keys == apl64.GFX.keys, f"{line!r}: keys left {self.keys}, model {apl64.GFX.keys}"
        return r


NUMS = ["0", "1", "2", "3", "4", "7", "15", "16", "1000", "4095", "4096", "32767", "32768", "65535", "65536", "¯1", "1.5", "2.0", "1e10", "'a'", "⍬", "1 2", "(2 2⍴1)"]


def test_snd_pool():
    s = Keyed()
    kinds, n = {}, 0
    for a in ["1", "2", "3", "0", "4", "¯1", "1 2", "'a'", "1.5", "2.0", "⍬"]:
        for b in NUMS + ["4000 1", "4000 1 0 9", "4000 1 0 9 15 5", "4000 1 0 9 15 5 1000", "4000 8 2 3 4 5 4095", "65535 15 15 15 15 15 4095", "0 0 0 0 0 0 0", "1 2 3", "1 2 3 4 5",
                        "1 2 3 4 5 6 7 8", "40000 15", "40000.0 15", "1 16", "1 2 3 16", "1 2 3 4 5 16", "1 2 3 4 5 6 4096", "1 ¯1", "1 1.5", "1 2 3 4 1.5 6", "100 'a'", "(2 2⍴1 2 3 4)", "3⍴7"]:
            if n % 40 == 0:
                s.reset()
            k = s.run(f"{a} ⎕SND {b}")
            kinds[k] = kinds.get(k, 0) + 1
            n += 1
    for b in NUMS + ["15 15", "7 ⋄ ⎕SND 0"]:
        s.reset()
        k = s.run(f"⎕SND {b}")
        kinds[k] = kinds.get(k, 0) + 1
        n += 1
    print(f"snd: {n} calls with every kind of argument match the model, registers included {dict(sorted(kinds.items()))}")


def test_snd_streams():
    rng = random.Random(6581)
    s = Keyed()
    for i in range(300):
        if i % 30 == 0:
            s.reset()
        r = rng.random()
        if r < 0.15:
            line = f"⎕SND {rng.randint(0, 15)}"
        else:
            nums = [rng.randint(0, 65535), rng.randint(0, 15), rng.randint(0, 15), rng.randint(0, 15), rng.randint(0, 15), rng.randint(0, 15), rng.randint(0, 4095)]
            n = rng.choice((1, 2, 4, 6, 7))
            line = f"{rng.randint(1, 3)} ⎕SND " + " ".join(map(str, nums[:n])) if n > 1 else f"{rng.randint(1, 3)} ⎕SND ,{nums[0]}"
        s.run(line)
    print("snd: 300 random voices and volumes leave the registers the model says")


def test_key():
    s = Keyed()
    lines = [("⎕KEY 0", [65]), ("⎕KEY 0", []), ("⎕KEY 0", [13, 65]), ("⎕KEY 5", [3]), ("⎕KEY 5", []), ("⎕KEY 0 ⋄ ⎕KEY 0 ⋄ ⎕KEY 0", [1, 2]),
             ("A←⎕KEY 0 ⋄ A", [200]), ("1+⎕KEY 0", [9]), ("⍳⎕KEY 0", [3]), ("(⎕KEY 0),⎕KEY 0", [7, 8]), ("⎕KEY 0 0", [5]), ("⎕KEY 'a'", []), ("⎕KEY ¯1", [1]),
             ("⎕KEY 32768", [1]), ("⎕KEY 32767", [88]), ("⎕KEY 1.5", [1]), ("⎕KEY ⍬", [1]), ("⎕KEY", [1]), ("1 ⎕KEY 0", [1]), ("⎕KEY 2 3⍴0", [1]), ("+/⎕KEY 0", [5]),
             ("⎕KEY[1]0", [1]), ("⎕KEY.+1", [1]), ("⎕KEY/1", [1]), ("2 3 ⎕KEY 0", [1]), ("A←⎕KEY 0 ⋄ B←⎕KEY 0 ⋄ A B", [3, 4]), ("⎕KEY 0 ⋄ 5", [1]), ("5 ⋄ ⎕KEY 0", [6]),
             ("∇R←GET", []), ("R←⎕KEY 0", []), ("∇", []), ("GET", [42]), ("GET", []), ("GET+GET", [1, 2]), ("∇POLL;K", []), ("K←⎕KEY 0", []), ("K", []), ("∇", []), ("POLL", [77]),
             ("⎕GR 1 ⋄ ⎕KEY 0", [5]), ("⎕GR 0", []), ("A←⎕SND 15", []), ("1+⎕SND 15", []), ("(⎕SND 15)", []), ("⎕SND 15 ⋄ 5", []), ("2 ⎕SND 5 ⋄ ⎕KEY 0", [9])]
    for line, keys in lines:
        s.run(line, keys)
    print(f"snd: {len(lines)} ⎕KEY lines match the model, keys consumed included")


if __name__ == "__main__":
    test_key()
    test_snd_pool()
    test_snd_streams()
