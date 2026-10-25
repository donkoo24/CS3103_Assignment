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
    assert history_items(history.history_msg(0, 0, 60)) == []


def test_duplicate_final_is_stored_only_once():
    history = FinalHistory()
    final = caption(1, 100.0, revision=3)

    history.add(final)
    history.add(final)
    history.add(caption(1, 101.0, revision=4))

    assert len(history) == 1
    assert history_items(history.history_msg(0, 0, 60)) == [
        json.loads(final.wire)
    ]


def test_history_is_oldest_to_newest_and_final_only():
    history = FinalHistory()
    history.add(caption(3, 102.0))
    history.add(caption(1, 100.0))
    history.add(caption(2, 101.0, final=False))
    history.add(caption(2, 101.0))

    items = history_items(history.history_msg(0, 0, 60))

    assert [item["segment"] for item in items] == [1, 2, 3]
    assert all(item["final"] is True for item in items)


def test_history_keeps_segment_order_for_non_monotonic_insertions():
    history = FinalHistory()
    history.add(caption(3, 100.0))
    history.add(caption(1, 102.0))
    history.add(caption(2, 101.0))

    items = history_items(history.history_msg(0, 0, 60))

    assert [item["segment"] for item in items] == [1, 2, 3]


def test_time_pruning_uses_newest_source_timestamp():
    history = FinalHistory(max_seconds=10)
    history.add(caption(1, 99.0))
    history.add(caption(2, 109.9))
    history.add(caption(3, 110.0))

    assert [item["segment"] for item in history_items(
        history.history_msg(0, 0, 60)
    )] == [2, 3]


def test_count_pruning_removes_oldest_entries():
    history = FinalHistory(max_seconds=90, max_items=2)
    for segment in range(1, 4):
        history.add(caption(segment, 100.0 + segment))

    assert len(history) == 2
    assert [item["segment"] for item in history_items(
        history.history_msg(0, 0, 60)
    )] == [2, 3]


def test_late_join_honors_requested_window_and_caps_at_60_seconds():
    history = FinalHistory()
    for segment, source_ts in enumerate((0.0, 20.0, 40.0, 70.0), start=1):
        history.add(caption(segment, source_ts))

    # The newest source timestamp is 70, so a 30-second request starts at 40.
    assert [item["segment"] for item in history_items(
        history.history_msg(0, 0, 30)
    )] == [3, 4]

    # A request above 60 seconds is capped to the 60-second late-join window.
    assert [item["segment"] for item in history_items(
        history.history_msg(0, 0, 999)
    )] == [2, 3, 4]


def test_resume_uses_full_60_second_window_and_excludes_existing_finals():
    history = FinalHistory()
    for segment, source_ts in enumerate((0.0, 20.0, 40.0, 70.0), start=1):
        history.add(caption(segment, source_ts))

    # The one-second request is ignored for resume. Segment 2 is already
    # finalized by the client and must not be sent again.
    items = history_items(history.history_msg(2, 1, 1))

    assert [item["segment"] for item in items] == [3, 4]


def test_resume_includes_newer_final_for_same_segment():
    history = FinalHistory()
    history.add(caption(5, 100.0, revision=3))

    items = history_items(history.history_msg(5, 2, 1))

    assert [(item["segment"], item["revision"]) for item in items] == [(5, 3)]


def test_empty_history_serializes_valid_json():
    message = FinalHistory().history_msg(0, 0, 30)

    assert message == '{"type":"HISTORY","items":[]}'
    assert json.loads(message) == {"type": "HISTORY", "items": []}
