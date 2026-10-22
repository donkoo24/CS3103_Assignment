# AI usage notes (raw log; compiled into AI_USAGE.md before submission)

| PR / task | Tool | Used for | Rejected or corrected |
|---|---|---|---|
| DA-2 `feat/semantic-mailbox` | Claude Code | Drafting `Mailbox` and its randomised invariant tests | Rejected the obvious design of reacting only to transport backpressure: measured on T3 that slow readers' backlog sits in the client's kernel buffer + 16-frame library queue, which the server's send buffer never sees (motivates the ping-probe lag detection in DA-1). |
| DA-4 `feat/exp-slow-burst` | Claude Code | Drafting `scripts/burst_run.py` and the delivery report section | Measurement hygiene: stray server/load-generator processes from an earlier aborted run silently contaminated two benchmark runs (one showed 0% completeness); every run now starts by killing strays and asserting the port is free. |
