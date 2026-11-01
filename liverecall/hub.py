"""Fan-out of accepted captions to many WebSocket clients.

``Hub.publish()`` is synchronous and never awaits network I/O: it pushes the
caption into every client's :class:`Mailbox` and wakes that client's writer
task. Each client has exactly one writer task, so a slow or stalled socket only
ever delays its own writer (slow-client isolation).

Lag detection uses returned pings as transport progress markers. Healthy
clients receive every revision. A delayed probe switches that connection to
one unacknowledged frame, holds provisional traffic, and batches pending finals.
A large delay relative to the best observed RTT enables conservative reader
pacing, retained through the recovery hold. This is a heuristic, not an
application acknowledgement: a peer library may still buffer unread messages.

The lag threshold is capped so congestion at connection startup cannot become
an unlimited baseline. Small transport buffers and negotiated compression reduce
shared bandwidth pressure. On Linux, a message and its immediate ping share one
brief TCP_CORK scope, flushed at the next event-loop yield or on scope exit.

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
from .policy import Action, FifoMailbox, on_backlog

log = logging.getLogger("liverecall.hub")


class Publishable(Protocol):
    """What the hub needs from a caption (``liverecall.protocol.Caption``)."""

    segment: int
    final: bool
    wire: str  # pre-encoded CAPTION_UPDATE JSON, shared by all clients


@dataclass(frozen=True)
class DeliveryConfig:
    delivery: str = "semantic"
    finals_cap: int = 512  # pending finals per client before forcing a resync
    write_limit: int = 1024  # asyncio write-buffer high-water mark (bytes)
    notsent_lowat: int = 1024  # kernel unsent-bytes limit (bytes), 0 = off
    probe_interval: float = 1.0  # probe at least this often (s) ...
    window: int = 32  # ... and every window/2 frames; max unacknowledged frames
    lag_min: float = 1.0
    lag_max: float = 1.0  # cap when the connection starts congested
    hold_factor: float = 10.0  # degraded hold = hold_factor x time stuck ...
    hold_min: float = 2.0  # ... clamped to [hold_min, hold_max] ...
    hold_max: float = 120.0  # ... and doubled for every repeated strike
    strike_decay: float = 60.0  # lag-free seconds that forgive one strike
    reader_batch_gap: float = 1.5  # seconds between degraded reader batches
    idle_flush_delay: float = 0.5  # bounded wait for finals after source silence


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
        self.mailbox = (FifoMailbox(self.cfg.finals_cap) if self.cfg.delivery == "fifo"
                        else Mailbox(self.cfg.finals_cap))
        self._window = self.cfg.window
        self.sent = 0  # frames sent (one WebSocket message each)
        self._acked = 0  # frames acknowledged by a returned probe
        self._probe_frame = 0  # self.sent when the outstanding probe was sent
        self.lag_events = 0
        self.min_rtt = math.inf
        self._loop = asyncio.get_running_loop()
        self._wake = asyncio.Event()
        self._last_send = -math.inf
        self._last_offer = -math.inf
        self._probe: asyncio.Future[float] | None = None
        self._probe_sent = -math.inf
        self._probe_lagged = False
        self._strikes = 0
        self._last_strike = -math.inf
        self._degraded_until = -math.inf
        self._catchup = False
        self._batch_gap = 0.0  # > 0 while finals must be batched (slow reader)
        self._retry_at: float | None = None  # when a throttled frame may go
        _limit_buffers(ws, self.cfg)
        self.task = asyncio.create_task(self._run(list(first_messages)))

    # Called synchronously by Hub.publish().
    def offer(self, caption: Publishable) -> None:
        self._last_offer = self._loop.time()
        accepted = self.mailbox.push(caption.segment, caption.final, caption.wire)
        action = on_backlog({"overflowed": not accepted, "pending": len(self.mailbox)},
                            self.cfg.finals_cap)
        if action is Action.KEEP:
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
                    # Woken by publish(), by a pong, or when a throttle expires.
                    self._wake.clear()
                    timeout = None
                    if self._retry_at is not None:
                        timeout = max(0.0, self._retry_at - self._loop.time())
                    try:
                        await asyncio.wait_for(self._wake.wait(), timeout)
                    except asyncio.TimeoutError:  # noqa: UP041 - distinct on 3.10
                        pass
                    continue
                with _coalesce_writes(self.ws):
                    await self.ws.send(msg)
                    self.sent += 1
                    self._last_send = self._loop.time()
                    if self.cfg.delivery != "fifo":
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
        self._retry_at = None
        mb = self.mailbox
        if self.cfg.delivery == "fifo":
            return mb.pop()
        if not len(mb):
            return None
        now = self._loop.time()
        idle_at = self._last_offer + self.cfg.idle_flush_delay
        overdue = self._probe_overdue(now)
        if overdue and not self._probe_lagged:
            self._probe_lagged = True
            self._strike(now)
        # A quiet source cannot supersede its durable finals. Allow one extra
        # final batch beyond the usual window, never an unbounded bypass.
        if mb.has_final and now >= idle_at and self.sent - self._acked < self._window + 1:
            self._catchup = False
            return self._batch_finals()
        if overdue or (self._probe is not None and self.sent - self._acked >= self._window):
            if mb.has_final and idle_at > now:
                self._retry_at = idle_at
            return None
        degraded = now < self._degraded_until
        if not degraded:
            self._window = self.cfg.window
        if mb.has_final:
            if self._catchup or degraded:
                ready_at = self._last_send + (0.0 if self._catchup else self._batch_gap)
                if now < ready_at:
                    self._retry_at = min(ready_at, idle_at) if idle_at > now else ready_at
                    return None
                self._catchup = False
                return self._batch_finals()
            return mb.pop_final()
        self._catchup = False
        if degraded:
            # Spend the measured slow reader capacity on durable finals.
            # New provisionals still coalesce and resume after recovery.
            self._retry_at = self._degraded_until
            return None
        return mb.pop_provisional()

    def _batch_finals(self) -> str:
        finals = self.mailbox.pop_finals()
        if len(finals) == 1:
            return finals[0]
        return '{"type":"HISTORY","items":[' + ",".join(finals) + "]}"

    def _lag_threshold(self) -> float:
        if math.isinf(self.min_rtt):
            return self.cfg.lag_min
        return min(self.cfg.lag_max, max(self.cfg.lag_min, 3.0 * self.min_rtt))

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
        self._window = min(self._window, 1)
        self.lag_events += 1
        self.hub.lag_events += 1

    async def _maybe_probe(self) -> None:
        if self._probe is not None:
            return
        now = self._loop.time()
        due = now - self._probe_sent >= self.cfg.probe_interval
        if due or self.sent - self._acked >= self._window // 2:
            self._probe_sent = now
            self._probe_frame = self.sent
            self._probe_lagged = False
            self._probe = await self.ws.ping()
            self._probe.add_done_callback(self._on_pong)

    def _on_pong(self, fut: asyncio.Future[float]) -> None:
        self._probe = None
        if fut.cancelled() or fut.exception() is not None:
            return  # connection closing
        latency = fut.result()
        self._acked = self._probe_frame
        if not self._probe_lagged and latency >= self._lag_threshold():
            self._probe_lagged = True  # late, though nobody was waiting on it
            self._strike(self._loop.time())
        self.min_rtt = min(self.min_rtt, latency)
        if self._probe_lagged:
            # The client has just read up to the probe: deliver what it missed
            # in one frame, then stay degraded for a hold proportional to how
            # long it was stuck so its remaining backlog drains instead of
            # being topped up again.
            self._catchup = True
            stuck = self._loop.time() - self._probe_sent
            cfg = self.cfg
            previous_gap = self._batch_gap if self._loop.time() < self._degraded_until else 0.0
            # A network RTT is not an application read interval. Only infer
            # reader pacing from a large delay above the best observed RTT.
            reader_lag = latency > max(2.0, 8.0 * self.min_rtt)
            self._batch_gap = max(previous_gap, cfg.reader_batch_gap if reader_lag else 0.0)
            hold = min(cfg.hold_max, max(cfg.hold_min, cfg.hold_factor * stuck))
            hold = min(cfg.hold_max, hold * 2 ** (self._strikes - 1))
            self._degraded_until = self._loop.time() + hold
        self._wake.set()


class Hub:
    def __init__(self, config: DeliveryConfig | None = None) -> None:
        if config is None:
            from .config import load_from_env
            config = load_from_env().delivery_config()
        self.config = config
        self.sessions: set[Session] = set()
        self.lag_events = 0
        self.overflows = 0
        self._final_gap = math.inf  # EWMA of seconds between finals
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
            if not math.isinf(self._last_final):
                gap = now - self._last_final
                old = self._final_gap
                self._final_gap = gap if math.isinf(old) else old + 0.2 * (gap - old)
            self._last_final = now
        for session in tuple(self.sessions):  # offer() may unregister
            session.offer(caption)

    @property
    def finals_rate(self) -> float:
        """Finals per second recently published (0 until two are seen)."""
        return 1.0 / self._final_gap if self._final_gap > 0 else math.inf

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


@contextlib.contextmanager
def _coalesce_writes(ws):
    """Flush a caption and its immediate probe together, never across a yield."""
    transport = getattr(ws, "transport", None)
    sock = transport.get_extra_info("socket") if transport is not None else None
    option = getattr(socket, "TCP_CORK", None)
    enabled = False
    if sock is not None and option is not None:
        try:
            sock.setsockopt(socket.IPPROTO_TCP, option, 1)
            enabled = True
        except OSError:
            pass

    def flush():
        if enabled:
            with contextlib.suppress(OSError):
                sock.setsockopt(socket.IPPROTO_TCP, option, 0)

    handle = asyncio.get_running_loop().call_soon(flush) if enabled else None
    try:
        yield
    finally:
        if handle is not None:
            handle.cancel()
        flush()
