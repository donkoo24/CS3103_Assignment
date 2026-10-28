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

const WS_URL = "ws://127.0.0.1:8765";
const statusEl = document.getElementById("status");
const liveEl = document.getElementById("live");
const recallEl = document.getElementById("recall");

const store = new CaptionStore();
const segmentRows = {}; // Track DOM elements by segment ID
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

function handleCaptionUpdate(msg) {
    // 1. Pass through the client-side state firewall to ensure it's a valid caption (i.e. not another caption after segement was "final" and strictly newer)
    const { accepted } = store.apply(msg);
    if (!accepted) return;

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
    
    liveEl.scrollTop = liveEl.scrollHeight;
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
      console.log(`HISTORY with ${msg.items?.length ?? 0} item(s)`, msg);
      // TODO: merge history without stale/duplicate final captions.
      // Dylan to implement the History merge
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
    const seconds = Number(button.dataset.seconds);
    recallEl.textContent = `TODO: show finalized captions from the previous ${seconds} seconds using local state.`;
  });
}

connect();
