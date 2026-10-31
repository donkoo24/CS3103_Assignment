"""Record the tested source/settings and medians of three independent runs."""
import json
import math
import os
import platform
import statistics
import subprocess
import sys
from pathlib import Path
from dataclasses import asdict
import websockets


def median_summary(runs):
    result = {}
    for key in set.intersection(*(set(run) for run in runs)):
        values = [run[key] for run in runs]
        if all(isinstance(v, dict) for v in values):
            result[key] = median_summary(values)
        elif all(isinstance(v, (int, float)) and not isinstance(v, bool)
                 and math.isfinite(v) for v in values):
            result[key] = statistics.median(values)
    return result


def main():
    if sys.argv[1] == "--summarize":
        directory = Path(sys.argv[2])
        paths = sorted(directory.glob("results_run*.json"))
        if len(paths) != 3:
            raise SystemExit("Expected three complete runs; no median produced")
        runs = [json.loads(p.read_text()) for p in paths]
        (directory / "median.json").write_text(json.dumps(median_summary(runs), indent=2))
        return
    path, scenario = sys.argv[1:]
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    try:
        from liverecall.config import load_from_env
        config = asdict(load_from_env())
    except ImportError:
        config = None
    data = dict(scenario=scenario, platform=platform.platform(), python=sys.version,
                websockets=websockets.__version__, effective_config=config,
                knobs={k:v for k,v in os.environ.items() if k.startswith("LR_")},
                revision=subprocess.check_output(["git","rev-parse","HEAD"], text=True).strip(),
                dirty=bool(subprocess.check_output(["git","status","--porcelain","--untracked-files=no"],text=True).strip()),
                cpu_affinity=sorted(os.sched_getaffinity(0)),
                network_namespace=os.readlink("/proc/self/ns/net"))
    Path(path).write_text(json.dumps(data, indent=2))


if __name__ == "__main__":
    main()
