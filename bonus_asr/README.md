# CS3103 LiveRecall - Bonus Feature: Real-Lecture ASR Integration

## 1. System Overview & Architecture

The bonus feature implements a real-time, streaming speech recognition ingestion pipeline that feeds live lecture captions directly into the **same** LiveRecall server (`solution_server.py`) and browser client (`client/index.html`) using the mandatory WebSocket protocol:

```
+---------------------------------------------------------------------------------------+
| BONUS ASR PIPELINE (bonus_asr/)                                                       |
|                                                                                       |
| [ bonus_asr/my_lecture.mp4 ] (Real 3-minute lecture video)                            |
|           |                                                                           |
|           v (Piped via standalone ffmpeg: 16 kHz, 16-bit Mono PCM at real-time rate)  |
|   Audio Ingestion Stream                                                              |
|           |                                                                           |
|           v (200 ms audio chunks)                                                     |
|   Vosk Streaming ASR Engine (Kaldi acoustic model in bonus_asr/model)                 |
|           |                                                                           |
|           +---> Partial Hypothesis  ---> [ final=false, rev=1..N-1 ]                  |
|           |                                       |                                   |
|           +---> Natural Speech Pause ---> [ final=true,  rev=N, segment++ ]           |
|                                                   |                                   |
|                                                   v                                   |
|                                        bonus_asr/asr_source.py                        |
+---------------------------------------------------|-----------------------------------+
                                                    | WebSocket (LiveRecall Protocol)
                                                    v
                                      +----------------------------+
                                      |   solution_server.py       | (ws://127.0.0.1:8765)
                                      +--------------+-------------+
                                                     | Broadcast
                                                     v
                                      +----------------------------+
                                      |   Browser Client (UI)      | (client/index.html)
                                      +----------------------------+
```

### Key Design Principles:
1. **Strict Dependency Isolation**: All ASR dependencies (`vosk`, `imageio-ffmpeg`) are maintained inside `bonus_asr/.venv-asr` and listed in `bonus_asr/requirements-asr.txt`. The root `requirements.txt` and mandatory evaluation path remain completely lightweight and untouched.
2. **Zero Modification to Core Server / Client**: The identical `solution_server.py` and `client/` code are used without modification.
3. **True Acoustic Speech-to-Text**: Audio is decoded directly from speech sound waves in real time. No text transcripts or pre-baked subtitles are used.
4. **Standalone & Self-Contained**: Uses an isolated virtual environment and bundled standalone `ffmpeg` binary, so no root privileges (`sudo`) or global system modifications are required.

---

## 2. Directory Contents

- `my_lecture.mp4`: Representative continuous 3-minute lecture video (MIT computer science lecture).
- `run_bonus_demo.sh`: One-command demonstration runner. Starts `solution_server.py`, guides you to open the browser client, and streams live captions from `my_lecture.mp4`.
- `asr_source.py`: Streaming caption source client implementing the LiveRecall WebSocket protocol (`SOURCE_HELLO`, `CAPTION_UPDATE`, `SOURCE_DONE`).
- `asr_engine.py`: Unified streaming ASR adapter supporting Vosk (Kaldi) and faster-whisper.
- `model/`: Compact English acoustic model directory (`vosk-model-small-en-us-0.15`, ~40 MB). *(Generated via `install_asr.sh`)*.
- `.venv-asr/`: Isolated virtual environment containing `vosk` and standalone `ffmpeg`. *(Generated via `install_asr.sh`)*.
- `requirements-asr.txt`: Isolated dependencies for the ASR environment.
- `install_asr.sh`: Automated installer script for setting up the ASR environment on any new device.

---

## 3. Setup

### Prerequisites
- Python 3.10 or higher
- Standard tools: `bash`, `python3-venv` (usually pre-installed or via `sudo apt install python3-venv`)
- Network access for initial 40MB model download

### Option A: One-Command Automated Setup (Recommended)
Run the setup script:
```bash
./bonus_asr/install_asr.sh
```
This script automatically:
1. Creates the isolated virtual environment at `bonus_asr/.venv-asr/`.
2. Installs `vosk` and `imageio-ffmpeg` (which provides a standalone `ffmpeg` without needing `sudo apt install ffmpeg`).
3. Downloads and extracts the compact Vosk English model into `bonus_asr/model/`.
4. Symlinks the standalone `ffmpeg` into `bonus_asr/.venv-asr/bin/ffmpeg`.

*(Note: Even if you forget to run `install_asr.sh`, running `./bonus_asr/run_bonus_demo.sh` will detect that the environment is missing and automatically bootstrap it for you).*

---

## 4. Running the 3-Minute Lecture Demo

To run the complete demonstration on any device:

```bash
./bonus_asr/run_bonus_demo.sh
```

### Demonstration Steps:
1. The script automatically launches `solution_server.py` on port 8765.
2. Open the student browser client in your browser:
   - Or via local HTTP server: `http://localhost:8000` (run `python3 -m http.server 8000 --directory client` in another tab).
3. In the terminal running `run_bonus_demo.sh`, press **[Enter]**.
4. **Live Visual Observations**:
   - **Provisional Revisions**: As the lecturer speaks, words appear immediately in italics and dynamically expand.
   - **Finalized Lines**: When the lecturer pauses between sentences, the caption turns solid/normal font, locking the segment into durable history.
   - **What Did I Miss?**: Click the `15 s`, `30 s`, or `60 s` buttons in the browser client to verify that recently spoken sentences are retrieved instantly from local client history.
   - **Late Join / Reconnect**: Open a new browser tab mid-lecture; the new client sends `CLIENT_HELLO` and recovers recent finalized sentences from server history.

---

## 5. Protocol Compatibility

`asr_source.py` conforms to existing LiveRecall specification:

1. **Source Handshake**:
   ```json
   {
     "type": "SOURCE_HELLO",
     "session": "L1"
   }
   ```
2. **Provisional Revisions (`final: false`)**:
   As the speaker vocalizes words within an utterance, partial hypotheses are emitted with monotonically increasing revisions:
   ```json
   {
     "type": "CAPTION_UPDATE",
     "session": "L1",
     "segment": 1,
     "revision": 3,
     "source_ts": 1762000000.123,
     "final": false,
     "text": "all right so welcome to the first lecture"
   }
   ```
3. **Finalized Segment (`final: true`)**:
   When the speaker pauses at a sentence boundary, the segment is committed with `final: true`. Older revisions can never overwrite it:
   ```json
   {
     "type": "CAPTION_UPDATE",
     "session": "L1",
     "segment": 1,
     "revision": 12,
     "source_ts": 1762000000.456,
     "final": true,
     "text": "all right so welcome to the first lecture of six one hundred l that's our new number"
   }
   ```
   The source then advances `segment = 2` and resets `revision = 0`.

---

## 6. Timing & Integration Limitations

### 1. Acoustic Latency vs Recognition Accuracy
- **Deterministic Source**: `caption_source.py` emits pre-scripted revisions at artificial intervals (e.g., every 100 ms) with zero acoustic latency.
- **Real ASR Reality**: Real-time ASR models require an acoustic context window (typically 200 ms to 500 ms of future audio frames, known as "right-context") to disambiguate phonemes and resolve word boundaries. In addition, neural beam-search decoding introduces computational processing latency. Consequently, there is an unavoidable **minimum physical delay of 300–600 ms** between when a speaker utters a phoneme and when the first provisional revision can be dispatched over the WebSocket.

### 2. Voice Activity Detection (VAD) & Sentence Boundary Ambiguity
- **The Segmentation Problem**: Live speech does not emit syntactic punctuation. The ASR pipeline relies on Voice Activity Detection (VAD) energy thresholds and acoustic pauses to determine when to commit a segment (`final: true`).
- **Failure Modes**:
  - *Premature Finalization*: A lecturer hesitating or pausing mid-sentence (e.g. *"TCP congestion control... [0.6s pause]... uses AIMD"*) causes the VAD to trigger `final: true` prematurely, splitting a single grammatical thought across two segments.
  - *Run-on Segments*: A rapid speaker who does not pause causes the segment buffer to grow indefinitely. In LiveRecall, this delays the finalization of durable state and prevents the history buffer from caching discrete historical sentences for "What did I miss?".
- **Mitigation**: A production system requires a hybrid endpointing heuristic combining VAD silence duration with language-model punctuation prediction.

### 3. Local Host Resource Contention
- **CPU & Memory Contention**: Running local neural inference (e.g., Vosk Kaldi) consumes substantial CPU/GPU capacity and memory bandwidth.
- **Impact on WebSocket Server**: If the ASR engine runs on the same Ubuntu evaluation host as `solution_server.py` and 100+ concurrent simulated WebSocket clients, the intensive matrix multiplications can starve the Python `asyncio` event loop. This leads to artificial event-loop latency spikes, inflating measured P95/P99 caption age in benchmarking tests. In a production deployment, the ASR ingestion tier must be decoupled from the WebSocket broadcast distribution tier across dedicated processes or host machines.
