"""The memory map (DESIGN.md) checked from the label file: nothing overlaps, everything is where the plan says."""
import os
import re
import sys

sys.path.insert(0, os.getcwd())
from harness import ZP_ALLOWED, load

_, L = load("eval")
code_end = L["OVL_IMG"]                 # the resident code; the overlay images follow it in the PRG


def test_layout():
    # the program image and the BASIC stub
    assert L["ORG"] == 0x0801 and L["start"] == 2061
    # fixed low RAM: transient line buffers in the old screen, variables in the tape buffer
    assert L["INBUF"] == 0x0400 and L["TC"] + 256 <= 0x0800
    assert 0x033C <= L["WS"] + 0x50 and L["WS"] + 0xFF <= 0x03FC, "variable block leaves the tape buffer"
    # the tables lie between the code and the heap and never overlap. Those that need a page start on one; the
    # rest may sit in the gap before the first page boundary (bss.inc), so the space left over is under a page.
    sizes = {"HTL": 256, "HTH": 256, "HM": 256, "VARS": 1024, "VSTACK": 512, "FSTK": 256, "SYMTAB": 2048,
             "OUTBUF": 1024, "SBUF": 512, "SDV": 8, "RV": 76, "FACC": 40, "FMT": 96, "DIGS": 40, "FR": 24,
             "COLW": 256, "STV": 96, "HIST": 256, "FNBUF": 32, "FNPFX": 4, "CMDBUF": 12, "WSNAME": 20, "NAMETMP": 20,
             "OVWIN": L["OVWIN_SIZE"]}
    spans = sorted((L[n], L[n] + size, n) for n, size in sizes.items())
    assert spans[0][0] >= code_end and spans[-1][1] <= L["HEAP_BASE"]
    wasted = spans[0][0] - code_end + L["HEAP_BASE"] - spans[-1][1]
    for (a, b, n), (a2, b2, n2) in zip(spans, spans[1:]):
        assert b <= a2, f"tables overlap: {n} and {n2}"
        wasted += a2 - b
    assert wasted < 256, f"{wasted} bytes between the tables are unused"
    assert L["BSS0"] % 256 == 0 and L["BSS0"] >= code_end and L["HTL"] == L["BSS0"]
    assert L["VARS"] % 256 == 0 and (L["SDV"] & 0xFF) <= 0xF8, "SDV holds jmp (indirect) vectors: none may straddle a page"
    assert {n: L[n + "_EARLY"] for n in ("RV", "FACC", "FMT", "DIGS", "FR")}, "gap placement flags"
    for n in ("RV", "FACC", "FMT", "DIGS", "FR"):
        assert (L[n] < L["BSS0"]) == bool(L[n + "_EARLY"]), n
    assert sizes["VARS"] == 1024 and sizes["VSTACK"] == 512 and sizes["FSTK"] == 256
    assert L["VSTACK"] % 256 == 0 and L["VSTACK_END"] == L["VSTACK"] + 512
    assert L["SYMTAB"] % 256 == 0 and L["SYMEND_HI"] == (L["SYMTAB"] + 2048 >> 8) - 1
    assert L["FK"] == L["FSTK"] and L["FFN"] + 64 == L["FSTK"] + 256
    # overlays: the images follow the resident code in the PRG and fit the window, which the tables place last
    assert L["ORG"] + os.path.getsize("build/eval.bin") == L["INIT_END"] and L["INIT_START"] == L["OVL_IMG"] + L["OVL_TOT"]
    assert L["OVL_TOT"] < 0x10000 and L["OVWIN"] + L["OVWIN_SIZE"] == L["HEAP_BASE"]
    biggest = max(L[n] for n in L if n.startswith("OVN_"))
    assert biggest <= L["OVWIN_SIZE"] and L["OVWIN_SIZE"] - biggest < 64, "the window should be as small as the biggest overlay allows"
    # the heap: at least 12 KB (the floor DESIGN.md sets), ending under the screen; the test log lives above the machine's RAM map
    assert L["HEAP_LIMIT"] == 0xCC00 and L["HEAP_LIMIT"] - L["HEAP_BASE"] >= 0x3000
    assert L["LOGBUF"] >= 0xD000
    # zero page: every pool pointer is inside the allowed range and none overlap
    ptrs = ["op", "tp", "sp", "ep", "qsrc", "mp", "fp", "sdpa", "sdpb", "hadr", "gsrc", "gp", "cs", "cd", "vsp",
            "cptr", "vp", "dp", "logp"]
    used = []
    for n in ptrs:
        assert L[n] in ZP_ALLOWED and L[n] + 1 in ZP_ALLOWED and L[n] < 0x76, n
        used += [L[n], L[n] + 1]
    assert len(set(used)) == len(used), "pointer pool overlaps"
    # zero-page variables never overlap (sizes come from how the code uses each name)
    src = ""
    for f in sorted(os.listdir("asm")):
        if f.endswith((".asm", ".inc")) and f != "smoke.asm" and f != "pow10.inc":
            src += open("asm/" + f).read() + "\n"
    zp = {}
    for line in src.split("\n"):
        m = re.match(r"^([a-z][A-Za-z0-9_]*)\s*=\s*\$([0-9a-f]{2})\b", line)
        if m:
            zp[m.group(1)] = int(m.group(2), 16)
    body = "\n".join(l.split(";")[0] for l in src.split("\n") if not re.match(r"^[A-Za-z_]\w*\s*=", l))
    spans = []
    for n, a in zp.items():
        refs = re.findall(r"(?<![\w.])" + re.escape(n) + r"(?:\s*\+\s*(\d+))?(?![\w])", body)
        size = max([int(r) if r else 0 for r in refs] or [0]) + 1
        if n in ("fa", "fb"):
            size = 3
        if n == "ptr" or n in ("ep", "op", "tp", "sp", "qsrc", "mp", "fp", "sdpa", "sdpb", "hadr", "gsrc", "gp", "cs", "cd",
                               "vsp", "cptr", "vp", "dp", "logp"):
            size = 2
        spans.append((a, a + size - 1, n))
    spans.sort()
    alias_ok = {frozenset(x) for x in [("p0", "rl"), ("p1", "rh"), ("p2", "ql"), ("p3", "qh")]}
    for i, (a, b, n) in enumerate(spans):
        assert a in ZP_ALLOWED and b in ZP_ALLOWED, (n, hex(a))
        for a2, b2, n2 in spans[i + 1:]:
            if a2 > b:
                break
            assert frozenset((n, n2)) in alias_ok, f"zero-page variables overlap: {n} ${a:02X}-${b:02X} and {n2} ${a2:02X}"
    print(f"layout: code ${L['ORG']:04X}-${code_end - 1:04X} ({code_end - L['ORG']} bytes) and {L['OVL_TOT']} bytes of overlays, tables to "
          f"${L['HEAP_BASE'] - 1:04X}, heap {L['HEAP_LIMIT'] - L['HEAP_BASE']} bytes; all invariants hold")


if __name__ == "__main__":
    test_layout()
