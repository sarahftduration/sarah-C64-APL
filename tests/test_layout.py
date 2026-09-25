"""The memory map (DESIGN.md) checked from the label file: nothing overlaps, everything is where the plan says."""
import os
import re
import sys

sys.path.insert(0, os.getcwd())
from harness import ZP_ALLOWED, load

_, L = load("eval")
code_end = L["ORG"] + os.path.getsize("build/eval.bin")


def test_layout():
    # the program image and the BASIC stub
    assert L["ORG"] == 0x0801 and L["start"] == 2061
    # fixed low RAM: transient line buffers in the old screen, variables in the tape buffer
    assert L["INBUF"] == 0x0400 and L["TC"] + 256 <= 0x0800
    assert 0x033C <= L["WS"] + 0x50 and L["WS"] + 0xFF <= 0x03FC, "variable block leaves the tape buffer"
    # tables follow the code, in order, without overlap; the heap follows the tables
    order = ["HTL", "HTH", "HM", "VARS", "VSTACK", "FSTK", "SYMTAB", "OUTBUF", "SBUF", "SDV", "RV", "FACC", "FMT",
             "DIGS", "FR", "COLW", "HEAP_BASE"]
    assert L["BSS0"] >= code_end and L["BSS0"] % 256 == 0
    addrs = [L[n] for n in order]
    assert addrs == sorted(addrs) and len(set(addrs)) == len(addrs), "tables out of order or overlapping"
    assert L["HTL"] == L["BSS0"]
    sizes = {n: b - a for n, a, b in zip(order, addrs, addrs[1:])}
    assert sizes["VARS"] == 1024 and sizes["VSTACK"] == 512 and sizes["FSTK"] == 512
    assert L["VSTACK"] % 256 == 0 and L["VSTACK_END"] == L["VSTACK"] + 512
    assert L["SYMTAB"] % 256 == 0 and L["SYMEND_HI"] == (L["SYMTAB"] + 2048 >> 8) - 1
    assert L["FK"] == L["FSTK"] and L["FFN"] + 128 == L["FSTK"] + 512
    # the heap: at least 24 KB, ending under the screen; the test log lives above the machine's RAM map
    assert L["HEAP_LIMIT"] == 0xCC00 and L["HEAP_LIMIT"] - L["HEAP_BASE"] >= 0x6000
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
    print(f"layout: code ${L['ORG']:04X}-${code_end - 1:04X} ({code_end - L['ORG']} bytes), tables to "
          f"${L['HEAP_BASE'] - 1:04X}, heap {L['HEAP_LIMIT'] - L['HEAP_BASE']} bytes; all invariants hold")


if __name__ == "__main__":
    test_layout()
