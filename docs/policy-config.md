# Bounded delivery configuration

Defaults: semantic delivery, 4096-byte write limit, inbound WebSocket frame high-water mark 16, compression
off, 512 pending finals, backlog 4096. These match the retained controlled T3
comparison; they are not claimed optimal for every hidden workload. Startup tries
to raise the file-descriptor soft limit to the existing hard limit.

`LR_MAX_QUEUE` counts incoming WebSocket frames in the library and is a
flow-control high-water mark, not the outgoing caption backlog.
`LR_WRITE_LIMIT`, `LR_MAX_QUEUE`, `LR_FINALS_CAP` accept positive integers;
`LR_COMPRESSION=none|deflate` controls the bandwidth/CPU trade-off.
`LR_DELIVERY=semantic|fifo` disables semantic scheduling for the single before/after
experiment. FIFO preserves every queued revision in order and bypasses semantic
probes and batching. Production uses semantic delivery.

The semantic mailbox has at most 512 pending finals and the policy bounds total
pending entries at twice the configured cap; one additional frame may be in flight.
Overflow closes code 1013 so the reconnecting client can recover from bounded
final history. This is deliberate eviction, not silent loss of final captions.

This PR extends Damian's Hub and Don's server wiring, both now merged on
`main`. The startup `apply_startup_limits()` hook is applied to the real
`websockets.serve()` path.
The extra probe-interval knob and unsupported “best configuration” claims were
removed; the Hub's existing 1-second default remains unchanged.
