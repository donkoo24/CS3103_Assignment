# Full T/H rerun — 2026-11-02

Frozen server revision: `fb279c2324ed6ca558b46ce7248dfe0b3a35fdca`. Tests ran sequentially in an isolated user/network namespace, three independent server restarts per profile. H cases are the team-plan scenarios, not the instructor-only hidden evaluator. Workload commands are preserved in `run.sh`.

| Profile | Runs | Median final completeness | Worst run | Median P95 ms | Median fresh finals |
|---|---:|---:|---:|---:|---:|
| t1 | 3 | 100.000% | 100.000% | 2.79 | 100.00% |
| t2 | 3 | 100.000% | 100.000% | 9.54 | 100.00% |
| t3 | 3 | 100.000% | 100.000% | 8.69 | 92.89% |
| t4 | 3 | 100.000% | 100.000% | 8.24 | 98.42% |
| t5 | 3 | 100.000% | 100.000% | 664.36 | 88.27% |
| h1_500 | 3 | 100.000% | 100.000% | 35.26 | 100.00% |
| h1_1000 | 3 | 100.000% | 100.000% | 71.83 | 100.00% |
| h2 | 3 | 100.000% | 100.000% | 23.53 | 73.55% |
| h3_2mbit | 3 | 100.000% | 100.000% | 619.97 | 70.97% |
| h3_1mbit | 3 | 100.000% | 100.000% | 1443.61 | 57.72% |
| h4 | 3 | 100.000% | 100.000% | 537.63 | 92.81% |
| h5 | 3 | 100.000% | 100.000% | 23.39 | 91.45% |
| h6 | 3 | 100.000% | 100.000% | 14.50 | 92.89% |
| h7 | 3 | 100.000% | 100.000% | 11.41 | 91.08% |
| h8 | 3 | 99.873% | 99.526% | 5053.18 | 55.50% |

Total recorded error counters across completed runs: `{'duplicates': 0, 'stale': 0, 'invalid_history_nonfinal': 0, 'connection_errors': 0}`.

The frozen revision passed 257 Python tests, 23 browser tests and the final submission startup check. The separate Firefox offline fix is PR #27 and passed 28 browser tests plus CI; that browser-only change was not mixed into this frozen network campaign.

Each profile retains per-run CSV/JSON, median metrics, exact settings/revision, qdisc description, logs and RSS samples. A successful harness exit does not by itself mean every metric met a target. Check individual runs as well as medians. Packet loss randomness is not fixed, so this is a new campaign rather than an identical loss replay.

Compact JSON, metadata, logs and RSS samples are committed here. Full raw CSV
traces remain on the VM in /home/user1/CS3103_Assignment/.validation/full-rerun-20261102-9i5dcl7b. `SHA256SUMS` records the original files, including those local CSV traces.
