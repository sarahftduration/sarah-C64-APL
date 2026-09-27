"""Roll and deal (?), the random number generator, and )SEED: the 6502 against the model, and the model's sanity."""
import collections
import os
import random
import sys

sys.path.insert(0, os.getcwd())
import apl64
from harness import call, load
from test_eval import Session, check
from test_overlay import command, screen_text, start


def test_model_sanity():
    apl64.rng_seed(1)
    draws = [apl64.rng_draw() for _ in range(20000)]
    assert 16500 < len(set(draws)) < 18000 and min(draws) < 500 and max(draws) > 65000
    ones = sum(bin(d).count("1") for d in draws) / (16 * len(draws))
    assert 0.49 < ones < 0.51, ones
    apl64.rng_seed(2)
    counts = collections.Counter()
    for _ in range(4):
        counts.update(apl64.roll(apl64.vector(apl64.INT, [10] * 5000)).data)
    assert all(1700 < counts[k] < 2300 for k in range(1, 11)), sorted(counts.items())
    apl64.rng_seed(3)
    for n in (1, 2, 7, 100, 1000):
        for a in (0, 1, n // 2, n):
            d = apl64.deal(apl64.scalar(apl64.INT, a), apl64.scalar(apl64.INT, n)).data
            assert len(d) == a and len(set(d)) == a and all(1 <= x <= n for x in d)
    zeros = apl64.roll(apl64.vector(apl64.INT, [0] * 1000)).data
    assert all(0 < apl64.f_to_fraction(z) < 1 for z in zeros)
    apl64.rng_seed(5)
    a = [apl64.rng_draw() for _ in range(5)]
    apl64.rng_seed(5)
    assert a == [apl64.rng_draw() for _ in range(5)]
    print("random: the model's generator, roll and deal are uniform enough, and deal gives distinct numbers")


OPS = ["0", "1", "2", "6", "10", "100", "1000", "32767", "32768", "65535", "¯1", "¯5", "1.5", "2.0", "5.0", "1e10", "'a'", "⍬", "1 2 3", "6 6 6 6", "0 1 6", "(2 3⍴6)", "(2 2⍴0 1 2 3)",
       "(3 0⍴1)", "1 1", "0.5", "(⍳4)", "100⍴10"]


def test_pool():
    s = Session()
    kinds = {}
    n = 0
    for a in OPS:
        for line in [f"?{a}"] + [f"{a}?{b}" for b in OPS]:
            if n % 30 == 0:
                s.reset()
            k = check(s, line)
            kinds[k] = kinds.get(k, 0) + 1
            n += 1
    print(f"random: {n} roll and deal cases match the model, generator state included {dict(sorted(kinds.items()))}")


def test_streams():
    """Long runs: the numbers drawn (and the state left) are the same on both, across seeds."""
    s = Session()
    for seed in (0, 1, 7, 255, 256, 4242, 65535):
        s.reset()
        s.seed(seed)
        for line in ["?100⍴6", "?50⍴1000", "10?10", "?0 0 0", "20?100", "?5 5⍴20", "?200⍴32767", "+/?300⍴2", "100?1000", "?4⍴0 1 2 3", "1000?1000"]:
            check(s, line)
    print("random: 7 seeds, long draws and deals give the model's numbers and leave the same state")


def test_random_lines():
    rng = random.Random(41)
    s = Session()
    for i in range(500):
        if i % 30 == 0:
            s.reset()
        r = rng.random()
        if r < .5:
            k = rng.randint(1, 6)
            ns = " ".join(str(rng.choice([1, 2, 6, 10, 100, 32767, 0, 5, 50])) for _ in range(k))
            check(s, f"?{ns}" if rng.random() < .8 else f"?{k} {k}⍴{ns.split()[0]}")
        else:
            b = rng.choice([1, 5, 10, 50, 100, 300])
            a = rng.randint(0, b)
            check(s, f"{a}?{b}")
    print("random: 500 random rolls and deals match the model")


def test_syntax():
    s = Session()
    for line in ["?", "1?", "?1?2", "?(?6)", "?6+1", "1+?6", "(?6)+?6", "A←?6 ⋄ A", "A←10?10 ⋄ A[⍋A]", "+/10?10", "⍴5?10", "?⍳5", "(?5)?10", "3?(?5)", "3?10?10", "?3?10", "(3?10)?10",
                 "?/1 2", "?\\1 2", "1 2?/3", "?[1]6", "1?[1]6", "5?5 ⋄ 5?5", "?6 ⋄ ?6", "M←3 3⍴?9⍴9 ⋄ M", "?M", "∇R←F N", "R←?N", "∇", "F 6", "F 0", "F 1 2 3", "∇R←G N", "R←N?N", "∇", "G 5", "G 0", "∇R←H", "R←?6", "∇", "H", "H+H",
                 "(1?1),2?2", "?1 2,3", "⍴?0⍴6", "⍴?2 3⍴6", "×/⍴?2 3⍴6", "⌈/?100⍴6", "⌊/?100⍴6", "6=?100⍴6", "+/6=?100⍴6", "?6 6 6 6 6 6", "6 6 6 6 6 6=?6 6 6 6 6 6"]:
        check(s, line)
    print("random: syntax and edge cases match the model")


def test_seed_command():
    """)SEED n: sets the state as apl64.rng_seed does; a missing, non-numeric or too big n is BAD COMMAND."""
    m, L = start()
    rs = lambda: sum(m.memory[L["rnd_state"] + i] << 8 * i for i in range(4))
    for n in (0, 1, 5, 255, 256, 4242, 12345, 65535):
        command(m, L, f")SEED {n}")
        apl64.rng_seed(n)
        assert rs() == apl64._RNG[0], (n, hex(rs()), hex(apl64._RNG[0]))
    before = rs()
    for bad in (")SEED", ")SEED   ", ")SEED x", ")SEED 65536", ")SEED 1x", ")SEED -1", ")SEED 99999999", ")SEED 1.5"):
        call(m, L["scr_clear"])
        command(m, L, bad)
        assert "BAD COMMAND" in " ".join(screen_text(m, L)), (bad, screen_text(m, L)[:2])
        assert rs() == before, bad
    command(m, L, ")seed 7  ")
    apl64.rng_seed(7)
    assert rs() == apl64._RNG[0]
    print("random: )SEED sets the generator like the model and refuses what is not a number from 0 to 65535")


if __name__ == "__main__":
    test_model_sanity()
    test_seed_command()
    test_syntax()
    test_pool()
    test_streams()
    test_random_lines()
