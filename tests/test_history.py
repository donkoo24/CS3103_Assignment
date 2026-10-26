import json

from liverecall.history import FinalHistory
from liverecall.protocol import Caption, caption_from


def caption(
    segment: int,
    source_ts: float,
    *,
    revision: int = 1,
    final: bool = True,
    text: str | None = None,
) -> Caption:
    text = text or f"caption {segment}"
    wire = json.dumps(
        {
            "type": "CAPTION_UPDATE",
            "segment": segment,
            "revision": revision,
            "source_ts": source_ts,
            "final": final,
            "text": text,
        },
        separators=(",", ":"),
    )
    parsed = caption_from(json.loads(wire))
    assert parsed is not None
    return parsed


def history_items(message: str) -> list[dict]:
    payload = json.loads(message)
    assert payload["type"] == "HISTORY"
    return payload["items"]


def test_non_final_captions_never_enter_history():
    history = FinalHistory()

    history.add(caption(1, 100.0, final=False))

    assert len(history) == 0
    assert history_items(history.cached_history(0, 0, 60)) == []


def test_duplicate_final_is_stored_only_once():
    history = FinalHistory()
    final = caption(1, 100.0, revision=3)

    history.add(final)
    history.add(final)
    history.add(caption(1, 101.0, revision=4))

    assert len(history) == 1
    assert history_items(history.cached_history(0, 0, 60)) == [
        json.loads(final.wire)
    ]


def test_history_is_oldest_to_newest_and_final_only():
    history = FinalHistory()
    history.add(caption(3, 102.0))
    history.add(caption(1, 100.0))
    history.add(caption(2, 101.0, final=False))
    history.add(caption(2, 101.0))

    items = history_items(history.cached_history(0, 0, 60))

    assert [item["segment"] for item in items] == [1, 2, 3]
    assert all(item["final"] is True for item in items)


def test_history_keeps_segment_order_for_non_monotonic_insertions():
    history = FinalHistory()
    history.add(caption(3, 100.0))
    history.add(caption(1, 102.0))
    history.add(caption(2, 101.0))

    items = history_items(history.cached_history(0, 0, 60))

    assert [item["segment"] for item in items] == [1, 2, 3]


def test_time_pruning_uses_newest_source_timestamp():
    history = FinalHistory(max_seconds=10)
    history.add(caption(1, 99.0))
    history.add(caption(2, 109.9))
    history.add(caption(3, 110.0))

    assert [item["segment"] for item in history_items(
        history.cached_history(0, 0, 60)
    )] == [2, 3]


def test_count_pruning_removes_oldest_entries():
    history = FinalHistory(max_seconds=90, max_items=2)
    for segment in range(1, 4):
        history.add(caption(segment, 100.0 + segment))

    assert len(history) == 2
    assert [item["segment"] for item in history_items(
        history.cached_history(0, 0, 60)
    )] == [2, 3]


def test_late_join_honors_requested_window_and_caps_at_60_seconds():
    history = FinalHistory()
    for segment, source_ts in enumerate((0.0, 20.0, 40.0, 70.0), start=1):
        history.add(caption(segment, source_ts))

    # The newest source timestamp is 70, so a 30-second request starts at 40.
    assert [item["segment"] for item in history_items(
        history.cached_history(0, 0, 30)
    )] == [3, 4]

    # A request above 60 seconds is capped to the 60-second late-join window.
    assert [item["segment"] for item in history_items(
        history.cached_history(0, 0, 999)
    )] == [2, 3, 4]


def test_resume_uses_full_60_second_window_and_excludes_existing_finals():
    history = FinalHistory()
    for segment, source_ts in enumerate((0.0, 20.0, 40.0, 70.0), start=1):
        history.add(caption(segment, source_ts))

    # The one-second request is ignored for resume. Segment 2 is already
    # finalized by the client and must not be sent again.
    items = history_items(history.cached_history(2, 1, 1))

    assert [item["segment"] for item in items] == [3, 4]


def test_resume_includes_newer_final_for_same_segment():
    history = FinalHistory()
    history.add(caption(5, 100.0, revision=3))

    items = history_items(history.cached_history(5, 2, 1))

    assert [(item["segment"], item["revision"]) for item in items] == [(5, 3)]


def test_empty_history_serializes_valid_json():
    message = FinalHistory().history_msg(())

    assert message == '{"type":"HISTORY","items":[]}'
    assert json.loads(message) == {"type": "HISTORY", "items": []}


def test_history_msg_only_constructs_from_selected_items():
    final = caption(4, 100.0)

    message = FinalHistory.history_msg((final,))

    assert history_items(message) == [json.loads(final.wire)]


def test_history_for_returns_selected_caption_objects():
    history = FinalHistory()
    first = caption(1, 100.0)
    second = caption(2, 110.0)
    history.add(first)
    history.add(second)

    assert history.history_for(0, 0, 60) == (first, second)


def test_cached_history_reuses_encoded_message_until_history_changes(monkeypatch):
    history = FinalHistory()
    history.add(caption(1, 100.0))
    original = history.history_msg
    calls = 0

    def counted(items):
        nonlocal calls
        calls += 1
        return original(items)

    monkeypatch.setattr(history, "history_msg", counted)

    first = history.cached_history(0, 0, 60)
    second = history.cached_history(0, 0, 60)
    assert first == second
    assert calls == 1

    history.add(caption(2, 101.0))
    history.cached_history(0, 0, 60)
    assert calls == 2


def test_history_message_cache_is_lru_bounded():
    history = FinalHistory()
    history.add(caption(1, 100.0))

    for segment in range(1, 65):
        history.cached_history(segment, 0, 60)

    # Touch the oldest entry, making the second entry the eviction target.
    history.cached_history(1, 0, 60)
    history.cached_history(65, 0, 60)

    assert len(history._message_cache) == 64
    assert history._message_cache.bytes_used <= 8 * 1024 * 1024
    assert (1, 0, 60.0) in history._message_cache._items
    assert (2, 0, 60.0) not in history._message_cache._items


def test_history_message_cache_rejects_oversized_messages():
    history = FinalHistory()
    history._message_cache.max_bytes = 1
    history.add(caption(1, 100.0))

    history.cached_history(0, 0, 60)

    assert len(history._message_cache) == 0
    assert history._message_cache.bytes_used == 0
