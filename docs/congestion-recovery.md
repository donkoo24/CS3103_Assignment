# Congestion and combined-impairment recovery

The final-flush follow-up below achieved 100% completeness in three H3
1 Mbit/s repeats; H8 remains imperfect.

The team-plan H3 and H8 profiles exposed delivery limits. These are local
stress scenarios, not the instructor's undisclosed hidden tests. Source,
load-client and analyser measurement logic were not changed.

## Findings and changes

- A congested connection could establish a large minimum ping RTT. Multiplying
  that by three allowed seconds of queueing before the Hub reacted. Cap the
  lag allowance at one second, including connections congested from startup.
- Keep the healthy 32-frame window, but allow only one unacknowledged frame
  after lag is detected. Coalesce provisional updates in the mailbox while
  the connection recovers and send pending finals together. Healthy connections
  still receive every revision; the normal window and newest pending provisional
  resume after the recovery hold.
- The former `stuck / 12` estimate assumed a particular client queue drain.
  Loss and partially filled queues violate that assumption. Use a conservative
  1.5-second batch interval only after a large delay relative to the best RTT
  (over two seconds and eight times the best RTT), and retain it during that
  recovery hold. This heuristic does not measure application consumption.
- Enable negotiated deflate by default and lower the write high-water mark to
  1 KiB. Lower Linux TCP_NOTSENT_LOWAT to 1 KiB as well; it is a notification
  threshold, not a hard limit on all kernel buffering. Existing environment
  overrides remain available.
- Briefly coalesce a caption and its immediate ping with Linux TCP_CORK. Flush
  on scope exit and at the next event-loop yield so a blocked send cannot leave
  the socket corked. Unsupported platforms use the existing write path.

The implementation plan was to diagnose the saved client traces, try targeted
changes, add regressions for lag detection and recovery, then validate one fixed
Git revision. Intermediate diagnostic trials remain local; the committed evidence
is the baseline campaign and the final three-run validation. Several settings
changed together, so the comparison measures the combined change, not an isolated
contribution from any single setting.

## Initial three-run validation (d38cd28)

`experiments/congestion-recovery/` preserves per-run JSON, compressed CSV/logs,
network settings, Git revisions, and uncompressed-file SHA256 hashes. The original
server code matches the current main parent; later main changes affected the UI
and documentation. Each final profile restarted the server three times on Ubuntu
22.04.5, Python 3.10.12, websockets 16.1.1, using the same workload parameters and
seed 3103. Each shaped profile ran inside a private user/network namespace.

| Profile | Before final completeness | After final completeness | Before fresh finals | After fresh finals |
|---|---:|---:|---:|---:|
| H3, 1 Mbit/s | 84.03%, 79.34% completed attempts; another attempt aborted | 99.99% median | 0% in completed attempts | 50.11% median |
| H3, 2 Mbit/s | 99.99% median | 100% median | 0.62% median | 69.38% median |
| H8 | 98.30% median | 99.84% median | 54.29% median | 52.95% median |

All nine final runs exceeded the team's internal 99.5% completeness target and
had zero duplicate, stale, invalid-history and connection-error events. The
1 Mbit/s completeness values were 99.912%, 99.993%, 99.986%; H8 values were
99.838%, 99.789%, 99.969%. These do not establish perfect delivery in every run.
The baseline 1 Mbit/s profile has no valid median because run 2 aborted on an
opening-handshake timeout; its completed attempts had 25 and 22 connection errors.

H8's median overall P95 age decreased from 7.90 s to 4.60 s, while normal-reader
P95 rose from 658 ms to 696 ms and the fresh-final ratio fell. The analyser's live
latency percentiles exclude HISTORY items, so a lower live percentile alone does
not prove faster final recovery. Its reconnect timing also includes later HISTORY
messages on a reconnected socket, rather than only the initial reply. Inspect the
raw events alongside completeness and freshness.

## Reproduction

Use the same code/settings for all three restarts. Install runtime dependencies
and activate the repository virtual environment first. For H3 at 1 Mbit/s:

```sh
unshare --user --map-root-user --net bash -c '
  ip link set lo up
  trap "tc qdisc del dev lo root" EXIT
  tc qdisc add dev lo root tbf rate 1mbit burst 32kbit latency 400ms
  python run_demo.py --clients 300 --duration 40 --runs 3 --quiet-server --output-stem h3_1mbit
'
```

Use `rate 2mbit` for the other H3 profile. For H8:

```sh
unshare --user --map-root-user --net bash -c '
  ip link set lo up
  trap "tc qdisc del dev lo root" EXIT
  tc qdisc add dev lo root netem delay 120ms 30ms distribution normal loss 3%
  python run_demo.py --clients 300 --duration 60 --runs 3 --quiet-server \
    --slow-percent 30 --slow-ms 1000 --disconnect-percent 50 \
    --disconnect-at 15 --disconnect-seconds 10 --output-stem h8
'
```

The baseline used 4096-byte writes, compression off and the original Hub. The
revised defaults use 1024-byte writes and deflate. The shared loopback cap applies
to source, client and control traffic. Netem loss randomness is not fixed, and
these sequential campaigns are not identical packet-loss replays.

## Remaining limits

Tight shared caps still cause delayed and occasionally missing finals at test
end. Compression adds CPU and memory cost. Reader classification is heuristic,
and a long recovery hold can suppress intermediate revisions after impairment
improves. Explicit application acknowledgements and adaptive recovery pacing are
still useful future work. The old `experiments/public/` results describe their
recorded revision and settings; they are not measurements of these new defaults.

## Public regression checks

Single independent T1–T5 runs on the fixed code all reached 100% final
completeness and zero duplicate, stale, invalid-history or connection-error
events. T1/T2 retained 100% revision coverage. T3's normal readers received
all 20,520 expected revisions. T2 P95 was 9.91 ms; T3 normal-reader P95 was
9.08 ms. T4 recovery P95 was 6.70 ms. T5 fresh finals were 90.71%. These
are regression checks, not replacement three-run public report medians.
The Python suite and browser suite passed, and the submission startup check
passed. Protected instructor source/test files were unchanged.

## Final-flush follow-up (f40770e)

A final batch could wait behind a late pong after the source stopped offering
updates. The writer also had no timer to revisit that condition. Record the
last offer time and wake after 0.5 seconds of source silence. Permit one final
batch beyond the usual acknowledgement window; further batches must wait for
acknowledged progress. Ordinary reader pacing and normal revision delivery stay
in place. This adds at most one reserved batch to the existing frame window.
It does not depend on SOURCE_DONE, source disconnection, client count or test duration.

Three independent server restarts of the unchanged workloads produced:

| Profile | Run 1 final deliveries | Run 2 final deliveries | Run 3 final deliveries |
|---|---:|---:|---:|
| H3, 1 Mbit/s | 14,700/14,700 | 14,700/14,700 | 14,700/14,700 |
| H8 | 22,774/22,800 | 22,707/22,800 | 22,776/22,800 |

All six runs had zero duplicate, stale, invalid-history and connection-error
events. H3 fresh finals were 58.54% median: 100% completeness does not establish
100% freshness. H8 completeness was 99.89% median, with a 99.59% worst run.
Its spread was wider than the initial validation, whose worst run was 99.79%;
the random loss patterns differ, so these small changes do not establish a
consistent H8 improvement. Perfect H8 completeness was not achieved.

The committed `final-flush/` evidence contains every run, metadata, compressed
traces/logs and hashes. Separate single-run T2, T3, T5 and 2 Mbit/s H3 regressions
all retained 100% final completeness with zero recorded correctness errors.
T2 retained every revision; all normal readers received every revision in T3.
The Python suite passed 257 tests, including bounded flush and timer wake tests.

Additional diagnostic changes to reader holds, batching schedules and source
completion handling did not reliably eliminate H8 misses. They were discarded;
the production change is the small bounded flush. The instructor source,
clients, analyser, network parameters, run counts and test deadlines were unchanged.
These local results are not a guarantee for the instructor's undisclosed workload.
