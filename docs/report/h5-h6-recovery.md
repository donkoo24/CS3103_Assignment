# H5/H6 Recovery and Late-Join Results

## Method

The experiments were run against the assembled server with the semantic
delivery policy enabled. Each scenario used three independent server restarts;
the reported central values are medians of the three per-run summaries rather
than pooled samples. Raw CSV logs, analyser JSON, metadata, and run logs are
retained in `experiments/public/h5/` and `experiments/public/h6/`.

The recorded runtime used Python 3.14.8, websockets 16.1.1, a 4096-byte write
limit, a 16-frame WebSocket queue, a 512-final pending cap, semantic delivery,
and a listen backlog of 4096. No network impairment was applied.

## Results

| Scenario | Workload | Recovery P50 | Recovery P95 | Recovered HISTORY items | Final completeness |
|---|---|---:|---:|---:|---:|
| H5 disconnect storm | 300 clients; 50% disconnect for 10 s at the harness default of 30 s | 14.54 ms | 17.10 ms | 1,950 | 100.00% |
| H6 late joiners | 200 clients; 30% join 15 s late | 0.26 ms | 0.45 ms | 1,140 | 100.00% |

Across all six runs, duplicate messages, stale messages, non-final HISTORY
items, and connection errors were zero. H5 produced 450 successful connections
per run: 300 initial connections and 150 reconnects. H6 produced 200 initial
connections, including 60 late joiners.

### Per-run variation

| Scenario | Run | Recovery P50 | Recovery P95 | Completeness | Duplicates | Stale | Invalid HISTORY | Connection errors |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| H5 | 1 | 13.27 ms | 17.09 ms | 100.00% | 0 | 0 | 0 | 0 |
| H5 | 2 | 14.54 ms | 17.10 ms | 100.00% | 0 | 0 | 0 | 0 |
| H5 | 3 | 17.00 ms | 18.75 ms | 100.00% | 0 | 0 | 0 | 0 |
| H6 | 1 | 0.25 ms | 0.38 ms | 100.00% | 0 | 0 | 0 | 0 |
| H6 | 2 | 0.26 ms | 0.63 ms | 100.00% | 0 | 0 | 0 | 0 |
| H6 | 3 | 0.26 ms | 0.45 ms | 100.00% | 0 | 0 | 0 | 0 |

## Interpretation

H5 exercises recovery while half of the clients leave and reconnect during the
same source run. The server recovered 1,950 finalized captions without
duplicates and delivered every expected final to every client. The modest
17.10 ms median P95 recovery time indicates that reconnecting clients received
their HISTORY snapshot promptly even while 300 clients remained active.

H6 exercises the late-join path rather than reconnecting an existing session.
The 60 late clients received 1,140 finalized HISTORY items in total and then
continued receiving live updates. Its sub-millisecond median recovery latency
is expected because the late clients connect locally after the history has
already been constructed; the important correctness result is that all 15,200
expected finals were eventually represented, with no duplicate or provisional
HISTORY entries.

Both scenarios rely on the bounded finalized-caption history. HISTORY contains
final captions only, and the history window is bounded by the server’s 90-second
retention and 512-item count limits. For each client handshake, the server
constructs the HISTORY snapshot and registers the client with that snapshot as
the first outbound message without awaiting between those operations. This
prevents a caption update from falling between history selection and live
registration. The reconnect cursor excludes finalized captions already held by
the client, while a late joiner uses the requested recent context window.

These results establish recovery and late-join behavior for the recorded H5/H6
workloads only. They do not measure packet loss, bandwidth caps, slow readers,
or longer retention periods.
