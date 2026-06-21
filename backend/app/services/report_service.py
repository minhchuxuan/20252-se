"""Reporting & CSV export service (Other Requirements 6.1 Data Retention/Export)."""
from __future__ import annotations

import csv
import io
from datetime import datetime

from sqlalchemy.orm import Session

from ..repositories import (
    DeviceRepository,
    ReadingRepository,
    RuleRepository,
    SavingsRepository,
)


class ReportService:
    def __init__(self, db: Session):
        self.db = db
        self.devices = DeviceRepository(db)
        self.readings = ReadingRepository(db)
        self.rules = RuleRepository(db)
        self.savings = SavingsRepository(db)

    def export_readings_csv(self, home_id: int, start: datetime, end: datetime) -> str:
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(
            ["device_id", "device_name", "timestamp", "power_w", "interval_kwh",
             "kwh_total", "temperature", "humidity", "occupancy"]
        )
        for device in self.devices.by_home(home_id):
            for r in self.readings.in_range(device.id, start, end):
                writer.writerow(
                    [device.id, device.name, r.ts.isoformat(), r.power_w, r.interval_kwh,
                     r.kwh_total, r.temperature, r.humidity, r.occupancy]
                )
        return buf.getvalue()

    def export_rules_csv(self, home_id: int) -> str:
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(
            ["rule_id", "name", "device_id", "enabled", "auto_apply", "when", "then",
             "source", "estimated_monthly_saving_vnd", "needs_recalculation"]
        )
        for r in self.rules.by_home(home_id):
            writer.writerow(
                [r.id, r.name, r.device_id, r.enabled, r.auto_apply, r.when_json, r.then_json,
                 r.source.value, r.estimated_monthly_saving_vnd, r.needs_recalculation]
            )
        return buf.getvalue()

    def export_savings_csv(self, home_id: int) -> str:
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(
            ["record_id", "rule_id", "device_id", "period_start", "period_end",
             "baseline_kwh", "expected_kwh_with_rule", "actual_kwh", "saved_kwh", "saved_vnd", "kind"]
        )
        for s in self.savings.by_home(home_id):
            writer.writerow(
                [s.id, s.rule_id, s.device_id, s.period_start.isoformat(), s.period_end.isoformat(),
                 s.baseline_kwh, s.expected_kwh_with_rule, s.actual_kwh, s.saved_kwh, s.saved_vnd,
                 s.kind.value]
            )
        return buf.getvalue()
