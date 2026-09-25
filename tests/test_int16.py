import os
import random
import sys

sys.path.insert(0, os.getcwd())
import apl64
from harness import call, load

IA, IB, FA = 0x30, 0x32, 0x10

EDGES = [0, 1, -1, 2, -2, 255, 256, -256, 32767, -32768, 32766, -32767, 16384, -16384]


def rv():
    return random.choice(EDGES + [random.randint(-32768, 32767)] * 6)


def w16(mpu, addr, v):
    mpu.memory[addr] = v & 0xFF
    mpu.memory[addr + 1] = (v >> 8) & 0xFF


def r16(mpu, addr):
    v = mpu.memory[addr] | mpu.memory[addr + 1] << 8
    return v - 65536 if v >= 32768 else v


def wrap(v):
    return ((v + 32768) & 0xFFFF) - 32768


def test_i_add_sub():
    mpu, L = load("eval")
    random.seed(16)
    n = 0
    for op, fn in (("i_add", lambda x, y: x + y), ("i_sub", lambda x, y: x - y)):
        for _ in range(20000):
            x, y = rv(), rv()
            w16(mpu, IA, x)
            w16(mpu, IB, y)
            call(mpu, L[op])
            true = fn(x, y)
            assert r16(mpu, IA) == wrap(true), (op, x, y)
            assert bool(mpu.p & 1) == (not -32768 <= true <= 32767), (op, x, y)
            n += 1
    print(f"int16 add/sub: {n} pairs match")


def test_i_mul():
    mpu, L = load("eval")
    random.seed(18)
    pairs = [(rv(), rv()) for _ in range(6000)]
    for _ in range(9000):                       # products near the int16 limits
        x = random.choice([-1, 1]) * random.randint(1, 32768)
        t = random.choice([32767, 32768, -32768, -32769])
        y = t // x + random.randint(-1, 1)
        if -32768 <= y <= 32767:
            pairs.append((x if x <= 32767 else -32768, y))
    ovf = 0
    for x, y in pairs:
        w16(mpu, IA, x)
        w16(mpu, IB, y)
        call(mpu, L["i_mul"])
        true = x * y
        assert r16(mpu, IA) == wrap(true), ("i_mul", x, y)
        assert bool(mpu.p & 1) == (not -32768 <= true <= 32767), ("i_mul", x, y)
        ovf += mpu.p & 1
    print(f"int16 multiply: {len(pairs)} pairs match ({ovf} overflow)")


def test_i_to_f():
    mpu, L = load("eval")
    for v in range(-32768, 32768):
        w16(mpu, IA, v)
        call(mpu, L["i_to_f"])
        got = (mpu.memory[FA] << 16) | (mpu.memory[FA + 1] << 8) | mpu.memory[FA + 2]
        assert got == apl64.f_from_int(v), v
    print("int16 -> float24: all 65536 values match")


if __name__ == "__main__":
    test_i_add_sub()
    test_i_mul()
    test_i_to_f()
