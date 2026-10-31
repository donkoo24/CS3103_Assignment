# One controlled before/after comparison

The PDF requires at least one public stress comparison. Use T3 with the same
source revision and all transport settings unchanged; disable only semantic
scheduling. The real Hub and server wiring are now on `main`. Merge PR #12 for the
semantic/FIFO switch and PR #11 for the public-test wrapper before running. No historical source rewriting,
snapshot builder, full sweep or hidden-test matrix is needed.

```sh
LR_DELIVERY=fifo LR_OUTPUT=experiments/before-t3 bash scripts/stress.sh t3
LR_DELIVERY=semantic LR_OUTPUT=experiments/after-t3 bash scripts/stress.sh t3
```

Both commands use 100 clients, 60 seconds, 10% slow readers at 500 ms, three
independent server restarts, 4096-byte writes, queue 16 and compression off.
Keep seed 3103 (the instructor default). Compare the medians for completeness,
P50/P95/P99, fresh caption/final ratios, normal-client latency, recovery and RSS.
Keep all three per-run summaries and logs; do not substitute a fast but incomplete
run for a successful optimization. FIFO is an experimental mode only.

The retained measured comparison is in `experiments/public/comparison/` on the
report branch. Its source hashes and settings are recorded alongside the data.
It improves completeness and tail age, with slow-reader freshness still limited.
No claim is made that these settings optimize constrained-bandwidth hidden tests.
