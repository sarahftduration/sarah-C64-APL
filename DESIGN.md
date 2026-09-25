# APL for the Commodore 64: design notes

Living spec. `apl64.py` is the executable reference model; where this file
and the model disagree, the model wins and this file has a bug.

## Goals and scope

- Self-hosted, interactive APL on a stock C64 (6510, ~1 MHz, 64 KB).
- A **tokenizing interpreter** (like BASIC), not a native-code compiler.
  APL is dynamically typed and array-shaped, so compiled code would mostly
  be calls into a runtime and would cost RAM for little speedup.
- Cross-developed on a modern machine; it does not need to be *built* on the C64.
- 6502 assembly runtime, tested differentially against the Python model.

## Memory plan (with BASIC ROM banked out via $01)

Roughly $0801-$CFFF (about 50 KB) usable. KERNAL stays enabled for keyboard
scanning and disk I/O (`)SAVE` / `)LOAD` are KERNAL calls).

- Runtime code at the bottom (about 12-16 KB when done)
- Symbol table and tokenized function bodies above it
- Array heap grows up, value stack grows down from the top
- Heap uses a **handle table** (one slot per array, 2 bytes) and a
  **mark-compact GC**; compaction updates one pointer per array.

## Element types (homogeneous arrays, no mixing)

| Tag | Type  | Bytes | Notes |
|-----|-------|-------|-------|
| 0   | BOOL  | 1     | 0 or 1, one byte per element (no bit packing yet) |
| 1   | CHAR  | 1     | code into the custom charset |
| 2   | INT   | 2     | signed 16-bit, little-endian |
| 3   | FLOAT | 3     | float24, below |

Mixing types in one array (`1 'a'`, `'a',1`) is a DOMAIN ERROR. Numeric
types widen along BOOL -> INT -> FLOAT. CHAR never mixes with numbers.
An empty vector keeps its type (`''` is CHAR, `⍬` is INT); in catenate an
empty operand adopts the other operand's type.

## float24

```
byte 0: exponent, excess-128, 0 means the value zero
byte 1: sign bit | top 7 bits of the stored fraction
byte 2: low 8 bits of the stored fraction
value = (-1)^s * (0x8000 | fraction15) / 2^16 * 2^(exp-128)
```

- 16-bit significand (hidden leading 1), about 4.8 decimal digits.
- Range about 1.5e-39 to 1.7e38. Every int16 is exact.
- + - x / are **correctly rounded, round-to-nearest-even** (6502: guard,
  round and sticky bits). Underflow flushes to zero. Overflow is DOMAIN ERROR.
  No NaN, no Inf, no negative zero.
- Ordering: `(exp<<16 | fraction)` is monotonic in magnitude, so exact
  compare is a sign-magnitude compare of the raw bytes.
- Comparison tolerance (floats only; int/int is exact):
  `a = b` iff `a == b`, or `a - b == 0`, or
  `exp(a-b) <= max(exp(a), exp(b)) - 14`.
  `< <= > >=` apply that test first, then compare exactly.
  0 is never tolerantly equal to a nonzero value.
- **Print precision (⎕PP) defaults to 4**, not 5: 10^4 < 2^15, so a 4-digit
  decimal always survives parse -> float24 -> print. At 5 digits the noise
  shows (0.001 prints as 0.00099999). Whole-valued floats up to 65536 print
  exactly.
- Parse and print use a table of powers of ten. They are **not** required to
  be bit-exact against the model (1 ulp allowed); everything else is.

## Arithmetic rules

- `+ - ×` on BOOL/INT run in int16 optimistically. If **any** result element
  leaves int16, the whole primitive is redone in float24. (6502: the V flag
  catches add/sub overflow; for multiply, check whether the upper bytes of the
  32-bit product are just sign extension.)
- `÷` always yields FLOAT. `0÷0` is 1; `x÷0` is DOMAIN ERROR.
- Comparisons yield BOOL. CHAR supports only `=` and `≠` (char vs number is
  0 / 1, not an error); other CHAR arithmetic or ordering is DOMAIN ERROR.
- Scalar extension only (a scalar with an array); otherwise RANK ERROR or
  LENGTH ERROR.
- `f/` reduces right to left (`-/1 2 3` is 2). `+/` accumulates **exactly and
  rounds once**. Empty reduce returns the identity (+ 0, - 0, × 1, ÷ 1,
  = 1, ≠ 0, < 0, ≤ 1, > 0, ≥ 1). Reduce on a matrix works along the last axis.
- `⍳n` is INT, origin 1 (⎕IO=1). `⍴` monadic gives an INT shape vector;
  dyadic reshape cycles data and fills an empty right argument with 0 or space.
- Arrays are limited to `WS_BYTES` (45000 in the model) and 65535 elements:
  WS FULL.

## Heap array layout (also the literal body in the token stream)

```
byte 0:    type (bits 0-1) | rank (bits 2-3)
bytes 1-2: element count, 16-bit little-endian
then 2 bytes (little-endian) per axis, rank <= 2
then the data, element width from the type
```

INT is two's complement little-endian. FLOAT is the three bytes above in
order (exp, sign|hi7, lo8).

## Value cells and the heap (6502)

A value is a fixed **4-byte cell**: `tag, b1, b2, b3`. The tag is
`type | rank<<2`, the same byte as an array header. Rank 0 is a scalar with its
data in `b1..b3`, so scalar code never touches the allocator. Rank 1 or 2 is an
array with its heap handle in `b1`. Tag `$80` marks an undefined variable.
Arrays are immutable and shared: assignment copies the cell, not the array.

The heap is `[handle][array header + data]` blocks laid end to end, each block
holding exactly the array layout below, so a token literal, a heap block and
`Value.to_bytes()` are the same bytes. There are **256 handles** (a 1-byte
handle indexes a table of 2-byte addresses; a 257th live array is LIMIT ERROR).
Nothing is freed explicitly. When an allocation does not fit, or no handle is
free, `gc` marks everything reachable from the value stack, the variable table
and one pinned handle (the array just allocated), then slides live blocks down
and updates one table entry each. Any allocation may therefore move arrays: a
primitive allocates its result first and re-derives operand data pointers after.

Per-array size is limited to `wsmax` bytes (45000, the model's `WS_BYTES`), and
the heap itself is the real limit; both raise WS FULL.

## Character encoding

CHAR data and the tokenizer's input use one byte per character: ASCII keeps
its ASCII code, and the APL glyphs get fixed codes (`GLYPH_CODES` in the
model). Glyphs that are also tokens use their token code.

| Code | Glyph | Code | Glyph | Code | Glyph |
|------|-------|------|-------|------|-------|
| `$82` | `×` | `$8A` | `⍳` | `$91` | `←` |
| `$83` | `÷` | `$8B` | `⍴` | `$92` | `→` |
| `$85` | `≠` | `$C2` | `¨`  | `$93` | `⋄` |
| `$87` | `≤` | `$C4` | `∘`  | `$94` | `⍬` |
| `$89` | `≥` | `$C5` | `⍤`  | `$95` | `⍝` |
| `$90` | `¯` | `$96` | `∆`  | `$97` | `⍙` |

A character with no code is a DOMAIN ERROR inside a string and a SYNTAX ERROR
elsewhere. Input lines are at most 255 bytes and end with `$00`.

## Token stream

One line ends with `$00`.

| Code | Meaning |
|------|---------|
| `$00` | End of line |
| `$01` | Literal, followed by an array body (layout above) |
| `$02` | Name, followed by a 1-byte symbol index (max 256 names) |
| `$03-$0A` | `(  )  [  ]  ←  →  ⋄  ;` |
| `$10-$7F` | Reserved (system functions, ⎕ names, control keywords) |
| `$80+i` | Primitive function, `i` indexes `+-×÷=≠<≤>≥⍳⍴,` |
| `$C0+i` | Operator, `i` indexes `/\¨.∘⍤` |

- Number strands and strings are folded into **one literal** by the tokenizer.
  Narrowest type wins: all 0/1 is BOOL; all whole numbers in int16 is INT;
  anything else is FLOAT. Adjacent numeric and character literals are a
  DOMAIN ERROR at tokenize time.
- One token per glyph. The evaluator decides monadic or dyadic from the left
  context, and looks up the pair in the primitive table.
- Comments (`⍝`) are stripped on entry. If we want to keep them for function
  listing, store them as a `$10` token that the evaluator skips.
- Negative numbers use `¯` inside numeric literals. `-` is always the function.

## Evaluator

No parse tree. Scan tokens right to left:

1. The rightmost token must be a value (literal, name, or a parenthesized
   expression, which is evaluated recursively).
2. Loop on the token to the left:
   - `←` with a name immediately before it: assign, continue leftward
   - a function: if a value is immediately to its left it is dyadic, otherwise
     monadic
   - an operator takes the primitive immediately to its left as its operand
     and the result is a derived function (only `/` on scalar dyadic
     primitives is implemented)
   - anything else is a SYNTAX ERROR
3. `⋄` splits statements. A statement whose leftmost tokens are `name ←` is
   not echoed.

## Errors

`DOMAIN ERROR, LENGTH ERROR, RANK ERROR, SYNTAX ERROR, VALUE ERROR,
NONCE ERROR (not implemented), LIMIT ERROR, WS FULL`

## Testing strategy

1. `apl64.py` is the executable spec (`python3 apl64.py --test`).
2. 6502 primitives are assembled and run headless under **py65**.
3. Differential tests: random operands through both, compare the raw bytes
   (type, shape, data). Any difference is a real bug, apart from decimal
   parse and print (1 ulp allowed).
4. **VICE** for final integration: custom charset, screen output, `.prg`
   loading, disk I/O.

## Display and input (planned)

- 40x25 text screen; matrices need column-aware output formatting.
- Custom 2 KB APL character set in RAM, selected via `$D018`.
- Keyboard: Commodore/Shift-modified keys for common glyphs plus a two-key
  digraph fallback.

## Evaluator (6502)

`asm/eval.asm` (with `heap.inc` and `prims.inc`) follows `Interp.eval_tokens`
step for step, including the order of checks and errors. `eval_line` evaluates a
tokenized line: parentheses must balance across the whole line (SYNTAX ERROR
before anything is evaluated), statements split at diamonds outside
parentheses, and each value is passed to an echo hook unless the statement
starts with `name ←`. Variables persist across lines and errors; the value
stack is reset.

The token stream has variable-length literals, so it cannot be scanned right to
left. A forward pass builds an index (address and code per token), and the
evaluator runs over index ranges. Parenthesised groups do not recurse: a frame
(kind, saved bound, resume position, pending function) goes on a 128-entry
frame stack, and when the inner range is exhausted the frame says whether the
value is the initial value or the left operand of a pending function. A
dyadic primitive finds its left operand on top of the value stack and its right
one below.

Implemented so far: literals, names, assignment, parentheses, `⋄`, and the
structural primitives `⍳`, `⍴` (monadic and dyadic), `,` (monadic and dyadic),
monadic `+`. Everything else returns NONCE ERROR (in the model that is also the
answer for `[ ] → ;`, dyadic `⍳`, and any operator other than `f/` on scalar
dyadics; but the model does compute arithmetic, comparisons and reduce).

One deliberate difference: the model returns echoes only when the whole line
succeeds, so `1 ⋄ A B` prints nothing. The 6502 echoes each statement as it
finishes, like an APL session, and then reports the error. The tests compare
echoes only on lines that succeed.

## Tokenizer (6502)

`asm/tokenizer.asm` matches `Interp.tokenize` byte for byte: tokens, symbol
table (names in order of first use, 256 max) and every error kind. The one
allowed difference is decimal number parsing, below.

Number strands are folded into one BOOL, INT or FLOAT literal. Whether a
value is INT/BOOL or FLOAT is always exact (`1.0`, `10e¯1` and `5e0` are
integers; `32768` is FLOAT). Overflow (above about 1.7e38) is a DOMAIN ERROR
reported when the strand ends, so a syntax error later in the strand wins.
An explicit exponent beyond ±400 is a DOMAIN ERROR if positive and zero if
negative, as in the model.

Decimal to float24: the mantissa keeps 9 significant digits (a nonzero digit
beyond that acts as a sticky bit). Integer values up to 65535 are built
exactly. Anything else is `digits × 10^e`, using a 32-bit power-of-ten table
(`asm/pow10.inc`, generated by `tools/gen_pow10.py`) and the same rounding
as `f_mul`: a 32×32 multiply for e ≥ 0, an exact long division for e from -1
to -13, and a table reciprocal below that. The result is **bit-exact** for up
to 9 significant digits with e from -13 to 13, and within **1 ulp** of the
model otherwise. Underflow flushes to a FLOAT zero.

Buffers: input at `INBUF` (page aligned), strand scratch at `SBUF` (4 bytes
per element), tokens at `OUTBUF` (6 bytes per input byte is enough), symbols
at `SYMTAB`.

## Implemented in the model so far

`+ - × ÷` (monadic: identity, negate, signum, reciprocal), `= ≠ < ≤ > ≥`,
`⍳`, `⍴` (monadic and dyadic), `,` (ravel, and catenate on vectors),
`f/` for scalar dyadic `f`, assignment, `( )`, `⋄`, `⍬`.

NONCE: `\ ¨ . ∘ ⍤`, replicate (`n/x`), indexing `[ ]`, branch `→`, `;`,
catenate on matrices, index-of (dyadic `⍳`), user-defined functions.

## Next steps

Done (6502, differentially tested under py65): float24 add, sub, mul, div;
int16 add, sub, mul with the all-or-nothing redo in float24; tokenizer;
handle heap and GC; evaluator core with the structural primitives.

1. 6502: scalar dyadic `+ - × ÷` and comparisons with type dispatch (BOOL and
   INT to INT, redo in FLOAT, float24 tolerant comparison), monadic `- × ÷`,
   reduce (`f/`, exact `+/`), and the print formatter (`f_format`).
   Also budget zero page: the tests use `$10`-`$FF` freely, but the KERNAL owns
   much of `$90`-`$FF`.
2. Model: matrix catenate, indexing, `∘.`, `\`, user functions, control flow.
3. Charset, keyboard entry, `)SAVE` / `)LOAD`.
4. Later options: bit-packed BOOL, 4-byte float, transcendentals, fusion of
   scalar pipelines (e.g. `+/A×B` in one loop).
