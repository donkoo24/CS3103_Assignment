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