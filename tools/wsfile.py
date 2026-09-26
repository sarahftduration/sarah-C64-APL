"""Workspace files (DESIGN.md, Workspace files): the encoder, and a decoder that follows the 6502
loader step for step, including the partial workspace a failed load leaves behind."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import apl64

MAGIC = b"APLW" + bytes([3])
UNDEFINED = 0x80
FUNCTION = 0x15               # a function: the tag of a CHAR vector, plus $10
WIDTH = (1, 1, 2, 3)
INV = {v: k for k, v in apl64.GLYPH_CODES.items()}


def value_bytes(v):
    """A scalar is its tag and data; an array is the heap layout (tag, count, lengths, data)."""
    b = v.to_bytes()
    return bytes([b[0]]) + b[3:] if v.rank == 0 else b


def checksum(d):
    """Of a function's data: for each byte, add it, then rotate the 16 bits left."""
    c = 0
    for b in d:
        c = (c + b) & 0xFFFF
        c = ((c << 1) | (c >> 15)) & 0xFFFF
    return c


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
            out += bytes([FUNCTION]) + b[1:] + checksum(b[5:]).to_bytes(2, "little")
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
                raw = r.take(count * WIDTH[t])
                v = _value(t, rank, shape, raw)
                if tag == FUNCTION:
                    if r.u16() != checksum(raw):        # (a damaged function is not stored)
                        return "notws", m
                    m.funcs[idx] = apl64.Func.from_bytes(raw)
                else:
                    m.vars[idx] = v
            n -= 1
        if r.byte() != ord("E"):
            return "notws", m
    except _IO:
        return "io", m
    return "ok", m
