# Ubuntu public experiments

Use the existing Ubuntu VM. Install with `bash scripts/setup_ubuntu.sh`, activate
`.venv`, then run `bash scripts/stress.sh t1` through `t5`. Each test uses exactly
three independent restarts and the parameters in PUBLIC_TESTS.md. The runner
retains instructor CSV/JSON, logs, memory samples, source/settings and per-metric
medians. Percentiles are medians of per-run percentiles, not pooled percentiles.

T5 requires `sudo -n tc` permission, or run inside a private user/network namespace:

```sh
unshare --user --map-root-user --net bash -c 'ip link set lo up; PYTHON=.venv/bin/python bash scripts/stress.sh t5'
```

T5 adds 120 ms ±30 ms delay and 3% loss on loopback, affecting both source and
client traffic. Cleanup removes only the qdisc added by this run. Existing shaping
is rejected. Do not run other benchmarks in the same namespace concurrently.
`LR_OUTPUT` chooses a new output directory; evidence is never overwritten.

The existing CI's 99.5% completeness and 99% coverage checks are team development
criteria. The PDF specifies hidden-mark caps below 99% and 95% completeness; it
does not prescribe the removed H2 latency or H3 freshness thresholds. Assess actual
completeness, duplicate/stale errors, freshness, tail age, recovery and memory.
Use `monitor_server.py` manually if diagnosing one run outside the wrapper.
