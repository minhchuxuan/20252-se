"""Time helpers: billing-cycle and day boundaries (UTC, timezone-aware)."""
from __future__ import annotations

from calendar import monthrange
from datetime import datetime, timedelta, timezone


def start_of_day(ts: datetime) -> datetime:
    return ts.replace(hour=0, minute=0, second=0, microsecond=0)


def current_billing_cycle(ts: datetime, billing_day: int = 1) -> tuple[datetime, datetime]:
    """Return [start, end) of the billing cycle containing ``ts``.

    The cycle starts on ``billing_day`` of the month (clamped to month length).
    """
    def clamp_day(year: int, month: int, day: int) -> datetime:
        last = monthrange(year, month)[1]
        return datetime(year, month, min(day, last), tzinfo=timezone.utc)

    this_month_start = clamp_day(ts.year, ts.month, billing_day)
    if ts >= this_month_start:
        start = this_month_start
        ny, nm = (ts.year + 1, 1) if ts.month == 12 else (ts.year, ts.month + 1)
        end = clamp_day(ny, nm, billing_day)
    else:
        py, pm = (ts.year - 1, 12) if ts.month == 1 else (ts.year, ts.month - 1)
        start = clamp_day(py, pm, billing_day)
        end = this_month_start
    return start, end


def days_in_cycle(start: datetime, end: datetime) -> float:
    return (end - start).total_seconds() / 86400.0


def hour_set_from_window(start_hm: str, end_hm: str) -> set[int]:
    """Hours (of-day) touched by a 'HH:MM'-'HH:MM' window (wraps midnight).

    Computed from the actual minute boundaries so a sub-hour window such as
    09:30-09:45 maps to {9} rather than the whole day. An empty/identical window
    (start == end) is treated as the full day.
    """
    sm = int(start_hm.split(":")[0]) * 60 + int(start_hm.split(":")[1])
    em = int(end_hm.split(":")[0]) * 60 + int(end_hm.split(":")[1])
    if sm == em:
        return set(range(24))
    if sm < em:
        return {(m // 60) for m in range(sm, em)}
    # wraps midnight
    return {(m // 60) for m in range(sm, 24 * 60)} | {(m // 60) for m in range(0, em)}
