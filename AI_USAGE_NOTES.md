# AI usage notes (raw log; compiled into AI_USAGE.md before submission)

| PR / task | Tool | Used for | Rejected or corrected |
|---|---|---|---|
| DA-2 `feat/semantic-mailbox` | Claude Code | Drafting `Mailbox` and its randomised invariant tests | Rejected the obvious design of reacting only to transport backpressure: measured on T3 that slow readers' backlog sits in the client's kernel buffer + 16-frame library queue, which the server's send buffer never sees (motivates the ping-probe lag detection in DA-1). |
| DA-1 `feat/hub-writers` | Claude Code | Drafting the hub, the ping-probe lag detector, and the fake-socket + real-socket tests | Two AI-written bugs caught by tests: `inf // 30` is `nan` so the first lag event crashed the writer silently (fixed + writer now logs and closes 1011 on any bug); lag was only detected if the writer happened to run while the probe was overdue (now also judged when the pong arrives). Also rejected ruff's UP041 autofix: on Python 3.10 `asyncio.TimeoutError` is not the builtin `TimeoutError`. | Also: the first AI design detected lag only by probe *time*; a 10x burst test showed slow readers receiving ~80 frames before detection, so we added a pong-acknowledged frame window (completeness 90.5% -> 99.7% under bursts).

| LE-2 `feat/policy-config` | OpenAI Codex | I used AI to assist with validated settings, bounded overflow handling, FIFO comparison and startup limits. | I removed my additional probe-timing knob and reverted the unproven multi-setting tuning choice; the retained defaults match the controlled comparison. |

| LE-4 `feat/sweeps-before-after` | OpenAI Codex | I used AI to assist with a controlled T3 comparison with semantic delivery disabled/enabled. | I reduced the earlier matrices to one comparison required by the PDF and removed the snapshot, resume and sweep framework. |

| LE-1 `feat/vm-and-stress` | OpenAI Codex | I used AI to assist with the Ubuntu setup and T1–T5 wrapper, provenance and cleanup checks. | I removed the unnecessary Node installer, hidden-profile framework and extra performance gates after comparing the plan with the PDF. |

| LE-3 `feat/client-shell` | OpenAI Codex | I used AI to assist with the layout, bounded rendering, scroll controls, status and team-module adapters. | I adapted Don's merged ES module CaptionStore in the separate shell PR #13 while keeping caption semantics in its owner's module. Don's store and Damian's connection manager are merged. Dylan's browser history is in PR #18 and Leonard's shell PR #13 imports it. I used AI to assist with integration review; a headless two-tab smoke passed, while the required demo video remains pending. |

| LE-5 `feat/exp-network-report` | OpenAI Codex | I used AI to help trim the experiment archive, run T1–T5 three times, preserve one comparison, and prepare the report and figures. | I corrected the overextended experiment plan against the PDF, removed unsupported default/threshold claims, and kept peer integration, video and contribution agreement explicitly pending. |
