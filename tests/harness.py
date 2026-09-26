"""Load a 64tass binary into py65 and call routines by label."""
import atexit
import os
import re
import shutil
from py65.devices.mpu6502 import MPU

RTS_SENTINEL = 0xFFF0

# The zero page we may write (DESIGN.md, memory map): $02-$8F and $FB-$FE. $00/$01 are
# the CPU port and $90-$FA belong to the KERNAL.
ZP_ALLOWED = set(range(0x02, 0x90)) | set(range(0xFB, 0xFF))


_SCRATCH = None


def scratch(name=""):
    """A path in a directory private to this process (build/scratch/<pid>, removed at exit).

    The tests that build and run images (keytest, selftest) put them here rather than in build/, so
    test files can run at the same time without overwriting each other's files."""
    global _SCRATCH
    if _SCRATCH is None:
        _SCRATCH = os.path.join("build", "scratch", str(os.getpid()))
        os.makedirs(_SCRATCH, exist_ok=True)
        atexit.register(shutil.rmtree, _SCRATCH, ignore_errors=True)
    return os.path.join(_SCRATCH, name)


def load(name, reu_kb=512):
    """Load build/<name>.bin at its ORG label and return (mpu, labels).

    An image with overlays (label OVL_IMG) gets what start-up gives it on the real machine: the overlay
    images are copied to a modelled REU of reu_kb KB (0: none) and the RAM they were loaded into is
    cleared, since the tables take it over. mpu.reu is the REU."""
    mpu = MPU()
    with open(f"build/{name}.bin", "rb") as f:
        data = f.read()
    labels = {}
    with open(f"build/{name}.lbl") as f:
        for line in f:
            m = re.match(r"(\S+)\s*=\s*(\$[0-9a-fA-F]+|\d+)\s*$", line)
            if m:
                v = m.group(2)
                labels[m.group(1)] = int(v[1:], 16) if v[0] == "$" else int(v)
    origin = labels.get("ORG", 0xC000)
    mpu.memory[origin:origin + len(data)] = list(data)
    mpu.reu = None
    if "OVL_IMG" in labels and "reu_trig" in labels:
        img, tot = labels["OVL_IMG"], labels["OVL_TOT"]
        if reu_kb:
            mpu.reu = Reu(mpu, labels, reu_kb * 1024)
            mpu.reu.mem[0:tot] = bytes(mpu.memory[img:img + tot])
            mpu.memory[labels["reu_banks"]] = min(255, reu_kb // 64)
        mpu.memory[img:img + tot] = [0] * tot
    return mpu, labels


def call(mpu, addr, max_steps=1_000_000):
    """JSR-style call: run until the routine's RTS pops the sentinel."""
    zp_before = list(mpu.memory[0:0x100])
    ret = RTS_SENTINEL - 1
    mpu.memory[0x1FF] = ret >> 8
    mpu.memory[0x1FE] = ret & 0xFF
    mpu.sp = 0xFD
    mpu.pc = addr
    hooks = getattr(mpu, "hooks", None)     # {address: function(mpu)}, run just before that instruction
    for _ in range(max_steps):
        if hooks and mpu.pc in hooks:
            hooks[mpu.pc](mpu)
        mpu.step()
        if mpu.pc == RTS_SENTINEL:
            bad = [a for a in range(0x100) if mpu.memory[a] != zp_before[a] and a not in ZP_ALLOWED]
            assert not bad, f"zero page written outside the allowed set: {[hex(a) for a in bad]}"
            return
    raise RuntimeError("routine did not return")


class Reu:
    """A RAM Expansion Unit for py65 tests: the transfer happens when the program reaches the
    instruction that stores the command (label reu_trig), using the registers in memory.

    size is in bytes (a power of two, at least 128 KB); the REU address wraps at that size, as a real
    one does. Only stash and fetch are modelled (the program uses no others)."""

    def __init__(self, mpu, labels, size):
        self.mpu, self.size = mpu, size
        self.mem = bytearray(size)
        self.transfers = []
        if not hasattr(mpu, "hooks"):
            mpu.hooks = {}
        mpu.hooks[labels["reu_trig"]] = self.trigger
        self.labels = labels
        self.loads = []                 # the overlay ids fetched, in order
        if "ov_fetch" in labels:
            mpu.hooks[labels["ov_fetch"]] = self.check_switch

    def trigger(self, mpu):
        m = mpu.memory
        cmd = mpu.a
        c64 = m[0xDF02] | m[0xDF03] << 8
        reu = m[0xDF04] | m[0xDF05] << 8 | m[0xDF06] << 16
        n = (m[0xDF07] | m[0xDF08] << 8) or 0x10000
        assert cmd & 0x90 == 0x90 and cmd & 3 in (0, 1), f"unmodelled REU command {cmd:02x}"
        assert m[0xDF0A] == 0, "address control must count both addresses up"
        self.transfers.append((cmd & 3, c64, reu, n))
        for i in range(n):
            r = (reu + i) % self.size
            if cmd & 3 == 0:
                self.mem[r] = m[(c64 + i) & 0xFFFF]
            else:
                m[(c64 + i) & 0xFFFF] = self.mem[r]

    def check_switch(self, mpu):
        """An overlay is about to be fetched into the window: no return address on the stack may point into it
        (the routine that called us would come back to other code)."""
        L = self.labels
        lo, hi = L["OVWIN"], L["OVWIN"] + L["OVWIN_SIZE"]
        m = mpu.memory
        for a in range(0x100 + mpu.sp + 1, 0x1FF):
            ret = (m[a] | m[a + 1] << 8) + 1
            assert not lo <= ret < hi, f"an overlay is loaded while code in the window is still active (stack ${a:03x}: ${ret:04x})"
        self.loads.append(mpu.x)
