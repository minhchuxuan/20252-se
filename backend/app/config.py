"""Application configuration.

All tunables that the SRS references as policy thresholds live here so they are
traceable and adjustable for the demo without code changes.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Anchor the demo SQLite DB to the backend directory so it resolves to the same
# absolute path no matter where uvicorn is started from. A relative path made the
# DB (and its write journal) location depend on the launch CWD, which could leave
# it in a non-writable directory and surface as "attempt to write a readonly database".
_BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SHEO_", env_file=".env", extra="ignore")

    app_name: str = "AI-Driven Smart Home Energy Optimizer"
    debug: bool = True

    # --- Persistence ---
    database_url: str = f"sqlite:///{_BACKEND_DIR / 'sheo.db'}"

    # --- Security (NFR-SEC) ---
    jwt_secret: str = "dev-only-secret-change-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 720

    # --- Real-time monitoring (REQ-4.1.x / NFR-PER) ---
    telemetry_interval_seconds: float = 2.0   # live simulator emit cadence (<= 5s refresh)
    offline_threshold_seconds: int = 60       # REQ-4.1.4: no telemetry > 60s -> unreachable
    reading_retention_days: int = 365         # REQ-4.1.3: 1-min aggregates >= 12 months

    # --- Optimization / bill-saving (REQ-4.5.x) ---
    baseline_days: int = 14                   # REQ-4.5.1: 14-day baseline
    savings_drift_threshold: float = 0.20     # REQ-4.5.5: +/-20% -> needs recalculation
    default_tariff_vnd_per_kwh: float = 2500.0  # manual fallback (Business Rule, REQ Tariff)

    # --- Habit learning / recommendations (REQ-4.4.x) ---
    recommendation_min_days: int = 7          # REQ-4.4.1
    recommendation_max_active: int = 5        # REQ-4.4.3
    recommendation_dismiss_days: int = 30     # REQ-4.4.5

    # --- Rules / auto-actions (REQ-4.3.x) ---
    undo_window_seconds: int = 120            # REQ-4.3.6: undo for 2 minutes

    # --- Safety (NFR-SAF) ---
    ac_compressor_min_interval_seconds: int = 180  # NFR-SAF-1: <= 1 compressor cmd / 3 min

    # --- Localization (Other Requirements 6.2) ---
    currency: str = "VND"
    default_locale: str = "vi"

    # --- Demo seeding & background tasks ---
    seed_history_days: int = 21               # > 14 baseline and > 7 recommendation window
    seed_on_startup: bool = True
    enable_background: bool = True            # simulator + scheduler loops (disabled in tests)

    # --- CORS (frontend dev server) ---
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
    ]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
