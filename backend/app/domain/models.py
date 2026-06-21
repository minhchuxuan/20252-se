"""ORM models (SQLAlchemy 2.0 declarative) — the persistent domain model.

Entity-relationship overview:

The deployment models one apartment building. Each Home is a *unit* occupied by
one Resident; the Administrator (building owner) has no unit (home_id NULL) and
oversees every unit. A Tariff with home_id NULL is the building-wide tariff.

    Home(unit) 1--* User     Home 1--* Device         Tariff (home_id NULL = building)
    Home 1--* Rule           Home 1--* Recommendation Home 1--* Notification
    Device 1--* Reading      Device 1--* RuleExecution
    Rule 1--* RuleExecution  Rule 1--* SavingsRecord
    User *--* Device  (via DevicePermission — resident control grants)
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    TypeDecorator,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class TZDateTime(TypeDecorator):
    """Timezone-aware UTC datetime that survives SQLite's tz-naive storage.

    Aware values are normalised to UTC and stored naive; loaded values get UTC
    re-attached, so the whole codebase can compare/serialise aware datetimes
    consistently regardless of backend.
    """

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect):
        if value is None:
            return None
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


class EnumType(TypeDecorator):
    """Stores an Enum by its ``.value`` and reconstructs the Enum on load, so the
    whole codebase works with real Enum members (not bare strings) regardless of
    SQLite's lack of a native enum type."""

    impl = String
    cache_ok = True

    def __init__(self, enum_cls, length: int = 24, **kw):
        self.enum_cls = enum_cls
        super().__init__(length=length, **kw)

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, self.enum_cls):
            return value.value
        return self.enum_cls(value).value

    def process_result_value(self, value, dialect):
        return None if value is None else self.enum_cls(value)


from ..core.clock import now
from .enums import (
    CommandOutcome,
    DeviceType,
    Initiator,
    NotificationType,
    RecommendationStatus,
    Role,
    RuleSource,
    SavingsKind,
    TariffType,
)


class Base(DeclarativeBase):
    pass


def _now() -> datetime:
    return now()


class Home(Base):
    __tablename__ = "homes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    billing_cycle_day: Mapped[int] = mapped_column(Integer, default=1)  # day-of-month
    locale: Mapped[str] = mapped_column(String(8), default="vi")
    created_at: Mapped[datetime] = mapped_column(TZDateTime, default=_now)

    users: Mapped[list["User"]] = relationship(back_populates="home")
    devices: Mapped[list["Device"]] = relationship(back_populates="home")
    tariffs: Mapped[list["Tariff"]] = relationship(back_populates="home")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(255))  # NFR-SEC-3: never plaintext
    role: Mapped[Role] = mapped_column(EnumType(Role), default=Role.RESIDENT)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    home_id: Mapped[int | None] = mapped_column(ForeignKey("homes.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TZDateTime, default=_now)

    home: Mapped["Home"] = relationship(back_populates="users")
    permissions: Mapped[list["DevicePermission"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class DevicePermission(Base):
    """Per-device control grant for a Resident (Business Rule / RBAC)."""
    __tablename__ = "device_permissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"))
    can_control: Mapped[bool] = mapped_column(Boolean, default=True)

    user: Mapped["User"] = relationship(back_populates="permissions")


class Tariff(Base):
    __tablename__ = "tariffs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # NULL = a building-wide tariff set by the Administrator (apartment owner) and
    # shared by every unit; a non-NULL home_id is a per-unit override.
    home_id: Mapped[int | None] = mapped_column(ForeignKey("homes.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(120))
    type: Mapped[TariffType] = mapped_column(EnumType(TariffType), default=TariffType.FLAT)
    # FLAT:  {"price": 2500}
    # TIERED:{"tiers": [{"up_to_kwh": 50, "price": 1806}, {"up_to_kwh": null, "price": 3151}]}
    # TOU:   {"windows": [{"start":"22:00","end":"04:00","price":1200}], "default_price":2900}
    config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    currency: Mapped[str] = mapped_column(String(8), default="VND")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(TZDateTime, default=_now)

    home: Mapped["Home"] = relationship(back_populates="tariffs")


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    home_id: Mapped[int] = mapped_column(ForeignKey("homes.id"))
    name: Mapped[str] = mapped_column(String(120))
    type: Mapped[DeviceType] = mapped_column(EnumType(DeviceType))
    room: Mapped[str] = mapped_column(String(80), default="Living room")
    online: Mapped[bool] = mapped_column(Boolean, default=True)
    last_seen_at: Mapped[datetime] = mapped_column(TZDateTime, default=_now)
    # Current control + telemetry state (e.g. {"power":"on","speed":3,"power_w":42.0}).
    state: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    kwh_total: Mapped[float] = mapped_column(Float, default=0.0)  # cumulative energy
    safety_critical: Mapped[bool] = mapped_column(Boolean, default=False)  # NFR-SAF-2
    # Capability schema snapshot stored with the device (SRS 2.2: "store schema").
    capability: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    is_mock: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(TZDateTime, default=_now)

    home: Mapped["Home"] = relationship(back_populates="devices")
    readings: Mapped[list["Reading"]] = relationship(
        back_populates="device", cascade="all, delete-orphan"
    )


class Reading(Base):
    """A telemetry sample. Power devices use power_w/interval_kwh/kwh_total;
    sensors use temperature/humidity/occupancy (REQ-4.1.x, 3.2)."""
    __tablename__ = "readings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"), index=True)
    ts: Mapped[datetime] = mapped_column(TZDateTime, index=True, default=_now)
    power_w: Mapped[float | None] = mapped_column(Float, nullable=True)
    interval_kwh: Mapped[float] = mapped_column(Float, default=0.0)  # energy since previous sample
    kwh_total: Mapped[float | None] = mapped_column(Float, nullable=True)  # cumulative snapshot
    temperature: Mapped[float | None] = mapped_column(Float, nullable=True)
    humidity: Mapped[float | None] = mapped_column(Float, nullable=True)
    occupancy: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    device: Mapped["Device"] = relationship(back_populates="readings")


class Rule(Base):
    """WHEN <condition> THEN <action> [UNTIL <stop>] (REQ-4.3.x)."""
    __tablename__ = "rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    home_id: Mapped[int] = mapped_column(ForeignKey("homes.id"))
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"))
    name: Mapped[str] = mapped_column(String(160))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    auto_apply: Mapped[bool] = mapped_column(Boolean, default=False)  # REQ-4.3.6: off by default
    priority: Mapped[int] = mapped_column(Integer, default=100)
    when_json: Mapped[dict[str, Any]] = mapped_column(JSON)   # condition AST
    then_json: Mapped[dict[str, Any]] = mapped_column(JSON)   # {control, value}
    until_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    source: Mapped[RuleSource] = mapped_column(EnumType(RuleSource), default=RuleSource.USER)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    estimated_monthly_saving_vnd: Mapped[float] = mapped_column(Float, default=0.0)
    baseline_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    needs_recalculation: Mapped[bool] = mapped_column(Boolean, default=False)  # REQ-4.5.5
    last_fired_at: Mapped[datetime | None] = mapped_column(TZDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TZDateTime, default=_now)
    # NB: no ORM relationship to RuleExecution on purpose — deleting a Rule must
    # NOT cascade to / nullify its execution history (Business Rule). Executions
    # are queried by rule_id via the repository, keeping the audit log intact.


class RuleExecution(Base):
    """Immutable execution log (REQ-4.3.5). Deleting a Rule must NOT delete these
    for the current billing cycle (Business Rule) — no FK cascade / relationship."""
    __tablename__ = "rule_executions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    rule_id: Mapped[int] = mapped_column(ForeignKey("rules.id"))
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"))
    ts: Mapped[datetime] = mapped_column(TZDateTime, default=_now, index=True)
    action_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    initiator: Mapped[Initiator] = mapped_column(EnumType(Initiator))
    outcome: Mapped[CommandOutcome] = mapped_column(EnumType(CommandOutcome))
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Undo support (REQ-4.3.6).
    undo_deadline: Mapped[datetime | None] = mapped_column(TZDateTime, nullable=True)
    prior_state: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    undone: Mapped[bool] = mapped_column(Boolean, default=False)


class Recommendation(Base):
    """Habit-derived, explainable WHEN-THEN suggestion (REQ-4.4.x)."""
    __tablename__ = "recommendations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    home_id: Mapped[int] = mapped_column(ForeignKey("homes.id"))
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"))
    title: Mapped[str] = mapped_column(String(200))
    when_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    then_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    until_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    rationale: Mapped[str] = mapped_column(Text)            # human-readable explanation
    data_window_start: Mapped[datetime] = mapped_column(TZDateTime)
    data_window_end: Mapped[datetime] = mapped_column(TZDateTime)
    estimated_monthly_saving_vnd: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[RecommendationStatus] = mapped_column(EnumType(RecommendationStatus), default=RecommendationStatus.ACTIVE)
    # signature = device_id + condition kind; used for 30-day dismissal suppression (REQ-4.4.5).
    signature: Mapped[str] = mapped_column(String(120), index=True)
    dismissed_until: Mapped[datetime | None] = mapped_column(TZDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TZDateTime, default=_now)


class SavingsRecord(Base):
    """Estimated or measured saving for a rule/device over a period (REQ-4.5.x)."""
    __tablename__ = "savings_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    home_id: Mapped[int] = mapped_column(ForeignKey("homes.id"))
    rule_id: Mapped[int | None] = mapped_column(ForeignKey("rules.id"), nullable=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"))
    period_start: Mapped[datetime] = mapped_column(TZDateTime)
    period_end: Mapped[datetime] = mapped_column(TZDateTime)
    baseline_kwh: Mapped[float] = mapped_column(Float, default=0.0)
    expected_kwh_with_rule: Mapped[float] = mapped_column(Float, default=0.0)
    actual_kwh: Mapped[float | None] = mapped_column(Float, nullable=True)
    saved_kwh: Mapped[float] = mapped_column(Float, default=0.0)
    saved_vnd: Mapped[float] = mapped_column(Float, default=0.0)
    kind: Mapped[SavingsKind] = mapped_column(EnumType(SavingsKind), default=SavingsKind.ESTIMATE)
    created_at: Mapped[datetime] = mapped_column(TZDateTime, default=_now)


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    home_id: Mapped[int] = mapped_column(ForeignKey("homes.id"))
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    type: Mapped[NotificationType] = mapped_column(EnumType(NotificationType))
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text, default="")
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    ts: Mapped[datetime] = mapped_column(TZDateTime, default=_now, index=True)
