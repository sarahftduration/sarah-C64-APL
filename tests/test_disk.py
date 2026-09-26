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
from harness import scratch
from test_keys import EditorModel, build_keytest, petscii, show
from test_vice import ROMS


LIB_PAGE = 22


def dir_lines(disk):
    """The directory VICE builds for a host folder acting as drive 8, as )LIB prints it.

    Each line is the drive's line number (the block count) and text; )LIB prints the number, a space
    and the text, as BASIC's LIST does. VICE lists the header (line number 1, no disk name), the
    entries "." and "..", every file sorted by its upper-cased name with a block count of one per
    254 bytes rounded up and the type PRG (whatever the name), and 65535 BLOCKS FREE."""
    def entry(blocks, name, kind):
        return blocks, " " * (4 - len(str(blocks))) + '"' + name + '"' + " " * (17 - len(name)) + kind
    lines = [(1, '"' + " " * 16 + '"  #8:0'), entry(1, ".", "DIR"), entry(1, "..", "DIR")]
    for name in sorted(n.upper() for n in disk):
        size = len(disk[name.lower()])
        lines.append(entry(-(-size // 254), name, "PRG"))
    lines.append((65535, "BLOCKS FREE."))
    return [f"{n} {text}".rstrip().encode() for n, text in lines]


def dos_lines(disk, label="TEST", ident="01"):
    """The directory a real 1541 reports for a freshly formatted disk holding `disk` (all SEQ files, in
    the order they were written): the header with the disk name and ID, one line per file with its
    block count, and the free blocks (664 on an empty disk). The text is laid out as VICE's folder
    listing above, so only the header, the types and the counts differ."""
    def entry(blocks, name, kind):
        return blocks, " " * (4 - len(str(blocks))) + '"' + name + '"' + " " * (17 - len(name)) + kind
    lines, used = [(0, '"' + label.ljust(16) + '" ' + ident + " 2A")], 0
    for name, data in disk.items():
        blocks = -(-len(data) // 254)
        used += blocks
        lines.append(entry(blocks, name.upper(), "SEQ"))
    lines.append((664 - used, "BLOCKS FREE."))
    return [f"{n} {text}".rstrip().encode() for n, text in lines]


class DiskModel(EditorModel):
    paused = False                      # )LIB is waiting at MORE for a key (the base class prompts in __init__)

    def __init__(self, heap, disk, dos=False):
        super().__init__(heap)
        self.dos = dos                  # a real drive's directory rather than VICE's folder listing
        self.disk = dict(disk)          # lower-case file name -> bytes
        self.written = set()
        self.lib_rest, self.lib_n = [], 0

    def prompt(self):
        if not self.paused:             # a paused listing ends with the prompt, not before
            super().prompt()

    def screen(self):
        return bytes(self.scr.mem) if self.paused else super().screen()     # no cursor block while at MORE

    def lib_go(self):
        while self.lib_rest:
            if self.lib_n == LIB_PAGE:
                self.scr.write(b"MORE")
                self.paused = True
                return
            self.scr.write(self.lib_rest.pop(0) + b"\n")
            self.lib_n += 1
        self.paused = False

    def key(self, k):
        if not self.paused:
            return super().key(k)
        for _ in range(4):              # the MORE is erased, then any key goes on and RUN/STOP stops
            self.scr.back()
        self.lib_n = 0
        if k == 3:
            self.lib_rest = []
        self.paused = False
        self.lib_go()
        if not self.paused:
            self.prompt()

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
        elif word == "LIB":
            self.lib_rest, self.lib_n = (dos_lines if self.dos else dir_lines)(self.disk), 0
            self.lib_go()
        else:
            super().syscmd(t)


def run_vice_disk(prg, initbreak, hostdir, script):
    with tempfile.TemporaryDirectory() as d:
        mon = os.path.join(d, "mon.txt")
        with open(mon, "w") as f:
            f.write("\n".join(l.replace("{DIR}", d) for l in script) + "\nquit\n")
        cmd = ["x64sc", "-default", "+saveres", "-console", "-silent", "+sound", "-warp", "-kernal", "roms/kernal.bin", "-basic",
               "roms/basic.bin", "-chargen", "roms/chargen.bin", "-autostartprgmode", "1", "-initbreak", initbreak,
               "-limitcycles", "800000000", "+drive8truedrive", "-iecdevice8", "-fs8", hostdir,
               "-autostart", prg, "-moncommands", mon]
        subprocess.run(cmd, capture_output=True, timeout=400)
        return {n: open(os.path.join(d, n), "rb").read() for n in os.listdir(d) if n != "mon.txt"}


def mask_dirs(screen):
    """Blank the block counts of the "." and ".." rows: VICE takes them from the host folders' sizes, which
    depend on the filesystem. The number and its padding always fill five columns, so nothing shifts."""
    rows = [bytearray(screen[r * 40:r * 40 + 40]) for r in range(25)]
    for row in rows:
        if bytes(row[5:8]) == b'"."' or bytes(row[5:9]) == b'".."':
            row[0:5] = b" " * 5
    return b"".join(rows)


def session(text, disk=None):
    """Type `text` on a machine whose drive 8 holds `disk`; check the screen and every file written."""
    disk = disk or {}
    keys = petscii(text)
    L = build_keytest(keys)
    with tempfile.TemporaryDirectory() as host:
        for name, data in disk.items():
            with open(os.path.join(host, name), "wb") as f:
                f.write(data)
        files = run_vice_disk(scratch("keytest.prg"), hex(L["selftest_done"]), host,
                              ['save "{DIR}/screen.bin" 0 cc00 cfe7'])
        after = {n: open(os.path.join(host, n), "rb").read() for n in os.listdir(host)}
    ed = DiskModel((L["HEAP_BASE"], L["HEAP_LIMIT"]), disk)
    for k in keys:
        ed.key(k)
    got, want = files["screen.bin"][2:], ed.screen()
    if mask_dirs(got) != mask_dirs(want):
        show(got, want)
        raise AssertionError(f"screen differs from the model for {text[:200]!r}")
    for n in ed.written:
        assert after.get(n) == ed.disk[n], f"file {n!r}: the machine wrote {after.get(n)!r}, expected {ed.disk[n]!r}"
    return ed, after


def dos1541_rom():
    """The 1541 ROM VICE needs for a real drive: roms/dos1541.bin, or one in VICE's own data folders."""
    name = "dos1541-325302-01+901229-05.bin"
    for path in ("roms/dos1541.bin", os.path.expanduser("~/.local/share/vice/DRIVES/" + name),
                 "/usr/share/vice/DRIVES/" + name):
        if os.path.exists(path):
            return os.path.abspath(path)


def image_session(text, files=None):
    """Type `text` on a machine whose drive 8 is a real (emulated) 1541 holding a formatted disk image
    with `files` (SEQ files, lower-case name -> bytes). Checks the screen against the model, and the
    files the machine saved by reading them back out of the image."""
    files = files or {}
    keys = petscii(text)
    L = build_keytest(keys)
    with tempfile.TemporaryDirectory() as d:
        img = os.path.join(d, "t.d64")
        cmd = ["c1541", "-format", "test,01", "d64", img]
        for n, data in files.items():
            with open(os.path.join(d, "src_" + n), "wb") as f:
                f.write(data)
            cmd += ["-write", os.path.join(d, "src_" + n), n + ",s"]
        subprocess.run(cmd, capture_output=True, check=True)
        mon = os.path.join(d, "mon.txt")
        with open(mon, "w") as f:
            f.write(f'save "{d}/screen.bin" 0 cc00 cfe7\nquit\n')
        subprocess.run(["x64sc", "-default", "+saveres", "-console", "-silent", "+sound", "-warp",
                        "-kernal", "roms/kernal.bin", "-basic", "roms/basic.bin", "-chargen", "roms/chargen.bin",
                        "-dos1541", dos1541_rom(), "-autostartprgmode", "1", "-initbreak", hex(L["selftest_done"]),
                        "-limitcycles", "1500000000", "-drive8type", "1541", "-8", img,
                        "-autostart", scratch("keytest.prg"), "-moncommands", mon], capture_output=True, timeout=600)
        ed = DiskModel((L["HEAP_BASE"], L["HEAP_LIMIT"]), files, dos=True)
        for k in keys:
            ed.key(k)
        got = open(os.path.join(d, "screen.bin"), "rb").read()[2:]
        if got != ed.screen():
            show(got, ed.screen())
            raise AssertionError(f"screen differs from the model for {text[:200]!r} on a real drive")
        for n in ed.written:
            out = os.path.join(d, "out_" + n)
            subprocess.run(["c1541", img, "-read", n + ",s", out], capture_output=True)
            assert os.path.exists(out) and open(out, "rb").read() == ed.disk[n], f"file {n!r} on the disk image"


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
    assert after["t1"][:7] == b"APLW\x02" + (len(VALUES)).to_bytes(2, "little")
    session("a{LA}1{RET})save{RET})wsid foo{RET})save{RET}a{LA}2{RET})save{RET})save FOO{RET})wsid{RET}")   # no name; replacing
    session("a{LA}1{RET})save a-b.c{RET}")
    session(")save e{RET}")                                     # an empty workspace
    session("a{LA}{P}i5{RET}b{LA}a{RET}c{LA}b,b{RET})save shared{RET})free{RET})clear{RET})load shared{RET})free{RET}")
    session("{P}h{LA}1{RET}{P}H{LA}2{RET})save deltas{RET})clear{RET})load deltas{RET})vars{RET}")   # ∆ and ⍙ in names
    session("a{LA}1{RET})save x{RET})wsid bad{P}{LA}name{RET})wsid{RET})save{RET})wsid{RET}")   # a bad name must not disturb the good one
    print("disk: )SAVE writes the files the encoder predicts; names, replace, empty workspace, shared arrays")


def test_functions():
    """Functions survive )SAVE and )LOAD (the symbol numbers in their token streams too), and a damaged
    function makes the file NOT A WORKSPACE, the workspace left as far as it was loaded."""
    from test_keys import typed_lines
    defs = typed_lines("z←9", "∇R←SQ X", "R←X×X", "∇", "y←SQ z", "∇R←A ADD B;T", "T←A+B", "R←T×w", "∇", "w←2",
                       "∇SHOW X", "X", "'done'", "∇", "∇R←K", "R←SQ 3", "∇")
    session(defs + ")save fw{RET})fns{RET})clear{RET})fns{RET})load fw{RET})fns{RET})vars{RET}" +
            typed_lines("SQ 5", "1 ADD 2", "SHOW 1 2", "K", "y", "w←10", "3 ADD 4", "K+1"))
    session(defs + ")save fw{RET})erase SQ{RET})load fw{RET}" + typed_lines("K", "SQ 2"))          # a function loaded over a function
    m, good = ws(["∇R←SQ X", "R←X×X", "∇", "∇F", "1", "SQ 2", "∇", "q←3"])                       # symbols with no value, too
    session(")load ff{RET})fns{RET})vars{RET}" + typed_lines("SQ 4", "F", "q"), {"ff": good})
    i = good.index(b"\x15")                                   # the first function's block
    for name, data in {
        "fnbadsym": good[:i + 9] + bytes([200]) + good[i + 10:],
        "fnbadtok": good[:i + 20] + bytes([0x20]) + good[i + 21:],
        "fnbadcnt": good[:i + 8] + bytes([9]) + good[i + 9:],
        "fnbadsum": good[:i + 5 + 4 + 5 + 9] + bytes([good[i + 5 + 4 + 5 + 9] ^ 1]) + good[i + 5 + 4 + 5 + 10:],
        "fncut": good[:i + 12],
        "fncut2": good[:good.index(b"E", i) - 1],
    }.items():
        session(")load " + name + "{RET})fns{RET})vars{RET})wsid{RET}", {name: data})
    print("disk: functions round-trip through )SAVE and )LOAD; damaged functions fail their checksum as the model says")


def test_readonly():
    """A drive that refuses the write: the KERNAL reports nothing, only the drive's error channel does."""
    keys = petscii("a{LA}1{RET})save t{RET})wsid{RET})load t{RET}")
    L = build_keytest(keys)
    with tempfile.TemporaryDirectory() as host:
        os.chmod(host, 0o555)
        files = run_vice_disk(scratch("keytest.prg"), hex(L["selftest_done"]), host,
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


def test_lib():
    files = {"alpha": bytes(12), "b": bytes(254), "c": bytes(255), "big": bytes(5000), "zz.9": bytes(1)}
    session(")lib{RET}")                                              # nothing on the drive
    session(")lib{RET}", files)                                       # block counts round up per 254 bytes
    session(")LIB{RET})Lib extra words{RET}", files)                  # case and arguments
    session("a{LA}1{RET})save t1{RET})lib{RET})save t2{RET}a{LA}{P}i9{RET})save t2{RET})lib{RET}", files)   # our own files appear
    session(")lib{RET}1+1{RET}a{LA}5{RET}a{RET}", files)              # the machine goes on working afterwards
    session(")lib{RET})lib{RET})lib{RET}")                            # repeated: the channel is closed each time
    print("disk: )LIB lists the drive as VICE reports it (header, entries, block counts, free blocks)")


def test_lib_paging():
    def many(n):
        return {f"f{i:02d}": bytes(i + 1) for i in range(n)}
    for n in (0, 17, 18, 19, 20, 30, 41, 63, 64, 70):           # 22 lines per page; the header, . .. and BLOCKS FREE add four
        session(")lib{RET}" + "x" * 4, many(n))                 # any key goes on
    session(")lib{RET}", many(30))                              # the script ends at MORE
    session(")lib{RET}x", many(30))                             # ... or just after it
    session(")lib{RET}{$03}1+1{RET}", many(30))                # RUN/STOP ends the listing at the first MORE
    session(")lib{RET}x{$03}1+1{RET}", many(60))                # ... or a later one
    session(")lib{RET}{RET}{UP}x{DEL}q", many(30))              # the key that continues is not typed into the line
    session(")lib{RET}x")                                       # a short listing never asks for a key: x is typed at the prompt
    print("disk: )LIB pages every 22 lines only when more follow; any key continues, RUN/STOP stops, the prompt returns")


def test_real_drive():
    """A real 1541 (its DOS runs on its own CPU) differs from VICE's folder mode: closing the error channel
    closes every file, so the status of a file being read must be read without closing channel 15.
    The folder tests cannot see that; these can."""
    m, good = ws(VALUES)
    image_session("a{LA}1 2 3{RET}b{LA}'hi'{RET})save q1{RET})clear{RET})load q1{RET})vars{RET}a{RET}b{RET}")
    image_session(")load nothere{RET})load t1{RET})vars{RET})load nothere{RET})wsid{RET}", {"t1": good})   # missing, then found, then missing
    image_session(")lib{RET})lib{RET}", {"t1": good, "small": bytes(3), "n254": bytes(254), "n255": bytes(255)})
    image_session(")lib{RET}a{LA}1{RET})save w1{RET})lib{RET})load w1{RET})lib{RET})load t1{RET}", {"t1": good})   # LIB does not disturb LOAD
    image_session(")lib{RET}", {f"f{i:02d}": bytes(i + 1) for i in range(30)})                            # paging, then the end
    image_session(")lib{RET}x{$03}1+1{RET}", {f"f{i:02d}": bytes(i + 1) for i in range(30)})              # RUN/STOP at MORE
    image_session("a{LA}1{RET})save t1{RET})save t1{RET})lib{RET})load t1{RET})vars{RET}", {"t1": good})     # replacing keeps working
    print("disk: on a real 1541 with a disk image, )SAVE, )LOAD (also missing files) and )LIB match the model")


def test_corrupt():
    m, good = ws(["a←1 2 3", "bb←'hi'", "c←2 2⍴1.5 2 3 4", "d←5"])
    head = good[:5]
    cases = {
        "badmagic": b"NOPE" + good[4:],
        "version1": good[:4] + bytes([1]) + good[5:],
        "version3": good[:4] + bytes([3]) + good[5:],
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
        test_functions()
        test_readonly()
        test_load()
        test_lib()
        test_lib_paging()
        test_corrupt()
        if dos1541_rom() and subprocess.run(["which", "c1541"], capture_output=True).returncode == 0:
            test_real_drive()
        else:
            print("disk: real-drive tests skipped (need the 1541 ROM in roms/dos1541.bin or VICE's folders, and c1541)")
