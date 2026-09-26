import os
import random
import re
import sys

sys.path.insert(0, os.getcwd())
import apl64
from harness import call, load

ERR = {1: 'SYNTAX ERROR', 2: 'DOMAIN ERROR', 3: 'LIMIT ERROR', 4: 'NONCE ERROR',
       5: 'VALUE ERROR', 6: 'RANK ERROR', 7: 'LENGTH ERROR', 8: 'WS FULL'}
WIDTH = (1, 1, 2, 3)
WS = 3000                      # per-array byte limit, in the model and on the 6502
UNIMPLEMENTED = set('[];')       # indexing is in the model only so far


class Session:
    def __init__(self):
        self.m, self.L = load("eval")
        apl64.WS_BYTES = WS
        self.reset()

    def word(self, name, v):
        a = self.L[name]
        self.m.memory[a] = v & 0xFF
        self.m.memory[a + 1] = v >> 8

    def reset(self):
        call(self.m, self.L["tok_init"])
        call(self.m, self.L["eval_init"])
        self.word("echov", self.L["echo_log"])
        self.word("wsmax", WS)
        self.model = apl64.Interp()

    def run6502(self, line):
        m, L = self.m, self.L
        data = apl64.encode_line(line)
        assert len(data) <= 255
        INBUF = L["INBUF"]
        m.memory[INBUF:INBUF + len(data) + 1] = list(data) + [0]
        call(m, L["tokenize"], max_steps=2_000_000)
        if m.p & 1:
            return ('err', ERR[m.a])
        self.word("logp", L["LOGBUF"])
        call(m, L["eval_line"], max_steps=20_000_000)
        if m.p & 1:
            return ('err', ERR[m.a])
        end = m.memory[L["logp"]] | m.memory[L["logp"] + 1] << 8
        return ('ok', bytes(m.memory[L["LOGBUF"]:end]))

    def cell_bytes(self, addr):
        m, L = self.m, self.L
        tag = m.memory[addr]
        if tag == 0x80:
            return None
        t, rank = tag & 3, tag >> 2 & 3
        if rank == 0:
            return bytes([tag, 1, 0]) + bytes(m.memory[addr + 1:addr + 1 + WIDTH[t]])
        h = m.memory[addr + 1]
        a = m.memory[L["HTL"] + h] | m.memory[L["HTH"] + h] << 8
        n = m.memory[a + 1] | m.memory[a + 2] << 8
        return bytes(m.memory[a:a + 3 + 2 * rank + n * WIDTH[t]])

    def vars6502(self):
        n = self.m.memory[self.L["symcnt"]] | self.m.memory[self.L["symcnt"] + 1] << 8
        return [self.cell_bytes(self.L["VARS"] + 4 * i) for i in range(n)]

    def run_model(self, line):
        try:
            return ('ok', b''.join(v.to_bytes() for v in self.model.run_values(line)))
        except apl64.AplError as e:
            return ('err', e.kind)

    def vars_model(self):
        return [self.model.vars[i].to_bytes() if i in self.model.vars else None
                for i in range(len(self.model.names))]


def check(s, line):
    if UNIMPLEMENTED & set(line):
        s.reset()               # the 6502 does not know this syntax yet
        return 'nonce'
    got = s.run6502(line)
    want = s.run_model(line)
    if got == ('err', 'NONCE ERROR') and want != got:
        assert UNIMPLEMENTED & set(line), f"unexpected NONCE for {line!r}, model {want}"
        s.reset()
        return 'nonce'
    if got[0] == 'err' or want[0] == 'err':
        assert got == want, f"{line!r}\n  6502  {got}\n  model {want}"
    else:
        assert got == want, f"{line!r}\n  6502  {got[1].hex()}\n  model {want[1].hex()}"
    assert s.vars6502() == s.vars_model(), f"{line!r}: variables differ"
    return got[1] if got[0] == 'err' else 'ok'


FIXED = [
    "1", "1 2 3", "0", "¯5", "1.5", "2 3.5", "40000", "'a'", "'abc'", "''", "⍬", "'it''s'",
    "A←5", "A←5 ⋄ A", "A←1 2 3 ⋄ B←A ⋄ B", "A←B←3 ⋄ A ⋄ B", "(1)", "((1 2 3))", "(A←2)", "1 ⋄ 2 ⋄ 3",
    "⍴1 2 3", "⍴5", "⍴⍬", "⍴''", "⍴'abc'", "⍴2 3⍴⍳6", "⍴⍴2 3⍴⍳6", "⍴⍴⍴5",
    "⍳0", "⍳1", "⍳5", "⍳2.0", "⍳,3", "⍳⍳3", "⍳¯1", "⍳'a'", "⍳1 2", "⍳⍬", "⍳2 3⍴1", "⍳1.5", "⍳40000",
    "⍳32768", "⍳4000", "⍳'',5",
    "2 3⍴⍳6", "3⍴1 2", "5⍴'ab'", "0⍴5", "⍬⍴5", "2 2⍴'abcd'", "2 3⍴1.5", "4⍴⍬", "3⍴''", "2 3⍴⍬",
    "(⍳3)⍴5", "2 3 4⍴1", "¯1⍴5", "2 ¯3⍴1", "'a'⍴1", "1.5⍴1", "2.0⍴7", "40000⍴1", "100 100⍴1", "1000⍴1 2 3",
    "2 3⍴2 3⍴⍳6", "(2 3⍴⍳6)⍴1", "1⍴2 3⍴4", "0 3⍴1", "3 0⍴1", "0⍴''",
    ",5", ",1 2 3", ",2 3⍴⍳6", ",'a'", ",''", ",⍬", ",,5", ",⍴5",
    "1 2,3 4", "1,2", "1,2,3", "(⍳3),4 5", "1 2,3.5", "1.5,2", "'ab','cd'", "'a','b'", "'ab',''", "'',1 2",
    "1 2,'a'", "'a',1", "⍬,1", "⍬,'a'", "⍬,⍬", "1 0 1,1 2", "1 0 1,0", "(2 3⍴⍳6),1", "1,2 3⍴4", "'a',2 2⍴'abcd'",
    "1 2,40000", "40000,1 2", "0,1.5 2", "1 0,1 0", "(⍳1000),⍳1000", "(⍳2000),⍳2000",
    "+5", "+1 2 3", "+'a'", "+2 3⍴⍳6", "++5", "+⍬", "+''",
    "B", "A", "A←B", "1 B", "B←", "←3", "()", "(", ")", "1)", "(1", "((1)", "1 2 A", "A A", "1 ⍴",
    "⍴", ",", "⍳", "⍴⍳", "1 2 3 ⍴⍳", "(1 2)(3)", "1 (2)", "(1) 2", "A←(B←3)", "1⍴(2)", "(⍳2)(⍳3)",
    "1 ⋄", "⋄", "⋄ 1", "1 ⋄⋄ 2", "(1 ⋄ 2)", "A←1 ⋄ A←A,2 ⋄ A", "A←⍳3 ⋄ A←A,A ⋄ A←A,A ⋄ ⍴A",
    "A[1]", "A[1;2]", "→1", "1;2", "[", "]", "1[", "A←1 ⋄ B←A[", "1 ⋄ [",
    "⍳3 ⋄ ⍴⍳3 ⋄ ,⍳3", "A←2 3⍴⍳6 ⋄ ⍴A ⋄ ,A ⋄ (⍴A)⍴0", "A←'hello' ⋄ B←'world' ⋄ A,' ',B",
    "1+2", "+/1 2 3", "1 2 3+4 5 6", "-1", "×2", "÷2", "1=1", "1 2 3=1 2 4", "3-1", "⍴1+2", "1⍴2+3",
    "1+2×3", "(1+2)×3", "10÷4", "10÷0", "0÷0", "1 2 3-1", "A←1 2 3 ⋄ A×A", "A←⍳5 ⋄ A=3", "2 3⍴⍳6 ⋄ 1+2 3⍴⍳6",
    "(2 3⍴⍳6)+2 3⍴1", "(2 3⍴⍳6)+3 2⍴1", "1 2+1 2 3", "1 2+(2 3⍴1)", "'a'+1", "'a'='a'", "'a'≠'b'", "'a'<'b'",
    "1='a'", "'abc'='abd'", "⍬+1", "''='a'", "⍬×⍬", "32767+1", "¯32768-1", "¯32768×¯1", "-¯32768", "-32767",
    "200×200", "181×181", "182×182", "1e38×10", "1e38+1e38", "1÷3", "2÷3", "1.5×2", "0.1+0.2", "0.1+0.2=0.3",
    "100000=100001", "1=1.00003", "1=1.0001", "×¯5 0 5", "×¯2.5 0 2.5", "×'a'", "-'a'", "÷'a'", "÷0", "÷4", "÷¯4",
    "-1 2 3", "-2 3⍴⍳6", "÷2 3⍴⍳6", "×2 3⍴¯1 0 1", "-1.5", "-⍬", "÷⍬", "×⍬", "3-3", "1<2", "2<1", "1≤1", "1≥2", "1>0",
    "+/⍳4", "×/⍳5", "-/⍳4", "÷/1 2 4", "=/1 1 1", "≠/1 2 3", "+\\1 2", "+/2 3⍴⍳6", "×/2 3⍴⍳6", "+/32767 1", "×/⍳10",
    "+/1e10 1 ¯1e10", "+/1 2,3.5", "+/'ab'", "+/''", "+/5", "+/'a'", "+/2 3⍴1.5", "A←⍳5 ⋄ +/A×A", "+/(⍳3)+⍳3", "1+/2", ",/1 2", "⍴/1 2",
    "(⍳3)=⍳3", "(⍳3)<3", "1 2 3≠1 5 3", "+/⍳3", "A←5 ⋄ A+A", "B←1 2 3 ⋄ B←B+1 ⋄ B", "(A←2)+A←3",
]


def gen_line(rng, defined):
    names = "ABCD"

    def lit():
        return rng.choice(["0", "1", "7", "¯2", "1 2 3", "4 5", "0 1 1", "3", "10", "2", "1 2 3 4 5 6",
                           "1.5", "2 3.5", "40000", "⍬", "'a'", "'abc'", "''", "'xy'", "'it''s'", "2 3", "3 2",
                           "32767", "¯32768", "0.1", "1e38", "1.00003", "100001", "1 0 1"])

    def operand():
        if rng.random() < .35:
            pool = defined if defined and rng.random() < .93 else names
            return rng.choice(pool)
        return lit()

    def expr(d):
        r = rng.random()
        if d <= 0 or r < .2:
            return operand()
        if r < .42:
            if rng.random() < .18:                          # reduce
                return rng.choice("+-×÷=≠<≤>≥") + "/" + expr(d - 1)
            op = rng.choice("⍳⍴,+-×÷")
            if op == "⍳" and rng.random() < .8:          # a small scalar is the usual argument
                return "⍳" + rng.choice(["0", "1", "3", "5", "12", "2.0", "(" + expr(d - 1) + ")"])
            return op + rng.choice(["", " "]) + expr(d - 1)
        if r < .72:
            if rng.random() < .3:                          # dimension list on the left of ⍴
                return rng.choice(["3", "2 3", "0", "5", "1 4", "6", "2 2"]) + "⍴" + expr(d - 1)
            left = operand() if rng.random() < .6 else "(" + expr(d - 1) + ")"
            return left + rng.choice("⍴,+-×÷=≠<≤>≥") + expr(d - 1)
        if r < .82:
            return "(" + expr(d - 1) + ")"
        return rng.choice(names) + "←" + expr(d - 1)

    stmts = [expr(rng.choice([1, 2, 3, 3, 4])) for _ in range(rng.choice([1, 1, 1, 2, 3]))]
    line = "⋄".join(stmts)
    if rng.random() < .12:                              # damage it: syntax errors, odd tokens
        chars = list(line)
        k = rng.randrange(len(chars) + 1)
        chars.insert(k, rng.choice("()←⋄⍴,⍳+ A'1.[]") ) if rng.random() < .6 else chars.pop(min(k, len(chars) - 1))
        line = "".join(chars)
    return line


def test_fixed():
    s = Session()
    kinds = {}
    for line in FIXED:
        k = check(s, line)
        kinds[k] = kinds.get(k, 0) + 1
    print(f"evaluator fixed cases: {len(FIXED)} {kinds}")


def test_fuzz():
    rng = random.Random(21)
    s = Session()
    kinds = {}
    for n in range(4000):
        if n % 6 == 0:
            s.reset()
        defined = [nm for i, nm in enumerate(s.model.names) if i in s.model.vars]
        line = gen_line(rng, defined)
        if len(apl64.encode_line(line)) > 255:
            continue
        k = check(s, line)
        kinds[k] = kinds.get(k, 0) + 1
    print(f"evaluator fuzz: {sum(kinds.values())} lines {dict(sorted(kinds.items()))}")


def test_gc_pressure():
    """Arrays are created and dropped far faster than the heap holds them."""
    s = Session()
    rng = random.Random(9)
    lines = 0
    for i in range(160):
        a, b = rng.sample("ABCD", 2)
        n = rng.choice([300, 700, 1200, 1400])
        line = rng.choice([f"{a}←⍳{n}", f"{a}←,{b}", f"{a}←{b},{b}", f"{a}←{n}⍴{rng.choice(['1', '1 2 3', '2.5'])}",
                           f"{a}←(⍳{n}),⍳{n}", f"⍴{a}", f"{a}←⍴{b}", f"{a}←2 3⍴{b}"])
        check(s, line)
        lines += 1
    assert s.m.memory[s.L["htop"]] | s.m.memory[s.L["htop"] + 1] << 8 <= s.L["HEAP_LIMIT"]
    print(f"evaluator GC pressure: {lines} allocating lines match the model")


if __name__ == "__main__":
    test_fixed()
    test_fuzz()
    test_gc_pressure()
