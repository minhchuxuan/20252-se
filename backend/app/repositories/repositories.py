"""Data-access layer — the Repository pattern (SE Intro 16 requirements tracing,
SE Intro 11/12 repository style).

Services depend on these repositories rather than on SQLAlchemy directly, so the
business logic stays persistence-agnostic and unit-testable. Each repository is
cohesive around one aggregate.
"""
from __future__ import annotations

from datetime import datetime
from typing import Generic, TypeVar

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..domain.enums import RecommendationStatus
from ..domain.models import (
    Base,
    Device,
    DevicePermission,
    Home,
    Notification,
    Reading,
    Recommendation,
    Rule,
    RuleExecution,
    SavingsRecord,
    Tariff,
    User,
)

T = TypeVar("T", bound=Base)


class Repository(Generic[T]):
    model: type[T]

    def __init__(self, db: Session):
        self.db = db

    def get(self, obj_id: int) -> T | None:
        return self.db.get(self.model, obj_id)

    def list(self) -> list[T]:
        return list(self.db.scalars(select(self.model)).all())

    def add(self, obj: T) -> T:
        self.db.add(obj)
        self.db.flush()
        return obj

    def delete(self, obj: T) -> None:
        self.db.delete(obj)

    def commit(self) -> None:
        self.db.commit()


class HomeRepository(Repository[Home]):
    model = Home


class UserRepository(Repository[User]):
    model = User

    def by_email(self, email: str) -> User | None:
        return self.db.scalars(select(User).where(User.email == email.lower())).first()

    def by_home(self, home_id: int) -> list[User]:
        return list(self.db.scalars(select(User).where(User.home_id == home_id)).all())

    def residents(self) -> list[User]:
        """All Residents (tenants) across the building, ordered by unit."""
        from ..domain.enums import Role

        return list(
            self.db.scalars(
                select(User).where(User.role == Role.RESIDENT).order_by(User.home_id)
            ).all()
        )


class DevicePermissionRepository(Repository[DevicePermission]):
    model = DevicePermission

    def for_user(self, user_id: int) -> list[DevicePermission]:
        return list(
            self.db.scalars(
                select(DevicePermission).where(DevicePermission.user_id == user_id)
            ).all()
        )

    def can_control(self, user_id: int, device_id: int) -> bool:
        perm = self.db.scalars(
            select(DevicePermission).where(
                DevicePermission.user_id == user_id,
                DevicePermission.device_id == device_id,
            )
        ).first()
        return bool(perm and perm.can_control)


class DeviceRepository(Repository[Device]):
    model = Device

    def by_home(self, home_id: int) -> list[Device]:
        return list(
            self.db.scalars(
                select(Device).where(Device.home_id == home_id).order_by(Device.id)
            ).all()
        )

    def in_home(self, device_id: int, home_id: int) -> Device | None:
        return self.db.scalars(
            select(Device).where(Device.id == device_id, Device.home_id == home_id)
        ).first()


class ReadingRepository(Repository[Reading]):
    model = Reading

    def latest_for_device(self, device_id: int) -> Reading | None:
        return self.db.scalars(
            select(Reading).where(Reading.device_id == device_id).order_by(Reading.ts.desc())
        ).first()

    def in_range(self, device_id: int, start: datetime, end: datetime) -> list[Reading]:
        return list(
            self.db.scalars(
                select(Reading)
                .where(Reading.device_id == device_id, Reading.ts >= start, Reading.ts < end)
                .order_by(Reading.ts)
            ).all()
        )

    def sum_energy(self, device_id: int, start: datetime, end: datetime) -> float:
        total = self.db.scalar(
            select(func.coalesce(func.sum(Reading.interval_kwh), 0.0)).where(
                Reading.device_id == device_id, Reading.ts >= start, Reading.ts < end
            )
        )
        return float(total or 0.0)

    def first_reading_ts(self, device_id: int) -> datetime | None:
        return self.db.scalar(
            select(func.min(Reading.ts)).where(Reading.device_id == device_id)
        )


class RuleRepository(Repository[Rule]):
    model = Rule

    def by_home(self, home_id: int) -> list[Rule]:
        return list(
            self.db.scalars(
                select(Rule).where(Rule.home_id == home_id).order_by(Rule.id)
            ).all()
        )

    def enabled_by_home(self, home_id: int) -> list[Rule]:
        return list(
            self.db.scalars(
                select(Rule).where(Rule.home_id == home_id, Rule.enabled.is_(True))
            ).all()
        )

    def for_device(self, device_id: int) -> list[Rule]:
        return list(self.db.scalars(select(Rule).where(Rule.device_id == device_id)).all())


class RuleExecutionRepository(Repository[RuleExecution]):
    model = RuleExecution

    def by_rule(self, rule_id: int) -> list[RuleExecution]:
        return list(
            self.db.scalars(
                select(RuleExecution)
                .where(RuleExecution.rule_id == rule_id)
                .order_by(RuleExecution.ts.desc())
            ).all()
        )

    def recent_for_device(self, device_id: int, limit: int = 50) -> list[RuleExecution]:
        return list(
            self.db.scalars(
                select(RuleExecution)
                .where(RuleExecution.device_id == device_id)
                .order_by(RuleExecution.ts.desc())
                .limit(limit)
            ).all()
        )


class RecommendationRepository(Repository[Recommendation]):
    model = Recommendation

    def active_for_home(self, home_id: int) -> list[Recommendation]:
        return list(
            self.db.scalars(
                select(Recommendation).where(
                    Recommendation.home_id == home_id,
                    Recommendation.status == RecommendationStatus.ACTIVE,
                )
            ).all()
        )

    def by_signature(self, home_id: int, signature: str) -> list[Recommendation]:
        return list(
            self.db.scalars(
                select(Recommendation).where(
                    Recommendation.home_id == home_id,
                    Recommendation.signature == signature,
                )
            ).all()
        )


class SavingsRepository(Repository[SavingsRecord]):
    model = SavingsRecord

    def by_home(self, home_id: int) -> list[SavingsRecord]:
        return list(
            self.db.scalars(
                select(SavingsRecord).where(SavingsRecord.home_id == home_id)
            ).all()
        )

    def measured_in_period(
        self, home_id: int, start: datetime, end: datetime
    ) -> list[SavingsRecord]:
        from ..domain.enums import SavingsKind

        return list(
            self.db.scalars(
                select(SavingsRecord).where(
                    SavingsRecord.home_id == home_id,
                    SavingsRecord.kind == SavingsKind.MEASURED,
                    SavingsRecord.period_start >= start,
                    SavingsRecord.period_end <= end,
                )
            ).all()
        )


class NotificationRepository(Repository[Notification]):
    model = Notification

    def by_home(self, home_id: int, limit: int = 50) -> list[Notification]:
        return list(
            self.db.scalars(
                select(Notification)
                .where(Notification.home_id == home_id)
                .order_by(Notification.ts.desc())
                .limit(limit)
            ).all()
        )


class TariffRepository(Repository[Tariff]):
    model = Tariff

    def active_for_home(self, home_id: int | None) -> Tariff | None:
        # A per-unit tariff takes precedence; otherwise fall back to the
        # building-wide tariff (home_id NULL) set by the Administrator.
        if home_id is not None:
            specific = self.db.scalars(
                select(Tariff).where(Tariff.home_id == home_id, Tariff.active.is_(True))
            ).first()
            if specific is not None:
                return specific
        return self.db.scalars(
            select(Tariff).where(Tariff.home_id.is_(None), Tariff.active.is_(True))
        ).first()

    def building(self) -> list[Tariff]:
        """The building-wide tariffs (home_id NULL) the Administrator manages."""
        return list(self.db.scalars(select(Tariff).where(Tariff.home_id.is_(None))).all())

    def by_home(self, home_id: int) -> list[Tariff]:
        return list(self.db.scalars(select(Tariff).where(Tariff.home_id == home_id)).all())
