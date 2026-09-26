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

Code and read-only tables **19,288 bytes** (`$0801`-`$5358`, including the start-up
code, screen driver, charset data, editor and system commands: about 4 KB); tables
7,832 bytes; **heap 23,000 bytes** (`$7228` to `$CBFF`; it starts where the tables
end). **The heap has a floor of 16 KB** (the build fails below it, and `tests/test_layout.py`
checks it); it was 24 KB until the features still to come needed the room, on the reasoning that
a plain C64 is for small workspaces and an REU (see the storage tier below) is for big ones. Code
now costs heap byte for byte: the tables that need a page (`VARS`, `VSTACK`, `SYMTAB`) start on a
page boundary, and the tables that do not need one (`RV`, `FMT`, `FACC`, `DIGS`, `FR`) fill the gap
before it when they fit (`asm/bss.inc`), so there is no cliff where the heap suddenly loses 256
bytes. The tables are sized by proven worst cases (6 bytes of tokens per input byte, 85 levels of
nesting, 256 handles and names), so shrinking them means lowering a limit. Code that is only
needed by the tests (the echo log) and repeated out-of-range branches are the first
places to save. Read-only indexing cost 1,302 bytes of code (about 850 in `asm/index.inc`, the rest
in the evaluator's bracket frames), so the heap went from 24,792 to 23,512 bytes; indexed assignment took another 512 (23,000). The per-array limit `WS_BYTES` / `wsmax` is 16,000 bytes.

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
2,048; token output 1,536 (6 bytes per input byte, worst case); number-strand
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
   the model, `wsmax` on the 6502), about three quarters of the old 24 KB minimum heap. With the 16 KB floor the heap itself
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

## Errors

`DOMAIN ERROR, LENGTH ERROR, RANK ERROR, SYNTAX ERROR, VALUE ERROR,
NONCE ERROR (not implemented), LIMIT ERROR, WS FULL, INDEX ERROR` (codes 1 to 9 on the
6502, in that order except that INDEX ERROR is 9: an index outside `1..length`)

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
| `)ERASE a b ...` | undefine variables; the argument is tokenized as APL, so it must be names only (`BAD COMMAND` otherwise, unknown names are ignored) |
| `)CLEAR` | empty the workspace, symbol table and workspace name; prints `CLEAR WS` |
| `)FREE` | collect, then print the heap bytes free (`n BYTES FREE`) |
| `)WSID [name]` | show (or `CLEAR WS`) or set the workspace name: 1-16 of `A-Z 0-9 - .`, lower case folded; `BAD NAME` otherwise, leaving the old name alone |
| `)SAVE [name]` | write the workspace to drive 8; without a name, use the workspace name; prints `SAVED` |
| `)LOAD [name]` | replace the workspace from a file; prints `LOADED` |
| `)LIB` | list the disk in drive 8 as the drive reports it: header, one line per file (blocks, name, type), blocks free; 22 lines at a time, `MORE` waits for a key (RUN/STOP stops) |
| `)OFF` | reset the machine |

Anything else is `BAD COMMAND`. Drive errors print `FILE NOT FOUND` or `FILE ERROR`;
a bad file prints `NOT A WORKSPACE` (or `WS FULL`).

**Workspace file** (`tools/wsfile.py` is the reference encoder and decoder):

```
"APLW", version 1, number of variables (2 bytes, little endian)
for each defined variable, in symbol order:
    name: a length byte, then the characters (our codes)
    value: the tag byte (type | rank<<2), then
        rank 0: the 1-3 data bytes
        rank 1-2: count (2), a length per axis (2 each), the data
"E"
```

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
fit the per-array limit. A failure part-way (truncated file, bad trailer, bad tag) leaves
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
NONCE ERROR in the model too, and `→`, axis brackets and dyadic `⍳` likewise. `x f/ y`
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
a vector of row results converted to the widest row type. The model raises a
Python IndexError on a matrix with no rows; the 6502 returns an empty vector.

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
per element), tokens at `OUTBUF` (6 bytes per input byte is enough), symbols
at `SYMTAB`.

## Implemented in the model so far

`+ - × ÷` (monadic: identity, negate, signum, reciprocal), `= ≠ < ≤ > ≥`,
`⍳`, `⍴` (monadic and dyadic), `,` (ravel, and catenate on vectors),
`f/` for scalar dyadic `f`, assignment, `( )`, `⋄`, `⍬`, indexing `A[i]`, `A[i;j]` and indexed assignment `A[i;j]←v`.

NONCE: `\ ¨ . ∘ ⍤`, replicate (`n/x`), axis brackets, branch `→`,
catenate on matrices, index-of (dyadic `⍳`), user-defined functions.

## Plan: optional extra RAM (REU) as a storage tier

Not built yet. The decisions so far (from the design discussion):

- **Never required.** The interpreter runs in plain C64 RAM exactly as today; a plain machine is for
  small workspaces. With a RAM Expansion Unit (VICE `-reu -reusize N`, or an Ultimate cartridge's
  emulated one) it uses the extra RAM automatically, detected at start-up.
- **What it does.** The CPU cannot address an REU; a DMA controller copies blocks between it and main
  RAM. So it is used to *spill* arrays: each handle is either resident in the heap or held in the REU,
  and `getval` (the one place an array's data address is derived) makes an array resident before use.
  When the heap is full, instead of WS FULL, live arrays that are not the operands of the current
  operation (the top one or two stack cells) or its pinned result are moved out. Marking needs no
  change, since `gcmark` reads only cells. Without an REU the spill path is off and the behaviour is
  today's.
- **Limit.** One operation's operands and result must still fit in main RAM together. Arrays larger
  than that (streaming through chunks) are a later step.
- **Cost.** A table saying where each spilled array is: about 512 bytes, allocated at start-up only
  if an REU is present, so a plain machine pays nothing.
- **Testing.** Differential: the same sessions with a tiny main heap and a VICE REU must give the
  results of the model, whether or not arrays spilled. `tests/test_stress.py` already enforces the
  precondition, that no data address survives an allocation.
- **Also possible later:** `)SAVE` / `)LOAD` to an REU "drive", workspace snapshots, and code overlays
  for rarely used parts, kept optional by leaving a resident or disk-loaded copy.

Also planned later: graphics. A hires bitmap can live at `$E000` in VIC bank 3 (the RAM under the
KERNAL, which the interpreter cannot use), with its colour map under the I/O area, so it costs no
heap; the cost is drawing code and a way to call it from APL.

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
