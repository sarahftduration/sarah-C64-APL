PY    := .venv/bin/python
ASM   := 64tass
SRCS  := $(wildcard asm/*.asm)
BINS  := $(SRCS:asm/%.asm=build/%.bin)
INCS  := asm/pow10.inc

.PHONY: all test model-test clean
all: $(BINS)

asm/pow10.inc: tools/gen_pow10.py
	python3 tools/gen_pow10.py > $@

# every binary depends on every source: the .asm files include each other
$(BINS): $(SRCS) $(INCS)

build/%.bin: asm/%.asm
	@mkdir -p build
	$(ASM) --nostart --labels=build/$*.lbl --list=build/$*.lst -o $@ $<

test: model-test $(BINS)
	@for t in tests/test_*.py; do PYTHONPATH=tests $(PY) $$t || exit 1; done

model-test:
	python3 apl64.py --test

clean:
	rm -rf build
