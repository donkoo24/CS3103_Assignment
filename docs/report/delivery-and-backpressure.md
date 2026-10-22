# Delivery & backpressure (report section draft: Damian)

> Draft for `report.pdf`. Numbers are single local runs (macOS) from the PR
> evidence; replace them with 3-run Ubuntu medians from `run_demo.py` and
> `scripts/burst_run.py` before submission.

## Architecture

`Hub.publish()` runs inside the source handler and is **synchronous**: it only
pushes the pre-encoded caption into each client's `Mailbox` and wakes that
client's writer task. Every client has exactly one writer task (`Session`), so
a slow socket can delay only itself. In the starter, the source loop awaited
`gather()` over all sends, so one slow group stalled everyone (H2: normal-client
P95 = 7.0 s).

**Mailbox** (`liverecall/mailbox.py`):
- finals are queued in order and never dropped;
- each unfinished segment has one provisional slot, which a newer revision
  overwrites (coalescing);
- a final removes its pending provisional, and later provisionals for that
  segment are ignored, so no stale update is ever sent;
- delivery order is finals first, then the newest revision of the oldest
  unfinished segment.

## Why transport backpressure is not enough

TCP/WebSocket backpressure reaches the server only when the server's own send
buffer fills. A slow *reader* never fills it. Its backlog sits in its kernel
receive buffer and in the `websockets` client's frame queue, which pauses
reading at 16 frames and resumes at 4. At caption bitrates (~170 B/frame) that
holds minutes of stale captions.

We measured this on the starter (T3: 10% of readers at 500 ms per message):
- slow-client P95 was **18.7 s**;
- final completeness was **95.3%**, below the 99% correctness gate;
- the server never saw any backpressure.

## Lag detection: a ping as an acknowledgement

Each writer keeps one WebSocket ping in flight. A peer processes the ping only
after every frame queued in front of it, so:
- **a pong acknowledges every earlier frame.** At most `window` = 32 frames
  may be unacknowledged; a probe goes out every 1 s or every 16 frames. This
  bounds a slow reader's backlog however fast the source bursts.
- **an overdue pong** (> max(1 s, 3 × min RTT)) **is a strike**: the client is
  behind.

## Overload policy (per client)

| State | Behaviour | Why |
|---|---|---|
| Healthy | every revision, immediately | full coverage when not overloaded |
| Stuck (pong overdue or window full) | send nothing; finals queue, provisionals coalesce | anything sent would only queue behind the backlog |
| Caught up to the probe | all held finals in **one `HISTORY` frame** | one read instead of one per final |
| Degraded (hold = 10 × time stuck, ×2 per repeated strike) | provisionals ≤ 1 frame/s; finals one per frame, or **batched** if the client reads slower than finals arrive | lets the client-side backlog drain instead of topping it up |

**Read-rate estimate.** A saturated reader answers the probe only after
draining its queue from 16 to 4 frames, so its time per read ≈ stuck ÷ 12. If
`read_time × finals_rate ≥ 1`, its finals are batched, one frame per
1.5 read times.
- A 500 ms reader keeps individual (fresher) finals.
- A 1000 ms reader, which cannot keep up one final per frame, is batched and
  stays complete.
- A congested-but-fast client (stuck for only about an RTT) is not batched.

**Bandwidth.** Each connection caps asyncio's write buffer (4 KiB) and the
kernel's unsent bytes (`TCP_NOTSENT_LOWAT`, 16 KiB). When the link is the
bottleneck, `send()` blocks early and the backlog forms in the mailbox, where
obsolete provisionals coalesce, instead of as stale frames inside buffers we
cannot edit.

**Bounds.**
- Pending finals per client ≤ 512. Exceeding that closes the client with 1013
  so that it resumes via HISTORY.
- One provisional per unfinished segment.
- In-flight frames ≤ 32.

## Results (single local runs; to be replaced by Ubuntu medians)

| Scenario | Starter: completeness / P95 / normal-client P95 | Ours: completeness / P95 / normal-client P95 |
|---|---|---|
| T2: 100 clients | 100% / 21 ms / 21 ms | 100% / 31 ms / 31 ms (coverage 100%) |
| T3: 10% slow @ 500 ms, 60 s | 95.31% / 1.80 s / 19 ms | **100%** / **27 ms** / 25 ms |
| H2: 30% slow @ 1000 ms, 60 s | 77.50% / 21.9 s / 7.0 s | **100%** / **108 ms** / 45 ms |
| H7: 10× revision burst, 10% slow, 40 s | 90.53% / 11 ms / 11 ms | **99.74%** / 12 ms / 11 ms |

0 duplicates and 0 stale updates in every run. T3 slow-client P50 fell from
9.7 s to 0.6 s.

## Trade-offs and limitations

- **Detection floor.** A slow reader is detectable only once its library queue
  is full, so it is always about 16 frames (≈ 8 s at 500 ms) behind before the
  policy reacts. This is the residual slow-client P95. Removing it would need
  an application-level acknowledgement from the client.
- **The read-rate estimate models the reference client** (`websockets`
  watermarks 16/4, configurable as `client_queue_band`). Browsers dispatch
  frames immediately, so in practice they only get stuck on network
  congestion, where the estimate correctly declines to batch.
- **Mid-stream `HISTORY`** keeps the spec's meaning ("finalized captions you
  are missing, oldest first"), but it is a protocol extension the browser
  client must accept at any time.
- **A long hold** keeps a recovered slow reader on reduced provisionals for up
  to minutes. Finals stay fresh; only intermediate revisions are skipped.
