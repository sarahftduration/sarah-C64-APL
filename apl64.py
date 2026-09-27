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
"\\" is scan: element k of f\\v is f/ of the first k elements (so -\\1 2 3 is 1 ¯1 2), along the
last axis, the result the shape of v.  a∘.f b is the outer product: f between every element of a
and every element of b, shaped like the shape of a followed by the shape of b (LIMIT ERROR past
rank 2); f is one of the scalar dyadic functions.
A function or operator followed by [k] takes an axis: +/[k]v, +\\[k]v, ⌽[k]v and a⌽[k]v, k from 1 to the rank of v
(RANK, DOMAIN, INDEX ERROR); axis 1 of a matrix is worked as the last axis of its transpose (axis_fn).
"\\" after a value is expand (a\\b: the 0s of a are fills, the 1s take the elements of b); a~b is without, ⍉ is
transpose (a⍉b takes a permutation of the axes).
a f.g b is the inner product: f/ of (a g b) over the last axis of a and the first axis of b (see make_inner).
Division always gives FLOAT.  0 / 0 is 1; x / 0 is DOMAIN ERROR.
Origin is 1.  Rank <= 2.  Indexing A[i] and A[i;j] (the
result shape is the index shapes joined; a result of rank 3 or more is
LIMIT ERROR; a bad index value is INDEX ERROR); indices are evaluated right
to left, then the indexed array.  Indexed assignment A[i]<-v makes a new array (index_assign).  Workspace is limited to WS_BYTES per array.

Token stream (bytes), one line ends with $00:
    $00 end   $01 literal   $02 name (1-byte symbol index)
    $03 (  $04 )  $05 [  $06 ]  $07 <-  $08 ->  $09 diamond  $0A ;  $0C the empty vector
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


def f_floor(p):
    """The greatest whole number not above p, as a float24 (always exact)."""
    if p >> 16 == 0:
        return 0
    return f_from_fraction(Fraction(math.floor(f_to_fraction(p))))


def f_ceil(p):
    return f_neg(f_floor(f_neg(p)))


def _floorlike(fn):
    """Monadic floor and ceiling: whole numbers stay as they are; FLOAT becomes INT if every
    result fits int16, else stays FLOAT (with the whole values)."""
    def run(t, xs):
        if t == CHAR:
            raise AplError('DOMAIN ERROR')
        if t != FLOAT:
            return t, list(xs)
        fs = [fn(x) for x in xs]
        ns = [f_whole(f) for f in fs]
        if all(_in16(n) for n in ns):
            return INT, ns
        return FLOAT, fs
    return run


def _bit(t, x):
    """The 0 or 1 that x is, for the logical functions; anything else is DOMAIN ERROR."""
    if t == CHAR or (x != 0 and x != (ONE if t == FLOAT else 1)):
        raise AplError('DOMAIN ERROR')
    return 0 if x == 0 else 1


def _logic(name):
    """A and B, A or B on 0s and 1s (BOOL, INT or FLOAT values): BOOL results."""
    def run(ta, xs, tb, ys):
        if ta == CHAR or tb == CHAR:
            raise AplError('DOMAIN ERROR')
        out = []
        for x, y in zip(xs, ys):
            a, b = _bit(ta, x), _bit(tb, y)
            out.append(a & b if name == '∧' else a | b)
        return BOOL, out
    return run


def _m_not(t, xs):
    if t == CHAR:
        raise AplError('DOMAIN ERROR')
    return BOOL, [1 - _bit(t, x) for x in xs]


def _m_abs(t, xs):
    """|x: BOOL and INT give INT (FLOAT for the whole array if -32768 turns up), FLOAT clears the sign."""
    if t == CHAR:
        raise AplError('DOMAIN ERROR')
    if t == FLOAT:
        return FLOAT, [x & ~0x8000 if x >> 16 else 0 for x in xs]
    out = [abs(x) for x in xs]
    if all(_in16(v) for v in out):
        return INT, out
    return FLOAT, [f_from_int(v) for v in out]


def _maxmin(name):
    """A max B and A min B: exact comparison (no tolerance); INT unless a FLOAT is involved."""
    def run(ta, xs, tb, ys):
        if ta == CHAR or tb == CHAR:
            raise AplError('DOMAIN ERROR')
        if ta != FLOAT and tb != FLOAT:
            return INT, [max(x, y) if name == '⌈' else min(x, y) for x, y in zip(xs, ys)]
        out = []
        for x, y in zip(xs, ys):
            fx, fy = to_f(ta, x), to_f(tb, y)
            if name == '⌈':
                out.append(fx if _fkey(fx) >= _fkey(fy) else fy)
            else:
                out.append(fx if _fkey(fx) <= _fkey(fy) else fy)
        return FLOAT, out
    return run


def f_residue(a, b):
    """A|B for float24: B - A * floor(B / A), each step rounded, then moved into [0, A) (or (A, 0]) if
    the roundings left it outside.  A = 0 gives B."""
    if a >> 16 == 0:
        return b
    r = f_sub(b, f_mul(a, f_floor(f_div(b, a))))
    if r >> 16:
        if (r >> 15 & 1) != (a >> 15 & 1):
            r = f_add(r, a)
        elif (r & 0xFF7FFF) >= (a & 0xFF7FFF):
            r = f_sub(r, a)
    return r


def _residue(ta, xs, tb, ys):
    if ta == CHAR or tb == CHAR:
        raise AplError('DOMAIN ERROR')
    if ta != FLOAT and tb != FLOAT:
        return INT, [y % x if x else y for x, y in zip(xs, ys)]
    return FLOAT, [f_residue(to_f(ta, x), to_f(tb, y)) for x, y in zip(xs, ys)]


SCALAR_DYADIC = '+-×÷=≠<≤>≥⌈⌊|∧∨'
_DY = {'+': _arith('+'), '-': _arith('-'), '×': _arith('×'), '÷': _div,
       '⌈': _maxmin('⌈'), '⌊': _maxmin('⌊'), '|': _residue, '∧': _logic('∧'), '∨': _logic('∨')}
for _g in '=≠<≤>≥':
    _DY[_g] = _cmp(_g)
_MON = {'+': _m_id, '-': _m_neg, '×': _m_sign, '÷': _m_recip,
        '⌈': _floorlike(f_ceil), '⌊': _floorlike(f_floor), '|': _m_abs}


# =========================================================================
# Numeric functions: exp, ln, square root, power, logarithm
# =========================================================================
# float24 has a 16-bit significand, so each of these is a short program of + - x / on it, run by the
# small interpreter below (vm_run).  The 6502 runs the same programs, as data generated from
# MATH_PROGS by tools/gen_math.py, through the same float routines, so the two agree to the last bit.
# The interpreter has an accumulator, eight float slots and an integer register ir.  Every instruction is
# an opcode and an operand: a constant, slot, count or bit.
VM_OPS = ['END', 'LDK', 'LDS', 'STS', 'ADDS', 'SUBS', 'MULS', 'DIVS', 'RSUBS', 'RDIVS', 'ADDK', 'SUBK', 'MULK',
          'DIVK', 'RSUBK', 'RDIVK', 'NEG', 'ABS', 'FREXP', 'ITOF', 'ROUND', 'LDEXP', 'DECIR', 'SARIR', 'IFBIT',
          'NEGS', 'SETIR', 'CALL', 'DOMERR']
OP_IFLT, OP_IFGE = 32, 48        # 32+n, 48+n: run the next n instructions only if acc < / >= the constant, else skip them
MATH_CONST_NAMES = []
MATH_CONSTS = []


def _mconst(name, x):
    MATH_CONST_NAMES.append(name)
    MATH_CONSTS.append(f_from_fraction(Fraction(x)))


_mconst('one', 1)
_mconst('two', 2)
_mconst('half', 0.5)
_mconst('log2e', 1 / math.log(2))
_mconst('ln2hi', 355 / 512)                 # (9 bits: a whole number times it is exact)
_mconst('ln2lo', math.log(2) - 355 / 512)
for _i in range(1, 8):
    _mconst('c%d' % _i, 1 / math.factorial(_i))
_mconst('sqrthalf', math.sqrt(0.5))
_mconst('third', 1 / 3)
_mconst('fifth', 1 / 5)
_mconst('seventh', 1 / 7)
_mconst('ninth', 1 / 9)
_mconst('sq0', 0.41731)
_mconst('sq1', 0.59016)
_mconst('m100', -100)
_mconst('p89', 89)
_mconst('zero', 0)
_mconst('tiny', 1e-30)
_mconst('onep', 1 + 2 ** -15)                # the float after 1
_mconst('pi', math.pi)
_mconst('pio2', math.pi / 2)
_mconst('pio4', math.pi / 4)
_mconst('tan8', math.tan(math.pi / 8))
_mconst('twoopi', 2 / math.pi)
_A = 201 / 128                               # pi/2 in three pieces, the first two of 8 bits (k times them is exact)
_B = round((math.pi / 2 - _A) * 2 ** 19) / 2 ** 19
_mconst('pio2a', _A)
_mconst('pio2b', _B)
_mconst('pio2c', math.pi / 2 - _A - _B)
_mconst('sn3', -1 / 6)
_mconst('sn5', 1 / 120)
_mconst('sn7', -1 / 5040)
_mconst('cs2', -1 / 2)
_mconst('cs4', 1 / 24)
_mconst('cs6', -1 / 720)
_mconst('cs8', 1 / 40320)
for _i in (3, 5, 7, 9, 11, 13):
    _mconst('at%d' % _i, (-1) ** ((_i - 1) // 2) / _i)


MATH_PROG_NAMES = ['EXP', 'LN', 'SQRT', 'TRIG', 'SINTAIL', 'COSTAIL', 'SIN', 'COS', 'TAN', 'ATAN', 'ASIN', 'ACOS', 'CIRC0', 'CIRC4']


def _asm(*ops):
    """Assemble (name, operand ...) tuples into (opcode, operand) pairs; CALL takes a program's name."""
    out = []
    for o in ops:
        name = o[0]
        if name == 'CALL':
            out.append((VM_OPS.index('CALL'), MATH_PROG_NAMES.index(o[1])))
            continue
        if name in ('IFLT', 'IFGE'):
            out.append(((OP_IFLT if name == 'IFLT' else OP_IFGE) + o[2], MATH_CONST_NAMES.index(o[1])))
        elif name == 'IFBIT':
            out.append((VM_OPS.index('IFBIT'), o[1] << 4 | o[2]))
        else:
            a = o[1] if len(o) > 1 else 0
            if isinstance(a, str):
                a = MATH_CONST_NAMES.index(a)
            out.append((VM_OPS.index(name), a))
    return out


MATH_PROGS = {
    # x in acc; exp x = 2^k * exp r, r = x - k ln 2 (ln 2 in two parts, so k*ln2hi is exact), a polynomial for exp r
    'EXP': _asm(('STS', 0), ('MULK', 'log2e'), ('ROUND',), ('ITOF',), ('STS', 1), ('MULK', 'ln2hi'), ('RSUBS', 0), ('STS', 2),
                ('LDS', 1), ('MULK', 'ln2lo'), ('RSUBS', 2), ('STS', 2),
                ('LDK', 'c7'), ('MULS', 2), ('ADDK', 'c6'), ('MULS', 2), ('ADDK', 'c5'), ('MULS', 2), ('ADDK', 'c4'), ('MULS', 2),
                ('ADDK', 'c3'), ('MULS', 2), ('ADDK', 'c2'), ('MULS', 2), ('ADDK', 'c1'), ('MULS', 2), ('ADDK', 'one'),
                ('LDEXP',), ('END',)),
    # x > 0 in acc; x = m 2^e with m brought into [0.7, 1.4); ln m = 2 z (1 + z2/3 + z2^2/5 + ...), z = (m-1)/(m+1)
    'LN': _asm(('FREXP',), ('STS', 0), ('IFLT', 'sqrthalf', 3), ('MULK', 'two'), ('STS', 0), ('DECIR',),
               ('LDS', 0), ('SUBK', 'one'), ('STS', 1), ('LDS', 0), ('ADDK', 'one'), ('RDIVS', 1), ('STS', 1),
               ('MULS', 1), ('STS', 2), ('LDK', 'ninth'), ('MULS', 2), ('ADDK', 'seventh'), ('MULS', 2), ('ADDK', 'fifth'), ('MULS', 2),
               ('ADDK', 'third'), ('MULS', 2), ('ADDK', 'one'), ('MULS', 1), ('MULK', 'two'), ('STS', 3),
               ('ITOF',), ('STS', 4), ('MULK', 'ln2hi'), ('ADDS', 3), ('STS', 3), ('LDS', 4), ('MULK', 'ln2lo'), ('ADDS', 3), ('END',)),
    # x > 0 in acc; m in [0.5, 2) and an even exponent, Newton's method from a straight line (3 rounds), then 2^(e/2)
    'SQRT': _asm(('FREXP',), ('STS', 0), ('IFBIT', 0, 3), ('MULK', 'two'), ('STS', 0), ('DECIR',),
                 ('LDS', 0), ('MULK', 'sq1'), ('ADDK', 'sq0'), ('STS', 1),
                 ('LDS', 0), ('DIVS', 1), ('ADDS', 1), ('MULK', 'half'), ('STS', 1),
                 ('LDS', 0), ('DIVS', 1), ('ADDS', 1), ('MULK', 'half'), ('STS', 1),
                 ('LDS', 0), ('DIVS', 1), ('ADDS', 1), ('MULK', 'half'),
                 ('SARIR',), ('LDEXP',), ('END',)),
    # sin and cos: k = round(x 2/pi), r = x - k pi/2 (three pieces), polynomials for sin r and cos r in slots 4 and 5, ir = k
    'TRIG': _asm(('STS', 0), ('MULK', 'twoopi'), ('ROUND',), ('ITOF',), ('STS', 1), ('MULK', 'pio2a'), ('RSUBS', 0), ('STS', 2),
                 ('LDS', 1), ('MULK', 'pio2b'), ('RSUBS', 2), ('STS', 2), ('LDS', 1), ('MULK', 'pio2c'), ('RSUBS', 2), ('STS', 2),
                 ('MULS', 2), ('STS', 3),
                 ('LDK', 'sn7'), ('MULS', 3), ('ADDK', 'sn5'), ('MULS', 3), ('ADDK', 'sn3'), ('MULS', 3), ('ADDK', 'one'), ('MULS', 2), ('STS', 4),
                 ('LDK', 'cs8'), ('MULS', 3), ('ADDK', 'cs6'), ('MULS', 3), ('ADDK', 'cs4'), ('MULS', 3), ('ADDK', 'cs2'), ('MULS', 3), ('ADDK', 'one'), ('STS', 5),
                 ('END',)),
    # the quadrant k & 3 picks sin r or cos r, and the sign
    'SINTAIL': _asm(('LDS', 4), ('IFBIT', 0, 1), ('LDS', 5), ('IFBIT', 1, 1), ('NEG',), ('END',)),
    'COSTAIL': _asm(('LDS', 5), ('IFBIT', 0, 1), ('LDS', 4), ('IFBIT', 0, 1), ('NEG',), ('IFBIT', 1, 1), ('NEG',), ('END',)),
    'SIN': _asm(('CALL', 'TRIG'), ('CALL', 'SINTAIL'), ('END',)),
    'COS': _asm(('CALL', 'TRIG'), ('CALL', 'COSTAIL'), ('END',)),
    'TAN': _asm(('CALL', 'TRIG'), ('CALL', 'SINTAIL'), ('STS', 6), ('CALL', 'COSTAIL'), ('STS', 7), ('LDS', 6), ('DIVS', 7), ('END',)),
    # atan of |x| brought into [0, tan(pi/8)]: 1/a if a >= 1 (ir = 1), then (a-1)/(a+1) with pi/4 added; the series; the sign of x
    'ATAN': _asm(('STS', 0), ('ABS',), ('STS', 1), ('SETIR', 0), ('LDK', 'zero'), ('STS', 2),
                 ('LDS', 1), ('IFGE', 'one', 3), ('RDIVK', 'one'), ('STS', 1), ('SETIR', 1),
                 ('LDS', 1), ('IFGE', 'tan8', 8), ('SUBK', 'one'), ('STS', 3), ('LDS', 1), ('ADDK', 'one'), ('RDIVS', 3), ('STS', 1), ('LDK', 'pio4'), ('STS', 2),
                 ('LDS', 1), ('MULS', 1), ('STS', 3),
                 ('LDK', 'at13'), ('MULS', 3), ('ADDK', 'at11'), ('MULS', 3), ('ADDK', 'at9'), ('MULS', 3), ('ADDK', 'at7'), ('MULS', 3),
                 ('ADDK', 'at5'), ('MULS', 3), ('ADDK', 'at3'), ('MULS', 3), ('ADDK', 'one'), ('MULS', 1), ('ADDS', 2),
                 ('IFBIT', 0, 1), ('RSUBK', 'pio2'), ('NEGS', 0), ('END',)),
    # asin x = atan(x / sqrt((1-a)(1+a))), a = |x|; |x| > 1 is DOMAIN ERROR and |x| = 1 gives +-pi/2
    'ASIN': _asm(('STS', 6), ('ABS',), ('STS', 7), ('IFGE', 'onep', 1), ('DOMERR',),
                 ('RSUBK', 'one'), ('STS', 8), ('LDS', 7), ('ADDK', 'one'), ('MULS', 8),
                 ('IFLT', 'tiny', 3), ('LDK', 'pio2'), ('NEGS', 6), ('END',),
                 ('CALL', 'SQRT'), ('STS', 8), ('LDS', 6), ('DIVS', 8), ('CALL', 'ATAN'), ('END',)),
    # acos x = 2 atan(sqrt((1-x)/(1+x))); acos(-1) = pi, acos(1) = 0
    'ACOS': _asm(('STS', 6), ('ABS',), ('IFGE', 'onep', 1), ('DOMERR',),
                 ('LDS', 6), ('RSUBK', 'one'), ('STS', 7), ('LDS', 6), ('ADDK', 'one'),
                 ('IFLT', 'tiny', 2), ('LDK', 'pi'), ('END',),
                 ('RDIVS', 7), ('IFLT', 'tiny', 1), ('END',), ('CALL', 'SQRT'), ('CALL', 'ATAN'), ('MULK', 'two'), ('END',)),
    # 0 circle x = sqrt(1 - x^2) and 4 circle x = sqrt(1 + x^2)
    'CIRC0': _asm(('ABS',), ('STS', 7), ('IFGE', 'onep', 1), ('DOMERR',),
                  ('RSUBK', 'one'), ('STS', 8), ('LDS', 7), ('ADDK', 'one'), ('MULS', 8),
                  ('IFLT', 'tiny', 1), ('END',), ('CALL', 'SQRT'), ('END',)),
    'CIRC4': _asm(('STS', 7), ('MULS', 7), ('ADDK', 'one'), ('CALL', 'SQRT'), ('END',)),
}


def vm_run(prog, x):
    """Run a program on the float24 x; returns the accumulator."""
    return _vm(prog, x, [0] * 12, [0])


def _vm(prog, acc, S, st):
    """The interpreter proper: S is the slots, st[0] the integer register (both shared with called programs)."""
    ir, pc = st[0], 0
    while True:
        op, arg = prog[pc]
        pc += 1
        if op >= OP_IFLT:
            below = _fkey(acc) < _fkey(MATH_CONSTS[arg])
            if below != (op < OP_IFGE):
                pc += op & 15
            continue
        name = VM_OPS[op]
        if name == 'END':
            st[0] = ir
            return acc
        elif name == 'CALL':
            st[0] = ir
            acc = _vm(MATH_PROGS[MATH_PROG_NAMES[arg]], acc, S, st)
            ir = st[0]
        elif name == 'DOMERR':
            raise AplError('DOMAIN ERROR')
        elif name == 'LDK':
            acc = MATH_CONSTS[arg]
        elif name == 'LDS':
            acc = S[arg]
        elif name == 'STS':
            S[arg] = acc
        elif name == 'ADDS':
            acc = f_add(acc, S[arg])
        elif name == 'SUBS':
            acc = f_sub(acc, S[arg])
        elif name == 'MULS':
            acc = f_mul(acc, S[arg])
        elif name == 'DIVS':
            acc = f_div(acc, S[arg])
        elif name == 'RSUBS':
            acc = f_sub(S[arg], acc)
        elif name == 'RDIVS':
            acc = f_div(S[arg], acc)
        elif name == 'ADDK':
            acc = f_add(acc, MATH_CONSTS[arg])
        elif name == 'SUBK':
            acc = f_sub(acc, MATH_CONSTS[arg])
        elif name == 'MULK':
            acc = f_mul(acc, MATH_CONSTS[arg])
        elif name == 'DIVK':
            acc = f_div(acc, MATH_CONSTS[arg])
        elif name == 'RSUBK':
            acc = f_sub(MATH_CONSTS[arg], acc)
        elif name == 'RDIVK':
            acc = f_div(MATH_CONSTS[arg], acc)
        elif name == 'NEG':
            acc = f_neg(acc)
        elif name == 'ABS':
            acc = acc & ~0x8000 if acc >> 16 else 0
        elif name == 'FREXP':                         # acc = the significand in [0.5, 1) (exponent 128), ir = the exponent
            ir = (acc >> 16) - 128
            acc = (acc & 0xFFFF) | (128 << 16)
        elif name == 'ITOF':
            acc = f_from_int(ir)
        elif name == 'ROUND':                         # ir = floor(acc + 0.5), which must fit int16
            ir = f_whole(f_floor(f_add(acc, MATH_CONSTS[MATH_CONST_NAMES.index('half')])))
            if not -32768 <= ir <= 32767:
                raise AplError('DOMAIN ERROR')
        elif name == 'LDEXP':                         # acc = acc * 2^ir: overflow is DOMAIN ERROR, underflow is zero
            if acc >> 16:
                e = (acc >> 16) + ir
                if e > 255:
                    raise AplError('DOMAIN ERROR')
                acc = 0 if e < 1 else (acc & 0xFFFF) | (e << 16)
        elif name == 'DECIR':
            ir -= 1
        elif name == 'SARIR':
            ir >>= 1
        elif name == 'IFBIT':
            if not ir >> (arg >> 4) & 1:
                pc += arg & 15
        elif name == 'NEGS':
            if S[arg] >> 16 and S[arg] & 0x8000:
                acc = f_neg(acc)
        elif name == 'SETIR':
            ir = arg
        else:
            raise Exception(name)


def _k(name):
    return MATH_CONSTS[MATH_CONST_NAMES.index(name)]


def f_exp(x):
    """e to the x.  Below -100 it is zero (it would underflow); above 89 it overflows."""
    if _fkey(x) < _fkey(_k('m100')):
        return 0
    if _fkey(x) > _fkey(_k('p89')):
        raise AplError('DOMAIN ERROR')
    return vm_run(MATH_PROGS['EXP'], x)


def f_ln(x):
    """Natural logarithm; zero and negative numbers are DOMAIN ERROR."""
    if x >> 16 == 0 or x & 0x8000:
        raise AplError('DOMAIN ERROR')
    return vm_run(MATH_PROGS['LN'], x)


def f_sqrt(x):
    if x >> 16 == 0 or x & 0x8000:
        raise AplError('DOMAIN ERROR')
    return vm_run(MATH_PROGS['SQRT'], x)


def f_powi(a, n):
    """a to the whole power n >= 1 by repeated squaring."""
    r = ONE
    while True:
        if n & 1:
            r = f_mul(r, a)
        n >>= 1
        if n == 0:
            return r
        a = f_mul(a, a)


def f_pow(a, b):
    """a to the power b.  0*0 is 1; 0 to a negative power, a negative number to a power that is not a whole
    number of magnitude at most 127, are DOMAIN ERROR.  Whole powers (magnitude 127 or less) are products, so
    they are exact when the result is representable; 0.5 is the square root; otherwise exp(b ln a)."""
    if b >> 16 == 0:
        return ONE
    if a >> 16 == 0:
        if b & 0x8000:
            raise AplError('DOMAIN ERROR')
        return 0
    n = f_whole(b)
    if n is not None and abs(n) <= 127:
        r = f_powi(a, abs(n))
        return r if n > 0 else f_div(ONE, r)
    if a & 0x8000:
        raise AplError('DOMAIN ERROR')
    if b == _k('half'):
        return f_sqrt(a)
    return f_exp(f_mul(b, f_ln(a)))


def f_log(a, b):
    """The logarithm of b to the base a."""
    return f_div(f_ln(b), f_ln(a))


def _whole_nonneg(x):
    """x as a whole number from 0 to 65535, else DOMAIN ERROR."""
    n = f_whole(x)
    if n is None or not 0 <= n <= 65535:
        raise AplError('DOMAIN ERROR')
    return n


def f_fact(x):
    """x! for a whole x from 0 (its product overflows float24 above 33, which is DOMAIN ERROR)."""
    n = _whole_nonneg(x)
    r = ONE
    for i in range(2, n + 1):
        r = f_mul(r, f_from_int(i))
    return r


def f_binom(a, b):
    """a!b, the number of ways to choose a things from b: whole numbers from 0, 0 if a is above b.  The product
    r*(b-k+i)/i is taken a step at a time (k = the smaller of a and b-a), so it is a whole number at every step."""
    na, nb = _whole_nonneg(a), _whole_nonneg(b)
    if na > nb:
        return 0
    k = min(na, nb - na)
    r = ONE
    for i in range(1, k + 1):
        r = f_div(f_mul(r, f_from_int(nb - k + i)), f_from_int(i))
    return r


# --- random numbers ---------------------------------------------------------------------------------------------------
# xorshift32; a draw is the top 16 bits of the state.  The 6502 keeps the same state (rnd_state) and gives the same numbers;
# )SEED n (n from 0 to 65535) sets it with rng_seed.
_RNG = [0x2545F491]


def rng_seed(n):
    n &= 0xFFFF
    _RNG[0] = (n << 16) | ((n ^ 0x5A5A) & 0xFFFF) | 1


def rng_draw():
    x = _RNG[0]
    x ^= (x << 13) & 0xFFFFFFFF
    x ^= x >> 17
    x ^= (x << 5) & 0xFFFFFFFF
    _RNG[0] = x
    return x >> 16


def roll(v):
    """?v: for each element n a random integer from 1 to n (n from 1 to 32767; DOMAIN ERROR for anything else, all checked before
    the first draw); a 0 gives a random number between 0 and 1 (r/65536 for an odd r), and makes the whole result FLOAT."""
    if v.t == CHAR:
        raise AplError('DOMAIN ERROR')
    ns = []
    for x in v.data:
        n = f_whole(x) if v.t == FLOAT else x
        if n is None or not 0 <= n <= 32767:
            raise AplError('DOMAIN ERROR')
        ns.append(n)
    zero = 0 in ns
    out = []
    for n in ns:
        r = rng_draw()
        if n == 0:
            out.append(f_from_fraction(Fraction(r | 1, 65536)))
        else:
            k = (r * n >> 16) + 1
            out.append(f_from_int(k) if zero else k)
    return Value(FLOAT if zero else INT, v.shape, out)


def deal(a, b):
    """a?b: a different integers from 1 to b, in random order (the first a of a shuffle of 1..b).  a and b are single whole
    numbers with 0 <= a <= b <= 32767."""
    xa, xb = to_ints(a), to_ints(b)
    if len(xa) != 1 or len(xb) != 1:
        raise AplError('LENGTH ERROR')
    na, nb = xa[0], xb[0]
    if not 0 <= na <= nb <= 32767:
        raise AplError('DOMAIN ERROR')
    check_size(INT, nb)
    perm = list(range(1, nb + 1))
    for i in range(na):
        j = i + (rng_draw() * (nb - i) >> 16)
        perm[i], perm[j] = perm[j], perm[i]
    return vector(INT, perm[:na])


def f_pi_times(x):
    return f_mul(x, _k('pi'))


# k circle x: 0 sqrt(1-x^2), 1 sin, 2 cos, 3 tan, 4 sqrt(1+x^2), -1 asin, -2 acos, -3 atan (the hyperbolic ones,
# 5 to 7 and -4 to -7, are NONCE ERROR; anything else is DOMAIN ERROR)
CIRCLE_PROGS = {0: 'CIRC0', 1: 'SIN', 2: 'COS', 3: 'TAN', 4: 'CIRC4', -1: 'ASIN', -2: 'ACOS', -3: 'ATAN'}


def f_circle(k, x):
    n = f_whole(k)
    if n is None or not -7 <= n <= 7:
        raise AplError('DOMAIN ERROR')
    if n not in CIRCLE_PROGS:
        raise AplError('NONCE ERROR')
    return vm_run(MATH_PROGS[CIRCLE_PROGS[n]], x)


def _float_fn1(fn):
    def run(t, xs):
        if t == CHAR:
            raise AplError('DOMAIN ERROR')
        return FLOAT, [fn(to_f(t, x)) for x in xs]
    return run


def _float_fn2(fn):
    def run(ta, xs, tb, ys):
        if ta == CHAR or tb == CHAR:
            raise AplError('DOMAIN ERROR')
        return FLOAT, [fn(to_f(ta, x), to_f(tb, y)) for x, y in zip(xs, ys)]
    return run


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


def _same(ta, x, tb, y):
    """Are two elements equal?  Exactly, across BOOL, INT and FLOAT; a character equals only a character."""
    if ta == CHAR or tb == CHAR:
        return ta == tb and x == y
    if ta == FLOAT or tb == FLOAT:
        return to_f(ta, x) == to_f(tb, y)
    return x == y


def index_of(a, b):
    """a⍳b: for each element of b, its 1-based position in the vector a, or 1 + the length of a."""
    if a.rank != 1:
        raise AplError('RANK ERROR')
    out = []
    for y in b.data:
        k = next((i for i, x in enumerate(a.data) if _same(a.t, x, b.t, y)), len(a.data))
        out.append(k + 1)
    return Value(INT, b.shape, out)


def member(a, b):
    """a∊b: for each element of a, whether it is in b."""
    return Value(BOOL, a.shape, [int(any(_same(a.t, x, b.t, y) for y in b.data)) for x in a.data])


def grade(descending):
    """⍋v and ⍒v: the positions that put the vector v in order (equal elements keep their order)."""
    def run(v):
        if v.rank != 1:
            raise AplError('RANK ERROR')
        key = _fkey if v.t == FLOAT else (lambda x: x)
        order = sorted(range(v.count), key=lambda i: key(v.data[i]), reverse=descending)
        return vector(INT, [i + 1 for i in order])
    return run


def reverse(v):
    """⌽v: each row (the last axis) backwards; a scalar is unchanged."""
    if v.rank == 0:
        return v
    n = v.shape[-1]
    if v.rank == 1:
        return Value(v.t, v.shape, v.data[::-1])
    return Value(v.t, v.shape, [x for r in range(v.shape[0]) for x in v.data[r * n:(r + 1) * n][::-1]])


def rotate(a, v):
    """a⌽v: each row (the last axis) rotated to the left by a (to the right if negative). a is one whole
    number; a scalar v is unchanged.  A rotation with a value for each row is NONCE ERROR."""
    xs = to_ints(a)
    if len(xs) != 1:
        raise AplError('NONCE ERROR')
    if not -32768 <= xs[0] <= 32767:
        raise AplError('DOMAIN ERROR')              # the amount must fit int16
    if v.rank == 0 or v.count == 0:
        return v
    n = v.shape[-1]
    k = xs[0] % n
    rows = [v.data[r * n:(r + 1) * n] for r in range(v.count // n)]
    return Value(v.t, v.shape, [x for row in rows for x in row[k:] + row[:k]])


def _shape_args(a, b):
    """For take and drop: one whole number per axis of b (a scalar b counts as a vector of 1)."""
    xs = to_ints(a)
    dims = b.shape if b.rank else (1,)
    if len(xs) != len(dims):
        raise AplError('LENGTH ERROR')
    return xs, dims


def _resize(b, dims, out, start):
    """The array of shape out whose element (i, j) is b's element (start0+i, start1+j), or the fill
    element where that is outside b."""
    n = 1
    for o in out:
        if o > 65535:
            raise AplError('WS FULL')               # (a length that does not fit 16 bits)
        n *= o
    check_size(b.t, n)
    src = b.data
    fill = FILL[b.t]
    if len(dims) == 1:
        data = [src[start[0] + i] if 0 <= start[0] + i < dims[0] else fill for i in range(out[0])]
    else:
        data = [src[(start[0] + i) * dims[1] + start[1] + j]
                if 0 <= start[0] + i < dims[0] and 0 <= start[1] + j < dims[1] else fill
                for i in range(out[0]) for j in range(out[1])]
    return Value(b.t, tuple(out), data)


def take(a, b):
    """a↑b: the first (or, if negative, last) |a| elements along each axis, padded with 0 or blank."""
    xs, dims = _shape_args(a, b)
    return _resize(b, dims, [abs(x) for x in xs], [0 if x >= 0 else d + x for x, d in zip(xs, dims)])


def drop(a, b):
    """a↓b: without the first (or, if negative, last) |a| elements along each axis."""
    xs, dims = _shape_args(a, b)
    return _resize(b, dims, [max(0, d - abs(x)) for x, d in zip(xs, dims)], [max(0, x) for x in xs])


def replicate(a, b):
    """a/b: each element of the vector (or scalar) b repeated as many times as the matching
    element of a says.  a is non-negative whole numbers, one per element of b, or one for all,
    or (a one-element b) many for it; compress is the case of 0s and 1s.  A matrix b is done row by
    row (its columns are repeated).  Checks: a (RANK, DOMAIN), the lengths (LENGTH), negative counts
    (DOMAIN), size (WS FULL)."""
    xs = to_ints(a)
    n = b.shape[-1] if b.rank else 1
    m = b.shape[0] if b.rank == 2 else 1
    rows = [b.data[r * n:(r + 1) * n] for r in range(m)] if b.rank == 2 else [b.data]
    k = len(xs)
    if k != n:
        if k == 1:
            xs = xs * n
        elif n == 1:
            rows = [row * k for row in rows]
        else:
            raise AplError('LENGTH ERROR')
    if any(x < 0 for x in xs):
        raise AplError('DOMAIN ERROR')
    total = sum(xs)
    if total > 65535:
        raise AplError('WS FULL')
    check_size(b.t, m * total)
    out = [[d for d, x in zip(row, xs) for _ in range(x)] for row in rows]
    if b.rank == 2:
        return Value(b.t, (m, total), [x for row in out for x in row])
    return vector(b.t, out[0])


def expand(a, b):
    """a\\b: a vector of 0s and 1s (a) says where the elements of b go: each 1 takes the next element of b
    and each 0 has a fill (0 or a blank) instead.  b is a vector with one element per 1, or a scalar (used for
    all of them); a matrix b is expanded row by row (each row needs one element per 1).  Checks: a (RANK,
    DOMAIN), a's values (DOMAIN), lengths, size."""
    xs = to_ints(a)
    if any(x not in (0, 1) for x in xs):
        raise AplError('DOMAIN ERROR')
    ones = sum(xs)
    m = b.shape[0] if b.rank == 2 else 1
    n = b.shape[-1] if b.rank else 1
    if b.rank == 0:
        rows = [b.data * ones]
    else:
        if n != ones:
            raise AplError('LENGTH ERROR')
        rows = [b.data[r * n:(r + 1) * n] for r in range(m)] if b.rank == 2 else [b.data]
    if len(xs) > 65535:
        raise AplError('WS FULL')
    check_size(b.t, m * len(xs))
    out = []
    for row in rows:
        it = iter(row)
        out.append([next(it) if x else FILL[b.t] for x in xs])
    if b.rank == 2:
        return Value(b.t, (m, len(xs)), [x for row in out for x in row])
    return vector(b.t, out[0])


def without(a, b):
    """a~b: the elements of the vector a that are not in b (a scalar a counts as a vector of one)."""
    if a.rank > 1:
        raise AplError('RANK ERROR')
    return vector(a.t, [x for x in a.data if not any(_same(a.t, x, b.t, y) for y in b.data)])


def transpose(v):
    """⍉v: rows and columns exchanged; a scalar or vector is unchanged."""
    if v.rank < 2:
        return v
    m, n = v.shape
    return Value(v.t, (n, m), [v.data[i * n + j] for j in range(n) for i in range(m)])


def transpose_axes(a, v):
    """a⍉v: a names the axis of the result that each axis of v becomes: a permutation of 1..rank v
    (one entry per axis, LENGTH ERROR otherwise, DOMAIN ERROR if it is not a permutation)."""
    xs = to_ints(a)
    if len(xs) != v.rank:
        raise AplError('LENGTH ERROR')
    if sorted(xs) != list(range(1, v.rank + 1)):
        raise AplError('DOMAIN ERROR')
    return transpose(v) if xs == [2, 1] else v


def ravel(v):
    return vector(v.t, v.data)


def _catenate_rows(a, b):
    """a,b with a matrix among them: the columns of b follow those of a; a vector (one element per row) or
    a scalar (repeated) is a single column."""
    m = a.shape[0] if a.rank == 2 else b.shape[0]

    def cols(v):
        if v.rank == 2:
            if v.shape[0] != m:
                raise AplError('LENGTH ERROR')
            return v.shape[1], [v.data[r * v.shape[1]:(r + 1) * v.shape[1]] for r in range(m)]
        if v.rank == 1:
            if v.count != m:
                raise AplError('LENGTH ERROR')
            return 1, [[x] for x in v.data]
        return 1, [[v.data[0]] for _ in range(m)]
    (ka, ra), (kb, rb) = cols(a), cols(b)
    if a.count == 0:
        t = b.t
    elif b.count == 0:
        t = a.t
    else:
        t = join_type(a.t, b.t)
    if ka + kb > 65535:
        raise AplError('WS FULL')
    data = []
    for r in range(m):
        data += [convert(a.t, t, x) for x in ra[r]] + [convert(b.t, t, x) for x in rb[r]]
    check_size(t, m * (ka + kb))
    return Value(t, (m, ka + kb), data)


def catenate(a, b):
    if a.rank == 2 or b.rank == 2:
        return _catenate_rows(a, b)
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
          '>': (BOOL, 0), '≥': (BOOL, 1), '⌈': None, '⌊': None, '|': (INT, 0), '∧': (BOOL, 1), '∨': (BOOL, 0)}


def _reduce_row(glyph, dy, t, xs):
    if not xs:
        if _IDENT[glyph] is None:
            raise AplError('DOMAIN ERROR')              # no identity: the largest and smallest numbers do not exist
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
        if glyph in '-×÷⌈⌊|∧∨' and t == CHAR:
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
        if not rows:                                    # a matrix with no rows: an empty vector of the identity's type
            return Value(_IDENT[glyph][0] if _IDENT[glyph] else INT, v.shape[:-1], [])
        t = rows[0].t
        for r in rows[1:]:
            t = join_type(t, r.t)
        data = [convert(r.t, t, r.data[0]) for r in rows]
        return Value(t, v.shape[:-1], data)
    return red


def make_scan(glyph):
    """f\\v: along the last axis, element k is f/ of the first k+1 elements (each prefix
    reduced right to left, so - and ÷ alternate).  The result has the shape of v, its type
    the widest of the prefix results."""
    dy = PRIMS[glyph][1]

    def scan(v):
        if v.rank == 0:
            return v
        n = v.shape[-1]
        lead = v.shape[0] if v.rank == 2 else 1
        outs = [_reduce_row(glyph, dy, v.t, v.data[r * n:r * n + k])
                for r in range(lead) for k in range(1, n + 1)]
        if not outs:
            return Value(v.t, v.shape, [])
        t = outs[0].t
        for o in outs[1:]:
            t = join_type(t, o.t)
        return Value(t, v.shape, [convert(o.t, t, o.data[0]) for o in outs])
    return scan


def make_outer(glyph):
    """a∘.f b: f applied to every element of a with every element of b; the shape of the
    result is the shape of a followed by the shape of b (rank over 2 is LIMIT ERROR, and a
    result over 65535 elements is WS FULL before anything is computed)."""
    fn = _DY[glyph]

    def outer(a, b):
        shape = a.shape + b.shape
        if len(shape) > 2:
            raise AplError('LIMIT ERROR')
        n = len(a.data) * len(b.data)
        if n > 65535:
            raise AplError('WS FULL')
        t, data = fn(a.t, [x for x in a.data for _ in b.data], b.t, list(b.data) * len(a.data))
        return Value(t, shape, data)
    return outer


def axis_fn(fn, k, cat=False):
    """The (monadic, dyadic) pair fn applied along axis k of a matrix: these functions work along the last
    axis, so for axis 1 the matrices among the arguments are transposed before and, if the result is a
    matrix, after.  For axis 2 (of a matrix) and axis 1 of a vector fn is used as it is.  cat: for
    catenation the axis must exist in one of the two arguments (INDEX ERROR)."""
    mon, dy = fn

    def fix(r):
        return transpose(r) if k == 1 and r.rank == 2 else r

    def tr(v):
        return transpose(v) if k == 1 else v

    def d(a, v):
        if cat and max(a.rank, v.rank) < k:
            raise AplError('INDEX ERROR')
        return fix(dy(tr(a), tr(v)))
    return (lambda v: fix(mon(tr(v))), d)


def make_inner(fglyph, gglyph):
    """a f.g b: f/ of (a g b) over the last axis of a and the first axis of b.  The result has the shape
    of a without its last axis followed by the shape of b without its first (a scalar counts as extending
    to the other's length).  Every element is f/ of the g-products of a row of a and a column of b, so
    the rules for types, DOMAIN ERROR and WS FULL are those of the scalar functions and of reduce.  Inner
    axes of different lengths are LENGTH ERROR; a result with a zero dimension is NONCE ERROR."""
    dyf, dyg = PRIMS[fglyph][1], PRIMS[gglyph][1]

    def inner(a, b):
        na = a.shape[-1] if a.rank else 1
        nb = b.shape[0] if b.rank else 1
        if a.rank and b.rank and na != nb:
            raise AplError('LENGTH ERROR')
        n = nb if a.rank == 0 else na
        m = a.shape[0] if a.rank == 2 else 1
        p = b.shape[1] if b.rank == 2 else 1
        if m == 0 or p == 0:
            raise AplError('NONCE ERROR')
        shape = (a.shape[:1] if a.rank == 2 else ()) + (b.shape[1:] if b.rank == 2 else ())
        outs = []
        for i in range(m):
            row = a.data[i * n:(i + 1) * n] if a.rank else a.data * n
            for j in range(p):
                col = b.data[j::p] if b.rank == 2 else (b.data if b.rank else b.data * n)
                ys = Value(b.t, (n,), col)
                xs = Value(a.t, (n,), row)
                tv = dyg(xs, ys)
                outs.append(_reduce_row(fglyph, dyf, tv.t, tv.data))
        t = outs[0].t
        for o in outs[1:]:
            t = join_type(t, o.t)
        return Value(t, shape, [convert(o.t, t, o.data[0]) for o in outs])
    return inner


PRIMS = {}
for _g in SCALAR_DYADIC:
    _m = _MON.get(_g)
    PRIMS[_g] = (
        (lambda f: (lambda v: monadic_scalar(f, v)))(_m) if _m else _nonce,
        (lambda f: (lambda a, b: dyadic_scalar(f, a, b)))(_DY[_g]))
PRIMS['~'] = (lambda v: monadic_scalar(_m_not, v), without)
PRIMS['⌽'] = (reverse, rotate)
PRIMS['↑'] = (_nonce, take)
PRIMS['↓'] = (_nonce, drop)
PRIMS['⍳'] = (iota, index_of)
PRIMS['∊'] = (_nonce, member)
PRIMS['⍋'] = (grade(False), _nonce)
PRIMS['⍉'] = (transpose, transpose_axes)
MATH_DYADIC = '*⍟○!'                 # scalar functions that outer product takes but reduce, scan and inner product do not
_DY['*'] = _float_fn2(f_pow)
_DY['⍟'] = _float_fn2(f_log)
for _g, _m in (('*', f_exp), ('⍟', f_ln)):
    PRIMS[_g] = ((lambda f: (lambda v: monadic_scalar(_float_fn1(f), v)))(_m),
                 (lambda f: (lambda a, b: dyadic_scalar(f, a, b)))(_DY[_g]))
_DY['○'] = _float_fn2(f_circle)
PRIMS['○'] = (lambda v: monadic_scalar(_float_fn1(f_pi_times), v), lambda a, b: dyadic_scalar(_DY['○'], a, b))
_DY['!'] = _float_fn2(f_binom)
PRIMS['!'] = (lambda v: monadic_scalar(_float_fn1(f_fact), v), lambda a, b: dyadic_scalar(_DY['!'], a, b))
PRIMS['?'] = (roll, deal)
PRIMS['⍒'] = (grade(True), _nonce)
PRIMS['⍴'] = (shape_of, reshape)
PRIMS[','] = (ravel, catenate)


# =========================================================================
# Graphics: the multicolor bitmap and the quad functions (⎕GR ⎕INK ⎕PAL ⎕PLOT ⎕LINE ⎕BOX ⎕WAIT)
# =========================================================================
# The picture is 160 x 200 pixels of 2 bits, stored as the VIC-II reads it: 8000 bytes, cell (cx, cy) of 4 x 8 pixels at
# cy*320 + cx*8 with one byte per pixel row, the leftmost pixel in the top bits.  A pixel's value 0 shows the background
# colour, 1 and 2 the high and low nibble of the cell's byte in screen RAM, 3 the cell's colour RAM.  These are the
# machine's own memory (the 6502 keeps them at $E000, $CC00 and $D800), so the tests compare them byte for byte.
# The functions give no value (⎕KEY does).  ⎕GR, ⎕WAIT, ⎕SND and ⎕KEY work in text mode, the others need graphics mode (NO GRAPHICS); coordinates are floored and
# saturated to the int16 range; whole-argument checks come in the order: mode, CHAR arguments (right, left) DOMAIN,
# lengths (right, left) LENGTH, then the values (right, left) DOMAIN.
GFX_ROWS = 25
GFX_COLS = 40
GFX_DEFAULT_PAL = (0, 1, 2, 14)             # background, then the colours of pixel values 1, 2, 3
HIRES_DEFAULT_PAL = (0, 1)                  # the colours of pixel values 0 and 1 in hires mode
QUAD_NAMES = ['GR', 'PAL', 'INK', 'PLOT', 'LINE', 'BOX', 'WAIT', 'SND', 'SPD', 'SPR', 'SPC', '', 'KEY']        # tokens $A0 + i; the first 12 give no value, the rest do
QUAD_TOKEN = 0xA0
QUAD_NOVALUE = 12                            # the functions below this number give no value (the machine tells them by token < $AC)
SID_REGS = 25                               # $D400-$D418


class _Gfx:
    def __init__(self):
        self.reset()

    def reset(self):
        self.mode = 0                       # 0 text, 1 multicolor, 2 hires
        self.ink = 1
        self.bg = 0
        self.bitmap = bytearray(8000)
        self.scr = bytearray(GFX_ROWS * GFX_COLS)
        self.col = bytearray(GFX_ROWS * GFX_COLS)
        self.sid = bytearray(SID_REGS)      # what the SID's registers were last given (they cannot be read back)
        self.keys = []                      # the keys waiting, for ⎕KEY (the tests put them here; the machine reads the keyboard)
        self.vic = bytearray(0x30)          # the sprite registers of the VIC-II, by address - $D000 (the others are the mode's business)
        self.ptr = bytearray(range(96, 104))            # the sprite pointers ($CFF8 on): sprite n shows shape n
        self.shapes = bytearray(28 * 64)    # the 28 shapes of 64 bytes, in the RAM under the I/O area from $D800


GFX = _Gfx()


def gfx_reset():
    GFX.reset()


def _q_ints(v):
    """The elements as int16: floats are floored, and saturate at the ends of the range."""
    out = []
    for x in v.data:
        if v.t == FLOAT:
            f = f_to_fraction(x)
            x = -32768 if f < -32768 else 32767 if f >= 32768 else math.floor(f)
        out.append(x)
    return out


def _q_mode():
    if GFX.mode == 0:
        raise AplError('NO GRAPHICS')


def _q_types(*vs):
    for v in vs:
        if v.t == CHAR:
            raise AplError('DOMAIN ERROR')


def _q_one(v, lo, hi):
    """The one number in v, checked to lie in lo..hi."""
    _q_types(v)
    if v.count != 1:
        raise AplError('LENGTH ERROR')
    n = _q_ints(v)[0]
    if not lo <= n <= hi:
        raise AplError('DOMAIN ERROR')
    return n


def _q_range(vals, lo, hi):
    if any(not lo <= x <= hi for x in vals):
        raise AplError('DOMAIN ERROR')
    return vals


def q_gr(v):
    n = _q_one(v, 0, 2)
    if n == 0:
        GFX.mode = 0
        return None
    GFX.mode = n
    GFX.ink = 1
    GFX.bitmap = bytearray(8000)
    if n == 1:
        GFX.bg = GFX_DEFAULT_PAL[0]
        GFX.scr = bytearray([GFX_DEFAULT_PAL[1] << 4 | GFX_DEFAULT_PAL[2]] * (GFX_ROWS * GFX_COLS))
        GFX.col = bytearray([GFX_DEFAULT_PAL[3]] * (GFX_ROWS * GFX_COLS))
    else:                                   # hires: white on black; colour RAM is not used, and is left as it was
        GFX.bg = HIRES_DEFAULT_PAL[0]
        GFX.scr = bytearray([HIRES_DEFAULT_PAL[1] << 4 | HIRES_DEFAULT_PAL[0]] * (GFX_ROWS * GFX_COLS))
    return None


def _q_ncol():
    """The colours of a cell's palette: pixel values 0 to 3 in multicolor mode (the background is the same everywhere), 0 and 1 in hires."""
    return 4 if GFX.mode == 1 else 2


def q_ink(v):
    _q_mode()
    GFX.ink = _q_one(v, 0, _q_ncol() - 1)


def q_wait(v):
    _q_one(v, 0, 32767)


def q_pal(v):
    """Multicolor: bg c1 c2 c3, the background and the three colours of every cell. Hires: c0 c1 for every cell (and the border)."""
    _q_mode()
    _q_types(v)
    if v.count != _q_ncol():
        raise AplError('LENGTH ERROR')
    cols = _q_range(_q_ints(v), 0, 15)
    GFX.bg = cols[0]
    if GFX.mode == 1:
        GFX.scr = bytearray([cols[1] << 4 | cols[2]] * (GFX_ROWS * GFX_COLS))
        GFX.col = bytearray([cols[3]] * (GFX_ROWS * GFX_COLS))
    else:
        GFX.scr = bytearray([cols[1] << 4 | cols[0]] * (GFX_ROWS * GFX_COLS))


def q_pal2(a, v):
    """rows ⎕PAL c1 c2 c3 (hires: c0 c1): the colours of the cells in those rows (0 to 24); or the colours for each row, in a
    vector or matrix of as many times the numbers as rows (one row of the matrix per row)."""
    _q_mode()
    _q_types(v, a)
    k = 4 - GFX.mode                       # 3 colours per row in multicolor, 2 in hires
    uniform = v.count == k
    if not uniform and v.count != k * a.count:
        raise AplError('LENGTH ERROR')
    cols = _q_range(_q_ints(v), 0, 15)
    for i, r in enumerate(_q_range(_q_ints(a), 0, GFX_ROWS - 1)):
        cs = cols[:k] if uniform else cols[k * i:k * i + k]
        for c in range(GFX_COLS):
            if GFX.mode == 1:
                GFX.scr[r * GFX_COLS + c] = cs[0] << 4 | cs[1]
                GFX.col[r * GFX_COLS + c] = cs[2]
            else:
                GFX.scr[r * GFX_COLS + c] = cs[1] << 4 | cs[0]


def gfx_width():
    return 160 if GFX.mode == 1 else 320


def gfx_plot(x, y):
    """Set the pixel to the ink; a point off the screen is skipped."""
    if 0 <= x < gfx_width() and 0 <= y < 200:
        if GFX.mode == 1:
            a = (y >> 3) * 320 + (x >> 2) * 8 + (y & 7)
            sh = 6 - 2 * (x & 3)
            GFX.bitmap[a] = GFX.bitmap[a] & ~(3 << sh) & 0xFF | GFX.ink << sh
        else:
            a = (y >> 3) * 320 + (x >> 3) * 8 + (y & 7)
            sh = 7 - (x & 7)
            GFX.bitmap[a] = GFX.bitmap[a] & ~(1 << sh) & 0xFF | GFX.ink << sh


def q_plot(a, b):
    """x ⎕PLOT y: the points (x, y); either may be a single number for all the points of the other."""
    _q_mode()
    _q_types(b, a)
    nx, ny = a.count, b.count
    if nx == ny or ny == 1:
        n = nx
    elif nx == 1:
        n = ny
    else:
        raise AplError('LENGTH ERROR')
    xs, ys = _q_ints(a), _q_ints(b)
    for i in range(n):
        gfx_plot(xs[i if nx > 1 else 0], ys[i if ny > 1 else 0])


def _q_corners(a, b, lo, hi):
    _q_mode()
    _q_types(b, a)
    if b.count != 2 or a.count != 2:
        raise AplError('LENGTH ERROR')
    y1 = _q_range(_q_ints(b), lo, hi)
    x0 = _q_range(_q_ints(a), lo, hi)
    return x0[0], x0[1], y1[0], y1[1]


def q_line(a, b):
    """(x0 y0) ⎕LINE (x1 y1): Bresenham's line, end points within 4095 of the origin (so the arithmetic stays in 16 bits)."""
    x0, y0, x1, y1 = _q_corners(a, b, -4095, 4095)
    dx, dy = abs(x1 - x0), -abs(y1 - y0)
    sx, sy = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
    err = dx + dy
    while True:
        gfx_plot(x0, y0)
        if x0 == x1 and y0 == y1:
            break
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x0 += sx
        if e2 <= dx:
            err += dx
            y0 += sy


def q_box(a, b):
    """(x0 y0) ⎕BOX (x1 y1): the filled rectangle between the corners, both included."""
    x0, y0, x1, y1 = _q_corners(a, b, -32768, 32767)
    for y in range(max(min(y0, y1), 0), min(max(y0, y1), 199) + 1):
        for x in range(max(min(x0, x1), 0), min(max(x0, x1), gfx_width() - 1) + 1):
            gfx_plot(x, y)


def q_key(v):
    """⎕KEY n: the code of a key pressed (the KERNAL's, PETSCII), waiting up to n frames for one; 0 if none came."""
    _q_one(v, 0, 32767)
    return scalar(INT, GFX.keys.pop(0) if GFX.keys else 0)


def _q_whole(v):
    """The elements as whole numbers (DOMAIN otherwise): the sound's numbers reach 65535, past what ⎕PLOT's int16 reading takes."""
    out = []
    for x in v.data:
        n = f_whole(x) if v.t == FLOAT else x
        if n is None:
            raise AplError('DOMAIN ERROR')
        out.append(n)
    return out


def q_snd1(v):
    """⎕SND n: the master volume, 0 to 15 (written to the whole register: the filter is not used)."""
    _q_types(v)
    if v.count != 1:
        raise AplError('LENGTH ERROR')
    n = _q_range(_q_whole(v), 0, 15)[0]
    GFX.sid[0x18] = n


SND_COUNTS = (1, 2, 4, 6, 7)                # numbers a voice can be given: freq; + wave; + attack decay; + sustain release; + pulse width


def q_snd2(a, v):
    """voice ⎕SND freq wave attack decay sustain release width (the first 1, 2, 4, 6 or 7): voice 1 to 3; freq 0-65535, wave
    0-15 (1 triangle, 2 sawtooth, 4 pulse, 8 noise, sums mix them; 0 silences the voice: gate off), attack, decay, sustain,
    release 0-15, pulse width 0-4095.  Registers not given are left alone (so the AD and SR bytes are always given whole)."""
    _q_types(v, a)
    if a.count != 1 or v.count not in SND_COUNTS:
        raise AplError('LENGTH ERROR')
    voice = _q_range(_q_whole(a), 1, 3)[0]
    nums = _q_whole(v)
    limits = (65535, 15, 15, 15, 15, 15, 4095)
    for x, hi in zip(nums, limits):
        _q_range([x], 0, hi)
    base = 7 * (voice - 1)
    r = GFX.sid
    r[base], r[base + 1] = nums[0] & 255, nums[0] >> 8
    if len(nums) >= 2:
        r[base + 4] = nums[1] << 4 | (1 if nums[1] else 0)
    if len(nums) >= 4:
        r[base + 5] = nums[2] << 4 | nums[3]
    if len(nums) >= 6:
        r[base + 6] = nums[4] << 4 | nums[5]
    if len(nums) == 7:
        r[base + 2], r[base + 3] = nums[6] & 255, nums[6] >> 8


# --- sprites ----------------------------------------------------------------------------------------------------
# Eight sprites of 24 x 21 pixels.  Their shapes are kept, 28 of them, in the RAM under the I/O area ($D800-$DEFF: pointer 96 + slot; $DF00 up is left alone, where the REU's registers are),
# and a sprite shows the shape its pointer names.  Coordinates are the 320 x 200 screen's own physical pixels: x from -24 to 487,
# y from -50 to 205, (0, 0) being the top left of the picture (sprite registers count from 24 and 50).
SPR_ENABLE, SPR_MSB, SPR_XEXP, SPR_YEXP, SPR_PRIO, SPR_MULTI, SPR_COL0, SPR_MC1 = 0x15, 0x10, 0x1D, 0x17, 0x1B, 0x1C, 0x27, 0x25


def _q_bit(reg, n, on):
    GFX.vic[reg] = GFX.vic[reg] & ~(1 << n) & 255 | (1 << n if on else 0)


def q_spr1(v):
    """⎕SPR mask: which sprites are on (bit n for sprite n)."""
    _q_types(v)
    if v.count != 1:
        raise AplError('LENGTH ERROR')
    GFX.vic[SPR_ENABLE] = _q_range(_q_ints(v), 0, 255)[0]


def q_spc(v):
    """⎕SPC a b: the two colours multicolor sprites share."""
    _q_types(v)
    if v.count != 2:
        raise AplError('LENGTH ERROR')
    a, b = _q_range(_q_ints(v), 0, 15)
    GFX.vic[SPR_MC1], GFX.vic[SPR_MC1 + 1] = a, b


def q_spr2(a, v):
    """n ⎕SPR x y shape colour flags (the first 2, 3, 4 or 5): sprite n (0-7) is put at (x, y) and switched on; shape 0-27; colour 0-15;
    flags 0-15: 1 multicolor, 2 double width, 4 double height, 8 behind the picture.  Numbers are floored."""
    _q_types(v, a)
    if a.count != 1 or not 2 <= v.count <= 5:
        raise AplError('LENGTH ERROR')
    n = _q_range(_q_ints(a), 0, 7)[0]
    nums = _q_ints(v)
    for x, (lo, hi) in zip(nums, ((-24, 487), (-50, 205), (0, 27), (0, 15), (0, 15))):
        _q_range([x], lo, hi)
    x, y = nums[0] + 24, nums[1] + 50
    GFX.vic[2 * n], GFX.vic[2 * n + 1] = x & 255, y
    _q_bit(SPR_MSB, n, x > 255)
    if len(nums) >= 3:
        GFX.ptr[n] = 96 + nums[2]
    if len(nums) >= 4:
        GFX.vic[SPR_COL0 + n] = nums[3]
    if len(nums) == 5:
        _q_bit(SPR_MULTI, n, nums[4] & 1)
        _q_bit(SPR_XEXP, n, nums[4] & 2)
        _q_bit(SPR_YEXP, n, nums[4] & 4)
        _q_bit(SPR_PRIO, n, nums[4] & 8)
    _q_bit(SPR_ENABLE, n, True)


def q_spd(a, v):
    """slot ⎕SPD shape: a shape from 21 x 24 zeros and ones (a hires sprite), 21 x 12 numbers 0-3 (multicolor: two bits a pixel) or 63 bytes."""
    _q_types(v, a)
    if a.count != 1 or not (v.rank == 1 and v.count == 63 or v.rank == 2 and tuple(v.shape) in ((21, 24), (21, 12))):
        raise AplError('LENGTH ERROR')
    slot = _q_range(_q_ints(a), 0, 27)[0]
    nums = _q_ints(v)
    if v.rank == 1:
        data = _q_range(nums, 0, 255)
    elif v.shape[1] == 24:
        bits = _q_range(nums, 0, 1)
        data = [sum(bits[r * 24 + c * 8 + k] << 7 - k for k in range(8)) for r in range(21) for c in range(3)]
    else:
        px = _q_range(nums, 0, 3)
        data = [sum(px[r * 12 + c * 4 + k] << 6 - 2 * k for k in range(4)) for r in range(21) for c in range(3)]
    GFX.shapes[64 * slot:64 * slot + 63] = bytes(data)


QUAD_PRIMS = {'⎕GR': (q_gr, _nonce), '⎕PAL': (q_pal, q_pal2), '⎕INK': (q_ink, _nonce), '⎕PLOT': (_nonce, q_plot),
              '⎕LINE': (_nonce, q_line), '⎕BOX': (_nonce, q_box), '⎕WAIT': (q_wait, _nonce), '⎕SND': (q_snd1, q_snd2), '⎕SPD': (_nonce, q_spd), '⎕SPR': (q_spr1, q_spr2), '⎕SPC': (q_spc, _nonce),
              '⎕KEY': (q_key, _nonce)}
PRIMS.update(QUAD_PRIMS)


def _glyph_of(tok):
    """The glyph (or ⎕NAME) of a function token."""
    if tok >= QUAD_TOKEN:
        return '⎕' + QUAD_NAMES[tok - QUAD_TOKEN]
    return PRIM_GLYPHS[tok - 0x80]


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
T_EMPTY = 12                    # the empty numeric vector: one byte, though a literal would be six
T_LPAR, T_RPAR, T_LBRK, T_RBRK, T_ASSIGN, T_BRANCH, T_DIAMOND, T_SEMI = range(3, 11)
SYNTAX_TOKENS = {'(': T_LPAR, ')': T_RPAR, '[': T_LBRK, ']': T_RBRK,
                 '←': T_ASSIGN, '→': T_BRANCH, '⋄': T_DIAMOND, ';': T_SEMI}
PRIM_GLYPHS = '+-×÷=≠<≤>≥⍳⍴,⌈⌊|∧∨~⌽↑↓∊⍋⍒⍉*⍟○!?'
OP_GLYPHS = '/\\¨.∘⍤'
# Charset codes for the non-ASCII glyphs; ASCII characters keep their ASCII code.
# The 6502 tokenizer receives lines in this encoding. Glyphs that are also
# tokens use their token code.
GLYPH_CODES = {'⍟': 0xA2, '○': 0xA3, '⍉': 0xA1, '∊': 0x9E, '⍋': 0x9F, '⍒': 0xA0, '⌽': 0x9B, '↑': 0x9C, '↓': 0x9D, '∧': 0x99, '∨': 0x9A, '⌈': 0x8D, '⌊': 0x8E, '×': 0x82, '÷': 0x83, '≠': 0x85, '≤': 0x87, '≥': 0x89,
               '⍳': 0x8A, '⍴': 0x8B, '¨': 0xC2, '∘': 0xC4, '⍤': 0xC5,
               '¯': 0x90, '←': 0x91, '→': 0x92, '⋄': 0x93, '⍬': 0x94,
               '⍝': 0x95, '∆': 0x96, '⍙': 0x97, '∇': 0x98, '⎕': 0xA4}


def char_code(ch):
    if ord(ch) < 128:
        return ord(ch)
    if ch in GLYPH_CODES:
        return GLYPH_CODES[ch]
    raise AplError('DOMAIN ERROR')


def encode_line(line):
    return bytes(char_code(c) for c in line)


QUAD_RE = re.compile(r'[A-Za-z]+')
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
                out.append(T_EMPTY)
                i += 1
            elif c == '⎕':
                m = QUAD_RE.match(line, i + 1)
                if not m or m.group().upper() not in QUAD_NAMES:
                    raise AplError('SYNTAX ERROR')
                out.append(QUAD_TOKEN + QUAD_NAMES.index(m.group().upper()))
                i = m.end()
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
            elif c == T_EMPTY:
                toks.append((T_LIT, vector(INT, [])))
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
                    val, i = self._axis(toks, j, i, val)    # an axis after a function: +/[1]A  ⌽[1]A
                    continue
                raise AplError('SYNTAX ERROR')
            elif c >= 0xC0:
                if i == 0:
                    raise AplError('SYNTAX ERROR')
                pc = toks[i - 1][0]
                if self._isv(toks[i - 1]):                  # a/b: replicate and compress
                    if OP_GLYPHS[c - 0xC0] not in '/\\':
                        raise AplError('NONCE ERROR')
                    left, i = self._operand(toks, i - 1)
                    if left is None:
                        raise AplError('VALUE ERROR')
                    val = (replicate if OP_GLYPHS[c - 0xC0] == '/' else expand)(left, val)
                    continue
                if not 0x80 <= pc < 0xC0:
                    raise AplError('SYNTAX ERROR')
                g = OP_GLYPHS[c - 0xC0]
                pg = _glyph_of(pc)
                if g not in '/\\' or pg not in SCALAR_DYADIC:
                    raise AplError('NONCE ERROR')
                fn = ((make_reduce if g == '/' else make_scan)(pg), _nonce)
                i -= 2
                val = self._apply(fn, toks, i, val)
                i = self._pos
            elif c >= 0x80 and i >= 2 and toks[i - 1][0] == 0xC3 and 0x80 <= toks[i - 2][0] < 0xC0:
                pf = _glyph_of(toks[i - 2][0])     # a f.g b: inner product
                pg = _glyph_of(c)
                if pf not in SCALAR_DYADIC or pg not in SCALAR_DYADIC:
                    raise AplError('NONCE ERROR')
                i -= 3
                if i < 0 or not self._isv(toks[i]):
                    raise AplError('SYNTAX ERROR')
                left, i = self._operand(toks, i)
                if left is None:
                    raise AplError('VALUE ERROR')
                val = make_inner(pf, pg)(left, val)
            elif c >= 0x80 and i >= 2 and toks[i - 1][0] == 0xC3 and toks[i - 2][0] == 0xC4:
                pg = _glyph_of(c)                  # a∘.f b: outer product
                if pg not in SCALAR_DYADIC + MATH_DYADIC:
                    raise AplError('NONCE ERROR')
                i -= 3
                if i < 0 or not self._isv(toks[i]):
                    raise AplError('SYNTAX ERROR')
                left, i = self._operand(toks, i)
                if left is None:
                    raise AplError('VALUE ERROR')
                val = make_outer(pg)(left, val)
            elif c >= 0x80:
                fn = PRIMS[_glyph_of(c)]
                i -= 1
                val = self._apply(fn, toks, i, val)
                i = self._pos
                if val is None and not (top and i < 0):
                    raise AplError('VALUE ERROR')
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

    def _axis_end(self, toks, i):
        """Is the ']' at i the end of an axis (its '[' follows a function) and not of an index?"""
        if toks[i][0] != T_RBRK:
            return False
        j = self._match(toks, i, T_RBRK, T_LBRK)
        return j > 0 and toks[j - 1][0] >= 0x80

    def _axis(self, toks, j, i, val):
        """f/[k]v, f\\[k]v, ⌽[k]v, a⌽[k]v, a/[k]v, a\\[k]v and a,[k]v: the brackets at j..i follow a
        function; val is the right argument.  k is a scalar (RANK ERROR) whole number (DOMAIN ERROR),
        1 or 2, and not above the rank of val (INDEX ERROR; for catenation the axis may be one
        of the left argument, which is checked when it is applied); then the function must be one
        that takes an axis (NONCE ERROR otherwise)."""
        kv = self.eval_tokens(toks[j + 1:i])
        if kv.rank != 0:
            raise AplError('RANK ERROR')
        k = to_ints(kv)[0]
        tk = toks[j - 1][0]
        cat = tk < 0xC0 and _glyph_of(tk) == ','
        if k not in (1, 2) or (val.rank < k and not cat):
            raise AplError('INDEX ERROR')
        if tk >= 0xC0:                                          # an operator: f/ f\ (its function) or a/ a\ (a value)
            if j < 2:
                raise AplError('SYNTAX ERROR')
            g = OP_GLYPHS[tk - 0xC0]
            if 0x80 <= toks[j - 2][0] < 0xC0:
                pg = _glyph_of(toks[j - 2][0])
                if g not in '/\\' or pg not in SCALAR_DYADIC:
                    raise AplError('NONCE ERROR')
                fn, pos = ((make_reduce if g == '/' else make_scan)(pg), _nonce), j - 2
            elif self._isv(toks[j - 2]):
                if g not in '/\\':
                    raise AplError('NONCE ERROR')
                fn, pos = (_nonce, replicate if g == '/' else expand), j - 1
            else:
                raise AplError('SYNTAX ERROR')
        else:
            pg = _glyph_of(tk)
            if pg not in ('⌽', ','):
                raise AplError('NONCE ERROR')
            fn, pos = PRIMS[pg], j - 1
            if cat:
                fn = (_nonce, fn[1])                             # ,[k]v is not the ravel
        val = self._apply(axis_fn(fn, k, cat), toks, pos - 1, val)
        return val, self._pos

    def _apply(self, fn, toks, i, right):
        """Apply fn monadically or dyadically; leaves new index in self._pos (set
        after the call, which may run nested evaluations)."""
        if i >= 0 and self._isv(toks[i]) and not self._axis_end(toks, i):
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
        ('2/3', '3 3'),
        ('1 0 1/4 5 6', '4 6'),
        ('1 0 1/\'abc\'', 'ac'),
        ('0/5', ''),
        ('2 0 1/1 2 3', '1 1 3'),
        ('1 2/3', '3 3 3'),
        ('2/1 2', '1 1 2 2'),
        ('1 1/1 2 3', '!LENGTH ERROR'),
        ('¯1/5', '!DOMAIN ERROR'),
        ('1.5/5', '!DOMAIN ERROR'),
        ("'a'/5", '!DOMAIN ERROR'),
        ('(2 2⍴1)/5', '!RANK ERROR'),
        ('1/2 2⍴1', '1 1|1 1'), ('1 0 1/2 3⍴⍳6', '1 3|4 6'), ('2/2 3⍴⍳6', '1 1 2 2 3 3|4 4 5 5 6 6'), ('1 0 1/[1]3 2⍴⍳6', '1 2|5 6'), ('0 0 0/2 3⍴⍳6', '|'),
        ('(2 3⍴⍳6),(2 2⍴7 8 9 10)', '1 2 3 7  8|4 5 6 9 10'), ('(2 3⍴⍳6),1 2', '1 2 3 1|4 5 6 2'), ('1 2,2 3⍴⍳6', '1 1 2 3|2 4 5 6'), ('(2 3⍴⍳6),5', '1 2 3 5|4 5 6 5'),
        ('(2 2⍴1 2 3 4),[1]5 6', '1 2|3 4|5 6'), ('1 2,[1]2 2⍴3 4 5 6', '1 2|3 4|5 6'), ('(2 2⍴1),[2]1 2', '1 1 1|1 1 2'), ('1 2,[2]3 4', '!INDEX ERROR'),
        ('(2 3⍴⍳6),1 2 3', '!LENGTH ERROR'), ("(2 2⍴1),'a'", '!DOMAIN ERROR'), ('(2 2⍴1),(3 2⍴1)', '!LENGTH ERROR'),
        ('1 0 1\\1 2 3', '!LENGTH ERROR'),
        ('(1 0 1=1 2 1)/⍳3', '1 3'),
        ('+/2/1 2', '6'),
        ('A←3 ⋄ A/⍳2', '1 1 1 2 2 2'),
        ('40000/1', '!WS FULL'),
        ('⍬/⍬', ''),
        ('1 1 1/⍬', '!LENGTH ERROR'),
        ('⍳¯1', '!DOMAIN ERROR'),
        ('10 20 30⍳20', '2'), ('10 20 30⍳5 30 10', '4 3 1'), ('10 20 30⍳2 2⍴10 20 30 40', '1 2|3 4'), ("'abc'⍳'cab'", '3 1 2'),
        ("'abc'⍳'z'", '4'), ('1 2 3⍳1.5-0.5', '1'), ('1.5 2⍳2 1.5', '2 1'), ("1 2 3⍳'a'", '4'), ("'a'⍳1", '!RANK ERROR'),
        ('⍬⍳1 2', '1 1'), ('1 2⍳⍬', ''), ('5⍳5', '!RANK ERROR'), ('1 2 3∊2', '0 1 0'), ("'abc'∊'cd'", '0 0 1'),
        ('(2 2⍴1 2 3 4)∊2 4', '0 1|0 1'), ('⍬∊1', ''), ('1∊⍬', '0'), ('1 2∊1.5-0.5 3', '1 0'),
        ('⍋3 1 2', '2 3 1'), ('⍒3 1 2', '1 3 2'), ('⍋3 1 2 1', '2 4 3 1'), ('⍒3 1 2 1', '1 3 2 4'), ("⍋'hello'", '2 1 3 4 5'),
        ('⍋1.5 ¯2 0 1.5', '2 3 1 4'), ('⍋⍬', ''), ('⍋5', '!RANK ERROR'), ('⍋2 2⍴1', '!RANK ERROR'), ('⍋32767 ¯32768 0', '2 3 1'),
        ('⌽1 2 3', '3 2 1'), ('⌽5', '5'), ('⌽2 3⍴⍳6', '3 2 1|6 5 4'), ("⌽'abc'", 'cba'), ('⌽⍬', ''),
        ('1⌽1 2 3 4', '2 3 4 1'), ('¯1⌽1 2 3 4', '4 1 2 3'), ('5⌽1 2 3 4', '2 3 4 1'), ('1⌽2 3⍴⍳6', '2 3 1|5 6 4'),
        ('1⌽5', '5'), ('1 2⌽1 2 3', '!NONCE ERROR'), ('(2 3⍴1)⌽1 2 3', '!RANK ERROR'), ('1.5⌽1 2', '!DOMAIN ERROR'),
        ('3↑1 2 3 4 5', '1 2 3'), ('¯3↑1 2 3 4 5', '3 4 5'), ('7↑1 2 3', '1 2 3 0 0 0 0'), ('¯7↑1 2 3', '0 0 0 0 1 2 3'),
        ('3↑5', '5 0 0'), ("5↑'ab'", 'ab   '), ('2 2↑3 3⍴⍳9', '1 2|4 5'), ('¯2 ¯2↑3 3⍴⍳9', '5 6|8 9'),
        ('2↑3 3⍴⍳9', '!LENGTH ERROR'), ('3↓1 2 3 4 5', '4 5'), ('¯3↓1 2 3 4 5', '1 2'), ('7↓1 2 3', ''),
        ('1 1↓3 3⍴⍳9', '5 6|8 9'), ('⍴0 5↑3 3⍴⍳9', '0 5'), ('1.5↑1', '!DOMAIN ERROR'), ('100000↑1', '!WS FULL'),
        ('↑1', '!NONCE ERROR'), ('(2 2⍴1)↑1', '!RANK ERROR'),
        ('3⌈5', '5'), ('3⌊5', '3'), ('1 5 3⌈4', '4 5 4'), ('1 5 3⌊4', '1 4 3'), ('1.5⌈2', '2'), ('1.5⌊2', '1.5'),
        ("'a'⌈1", '!DOMAIN ERROR'), ('(2 3⍴⍳6)⌈3', '3 3 3|4 5 6'), ('1 0⌈0 1', '1 1'),
        ('⌈2.5', '3'), ('⌊2.5', '2'), ('⌈¯2.5', '¯2'), ('⌊¯2.5', '¯3'), ('⌊1e10', '1E10'), ('⌊1e10 1.5', '1E10 1'),
        ('⌊1.5 ¯1.5 3', '1 ¯2 3'), ('⌊¯0.3', '¯1'), ('⌈¯0.3', '0'), ("⌊'a'", '!DOMAIN ERROR'), ('⌈1 2 3', '1 2 3'),
        ('|¯5', '5'), ('|5 ¯3 0', '5 3 0'), ('|¯32768', '32768'), ('|1.5 ¯2.5', '1.5 2.5'), ("|'a'", '!DOMAIN ERROR'),
        ('3|7', '1'), ('3|¯7', '2'), ('¯3|7', '¯2'), ('¯3|¯7', '¯1'), ('0|5', '5'), ('3|0', '0'),
        ('1|2.5', '0.5'), ('1|¯2.5', '0.5'), ('¯1|2.5', '¯0.5'), ('0.5|1.3', '0.3'), ('3|7.5', '1.5'),
        ('¯32768|1', '¯32767'), ('5|1 2 3 4 5 6 7', '1 2 3 4 0 1 2'), ('1 2 3|10', '0 0 1'), ("3|'a'", '!DOMAIN ERROR'),
        ('1E¯30|1E30', '!DOMAIN ERROR'), ('1E30|1E¯30', '1E¯30'),
        ('⌈/1 5 3', '5'), ('⌊/1 5 3', '1'), ('⌈/⍬', '!DOMAIN ERROR'), ('|/⍬', '0'), ('⌊/2 3⍴4 1 5 9 2 7', '1 2'),
        ('5|⌈/3 9 7', '4'), ("⌈/'ab'", '!DOMAIN ERROR'),
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
        ('+/[1]A', '95'),
        ('*0', '1'), ('*1', '2.718'), ('*¯1', '0.3679'), ('*89', '!DOMAIN ERROR'), ('*¯200', '0'), ('⍟1', '0'), ('⍟¯1', '!DOMAIN ERROR'), ('⍟0', '!DOMAIN ERROR'), ('⍟10', '2.303'),
        ('2*10', '1024'), ('2*¯1', '0.5'), ('0*0', '1'), ('0*¯1', '!DOMAIN ERROR'), ('¯2*3', '¯8'), ('¯2*0.5', '!DOMAIN ERROR'), ('16*0.5', '4'), ('2⍟8', '3'), ('1⍟5', '!DOMAIN ERROR'),
        ('(⍳3)∘.*⍳3', '1 1  1|2 4  8|3 9 27'), ('○1', '3.142'), ('1○0', '0'), ('2○0', '1'), ('¯3○1', '0.7854'), ('¯1○2', '!DOMAIN ERROR'), ('5○1', '!NONCE ERROR'), ('1.5○1', '!DOMAIN ERROR'), ('0○1', '0'), ('4○0', '1'), ("'a'*2", '!DOMAIN ERROR'), ('*/1 2', '!NONCE ERROR'), ('1 2+.*3 4', '!NONCE ERROR'), ('?1', '1'), ('?1 1 1', '1 1 1'), ('⍴?100⍴6', '100'), ('∧/(?100⍴6)∊⍳6', '1'), ('0?5', ''), ('1?1', '1'), ('+/3?3', '6'), ('?32768', '!DOMAIN ERROR'), ('5?3', '!DOMAIN ERROR'), ('1 2?5', '!LENGTH ERROR'), ('?¯1', '!DOMAIN ERROR'), ('⍴?0 5', '2'),
        ('!5', '120'), ('!0', '1'), ('!34', '!DOMAIN ERROR'), ('!2.5', '!DOMAIN ERROR'), ('!¯1', '!DOMAIN ERROR'), ('2!5', '10'), ('6!5', '0'), ('0!0', '1'), ('(⍳4)∘.!⍳4', '1 2 3 4|0 1 3 6|0 0 1 4|0 0 0 1'),
        ('+/[1]2 3⍴⍳6', '5 7 9'), ('+/[2]2 3⍴⍳6', '6 15'), ('+\\[1]2 3⍴⍳6', '1 2 3|5 7 9'), ('⌽[1]2 3⍴⍳6', '4 5 6|1 2 3'), ('1⌽[1]2 3⍴⍳6', '4 5 6|1 2 3'),
        ('+/[1]⍳4', '10'), ('+/[2]⍳4', '!INDEX ERROR'), ('+/[0]2 3⍴⍳6', '!INDEX ERROR'), ('+/[1.5]2 3⍴⍳6', '!DOMAIN ERROR'), ('+/[1 2]2 3⍴⍳6', '!RANK ERROR'),
        ('+[1]2 3⍴⍳6', '!NONCE ERROR'), ('1 0/[1]2 3⍴⍳6', '1 2 3'), ('⌽[1]', '!SYNTAX ERROR'), ('2×+/[1]2 3⍴⍳6', '10 14 18'), ('+/[1]⌽2 3⍴⍳6', '9 7 5'),
        ('⍉2 3⍴⍳6', '1 4|2 5|3 6'), ('⍉⍳3', '1 2 3'), ('⍉5', '5'), ('2 1⍉2 3⍴⍳6', '1 4|2 5|3 6'), ('1 2⍉2 3⍴⍳6', '1 2 3|4 5 6'),
        ('1 1⍉2 2⍴⍳4', '!DOMAIN ERROR'), ('2 1⍉⍳3', '!LENGTH ERROR'), ('⍬⍉5', '5'), ("⍉'ab'", 'ab'), ('⍉⍉2 3⍴⍳6', '1 2 3|4 5 6'),
        ('(⍳5)~2 4', '1 3 5'), ("'hello'~'l'", 'heo'), ('3~1 2 3', ''), ('1 2 3~⍬', '1 2 3'), ('(2 2⍴1)~1', '!RANK ERROR'), ('1 2 3~2.0', '1 3'),
        ('1 0 1\\7 8', '7 0 8'), ('1 0 1 1\\1 2 3', '1 0 2 3'), ("1 0 1\\'ab'", 'a b'), ('1 0 1\\5', '5 0 5'), ('0 0\\⍬', '0 0'),
        ('1 2\\3 4', '!DOMAIN ERROR'), ('1 0 1\\2 2⍴1', '1 0 1|1 0 1'), ('1 0 1\\2 3⍴1', '!LENGTH ERROR'), ('(2 2⍴1)\\1 2', '!RANK ERROR'),
        ('+\\1 2 3 4', '1 3 6 10'), ('-\\1 2 3 4', '1 ¯1 2 ¯2'), ('×\\⍳5', '1 2 6 24 120'), ('+\\2 3⍴⍳6', '1 3  6|4 9 15'),
        ('⌈\\3 1 4 1 5', '3 3 4 4 5'), ('+\\⍬', ''), ('+\\5', '5'), ('+\\32767 1 1', '32767 32768 32769'),
        ("+\\'ab'", '!DOMAIN ERROR'), ('1 2+\\3', '!NONCE ERROR'), ('1 2\\3', '!DOMAIN ERROR'),
        ('1 2 3∘.×1 2 3', '1 2 3|2 4 6|3 6 9'), ('(⍳3)∘.=⍳3', '1 0 0|0 1 0|0 0 1'), ('1 2∘.+10 20 30', '11 21 31|12 22 32'),
        ('2∘.+3', '5'), ('2∘.+1 2', '3 4'), ('(2 2⍴1)∘.+1 2', '!LIMIT ERROR'), ('∘.+1', '!SYNTAX ERROR'),
        ('1 2∘.⍳3', '!NONCE ERROR'), ('(⍳300)∘.+⍳300', '!WS FULL'),
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
