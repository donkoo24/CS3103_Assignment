#!/usr/bin/env python3
"""H7 burst scenario: the public harness at a much higher caption revision rate.

run_demo.py always runs caption_source.py at its default pace (~4 messages per
0.75 s). This wrapper runs the same unmodified instructor programs
(solution_server.py, load_clients.py, caption_source.py, analyse_results.py)
with a faster source, e.g. 10x the revision rate, and reports the median of
independent runs exactly like run_demo.py.

    python scripts/burst_run.py --clients 200 --duration 40 --runs 3 \
        --revision-delay 0.02 --segment-gap 0.035 --slow-percent 10
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from analyse_results import analyse_file, print_summary
from run_demo import print_medians, terminate_process, wait_for_port

REVISIONS_PER_SEGMENT = 3  # the public caption_source.py generator


def one_run(args, run_no: int) -> dict:
    stem = f"{args.output_stem}_run{run_no:02d}" if args.runs > 1 else args.output_stem
    csv_path, json_path = ROOT / f"{stem}.csv", ROOT / f"{stem}.json"
    uri = f"ws://127.0.0.1:{args.port}"
    per_segment = (REVISIONS_PER_SEGMENT - 1) * args.revision_delay + args.segment_gap
    active = max(3.0, args.duration - args.source_start_delay - 2.0)
    segments = max(4, math.floor(active / per_segment))

    py = sys.executable
    server = clients = None
    try:
        print(
            f"\n=== Run {run_no}/{args.runs}: {segments} segments, "
            f"{REVISIONS_PER_SEGMENT / per_segment:.1f} revisions/s ==="
        )
        server = subprocess.Popen(
            [py, "-u", "solution_server.py", "--port", str(args.port)],
            cwd=ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
        )
        wait_for_port(args.port, server)
        clients = subprocess.Popen(
            [
                py,
                "-u",
                "load_clients.py",
                "--uri",
                uri,
                "--clients",
                str(args.clients),
                "--duration",
                str(args.duration),
                "--output",
                str(csv_path),
                "--seed",
                str(args.seed),
                "--slow-percent",
                str(args.slow_percent),
                "--slow-ms",
                str(args.slow_ms),
            ],
            cwd=ROOT,
        )
        time.sleep(args.source_start_delay)
        subprocess.run(
            [
                py,
                "-u",
                "caption_source.py",
                "--uri",
                uri,
                "--quiet",
                "--segments",
                str(segments),
                "--revision-delay",
                str(args.revision_delay),
                "--segment-gap",
                str(args.segment_gap),
            ],
            cwd=ROOT,
            check=True,
        )
        if clients.wait() != 0:
            raise RuntimeError("load_clients.py failed")
        summary = analyse_file(
            csv_path,
            expected_finals=segments,
            expected_updates=segments * REVISIONS_PER_SEGMENT,
            fresh_threshold_ms=args.fresh_threshold_ms,
        )
        print_summary(summary, args.fresh_threshold_ms)
        json_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        return summary
    finally:
        terminate_process(clients, "load_clients.py")
        terminate_process(server, "solution_server.py")
        time.sleep(0.25)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--clients", type=int, default=200)
    p.add_argument("--duration", type=float, default=40)
    p.add_argument("--runs", type=int, default=1)
    p.add_argument("--revision-delay", type=float, default=0.02)
    p.add_argument("--segment-gap", type=float, default=0.035)
    p.add_argument("--slow-percent", type=float, default=0)
    p.add_argument("--slow-ms", type=float, default=500)
    p.add_argument("--fresh-threshold-ms", type=float, default=500.0)
    p.add_argument("--source-start-delay", type=float, default=1.0)
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--seed", type=int, default=3103)
    p.add_argument("--output-stem", default="h7_burst")
    # Accepted for drop-in compatibility with run_demo.py's CLI (stress.sh);
    # the server's output is always discarded here.
    p.add_argument("--quiet-server", action="store_true")
    args = p.parse_args()
    summaries = [one_run(args, n) for n in range(1, args.runs + 1)]
    print_medians(summaries)


if __name__ == "__main__":
    main()
