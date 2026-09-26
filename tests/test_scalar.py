import os
import random
import sys

sys.path.insert(0, os.getcwd())
import apl64
from harness import call, load, use_overlay
from test_eval import Session, check

FA, FB = 0x10, 0x13


def to_bytes(p):
    return [p >> 16, (p >> 8) & 0xFF, p & 0xFF]


def rand_f(rng):
    if rng.random() < .06:
        return 0
    e = rng.choice([rng.randint(1, 255), rng.randint(120, 140), rng.randint(1, 5), rng.randint(250, 255)])
    return (e << 16) | (rng.getrandbits(1) << 15) | rng.choice([0, 0x7FFF, rng.getrandbits(15)])


def test_f_cmp3():
    m, L = load("eval")
    rng = random.Random(3)
    counts = {"eq": 0, "lt": 0, "gt": 0, "domain": 0}
    for _ in range(40000):
        a = rand_f(rng)
        r = rng.random()
        if r < .3:                                       # nearly equal: exercises the tolerance
            b = a ^ rng.choice([0, 1, 2, 3, 0x40, 0x100, 0x200, 0x8000])
            if b >> 16 == 0:
                b = a
        elif r < .4:
            b = apl64.f_neg(a)
        elif r < .5:
            b = (a & ~0xFF7FFF) | ((min(255, max(1, (a >> 16) + rng.randint(-1, 1)))) << 16) | rng.getrandbits(15)
        else:
            b = rand_f(rng)
        m.memory[FA:FA + 3] = to_bytes(a)
        m.memory[FB:FB + 3] = to_bytes(b)
        call(m, L["f_cmp3"])
        try:
            eq = apl64.f_teq(a, b)
        except apl64.AplError:
            assert m.p & 1 and m.a == 2, (hex(a), hex(b))
            counts["domain"] += 1
            continue
        assert not m.p & 1, (hex(a), hex(b))
        ka, kb = apl64._fkey(a), apl64._fkey(b)
        got = (m.memory[L["ceq"]], m.memory[L["clt"]], m.memory[L["cgt"]])
        assert got == (int(eq), int(ka < kb), int(ka > kb)), (hex(a), hex(b), got)
        counts["eq" if eq else "lt" if ka < kb else "gt"] += 1
    print(f"float compare: 40000 pairs match f_teq/_fkey {counts}")


POOL = ["0", "1", "7", "¯3", "32767", "¯32768", "32768", "40000", "¯40000", "1.5", "¯2.25", "0.1",
        "1e38", "¯1e38", "1e¯38", "1e¯39", "100000", "100001", "1.00002", "1.00003", "1.0001",
        "'a'", "'b'", "1 2 3", "0 1 1", "¯1 0 1", "32767 1", "¯32768 ¯1", "1.5 2.5 ¯3", "1 1.00003 100000",
        "'abc'", "'ab'", "⍬", "''", "4 5", "1 0", "(1⍴5)", "(1⍴1.5)",
        "(2 3⍴⍳6)", "(2 3⍴1.5)", "(3 2⍴1 0)", "(2 3⍴'abcdef')", "(0 3⍴1)", "(2 3⍴¯32768)",
        "(⍳4)", "(1 2 3 4×10000)", "(1 2,3.5)"]
OPS = "+-×÷=≠<≤>≥⌈⌊|∧∨"
POOL += ["1.0", "0.0", "1 0 1 1", "(2 2⍴1 0 0 1)", "(⍳0)", "1 0", "(1⍴1)", "2 0",
         "2.5", "¯2.5", "0.3", "¯0.3", "65535", "65536", "1e10", "¯1e10", "3.5 ¯3.5 0.5", "1e30", "7 ¯7 0 32768", "1e¯3 2e¯3"]


def test_f_floor_residue():
    """The floor and the residue kernels against the model's f_floor and f_residue, on floats of every size."""
    m, L = load("eval")
    rng = random.Random(4)
    n = dom = 0
    for _ in range(30000):
        a = rand_f(rng)
        if rng.random() < .5:
            a = (rng.choice([127, 128, 129, 130, 135, 140, 143, 144, 145]) << 16) | (rng.getrandbits(1) << 15) | rng.getrandbits(15)
        m.memory[FA:FA + 3] = to_bytes(a)
        use_overlay(m, L, "FLOOR")
        call(m, L["f_floor"])
        got = m.memory[FA] << 16 | m.memory[FA + 1] << 8 | m.memory[FA + 2]
        assert got == apl64.f_floor(a), (hex(a), hex(got), hex(apl64.f_floor(a)))
    for _ in range(30000):
        a, b = rand_f(rng), rand_f(rng)
        r = rng.random()
        if r < .5:                                       # exponents that make the quotient of moderate size
            e = rng.randint(120, 150)
            a = (e << 16) | (rng.getrandbits(1) << 15) | rng.getrandbits(15)
            b = ((e + rng.randint(-3, 12)) << 16) | (rng.getrandbits(1) << 15) | rng.getrandbits(15)
        m.memory[FA:FA + 3] = to_bytes(a)
        m.memory[FB:FB + 3] = to_bytes(b)
        call(m, L["k_fres"], max_steps=200000)
        try:
            want = apl64.f_residue(a, b)
        except apl64.AplError:
            assert m.p & 1 and m.a == 2, (hex(a), hex(b))
            dom += 1
            continue
        assert not m.p & 1, (hex(a), hex(b))
        got = m.memory[FA] << 16 | m.memory[FA + 1] << 8 | m.memory[FA + 2]
        assert got == want, (hex(a), hex(b), hex(got), hex(want))
        n += 1
    print(f"float floor and residue: 30000 floors and {n} residues ({dom} overflows) match the model bit for bit")


def test_matrix():
    rng = random.Random(8)
    s = Session()
    kinds = {}
    lines = [f"{a}{op}{b}" for a in POOL for op in OPS for b in POOL]
    rng.shuffle(lines)
    lines = lines[:6000] + [f"{op}{a}" for a in POOL for op in "-×÷+⌈⌊|~"]
    for n, line in enumerate(lines):
        if n % 25 == 0:
            s.reset()
        k = check(s, line)
        kinds[k] = kinds.get(k, 0) + 1
    print(f"scalar functions: {len(lines)} operand combinations match the model {dict(sorted(kinds.items()))}")


def test_sizes():
    """The model computes before it checks the size: DOMAIN wins over WS FULL."""
    s = Session()
    for line in ["(⍳1100)÷0", "(⍳1100)÷1", "(⍳1100)+0.5", "(⍳1100)=1", "(⍳1400)+(⍳1400)", "(⍳1600)+(⍳1600)",
                 "(⍳1400)×32767", "(⍳1400)×0", "(⍳1100)÷0.5", "(⍳1100)<1.5", "(⍳1100)=1e38", "-⍳1100", "÷⍳1100",
                 "×⍳1100", "×⍳1600", "-⍳1600", "(⍳1100)-⍳1100", "(1100⍴1e38)+1100⍴1e38", "(1100⍴1e38)×1100⍴1e38",
                 "(1100⍴1e38)=1100⍴¯1e38", "(1100⍴1e38)<1100⍴¯1e38", "(500⍴1e38)-500⍴¯1e38"]:
        check(s, line)
    print("scalar functions: size limit versus DOMAIN ordering matches the model")


if __name__ == "__main__":
    test_f_cmp3()
    test_f_floor_residue()
    test_sizes()
    test_matrix()
