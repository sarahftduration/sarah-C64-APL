"""Transpose ⍉, without ~ and expand \\ against the model."""
import os
import random
import sys

sys.path.insert(0, os.getcwd())
from test_eval import Session, check
from test_reduce import rand_float

POOL = ["5", "1.5", "'a'", "0", "1", "1 2 3", "0 1 1", "1 0 1 1", "¯1 0 1 5", "32767 1", "¯32768 ¯1", "1.5 2.5 ¯3", "1e38 1e38",
        "'abc'", "'hello'", "''", "⍬", "1⍴7", "2 3", "3 1 2 3 1", "1 2.0 3", "'a'", "(2 3⍴⍳6)", "(3 2⍴⍳6)", "(2 2⍴1 0)", "(3 1⍴1 2 3)",
        "(1 3⍴4 5 6)", "(2 3⍴1.5)", "(3 2⍴'abcdef')", "(3 0⍴1)", "(0 3⍴1)", "(2 2⍴'abcd')", "(4 3⍴⍳12)", "1 0 0 1 1", "0 0 0"]


def test_transpose():
    s = Session()
    n = 0
    for a in POOL:
        for line in [f"⍉{a}", f"⍉⍉{a}", f"1 2⍉{a}", f"2 1⍉{a}", f"1⍉{a}", f"⍬⍉{a}", f"1 1⍉{a}", f"0⍉{a}", f"1 2 3⍉{a}", f"'a'⍉{a}", f"1.5⍉{a}",
                     f"(2 2⍴1)⍉{a}", f"2 1.0⍉{a}", f"3 1⍉{a}", f"¯1 2⍉{a}", f"(⍳2)⍉{a}"]:
            if n % 30 == 0:
                s.reset()
            check(s, line)
            n += 1
    print(f"transpose: {n} monadic and dyadic cases match the model")


def test_without():
    s = Session()
    kinds = {}
    n = 0
    for a in POOL:
        for b in POOL:
            if n % 30 == 0:
                s.reset()
            k = check(s, f"{a}~{b}")
            kinds[k] = kinds.get(k, 0) + 1
            n += 1
    print(f"without: {n} operand pairs match the model {dict(sorted(kinds.items()))}")


def test_expand():
    s = Session()
    kinds = {}
    n = 0
    for a in POOL:
        for b in POOL:
            if n % 30 == 0:
                s.reset()
            k = check(s, f"{a}\\{b}")
            kinds[k] = kinds.get(k, 0) + 1
            n += 1
    lines = ["1 0 1\\7 8", "1 1 1\\2 3 4", "0 0 0\\⍬", "0 0 0\\5", "1 0 1 0 1\\'abc'", "0 1\\1.5", "1 0\\32767", "0\\⍬", "1\\5", "(1 0 1)\\1 2", "1 0 1\\(1 2)",
             "1 0 1 1\\1 2 3", "1 0 1\\1 2 3", "1 0 1\\⍬", "1.0 0\\7", "1 ¯1\\1 2", "1 2\\1 2", "1e10 0\\1", "0 1 0\\'x'", "(⍳3)\\1", "1 0,1\\1 2",
             "1 0 1\\1 2 3 4", "A←1 0 1 ⋄ A\\4 5", "A←1 1 0 ⋄ B←A\\7 8 ⋄ B", "1 0 1\\(2 2⍴1)"]
    for line in lines:
        check(s, line)
    print(f"expand: {n} operand pairs and {len(lines)} more lines match the model {dict(sorted(kinds.items()))}")


def test_random():
    rng = random.Random(14)
    s = Session()
    for i in range(600):
        if i % 30 == 0:
            s.reset()
        r = rng.random()
        if r < .34:
            m, n = rng.randint(1, 5), rng.randint(1, 5)
            vals = " ".join(rng.choice(["0", "1", "7", "1.5", "32767", "¯1", rand_float(rng)]) for _ in range(m * n))
            check(s, rng.choice(["⍉", "2 1⍉", "1 2⍉"]) + f"({m} {n}⍴{vals})")
        elif r < .67:
            a = " ".join(rng.choice(["1", "2", "3", "1.5", "0", "¯1"]) for _ in range(rng.randint(0, 6)))
            b = " ".join(rng.choice(["1", "2", "3", "1.0", "0", "5"]) for _ in range(rng.randint(0, 5)))
            check(s, f"{a or '⍬'}~{b or '⍬'}")
        else:
            a = [rng.randint(0, 1) for _ in range(rng.randint(0, 8))]
            k = sum(a)
            b = " ".join(rng.choice(["1", "2.5", "32767", "¯4"]) for _ in range(k if rng.random() < .8 else k + 1))
            check(s, f"{' '.join(map(str, a)) or '⍬'}\\{b or '⍬'}")
    print("shape functions: 600 random transposes, withouts and expansions match the model")


def test_syntax():
    s = Session()
    for line in ["⍉", "⍉⍉", "1⍉", "⍉A", "A←2 3⍴⍳6 ⋄ ⍉A", "A←2 3⍴⍳6 ⋄ B←⍉A ⋄ ⍴B", "A←2 3⍴⍳6 ⋄ (⍉A)+⍉A", "A←2 3⍴⍳6 ⋄ A+.×⍉A", "+/⍉2 3⍴⍳6", "⍉+/2 3⍴⍳6", "⍉1 2 3∘.×1 2 3",
                 "1 2 3~", "~", "~1 2", "1 2 3~~1", "1 2 3~2~3", "(1 2 3~2)+1", "1+1 2 3~2", "A←1 2 3 4 ⋄ A~A[2]", "A←⍳5 ⋄ A~A>2", "A←⍳5 ⋄ A~A[3 4]", "\\1 2", "1 0\\", "1 0\\\\1 2",
                 "1 0 1\\⍳2", "(1 0 1)\\⍳2", "1 0 1\\+/1 2", "1 0 1\\1 2 ⋄ 3", "+\\1 0 1\\1 2", "+/1 0 1\\1 2", "A←1 0 1 ⋄ +/A\\1 2", "2⍴1 0 1\\1 2", "⍴1 0 1\\1 2", "⍳3\\1", "1 2 3∘.~1", "1 2+\\3", "1 0 1\\'ab'",
                 "⍉'abc'", "⍉''", "⍉⍬", "⍉2 3⍴'abcdef'", "⍉1 1⍴5", "⍉1 5⍴⍳5", "⍉5 1⍴⍳5", "'abc'~'b'", "'abc'~'B'", "'abc'~⍬", "⍬~'abc'", "1 2 3~2 3⍴⍳6", "1 2 3~(2 3⍴⍳6)", "3~3", "3~4", "'a'~'a'", "'a'~1"]:
        check(s, line)
    print("shape functions: syntax, NONCE and edge cases match the model")


def test_sizes():
    s = Session()
    for line in ["⍉10 100⍴1", "⍉20 100⍴1", "⍉30 50⍴1.5", "⍉20 40⍴1.5", "⍉40 40⍴1", "⍉50 60⍴1", "⍉1 3000⍴1", "⍉1 3001⍴1", "⍉3001 1⍴1", "(⍳1000)~1 2", "(⍳1500)~⍬", "(⍳1600)~⍬", "(⍳1600)~1600",
                 "(1000⍴1)\\1000⍴5", "(1000⍴1 0)\\500⍴5", "(1500⍴1 0)\\750⍴5", "(1600⍴1 0)\\800⍴5", "(3000⍴0)\\⍬", "(3001⍴0)\\⍬", "(3000⍴0)\\5", "(1500⍴1)\\1.5", "(1000⍴1)\\1.5"]:
        check(s, line)
    print("shape functions: result size limits match the model")


if __name__ == "__main__":
    test_syntax()
    test_transpose()
    test_without()
    test_expand()
    test_random()
    test_sizes()
