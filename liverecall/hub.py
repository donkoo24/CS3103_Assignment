"""Fan-out of accepted captions to many WebSocket clients.

``Hub.publish()`` is synchronous and never awaits network I/O: it pushes the
caption into every client's :class:`Mailbox` and wakes that client's writer
task. Each client has exactly one writer task, so a slow or stalled socket only
ever delays its own writer (slow-client isolation).

Lag detection. Transport backpressure alone cannot see a slow *reader*: its
kernel receive buffer and its WebSocket library queue (16 frames in the
``websockets`` client) absorb the backlog long before our send buffer fills.
Each writer therefore keeps one WebSocket ping in flight as a probe. The peer
reads the ping only after every frame queued in front of it, so an overdue pong
means "this client is behind" (a *strike*). Policy per client:

* stuck (probe overdue): send nothing; anything sent now would only queue
  behind the backlog, so finals accumulate and provisionals coalesce;
* caught up to the probe: flush every held final as ONE ``HISTORY`` frame
  (finalized captions the client is missing, oldest first) - one read for the
  client instead of one per final;
* degraded (a hold of ``hold_factor`` x the time it was stuck, doubled per
  repeated strike): provisionals at most one frame per ``degraded_gap``.
  Finals go out one per frame - unless the client reads slower than finals
  are produced. A saturated reader answers the probe only after draining its
  library queue (16 -> 4 frames for ``websockets``), so its time per read is
  about ``stuck / client_queue_band``. If that is too slow for the measured
  finals rate, its finals are batched, one frame per 1.5 read times, so it
  catches up and stays complete instead of falling further behind;
* otherwise: every revision, immediately.

Bandwidth. Per connection we cap the asyncio write buffer (``write_limit``)
and, on Linux/macOS, the kernel's not-yet-sent bytes (``TCP_NOTSENT_LOWAT``).
When the network is the bottleneck, ``send()`` therefore blocks early and the
backlog builds up in the mailbox, where obsolete provisionals are coalesced,
instead of as stale frames inside buffers we cannot edit.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import math
import socket
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Protocol

from websockets.exceptions import ConnectionClosed

from .mailbox import Mailbox

log = logging.getLogger("liverecall.hub")


class Publishable(Protocol):
    """What the hub needs from a caption (``liverecall.protocol.Caption``)."""

    segment: int
    final: bool
    wire: str  # pre-encoded CAPTION_UPDATE JSON, shared by all clients


@dataclass(frozen=True)
class DeliveryConfig:
    finals_cap: int = 512  # pending finals per client before forcing a resync
    write_limit: int = 4096  # asyncio write-buffer high-water mark (bytes)
    notsent_lowat: int = 16384  # kernel unsent-bytes limit (bytes), 0 = off
    probe_interval: float = 1.0  # min seconds between lag probes per client
    lag_min: float = 1.0  # probe overdue threshold floor (s); else 3 x min RTT
    degraded_gap: float = 1.0  # min seconds between frames for provisionals
    hold_factor: float = 10.0  # degraded hold = hold_factor x time stuck ...
    hold_min: float = 2.0  # ... clamped to [hold_min, hold_max] ...
    hold_max: float = 120.0  # ... and doubled for every repeated strike
    strike_decay: float = 60.0  # lag-free seconds that forgive one strike
    client_queue_band: int = 12  # frames a saturated client reads before a pong
    batch_gap_max: float = 8.0  # cap on the slow-reader finals batch gap


class Session:
    """One connected client: its mailbox, writer task and lag state."""

    def __init__(
        self,
        hub: Hub,
        ws: Any,
        client_id: Any,
        first_messages: Iterable[str],
    ) -> None:
        self.hub = hub
        self.ws = ws
        self.client_id = client_id
        self.cfg = hub.config
        self.mailbox = Mailbox(self.cfg.finals_cap)
        self.sent = 0
        self.lag_events = 0
        self.min_rtt = math.inf
        self._loop = asyncio.get_running_loop()
        self._wake = asyncio.Event()
        self._last_send = -math.inf
        self._probe: asyncio.Future[float] | None = None
        self._probe_sent = -math.inf
        self._probe_lagged = False
        self._strikes = 0
        self._last_strike = -math.inf
        self._degraded_until = -math.inf
        self._catchup = False
        self._batch_gap = 0.0  # > 0 while finals must be batched (slow reader)
        _limit_buffers(ws, self.cfg)
        self.task = asyncio.create_task(self._run(list(first_messages)))

    # Called synchronously by Hub.publish().
    def offer(self, caption: Publishable) -> None:
        if self.mailbox.push(caption.segment, caption.final, caption.wire):
            self._wake.set()
        else:
            self.hub._overflow(self)

    @property
    def degraded(self) -> bool:
        now = self._loop.time()
        return now < self._degraded_until or self._probe_overdue(now)

    async def _run(self, first_messages: list[str]) -> None:
        try:
            for msg in first_messages:  # e.g. HISTORY, before any live update
                await self.ws.send(msg)
            while True:
                msg = self._next()
                if msg is None:
                    # No await between _next() and clear(): no lost wake-up.
                    self._wake.clear()
                    timeout = 0.1 if len(self.mailbox) else None  # throttled
                    try:
                        await asyncio.wait_for(self._wake.wait(), timeout)
                    except asyncio.TimeoutError:  # noqa: UP041 - distinct on 3.10
                        pass
                    continue
                await self.ws.send(msg)
                self.sent += 1
                self._last_send = self._loop.time()
                await self._maybe_probe()
        except ConnectionClosed:
            pass
        except Exception:  # a delivery bug must not silently stall a client
            log.exception("writer for client %s failed", self.client_id)
            await _close_quietly(self.ws, 1011, "internal error")
        finally:
            self.hub.sessions.discard(self)

    def _next(self) -> str | None:
        """Next frame to send, or None to wait. See the module docstring."""
        if not len(self.mailbox):
            return None
        now = self._loop.time()
        if self._probe_overdue(now):
            if not self._probe_lagged:
                self._probe_lagged = True
                self._strike(now)
            return None
        mb = self.mailbox
        degraded = now < self._degraded_until
        if mb.has_final:
            if self._catchup:
                self._catchup = False
                return self._batch_finals()
            if degraded and self._batch_gap:
                if now - self._last_send < self._batch_gap:
                    return None
                return self._batch_finals()
            return mb.pop_final()
        if not degraded or now - self._last_send >= self.cfg.degraded_gap:
            return mb.pop_provisional()
        return None

    def _batch_finals(self) -> str:
        finals = self.mailbox.pop_finals()
        if len(finals) == 1:
            return finals[0]
        return '{"type":"HISTORY","items":[' + ",".join(finals) + "]}"

    def _lag_threshold(self) -> float:
        if math.isinf(self.min_rtt):
            return self.cfg.lag_min
        return max(self.cfg.lag_min, 3.0 * self.min_rtt)

    def _probe_overdue(self, now: float) -> bool:
        return (
            self._probe is not None
            and not self._probe.done()
            and now - self._probe_sent >= self._lag_threshold()
        )

    def _strike(self, now: float) -> None:
        if self._strikes:  # forgive one strike per lag-free strike_decay
            forgiven = int((now - self._last_strike) // self.cfg.strike_decay)
            self._strikes = max(0, self._strikes - forgiven)
        self._strikes += 1
        self._last_strike = now
        self.lag_events += 1
        self.hub.lag_events += 1

    async def _maybe_probe(self) -> None:
        now = self._loop.time()
        if self._probe is None and now - self._probe_sent >= self.cfg.probe_interval:
            self._probe_sent = now
            self._probe_lagged = False
            self._probe = await self.ws.ping()
            self._probe.add_done_callback(self._on_pong)

    def _on_pong(self, fut: asyncio.Future[float]) -> None:
        self._probe = None
        if fut.cancelled() or fut.exception() is not None:
            return  # connection closing
        self.min_rtt = min(self.min_rtt, fut.result())
        if self._probe_lagged:
            # The client has just read up to the probe: deliver what it missed
            # in one frame, then stay degraded for a hold proportional to how
            # long it was stuck so its remaining backlog drains instead of
            # being topped up again.
            self._catchup = True
            stuck = self._loop.time() - self._probe_sent
            cfg = self.cfg
            read_time = stuck / cfg.client_queue_band
            too_slow = read_time * self.hub.finals_rate >= 1.0
            self._batch_gap = (
                min(cfg.batch_gap_max, 1.5 * read_time) if too_slow else 0.0
            )
            hold = min(cfg.hold_max, max(cfg.hold_min, cfg.hold_factor * stuck))
            hold = min(cfg.hold_max, hold * 2 ** (self._strikes - 1))
            self._degraded_until = self._loop.time() + hold
        self._wake.set()


class Hub:
    def __init__(self, config: DeliveryConfig | None = None) -> None:
        self.config = config or DeliveryConfig()
        self.sessions: set[Session] = set()
        self.lag_events = 0
        self.overflows = 0
        self.finals_rate = 0.0  # finals per second (EWMA of inter-final gaps)
        self._last_final = -math.inf
        self._closing: set[asyncio.Task[None]] = set()

    def register(
        self, ws: Any, client_id: Any, first_messages: Iterable[str] = ()
    ) -> Session:
        """Start delivering to ``ws``. Synchronous: call it in the same step as
        the HISTORY snapshot so no update falls between the two."""
        session = Session(self, ws, client_id, first_messages)
        self.sessions.add(session)
        return session

    def unregister(self, session: Session) -> None:
        self.sessions.discard(session)
        if not session.task.done():
            session.task.cancel()

    def publish(self, caption: Publishable) -> None:
        """Hand an accepted caption to every client. Never awaits."""
        if caption.final:
            now = asyncio.get_running_loop().time()
            if not math.isinf(self._last_final) and now > self._last_final:
                rate = 1.0 / (now - self._last_final)
                self.finals_rate += 0.2 * (rate - self.finals_rate)
            self._last_final = now
        for session in tuple(self.sessions):  # offer() may unregister
            session.offer(caption)

    def stats(self) -> dict[str, int]:
        sessions = tuple(self.sessions)
        return {
            "clients": len(sessions),
            "degraded": sum(s.degraded for s in sessions),
            "max_pending": max((len(s.mailbox) for s in sessions), default=0),
            "coalesced": sum(s.mailbox.coalesced for s in sessions),
            "lag_events": self.lag_events,
            "overflows": self.overflows,
        }

    def _overflow(self, session: Session) -> None:
        """A client let ``finals_cap`` finals pile up: drop its backlog and
        close it with 1013 (Try Again Later) so it resumes via HISTORY, which
        delivers everything it missed in one message."""
        self.overflows += 1
        self.unregister(session)
        log.warning("client %s overflowed; closing for resync", session.client_id)
        task = asyncio.ensure_future(_close_quietly(session.ws, 1013, "resync"))
        self._closing.add(task)  # keep a reference until the close completes
        task.add_done_callback(self._closing.discard)


def _limit_buffers(ws: Any, cfg: DeliveryConfig) -> None:
    transport = getattr(ws, "transport", None)
    if transport is None:
        return
    transport.set_write_buffer_limits(high=cfg.write_limit)
    sock = transport.get_extra_info("socket")
    lowat = getattr(socket, "TCP_NOTSENT_LOWAT", None)
    if sock is not None and lowat is not None and cfg.notsent_lowat > 0:
        try:
            sock.setsockopt(socket.IPPROTO_TCP, lowat, cfg.notsent_lowat)
        except OSError:
            pass


async def _close_quietly(ws: Any, code: int, reason: str) -> None:
    with contextlib.suppress(Exception):  # already closing: nothing to recover
        await ws.close(code, reason)
