"""Sample only server children of this run_demo/burst runner across restarts."""

from __future__ import annotations

import argparse
import csv
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from monitor_server import rss_kb


def server_children(parent):
    children = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            args = (entry / "cmdline").read_bytes().split(b"\0")
            if b"solution_server.py" not in args:
                continue
            status = (entry / "status").read_text()
            ppid = next(
                line.split()[1]
                for line in status.splitlines()
                if line.startswith("PPid:")
            )
            if int(ppid) == parent:
                children.append(int(entry.name))
        except (OSError, StopIteration, ValueError):
            continue
    return children


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parent", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    start = time.monotonic()
    # Stream to disk; no growing in-memory sample buffer.
    with args.output.open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["elapsed_s", "pid", "rss_mb"])
        while True:
            try:
                os.kill(args.parent, 0)
            except ProcessLookupError:
                break
            for pid in server_children(args.parent):
                value = rss_kb(pid)
                if value is not None:
                    writer.writerow(
                        [f"{time.monotonic() - start:.3f}", pid, f"{value / 1024:.3f}"]
                    )
            stream.flush()
            time.sleep(1)


if __name__ == "__main__":
    main()
