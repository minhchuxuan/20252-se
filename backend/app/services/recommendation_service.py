"""Recommendation service (REQ-4.4.x) — orchestrates the recommendation lifecycle.

Habit *detection* (the AI concern) is delegated to a swappable ``RecommendationProvider``
(Strategy). This service owns the parts that are SHEO's own software: pricing each
candidate in VND (REQ-4.5, via ``OptimizationService``), the min-saving filter, duplicate
and 30-day-dismissal suppression (REQ-4.4.5), the active-recommendation cap, persistence,
and conversion of an accepted recommendation into a real rule (REQ-4.4.4).
"""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy.orm import Session

from ..config import settings
from ..core.clock import now
from ..core.events import EventType, bus
from ..domain.enums import RecommendationStatus, RuleSource
from ..domain.models import Recommendation
from ..repositories import DeviceRepository, RecommendationRepository
from .optimization_service import OptimizationService
from .recommendation_provider import HeuristicRecommendationProvider, RecommendationProvider
from .rule_engine import RuleEngine

# Only surface a recommendation if it saves at least this much per month.
_MIN_SAVING_VND = 3000.0


class RecommendationService:
    def __init__(self, db: Session, provider: RecommendationProvider | None = None):
        self.db = db
        self.repo = RecommendationRepository(db)
        self.devices = DeviceRepository(db)
        self.optimizer = OptimizationService(db)
        self.engine = RuleEngine(db)
        # The provider is injected at the composition root; default to the deterministic,
        # explainable miner. A black-box ML provider can be substituted here.
        self.provider = provider or HeuristicRecommendationProvider(db)

    # ----------------------------------------------------------- public
    def list_active(self, home_id: int) -> list[Recommendation]:
        recs = self.repo.active_for_home(home_id)
        recs.sort(key=lambda r: r.estimated_monthly_saving_vnd, reverse=True)
        return recs[: settings.recommendation_max_active]

    def analyze(self, home_id: int) -> list[Recommendation]:
        """Mine habits via the provider, price them in VND, then persist new
        recommendations and enforce caps/suppression."""
        created: list[Recommendation] = []
        for cand in self.provider.mine(home_id):
            device = self.devices.get(cand.device_id)
            if device is None:
                continue
            # Pricing is SHEO's own logic (REQ-4.5), never the provider's.
            est = self.optimizer.estimate_rule(device, cand.when, cand.then, cand.until)
            saving = est.saved_vnd_month
            if saving < _MIN_SAVING_VND:
                continue
            if not self._is_allowed(home_id, cand.signature):
                continue
            rec = self.repo.add(
                Recommendation(
                    home_id=home_id, device_id=cand.device_id, title=cand.title,
                    when_json=cand.when, then_json=cand.then, until_json=cand.until,
                    rationale=cand.rationale,
                    data_window_start=cand.window_start, data_window_end=cand.window_end,
                    estimated_monthly_saving_vnd=saving,
                    signature=cand.signature, status=RecommendationStatus.ACTIVE,
                )
            )
            created.append(rec)
            bus.publish(
                EventType.RECOMMENDATION_READY,
                {"home_id": home_id, "recommendation_id": rec.id, "title": "New saving idea: " + rec.title,
                 "body": f"Estimated saving ≈ {rec.estimated_monthly_saving_vnd:,.0f} VND/month"},
            )
        self.db.commit()
        self._enforce_max_active(home_id)
        return self.list_active(home_id)

    def accept(self, rec_id: int, home_id: int, name: str | None, auto_apply: bool):
        from ..schemas.common import Action, Condition
        from ..schemas.rule import RuleCreate

        rec = self._get(rec_id, home_id)
        data = RuleCreate(
            name=name or rec.title,
            device_id=rec.device_id,
            when=Condition(**rec.when_json),
            then=Action(**rec.then_json),
            until=Condition(**rec.until_json) if rec.until_json else None,
            enabled=True,
            auto_apply=auto_apply,
        )
        rule = self.engine.create(home_id, None, data, source=RuleSource.RECOMMENDATION)
        rec.status = RecommendationStatus.ACCEPTED
        self.db.commit()
        return rule

    def dismiss(self, rec_id: int, home_id: int) -> Recommendation:
        rec = self._get(rec_id, home_id)
        rec.status = RecommendationStatus.DISMISSED
        rec.dismissed_until = now() + timedelta(days=settings.recommendation_dismiss_days)
        self.db.commit()
        return rec

    # ----------------------------------------------------------- helpers
    def _is_allowed(self, home_id: int, signature: str) -> bool:
        """No duplicate active rec; respect 30-day dismissal (REQ-4.4.5)."""
        for existing in self.repo.by_signature(home_id, signature):
            if existing.status == RecommendationStatus.ACTIVE:
                return False
            if existing.status == RecommendationStatus.ACCEPTED:
                return False
            if (
                existing.status == RecommendationStatus.DISMISSED
                and existing.dismissed_until
                and existing.dismissed_until > now()
            ):
                return False
        return True

    def _enforce_max_active(self, home_id: int) -> None:
        active = self.repo.active_for_home(home_id)
        active.sort(key=lambda r: r.estimated_monthly_saving_vnd, reverse=True)
        for extra in active[settings.recommendation_max_active:]:
            extra.status = RecommendationStatus.EXPIRED
        self.db.commit()

    def _get(self, rec_id: int, home_id: int) -> Recommendation:
        from ..core.errors import NotFoundError

        rec = self.db.get(Recommendation, rec_id)
        if rec is None or rec.home_id != home_id:
            raise NotFoundError("Recommendation not found")
        return rec
