import asyncio
from unittest.mock import patch

import pytest

from liverecall.config import load_from_env
from liverecall.hub import Hub
from liverecall.policy import Action, FifoMailbox, apply_startup_limits, on_backlog


def test_config():
    config = load_from_env(
        {"LR_DELIVERY": "fifo", "LR_COMPRESSION": "deflate", "LR_FINALS_CAP": "2"}
    )
    assert config.delivery_config().delivery == "fifo"
    assert config.finals_cap == 2
    assert config.serve_kwargs()["backlog"] == 4096
    assert config.compression == "deflate"


@pytest.mark.parametrize(
    "key,value",
    [
        ("LR_WRITE_LIMIT", "0"),
        ("LR_MAX_QUEUE", "-1"),
        ("LR_FINALS_CAP", "nan"),
        ("LR_COMPRESSION", "brotli"),
        ("LR_DELIVERY", "other"),
    ],
)
def test_invalid_config(key, value):
    with pytest.raises(ValueError):
        load_from_env({key: value})


def test_fifo_order_and_bounds():
    box = FifoMailbox(2)
    for final, wire in [(False, "p1"), (False, "p2"), (True, "f1"), (True, "f2")]:
        assert box.push(1, final, wire)
    assert [box.pop() for _ in range(4)] == ["p1", "p2", "f1", "f2"]
    assert box.pop() is None
    assert box.push(1, True, "a")
    assert box.push(2, True, "b")
    assert not box.push(3, True, "c")
    assert len(box) == 0 and box.overflowed
    box = FifoMailbox(1)
    assert box.push(1, False, "a") and box.push(1, False, "b")
    assert not box.push(1, False, "c")


def test_policy_and_startup():
    assert on_backlog({"pending_finals": 3}, 2) is Action.CLOSE_1013
    assert on_backlog({"pending_finals": 2}, 2) is Action.KEEP
    assert on_backlog({"pending": 5}, 2) is Action.CLOSE_1013
    with (
        patch("resource.getrlimit", return_value=(1024, 4096)),
        patch("resource.setrlimit") as set_limit,
    ):
        assert apply_startup_limits()["backlog"] == 4096
        set_limit.assert_called_once()
    with patch("resource.getrlimit", side_effect=OSError("denied")):
        assert apply_startup_limits()["backlog"] == 4096


def test_hub_fifo_preserves_revisions_without_probes_and_closes_overflow():
    from types import SimpleNamespace

    class Socket:
        def __init__(self):
            self.sent = []
            self.closed = None

        async def send(self, wire):
            self.sent.append(wire)

        async def close(self, code, reason):
            self.closed = code

    async def scenario():
        hub = Hub(
            load_from_env(
                {"LR_DELIVERY": "fifo", "LR_FINALS_CAP": "2"}
            ).delivery_config()
        )
        ws = Socket()
        session = hub.register(ws, 1, ["history"])
        for wire in ("p1", "p2", "final"):
            hub.publish(SimpleNamespace(segment=1, final=wire == "final", wire=wire))
        await asyncio.sleep(0.02)
        assert ws.sent == ["history", "p1", "p2", "final"]
        for segment in range(3):
            hub.publish(SimpleNamespace(segment=segment, final=True, wire="final"))
        await asyncio.sleep(0.02)
        assert ws.closed == 1013 and session not in hub.sessions

    asyncio.run(scenario())
