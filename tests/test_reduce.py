import os
import random
import sys

sys.path.insert(0, os.getcwd())
import apl64
from fractions import Fraction
from test_eval import Session, check
from test_tokenizer import exact_decimal

GLYPHS = "+-×÷=≠<≤>≥"

# (a 0-row matrix is left out: the model raises IndexError on it)
POOL = ["5", "1.5", "'a'", "1 2 3", "0 1 1", "¯1 0 1 5", "32767 1", "¯32768 ¯1", "1.5 2.5 ¯3", "1e38 1e38",
        "1e10 1 ¯1e10", "1e¯38 1e¯38", "100000 1 ¯100000", "1 2 3 4 5 6 7 8", "⍳10", "⍬", "1⍴7", "1⍴1.5", "2 2 2 2",
        "40000 40000", "¯2 3", "1 0 0", "0 0 0", "'abc'", "''", "1 2.5", "0.1 0.2 0.3", "1e10 1e¯10 1", "3 1 2",
        "200 200", "181 182", "1e20 ¯1e20 1", "1e38 ¯1e38", "1 1e¯30", "¯32768", "32767 32767 32767",
        "0 1", "1 1", "'aab'", "'aa'", "1 2 3 1 2 3", "¯1 ¯1 ¯1", "1.5 1.5", "1e¯30 1e30", "0 0",
        "(2 3⍴⍳6)", "(3 2⍴1 0)", "(2 2⍴32767 1 5 5)", "(2 2⍴5 5 32767 1)", "(2 3⍴1.5)", "(3 0⍴1)", "(2 3⍴'abcdef')",
        "(2 1⍴1 2)", "(1 3⍴4 5 6)", "(2 2⍴1e38 1e38 1 2)", "(3 3⍴⍳9)", "(2 3⍴1 0)", "(3 1⍴'a')", "(2 2⍴1e10 1 ¯1e10 5)",
        "(2 3⍴¯32768 ¯1 5)", "(4 2⍴1 2 3)"]


def test_pool():
    s = Session()
    kinds = {}
    n = 0
    for a in POOL:
        for g in GLYPHS:
            if n % 30 == 0:
                s.reset()
            n += 1
            k = check(s, f"{g}/{a}")
            kinds[k] = kinds.get(k, 0) + 1
    print(f"reduce: {n} function/operand combinations match the model {dict(sorted(kinds.items()))}")


def rand_float(rng):
    m = rng.choice([1, 2, 3, 5, 7, 12345, 99999, 65536, 32768, 100001])
    k = rng.choice([rng.randint(-45, 38), rng.randint(-5, 5), rng.randint(-40, -30), rng.randint(30, 38), 0])
    return ("¯" if rng.random() < .45 else "") + f"{m}e{'¯' if k < 0 else ''}{abs(k)}"


def test_exact_sums():
    """+ over FLOAT is exact and rounded once, so cancellation and tiny terms must survive."""
    rng = random.Random(4)
    s = Session()
    n = 0
    for i in range(1500):
        if i % 30 == 0:
            s.reset()
        xs = [rand_float(rng) for _ in range(rng.randint(2, 9))]
        if rng.random() < .4:                                   # add exact cancelling pairs
            extra = [x[1:] if x.startswith("¯") else "¯" + x for x in xs[:rng.randint(1, len(xs))]]
            xs += extra
            rng.shuffle(xs)
        if rng.random() < .25:
            xs.append("1")
        line = "+/" + " ".join(xs)
        if len(apl64.encode_line(line)) > 255:
            continue
        check(s, line)
        n += 1
    print(f"reduce: {n} random exact float sums (with cancellation) match the model bit for bit")


def test_rounding_ties():
    """A base, half an ulp of it, and a tiny extra term: the sticky bits decide the rounding."""
    rng = random.Random(12)
    s = Session()
    n = 0
    for i in range(1200):
        if i % 30 == 0:
            s.reset()
        eb = rng.randint(60, 200)
        base = (eb << 16) | rng.getrandbits(15)
        half = apl64.f_from_fraction(Fraction(1, 2 ** 145) * 2 ** eb)               # half an ulp of base
        tiny_e = eb - 25 - rng.randint(0, 90)
        tiny = (tiny_e << 16) | rng.choice([0, 0, 0x4000, rng.getrandbits(15)])
        parts = [base, half, tiny]
        if rng.random() < .3:
            parts.append(apl64.f_neg(apl64.f_from_fraction(Fraction(1, 2 ** 145) * 2 ** (eb - rng.randint(0, 3)))))
        if rng.random() < .4:
            parts = [apl64.f_neg(p) for p in parts]
        rng.shuffle(parts)
        line = "+/" + " ".join(exact_decimal(p) for p in parts)
        if len(line) > 255:
            continue
        check(s, line)
        n += 1
    print(f"reduce: {n} sums whose rounding depends on sticky bits far below the mantissa match the model")


def test_folds():
    """The other functions fold right to left through the full dyadic function."""
    rng = random.Random(6)
    s = Session()
    n = 0
    for i in range(1500):
        if i % 30 == 0:
            s.reset()
        g = rng.choice("-×÷=≠<≤>≥")
        kind = rng.random()
        if kind < .4:
            xs = [str(rng.choice([1, 2, 3, 7, 10, 100, 181, 200, 32767, -32768, 0, 5])).replace("-", "¯")
                  for _ in range(rng.randint(1, 9))]
        elif kind < .8:
            xs = [rand_float(rng) if rng.random() < .5 else str(rng.randint(-9, 9)).replace("-", "¯")
                  for _ in range(rng.randint(1, 8))]
        else:
            xs = [rng.choice(["1", "1.00001", "1.00003", "0.99999", "2"]) for _ in range(rng.randint(1, 8))]
        r = rng.random()
        if r < .25:
            rows = rng.randint(1, 4)
            cols = rng.randint(1, 4)
            line = f"{g}/({rows} {cols}⍴{' '.join(xs)})"
        else:
            line = f"{g}/{' '.join(xs)}"
        check(s, line)
        n += 1
    print(f"reduce: {n} random folds match the model")


def test_syntax():
    s = Session()
    for line in ["1/2", "1 2/3 4", "A←1 ⋄ A/2", "(1 2)/3 4", "1\\2", "1+/2", "A←1 ⋄ A+/2 3", "(1)+/2 3", "B+/1", "(B)+/1", ",/1 2", "⍴/1 2", "+\\1 2", "+¨1", "/", "+/", "1 /", "+/ ",
                 "+/+/1 2 3", "+/⍳0", "×/⍬", "÷/⍬", "-/⍬", "=/⍬", "≠/⍬", "</⍬", "≤/⍬", ">/⍬", "≥/⍬", "+/''", "×/''", "=/''",
                 "+/(⍳3)", "+/⍳3 ⋄ ×/⍳4", "A←+/⍳5 ⋄ A", "(+/1 2 3)+1", "1+(+/1 2 3)", "(+/1 2 3)+(+/4 5)", "+/+/2 3⍴⍳6",
                 "+/,2 3⍴⍳6", "⍴+/2 3⍴⍳6", "+/(2 3⍴⍳6)+1", "-/1 2 3=1 2 3", "(⍳3)+/1", "+/(1)", "+/((2))", "+/()", "+/1 2 ()",
                 "1 2 3 +/", "+/[1]", "+/→1", "+/A", "A←1 2 3 ⋄ +/A", "A←2 3⍴⍳6 ⋄ +/A ⋄ ×/A ⋄ ⌈/A" if False else "A←2 3⍴⍳6 ⋄ +/A ⋄ ×/A"]:
        check(s, line)
    print("reduce: syntax, NONCE and edge cases match the model")


def test_sizes():
    s = Session()
    for line in ["+/(1500 2⍴1)", "+/(1600 1⍴1)", "+/(1000 3⍴1.5)", "÷/(1100 1⍴2)", "-/(1100 2⍴1e38 ¯1e38)", "×/(1100 2⍴1e30 1e30)",
                 "+/(600 4⍴32767)", "+/(1000 3⍴⍳3)", "=/(1400 2⍴1)", "=/(2900 1⍴1)", "+/(1400 2⍴32767)",
                 "÷/(1002 2⍴1 1 1 0)", "÷/(1002 2⍴1 1 1 1)", "÷/(1100 1⍴1 0)", "-/(1002 2⍴1 1 1 0)", "+/(1002 2⍴1 1 1 0)"]:
        check(s, line)
    print("reduce: result size and DOMAIN ordering match the model")


if __name__ == "__main__":
    test_syntax()
    test_pool()
    test_exact_sums()
    test_rounding_ties()
    test_folds()
    test_sizes()
