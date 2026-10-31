/*
 * Working but deliberately naive LiveRecall browser starter.
 *
 * Provided mechanical behavior:
 *   - opens a WebSocket
 *   - sends CLIENT_HELLO
 *   - visibly appends every received CAPTION_UPDATE
 *   - displays whether an update is provisional/final
 *
 * Graded TODOs:
 *   - replace revisions rather than appending duplicates
 *   - maintain >=60 s of finalized local state
 *   - implement 30 s default recall + 15/30/60 s views
 *   - automatic reconnect + correct resume state
 *   - HISTORY merge/deduplication
 *   - usable final UI
 */
import { CaptionStore } from './store.js';
import { createHistory } from './history.js';

const WS_URL = "ws://127.0.0.1:8765";
const statusEl = document.getElementById("status");
const liveEl = document.getElementById("live");
const recallEl = document.getElementById("recall");

const store = new CaptionStore();
const history = createHistory();
const segmentRows = {}; // Track DOM elements by segment ID
const recoveredSegments = new Set(); // Bounded to the local history item cap.
const MAX_RECOVERED_MARKS = 512;
let recallSeconds = 30;
let ws;

function numericClientId() {
  const key = "liverecall-client-id";
  let value = sessionStorage.getItem(key);
  if (!value) {
    value = String(Math.floor(100000 + Math.random() * 900000));
    sessionStorage.setItem(key, value);
  }
  return Number(value);
}

function renderRecall() {
    const items = history.recall(recallSeconds);
    if (!items.length) {
        recallEl.textContent = "No finalized captions in this window.";
        return;
    }

    const now = Date.now() / 1000;
    recallEl.textContent = items.map((caption) => {
        const age = Math.max(0, Math.round(now - caption.source_ts));
        const label = recoveredSegments.has(caption.segment) ? "RECOVERED" : "FINAL";
        return `[${label}] ${age}s ago · segment ${caption.segment}: ${caption.text}`;
    }).join("\n");
}

function markRecovered(segment) {
    if (recoveredSegments.size >= MAX_RECOVERED_MARKS && !recoveredSegments.has(segment)) {
        recoveredSegments.delete(recoveredSegments.values().next().value);
    }
    recoveredSegments.add(segment);
}

function handleCaptionUpdate(msg, recovered = false) {
    // 1. Pass through the client-side state firewall to ensure it's a valid caption (i.e. not another caption after segement was "final" and strictly newer)
    const { accepted } = store.apply(msg);
    if (!accepted) return;

    if (msg.final && !recovered) {
        history.addFinal(msg);
    }

    // 2. Format the text visually
    const stateLabel = msg.final ? "FINAL" : "PROVISIONAL";
    const text = `[${stateLabel}] segment ${msg.segment} rev ${msg.revision}: ${msg.text}`;
    
    // 3. In-Place DOM Mutation
    let row = segmentRows[msg.segment];
    if (!row) {
        row = document.createElement("div");
        liveEl.appendChild(row);
        segmentRows[msg.segment] = row; // Cache the DOM node
    }

    row.textContent = text;
    
    // 4. Visual distinction requirement (from spec)
    if (msg.final) {
        row.style.color = "black";
        row.style.fontStyle = "normal";
        row.style.fontWeight = "bold";
    } else {
        row.style.color = "gray";
        row.style.fontStyle = "italic";
        row.style.fontWeight = "normal";
    }

    if (recovered || recoveredSegments.has(msg.segment)) {
        row.dataset.recovered = "true";
        row.style.backgroundColor = "#fff7cc";
    }
    
    liveEl.scrollTop = liveEl.scrollHeight;
    renderRecall();
}

function connect() {
  statusEl.textContent = "connecting";
  ws = new WebSocket(WS_URL);

  ws.addEventListener("open", () => {
    statusEl.textContent = "connected";
    const resumeState = store.latestFinal();
    ws.send(JSON.stringify({
      type: "CLIENT_HELLO",
      client_id: numericClientId(),
      session: "L1",
      last_segment: resumeState.segment,
      last_revision: resumeState.revision,
      history_seconds: 30 // default is 30
    }));
  });

  ws.addEventListener("message", (event) => {
    const msg = JSON.parse(event.data);
    if (msg.type === "CAPTION_UPDATE") {
      handleCaptionUpdate(msg);
    } else if (msg.type === "HISTORY") {
      const items = Array.isArray(msg.items)
        ? msg.items.filter((item) => item && item.final === true)
        : [];
      const recovered = history.mergeHistory(items);
      for (const caption of recovered) {
        markRecovered(caption.segment);
        handleCaptionUpdate(caption, true);
      }
      renderRecall();
    }
  });

  ws.addEventListener("close", () => {
    statusEl.textContent = "disconnected";
    // TODO: automatic reconnect after a short delay, using finalized resume state.
    // Damien to implement through connection.js
  });

  ws.addEventListener("error", () => {
    statusEl.textContent = "connection error";
  });
}

for (const button of document.querySelectorAll("button[data-seconds]")) {
  button.addEventListener("click", () => {
    recallSeconds = Number(button.dataset.seconds);
    renderRecall();
  });
}

renderRecall();
connect();
