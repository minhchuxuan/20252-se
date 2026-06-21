"""Authentication & account service (NFR-SEC-2/3; Business Rule: only the
Administrator manages residents)."""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..config import settings
from ..core.errors import AuthError, ConflictError
from ..core.security import create_access_token, hash_password, verify_password
from ..domain.enums import Role, TariffType
from ..domain.models import Home, Tariff, User
from ..repositories import (
    DevicePermissionRepository,
    DeviceRepository,
    HomeRepository,
    TariffRepository,
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
        self.tariffs = TariffRepository(db)

    def register_admin(self, email: str, full_name: str, password: str, building_name: str) -> User:
        """Public sign-up: the apartment owner / building management registers and becomes
        the Administrator. The Administrator owns no single unit (home_id NULL) and oversees
        every unit in the building; a building-wide default tariff is created on first sign-up."""
        email = email.lower()
        if self.users.by_email(email):
            raise ConflictError("Email already registered")
        user = self.users.add(
            User(
                email=email,
                full_name=full_name,
                password_hash=hash_password(password),
                role=Role.ADMIN,
                home_id=None,
            )
        )
        if self.tariffs.active_for_home(None) is None:
            self.db.add(Tariff(
                home_id=None, name="Default flat", type=TariffType.FLAT,
                config={"price": settings.default_tariff_vnd_per_kwh},
                currency=settings.currency, active=True,
            ))
        self.db.commit()
        return user

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
