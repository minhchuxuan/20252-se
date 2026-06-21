"""Tariff pricing service.

Supports flat, tiered (EVN-style progressive blocks) and time-of-use tariffs.
Tariff data can be configured manually when no tariff API is available
(Business Rule / Assumptions). All prices are VND/kWh.
"""
from __future__ import annotations

from datetime import datetime, time

from sqlalchemy.orm import Session

from ..config import settings
from ..core.clock import now
from ..domain.enums import TariffType
from ..domain.models import Tariff
from ..repositories import TariffRepository


class TariffService:
    def __init__(self, db: Session):
        self.db = db
        self.tariffs = TariffRepository(db)

    def active(self, home_id: int | None) -> Tariff:
        tariff = self.tariffs.active_for_home(home_id)
        if tariff is None:
            # Manual fallback (Assumptions & Dependencies): a building-wide default.
            tariff = Tariff(
                home_id=None,
                name="Default flat",
                type=TariffType.FLAT,
                config={"price": settings.default_tariff_vnd_per_kwh},
                currency=settings.currency,
                active=True,
            )
        return tariff

    # ------------------------------------------------------------------ pricing
    def effective_price(
        self, tariff: Tariff, ts: datetime | None = None, monthly_kwh: float = 0.0
    ) -> float:
        """A single representative VND/kWh for the SRS savings formula (REQ-4.5.2).

        * flat   -> the flat price
        * tiered -> marginal block price at the home's current monthly usage
        * tou    -> price of the window at ``ts`` (defaults to the default price)
        """
        cfg = tariff.config or {}
        if tariff.type == TariffType.FLAT:
            return float(cfg.get("price", settings.default_tariff_vnd_per_kwh))
        if tariff.type == TariffType.TIERED:
            return self._tier_price(cfg.get("tiers", []), monthly_kwh)
        if tariff.type == TariffType.TOU:
            return self._tou_price(cfg, ts or now())
        return settings.default_tariff_vnd_per_kwh

    def price_energy(
        self, tariff: Tariff, kwh: float, ts: datetime | None = None, monthly_kwh_before: float = 0.0
    ) -> float:
        """Cost (VND) of consuming ``kwh`` starting from cumulative ``monthly_kwh_before``."""
        if kwh <= 0:
            return 0.0
        cfg = tariff.config or {}
        if tariff.type == TariffType.TIERED:
            return self._tiered_cost(cfg.get("tiers", []), monthly_kwh_before, kwh)
        return kwh * self.effective_price(tariff, ts, monthly_kwh_before)

    def current_window(self, tariff: Tariff, ts: datetime | None = None) -> str:
        """Return the active TOU window name ('peak'/'offpeak'/'normal')."""
        if tariff.type != TariffType.TOU:
            return "normal"
        ts = ts or now()
        for w in (tariff.config or {}).get("windows", []):
            if self._in_window(w.get("start"), w.get("end"), ts):
                return w.get("name", "normal")
        return "normal"

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _tier_price(tiers: list[dict], monthly_kwh: float) -> float:
        cumulative = 0.0
        for tier in tiers:
            up_to = tier.get("up_to_kwh")
            if up_to is None or monthly_kwh < up_to:
                return float(tier["price"])
            cumulative = up_to
        return float(tiers[-1]["price"]) if tiers else settings.default_tariff_vnd_per_kwh

    @staticmethod
    def _tiered_cost(tiers: list[dict], start_kwh: float, kwh: float) -> float:
        """Integrate progressive blocks from start_kwh to start_kwh+kwh."""
        remaining = kwh
        pos = start_kwh
        cost = 0.0
        lower = 0.0
        for tier in tiers:
            up_to = tier.get("up_to_kwh")
            upper = float("inf") if up_to is None else float(up_to)
            block_top = upper
            if pos < block_top:
                take = min(remaining, block_top - pos)
                if take > 0:
                    cost += take * float(tier["price"])
                    pos += take
                    remaining -= take
            lower = upper
            if remaining <= 0:
                break
        if remaining > 0 and tiers:  # beyond last finite tier
            cost += remaining * float(tiers[-1]["price"])
        return cost

    def _tou_price(self, cfg: dict, ts: datetime) -> float:
        for w in cfg.get("windows", []):
            if self._in_window(w.get("start"), w.get("end"), ts):
                return float(w["price"])
        return float(cfg.get("default_price", settings.default_tariff_vnd_per_kwh))

    @staticmethod
    def _in_window(start: str | None, end: str | None, ts: datetime) -> bool:
        if not start or not end:
            return False
        sh, sm = map(int, start.split(":"))
        eh, em = map(int, end.split(":"))
        s, e, cur = time(sh, sm), time(eh, em), ts.time()
        if s <= e:
            return s <= cur < e
        return cur >= s or cur < e  # window wraps midnight
