"""Sim clock and timer queue. Events fire strictly in time order (ties: in scheduling order)."""

import heapq
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from itertools import count


@dataclass(order=True)
class Timer:
    at: datetime
    seq: int
    kind: str = field(compare=False)
    request_id: str | None = field(compare=False, default=None)
    payload: dict = field(compare=False, default_factory=dict)
    cancelled: bool = field(compare=False, default=False)


Handler = Callable[[Timer], None]


class Clock:
    def __init__(self, now: datetime):
        self.now = now
        self._queue: list[Timer] = []
        self._seq = count()

    def schedule(self, at: datetime, kind: str, request_id: str | None = None, payload: dict | None = None) -> Timer:
        timer = Timer(at, next(self._seq), kind, request_id, payload or {})
        heapq.heappush(self._queue, timer)
        return timer

    def cancel(self, timer: Timer) -> None:
        timer.cancelled = True

    def peek(self) -> Timer | None:
        while self._queue and self._queue[0].cancelled:
            heapq.heappop(self._queue)
        return self._queue[0] if self._queue else None

    def pending(self) -> list[Timer]:
        return sorted(t for t in self._queue if not t.cancelled)

    def step(self, handler: Handler) -> Timer | None:
        """Jump to the next event and process only that one."""
        timer = self.peek()
        if timer is None:
            return None
        heapq.heappop(self._queue)
        self.now = max(self.now, timer.at)
        handler(timer)
        return timer

    def advance(self, minutes: float, handler: Handler) -> list[Timer]:
        """Process every event up to now + minutes, including ones scheduled along the way."""
        target = self.now + timedelta(minutes=minutes)
        fired = []
        while (timer := self.peek()) is not None and timer.at <= target:
            fired.append(self.step(handler))
        self.now = target
        return fired
