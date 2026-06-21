"""Device management & control endpoints (REQ-4.2.x)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..domain.models import User
from ..schemas.device import (
    CapabilityOut,
    CommandRequest,
    CommandResult,
    DeviceCreate,
    DeviceOut,
    MockProfileOut,
)
from ..services.device_service import DeviceService
from .deps import get_current_user, require_admin_or_dev

router = APIRouter(prefix="/api/devices", tags=["devices"])


@router.get("", response_model=list[DeviceOut])
def list_devices(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return DeviceService(db).list_for_home(user.home_id)


@router.get("/profiles/mock", response_model=list[MockProfileOut])
def mock_profiles(user: User = Depends(get_current_user)):
    """Available mock device profiles (Add Mock Device use case)."""
    return DeviceService.mock_profiles()


@router.post("", response_model=DeviceOut, status_code=201)
def add_mock_device(
    body: DeviceCreate,
    user: User = Depends(require_admin_or_dev),
    db: Session = Depends(get_db),
):
    return DeviceService(db).add_mock_device(user.home_id, body)


@router.get("/{device_id}", response_model=DeviceOut)
def get_device(device_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return DeviceService(db).get_or_404(device_id, user.home_id)


@router.delete("/{device_id}", status_code=204)
def delete_device(
    device_id: int, user: User = Depends(require_admin_or_dev), db: Session = Depends(get_db)
):
    DeviceService(db).delete_device(device_id, user.home_id)


@router.get("/{device_id}/capabilities", response_model=CapabilityOut)
def get_capabilities(
    device_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """REQ-4.2.1: the schema that drives the control UI."""
    return DeviceService(db).capability(device_id, user.home_id)


@router.post("/{device_id}/command", response_model=CommandResult)
def send_command(
    device_id: int,
    body: CommandRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """REQ-4.2.3/4.2.4: validate against capability, dispatch, return outcome."""
    return DeviceService(db).send_user_command(user, device_id, body.control, body.value)


@router.post("/{device_id}/connectivity", response_model=DeviceOut)
def set_connectivity(
    device_id: int,
    online: bool,
    user: User = Depends(require_admin_or_dev),
    db: Session = Depends(get_db),
):
    """Demo/test hook to force a device offline/online (exercises REQ-4.1.4)."""
    return DeviceService(db).set_connectivity(device_id, user.home_id, online)
