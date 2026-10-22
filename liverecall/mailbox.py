"""Per-client semantic mailbox: the bounded outbound buffer of one client.

Finals are durable state: they are queued in arrival order and are never
coalesced or dropped. Provisional revisions are disposable: each unfinished
segment has a single slot, and a newer revision overwrites an older one that
has not been sent yet ("coalescing"). A client that keeps up drains the mailbox
after every push and therefore receives every revision; a client that falls
behind automatically receives every final plus only the newest provisional
state, so it converges immediately once it catches up instead of replaying a
stale backlog.

Bounds (memory never grows with lecture length or client slowness):
  * ``_finals``      <= ``finals_cap`` entries; exceeding it is an overflow.
  * ``_provisional`` <= one entry per unfinished segment.
  * ``_finalized``   <= ``finals_cap`` most recently finalized segment ids.
On overflow the mailbox discards its contents and rejects further pushes; the
caller must resynchronise the client (close it so that it resumes via HISTORY).
"""

from __future__ import annotations

from collections import OrderedDict, deque


class Mailbox:
    __slots__ = (
        "_finalized",
        "_finals",
        "_provisional",
        "coalesced",
        "finals_cap",
        "overflowed",
    )

    def __init__(self, finals_cap: int = 512) -> None:
        if finals_cap < 1:
            raise ValueError("finals_cap must be >= 1")
        self.finals_cap = finals_cap
        self._finals: deque[str] = deque()
        self._provisional: dict[int, str] = {}
        # Segments whose final is queued or sent: a provisional for one of them
        # is obsolete and must never be delivered (it would be a stale update).
        self._finalized: OrderedDict[int, None] = OrderedDict()
        self.overflowed = False
        self.coalesced = 0  # provisional revisions superseded before sending

    def push(self, segment: int, final: bool, wire: str) -> bool:
        """Queue an encoded CAPTION_UPDATE. Returns False once overflowed.

        Callers must push revisions of a segment in increasing order (the
        server's caption state only forwards accepted, newer revisions).
        """
        if self.overflowed:
            return False
        if not final:
            if segment in self._finalized:
                return True  # obsolete: its final is already queued or sent
            if segment in self._provisional:
                self.coalesced += 1
            self._provisional[segment] = wire
            return True

        if self._provisional.pop(segment, None) is not None:
            self.coalesced += 1
        self._finalized[segment] = None
        if len(self._finalized) > self.finals_cap:
            self._finalized.popitem(last=False)
        self._finals.append(wire)
        if len(self._finals) > self.finals_cap:
            self.overflowed = True
            self._finals.clear()
            self._provisional.clear()
            return False
        return True

    def pop_final(self) -> str | None:
        """Oldest pending final, if any."""
        return self._finals.popleft() if self._finals else None

    def pop_finals(self) -> list[str]:
        """All pending finals, oldest first (for one batched frame)."""
        finals = list(self._finals)
        self._finals.clear()
        return finals

    def pop_provisional(self) -> str | None:
        """Newest pending revision of the oldest unfinished segment, if any."""
        if not self._provisional:
            return None
        segment = next(iter(self._provisional))
        return self._provisional.pop(segment)

    def pop(self) -> str | None:
        """Next message in delivery order: finals first, then provisionals."""
        return self.pop_final() or self.pop_provisional()

    @property
    def has_final(self) -> bool:
        return bool(self._finals)

    @property
    def has_provisional(self) -> bool:
        return bool(self._provisional)

    def __len__(self) -> int:
        return len(self._finals) + len(self._provisional)
