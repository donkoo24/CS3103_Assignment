import asyncio
import json

import solution_server
from liverecall.history import FinalHistory
from liverecall.protocol import Caption
from liverecall.state import CaptionState
from solution_server import handle_client


def test_revision_state_tracks_bounded_history_without_resurrecting_finals():
    state = CaptionState()
    history = FinalHistory(max_items=4)
    for segment in range(1, 21):
        cap = Caption(segment, 1, float(segment), True, str(segment), "wire")
        assert state.apply(cap)
        history.add(cap)
        state.prune(history.oldest_segment)

    assert history.oldest_segment == 17
    assert set(state.latest) == {17, 18, 19, 20}
    assert not state.apply(Caption(1, 2, 1.0, True, "replay", "wire"))
    assert not state.apply(Caption(20, 2, 20.0, True, "replay", "wire"))
    state.reset()
    assert state.apply(Caption(1, 1, 1.0, False, "new source", "wire"))


def test_bad_client_cursor_closes_with_protocol_error():
    class Socket:
        closed = None

        async def close(self, code, reason):
            self.closed = code

    socket = Socket()
    asyncio.run(handle_client(socket, {"last_segment": ["bad"]}))
    assert socket.closed == 1008


def test_source_pipeline_prunes_revision_state(monkeypatch):
    state = CaptionState()
    history = FinalHistory(max_items=4)

    class Hub:
        def publish(self, cap):
            pass

    class Source:
        async def __aiter__(self):
            for segment in range(1, 21):
                yield json.dumps({
                    "type": "CAPTION_UPDATE", "segment": segment,
                    "revision": 1, "source_ts": float(segment),
                    "final": True, "text": str(segment),
                })

    monkeypatch.setattr(solution_server, "STATE", state)
    monkeypatch.setattr(solution_server, "HISTORY", history)
    monkeypatch.setattr(solution_server, "HUB", Hub())
    asyncio.run(solution_server.handle_source(Source(), {"session": "L1"}))
    assert set(state.latest) == {17, 18, 19, 20}
