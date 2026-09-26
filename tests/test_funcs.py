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
    test_line_limit()
    test_heap_full()
