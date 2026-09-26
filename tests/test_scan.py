import os
import random
import sys

sys.path.insert(0, os.getcwd())
from test_eval import Session, check
from test_reduce import POOL, rand_float

GLYPHS = "+-×÷=≠<≤>≥⌈⌊|∧∨"
SCALARS_ONLY = [p for p in POOL if not p.startswith("(") and p not in ("⍬", "''")]

# operands for the outer product: scalars, vectors of every type, a few matrices
OUTER = ["5", "1.5", "'a'", "0", "1 2 3", "0 1 1", "¯1 0 1 5", "32767 1", "¯32768 ¯1", "1.5 2.5 ¯3", "1e38 1e38",
         "100 200", "'abc'", "1 0", "⍬", "''", "1⍴7", "2 3", "1e¯38 1", "(2 3⍴⍳6)", "(2 2⍴1 0)", "(3 0⍴1)", "(2 1⍴1 2)",
         "181 182 ¯181", "0 0", "3 1 2", "1 2 3 4 5 6 7 8", "40000 40000"]


def test_scan_pool():
    s = Session()
    kinds = {}
    n = 0
    for a in POOL:
        for g in GLYPHS:
            if n % 30 == 0:
                s.reset()
            n += 1
            k = check(s, f"{g}\\{a}")
            kinds[k] = kinds.get(k, 0) + 1
    print(f"scan: {n} function/operand combinations match the model {dict(sorted(kinds.items()))}")


def test_scan_random():
    """Prefix results change type part-way (INT overflowing to FLOAT), so the result is restarted wider."""
    rng = random.Random(21)
    s = Session()
    n = 0
    for i in range(1200):
        if i % 30 == 0:
            s.reset()
        g = rng.choice(GLYPHS + "+×-+×")
        kind = rng.random()
        if kind < .4:
            xs = [str(rng.choice([1, 2, 3, 7, 10, 100, 181, 200, 32767, -32768, 0, 5, 255, -1])).replace("-", "¯")
                  for _ in range(rng.randint(1, 9))]
        elif kind < .8:
            xs = [rand_float(rng) if rng.random() < .5 else str(rng.randint(-9, 9)).replace("-", "¯")
                  for _ in range(rng.randint(1, 8))]
        else:
            xs = [rng.choice(["1", "1.00001", "1.00003", "0.99999", "2", "0", "1e10", "¯1e10", "1e¯10"])
                  for _ in range(rng.randint(1, 8))]
        if rng.random() < .3:
            line = f"{g}\\({rng.randint(1, 4)} {rng.randint(1, 4)}⍴{' '.join(xs)})"
        else:
            line = f"{g}\\{' '.join(xs)}"
        check(s, line)
        n += 1
    print(f"scan: {n} random scans match the model")


def test_scan_exact_sums():
    """+\\ keeps its exact sum between prefixes (also when it is negative, which the rounding sees negated),
    so every prefix is the exact sum rounded once, however much cancels."""
    rng = random.Random(8)
    s = Session()
    n = 0
    for i in range(700):
        if i % 30 == 0:
            s.reset()
        xs = [rand_float(rng) for _ in range(rng.randint(2, 6))]
        if rng.random() < .5:
            xs += [x[1:] if x.startswith("¯") else "¯" + x for x in xs[:rng.randint(1, len(xs))]]
            rng.shuffle(xs)
        if rng.random() < .3:
            xs.insert(rng.randint(0, len(xs)), "1")
        line = "+\\" + " ".join(xs)
        if len(line.encode("utf-16")) > 250:
            continue
        check(s, line)
        n += 1
    print(f"scan: {n} random float running sums (with cancellation) match the model")


def test_outer_pool():
    """Every pair of operands, each with one of the functions in turn (test_outer_functions has them all)."""
    s = Session()
    kinds = {}
    fns = "+-×÷=<⌈|∧"
    n = 0
    for i, a in enumerate(OUTER):
        for j, b in enumerate(OUTER):
            if n % 30 == 0:
                s.reset()
            n += 1
            k = check(s, f"{a}∘.{fns[(i + j) % len(fns)]}{b}")
            kinds[k] = kinds.get(k, 0) + 1
    print(f"outer product: {n} operand pairs match the model {dict(sorted(kinds.items()))}")


def test_outer_functions():
    s = Session()
    n = 0
    for g in GLYPHS:
        for a, b in [("1 2 3", "4 5"), ("1.5 ¯2", "3 4 0.5"), ("0 1", "0 1"), ("32767 5", "1 2"), ("'ab'", "'bc'"),
                     ("1e38 1", "1e38 ¯1e38"), ("3", "1 2"), ("1 2", "3"), ("2", "3"), ("0 0", "0 0"), ("¯32768 1", "¯1 1")]:
            if n % 30 == 0:
                s.reset()
            n += 1
            check(s, f"{a}∘.{g}{b}")
    print(f"outer product: {n} function/operand combinations match the model")


def test_outer_random():
    rng = random.Random(33)
    s = Session()
    n = 0
    for i in range(600):
        if i % 30 == 0:
            s.reset()

        def vec():
            k = rng.random()
            m = rng.randint(1, 6)
            if k < .4:
                return " ".join(str(rng.choice([0, 1, 2, 3, 100, 181, 200, 32767, -32768, -1, 7])).replace("-", "¯") for _ in range(m))
            if k < .8:
                return " ".join(rand_float(rng) if rng.random() < .5 else str(rng.randint(-9, 9)).replace("-", "¯") for _ in range(m))
            return " ".join(rng.choice(["1", "0", "1.5", "0.1", "1e10"]) for _ in range(m))
        g = rng.choice(GLYPHS)
        check(s, f"{vec()}∘.{g}{vec()}")
        n += 1
    print(f"outer product: {n} random products match the model")


def test_syntax():
    s = Session()
    for line in ["∘.+1", "∘.+", "1 2∘.", "1 2∘.+", "1∘.+", "1 2∘+3", "1 2.+3 4", "1 2∘.⍳3", "1 2∘.⍴3", "1 2∘.,3", "1 2∘.~3", "1 2∘.⌽3",
                 "1 2∘.∘.+3", "A←1 2 ⋄ A∘.+A", "A←1 2 ⋄ B←A∘.×A ⋄ B", "(⍳3)∘.+(⍳3)∘.+⍳3", "1 2∘.+(3 4∘.×5 6)", "(1 2∘.+3 4)+1", "+/1 2 3∘.×1 2 3",
                 "+\\1 2 3∘.×1 2 3", "1+1 2∘.+3 4", "(2 2⍴1)∘.+1 2", "1 2∘.+2 2⍴1", "(2 2⍴1)∘.+(2 2⍴1)", "(2 2⍴1)∘.+3", "3∘.+2 2⍴1", "1 2 3∘.+⍬",
                 "⍬∘.+1 2 3", "⍬∘.+⍬", "''∘.=''", "1 2∘.+'a'", "'a'∘.=1 2", "A∘.+1", "1 2∘.+B", "A←1 2 ⋄ A[1]∘.+A",
                 "1 2 3∘.×1 2 3⋄5", "1 2 3∘.-1 2 3", "2 3∘.÷0 1", "0 1∘.÷0 1", "(⍳100)∘.+⍳100", "(⍳200)∘.+⍳200", "(⍳300)∘.+⍳300",
                 "(⍳20)∘.+⍳20", "(⍳50)∘.=⍳50", "(⍳100)∘.=⍳100", "(⍳40)∘.+⍳40", "1e10 1∘.×1e10 1", "1e10 ¯1e10∘.×1e30 1e10",
                 "\\1 2", "+\\", "+\\+\\1 2 3", "1 2\\3 4", "1+\\2 3", "+\\1 2 ⋄ +\\3 4", "A←+\\⍳5 ⋄ A", "A←⍳5 ⋄ A←+\\A ⋄ A", "(+\\1 2 3)+1", "+\\(1 2 3)",
                 "+\\(2 3⍴⍳6)", "⍴+\\2 3⍴⍳6", "-\\'ab'", "=\\'aab'", "≠\\'aab'", "=\\'a'", "+\\'a'", "-\\,5", "×\\⍬", "+\\''", "+\\3 0⍴1",
                 "+\\0 3⍴1" if False else "+\\1", "⍳\\1 2", "⍴\\1 2", ",\\1 2", "~\\1 2", "⌽\\1 2", "+\\[1]1 2", "+\\A", "+\\→1"]:
        check(s, line)
    print("scan and outer product: syntax, NONCE and edge cases match the model")


def test_sizes():
    """A result wider than its operand (BOOL scanned into INT) can be too big: WS FULL, but DOMAIN wins."""
    s = Session()
    for line in ["+\\(1000 3⍴1)", "+\\(1600 1⍴1)", "+\\(2 1500⍴1)", "+\\(2 1600⍴1)", "+\\3000⍴1", "+\\1600⍴1", "+\\1500⍴1", "+\\1499⍴1",
                 "×\\(1000 3⍴1.5)", "×\\(600 3⍴1.5)", "+\\1000⍴32767", "+\\(1 1400⍴32767)", "+\\1400⍴1.5", "+\\1000⍴1.5",
                 "÷\\(1000 2⍴2)", "÷\\(1100 2⍴0 1)", "-\\(1000 2⍴1 0)", "≠\\(1000 3⍴1)", "∧\\(1600 2⍴1)",
                 "(⍳1000)∘.+1 2", "(⍳1500)∘.+1", "(⍳1000)∘.=⍳2", "(⍳500)∘.=⍳500", "(⍳2000)∘.+⍳2",
                 "(⍳1000)∘.+⍳3", "(⍳100)∘.=⍳20", "(⍳100)∘.+⍳20", "(⍳100)∘.÷⍳15", "(⍳100)∘.÷0 1", "(⍳200)∘.=⍳100", "(⍳200)∘.≤⍳200",
                 "(100⍴1)∘.+100⍴1", "(1000⍴'a')∘.+1 2"]:
        check(s, line)
    print("scan and outer product: result size and DOMAIN ordering match the model")


if __name__ == "__main__":
    test_syntax()
    test_scan_pool()
    test_scan_random()
    test_scan_exact_sums()
    test_outer_pool()
    test_outer_functions()
    test_outer_random()
    test_sizes()
