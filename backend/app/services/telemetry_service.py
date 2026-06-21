"""Real-time monitoring & reporting service (REQ-4.1.x)."""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from ..config import settings
from ..core.clock import now
from ..core.errors import NotFoundError
from ..core.events import EventType, bus
from ..core.timeutil import current_billing_cycle, start_of_day
from ..domain.enums import DeviceType
from ..domain.models import Device, Home
from ..repositories import DeviceRepository, ReadingRepository
from ..schemas.telemetry import (
    ConsumptionPoint,
    ConsumptionSeries,
    DashboardOut,
    DeviceLive,
    TopConsumer,
)
from .optimization_service import OptimizationService
from .tariff_service import TariffService


class TelemetryService:
    def __init__(self, db: Session):
        self.db = db
        self.devices = DeviceRepository(db)
        self.readings = ReadingRepository(db)
        self.tariffs = TariffService(db)
        self.optimizer = OptimizationService(db)

    # ----------------------------------------------------------- offline detection
    def refresh_online_status(self, home_id: int) -> None:
        """REQ-4.1.4: mark a device unreachable if silent for > threshold."""
        threshold = timedelta(seconds=settings.offline_threshold_seconds)
        ts = now()
        for device in self.devices.by_home(home_id):
            silent = (ts - device.last_seen_at) > threshold
            forced = (device.state or {}).get("forced_offline", False)
            should_be_online = not silent and not forced
            if device.online and not should_be_online:
                device.online = False
                bus.publish(
                    EventType.DEVICE_OFFLINE,
                    {"device_id": device.id, "home_id": home_id, "name": device.name},
                )
            elif not device.online and should_be_online:
                device.online = True
                bus.publish(EventType.DEVICE_ONLINE, {"device_id": device.id, "home_id": home_id})
        self.db.commit()

    # ----------------------------------------------------------- dashboard
    def dashboard(self, home_id: int) -> DashboardOut:
        if home_id is None:
            from ..core.errors import PermissionDeniedError
            raise PermissionDeniedError("The administrator has no unit; use the building overview")
        self.refresh_online_status(home_id)
        ts = now()
        home = self.db.get(Home, home_id)
        tariff = self.tariffs.active(home_id)
        devices = self.devices.by_home(home_id)

        day_start = start_of_day(ts)
        cycle_start, cycle_end = current_billing_cycle(ts, home.billing_cycle_day if home else 1)

        total_w = 0.0
        kwh_today = 0.0
        kwh_cycle = 0.0
        live: list[DeviceLive] = []
        for d in devices:
            power_w = float((d.state or {}).get("power_w", 0.0)) if d.online else 0.0
            if d.type != DeviceType.SENSOR and d.online:
                total_w += power_w
            d_today = self.readings.sum_energy(d.id, day_start, ts)
            kwh_today += d_today
            kwh_cycle += self.readings.sum_energy(d.id, cycle_start, ts)
            live.append(
                DeviceLive(
                    device_id=d.id, name=d.name, type=d.type.value, room=d.room,
                    online=d.online, power_w=round(power_w, 1), kwh_today=round(d_today, 3),
                    temperature=(d.state or {}).get("temperature"),
                    occupancy=(d.state or {}).get("occupancy"),
                )
            )
        live.sort(key=lambda x: x.power_w, reverse=True)

        # Projected bill for the whole cycle (REQ-4.1.2 cumulative + estimate).
        elapsed_days = max((ts - cycle_start).total_seconds() / 86400.0, 0.01)
        total_days = max((cycle_end - cycle_start).total_seconds() / 86400.0, 1.0)
        projected_kwh = kwh_cycle / elapsed_days * total_days
        estimated_bill = self.tariffs.price_energy(tariff, projected_kwh)

        summary = self.optimizer.savings_summary(home_id)
        return DashboardOut(
            home_total_w=round(total_w, 1),
            kwh_today=round(kwh_today, 3),
            kwh_cycle=round(kwh_cycle, 3),
            estimated_bill_vnd=round(estimated_bill, 0),
            savings_cycle_vnd=summary.saved_vnd_cycle,
            currency=tariff.currency,
            tariff_name=tariff.name,
            online_devices=sum(1 for d in devices if d.online),
            total_devices=len(devices),
            devices=live,
            generated_at=ts,
        )

    # ----------------------------------------------------------- consumption series
    def consumption_series(
        self, home_id: int, device_id: int | None, start: datetime, end: datetime, granularity: str
    ) -> ConsumptionSeries:
        tariff = self.tariffs.active(home_id)
        # NFR-SEC-4: a caller-supplied device_id must be scoped to the caller's
        # home, otherwise readings of another home could be read (cross-home IDOR).
        if device_id is not None:
            if self.devices.in_home(device_id, home_id) is None:
                raise NotFoundError(f"Device {device_id} not found")
            device_ids = [device_id]
        else:
            device_ids = [d.id for d in self.devices.by_home(home_id)]
        buckets: dict[str, float] = {}
        for did in device_ids:
            for r in self.readings.in_range(did, start, end):
                key = self._bucket_key(r.ts, granularity)
                buckets[key] = buckets.get(key, 0.0) + (r.interval_kwh or 0.0)
        points = [
            ConsumptionPoint(
                bucket=k, kwh=round(v, 3),
                cost_vnd=round(self.tariffs.price_energy(tariff, v), 0),
            )
            for k, v in sorted(buckets.items())
        ]
        total_kwh = sum(p.kwh for p in points)
        return ConsumptionSeries(
            device_id=device_id, granularity=granularity, start=start, end=end,
            points=points, total_kwh=round(total_kwh, 3),
            total_cost_vnd=round(self.tariffs.price_energy(tariff, total_kwh), 0),
        )

    def top_consumers(
        self, home_id: int, start: datetime, end: datetime, limit: int = 3
    ) -> list[TopConsumer]:
        """REQ-4.1.5: top consuming devices for a day/week/month."""
        tariff = self.tariffs.active(home_id)
        rows: list[tuple[Device, float]] = []
        for d in self.devices.by_home(home_id):
            if d.type == DeviceType.SENSOR:
                continue
            rows.append((d, self.readings.sum_energy(d.id, start, end)))
        total = sum(k for _, k in rows) or 1.0
        rows.sort(key=lambda x: x[1], reverse=True)
        return [
            TopConsumer(
                device_id=d.id, name=d.name, type=d.type.value, kwh=round(k, 3),
                cost_vnd=round(self.tariffs.price_energy(tariff, k), 0),
                share_pct=round(k / total * 100, 1),
            )
            for d, k in rows[:limit]
        ]

    @staticmethod
    def _bucket_key(ts: datetime, granularity: str) -> str:
        if granularity == "hour":
            return ts.strftime("%Y-%m-%dT%H:00")
        return ts.strftime("%Y-%m-%d")
