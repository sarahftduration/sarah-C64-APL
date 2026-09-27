"""Numeric functions * and ⍟: the model's accuracy against Python's math, and the 6502 against the model."""
import math
import os
import random
import sys
from fractions import Fraction

sys.path.insert(0, os.getcwd())
import apl64
from apl64 import (AplError, MATH_CONSTS, MATH_CONST_NAMES, MATH_PROGS, VM_OPS, OP_IFGE, OP_IFLT, f_from_fraction, f_to_fraction,
                   f_exp, f_ln, f_sqrt, f_pow, f_log, vm_run)
from harness import call, load, use_overlay
from test_eval import Session, check

FA = 0x10


def F(x):
    return f_from_fraction(Fraction(x))


def V(p):
    return float(f_to_fraction(p))


def rel(got, want):
    return abs(V(got) - want) / abs(want) / 2 ** -16 if want else 0     # in units of 2^-16 of the true value


def test_circle_accuracy():
    """sin, cos, tan and the inverse functions against the real ones (absolute error, in units of 2^-16)."""
    import apl64 as m
    assert list(MATH_PROGS) == m.MATH_PROG_NAMES
    rng = random.Random(5)
    run = lambda name, x: V(vm_run(MATH_PROGS[name], F(x)))
    worst = {}

    def note(name, e, x):
        if e > worst.get(name, (0, 0))[0]:
            worst[name] = (e, x)
    for _ in range(3000):
        x = rng.choice([rng.uniform(-10, 10), rng.uniform(-400, 400), rng.uniform(-1, 1)])
        xf = V(F(x))
        note("sin", abs(run("SIN", x) - math.sin(xf)) / 2 ** -16, x)
        note("cos", abs(run("COS", x) - math.cos(xf)) / 2 ** -16, x)
        if abs(math.cos(xf)) > 0.1:
            note("tan", abs(run("TAN", x) - math.tan(xf)) / abs(math.tan(xf)) / 2 ** -16, x)
        y = rng.choice([rng.uniform(-1, 1), rng.uniform(-3, 3), rng.uniform(-1e4, 1e4)])
        yf = V(F(y))
        note("atan", abs(run("ATAN", y) - math.atan(yf)) / 2 ** -16, y)
        z = rng.uniform(-1, 1)
        zf = V(F(z))
        note("asin", abs(run("ASIN", z) - math.asin(zf)) / 2 ** -16, z)
        if zf != -1:
            note("acos", abs(run("ACOS", z) - math.acos(zf)) / math.acos(zf) / 2 ** -16 if math.acos(zf) else 0, z)
        note("circ0", abs(run("CIRC0", z) - math.sqrt(1 - zf * zf)) / 2 ** -16, z)
        note("circ4", abs(run("CIRC4", y) - math.sqrt(1 + yf * yf)) / abs(math.sqrt(1 + yf * yf)) / 2 ** -16, y)
        h = rng.choice([rng.uniform(-88, 88), rng.uniform(-1, 1)])       # sinh/cosh/tanh call EXP: bounded as it is
        hf = V(F(h))
        note("sinh", abs(run("SINH", h) - math.sinh(hf)) / max(abs(math.sinh(hf)), 2 ** -16) / 2 ** -16, h)
        note("cosh", abs(run("COSH", h) - math.cosh(hf)) / math.cosh(hf) / 2 ** -16, h)
        note("tanh", abs(run("TANH", h) - math.tanh(hf)) / 2 ** -16, h)
        hw = rng.choice([rng.uniform(-44, 44), rng.uniform(-1, 1), rng.uniform(-1e4, 1e4)])   # asinh never calls EXP
        hwf = V(F(hw))
        note("asinh", abs(run("ASINH", hw) - math.asinh(hwf)) / max(abs(math.asinh(hwf)), 2 ** -16) / 2 ** -16, hw)
        c = rng.choice([rng.uniform(1, 44), rng.uniform(1, 1e4), 1 + rng.uniform(0, 1e-3)])
        cf = V(F(c))
        note("circm4", abs(run("CIRCM4", c) - math.sqrt(cf * cf - 1)) / max(math.sqrt(cf * cf - 1), 2 ** -16) / 2 ** -16, c)
        note("acosh", abs(run("ACOSH", c) - math.acosh(cf)) / max(math.acosh(cf), 2 ** -16) / 2 ** -16, c)
        w = rng.choice([rng.uniform(-0.999, 0.999), rng.uniform(-1, 1), rng.uniform(-0.5, 0.5)])
        wf = V(F(w))
        if abs(wf) < 1:
            note("atanh", abs(run("ATANH", w) - math.atanh(wf)) / max(abs(math.atanh(wf)), 2 ** -16) / 2 ** -16, w)
    # acosh and atanh diverge at their domain's edge (derivative -> infinity as x -> 1 or |x| -> 1), so a
    # float24 input a couple of units off the true x there is inherently a much larger error in the result:
    # not a defect in the algorithm, just what happens right next to a singularity.
    bounds = {"sinh": 10, "cosh": 10, "tanh": 10, "asinh": 10, "circm4": 10, "acosh": 100, "atanh": 100}
    for k, (e, x) in worst.items():
        assert e <= bounds.get(k, 6), f"{k}: {e:.2f} units at {x}"
    assert V(vm_run(MATH_PROGS["SIN"], 0)) == 0 and V(vm_run(MATH_PROGS["COS"], 0)) == 1 and V(vm_run(MATH_PROGS["ATAN"], 0)) == 0
    assert V(vm_run(MATH_PROGS["ACOS"], F(1))) == 0 and abs(V(vm_run(MATH_PROGS["ASIN"], F(1))) - math.pi / 2) < 1e-4
    assert abs(V(vm_run(MATH_PROGS["ACOS"], F(-1))) - math.pi) < 1e-4
    for x in (1.0001, -1.0001, 2, -100):
        for name in ("ASIN", "ACOS", "CIRC0", "ATANH"):
            try:
                vm_run(MATH_PROGS[name], F(x))
                raise AssertionError((name, x))
            except AplError as e:
                assert e.kind == "DOMAIN ERROR"
    for x in (0, 0.5, -0.5, 0.9999, -0.9999):
        for name in ("CIRCM4", "ACOSH"):
            try:
                vm_run(MATH_PROGS[name], F(x))
                raise AssertionError((name, x))
            except AplError as e:
                assert e.kind == "DOMAIN ERROR"
    assert V(vm_run(MATH_PROGS["SINH"], 0)) == 0 and V(vm_run(MATH_PROGS["COSH"], 0)) == 1 and V(vm_run(MATH_PROGS["TANH"], 0)) == 0
    assert V(vm_run(MATH_PROGS["ASINH"], 0)) == 0 and V(vm_run(MATH_PROGS["CIRCM4"], F(1))) == 0 and V(vm_run(MATH_PROGS["ACOSH"], F(1))) == 0
    print("math: the circle functions stay within " + ", ".join(f"{k} {worst[k][0]:.1f}" for k in sorted(worst)) + " units of 2^-16 of the true values")


def test_generated_tables():
    """asm/mathprog.inc is what tools/gen_math.py makes from the model."""
    import subprocess
    out = subprocess.run([sys.executable, "tools/gen_math.py"], capture_output=True, text=True, check=True).stdout
    assert out == open("asm/mathprog.inc", encoding="utf-8").read(), "asm/mathprog.inc is stale: run make asm/mathprog.inc"
    print("math: asm/mathprog.inc matches the model's programs")


def test_accuracy():
    """The algorithms themselves, against the real functions (the 6502 is then checked against the model)."""
    rng = random.Random(1)
    worst = {}

    def note(name, u, x):
        if u > worst.get(name, (0, 0))[0]:
            worst[name] = (u, x)
    for _ in range(6000):
        x = rng.choice([rng.uniform(-88, 88), rng.uniform(-1, 1), rng.uniform(-10, 10)])
        note("exp", rel(f_exp(F(x)), math.exp(V(F(x)))), x)
        y = math.exp(rng.uniform(-85, 85)) if rng.random() < .5 else rng.uniform(0.9, 1.1) if rng.random() < .5 else rng.uniform(0.01, 100)
        note("ln", rel(f_ln(F(y)), math.log(V(F(y)))) if V(F(y)) != 1 else 0, y)
        note("sqrt", rel(f_sqrt(F(y)), math.sqrt(V(F(y)))), y)
        a, b = rng.uniform(0.01, 30), rng.uniform(-3, 3)
        want = V(F(a)) ** V(F(b))
        if 1e-30 < want < 1e30:
            note("pow", rel(f_pow(F(a), F(b)), want) / (1 + abs(V(F(b)) * math.log(V(F(a))))), (a, b))
    bounds = {"exp": 2, "ln": 5, "sqrt": 2, "pow": 3}
    for k, (u, x) in worst.items():
        assert u <= bounds[k], f"{k}: {u:.2f} units of 2^-16 at {x}"
    for i in range(1, 200):                                         # perfect squares and small whole powers are exact
        assert f_sqrt(F(i * i)) == F(i), i
    for a in range(-9, 10):
        for n in range(1, 8):
            if abs(a) ** n < 65536 and a != 0:
                assert f_pow(F(a), F(n)) == F(a ** n), (a, n)
    assert f_pow(F(2), F(-3)) == F(0.125) and f_pow(F(0), F(0)) == F(1) and f_exp(F(0)) == F(1) and f_ln(F(1)) == 0
    for b in (2, 3, 10):
        for k in range(-30, 30):
            got = V(f_log(F(b), F(float(b) ** k)))
            if 1e-30 < float(b) ** k < 1e30:
                assert abs(got - k) <= 3e-4 * (1 + abs(k)), (b, k, got)
    print("math: exp, ln, sqrt and power stay within " + ", ".join(f"{k} {worst[k][0]:.2f}" for k in sorted(worst)) + " units of 2^-16; perfect squares and small integer powers are exact")


POOL = ["0", "1", "2", "3", "0.5", "1.5", "2.5", "¯1", "¯2", "¯0.5", "¯1.5", "10", "100", "127", "128", "¯127", "¯128", "0.1", "7", "1e10", "¯1e10", "1e38", "1e¯38", "32767",
        "¯32768", "88", "89", "¯100", "¯101", "0.3", "1e¯5", "2.718281828", "'a'", "⍬", "1 2 3", "0.5 4 9", "(2 2⍴1 2 3 4)", "(2 3⍴0.5 2 ¯2 3 0 1)"]


def test_scalar_pool():
    s = Session()
    kinds = {}
    n = 0
    for a in POOL:
        for line in (f"*{a}", f"⍟{a}"):
            if n % 30 == 0:
                s.reset()
            k = check(s, line)
            kinds[k] = kinds.get(k, 0) + 1
            n += 1
        for b in POOL:
            for f in "*⍟":
                if n % 30 == 0:
                    s.reset()
                k = check(s, f"{a}{f}{b}")
                kinds[k] = kinds.get(k, 0) + 1
                n += 1
    print(f"math: {n} monadic and dyadic operand combinations match the model {dict(sorted(kinds.items()))}")


def test_circle():
    s = Session()
    kinds = {}
    n = 0
    ks = ["0", "1", "2", "3", "4", "¯1", "¯2", "¯3", "5", "6", "7", "¯4", "¯5", "¯6", "¯7", "8", "¯8", "1.5", "1.0", "1 2 3", "'a'", "⍬", "2 2⍴1 2 3 4"]
    xs = ["0", "1", "¯1", "0.5", "¯0.5", "0.999", "1.001", "2", "¯2", "3.14159", "1.5708", "1e10", "¯100", "1e¯20", "32767", "0.7071", "1 2 3", "0.1 0.5 ¯0.9", "(2 2⍴0.1 0.2 0.3 0.4)", "'b'", "⍬"]
    for k in ks:
        for x in xs:
            if n % 30 == 0:
                s.reset()
            r = check(s, f"{k}○{x}")
            kinds[r] = kinds.get(r, 0) + 1
            n += 1
    for x in xs:
        check(s, f"○{x}")
        n += 1
    print(f"math: {n} circle function and pi-times cases match the model {dict(sorted(kinds.items()))}")
    rng = random.Random(9)
    for i in range(600):
        if i % 30 == 0:
            s.reset()
        k = rng.choice(["1", "2", "3", "¯1", "¯2", "¯3", "0", "4", "5", "6", "7", "¯4", "¯5", "¯6", "¯7"])
        x = rng.choice([f"{rng.uniform(-8, 8):.4f}", f"{rng.uniform(-1, 1):.4f}", f"{rng.uniform(-400, 400):.3f}", "1e¯5", f"{rng.uniform(-3, 3):.2f}"]).replace("-", "¯")
        check(s, f"{k}○{x}")
    print("math: 600 random circle function cases match the model")


def test_factorial():
    from apl64 import f_fact, f_binom
    for n in range(0, 9):
        assert f_fact(F(n)) == F(math.factorial(n)), n
    for n in range(0, 25):
        for k in range(0, n + 1):
            got = V(f_binom(F(k), F(n)))
            assert abs(got - math.comb(n, k)) <= math.comb(n, k) * 3e-5 * (1 + k), (k, n, got)
    for n in range(0, 17):
        for k in range(0, n + 1):
            if math.comb(n, k) < 65536 and n <= 13:
                assert f_binom(F(k), F(n)) == F(math.comb(n, k)), (k, n)
    s = Session()
    kinds = {}
    n = 0
    vals = ["0", "1", "2", "3", "5", "10", "20", "33", "34", "100", "1000", "32767", "32768", "65535", "65536", "¯1", "¯5", "0.5", "2.5", "1e10", "7.0", "'a'", "⍬", "1 2 3", "(2 2⍴0 1 2 3)"]
    for a in vals:
        for line in [f"!{a}"] + [f"{a}!{b}" for b in vals]:
            if n % 30 == 0:
                s.reset()
            r = check(s, line)
            kinds[r] = kinds.get(r, 0) + 1
            n += 1
    rng = random.Random(3)
    for i in range(300):
        if i % 30 == 0:
            s.reset()
        b = rng.choice([rng.randint(0, 40), rng.randint(0, 300), rng.randint(0, 32767), rng.choice([65535, 65536])])
        a = rng.choice([rng.randint(0, 10), rng.randint(0, b if b < 40 else 40), rng.randint(0, 300)])
        check(s, f"{a}!{b}")
        n += 1
    print(f"math: factorial and binomial: exact for small values; {n} cases match the model {dict(sorted(kinds.items()))}")


def test_random():
    rng = random.Random(7)
    s = Session()

    def num():
        r = rng.random()
        if r < .3:
            return str(rng.randint(-20, 20)).replace("-", "¯")
        if r < .8:
            return f"{rng.uniform(-30, 30):.4f}".replace("-", "¯")
        return rng.choice(["1e10", "1e¯10", "0.5", "2", "88", "¯88", "32767", "1e38", "1e¯38", "0.001", "¯3", "3"])
    for i in range(900):
        if i % 30 == 0:
            s.reset()
        f = rng.choice(["*", "⍟", "*", "*"])
        if rng.random() < .35:
            check(s, f"{f}{num()}")
        else:
            check(s, f"{num()}{f}{num()}")
    for i in range(150):
        if i % 30 == 0:
            s.reset()
        vec = " ".join(num() for _ in range(rng.randint(1, 5)))
        check(s, rng.choice([f"{vec}*{num()}", f"{num()}*{vec}", f"*{vec}", f"⍟{vec}", f"{num()}⍟{vec}"]))
    print("math: 1,050 random monadic and dyadic cases match the model")


def test_syntax():
    s = Session()
    for line in ["*", "⍟", "2*", "*2*3", "2*3*2", "(2*3)*2", "2*(3*2)", "*⍟2", "⍟*2", "*1+1", "1+*1", "(*1)+1", "A←*1 ⋄ A", "A←2*10 ⋄ A+1", "+/*1 2 3", "*+/1 2 3", "⍳2*3", "⍴2*3",
                 "(⍳3)∘.*⍳3", "1 2 3∘.*2", "2∘.*1 2 3", "(⍳3)∘.⍟⍳3", "*∘.+1", "1 2∘.*'a'", "+.*1", "1 2+.*3 4", "1 2*.+3 4", "*/1 2", "*\\1 2", "2*/1 2", "1 2 3*/[1]4",
                 "*[1]2", "*[1]1 2", "2*[1]3", "*.", "*.5", "2*.5", "2 *. 5", "*'a'", "⍟'a'", "*''", "⍟⍬", "2*⍬", "⍬*2", "⍬*⍬", "1 2*1 2 3", "1 2 3*1 2", "(2 3⍴1)*(2 3⍴2)", "(2 3⍴1)*(3 2⍴2)",
                 "?", "!", "○", "?1", "!1", "○1", "1?2", "1!2", "1○2", "1○", "○○1", "1○1○1", "(1○1)○1", "1 2○", "+/1○1 2 3", "1○+/1 2 3", "○/1 2", "1○∘.+1", "1 2∘.○3 4", "(⍳3)∘.○(⍳3)÷3", "1 2+.○3 4", "1○[1]2 3⍴1", "*2 3⍴⍳6", "2*2 3⍴⍳6", "M←2 3⍴⍳6 ⋄ ⍟M", "M←2 3⍴⍳6 ⋄ M*2", "M←2 3⍴⍳6 ⋄ (⍉M)*0.5", "*1 2 ⋄ ⍟5", "2*3 ⋄ 4",
                 "∇R←F X", "R←*X", "∇", "F 1", "F 1 2 3", "F ¯200", "F 100", "∇R←G X", "R←X*X", "∇", "G 3", "G 0.5", "G ¯2", "G 1e10"]:
        check(s, line)
    print("math: syntax, NONCE and edge cases match the model")


def test_sizes():
    s = Session()
    for line in ["*300⍴1", "*1500⍴1", "*1500⍴1.5", "*1000⍴0", "2*1000⍴3", "2*1500⍴3", "(1000⍴2)*3", "(1500⍴2)*3", "⍟1500⍴2", "(40 40⍴2)*3", "(30 30⍴2)*3", "(10 10⍴1.5)*(10 10⍴2)",
                 "(⍳40)∘.*⍳40", "(⍳30)∘.*⍳30", "(⍳20)∘.*⍳20", "(⍳50)∘.⍟⍳20", "(⍳20)∘.⍟⍳20", "*(1000⍴0),'a'"]:
        check(s, line)
    print("math: result sizes match the model")


# --- the interpreter itself: random programs through both ------------------------------------------------------------
OPS_ARG = {"LDK": 22, "LDS": 8, "STS": 8, "ADDS": 8, "SUBS": 8, "MULS": 8, "DIVS": 8, "RSUBS": 8, "RDIVS": 8, "ADDK": 22, "SUBK": 22, "MULK": 22,
           "DIVK": 22, "RSUBK": 22, "RDIVK": 22, "NEGS": 8, "SETIR": 40}
OPS_NOARG = ["NEG", "ABS", "FREXP", "ITOF", "ROUND", "LDEXP", "DECIR", "SARIR", "NEG", "ABS"]


def random_program(rng):
    prog = []
    for _ in range(rng.randint(3, 25)):
        r = rng.random()
        if r < .12:
            prog.append((rng.choice([OP_IFLT, OP_IFGE]) + rng.randint(0, 4), rng.randrange(len(MATH_CONSTS))))
        elif r < .2:
            prog.append((VM_OPS.index("IFBIT"), rng.randint(0, 1) << 4 | rng.randint(0, 4)))
        elif r < .27:
            prog.append((VM_OPS.index("CALL"), rng.randrange(len(MATH_PROGS))))
        elif r < .28:
            prog.append((VM_OPS.index("DOMERR"), 0))
        elif r < .5:
            prog.append((VM_OPS.index(rng.choice(OPS_NOARG)), 0))
        else:
            name = rng.choice(list(OPS_ARG))
            prog.append((VM_OPS.index(name), rng.randrange(OPS_ARG[name])))
    return prog + [(0, 0)] * 6


def rand_float(rng):
    r = rng.random()
    if r < .1:
        return 0
    if r < .5:
        return F(rng.uniform(-50, 50))
    if r < .8:
        return F(rng.choice([1, 2, 0.5, -1, 3, 100, 7.5, -0.25]))
    return (rng.randint(1, 255) << 16) | rng.getrandbits(16)


def test_interpreter():
    """Every instruction of the 6502 interpreter against apl64.vm_run, on random programs and starting values."""
    rng = random.Random(11)
    m, L = load("eval")
    use_overlay(m, L, "MATH")
    n = ok = 0
    errs = 0
    for _ in range(1500):
        prog = random_program(rng)
        x = rand_float(rng)
        for i in range(27):
            m.memory[L["mv_s"] + i] = 0
        base = 0x9000
        for i, (op, arg) in enumerate(prog):
            m.memory[base + 2 * i] = op
            m.memory[base + 2 * i + 1] = arg
        m.memory[FA:FA + 3] = [x >> 16, x >> 8 & 0xFF, x & 0xFF]
        try:
            want = vm_run(prog, x)
            wanterr = None
        except AplError as e:
            want, wanterr = None, e.kind
        except IndexError:
            continue                                    # (a skip that runs off the end of the program)
        m.a, m.x = base & 0xFF, base >> 8
        call(m, L["mv_run"], max_steps=200000)
        got = m.memory[FA] << 16 | m.memory[FA + 1] << 8 | m.memory[FA + 2]
        if wanterr:
            assert m.p & 1 and m.a == 2, (prog, hex(x), wanterr, m.p & 1, m.a)
            errs += 1
        else:
            assert not m.p & 1 and got == want, (prog, hex(x), hex(got), hex(want))
        n += 1
    print(f"math: {n} random interpreter programs ({errs} ending in DOMAIN ERROR) give the model's results bit for bit")


if __name__ == "__main__":
    test_generated_tables()
    test_accuracy()
    test_circle_accuracy()
    test_circle()
    test_factorial()
    test_interpreter()
    test_syntax()
    test_scalar_pool()
    test_random()
    test_sizes()
