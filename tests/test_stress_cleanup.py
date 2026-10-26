"""Exercise shell failure cleanup with fake tc; never requires root/network changes."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("runner_status,gate_status", [(0, 0), (7, 0)])
def test_network_cleanup_even_on_runner_or_gate_failure(
    tmp_path, runner_status, gate_status
):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    shutil.copy(ROOT / "scripts/stress.sh", scripts / "stress.sh")
    bin_path = tmp_path / "bin"
    bin_path.mkdir()
    helpers = {
        "flock": "#!/bin/bash\nexit 0\n",
        "sudo": '#!/bin/bash\necho "$*" >> "$CALLS"\nexit 0\n',
        "tc": '#!/bin/bash\necho "qdisc noqueue 0: root"\n',
        "fake-python": """#!/bin/bash
case "$1" in
run_demo.py)
  if [[ $RUNNER_STATUS != 0 ]]; then exit "$RUNNER_STATUS"; fi
  while [[ $# -gt 0 ]]; do
    if [[ $1 == --output-stem ]]; then mkdir -p "$(dirname "$2")"; for run in 01 02 03; do echo '{}' > "${2}_run${run}.json"; done; break; fi
    shift
  done;;
scripts/check_results.py) exit "$GATE_STATUS";;
esac
exit 0
""",
    }
    for name, content in helpers.items():
        path = bin_path / name
        path.write_text(content)
        path.chmod(0o755)
    calls = tmp_path / "calls"
    env = dict(
        os.environ,
        PATH=f"{bin_path}:{os.environ['PATH']}",
        PYTHON=str(bin_path / "fake-python"),
        CALLS=str(calls),
        RUNNER_STATUS=str(runner_status),
        GATE_STATUS=str(gate_status),
    )
    result = subprocess.run(
        ["bash", str(scripts / "stress.sh"), "t5"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == (runner_status or gate_status), result.stderr
    assert "tc qdisc add dev lo root netem" in calls.read_text()
    assert calls.read_text().splitlines()[-1] == "-n tc qdisc del dev lo root"
