"""Notification service (SRS 3.3 Notification interface).

Acts as an Observer of the event bus: device-offline, rule-fired and
recommendation-ready events are turned into stored notifications and re-published
as NOTIFICATION_CREATED for the WebSocket broadcaster.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from ..core.events import EventType, bus
from ..core.errors import NotFoundError
from ..database import SessionLocal
from ..domain.enums import NotificationType
from ..domain.models import Notification
from ..repositories import NotificationRepository


class NotificationService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = NotificationRepository(db)

    def create(
        self,
        home_id: int,
        ntype: NotificationType,
        title: str,
        body: str = "",
        data: dict[str, Any] | None = None,
        user_id: int | None = None,
    ) -> Notification:
        notif = self.repo.add(
            Notification(
                home_id=home_id, user_id=user_id, type=ntype, title=title,
                body=body, data=data or {},
            )
        )
        self.db.commit()
        bus.publish(
            EventType.NOTIFICATION_CREATED,
            {"home_id": home_id, "notification": {"id": notif.id, "title": title, "type": ntype.value, "body": body}},
        )
        return notif

    def list(self, home_id: int, limit: int = 50) -> list[Notification]:
        return self.repo.by_home(home_id, limit)

    def mark_read(self, notif_id: int, home_id: int) -> Notification:
        notif = self.db.get(Notification, notif_id)
        if notif is None or notif.home_id != home_id:
            raise NotFoundError("Notification not found")
        notif.read = True
        self.db.commit()
        return notif

    def mark_all_read(self, home_id: int) -> int:
        items = self.repo.by_home(home_id, limit=500)
        count = 0
        for n in items:
            if not n.read:
                n.read = True
                count += 1
        self.db.commit()
        return count


# --------------------------------------------------------------------------
# Event subscribers (Observer). Registered once at app startup.
# --------------------------------------------------------------------------
def _on_device_offline(payload: dict[str, Any]) -> None:
    db = SessionLocal()
    try:
        NotificationService(db).create(
            payload["home_id"], NotificationType.DEVICE_OFFLINE,
            title=f"Device offline: {payload.get('name', payload['device_id'])}",
            body="No telemetry received for over 60 seconds.",
            data={"device_id": payload["device_id"]},
        )
    finally:
        db.close()


def _on_rule_fired(payload: dict[str, Any]) -> None:
    db = SessionLocal()
    try:
        NotificationService(db).create(
            payload["home_id"], NotificationType.RULE_FIRED,
            title=payload.get("title", "Rule fired"),
            body=payload.get("body", ""),
            data={"rule_id": payload.get("rule_id"), "execution_id": payload.get("execution_id")},
        )
    finally:
        db.close()


def _on_recommendation_ready(payload: dict[str, Any]) -> None:
    db = SessionLocal()
    try:
        NotificationService(db).create(
            payload["home_id"], NotificationType.RECOMMENDATION_READY,
            title=payload.get("title", "New saving recommendation"),
            body=payload.get("body", ""),
            data={"recommendation_id": payload.get("recommendation_id")},
        )
    finally:
        db.close()


_registered = False


def register_subscribers() -> None:
    global _registered
    if _registered:
        return
    bus.subscribe(EventType.DEVICE_OFFLINE, _on_device_offline)
    bus.subscribe(EventType.RULE_FIRED, _on_rule_fired)
    bus.subscribe(EventType.RECOMMENDATION_READY, _on_recommendation_ready)
    _registered = True
