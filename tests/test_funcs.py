"""User-defined functions on the 6502 (py65) against the model: the del editor and, from the
call machinery on, calls. Sessions of lines are run through do_line one after the other;
after each line the echo (or error) and every variable and function block must agree.
"""
import os
import random
import sys

sys.path.insert(0, os.getcwd())
import apl64
from harness import call
from test_eval import Session, check

D = "∇"

DEFS = [
    # each list is one session
    [D + "R←SQ X", "R←X×X", D],
    [D + "R←A ADD B", "R←A+B", "", D, D + "R←A ADD B", D],
    [D + "F", D, D + "F", "1", "2", D],
    [D + "R←K", "R←42", D, D + "K", D],
    [D + "SHOW X", "X", "X+1", D],
    [D + "R←F X;T;U", "T←X", D, D + "R←F X;T;U", D],
    [D + "A F B;C", "C←A+B", "C", D],
    [D + "R←F", "R←1", D, D + "G←F", D],
    [D + "  R←F X  ;  T  ", D],
    [D + "R←F X;T", "  " + D + "  ", "1"],
    ["\t" + D + "F", "\t" + D + "\t"],
    ["V←5", D + "V", D + "R←V X", D + "R←F V", D + "F V", D + "V F 1"],
    [D, D + " ", D + "1", D + "1 2", D + "'a'", D + "(F)", D + "F[1]", D + "F ← 1", D + "R←", D + "←F", D + "R←←F",
     D + "A F B C", D + "R←A F B C", D + "F X;", D + "F X;;Y", D + "F X;1", D + "F;X;X", D + "F X;F", D + "F F",
     D + "X F X", D + "R←R F X", D + "R←X F X", D + "R←F X;R", D + "A B C D", D + "F X Y"],
    [D + "F;X", D + "R F X", D],
    [D + "R F X", "R+X", D + "F;X", D],
    [D + "R←F X", "(1", "1)", "1[", "'unclosed", "1 2 3", "R←X→", "1 ⋄ 2", "⍝ comment", "", "A←", D, D + "F"],
    [D + "F", "!", "@", "1 'a'", "R←X", D, D + "G", D + "1"],
    [D + "R←F X", "R←" + "X+" * 60 + "1", D],
    [D + "R←F X", "'" + "a" * 200 + "'", "2 3⍴⍳6", "1.5 ¯2 1e10 40000", "⍬", D],
    [D + "F", "F", D, D + "F", "G", D, D + "G", D],
    [D + "F", D + "F", D + "F", D],
    ["A←1", D + "F", "A", D + "G X;A", "A", D, "A"],
    [D + "F", "1", D, "B←2", "B", D + "F", "2", D, "C←3"],
]


def run(session_lines, s=None):
    s = s or Session()
    s.reset()
    kinds = []
    for line in session_lines:
        kinds.append(check(s, line))
    return kinds


def test_definitions():
    n = 0
    for lines in DEFS:
        run(lines)
        n += len(lines)
    print(f"functions: {len(DEFS)} definition sessions ({n} lines): headers, bodies and errors match the model")


CALLS = [
    [D + "R←SQ X", "R←X×X", D, "SQ 5", "SQ 1 2 3", "1+SQ 3", "SQ SQ 3", "(SQ 2)+SQ 3", "SQ 2 3⍴⍳6", "A←SQ 4", "A"],
    [D + "R←A ADD B", "R←A+B", D, "1 ADD 2", "1 2 3 ADD 10", "ADD 1", "1 ADD 2 ADD 3", "(1 ADD 2)ADD 3", "3 ADD"],
    [D + "R←K", "R←42", D, "K", "K+1", "2×K", "K K", "K,K", "⍳K", "A←K", "A", "(K)", "K[1]", "K K K"],
    [D + "SHOW X", "X", "X+1", D, "SHOW 5", "SHOW 1 2", "1+SHOW 1", "A←SHOW 1", "(SHOW 1)", "SHOW SHOW 1"],
    [D + "SET X", "G←X", D, "SET 7", "G", "A←SET 1", "G"],
    [D + "R←F X;T", "T←X+1", "R←T×2", D, "T←9", "F 1", "T", "F 2", "T"],
    [D + "R←F X", "R←G X", D, D + "R←G X", "R←X+1", D, "F 1", "2+F 3"],
    [D + "R←SUM N", "R←N+SUM N-1", D, "SUM 3", "1"],
    [D + "R←N NOP", "R←N", D, "3 NOP 4", "NOP 4"],
    [D + "F", "1", "G←2", D, "F", "G", "F←3"],
    [D + "R←F X", "R←X", "(1", D, "F 1"],
    [D + "R←F X", "R←X→", D, "F 1"],
    [D + "F X", "Y←X", D, "F 3", "Y", "(F 4)", "1+F 4", "A←F 4"],
    [D + "R←F X", "R←X", D, "F", "A←1 ⋄ F A", "F A A", "A F A"],
    [D + "R←F X;Y", "Y←5", "R←Y+X", D, "Y←1", "F 10", "Y", D + "R←G X", "R←Y+F X", D, "G 1", "Y"],
    [D + "R←F X", "R←Q", D, "F 1", "Q←7", "F 1"],
    [D + "R←F X", "R←1÷0", D, "A←3", "F A", "A"],
    [D + "R←F X;A", "A←0", "R←1÷0", D, "A←33", "F 1", "A"],
    ["A←⍳3", D + "R←F X", "R←A[X]", D, "F 2", "F 9"],
    [D + "R←F X;A", "A←⍳3", "A[2]←X", "R←A", D, "F 9", "A"],
    [D + "R←F X", "R←+/X", D, "F ⍳5", "F 2 3⍴⍳6"],
    [D + "F X", "⍴X", "⍳X", D, "F 3", "F←⍳⍴"],
    [D + "R←F X", "R←X+1", "R←R×2", D, "F 1", "F F 1", "F F F 1", "1+F 1", "F 1+F 1", "A←F 1 ⋄ A"],
    [D + "R←A F B", "R←A-B", D, "10 F 3", "F 3", "(1 2) F 3", "1 2 F 3 4", "1 2 F 3 4 5", "10 F 3 F 1", "(10 F 3)F 1"],
    [D + "R←F X;X", D, D + "R←F X;Y;Z", "Y←1", "Z←2", "R←X+Y+Z", D, "F 1", "F 5"],
    [D + "R←F X", "X←X+1", "R←X", D, "A←1", "F A", "A"],
    [D + "R←F", "R←1", D, D + "R←G", "R←F+1", D, "G", "F", "F G", "G+F"],
    [D + "F", D, "F", "F F", "A←F", "(F)"],
    [D + "F", "1 ⋄ 2", "3", D, "F", "A←F ⋄ F"],
    [D + "R←F X", "R←X", D, "V←3", "F V", "V←F 4", "V", D + "R←G Y", "R←Y", D, "G F 5"],
    [D + "R←F X", "R←X", D, "F←1", "F", "A←1", "A F", "F"],
    [D + "R←F X;F", D],
    [D + "R←F X", "R←X", D, D + "R←G X;F", "R←F 1", D, "G 1"],
    [D + "R←F X", "R←X[1]", D, "F 1 2 3", "F 5", "F ⍬"],
    [D + "F X", "A←X", "A[1]←9", D, "F 1 2", "A"],
    [D + "F", "T[1]←1", D, "T←⍳2", "F", "T", D + "N", "N[1]←3", D, "N"],
    [D + "R←F X", "R←X", D, "F[1]←2", "F 1[1]", "(F 1)[1]", "F[1]", "1 F[1]"],
    [D + "R←F X", "R←X", D, "F/1 2", "+/F 1 2", "F¨1", "F.+1"],
    [D + "F", "1", D, D + "A G B", "A", D, "1 G 2", "(1+2)G 3", "1 G (2)", "F+1", "1+F", "F F", "(F)", "F ⋄ 1", "F ⋄ F", "G", "1 G 2 G 3"],
    [D + "F", "1", D, D + "A G B", "A", D, "((1)-2)G 3", "((1 2)-1)G 3", "A←(1 G 2)", "(1 G 2)+1", "1+(1 G 2)", "⍴1 G 2", "1 G ⍴2"],
    ["A←1", D + "R←F X;A", "A←X", "R←A×2", D, D + "R←G X;A", "A←X+1", "R←F A", D, "G 1", "A", "F 5", "A", "G G 1"],
    ["A←⍳5", D + "R←F X", "R←X[A]", D, D + "R←G X;A", "A←2 2⍴⍳4", "R←F A", D, "F 1 2 3 4 5", "G 1 2 3 4 5", "A"],
]


def test_calls():
    n = 0
    for lines in CALLS:
        run(lines)
        n += len(lines)
    print(f"functions: {len(CALLS)} calling sessions ({n} lines) match the model")



def gen_expr(rng, names, funcs, d):
    """A random expression; funcs are (name, nargs, hasres) of functions already defined."""
    lits = ["1", "2", "3", "0", "¯1", "1 2 3", "4 5", "2 3", "1.5", "'ab'", "⍬", "10", "0 1 1"]
    if d <= 0 or rng.random() < .25:
        pool = [f for f in funcs if f[1] == 0 and f[2]]
        r = rng.random()
        if r < .45 and names:
            return rng.choice(names)
        if r < .55 and pool:
            return rng.choice(pool)[0]
        return rng.choice(lits)
    r = rng.random()
    monadic = [f for f in funcs if f[1] >= 1 and f[2]]
    dyadic = [f for f in funcs if f[1] == 2 and f[2]]
    if r < .2 and monadic:
        return rng.choice(monadic)[0] + " " + gen_expr(rng, names, funcs, d - 1)
    if r < .3 and dyadic:
        return "(" + gen_expr(rng, names, funcs, d - 1) + ")" + rng.choice(dyadic)[0] + " " + gen_expr(rng, names, funcs, d - 1)
    if r < .5:
        return rng.choice("+-×⍳⍴,") + gen_expr(rng, names, funcs, d - 1)
    if r < .8:
        return "(" + gen_expr(rng, names, funcs, d - 1) + ")" + rng.choice("+-×⍴,=<") + gen_expr(rng, names, funcs, d - 1)
    if r < .9 and names:
        return rng.choice(names) + "[" + gen_expr(rng, names, funcs, d - 1) + "]"
    return "(" + gen_expr(rng, names, funcs, d - 1) + ")"


def gen_function_session(rng):
    """Definitions of one to three functions (each may call the earlier ones), then calls."""
    lines, funcs = [], []
    glob = ["A", "B"]
    lines += ["A←" + rng.choice(["3", "1 2 3", "⍳4", "2 2⍴⍳4", "'xy'"]), "B←" + rng.choice(["5", "2 3", "0"])]
    for k, fname in enumerate(rng.sample(["F", "G", "H", "K"], rng.choice([1, 2, 3]))):
        nargs = rng.choice([0, 1, 1, 2])
        hasres = rng.random() < .8
        left, right = ("X", "Y") if nargs == 2 else (None, "X")
        locs = rng.sample(["T", "U", "A"], rng.choice([0, 0, 1, 2]))
        names = ["X", "Y", "T", "U", "A", "B"] if nargs == 2 else ["X", "T", "U", "A", "B"]
        head = (("R←" if hasres else "") + " ".join(([left] if left else []) + [fname] + ([right] if nargs else []))
                + "".join(";" + n for n in locs))
        lines.append(D + head)
        for _ in range(rng.choice([1, 2, 2, 3, 4])):
            r = rng.random()
            e = gen_expr(rng, names, funcs, rng.choice([1, 2, 3]))
            if r < .45:
                lines.append(rng.choice(["T", "U", "A", "B"]) + "←" + e)
            elif r < .6 and hasres:
                lines.append("R←" + e)
            else:
                lines.append(e)
        if hasres and rng.random() < .85:
            lines.append("R←" + gen_expr(rng, names, funcs, 2))
        lines.append(D)
        funcs.append((fname, nargs, hasres))
    for _ in range(rng.choice([2, 3, 4])):
        f = rng.choice(funcs)
        arg = gen_expr(rng, glob, [], 1)
        call = f[0] if f[1] == 0 else (f[0] + " " + arg if f[1] == 1 else "(" + gen_expr(rng, glob, [], 1) + ")" + f[0] + " " + arg)
        lines.append(rng.choice(["", "", "1+", "A←", "(", ""]) + call + (")" if False else ""))
        lines.append(rng.choice(["A", "B", "T", "X"]))
    return lines


def test_fuzz_functions(n=300, seed=5):
    rng = random.Random(seed)
    s = Session()
    kinds = {}
    for _ in range(n):
        lines = gen_function_session(rng)
        s.reset()
        for line in lines:
            if len(apl64.encode_line(line)) > 255:
                continue
            k = check(s, line)
            kinds[k] = kinds.get(k, 0) + 1
    print(f"functions: {n} random sessions match the model {dict(sorted(kinds.items()))}")


def test_call_heap_full():
    """A call that cannot save its context gives WS FULL and leaves nothing behind."""
    s = Session()
    s.reset()
    for line in [D + "R←F X;T", "T←X", "R←T+1", D]:
        check(s, line)
    k = 0
    n = 1400
    while n >= 1:
        got = s.run6502(f"V{k}←⍳{n}")
        if got[0] == "err":
            s.model.name_index(f"V{k}")       # the tokeniser made the name even though the line failed
            n //= 2
        else:
            s.run_model(f"V{k}←⍳{n}")
            k += 1
    got = s.run6502("F 1")
    assert got == ("err", "WS FULL"), got
    m, L = s.m, s.L
    assert m.memory[L["cdepth"]] == 0
    check(s, "V0←1")                  # frees a big block again
    check(s, "V1←1")
    check(s, "F 1")
    check(s, "F F 1")


def test_fn_check():
    """The loader's check of a function block (fn_check) agrees with wsfile.function_valid on real
    functions and on thousands of damaged ones."""
    sys.path.insert(0, "tools")
    import wsfile
    s = Session()
    s.reset()
    for line in [D + "R←F X;T", "T←X+1 2 3", "R←T×'ab'[1]", "(1 2 3)[2]", "2 3⍴⍳6", "1.5 ¯2 40000 1e10", D,
                 D + "R←A G B", "R←A+B", D, D + "H", D]:
        check(s, line)
    m, L = s.m, s.L
    nsym = len(s.model.names)

    def block_of(sym):
        h = m.memory[L["VARS"] + 4 * sym + 1]
        a = m.memory[L["HTL"] + h] | m.memory[L["HTH"] + h] << 8
        return a, m.memory[a + 1] | m.memory[a + 2] << 8

    def run_check():
        for sym in range(nsym):
            m.memory[L["VARS"] + 4 * sym] = m.memory[L["VARS"] + 4 * sym]     # (cells unchanged)
        call(m, L["fn_check"], max_steps=2_000_000)
        return not (m.p & 1)

    def one(sym, data, syms=nsym):
        a, n = block_of(sym)
        assert len(data) == n
        m.memory[a + 5:a + 5 + n] = list(data)
        m.memory[L["symcnt"]] = syms & 255
        m.memory[L["symcnt"] + 1] = syms >> 8
        return run_check()

    funcs = [i for i in sorted(s.model.funcs)]
    cells = {i: bytes(m.memory[L["VARS"] + 4 * i:L["VARS"] + 4 * i + 4]) for i in funcs}
    rng = random.Random(3)
    tested = valid = 0
    for sym in funcs:
        for other in funcs:                     # only this function is looked at
            m.memory[L["VARS"] + 4 * other] = cells[other][0] if other == sym else 0x80
        a, n = block_of(sym)
        orig = bytes(m.memory[a + 5:a + 5 + n])
        assert wsfile.function_valid(orig, nsym) and one(sym, orig)
        for k in range(1500):
            d = bytearray(orig)
            for _ in range(rng.choice([1, 1, 2, 3])):
                d[rng.randrange(len(d))] = rng.choice([0, 1, 2, 3, 5, 6, 11, 0x80, 0xFF, rng.randrange(256)])
            syms = rng.choice([nsym, nsym, sym + 1, 200, 256])
            want = wsfile.function_valid(bytes(d), syms)
            got = one(sym, bytes(d), syms)
            assert got == want, (sym, bytes(d).hex(), syms, got, want)
            tested += 1
            valid += want
        one(sym, orig)
    print(f"functions: fn_check agrees with the checker on {tested} damaged blocks ({valid} of them still valid)")

def test_line_limit():
    """255 lines fit, the 256th is LIMIT ERROR (the model and the 6502 agree)."""
    s = Session()
    s.reset()
    check(s, D + "F")
    for i in range(255):
        assert check(s, str(i % 10)) == "ok"
    assert check(s, "1") == "LIMIT ERROR"
    check(s, D)


def test_heap_full():
    """The 6502 refuses a line that does not fit in the heap (WS FULL) and stays usable."""
    s = Session()
    s.reset()
    check(s, D + "F")
    line = "'" + "a" * 240 + "'"
    err = None
    for i in range(200):
        got = s.run6502(line)
        if got[0] == "err":
            err = got[1]
            break
        s.run_model(line)
    assert err == "WS FULL", err
    assert s.run6502(D) == ("ok", b"")
    assert s.run6502("1")[0] == "ok"
    assert s.run6502(D + "F")[0] == "ok"


if __name__ == "__main__":
    test_definitions()
    test_calls()
    test_fuzz_functions()
    test_fn_check()
    test_line_limit()
    test_heap_full()
    test_call_heap_full()
