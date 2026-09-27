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

## Memory map

The layout for the real machine. Steps 1-3 of the migration below are done: the
program assembles at `$0801` with the tables and heap placed by the assembler
(`asm/layout.inc`, `asm/bss.inc`), the pointers live in a zero-page pool, and
the tests enforce the map (`tests/test_layout.py`, and a guard in the harness that
fails any routine writing zero page outside the allowed set). What is left is
the video and start-up code that uses it.

### Measured before the migration

- **Code and read-only tables: 13,072 bytes.** float24 715, int16 464, tokenizer
  2,164 (+ 516 power-of-ten table), heap 929, primitives 1,387, scalar functions
  1,723, reduce 1,820, formatter 2,153, evaluator core 1,201.
- **Zero page: 200 bytes written** across the tokenizer, evaluator and formatter
  (traced under py65), 106 of them in `$90`-`$FA`, which the KERNAL owns. Only 62
  of those bytes must be zero page (18 indirect pointers, 36 bytes, plus the 21
  float24 registers and `ia`/`ib`/`sgn`); the rest is scratch that can be
  ordinary RAM.
- **Hardware stack: 20 bytes deep** at most (no recursion; measured over the
  tests plus deep nesting).
- **Tables**: about 7.9 KB, listed below.

### Measured after the migration

Code and read-only tables **25,289 bytes** (`$0801`-`$6AC9`, including the start-up
code, screen driver, charset data, editor and system commands: about 4 KB); tables
7,832 bytes; **heap 17,680 bytes** (`$86F0` to `$CBFF`; it starts where the tables
end). **The heap has a floor of 12 KB** (it was 16 KB until 2026-09-26, when more operators were preferred to room; the REU tier may give heap back; the build fails below it, and `tests/test_layout.py`
checks it); it was 24 KB until the features still to come needed the room, on the reasoning that
a plain C64 is for small workspaces and an REU (see the storage tier below) is for big ones. Code
now costs heap byte for byte: the tables that need a page (`VARS`, `VSTACK`, `SYMTAB`) start on a
page boundary, and the tables that do not need one (`RV`, `FMT`, `FACC`, `DIGS`, `FR`) fill the gap
before it when they fit (`asm/bss.inc`), so there is no cliff where the heap suddenly loses 256
bytes. The tables are sized by proven worst cases (3.5 bytes of tokens per input byte at worst, 64 levels of
nesting, 256 handles and names), so shrinking them means lowering a limit. Code that is only
needed by the tests (the echo log) and repeated out-of-range branches are the first
places to save. Read-only indexing cost 1,302 bytes of code (about 850 in `asm/index.inc`, the rest
in the evaluator's bracket frames), so the heap went from 24,792 to 23,512 bytes; indexed assignment took another 512, and a trimming pass (one cursor routine for checking and gathering, 0-based
indices, the result pushed with `pushcv`, the no-echo rule decided by the assignment itself) won back 240 (23,240). User-defined functions took about 3,000 (20,224), then about 900 back: the definition editor 640, calls 1,300 (call, return, contexts, classify, unwinding), a first full check of loaded functions 800 that was replaced by a checksum (about 100), and the rest `)FNS`, the file format and the state tables (80 bytes); the heap was then 20,856 (an earlier figure of 21,112 was a miscalculation); branches and labels took about 670 more (20,184), replicate/compress about 590 (19,592), the RUN/STOP check 32 (19,560); then a trim (far-branch stubs, a 64-entry frame stack, `⍬` as a one-byte token so the token buffer is 1,024) won back 840 (20,400). `⌈ ⌊ |` then cost about 1,120 (19,280): the kernels for INT and FLOAT (about 460, residue being the largest), floor and ceiling (about 500) and the glue; `∧ ∨ ~` about 220 more (19,064); `⌽ ↑ ↓` about 1,400 (17,680), which left 1,300 bytes above the old 16 KB floor. The per-array limit `WS_BYTES` / `wsmax` is 16,000 bytes.

Zero page is now fully allocated: the float24 registers, `ia`/`ib`/`sgn`, the
38-byte pointer pool (`$50`-`$75`), and the 54 most-referenced variables (chosen
by references per byte, filling the spare ranges). The other 75 variables are RAM
at the cassette buffer. Absolute addressing costs a byte per reference: the
first pass grew the code by 1.3 KB, and promoting those 54 variables won back
850 bytes. **New code should use RAM variables unless a variable is genuinely
hot**, and the harness fails any write outside `$02`-`$8F` and `$FB`-`$FE`.

### Machine configuration

`$01 = $36`: BASIC ROM out, KERNAL and I/O in. RAM is then contiguous from
`$0800` to `$CFFF`. The KERNAL stays for the keyboard scan, the 60 Hz interrupt
and disk I/O (`)SAVE` / `)LOAD`). Output is direct writes to screen RAM, never
CHROUT, because our glyph codes would be taken for PETSCII controls.

**Video (recommended): VIC bank 3.** `$DD00` bits 1-0 = `%00` (read-modify-write,
the upper bits are the IEC serial lines) and `$D018 = $34`: screen RAM at `$CC00`,
character set at `$D000`. In bank 3 the VIC reads RAM, not the character ROM, at
`$D000`-`$DFFF`. That is the RAM under the I/O area, which the CPU cannot see
while I/O is on, so a 2 KB charset there costs no usable memory. It is written
once at start-up with interrupts off and `$01 = $34`. (Bank 0 with the charset at
`$2000` is simpler but leaves a 2 KB hole in the middle of RAM: about 2.5 KB less
heap.) Consequences:

- The KERNAL still thinks the screen is at `$0400`. Set its cursor-blink flag
  (`$CC`) so its interrupt never draws there, and point the NMI vector (`$0318`) at
  an `rti`: RUN/STOP-RESTORE would otherwise reset the video registers and
  jump through `$A002`, which is our RAM. Call SETMSG with 0 so LOAD/SAVE print
  nothing.
- `$0400`-`$07FF` is then free.

### Map

| Address | Use |
|---|---|
| `$0002`-`$008F` | zero page, ours (142 bytes); plan below |
| `$0090`-`$00FA` | KERNAL zero page: never touched |
| `$00FB`-`$00FE` | spare |
| `$0100`-`$01FF` | hardware stack (we use about 20 bytes) |
| `$0200`-`$033B` | KERNAL/BASIC: left alone (`$0318` NMI vector patched) |
| `$033C`-`$03FB` | tape buffer, free: 192 bytes of non-zero-page variables |
| `$0400`-`$07FF` | transient per-line buffers: input line (256) and token index (768) |
| `$0801` | BASIC stub `10 SYS 2064` |
| `$0810`- | code and read-only tables, loaded from the PRG (13.1 KB now; budget 20 KB) |
| after the code | uninitialised tables, not in the PRG (below) |
| after the tables | **heap**, up to `$CBFF` |
| `$CC00`-`$CFFF` | screen RAM (VIC bank 3) |
| `$D000`-`$D7FF` | 2 KB character set, RAM under I/O, VIC only |
| `$D800`-`$DFFF` | colour RAM and I/O |
| `$E000`-`$FFFF` | KERNAL ROM |

Uninitialised tables (7.9 KB): remaining variables 512; handle table 768; variable
cells 1,024 (256 names); value stack 512 (128 cells); frame stack 512; symbol table
2,048; token output 1,024 (at most about 3.5 bytes per input byte); number-strand
scratch 512; formatter/reduce buffers 512. Value stack and frame stack are cut
from today's 192 and 128 entries: nesting depth is at most about 85 in a
255-byte line, and overflow is LIMIT ERROR anyway.

The heap starts wherever the tables end (the assembler computes it), so the heap
is whatever the code leaves. **Heap: about 29 KB with today's code, about 22 KB
at the 20 KB code budget.**

### Zero page

| Range | Use |
|---|---|
| `$02`-`$0F` | spare |
| `$10`-`$24` | float24 registers, as now |
| `$30`-`$33`, `$48` | `ia`, `ib`, `sgn`, as now |
| `$34`-`$47` | freed by retiring the int16 vector kernel |
| `$50`-`$7F` | pointer pool: the 18 indirect pointers (36 bytes) and 12 slots to spare |
| `$80`-`$8F` | spare, for hot counters |
| `$FB`-`$FE` | spare |

Every other current zero-page variable becomes an absolute RAM variable (same
instructions, one cycle slower; the assembler flags the few zero-page-only
forms). About 80 bytes used, about 66 spare. A guard keeps it that way: the test
harness will fail any write outside the allowed set.

### Decisions to confirm

1. **Video: bank 3 with the charset in the RAM under I/O** (recommended) or bank 0
   with a hole. Bank 3 costs some start-up code and needs checking in VICE.
2. **The per-array limit falls from 45,000 bytes to about 16,000** (`WS_BYTES` in
   the model, `wsmax` on the 6502), about three quarters of the old 24 KB minimum heap. With the 12 KB floor the heap itself
   is the tighter limit on a plain machine, and WS FULL is reported by whichever comes first.
   Arrays as large as the model allows today cannot exist in 22 KB. Larger
   arrays would need more heap, and the only big source left is banking the
   KERNAL out (+8 KB), which means writing our own interrupt, keyboard scan and
   disk code: not recommended.
3. **Retire the int16 vector kernel** (`vec_add` and friends): the evaluator no
   longer uses it. Saves about 300 bytes of code and 20 zero-page bytes; its tests go.

### Migration, in order (each step keeps `make test` green)

1. **Done.** `eval.asm` is the only top-level source; tests read addresses from
   the label file; the int16 vector kernel is retired.
2. **Done.** Scratch variables moved out of zero page (to the tape buffer at
   `$033C`), pointers into the pool, and the harness guard added. The
   most-referenced variables went back into the spare zero page, winning
   back 850 of the 1.3 KB the move cost.
3. **Done.** Assembled at `$0801` with the BASIC stub, computed heap base, `wsmax`
   16,000, real addresses in the harness. `make prg` builds `build/apl.prg`.
4. **Started.** `tests/test_vice.py` runs the PRG in headless VICE with the real
   KERNAL: it autostarts (injected into RAM), BASIC runs the `SYS` stub, and the
   CPU stops at `start` with the whole image in RAM. It needs the ROMs in `roms/`
   as `chargen.bin`, `basic.bin` and `kernal.bin` (C64 revision 3: 901225-01,
   901226-01, 901227-03; the directory is git-ignored, they are copyrighted) and
   skips itself without them. Still to do, once there is a screen driver: poke a
   line into the input buffer through the monitor, run it, and compare the screen
   RAM at `$CC00`.
5. **Done**: screen driver, charset, keyboard entry and the line editor (see
   Display and input). `)SAVE` / `)LOAD` and system commands are next.

### Verified in VICE

`tests/test_screen.py` runs scripted sessions on the real KERNAL and compares
screen RAM with the model through a Python model of the driver (wrapping, exact
40-column lines, scrolling once and twice, a long session), and checks the charset
RAM against the character ROM plus the glyph table, the VIC and CIA2 registers,
`$01`, the KERNAL flags, the NMI vector, and that the KERNAL interrupt is still
running. A screenshot confirmed the VIC really renders from the RAM charset in
bank 3. `tests/test_keys.py` types through the real KERNAL keyboard buffer (`GETIN`
with the interrupt scan, screen moved) and runs scripted editor sessions. Not yet
checked: the physical keyboard matrix; the RESTORE key itself (only the vector is
verified); SAVE/LOAD staying silent and inside their zero page.

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
- Arrays are limited to `WS_BYTES` (16000 in the model) and 65535 elements:
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

**Rules the code follows** (audited, and enforced by `tests/test_stress.py`, which reverses the order
of every block on the heap at each call to `alloc` and reruns the evaluator tests):

1. An array's data address comes only from `getval` (an existing cell) or `newarr` (a new result).
   The handle table is read in `heap.inc` alone.
2. No data address survives an allocation. Primitives allocate the result first and call `getval`
   again on their operands (`p_reduce` keeps the operand cell's address and re-derives it per row).
3. The collector never reads array contents: `gcmark` looks only at cells, and the arrays hold no
   handles, so marking does not care where an array is.
4. A primitive's operands are the top one or two cells of the value stack, and its result is the
   pinned handle. Everything else is only reachable, not in use.

These are what a second storage tier (extra RAM to spill arrays into) needs: residency could be
guaranteed inside `getval`, and eviction could take any live array that is not an operand or the
pinned result. The one place that is not stress-tested is `)LOAD`, which runs on VICE only.

Per-array size is limited to `wsmax` bytes (16000, the model's `WS_BYTES`), and
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
| `$98` | `∇` | `$8D` | `⌈` | `$8E` | `⌊` |
| `$99` | `∧` | `$9A` | `∨` | `$9B` | `⌽` |
| `$9C` | `↑` | `$9D` | `↓` | | |

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
| `$0B` | a name of a function with arguments (made when a line is loaded, never stored; two bytes like a name) |
| `$0C` | `⍬`, the empty INT vector, in one byte (a literal would be six); the evaluator makes the array |
| `$10-$7F` | Reserved (system functions, ⎕ names, control keywords) |
| `$80+i` | Primitive function, `i` indexes `+-×÷=≠<≤>≥⍳⍴,⌈⌊\|∧∨~⌽↑↓∊⍋⍒⍉` |
| `$C0+i` | Operator, `i` indexes `/\¨.∘⍤⌿⍀` |

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

1. The rightmost token must be a value (literal, name, a parenthesized
   expression, which is evaluated recursively, or any of these followed by an
   index `[i]` / `[i;j]`).
2. Loop on the token to the left:
   - `←` with a name immediately before it: assign, continue leftward
   - a function: if a value is immediately to its left it is dyadic, otherwise
     monadic
   - an operator takes the primitive immediately to its left as its operand
     and the result is a derived function (only `/` on scalar dyadic
     primitives is implemented)
   - anything else is a SYNTAX ERROR
   An index applies to the value just before its `[`, which may be a name, a
   literal, a parenthesized expression or another index (`A[1 2][2]`). The
   groups between the brackets are evaluated right to left, then the
   indexed value; an empty group means the whole axis. `A[i]` has the shape
   of `i` (a scalar index gives a scalar), `M[i;j]` the shapes of `i` and `j`
   joined (a result of rank 3 or more is LIMIT ERROR). Axis brackets
   (`+/[1]A`) are NONCE ERROR.
   `A[i;j]←v` (only on a plain name) evaluates `v`, then the groups right to
   left, then looks `A` up; `v` is a scalar or has exactly the shape of the
   selection (RANK ERROR, else LENGTH ERROR), the type is the join of the two
   (DOMAIN ERROR for characters with numbers, unless the selection is empty,
   which changes nothing), and the result is a new array (other names keep the
   old one; with repeated indices the last write wins). It is not echoed, like
   `name←`, and its value is `v`.
3. `⋄` splits statements. A statement whose leftmost tokens are `name ←` is
   not echoed.

## Maximum, minimum, floor, ceiling, residue, magnitude

`⌈ ⌊ |` (typed pound `s`, `d`, `l`; `|` is the ASCII bar) are scalar functions run by the same
engine as `+ - × ÷ = ≠ < ≤ > ≥` (`asm/scalar.inc`), so scalar extension, shape checks, DOMAIN ERROR for
characters, and the size rules are the same, and `⌈/ ⌊/ |/` work like the other reductions.

- **`A⌈B`, `A⌊B`**: the larger and smaller. BOOL and INT give INT; a FLOAT operand gives FLOAT. The order
  is exact (no comparison tolerance).
- **`⌈B`, `⌊B`**: ceiling and floor. BOOL and INT are unchanged. FLOAT becomes INT if every result fits int16,
  otherwise stays FLOAT (whole values). The floor is exact (no tolerance).
- **`A|B`**: the residue, `B` modulo `A`, with the sign of `A`; `0|B` is `B`. BOOL and INT give exact INT. FLOAT
  gives `B - A × ⌊B÷A` with each step rounded, then, if that left the result outside `[0,A)`
  (or `(A,0]`), one correction by `A`; overflow of the division is DOMAIN ERROR.
- **`|B`**: the magnitude; BOOL and INT give INT (the whole array becomes FLOAT if `¯32768` is in it),
  FLOAT clears the sign.
- `⌈/⍬` and `⌊/⍬` are DOMAIN ERROR (the identity would be the largest or smallest number), `|/⍬` is 0.

## Logic

`∧ ∨` (pound `w`, `v`) and `~` (pound `n`) work on 0s and 1s: every element must be a BOOL, an INT or a
FLOAT that is exactly 0 or 1, else DOMAIN ERROR (characters too, even in an empty array). `A∧B` and `A∨B` are
scalar functions of the engine (shapes and extension as for `=`), `~B` is 1-B; the results are BOOL. There
is no LCM/GCD, and dyadic `~` (without) is NONCE ERROR. `∧/` and `∨/` reduce with identities 1 and 0; a
one-element row is returned as it is, like the other reductions (so `∧/,2` is 2).

## Index-of, membership, grade

`A⍳B` (a vector `A`, else RANK ERROR): for each element of `B` its 1-based position in `A`, or 1+⍴A; the
result is INT with `B`'s shape. `A∊B`: for each element of `A`, whether it is in `B`; BOOL, `A`'s shape.
Elements are equal if they are equal numbers (exactly, across BOOL, INT and FLOAT) or equal characters; a
character never equals a number. `⍋V`, `⍒V` (pound `7`, `3`; `∊` is pound `e`): the positions that put the vector `V`
in order, INT; equal elements keep their order (also for `⍒`); floats are ordered exactly; anything but a vector is
RANK ERROR. The 6502 sorts by insertion, so long vectors are slow (about n²/4 comparisons). `asm/search.inc`.

## Reverse, rotate, take, drop

`⌽ ↑ ↓` (pound `a`, `y`, `u`; `asm/reshape.inc`) work on scalars, vectors and matrices (along the last axis
for `⌽`). The left argument is whole numbers: RANK ERROR above a vector, DOMAIN ERROR for anything else.

- **`⌽B`**: each row backwards; a scalar is unchanged.
- **`A⌽B`**: each row rotated left by `A` (right if negative), `A` a single whole number that fits int16
  (DOMAIN ERROR beyond); a scalar or empty `B` is unchanged; one number per row is NONCE ERROR.
- **`A↑B`**: the first `|A|` elements, or the last if `A` is negative, along each axis, padded with 0 (a blank for
  characters) where `B` is short. `A` has one number per axis (a scalar for a vector; a scalar `B` counts as a
  vector of one); any other length is LENGTH ERROR. A length over 65535 is WS FULL, like a result too big.
- **`A↓B`**: `B` without those elements; overdropping gives an empty array. Both give the type of `B`, and a
  scalar `B` becomes a vector.
- Monadic `↑ ↓` and dyadic `~` are NONCE ERROR.

## Replicate and compress

`a/b` (a value to the left of `/`, `asm/replicate.inc`): each element of the vector or scalar `b` is
repeated as many times as the matching element of `a` says, so 0s and 1s select (`(A>2)/A`).
`a` is non-negative whole numbers (RANK ERROR above a vector, DOMAIN ERROR for anything else,
negative counts included); it has one element per element of `b`, or one element for all of `b`
(`3/5` is `5 5 5`), or `b` has one element for all of `a`; any other lengths are LENGTH ERROR. A
matrix `b` is done a row at a time (its columns are repeated; `a/[1]M` does its rows), WS FULL if the result is too big. The
result has `b`'s type and, for a matrix, `b`'s row count. A count of a single element applied to an empty `b` is not
looked at. `x f/ y` and the other operators after a value are still NONCE ERROR.

## Scan and outer product

`f\v` (scan, `p_scan` in `asm/reduce.inc`): element k along the last axis is `f/` of the first k
elements, each prefix reduced right to left, so `-\1 2 3 4` is `1 ¯1 2 ¯2`. The result has the operand's
shape and the widest type of the prefix results (`+\32767 1` turns FLOAT at the second element and
the result is restarted wider, as for a matrix reduce). It reuses the reduce code: the "rows" are the
prefixes, taken in order, so the results arrive in the layout of the result. A scalar or an empty operand
comes back unchanged. Only `+` is fast: BOOL and INT keep a running 32-bit sum and FLOAT keeps the exact
fixed-point accumulator, so each prefix costs one addition (the accumulator is negated for rounding and
negated back). Every other function folds each prefix from scratch, which costs n² element operations.
`x f\y` is NONCE ERROR, and so is expand `a\b`.

`a∘.f b` (outer product, `p_outer` in `asm/scalar.inc`): `f` between every element of `a` and every
element of `b`, for the scalar dyadic functions; the result has the shape of `a` followed by the shape of
`b`. It is the scalar engine with `owa` (the width of `a`'s elements) set: with a scalar operand it is the
ordinary scalar extension, with two vectors the engine makes one pass over `b` per element of `a`, and a
higher rank is LIMIT ERROR (checked first), then more than 65535 elements WS FULL, then the types (DOMAIN)
and the size, in the order of the other scalar functions. Monadic `∘.f` is SYNTAX ERROR; any other `f` is
NONCE ERROR. The evaluator marks the function as an outer product by adding `$60` to its token.

## Numeric functions

`*` (monadic: e to the x; dyadic: power), `⍟` (monadic: natural logarithm; dyadic: logarithm to a base) `○` (pi times; the circle functions) and `!` (factorial; binomial). Both give FLOAT.
The glyph `⍟` is pound `*`, `○` pound `o` (`?` is token `$9e`: see Random numbers).
float24 has a 16-bit significand, so each function is a short program of `+ - × ÷` on it, run by a small interpreter
(`vm_run` in the model, `mv_run` in `asm/math.inc`, an overlay of about 2.5 KB): an accumulator, twelve float slots, an integer
register and two-byte instructions (an opcode and a constant, slot, count or bit; `IFLT` and `IFGE` run the next n instructions
only if the accumulator is below / not below a constant). The programs and constants are data in `apl64.py` (`MATH_PROGS`,
`MATH_CONSTS`); `tools/gen_math.py` writes them as `asm/mathprog.inc` and `tests/test_math.py` checks that it is not stale.
Because the 6502 runs the same program bytes through the same correctly-rounded float routines, model and machine agree bit for
bit; the tests also run random programs through both interpreters, and compare the model with Python's `math`
(exp within 1.5 units of 2^-16 of the true value, ln 3.5, sqrt 1.5, power 2 times (1 + |b ln a|); perfect squares and small integer
powers are exact).

- **exp**: below -100 the result is 0, above 89 it is DOMAIN ERROR; otherwise `x = k ln 2 + r` (`ln 2` in two parts, so `k*ln2hi` is
  exact), a degree-7 polynomial for `exp r`, and the result scaled by `2^k` (overflow DOMAIN ERROR, underflow 0).
- **ln**: zero and negatives are DOMAIN ERROR; `x = m 2^e` with `m` in [0.7, 1.4), `ln m = 2z(1 + z²/3 + z⁴/5 + ...)`, `z = (m-1)/(m+1)`.
- **sqrt** (the power 0.5): Newton's method from a straight line, three rounds, on a significand in [0.5, 2) and an even exponent.
- **a\*b**: `b = 0` is 1 (also `0*0`); `a = 0` is 0, or DOMAIN ERROR for negative `b`; a whole `b` of magnitude 1 to 127 is a product by
  repeated squaring (`2*10` is exactly 1024), reciprocal for negative `b`, and works for negative `a`; other `b` need `a > 0`
  (DOMAIN ERROR otherwise) and give `exp(b ln a)`. **a⍟b** is `ln b ÷ ln a`.
- **○**: monadic `○x` is `π×x`; dyadic `k○x` takes `k` a whole number from -7 to 7 (DOMAIN ERROR otherwise) and gives `0` √(1-x²), `1` sin,
  `2` cos, `3` tan, `4` √(1+x²), `5` sinh, `6` cosh, `7` tanh, `¯1` asin, `¯2` acos, `¯3` atan, `¯4` √(x²-1), `¯5` asinh, `¯6` acosh, `¯7` atanh.
  Trigonometry reduces `x` by `k = round(2x/π)` (π/2 in three pieces, the first two of 8 bits so `k×piece` is exact for `|k| ≤ 255`, that is `|x|`
  up to about 400; beyond that `x` itself has too few bits to mean much, and `|x|` above about 51,000 is DOMAIN ERROR), polynomials for sin r and
  cos r, and the quadrant `k & 3` chooses which and the sign. atan works on `|x|`, inverted if it is 1 or more, then `(a-1)/(a+1)` with π/4 added
  above tan(π/8), then a series; asin is `atan(x/√((1-|x|)(1+|x|)))` (|x| > 1 is DOMAIN ERROR, |x| = 1 is ±π/2) and acos is
  `2 atan √((1-x)/(1+x))`. The interpreter's `CALL` runs another program (shared slots and integer register; a caller keeps what it needs in
  slots 6 and up, past whatever the program it is about to call uses itself — the same rule a stack frame would enforce, and easy to get
  wrong silently: nothing marks a slot as "in use", so a collision just computes the wrong answer, never an error) and `DOMERR` raises
  DOMAIN ERROR. Accuracy against the real functions: sin and cos within 1.3, tan 3.5, atan 1.7, asin 2.3, acos 3.4 units of 2^-16 (absolute
  for the first four, relative for tan and acos).
- **the hyperbolic functions** (`sinh cosh tanh asinh acosh atanh`, and monadic `¯4○`): `sinh`/`cosh` are `(e^x ∓ e^-x)/2` above `|x| = 0.5`
  (reusing `EXP`, so they overflow on the same DOMAIN ERROR boundary exp itself does, around `|x|` in the high 80s) and the ordinary Taylor
  series in `x²` below it — `e^x` and `e^-x` are both close to 1 there, so the subtraction (or, for cosh, the /2 that throws away what
  `e^-x` added back) cancels away most of float24's precision, where the series (odd terms for sinh, even for cosh, reusing `EXP`'s own
  `c1..c7 = 1/i!`) is exact well past it. `tanh` is `sinh x ÷ cosh x` (the /2 in each cancels exactly, being a power of two). `¯4○` (`√(x²-1)`,
  `|x| < 1` DOMAIN ERROR) mirrors `0○`'s `√(1-x²)`, factored the same way; `acosh` is `ln(x + √(x²-1))`, `x ≥ 1` DOMAIN ERROR otherwise — no
  small-`x` trap here, since `√(x²-1)` is itself small near `x = 1`, not swallowed by adding it to `x`. `asinh` and `atanh` have the same
  small-argument trap as sinh/cosh (`ln(x + √(x²+1))` adds `x` to something that has already rounded away anything smaller than it, and
  `(1+x)/(1-x)` does the same to both sides of the ratio before it is ever divided): below `|x| = 0.5`, `atanh` uses the series in `x²`
  reusing `ATAN`'s own `third fifth seventh ninth = 1/3 1/5 1/7 1/9`, and `asinh` is `atanh(x / √(x²+1))` (dividing `x` by something close to
  1 keeps all of it, where adding does not). At or above half, `asinh` goes back to `ln(|x| + √(x²+1))`, always adding two positives — never
  the near-cancellation `ln(x + √(x²+1))` has for a large negative `x`, where `√(x²+1)` is close to `-x` — negated at the end since asinh is
  odd. `acosh` and `atanh` diverge at their domain's edge (the derivative going to infinity as `x → 1` or `|x| → 1`), so their accuracy
  necessarily gets worse right there: a float24 input a few units off the true `x` is a much bigger error in the result, not a defect in
  the algorithm. Accuracy: sinh, cosh, tanh, asinh and `¯4○` within 10 units of 2^-16 away from their singularity (sinh/cosh inherit exp's
  own ceiling approaching DOMAIN ERROR); acosh and atanh within 10 except right at their domain's edge.
- **!**: monadic `!n` is the factorial of a whole number from 0 (the product overflows float24 above 33: DOMAIN ERROR); dyadic `a!b` is the
  number of ways to choose `a` things from `b` (0 if `a` is above `b`), computed a step at a time as `r×(b-k+i)÷i`, `k` the smaller of
  `a` and `b-a`, so it is whole at every step (exact when the numbers stay under 65536). Both take whole numbers from 0 to 65535 only; the
  gamma function (non-whole and negative arguments) is not done: DOMAIN ERROR. The kernels are the overlay `asm/fact.inc` (550 bytes), which
  the engine loads for operations 20 and 24 instead of the numeric one.
- They are scalar functions in the engine (operations 17 to 24; the kernels are in the overlay, loaded when the engine sets up an
  operation), so they work on arrays and in outer product (`(⍳5)∘.*2`); reduce, scan and inner product do not take them (NONCE ERROR:
  the kernels' overlay cannot be loaded while the inner product's is running).

## Random numbers

`?n` (roll) and `a?b` (deal) (`asm/rand.inc`, an overlay of 991 bytes; model `roll`, `deal`, `rng_draw`, `rng_seed`). The generator is
xorshift32 (`x ^= x<<13; x ^= x>>17; x ^= x<<5`), its four-byte state `rnd_state` kept in resident code so it survives overlay changes;
a draw is the top 16 bits of the state. It is seeded from the CIA timer and the jiffy clock at start-up, and `)SEED n` (n from 0 to 65535, otherwise
BAD COMMAND; `sysov.inc`) sets it to `n << 16 | (n xor $5A5A) | 1`, so a session can be repeated.

- **`?v`**: for each element `n` (whole, 0 to 32767, else DOMAIN ERROR; all are checked before the first draw, so an error leaves the generator alone)
  a random integer `(r × n >> 16) + 1`, in order; a 0 gives the number `r|1 ÷ 65536` (strictly between 0 and 1, exact in float24) and, if there
  is one, the whole result is FLOAT. The result has the shape of `v`; a scalar gives a scalar.
- **`a?b`**: `a` and `b` are single whole numbers with `0 ≤ a ≤ b ≤ 32767` (LENGTH ERROR unless each has one element, DOMAIN ERROR otherwise): `a` distinct
  integers from 1 to `b` in random order, the first `a` of a partial Fisher-Yates shuffle (`j = i + (r × (b-i) >> 16)`, swap, for `i` below `a`).
  The working array of `b` numbers is a real array on the stack, so `5?32767` is WS FULL on a small heap.
- Tests: `tests/test_random.py` compares model and machine including the generator's state after every line (`tests/test_eval.py check`), and `)SEED` and the
  distribution in the model; the VICE key sessions use `)SEED` to repeat a run.

## Decode and encode

`B⊥V` and `B⊤V` (dyadic only: a monadic call is NONCE ERROR; model `decode`, `encode`; `asm/baseconv.inc`, an overlay of 1,727 bytes,
tokens `$B0 $B1` since the quad functions already fill `$A0`-`$AC` and `PRIM_GLYPHS` fills `$80`-`$9F` — `DECODE_GLYPHS`/`DECODE_TOKEN`
is a second small range, the same shape as the quad names' own, with `_glyph_of` checking it first). Keys: pound `b` (mnemonic: base),
pound shift-`b` (⊤ is ⊥ upside down, so the shift of the same key).

- **`B⊥V`**: mixed-radix decode. `n` is the digit count: `V`'s length, or its row count if `V` is a matrix (one result per column, a
  vector). `B` is one radix per digit or a single one for all (LENGTH ERROR otherwise; its first element never affects the result, as
  in APL generally). Horner's rule, left to right, in the ordinary `×` and `+`, so an int16 overflow promotes the running total to
  FLOAT exactly as it would inline. `B` and `V` are rank 0 or 1 (2 for `V`); CHAR is DOMAIN ERROR.
- **`B⊤V`**: mixed-radix encode (a matrix `V` is NONCE ERROR). `n` is the length of `B` (1 if a scalar): the digit count. Least
  significant first, one element of `V` at a time: each digit is `B[i]|remaining` (a zero radix absorbs everything left, per `|`'s
  own rule, and every higher digit is then 0); what is left is divided out exactly (`(remaining-digit)÷B[i]`), so `÷` always promotes
  it to FLOAT after the first non-trivial digit — an accepted quirk, since the formatter prints an exact float with no `.` (a
  monadic `⌊` after each division would keep it INT when it fits, but `⌊` is an overlay of its own, and nothing an overlay calls may
  load another). The result is a vector (`V` a scalar) or a matrix (`V` a vector, one column per element, digits down the rows).

On the 6502 (`p_decode`, `p_encode`), every step is one scalar pair through the ordinary scalar engine (`p_sdyad`, resident) — never
a whole array — so no int16/FLOAT promotion rule is reimplemented: `bc_getelem` (using `elemaddr`, resident) fetches one element of
`B` or `V` as a 4-byte cell, `bc_place` writes one result element into the growing result array, allocated once (`newarr`) and
widened in place (`cvcopy`, replacing the value-stack cell, exactly as inner product widens its own result) the first time a wider
element arrives; an empty result defaults to INT, matching the model's `_stack`/`Value` fallback. `p_sdyad`'s dyadic convention:
**`topcell` is the left argument, `secondcell` the right** (confirmed directly — this is easy to get backwards for a non-commutative
function like `|`, `-` or `÷`, where swapping the push order silently swaps which operand is the modulus/minuend/dividend rather
than raising an error). Two bugs came from this file specifically: `cv` (`WS+$d0`-`$d3`, resident) is scratch that `pushcv` writes on
every call, so nothing here may keep state in the WS+ range at all — variables live in the overlay image instead, like inner
product's (a WS+ offset that looks free by grep is not: it is either genuinely unclaimed or, as here, owned by resident code that is
"free" only because nothing had needed it yet); and encode's zero-radix flag had its two branches swapped, so every ordinary digit
took the absorb path and every zero radix divided (silently wrong values, not a crash, since both paths are individually valid
control flow — the fix was found by hooking `p_sdyad`'s own entry and comparing `topcell`/`secondcell` against an isolated push/call
test that used the same op number and got the right answer). Checks run both ranks (RANK ERROR) before either domain (DOMAIN ERROR),
matching the model's `if b.rank>1 or v.rank>1: ... if b.t==CHAR or v.t==CHAR: ...` order exactly.

Tests: `tests/test_baseconv.py` (syntax/NONCE, a base/value pool, random decodes and encodes, matrix decodes and round trips through
both functions together).

## Axis brackets

`f/[k]A`, `f\[k]A`, `⌽[k]A` and `a⌽[k]A` (`Interp._axis` in the model): a bracket after a function or operator
gives the axis, `k` a scalar whole number from 1 to the rank of the array to its right (RANK, DOMAIN and INDEX
ERROR, in that order); any other function or operator (`+[1]`, `⍳[1]`, `a/[1]b`, `f.g[1]` ...) is NONCE ERROR, and
so is a user-defined function. These functions work along the last axis, so axis 1 of a matrix is done by
transposing the matrix, applying the function, and transposing the result back if it is a matrix (`axis_fn`); axis
2 of a matrix and axis 1 of a vector are the ordinary function. Also with an axis: compress and expand (`a/[k]M`, `a\\[k]M`, `p_repl` and `p_expand` do a matrix a row at a time) and catenation (`A,[k]B`), for which the axis may be one of the
left argument's, checked when both arguments are known (INDEX ERROR); monadic `,[k]` is NONCE ERROR. The flags are `AX_FLIP` for axis 1 (matrices among
the arguments, on either side, are transposed and a matrix result is transposed back) and `AX_K2` for axis 2.

On the 6502 (`rl_axis`, `ct_ax`, `axfin` in `eval.asm`, `p_axis` in `reshape.inc`): the group in the brackets is a
range of its own (frame kind `K_AXIS`); when its value is done `p_axis` checks it against the array below it,
takes it off and, for axis 1 of a matrix, replaces the matrix with its transpose, leaving the flags `AX_GIVEN`
and `AX_FLIP` in `ev_axn`. The next function token picks them up in `rl_fn2` (`ev_axc`; NONCE unless it is
`/`, `\` or `⌽`); a dyadic one keeps them in the flag bits of `ev_pkind`, which the frames save, so an axis
inside the left operand cannot disturb them. After the function is applied `axfin` transposes the result if
`AX_FLIP` is set. A `]` whose `[` follows a function is an axis, never the end of an indexed left operand: `+/[1]⍳4`
applies `⍳` monadically.

### The first-axis glyphs: `⌿ ⍀ ⊖`

`⊖B`, `A⊖B` (pound shift-`A`, `asm/eval.asm`), `f⌿B`, `A⌿B`, `f⍀B` and `A⍀B` (pound `/` and pound `?`, the shifts
of the same key) are `⌽[1]`, `f/[1]` and `f\[1]` written without a bracket: sugar, not a new mechanism. `PRIMS['⊖']
= axis_fn(PRIMS['⌽'], 1)` in the model; the tokenizer appends `⊖` to `PRIM_GLYPHS` (token `$9F`) and `⌿ ⍀` to
`OP_GLYPHS` (tokens `$C6 $C7`), so every existing token value keeps its meaning. Unlike a bracket, these never
raise INDEX ERROR for a scalar or vector argument (there is no axis value to check the rank against — `axis_fn`'s
`tr`/`fix` are identity below rank 2, so `⊖` and `f⌿` on anything but a matrix are just `⌽` and `f/`); combining
one with a bracket (`⊖[1]A`, `f⌿[1]A`) is NONCE ERROR, same as any other function that is not `/`, `\` or `⌽`.

On the 6502 (`rl_fnok`, `rl_fn2` and `rl_val` in `eval.asm`), the sugar is expanded at the point the token is seen,
matching what `s_axis` would have done for an explicit `[1]`: the array already on the value stack (the operand
to the right, which right-to-left evaluation has already reduced to one cell) is transposed now if it is a matrix
(`jsr s_transpose`, a no-op below rank 2), `ev_axn` is set to `AX_GIVEN+AX_FLIP` as if a bracket had just closed,
and `ev_tok` is rewritten to `$93` (`⌽`), `$c0` (`/`) or `$c1` (`\`) so every later step — the dyadic left operand's
own transpose in `axpre`, the result's transpose back in `axfin` — is the untouched, already-tested bracket
machinery. `ev_axn` nonzero already (a bracket was given too) is NONCE before any of this runs. The one pitfall:
the transpose is a `jsr` to an overlay stub, which clobbers X, so the pending function code (`$7e`/`$7f` for
`a⍀b`/`a⌿b`) must be reloaded from a constant afterwards, not carried in X across the call.

## Catenate on matrices

`A,B` when one of them is a matrix (`asm/catm.inc`, an overlay of 714 bytes, entered from the resident `p_catenate`; model
`_catenate_rows`): the columns of `B` follow those of `A` in every row. A vector needs one element per row and
is a single column (LENGTH ERROR otherwise); a scalar is repeated for each row; two matrices need the same number of
rows. An empty argument gives way to the other for the type, as in vectors; a character and a number do not mix
(DOMAIN ERROR); more than 65535 elements is WS FULL. `A,[1]B` stacks rows (it is `A,B` on the transposes), so a vector
there is a row. `a/M` and `a\M` (compress, expand) apply the counts to each row of `M`, `a/[1]M` to each column.

## Transpose, without and expand

`⍉B` (pound `t`, charset code `$A1`, token `$99`; `p_transpose` in `reshape.inc`): a matrix with rows and columns
exchanged; a scalar or vector is unchanged. `A⍉B` takes a permutation of the axes: one whole number per axis of
`B` (LENGTH ERROR otherwise), `1 2` leaves a matrix as it is and `2 1` transposes it, anything else is DOMAIN
ERROR (only rank 2 exists, so there is nothing else to permute). `A~B` (`p_without` in `search.inc`): the
elements of the vector (or scalar) `A` that are not in `B`, in order, with the same equality as `∊` (exact across
BOOL, INT and FLOAT, a character equals only a character); `B` may have any shape; RANK ERROR for a matrix `A`; the
result is a vector of `A`'s type. `A\B` (expand, `p_expand` in `replicate.inc`; the evaluator gives it the function
code `$7e`, as `a/b` has `$7f`): `A` is 0s and 1s (RANK ERROR above a vector, DOMAIN ERROR for anything else),
`B` a vector with one element per 1 (LENGTH ERROR otherwise) or a scalar (used for every 1), a matrix `B` is
NONCE ERROR; the result has one element for each element of `A`: the next element of `B` for a 1, a 0 or a blank
for a 0. Checks go in the model's order (`expand`, `without`, `transpose_axes` in `apl64.py`).

## Inner product

`a f.g b` (`make_inner` in the model, `asm/inner.inc`, an overlay of 1,472 bytes; `f` and `g` are scalar dyadic
functions, otherwise NONCE ERROR; monadic use is SYNTAX ERROR): `f/` of `a g b` over the last axis of `a` and
the first axis of `b`. The result has the shape of `a` without its last axis followed by the shape of `b`
without its first, so vector and vector give a scalar and matrix and matrix a matrix. A scalar operand
extends to the other's inner length; other inner lengths that differ are LENGTH ERROR; a result with a
zero dimension is NONCE ERROR (an empty inner axis is fine: `f/` of nothing is the identity). Each element is
what the model's reduce gives for the row of `g` results, so types, DOMAIN ERROR and the single-element rules
are those of the scalar functions and of reduce.

On the 6502 the evaluator marks `f.g` with a frame kind of its own (`K_LEFTI`, the function code
`f*16 + g` in the engine's operation numbers) and calls `p_inner` through `s_inner`. For each element it
copies row `i` of `a` and column `j` of `b` into two new vectors (a scalar is repeated), runs `p_sdyad` for
`g` and `p_reduce` for `f`, and stores the scalar it gets. The result array is allocated when the first
element has given its type and is widened (what is there is converted and copied) when a later element needs
a wider one. A result that does not fit is not an error yet: the remaining elements are still computed so that
a DOMAIN ERROR anywhere wins over WS FULL, as in the model. It costs time, not memory, in the number of
elements times the inner length: about 8,000 6502 cycles per element and a little per inner element.

## User-defined functions

`∇` (typed as pound `g`) starts a definition when it is the first non-blank character of a
line; the rest of the line is the header, `[R←][A ]FN[ B][;L1;L2...]`: an optional result name,
a function name with no, one or two argument names (niladic, monadic, dyadic; a monadic
function has the right argument only), and localised names after semicolons. Every name must
differ from the others and from the function's; the function's name must not be a variable
(SYNTAX ERROR otherwise; an existing function is simply replaced). The prompt becomes `[n]`, the
number of the next line, and every line typed is tokenised and added to the body (a line the
tokenizer or the bracket check refuses is reported and not added; 255 lines at most, LIMIT
ERROR); a line holding only `∇` ends the definition. There is no editor for existing
functions: retype them. `)` lines are body lines while defining.

Calling: a name of a function that takes arguments is a function in an expression, applied
monadically or dyadically by what is to its left (a dyadic call of a monadic function is a
SYNTAX ERROR; a monadic call of a dyadic one leaves the left argument undefined); a niladic
function's name is a value that is computed wherever it stands. The header's names (result,
arguments, locals) are *localised* by the call: they are undefined on entry (the arguments then get
their values) and get their old values back however the call ends, an error included, so
assignments to any other name are global and the called function sees its caller's names
(dynamic scoping). The result is the result name's value at the end (VALUE ERROR if it has
none). Every line runs as if typed; a value that is not assigned is printed. A function with no
result may only end a statement (`F 3`, not `1+F 3`, `A←F 3`, `(F 3)`): nothing is printed for
it. A function's name cannot be assigned to or indexed for assignment. Calls nest 16 deep
(LIMIT ERROR); the value stack (128 cells, each call takes one plus one per localised name)
may give LIMIT ERROR sooner. **Control flow.** A statement whose first token is `→` is a branch (in a function; at the keyboard
it is NONCE ERROR, and `→` anywhere but first in a statement is SYNTAX ERROR). The expression after
it is evaluated as usual (a call giving no value is a VALUE ERROR) and its first element is the number
of the next line to run: 1 to the number of lines goes to that line, anything else (0, negative, past
the end) leaves the function, and an empty value does nothing and goes on with the next statement.
A character value or a non-whole number is DOMAIN ERROR. The rest of the current line is skipped when
a branch is taken. Conditions are written with what exists: `→END×⍳N=0` branches to `END` only when
`N=0` (`⍳1` is `1`, `⍳0` is empty), and `→0×⍳N<2` leaves the function when `N<2`.

A line may start with a label, `NAME:` (no space before the colon); the label is a name that
holds the number of its line (an INT scalar) during every call, so `→TOP` is a jump to `TOP:`.
Labels are localised like the other names of the header, must differ from every other name of
the function and from each other (SYNTAX ERROR), and with the header's names there may be at most
98 symbols (LIMIT ERROR). The colon must directly follow the name, which must be the first thing on
the line; a label alone on a line is an empty line, `→` to it goes on to the next. The label is
removed from the stored tokens, so it costs a symbol and a byte of line number, not space in the
line. Calls nest 16 deep; a loop has no limit but the keyboard: RUN/STOP stops a running function
with INTERRUPT (below).

**RUN/STOP.** Between two lines of a function (`fn_nextline`, where every loop and every recursion
passes) the stop key's flag, which the KERNAL's interrupt keeps in `$91` (`$7F` while the key is down),
is looked at; if it is set, the error INTERRUPT (code 10) ends the call like any other error, giving the
localised names back, and the prompt returns. A single primitive, however big, is never interrupted, and
neither is anything typed at the keyboard that has no function in it. The key also puts a `$03` in the
keyboard buffer, which the editor ignores. Tested (`tests/test_funcs.py`) by setting `$91` from a hook
while a loop or a recursion runs; VICE cannot press the key from its monitor.

A function is a variable cell with tag `$15` (a CHAR vector, plus `$10` for "function") whose
block is (`Func.to_bytes()` in the model): nargs, hasres, nsyms, nlines, nlabels, then nsyms symbol
numbers (result, left argument, right argument, locals, the ones that exist, then the labels),
then the line number of each label, then each line as a 2-byte size and its token stream. While it is being defined its block is the last in the heap and each
line is appended in place; the variable is set at the header.

The evaluator makes a call without recursion of the hardware stack (`asm/funcs.inc`).
`classify`, run whenever a line is loaded, turns names of functions with arguments into `T_FN`
tokens, so a name is a function or a value without further lookup. A call saves the calling line in a
heap block (17 register bytes, the evaluator's frames, the token stream), pushes a record on
the value stack (that block's cell, then the old values of the localised names) and runs the
lines through the ordinary statement loop; `udf_return` restores everything, replaces the operands by
the result and carries on at the same point. An error leaves through the normal error returns
(each nested call added one return address to the hardware stack, which the chain of `rts`
unwinds) and `eval_line` then gives the names back (`unwind`).

## Errors

`DOMAIN ERROR, LENGTH ERROR, RANK ERROR, SYNTAX ERROR, VALUE ERROR,
NONCE ERROR (not implemented), LIMIT ERROR, WS FULL, INDEX ERROR, INTERRUPT` (codes 1 to 10 on the
6502, in that order except that INDEX ERROR is 9, an index outside `1..length`, and INTERRUPT is 10,
the stop key; the model has no interrupt)

## Testing strategy

1. `apl64.py` is the executable spec (`python3 apl64.py --test`).
2. 6502 primitives are assembled and run headless under **py65**.
3. Differential tests: random operands through both, compare the raw bytes
   (type, shape, data). Any difference is a real bug, apart from decimal
   parse and print (1 ulp allowed).
4. **VICE** for final integration: custom charset, screen output, `.prg`
   loading, disk I/O.

## System commands and workspace files

A line whose first non-blank character is `)` is a system command (`asm/syscmd.inc`,
`asm/disk.inc`). It is handled before the tokenizer sees the line, and names are
case-insensitive.

| Command | Effect |
|---|---|
| `)VARS` | the defined variables, sorted by character code, separated by spaces, wrapped at column 40 (a name that would end past column 40 starts a new line) |
| `)FNS` | the same for the user-defined functions |
| `)ERASE a b ...` | undefine variables or functions; the argument is tokenized as APL, so it must be names only (`BAD COMMAND` otherwise, unknown names are ignored) |
| `)CLEAR` | empty the workspace, symbol table and workspace name; prints `CLEAR WS` |
| `)FREE` | collect, then print the heap bytes free (`n BYTES FREE`) |
| `)WSID [name]` | show (or `CLEAR WS`) or set the workspace name: 1-16 of `A-Z 0-9 - .`, lower case folded; `BAD NAME` otherwise, leaving the old name alone |
| `)SAVE [name]` | write the workspace to drive 8; without a name, use the workspace name; prints `SAVED` |
| `)LOAD [name]` | replace the workspace from a file; prints `LOADED` |
| `)LIB` | list the disk in drive 8 as the drive reports it: header, one line per file (blocks, name, type), blocks free; 22 lines at a time, `MORE` waits for a key (RUN/STOP stops) |
| `)SEED n` | set the random number generator from `n`, a decimal number from 0 to 65535 (`BAD COMMAND` for anything else); see Random numbers |
| `)OFF` | reset the machine |

Anything else is `BAD COMMAND`. Drive errors print `FILE NOT FOUND` or `FILE ERROR`;
a bad file prints `NOT A WORKSPACE` (or `WS FULL`).

**Workspace file** (`tools/wsfile.py` is the reference encoder and decoder):

```
"APLW", version 3, number of symbols (2 bytes, little endian)
for each symbol, in symbol order (defined or not):
    name: a length byte, then the characters (our codes)
    value: the tag byte (type | rank<<2), then
        rank 0: the 1-3 data bytes
        rank 1-2: count (2), a length per axis (2 each), the data
      or the tag $80 alone: the symbol has no value
      or the tag $15 (a CHAR vector plus $10), the data of a function (see User-defined functions),
        and a 2-byte checksum of that data (for each byte: add it, rotate 16 bits left)
"E"
```

Every symbol is written because the token streams of functions name symbols by number: loading
recreates the symbols in the same order, so the numbers stay right.

It is a logical format, not a memory image, so saved workspaces survive rebuilds of the
program. It is streamed through the KERNAL (`OPEN`, `CHROUT`, `CHRIN`); after each
operation the drive's error channel is read, because the KERNAL reports nothing for a
missing file or a full disk. The file name sent to the drive is the upper-cased name
(`@0:NAME,S,W` to replace, `NAME,S,R` to read). The workspace name is set by a
successful `)SAVE`, and by `)LOAD` even if it then fails.

`)LOAD` checks the first five bytes before doing anything; only then is the workspace
cleared. It then reads the variables one at a time, recreating each name by running it
through the tokenizer (so symbol indexes are rebuilt, and a name must tokenize to
exactly one name). An array's count must equal its lengths' product and its size must
fit the per-array limit. A function's checksum is verified as soon as its data is read; a
mismatch makes the file `NOT A WORKSPACE` (the function is not stored, what was read before
stays). The checksum guards against damage, not against a file made to look right: a
function's token stream is trusted once it passes. A failure part-way (truncated file, bad trailer, bad tag) leaves
the variables read so far in place, and reports the error. An empty file is `NOT A
WORKSPACE`: DOS returns one garbage byte for it, indistinguishable from a bad first byte.

**The drive's error channel.** Closing channel 15 makes CBM DOS close every open file, so the
error channel must stay open while a file is being read: `)LOAD` and `)LIB` open the file, read
the status with `disk_peek` (channel 15 stays open), read the data, and `close_file` closes the file
and then channel 15. `disk_status` (which closes channel 15 itself) is only for when no file is
open, as after a `)SAVE`. VICE's host-folder mode has no such channels, so only the real-drive
test (below) can catch a mistake here.

**`)LIB`** opens `$` like BASIC's `LOAD` (secondary address 0) and reads the program the drive
makes of the directory: a load address, then per line a link (zero at the end), the line number
(the block count) and text ending in a zero. Each line prints as BASIC's `LIST` does: the number,
a space, the text; control codes (the header's reverse-on) are dropped and shifted letters print
as capitals. After 22 lines, if another line follows, `MORE` is printed and a key awaited (any key
continues, RUN/STOP ends the listing); the prompt is erased before the listing goes on. VICE's
host-folder mode lists `.` and `..` and gives 65535 blocks free, a real 1541 lists the disk name
and ID and its real block counts. Extra words after `)LIB` are ignored.

Tests: `tests/test_disk.py` types sessions on VICE with a host folder as drive 8, and (when the
1541 ROM is found, in `roms/dos1541.bin` or VICE's own folders, and `c1541` is installed) on a real
emulated 1541 with a `.d64` image.

Not yet done: a way to choose a drive other than 8, and `)OFF` is untested (it jumps through the
reset vector).

## Display and input

Start-up, the charset, the screen driver, keyboard entry and the line editor are
done (`asm/startup.inc`, `asm/editor.inc`). The machine now boots into a REPL.

- **Start-up** (`startup`, entered from the BASIC stub): `$01 = $36`; the
  KERNAL's cursor blink off and its SHIFT+C= charset switching off (`$CC`, `$0291`:
  that switch rewrites `$D018` and would re-point our charset); the NMI vector at
  `$0318` patched to acknowledge and return; KERNAL messages off; charset
  built; VIC bank 3, `$D018 = $34`; colours; screen cleared; interrupts on.
- **Charset** (`build_charset`): 2 KB at `$D000` indexed by *our* codes, built
  with interrupts off and `$01 = $33`: shapes copied from the character ROM's second
  set (ASCII space to `?`, `@`, `A`-`Z`, `[`, `]`, `a`-`z`), plus hand-drawn glyphs
  for the ASCII the C64 lacks (`\ ^ _ ` { | } ~`), a cursor block at `$7F`, and the
  APL glyphs. The data and the artwork are in `tools/glyphs.py`, which generates
  `asm/glyphs.inc`. The glyphs are drawn to the ROM's stroke weight (columns 1-6, rows 0-6, two-pixel verticals, operators centred on row 3); the artwork in `tools/glyphs.py` is written as pictures so it is easy to change.
- **Screen driver** (`scr_put`, installed as the formatter's `outv`): 40x25,
  direct writes to `$CC00`, our codes are the screen codes. `$0a` is a newline; a
  character in column 39 wraps; below row 24 the screen scrolls one row;
  `scr_back` steps back a cell, across a wrapped line. The cursor pointer shares
  the test log pointer's zero-page slot.
- **Keys** (`tools/keys.py`, which generates `asm/keys.inc`): the KERNAL's `GETIN`
  delivers PETSCII; an unshifted letter is `$41`-`$5A` and a shifted one
  `$C1`-`$DA`, which we type as lower and upper case. The **pound key is a
  prefix**: the next key is looked up in the digraph table, using the standard APL
  keyboard positions where the C64 has the key. The left-arrow key types `←`
  directly.

  | after `£` | types | after `£` | types | after `£` | types |
  |---|---|---|---|---|---|
  | `i` | `⍳` | `-` | `×` | `8` | `≠` |
  | `r` | `⍴` | `=` | `÷` | `4` or `<` | `≤` |
  | `j` | `∘` | `2` | `¯` | `6` or `>` | `≥` |
  | `1` | `¨` | `0` | `⍤` | `'` | `⍬` |
  | `[` | `←` | `]` | `→` | `.` | `⋄` |
  | `,` | `⍝` | `h` | `∆` | shifted `h` | `⍙` |
  | `g` | `∇` | `s` | `⌈` | `d` | `⌊` |
  | `l` | `\|` | `w` | `∧` | `v` | `∨` |
  | `n` | `~` | `a` | `⌽` | `y` | `↑` |
  | `u` | `↓` | shifted `a` | `⊖` | `/` | `⌿` |
  | `?` | `⍀` | | | | |
  | `←` key | `_` | `£` | `\` | anything else | nothing |

- **Line editor** (`edit_key`, `repl`): the line is built in the tokenizer's input
  buffer. Keys append; DEL backspaces (across wrapped rows); RETURN runs the line;
  cursor-up recalls the last non-empty line; SHIFT+CLR/HOME clears the screen and
  redraws the line; other keys do nothing. Lines are capped at 255 characters. The
  prompt is six spaces, the cursor a block drawn while waiting for a key, and
  errors print their names.
- **Test builds**: `-D SELFTEST=1` runs a scripted session of lines
  (`tests/test_screen.py`); `-D KEYTEST=1` reads keys from a script instead of the
  keyboard (`tests/test_keys.py`). Normal builds pass both as 0.

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

Implemented so far: literals, names, assignment, parentheses, indexing and indexed assignment (`asm/index.inc`), `⋄`, the
structural primitives `⍳`, `⍴` and `,` (monadic and dyadic), the scalar
functions in `asm/scalar.inc` (dyadic `+ - × ÷ = ≠ < ≤ > ≥`, monadic `+ - × ÷`),
and reduce `f/` for those ten functions (`asm/reduce.inc`). Everything else
returns NONCE ERROR: other operators, and `f/` for other functions, which are
NONCE ERROR in the model too, and axis brackets and dyadic `⍳` likewise. `x f/ y`
evaluates `x` first (so its errors come first) and then gives NONCE ERROR.

Scalar functions share one engine. Shapes are conformed first (equal, or one
side scalar; otherwise RANK ERROR or LENGTH ERROR), then types are checked
(CHAR is a DOMAIN ERROR except for `=` and `≠`), then a result is allocated and
each element goes through four routines chosen per operation and operand type:
load B, load A, kernel, store. Integer arithmetic runs into an INT result; if
any element overflows int16 the whole operation is redone into a FLOAT result.
Monadic `-` and `÷` run as `0-x` and `1÷x`. The model computes every element
before it checks the result size, so when the allocation fails the 6502 does a
dry run first and a DOMAIN ERROR from any element wins over WS FULL.

Reduce works along the last axis and gives one scalar per row. A scalar operand
comes back unchanged. An empty row gives the function's identity, even for CHAR.
`+` sums exactly: BOOL and INT as integers (INT if the sum fits int16, else
FLOAT), FLOAT in a 40-byte fixed-point accumulator (bit k weighs 2^(k-143), wide
enough for the whole float24 range) rounded once. A one-element row has its own
rules (`÷` of an integer is FLOAT, `-` and `×` of a BOOL is INT, otherwise the
element). Anything longer folds right to left through the full dyadic
function, so INT overflow turns the accumulator FLOAT part-way. A matrix gives
a vector of row results converted to the widest row type. A matrix with no rows gives an empty vector
(of the identity's type; INT for `⌈ ⌊ |`).

The float comparison follows `f_teq` and `_fkey`, including its tolerance
test. That test subtracts, so comparing values whose difference overflows
(`1e38=¯1e38`) is a DOMAIN ERROR in the model, and on the 6502.

One deliberate difference: the model returns echoes only when the whole line
succeeds, so `1 ⋄ A B` prints nothing. The 6502 echoes each statement as it
finishes, like an APL session, and then reports the error. The tests compare
echoes only on lines that succeed.

## Output formatting (6502)

`asm/format.inc` matches `format_value` and `f_format` byte for byte. `fmt_value`
writes the top value's text one byte at a time through `fput` (`jmp (outv)`);
`echo_print` is `fmt_value` plus a newline, ready to be the echo hook once a
screen driver exists. Newline is `$0a` and the high minus is `$90`; a screen
driver will translate.

Numbers print to 4 significant digits, rounded half up on the exact value, and
integers up to 65536 print in full (`f_format`). The model rounds exact
rationals, so an exactly representable value like `123450` is a tie and prints
`1.235E5`; an approximate power-of-ten table would get such ties wrong. Half-up
rounding only needs the first five significant digits, so those are computed
exactly: a large integer by doubling a decimal digit array, a fraction by
repeatedly multiplying its 144-bit binary expansion by 10. Plain notation covers
exponents -5 to 9, otherwise `d.dddE±k`. Vectors are elements joined by spaces;
matrices are laid out in columns as wide as their widest entry, right aligned
(two passes, at most 256 columns, else LIMIT ERROR). The model raises a Python
`ValueError` on a numeric matrix with no rows and columns; the 6502 prints
nothing for it.

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
per element), tokens at `OUTBUF` (1,024 bytes; 3.5 per input byte is the worst case, `.5A.5A...` and `1(1(`... make 3), symbols
at `SYMTAB`.

## Implemented in the model so far

`+ - × ÷` (monadic: identity, negate, signum, reciprocal), `= ≠ < ≤ > ≥`,
`⍳`, `⍴` (monadic and dyadic), `,` (ravel, and catenate on vectors),
`f/` and `f\` for scalar dyadic `f` (including `⌈ ⌊ |`), `a∘.f b`, replicate and compress `a/b`, assignment, `( )`, `⋄`, `⍬`, indexing `A[i]`, `A[i;j]` and indexed assignment `A[i;j]←v`.

NONCE: `¨ ⍤`, `∘.` with a function that is not scalar dyadic, an axis on anything but reduce, scan and `⌽`, `→` outside a function,
user-defined functions.

## REU: overlays, then array spill

Decided 2026-09-26: the machine is meant to run with an REU (VICE `-reu -reusize N`, or an Ultimate's
emulated one). Code in an overlay costs no heap, which is the only way to fit the planned features (the
heap had 3,500 bytes above its 12 KB floor). Without an REU the program still starts and prints
`NO REU: LIMITED FEATURES`; it then has only the resident code, and the overlaid features report an
error. There is one build.

**Built: `asm/reu.inc`.** `reu_detect` (start-up) checks that the registers at `$DF02-$DF05` read back
two patterns, then finds the size by wrap-around (bank N of an REU of N banks is bank 0), setting
`reu_banks` (64 KB banks, 255 for 16 MB, 0 for none). `reu_stash` and `reu_fetch` move a block: the
caller stores the C64 address in `$DF02`, the REU address (offset low, high, bank) in `$DF04` and the
length in `$DF07`, and the call returns when the transfer, which stops the CPU, is done. Tests: py65 with
`tests/harness.py Reu`, which performs the transfer when the program reaches `reu_trig`, and VICE with
real REUs of 128 KB to 16 MB and with none. All the VICE tests now start VICE with `-reu -reusize 512`.

**Built: overlays (`asm/overlay.inc`, `asm/ovimg.inc`).** Each overlay is a `.logical` block assembled to
run at `OVWIN`, and its image sits in the PRG after the resident code, in the RAM the tables and heap later
take over; the tables' first byte is where the images begin (`OVL_IMG`). `startup` calls `reu_detect` and
`ov_init` before anything else, which stashes all the images to REU offset 0. `ov_ensure` (A = id) fetches
an overlay into the window unless it is already there (`ov_cur`); with no REU it fails with error 11,
`NO REU`. A routine in an overlay is reached either through a table that carries the overlay id (the
`)` command table: `.byte 0, id, .word handler`) or through a resident stub, `name: .ovstub routine, id`
(`jsr ov_call` followed by the id and the routine's address; the registers arrive intact and the routine's
`rts` returns to the stub's caller). The window is `OVWIN_SIZE` bytes, the length of the biggest overlay
(checked at build time and by `test_layout.py`, which wants it within 64 bytes). Rules: an overlay may call
resident code, but nothing it calls may load another overlay while it is still running; the test harness
(`Reu.check_switch`, at `ov_fetch`) fails any test that does. Tests: `tests/test_overlay.py`; every other
test now runs the overlaid code through the real dispatcher (py65 loads the images into its REU as
start-up does), and the disk and key tests do so in VICE.

Overlays so far (sizes in bytes; the window is the largest, 1,891): `)` command handlers (`sysov.inc`, 636),
disk commands (`disk.inc`, 1,891), search `⍳ ∊ ⍋ ⍒ ~` (1,613), reshape `⌽ ↑ ↓` (1,316), transpose and axis (593), matrix catenation (714), replicate and expand, also of matrices (1,385), the del
editor (`fdef.inc`, 1,086), monadic floor and ceiling (`floor.inc`, 388) and inner product (`inner.inc`, 1,472). Their entry points in resident
code are stubs (`s_x` runs `p_x`, in `overlay.inc`). Start-up data that is read once (the character shapes,
`glyphs.inc`) sits after the images in the PRG and is not copied anywhere; nothing may write to that RAM
before `build_charset` has read it. The heap went from 15,364 to 20,717 bytes (20,625 with the inner product's stub and evaluator changes).

What stays resident is what loops use all the time (the scalar engine and its kernels, `⍳ ⍴ ,`, indexing,
reduce, the evaluator, calls and branches, the heap and the formatter), so that a user function's loop does
not fetch an overlay on every line (a fetch costs about a millisecond per KB). Code called by an overlay
must be resident too: that is why `elemaddr` (index), `k_ires`, `k_fres`, `flr_q` and `f_floor` did not move.
New features are written as overlays, so they cost the stubs and (if bigger than 1,891 bytes) window growth,
not heap.

**Array spill (built).** When an allocation does not fit even after garbage collection, arrays that only a variable holds are moved to
the REU and come back when they are next used, so a workspace can be much bigger than main RAM. Code: the end of `asm/heap.inc`.

- **Where they go.** Each handle has a fixed 16 KB slot in the REU: handle `h` is at `$10000 + h × $4000` (bank `1 + h>>2`, four to a bank; bank 0 holds the overlay
  images), so where a spilled array is needs no table. A slot holds the block as it was in the heap (header and data, without the handle byte; at most 16,007
  bytes). A handle whose bank is beyond the REU's size has no slot: its array is never spilled. Full coverage of all 256 handles needs an REU of 4,160 KB; a
  4 MB one (the launcher's) covers handles up to 251. A spilled array has `HTH = $FF` and no block in the heap.
- **What may spill.** `gc` marks handles: 2 = in use (an operand on the value stack, the pinned result, or a function's block, which is run in place and never
  moves), 1 = only a variable holds it; only marks of 1 are candidates. The rule that makes it safe: **everything on the value stack is in the heap**, so a
  routine that has looked at its operands can allocate without them moving out from under it. `pushcv` (the one way anything is pushed) brings a spilled array back
  first (`fault_in`), `ensure_res` does the same for code that reads a variable directly (`)SAVE`), and `getval` traps (`spill_bug`) if it ever meets a spilled array.
- **When.** `alloc`: try, collect, try, and then (if `reu_banks` is not 0) `spill_for`: pick the biggest candidate, stash it (DMA), mark it `$FF`, repeat until the free space
  plus what was freed covers the request, then compact (which drops the spilled blocks) and try again; WS FULL if that is still not enough or nothing can move. `fault_in`
  reads the block's header from the slot, works out its size, allocates it (which may spill others) and fetches it, under the same handle number. `gc` also frees a
  spilled handle nothing refers to any more.
- **Limit.** One operation's operands and result must fit in the heap together (chunked operations would lift that); with no REU nothing changes.
- **The heap's top is a variable** (`hlim`, initially `HEAP_LIMIT`) so the tests can make the heap small.
- **Tests.** `tests/test_heap.py` (invariants with spilled handles, the stack never spills, `pushcv` faults arrays in), `tests/test_spill.py` (the evaluator's own cases, a
  random workspace of a dozen 100-400 element variables, and function sessions in heaps of 1.2 to 20 KB, some squeezed to a few hundred bytes free at every allocation, some
  with every block also moved at each allocation, all matching the model), and the real-VICE screen session, which holds seven 3 KB arrays in a 19 KB heap and asserts that
  some are in the REU at the end.

## Graphics

Done 2026-09-26: the multicolor bitmap (160 x 200, four values per pixel) and the hires bitmap (320 x 200, two values), two modes of the
same functions (`⎕GR 1`, `⎕GR 2`). Model: `apl64.py`, section Graphics; 6502: two overlays (so an REU is needed), `asm/gfx.inc` (mode and colours, 1.4 KB) and
`asm/draw.inc` (plot, line, box, 1.8 KB), which share `asm/gfxcom.inc` by including it each inside a `.block` of its own (`g1`, `g2`); tests: `tests/test_gfx.py` (py65 against the model, the picture compared byte for byte) and
`tests/test_gfx_vice.py` (real VICE: registers, memory and a screenshot).

**Where the picture lives.** The bitmap is the 8000 bytes at `$E000` (RAM under the KERNAL, in VIC bank 3, so it costs no
heap); the CPU sees it only with `$01` bit 1 cleared and interrupts off, which the drawing loops do around themselves
(`gq_ron`/`gq_roff`; `$01` is restored to what it was). Cell colours are the text screen's RAM (`$CC00`, 1000 bytes: the
high nibble is the colour of pixel value 1, the low nibble that of value 2) and colour RAM (`$D800`, value 3); value 0 is
the background (`$D021`, and the border follows it). `$D011` bit 5, `$D016` bit 4 and `$D018 = $38` switch the mode.
The model keeps exactly these three byte arrays, and the tests compare them.
**Hires** (`$D016` bit 4 clear): one bit per pixel, the leftmost in bit 7 of the byte; pixel value 1 shows the high nibble of the cell's screen RAM byte, 0 the low nibble; colour RAM is not used (left as it was, and not compared); the border follows pixel value 0's colour. The code that differs by mode is table-driven (`gq_mo`, `gq_xm`, `gq_xlim`, tables indexed by the pixel's place in its byte plus 0 or 4).

**Text and graphics share the screen RAM**, so entering graphics mode (`⎕GR 1`) stashes the text screen in the REU
(bank 0, `$E000`, above the overlay images: `ovimg.inc` checks that they end below it) and leaving puts it back and refills
colour RAM with the text colour. While a picture is up (`gr_on` = $80) the screen driver ignores everything printed
(`scr_put`), so no echo or message can damage the colours. The REPL, after each line, waits for a key if the line left
a picture up (`gr_after`), then leaves graphics mode, and only then prints an error message. So a picture stays until a key
is pressed, and several drawing statements must be on one line (with `⋄`) or in a function. (A split screen, with a
few text lines under the picture, would need a raster interrupt: not done.)

**Sprites** (asm/spr.inc, a third graphics overlay of 1.3 KB; model section Sprites; `tests/test_spr.py`, and a screenshot check in `test_gfx_vice.py`). They work in text and graphics modes alike.
The VIC-II's 8 sprites are 24 x 21 pixels. Their 28 shapes live in the RAM under the I/O area (`$D800`-`$DEFF`, 64 bytes each: pointers 96 to 123; `$DF00` up is left alone
because the REU's registers are there), and the pointers are the last 8 bytes of screen RAM (`$CFF8`, which screen clearing rewrites: `spr_setptrs`). Start-up empties the shapes and
points sprite n at shape n. Sprites are never switched off by leaving graphics mode: `⎕SPR 0` hides them all.

| call | does |
|---|---|
| `s ⎕SPD shape` | shape slot s (0-27) is defined by a 21 x 24 matrix of 0/1 (hires sprite), a 21 x 12 matrix of 0-3 (multicolor: two bits a pixel, so half as wide) or 63 bytes |
| `n ⎕SPR x y shape colour flags` | sprite n (0-7) goes to (x, y) and is switched on; the first 2, 3, 4 or 5 numbers: `shape` 0-27, `colour` 0-15, `flags` 0-15 = 1 multicolor + 2 double width + 4 double height + 8 behind the picture |
| `⎕SPR m` | the sprites switched on: bit n of m for sprite n (`⎕SPR 0` hides all) |
| `n ⎕MOVE x,y` | moves sprite n through the positions (x's then y's joined in one vector), one to each video frame, and switches it on: exact 50-a-second animation from one statement. `(n, first, count) ⎕MOVE x,y` plays `count` positions from position `first` (1 up) of a longer table, so a whole tune's worth of motion can be computed once and played a piece at a time |
| `⎕SPC a b` | the two colours multicolor sprites share: pixel value 1 shows a, value 3 shows b, value 2 the sprite's own colour, 0 is clear |

Coordinates are the 320 x 200 screen's physical pixels with (0, 0) at the top left of the picture: x from -24 to 487 (past the right edge, and off the left), y from -50 to 205; numbers are floored,
anything outside is DOMAIN. (Multicolor pictures have pixels two physical pixels wide, so x is doubled against `⎕PLOT`'s.) Lower-numbered sprites are in front. The model keeps the VIC-II's
sprite registers, the pointers and the shape memory as bytes, and the tests compare them; VICE compares every pixel of a screenshot with sprites rendered from the model.

**How fast is it?** The interpreter's own work is what limits animation: a statement costs about 6 ms (a video frame is 20 ms), a scalar index `X[I]` about 8 ms more, indexing a matrix row about 1 ms an element,
float arithmetic 1-3 ms an element, integer 0.3-0.5. The hardware operations are cheap: a `⎕SPR` about 1 ms, a full-screen `⎕BOX` 0.3 s, `⎕PLOT` 0.25 ms a point. So do the arithmetic for a whole
animation once, up front, into vectors, and let `⎕MOVE`, `⎕PLOT` or `⎕BOX` consume them; a loop that computes as it draws manages 15 to 20 steps a second at best. `demos/ode.txt` computes its
448 frames of ball movement in 4 seconds before it starts, then plays each note with five short statements.

**Sound and keys** share the quad names and the overlay `gfx.inc`; they work in text mode. `⎕SND` has no dependence on graphics; the tests compare the 25 SID registers with the model's copy. The quad functions with a token below `$AC` give no value (`qfin` drops their dummy result); `⎕KEY` (index 12) is the first to give one.

**The functions** (quad names, tokens `$A0` and up; the tokenizer takes `⎕` and up to four letters, either case, from
`asm/quadnames.inc`, generated from `apl64.QUAD_NAMES`; on the keyboard `⎕` is pound then shifted L). None gives a
value: like a function without a result, a call may only end a statement (`A←⎕GR 1`, `1+⎕INK 2` and `(⎕GR 1)` are VALUE
ERROR); the evaluator drops the dummy result the overlay leaves (`qfin`).

| call | does |
|---|---|
| `⎕GR 1`, `⎕GR 2` / `⎕GR 0` | multicolor (160 x 200, cleared, palette `0 1 2 14`, ink 1) or hires (320 x 200, white on black) picture on / back to text; other values DOMAIN. Going from one mode to the other clears the picture |
| `⎕PAL b c1 c2 c3` | the background and the three cell colours (0-15) of every cell |
| `rows ⎕PAL c1 c2 c3` | the three cell colours of those cell rows (0-24), each of 40 cells: horizontal colour bands. Hires: two colours `c0 c1` |
| `rows ⎕PAL cs` | the same with three colours for each row: `cs` has 3 times as many numbers as `rows`, a vector or a matrix with a row per row; one call sets a whole gradient (in hires, two colours per row) |
| `⎕INK n` | the pixel value (0-3, hires 0-1) the drawing functions use |
| `x ⎕PLOT y` | points; x and y are vectors of the same length, or one may be a single number; off-screen points are skipped |
| `(x0 y0) ⎕LINE (x1 y1)` | Bresenham's line, ends included; end points within ±4095 (DOMAIN otherwise: the arithmetic stays in 16 bits) |
| `⎕BOX x0 y0 x1 y1` | the same with the four numbers in one vector: one index `Q[i;]` into a table of rectangles is all a bar chart costs |
| `(x0 y0) ⎕BOX (x1 y1)` | the filled rectangle between two corners, clipped to the screen |
| `⎕WAIT n` | n video frames (RUN/STOP ends it); 50 a second on a PAL machine |
| `⎕KEY n` | *gives a value*: the code of a key pressed (the KERNAL's GETIN, PETSCII: RETURN 13, space 32, cursor up 145, down 17, left 157, right 29, unshifted letters 65-90, shifted 193-218), waiting up to n frames for one (0: look once); 0 if none came. Works in text mode too; RUN/STOP ends the wait. Keys come through `getkey_vec`, so the tests script them |
| `⎕SND n` | the SID's master volume (0-15; start-up sets 15) |
| `v ⎕SND f w a d s r p` | voice v (1-3) is given up to seven whole numbers, only these counts being allowed: 1 (`f`), 2 (`f w`), 4 (`f w a d`), 6, 7. `f` frequency 0-65535 (the SID's units: Hz x 17.03 on a PAL machine; A 440 is 7492), `w` waveform 0-15 (1 triangle, 2 sawtooth, 4 pulse, 8 noise; sums mix them; 0 turns the gate off: the voice dies away at its release rate; anything else turns it on), `a d s r` attack, decay, sustain, release 0-15, `p` pulse width 0-4095. A register pair is always written whole because the SID's registers cannot be read back (nothing is kept in RAM) |

Coordinates are pixels from the top left, x 0-159 (hires 0-319), y 0-199. Numbers are floored (so `⌊` is not needed on computed
coordinates) and saturate at the ends of the int16 range; CHAR arguments are DOMAIN. All but `⎕GR` and `⎕WAIT` need
graphics mode (NO GRAPHICS, error 12). Checks run in a fixed order, which the model and the machine share: mode, CHAR
arguments (right then left) DOMAIN, lengths LENGTH, then values DOMAIN.

**Code.** `apply_mon`/`apply_dy` send tokens `$A0`-`$AF` to the overlay (`s_gfxm`/`s_gfxd`, function number in A); the
routines are dispatched by pushing their addresses and `rts`. Arguments are read through `gq_elem` (int, bool or float
element as a saturated int16; floats through the resident `flr_q`). Each pixel is set by `gq_pix` from a table of cell-row
addresses. Splitting the code over two overlays keeps the window at 2,216 bytes (the biggest overlay, still the numeric functions; the window's size
is computed in `ovimg.inc`); the resident additions (dispatch, the tokenizer's quad names, `qfin`, `gr_after`, stubs) took the heap from 19,112
to 18,812 bytes. `⎕BOX` sets the bytes of a row whole, with masks for the two ends, so a full screen takes 0.3 s (pixel by pixel it was 6).

Reasons for the choices: floats need no `⌊` because demos compute coordinates all the time; `⎕PLOT` takes two vectors because
`x y ⎕PLOT` with a matrix would need a reshape on every call; points off the screen are skipped, not errors, because a curve
may leave the picture; lines are limited to ±4095 so the whole algorithm is 16 bit.

## Next steps

Done (6502, differentially tested under py65): float24 add, sub, mul, div;
int16 add, sub, mul with the all-or-nothing redo in float24; tokenizer;
handle heap and GC; evaluator core with the structural primitives, the scalar
functions, reduce and the output formatter.

1. Memory map: implement the plan above (three decisions to confirm first).
2. Trimming code (see the heap figure above; `)LIB` is done) and a drive selector; then the
   language features the model still lacks (more operators, user-defined
   functions).
3. Model: matrix catenate, `∘.`, `\`, user functions, control flow.
4. Later options: bit-packed BOOL, 4-byte float, transcendentals, fusion of
   scalar pipelines (e.g. `+/A×B` in one loop).

## Recording demo videos

`python3 tools/record.py demos/tour.txt out.mp4` starts VICE on a private Xvfb display at real speed, waits for
the program, captures the VICE window (menu and status bar included) with ffmpeg's x11grab at 50 fps, and types
the demo file through xdotool, so the typing goes through the real keyboard path. Glyphs are written as they
display and are typed as pound-key digraphs; `\` is typed as the pound key twice; `←` is VICE's End key (the
symbolic keymap's left arrow). Keys are held 80 ms: VICE scans the keyboard once a frame, and quicker taps
(and shifted keys especially) were lost. This VICE build has no ffmpeg movie recorder, and its own wav recorder writes nothing; the sound is captured instead from a PulseAudio null sink that VICE is pointed at (`PULSE_SINK`), by the same ffmpeg that grabs the screen. Shifted keys are typed with the shift key pressed first and held. `@speed N` in a demo file plays the video from there N times faster (the typing of a long function is best seen as a time-lapse; the recorder cuts the
capture into stretches and re-encodes it with ffmpeg). `demos/sunset.txt` is the graphics demo. Generated videos are not committed (they show ROM-derived text); use `)SEED` to make random demos repeat.
