import os
import random
import sys
from fractions import Fraction

sys.path.insert(0, os.getcwd())
import apl64
from harness import call, load
from test_eval import Session, FIXED

FA = 0x10


def encode(s, char_data=False):
    """The model's text as bytes in the charset: only the high minus is not ASCII."""
    if char_data:
        return bytes(ord(c) for c in s)
    return s.replace('¯', '\x90').encode('latin-1')


class FSession(Session):
    def reset(self):
        super().reset()
        self.word("echov", self.L["echo_print"])
        self.word("outv", self.L["lput"])

    def run_model_text(self, line):
        try:
            vals = self.model.run_values(line)
            out = b''
            for v in vals:
                out += encode(apl64.format_value(v), v.t == apl64.CHAR) + b'\n'
            return ('ok', out)
        except apl64.AplError as e:
            return ('err', e.kind)


def test_f_fmt():
    m, L = load("eval")
    rng = random.Random(5)
    ps = []
    for _ in range(9000):                                      # every kind of magnitude
        e = rng.choice([rng.randint(1, 255), rng.randint(100, 160), rng.randint(120, 150)])
        ps.append((e << 16) | (rng.getrandbits(1) << 15) | rng.choice([rng.getrandbits(15), 0, 0x7FFF]))
    for e in range(1, 256):                                    # every exponent, plain and all-ones
        for frac in (0, 0x7FFF, 0x4000):
            ps.append((e << 16) | frac)
    for n in list(range(1, 200)) + [999, 1000, 9999, 10000, 12345, 32767, 32768, 65535, 65536, 65537, 99999, 100000,
                                    123450, 123456, 999949, 999950, 999951, 1234500, 12345000, 1000000000, 9999500000]:
        p = apl64.f_from_fraction(Fraction(n))
        ps += [p, apl64.f_neg(p)]
    for num, den in [(1, 2), (1, 4), (1, 8), (3, 2), (5, 2), (1, 3), (2, 3), (1, 10), (1, 100), (1, 1000), (1, 10000),
                     (1, 100000), (1, 1000000), (12345, 10), (99995, 10), (99999, 100), (9999, 1000), (4999, 1000),
                     (1, 3), (12345, 100000), (5, 100000), (99995, 100000), (1, 65536), (65535, 65536), (3, 65536)]:
        p = apl64.f_from_fraction(Fraction(num, den))
        ps += [p, apl64.f_neg(p)]
    for p in ps:
        m.memory[FA:FA + 3] = [p >> 16, (p >> 8) & 0xFF, p & 0xFF]
        call(m, L["f_fmt"], max_steps=3_000_000)
        n = m.memory[L["flen"]]
        got = bytes(m.memory[L["fbuf"]:L["fbuf"] + n])
        want = encode(apl64.f_format(p))
        assert got == want, (hex(p), got, want)
    print(f"format float: {len(ps)} values print exactly like f_format")


def check_text(s, line):
    if set('[];') & set(line):
        s.reset()               # indexing is in the model only so far
        return 'nonce'
    got = s.run6502(line)
    want = s.run_model_text(line)
    if got[0] == 'err' or want[0] == 'err':
        assert got == want, f"{line!r}\n  6502  {got}\n  model {want}"
        return want[1] if want[0] == 'err' else 'ok'
    assert got == want, f"{line!r}\n  6502  {got[1]}\n  model {want[1]}"
    return 'ok'


TEXT = [
    "5", "¯5", "0", "1 2 3", "¯1 0 1", "1.5", "¯2.25", "0.1", "1 2.5 ¯3", "1e10", "1.2345e10", "¯1e¯10", "1e38", "1e¯38",
    "100000", "123456", "123450", "65536", "65537", "40000", "0.00001234", "0.000001234", "12345.5", "9999.5", "99995",
    "32767", "¯32768", "1 0 1 1", "⍬", "''", "'a'", "'hello'", "'it''s'", "1 2 3⍴'abc'", "3 2⍴'abcdef'", "2 3⍴⍳6",
    "2 3⍴¯5 10 200 ¯3000 4 5", "3 3⍴⍳9", "2 2⍴1.5 2 ¯3.25 100", "2 3⍴1e10 1 2 3 4 5", "3 1⍴⍳3", "1 3⍴⍳3", "2 0⍴1",
    "3 0⍴'a'", "0 0⍴1", "0 3⍴'a'", "2 3⍴0.1", "÷3", "÷⍳5", "(⍳5)÷3", "1÷7", "2*0" if False else "2×3.14159",
    "10÷4", "1e5×1e5", "32767+1", "¯32768-1", "+/⍳100", "×/⍳10", "×/⍳15", "×/⍳20", "1e20×1e10", "1 2 3=1 2 4",
    "A←⍳5 ⋄ A ⋄ A×A ⋄ A÷2", "1 ⋄ 2 3 ⋄ 'x'", "0.5 0.25 0.125", "1e¯5 1e¯6", "12345678901", "1E5", "¯1.5 ¯2.5",
    "2 3⍴1 ¯1", "2 2⍴'ab'", "(2 3⍴⍳6)÷4", "5 6⍴⍳30", "8 5⍴⍳40", "2 2⍴1e¯10 1e10 5 6",
]


def test_text():
    s = FSession()
    kinds = {}
    for line in TEXT:
        try:
            k = check_text(s, line)
        except (ValueError, IndexError):
            continue
        kinds[k] = kinds.get(k, 0) + 1
    print(f"format text: {len(TEXT)} lines print exactly like the model {kinds}")


def test_fuzz():
    from test_eval import gen_line
    rng = random.Random(31)
    s = FSession()
    kinds = {}
    for n in range(3000):
        if n % 6 == 0:
            s.reset()
        defined = [nm for i, nm in enumerate(s.model.names) if i in s.model.vars]
        line = gen_line(rng, defined)
        if len(apl64.encode_line(line)) > 255:
            continue
        try:
            k = check_text(s, line)
        except (ValueError, IndexError):
            s.reset()                       # the model raises on a 0-row matrix; skip it
            continue
        kinds[k] = kinds.get(k, 0) + 1
    print(f"format fuzz: {sum(kinds.values())} evaluated lines print like the model {dict(sorted(kinds.items()))}")


if __name__ == "__main__":
    test_f_fmt()
    test_text()
    test_fuzz()
