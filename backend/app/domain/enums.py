"""Enumerations shared across the domain model."""
from __future__ import annotations

import enum


class Role(str, enum.Enum):
    """System actor roles (C01 client/customer/user distinction). The Customer
    (apartment owner / building management) operates the system as ADMIN; residents /
    tenants are the end-users (RESIDENT); DEVELOPER is a maintainer. The Client
    (IoT contractor) is a business stakeholder, not a login role."""
    ADMIN = "admin"
    RESIDENT = "resident"
    DEVELOPER = "developer"


class DeviceType(str, enum.Enum):
    PLUG = "plug"
    BULB = "bulb"
    FAN = "fan"
    AC = "ac"
    SENSOR = "sensor"


class ControlKind(str, enum.Enum):
    """How a single controllable feature is rendered/validated."""
    TOGGLE = "toggle"   # on/off
    RANGE = "range"     # numeric within [min, max] step
    ENUM = "enum"       # one of a fixed value set
    READONLY = "readonly"


class CommandOutcome(str, enum.Enum):
    """REQ-4.2.4 command results."""
    SUCCESS = "success"
    REJECTED = "rejected"
    TIMEOUT = "timeout"
    SKIPPED = "skipped"   # e.g. auto_apply disabled, or safety guard


class Initiator(str, enum.Enum):
    """Who triggered a rule execution (REQ-4.3.5)."""
    USER = "user"
    SCHEDULER = "scheduler"
    SYSTEM = "system"


class RuleSource(str, enum.Enum):
    USER = "user"
    RECOMMENDATION = "recommendation"


class RecommendationStatus(str, enum.Enum):
    ACTIVE = "active"
    ACCEPTED = "accepted"
    DISMISSED = "dismissed"
    EXPIRED = "expired"


class SavingsKind(str, enum.Enum):
    ESTIMATE = "estimate"
    MEASURED = "measured"


class TariffType(str, enum.Enum):
    FLAT = "flat"
    TIERED = "tiered"
    TOU = "tou"   # time-of-use / peak-hour


class NotificationType(str, enum.Enum):
    RULE_FIRED = "rule_fired"
    RECOMMENDATION_READY = "recommendation_ready"
    DEVICE_OFFLINE = "device_offline"
    SAFETY_WARNING = "safety_warning"
    MONTHLY_REPORT = "monthly_report"
