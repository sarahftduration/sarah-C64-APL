"""Arrays spilled to the REU: the evaluator's own tests rerun with a heap too small for them.

A heap of a few KB makes ordinary programs run out of room all the time, so arrays that only a variable holds
are moved out to the REU and come back when they are next used. Every result must still match the model (a line
that needs more than the small heap holds at once is WS FULL on the machine and is skipped, and the session
restarted). A second mode squeezes the heap at every allocation, so nearly every one takes the slow path.
"""
import os
import random
import sys

sys.path.insert(0, os.getcwd())
import apl64
import test_eval as T
import test_stress as S

STASH = 0


class SpillSession(T.Session):
    def __init__(self, size, squeeze=None, reverse=False):
        super().__init__(reu_kb=8192, heap_size=size)
        self.tolerate_wsfull = True
        m, L = self.m, self.L
        if squeeze is not None:
            htop, hlim = L["htop"], L["hlim"]

            def tighten(mpu):                            # each allocation finds only a little room
                top = mpu.memory[htop] | mpu.memory[htop + 1] << 8
                lim = min(top + squeeze, L["HEAP_BASE"] + size)
                mpu.memory[hlim], mpu.memory[hlim + 1] = lim & 0xFF, lim >> 8
            m.hooks[L["alloc"]] = tighten
        if reverse:
            S.install(self)                              # (its hook replaces the squeeze: only one of the two at a time)

    def stashes(self):
        return sum(1 for t in self.m.reu.transfers if t[0] == STASH and t[2] >= 0x10000)

    def fetches(self):
        return sum(1 for t in self.m.reu.transfers if t[0] == 1 and t[2] >= 0x10000)


def run_lines(s, lines):
    n = 0
    for line in lines:
        T.check(s, line)
        n += 1
    return n


def test_fixed_small_heap():
    for size in (2500, 5000):
        s = SpillSession(size)
        n = run_lines(s, T.FIXED)
        skips = getattr(s, "wsfull_skips", 0)
        assert s.stashes() > 5, (s.stashes(), s.fetches())
        assert skips < n * 0.4, skips
        print(f"spill: {n} fixed cases match the model in a {size} byte heap: {s.stashes()} arrays moved out, {s.fetches()} brought back, {skips} too big for it")


def test_squeezed():
    s = SpillSession(20000, squeeze=300)
    n = run_lines(s, T.FIXED)
    skips = getattr(s, "wsfull_skips", 0)
    assert s.stashes() > 15 and s.fetches() >= 1, (s.stashes(), s.fetches())
    print(f"spill: {n} fixed cases match the model with only 300 bytes free at each allocation: {s.stashes()} moved out, {s.fetches()} back, {skips} skipped")


def test_reversed():
    """Spilling and moving every block at every allocation together."""
    s = SpillSession(3500, reverse=True)
    n = run_lines(s, T.FIXED)
    assert s.stashes() > 5
    print(f"spill: {n} fixed cases match the model in a 3500 byte heap with every block moved at each allocation: {s.stashes()} moved out")


def workspace_line(rng, defined):
    """A line about a dozen variables of a few hundred elements each, so a small heap cannot hold them all."""
    v = lambda: rng.choice(defined) if defined else "A0"
    r = rng.random()
    k = rng.randint(0, 11)
    n = rng.choice([50, 200, 300, 300, 400])
    if r < .18 or not defined:
        return rng.choice([f"A{k}←{rng.randint(-5, 5)}+⍳{n}", f"A{k}←{n}⍴{rng.randint(0, 9)}", f"A{k}←{rng.choice(['1.5', '2.5'])}×⍳{n}", f"A{k}←⌽⍳{n}"])
    if r < .32:
        return f"+/{v()}"
    if r < .44:
        return f"{v()}[{rng.randint(1, 50)} {rng.randint(1, 50)}]"
    if r < .56:
        return f"A{k}←{v()}+{v()}" if rng.random() < .7 else f"A{k}←{v()}×2"
    if r < .66:
        return f"{v()}[{rng.randint(1, 50)}]←{rng.randint(0, 99)}"
    if r < .74:
        return f"A{k}←{v()},{rng.randint(0, 9)}"
    if r < .82:
        return f"A{k}←{v()}"
    if r < .9:
        return f"⍴{v()}"
    if r < .95:
        return f"{v()}≥{v()}" if rng.random() < .0 else f"⌈/{v()}"
    return f"A{k}←⌽{v()}"


def test_fuzz():
    rng = random.Random(91)
    for size, squeeze in ((3000, None), (5000, None), (20000, 250)):
        s = SpillSession(size, squeeze=squeeze)
        n = 0
        for i in range(700):
            if i % 60 == 0:
                s.reset()
            defined = [nm for k, nm in enumerate(s.model.names) if k in s.model.vars and nm.startswith("A")]
            line = workspace_line(rng, defined)
            T.check(s, line)
            n += 1
        assert s.stashes() > 30 and s.fetches() > 30, (s.stashes(), s.fetches())
        print(f"spill: {n} random workspace lines match the model ({size} byte heap{f', {squeeze} bytes free at each allocation' if squeeze else ''}): "
              f"{s.stashes()} moved out, {s.fetches()} back, {getattr(s, 'wsfull_skips', 0)} too big")


def test_functions():
    import test_funcs as F
    s = SpillSession(1200)
    n = 0
    for lines in F.DEFS + F.CALLS + F.FLOW:
        s.reset()
        for line in lines:
            T.check(s, line)
            n += 1
    print(f"spill: {n} function-session lines match the model in a 1200 byte heap ({s.stashes()} moved out, {getattr(s, 'wsfull_skips', 0)} too big)")


def test_big_workspace():
    """Twenty arrays of 1,500 bytes (30 KB) in a heap of 12 KB: they all stay, and each can be used."""
    s = SpillSession(12000)
    for i in range(20):
        T.check(s, f"A{i}←{i}+⍳750")
    for i in range(20):
        T.check(s, f"+/A{i}")
        T.check(s, f"A{i}[1 750]")
    T.check(s, "B←A3+A17")
    T.check(s, "+/B")
    assert s.stashes() >= 10 and s.fetches() >= 10
    print(f"spill: a 30 KB workspace in a 12 KB heap works ({s.stashes()} moved out, {s.fetches()} brought back)")


if __name__ == "__main__":
    test_big_workspace()
    test_fixed_small_heap()
    test_squeezed()
    test_reversed()
    test_fuzz()
    test_functions()
