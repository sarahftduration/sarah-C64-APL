#!/usr/bin/env python3
"""Run the whole regression suite, test files in parallel, and optionally log the timings.

    python3 tools/run_tests.py                # run everything, print the results and the duration
    python3 tools/run_tests.py --log          # also append the timings to tests/timing.csv
    python3 tools/run_tests.py --jobs 1       # one file at a time (a serial reference)

First the serial stage (assemble, then the Python model's self-test), then every tests/test_*.py as
its own process, up to --jobs at a time (default: one per CPU). Slowest files start first, judged
from the last logged run. The files do not share writable state: the ones that build images use a
private scratch directory (tests/harness.py), and the rest only read build/. Every file is run to the
end even if another fails, so one run shows all the failures.

tests/timing.csv rows: timestamp,commit,jobs,dirty,item,seconds,result,host
  item is "build+model", each test file, "SUM" (the files' times added: what a serial run costs,
  overstated a little when files compete for CPUs), or "TOTAL" (the wall-clock time of the whole run).
  host is the machine's name: timings from different machines are not comparable.
  Commit the CSV with the change being tested.
"""
import argparse
import concurrent.futures as cf
import csv
import datetime
import glob
import os
import socket
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG = "tests/timing.csv"
HEADER = ["timestamp", "commit", "jobs", "dirty", "item", "seconds", "result", "host"]


# the test files need py65, which lives in the project's virtualenv
PYTHON = os.path.join(ROOT, ".venv", "bin", "python")
if not os.path.exists(PYTHON):
    PYTHON = sys.executable


HOST = socket.gethostname().split(".")[0]


def sh(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT, **kw)


def fmt(seconds):
    m = int(seconds // 60)
    return f"{m}m{seconds - 60 * m:04.1f}s"


def last_times():
    """Seconds per item from the most recent logged run, to start the slow files first."""
    times = {}
    try:
        with open(os.path.join(ROOT, LOG)) as f:
            for row in csv.DictReader(f):
                times[row["item"]] = float(row["seconds"])
    except (OSError, KeyError, ValueError):
        pass
    return times


def run_file(path):
    t0 = time.time()
    env = dict(os.environ, PYTHONPATH="tests")
    r = subprocess.run([PYTHON, path], capture_output=True, text=True, cwd=ROOT, env=env)
    return path, time.time() - t0, r.returncode == 0, r.stdout + r.stderr


def append_log(rows):
    """Append rows. An older log is converted first: no jobs column meant serial runs, and no host column
    meant the runs were made on this machine."""
    path = os.path.join(ROOT, LOG)
    old = []
    if os.path.exists(path):
        with open(path) as f:
            old = list(csv.reader(f))
    if not old:
        old = [HEADER]
    if "jobs" not in old[0]:
        old = [old[0][:2] + ["jobs"] + old[0][2:]] + [r[:2] + ["1"] + r[2:] for r in old[1:]]
    if "host" not in old[0]:
        old = [old[0] + ["host"]] + [r + [HOST] for r in old[1:]]
    with open(path, "w", newline="") as f:
        csv.writer(f, lineterminator="\n").writerows(old + rows)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--jobs", "-j", type=int, default=os.cpu_count() or 1)
    ap.add_argument("--log", action="store_true", help="append the timings to " + LOG)
    args = ap.parse_args()

    start = time.time()
    results = []                                        # (item, seconds, ok)
    outputs = {}

    t0 = time.time()
    b = sh(["make", "-s", "all", "build/apl.prg"])
    m = sh([sys.executable, "apl64.py", "--test"]) if b.returncode == 0 else None
    ok = b.returncode == 0 and m.returncode == 0
    results.append(("build+model", time.time() - t0, ok))
    if not ok:
        print(b.stdout + b.stderr + (m.stdout + m.stderr if m else ""))

    files = sorted(glob.glob(os.path.join(ROOT, "tests", "test_*.py")))
    files = [os.path.relpath(f, ROOT) for f in files]
    if ok:
        known = last_times()
        files.sort(key=lambda f: -known.get(os.path.basename(f), 0))
        jobs = max(1, min(args.jobs, len(files)))
        with cf.ThreadPoolExecutor(max_workers=jobs) as pool:
            futures = [pool.submit(run_file, f) for f in files]
            for fut in cf.as_completed(futures):
                path, secs, good, out = fut.result()
                name = os.path.basename(path)
                results.append((name, secs, good))
                outputs[name] = out
                print(f"  {'ok  ' if good else 'FAIL'} {name:<20} {secs:6.1f}s", flush=True)
    else:
        jobs = 1

    total = time.time() - start
    status = "ok" if all(g for _, _, g in results) else "FAIL"
    for name in sorted(outputs):
        good = next(g for n, _, g in results if n == name)
        print(f"\n=== {name}{'' if good else '  FAILED'}")
        print(outputs[name].rstrip())

    file_secs = sum(s for n, s, _ in results if n != "build+model")
    stamp = datetime.datetime.now().astimezone().strftime("%Y-%m-%dT%H:%M:%S%z")
    commit = sh(["git", "rev-parse", "--short", "HEAD"]).stdout.strip() or "unknown"
    dirty = int(bool(sh(["git", "status", "--porcelain", "--", ".", ":!" + LOG]).stdout.strip()))
    print(f"\nregression suite: {status} in {fmt(total)}, {jobs} at a time "
          f"(files add up to {fmt(file_secs)}; commit {commit}{', uncommitted changes' if dirty else ''})")
    if args.log:
        rows = [[stamp, commit, jobs, dirty, n, f"{s:.1f}", "ok" if g else "FAIL", HOST] for n, s, g in
                sorted(results, key=lambda r: (r[0] != "build+model", r[0]))]
        rows.append([stamp, commit, jobs, dirty, "SUM", f"{file_secs:.1f}", status, HOST])
        rows.append([stamp, commit, jobs, dirty, "TOTAL", f"{total:.1f}", status, HOST])
        append_log(rows)
        print(f"logged to {LOG}")
    return 0 if status == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
