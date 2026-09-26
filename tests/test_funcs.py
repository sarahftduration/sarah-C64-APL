"""User-defined functions on the 6502 (py65) against the model: the del editor and, from the
call machinery on, calls. Sessions of lines are run through do_line one after the other;
after each line the echo (or error) and every variable and function block must agree.
"""
import os
import random
import sys

sys.path.insert(0, os.getcwd())
import apl64
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
        body_start = len(lines) - sum(1 for _ in range(0))       # (index of the first body line is found below)
        lines.append(D)
        head_at = max(i for i, ln in enumerate(lines) if ln.startswith(D + ("R←" if hasres else "")) and ln != D)
        body = lines[head_at + 1:-1]
        used = set(names) | {fname}
        labs = [n for n in ("LA", "LB", "LC") if n not in used]
        for i in range(len(body)):                          # forward branches and labels only: no loops
            r = rng.random()
            if r < .25 and i + 2 <= len(body):
                target = rng.choice([str(rng.randrange(i + 2, len(body) + 2)), "0"] +
                                    [lb for lb in labs if False])
                cond = gen_expr(rng, names, funcs, 1)
                body[i] = rng.choice(["→" + target, "→" + target + "×⍳" + cond, "→⍳0", "→" + cond, "→" + target + " " + target])
            elif r < .4 and labs and i + 1 < len(body):
                lb = labs.pop(0)
                body[i] = lb + ":" + body[i]
                if rng.random() < .7 and i > 0 and not body[i - 1].startswith("→"):
                    body[i - 1] = "→" + lb + "×⍳" + gen_expr(rng, names, funcs, 1)
        lines[head_at + 1:-1] = body
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


A = "→"
FLOW = [
    [D + "F", "1", A + "0", "2", D, "F"],
    [D + "F", "1", A + "4", "2", D, "F"],
    [D + "F", A + "3", "1", "2", "3", D, "F"],
    [D + "F", A + "⍳0", "1", D, "F"],
    [D + "F", A + "2 1", "1", "2", D, "F"],
    [D + "F", A + "2.0", "1", "2", D, "F", D + "G", A + "2.5", D, "G", D + "H", A + "'a'", D, "H", D + "K", A + "''", D, "K"],
    [D + "F", A + "¯1", "1", D, "F", D + "G", A + "1 ⋄ 5", "7", D, "G"][:5] + [D + "G", A + "3 ⋄ 5", "7", "8", D, "G"],
    [D + "F", "1 ⋄ " + A + "3 ⋄ 2", "3", D, "F"],
    [D + "F", A + "⍳0 ⋄ 7", D, "F"],
    [D + "F", A + "1+", D, D + "G", "(" + A + "1)", D, D + "H", "1+" + A + "1", D, "F", "G", "H"],
    [D + "F", A + "Q", D, D + "G", A + "1" + A + "2", D, "F", "G"],
    [D + "F X", A + "X÷0", D, "F 1"],
    [D + "F", A + "F", D, D + "G", A + "G G", D, D + "H", A + "1 2", D, "H"][:3] + [D + "H", A + "2 3", "1", "2", D, "H"],
    [A + "1", "1" + A + "1", A, "A←" + A + "1", "(" + A + "1)", "⍳" + A + "1"],
    [D + "F", "L:1", "M: 2", "N :3", D, "F", "L", "M"],
    [D + "F", "L:L", "M:M+L", D, "F"],
    [D + "F", "L:", "M:", A + "M+2", "Z", D, "F"],
    [D + "F", "L:1", "L:2", D + "F", "F:1", D + "F X", "X:1", D + "R←F X;L", "L:1", D + "F", "A1:5", "B_2:A1", D, "F"],
    [D + "F", "L:1 2", "M:(", D, "F"],
    [D + "F", "L:'x:y'", "'a:b'", "⍝ z: comment", "K:⍝ c", D, "F"],
    [D + "R←F X", "R←L", "L:R←R+1", D, D + "G", "F 1", D, "G", "L"],
    [D + "R←F", "R←M", "M:R←R,M", D, D + "R←G", "R←F", D, "F", "G", "M"],
    [D + "R←SUMTO N;I", "R←0", "I←1", "TOP:R←R+I", "I←I+1", A + "TOP×⍳I≤N", D, "SUMTO 10", "SUMTO 0", "SUMTO 100", "SUMTO 1000"],
    [D + "R←FACT N", "R←1", A + "0×⍳N<2", "R←N×FACT N-1", D, "FACT 1", "FACT 5", "FACT 7", "FACT 8", "FACT ⍳5"],
    [D + "R←FIB N", "R←N", A + "0×⍳N<2", "R←(FIB N-1)+FIB N-2", D, "FIB 0", "FIB 1", "FIB 10", "FIB 12"],
    [D + "R←F X", A + "3", "R←1", "R←2", D, "F 0", "1+F 1"],
    [D + "R←F X;A", "A←X", "L1:A←A+1", "→L3×⍳A>5", "→L1", "L3:R←A", D, "F 1", "F 3", "F 9"],
    [D + "R←A DIV B", "R←A÷B", D, "6 DIV 3", "1 DIV 0"],
    [D + "F", "L1:'a'", "L2:'b'", A + "L2+2", "'skip'", "'c'", D, "F"],
    [D + "R←F X", "R←X", A + "3×⍳X>0", "R←-X", "R←R,R", D, "F 1", "F ¯1", "F 0"],
    [D + "F X;Y", "Y←0", "N:Y←Y+1", "Y", A + "N×⍳Y<X", D, "F 3", "F 1", "F 0"],
    [D + "F", "A←1", A + "4", "A←2", "A", D, "F", "A"],
    [D + "F", A + "1+1", "'skipped'", "'here'", D, "F"],
    [D + "G", "1", "'x'", D, "G"],
    # a function calling another that branches out early
    [D + "R←G X", "R←1", A + "0", "R←2", D, D + "R←F X", "R←G X", "R←R+G X", D, "F 1", "F F 1"],
    # branch out of a called function does not leave the caller
    [D + "G", "1", A + "0", "2", D, D + "F", "G", "'after'", D, "F"],
    # many lines and a label on the last
    [D + "R←F", "R←0"] + ["R←R+1"] * 40 + ["END:R←R+END", D, "F"],
    [D + "F X", "X", D, D + "G", "→F 3", "1", D, "G"],
    [D + "F" + "".join(f";L{i}" for i in range(60))] + [f"K{i}:{i}" for i in range(42)] + [D, "F"],       # the 99-symbol limit
    [D + "F" + "".join(f";L{i}" for i in range(59))] + [f"K{i}:{i}" for i in range(42)] + [D, "F"],
    # a name that is a label in one function and a variable in another
    ["L←5", D + "F", "L:L", D, "F", "L", D + "R←G", "R←L", D, "G"],
]


def test_flow():
    n = 0
    for lines in FLOW:
        run(lines)
        n += len(lines)
    print(f"functions: {len(FLOW)} control-flow sessions ({n} lines: branches, labels, loops, recursion) match the model")



def test_interrupt():
    """RUN/STOP (the KERNAL's flag at $91) stops a running function between two lines, gives
    INTERRUPT, gives the localised names back and leaves the machine usable."""
    s = Session()
    s.reset()
    for line in ["A←7", D + "R←SPIN N;A", "A←N", "TOP:A←A+1", "→TOP", D, D + "R←OUTER X;A", "A←1", "R←SPIN X", D, D + "LOOP", "→1", D,
                 D + "F", "1", D]:
        check(s, line)
    m, L = s.m, s.L
    for line, after_lines in [("SPIN 3", 5), ("OUTER 2", 40), ("LOOP", 1), ("LOOP", 300), ("1+SPIN 1", 7)]:
        count = [0]

        def poke(mm, count=count, n=after_lines):
            count[0] += 1
            if count[0] == n:
                mm.memory[0x91] = 0x7F

        m.hooks = {L["fn_nextline"]: poke, L["fn_intr"]: lambda mm: mm.memory.__setitem__(0x91, 0)}
        got = s.run6502(line)
        m.hooks = {}
        assert got == ("err", "INTERRUPT"), (line, got)
        assert m.memory[L["cdepth"]] == 0
        assert s.vars6502() == s.vars_model(), line              # A is 7 again
    t = L["errtab"] + 2 * 9                                     # the message for error 10
    a = m.memory[t] | m.memory[t + 1] << 8
    assert bytes(m.memory[a:a + 9]) == b"INTERRUPT" and m.memory[a + 9] == 0
    assert s.run6502("1+1")[0] == "ok"
    check(s, "F")
    check(s, "A")
    # a key that is not held does nothing
    m.memory[0x91] = 0xFF
    check(s, "F")
    m.memory[0x91] = 0
    print("functions: RUN/STOP interrupts loops and recursion between lines, restoring the names")

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
    assert s.run6502(D + "F")[0] in ("ok", "err")       # a header needs a few bytes: it may not fit either


if __name__ == "__main__":
    test_definitions()
    test_calls()
    test_flow()
    test_fuzz_functions()
    test_interrupt()
    test_line_limit()
    test_heap_full()
    test_call_heap_full()
