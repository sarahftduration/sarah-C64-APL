#!/bin/bash
# Run the whole regression suite (what `make test` runs), print how long it took, and append the
# timings to tests/timing.csv so the growth can be tracked. Commit the CSV with the change being tested.
#
# Rows: timestamp,commit,dirty,item,seconds,result
#   item is "build+model" (assembling and the Python model's self-test), each tests/test_*.py, or TOTAL.
#   dirty is 1 if the working tree differed from the commit (other than this log), 0 otherwise.
set -u
cd "$(dirname "$0")/.."
LOG=tests/timing.csv
PY=.venv/bin/python

now() { date +%s.%N; }
[ -f "$LOG" ] || echo "timestamp,commit,dirty,item,seconds,result" > "$LOG"
stamp=$(date +%Y-%m-%dT%H:%M:%S%z)
commit=$(git rev-parse --short HEAD 2>/dev/null || echo unknown)
dirty=0; [ -n "$(git status --porcelain -- . ':!tests/timing.csv' 2>/dev/null)" ] && dirty=1

rows=()
record() { rows+=("$stamp,$commit,$dirty,$1,$(printf '%.1f' "$2"),$3"); }
fmt() { awk -v s="$1" 'BEGIN{m=int(s/60); printf "%dm%04.1fs", m, s-60*m}'; }

t_all=$(now); status=ok

t0=$(now)
if make -s all build/apl.prg && python3 apl64.py --test >/dev/null; then r=ok; else r=FAIL; status=FAIL; fi
record "build+model" "$(echo "$(now) - $t0" | bc -l)" $r

if [ "$status" = ok ]; then
    for t in tests/test_*.py; do
        t0=$(now)
        if PYTHONPATH=tests $PY "$t"; then r=ok; else r=FAIL; status=FAIL; fi
        record "$(basename "$t")" "$(echo "$(now) - $t0" | bc -l)" $r
        [ "$status" = ok ] || break            # like make test: stop at the first failure
    done
fi

total=$(echo "$(now) - $t_all" | bc -l)
record TOTAL "$total" $status
printf '%s\n' "${rows[@]}" >> "$LOG"

echo
echo "regression suite: $status in $(fmt "$total") (commit $commit$([ $dirty = 1 ] && echo ", uncommitted changes"))"
for r in "${rows[@]}"; do IFS=, read -r _ _ _ item secs res <<<"$r"; printf '  %-22s %7ss  %s\n' "$item" "$secs" "$res"; done
echo "logged to $LOG"
[ "$status" = ok ]
