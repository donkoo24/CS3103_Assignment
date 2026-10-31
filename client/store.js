export class CaptionStore {
    constructor() {
        this.latest = new Map(); // Maps segment ID -> { revision, final, text }
        this.maxEntries = 512;
        this.minRetainedSegment = 0;
        this.highestFinalSeg = 0;
        this.highestFinalRev = 0;
    }

    apply(msg) {
        const seg = msg && msg.segment;
        const rev = msg && msg.revision;
        if (!Number.isSafeInteger(seg) || seg < 0 ||
            !Number.isSafeInteger(rev) || rev < 1 ||
            typeof msg.final !== 'boolean' || typeof msg.text !== 'string') {
            return { accepted: false, changed: false };
        }
        // Evicted finals remain durable: an old replay cannot re-enter the map.
        if (seg < this.minRetainedSegment) {
            return { accepted: false, changed: false };
        }
        
        if (!this.latest.has(seg)) {
            this.latest.set(seg, { revision: rev, final: msg.final, text: msg.text });
            this._updateLatestFinal(seg, rev, msg.final);
            this._prune();
            return { accepted: true, changed: true };
        }

        const stored = this.latest.get(seg);
        
        // Rule: A finalized segment is durable.
        if (stored.final) {
            return { accepted: false, changed: false };
        }

        // Rule: Only accept strictly newer revisions.
        if (rev > stored.revision) {
            stored.revision = rev;
            stored.final = msg.final;
            stored.text = msg.text;
            this._updateLatestFinal(seg, rev, msg.final);
            return { accepted: true, changed: true };
        }

        return { accepted: false, changed: false };
    }

    _updateLatestFinal(seg, rev, isFinal) {
        if (isFinal) {
            if (seg > this.highestFinalSeg || (seg === this.highestFinalSeg && rev > this.highestFinalRev)) {
                this.highestFinalSeg = seg;
                this.highestFinalRev = rev;
            }
        }
    }

    _prune() {
        while (this.latest.size > this.maxEntries) {
            const oldest = Math.min(...this.latest.keys());
            this.latest.delete(oldest);
            this.minRetainedSegment = Math.max(this.minRetainedSegment, oldest + 1);
        }
    }

    latestFinal() {
        return { segment: this.highestFinalSeg, revision: this.highestFinalRev };
    }
}
