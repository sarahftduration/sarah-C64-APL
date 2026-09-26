"""The REU: detection, size and block transfers, in py65 with a modelled REU and in VICE with a real one."""
import os
import random
import subprocess
import sys

sys.path.insert(0, os.getcwd())
from harness import Reu, call, load
from test_vice import ROMS, run_vice

KB = 1024


def test_model():
    for kb, banks in [(128, 2), (256, 4), (512, 8), (1024, 16), (2048, 32), (16384, 255)]:
        m, L = load("eval")
        reu = Reu(m, L, kb * KB)
        call(m, L["reu_detect"])
        assert not m.p & 1, f"an REU of {kb} KB was not detected"
        assert m.memory[L["reu_banks"]] == banks, (kb, m.memory[L["reu_banks"]])
    print("reu: 6 sizes (128 KB to 16 MB) detected in py65")


def test_transfers():
    rng = random.Random(5)
    m, L = load("eval")
    reu = Reu(m, L, 512 * KB)
    call(m, L["reu_detect"])
    for _ in range(20):
        n = rng.choice([1, 2, 255, 256, 300, 3000, 12000])
        c64 = rng.randint(0x9000, 0xCC00 - n)
        offset = rng.randint(0, 512 * KB - 1)              # (may wrap around the end of the REU)
        data = bytes(rng.getrandbits(8) for _ in range(n))
        m.memory[c64:c64 + n] = list(data)
        for name, v in [("C64", c64), ("ADDR", offset)]:
            a = {"C64": 0xDF02, "ADDR": 0xDF04}[name]
            for k in range(2 if name == "C64" else 3):
                m.memory[a + k] = v >> 8 * k & 0xFF
        m.memory[0xDF07], m.memory[0xDF08] = n & 0xFF, n >> 8 & 0xFF
        call(m, L["reu_stash"])
        m.memory[c64:c64 + n] = [0] * n
        call(m, L["reu_fetch"])
        assert bytes(m.memory[c64:c64 + n]) == data
    print("reu: 20 stash/fetch round trips of 1 to 12000 bytes, some wrapping at the end of the REU")


def vice_banks(reu_kb):
    """Run the PRG in VICE with an REU of reu_kb KB (None: no REU); return (reu_banks, screen text)."""
    _, L = load("eval")
    args = ["-reu", "-reusize", str(reu_kb)] if reu_kb else []
    _, files = run_vice([f'save "{{DIR}}/banks.bin" 0 {L["reu_banks"]:04x} {L["reu_banks"]:04x}',
                         'save "{DIR}/scr.bin" 0 cc00 cfe7'], hex(L["app_main"]), extra=args)
    banks = files["banks.bin"][2]
    scr = files["scr.bin"][2:]
    text = "".join(chr(b) if 32 <= b < 127 else " " for b in scr)
    return banks, text


def test_vice():
    for kb, banks in [(128, 2), (512, 8), (2048, 32), (16384, 255)]:
        got, text = vice_banks(kb)
        assert got == banks, f"VICE with {kb} KB: reu_banks {got}"
        assert "NO REU" not in text
    got, text = vice_banks(None)
    assert got == 0, f"no REU: reu_banks {got}"
    assert "NO REU: LIMITED FEATURES" in text, text[:200]
    print("reu: VICE finds 128 KB, 512 KB, 2 MB and 16 MB REUs by DMA wrap-around; without one the notice is shown")


if __name__ == "__main__":
    test_model()
    test_transfers()
    if not all(os.path.exists("roms/" + r) for r in ROMS):
        print("reu: VICE checks skipped (no C64 ROMs in roms/)")
    elif subprocess.run(["which", "x64sc"], capture_output=True).returncode:
        print("reu: VICE checks skipped (x64sc not installed)")
    else:
        test_vice()
