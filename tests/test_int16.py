import os
import random
import sys

sys.path.insert(0, os.getcwd())
import apl64
from harness import call, load

IA, IB, FA = 0x30, 0x32, 0x10
PA, PB, PR, CNT, STRA, STRB = 0x34, 0x36, 0x38, 0x3A, 0x3C, 0x3D
BUF_A, BUF_B, BUF_R = 0x2000, 0x2400, 0x2800

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
    mpu, L = load("int16")
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


def test_i_to_f():
    mpu, L = load("int16")
    for v in range(-32768, 32768):
        w16(mpu, IA, v)
        call(mpu, L["i_to_f"])
        got = (mpu.memory[FA] << 16) | (mpu.memory[FA + 1] << 8) | mpu.memory[FA + 2]
        assert got == apl64.f_from_int(v), v
    print("int16 -> float24: all 65536 values match")


def run_vec(mpu, L, name, xs, ys, scalar_a, scalar_b):
    n = max(len(xs), len(ys))
    for i, v in enumerate(xs):
        w16(mpu, BUF_A + 2 * i, v)
    for i, v in enumerate(ys):
        w16(mpu, BUF_B + 2 * i, v)
    for addr, val in ((PA, BUF_A), (PB, BUF_B), (PR, BUF_R), (CNT, n)):
        w16(mpu, addr, val)
    mpu.memory[STRA] = 0 if scalar_a else 2
    mpu.memory[STRB] = 0 if scalar_b else 2
    call(mpu, L[name])
    if mpu.p & 1:
        return apl64.FLOAT, [
            (mpu.memory[BUF_R + 3 * i] << 16) | (mpu.memory[BUF_R + 3 * i + 1] << 8)
            | mpu.memory[BUF_R + 3 * i + 2] for i in range(n)]
    return apl64.INT, [r16(mpu, BUF_R + 2 * i) for i in range(n)]


def test_vec():
    mpu, L = load("int16")
    random.seed(17)
    counts = {"int": 0, "float": 0}
    for name, sym in (("vec_add", "+"), ("vec_sub", "-")):
        model = apl64._arith(sym)
        for _ in range(3000):
            n = random.choice([0, 1, 1, 2, 3, 5, 8, 20])
            mode = random.choice(["vec", "vec", "sa", "sb"])
            if mode != "vec" and n == 0:
                n = 1
            small = random.random() < .6
            gen = (lambda: random.randint(-100, 100)) if small else rv
            xs = [gen() for _ in range(1 if mode == "sa" else n)]
            ys = [gen() for _ in range(1 if mode == "sb" else n)]
            ex = xs * n if mode == "sa" else xs
            ey = ys * n if mode == "sb" else ys
            want = model(apl64.INT, ex, apl64.INT, ey)
            got = run_vec(mpu, L, name, xs, ys, mode == "sa", mode == "sb")
            assert got == want, (name, mode, xs, ys, got, want)
            counts["int" if want[0] == apl64.INT else "float"] += 1
    print(f"int16 vector kernel: {counts} results match the model")


if __name__ == "__main__":
    test_i_add_sub()
    test_i_to_f()
    test_vec()
