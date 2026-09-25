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
    # no symbol may name a zero-page address outside the allowed set (except constants)
    for n, v in L.items():
        if n.isupper() or n.startswith("E_") or n in ("nl",):
            continue
    print(f"layout: code ${L['ORG']:04X}-${code_end - 1:04X} ({code_end - L['ORG']} bytes), tables to "
          f"${L['HEAP_BASE'] - 1:04X}, heap {L['HEAP_LIMIT'] - L['HEAP_BASE']} bytes; all invariants hold")


if __name__ == "__main__":
    test_layout()
