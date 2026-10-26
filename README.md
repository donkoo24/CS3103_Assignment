# LiveRecall — CS3103 Assignment 4

Leonard's feature PRs implement the bounded overload policy, browser shell,
Ubuntu public-test helper, one before/after comparison and experiment/report work.
The PDF is the requirement source. The runtime needs only `requirements.txt`.

## Ubuntu setup and startup

```sh
sudo apt-get update
sudo apt-get install -y python3 python3-venv python3-pip iproute2
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python solution_server.py --port 8765
```

For development: `python -m pip install -r requirements-dev.txt`.
Run `python -m pytest -q`, the browser tests with Node 20 or newer
(`node --test client/tests/*.*js`), and `python submission_check.py`.
No model, database or network access is needed to start the server.

## Browser demo

```sh
python -m http.server 8000 --directory client
# In another terminal:
python caption_source.py --duration 120
```

Open `http://<VM-IP>:8000` in two tabs. The browser uses the page hostname on
WebSocket port 8765. Override with `?server=ws%3A%2F%2F<host>%3A8765`.
The required demo shows continuous provisional/final caption replacement,
15/30/60-second local recall (default 30), late join and automatic reconnect
with incremental final recovery and no duplicates. See DEMO_GUIDE.md.

Don's server wiring and client store, Damian's Hub and connection module,
and Dylan's server history are now on `main`. Leonard's separate shell PR
#13 adapts Don's ES-module store and Damian's connection API. Dylan's browser
history module is still absent. The shell reports Offline until it is added.
The report describes assembled server measurements, not a completed browser demo.
The draft PRs must not be submitted as a completed application without integration.

## Public experiments

After merging PR #11's public-test wrapper with the server and policy:

```sh
bash scripts/stress.sh t1
bash scripts/stress.sh t2
bash scripts/stress.sh t3
bash scripts/stress.sh t4
# Private namespace: real tc/netem without changing the VM's host network.
unshare --user --map-root-user --net bash -c 'ip link set lo up; PYTHON=.venv/bin/python bash scripts/stress.sh t5'
```

Each profile runs three independent experiments with the exact PUBLIC_TESTS.md
parameters and saves CSV/JSON, logs, memory, settings and median metrics. T5
applies 120 ms ±30 ms delay and 3% loss to loopback. A cleanup trap removes shaping.
Alternatively use the supplied commands directly from PUBLIC_TESTS.md.

See `docs/before-after.md` for the single paired T3 comparison. Semantic scheduling
is compared with the same server in bounded FIFO mode; all other settings stay
fixed. Defaults are conservative comparison settings, not a claimed hidden-test
optimum. The PDF's hidden-mark completeness caps are 99% and 95%; the team's
stricter CI checks are separate development criteria.

## Report and submission

`experiments/public/` contains only the required public results and one comparison.
`docs/report/experiments-and-results.md` explains method, measurements, trade-offs,
limitations and future work. Rebuild `report.pdf` using `python scripts/build_report.py`.
Rebuild figures using `python scripts/plot_experiments.py`.

Before submission: integrate and manually verify the browser, bound the long-lived
client store and server revision state, and review the four-page
report and AI usage; agree the contribution percentages; record the compulsory
5–7 minute demo video; run `python submission_check.py --final` on a clean checkout.
A file-presence check does not certify these human deliverables. No final tag is set.
Create a submission archive with `git archive --format=zip HEAD -o ../LiveRecall.zip`
only after team review. TEAM_TASKS.md is local planning material and is not tracked.
