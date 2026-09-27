import os
import random
import sys

sys.path.insert(0, os.getcwd())
from harness import call, load

WIDTH = (1, 1, 2, 3)
E_LIMIT, E_WSFULL = 3, 8


SPILLED = 0xFF                      # HTH of an array that is in the REU


class Heap:
    def __init__(self, reu_kb=8192, size=None):
        """reu_kb: the REU (0: none, so nothing can spill); size: make the heap only this many bytes."""
        self.m, self.L = load("eval", reu_kb=reu_kb)
        call(self.m, self.L["heap_init"])
        self.HEAP_BASE, self.HEAP_LIMIT = self.L["HEAP_BASE"], self.L["HEAP_LIMIT"]
        if size:
            self.HEAP_LIMIT = self.HEAP_BASE + size
            self.zp("hlim", self.HEAP_LIMIT, 2)
        self.VARS = self.L["VARS"]
        self.shadow = {}                    # handle -> bytes of header + data
        self.vars = {}                      # slot -> handle
        self.stack = []                     # handles on the value stack

    def zp(self, name, v, n=1):
        a = self.L[name]
        for i in range(n):
            self.m.memory[a + i] = (v >> 8 * i) & 0xFF

    def rd(self, name, n=1):
        a = self.L[name]
        return sum(self.m.memory[a + i] << 8 * i for i in range(n))

    def new(self, t, rank, count, d0, d1=0):
        self.zp("nt", t)
        self.zp("nrk", rank)
        self.zp("nn", count, 2)
        self.zp("nd0", d0, 2)
        self.zp("nd1", d1, 2)
        call(self.m, self.L["newarr"], max_steps=5_000_000)
        if self.m.p & 1:
            return None, self.m.a
        h = self.m.memory[self.L["hnew"]]
        dp = self.rd("dp", 2)
        n = count * WIDTH[t]
        data = [random.randrange(256) for _ in range(n)]
        self.m.memory[dp:dp + n] = data
        addr = self.m.memory[self.L["HTL"] + h] | self.m.memory[self.L["HTH"] + h] << 8
        hdr = 3 + 2 * rank
        assert dp == addr + hdr, (hex(dp), hex(addr))
        blob = bytes(self.m.memory[addr:addr + hdr]) + bytes(data)
        assert self.m.memory[self.L["cv"]] == t | rank << 2
        assert self.m.memory[self.L["cv"] + 1] == h
        return h, blob

    def gc(self):
        call(self.m, self.L["gc"], max_steps=5_000_000)

    def set_var(self, slot, handle, tag=None):
        a = self.VARS + 4 * slot
        if handle is None:
            self.m.memory[a:a + 4] = [0x80, 0, 0, 0]
            self.vars.pop(slot, None)
        else:
            self.m.memory[a:a + 4] = [tag, handle, 0, 0]
            self.vars[slot] = handle

    def push(self, handle, tag):
        vsp = self.rd("vsp", 2)
        self.m.memory[vsp:vsp + 4] = [tag, handle, 0, 0]
        self.zp("vsp", vsp + 4, 2)
        self.stack.append(handle)

    def pop(self):
        self.zp("vsp", self.rd("vsp", 2) - 4, 2)
        self.stack.pop()

    def roots(self):
        return set(self.vars.values()) | set(self.stack)

    def spilled(self):
        return {h for h in range(256) if self.m.memory[self.L["HTH"] + h] == SPILLED}

    def slot(self, h):
        return 0x10000 + h * 0x4000

    def fault(self, h, tag):
        """Push the cell of handle h the way the evaluator pushes a variable's value (pushcv brings a spilled array back)."""
        m, L = self.m, self.L
        m.memory[L["cv"]:L["cv"] + 4] = [tag, h, 0, 0]
        call(m, L["pushcv"], max_steps=5_000_000)
        assert not m.p & 1, m.a
        self.stack.append(h)
        assert m.memory[L["HTH"] + h] not in (0, SPILLED)

    def check(self, after_gc=False):
        m, L = self.m, self.L
        top = self.rd("htop", 2)
        assert self.HEAP_BASE <= top <= self.HEAP_LIMIT
        # walk the heap: blocks must tile it exactly and agree with the handle table
        p, live = self.HEAP_BASE, set()
        while p < top:
            h = m.memory[p]
            tag = m.memory[p + 1]
            n = m.memory[p + 2] | m.memory[p + 3] << 8
            size = 4 + 2 * (tag >> 2 & 3) + n * WIDTH[tag & 3]
            assert m.memory[L["HTL"] + h] | m.memory[L["HTH"] + h] << 8 == p + 1, (h, hex(p))
            assert h not in live
            live.add(h)
            p += size
        assert p == top, "blocks do not tile the heap"
        spilled = self.spilled()
        for h in range(256):
            if m.memory[L["HTH"] + h] and h not in spilled:
                assert h in live, f"handle {h} in table but not in heap"
        assert not spilled & live, "an array is both in the heap and in the REU"
        assert all(h in live for h in self.stack), "an array on the stack is not in the heap"
        for h in spilled:
            assert h not in self.stack, f"handle {h} is in the REU but on the stack"
            assert h in self.shadow and self.slot(h) + len(self.shadow[h]) <= self.slot(h) + 0x4000
            assert bytes(m.reu.mem[self.slot(h):self.slot(h) + len(self.shadow[h])]) == self.shadow[h][0:], f"handle {h} corrupted in the REU"
        for h in self.roots():
            assert h in live or h in spilled, f"rooted handle {h} lost"
            if h in spilled:
                continue
            addr = m.memory[L["HTL"] + h] | m.memory[L["HTH"] + h] << 8
            want = self.shadow[h]
            assert bytes(m.memory[addr:addr + len(want)]) == want, f"handle {h} corrupted"
        if after_gc:
            pinned = {m.memory[L["hpin"]]} if m.memory[L["hpinf"]] else set()
            assert live | spilled == self.roots() | pinned, (sorted(live), sorted(spilled), sorted(self.roots()))
        return live, top


def run_random(seed, steps):
    random.seed(seed)
    h = Heap()
    stats = {"alloc": 0, "gc_freed": 0, "wsfull": 0}
    for _ in range(steps):
        op = random.random()
        if op < 0.55:
            t = random.randrange(4)
            if random.random() < .5:
                n = random.choice([0, 1, 2, 5, random.randrange(400), random.randrange(2500)])
                args = (t, 1, n, n)
            else:
                r, c = random.randrange(20), random.randrange(20)
                args = (t, 2, r * c, r, c)
            before = h.check()[1]
            handle, blob = h.new(*args)
            if handle is None:
                assert blob == E_WSFULL, blob
                stats["wsfull"] += 1
                continue
            stats["alloc"] += 1
            h.shadow[handle] = blob
            where = random.random()
            if where < .6:
                slot = random.randrange(48)
                h.set_var(slot, handle, args[0] | args[1] << 2)
            elif where < .8 and len(h.stack) < 20:
                h.push(handle, args[0] | args[1] << 2)
            # else: left unrooted: it may vanish at the next collection
        elif op < 0.7:
            h.set_var(random.randrange(48), None)
        elif op < 0.78 and h.stack:
            h.pop()
        elif op < 0.9:
            h.gc()
            h.check(after_gc=True)
            continue
        else:
            slot = random.randrange(48)
            h.set_var(slot, None)
            h.set_var(slot + 100, None)
        h.check()
    h.gc()
    h.check(after_gc=True)
    return stats


def test_random():
    tot = {"alloc": 0, "wsfull": 0}
    for seed in range(6):
        s = run_random(seed, 500)
        tot["alloc"] += s["alloc"]
        tot["wsfull"] += s["wsfull"]
    print(f"heap random ops: {tot['alloc']} allocations, {tot['wsfull']} WS FULL, invariants held after every step")


def test_exhaustion():
    h = Heap(reu_kb=0)
    random.seed(1)
    n = 0
    while True:                                      # fill the heap with rooted 2000-byte arrays
        handle, blob = h.new(2, 1, 1000, 1000)
        if handle is None:
            assert blob == E_WSFULL
            break
        h.shadow[handle] = blob
        h.set_var(n % 200, handle, 2 | 1 << 2)
        n += 1
        if n > 195:
            break
    top = h.check()[1]
    assert n >= (h.HEAP_LIMIT - h.HEAP_BASE) // 2100      # (a 2,000-byte array costs a little more with its header)
    # drop everything: the next big allocation must succeed by collecting
    for slot in list(h.vars):
        h.set_var(slot, None)
    handle, blob = h.new(2, 1, 1000, 1000)
    assert handle is not None
    h.shadow[handle] = blob
    h.set_var(0, handle, 2 | 1 << 2)
    h.check()
    print(f"heap exhaustion: filled with {n} arrays, then reclaimed after dropping them")


def test_spill():
    """A small heap and an REU: allocations go on succeeding by moving arrays that only variables hold out to the REU."""
    h = Heap(size=9000)
    random.seed(5)
    tag = 2 | 1 << 2
    for i in range(30):                                         # 30 arrays of 1000 bytes in a 9000 byte heap
        handle, blob = h.new(2, 1, 500, 500)
        assert handle is not None, i
        h.shadow[handle] = blob
        h.set_var(i, handle, tag)
        h.check()
    spilled = h.spilled()
    assert len(spilled) >= 20, len(spilled)
    # every array can be brought back and still holds what it held
    for slot in range(30):
        handle = h.vars[slot]
        h.fault(handle, tag)
        h.check()
        h.pop()
    # something on the stack is never moved: fill up again, holding the first array on the stack
    handle = h.vars[0]
    h.fault(handle, tag)
    for i in range(30, 60):
        hh, blob = h.new(2, 1, 500, 500)
        assert hh is not None, i
        h.shadow[hh] = blob
        h.set_var(i, hh, tag)
        h.check()
        assert h.m.memory[h.L["HTH"] + handle] not in (0, SPILLED)
    print(f"heap spill: 60 arrays of 1000 bytes in a 9000 byte heap; {len(h.spilled())} in the REU; each comes back intact; one held on the stack stayed put")


def test_spill_limits():
    """No REU: WS FULL as before. Functions' blocks and arrays on the stack are not moved; a single array too big for the heap is WS FULL."""
    h = Heap(reu_kb=0, size=9000)
    for i in range(12):
        handle, blob = h.new(2, 1, 500, 500)
        if handle is None:
            assert blob == E_WSFULL and i >= 8, (i, blob)
            break
        h.shadow[handle] = blob
        h.set_var(i, handle, 2 | 1 << 2)
    else:
        raise AssertionError("no WS FULL without an REU")
    assert not h.spilled()
    h = Heap(size=9000)
    handle, err = h.new(2, 1, 4600, 4600)                        # 9,200 bytes: more than the whole heap
    assert handle is None and err == E_WSFULL
    keep = []
    for i in range(3):                                           # arrays on the stack: three of 2900 bytes nearly fill the heap
        hh, blob = h.new(2, 1, 1450, 1450)
        assert hh is not None
        h.shadow[hh] = blob
        h.push(hh, 2 | 1 << 2)
        keep.append(hh)
    hh, err = h.new(2, 1, 1450, 1450)                            # nothing may move: WS FULL
    assert hh is None and err == E_WSFULL and not h.spilled()
    h.check()
    print("heap spill limits: none without an REU, nothing on the stack moves, an array bigger than the heap is WS FULL")


def test_handles():
    h = Heap()
    for i in range(256):
        handle, blob = h.new(0, 1, 1, 1)
        assert handle is not None, i
        h.shadow[handle] = blob
        h.set_var(i, handle, 0 | 1 << 2)
    handle, err = h.new(0, 1, 1, 1)
    assert handle is None and err == E_LIMIT, err
    h.check()
    print("heap handles: all 256 used, the 257th is LIMIT ERROR")


def test_size_limit():
    h = Heap()
    h.zp("wsmax", 1000, 2)
    handle, err = h.new(2, 1, 501, 501)         # 1002 bytes > 1000
    assert handle is None and err == E_WSFULL
    handle, blob = h.new(2, 1, 500, 500)
    assert handle is not None
    handle, err = h.new(3, 1, 334, 334)         # 1002 bytes
    assert handle is None and err == E_WSFULL
    print("heap per-array limit: WS FULL exactly above wsmax bytes")


if __name__ == "__main__":
    test_random()
    test_spill()
    test_spill_limits()
    test_exhaustion()
    test_handles()
    test_size_limit()
