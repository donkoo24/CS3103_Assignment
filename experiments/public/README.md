# Required public-test evidence

`t1`–`t5`: refreshed on the assembled PR #19 server code after PRs #16
and #17 merged, with three independent restarts per case, run sequentially in an isolated user/network namespace on the existing Ubuntu
22.04.5 VM. Each directory contains original analyser JSON, losslessly compressed
instructor CSV, logs, RSS and exact source/settings metadata. Percentiles in
`summary.json` are medians of per-run percentiles. Netem randomness is not fixed.

All three refreshed T5 runs reached 100% final completeness (4,900/4,900
per run). An earlier separate campaign missed the last final in one T5 run;
netem randomness and timing differ, so that change cannot be attributed to
PR #19. The PDF's hidden-mark cap starts below 99%.

`comparison/fifo` and `comparison/semantic`: a fresh controlled T3 pair,
three independent server restarts per mode. Both used the same assembled Git
revision, private network namespace, four-CPU affinity, workload and effective
settings except `LR_DELIVERY`. The 16-CPU T1–T5 public campaign is separate;
do not attribute absolute latency differences between campaigns to the delivery
switch. FIFO's incomplete delivery is the measured baseline, not a pass claim.

The tested runtime combines Don's protocol/state/server wiring, Dylan's final
history and Damian's Hub with Leonard's policy/configuration and PR #19's state
retention fix. Metadata records Git revision, settings, CPU and namespace;
`runtime-sha256.txt` lists assembled server file hashes. The browser shell/store/
history are not exercised by the simulated-client tests. The comparison tests
slow readers, with no `tc` bandwidth cap or packet loss.

The Hub, server wiring, test wrapper and policy from PRs #6, #10, #11 and #12
are now on `main`. Reproduce with the five commands in README.md, then the
two T3 commands in docs/before-after.md. No instructor test
program or measurement logic was edited. The larger optional matrices, source
bundles and failed sweep trials are no longer submission artifacts; the old
feature branches were backed up locally before rewriting them.

PR #19 adds source-state pruning and malformed HELLO handling to the
assembled campaign; its cross-component behavior needs peer review before final submission. These results establish deterministic public behavior only, not
complete application correctness or hidden-performance marks. Inspect all three
runs, not only medians, for completeness and nonzero error counters.
