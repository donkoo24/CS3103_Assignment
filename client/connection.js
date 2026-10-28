/*
 * LiveRecall connection manager: one WebSocket to the server that survives
 * drops. It sends CLIENT_HELLO with the client's latest *finalized* state on
 * every (re)connect, so the server's HISTORY carries exactly what was missed,
 * and reconnects with capped exponential backoff plus jitter (so a server
 * restart is not hit by every student at the same instant).
 *
 * Plain script (no build step): in the browser it defines
 * `window.LiveRecall.createConnection`; in Node it is `require`-able for tests.
 *
 *   const conn = LiveRecall.createConnection({
 *     url: "ws://127.0.0.1:8765",
 *     clientId: 17,
 *     getResumeState: () => store.latestFinal(),   // {segment, revision}
 *     onMessage: (msg) => ...,                      // parsed HISTORY / CAPTION_UPDATE
 *     onStatus: (status, info) => ...,              // see STATUS below
 *   });
 */
(function (root) {
  "use strict";

  // connecting -> connected -> (drop) -> reconnecting -> connecting -> ...
  const STATUS = Object.freeze({
    CONNECTING: "connecting",
    CONNECTED: "connected",
    RECONNECTING: "reconnecting",
    CLOSED: "closed", // close() was called; no further reconnects
  });

  function createConnection(options) {
    const opts = Object.assign(
      {
        session: "L1",
        historySeconds: 60, // fill the full local recall window on (re)join
        initialDelayMs: 500,
        maxDelayMs: 5000,
        connectTimeoutMs: 5000, // handshake must complete within this
        silenceTimeoutMs: 30000, // no frame for this long => assume dead link
        getResumeState: () => ({ segment: 0, revision: 0 }),
        onMessage: () => {},
        onStatus: () => {},
        WebSocket: root.WebSocket,
        setTimeout: root.setTimeout.bind(root),
        clearTimeout: root.clearTimeout.bind(root),
        now: () => Date.now(),
        random: Math.random,
        env: typeof window === "undefined" ? null : window,
      },
      options
    );

    let ws = null;
    let attempt = 0; // consecutive failed attempts; reset once HISTORY arrives
    let retryTimer = null;
    let watchdogTimer = null;
    let lastMessageAt = null;
    let stopped = false;

    function report(status, extra) {
      opts.onStatus(status, Object.assign({ attempt, lastMessageAt }, extra));
    }

    function backoffMs() {
      // Capped exponential backoff with "equal jitter": half fixed, half random.
      const cap = Math.min(opts.maxDelayMs, opts.initialDelayMs * 2 ** attempt);
      return cap / 2 + opts.random() * (cap / 2);
    }

    // One watchdog per socket: first bounds the handshake, then (re-armed by
    // every frame) bounds silence. Browsers cannot see WebSocket pings, so a
    // long silence is the only client-side sign of a half-open link (e.g.
    // after laptop sleep); either way the socket is abandoned and replaced.
    function armWatchdog(ms, onExpire) {
      opts.clearTimeout(watchdogTimer);
      watchdogTimer = opts.setTimeout(onExpire, ms);
    }

    function open() {
      retryTimer = null;
      if (stopped) return;
      report(STATUS.CONNECTING);
      let socket;
      try {
        socket = new opts.WebSocket(opts.url);
      } catch (err) {
        scheduleReconnect();
        return;
      }
      ws = socket;

      // Idempotent: implementations differ on whether "close" follows "error"
      // (Node's WebSocket fires only "error" for a refused connection).
      const fail = () => {
        if (ws !== socket) return; // already handled, or superseded
        ws = null;
        opts.clearTimeout(watchdogTimer);
        try {
          socket.close(4000, "abandoned");
        } catch (err) {
          // already closed / never opened: nothing to release
        }
        scheduleReconnect();
      };
      armWatchdog(opts.connectTimeoutMs, fail);

      socket.onopen = () => {
        const state = opts.getResumeState() || {};
        socket.send(
          JSON.stringify({
            type: "CLIENT_HELLO",
            client_id: opts.clientId,
            session: opts.session,
            last_segment: state.segment || 0,
            last_revision: state.revision || 0,
            history_seconds: opts.historySeconds,
          })
        );
        report(STATUS.CONNECTED);
        armWatchdog(opts.silenceTimeoutMs, fail);
      };

      socket.onmessage = (event) => {
        let msg;
        try {
          msg = JSON.parse(event.data);
        } catch (err) {
          return; // ignore malformed frames rather than dropping the link
        }
        lastMessageAt = opts.now();
        if (msg.type === "HISTORY") attempt = 0; // handshake fully succeeded
        armWatchdog(opts.silenceTimeoutMs, fail);
        opts.onMessage(msg);
      };

      socket.onclose = fail;
      socket.onerror = fail;
    }

    function scheduleReconnect() {
      if (stopped || retryTimer !== null) return;
      const delay = backoffMs();
      attempt += 1;
      report(STATUS.RECONNECTING, { inMs: delay });
      retryTimer = opts.setTimeout(open, delay);
    }

    function reconnectNow() {
      // Skip the remaining backoff, e.g. when the tab becomes visible again or
      // the OS reports the network is back.
      if (stopped || ws) return;
      opts.clearTimeout(retryTimer);
      retryTimer = null;
      open();
    }

    function onVisibility() {
      if (!opts.env.document || opts.env.document.visibilityState === "visible") {
        reconnectNow();
      }
    }

    if (opts.env) {
      opts.env.addEventListener("online", reconnectNow);
      if (opts.env.document) {
        opts.env.document.addEventListener("visibilitychange", onVisibility);
      }
    }

    open();

    return {
      reconnectNow,
      close() {
        stopped = true;
        opts.clearTimeout(retryTimer);
        opts.clearTimeout(watchdogTimer);
        if (opts.env) {
          opts.env.removeEventListener("online", reconnectNow);
          if (opts.env.document) {
            opts.env.document.removeEventListener("visibilitychange", onVisibility);
          }
        }
        if (ws) ws.close(1000, "client closed");
        ws = null;
        report(STATUS.CLOSED);
      },
    };
  }

  const api = { createConnection, STATUS };
  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  } else {
    root.LiveRecall = Object.assign(root.LiveRecall || {}, api);
  }
})(typeof globalThis !== "undefined" ? globalThis : this);
