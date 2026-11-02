import assert from "node:assert/strict";
import test from "node:test";

import connection from "../connection.js";

const { createConnection, STATUS } = connection;

// Deterministic clock: timers fire only when advance() is called.
function fakeClock() {
  let now = 0;
  let seq = 0;
  const timers = new Map();
  return {
    now: () => now,
    setTimeout(fn, ms) {
      timers.set(++seq, { at: now + ms, fn });
      return seq;
    },
    clearTimeout(id) {
      timers.delete(id);
    },
    advance(ms) {
      const until = now + ms;
      for (;;) {
        const due = [...timers].filter(([, t]) => t.at <= until);
        if (!due.length) break;
        const [id, t] = due.sort((a, b) => a[1].at - b[1].at)[0];
        timers.delete(id);
        now = t.at;
        t.fn();
      }
      now = until;
    },
  };
}

function fakeSockets() {
  const created = [];
  class FakeWebSocket {
    constructor(url) {
      this.url = url;
      this.sent = [];
      this.closed = null;
      created.push(this);
    }
    send(data) {
      this.sent.push(JSON.parse(data));
    }
    close(code, reason) {
      this.closed ??= { code, reason };
      this.onclose?.({ code });
    }
    // test helpers
    open() {
      this.onopen?.();
    }
    receive(obj) {
      this.onmessage?.({ data: typeof obj === "string" ? obj : JSON.stringify(obj) });
    }
    drop() {
      this.onclose?.({ code: 1006 });
    }
    fail() {
      this.onerror?.({}); // like Node's WebSocket: "error" with no "close"
    }
  }
  return { FakeWebSocket, created };
}

function setup(extra = {}) {
  const clock = fakeClock();
  const { FakeWebSocket, created } = fakeSockets();
  const statuses = [];
  const messages = [];
  let resume = { segment: 0, revision: 0 };
  const conn = createConnection({
    url: "ws://test",
    clientId: 7,
    WebSocket: FakeWebSocket,
    setTimeout: clock.setTimeout,
    clearTimeout: clock.clearTimeout,
    now: clock.now,
    random: () => 1, // upper end of the jitter range: deterministic delays
    env: null,
    getResumeState: () => resume,
    onMessage: (m) => messages.push(m),
    onStatus: (s, info) => statuses.push({ s, ...info }),
    ...extra,
  });
  return {
    conn,
    clock,
    created,
    statuses,
    messages,
    setResume: (r) => (resume = r),
    last: () => created.at(-1),
  };
}

test("sends CLIENT_HELLO with the latest finalized state on every connect", () => {
  const t = setup();
  t.last().open();
  assert.deepEqual(t.last().sent[0], {
    type: "CLIENT_HELLO",
    client_id: 7,
    session: "L1",
    last_segment: 0,
    last_revision: 0,
    history_seconds: 60,
  });

  t.setResume({ segment: 38, revision: 3 });
  t.last().drop();
  t.clock.advance(500);
  t.last().open();
  assert.equal(t.created.length, 2);
  assert.equal(t.last().sent[0].last_segment, 38);
  assert.equal(t.last().sent[0].last_revision, 3);
});

test("delivers parsed messages and ignores malformed frames", () => {
  const t = setup();
  t.last().open();
  t.last().receive({ type: "HISTORY", items: [] });
  t.last().receive("not json");
  t.last().receive({ type: "CAPTION_UPDATE", segment: 1, revision: 1 });
  assert.deepEqual(
    t.messages.map((m) => m.type),
    ["HISTORY", "CAPTION_UPDATE"]
  );
});

test("reconnects with capped exponential backoff, reset after a full handshake", () => {
  const t = setup();
  const delays = [];
  for (let i = 0; i < 6; i++) {
    t.last().drop(); // refused before the handshake completes
    delays.push(t.statuses.at(-1).inMs);
    t.clock.advance(t.statuses.at(-1).inMs);
  }
  assert.deepEqual(delays, [500, 1000, 2000, 4000, 5000, 5000]);
  assert.equal(t.created.length, 7);

  t.last().open();
  t.last().receive({ type: "HISTORY", items: [] }); // handshake succeeded
  t.last().drop();
  assert.equal(t.statuses.at(-1).inMs, 500);
});

test("jitter spreads reconnects between half and the full backoff", () => {
  const t = setup({ random: () => 0 });
  t.last().drop();
  assert.equal(t.statuses.at(-1).inMs, 250);
});

test("reports status transitions for the UI badge", () => {
  const t = setup();
  t.last().open();
  t.last().drop();
  assert.deepEqual(
    t.statuses.map((x) => x.s),
    [STATUS.CONNECTING, STATUS.CONNECTED, STATUS.RECONNECTING]
  );
});

test("a silent connection is treated as dead and replaced", () => {
  const t = setup({ silenceTimeoutMs: 1000 });
  t.last().open();
  t.clock.advance(900);
  t.last().receive({ type: "CAPTION_UPDATE" }); // traffic re-arms the timer
  t.clock.advance(900);
  assert.equal(t.last().closed, null);
  t.clock.advance(200);
  assert.equal(t.created[0].closed.code, 4000);
  t.clock.advance(500);
  assert.equal(t.created.length, 2);
});

test("a failed connect that reports only an error still reconnects", () => {
  const t = setup();
  t.last().fail();
  t.last().drop(); // a late "close" for the same socket is ignored
  assert.equal(t.statuses.filter((x) => x.s === STATUS.RECONNECTING).length, 1);
  t.clock.advance(500);
  assert.equal(t.created.length, 2);
});

test("a handshake that never completes is abandoned", () => {
  const t = setup({ connectTimeoutMs: 2000 });
  t.clock.advance(1999);
  assert.equal(t.created.length, 1);
  t.clock.advance(1);
  assert.equal(t.created[0].closed.code, 4000);
  t.clock.advance(500);
  assert.equal(t.created.length, 2);
});

test("reconnectNow skips the remaining backoff; close() stops for good", () => {
  const t = setup();
  t.last().drop();
  t.conn.reconnectNow();
  assert.equal(t.created.length, 2);

  t.conn.close();
  assert.equal(t.statuses.at(-1).s, STATUS.CLOSED);
  t.clock.advance(60_000);
  t.conn.reconnectNow();
  assert.equal(t.created.length, 2);
});

test("online / visible events trigger an immediate reconnect", () => {
  const listeners = {};
  const env = {
    addEventListener: (type, fn) => (listeners[type] = fn),
    removeEventListener: (type) => delete listeners[type],
    document: {
      visibilityState: "hidden",
      addEventListener: (type, fn) => (listeners[type] = fn),
      removeEventListener: (type) => delete listeners[type],
    },
  };
  const t = setup({ env });
  t.last().drop();
  listeners.visibilitychange(); // still hidden: keep backing off
  assert.equal(t.created.length, 1);
  env.document.visibilityState = "visible";
  listeners.visibilitychange();
  assert.equal(t.created.length, 2);
  t.last().drop();
  listeners.online();
  assert.equal(t.created.length, 3);
  t.conn.close();
  assert.deepEqual(Object.keys(listeners), []);
});

test("close ignores queued messages and late opens from the stopped socket", () => {
  const t = setup();
  const socket = t.last();
  t.conn.close();
  socket.open();
  socket.receive({ type: "CAPTION_UPDATE", segment: 1, revision: 1 });
  socket.receive({ type: "HISTORY", items: [] });
  t.clock.advance(60000);
  assert.deepEqual(socket.sent, []);
  assert.deepEqual(t.messages, []);
  assert.equal(t.statuses.at(-1).s, STATUS.CLOSED);
  assert.equal(t.created.length, 1);
});

test("replaced socket cannot deliver messages or overwrite the new connection status", () => {
  const t = setup();
  const old = t.last();
  old.open();
  old.drop();
  t.clock.advance(500);
  const current = t.last();
  current.open();
  current.receive({ type: "HISTORY", items: [] });
  const count = t.messages.length;
  old.open();
  old.receive({ type: "CAPTION_UPDATE", segment: 50, revision: 1 });
  assert.equal(old.sent.length, 1);
  assert.equal(t.messages.length, count);
  assert.equal(t.statuses.at(-1).s, STATUS.CONNECTED);
  current.receive({ type: "CAPTION_UPDATE", segment: 51, revision: 1 });
  assert.equal(t.messages.at(-1).segment, 51);
  t.conn.close();
});

function networkEnv(online) {
  const listeners = {};
  return {
    listeners,
    navigator: { onLine: online },
    addEventListener: (name, fn) => { listeners[name] = fn; },
    removeEventListener: (name) => { delete listeners[name]; },
  };
}

test("offline closes the socket and resumes from finalized state when online", () => {
  const env = networkEnv(true);
  const t = setup({ env });
  const old = t.last();
  old.open();
  t.setResume({ segment: 8, revision: 3 });
  env.navigator.onLine = false;
  env.listeners.offline();
  old.receive({ type: "CAPTION_UPDATE", segment: 9, revision: 1 });
  t.clock.advance(60000);
  assert.deepEqual(t.messages, []);
  assert.equal(old.closed.code, 1000);
  assert.equal(t.statuses.at(-1).s, STATUS.OFFLINE);
  assert.equal(t.created.length, 1);
  env.navigator.onLine = true;
  env.listeners.online();
  t.last().open();
  assert.equal(t.created.length, 2);
  assert.equal(t.last().sent[0].last_segment, 8);
  t.conn.close();
  assert.equal(env.listeners.offline, undefined);
});

test("initial offline state waits for online without retry timers", () => {
  const env = networkEnv(false);
  const t = setup({ env });
  t.clock.advance(60000);
  assert.equal(t.created.length, 0);
  assert.equal(t.statuses.at(-1).s, STATUS.OFFLINE);
  env.navigator.onLine = true;
  env.listeners.online();
  assert.equal(t.created.length, 1);
  t.conn.close();
});

test("an offline network flag rejects messages even before the offline event", () => {
  const env = networkEnv(true);
  const t = setup({ env });
  t.last().open();
  env.navigator.onLine = false;
  t.last().receive({ type: "CAPTION_UPDATE", segment: 1, revision: 1 });
  assert.deepEqual(t.messages, []);
  assert.equal(t.statuses.at(-1).s, STATUS.OFFLINE);
  t.conn.close();
});
