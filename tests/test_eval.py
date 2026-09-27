import os
import random
import re
import sys

sys.path.insert(0, os.getcwd())
import apl64
from harness import call, load

ERR = {1: 'SYNTAX ERROR', 2: 'DOMAIN ERROR', 3: 'LIMIT ERROR', 4: 'NONCE ERROR',
       5: 'VALUE ERROR', 6: 'RANK ERROR', 7: 'LENGTH ERROR', 8: 'WS FULL', 9: 'INDEX ERROR', 10: 'INTERRUPT', 12: 'NO GRAPHICS'}
WIDTH = (1, 1, 2, 3)
WS = 3000                      # per-array byte limit, in the model and on the 6502
UNIMPLEMENTED = set()


class Session:
    def __init__(self, reu_kb=512, heap_size=None, spill=True):
        """heap_size: make the heap this many bytes (tests of spilling to the REU); reu_kb: the REU's size; spill=False: an REU
        for the overlays but no room in it for arrays (the machine reports one 64 KB bank), so the heap cannot grow."""
        self.heap_size = heap_size
        self.m, self.L = load("eval", reu_kb=reu_kb)
        if not spill:
            self.m.memory[self.L["reu_banks"]] = 1
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
        if self.heap_size:
            self.word("hlim", self.L["HEAP_BASE"] + self.heap_size)
        self.model = apl64.Interp()
        apl64.gfx_reset()
        self.seed(4242)

    def seed(self, n):
        """The same random number generator state in the model and on the 6502."""
        apl64.rng_seed(n)
        st = apl64._RNG[0]
        for i in range(4):
            self.m.memory[self.L["rnd_state"] + i] = st >> 8 * i & 0xFF

    def run6502(self, line):
        m, L = self.m, self.L
        data = apl64.encode_line(line)
        assert len(data) <= 255
        INBUF = L["INBUF"]
        m.memory[INBUF:INBUF + len(data) + 1] = list(data) + [0]
        self.word("logp", L["LOGBUF"])
        call(m, L["do_line"], max_steps=20_000_000)
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
        h = m.memory[addr + 1]      # (a function's block is a CHAR vector too)
        if m.memory[L["HTH"] + h] == 0xFF:                  # in the REU: its slot holds the block
            a, mem = 0x10000 + h * 0x4000, m.reu.mem
            n = mem[a + 1] | mem[a + 2] << 8
            return bytes(mem[a:a + 3 + 2 * rank + n * WIDTH[t]])
        a = m.memory[L["HTL"] + h] | m.memory[L["HTH"] + h] << 8
        n = m.memory[a + 1] | m.memory[a + 2] << 8
        return bytes(m.memory[a:a + 3 + 2 * rank + n * WIDTH[t]])

    def vars6502(self):
        n = self.m.memory[self.L["symcnt"]] | self.m.memory[self.L["symcnt"] + 1] << 8
        return [self.cell_bytes(self.L["VARS"] + 4 * i) for i in range(n)]

    def gfx_differences(self):
        """What differs between the model's picture and the machine's (nothing, when both are in text mode)."""
        m, L, g = self.m.memory, self.L, apl64.GFX
        diffs = []
        if m[L["gr_mode"]] != g.mode or (m[L["gr_on"]] == 0x80) != (g.mode != 0):
            return [f"mode {m[L['gr_mode']]} (on {m[L['gr_on']]:02x}), model {g.mode}"]
        if getattr(self, "check_sid", False):
            sid = bytes(m[0xD400:0xD400 + apl64.SID_REGS])
            if sid != bytes(g.sid):
                diffs.append(f"SID registers {sid.hex()}, model {bytes(g.sid).hex()}")
        if g.mode == 0:
            return diffs
        if m[L["gr_ink"]] != g.ink:
            diffs.append(f"ink {m[L['gr_ink']]}, model {g.ink}")
        if m[0xD021] != g.bg or m[0xD020] != g.bg:
            diffs.append(f"background {m[0xD021]} border {m[0xD020]}, model {g.bg}")
        for name, mem, want in (("bitmap", m[0xE000:0xE000 + 8000], g.bitmap), ("screen RAM", m[0xCC00:0xCC00 + 1000], g.scr),
                                ("colour RAM", m[0xD800:0xD800 + 1000], g.col))[:3 if g.mode == 1 else 2]:      # (hires does not use colour RAM)
            if bytes(mem) != bytes(want):
                bad = [i for i in range(len(want)) if mem[i] != want[i]]
                diffs.append(f"{name}: {len(bad)} bytes differ, the first at {bad[0]} ({mem[bad[0]]:02x}, model {want[bad[0]]:02x})")
        return diffs

    def run_model(self, line):
        try:
            return ('ok', b''.join(v.to_bytes() for v in self.model.run_values(line)))
        except apl64.AplError as e:
            return ('err', e.kind)

    def vars_model(self):
        out = []
        for i in range(len(self.model.names)):
            if i in self.model.vars:
                out.append(self.model.vars[i].to_bytes())
            elif self.model.defining is not None and self.model.defining[0] == i:
                out.append(self.model.defining[1].block_bytes())     # the 6502 installs it at the header
            elif i in self.model.funcs:
                out.append(self.model.funcs[i].block_bytes())
            else:
                out.append(None)
        return out


def check(s, line):
    got = s.run6502(line)
    want = s.run_model(line)
    if got == ('err', 'WS FULL') and want != got and getattr(s, 'tolerate_wsfull', False):
        s.wsfull_skips = getattr(s, 'wsfull_skips', 0) + 1          # (a deliberately small heap: the model has more room)
        s.reset()
        return 'wsfull'
    if got == ('err', 'NONCE ERROR') and want != got:
        assert UNIMPLEMENTED & set(line), f"unexpected NONCE for {line!r}, model {want}"
        s.reset()
        return 'nonce'
    if got[0] == 'err' or want[0] == 'err':
        assert got == want, f"{line!r}\n  6502  {got}\n  model {want}"
    else:
        assert got == want, f"{line!r}\n  6502  {got[1].hex()}\n  model {want[1].hex()}"
    assert s.vars6502() == s.vars_model(), f"{line!r}: variables differ"
    gfx_diff = s.gfx_differences()
    assert not gfx_diff, f"{line!r}: the picture differs: {gfx_diff}"
    rs = sum(s.m.memory[s.L["rnd_state"] + i] << 8 * i for i in range(4))
    assert rs == apl64._RNG[0], f"{line!r}: the random number generator's state differs ({rs:08x}, model {apl64._RNG[0]:08x})"
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
    # indexing
    "A←10 20 30 40 ⋄ A[2]", "A[3 1]", "A[⍳0]", "A[2 2⍴1 2 3 4]", "A[1]+A[4]", "A[A[1]÷10]", "A[2.0]", "A[]", "A[5]", "A[0]",
    "A[¯1]", "A[1.5]", "A['a']", "A[1;2]", "5[1]", "M←3 4⍴⍳12 ⋄ M[2;3]", "M[2;]", "M[;2]", "M[;]", "M[1 3;2 4]", "M[3 1;1]",
    "M[2 2⍴1 2 3 1;1]", "M[1]", "M[1;2;3]", "M[4;1]", "M[1;5]", "M[1 2;1 2]", "M[2 2⍴1;1 2]", "(⍳5)[3]", "(2 3⍴⍳6)[2;2]",
    "'hello'[1 5]", "1 2 3[2]", "B←2 3⍴⍳6 ⋄ ⍴B[;1]", "⍴A[2 2⍴1]", "A[1][1]", "A[1 2][2]", "M[2;][3]", "+/M[;1]", "A[QQ]", "QQ[1]",
    "A[1", "A[1)", "(A[1)]", "A]", "[1]", "+[1]", "1;2", "A[1;]", "A[1]←5", "+/[1]A", "A[1⋄2]", "A[(1)]", "A[(⍳2)]", "(A)[2]",
    "A[1 2 3;]", "M[;;]", "M[;1;]", "M[(1);(2)]", "M[⍳0;1]", "M[1;⍳0]", "⍴M[⍳0;1]", "⍴M[1;⍳0]", "A[1.0 2]", "A[1 2.5]", "A[1 ¯1]",
    "A[1 5]", "A['a' 5]", "A[5 'a']", "A[40000]", "A[1e10]", "A[1e¯10]", "A[⍬]", "A[0 0]", "A[1 1 1 1]", "M[1 1;1 1]", "M[3;4]",
    "F←1.5 2.5 3.5 ⋄ F[2]", "F[3 1]", "F[2 2⍴1 2 3 1]", "C←'abcdef' ⋄ C[6 1]", "C[2 3⍴1]", "L←1 0 1 1 ⋄ L[3]", "L[⍳4]", "A[L]", "A[1+L]",
    "G←2 3⍴1.5 2.5 3.5 4.5 5.5 6.5 ⋄ G[2;3]", "G[;2]", "G[2;]", "G[1 2;3 1]", "H←2 3⍴'abcdef' ⋄ H[2;3]", "H[;2]", "H[2;1 3]",
    "A[1]+A[2]+A[3]", "A[3]-A[2]-A[1]", "1+A[2]", "A[2]+1", "(A[2])+1", "⍴A[1 2]", "⍳A[1]÷10", "A[⍳A[1]÷10]", "+/A[⍳4]", "-/A[1 2]",
    "A[1]+/A[1 2]", "A+/[1]A", "(⍳3)[2]+A[3]", "A[M[1;1]]", "A[M[1;1 2]]", "A[M[1 2;1]]", "A[A[A[1]÷10]]", "M[A[1]÷10;A[2]÷10]",
    "A←M[2;] ⋄ A", "B←M[;2] ⋄ B←B[2 3] ⋄ B", "N←M[2 3;1 2] ⋄ N[2;2]", "A←A[4 3 2 1] ⋄ A", "X←,5 ⋄ X[1]", "X←5 ⋄ X[1]", "S←⍬ ⋄ S[1]",
    "E←3 0⍴1 ⋄ E[1;1]", "E[⍳0;]", "M[;⍳0]", "1000⍴1 ⋄ (1000⍴1)[500]", "V←⍳1000 ⋄ V[1000 1]", "V[⍳500]", "V[2 3⍴⍳6]", "V[V]",
    "V[1000+1]", "K←100 100⍴⍳100 ⋄ K[100;100]", "K[;1]", "K[2 2⍴1;2 2⍴1]", "K[⍳100;⍳100]", "K[1 2;⍳100]",
    # indexed assignment
    "P←1 2 3 4 5 ⋄ P[2]←9", "P", "P[2 4]←0", "P", "P[1 3]←7 8", "P", "P[1 2]←1 2 3", "P[1]←1 2", "P[1 2]←3 3⍴1", "P[6]←1",
    "P[1;1]←1", "P[1]←'a'", "P", "Q←P ⋄ P[1]←99 ⋄ Q", "P", "P[1]+P[2]←3", "1+P[2]←5", "P[1 1]←4 5", "P[1]", "P[⍳0]←1", "P[⍳0]←1 2",
    "P[⍳0]←'a'", "P[2]←1.5", "P", "R←'hello' ⋄ R[1]←'j' ⋄ R", "R[1]←1", "R[2 3]←'ab' ⋄ R", "R[2]←'xy'", "B←1 0 1 ⋄ B[2]←1 ⋄ B",
    "B[2]←5 ⋄ B", "B[1]←1.5 ⋄ B", "N←2 3⍴⍳6 ⋄ N[2;3]←0 ⋄ N", "N[;1]←7 8 ⋄ N", "N[1;]←9 ⋄ N", "N[1 2;1 2]←2 2⍴1 2 3 4 ⋄ N",
    "N[1 2;1 2]←1 2 3 4", "N[1 2;1 2]←2 3⍴1", "N[;]←0 ⋄ N", "N[1]←1", "N[3;1]←1", "N[2 2⍴1;1 2]←1", "N[1;2]←2.5 ⋄ N", "ZZ[1]←1",
    "(P)[1]←1", "P[1][1]←1", "[1]←1", "P[QQ]←1", "P[1]←QQ", "P[1←2", "P[1]←2 ⋄ P[2]←3 ⋄ P", "P[P[1]]←4 ⋄ P", "P[1 2]←P[2 1] ⋄ P",
    "SS←5 ⋄ SS[1]←2", "P[1]←", "P[]←0 ⋄ P", "P[]←⍳5 ⋄ P", "P[⍳5]←5-⍳5 ⋄ P", "P[2 3]←'a'", "P[2]←3 ⋄ P[3]←P[2]", "T←⍳5 ⋄ T[3]←1e10 ⋄ T",
    "U←1 2 3 ⋄ U[2]←40000 ⋄ U", "U[2]←¯1 ⋄ U", "V←2 2⍴'abcd' ⋄ V[1;2]←'z' ⋄ V", "V[;1]←'xy' ⋄ V", "V[1;1]←5", "V[⍳0;1]←'a'",
    "W←⍳10 ⋄ W[W]←11-W ⋄ W", "X←3 ⍴ 1.5 ⋄ X[2]←1 ⋄ X", "X[1 2 3]←1 2 3 ⋄ X", "Y←⍳3 ⋄ Y[1]←Y[3] ⋄ Y", "Y[2]←Y ⋄ Y", "Y[1 2]←Y",
    "A←⍳3 ⋄ B←A ⋄ A[1]←5 ⋄ A ⋄ B", "A[1]←5 ⋄ ⍴A", "A[1]←A[2]←9 ⋄ A", "A←⍳3 ⋄ A[1]←A[1]+1 ⋄ A", "A[1]←1 ⋄ A[2]←2 ⋄ A[3]←3 ⋄ A",
    "K←100 100⍴0 ⋄ K[1;1]←1 ⋄ K[100;100]←2 ⋄ +/,K", "K[;1]←⍳100 ⋄ +/K[;1]", "K[1;]←⍳100 ⋄ K[1;100]",
    "W←2 2⍴1 ⋄ W[1000⍴1;1000⍴1]", "W[300⍴1;100⍴1]", "W[30⍴1;10⍴1]", "⍴W[30⍴1;10⍴1]", "W[1000⍴1;1]", "W[1;3000⍴1]", "W[256⍴1;256⍴1]", "W[256⍴1;255⍴1]",
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
    "3⌈5", "3⌊5", "1 5 3⌈4", "1 5 3⌊4", "1.5⌈2", "1.5⌊2", "'a'⌈1", "(2 3⍴⍳6)⌈3", "⌈2.5", "⌊2.5", "⌈¯2.5", "⌊¯2.5", "⌊1e10 1.5", "⌊'a'",
    "|¯5", "|5 ¯3 0", "|¯32768", "|1.5 ¯2.5", "|'a'", "3|7", "3|¯7", "¯3|7", "¯3|¯7", "0|5", "1|2.5", "1|¯2.5", "¯32768|1", "5|1 2 3 4 5 6 7",
    "⌈/1 5 3", "⌊/1 5 3", "⌈/⍬", "|/⍬", "⌊/2 3⍴4 1 5 9 2 7", "5|⌈/3 9 7", "⌈\\1 2", "⌈.+1", "1 ⌈/ 2", "2⌈/3 4", "(⍳5)|17",
    "A←⍳10 ⋄ A|A×A", "⌊/⌈/2 2⍴1", "⌈⌈⌈1.5", "|-3", "-|3", "3⌊⌈2.2", "1⌈2⌊3", "⌈/⌊/2 3⍴⍳6", "|⌊¯2.5",
    "1∧1", "1∧0", "0∨0", "0∨1", "1 0 1∧1 1 0", "1 0 1∨0 0 0", "~1", "~0 1 1", "~2", "1∧2", "'a'∧1", "~'a'", "1.5∨0", "1.0∧1", "(1=1 2 3)∧(2=2 2 2)",
    "∧/1 1 0", "∧/1 1 1", "∨/0 0 1", "∨/⍬", "∧/⍬", "∧/,2", "∧/2 2", "1 0∧1 0 1", "~~1", "1~0", "(2 2⍴1 0)∨1", "+/~1 0 1", "∧/'ab'", "~⍬", "⍬∧⍬",
    "(1.5-0.5)∧1", "(0.5+0.5)∨0", "(1.5-0.5)∧2", "(1.5-0.5)∧1.5", "~(1.5-0.5)", "~(1.5-1.5)", "(1.5-1.5)∨(1.5-0.5)", "(2.5-1.5)∧(2.5-1.5)", "(1.5 0.5+0.5 ¯0.5)∨0", "(1.5-0.5)∧'a'",
    "~(⍳3)>1", "(~1 0)∧0 1", "1 0 1/⍳3", "(⍳5>2)/⍳5", "A←1 0 1 ⋄ ~A∨~A", "0∧1∨1", "1∨0∧0", "~~~1", "(2 3⍴⍳6)∧1", "1e0∧1",
    "10 20 30⍳20", "10 20 30⍳5 30 10", "10 20 30⍳2 2⍴10 20 30 40", "'abc'⍳'cab'", "'abc'⍳'z'", "1 2 3⍳1.5-0.5", "1.5 2⍳2 1.5", "1 2 3⍳'a'", "'a'⍳1", "⍬⍳1 2",
    "1 2⍳⍬", "5⍳5", "(2 2⍴1)⍳1", "1 0 1⍳1", "10 20⍳20", "1 2 3⍳3.5-0.5", "(⍳5)⍳5 4 3 2 1 0 6", "'hello world'⍳'lo'", "1e10 1⍳1", "1.5 2.5⍳1.5", "⍬⍳⍬", "1 2⍳1", "0 1⍳1 0 2",
    "1 2 3∊2", "'abc'∊'cd'", "(2 2⍴1 2 3 4)∊2 4", "⍬∊1", "1∊⍬", "1 2∊1.5-0.5 3", "5∊5", "'a'∊'abc'", "'a'∊1 2", "1∊'a'", "(⍳5)∊2 4", "1.5∊1.5 2", "3 4∊(2 2⍴3 5 6 7)", "⍬∊⍬", "0∊0 1", "1e10∊1e10",
    "⍋3 1 2", "⍒3 1 2", "⍋3 1 2 1", "⍒3 1 2 1", "⍋'hello'", "⍒'hello'", "⍋1.5 ¯2 0 1.5", "⍒1.5 ¯2 0 1.5", "⍋⍬", "⍋5", "⍋2 2⍴1", "⍋32767 ¯32768 0", "⍒32767 ¯32768 0", "⍋1e10 1 ¯1e10", "⍋0 1 1 0",
    "⍒0 1 1 0", "⍋,7", "⍋2 1", "A←5 3 9 1 ⋄ A[⍋A]", "A[⍒A]", "⍋⍋3 1 2", "⍋⍒3 1 3", "⍋⍳9", "⍒⍳9", "⍋9-⍳9", "⍋(⍳20)|17×⍳20", "(⍋3 1 2)⍳1 2 3", "⍋'ba','ab'",
    "⌽1 2 3", "⌽5", "⌽2 3⍴⍳6", "⌽'abc'", "⌽⍬", "1⌽1 2 3 4", "¯1⌽1 2 3 4", "5⌽1 2 3 4", "0⌽1 2 3", "1⌽2 3⍴⍳6", "¯1⌽2 3⍴⍳6", "1⌽5", "1 2⌽1 2 3",
    "(2 3⍴1)⌽1 2 3", "1.5⌽1 2", "'a'⌽1 2", "2⌽⍬", "32768⌽1 2 3", "¯32768⌽1 2 3", "32767⌽⍳7", "¯32767⌽⍳7", "1e10⌽1", "2⌽'abcde'", "3⌽1.5 2.5 3.5 4.5", "1⌽3 2⍴1 2 3 4 5 6", "⌽⌽⍳4",
    "⌽(2 3⍴1 0 1)∧1", "⍴⌽2 3⍴⍳6", "(⍳0)⌽⍳3", "1⌽1⍴7", "⌽1⍴7", "1⌽0⍴5", "⌽3 0⍴1", "2⌽3 0⍴1", "⌽0⍴'a'",
    "3↑1 2 3 4 5", "¯3↑1 2 3 4 5", "7↑1 2 3", "¯7↑1 2 3", "0↑1 2 3", "3↑5", "2↑'abc'", "5↑'ab'", "2 2↑3 3⍴⍳9", "¯2 ¯2↑3 3⍴⍳9", "4 4↑2 2⍴1", "2↑3 3⍴⍳9",
    "1 2 3↑1 2", "2 3↑1 2 3 4 5", "1.5↑1", "100000↑1", "'a'↑1", "(2 2⍴1)↑1", "1e10↑1", "1↑⍬", "↑1", "3↑1.5 2.5", "¯1 3↑2 2⍴⍳4", "2 ¯4↑2 3⍴⍳6", "0 3↑2 2⍴1", "⍴0 3↑2 2⍴1",
    "3↓1 2 3 4 5", "¯3↓1 2 3 4 5", "7↓1 2 3", "0↓1 2 3", "2↓5", "1 1↓3 3⍴⍳9", "¯1 ¯1↓3 3⍴⍳9", "1 ¯1↓3 3⍴⍳9", "5 0↓3 3⍴⍳9", "⍴5 0↓3 3⍴⍳9", "1e10↓1 2 3", "¯1e10↓1 2 3", "1↓⍬", "↓1",
    "1↓'abc'", "¯2↓'abc'", "2↓3 3⍴⍳9", "3↑⍳3", "¯3↑⍳3", "(⍳3)↑⍳5", "2↓(2 3⍴⍳6)", "1⌽3↑⍳5", "(¯2↓⍳5),⌽2↑⍳5", "⌽5↓⍳9", "+/3↑⍳9", "⍴3↑2 2⍴1", "40000↓1", "5↑40000⍴1",
    "2/3", "1 0 1/4 5 6", "1 0 1/'abc'", "0/5", "2 0 1/1 2 3", "1 2/3", "2/1 2", "1 1/1 2 3", "¯1/5", "1.5/5", "'a'/5",
    "(2 2⍴1)/5", "1/2 2⍴1", "1 0 1\\1 2 3", "(1 0 1=1 2 1)/⍳3", "+/2/1 2", "A←3 ⋄ A/⍳2", "40000/1", "⍬/⍬", "1 1 1/⍬", "1/⍬", "3/⍬", "¯1/⍬", "100001/''", "¯1/''", "1e10/⍬",
    "1 0 1/1.5 2 3", "1 1 0 0 1/⍳5", "0 0 0/1 2 3", "1 0 1/'',5", "(3⍴1)/'abc'", "2/'ab'", "3 0 2/⍳3", "1/5", "1 1/5", "1/1 1", "2 1/1",
    "1 2 3/'a'", "1 2 3/1 2 3 4", "(⍳0)/⍳0", "1e10/1", "¯1e10/1", "65535/1", "40000 40000/1 2", "255 255 255/1 2 3", "A←1 0 1 ⋄ A/⍳3 ⋄ A/A",
    "2/2/1", "2/(2/1)", "(1 0)/(2/1 2)", "1 0 1/A←4 5 6", "+/(⍳5)/⍳5", "(⍳3)/⍳3", "(⍳3)=⍳3", "(1 0 1)/(⍳3)", "1 1/A", "/1", "1/", "1//1",
    "(⍳3)=⍳3", "(⍳3)<3", "1 2 3≠1 5 3", "+/⍳3", "A←5 ⋄ A+A", "B←1 2 3 ⋄ B←B+1 ⋄ B", "(A←2)+A←3",
    # scan, outer product and inner product (their own tests are test_scan.py and test_inner.py)
    "+\\1 2 3 4", "-\\2 3⍴⍳6", "+\\32767 1 1", "×\\1.5 2 3", "1 2 3∘.×1 2 3", "(⍳3)∘.=⍳3", "1.5 2∘.+1 2", "1 2 3+.×4 5 6", "(2 3⍴⍳6)+.×3 2⍴⍳6",
    "(2 2⍴32767 1 5 5)+.×2 2⍴2 1 1 1", "(2 2⍴1 1 1 1)+.×2 2⍴32767 1 1 32767", "1 2+.×2 3⍴1.5", "(2 3⍴1 0 1 1 1 0)∧.=3 2⍴1 0 1 1 0 0",
    "(2 2⍴1 2 3 4)⌈.+2 2⍴1 2 3 4", "A←2 2⍴⍳4 ⋄ A+.×A+.×A",
    "⍉2 3⍴⍳6", "2 1⍉3 2⍴1.5", "⍉⍉2 3⍴⍳6", "1 2 3 4 5~2 4", "'hello'~'l'", "1 0 1\\7 8", "1 0 1 1\\1 2 3", "1 0 1\\'ab'", "1 0 1\\5", "A←2 3⍴⍳6 ⋄ (⍉A)+.×A",
    "+/[1]2 3⍴⍳6", "+/[2]2 3⍴⍳6", "+\\[1]3 2⍴⍳6", "⌽[1]2 3⍴⍳6", "2⌽[2]2 3⍴1.5", "×\\[1]2 3⍴1 2 32767 4 5 6", "+/[1]⍳4", "+/[3]2 3⍴⍳6", "+/[1.5]2 3⍴⍳6", "A←3 2⍴⍳6 ⋄ (+/[1]A)+/[2]A",
    "(2 3⍴⍳6),(2 2⍴7 8 9 10)", "(2 3⍴⍳6),1 2", "1 2,2 3⍴1.5", "(2 3⍴⍳6),[1]2 3⍴1", "1 2 3,[1]2 3⍴⍳6", "(2 2⍴1),[2]1 2", "1 0 1/2 3⍴⍳6", "1 0/[1]2 3⍴⍳6", "1 0 1\\2 2⍴7 8 9 10", "0 1\\[1]2 2⍴⍳4", "(2 2⍴'ab'),(2 1⍴'cd')", "(2 3⍴1),(3 2⍴1)",
    "*1", "*1 2 3", "⍟10", "⍟2 3⍴⍳6", "2*10", "2*0.5", "0.3*2.7", "(⍳3)∘.*⍳3", "2*⍳6", "(2 3⍴⍳6)*2", "2⍟8 16", "*100", "⍟0", "¯2*0.5", "A←*⍳4 ⋄ A", "(⍳4)∘.⍟⍳4", "?6", "?0", "5?10", "?2 3⍴10", "?20⍴6", "10?10", "?0 5 ⋄ ?6", "?32768", "5?3", "!5", "!⍳6", "2!5", "3!⍳8", "(⍳4)∘.!⍳4", "!34", "!¯1", "○1", "○⍳4", "1○0.5", "2○⍳3", "3○0.5 1", "¯1○0.5", "¯2○0.3", "¯3○2", "(⍳3)∘.○⍳3", "1○1e10", "5○1",
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
        if r < .86:                                     # indexed assignment
            groups = [rng.choice(["", operand(), rng.choice(["1", "2", "1 2", "⍳3", "2 1", "3"])])
                      for _ in range(rng.choice([1, 1, 2]))]
            return rng.choice(names) + "[" + ";".join(groups) + "]←" + expr(d - 1)
        if r < .89:                                     # replicate, compress, rotate, take, drop
            if rng.random() < .3:
                return rng.choice("⌽⍋⍒") + expr(d - 1)
            return "(" + expr(d - 1) + ")" + rng.choice(["/", "/", "⌽", "↑", "↓", "∧", "∨", "⍳", "∊"]) + expr(d - 1)
        if r < .92:                                     # indexing
            base = rng.choice(names) if rng.random() < .7 else "(" + expr(d - 1) + ")"
            groups = [rng.choice(["", expr(d - 1), operand(), rng.choice(["1", "2", "1 2", "⍳3", "2 1"])])
                      for _ in range(rng.choice([1, 1, 1, 2, 2, 3]))]
            return base + "[" + ";".join(groups) + "]"
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


def test_nesting_limit():
    """Frames are 64 deep: 64 nested parentheses work, 65 are a LIMIT ERROR (the model has no limit)."""
    s = Session()
    s.reset()
    ok = s.run6502("(" * 64 + "1" + ")" * 64)
    assert ok[0] == "ok" and ok[1] == s.run_model("1")[1], ok
    assert s.run6502("(" * 65 + "1" + ")" * 65) == ("err", "LIMIT ERROR")
    assert s.run6502("1+1")[0] == "ok"
    print("evaluator: 64 nested parentheses are fine, 65 are a LIMIT ERROR")


def test_gc_pressure():
    """Arrays are created and dropped far faster than the heap holds them."""
    s = Session()
    rng = random.Random(9)
    lines = 0
    for i in range(160):
        a, b = rng.sample("ABCD", 2)
        n = rng.choice([300, 700, 1200, 1400])
        line = rng.choice([f"{a}←⍳{n}", f"{a}←,{b}", f"{a}←{b},{b}", f"{a}←{n}⍴{rng.choice(['1', '1 2 3', '2.5'])}",
                           f"{a}←(⍳{n}),⍳{n}", f"⍴{a}", f"{a}←⍴{b}", f"{a}←2 3⍴{b}",
                           f"{a}←{b}[⍳{n // 2}]", f"{a}←{b}[{b}]", f"{a}←(2 {n // 4}⍴{b})[2;]", f"{a}←(⍳{n})[⍳{n // 3}]",
                           f"{a}←⍳{n} ⋄ {a}[⍳{n // 2}]←{n}", f"{a}←⍳{n} ⋄ {b}←{a} ⋄ {a}[1]←0.5", f"{a}←{n}⍴1 ⋄ {a}[2]←'a'",
                           f"{a}←2/⍳{n // 2}", f"{a}←⍋{n // 6}|17×⍳{n // 3}", f"{a}←(⍳{n // 3})⍳{n // 4}⍴5", f"{a}←(⍳{n // 4})∊{n // 3}⍴7", f"{a}←{n // 3}↑⍳{n}", f"{a}←⌽{b}", f"{a}←{n // 2}⌽⍳{n}", f"{a}←¯{n // 4}↓{b},{b}", f"{a}←(⍳{n})=⍳{n}", f"{a}←({b}>0)/{b}"])
        check(s, line)
        lines += 1
    assert s.m.memory[s.L["htop"]] | s.m.memory[s.L["htop"] + 1] << 8 <= s.L["HEAP_LIMIT"]
    print(f"evaluator GC pressure: {lines} allocating lines match the model")


if __name__ == "__main__":
    test_fixed()
    test_fuzz()
    test_nesting_limit()
    test_gc_pressure()
