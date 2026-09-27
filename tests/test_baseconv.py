"""Decode B⊥V and encode B⊤V against the model."""
import os
import random
import sys

sys.path.insert(0, os.getcwd())
from test_eval import Session, check
from test_reduce import rand_float

BASES = ["2", "10", "1", "0", "¯1", "1.5", "2 3", "2 2 2", "24 60 60", "1 0 1", "0 24", "10 10", "2 0 2",
         "¯2 3", "1.5 2", "0 0", "⍬", "2 3 4 5", "'a'"]
VALS = ["5", "0", "1", "¯5", "1.5", "9000", "123", "40000", "¯32768", "32767", "1e38", "0.5", "'a'", "⍬", "''",
        "1 0 1", "0 1 1", "1 2 3", "¯1 0 5", "1.5 2.5", "1e38 1e38", "'abc'", "2 3 4", "5 6", "(2 3⍴⍳6)", "(2 2⍴1 0 1 1)"]


def test_syntax():
    s = Session()
    for line in ["2⊥5", "2⊤5", "⊥5", "⊤5", "⊥", "⊤", "2⊥", "2⊤", "A←2 3⍴⍳6 ⋄ 2⊥A", "A←2 3⍴⍳6 ⋄ 2⊤A", "(2 3⍴1)⊥1 2 3",
                 "2 3⊤(2 2⍴1)", "2 3 4⊥1", "2 3 4⊤5", "0 24⊥3", "3⊥1 2", "2⊥'a'", "'a'⊥1", "2⊤'a'", "'a'⊤1",
                 "A←2⊥1 0 1 ⋄ A", "A←2 3⊤5 ⋄ A", "2⊥1 0 1 ⋄ 1", "+/2⊥1 0 1", "2⊥1+1 0 1", "(2⊥1 0 1)+1",
                 "A←5 ⋄ A⊥1 0", "A←5 ⋄ 1 0⊤A"]:
        check(s, line)
    print("baseconv: syntax, NONCE and edge cases match the model")


def test_pool():
    s = Session()
    kinds = {}
    n = 0
    for b in BASES:
        for v in VALS:
            if n % 30 == 0:
                s.reset()
            k = check(s, f"{b}⊥{v}")
            kinds[k] = kinds.get(k, 0) + 1
            n += 1
            k = check(s, f"{b}⊤{v}")
            kinds[k] = kinds.get(k, 0) + 1
            n += 1
    print(f"baseconv: {n} base/value combinations match the model {dict(sorted(kinds.items()))}")


def test_random():
    rng = random.Random(11)
    s = Session()
    n = 0
    for i in range(600):
        if i % 30 == 0:
            s.reset()
        nb = rng.randint(1, 4)
        bvals = " ".join(rng.choice(["0", "1", "2", "3", "10", "24", "60", "¯1", "100", rand_float(rng)]) for _ in range(nb))
        base = bvals if nb > 1 else rng.choice([bvals, f"({bvals})"])
        if rng.random() < 0.5:
            v = rng.choice(["5", "0", "¯5", "9000", "32767", "40000", rand_float(rng)])
            check(s, f"{base}⊤{v}")
        else:
            m = rng.randint(1, 5)
            vvals = " ".join(rng.choice(["0", "1", "2", "5", "60", "¯1", "100", rand_float(rng)]) for _ in range(m))
            check(s, f"{base}⊥{vvals}")
        n += 1
    print(f"baseconv: {n} random decodes and encodes match the model")


def test_matrices():
    """Decode of a matrix V (one result per column) and its round trip through encode."""
    s = Session()
    n = 0
    mats = ["(2 3⍴1 0 1 0 1 1)", "(3 2⍴1 1 0 3 2 1)", "(2 3⍴1.5 2 ¯1 0 3 1)", "(3 3⍴⍳9)", "(2 0⍴1)", "(0 3⍴1)"]
    for b in ["2", "10", "2 3", "1.5 2", "24 60"]:
        for m in mats:
            if n % 30 == 0:
                s.reset()
            check(s, f"{b}⊥{m}")
            n += 1
    for line in ["A←2 3⍴⍳6 ⋄ B←2⊥A ⋄ B←2⊤B ⋄ B", "A←24 60 60⊥2 3⍴2 30 0 1 15 45 ⋄ A", "24 60 60⊤24 60 60⊥2 30 0",
                 "2⊤2⊥1 0 1", "10⊥10⊤123"]:
        check(s, line)
    print(f"baseconv: {n} matrix decodes plus round trips match the model")


if __name__ == "__main__":
    test_syntax()
    test_pool()
    test_random()
    test_matrices()
