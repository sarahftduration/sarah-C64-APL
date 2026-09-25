"""Load a 64tass binary into py65 and call routines by label."""
import re
from py65.devices.mpu6502 import MPU

RTS_SENTINEL = 0xFFF0


def load(name, origin=0xC000):
    mpu = MPU()
    with open(f"build/{name}.bin", "rb") as f:
        data = f.read()
    mpu.memory[origin:origin + len(data)] = list(data)
    labels = {}
    with open(f"build/{name}.lbl") as f:
        for line in f:
            m = re.match(r"(\S+)\s*=\s*(\$[0-9a-fA-F]+|\d+)\s*$", line)
            if m:
                v = m.group(2)
                labels[m.group(1)] = int(v[1:], 16) if v[0] == "$" else int(v)
    return mpu, labels


def call(mpu, addr, max_steps=1_000_000):
    """JSR-style call: run until the routine's RTS pops the sentinel."""
    ret = RTS_SENTINEL - 1
    mpu.memory[0x1FF] = ret >> 8
    mpu.memory[0x1FE] = ret & 0xFF
    mpu.sp = 0xFD
    mpu.pc = addr
    for _ in range(max_steps):
        mpu.step()
        if mpu.pc == RTS_SENTINEL:
            return
    raise RuntimeError("routine did not return")
