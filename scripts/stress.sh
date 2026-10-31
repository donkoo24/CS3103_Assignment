#!/usr/bin/env bash
# The PDF's public tests, each with three independent server restarts.
set -euo pipefail
cd "$(dirname "$0")/.."
scenario=${1:?Usage: stress.sh <t1|t2|t3|t4|t5>}
[[ $# == 1 ]] || { echo "Use the exact public profiles; see PUBLIC_TESTS.md" >&2; exit 2; }
python=${PYTHON:-python3}
clients=100; duration=60; extra=()
case "$scenario" in
 t1) clients=20; duration=20;;
 t2|t5) duration=40;;
 t3) extra=(--slow-percent 10 --slow-ms 500);;
 t4) extra=(--disconnect-percent 20 --disconnect-at 15 --disconnect-seconds 5);;
 *) echo "Unknown public test: $scenario" >&2; exit 2;;
esac
out=${LR_OUTPUT:-experiments/$scenario/$(date -u +%Y%m%dT%H%M%S)-$$}
[[ ! -e $out ]] || { echo "Refusing to overwrite $out" >&2; exit 1; }
mkdir -p "$out"
netns=$(readlink /proc/self/ns/net | tr -cd '0-9')
exec 9>"/tmp/liverecall-stress-${netns:-host}.lock"
flock -n 9 || { echo "Another experiment is active in this network namespace" >&2; exit 1; }
tc_command=(tc)
if (( EUID != 0 )); then tc_command=(sudo -n tc); fi
shaped=0; runner_pid=; monitor_pid=
cleanup() {
  if [[ -n $runner_pid ]]; then kill -TERM -- "-$runner_pid" 2>/dev/null || true; fi
  if [[ -n $monitor_pid ]]; then kill "$monitor_pid" 2>/dev/null || true; fi
  if (( shaped )); then "${tc_command[@]}" qdisc del dev lo root; fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
if [[ $scenario == t5 ]]; then
  # Do not replace an existing experiment's qdisc.
  if ! tc qdisc show dev lo | grep -q '^qdisc noqueue '; then
    echo "Loopback already has a root qdisc; reset it explicitly first" >&2; exit 1
  fi
  "${tc_command[@]}" qdisc add dev lo root netem delay 120ms 30ms loss 3%
  shaped=1
fi
"$python" scripts/experiment_record.py "$out/metadata.json" "$scenario"
setsid "$python" run_demo.py --clients "$clients" --duration "$duration" --runs 3   --quiet-server "${extra[@]}" --output-stem "$out/results" >"$out/run.log" 2>&1 &
runner_pid=$!
"$python" scripts/monitor_runs.py --parent "$runner_pid" --output "$out/memory.csv" &
monitor_pid=$!
status=0
wait "$runner_pid" || status=$?
kill "$monitor_pid" 2>/dev/null || true
wait "$monitor_pid" 2>/dev/null || true
monitor_pid=
kill -TERM -- "-$runner_pid" 2>/dev/null || true
runner_pid=
if (( status )); then cat "$out/run.log"; exit "$status"; fi
"$python" scripts/experiment_record.py --summarize "$out"
echo "Three-run results and medians: $out"
