"""Central time source.

A single indirection over ``datetime.now`` so that:
  * tests can freeze/advance time deterministically, and
  * the live simulator can optionally run on an accelerated clock for demos.

All persisted timestamps are timezone-aware UTC.
"""
from __future__ import annotations

from datetime import datetime, timezone


class Clock:
    """Wall-clock time source (UTC). Override ``now`` in tests."""

    def now(self) -> datetime:
        return datetime.now(timezone.utc)


class FrozenClock(Clock):
    """Deterministic clock for tests; time only moves when advanced explicitly."""

    def __init__(self, start: datetime):
        self._now = start if start.tzinfo else start.replace(tzinfo=timezone.utc)

    def now(self) -> datetime:
        return self._now

    def advance(self, seconds: float) -> datetime:
        from datetime import timedelta

        self._now = self._now + timedelta(seconds=seconds)
        return self._now


# Process-wide default clock. Swappable via ``set_clock`` (used by tests).
_clock: Clock = Clock()


def get_clock() -> Clock:
    return _clock


def set_clock(clock: Clock) -> None:
    global _clock
    _clock = clock


def now() -> datetime:
    return _clock.now()
