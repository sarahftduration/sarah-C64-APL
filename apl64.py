#!/usr/bin/env python3
"""
apl64.py -- bit-exact reference model for a tokenizing APL interpreter
targeting the Commodore 64.  The 6502 runtime is specified by this file.

Run the REPL:      python3 apl64.py
Run the self-test: python3 apl64.py --test

DESIGN SUMMARY
--------------
Element types (one type per array, no mixing):
    0 BOOL   1 byte    0 or 1
    1 CHAR   1 byte    8-bit code into the custom charset
    2 INT    2 bytes   signed 16-bit, little-endian
    3 FLOAT  3 bytes   float24, see below

float24 (3 bytes):
    byte 0: exponent, excess-128, 0 means the value zero
    byte 1: sign bit | top 7 bits of the stored fraction
    byte 2: low 8 bits of the stored fraction
    value = (-1)^s * (0x8000 | fraction15) / 2^16 * 2^(exp - 128)
    i.e. a 16-bit significand with a hidden leading 1, in [0.5, 1) * 2^(e-128).
    Range about 1.5e-39 .. 1.7e38.  Every int16 is exact.
    Add, sub, mul, div are correctly rounded (round-to-nearest-even), which
    the 6502 achieves with guard, round and sticky bits.
    Underflow flushes to zero.  Overflow is DOMAIN ERROR.  No NaN or Inf.

Comparison tolerance (floats only; int/int comparison is exact):
    a = b  iff  a == b, or a - b == 0, or
                exp(a - b) <= max(exp(a), exp(b)) - TOL_SHIFT
    which is cheap on a 6502 (one subtract plus an exponent compare).
    < <= > >= use that test and then an exact sign-magnitude compare.

Integer arithmetic (+ - x) is optimistic: run in int16, and if ANY result
element leaves int16, redo the whole primitive in float24.
"/" is reduce (right to left).  "+/" accumulates exactly and rounds once.
Division always gives FLOAT.  0 / 0 is 1; x / 0 is DOMAIN ERROR.
Origin is 1.  Rank <= 2.  Workspace is limited to WS_BYTES per array.

Token stream (bytes), one line ends with $00:
    $00 end   $01 literal   $02 name (1-byte symbol index)
    $03 (  $04 )  $05 [  $06 ]  $07 <-  $08 ->  $09 diamond  $0A ;
    $80+i primitive function, i indexing PRIM_GLYPHS
    $C0+i operator, i indexing OP_GLYPHS
Literal body is exactly the heap layout of an array:
    byte 0:    type | rank << 2
    bytes 1-2: element count (16-bit LE)
    then 2 bytes (LE) per axis, then the data.
The tokenizer folds number strands and character strings into one literal
and picks the narrowest numeric type.  Mixed strands are DOMAIN ERROR.

Not bit-exact against the 6502 (model is the spec, the 6502 may differ by
1 ulp): decimal parsing and decimal formatting.  Everything else is exact.
"""

import math
import random
import re
import sys
from fractions import Fraction


class AplError(Exception):
    def __init__(self, kind):
        super().__init__(kind)
        self.kind = kind


# =========================================================================
# float24
# =========================================================================
BIAS = 144          # value = M * 2^(e - BIAS), M in [2^15, 2^16)
TOL_SHIFT = 14
PP = 4              # print precision: 16-bit significand => 10^4 < 2^15, so a
                    # 4-digit decimal always survives parse -> float24 -> print


def _round_pack(sign, n, e2):
    """Pack (-1)^sign * n * 2^e2 (n > 0 an integer) as float24, RNE."""
    length = n.bit_length()
    if length > 16:
        sh = length - 16
        q = n >> sh
        rem = n & ((1 << sh) - 1)
        half = 1 << (sh - 1)
        if rem > half or (rem == half and (q & 1)):
            q += 1
            if q == 1 << 16:
                q >>= 1
                sh += 1
        e2 += sh
    else:
        q = n << (16 - length)
        e2 -= 16 - length
    e = e2 + BIAS
    if e < 1:
        return 0                      # underflow flushes to zero
    if e > 255:
        raise AplError('DOMAIN ERROR')  # overflow
    return (e << 16) | (sign << 15) | (q & 0x7FFF)


def _sme(p):
    """(sign, mantissa, e2) with value = +-mantissa * 2^e2, or None for zero."""
    e = p >> 16
    if e == 0:
        return None
    return (p >> 15) & 1, 0x8000 | (p & 0x7FFF), e - BIAS


def f_neg(p):
    return 0 if p >> 16 == 0 else p ^ 0x8000


def f_add(a, b):
    x, y = _sme(a), _sme(b)
    if x is None:
        return b
    if y is None:
        return a
    e2 = min(x[2], y[2])
    va = x[1] << (x[2] - e2)
    vb = y[1] << (y[2] - e2)
    s = (-va if x[0] else va) + (-vb if y[0] else vb)
    if s == 0:
        return 0
    return _round_pack(1 if s < 0 else 0, abs(s), e2)


def f_sub(a, b):
    return f_add(a, f_neg(b))


def f_mul(a, b):
    x, y = _sme(a), _sme(b)
    if x is None or y is None:
        return 0
    return _round_pack(x[0] ^ y[0], x[1] * y[1], x[2] + y[2])


def f_div(a, b):
    x, y = _sme(a), _sme(b)
    if y is None:
        raise AplError('DOMAIN ERROR')
    if x is None:
        return 0
    q, r = divmod(x[1] << 24, y[1])
    n = (q << 1) | (1 if r else 0)          # sticky bit
    return _round_pack(x[0] ^ y[0], n, x[2] - y[2] - 25)


def f_from_int(n):
    if n == 0:
        return 0
    return _round_pack(1 if n < 0 else 0, abs(n), 0)


def f_from_fraction(x):
    if x == 0:
        return 0
    sign = 1 if x < 0 else 0
    x = abs(x)
    num, den = x.numerator, x.denominator
    k = max(0, 18 + den.bit_length() - num.bit_length())
    q, r = divmod(num << k, den)
    return _round_pack(sign, (q << 1) | (1 if r else 0), -k - 1)


def f_to_fraction(p):
    t = _sme(p)
    if t is None:
        return Fraction(0)
    v = Fraction(t[1]) * Fraction(2) ** t[2]
    return -v if t[0] else v


def f_whole(p):
    """The integer value if p is whole, else None."""
    x = f_to_fraction(p)
    return int(x) if x.denominator == 1 else None


def f_sum(ps):
    """Exact sum rounded once (the +/ wide accumulator)."""
    parts = [_sme(p) for p in ps if p >> 16]
    if not parts:
        return 0
    e2 = min(t[2] for t in parts)
    s = sum((-1 if t[0] else 1) * (t[1] << (t[2] - e2)) for t in parts)
    if s == 0:
        return 0
    return _round_pack(1 if s < 0 else 0, abs(s), e2)


def _fkey(p):
    if p >> 16 == 0:
        return 0
    mag = p & 0xFF7FFF
    return -mag if p & 0x8000 else mag


def f_teq(a, b):
    if a == b:
        return True
    d = f_sub(a, b)
    if d == 0:
        return True
    return (d >> 16) <= max(a >> 16, b >> 16) - TOL_SHIFT


def f_lt(a, b):
    return (not f_teq(a, b)) and _fkey(a) < _fkey(b)


def f_le(a, b):
    return f_teq(a, b) or _fkey(a) < _fkey(b)


def f_gt(a, b):
    return f_lt(b, a)


def f_ge(a, b):
    return f_le(b, a)


ONE = f_from_int(1)


NUM_RE = re.compile(r'¯?(?:\d+\.?\d*|\.\d+)(?:[eE]¯?\d+)?')


def parse_number(s):
    neg = s.startswith('¯')
    if neg:
        s = s[1:]
    mant, _, ex = s.lower().partition('e')
    ip, _, fp = mant.partition('.')
    val = Fraction(int((ip + fp) or '0'), 10 ** len(fp))
    if ex:
        e = int(ex.replace('¯', '-'))
        if val != 0 and abs(e) > 400:
            if e > 0:
                raise AplError('DOMAIN ERROR')
            return Fraction(0)
        val *= Fraction(10) ** e
    return -val if neg else val


def f_format(p, pp=None):
    pp = pp or PP
    x = f_to_fraction(p)
    if x == 0:
        return '0'
    if x.denominator == 1 and abs(x) <= 65536:
        return str(int(x)).replace('-', '¯')   # exact: every bit is meaningful
    neg = x < 0
    x = abs(x)
    k = int(math.floor(math.log10(float(x))))
    while Fraction(10) ** k > x:
        k -= 1
    while Fraction(10) ** (k + 1) <= x:
        k += 1
    digits = int(x / Fraction(10) ** (k - pp + 1) + Fraction(1, 2))
    if digits >= 10 ** pp:
        digits = 10 ** (pp - 1)
        k += 1
    ds = str(digits).rstrip('0')
    if -5 <= k <= 9:
        if k >= 0:
            if len(ds) <= k + 1:
                s = ds + '0' * (k + 1 - len(ds))
            else:
                s = ds[:k + 1] + '.' + ds[k + 1:]
        else:
            s = '0.' + '0' * (-k - 1) + ds
    else:
        s = ds[0] + ('.' + ds[1:] if len(ds) > 1 else '')
        s += 'E' + ('¯' + str(-k) if k < 0 else str(k))
    return ('¯' if neg else '') + s


# =========================================================================
# Values
# =========================================================================
BOOL, CHAR, INT, FLOAT = 0, 1, 2, 3
WIDTH = (1, 1, 2, 3)
LADDER = {BOOL: 0, INT: 1, FLOAT: 2}
FILL = {BOOL: 0, CHAR: 32, INT: 0, FLOAT: 0}
WS_BYTES = 45000


def check_size(t, n):
    if n > 65535 or n * WIDTH[t] > WS_BYTES:
        raise AplError('WS FULL')


class Value:
    def __init__(self, t, shape, data):
        self.t = t
        self.shape = tuple(shape)
        self.data = list(data)
        n = 1
        for s in self.shape:
            n *= s
        assert n == len(self.data), (self.shape, len(self.data))
        check_size(t, n)

    @property
    def rank(self):
        return len(self.shape)

    @property
    def count(self):
        return len(self.data)

    def to_bytes(self):
        out = bytearray([self.t | (self.rank << 2)])
        out += self.count.to_bytes(2, 'little')
        for s in self.shape:
            out += s.to_bytes(2, 'little')
        for x in self.data:
            if self.t in (BOOL, CHAR):
                out.append(x)
            elif self.t == INT:
                out += (x & 0xFFFF).to_bytes(2, 'little')
            else:
                out += x.to_bytes(3, 'big')     # exp, sign|hi7, lo8
        return bytes(out)

    @staticmethod
    def from_bytes(buf, pos):
        t = buf[pos] & 3
        rank = buf[pos] >> 2
        count = buf[pos + 1] | (buf[pos + 2] << 8)
        pos += 3
        shape = []
        for _ in range(rank):
            shape.append(buf[pos] | (buf[pos + 1] << 8))
            pos += 2
        data = []
        for _ in range(count):
            if t in (BOOL, CHAR):
                data.append(buf[pos])
            elif t == INT:
                v = buf[pos] | (buf[pos + 1] << 8)
                data.append(v - 65536 if v >= 32768 else v)
            else:
                data.append(int.from_bytes(buf[pos:pos + 3], 'big'))
            pos += WIDTH[t]
        return Value(t, shape, data), pos

    def __eq__(self, o):
        return (self.t, self.shape, self.data) == (o.t, o.shape, o.data)

    def __repr__(self):
        return 'Value(%s, %s, %s)' % (('BOOL', 'CHAR', 'INT', 'FLOAT')[self.t],
                                      self.shape, self.data)


def scalar(t, x):
    return Value(t, (), [x])


def vector(t, xs):
    return Value(t, (len(xs),), xs)


def join_type(ta, tb):
    if ta == tb:
        return ta
    if CHAR in (ta, tb):
        raise AplError('DOMAIN ERROR')
    return ta if LADDER[ta] > LADDER[tb] else tb


def convert(tf, tt, x):
    if tf == tt:
        return x
    if CHAR in (tf, tt):
        raise AplError('DOMAIN ERROR')
    if tt == FLOAT:
        return f_from_int(x)
    return x                     # BOOL -> INT


def to_f(t, x):
    return x if t == FLOAT else f_from_int(x)


def to_ints(v):
    if v.rank > 1:
        raise AplError('RANK ERROR')
    out = []
    for x in v.data:
        if v.t in (BOOL, INT):
            out.append(x)
        elif v.t == FLOAT:
            n = f_whole(x)
            if n is None:
                raise AplError('DOMAIN ERROR')
            out.append(n)
        else:
            raise AplError('DOMAIN ERROR')
    return out


# =========================================================================
# Scalar functions
# =========================================================================
def conform(a, b):
    if a.shape == b.shape:
        return a.shape, a.data, b.data
    if a.rank == 0:
        return b.shape, a.data * b.count, b.data
    if b.rank == 0:
        return a.shape, a.data, b.data * a.count
    if a.rank != b.rank:
        raise AplError('RANK ERROR')
    raise AplError('LENGTH ERROR')


def monadic_scalar(fn, v):
    t, data = fn(v.t, v.data)
    return Value(t, v.shape, data)


def dyadic_scalar(fn, a, b):
    shape, xs, ys = conform(a, b)
    t, data = fn(a.t, xs, b.t, ys)
    return Value(t, shape, data)


def _in16(v):
    return -32768 <= v <= 32767


def _arith(name):
    iop = {'+': lambda x, y: x + y, '-': lambda x, y: x - y,
           '×': lambda x, y: x * y}[name]
    fop = {'+': f_add, '-': f_sub, '×': f_mul}[name]

    def run(ta, xs, tb, ys):
        if ta == CHAR or tb == CHAR:
            raise AplError('DOMAIN ERROR')
        if ta != FLOAT and tb != FLOAT:
            out = [iop(x, y) for x, y in zip(xs, ys)]
            if all(_in16(v) for v in out):
                return INT, out
            # overflow: redo everything in float
        return FLOAT, [fop(to_f(ta, x), to_f(tb, y)) for x, y in zip(xs, ys)]
    return run


def _div(ta, xs, tb, ys):
    if ta == CHAR or tb == CHAR:
        raise AplError('DOMAIN ERROR')
    out = []
    for x, y in zip(xs, ys):
        fx, fy = to_f(ta, x), to_f(tb, y)
        if fy == 0:
            if fx != 0:
                raise AplError('DOMAIN ERROR')
            out.append(ONE)                    # 0 / 0 is 1
        else:
            out.append(f_div(fx, fy))
    return FLOAT, out


_INT_CMP = {'=': lambda x, y: x == y, '≠': lambda x, y: x != y,
            '<': lambda x, y: x < y, '≤': lambda x, y: x <= y,
            '>': lambda x, y: x > y, '≥': lambda x, y: x >= y}
_F_CMP = {'=': f_teq, '≠': lambda a, b: not f_teq(a, b),
          '<': f_lt, '≤': f_le, '>': f_gt, '≥': f_ge}


def _cmp(name):
    def run(ta, xs, tb, ys):
        if ta == CHAR or tb == CHAR:
            if name not in ('=', '≠'):
                raise AplError('DOMAIN ERROR')
            eq = [ta == tb and x == y for x, y in zip(xs, ys)]
            return BOOL, [int(e if name == '=' else not e) for e in eq]
        if ta == FLOAT or tb == FLOAT:
            f = _F_CMP[name]
            return BOOL, [int(f(to_f(ta, x), to_f(tb, y))) for x, y in zip(xs, ys)]
        f = _INT_CMP[name]
        return BOOL, [int(f(x, y)) for x, y in zip(xs, ys)]
    return run


def _m_id(t, xs):
    if t == CHAR:
        raise AplError('DOMAIN ERROR')
    return t, list(xs)


def _m_neg(t, xs):
    if t == CHAR:
        raise AplError('DOMAIN ERROR')
    if t == FLOAT:
        return FLOAT, [f_neg(x) for x in xs]
    out = [-x for x in xs]
    if all(_in16(v) for v in out):
        return INT, out
    return FLOAT, [f_from_int(v) for v in out]


def _m_sign(t, xs):
    if t == CHAR:
        raise AplError('DOMAIN ERROR')
    if t == FLOAT:
        return INT, [0 if x >> 16 == 0 else (-1 if x & 0x8000 else 1) for x in xs]
    return INT, [(x > 0) - (x < 0) for x in xs]


def _m_recip(t, xs):
    return _div(INT, [1] * len(xs), t, xs)


def _nonce(*_):
    raise AplError('NONCE ERROR')


SCALAR_DYADIC = '+-×÷=≠<≤>≥'
_DY = {'+': _arith('+'), '-': _arith('-'), '×': _arith('×'), '÷': _div}
for _g in '=≠<≤>≥':
    _DY[_g] = _cmp(_g)
_MON = {'+': _m_id, '-': _m_neg, '×': _m_sign, '÷': _m_recip}


# =========================================================================
# Structural primitives
# =========================================================================
def iota(v):
    xs = to_ints(v)
    if len(xs) != 1:
        raise AplError('LENGTH ERROR')
    n = xs[0]
    if n < 0 or n > 32767:
        raise AplError('DOMAIN ERROR')
    check_size(INT, n)
    return vector(INT, list(range(1, n + 1)))


def shape_of(v):
    return vector(INT, list(v.shape))


def reshape(a, b):
    dims = to_ints(a)
    if len(dims) > 2:
        raise AplError('LIMIT ERROR')
    if any(d < 0 for d in dims):
        raise AplError('DOMAIN ERROR')
    n = 1
    for d in dims:
        n *= d
    check_size(b.t, n)
    if n == 0:
        data = []
    else:
        src = b.data or [FILL[b.t]]
        data = [src[k % len(src)] for k in range(n)]
    return Value(b.t, tuple(dims), data)


def ravel(v):
    return vector(v.t, v.data)


def catenate(a, b):
    if a.rank > 1 or b.rank > 1:
        raise AplError('NONCE ERROR')
    if a.count == 0:
        t = b.t
    elif b.count == 0:
        t = a.t
    else:
        t = join_type(a.t, b.t)
    data = ([convert(a.t, t, x) for x in a.data] +
            [convert(b.t, t, x) for x in b.data])
    return vector(t, data)


# =========================================================================
# Reduce
# =========================================================================
_IDENT = {'+': (INT, 0), '-': (INT, 0), '×': (INT, 1), '÷': (FLOAT, ONE),
          '=': (BOOL, 1), '≠': (BOOL, 0), '<': (BOOL, 0), '≤': (BOOL, 1),
          '>': (BOOL, 0), '≥': (BOOL, 1)}


def _reduce_row(glyph, dy, t, xs):
    if not xs:
        it, iv = _IDENT[glyph]
        return scalar(it, iv)
    if glyph == '+':
        if t == CHAR:
            raise AplError('DOMAIN ERROR')
        if t == FLOAT:
            return scalar(FLOAT, f_sum(xs))
        s = sum(xs)
        return scalar(INT, s) if _in16(s) else scalar(FLOAT, f_from_int(s))
    if len(xs) == 1:
        if glyph in '-×÷' and t == CHAR:
            raise AplError('DOMAIN ERROR')
        if glyph == '÷' and t != FLOAT:
            return scalar(FLOAT, f_from_int(xs[0]))
        if glyph in '-×' and t == BOOL:
            return scalar(INT, xs[0])
        return scalar(t, xs[0])
    acc = scalar(t, xs[-1])
    for x in reversed(xs[:-1]):
        acc = dy(scalar(t, x), acc)
    return acc


def make_reduce(glyph):
    dy = PRIMS[glyph][1]

    def red(v):
        if v.rank == 0:
            return v
        n = v.shape[-1]
        lead = v.shape[0] if v.rank == 2 else 1
        rows = [_reduce_row(glyph, dy, v.t, v.data[r * n:(r + 1) * n])
                for r in range(lead)]
        t = rows[0].t
        for r in rows[1:]:
            t = join_type(t, r.t)
        data = [convert(r.t, t, r.data[0]) for r in rows]
        return Value(t, v.shape[:-1], data)
    return red


PRIMS = {}
for _g in SCALAR_DYADIC:
    _m = _MON.get(_g)
    PRIMS[_g] = (
        (lambda f: (lambda v: monadic_scalar(f, v)))(_m) if _m else _nonce,
        (lambda f: (lambda a, b: dyadic_scalar(f, a, b)))(_DY[_g]))
PRIMS['⍳'] = (iota, _nonce)
PRIMS['⍴'] = (shape_of, reshape)
PRIMS[','] = (ravel, catenate)


# =========================================================================
# Output formatting
# =========================================================================
def fmt_elem(t, x):
    if t in (BOOL, INT):
        return str(x).replace('-', '¯')
    return f_format(x)


def format_value(v):
    if v.t == CHAR:
        if v.rank == 0:
            return chr(v.data[0])
        if v.rank == 1:
            return ''.join(map(chr, v.data))
        r, c = v.shape
        return '\n'.join(''.join(map(chr, v.data[i * c:(i + 1) * c]))
                         for i in range(r))
    strs = [fmt_elem(v.t, x) for x in v.data]
    if v.rank <= 1:
        return ' '.join(strs)
    r, c = v.shape
    if c == 0:
        return '\n'.join('' for _ in range(r))
    widths = [max(len(strs[i * c + j]) for i in range(r)) for j in range(c)]
    return '\n'.join(' '.join(strs[i * c + j].rjust(widths[j]) for j in range(c))
                     for i in range(r))


# =========================================================================
# Tokenizer and evaluator
# =========================================================================
T_END, T_LIT, T_NAME = 0, 1, 2
T_LPAR, T_RPAR, T_LBRK, T_RBRK, T_ASSIGN, T_BRANCH, T_DIAMOND, T_SEMI = range(3, 11)
SYNTAX_TOKENS = {'(': T_LPAR, ')': T_RPAR, '[': T_LBRK, ']': T_RBRK,
                 '←': T_ASSIGN, '→': T_BRANCH, '⋄': T_DIAMOND, ';': T_SEMI}
PRIM_GLYPHS = '+-×÷=≠<≤>≥⍳⍴,'
OP_GLYPHS = '/\\¨.∘⍤'
NAME_RE = re.compile(r'[A-Za-z_∆⍙][A-Za-z0-9_∆⍙]*')


def _is_value_tok(c):
    return c in (T_LIT, T_NAME, T_RPAR)


def _skip_ws(line, i):
    while i < len(line) and line[i] in ' \t':
        i += 1
    return i


def _starts_number(line, i):
    if i >= len(line):
        return False
    c = line[i]
    return (c == '¯' or c.isdigit() or
            (c == '.' and i + 1 < len(line) and line[i + 1].isdigit()))


def literal_from_numbers(vals):
    if all(v.denominator == 1 and _in16(v) for v in vals):
        t = BOOL if all(v in (0, 1) for v in vals) else INT
        data = [int(v) for v in vals]
    else:
        t = FLOAT
        data = [f_from_fraction(v) for v in vals]
    return scalar(t, data[0]) if len(data) == 1 else vector(t, data)


class Interp:
    def __init__(self):
        self.names = []
        self.index = {}
        self.vars = {}

    # ---- tokenizer -------------------------------------------------------
    def name_index(self, nm):
        if nm not in self.index:
            if len(self.names) >= 256:
                raise AplError('LIMIT ERROR')
            self.index[nm] = len(self.names)
            self.names.append(nm)
        return self.index[nm]

    def tokenize(self, line):
        out = bytearray()
        i, n = 0, len(line)
        while i < n:
            c = line[i]
            if c in ' \t':
                i += 1
            elif c == '⍝':
                break
            elif c == "'":
                chars = []
                j = i + 1
                while True:
                    if j >= n:
                        raise AplError('SYNTAX ERROR')
                    if line[j] == "'":
                        if j + 1 < n and line[j + 1] == "'":
                            chars.append("'")
                            j += 2
                            continue
                        break
                    chars.append(line[j])
                    j += 1
                i = j + 1
                if any(ord(ch) > 255 for ch in chars):
                    raise AplError('DOMAIN ERROR')
                codes = [ord(ch) for ch in chars]
                v = scalar(CHAR, codes[0]) if len(codes) == 1 else vector(CHAR, codes)
                out.append(T_LIT)
                out += v.to_bytes()
                k = _skip_ws(line, i)
                if k < n and (line[k] == "'" or _starts_number(line, k)):
                    raise AplError('DOMAIN ERROR')      # mixed / nested strand
            elif _starts_number(line, i):
                vals = []
                while True:
                    m = NUM_RE.match(line, i)
                    if not m:
                        raise AplError('SYNTAX ERROR')
                    vals.append(parse_number(m.group()))
                    i = m.end()
                    k = _skip_ws(line, i)
                    if k < n and _starts_number(line, k):
                        i = k
                        continue
                    if k < n and line[k] == "'":
                        raise AplError('DOMAIN ERROR')  # mixed strand
                    break
                out.append(T_LIT)
                out += literal_from_numbers(vals).to_bytes()
            elif c == '⍬':
                out.append(T_LIT)
                out += vector(INT, []).to_bytes()
                i += 1
            elif NAME_RE.match(line, i):
                m = NAME_RE.match(line, i)
                out += bytes([T_NAME, self.name_index(m.group())])
                i = m.end()
            elif c in SYNTAX_TOKENS:
                out.append(SYNTAX_TOKENS[c])
                i += 1
            elif c in PRIM_GLYPHS:
                out.append(0x80 + PRIM_GLYPHS.index(c))
                i += 1
            elif c in OP_GLYPHS:
                out.append(0xC0 + OP_GLYPHS.index(c))
                i += 1
            else:
                raise AplError('SYNTAX ERROR')
        out.append(T_END)
        return bytes(out)

    @staticmethod
    def decode(buf):
        toks, i = [], 0
        while True:
            c = buf[i]
            i += 1
            if c == T_END:
                return toks
            if c == T_LIT:
                v, i = Value.from_bytes(buf, i)
                toks.append((c, v))
            elif c == T_NAME:
                toks.append((c, buf[i]))
                i += 1
            else:
                toks.append((c, None))

    # ---- evaluator (right to left) --------------------------------------
    def lookup(self, idx):
        if idx not in self.vars:
            raise AplError('VALUE ERROR')
        return self.vars[idx]

    def _operand(self, toks, i):
        c, arg = toks[i]
        if c == T_LIT:
            return arg, i - 1
        if c == T_NAME:
            return self.lookup(arg), i - 1
        depth, j = 0, i
        while j >= 0:
            cj = toks[j][0]
            if cj == T_RPAR:
                depth += 1
            elif cj == T_LPAR:
                depth -= 1
                if depth == 0:
                    break
            j -= 1
        if j < 0 or j + 1 >= i:
            raise AplError('SYNTAX ERROR')
        return self.eval_tokens(toks[j + 1:i]), j - 1

    def eval_tokens(self, toks):
        if any(c in (T_LBRK, T_RBRK, T_BRANCH, T_SEMI) for c, _ in toks):
            raise AplError('NONCE ERROR')
        i = len(toks) - 1
        if i < 0 or not _is_value_tok(toks[i][0]):
            raise AplError('SYNTAX ERROR')
        val, i = self._operand(toks, i)
        while i >= 0:
            c = toks[i][0]
            if c == T_ASSIGN:
                if i == 0 or toks[i - 1][0] != T_NAME:
                    raise AplError('SYNTAX ERROR')
                self.vars[toks[i - 1][1]] = val
                i -= 2
            elif c >= 0xC0:
                if i == 0:
                    raise AplError('SYNTAX ERROR')
                pc = toks[i - 1][0]
                if _is_value_tok(pc):
                    raise AplError('NONCE ERROR')       # replicate / compress
                if not 0x80 <= pc < 0xC0:
                    raise AplError('SYNTAX ERROR')
                g = OP_GLYPHS[c - 0xC0]
                pg = PRIM_GLYPHS[pc - 0x80]
                if g != '/' or pg not in SCALAR_DYADIC:
                    raise AplError('NONCE ERROR')
                fn = (make_reduce(pg), _nonce)
                i -= 2
                val = self._apply(fn, toks, i, val)
                i = self._pos
            elif c >= 0x80:
                fn = PRIMS[PRIM_GLYPHS[c - 0x80]]
                i -= 1
                val = self._apply(fn, toks, i, val)
                i = self._pos
            else:
                raise AplError('SYNTAX ERROR')
        return val

    def _apply(self, fn, toks, i, right):
        """Apply fn monadically or dyadically; leaves new index in self._pos."""
        if i >= 0 and _is_value_tok(toks[i][0]):
            left, i = self._operand(toks, i)
            self._pos = i
            return fn[1](left, right)
        self._pos = i
        return fn[0](right)

    def run_line(self, line):
        toks = self.decode(self.tokenize(line))
        stmts, cur, depth = [], [], 0
        for tk in toks:
            if tk[0] == T_LPAR:
                depth += 1
            elif tk[0] == T_RPAR:
                depth -= 1
                if depth < 0:
                    raise AplError('SYNTAX ERROR')
            if tk[0] == T_DIAMOND and depth == 0:
                stmts.append(cur)
                cur = []
            else:
                cur.append(tk)
        stmts.append(cur)
        if depth != 0:
            raise AplError('SYNTAX ERROR')
        outs = []
        for st in stmts:
            if not st:
                continue
            val = self.eval_tokens(st)
            if not (len(st) >= 2 and st[0][0] == T_NAME and st[1][0] == T_ASSIGN):
                outs.append(format_value(val))
        return outs


# =========================================================================
# REPL
# =========================================================================
def repl():
    ws = Interp()
    while True:
        try:
            line = input('      ')
        except EOFError:
            break
        try:
            for o in ws.run_line(line):
                print(o)
        except AplError as e:
            print(e.kind)
            print('      ' + line)


# =========================================================================
# Self-test
# =========================================================================
def _ref_round(x):
    """Independent correctly-rounded float24 of an exact Fraction."""
    if x == 0:
        return 0
    s = 1 if x < 0 else 0
    a = abs(x)
    e = a.numerator.bit_length() - a.denominator.bit_length()
    while a >= Fraction(2) ** e:
        e += 1
    while a < Fraction(2) ** (e - 1):
        e -= 1
    m = round(a / Fraction(2) ** e * 65536)          # half-even
    if m == 65536:
        m, e = 32768, e + 1
    ef = e + 128
    if ef < 1:
        return 0
    if ef > 255:
        raise AplError('DOMAIN ERROR')
    return (ef << 16) | (s << 15) | (m & 0x7FFF)


def _try(f):
    try:
        return f()
    except AplError as e:
        return e.kind


def _rand_f(rng, emin, emax):
    return (rng.randint(emin, emax) << 16) | (rng.randint(0, 1) << 15) | rng.randint(0, 0x7FFF)


def selftest():
    rng = random.Random(64)
    n = 0

    # int16 <-> float24 is exact
    for i in range(-32768, 32768):
        assert f_whole(f_from_int(i)) == i, i
    n += 1

    # arithmetic is correctly rounded, including near overflow and underflow
    ops = [(f_add, lambda a, b: a + b), (f_sub, lambda a, b: a - b),
           (f_mul, lambda a, b: a * b), (f_div, lambda a, b: a / b)]
    for lo, hi, count in ((100, 160, 4000), (1, 255, 4000), (120, 136, 4000)):
        for _ in range(count):
            a, b = _rand_f(rng, lo, hi), _rand_f(rng, lo, hi)
            fa, fb = f_to_fraction(a), f_to_fraction(b)
            for fop, xop in ops:
                got = _try(lambda: fop(a, b))
                want = _try(lambda: _ref_round(xop(fa, fb)))
                assert got == want, (fop.__name__, hex(a), hex(b), got, want)
    n += 1

    # agreement with IEEE doubles to within one unit of the 16-bit significand
    for _ in range(3000):
        a, b = _rand_f(rng, 110, 150), _rand_f(rng, 110, 150)
        da, db = float(f_to_fraction(a)), float(f_to_fraction(b))
        for fop, dop in ((f_add, da + db), (f_mul, da * db), (f_div, da / db)):
            r = float(f_to_fraction(fop(a, b)))
            assert abs(r - dop) <= abs(dop) * 2 ** -16 or r == 0, (fop.__name__, a, b)
    n += 1

    # exact sum rounds once
    ps = [f_from_fraction(Fraction(1, 10)) for _ in range(100)]
    assert abs(float(f_to_fraction(f_sum(ps))) - 10.0) < 1e-3
    n += 1

    # tolerance rule
    one = f_from_int(1)
    assert f_teq(one, f_add(one, f_from_fraction(Fraction(1, 2 ** 15))))
    assert not f_teq(one, f_from_fraction(Fraction(1001, 1000)))
    assert not f_teq(0, f_from_fraction(Fraction(1, 10 ** 30)))
    assert f_lt(f_from_int(1), f_from_int(2)) and not f_lt(one, f_neg(one))
    assert not f_lt(one, f_add(one, f_from_fraction(Fraction(1, 2 ** 15))))
    n += 1

    # bytes: token stream, heap layout, float24 layout
    ws = Interp()
    assert ws.tokenize('1 2 3') == bytes.fromhex('01 06 0300 0300 0100 0200 0300 00')
    v = Interp().decode(Interp().tokenize('÷3'))
    assert v[0][0] == 0x83
    assert ws.eval_tokens(ws.decode(ws.tokenize('1÷3'))).to_bytes() == \
        bytes.fromhex('03 0100 7f2aab')
    n += 1

    # APL expressions: (source, expected output lines joined by | ) or !ERROR
    cases = [
        ('1 2 3+4 5 6', '5 7 9'),
        ('⍳5', '1 2 3 4 5'),
        ('⍳0', ''),
        ('+/⍳100', '5050'),
        ('+/⍳300', '45150'),
        ('×/⍳8', '40320'),
        ('-/1 2 3', '2'),
        ('÷3', '0.3333'),
        ('2÷3', '0.6667'),
        ('10÷4', '2.5'),
        ('0÷0', '1'),
        ('1÷0', '!DOMAIN ERROR'),
        ('0.1+0.2', '0.3'),
        ('1E10', '1E10'),
        ('1E¯3', '0.001'),
        ('10000×10', '100000'),
        ('¯5', '¯5'),
        ('×¯3 0 2', '¯1 0 1'),
        ('-1 2', '¯1 ¯2'),
        ('3 4⍴⍳12', '1  2  3  4|5  6  7  8|9 10 11 12'),
        ('⍴3 4⍴⍳12', '3 4'),
        ('⍴5', ''),
        ('+/3 3⍴⍳9', '6 15 24'),
        ('⍳3 ⋄ ⍳2', '1 2 3|1 2'),
        ('(⍳3),⍳2', '1 2 3 1 2'),
        ('2 3⍴1 2', '1 2 1|2 1 2'),
        ('1 2 3=1 5 3', '1 0 1'),
        ("'abc'='abd'", '1 1 0'),
        ("'a'=97", '0'),
        ('1.00001=1', '1'),
        ('3≥2', '1'),
        ("'hello'", 'hello'),
        ("'it''s'", "it's"),
        ('+/⍬', '0'),
        ('×/⍬', '1'),
        ('⍴⍬', '0'),
        ('A←⍳4 ⋄ +/A×A', '30'),
        ('A←⍳4', ''),
        ('1+A←2', '3'),
        ("1 'a'", '!DOMAIN ERROR'),
        ("'a',1", '!DOMAIN ERROR'),
        ("+/'abc'", '!DOMAIN ERROR'),
        ('1 2 3+4 5', '!LENGTH ERROR'),
        ('⍳30000', '!WS FULL'),
        ('QQ', '!VALUE ERROR'),
        ('1 2 3 4', '1 2 3 4'),
        ('(1+2', '!SYNTAX ERROR'),
        ('2/3', '!NONCE ERROR'),
        ('⍳¯1', '!DOMAIN ERROR'),
    ]
    ws = Interp()
    for src, want in cases:
        got = _try(lambda: '|'.join(ws.run_line(src)).replace('\n', '|'))
        if want.startswith('!'):
            want = want[1:]
        assert got == want, (src, got, want)
    n += 1

    # result types follow the rules
    def typ(src):
        return ws.eval_tokens(ws.decode(ws.tokenize(src))).t
    assert typ('1 0 1') == BOOL and typ('1 2 3') == INT and typ('1.5') == FLOAT
    assert typ('32767+1') == FLOAT and typ('32766+1') == INT
    assert typ('1+1') == INT and typ('1 1=1 0') == BOOL and typ('÷2') == FLOAT
    assert typ('+/1 1 1') == INT and typ('⍳5') == INT
    n += 1

    print('all %d test groups passed' % n)


if __name__ == '__main__':
    if '--test' in sys.argv:
        selftest()
    else:
        repl()
