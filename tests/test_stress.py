"""Stress test for the heap discipline: every allocation moves every array.

The 6502 code may not keep an array's data address across an allocation, because the collector can
move blocks (DESIGN.md, Value cells and the heap). A tier of storage that spills arrays to extra RAM
would rely on the same rule, and a stale address would read the wrong array. Ordinarily a block only
moves when garbage happens to sit below it, so a violation could go unnoticed for a long time.

Here, each time the code enters `alloc`, this test reverses the order of all the blocks on the heap and
fixes up the handle table, so a pointer held across an allocation is left pointing at some other array.
The evaluator's own tests are then rerun and must still match the model.
"""
import os
import random
import sys

sys.path.insert(0, os.getcwd())
import apl64
import test_eval as T

WIDTH = T.WIDTH


def install(s):
    m, L = s.m, s.L
    base, HTL, HTH = L["HEAP_BASE"], L["HTL"], L["HTH"]
    htop = L["htop"]
    stats = s.stats = {"allocs": 0, "moved": 0}

    def reverse_blocks(mpu):
        mem = mpu.memory
        top = mem[htop] | mem[htop + 1] << 8
        blocks, p = [], base
        while p < top:                                  # [handle][type|rank, count, shape, data]
            tag = mem[p + 1]
            n = mem[p + 2] | mem[p + 3] << 8
            size = 1 + 3 + 2 * (tag >> 2 & 3) + n * WIDTH[tag & 3]
            blocks.append((mem[p], bytes(mem[p:p + size])))
            p += size
        assert p == top, "the heap blocks do not tile the heap"
        stats["allocs"] += 1
        if len(blocks) < 2:
            return
        stats["moved"] += len(blocks)
        q = base
        for h, data in reversed(blocks):
            mem[q:q + len(data)] = list(data)
            mem[HTL + h], mem[HTH + h] = (q + 1) & 0xFF, (q + 1) >> 8
            q += len(data)

    m.hooks[L["alloc"]] = reverse_blocks


class StressSession(T.Session):
    def __init__(self):
        super().__init__()
        install(self)

    def reset(self):
        super().reset()


def run_corpus(lines, s):
    kinds = {}
    for line in lines:
        k = T.check(s, line)
        kinds[k] = kinds.get(k, 0) + 1
    return kinds


def test_fixed():
    s = StressSession()
    kinds = run_corpus(T.FIXED, s)
    print(f"stress: {len(T.FIXED)} fixed evaluator cases match the model with every block moved on each of "
          f"{s.stats['allocs']} allocations ({s.stats['moved']} block moves)")


def test_fuzz():
    rng = random.Random(77)
    s = StressSession()
    n_lines = 0
    for n in range(2500):
        if n % 6 == 0:
            s.reset()
        defined = [nm for i, nm in enumerate(s.model.names) if i in s.model.vars]
        line = T.gen_line(rng, defined)
        if len(apl64.encode_line(line)) > 255:
            continue
        T.check(s, line)
        n_lines += 1
    print(f"stress: {n_lines} random lines match the model ({s.stats['allocs']} allocations, {s.stats['moved']} block moves)")


def test_functions():
    """Function blocks and saved contexts move too: definitions and calls with every block moved."""
    import test_funcs as F
    s = StressSession()
    n = 0
    for lines in F.DEFS + F.CALLS + F.FLOW:
        s.reset()
        for line in lines:
            T.check(s, line)
            n += 1
    print(f"stress: {n} function-session lines match the model ({s.stats['allocs']} allocations, "
          f"{s.stats['moved']} block moves)")


if __name__ == "__main__":
    test_fixed()
    test_functions()
    test_fuzz()
