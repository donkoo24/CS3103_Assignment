"""Bounded overload behavior and best-effort POSIX startup scaling."""

from __future__ import annotations

import logging
from collections import deque
from enum import Enum

from .config import CONFIG, Config


class Action(Enum):
    KEEP = "keep"
    CLOSE_1013 = "close_1013"


def on_backlog(session_stats, finals_cap=None):
    cap = CONFIG.finals_cap if finals_cap is None else finals_cap
    if (
        session_stats.get("overflowed", False)
        or session_stats.get("pending_finals", 0) > cap
        or session_stats.get("pending", 0) > 2 * cap
    ):
        return Action.CLOSE_1013
    return Action.KEEP


def apply_startup_limits(config: Config = CONFIG):
    try:
        import resource

        soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
        if soft != hard:
            resource.setrlimit(resource.RLIMIT_NOFILE, (hard, hard))
    except (ImportError, OSError, ValueError) as exc:
        logging.getLogger(__name__).warning("Could not raise file limit: %s", exc)
    return config.serve_kwargs()


class FifoMailbox:
    """Comparison baseline: no coalescing, batching, or priority changes.

    At most finals_cap pending finals and 2*finals_cap total entries, plus
    one frame in the writer. Overflow closes/resumes rather than dropping finals.
    """

    def __init__(self, finals_cap=512):
        if finals_cap < 1:
            raise ValueError("finals_cap must be positive")
        self.finals_cap = finals_cap
        self._queue = deque()
        self._final_count = 0
        self.overflowed = False
        self.coalesced = 0

    def push(self, segment, final, wire):
        if self.overflowed:
            return False
        if len(self._queue) >= 2 * self.finals_cap or (
            final and self._final_count >= self.finals_cap
        ):
            self.overflowed = True
            self._queue.clear()
            self._final_count = 0
            return False
        self._queue.append((final, wire))
        self._final_count += bool(final)
        return True

    def pop(self):
        if not self._queue:
            return None
        final, wire = self._queue.popleft()
        self._final_count -= bool(final)
        return wire

    def __len__(self):
        return len(self._queue)
