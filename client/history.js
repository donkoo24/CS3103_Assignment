/*
 * Bounded local history of finalized captions.
 *
 * The browser keeps at most 90 seconds and 512 finalized captions. The
 * server's recovery history is also bounded, but this separate local copy is
 * what makes the recall buttons work without another network request.
 *
 * This file follows the rest of the client codebase and is loaded as an ES
 * module. The application can import createHistory directly.
 */
const MAX_SECONDS = 90;
const MAX_ITEMS = 512;
const RECALL_MAX_SECONDS = 60;

function asCaption(value) {
  if (!value || typeof value !== "object") return null;
  if (value.final !== true) return null;
  if (!Number.isSafeInteger(value.segment) || value.segment < 0) return null;
  if (!Number.isSafeInteger(value.revision) || value.revision < 1) return null;
  if (!Number.isFinite(value.source_ts)) return null;
  if (typeof value.text !== "string") return null;
  return {
    type: value.type,
    segment: value.segment,
    revision: value.revision,
    source_ts: value.source_ts,
    final: true,
    text: value.text,
  };
}

function compareCaptions(left, right) {
  return left.source_ts - right.source_ts ||
    left.segment - right.segment ||
    left.revision - right.revision;
}

export function createHistory(options = {}) {
    const opts = Object.assign({
      maxSeconds: MAX_SECONDS,
      maxItems: MAX_ITEMS,
      now: () => Date.now() / 1000,
    }, options || {});
    const maxSeconds = Number.isFinite(Number(opts.maxSeconds)) && Number(opts.maxSeconds) > 0
      ? Number(opts.maxSeconds)
      : MAX_SECONDS;
    const maxItems = Number.isSafeInteger(Number(opts.maxItems)) && Number(opts.maxItems) > 0
      ? Number(opts.maxItems)
      : MAX_ITEMS;
    const entries = new Map();
    let newestSourceTs = -Infinity;

    function sortedEntries() {
      return [...entries.values()].sort(compareCaptions);
    }

    function prune() {
      if (Number.isFinite(newestSourceTs)) {
        const cutoff = newestSourceTs - maxSeconds;
        for (const [segment, caption] of entries) {
          if (caption.source_ts < cutoff) entries.delete(segment);
        }
      }
      const ordered = sortedEntries();
      while (ordered.length > maxItems) {
        const oldest = ordered.shift();
        entries.delete(oldest.segment);
      }
    }

    function addFinal(value) {
      const caption = asCaption(value);
      if (!caption) return false;

      const existing = entries.get(caption.segment);
      if (existing) {
        // A finalized segment is durable. This also rejects duplicate and
        // conflicting later revisions from malformed or repeated HISTORY.
        return false;
      }

      entries.set(caption.segment, caption);
      newestSourceTs = Math.max(newestSourceTs, caption.source_ts);
      prune();
      return entries.has(caption.segment);
    }

    function recall(seconds) {
      let window = Number(seconds);
      if (!Number.isFinite(window)) window = 0;
      window = Math.max(0, Math.min(RECALL_MAX_SECONDS, window));

      let now = Number(opts.now());
      if (!Number.isFinite(now)) now = Date.now() / 1000;
      const cutoff = now - window;
      return sortedEntries()
        .filter((caption) => caption.source_ts >= cutoff && caption.source_ts <= now)
        .map((caption) => Object.assign({}, caption));
    }

    function mergeHistory(items) {
      if (!Array.isArray(items)) return [];
      const recovered = [];
      for (const item of items) {
        if (addFinal(item)) recovered.push(asCaption(item));
      }
      return recovered.sort(compareCaptions).map((caption) => Object.assign({}, caption));
    }

    return {
      addFinal,
      recall,
      mergeHistory,
      get size() { return entries.size; },
      MAX_SECONDS: maxSeconds,
      MAX_ITEMS: maxItems,
    };
}

export { MAX_SECONDS, MAX_ITEMS, RECALL_MAX_SECONDS };
