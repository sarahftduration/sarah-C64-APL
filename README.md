# APL for the Commodore 64

- `apl64.py`: executable reference model (tokenizer, evaluator, float24, primitives)
- `DESIGN.md`: the design decisions and the byte-level formats the 6502 must match

    python3 apl64.py --test   # self-test
    python3 apl64.py          # REPL (input needs the ¯ ← ⍳ ⍴ × ÷ glyphs)

## Tests

    make test          # the full regression suite, test files in parallel (tools/run_tests.py)
    make timed-test    # the same, and appends the durations to tests/timing.csv
    make test-serial   # one file at a time, stopping at the first failure

Run the timed one when you run the whole suite, and commit `tests/timing.csv` with the change, so
the growth of the suite's running time can be followed over time. Test files that build and run
images use a private scratch directory (`tests/harness.py`, `scratch()`), which is what lets them
run at the same time; a new file that writes files must do the same. The run time is now set by the
slowest file (`test_format.py`), so more CPUs will not help until that file is split.

## Toolchain for the 6502 work

- Assembler: 64tass or ca65 (cc65 suite)
- `pip install py65` for headless testing
- VICE (`x64sc`) for integration checks

Suggested layout as it grows: `asm/` for the runtime, `tests/` for the
differential harness, a `Makefile` to assemble and diff.
