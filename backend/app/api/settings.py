"""Settings, tariff configuration and notification endpoints
(Business Rule: manual tariff config; SRS 3.3 notifications; 6.2 localization)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..core.errors import NotFoundError
from ..database import get_db
from ..domain.models import Home, Tariff, User
from ..repositories import TariffRepository
from ..schemas.common import Message
from ..schemas.tariff import NotificationOut, SettingsOut, TariffCreate, TariffOut
from ..services.notification_service import NotificationService
from ..services.tariff_service import TariffService
from .deps import get_current_user, require_admin

router = APIRouter(prefix="/api", tags=["settings"])


@router.get("/settings", response_model=SettingsOut)
def get_settings(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    tariff = TariffService(db).active(user.home_id)
    home = db.get(Home, user.home_id) if user.home_id is not None else None
    return SettingsOut(
        home_id=home.id if home else None,
        home_name=home.name if home else "Building (all units)",
        locale=home.locale if home else "vi",
        currency=tariff.currency,
        billing_cycle_day=home.billing_cycle_day if home else 1,
        active_tariff=TariffOut.model_validate(tariff) if tariff.id else None,
    )


@router.get("/tariffs", response_model=list[TariffOut])
def list_tariffs(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # Tariffs are building-wide and set by the Administrator; everyone sees them.
    return TariffRepository(db).building()


@router.post("/tariffs", response_model=TariffOut, status_code=201)
def create_tariff(
    body: TariffCreate, admin: User = Depends(require_admin), db: Session = Depends(get_db)
):
    repo = TariffRepository(db)
    for t in repo.building():
        t.active = False
    tariff = repo.add(
        Tariff(
            home_id=None, name=body.name, type=body.type,
            config=body.config, currency=body.currency, active=True,
        )
    )
    db.commit()
    return tariff


@router.put("/tariffs/{tariff_id}/activate", response_model=TariffOut)
def activate_tariff(
    tariff_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)
):
    repo = TariffRepository(db)
    target = db.get(Tariff, tariff_id)
    if target is None or target.home_id is not None:
        raise NotFoundError("Tariff not found")
    for t in repo.building():
        t.active = t.id == tariff_id
    db.commit()
    return target


@router.get("/notifications", response_model=list[NotificationOut])
def list_notifications(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return NotificationService(db).list(user.home_id)


@router.post("/notifications/{notif_id}/read", response_model=NotificationOut)
def mark_read(notif_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return NotificationService(db).mark_read(notif_id, user.home_id)


@router.post("/notifications/read-all", response_model=Message)
def mark_all_read(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    count = NotificationService(db).mark_all_read(user.home_id)
    return Message(message=f"Marked {count} notifications as read")
