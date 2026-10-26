"""Bounded recovery history for finalized LiveRecall captions.

This module keeps a bounded finalized-caption index without re-encoding
captions when constructing a HISTORY message.
"""

from __future__ import annotations

import bisect
import json
import math

from .protocol import Caption


class FinalHistory:
    """Store a bounded set of finalized captions for recovery and late joins.

    The default retention is 90 seconds and the default count cap is 512
    finalized captions.
    """

    MAX_RETENTION_SECONDS = 90.0
    MAX_ITEMS = 512
    MAX_REQUEST_SECONDS = 60.0

    def __init__(
        self,
        max_seconds: float = MAX_RETENTION_SECONDS,
        max_items: int = MAX_ITEMS,
    ) -> None:
        if not math.isfinite(max_seconds) or max_seconds <= 0:
            raise ValueError("max_seconds must be a positive finite number")
        if max_items <= 0:
            raise ValueError("max_items must be positive")

        self.max_seconds = float(max_seconds)
        self.max_items = int(max_items)

        # The time index is used for O(log n + k) window selection of captions.
        # Entries are sorted by source timestamp, then segment/revision for ties.
        self._time_keys: list[tuple[float, int, int]] = []
        self._time_items: list[Caption] = []

        # Keep a separate segment-ordered index so the history remains
        # ordered by segment even when captions arrive out of order.
        # Used for comparing against what client has already received.
        self._segment_keys: list[tuple[int, int]] = []
        self._segment_items: list[Caption] = []
        self._by_segment: dict[int, Caption] = {}

        self._newest_source_ts: float | None = None

    def __len__(self) -> int:
        return len(self._time_items)

    def add(self, c: Caption) -> None:
        # Add one accepted final caption, ignoring unsupported entries.

        if not c.final or c.segment in self._by_segment:
            return

        # Add entry to list sorted by ts 
        time_key = (c.source_ts, c.segment, c.revision)
        time_pos = bisect.bisect_right(self._time_keys, time_key)
        self._time_keys.insert(time_pos, time_key)
        self._time_items.insert(time_pos, c)

        # Add entry to list sorted by segment
        segment_key = (c.segment, c.revision)
        segment_pos = bisect.bisect_left(self._segment_keys, segment_key)
        self._segment_keys.insert(segment_pos, segment_key)
        self._segment_items.insert(segment_pos, c)
        self._by_segment[c.segment] = c

        # Renew latest ts
        if self._newest_source_ts is None or c.source_ts > self._newest_source_ts:
            self._newest_source_ts = c.source_ts
        self._prune()

    def history_msg(self, last_seg: int, last_rev: int, seconds: float) -> str:
        """Return a compact HISTORY message for a late join or resume.

        A late join honors ``seconds`` up to 60 seconds.  A resume always
        searches the full 60-second recovery window so a reconnect cannot
        silently lose finals merely because the client requested a smaller
        late-join window.
        """

        if not self._time_items:
            return self._encode_history(())

        # Client's latest caption
        last_seg = self._safe_int(last_seg, default=0)
        last_rev = self._safe_int(last_rev, default=0)

        if last_seg > 0:
            # For a reconnect, get all within 60s, even if requested less
            window_seconds = min(self.MAX_REQUEST_SECONDS, self.max_seconds)
        else:
            # For a late join, use the specified seconds
            window_seconds = self._clamp_seconds(seconds)

        assert self._newest_source_ts is not None
        cutoff = self._newest_source_ts - window_seconds
        start_key = (cutoff, -math.inf, -math.inf)
        start = bisect.bisect_left(self._time_keys, start_key)

        selected: list[Caption] = []
        resume_key = (last_seg, last_rev)
        for c in self._time_items[start:]:
            if c.source_ts < cutoff:
                continue
            if last_seg > 0 and (c.segment, c.revision) <= resume_key:
                continue
            selected.append(c)

        # Source timestamps define oldest-to-newest delivery order for the
        # instructor source and increase with segment number.  If callers add
        # entries out of order with respect to those timestamps, preserve the
        # public segment-order contract before encoding the message.
        if any(
            left.segment > right.segment
            for left, right in zip(selected, selected[1:])
        ):
            selected.sort(key=lambda c: (c.segment, c.revision))
        return self._encode_history(selected)

    def _prune(self) -> None:
        # Helper function to remove entries with ts outside of max seconds window
        assert self._newest_source_ts is not None
        cutoff = self._newest_source_ts - self.max_seconds

        while self._time_items and self._time_items[0].source_ts < cutoff:
            self._remove_oldest()

        while len(self._time_items) > self.max_items:
            self._remove_oldest()

    def _remove_oldest(self) -> None:
        c = self._time_items.pop(0)
        self._time_keys.pop(0)

        segment_key = (c.segment, c.revision)
        segment_pos = bisect.bisect_left(self._segment_keys, segment_key)
        if (
            segment_pos >= len(self._segment_keys)
            or self._segment_keys[segment_pos] != segment_key
        ):
            raise RuntimeError("history indexes out of sync")
        self._segment_keys.pop(segment_pos)
        self._segment_items.pop(segment_pos)
        self._by_segment.pop(c.segment, None)

    @classmethod
    def _clamp_seconds(cls, seconds: float) -> float:
        try:
            value = float(seconds)
        except (TypeError, ValueError):
            return 0.0
        if math.isnan(value) or value <= 0:
            return 0.0
        if math.isinf(value):
            return cls.MAX_REQUEST_SECONDS
        return min(value, cls.MAX_REQUEST_SECONDS)

    @staticmethod
    def _safe_int(value: int, default: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _encode_history(items: tuple[Caption, ...] | list[Caption]) -> str:
        # The wrapper is encoded once, while each caption retains the compact
        # wire representation created by protocol.caption_from().
        if not items:
            return json.dumps({"type": "HISTORY", "items": []}, separators=(",", ":"))
        return '{"type":"HISTORY","items":[' + ",".join(
            c.wire for c in items
        ) + "]}"
