/* Leonard's shell. Caption semantics, recovery storage and transport are supplied
 * by the team modules; createShell also accepts explicit adapters for integration. */
(function (root) {
  "use strict";
  const MAX_ROWS = 300; // Live DOM, recall DOM and pending render map each <= 300.

  function serverURL(location) {
    const override = new URLSearchParams(location.search).get("server");
    const host = location.hostname || "localhost";
    const bracketed = host.includes(":") && !host.startsWith("[") ? `[${host}]` : host;
    const url = new URL(override || `${location.protocol === "https:" ? "wss" : "ws"}://${bracketed}:8765`);
    if (!["ws:", "wss:"].includes(url.protocol) || url.username || url.password || url.hash) {
      throw new Error("Server must be a ws:// or wss:// URL without credentials or a fragment.");
    }
    return url.href;
  }

  function createShell(options) {
    const { document: doc, store, history, createConnection } = options;
    const now = options.now || Date.now;
    const raf = options.requestAnimationFrame || root.requestAnimationFrame.bind(root);
    const live = doc.getElementById("live");
    const recall = doc.getElementById("recall");
    const status = doc.getElementById("status");
    const age = doc.getElementById("last-update");
    const followButton = doc.getElementById("follow-live");
    const rows = new Map();
    const pending = new Map();
    const recoveredSegments = new Set(); // Same 300-segment display bound.
    let scheduled = false, follow = true, lastUpdate = null, state = "connecting", seconds = 30;
    let disposed = false;

    function updateStatus() {
      const online = options.isOnline ? options.isOnline() : (!root.navigator || root.navigator.onLine !== false);
      status.textContent = !online ? "Offline" : state === "connected" ? "Connected" : state === "closed" ? "Offline" : "Reconnecting";
      status.dataset.state = online ? state : "closed";
      age.textContent = lastUpdate === null ? "Waiting for captions" : `Last update ${Math.max(0, Math.floor((now() - lastUpdate) / 1000))} s ago`;
    }

    function rowFor(caption, recovered) {
      const row = doc.createElement("p");
      row.className = `caption ${caption.final ? "final" : "provisional"}${recovered ? " recovered" : ""}`;
      row.dataset.segment = String(caption.segment);
      const label = doc.createElement("span");
      label.className = "caption-label";
      label.textContent = `${recovered ? "Recovered · " : ""}Segment ${caption.segment} · ${caption.final ? "Final" : "Updating…"}`;
      const text = doc.createElement("span");
      text.textContent = caption.text; // Text never becomes HTML from a remote source.
      row.append(label, text);
      return row;
    }

    function renderRecall() {
      const items = history.recall(seconds).slice(-MAX_ROWS);
      const fragment = doc.createDocumentFragment();
      for (const c of items) {
        const row = rowFor(c, recoveredSegments.has(c.segment) || Boolean(c.recovered));
        const time = doc.createElement("small");
        time.textContent = `${Math.max(0, Math.round(now() / 1000 - c.source_ts))} s ago`;
        row.append(time);
        fragment.append(row);
      }
      if (!items.length) fragment.append(doc.createTextNode("No finalized captions in this window."));
      recall.replaceChildren(fragment);
    }

    function render() {
      scheduled = false;
      if (disposed) return;
      // Preserve the reader's anchor when pruning rows above the viewport.
      const oldTop = live.scrollTop;
      let removedHeight = 0;
      for (const [segment, entry] of pending) {
        const row = rowFor(entry.caption, entry.recovered);
        if (rows.has(segment)) rows.get(segment).replaceWith(row);
        rows.set(segment, row);
      }
      pending.clear();
      const ordered = [...rows.keys()].sort((a, b) => a - b);
      while (ordered.length > MAX_ROWS) {
        const segment = ordered.shift();
        removedHeight += rows.get(segment).offsetHeight || 0;
        rows.delete(segment);
      }
      live.replaceChildren(...ordered.map(segment => rows.get(segment)));
      if (follow) live.scrollTop = live.scrollHeight;
      else live.scrollTop = Math.max(0, oldTop - removedHeight);
      renderRecall();
      updateStatus();
    }

    function schedule() {
      if (!scheduled && !disposed) { scheduled = true; raf(render); }
    }

    function accept(caption, recovered) {
      if (!caption || (recovered && caption.final !== true)) return;
      const result = store.apply(caption);
      if (!result || !result.accepted) return;
      if (caption.final && !recovered) history.addFinal(caption);
      if (recovered) {
        recoveredSegments.add(caption.segment);
        if (recoveredSegments.size > MAX_ROWS) recoveredSegments.delete(recoveredSegments.values().next().value);
      }
      lastUpdate = now();
      pending.set(caption.segment, {caption, recovered});
      // Prefer the newest segment context when a burst exceeds the visible bound.
      if (pending.size > MAX_ROWS) pending.delete(Math.min(...pending.keys()));
      schedule();
    }

    const conn = createConnection({
      url: options.url,
      clientId: options.clientId,
      getResumeState: () => store.latestFinal(),
      onStatus(value) { state = value; updateStatus(); },
      onMessage(message) {
        if (!message || typeof message !== "object") return;
        if (message.type === "CAPTION_UPDATE") accept(message, false);
        if (message.type === "HISTORY" && Array.isArray(message.items)) {
          const finals = message.items.filter(c => c && c.final === true);
          history.mergeHistory(finals);
          for (const c of finals) accept(c, true);
        }
      },
    });
    live.addEventListener("scroll", () => {
      follow = live.scrollHeight - live.clientHeight - live.scrollTop < 48;
      followButton.hidden = follow;
    });
    followButton.addEventListener("click", () => {
      follow = true; followButton.hidden = true; schedule();
    });
    for (const button of doc.querySelectorAll("button[data-seconds]")) {
      button.addEventListener("click", () => {
        seconds = Number(button.dataset.seconds);
        for (const other of doc.querySelectorAll("button[data-seconds]")) {
          other.setAttribute("aria-pressed", String(other === button));
        }
        schedule();
      });
    }
    updateStatus();
    schedule();
    const tick = (options.setInterval || root.setInterval)(() => { updateStatus(); }, 1000);
    return { close() { disposed = true; (options.clearInterval || root.clearInterval)(tick); conn.close(); } };
  }

  function boot() {
    const api = root.LiveRecall || {};
    const status = root.document.getElementById("status");
    try {
      const store = api.store || (api.createStore && api.createStore());
      const history = api.history || (api.createHistory && api.createHistory());
      if (!store || !history || !api.createConnection) {
        throw new Error("The caption client is unavailable. Please reload after the application is updated.");
      }
      let clientId = Math.floor(100000 + Math.random() * 900000);
      try {
        const saved = Number(root.sessionStorage.getItem("liverecall-client-id"));
        if (Number.isSafeInteger(saved) && saved > 0) clientId = saved;
        root.sessionStorage.setItem("liverecall-client-id", String(clientId));
      } catch (_) { /* Storage restrictions must not prevent connecting. */ }
      const url = serverURL(root.location);
      root.document.getElementById("server-url").textContent = url;
      const shell = createShell({document: root.document, store, history,
        createConnection: api.createConnection, clientId, url});
      root.addEventListener("pagehide", () => shell.close(), {once: true});
    } catch (error) {
      status.textContent = "Offline";
      root.document.getElementById("error").textContent = error.message;
    }
  }
  const api = {serverURL, createShell, MAX_ROWS};
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else { root.LiveRecall = Object.assign(root.LiveRecall || {}, api); boot(); }
})(typeof globalThis !== "undefined" ? globalThis : this);
