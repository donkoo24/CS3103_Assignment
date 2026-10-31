import test from 'node:test';
import assert from 'node:assert';
import { CaptionStore } from '../store.js';

test('CaptionStore accepts new segments', () => {
    const store = new CaptionStore();
    const res = store.apply({ segment: 1, revision: 1, final: false, text: "Hello" });
    assert.strictEqual(res.accepted, true);
});

test('CaptionStore rejects older revisions and locks finals', () => {
    const store = new CaptionStore();
    
    // Push Rev 2
    store.apply({ segment: 1, revision: 2, final: false, text: "Hello world" });
    
    // Reject Rev 1 (Stale)
    const resStale = store.apply({ segment: 1, revision: 1, final: false, text: "Hello" });
    assert.strictEqual(resStale.accepted, false);
    
    // Accept Rev 3 (Final)
    const resFinal = store.apply({ segment: 1, revision: 3, final: true, text: "Hello world!" });
    assert.strictEqual(resFinal.accepted, true);
    
    // Reject Rev 4 (Because Final is locked)
    const resAfterFinal = store.apply({ segment: 1, revision: 4, final: false, text: "Hello world!?" });
    assert.strictEqual(resAfterFinal.accepted, false);
});

test('CaptionStore accurately tracks latestFinal', () => {
    const store = new CaptionStore();
    store.apply({ segment: 1, revision: 1, final: true, text: "First" });
    store.apply({ segment: 3, revision: 2, final: true, text: "Third" });
    
    const latest = store.latestFinal();
    assert.strictEqual(latest.segment, 3);
    assert.strictEqual(latest.revision, 2);
});

test('CaptionStore bounds retained segments without reviving old finals', () => {
    const store = new CaptionStore();
    for (let segment = 1; segment <= 1000; segment++) {
        store.apply({ segment, revision: 1, final: true, text: String(segment) });
    }
    assert.strictEqual(store.latest.size, 512);
    assert.deepStrictEqual(store.latestFinal(), { segment: 1000, revision: 1 });
    assert.strictEqual(store.apply({ segment: 1, revision: 2, final: true, text: 'replay' }).accepted, false);
    assert.strictEqual(store.apply({ segment: 1000, revision: 2, final: true, text: 'replay' }).accepted, false);
});

test('CaptionStore rejects malformed updates before retention accounting', () => {
    const store = new CaptionStore();
    for (let i = 0; i < 600; i++) {
        assert.strictEqual(store.apply({ revision: 1, final: true, text: 'bad' }).accepted, false);
    }
    assert.strictEqual(store.latest.size, 0);
    assert.strictEqual(store.apply(null).accepted, false);
});
