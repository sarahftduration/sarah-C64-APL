"""Overlays: the dispatcher, the window and the rules, in py65 with a modelled REU (harness.Reu)."""
import os
import sys

sys.path.insert(0, os.getcwd())
from harness import call, load

E_NOREU = 11


def screen_text(m, L, rows=25):
    base = L["SCREEN"]
    return ["".join(chr(b) if 32 <= b < 127 else " " for b in m.memory[base + 40 * r:base + 40 * r + 40]).rstrip()
            for r in range(rows)]


def start(reu_kb=512):
    m, L = load("eval", reu_kb=reu_kb)
    call(m, L["tok_init"])
    call(m, L["eval_init"])
    call(m, L["scr_clear"])
    call(m, L["disk_init"])
    return m, L


def command(m, L, text):
    """Run a system command line the way the REPL does; returns (carry, A)."""
    data = list(text.encode("ascii")) + [0]
    m.memory[L["INBUF"]:L["INBUF"] + len(data)] = data
    m.x = 0
    call(m, L["syscmd"], max_steps=5_000_000)
    return m.p & 1


def test_load_and_swap():
    m, L = start()
    assert m.memory[L["ov_cur"]] == 0
    command(m, L, ")FREE")
    assert m.reu.loads == [1], m.reu.loads
    assert m.memory[L["ov_cur"]] == 1
    assert "BYTES FREE" in " ".join(screen_text(m, L))
    command(m, L, ")VARS")
    command(m, L, ")WSID")
    assert m.reu.loads == [1], "an overlay that is already in the window is not fetched again"
    m.a = 2                                     # the disk overlay (its commands need the KERNAL, which py65 lacks)
    call(m, L["ov_ensure"])
    assert not m.p & 1
    assert m.reu.loads == [1, 2] and m.memory[L["ov_cur"]] == 2
    disk = open("build/eval.bin", "rb").read()[L["OVP_DISK"] - L["ORG"]:][:L["OVN_DISK"]]
    assert bytes(m.memory[L["OVWIN"]:L["OVWIN"] + L["OVN_DISK"]]) == disk, "the window holds the disk overlay's image"
    command(m, L, ")FREE")
    assert m.reu.loads == [1, 2, 1]
    # the window holds the image bytes of the last overlay fetched
    win = bytes(m.memory[L["OVWIN"]:L["OVWIN"] + L["OVN_SYS"]])
    assert win == bytes(m.reu.mem[L["OVP_SYS"] - L["OVL_IMG"]:L["OVP_SYS"] - L["OVL_IMG"] + L["OVN_SYS"]])
    print("overlay: system and disk overlays are fetched into the window on demand, and only when the other one was there")


def test_no_reu():
    m, L = start(reu_kb=0)
    assert m.memory[L["reu_banks"]] == 0
    for cmd in (")FREE", ")VARS", ")SAVE X", ")LOAD X", ")LIB"):
        m.memory[L["SCREEN"]:L["SCREEN"] + 1000] = [32] * 1000
        call(m, L["scr_clear"])
        command(m, L, cmd)
        assert "NO REU" in " ".join(screen_text(m, L)), (cmd, screen_text(m, L)[:3])
        assert m.memory[L["ov_cur"]] == 0
    m.memory[L["SCREEN"]:L["SCREEN"] + 1000] = [32] * 1000
    call(m, L["scr_clear"])
    command(m, L, ")BOGUS")
    assert "BAD COMMAND" in " ".join(screen_text(m, L))
    print("overlay: without an REU every overlaid command says NO REU and the others still work")


def test_stub():
    """An inline-argument stub: jsr ov_call, id, entry. The routine's rts returns to the stub's caller, registers arrive intact."""
    m, L = start()
    stub = 0x9F00
    m.memory[stub:stub + 6] = [0x20, L["ov_call"] & 0xFF, L["ov_call"] >> 8, 1, L["cmd_free"] & 0xFF, L["cmd_free"] >> 8]
    call(m, stub)
    assert m.reu.loads == [1] and "BYTES FREE" in " ".join(screen_text(m, L))
    # registers: fetch a different overlay first, then call a stub for a routine that just returns (the disk overlay's first byte
    # is not code we can rely on, so use a resident rts as the target with overlay 2: ov_call must still load overlay 2)
    rts = L["ov_err"]
    m.memory[stub:stub + 6] = [0x20, L["ov_call"] & 0xFF, L["ov_call"] >> 8, 2, rts & 0xFF, rts >> 8]
    m.a, m.x, m.y = 0x12, 0x34, 0x56
    call(m, stub)
    assert m.reu.loads == [1, 2]
    assert (m.a, m.x, m.y) == (0x12, 0x34, 0x56), "A, X and Y must arrive at the routine as the caller had them"
    print("overlay: a stub loads its overlay, keeps the registers and returns to the caller")


def test_active_overlay_check():
    """The harness must notice an overlay being replaced while code in the window is on the stack."""
    m, L = start()
    ret = L["OVWIN"] + 10                                   # as if a routine in the window had done a jsr
    m.memory[0x1FD], m.memory[0x1FE] = (ret - 1) & 0xFF, (ret - 1) >> 8
    m.memory[0x1FF], m.memory[0x1FC] = 0xEF, 0xFF
    m.sp = 0xFC
    m.a = 1
    m.pc = L["ov_ensure"]
    try:
        for _ in range(200):
            if m.pc in m.hooks:
                m.hooks[m.pc](m)
            m.step()
    except AssertionError as e:
        assert "still active" in str(e)
        print("overlay: the test harness catches an overlay switch while the window's code is running")
        return
    raise AssertionError("the switch was not noticed")


def overlays(L):
    """[(name, physical address, length)] in image order."""
    out = [(n[4:], L["OVP_" + n[4:]], L[n]) for n in L if n.startswith("OVN_")]
    return sorted(out, key=lambda o: o[1])


def test_images():
    """The REU holds exactly the images the PRG carries, back to back from offset 0."""
    m, L = load("eval")
    ovs = overlays(L)
    pos = L["OVL_IMG"]
    for name, addr, n in ovs:
        assert addr == pos, name
        pos += n
    assert L["OVL_TOT"] == pos - L["OVL_IMG"]
    img = open("build/eval.bin", "rb").read()[L["OVL_IMG"] - L["ORG"]:]
    assert bytes(m.reu.mem[:L["OVL_TOT"]]) == img
    print(f"overlay: {L['OVL_TOT']} bytes of images ({', '.join(f'{n.lower()} {k}' for n, _, k in ovs)}) in the PRG and the REU, "
          f"window {L['OVWIN_SIZE']}")


if __name__ == "__main__":
    test_images()
    test_load_and_swap()
    test_no_reu()
    test_stub()
    test_active_overlay_check()
