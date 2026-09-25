PY    := .venv/bin/python
ASM   := 64tass
SRCS  := $(wildcard asm/*.asm)
BINS  := $(SRCS:asm/%.asm=build/%.bin)

.PHONY: all test model-test clean
all: $(BINS)

build/%.bin: asm/%.asm
	@mkdir -p build
	$(ASM) --nostart --labels=build/$*.lbl --list=build/$*.lst -o $@ $<

test: model-test $(BINS)
	@for t in tests/test_*.py; do PYTHONPATH=tests $(PY) $$t || exit 1; done

model-test:
	python3 apl64.py --test

clean:
	rm -rf build
