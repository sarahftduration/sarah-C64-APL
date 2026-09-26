import os
import random
import sys

sys.path.insert(0, os.getcwd())
from test_eval import Session, check
from test_reduce import rand_float

FG = "+-×÷=≠<≤>≥⌈⌊|∧∨"

OPERANDS = ["5", "1.5", "'a'", "0", "1", "1 2 3", "0 1 1", "¯1 0 1 5", "32767 1", "¯32768 ¯1", "1.5 2.5 ¯3", "1e38 1e38",
            "100 200", "'abc'", "1 0 1", "⍬", "''", "1⍴7", "2 3", "1e¯38 1", "181 182 ¯181", "3 1 2", "1 2 3 4",
            "(2 3⍴⍳6)", "(3 2⍴⍳6)", "(2 2⍴1 0)", "(3 1⍴1 2 3)", "(1 3⍴4 5 6)", "(2 3⍴1.5)", "(3 2⍴'abcdef')",
            "(3 0⍴1)", "(0 3⍴1)", "(2 2⍴32767 1 5 5)", "(2 2⍴5 5 32767 1)", "(3 3⍴⍳9)", "(2 3⍴1 0)", "(3 2⍴1e10 1 ¯1e10 5 1 1)"]


def test_pool():
    """Every pair of operands, each with one of the function pairs in turn."""
    s = Session()
    kinds = {}
    n = 0
    for i, a in enumerate(OPERANDS):
        for j, b in enumerate(OPERANDS):
            if n % 30 == 0:
                s.reset()
            f, g = FG[(i * 7 + j) % len(FG)], FG[(i + j * 5) % len(FG)]
            k = check(s, f"{a}{f}.{g}{b}")
            kinds[k] = kinds.get(k, 0) + 1
            n += 1
    print(f"inner product: {n} operand pairs match the model {dict(sorted(kinds.items()))}")


def test_functions():
    """Every f.g on small operands of each shape."""
    s = Session()
    n = 0
    shapes = [("1 2 3", "4 5 6"), ("(2 3⍴1 0 2 5 1 1)", "(3 2⍴1 1 0 3 2 1)"), ("1 0 1", "(3 2⍴1 0 1 1 0 0)"),
              ("(2 3⍴1.5 2 ¯1 0 3 1)", "1 2 0.5"), ("3", "1 2 3"), ("1 2", "3")]
    for f in FG:
        for g in FG:
            for a, b in shapes:
                if n % 30 == 0:
                    s.reset()
                check(s, f"{a}{f}.{g}{b}")
                n += 1
    print(f"inner product: {n} function pairs on six operand shapes match the model")


def test_types():
    """The type of an element can change part-way through the result: the array is widened, keeping what it holds."""
    s = Session()
    lines = ["(2 2⍴1 1 32767 32767)+.×2 2⍴2 1 1 1", "(2 2⍴1 1 1 1)+.×2 2⍴32767 1 1 32767", "(3 1⍴1 32767 1)+.×1 2⍴32767 5",
             "(2 2⍴1 0 0 1)+.×2 2⍴1e10 1 2 3", "(2 2⍴1 1 1 1)+.×2 2⍴1 1 1.5 1", "(3 3⍴⍳9)+.×3 3⍴1 1 1 1 1 1 1 1 1e10",
             "(2 2⍴1 1 1 1)∧.=2 2⍴1 1 1 0", "(2 3⍴1 0 1 1 1 1)∨.∧3 2⍴1 0 1 1 0 0", "(3 3⍴1 0 0 0 1 0 0 0 1)+.×3 3⍴⍳9",
             "(2 2⍴100 100 100 100)×.+2 2⍴100 100 100 100", "(2 2⍴1 2 3 4)÷.×2 2⍴1 2 3 4", "(4 2⍴⍳8)+.×2 4⍴32767 1",
             "(2 2⍴1 1 1 1)-.×2 2⍴32767 32767 1 1", "(3 2⍴1 1 1 1 1 1)+.×2 3⍴1 1 1 1 1 32767"]
    for line in lines:
        check(s, line)
    rng = random.Random(9)
    for i in range(500):
        if i % 30 == 0:
            s.reset()
        m, n, p = rng.randint(1, 3), rng.randint(1, 4), rng.randint(1, 3)

        def num():
            r = rng.random()
            if r < .55:
                return str(rng.choice([0, 1, 2, 3, 7, 100, 181, 32767, -32768, -1])).replace("-", "¯")
            if r < .85:
                return rand_float(rng)
            return rng.choice(["0.5", "1.5", "1e10"])
        a = " ".join(num() for _ in range(m * n))
        b = " ".join(num() for _ in range(n * p))
        f, g = rng.choice("+×+×⌈⌊-"), rng.choice("×+×=≤")
        check(s, f"({m} {n}⍴{a}){f}.{g}{n} {p}⍴{b}")
    print("inner product: 14 fixed and 500 random matrix products (widening results) match the model")


def test_syntax():
    s = Session()
    for line in ["+.×", "+.", "1 2+.", "1 2+.×", "+.×1 2", "1 2+.×+.×3 4", "1 2 3+.×(4 5 6+.×1 2 3)", "(1 2+.×3 4)+1", "1+1 2+.×3 4", "A←1 2 ⋄ A+.×A", "A←1 2 ⋄ B←2 2⍴A ⋄ A+.×B",
                 "A←2 2⍴⍳4 ⋄ A+.×A", "A←2 2⍴⍳4 ⋄ A+.×A+.×A", "+/1 2 3+.×4 5 6", "1 2 3⍳.+4", "1 2+.⍳3", "1 2 3∘.+4 5+.×6 7", "1 2+.×∘.×3", "1 2 3+.×4 5 6 ⋄ 7",
                 "(2 2⍴1)+.×(2 2⍴1)", "(2 2⍴1)+.×3", "3+.×(2 2⍴1)", "(2 2 2⍴1)+.×1", "2 3⍴1+.×1 2 3", "1 2+.×2 3⍴1 2 3", "(⍳3)+.×⍳3", "(⍳3)+.×(3 1⍴⍳3)",
                 "(1 3⍴⍳3)+.×⍳3", "(1 3⍴⍳3)+.×3 1⍴⍳3", "(3 1⍴⍳3)+.×1 3⍴⍳3", "'abc'≠.='abd'", "'abc'=.='abc'", "1 2 3+.×'a'", "⌈.+", "1 2⌈.+3 4", "1 2 3⌊.×4 5 6",
                 "⍬+.×⍬", "⍬⌈.+⍬", "''=.=''", "(3 0⍴1)+.×(0 2⍴1)", "(0 3⍴1)+.×3", "3+.×0 3⍴1", "(2 0⍴1)+.×(0 3⍴1)", "1 2+.×⍬", "⍬+.×1 2"]:
        check(s, line)
    print("inner product: syntax, NONCE and edge cases match the model")


def test_sizes():
    """A result too big to keep is WS FULL, but a DOMAIN ERROR in any element wins over it."""
    s = Session()
    for line in ["(34 2⍴1)+.÷2 30⍴1", "(30 2⍴1)+.÷2 30⍴1", "A←34 2⍴1 ⋄ B←2 30⍴1 ⋄ B[2;30]←0 ⋄ A+.÷B", "A←34 2⍴1 ⋄ B←2 30⍴1 ⋄ B[1;1]←0 ⋄ A+.÷B",
                 "A←30 2⍴1 ⋄ B←2 30⍴1 ⋄ B[2;30]←0 ⋄ A+.÷B", "(1000⍴1)+.×1000⍴1", "(1600⍴1)+.×1600⍴1", "(1600⍴1)+.×(1600 1⍴1)",
                 "(2 1600⍴1)+.×(1600 1⍴1)", "(2 1500⍴1)+.×(1500 2⍴1)", "(3 800⍴1.5)+.×800⍴2", "(2 800⍴1)+.×(800 2⍴1)",
                 "(20 2⍴1)+.×2 20⍴32767", "(1 1000⍴1)+.×(1000⍴1)", "(1 1600⍴1)+.×(1600 1⍴1)", "(10 40⍴1)+.×40 10⍴1.5", "(30 2⍴1)+.×2 20⍴1e10",
                 "(35 2⍴1)+.×2 30⍴32767", "(20 1⍴1)+.×1 40⍴1", "(50 1⍴1)+.×1 21⍴1", "(50 1⍴1)+.×1 61⍴1", "(50 1⍴1.5)+.×1 21⍴1"]:
        check(s, line)
    print("inner product: result size and DOMAIN ordering match the model")


if __name__ == "__main__":
    test_syntax()
    test_functions()
    test_types()
    test_pool()
    test_sizes()
