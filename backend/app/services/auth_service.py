"""Authentication & account service (NFR-SEC-2/3; Business Rule: only the
Administrator manages residents)."""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..core.errors import AuthError, ConflictError
from ..core.security import create_access_token, hash_password, verify_password
from ..domain.enums import Role
from ..domain.models import Home, User
from ..repositories import (
    DevicePermissionRepository,
    DeviceRepository,
    HomeRepository,
    UserRepository,
)
from .provisioning import provision_unit


class AuthService:
    def __init__(self, db: Session):
        self.db = db
        self.users = UserRepository(db)
        self.homes = HomeRepository(db)
        self.permissions = DevicePermissionRepository(db)
        self.devices = DeviceRepository(db)

    # Account creation is Administrator-only: the Administrator is seeded at deployment,
    # and Residents are onboarded through create_resident (BR-1, NFR-SEC-2). There is no
    # public self-registration path that could mint an Administrator.

    def authenticate(self, email: str, password: str) -> User:
        user = self.users.by_email(email.lower())
        if not user or not verify_password(password, user.password_hash):
            raise AuthError("Invalid email or password")
        if not user.is_active:
            raise AuthError("Account disabled")
        return user

    @staticmethod
    def issue_token(user: User) -> str:
        return create_access_token(user.email, user.role.value, user.home_id)

    def create_resident(
        self, admin: User, email: str, full_name: str, password: str, unit_name: str
    ) -> User:
        """The Administrator sells a unit to a Resident: it creates the unit (Home), the
        Resident account, and the default device package, granting the Resident control of
        every operable device (Business Rule: only the Owner onboards residents / RBAC)."""
        email = email.lower()
        if self.users.by_email(email):
            raise ConflictError("Email already registered")
        home = self.homes.add(Home(name=unit_name))
        member = self.users.add(
            User(
                email=email,
                full_name=full_name,
                password_hash=hash_password(password),
                role=Role.RESIDENT,
                home_id=home.id,
            )
        )
        self.db.flush()
        provision_unit(self.db, home, member)
        self.db.commit()
        return member
