import os
import random
import sys

sys.path.insert(0, os.getcwd())
import apl64
from harness import call, load

FA, FB = 0x10, 0x13


def to_bytes(p):
    return [p >> 16, (p >> 8) & 0xFF, p & 0xFF]


def from_bytes(bs):
    return (bs[0] << 16) | (bs[1] << 8) | bs[2]


def rand_f(rng, exp_lo=1, exp_hi=255):
    if rng.random() < 0.05:
        return 0
    e = rng.randint(exp_lo, exp_hi)
    frac = rng.choice([0, 0x7FFF, rng.getrandbits(15), rng.getrandbits(15)])
    return (e << 16) | (rng.getrandbits(1) << 15) | frac


def run(mpu, addr, a, b):
    mpu.memory[FA:FA + 3] = to_bytes(a)
    mpu.memory[FB:FB + 3] = to_bytes(b)
    call(mpu, addr)
    over = bool(mpu.p & 1)
    return over, from_bytes(mpu.memory[FA:FA + 3])


def expect(fn, a, b):
    try:
        return False, fn(a, b)
    except apl64.AplError:
        return True, None


def check(name, fn, mpu, addr, a, b):
    want = expect(fn, a, b)
    got = run(mpu, addr, a, b)
    if want[0]:
        ok = got[0]
    else:
        ok = (not got[0]) and got[1] == want[1]
    assert ok, f"{name}({a:06x}, {b:06x}): model {want}, 6502 {got}"


def cases(rng, n):
    for _ in range(n):
        a = rand_f(rng)
        mode = rng.random()
        if mode < 0.3:
            b = rand_f(rng)
        elif mode < 0.6 and a:                  # near a: small exponent gap
            e = min(255, max(1, (a >> 16) + rng.randint(-3, 3)))
            b = (e << 16) | (rng.getrandbits(1) << 15) | rng.getrandbits(15)
        elif mode < 0.75 and a:                 # near-cancellation
            b = apl64.f_neg(a) ^ rng.choice([0, 1, 2, 0x100])
        elif mode < 0.9:                        # extremes: over/underflow
            a = rand_f(rng, 250, 255) if rng.random() < .5 else rand_f(rng, 1, 3)
            b = rand_f(rng, 250, 255) if rng.random() < .5 else rand_f(rng, 1, 3)
        else:                                   # exponent gaps 8..26: lost bits
            a = rand_f(rng, 30, 220)
            e = (a >> 16) - rng.randint(8, 26)
            frac = rng.choice([0, 1, 0x7FFF, rng.getrandbits(15)])
            b = (e << 16) | (rng.getrandbits(1) << 15) | frac
            if rng.random() < .5:
                a = (a & ~0x7FFF) | rng.choice([0, 0x7FFF, 1])
        yield a, b


def mul_div_cases(rng, n):
    def frac():
        return rng.choice([0, 0x7FFF, 1, 1 << rng.randint(0, 14),
                           0x7FFF - (1 << rng.randint(0, 14)),
                           rng.getrandbits(15), rng.getrandbits(15)])

    def make(e):
        e = min(255, max(1, e))
        return (e << 16) | (rng.getrandbits(1) << 15) | frac()

    for _ in range(n):
        mode = rng.random()
        if mode < 0.03:
            yield rand_f(rng), 0
        elif mode < 0.06:
            yield 0, rand_f(rng)
        elif mode < 0.4:
            yield make(rng.randint(1, 255)), make(rng.randint(1, 255))
        elif mode < 0.7:                        # result exponent near the limits
            t = rng.choice([-2, -1, 0, 1, 2, 3, 253, 254, 255, 256, 257, 258])
            ea = rng.randint(1, 255)
            yield make(ea), make(t + 128 - ea + rng.randint(-1, 1))
        elif mode < 0.85:
            t = rng.choice([-2, -1, 0, 1, 2, 3, 253, 254, 255, 256, 257, 258])
            ea = rng.randint(1, 255)
            yield make(ea), make(ea - t + 128 + rng.randint(-1, 1))
        else:                                   # exact ties: odd 17-bit u*v
            while True:
                lu = rng.randint(1, 16)
                lv = rng.choice([17 - lu, 18 - lu])
                if not 1 <= lv <= 16:
                    continue
                u = (rng.getrandbits(lu - 1) << 1 | 1) | (1 << (lu - 1)) if lu > 1 else 1
                v = (rng.getrandbits(lv - 1) << 1 | 1) | (1 << (lv - 1)) if lv > 1 else 1
                if (u * v).bit_length() == 17:
                    break
            ma, mb = u << (16 - lu), v << (16 - lv)
            e = rng.randint(100, 150)
            yield ((e << 16) | (rng.getrandbits(1) << 15) | (ma & 0x7FFF),
                   (e << 16) | (rng.getrandbits(1) << 15) | (mb & 0x7FFF))


def test_f_mul_div():
    mpu, labels = load("float24")
    rng = random.Random(64)
    n = 0
    for a, b in mul_div_cases(rng, 60000):
        check("f_mul", apl64.f_mul, mpu, labels["f_mul"], a, b)
        check("f_div", apl64.f_div, mpu, labels["f_div"], a, b)
        n += 1
    print(f"float24 mul/div: {n} pairs match the model")


def test_f_add_sub():
    mpu, labels = load("float24")
    rng = random.Random(24)
    n = 0
    for a, b in cases(rng, 60000):
        check("f_add", apl64.f_add, mpu, labels["f_add"], a, b)
        check("f_sub", apl64.f_sub, mpu, labels["f_sub"], a, b)
        n += 1
    print(f"float24 add/sub: {n} pairs match the model")


if __name__ == "__main__":
    test_f_add_sub()
    test_f_mul_div()
