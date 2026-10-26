"""Time for the whole simulated network.

All services read time from a `Clock`, never from the system directly, so the demo can run RBI's 20-, 30- and
60-day deadlines in minutes. Times are timezone-aware UTC inside Ripple and shown in IST at the edges.
"""

from __future__ import annotations

import threading
import time
from datetime import UTC, datetime, timedelta, timezone
from typing import Protocol

IST = timezone(timedelta(hours=5, minutes=30), "IST")


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class SimClock:
    """A clock that starts at a chosen moment, runs `speed` times faster than real time, and can jump forward.

    Every process on the network builds its clock from the same `start`, `speed` and `real_anchor` (wall-clock
    seconds when the network started), so they all read the same simulated time. Time never goes backwards:
    `advance` only accepts positive steps, `set_speed` keeps the current reading, and a wall clock stepping back
    is ignored.
    """

    def __init__(self, start: datetime, speed: float = 1.0, real_anchor: float | None = None) -> None:
        if start.tzinfo is None:
            raise ValueError("start must be timezone-aware")
        if speed <= 0:
            raise ValueError("speed must be positive")
        self._lock = threading.Lock()
        self._anchor_sim = start.astimezone(UTC)
        self._anchor_real = time.time() if real_anchor is None else real_anchor
        self._speed = speed
        self._last = self._anchor_sim

    def now(self) -> datetime:
        with self._lock:
            return self._reading()

    def advance(self, step: timedelta) -> datetime:
        if step <= timedelta(0):
            raise ValueError("the clock only moves forward")
        with self._lock:
            self._anchor_sim = self._reading() + step
            self._anchor_real = time.time()
            self._last = self._anchor_sim
            return self._anchor_sim

    def set_speed(self, speed: float) -> None:
        if speed <= 0:
            raise ValueError("speed must be positive")
        with self._lock:
            self._anchor_sim = self._reading()
            self._anchor_real = time.time()
            self._speed = speed

    def _reading(self) -> datetime:
        elapsed = (time.time() - self._anchor_real) * self._speed
        self._last = max(self._last, self._anchor_sim + timedelta(seconds=elapsed))
        return self._last


class FixedClock:
    """A clock that only moves when told to; for tests."""

    def __init__(self, at: datetime) -> None:
        if at.tzinfo is None:
            raise ValueError("time must be timezone-aware")
        self._at = at.astimezone(UTC)

    def now(self) -> datetime:
        return self._at

    def advance(self, step: timedelta) -> datetime:
        if step <= timedelta(0):
            raise ValueError("the clock only moves forward")
        self._at += step
        return self._at
