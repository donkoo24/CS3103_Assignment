import asyncio
import json
import time
from dataclasses import dataclass

import websockets

from liverecall.hub import DeliveryConfig, Hub

FAST = DeliveryConfig(
    probe_interval=0.0, lag_min=0.05, hold_min=0.3, hold_factor=0.0, reader_batch_gap=0.0
)


@dataclass(frozen=True)
class Cap:
    segment: int
    revision: int
    final: bool

    @property
    def wire(self):
        return json.dumps(
            {"segment": self.segment, "revision": self.revision, "final": self.final}
        )


class FakeWS:
    """Stands in for a websockets connection; sends block while `gate` is clear."""

    def __init__(self, answer_pings=True):
        self.sent = []
        self.gate = asyncio.Event()
        self.gate.set()
        self.answer_pings = answer_pings
        self.pings = []
        self.closed = None

    async def send(self, msg):
        await self.gate.wait()
        self.sent.append(json.loads(msg))

    async def ping(self):
        fut = asyncio.get_running_loop().create_future()
        if self.answer_pings:
            fut.set_result(0.001)
        self.pings.append(fut)
        return fut

    async def close(self, code, reason):
        self.closed = (code, reason)


def revisions(segments, per_segment=3):
    for seg in range(1, segments + 1):
        for rev in range(1, per_segment + 1):
            yield Cap(seg, rev, rev == per_segment)


async def settle(seconds=0.05):
    await asyncio.sleep(seconds)


def keys(msgs):
    return [(m["segment"], m["revision"]) for m in msgs]


def test_history_first_then_every_revision_in_order():
    async def main():
        hub, ws = Hub(FAST), FakeWS()
        hub.register(ws, 1, ['{"type":"HISTORY","items":[]}'])
        for cap in revisions(3):
            hub.publish(cap)
            await settle(0.005)
        await settle()
        assert ws.sent[0] == {"type": "HISTORY", "items": []}
        assert keys(ws.sent[1:]) == [(c.segment, c.revision) for c in revisions(3)]

    asyncio.run(main())


def test_blocked_client_coalesces_to_finals_plus_newest_provisional():
    async def main():
        hub, ws = Hub(FAST), FakeWS()
        ws.gate.clear()  # network stalled: send() blocks
        hub.register(ws, 1)
        hub.publish(Cap(1, 1, False))
        await settle()  # writer is now blocked inside send(1,1)
        for cap in [*revisions(4)][1:]:
            hub.publish(cap)
        hub.publish(Cap(5, 1, False))
        hub.publish(Cap(5, 2, False))
        ws.gate.set()
        await settle()
        assert keys(ws.sent) == [(1, 1), (1, 3), (2, 3), (3, 3), (4, 3), (5, 2)]
        assert hub.stats()["coalesced"] >= 6

    asyncio.run(main())


def test_stuck_client_gets_held_finals_as_one_history_frame():
    async def main():
        hub, ws = Hub(FAST), FakeWS(answer_pings=False)
        session = hub.register(ws, 1)
        hub.publish(Cap(1, 1, False))  # sent; probe goes out, never answered
        await settle(0.1)  # probe is now overdue: the client is behind
        for cap in [*revisions(3)][1:]:
            hub.publish(cap)
        hub.publish(Cap(4, 1, False))
        await settle()
        assert keys(ws.sent) == [(1, 1)]  # stuck: nothing sent, all held
        assert session.degraded and hub.lag_events == 1

        ws.answer_pings = True  # subsequent catch-up frames are acknowledged
        ws.pings[0].set_result(1.0)  # client has now read up to the probe
        await settle()
        catchup = ws.sent[1]
        assert catchup["type"] == "HISTORY"
        assert keys(catchup["items"]) == [(1, 3), (2, 3), (3, 3)]
        assert session.degraded and len(ws.sent) == 2  # provisional held back
        await settle(FAST.hold_min + 0.05)
        assert keys(ws.sent[2:]) == [(4, 1)]  # newest provisional released

    asyncio.run(main())


def test_reader_slower_than_finals_rate_gets_batched_finals():
    async def main():
        cfg = DeliveryConfig(
            probe_interval=0.0, lag_min=0.05, hold_min=5.0, reader_batch_gap=0.0
        )
        hub, ws = Hub(cfg), FakeWS(answer_pings=False)
        hub.register(ws, 1)
        hub._final_gap = 0.1  # finals arrive every 0.1 s
        hub.publish(Cap(1, 1, False))
        await settle(0.1)  # stuck long enough: reads take ~0.1 s per frame
        ws.answer_pings = True
        hub.publish(Cap(1, 2, True))
        ws.pings[0].set_result(0.2)
        await settle()
        assert keys(ws.sent) == [(1, 1), (1, 2)]  # catch-up frame
        for seg in (2, 3, 4):
            hub.publish(Cap(seg, 1, True))
        await settle(0.5)  # batched: one frame instead of three
        assert len(ws.sent) == 3 and ws.sent[2]["type"] == "HISTORY"
        assert keys(ws.sent[2]["items"]) == [(2, 1), (3, 1), (4, 1)]

    asyncio.run(main())


def test_unacknowledged_frames_are_capped_by_the_window():
    async def main():
        cfg = DeliveryConfig(window=8, lag_min=60.0)  # isolate the window
        hub, ws = Hub(cfg), FakeWS(answer_pings=False)
        hub.register(ws, 1)
        for cap in revisions(10):  # 30 frames' worth, one by one
            hub.publish(cap)
            await settle(0.002)
        await settle()
        assert len(ws.sent) == 8  # then held until a pong acknowledges them
        assert hub.lag_events == 0  # a full window alone is not a strike
        for fut in ws.pings:
            fut.set_result(0.001)
        await settle()
        assert len(ws.sent) > 8  # resumes after the acknowledgement

    asyncio.run(main())


def test_overflow_closes_client_for_resync():
    async def main():
        hub = Hub(DeliveryConfig(finals_cap=3))
        ws = FakeWS()
        ws.gate.clear()
        hub.register(ws, 1)
        for seg in range(1, 6):
            hub.publish(Cap(seg, 1, True))
        await settle()
        assert ws.closed == (1013, "resync")
        assert hub.stats() | {"overflows": 1} == hub.stats()
        assert not hub.sessions

    asyncio.run(main())


def test_unregister_cancels_writer():
    async def main():
        hub, ws = Hub(FAST), FakeWS()
        session = hub.register(ws, 1)
        hub.unregister(session)
        await settle()
        assert session.task.cancelled() and not hub.sessions
        hub.publish(Cap(1, 1, True))  # no session left: nothing to do

    asyncio.run(main())


def test_real_sockets_stalled_reader_does_not_delay_normal_reader():
    """End-to-end over real WebSockets: a client that stops reading is
    detected via the ping probe while a normal client stays fresh."""

    async def main():
        cfg = DeliveryConfig(probe_interval=0.05, lag_min=0.2)
        hub = Hub(cfg)

        async def handler(ws):
            session = hub.register(ws, id(ws))
            try:
                async for _ in ws:
                    pass
            finally:
                hub.unregister(session)

        async with websockets.serve(handler, "127.0.0.1", 0) as server:
            port = server.sockets[0].getsockname()[1]
            uri = f"ws://127.0.0.1:{port}"
            async with (
                websockets.connect(uri) as fast,
                websockets.connect(uri, close_timeout=0.1),
            ):
                await settle(0.1)
                latencies = []
                for cap in revisions(40):
                    sent_at = time.perf_counter()
                    hub.publish(cap)
                    json.loads(await asyncio.wait_for(fast.recv(), 1))
                    latencies.append(time.perf_counter() - sent_at)
                    await asyncio.sleep(0.01)
                assert max(latencies) < 0.1
                assert hub.lag_events >= 1  # the silent client was detected
                stalled = next(s for s in hub.sessions if s.lag_events)
                assert len(stalled.mailbox) <= 40  # bounded: finals + 1 slot

    asyncio.run(main())


def test_congested_initial_rtt_does_not_disable_lag_detection():
    async def main():
        hub, ws = Hub(), FakeWS()
        session = hub.register(ws, 1)
        session.min_rtt = 5.0
        assert session._lag_threshold() <= hub.config.lag_max
        hub.unregister(session)
        await settle()

    asyncio.run(main())


def test_lagged_reader_reserves_capacity_for_finals_then_resumes_revisions():
    async def main():
        hub, ws = Hub(FAST), FakeWS()
        session = hub.register(ws, 1)
        session._degraded_until = asyncio.get_running_loop().time() + 0.2
        session._batch_gap = 0.02
        hub.publish(Cap(1, 1, True))
        hub.publish(Cap(2, 1, False))
        await settle(0.08)
        assert keys(ws.sent) == [(1, 1)]
        hub.publish(Cap(2, 2, False))
        hub.publish(Cap(3, 1, True))
        await settle(0.05)
        assert keys(ws.sent) == [(1, 1), (3, 1)]
        await settle(0.15)
        assert keys(ws.sent)[-1] == (2, 2)
        hub.unregister(session)
        await settle()

    asyncio.run(main())


def test_lagged_reader_batches_even_when_recent_final_rate_is_low():
    async def main():
        hub, ws = Hub(DeliveryConfig(lag_min=0.05, probe_interval=0.0)), FakeWS(answer_pings=False)
        session = hub.register(ws, 1)
        hub._final_gap = 100.0
        session.min_rtt = 0.001
        hub.publish(Cap(1, 1, False))
        await settle(0.1)
        ws.pings[0].set_result(3.0)
        await settle(0.01)
        assert session._batch_gap > 0
        hub.unregister(session)
        await settle()

    asyncio.run(main())


def test_packet_coalescing_flushes_before_wait_and_on_exception():
    import socket
    from types import SimpleNamespace
    from unittest.mock import Mock
    from liverecall.hub import _coalesce_writes

    if not hasattr(socket, 'TCP_CORK'):
        return

    async def main():
        sock = Mock()
        ws = SimpleNamespace(transport=SimpleNamespace(get_extra_info=lambda _: sock))
        with _coalesce_writes(ws):
            assert sock.setsockopt.call_args.args[-1] == 1
            await asyncio.sleep(0)
            assert sock.setsockopt.call_args.args[-1] == 0
        try:
            with _coalesce_writes(ws):
                raise RuntimeError('cancel send')
        except RuntimeError:
            pass
        assert sock.setsockopt.call_args.args[-1] == 0

    asyncio.run(main())
