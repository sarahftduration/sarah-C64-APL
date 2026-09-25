# APL for the Commodore 64

- `apl64.py`: executable reference model (tokenizer, evaluator, float24, primitives)
- `DESIGN.md`: the design decisions and the byte-level formats the 6502 must match

    python3 apl64.py --test   # self-test
    python3 apl64.py          # REPL (input needs the ¯ ← ⍳ ⍴ × ÷ glyphs)

## Tests

    make test          # the full regression suite
    make timed-test    # the same, timed; appends the durations to tests/timing.csv

Run the timed one when you run the whole suite, and commit `tests/timing.csv` with the change, so
the growth of the suite's running time can be followed over time.

## Toolchain for the 6502 work

- Assembler: 64tass or ca65 (cc65 suite)
- `pip install py65` for headless testing
- VICE (`x64sc`) for integration checks

Suggested layout as it grows: `asm/` for the runtime, `tests/` for the
differential harness, a `Makefile` to assemble and diff.
