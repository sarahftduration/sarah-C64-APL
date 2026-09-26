"""Catenate on matrices, compress and expand of matrices, and their axes, against the model."""
import os
import random
import sys

sys.path.insert(0, os.getcwd())
from test_eval import Session, check
from test_reduce import rand_float

OPS = ["5", "1.5", "'a'", "0", "1 2", "1 2 3", "0 1 1", "'ab'", "'abc'", "⍬", "''", "32767 1", "1e38 ¯1", "(2 3⍴⍳6)", "(3 2⍴⍳6)", "(2 2⍴1 0 1 1)", "(2 2⍴'abcd')",
       "(3 1⍴1 2 3)", "(1 3⍴4 5 6)", "(2 3⍴1.5)", "(2 1⍴'xy')", "(2 0⍴1)", "(0 3⍴1)", "(0 2⍴'a')", "(2 2⍴32767 1 5 5)", "(3 3⍴⍳9)", "(2 3⍴1e38 1 2 3 4 5)"]


def test_catenate():
    s = Session()
    kinds = {}
    n = 0
    for a in OPS:
        for b in OPS:
            for op in [",", ",[1]", ",[2]"]:
                if n % 30 == 0:
                    s.reset()
                k = check(s, f"{a}{op}{b}")
                kinds[k] = kinds.get(k, 0) + 1
                n += 1
    print(f"catenate: {n} operand pairs, plain and with an axis, match the model {dict(sorted(kinds.items()))}")


def test_compress_expand():
    s = Session()
    kinds = {}
    n = 0
    lefts = ["1 0 1", "1 1 0", "0 0 0", "1 1", "1 0", "2", "0", "1", "1 2 0", "1 2", "0 1 0 1", "⍬", "1 0 1 1", "(1 0)", "1.0 0", "1.5", "'a'", "¯1 1", "2 1 1"]
    for a in lefts:
        for b in OPS:
            for op in ["/", "\\", "/[1]", "/[2]", "\\[1]", "\\[2]"]:
                if n % 30 == 0:
                    s.reset()
                k = check(s, f"{a}{op}{b}")
                kinds[k] = kinds.get(k, 0) + 1
                n += 1
    print(f"compress and expand: {n} left operands, matrices and axes match the model {dict(sorted(kinds.items()))}")


def test_random():
    rng = random.Random(23)
    s = Session()
    for i in range(600):
        if i % 30 == 0:
            s.reset()
        m, n = rng.randint(1, 4), rng.randint(1, 4)

        def mat(rows, cols):
            vals = " ".join(rng.choice(["0", "1", "7", "1.5", "32767", "¯1", rand_float(rng), "100"]) for _ in range(rows * cols))
            return f"({rows} {cols}⍴{vals})"
        r = rng.random()
        if r < .4:
            ax = rng.choice(["", "[1]", "[2]"])
            if ax == "[1]":
                a, b = mat(rng.randint(1, 3), n), mat(rng.randint(1, 3), n)
            else:
                a, b = mat(m, rng.randint(1, 3)), mat(m, rng.randint(1, 3))
            if rng.random() < .3:
                b = " ".join(rng.choice(["1", "2.5", "3"]) for _ in range(n if ax == "[1]" else m)) or "⍬"
            check(s, f"{a},{ax}{b}")
        elif r < .7:
            k = n
            a = " ".join(str(rng.randint(0, 2)) for _ in range(rng.choice([k, k, 1])))
            check(s, f"{a}/{rng.choice(['', '[2]'])}{mat(m, n)}")
        elif r < .85:
            a = [rng.randint(0, 1) for _ in range(rng.randint(0, 5))]
            check(s, f"{' '.join(map(str, a)) or '⍬'}\\{rng.choice(['', '[2]'])}{mat(m, sum(a))}")
        else:
            a = " ".join(str(rng.randint(0, 2)) for _ in range(m))
            check(s, f"{a}/[1]{mat(m, n)}")
    print("matrices: 600 random catenations, compressions and expansions match the model")


def test_syntax():
    s = Session()
    for line in ["M←2 3⍴⍳6", "N←2 2⍴7 8 9 10", "M,N", "M,N,M", "M,(N,N)", "(M,N),1 2", "1+M,N", "+/M,N", "+/[1]M,[1]M", "⍴M,N", "⍴M,[1]M", "⍴,M,N", "A←M,N ⋄ A", "A←M ⋄ A←A,A ⋄ A", "A←M ⋄ A←A,[1]A ⋄ A",
                 "M,", ",M", ",[1]M", ",[2]M", "M,[1]", "M,[]N", "M,[1;2]N", "M,[1]N,[1]N", "M,[1]M,[2]M", "M,⍬", "⍬,M", "M,''", "5,5", "5,[1]5", "(⍳3),[1]⍳3", "(⍳3),[2]⍳3", "(2 2⍴1),[1](⍳2)", "(2 2⍴1),[2](⍳2)", "(⍳2),[1](2 2⍴1)",
                 "1 0 1/[1]", "/[1]M", "1 0 1/[1;1]M", "A←1 0 1 ⋄ A/M", "A←1 0 1 ⋄ A\\N", "A←1 0 1 ⋄ A/[2]M", "1 0 1/M,M", "(1 0 1/M),M", "1 0 1/1 0 1/M", "2/2/M", "2/[1]2/[2]M", "0 1/[1]M", "1 1 0/[1]3 2⍴⍳6",
                 "1 0 1\\N", "1 0 1\\[2]N", "0 1\\[1]2 2⍴⍳4", "1 0\\[1]2 2⍴⍳4", "+/1 0 1/M", "+/[1]1 0 1/M", "1 0 1/+/M", "1 0 1/[1]+/M", "⍉1 0 1/M", "1 0 1/⍉M",
                 "M\\M", "M/M", "3/M", "3/[1]M", "3\\M", "1 2/M", "1 0/M", "1/2 3 4⍴1", "1\\2 3 4⍴1", "1 0 1/'abc'", "1 0 1\\1 2", "1 0 1\\[2]1 2", "2 3⍴1 0 1\\1 2 ⋄ 5"]:
        check(s, line)
    print("matrices: syntax, NONCE and edge cases match the model")


def test_sizes():
    s = Session()
    for line in ["(20 40⍴1),20 40⍴1", "(20 50⍴1),20 50⍴1", "(30 50⍴1),30 50⍴1", "(20 30⍴1.5),20 30⍴1.5", "(20 30⍴1.5),[1]20 30⍴1.5", "(10 100⍴1),[1]10 100⍴1", "(15 100⍴1),[1]16 100⍴1",
                 "(1 3000⍴1),1 2⍴1", "(1 3000⍴1),(1 3000⍴1)", "(1500 1⍴1),[1]1500 1⍴1", "(1500 1⍴1),(1500 1⍴1)", "(1500 1⍴1),(1500 3⍴1)", "(1 1500⍴1),[2]1 1500⍴1", "(2 1500⍴1),2 1500⍴1",
                 "1 1 1/40 30⍴1", "2/40 30⍴1", "2/20 30⍴1", "3/20 30⍴1.5", "1 0/[1]40 30⍴1", "2/[1]40 30⍴1", "2/[1]20 30⍴1", "(40⍴1)\\40 40⍴1", "(50⍴1)\\20 50⍴1", "(60⍴1)\\20 60⍴1", "(30⍴1 0)\\20 15⍴1",
                 "1 0 1\\1500 2⍴1", "(1000⍴1)/1 1000⍴1", "(1000⍴2)/1 1000⍴1", "(1000⍴2)/[2]1 1000⍴1", "(1500⍴1)/1 1500⍴1", "2/1 1600⍴1", "2/1 3000⍴1", "2/3000 1⍴1", "3/[1]1000 1⍴1"]:
        check(s, line)
    print("matrices: result size limits match the model")


if __name__ == "__main__":
    test_syntax()
    test_catenate()
    test_compress_expand()
    test_random()
    test_sizes()
