""")SAVE and )LOAD on the real machine (VICE, with a host directory as disk drive 8).

Sessions are typed through the scripted editor; the screen is compared with a Python model and the
files the machine writes with the encoder in tools/wsfile.py. Loads read files prepared by that
encoder, including corrupt and truncated ones. Skipped without the ROMs in roms/ or without VICE.
"""
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.getcwd())
sys.path.insert(0, "tools")
import apl64
import wsfile
from test_keys import EditorModel, build_keytest, petscii, show
from test_vice import ROMS


class DiskModel(EditorModel):
    def __init__(self, heap, disk):
        super().__init__(heap)
        self.disk = dict(disk)          # lower-case file name -> bytes
        self.written = set()

    def name_arg(self, arg):
        """The workspace name a command uses, as get_name: an argument sets it, else the current one."""
        if arg:
            name = arg.split(" ")[0].upper()
            if 1 <= len(name) <= 16 and all(c.isalnum() and c.isascii() or c in "-." for c in name):
                self.wsname = name
            else:
                return None
        return self.wsname or None

    def syscmd(self, t):
        i = 0
        while i < len(t) and t[i] != " ":
            i += 1
        word, arg = t[:i].upper(), t[i:].lstrip(" ")
        if word == "SAVE":
            name = self.name_arg(arg)
            if name is None:
                self.say("BAD NAME")
                return
            self.disk[name.lower()] = wsfile.encode(self.model)
            self.written.add(name.lower())
            self.say("SAVED")
        elif word == "LOAD":
            name = self.name_arg(arg)
            if name is None:
                self.say("BAD NAME")
                return
            data = self.disk.get(name.lower())
            if data is None:
                self.say("FILE NOT FOUND")
                return
            status, m = wsfile.load(data)
            if m is not None:
                self.model = m
            self.say({"ok": "LOADED", "notws": "NOT A WORKSPACE", "wsfull": "WS FULL", "io": "FILE ERROR"}[status])
        else:
            super().syscmd(t)


def run_vice_disk(prg, initbreak, hostdir, script):
    with tempfile.TemporaryDirectory() as d:
        mon = os.path.join(d, "mon.txt")
        with open(mon, "w") as f:
            f.write("\n".join(l.replace("{DIR}", d) for l in script) + "\nquit\n")
        cmd = ["x64sc", "-console", "-silent", "+sound", "-warp", "-kernal", "roms/kernal.bin", "-basic",
               "roms/basic.bin", "-chargen", "roms/chargen.bin", "-autostartprgmode", "1", "-initbreak", initbreak,
               "-limitcycles", "800000000", "+drive8truedrive", "-iecdevice8", "-fs8", hostdir,
               "-autostart", prg, "-moncommands", mon]
        subprocess.run(cmd, capture_output=True, timeout=400)
        return {n: open(os.path.join(d, n), "rb").read() for n in os.listdir(d) if n != "mon.txt"}


def session(text, disk=None):
    """Type `text` on a machine whose drive 8 holds `disk`; check the screen and every file written."""
    disk = disk or {}
    keys = petscii(text)
    L = build_keytest(keys)
    with tempfile.TemporaryDirectory() as host:
        for name, data in disk.items():
            with open(os.path.join(host, name), "wb") as f:
                f.write(data)
        files = run_vice_disk("build/keytest.prg", hex(L["selftest_done"]), host,
                              ['save "{DIR}/screen.bin" 0 cc00 cfe7'])
        after = {n: open(os.path.join(host, n), "rb").read() for n in os.listdir(host)}
    ed = DiskModel((L["HEAP_BASE"], L["HEAP_LIMIT"]), disk)
    for k in keys:
        ed.key(k)
    got, want = files["screen.bin"][2:], ed.screen()
    if got != want:
        show(got, want)
        raise AssertionError(f"screen differs from the model for {text[:200]!r}")
    for n in ed.written:
        assert after.get(n) == ed.disk[n], f"file {n!r}: the machine wrote {after.get(n)!r}, expected {ed.disk[n]!r}"
    return ed, after


def ws(lines):
    """A workspace made by running `lines` in the model: (interp, encoded file)."""
    m = apl64.Interp()
    for line in lines:
        m.run_values(line)
    return m, wsfile.encode(m)


VALUES = ["a←1", "b←0 1 1 0", "c←¯5 300 32767 ¯32768", "d←1.5", "e←¯2.25 1e10 0.1", "f←'x'", "g←'hello world'",
          "h←2 3⍴⍳6", "i←2 2⍴1.5 ¯2 100 0.25", "j←⍬", "k←''", "l←0 3⍴1", "m←2 3⍴'abcdef'", "n←3 0⍴1", "o←1e38", "p←40000"]


def test_save():
    typed = "".join(v.replace("←", "{LA}") + "{RET}" for v in VALUES)
    typed = typed.replace("⍳", "{P}i").replace("⍬", "{P}'").replace("⍴", "{P}r")
    ed, after = session(typed + ")save t1{RET})wsid{RET}")
    assert after["t1"][:7] == b"APLW\x01" + (len(VALUES)).to_bytes(2, "little")
    session("a{LA}1{RET})save{RET})wsid foo{RET})save{RET}a{LA}2{RET})save{RET})save FOO{RET})wsid{RET}")   # no name; replacing
    session("a{LA}1{RET})save a-b.c{RET}")
    session(")save e{RET}")                                     # an empty workspace
    session("a{LA}{P}i5{RET}b{LA}a{RET}c{LA}b,b{RET})save shared{RET})free{RET})clear{RET})load shared{RET})free{RET}")
    session("{P}h{LA}1{RET}{P}H{LA}2{RET})save deltas{RET})clear{RET})load deltas{RET})vars{RET}")   # ∆ and ⍙ in names
    session("a{LA}1{RET})save x{RET})wsid bad{P}{LA}name{RET})wsid{RET})save{RET})wsid{RET}")   # a bad name must not disturb the good one
    print("disk: )SAVE writes the files the encoder predicts; names, replace, empty workspace, shared arrays")


def test_readonly():
    """A drive that refuses the write: the KERNAL reports nothing, only the drive's error channel does."""
    keys = petscii("a{LA}1{RET})save t{RET})wsid{RET})load t{RET}")
    L = build_keytest(keys)
    with tempfile.TemporaryDirectory() as host:
        os.chmod(host, 0o555)
        files = run_vice_disk("build/keytest.prg", hex(L["selftest_done"]), host,
                              ['save "{DIR}/screen.bin" 0 cc00 cfe7'])
        os.chmod(host, 0o755)
        assert os.listdir(host) == []
    scr = files["screen.bin"][2:]
    assert b"FILE ERROR" in scr and b"SAVED" not in scr, bytes(scr[:200])
    print("disk: a save the drive refuses reports FILE ERROR, not SAVED")


def test_load():
    m, good = ws(VALUES)
    disk = {"t1": good}
    session(")load t1{RET})vars{RET}" + "".join(c + "{RET}" for c in "abcdefghijmnop"), disk)   # (not l: the model cannot print a matrix with no rows)
    session("z{LA}9{RET}y{LA}'old'{RET})load t1{RET})vars{RET}z{RET})wsid{RET})free{RET}", disk)
    session(")load T1{RET})wsid{RET})save{RET})load nothere{RET})wsid{RET}", disk)
    session(")wsid t1{RET})load{RET})vars{RET})load{RET}", disk)
    session(")load{RET})load  {RET}", disk)
    session(")load a_b{RET})load nothere{RET})load {P}i{RET}", disk)
    # round trip on the machine itself
    session("a{LA}1 2 3{RET}b{LA}'txt'{RET}c{LA}2 2⍴1.5 2 3 4{RET})save rt{RET})clear{RET})vars{RET})load rt{RET})vars{RET}a{RET}b{RET}c{RET}".replace("⍴", "{P}r"))
    print("disk: )LOAD reads what the encoder writes (all types, shapes, empty arrays); missing files; names; round trip")


def test_corrupt():
    m, good = ws(["a←1 2 3", "bb←'hi'", "c←2 2⍴1.5 2 3 4", "d←5"])
    head = good[:5]
    cases = {
        "badmagic": b"NOPE" + good[4:],
        "version2": good[:4] + bytes([2]) + good[5:],
        "empty": b"",
        "onlymagic": good[:5],
        "nocount": good[:6],
        "badtrailer": good[:-1] + b"X",
        "extrabytes": good + b"junk",
        "zeroname": head + (1).to_bytes(2, "little") + bytes([0]) + b"E",
        "numname": head + (1).to_bytes(2, "little") + bytes([2]) + b"1a" + bytes([0, 5]) + b"E",
        "twotokens": head + (1).to_bytes(2, "little") + bytes([3]) + b"a b" + bytes([0, 5]) + b"E",
        "quotename": head + (1).to_bytes(2, "little") + bytes([2]) + b"a'" + bytes([0, 5]) + b"E",
        "badtagbits": head + (1).to_bytes(2, "little") + bytes([1]) + b"a" + bytes([0x12, 5]) + b"E",
        "rank3": head + (1).to_bytes(2, "little") + bytes([1]) + b"a" + bytes([0x0E, 5]) + b"E",
        "countmismatch": head + (1).to_bytes(2, "little") + bytes([1]) + b"a" + bytes([6]) + (3).to_bytes(2, "little") + (4).to_bytes(2, "little") + bytes(6) + b"E",
        "matrixmismatch": head + (1).to_bytes(2, "little") + bytes([1]) + b"a" + bytes([10]) + (6).to_bytes(2, "little") + (2).to_bytes(2, "little") + (2).to_bytes(2, "little") + bytes(12) + b"E",
        "counthigh": head + (1).to_bytes(2, "little") + bytes([1]) + b"a" + bytes([6]) + (3).to_bytes(2, "little") + (259).to_bytes(2, "little") + bytes(6) + b"E",
        "prodoverflow": head + (1).to_bytes(2, "little") + bytes([1]) + b"a" + bytes([10]) + (0).to_bytes(2, "little") + (256).to_bytes(2, "little") + (256).to_bytes(2, "little") + b"E",
        "matrixok": head + (1).to_bytes(2, "little") + bytes([1]) + b"a" + bytes([10]) + (6).to_bytes(2, "little") + (2).to_bytes(2, "little") + (3).to_bytes(2, "little") + bytes(12) + b"E",
        "toomany": head + (5).to_bytes(2, "little") + good[7:-1] + b"E",
        "dupnames": head + (2).to_bytes(2, "little") + bytes([1]) + b"a" + bytes([0, 5]) + bytes([1]) + b"a" + bytes([0, 7]) + b"E",
        "wsfull": head + (1).to_bytes(2, "little") + bytes([1]) + b"a" + bytes([7]) + (6000).to_bytes(2, "little") + (6000).to_bytes(2, "little") + bytes(18000) + b"E",
        "bigok": head + (1).to_bytes(2, "little") + bytes([1]) + b"a" + bytes([6]) + (6000).to_bytes(2, "little") + (6000).to_bytes(2, "little") + bytes(12000) + b"E",
    }
    for cut in range(6, len(good), 7):
        cases[f"cut{cut}"] = good[:cut]
    for name, data in cases.items():
        fn = name.replace("_", "x")[:8]
        session("z{LA}7{RET})load " + fn + "{RET})vars{RET}z{RET})free{RET})wsid{RET}", {fn: data})
    print(f"disk: {len(cases)} corrupt, truncated and oversized files are refused or partly loaded exactly as the model says")


if __name__ == "__main__":
    if not all(os.path.exists("roms/" + r) for r in ROMS):
        print("disk: skipped (no C64 ROMs in roms/)")
    elif subprocess.run(["which", "x64sc"], capture_output=True).returncode:
        print("disk: skipped (x64sc not installed)")
    else:
        test_save()
        test_readonly()
        test_load()
        test_corrupt()
