"""AI-Driven Smart Home Energy Optimizer — backend application package.

Layered architecture (see docs/02-sdd.md):

    api/          HTTP + WebSocket controllers (presentation tier boundary)
    services/     application/business logic
    repositories/ data-access layer (Repository pattern over SQLAlchemy)
    domain/       ORM models, enums, capability schema (problem-domain model)
    adapters/     per-device-type behaviour (Strategy pattern)
    simulator/    mock telemetry generator (replaces real hardware)
    core/         cross-cutting: security, event bus (Observer), clock, errors

The package is intentionally free of hard-coded per-device screens: every
control is described by a capability schema (domain/capability.py) and served
through ``GET /api/devices/{id}/capabilities`` (REQ-4.2.1).
"""

__version__ = "1.0.0"
