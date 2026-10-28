export class CaptionStore {
    constructor() {
        this.latest = new Map(); // Maps segment ID -> { revision, final, text }
        this.highestFinalSeg = 0;
        this.highestFinalRev = 0;
    }

    apply(msg) {
        const seg = msg.segment;
        const rev = msg.revision;
        
        if (!this.latest.has(seg)) {
            this.latest.set(seg, { revision: rev, final: msg.final, text: msg.text });
            this._updateLatestFinal(seg, rev, msg.final);
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

    latestFinal() {
        return { segment: this.highestFinalSeg, revision: this.highestFinalRev };
    }
}