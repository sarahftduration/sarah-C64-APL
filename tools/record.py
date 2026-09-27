"""Record APL/64 running in VICE as an mp4: python3 tools/record.py DEMO.txt OUT.mp4

VICE is started on a private virtual display (Xvfb) at real speed; ffmpeg captures the VICE window (menu and
status bar included) at 50 fps; keys go in through xdotool, so the typing goes through the real keyboard path.
Recording starts once the program is up. The sound is VICE's output to a PulseAudio null sink of its own, recorded by the
same ffmpeg as the picture (so they stay together); VICE 3.9's own wav recorder writes nothing here. No PulseAudio: no sound.

A demo file is lines of typing, except:
    # ...            a comment
    @wait SECONDS    let the machine run
    @pace SECONDS    the delay between typed keys from here on (default 0.09)
    @key NAME        one xdotool key, e.g. Return
    @type TEXT       type TEXT without pressing Return
    @speed N         play the video from here on N times faster (a time-lapse of the typing); @speed 1 for real time again
APL glyphs in the text are typed as the pound-key digraphs (tools/keys.py), so write them as they display.
"""
import os
import subprocess
import sys
import tempfile
import time

HOLD, GAP = 0.10, 0.06        # a key is held for a few frames (the KERNAL scans the keyboard once a frame), then released before the next; shorter holds lose shifted keys
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
import glyphs  # noqa: F401  (keeps the glyph tables importable from here)

# glyph -> the key typed after the pound key (tools/keys.py DIGRAPHS, keys as on the C64 keyboard)
DIGRAPH_KEY = {"⍳": "i", "⍴": "r", "×": "-", "÷": "=", "≠": "8", "≤": "4", "≥": "6", "¯": "2", "¨": "1", "∘": "j",
               "⍬": "'", "⋄": ".", "⍝": ",", "∆": "h", "∇": "g", "⌈": "s", "⌊": "d", "∧": "w", "∨": "v",
               "⌽": "a", "↑": "y", "↓": "u", "∊": "e", "⍋": "7", "⍒": "3", "⍉": "t", "⍟": "*", "○": "o",
               "→": "]", "⎕": "L", "|": "l", "≤": "4"}
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


SHIFTED = {"plus": "equal", "asterisk": "8", "parenleft": "9", "parenright": "0", "exclam": "1", "at": "2", "numbersign": "3", "dollar": "4",
           "percent": "5", "asciicircum": "6", "ampersand": "7", "underscore": "minus", "quotedbl": "apostrophe", "colon": "semicolon",
           "less": "comma", "greater": "period", "question": "slash", "asciitilde": "grave"}


def press(k, env, pace):
    """One key held for a few frames (VICE scans the keyboard once a frame). A shifted one has the shift key pressed first and
    held throughout: a bare keysym that needs a shift sends both at once, and under load VICE sometimes sees the key without it."""
    base = SHIFTED.get(k) or (k.lower() if len(k) == 1 and k.isupper() else None)
    if base:
        run(["xdotool", "keydown", "Shift_L"], env=env)
        time.sleep(0.04)
        run(["xdotool", "keydown", base], env=env)
        time.sleep(HOLD)
        run(["xdotool", "keyup", base], env=env)
        time.sleep(0.03)
        run(["xdotool", "keyup", "Shift_L"], env=env)
    else:
        run(["xdotool", "keydown", k], env=env)
        time.sleep(HOLD)
        run(["xdotool", "keyup", k], env=env)
    time.sleep(max(pace - HOLD, GAP))


def retime(src, dst, marks, total, audio):
    """Re-encode src with the stretches between the marks played at their speeds (the sound of a sped-up stretch is dropped)."""
    ends = [t for t, _ in marks[1:]] + [total + 1]
    parts, labels = [], []
    for i, ((a, speed), b) in enumerate(zip(marks, ends)):
        if b - a < 0.05:
            continue
        parts.append(f"[0:v]trim=start={a:.3f}:end={b:.3f},setpts=(PTS-STARTPTS)/{speed}[v{i}]")
        labels.append(f"[v{i}]")
        if audio:
            if speed == 1:
                parts.append(f"[0:a]atrim=start={a:.3f}:end={b:.3f},asetpts=PTS-STARTPTS[a{i}]")
            else:
                parts.append(f"anullsrc=r=44100:cl=stereo,atrim=duration={(b - a) / speed:.3f},asetpts=PTS-STARTPTS[a{i}]")
            labels.append(f"[a{i}]")
    n = len(labels) // (2 if audio else 1)
    graph = ";".join(parts) + f";{''.join(labels)}concat=n={n}:v=1:a={1 if audio else 0}" + ("[vo][ao]" if audio else "[vo]") + ";[vo]fps=50[out]"
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", src, "-filter_complex", graph, "-map", "[out]"]
    if audio:
        cmd += ["-map", "[ao]", "-c:a", "aac"]
    run(cmd + ["-c:v", "libx264", "-preset", "veryfast", "-crf", "16", "-pix_fmt", "yuv420p", dst])


def null_sink():
    """A PulseAudio sink of our own for VICE to play into (module id), or None if there is no PulseAudio."""
    r = subprocess.run(["pactl", "load-module", "module-null-sink", "sink_name=apl64rec"], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 and r.stdout.strip().isdigit() else None


def record(demo, out, prg=None, boot=None, reu_kb=4096):
    if prg is None:
        subprocess.run(["make", "-C", ROOT, "build/apl.prg"], check=True, capture_output=True)      # (the PRG that is run must be the current one)
        prg = os.path.join(ROOT, "build", "apl.prg")
    with tempfile.TemporaryDirectory() as tmp:
        disp = f":{700 + os.getpid() % 200}"
        xvfb = subprocess.Popen(["Xvfb", disp, "-screen", "0", "1024x768x24", "-nolisten", "tcp"],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        env = dict(os.environ, DISPLAY=disp)
        procs = [xvfb]
        sink = null_sink()
        if sink:
            env["PULSE_SINK"] = "apl64rec"
        try:
            time.sleep(1)
            vice = subprocess.Popen(
                ["x64sc", "-default", "+saveres", "-sounddev", "pulse" if sink else "dummy",
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
                                   *(["-f", "pulse", "-i", "apl64rec.monitor"] if sink else []),
                                   "-c:v", "libx264", "-preset", "veryfast", "-crf", "16", "-pix_fmt", "yuv420p",
                                   *(["-c:a", "aac"] if sink else []), silent],
                                  env=env, stdin=subprocess.PIPE)
            t0 = time.time()
            marks = [(0.0, 1.0)]                # (seconds since the capture began, the speed of the video from then on)
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
                if line.startswith("@speed "):
                    marks.append((time.time() - t0, float(line[7:])))
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
            if len(marks) > 1:
                retime(silent, out, marks, elapsed, bool(sink))
            else:
                os.replace(silent, out)
            return elapsed
        finally:
            if sink:
                subprocess.run(["pactl", "unload-module", sink], capture_output=True)
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
