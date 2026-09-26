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
Origin is 1.  Rank <= 2.  Indexing A[i] and A[i;j] (the
result shape is the index shapes joined; a result of rank 3 or more is
LIMIT ERROR; a bad index value is INDEX ERROR); indices are evaluated right
to left, then the indexed array.  Indexed assignment A[i]<-v makes a new array (index_assign).  Workspace is limited to WS_BYTES per array.

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
WS_BYTES = 16000


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


def to_ints(v, any_rank=False):
    if v.rank > 1 and not any_rank:
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


def _resolve_index(a, idxs):
    """Check the indices against a and return the 0-based positions along each
    axis and the shape of the selection.  idxs has one entry per axis of a,
    each a Value or None (elided: the whole axis).  The selection's shape is
    the shapes of the indices joined in axis order (an elided axis contributes
    its length, a scalar index contributes nothing); rank above 2 is LIMIT
    ERROR.  Checks run in this order: axis count (RANK), then per axis left to
    right the index type (DOMAIN) and range (INDEX), then the rank (LIMIT)."""
    if len(idxs) != a.rank:
        raise AplError('RANK ERROR')
    axes, shape = [], ()
    for dim, ix in zip(a.shape, idxs):
        if ix is None:
            axes.append(list(range(dim)))
            shape += (dim,)
            continue
        xs = to_ints(ix, any_rank=True)
        if any(x < 1 or x > dim for x in xs):
            raise AplError('INDEX ERROR')
        axes.append([x - 1 for x in xs])
        shape += ix.shape
    if len(shape) > 2:
        raise AplError('LIMIT ERROR')
    return axes, shape


def _positions(a, axes):
    """Element numbers of the selection, in row-major order of the selection."""
    if a.rank == 1:
        return axes[0]
    n = a.shape[1]
    return [r * n + c for r in axes[0] for c in axes[1]]


def index_value(a, idxs):
    """A[i] and A[i;j] (origin 1); the result has the type of a."""
    axes, shape = _resolve_index(a, idxs)
    return Value(a.t, shape, [a.data[p] for p in _positions(a, axes)])


def index_assign(a, idxs, v):
    """A[i]<-v: a new array (arrays are values; other names keep the old one).
    v is a scalar or has exactly the shape of the selection (RANK ERROR if its
    rank differs, else LENGTH ERROR).  The type is the join of both types
    (DOMAIN ERROR mixing characters and numbers, unless the selection is
    empty, which changes nothing).  With repeated indices the last write wins."""
    axes, shape = _resolve_index(a, idxs)
    if v.rank != 0:
        if v.rank != len(shape):
            raise AplError('RANK ERROR')
        if v.shape != shape:
            raise AplError('LENGTH ERROR')
    pos = _positions(a, axes)
    if not pos:
        return a
    t = join_type(a.t, v.t)
    data = [convert(a.t, t, x) for x in a.data]
    vals = v.data * len(pos) if v.rank == 0 else v.data
    for p, x in zip(pos, vals):
        data[p] = convert(v.t, t, x)
    return Value(t, a.shape, data)


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
# Charset codes for the non-ASCII glyphs; ASCII characters keep their ASCII code.
# The 6502 tokenizer receives lines in this encoding. Glyphs that are also
# tokens use their token code.
GLYPH_CODES = {'×': 0x82, '÷': 0x83, '≠': 0x85, '≤': 0x87, '≥': 0x89,
               '⍳': 0x8A, '⍴': 0x8B, '¨': 0xC2, '∘': 0xC4, '⍤': 0xC5,
               '¯': 0x90, '←': 0x91, '→': 0x92, '⋄': 0x93, '⍬': 0x94,
               '⍝': 0x95, '∆': 0x96, '⍙': 0x97, '∇': 0x98}


def char_code(ch):
    if ord(ch) < 128:
        return ord(ch)
    if ch in GLYPH_CODES:
        return GLYPH_CODES[ch]
    raise AplError('DOMAIN ERROR')


def encode_line(line):
    return bytes(char_code(c) for c in line)


NAME_RE = re.compile(r'[A-Za-z_∆⍙][A-Za-z0-9_∆⍙]*')
LABEL_RE = re.compile(r'[ \t]*[A-Za-z_∆⍙][A-Za-z0-9_∆⍙]*:')


MAX_DEPTH = 16          # nested calls of user-defined functions
MAX_LINES = 255         # lines in a function


class _Jump(Exception):
    """A branch: the number of the line to go on with (checked by the call)."""

    def __init__(self, line):
        super().__init__(line)
        self.line = line


class Func:
    """A user-defined function: nargs 0/1/2, result symbol (or None), argument
    symbols, the localised symbols, and its lines as token streams."""

    def __init__(self, nargs, res, larg, rarg, locs):
        self.nargs, self.res, self.larg, self.rarg, self.locs = nargs, res, larg, rarg, locs
        self.lines = []
        self.labels = []        # (symbol, line number): names for lines, set on entry

    @property
    def syms(self):
        """Every name a call localises: result, arguments, locals, then the labels."""
        return ([x for x in (self.res, self.larg, self.rarg) if x is not None] + self.locs +
                [s for s, _ in self.labels])

    def to_bytes(self):
        """The function as the 6502 keeps it: nargs, hasres, nsyms, nlines, nlabels, the symbols,
        the line number of each label, then each line's size (2 bytes) and its token stream."""
        data = bytes([self.nargs, 0 if self.res is None else 1, len(self.syms),
                      len(self.lines), len(self.labels)] + self.syms + [n for _, n in self.labels])
        for ln in self.lines:
            data += len(ln).to_bytes(2, 'little') + ln
        return data

    @staticmethod
    def from_bytes(d):
        """The inverse of to_bytes for data that passed the loader's checks."""
        nargs, hasres, nsyms, nlines, nlabels = d[:5]
        syms = list(d[5:5 + nsyms])
        p = 0
        res = larg = rarg = None
        if hasres:
            res, p = syms[0], 1
        if nargs == 2:
            larg, p = syms[p], p + 1
        if nargs >= 1:
            rarg, p = syms[p], p + 1
        f = Func(nargs, res, larg, rarg, syms[p:nsyms - nlabels])
        f.labels = list(zip(syms[nsyms - nlabels:], d[5 + nsyms:5 + nsyms + nlabels]))
        pos = 5 + nsyms + nlabels
        for _ in range(nlines):
            ln = d[pos] | d[pos + 1] << 8
            f.lines.append(bytes(d[pos + 2:pos + 2 + ln]))
            pos += 2 + ln
        return f

    def block_bytes(self):
        """...and its heap block: a CHAR vector holding those bytes."""
        d = self.to_bytes()
        n = len(d).to_bytes(2, 'little')
        return bytes([5]) + n + n + d


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
        self.funcs = {}         # symbol -> Func
        self.defining = None    # the function being typed: [name, Func]
        self.depth = 0
        self._outs = []

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
                codes = [char_code(ch) for ch in chars]
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

    def _isfn(self, tok):
        """Is this token the name of a function that takes arguments?  (Such
        a name is a function in the expression, everything else named is a value;
        a niladic function is called wherever a value is wanted.)"""
        c, arg = tok
        return c == T_NAME and arg in self.funcs and self.funcs[arg].nargs > 0

    def _isv(self, tok):
        """Can this token end a value?"""
        return tok[0] in (T_LIT, T_RPAR, T_RBRK) or (tok[0] == T_NAME and not self._isfn(tok))

    @staticmethod
    def _match(toks, i, close, open_):
        """Index of the open_ token matching the close token at i."""
        depth, j = 0, i
        while j >= 0:
            cj = toks[j][0]
            if cj == close:
                depth += 1
            elif cj == open_:
                depth -= 1
                if depth == 0:
                    return j
            j -= 1
        raise AplError('SYNTAX ERROR')

    def _index_groups(self, toks):
        """Split the tokens between [ and ] at top-level semicolons; an empty
        group is None.  Groups are evaluated right to left."""
        groups, cur, depth = [], [], 0
        for tk in toks:
            if tk[0] in (T_LPAR, T_LBRK):
                depth += 1
            elif tk[0] in (T_RPAR, T_RBRK):
                depth -= 1
            if tk[0] == T_SEMI and depth == 0:
                groups.append(cur)
                cur = []
            else:
                cur.append(tk)
        groups.append(cur)
        vals = [None] * len(groups)
        for k in range(len(groups) - 1, -1, -1):
            if groups[k]:
                vals[k] = self.eval_tokens(groups[k])
        return vals

    def _operand(self, toks, i):
        c, arg = toks[i]
        if c == T_RBRK:
            j = self._match(toks, i, T_RBRK, T_LBRK)
            if j == 0 or not self._isv(toks[j - 1]):
                raise AplError('SYNTAX ERROR')
            idxs = self._index_groups(toks[j + 1:i])
            base, k = self._operand(toks, j - 1)
            if base is None:
                raise AplError('VALUE ERROR')
            return index_value(base, idxs), k
        if c == T_LIT:
            return arg, i - 1
        if c == T_NAME:
            if arg in self.funcs:                       # a niladic function
                return self.call(self.funcs[arg], None, None), i - 1
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

    def eval_tokens(self, toks, top=False):
        """Evaluate one statement (top) or a parenthesised / index group.  A call of
        a function without a result gives None, which is only allowed to end a
        statement: nothing is echoed then."""
        if any(c == T_BRANCH for c, _ in toks):
            raise AplError('SYNTAX ERROR')          # a branch only starts a statement
        i = len(toks) - 1
        if i < 0 or not self._isv(toks[i]):
            raise AplError('SYNTAX ERROR')
        val, i = self._operand(toks, i)
        if val is None and not (top and i < 0):
            raise AplError('VALUE ERROR')
        while i >= 0:
            c = toks[i][0]
            if c == T_ASSIGN:
                if i > 0 and toks[i - 1][0] == T_RBRK:          # A[i;j]<-v
                    j = self._match(toks, i - 1, T_RBRK, T_LBRK)
                    if j == 0 or toks[j - 1][0] != T_NAME or toks[j - 1][1] in self.funcs:
                        raise AplError('SYNTAX ERROR')
                    idxs = self._index_groups(toks[j + 1:i - 1])
                    name = toks[j - 1][1]
                    self.vars[name] = index_assign(self.lookup(name), idxs, val)
                    i = j - 2
                    continue
                if i == 0 or toks[i - 1][0] != T_NAME or toks[i - 1][1] in self.funcs:
                    raise AplError('SYNTAX ERROR')
                self.vars[toks[i - 1][1]] = val
                i -= 2
            elif c == T_RBRK:
                j = self._match(toks, i, T_RBRK, T_LBRK)
                if j > 0 and toks[j - 1][0] >= 0x80:
                    raise AplError('NONCE ERROR')           # axis: +/[1] A
                raise AplError('SYNTAX ERROR')
            elif c >= 0xC0:
                if i == 0:
                    raise AplError('SYNTAX ERROR')
                pc = toks[i - 1][0]
                if self._isv(toks[i - 1]):
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
            elif self._isfn(toks[i]):
                f = self.funcs[toks[i][1]]
                i -= 1
                val = self._apply((lambda r: self.call(f, None, r),
                                   lambda l, r: self.call(f, l, r)), toks, i, val)
                i = self._pos
                if val is None and not (top and i < 0):
                    raise AplError('VALUE ERROR')
            else:
                raise AplError('SYNTAX ERROR')
        return val

    def _apply(self, fn, toks, i, right):
        """Apply fn monadically or dyadically; leaves new index in self._pos (set
        after the call, which may run nested evaluations)."""
        if i >= 0 and self._isv(toks[i]):
            left, i = self._operand(toks, i)
            if left is None:
                raise AplError('VALUE ERROR')
            result = fn[1](left, right)
        else:
            result = fn[0](right)
        self._pos = i
        return result

    @staticmethod
    def _is_assignment(st):
        """Does the statement start with name<- or name[...]<- (not echoed)?"""
        if len(st) < 2 or st[0][0] != T_NAME:
            return False
        if st[1][0] == T_ASSIGN:
            return True
        if st[1][0] != T_LBRK:
            return False
        depth = 0
        for k in range(1, len(st)):
            if st[k][0] in (T_LPAR, T_LBRK):
                depth += 1
            elif st[k][0] in (T_RPAR, T_RBRK):
                depth -= 1
                if depth == 0:
                    return k + 1 < len(st) and st[k + 1][0] == T_ASSIGN
        return False

    def run_line(self, line):
        return [format_value(v) for v in self.run_values(line)]

    def run_values(self, line):
        """Evaluate a line; return the values that would be echoed.  While a
        function is being defined, every line is a line of its body instead."""
        if self.defining is not None:
            self._def_line(line)
            return []
        text = line.lstrip(' \t')
        if text.startswith('\u2207'):
            self._begin_def(text[1:])
            return []
        self._outs = outs = []
        try:
            self._run_statements(self._statements(self.decode(self.tokenize(line))))
        except AplError as e:
            e.outs = outs           # what was echoed before the error (a function line can echo)
            raise
        return outs

    @staticmethod
    def _statements(toks):
        """Split a line at diamonds outside brackets; brackets must nest."""
        stmts, cur, stack = [], [], []
        for tk in toks:
            if tk[0] in (T_LPAR, T_LBRK):
                stack.append(tk[0])
            elif tk[0] in (T_RPAR, T_RBRK):
                if not stack or stack.pop() != tk[0] - 1:
                    raise AplError('SYNTAX ERROR')
            if tk[0] == T_DIAMOND and not stack:
                stmts.append(cur)
                cur = []
            else:
                cur.append(tk)
        stmts.append(cur)
        if stack:
            raise AplError('SYNTAX ERROR')
        return stmts

    def _run_statements(self, stmts):
        for st in stmts:
            if not st:
                continue
            branches = [k for k, (c, _) in enumerate(st) if c == T_BRANCH]
            if branches:
                if branches[0] != 0:
                    raise AplError('SYNTAX ERROR')
                if self.depth == 0:
                    raise AplError('NONCE ERROR')       # only functions branch
                if len(branches) > 1:
                    raise AplError('SYNTAX ERROR')
                self._branch(self.eval_tokens(st[1:]))
                continue
            val = self.eval_tokens(st, top=True)
            if val is not None and not self._is_assignment(st):
                self._outs.append(val)

    def _branch(self, v):
        """->v: the first element is the number of the next line; nothing (an empty v)
        goes on with the next statement; 0 or a number outside the lines leaves the function."""
        if v.t == CHAR:
            raise AplError('DOMAIN ERROR')
        if v.count == 0:
            return
        x = v.data[0]
        n = f_whole(x) if v.t == FLOAT else x
        if n is None:
            raise AplError('DOMAIN ERROR')
        raise _Jump(n)

    # ---- user-defined functions ---------------------------------------------
    def prompt(self):
        """What the input line starts with: six blanks, or [n] in a definition."""
        if self.defining is None:
            return '      '
        return ('[%d]' % (len(self.defining[1].lines) + 1)).ljust(6)

    def _begin_def(self, text):
        """The line was del followed by a header: R<-A FN B;L1;L2 (result, left
        argument, function name, right argument, localised names)."""
        toks = self.decode(self.tokenize(text))
        k = next((j for j, (c, _) in enumerate(toks) if c == T_SEMI), len(toks))
        head, tail, locs = toks[:k], toks[k:], []
        while tail:
            if len(tail) < 2 or tail[0][0] != T_SEMI or tail[1][0] != T_NAME:
                raise AplError('SYNTAX ERROR')
            locs.append(tail[1][1])
            tail = tail[2:]
        res = None
        if len(head) >= 2 and head[1][0] == T_ASSIGN:
            if head[0][0] != T_NAME:
                raise AplError('SYNTAX ERROR')
            res, head = head[0][1], head[2:]
        if not 1 <= len(head) <= 3 or any(c != T_NAME for c, _ in head):
            raise AplError('SYNTAX ERROR')
        names = [a for _, a in head]
        larg = rarg = None
        if len(names) == 1:
            fn = names[0]
        elif len(names) == 2:
            fn, rarg = names
        else:
            larg, fn, rarg = names
        f = Func(len(names) - 1, res, larg, rarg, locs)
        if len(set(f.syms + [fn])) != len(f.syms) + 1 or fn in self.vars:
            raise AplError('SYNTAX ERROR')
        self.defining = [fn, f]

    def _def_line(self, line):
        fn, f = self.defining
        if line.strip(' \t') == '\u2207':
            self.funcs[fn] = f
            self.defining = None
            return
        m = LABEL_RE.match(line)
        if m:                                           # NAME: at the start: a label
            line = line[:m.end() - 1] + ' ' + line[m.end():]
        toks = self.tokenize(line)
        label = None
        if m:
            label = self.decode(toks)[0][1]             # (the tokeniser made the symbol)
            if label in f.syms or label == fn:
                raise AplError('SYNTAX ERROR')
            if len(f.syms) >= 99:
                raise AplError('LIMIT ERROR')
            toks = toks[2:]
        self._statements(self.decode(toks))             # brackets must nest
        if len(f.lines) >= MAX_LINES:
            raise AplError('LIMIT ERROR')
        f.lines.append(toks)
        if label is not None:
            f.labels.append((label, len(f.lines)))

    def call(self, f, left, right):
        """Call f.  Names it uses (result, arguments, locals) are localised: they
        are undefined on entry and get their old values back on leaving, however
        it is left (dynamic scoping).  Returns the result value or None."""
        if (left is not None and f.nargs < 2) or (right is not None and f.nargs < 1):
            raise AplError('SYNTAX ERROR')
        if self.depth >= MAX_DEPTH:
            raise AplError('LIMIT ERROR')
        saved = [(s, self.vars.pop(s, None), self.funcs.pop(s, None)) for s in f.syms]
        self.depth += 1
        try:
            if left is not None:
                self.vars[f.larg] = left
            if right is not None:
                self.vars[f.rarg] = right
            for sym, n in f.labels:
                self.vars[sym] = scalar(INT, n)
            i = 0
            while i < len(f.lines):
                try:
                    self._run_statements(self._statements(self.decode(f.lines[i])))
                    i += 1
                except _Jump as j:
                    i = j.line - 1 if 1 <= j.line <= len(f.lines) else len(f.lines)
            if f.res is None:
                return None
            return self.lookup(f.res)
        finally:
            self.depth -= 1
            for s, v, fu in saved:
                self.vars.pop(s, None)
                self.funcs.pop(s, None)
                if v is not None:
                    self.vars[s] = v
                if fu is not None:
                    self.funcs[s] = fu


# =========================================================================
# REPL
# =========================================================================
def repl():
    ws = Interp()
    while True:
        try:
            line = input(ws.prompt())
        except EOFError:
            break
        try:
            for o in ws.run_line(line):
                print(o)
        except AplError as e:
            for v in getattr(e, 'outs', []):
                print(format_value(v))
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
        ('A←10 20 30 40 ⋄ A[2]', '20'),
        ('A[3 1]', '30 10'),
        ('A[⍳0]', ''),
        ('A[2 2⍴1 2 3 4]', '10 20|30 40'),
        ('A[1]+A[4]', '50'),
        ('A[A[1]÷10]', '10'),
        ('A[2.0]', '20'),
        ('A[]', '10 20 30 40'),
        ('A[5]', '!INDEX ERROR'),
        ('A[0]', '!INDEX ERROR'),
        ('A[¯1]', '!INDEX ERROR'),
        ('A[1.5]', '!DOMAIN ERROR'),
        ("A['a']", '!DOMAIN ERROR'),
        ('A[1;2]', '!RANK ERROR'),
        ('5[1]', '!RANK ERROR'),
        ('M←3 4⍴⍳12 ⋄ M[2;3]', '7'),
        ('M[2;]', '5 6 7 8'),
        ('M[;2]', '2 6 10'),
        ('M[;]', '1  2  3  4|5  6  7  8|9 10 11 12'),
        ('M[1 3;2 4]', ' 2  4|10 12'),
        ('M[3 1;1]', '9 1'),
        ('M[2 2⍴1 2 3 1;1]', '1 5|9 1'),
        ('M[1]', '!RANK ERROR'),
        ('M[1;2;3]', '!RANK ERROR'),
        ('M[4;1]', '!INDEX ERROR'),
        ('M[1;5]', '!INDEX ERROR'),
        ('M[1 2;1 2]', '1 2|5 6'),
        ('M[2 2⍴1;1 2]', '!LIMIT ERROR'),
        ('(⍳5)[3]', '3'),
        ('(2 3⍴⍳6)[2;2]', '5'),
        ("'hello'[1 5]", 'ho'),
        ('1 2 3[2]', '2'),
        ('B←2 3⍴⍳6 ⋄ ⍴B[;1]', '2'),
        ('⍴A[2 2⍴1]', '2 2'),
        ('A[1][1]', '!RANK ERROR'),
        ('A[1 2][2]', '20'),
        ('M[2;][3]', '7'),
        ('+/M[;1]', '15'),
        ('A[QQ]', '!VALUE ERROR'),
        ('QQ[1]', '!VALUE ERROR'),
        ('A[1', '!SYNTAX ERROR'),
        ('A[1)', '!SYNTAX ERROR'),
        ('(A[1)]', '!SYNTAX ERROR'),
        ('A]', '!SYNTAX ERROR'),
        ('[1]', '!SYNTAX ERROR'),
        ('+[1]', '!SYNTAX ERROR'),
        ('1;2', '!SYNTAX ERROR'),
        ('A[1;]', '!RANK ERROR'),
        ('A[1]←5', ''),
        ('A', '5 20 30 40'),
        ('+/[1]A', '!NONCE ERROR'),
        ('A[1⋄2]', '!SYNTAX ERROR'),
        ('P←1 2 3 4 5 ⋄ P[2]←9', ''),
        ('P', '1 9 3 4 5'),
        ('P[2 4]←0', ''),
        ('P', '1 0 3 0 5'),
        ('P[1 3]←7 8', ''),
        ('P', '7 0 8 0 5'),
        ('P[1 2]←1 2 3', '!LENGTH ERROR'),
        ('P[1]←1 2', '!RANK ERROR'),
        ('P[1 2]←3 3⍴1', '!RANK ERROR'),
        ('P[6]←1', '!INDEX ERROR'),
        ('P[1;1]←1', '!RANK ERROR'),
        ("P[1]←'a'", '!DOMAIN ERROR'),
        ('P', '7 0 8 0 5'),
        ('Q←P ⋄ P[1]←99 ⋄ Q', '7 0 8 0 5'),
        ('P[1]+P[2]←3', '102'),
        ('1+P[2]←5', '6'),
        ('P[1 1]←4 5', ''),
        ('P[1]', '5'),
        ('P[⍳0]←1', ''),
        ('P[⍳0]←1 2', '!LENGTH ERROR'),
        ("P[⍳0]←'a'", ''),
        ('P[2]←1.5', ''),
        ('P', '5 1.5 8 0 5'),
        ("R←'hello' ⋄ R[1]←'j' ⋄ R", 'jello'),
        ("R[1]←1", '!DOMAIN ERROR'),
        ('B←1 0 1 ⋄ B[2]←1 ⋄ B', '1 1 1'),
        ('B[2]←5 ⋄ B', '1 5 1'),
        ('N←2 3⍴⍳6 ⋄ N[2;3]←0 ⋄ N', '1 2 3|4 5 0'),
        ('N[;1]←7 8 ⋄ N', '7 2 3|8 5 0'),
        ('N[1;]←9 ⋄ N', '9 9 9|8 5 0'),
        ('N[1 2;1 2]←2 2⍴1 2 3 4 ⋄ N', '1 2 9|3 4 0'),
        ('N[1 2;1 2]←1 2 3 4', '!RANK ERROR'),
        ('N[1 2;1 2]←2 3⍴1', '!LENGTH ERROR'),
        ('N[;]←0 ⋄ N', '0 0 0|0 0 0'),
        ('N[1]←1', '!RANK ERROR'),
        ('N[3;1]←1', '!INDEX ERROR'),
        ('N[2 2⍴1;1 2]←1', '!LIMIT ERROR'),
        ('N[1;2]←2.5 ⋄ N', '0 2.5 0|0   0 0'),
        ('ZZ[1]←1', '!VALUE ERROR'),
        ('(P)[1]←1', '!SYNTAX ERROR'),
        ('P[1][1]←1', '!SYNTAX ERROR'),
        ('[1]←1', '!SYNTAX ERROR'),
        ('P[QQ]←1', '!VALUE ERROR'),
        ('P[1]←QQ', '!VALUE ERROR'),
        ('P[1←2', '!SYNTAX ERROR'),
        ('P[1]←2 ⋄ P[2]←3 ⋄ P', '2 3 8 0 5'),
        ('P[P[1]]←4 ⋄ P', '2 4 8 0 5'),
        ('P[1 2]←P[2 1] ⋄ P', '4 2 8 0 5'),
        ('SS←5 ⋄ SS[1]←2', '!RANK ERROR'),
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

    # user-defined functions: sessions of lines; '!KIND' marks an error
    def session(lines):
        w = Interp()
        out = []
        for ln in lines:
            r = _try(lambda: w.run_line(ln))
            out.append('!' + r if isinstance(r, str) else '|'.join(r))
        return out

    D = '\u2207'
    fn_cases = [
        ([D + 'R\u2190SQ X', 'R\u2190X\u00d7X', D, 'SQ 5', 'SQ 1 2 3', '1+SQ 3'],
         ['', '', '', '25', '1 4 9', '10']),
        ([D + 'R\u2190A ADD B', 'R\u2190A+B', D, '1 ADD 2', '1 2 3 ADD 10', 'ADD 1'],
         ['', '', '', '3', '11 12 13', '!VALUE ERROR']),
        ([D + 'R\u2190K', 'R\u219042', D, 'K', 'K+1', '2\u00d7K', 'K K'],
         ['', '', '', '42', '43', '84', '!SYNTAX ERROR']),
        ([D + 'SHOW X', 'X', 'X+1', D, 'SHOW 5', 'SHOW 1 2', '1+SHOW 1'],
         ['', '', '', '', '5|6', '1 2|2 3', '!VALUE ERROR']),
        ([D + 'SET X', 'G\u2190X', D, 'SET 7', 'G', 'A\u2190SET 1', 'G'],
         ['', '', '', '', '7', '!VALUE ERROR', '1']),
        ([D + 'R\u2190F X;T', 'T\u2190X+1', 'R\u2190T\u00d72', D, 'T\u21909', 'F 1', 'T', 'F 2', 'T'],
         ['', '', '', '', '', '4', '9', '6', '9']),
        ([D + 'R\u2190F X', 'R\u2190G X', D, D + 'R\u2190G X', 'R\u2190X+1', D, 'F 1', '2+F 3'],
         ['', '', '', '', '', '', '2', '6']),
        ([D + 'R\u2190FACT N', 'R\u21901', 'R\u2190N\u00d7FACT N-1', D, 'FACT 0'],
         ['', '', '', '', '!LIMIT ERROR']),
        ([D + 'R\u2190SUM N', 'R\u2190N+SUM N-1', D, 'SUM 3'],
         ['', '', '', '!LIMIT ERROR']),
        ([D + 'R\u2190N NOP', 'R\u2190N', D],
         ['', '', '']),
        ([D + 'F', '1', 'G\u21902', D, 'F', 'G', 'F\u21903'],
         ['', '', '', '', '1', '2', '!SYNTAX ERROR']),
        (['V\u21905', D + 'V', D],
         ['', '!SYNTAX ERROR', '!SYNTAX ERROR']),
        ([D + 'A F B C', D + 'R\u2190', D + 'R\u2190F R', D + 'F X;X', D + 'X F X', D + '1', D + 'F 1'],
         ['!SYNTAX ERROR'] * 7),
        ([D + 'R\u2190F X', 'R\u2190X', '(1', D, 'F 1'],
         ['', '', '!SYNTAX ERROR', '', '1']),
        ([D + 'R\u2190F X', 'R\u2190X\u2192', D, 'F 1'],
         ['', '', '', '!SYNTAX ERROR']),
        ([D + 'F X', 'Y\u2190X', D, 'F 3', 'Y', '(F 4)'],
         ['', '', '', '', '3', '!VALUE ERROR']),
        ([D + 'R\u2190F X', 'R\u2190X', D, 'F', 'A\u21901 ⋄ F A'],
         ['', '', '', '!SYNTAX ERROR', '1']),
        ([D + 'R\u2190F X;Y', 'Y\u21905', 'R\u2190Y+X', D, 'Y\u21901', 'F 10', 'Y', D + 'R\u2190G X', 'R\u2190Y+F X', D, 'G 1', 'Y'],
         ['', '', '', '', '', '15', '1', '', '', '', '7', '1']),
        ([D + 'R\u2190F X', 'R\u2190Q', D, 'F 1', 'Q\u21907', 'F 1'],
         ['', '', '', '!VALUE ERROR', '', '7']),
        ([D + 'R\u2190F X', 'R\u21901\u00f70', D, 'A\u21903', 'F A', 'A'],
         ['', '', '', '', '!DOMAIN ERROR', '3']),
        ([D + 'R\u2190F X;A', 'A\u21900', 'R\u21901\u00f70', D, 'A\u219033', 'F 1', 'A'],
         ['', '', '', '', '', '!DOMAIN ERROR', '33']),
        (['A\u2190\u23733', D + 'R\u2190F X', 'R\u2190A[X]', D, 'F 2', 'F 9'],
         ['', '', '', '', '2', '!INDEX ERROR']),
        ([D + 'R\u2190F X;A', 'A\u2190\u23733', 'A[2]\u2190X', 'R\u2190A', D, 'F 9', 'A'],
         ['', '', '', '', '', '1 9 3', '!VALUE ERROR']),
        ([D + 'R\u2190F X', 'R\u2190+/X', D, 'F \u23735', 'F 2 3\u2374\u23736'],
         ['', '', '', '15', '6 15']),
        ([D + 'F X', '\u2374X', '\u2373X', D, 'F 3', 'F\u2190\u2373\u2374'],
         ['', '', '', '', '|1 2 3', '!SYNTAX ERROR']),
    ]
    for lines, want in fn_cases:
        got = session(lines)
        assert got == want, (lines, got, want)
    n += 1

    # control flow (see test_funcs.FLOW for more)

    # control flow (test_funcs.FLOW has more, compared with the 6502)
    A_ = '\u2192'
    flow_cases = [
        ([A_ + '1', '1' + A_ + '1', A_], ['!NONCE ERROR', '!SYNTAX ERROR', '!NONCE ERROR']),
        ([D + 'F', '1', A_ + '0', '2', D, 'F'], ['', '', '', '', '', '1']),
        ([D + 'F', '1', A_ + '4', '2', D, 'F'], ['', '', '', '', '', '1']),
        ([D + 'F', A_ + '3', '1', '2', '3', D, 'F'], ['', '', '', '', '', '', '2|3']),
        ([D + 'F', A_ + '\u23730', '1', D, 'F'], ['', '', '', '', '1']),
        ([D + 'F', A_ + '2 1', '1', '2', D, 'F'], ['', '', '', '', '', '1|2']),
        ([D + 'F', A_ + '2.5', D, 'F', D + 'G', A_ + "'a'", D, 'G'],
         ['', '', '', '!DOMAIN ERROR', '', '', '', '!DOMAIN ERROR']),
        ([D + 'F', '1 \u22c4 ' + A_ + '3 \u22c4 2', '3', D, 'F'], ['', '', '', '', '1']),
        ([D + 'F', A_ + '1+', D, 'F', D + 'G', A_ + 'Q', D, 'G', D + 'H', A_ + '1' + A_ + '2', D, 'H'],
         ['', '', '', '!SYNTAX ERROR', '', '', '', '!VALUE ERROR', '', '', '', '!SYNTAX ERROR']),
        ([D + 'F', 'L:1', 'M: 2', 'N :3', D, 'F'], ['', '', '', '!SYNTAX ERROR', '', '1|2']),
        ([D + 'F', 'L:L', 'M:M+L', D, 'F'], ['', '', '', '', '1|3']),
        ([D + 'F', 'L:1', 'L:2', 'F:1', D, 'F'], ['', '', '!SYNTAX ERROR', '!SYNTAX ERROR', '', '1']),
        ([D + 'F', "L:'x:y'", "'a:b'", '\u235d z: comment', 'K:\u235d c', D, 'F'], ['', '', '', '', '', '', 'x:y|a:b']),
        ([D + 'R\u2190SUMTO N;I', 'R\u21900', 'I\u21901', 'TOP:R\u2190R+I', 'I\u2190I+1', A_ + 'TOP\u00d7\u2373I\u2264N', D,
          'SUMTO 10', 'SUMTO 100'], ['', '', '', '', '', '', '', '55', '5050']),
        ([D + 'R\u2190FACT N', 'R\u21901', A_ + '0\u00d7\u2373N<2', 'R\u2190N\u00d7FACT N-1', D, 'FACT 1', 'FACT 5', 'FACT 7'],
         ['', '', '', '', '', '1', '120', '5040']),
        ([D + 'R\u2190F X', A_ + '3', 'R\u21901', 'R\u21902', D, 'F 0'], ['', '', '', '', '', '2']),
    ]
    for lines, want in flow_cases:
        got = session(lines)
        assert got == want, (lines, got, want)
    n += 1

    print('all %d test groups passed' % n)


if __name__ == '__main__':
    if '--test' in sys.argv:
        selftest()
    else:
        repl()
