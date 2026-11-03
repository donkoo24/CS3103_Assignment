# Team 11 - LiveRecall

## Team members

- Damian Liew Cho Xiang / A0302976X / hub and per-client writer tasks, semantic mailbox, slow-reader lag detection and overload policy, browser connection/reconnect
- Dylan Tang Zhi Yew / A0307803J / bounded final history, resume and late-join handshake, HISTORY cache, browser recall history
- Don Koo / A0307817Y / protocol parsing, revision state, server wiring, browser caption store, ASR
- Leonard Lim Jia Hui / A0307813H / runtime configuration and overflow policy, startup scaling, FIFO baseline, browser shell/UI, Ubuntu test tooling

## Ubuntu setup

From a fresh Ubuntu 22.04 environment, in the repository root:

```bash
sudo apt-get update
sudo apt-get install -y python3 python3-venv python3-pip iproute2
```

`iproute2` provides `tc`, which is needed only for T5. Alternatively, `bash scripts/setup_ubuntu.sh` runs the setup and install steps and then `submission_check.py`.

## Install

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

The server needs only `websockets` (pinned in `requirements.txt`). It uses no model, database or Internet access.

For development tests (optional): `pip install -r requirements-dev.txt`, then run `python -m pytest -q`, `node --test client/tests/*.test.*` (Node 20+) and `python submission_check.py`.

## Required server

```bash
python solution_server.py --port 8765
```

The server binds to `0.0.0.0` and is ready within about a second.

## Browser client

The client is static HTML/JavaScript in `client/`, with no build step.

1. Start the server (above).
2. In a second terminal, serve the client:

   ```bash
   python -m http.server 8000 --directory client
   ```

3. Open `http://127.0.0.1:8000`. From another machine, use `http://<VM-IP>:8000`.

By default the client connects to the WebSocket server on port 8765 of the host that served the page (for `http://127.0.0.1:8000`, that is `ws://127.0.0.1:8765`). To use a different server, add a `server` query parameter to the page URL, for example `http://127.0.0.1:8000/?server=ws://127.0.0.1:9000`.

## Public deterministic tests

Each test runs three independent experiments, restarting the server each time; report the median.

| Test | Workload | Command |
|---|---|---|
| T1 | 20 clients, 20 s | `python run_demo.py --clients 20 --duration 20 --runs 3 --output-stem t1` |
| T2 | 100 clients, 40 s | `python run_demo.py --clients 100 --duration 40 --runs 3 --output-stem t2` |
| T3 | 100 clients, 60 s, 10% slow readers at 500 ms | `python run_demo.py --clients 100 --duration 60 --runs 3 --slow-percent 10 --slow-ms 500 --output-stem t3` |
| T4 | 100 clients, 60 s, 20% disconnect at 15 s for 5 s | `python run_demo.py --clients 100 --duration 60 --runs 3 --disconnect-percent 20 --disconnect-at 15 --disconnect-seconds 5 --output-stem t4` |
| T5 | T2 with 120 ± 30 ms delay and 3% loss on loopback | see below |

T5 (Ubuntu only):

```bash
sudo ./network_profiles/delay_loss.sh lo
python run_demo.py --clients 100 --duration 40 --runs 3 --output-stem t5
sudo ./network_profiles/reset.sh lo
```

The reported results were produced with `scripts/stress.sh`, which wraps the same commands. It also records metadata, server memory and settings, and removes the netem shaping on exit:

```bash
bash scripts/stress.sh t1        # likewise t2, t3, t4
unshare --user --map-root-user --net bash -c \
  'ip link set lo up; PYTHON=venv/bin/python bash scripts/stress.sh t5'
```

Running T5 inside `unshare` applies real `tc/netem` shaping in a private network namespace, without changing the VM's own network.

Before/after comparison (T3; only the delivery policy changes):

```bash
LR_WRITE_LIMIT=4096 LR_COMPRESSION=none LR_DELIVERY=fifo LR_OUTPUT=experiments/before-t3 bash scripts/stress.sh t3
LR_WRITE_LIMIT=4096 LR_COMPRESSION=none LR_DELIVERY=semantic LR_OUTPUT=experiments/after-t3  bash scripts/stress.sh t3
```

The historical public campaign is in `experiments/public/`. Current congestion
settings and limitations are in `docs/congestion-recovery.md`. The full T1–T5
and team-plan H1–H8 rerun is summarized in `experiments/20261102/`.
It delivered all finals in every run except H8; H8 remains imperfect.
The recorded FIFO comparison uses its original revision, 4096-byte writes and
compression off. Current defaults use 1024-byte writes and deflate.

## Mandatory deterministic application demo

No ASR or speech recognition is needed. Use three terminals:

```bash
# Terminal 1: server
python solution_server.py --port 8765

# Terminal 2: browser client files
python -m http.server 8000 --directory client

# Terminal 3: deterministic source (long mode, so 60 s recall is meaningful)
python caption_source.py --duration 120
```

Open `http://127.0.0.1:8000` in **two browser windows side by side**. Use separate windows rather than tabs: browsers pause painting in background tabs.

1. **Revision replacement.** Watch a segment labelled `[PROVISIONAL] … Updating…` (grey italics) grow in place and turn into `[FINAL]` on the same row. No duplicate line appears.
2. **What did I miss?** The right-hand panel shows the last 30 s by default. Click **15 s** and **60 s** to switch windows. It is served from browser memory, with no server request.
3. **Reconnect and recovery.** In one window, open DevTools → Network → set throttling to **Offline** for about 10 s. The status shows Offline/Reconnecting and the captions stop. Set it back to **No throttling**. The client reconnects automatically, and the missed finals appear tagged **Recovered**, followed by live captions, with no gap and no duplicate.
4. **Late join.** About a minute into the source run, open a third window at `http://127.0.0.1:8000`. It immediately shows recent finals tagged **Recovered** (from `HISTORY`), then continues live.

## Design notes

- **Revision/deduplication state.** The server (`liverecall/state.py`) and the browser (`client/store.js`) apply the same rule. An update is accepted only if its segment is new, or its revision is strictly newer and the segment is not yet final. Finals are permanent. Both sides prune old segments and reject anything below a monotonic floor, so an evicted segment cannot reappear.
- **Bounded server history.** `liverecall/history.py` keeps finals only: the last 90 s, at most 512. Encoded `HISTORY` replies are cached (LRU, 64 entries, 8 MiB) and the cache is cleared on every new final, so reconnect bursts share one reply.
- **Reconnect/late-join recovery.**
  - `CLIENT_HELLO` carries the client's last *finalized* segment and revision.
  - A returning client receives every retained final after that point, using the full 60 s window. A new client receives the last `history_seconds`, up to 60.
  - The current provisional is never replayed, because the client may already hold it.
  - The `HISTORY` snapshot and hub registration happen in one synchronous step, so no caption falls between them.
  - The browser reconnects with capped exponential backoff and jitter (0.5 s rising to 5 s).
- **Per-client buffering/backpressure policy.**
  - `Hub.publish()` is synchronous: it only places the pre-encoded caption in each client's mailbox (`liverecall/mailbox.py`). Each client has its own writer task, so a slow client delays only itself.
  - The mailbox keeps finals in order and never drops them. Each unfinished segment has a single provisional slot, which a newer revision overwrites.
  - TCP backpressure cannot detect a slow reader: its backlog sits in the client's own buffers. The writer therefore uses WebSocket ping/pong as an acknowledgement. Healthy clients use a 32-frame window; detected lag reduces it to one. A bounded final flush after source silence can use one extra batch until acknowledged progress.
- **Overload behavior and trade-offs.**
  - A lagging client holds provisionals while pending finals coalesce into batches. Normal revision delivery resumes after the recovery hold.
  - A client slower than the finals rate gets its finals batched.
  - Per-socket send buffers are kept small (1 KiB asyncio and 1 KiB `TCP_NOTSENT_LOWAT` (a notification threshold rather than a hard byte cap)), so under constrained bandwidth the backlog stays in the mailbox, where it can still be coalesced.
  - A client that exceeds 512 pending finals or 1,024 pending updates is closed with 1013 and resumes through `HISTORY`.
  - **Trade-off:** batching improves completeness while reducing intermediate revisions; recovered finals can be older than 500 ms. Combined H8 impairment still missed some finals before the deadline.
  - See `report.pdf` for the measurements.

## Optional ASR bonus

Attempted. `bonus_asr/` streams a recorded lecture (`bonus_asr/my_lecture.mp4`) through a local Vosk speech recogniser and feeds the captions into the same `solution_server.py` and browser client, using the standard LiveRecall protocol. Its dependencies are isolated in `bonus_asr/requirements-asr.txt` and a separate virtual environment, so the mandatory server path above does not need them.

```bash
./bonus_asr/run_bonus_demo.sh
```

The script installs the ASR environment and model on first run (about 40 MB, needs Internet access), then starts the server. Serve the browser client as above, open `http://127.0.0.1:8000`, and press Enter in the script's terminal to start the lecture. See `bonus_asr/README.md` for the design, setup details and limitations.