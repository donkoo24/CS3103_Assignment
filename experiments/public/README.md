# Required public-test evidence

`t1`–`t5`: refreshed after PRs #16 and #17 merged, with three independent
restarts per case on the reduced configuration,
run sequentially in an isolated user/network namespace on the existing Ubuntu
22.04.5 VM. Each directory contains original analyser JSON, losslessly compressed
instructor CSV, logs, RSS and exact source/settings metadata. Percentiles in
`summary.json` are medians of per-run percentiles. Netem randomness is not fixed.

T5 run 2 reached 99.98% final completeness (one final out of 4,900 was not
observed by the end); T5's three-run median is 100%. All three runs remain
visible. The PDF's hidden-mark cap starts below 99%; this public result is
reported honestly, without inferring that the final would never arrive.

`comparison/fifo` and `comparison/semantic`: the one retained earlier controlled
T3 pair, three independent repeats each. Both ran with the same four-CPU affinity
and unchanged settings. Other experiments used separate CPU partitions/namespaces
at that time. Current public runs use the VM's full 16-CPU affinity and execute
sequentially, so do not combine the two campaigns as an isolated optimization
comparison. FIFO's incomplete delivery is the measured baseline, not a pass claim.

The tested runtime combines Don's protocol/state/server wiring, Dylan's final
history and Damian's real Hub with Leonard's policy/configuration. See metadata
for source hashes and `runtime-sha256.txt` for the assembled runtime file hashes.
The browser shell/store/history are not exercised by the simulated-client tests.
The delivery Hub and policy settings match the retained earlier comparison.
The current server entry point also uses Dylan's later history cache, so the
older paired experiment should be interpreted within its own source snapshot.
Some old metadata contains `LR_PROBE_INTERVAL=1`;
the old configuration did not read that variable and the Hub's default is 1 second.
Absolute paths in old metadata describe that original run, not portable commands.

The Hub and server wiring from PRs #6 and #10 are now on `main`. Reproduce
after merging PRs #11 and #12; run the five commands in README.md, then the
two T3 commands in docs/before-after.md. No instructor test
program or measurement logic was edited. The larger optional matrices, source
bundles and failed sweep trials are no longer submission artifacts; the old
feature branches were backed up locally before rewriting them.

The report discusses source-state pruning and malformed HELLO review still needed
in peer wiring. These results establish deterministic public behavior only, not
complete application correctness or hidden-performance marks. Inspect all three
runs, not only medians, for completeness and nonzero error counters.
