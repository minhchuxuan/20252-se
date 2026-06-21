"""Rule scheduler — background async loop (REQ-4.3 auto-actions, REQ-4.5.4
measured savings accrual, REQ-4.4 periodic habit analysis).

Separate from the simulator so automation logic is independent of telemetry
generation (low coupling). Each tick it:
  1. evaluates every enabled rule and fires those whose WHEN holds,
  2. accrues measured savings for actively-saving rules,
  3. periodically re-runs the habit miner.
"""
from __future__ import annotations

import asyncio
import logging

from ..config import settings
from ..core.clock import now
from ..core.events import EventType, bus
from ..database import SessionLocal
from ..domain.enums import Initiator
from ..domain.models import Home
from ..repositories import HomeRepository, RuleRepository
from .optimization_service import OptimizationService
from .recommendation_service import RecommendationService
from .rule_engine import RuleEngine

logger = logging.getLogger("sheo.scheduler")

_TICK_SECONDS = 15.0
_ANALYZE_EVERY_TICKS = 20   # ~ every 5 minutes


class SchedulerEngine:
    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._running = False
        self._ticks = 0

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._running = True
            self._task = asyncio.create_task(self._run())
            logger.info("scheduler started (interval=%.1fs)", _TICK_SECONDS)

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _run(self) -> None:
        while self._running:
            try:
                self._tick_once()
            except Exception:
                logger.exception("scheduler tick failed")
            self._ticks += 1
            await asyncio.sleep(_TICK_SECONDS)

    def _tick_once(self) -> None:
        db = SessionLocal()
        try:
            homes = HomeRepository(db).list()
            engine = RuleEngine(db)
            optimizer = OptimizationService(db)
            for home in homes:
                self._evaluate_home(db, engine, optimizer, home)
                if self._ticks % _ANALYZE_EVERY_TICKS == 0:
                    RecommendationService(db).analyze(home.id)
        finally:
            db.close()

    def _evaluate_home(self, db, engine: RuleEngine, optimizer: OptimizationService, home: Home) -> None:
        for rule in RuleRepository(db).enabled_by_home(home.id):
            if engine.evaluate(rule):
                engine.execute(rule, initiator=Initiator.SCHEDULER)
        optimizer.accrue_savings(home.id, _TICK_SECONDS)
        # REQ-4.5.5: compare measured vs estimated saving and flag drift.
        for rule in RuleRepository(db).enabled_by_home(home.id):
            optimizer.check_drift(rule.id)


engine = SchedulerEngine()
