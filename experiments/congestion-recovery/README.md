# H3/H8 recovery evidence

See ../../docs/congestion-recovery.md for findings, workload commands, comparisons
and limitations. `before/` contains the original local H3/H8 campaign; `after/`
contains three independent restarts of each profile at Git revision d38cd28.

`summary.json` contains medians of per-run metrics, except the aborted baseline
1 Mbit/s profile, which is explicitly marked without a median. CSV and logs are
losslessly compressed. `raw-sha256.txt` hashes their original uncompressed bytes.
The instructor source, clients and analyser were not modified. These workloads
are team-plan hidden-like scenarios, not the private instructor evaluator.
