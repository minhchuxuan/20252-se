"""Simulated world model: ambient climate + household occupancy schedule.

Deterministic functions of time so that seeded history contains *reproducible*
behaviour patterns the habit miner can detect (e.g. a light left on after the
room becomes empty), and the savings engine has a stable baseline.
"""
from __future__ import annotations

import math
from datetime import datetime


def ambient_temp(ts: datetime) -> float:
    """Outdoor/indoor ambient temperature (°C), warm-climate daily cycle.

    Minimum ~26°C around 05:00, maximum ~34°C around 14:00.
    """
    # Phase so that the trough is at hour 5.
    hour = ts.hour + ts.minute / 60.0
    return 30.0 + 4.0 * math.sin((hour - 9.0) / 24.0 * 2 * math.pi)


# Hours (local) during which the home is EMPTY — occupants out at work/school
# during the day. The home is occupied the rest of the day, INCLUDING overnight
# when people are asleep (consistent with the bedroom AC running through the night).
_EMPTY_HOURS = set(range(9, 17))  # 09:00–17:00 away; home mornings, evenings, overnight


def is_occupied(ts: datetime) -> bool:
    """Deterministic household occupancy schedule (empty only during the working day)."""
    return ts.hour not in _EMPTY_HOURS


def world_context(ts: datetime) -> dict:
    """Context passed to adapters on each tick."""
    return {
        "ambient_temp": ambient_temp(ts),
        "occupied": is_occupied(ts),
        "hour": ts.hour,
        "minute_of_day": ts.hour * 60 + ts.minute,
        "weekday": ts.weekday(),
    }
