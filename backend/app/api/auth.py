"""Authentication & account endpoints (NFR-SEC; Business Rule: the Administrator manages residents)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..domain.models import User
from ..schemas.auth import (
    LoginRequest,
    ResidentCreate,
    TokenResponse,
    UserOut,
)
from ..services.auth_service import AuthService
from .deps import get_current_user, require_admin

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Note: there is deliberately no public self-registration endpoint. The single
# Administrator (building owner) is provisioned out-of-band (the deployment seed),
# and Residents are onboarded only by the Administrator via POST /auth/residents
# (Business Rule BR-1, NFR-SEC-2). A public /register would let any caller create an
# Administrator and, since the building is a single tenant, read every unit's data.


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    svc = AuthService(db)
    user = svc.authenticate(body.email, body.password)
    return TokenResponse(access_token=svc.issue_token(user), user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(user)


@router.post("/residents", response_model=UserOut, status_code=201)
def add_resident(
    body: ResidentCreate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> UserOut:
    member = AuthService(db).create_resident(
        admin, body.email, body.full_name, body.password, body.unit_name
    )
    return UserOut.model_validate(member)
