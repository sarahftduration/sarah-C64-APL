"""Axis brackets: f/[k]A, f\\[k]A, ⌽[k]A and a⌽[k]A against the model."""
import os
import random
import sys

sys.path.insert(0, os.getcwd())
from test_eval import Session, check
from test_reduce import rand_float

OPERANDS = ["5", "1.5", "'a'", "1 2 3", "0 1 1", "¯1 0 1 5", "32767 1", "1.5 2.5 ¯3", "'abc'", "⍬", "''", "(2 3⍴⍳6)", "(3 2⍴⍳6)", "(2 2⍴1 0 1 1)",
            "(3 1⍴1 2 3)", "(1 3⍴4 5 6)", "(2 3⍴1.5)", "(3 2⍴'abcdef')", "(3 0⍴1)", "(0 3⍴1)", "(2 2⍴32767 1 5 5)", "(4 3⍴⍳12)", "(3 3⍴1 0 0 0 1 0 0 0 1)",
            "(2 3⍴1e38 1e38 1 2 3 4)", "(2 3⍴¯32768 ¯1 5 1 1 1)"]
AXES = ["1", "2", "3", "0", "¯1", "1.0", "2.0", "1.5", "'a'", "1 2", "⍬", "(1+0)", "2-1", "1=1", "⍳1", ",1", "1e10", "32768"]


def test_pool():
    s = Session()
    kinds = {}
    n = 0
    for a in OPERANDS:
        for ax in AXES:
            for f in ["+/", "×\\", "⌽", "3⌽", "-/", "⌈\\", "=/", "∧/"]:
                if n % 30 == 0:
                    s.reset()
                k = check(s, f"{f[0]}{f[1]}[{ax}]{a}" if len(f) == 2 and f[1] in "/\\" else f"{f}[{ax}]{a}")
                kinds[k] = kinds.get(k, 0) + 1
                n += 1
    print(f"axis: {n} function, axis and operand combinations match the model {dict(sorted(kinds.items()))}")


def test_all_functions():
    """Every scalar function with reduce and scan along each axis of a matrix, and rotations."""
    s = Session()
    n = 0
    mats = ["(2 3⍴1 0 2 5 1 1)", "(3 2⍴1 1 0 3 2 1)", "(2 3⍴1.5 2 ¯1 0 3 1)", "(3 3⍴⍳9)"]
    for g in "+-×÷=≠<≤>≥⌈⌊|∧∨":
        for m in mats:
            for ax in "12":
                for op in "/\\":
                    if n % 30 == 0:
                        s.reset()
                    check(s, f"{g}{op}[{ax}]{m}")
                    n += 1
    for m in mats:
        for ax in "12":
            for k in ["0", "1", "¯1", "2", "5", "1.0"]:
                check(s, f"{k}⌽[{ax}]{m}")
                n += 1
            check(s, f"⌽[{ax}]{m}")
            n += 1
    print(f"axis: {n} reduces, scans and rotations along each axis of a matrix match the model")


def test_syntax():
    s = Session()
    for line in ["M←2 3⍴⍳6", "M←3 4⍴⍳12", "+/[1]M", "+/[2]M", "+/[1]M+1", "1+M+/[1]M", "(+/[1]M)×2", "2×+/[1]M", "+/[1]+/[1]M", "+/[1]+/[2]M", "+/[2]+\\[1]M", "⌽[1]⌽[2]M", "⌽[1]M[1;]",
                 "+/[1]M[;1]", "+/[1]1 2 3", "⌽[1]1 2 3", "1⌽[1]1 2 3", "⌽[2]1 2 3", "+/[1;1]M", "+/[]M", "+/[", "+/[1", "[1]M", "+[1]M", "-[1]M", "⍴[1]M", "⍳[1]3", ",[1]M", "~[1]M", "⍉[1]M",
                 "+.[1]M", "+.×[1]M", "∘.+[1]M", "+¨[1]M", "M+/[1]M", "M f/[1]M", "1 0/[1]M", "1 0\\[1]M", "A←1 0 1 ⋄ A/[1]M", "A←1 0 1 ⋄ A\\[1]M", "+/[1]", "⌽[1]", "1⌽[1]", "1 2⌽[1]M",
                 "(1 2)⌽[1]M", "M⌽[1]M", "(2 3⍴1)⌽[2]M", "+/[1]A", "A←5 ⋄ +/[1]A", "A←2 3⍴⍳6 ⋄ B←+/[1]A ⋄ B", "A←2 3⍴⍳6 ⋄ B←⌽[1]A ⋄ B", "A←2 3⍴⍳6 ⋄ A←+\\[1]A ⋄ A", "A←2 3⍴⍳6 ⋄ +/[1]A ⋄ +/[2]A",
                 "A←2 3⍴⍳6 ⋄ (+/[1]A)-+/[2]A", "+/[1]M ⋄ 1", "+/[1+1]M", "+/[⍳1]M", "+/[1 1⍴1]M", "+/[(1)]M", "+/[+/1]M", "+/[Z]M", "+/[1]Z", "x←1 ⋄ +/[x]M", "x←2 ⋄ +/[x]M", "x←3 ⋄ +/[x]M",
                 "∇R←F X", "R←+/[1]X", "∇", "F M", "F 1 2 3", "∇R←G X", "R←⌽[2]X", "∇", "G M", "∇R←H X", "R←X", "∇", "H[1]M", "H/[1]M", "1 H[1]M",
                 "+/[1]+/[1]+/[1]M", "⌽[1]⌽[1]M", "+\\[1]+\\[2]M", "+/[1]M[1 2;1 2]", "+/[2]M[2;]", "(⌽[1]M)[1;]", "⌽[1]M[2;1]"]:
        check(s, line)
    print("axis: syntax, NONCE and edge cases match the model")


def test_random():
    rng = random.Random(3)
    s = Session()
    n = 0
    for i in range(700):
        if i % 30 == 0:
            s.reset()
        m, k = rng.randint(1, 4), rng.randint(1, 4)
        vals = " ".join(rng.choice(["0", "1", "2", "7", "1.5", "32767", "¯1", rand_float(rng), "100"]) for _ in range(m * k))
        mat = f"({m} {k}⍴{vals})"
        f = rng.choice(["+/", "×/", "-/", "⌈/", "+\\", "×\\", "-\\", "⌊\\", "⌽", f"{rng.randint(-3, 3)}⌽".replace("-", "¯")])
        ax = rng.choice(["1", "2", "1", "2", "1+1", "1.0"])
        check(s, f"{f[0]}{f[1]}[{ax}]{mat}" if len(f) == 2 and f[1] in "/\\" else f"{f}[{ax}]{mat}")
        n += 1
    print(f"axis: {n} random reduces, scans and rotations of random matrices match the model")


def test_sizes():
    s = Session()
    for line in ["+/[1]40 50⍴1", "+\\[1]40 50⍴1", "+\\[1]30 50⍴1", "+\\[2]30 50⍴1", "⌽[1]40 50⍴1", "⌽[1]20 60⍴1.5", "⌽[1]15 60⍴1.5", "+/[1]1 3000⍴1", "+/[1]3000 1⍴1", "+\\[1]3000 1⍴1", "+\\[1]1 1400⍴1",
                 "⌽[1]1 3000⍴1", "⌽[1]1 3001⍴1", "⌽[1]3001 1⍴1", "×\\[1]30 40⍴1.5", "×\\[1]20 30⍴1.5", "+\\[1]20 80⍴32767", "+\\[1]25 30⍴32767"]:
        check(s, line)
    print("axis: result size limits match the model")


if __name__ == "__main__":
    test_syntax()
    test_pool()
    test_all_functions()
    test_random()
    test_sizes()
