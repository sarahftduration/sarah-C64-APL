"""Workspace files (DESIGN.md, Workspace files): the encoder, and a decoder that follows the 6502
loader step for step, including the partial workspace a failed load leaves behind."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import apl64

MAGIC = b"APLW" + bytes([2])
UNDEFINED = 0x80
FUNCTION = 0x15               # a function: the tag of a CHAR vector, plus $10
MAX_LINE = 1536               # OUTBUF: the largest token stream a line can have
WIDTH = (1, 1, 2, 3)
INV = {v: k for k, v in apl64.GLYPH_CODES.items()}


def value_bytes(v):
    """A scalar is its tag and data; an array is the heap layout (tag, count, lengths, data)."""
    b = v.to_bytes()
    return bytes([b[0]]) + b[3:] if v.rank == 0 else b


def encode(model):
    """Every symbol in order (the functions' token streams name symbols by number, so the numbers must
    survive): its name, then its value, a function, or a lone $80 if it has none."""
    out = bytearray(MAGIC) + len(model.names).to_bytes(2, "little")
    for i, name in enumerate(model.names):
        nb = apl64.encode_line(name)
        out += bytes([len(nb)]) + nb
        if i in model.vars:
            out += value_bytes(model.vars[i])
        elif i in model.funcs:
            b = model.funcs[i].block_bytes()
            out += bytes([FUNCTION]) + b[1:]
        else:
            out += bytes([UNDEFINED])
    return bytes(out) + b"E"


class _IO(Exception):
    pass


class _Reader:
    def __init__(self, data):
        self.d, self.p = data, 0

    def take(self, n):
        if self.p + n > len(self.d):
            self.p = len(self.d)
            raise _IO
        b = self.d[self.p:self.p + n]
        self.p += n
        return b

    def byte(self):
        return self.take(1)[0]

    def u16(self):
        return int.from_bytes(self.take(2), "little")


def _value(t, rank, shape, raw):
    n = len(raw) // WIDTH[t]
    data = []
    for i in range(n):
        chunk = raw[i * WIDTH[t]:(i + 1) * WIDTH[t]]
        if t in (apl64.BOOL, apl64.CHAR):
            data.append(chunk[0])
        elif t == apl64.INT:
            v = chunk[0] | chunk[1] << 8
            data.append(v - 65536 if v >= 32768 else v)
        else:
            data.append(int.from_bytes(chunk, "big"))
    return apl64.Value(t, shape, data)


class _RawFunc:
    """A function block that failed the checks: kept as it was read."""

    def __init__(self, raw):
        self.raw = raw

    def block_bytes(self):
        n = len(self.raw).to_bytes(2, "little")
        return bytes([5]) + n + n + self.raw


def _line_valid(line, nsym):
    """One token stream of a function: every token known and whole, ending in the end mark."""
    i = ntok = 0
    while i < len(line):
        c = line[i]
        if c == 0:
            return i == len(line) - 1
        ntok += 1
        if ntok > 255:
            return False
        if c == 1:                                  # a literal: the heap layout of an array
            if i + 4 > len(line):
                return False
            tag, count = line[i + 1], line[i + 2] | line[i + 3] << 8
            t, rank = tag & 3, tag >> 2 & 3
            if tag & 0xF0 or rank == 3 or i + 4 + 2 * rank > len(line):
                return False
            dims = [line[i + 4 + 2 * k] | line[i + 5 + 2 * k] << 8 for k in range(rank)]
            if (rank == 0 and count != 1) or (rank == 1 and dims[0] != count) or \
                    (rank == 2 and dims[0] * dims[1] != count):
                return False
            i += 4 + 2 * rank + count * WIDTH[t]
            if i > len(line):
                return False
        elif c == 2:                                # a name
            if i + 2 > len(line) or line[i + 1] >= nsym:
                return False
            i += 2
        elif 3 <= c <= 10 or c >= 0x80:
            i += 1
        else:
            return False
    return False


def function_valid(d, nsym):
    """Is this block a function the evaluator can run (the 6502 checks the same things)?"""
    n = len(d)
    if n < 4 or d[0] > 2 or d[1] > 1 or d[2] < d[1] + d[0] or 4 + d[2] > n:
        return False
    if any(s >= nsym for s in d[4:4 + d[2]]):
        return False
    pos = 4 + d[2]
    for _ in range(d[3]):
        if pos + 2 > n:
            return False
        ln = d[pos] | d[pos + 1] << 8
        if ln < 1 or ln > MAX_LINE or pos + 2 + ln > n or not _line_valid(d[pos + 2:pos + 2 + ln], nsym):
            return False
        pos += 2 + ln
    return pos == n


def load(data):
    """Returns (status, interp): status is 'ok', 'notws', 'wsfull' or 'io'; interp is the workspace
    left behind, or None if the file was refused before the workspace was cleared."""
    if not data:                    # DOS gives one garbage byte with the end flag for an empty file
        return "notws", None
    r = _Reader(data)
    try:
        for want in MAGIC:
            if r.byte() != want:
                return "notws", None
    except _IO:
        return "io", None
    m = apl64.Interp()
    try:
        n = r.u16()
        while n:
            ln = r.byte()
            if ln == 0:
                return "notws", m
            text = "".join(INV.get(c, chr(c)) for c in r.take(ln))
            try:
                toks = m.decode(m.tokenize(text))
            except apl64.AplError:
                return "notws", m
            if len(toks) != 1 or toks[0][0] != 2:
                return "notws", m
            idx = toks[0][1]
            tag = r.byte()
            t, rank = tag & 3, tag >> 2 & 3
            if tag == UNDEFINED:                # a symbol with no value
                n -= 1
                continue
            if (tag & 0xF0 and tag != FUNCTION) or rank == 3:
                return "notws", m
            if rank == 0:
                m.vars[idx] = _value(t, 0, (), r.take(WIDTH[t]))
            else:
                count, d0 = r.u16(), r.u16()
                d1 = r.u16() if rank == 2 else 0
                if (count != d0) if rank == 1 else (d0 * d1 != count):
                    return "notws", m
                if count * WIDTH[t] > apl64.WS_BYTES:
                    return "wsfull", m
                shape = (d0,) if rank == 1 else (d0, d1)
                v = _value(t, rank, shape, r.take(count * WIDTH[t]))
                if tag == FUNCTION:
                    m.funcs[idx] = v            # checked below, once every symbol exists
                else:
                    m.vars[idx] = v
            n -= 1
        if r.byte() != ord("E"):
            return "notws", m
        bad = False
        for idx in sorted(m.funcs):
            raw = bytes(m.funcs[idx].data)
            if function_valid(raw, len(m.names)):
                m.funcs[idx] = apl64.Func.from_bytes(raw)
            else:
                m.funcs[idx] = _RawFunc(raw)            # left in the workspace, like the 6502 leaves it
                bad = True
        if bad:
            return "notws", m
    except _IO:
        return "io", m
    return "ok", m
