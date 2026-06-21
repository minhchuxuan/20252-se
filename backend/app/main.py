"""Application entry point — FastAPI app factory.

Wires the layered system together (presentation tier), maps domain errors to HTTP
status codes, and manages the lifecycle of the background simulator and scheduler.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import __version__
from .config import settings
from .core.errors import DomainError
from .database import init_db
from .api import (
    admin,
    auth,
    devices,
    monitoring,
    recommendations,
    reports,
    rules,
    savings,
    settings as settings_api,
    ws,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("sheo")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    if settings.seed_on_startup:
        from .seed import run_seed

        run_seed()
    # Wire Observers.
    from .services.notification_service import register_subscribers

    register_subscribers()
    ws.manager.wire_bus()
    # Start background loops.
    if settings.enable_background:
        from .services.scheduler import engine as scheduler_engine
        from .simulator.engine import engine as simulator_engine

        simulator_engine.start()
        scheduler_engine.start()
        logger.info("background loops started")
    yield
    if settings.enable_background:
        from .services.scheduler import engine as scheduler_engine
        from .simulator.engine import engine as simulator_engine

        await simulator_engine.stop()
        await scheduler_engine.stop()


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        description="Capability-driven IoT energy dashboard with explainable WHEN-THEN "
        "optimization and VND bill-saving estimation.",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(DomainError)
    async def domain_error_handler(_: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.message, "info": exc.detail},
        )

    for module in (auth, admin, devices, monitoring, rules, recommendations, savings, reports, settings_api):
        app.include_router(module.router)
    app.include_router(ws.router)

    @app.get("/api/health", tags=["meta"])
    def health() -> dict:
        return {"status": "ok", "app": settings.app_name, "version": __version__}

    @app.get("/", tags=["meta"])
    def root() -> dict:
        """The backend is an API only; the user interface is the Vite app."""
        return {
            "app": settings.app_name,
            "version": __version__,
            "message": "This is the API server. Open the web UI at http://localhost:5173",
            "api_docs": "/docs",
            "health": "/api/health",
            "websocket": "/ws",
        }

    return app


app = create_app()
