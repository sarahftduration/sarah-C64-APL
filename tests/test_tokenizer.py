import os
import random
import re
import sys

sys.path.insert(0, os.getcwd())
import apl64
from harness import call, load

INBUF, OUTBUF, SYMTAB = 0x3000, 0x3400, 0x4000
ERR = {1: 'SYNTAX ERROR', 2: 'DOMAIN ERROR', 3: 'LIMIT ERROR', 4: 'NONCE ERROR'}


class Session:
    """One 6502 tokenizer and one model interpreter, kept in step."""

    def __init__(self):
        self.mpu, self.L = load("tokenizer")
        self.reset()

    def reset(self):
        call(self.mpu, self.L["tok_init"])
        self.model = apl64.Interp()

    def run6502(self, line):
        data = apl64.encode_line(line)
        assert len(data) <= 255
        m = self.mpu
        m.memory[INBUF:INBUF + len(data) + 1] = list(data) + [0]
        call(m, self.L["tokenize"], max_steps=2_000_000)
        if m.p & 1:
            return ('err', ERR[m.a])
        end = m.memory[self.L["op"]] | m.memory[self.L["op"] + 1] << 8
        return ('ok', bytes(m.memory[OUTBUF:end]))

    def names6502(self):
        m = self.mpu
        n = m.memory[self.L["symcnt"]] | m.memory[self.L["symcnt"] + 1] << 8
        names, p = [], SYMTAB
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


def unsupported(line):
    return (bool(re.search(r'\d\.|\.\d|\d[eE]¯?\d', line))
            or any(int(x) > 65535 for x in re.findall(r'\d+', line)))


def check(s, line):
    got = s.run6502(line)
    if got == ('err', 'NONCE ERROR'):
        assert unsupported(line), f"unexpected NONCE for {line!r}"
        s.reset()
        return 'nonce'
    want = s.run_model(line)
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
NONCE = ["1.5", "1e3", "100000", ".5", "¯.5", "1E¯2", "2 3.5", "65536", "1.", "9 1.5 'a'",
         "999999", "1e5"]


def gen_line(rng, pool):
    def number():
        vals = []
        for _ in range(rng.choice([1, 1, 2, 3, 5])):
            v = rng.choice(['0', '1', '7', '65535', '32767', '32768', '00',
                            str(rng.randint(0, 65535)), str(rng.randint(0, 300))])
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
    for line in NONCE:
        assert s.run6502(line) == ('err', 'NONCE ERROR'), line
        s.reset()
    print(f"tokenizer fixed cases: {len(FIXED)} match the model {kinds}; "
          f"{len(NONCE)} unimplemented forms give NONCE ERROR")


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
    assert check(s, "a" * 254) == 'ok'
    print("tokenizer limits: 256 names, 255-byte lines and 6-byte-per-glyph output ok")


def test_fuzz():
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
    print(f"tokenizer fuzz: {sum(kinds.values())} lines match the model {kinds}")


if __name__ == "__main__":
    test_fixed()
    test_limits()
    test_fuzz()
