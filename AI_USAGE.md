# AI / Coding-Assistant Usage

## Tools used

| Member | Tool | Used for |
|---|---|---|
| Don | Gemini | Drafting the JSON validation in `protocol.py`, the revision rules in `state.py`, the wiring in `solution_server.py`, and the pipeline for ASR. |
| Dylan | OpenAI Codex | Drafting and optimising the data structures in `history.py` (time and segment indexes, bounded HISTORY cache), and drafting `client/history.js` for client-side recall state. |
| Damian | Claude Code | Drafting the semantic mailbox, the hub and its ping-based lag detector, the browser connection manager, and their tests. Also used to analyse the slow-reader measurements behind the overload policy. |
| Leonard | OpenAI Codex | Runtime configuration and overflow policy, the browser shell, the Ubuntu T1–T5 wrapper, the before/after comparison, preparing experiment evidence and figures, and the H3/H8 congestion follow-up (analysing client traces, drafting the recovery changes and regression tests, running the Ubuntu experiments). |

Every AI-generated change was reviewed by its author, covered by tests, and merged through a pull request reviewed by another member.

## One useful suggestion

Claude Code suggested using WebSocket ping/pong as an acknowledgement to detect slow readers. A client answers a ping only after reading every frame sent before it, so a late pong shows that the client is behind, even when the server's own send buffer never fills.

We needed this because the obvious design, reacting only when `send()` blocks, never triggered for slow readers. Their backlog sits in the client's kernel receive buffer and its 16-frame library queue, where the server cannot see it.

We verified the suggestion with the unmodified harness, taking medians of 3 runs. On a scenario with 300 clients, 30% of them reading one message per second, final completeness rose from 77.5% on the starter server to 100% with the ping-based policy. Normal-client P95 caption age fell from 7.0 s to 39 ms. The controlled T3 comparison in the report (bounded FIFO 95.13% vs semantic 100.00% completeness) confirms the effect on the public workload.

## One suggestion that was wrong, inefficient, or required modification

While wiring the source loop to the hub in `solution_server.py`, Gemini generated:

```python
if STATE.apply(cap):
    await hub.publish(cap)
```

This was wrong for our design. Awaiting the publish step inside the source loop makes caption ingestion wait for client delivery, which recreates the starter server's bottleneck: one slow client delays every other client. We kept `Hub.publish()` synchronous. It only places the pre-encoded caption in each client's mailbox and wakes that client's own writer task, so the call returns without touching any socket:

```python
if STATE.apply(cap):
    ...
    HUB.publish(cap)  # synchronous; never awaits a socket
```

Other corrections: for the congestion follow-up, Leonard rejected Codex's suggestions to apply a small frame window to every client and to change `TCP_NODELAY` globally, because diagnostic runs got worse with both. Dylan rejected a Codex proposal to rewrite `app.js` and `history.js` as IIFE scripts, keeping them as ES modules like the rest of the client. An AI-written `inf // 30` produced `nan` and crashed a writer task, and time-only lag detection let about 80 frames reach a slow reader during a 10× burst; adding a 32-frame acknowledgement window raised completeness from 90.5% to 99.7%.

## Responsibility statement

We understand that the team remains responsible for the submitted code, experimental results, and claims, and that every member may be asked to explain or modify relevant code during the viva.
