PY    := .venv/bin/python
ASM   := 64tass -D SELFTEST=0 -D KEYTEST=0
SRCS  := $(wildcard asm/*.asm)
BINS  := $(SRCS:asm/%.asm=build/%.bin)
INCS  := asm/pow10.inc asm/glyphs.inc asm/keys.inc $(wildcard asm/*.inc)

.PHONY: all test timed-test model-test clean prg
all: $(BINS)

asm/pow10.inc: tools/gen_pow10.py
	python3 tools/gen_pow10.py > $@

asm/glyphs.inc: tools/gen_glyphs.py tools/glyphs.py
	python3 tools/gen_glyphs.py > $@

asm/keys.inc: tools/gen_keys.py tools/keys.py
	python3 tools/gen_keys.py > $@

# every binary depends on every source: the .asm files include each other
$(BINS): $(SRCS) $(INCS)

build/%.bin: asm/%.asm
	@mkdir -p build
	$(ASM) --nostart --labels=build/$*.lbl --list=build/$*.lst -o $@ $<

test: model-test $(BINS) build/apl.prg
	@for t in tests/test_*.py; do PYTHONPATH=tests $(PY) $$t || exit 1; done

# the full suite, timed: prints the duration and appends it to tests/timing.csv
timed-test:
	@tools/timed_test.sh

prg: build/apl.prg

build/apl.prg: $(SRCS) $(INCS)
	@mkdir -p build
	$(ASM) -o $@ asm/eval.asm

model-test:
	python3 apl64.py --test

clean:
	rm -rf build
