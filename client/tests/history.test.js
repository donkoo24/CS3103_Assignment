import test from 'node:test';
import assert from 'node:assert';
import { createHistory } from '../history.js';

function caption(segment, revision, source_ts, text = `s${segment}r${revision}`, final = true) {
  return { type: "CAPTION_UPDATE", segment, revision, source_ts, final, text };
}

test("stores only finals and recalls them chronologically", () => {
  const history = createHistory({ now: () => 1_000 });
  history.addFinal(caption(2, 1, 990));
  history.addFinal(caption(1, 2, 980));
  history.addFinal(caption(3, 1, 995, "provisional", false));

  assert.deepEqual(history.recall(30).map((item) => item.segment), [1, 2]);
  assert.equal(history.size, 2);
});

test("clamps recall windows to the supported range", () => {
  const history = createHistory({ now: () => 1_000 });
  history.addFinal(caption(1, 1, 940));
  history.addFinal(caption(2, 1, 990));

  assert.deepEqual(history.recall(15).map((item) => item.segment), [2]);
  assert.deepEqual(history.recall(60).map((item) => item.segment), [1, 2]);
  assert.deepEqual(history.recall(600).map((item) => item.segment), [1, 2]);
});

test("ignores malformed entries, duplicates, and later revisions of a final", () => {
  const history = createHistory({ now: () => 1_000 });
  assert.equal(history.addFinal(caption(1, 1, 990, "not final", false)), false);
  assert.equal(history.addFinal({ segment: 1, revision: 1, source_ts: 990, final: true }), false);
  assert.equal(history.addFinal(caption(1, 1, 990)), true);
  assert.equal(history.addFinal(caption(1, 1, 990)), false);
  assert.equal(history.addFinal(caption(1, 2, 991)), false);
  assert.equal(history.size, 1);
});

test("mergeHistory returns only newly recovered finals", () => {
  const history = createHistory({ now: () => 1_000 });
  const first = history.mergeHistory([
    caption(2, 1, 992),
    caption(1, 1, 991),
    caption(3, 1, 993, "not final", false),
  ]);
  const second = history.mergeHistory([caption(1, 1, 991), caption(2, 1, 992)]);

  assert.deepEqual(first.map((item) => item.segment), [1, 2]);
  assert.deepEqual(second, []);
});

test("enforces both time and count bounds", () => {
  const history = createHistory({ now: () => 1_000, maxSeconds: 90, maxItems: 2 });
  history.addFinal(caption(1, 1, 900));
  history.addFinal(caption(2, 1, 980));
  history.addFinal(caption(3, 1, 990));
  history.addFinal(caption(4, 1, 995));

  assert.equal(history.size, 2);
  assert.deepEqual(history.recall(60).map((item) => item.segment), [3, 4]);
});
