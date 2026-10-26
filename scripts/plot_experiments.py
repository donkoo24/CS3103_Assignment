"""Plot the first real T5 trace and T3 memory samples; no synthetic evidence."""
import csv
import gzip
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path("experiments/public")

def rows(path):
    with gzip.open(path, "rt", newline="") as stream:
        return list(csv.DictReader(stream))


def main():
    trace = ROOT / "t5/results_run01.csv.gz"
    values = sorted(float(r["latency_ms"]) for r in rows(trace)
                    if r["event_type"] == "CAPTION_UPDATE" and r["status"] == "accepted")
    fig, ax = plt.subplots(figsize=(6, 3))
    ax.step(values, [(i+1)/len(values) for i in range(len(values))], where="post")
    ax.set(xlabel="Caption age (ms)", ylabel="Cumulative fraction", title="T5 accepted live updates, run 1")
    fig.tight_layout(); fig.savefig(ROOT / "t5-cdf.png", dpi=150); plt.close(fig)
    fig, ax = plt.subplots(figsize=(6, 3))
    groups = {}
    for r in rows(ROOT / "t3/memory.csv.gz"):
        groups.setdefault(r["pid"], []).append(r)
    for pid, group in groups.items():
        ax.plot([float(r["elapsed_s"]) for r in group],
                [float(r["rss_mb"]) for r in group], label=f"PID {pid}")
    ax.set(xlabel="Elapsed (s)", ylabel="Server RSS (MiB)", title="T3: three independent server processes")
    ax.legend(); fig.tight_layout(); fig.savefig(ROOT / "t3-memory.png", dpi=150); plt.close(fig)


if __name__ == "__main__":
    main()
