"""Integration test in VICE: the PRG loads, BASIC runs its SYS stub, and the CPU reaches `start`.

Needs the C64 ROMs (chargen.bin, basic.bin, kernal.bin) in roms/, which are copyrighted and
git-ignored. Without them, or without VICE, this test is skipped.
"""
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.getcwd())
from harness import load

ROMS = ["chargen.bin", "basic.bin", "kernal.bin"]


def run_vice(monitor_lines, initbreak, cycles=60_000_000, extra=("-reu", "-reusize", "4096")):
    """Autostart build/apl.prg (injected into RAM); at the breakpoint run the monitor script."""
    with tempfile.TemporaryDirectory() as d:
        script = os.path.join(d, "mon.txt")
        with open(script, "w") as f:
            f.write("\n".join(l.replace("{DIR}", d) for l in monitor_lines) + "\nquit\n")
        cmd = ["x64sc", "-default", "+saveres", "-console", "-silent", "+sound", "-warp",
               "-kernal", "roms/kernal.bin", "-basic", "roms/basic.bin", "-chargen", "roms/chargen.bin",
               "-autostartprgmode", "1", "-initbreak", initbreak, "-limitcycles", str(cycles),
               "-autostart", "build/apl.prg", "-moncommands", script, *extra]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        files = {n: open(os.path.join(d, n), "rb").read() for n in os.listdir(d) if n != "mon.txt"}
        return r.stdout + r.stderr, files


def test_loads_and_starts():
    _, L = load("eval")
    image = open("build/eval.bin", "rb").read()
    end = L["ORG"] + len(image) - 1
    _, files = run_vice(['bank ram', 'registers', f'save "{{DIR}}/mem.bin" 0 {L["ORG"]:04x} {end:04x}'], hex(L["start"]))
    mem = files["mem.bin"]
    assert mem[:2] == bytes([L["ORG"] & 0xFF, L["ORG"] >> 8]), "VICE saved with an unexpected header"
    assert mem[2:] == image, "the RAM VICE ran differs from the assembled image"
    print(f"vice: PRG autostarted through the BASIC stub; the CPU stopped at start (${L['start']:04X}) "
          f"with all {len(image)} bytes of the image in RAM")


if __name__ == "__main__":
    if not all(os.path.exists("roms/" + r) for r in ROMS):
        print("vice: skipped (no C64 ROMs in roms/)")
    elif subprocess.run(["which", "x64sc"], capture_output=True).returncode:
        print("vice: skipped (x64sc not installed)")
    else:
        test_loads_and_starts()
