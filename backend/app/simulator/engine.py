"""Mock device simulator (REQ-4.2.5).

Two entry points share the same per-type adapters so live and historical data
are generated consistently:

* ``generate_history`` — pure function that fabricates back-dated telemetry for
  seeding (gives the baseline/habit/savings engines real data to work on).
* ``SimulatorEngine`` — async loop that emits live telemetry at the configured
  cadence, updating device state and publishing TELEMETRY_READING events.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from ..adapters.devices import get_adapter
from ..config import settings
from ..core.clock import now
from ..core.events import EventType, bus
from ..database import SessionLocal
from ..domain.enums import DeviceType
from ..domain.models import Device, Reading
from .world import world_context

logger = logging.getLogger("sheo.simulator")

# A behaviour script returns control overrides (e.g. {"power": "on"}) for time t.
Behavior = Callable[[datetime, dict[str, Any]], dict[str, Any]]


def generate_history(
    device_type: DeviceType,
    initial_state: dict[str, Any],
    start: datetime,
    end: datetime,
    step_seconds: int,
    behavior: Behavior | None = None,
    kwh_start: float = 0.0,
) -> tuple[list[dict[str, Any]], dict[str, Any], float]:
    """Step a device from ``start`` to ``end`` producing reading dicts.

    Returns (readings, final_state, final_kwh_total).
    """
    adapter = get_adapter(device_type)
    state = dict(initial_state)
    kwh_total = kwh_start
    readings: list[dict[str, Any]] = []
    ts = start
    while ts < end:
        ctx = world_context(ts)
        if behavior is not None:
            state.update(behavior(ts, state))
        state = adapter.tick(state, step_seconds, ctx)
        power_w = float(state.get("power_w", 0.0))
        interval = adapter.interval_kwh(power_w, step_seconds)
        kwh_total += interval
        readings.append(
            {
                "ts": ts,
                "power_w": power_w if device_type != DeviceType.SENSOR else None,
                "interval_kwh": interval if device_type != DeviceType.SENSOR else 0.0,
                "kwh_total": kwh_total if device_type != DeviceType.SENSOR else None,
                "temperature": state.get("temperature"),
                "humidity": state.get("humidity"),
                "occupancy": state.get("occupancy"),
            }
        )
        ts += timedelta(seconds=step_seconds)
    return readings, state, kwh_total


class SimulatorEngine:
    """Background async telemetry generator for live mock devices."""

    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._running = False

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._running = True
            self._task = asyncio.create_task(self._run())
            logger.info("simulator started (interval=%.1fs)", settings.telemetry_interval_seconds)

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _run(self) -> None:
        while self._running:
            try:
                self._tick_once()
            except Exception:
                logger.exception("simulator tick failed")
            await asyncio.sleep(settings.telemetry_interval_seconds)

    def _tick_once(self) -> None:
        ts = now()
        ctx = world_context(ts)
        db = SessionLocal()
        try:
            devices = db.query(Device).filter(Device.is_mock.is_(True)).all()
            dt = settings.telemetry_interval_seconds
            for device in devices:
                if device.state.get("forced_offline"):
                    continue  # demo hook: device stops reporting -> offline detection
                adapter = get_adapter(DeviceType(device.type))
                new_state = adapter.tick(dict(device.state or {}), dt, ctx)
                power_w = float(new_state.get("power_w", 0.0))
                interval = adapter.interval_kwh(power_w, dt)
                device.kwh_total = (device.kwh_total or 0.0) + interval
                new_state["power_w"] = power_w
                device.state = new_state
                device.last_seen_at = ts
                device.online = True
                reading = Reading(
                    device_id=device.id,
                    ts=ts,
                    power_w=power_w if device.type != DeviceType.SENSOR else None,
                    interval_kwh=interval if device.type != DeviceType.SENSOR else 0.0,
                    kwh_total=device.kwh_total if device.type != DeviceType.SENSOR else None,
                    temperature=new_state.get("temperature"),
                    humidity=new_state.get("humidity"),
                    occupancy=new_state.get("occupancy"),
                )
                db.add(reading)
                bus.publish(
                    EventType.TELEMETRY_READING,
                    {
                        "device_id": device.id,
                        "home_id": device.home_id,
                        "reading": {
                            "device_id": device.id,
                            "ts": ts.isoformat(),
                            "power_w": power_w,
                            "kwh_total": device.kwh_total,
                            "temperature": new_state.get("temperature"),
                            "occupancy": new_state.get("occupancy"),
                            "state": {k: v for k, v in new_state.items() if k != "power_w"},
                        },
                    },
                )
            db.commit()
        finally:
            db.close()


engine = SimulatorEngine()
