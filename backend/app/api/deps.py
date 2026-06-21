"""FastAPI dependencies: DB session, current user, role guards (NFR-SEC-2)."""
from __future__ import annotations

from collections.abc import Callable

import jwt
from fastapi import Depends, Header
from sqlalchemy.orm import Session

from ..core.errors import AuthError, PermissionDeniedError
from ..core.security import decode_access_token
from ..database import get_db
from ..domain.enums import Role
from ..domain.models import User
from ..repositories import UserRepository


def get_current_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise AuthError("Missing bearer token")
    token = authorization.split(" ", 1)[1]
    try:
        payload = decode_access_token(token)
    except jwt.PyJWTError:
        raise AuthError("Invalid or expired token")
    user = UserRepository(db).by_email(payload.get("sub", ""))
    if user is None or not user.is_active:
        raise AuthError("User not found or disabled")
    return user


def require_roles(*roles: Role) -> Callable[..., User]:
    def guard(user: User = Depends(get_current_user)) -> User:
        if roles and user.role not in roles:
            raise PermissionDeniedError(
                f"Requires role: {', '.join(r.value for r in roles)}"
            )
        return user

    return guard


require_admin = require_roles(Role.ADMIN)
require_admin_or_dev = require_roles(Role.ADMIN, Role.DEVELOPER)
