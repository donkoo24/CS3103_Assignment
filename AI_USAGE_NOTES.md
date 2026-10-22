# AI usage notes (raw log; compiled into AI_USAGE.md before submission)

| PR / task | Tool | Used for | Rejected or corrected |
|---|---|---|---|
| DA-2 `feat/semantic-mailbox` | Claude Code | Drafting `Mailbox` and its randomised invariant tests | Rejected the obvious design of reacting only to transport backpressure: measured on T3 that slow readers' backlog sits in the client's kernel buffer + 16-frame library queue, which the server's send buffer never sees (motivates the ping-probe lag detection in DA-1). |

| DA-3 `feat/client-connection` | Claude Code | Drafting `client/connection.js` and its fake-socket / fake-clock Node tests | Corrected the suggested CI step `node --test client/tests/`: a directory argument fails on Node 22 (tests run as globs), so CI uses `client/tests/*.test.mjs`. Rejected resuming from the newest *provisional* seen: CLIENT_HELLO must carry the latest *finalized* state or HISTORY would skip finals. |
