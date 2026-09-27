"""Record APL/64 running in VICE as an mp4: python3 tools/record.py DEMO.txt OUT.mp4

VICE is started on a private virtual display (Xvfb) at real speed; ffmpeg captures the VICE window (menu and
status bar included) at 50 fps; keys go in through xdotool, so the typing goes through the real keyboard path.
Recording starts once the program is up. There is no audio yet (no SID support); when there is, record VICE's
wav (-soundrecdev wav) and mux it in.

A demo file is lines of typing, except:
    # ...            a comment
    @wait SECONDS    let the machine run
    @pace SECONDS    the delay between typed keys from here on (default 0.09)
    @key NAME        one xdotool key, e.g. Return
    @type TEXT       type TEXT without pressing Return
APL glyphs in the text are typed as the pound-key digraphs (tools/keys.py), so write them as they display.
"""
import os
import subprocess
import sys
import tempfile
import time

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
import glyphs  # noqa: F401  (keeps the glyph tables importable from here)

# glyph -> the key typed after the pound key (tools/keys.py DIGRAPHS, keys as on the C64 keyboard)
DIGRAPH_KEY = {"⍳": "i", "⍴": "r", "×": "-", "÷": "=", "≠": "8", "≤": "4", "≥": "6", "¯": "2", "¨": "1", "∘": "j",
               "⍬": "'", "⋄": ".", "⍝": ",", "∆": "h", "∇": "g", "⌈": "s", "⌊": "d", "∧": "w", "∨": "v",
               "⌽": "a", "↑": "y", "↓": "u", "∊": "e", "⍋": "7", "⍒": "3", "⍉": "t", "⍟": "*", "○": "o",
               "→": "]", "⎕": "L"}
XKEY = {" ": "space", "'": "apostrophe", "-": "minus", "=": "equal", "*": "asterisk", ".": "period",
        ",": "comma", "[": "bracketleft", "]": "bracketright", "<": "less", ">": "greater", "/": "slash",
        "(": "parenleft", ")": "parenright", "+": "plus", ";": "semicolon", ":": "colon", "!": "exclam",
        "?": "question", "\"": "quotedbl", "@": "at", "#": "numbersign", "$": "dollar", "%": "percent",
        "&": "ampersand", "_": "underscore", "|": "bar", "\\": "backslash", "~": "asciitilde", "^": "asciicircum"}


def keys_for(text):
    """The xdotool key names that type TEXT."""
    out = []
    for ch in text:
        if ch in DIGRAPH_KEY:
            out += ["backslash", XKEY.get(DIGRAPH_KEY[ch], DIGRAPH_KEY[ch])]
        elif ch == "←":
            out.append("End")                          # VICE maps End to the C64 left-arrow key
        elif ch == "\\":
            out += ["backslash", "backslash"]         # the pound key twice: a real backslash (scan, expand)
        elif ch.isalnum() and ch.isascii():
            out.append(ch)
        else:
            out.append(XKEY.get(ch, ch))
    return out


def run(cmd, **kw):
    return subprocess.run(cmd, check=True, capture_output=True, text=True, **kw)


def press(k, env, pace):
    """One key held for a few frames (VICE scans the keyboard once per frame, so a bare tap can be lost)."""
    run(["xdotool", "keydown", k], env=env)
    time.sleep(0.08)
    run(["xdotool", "keyup", k], env=env)
    time.sleep(max(pace - 0.08, 0.06))


def record(demo, out, prg=None, boot=None, reu_kb=4096):
    prg = prg or os.path.join(ROOT, "build", "apl.prg")
    with tempfile.TemporaryDirectory() as tmp:
        disp = f":{700 + os.getpid() % 200}"
        xvfb = subprocess.Popen(["Xvfb", disp, "-screen", "0", "1024x768x24", "-nolisten", "tcp"],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        env = dict(os.environ, DISPLAY=disp)
        procs = [xvfb]
        try:
            time.sleep(1)
            vice = subprocess.Popen(
                ["x64sc", "-default", "+saveres", "-sounddev", "dummy",
                 "-kernal", f"{ROOT}/roms/kernal.bin", "-basic", f"{ROOT}/roms/basic.bin",
                 "-chargen", f"{ROOT}/roms/chargen.bin", "-autostartprgmode", "1", "-autostart", prg,
                 "-reu", "-reusize", str(reu_kb), "-VICIIfilter", "0"],
                env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            procs.append(vice)
            win = None
            for _ in range(100):
                r = subprocess.run(["xdotool", "search", "--onlyvisible", "--class", "x64sc"], env=env,
                                   capture_output=True, text=True)
                if r.stdout.split():
                    win = r.stdout.split()[-1]
                    break
                time.sleep(0.2)
            assert win, "VICE did not open a window"
            time.sleep(1)
            geo = run(["xdotool", "getwindowgeometry", "--shell", win], env=env).stdout
            g = dict(l.split("=") for l in geo.split())
            x, y, w, h = int(g["X"]), int(g["Y"]), int(g["WIDTH"]) & ~1, int(g["HEIGHT"]) & ~1
            run(["xdotool", "windowfocus", win], env=env)
            time.sleep(boot if boot is not None else 8)   # the welcome screen (REU overlays are stashed first)
            silent = os.path.join(tmp, "v.mp4")
            ff = subprocess.Popen(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "x11grab", "-draw_mouse", "0",
                                   "-framerate", "50", "-video_size", f"{w}x{h}", "-i", f"{disp}+{x},{y}",
                                   "-c:v", "libx264", "-preset", "veryfast", "-crf", "16", "-pix_fmt", "yuv420p", silent],
                                  env=env, stdin=subprocess.PIPE)
            t0 = time.time()
            pace = 0.09
            for line in demo.splitlines():
                line = line.rstrip("\n")
                if line.startswith("#") or (not line and False):
                    continue
                if line.startswith("@wait "):
                    time.sleep(float(line[6:]))
                    continue
                if line.startswith("@pace "):
                    pace = float(line[6:])
                    continue
                if line.startswith("@key "):
                    press(line[5:], env, pace)
                    continue
                text, ret = (line[6:], False) if line.startswith("@type ") else (line, True)
                for k in keys_for(text) + (["Return"] if ret else []):
                    press(k, env, pace)
            ff.stdin.write(b"q")
            ff.stdin.flush()
            ff.wait(timeout=30)
            elapsed = time.time() - t0
            vice.terminate()
            vice.wait(timeout=10)
            os.replace(silent, out)
            return elapsed
        finally:
            for p in reversed(procs):
                if p.poll() is None:
                    p.terminate()
                    try:
                        p.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        p.kill()


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    print(f"recorded {record(open(sys.argv[1]).read(), sys.argv[2]):.1f} s to {sys.argv[2]}")
