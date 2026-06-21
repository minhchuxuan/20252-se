"""In-process event bus — the Observer pattern (SE Intro 14).

Publishers (the simulator/telemetry ingestion, the rule engine) emit events
without knowing who consumes them. Subscribers (WebSocket broadcaster, rule
engine, notification service, savings accumulator) register independently. This
keeps the subsystems loosely coupled (low coupling, high cohesion).

Both sync and async subscribers are supported; async ones are scheduled on the
running event loop when available.
"""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from collections.abc import Awaitable, Callable
from enum import Enum
from typing import Any

logger = logging.getLogger("sheo.events")


class EventType(str, Enum):
    TELEMETRY_READING = "telemetry.reading"   # payload: {"device_id", "reading": {...}}
    DEVICE_OFFLINE = "device.offline"          # payload: {"device_id"}
    DEVICE_ONLINE = "device.online"            # payload: {"device_id"}
    RULE_FIRED = "rule.fired"                  # payload: {"rule_id", "execution_id", ...}
    RECOMMENDATION_READY = "recommendation.ready"
    NOTIFICATION_CREATED = "notification.created"
    COMMAND_APPLIED = "command.applied"


Handler = Callable[[dict[str, Any]], None | Awaitable[None]]


class EventBus:
    def __init__(self) -> None:
        self._subscribers: dict[EventType, list[Handler]] = defaultdict(list)

    def subscribe(self, event_type: EventType, handler: Handler) -> None:
        self._subscribers[event_type].append(handler)

    def unsubscribe(self, event_type: EventType, handler: Handler) -> None:
        if handler in self._subscribers[event_type]:
            self._subscribers[event_type].remove(handler)

    def publish(self, event_type: EventType, payload: dict[str, Any]) -> None:
        for handler in list(self._subscribers.get(event_type, [])):
            try:
                result = handler(payload)
                if asyncio.iscoroutine(result):
                    self._schedule(result)
            except Exception:  # a faulty subscriber must not break the publisher
                logger.exception("event subscriber failed for %s", event_type)

    @staticmethod
    def _schedule(coro: Awaitable[None]) -> None:
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(coro)
        except RuntimeError:
            # No running loop (e.g. synchronous test/seed context): run to completion.
            asyncio.run(coro)  # type: ignore[arg-type]


# Process-wide singleton bus.
bus = EventBus()
