import os
import random
import re
import sys

sys.path.insert(0, os.getcwd())
import apl64
from harness import call, load

ERR = {1: 'SYNTAX ERROR', 2: 'DOMAIN ERROR', 3: 'LIMIT ERROR'}


class Session:
    """One 6502 tokenizer and one model interpreter, kept in step."""

    def __init__(self):
        self.mpu, self.L = load("eval")
        self.reset()

    def reset(self):
        call(self.mpu, self.L["tok_init"])
        self.model = apl64.Interp()

    def run6502(self, line):
        data = apl64.encode_line(line)
        assert len(data) <= 255
        m = self.mpu
        INBUF = self.L["INBUF"]
        m.memory[INBUF:INBUF + len(data) + 1] = list(data) + [0]
        call(m, self.L["tokenize"], max_steps=2_000_000)
        if m.p & 1:
            return ('err', ERR[m.a])
        end = m.memory[self.L["op"]] | m.memory[self.L["op"] + 1] << 8
        return ('ok', bytes(m.memory[self.L["OUTBUF"]:end]))

    def names6502(self):
        m = self.mpu
        n = m.memory[self.L["symcnt"]] | m.memory[self.L["symcnt"] + 1] << 8
        names, p = [], self.L["SYMTAB"]
        for _ in range(n):
            ln = m.memory[p]
            raw = bytes(m.memory[p + 1:p + 1 + ln])
            names.append(raw)
            p += ln + 1
        return names

    def run_model(self, line):
        try:
            return ('ok', self.model.tokenize(line))
        except apl64.AplError as e:
            return ('err', e.kind)


ULP = {"exact": 0, "one_ulp": 0}


def ulp_diff(p, q):
    """0 if equal, 1 if adjacent floats, None otherwise."""
    if p == q:
        return 0
    if (p >> 16) == 0 or (q >> 16) == 0 or (p >> 15) & 1 != (q >> 15) & 1:
        return None
    kp, kq = (p >> 16) << 15 | (p & 0x7FFF), (q >> 16) << 15 | (q & 0x7FFF)
    return 1 if abs(kp - kq) == 1 else None


def streams_match(a, b):
    """Token streams equal, allowing FLOAT literal data to differ by 1 ulp."""
    i = j = 0
    while i < len(a) and j < len(b):
        if a[i] != b[j]:
            return False
        tok = a[i]
        i += 1
        j += 1
        if tok == 0:
            return i == len(a) and j == len(b)
        if tok == 1:
            va, i = apl64.Value.from_bytes(a, i)
            vb, j = apl64.Value.from_bytes(b, j)
            if (va.t, va.shape) != (vb.t, vb.shape):
                return False
            if va.t == apl64.FLOAT:
                for x, y in zip(va.data, vb.data):
                    d = ulp_diff(x, y)
                    if d is None:
                        return False
                    ULP["one_ulp" if d else "exact"] += 1
            elif va.data != vb.data:
                return False
        elif tok == 2:
            if a[i] != b[j]:
                return False
            i += 1
            j += 1
    return False


def check(s, line):
    got = s.run6502(line)
    want = s.run_model(line)
    if got[0] == 'ok' and want[0] == 'ok':
        assert streams_match(got[1], want[1]), f"{line!r}\n  6502  {got}\n  model {want}"
    else:
        assert got == want, f"{line!r}\n  6502  {got}\n  model {want}"
    have = s.names6502()
    assert have == [apl64.encode_line(n) for n in s.model.names], (line, have)
    return got[0]


FIXED = [
    "", "   ", "⍝ just a comment", "1", "0", "1 0 1 1", "1 2 3", "¯1", "¯1 0 1", "¯0",
    "007", "32767", "32768", "¯32768", "¯32769", "65535", "¯65535", "1 2 40000",
    "0 65535 ¯5", "1 1 1 ¯32768", "12  34\t56", "'a'", "'ab'", "''", "'it''s'", "''''",
    "'a b ×÷'", "'x' ⍝ trailing", "'unterminated", "'a' 'b'", "'a' 1", "1 'a'", "1 2'a'",
    "'a'3", "⍬", "⍬ ⍬", "1 ⍬ 2", "A", "abc", "A B A C B", "x1 y2 x1", "_a ∆b ⍙c a∆", "Ab aB",
    "1+2", "1 2 3+4 5 6", "+/⍳5", "A←1 2 3 ⋄ B←A×2", "(1+2)×3", "A[1;2]", "→0", "1+.×2",
    "+.×", "-\\1 2", "∘.=", "¨⍤", "≠≤≥⍴⍳÷×,", "1 ¯", "¯", "¯x", "1 . 2", "@", "1 ! 2", "a'b'",
    "1e", "1E+1", "12x", "x12", "1 2 3⍝c", "'⍝' 1+", "  1   +   2  ", "'''", "'a''",
]
DECIMAL = [
    "1.5", "0.5", ".5", "¯.5", "1e3", "1E¯2", "2 3.5", "65536", "1.", "9 1.5 'a'", "999999",
    "1e5", "1.0", "10e¯1", "0.0", "¯0.0", "0e5", "12.50e1", "1.e2", "1e0", "1e¯0", "1E005",
    "5.00000000000000001", "5.0000000000000000", "3.14159265358979", "0.1 0.2 0.3",
    "123456789012345678", "0.000000000000000000000000000001", "99999", "100001", "32768.5",
    "65535.5", "32767.5", "¯32768.0", "¯32768.5", "1e38", "1e39", "1.7e38", "1.8e38", "9e38",
    "1e¯38", "1e¯39", "1e¯40", "1e¯47", "1e¯48", "1e¯50", "1e400", "1e401", "1e¯400", "1e¯401",
    "0e401", "0.0e999", "1e99999999999", "1e¯99999999999", "1e", "1e5x", "1ex", "1E+1", "1.5.5",
    "1 .5", ".5.5", "1..5", "1e5e5", "4.5e1 7e0 ¯2.5e¯1", "0.000123 12300000", "1234567890123",
    "7.0000001", "255.999", "2.5e3", "6.5e4", "6.5535e4", "6.5536e4", "3e¯1", "12345678.9",
    "999999999", "9999999999", "0.999999999", "0.9999999999", "1e13", "1e14", "1.5e14",
    "8.5e¯10", "1.0000152587890625", "1.00001525878906250001", "170141183460469231731687303715884105728",
    "¯1.5 2 1e3", "1 0 1.0", "1 1.5", "0.0 1", "1e¯3 0", "00012.50", "0.10", "100e¯2",
]


def gen_line(rng, pool):
    def digits(n):
        return ''.join(rng.choice('0123456789') for _ in range(n))

    def decimal():
        ip = digits(rng.choice([0, 1, 1, 2, 3, 5, 9, 12]))
        fr = digits(rng.choice([0, 1, 2, 4, 9, 12])) if rng.random() < .7 else ''
        if not ip and not fr:
            ip = '0'
        v = ip + ('.' + fr if fr or rng.random() < .3 else '')
        if v.startswith('.') and not fr:
            v = '0' + v
        if rng.random() < .35:
            ex = rng.choice([rng.randint(0, 20), rng.randint(0, 60), rng.randint(390, 410),
                             rng.randint(0, 5), 99999])
            v += rng.choice('eE') + ('¯' if rng.random() < .45 else '') + str(ex)
        return v

    def number():
        vals = []
        for _ in range(rng.choice([1, 1, 2, 3, 5])):
            v = rng.choice(['0', '1', '7', '65535', '32767', '32768', '00',
                            str(rng.randint(0, 65535)), str(rng.randint(0, 300))])
            if rng.random() < .4:
                v = decimal()
            if rng.random() < .3:
                v = '¯' + v
            vals.append(v)
        return rng.choice([' ', '  ', '\t', ' ']).join(vals)

    def string():
        body = ''.join(rng.choice(["a", "b", " ", "Z", "9", "''", "×", "⍴", "+", "⍝", "\t", "!"])
                       for _ in range(rng.randint(0, 6)))
        return "'" + body + ("" if rng.random() < .03 else "'")

    parts = []
    for _ in range(rng.randint(1, 9)):
        k = rng.random()
        if k < .25:
            parts.append(number())
        elif k < .38:
            parts.append(string())
        elif k < .55:
            parts.append(rng.choice(pool))
        elif k < .90:
            parts.append(rng.choice('()[]←→⋄;+-×÷=≠<≤>≥⍳⍴,/\\¨.∘⍤⍬'))
        elif k < .94:
            parts.append('⍝ ' + rng.choice(["note", "'x", "1.5 e"]))
        else:
            parts.append(rng.choice(list('!@#$%&{}?^~"`|:') + ["'", "¯", "\x01"]))
    return rng.choice(['', ' ', '  ', '\t']).join(parts) if rng.random() < .5 else \
        ' '.join(parts)


def test_fixed():
    s = Session()
    kinds = {}
    for line in FIXED:
        k = check(s, line)
        kinds[k] = kinds.get(k, 0) + 1
    dk = {}
    for line in DECIMAL:
        s.reset()
        k = check(s, line)
        dk[k] = dk.get(k, 0) + 1
    print(f"tokenizer fixed cases: {len(FIXED)} match the model {kinds}; "
          f"{len(DECIMAL)} decimal cases {dk}")


def test_limits():
    s = Session()
    res = []
    for i in range(0, 300, 20):
        res.append(check(s, ' '.join(f"n{j}" for j in range(i, i + 20))))
    assert res.count('err') >= 2 and res[12] == 'err', res
    assert len(s.names6502()) == 256
    s.reset()
    assert check(s, "⍬" * 255) == 'ok'
    assert check(s, "'" + "z" * 253 + "'") == 'ok'
    assert check(s, "'" + "q''" * 84 + "'") == 'ok'
    assert check(s, ' '.join(["1"] * 127)) == 'ok'
    assert check(s, ' '.join(["¯40000"] * 36)) == 'ok'
    assert check(s, ' '.join(["1.5"] * 63)) == 'ok'
    assert check(s, ' '.join(["9"] * 124) + " 1e40") == 'err'
    assert check(s, "a" * 254) == 'ok'
    for line in ["1A" * 127, "''" * 127, ".5A" * 85, "1(" * 127, "⍬" * 255, "¯.5A" * 63, "1E9A" * 63, "'a'A" * 63]:
        assert check(s, line) in ('ok', 'err'), line
        n = len(apl64.Interp().tokenize(line))
        assert n <= 1024, (line, n)                     # OUTBUF's size
    print("tokenizer limits: 256 names, 255-byte lines and the densest lines fit the token buffer")


def test_density():
    """No line of 255 characters makes more than 1,024 bytes of tokens (the size of OUTBUF)."""
    rng = random.Random(8)
    atoms = ["1", "A", "'", "''", ".5", "⍬", "(", ")", "+", "1E9", "¯1", "[", "]", ";", "←", "⋄", "'a'", "x1", " ", "0.1", "12345", "→"]
    worst = 0.0
    m = apl64.Interp()
    for _ in range(3000):
        line = ""
        while len(line) < 250:
            line += rng.choice(atoms)
        line = line[:255]
        try:
            n = len(m.tokenize(line))
        except apl64.AplError:
            continue
        worst = max(worst, n / len(line))
        assert n <= 1024, (line, n)
    print(f"tokenizer: the densest of 3000 random lines makes {worst:.2f} token bytes per character (buffer allows 4)")


def exact_decimal(p):
    v = apl64.f_to_fraction(p)
    sign = '¯' if v < 0 else ''
    v = abs(v)
    k = v.denominator.bit_length() - 1
    n = v.numerator * 5 ** k
    d = str(n).rjust(k + 1, '0')
    return sign + (d[:-k] + '.' + d[-k:] if k else d)


def test_roundtrip():
    """The exact decimal expansion of any float24 must parse back to it."""
    rng = random.Random(11)
    s = Session()
    n = 0
    for _ in range(1500):
        e = rng.choice([rng.randint(1, 255), rng.randint(110, 150), rng.randint(1, 20),
                        rng.randint(235, 255)])
        p = (e << 16) | (rng.getrandbits(1) << 15) | rng.getrandbits(15)
        line = exact_decimal(p)
        if len(line) > 255:
            continue
        s.reset()
        got = s.run6502(line)
        want = s.run_model(line)
        assert want[0] == 'ok' and got == want, (line, got, want)
        n += 1
    print(f"tokenizer round trip: {n} exact float24 decimal expansions parse back bit for bit")


def test_exact_range():
    """Up to 9 significant digits and decimal exponent -13..13: no ulp tolerance."""
    rng = random.Random(5)
    s = Session()
    n = 0
    for _ in range(4000):
        nd = rng.choice([1, 2, 3, 4, 5, 6, 7, 8, 9])
        d = str(rng.randint(10 ** (nd - 1), 10 ** nd - 1))
        if rng.random() < .3:
            d = d.rstrip('0') or '0'
        e = rng.randint(-13, 13)
        j = rng.randint(0, len(d))
        x = e + (len(d) - j)                  # "dd.dd" scales by 10^-(len-j)
        line = d[:j] + ('.' if j < len(d) or rng.random() < .3 else '') + d[j:]
        if line.startswith('.') and rng.random() < .5:
            line = '0' + line
        if x or rng.random() < .3:
            line += rng.choice('eE') + ('¯' if x < 0 else '') + str(abs(x))
        if rng.random() < .3:
            line = '¯' + line
        s.reset()
        got, want = s.run6502(line), s.run_model(line)
        assert got == want, (line, got, want)
        n += 1
    print(f"tokenizer exact range: {n} decimals with <=9 digits and exponent -13..13 are bit-exact")


def test_ties():
    """Values exactly halfway between two float24s must round to even, like the model."""
    rng = random.Random(3)
    s = Session()
    lines = []
    for j in range(0, 14):
        for _ in range(60):
            n = (rng.randint(65536, 131071) | 1) << j     # odd 17-bit times 2^j
            if n <= 999999999:
                lines.append(str(n))
                lines.append(str(n) + '.0')
                lines.append('¯' + str(n))
    for _ in range(300):
        n = rng.randint(32768, 65535) * 2 + 1               # (odd 17-bit) / 2
        lines.append(f"{n // 2}.5")
    for k in range(1, 9):                                   # odd 17-bit / 2^k, exact decimals
        for _ in range(40):
            n = (rng.randint(65536, 131071) | 1) * 5 ** k
            d = str(n).rjust(k + 1, '0')
            lines.append(d[:-k] + '.' + d[-k:])
    lines += ["134223872", "13422387.2e1", "0.134223872e9", "2147483649", "4294967297"]
    for line in lines:
        s.reset()
        got, want = s.run6502(line), s.run_model(line)
        if len(line.lstrip('¯').replace('.', '').strip('0')) <= 9:
            assert got == want, (line, got, want)
        else:
            assert streams_match(got[1], want[1]), (line, got, want)
    print(f"tokenizer ties: {len(lines)} exact halfway values round to even like the model")


def test_fuzz():
    ULP.update(exact=0, one_ulp=0)
    rng = random.Random(7)
    pool = [f"{c}{d}" for c in "abAB_∆x" for d in ("", "1", "9z", "∆")] + ["Q" * 30]
    s = Session()
    kinds = {}
    for n in range(3000):
        if n % 8 == 0:
            s.reset()
        line = gen_line(rng, pool)
        if len(apl64.encode_line(line)) > 255:
            continue
        k = check(s, line)
        kinds[k] = kinds.get(k, 0) + 1
    print(f"tokenizer fuzz: {sum(kinds.values())} lines match the model {kinds}; "
          f"float literal elements: {ULP['exact']} exact, {ULP['one_ulp']} one ulp off")


if __name__ == "__main__":
    test_fixed()
    test_limits()
    test_density()
    test_roundtrip()
    test_exact_range()
    test_ties()
    test_fuzz()
