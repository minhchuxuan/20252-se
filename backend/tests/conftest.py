"""Pytest fixtures.

A session-scoped TestClient boots the app against a throwaway SQLite file with
the demo seed (so acceptance tests have 21 days of telemetry, devices, rules and
recommendations) but with the background simulator/scheduler DISABLED for
determinism. Environment is configured before the app is imported.
"""
from __future__ import annotations

import os

# Configure the app BEFORE importing it (settings are cached).
_TEST_DB = f"/tmp/sheo_test_{os.getpid()}.db"
if os.path.exists(_TEST_DB):
    os.remove(_TEST_DB)
os.environ["SHEO_DATABASE_URL"] = f"sqlite:///{_TEST_DB}"
os.environ["SHEO_ENABLE_BACKGROUND"] = "0"
os.environ["SHEO_SEED_ON_STARTUP"] = "1"

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c
    if os.path.exists(_TEST_DB):
        os.remove(_TEST_DB)


def _login(client, email: str) -> dict:
    res = client.post("/api/auth/login", json={"email": email, "password": "demo1234"})
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


@pytest.fixture(scope="session")
def admin_headers(client):
    return _login(client, "admin@demo.com")


@pytest.fixture(scope="session")
def resident_headers(client):
    return _login(client, "resident@demo.com")


@pytest.fixture(scope="session")
def dev_headers(client):
    return _login(client, "dev@demo.com")


@pytest.fixture
def devices(client, dev_headers):
    # Devices belong to a unit. The Developer's maintenance unit carries the full
    # default package and the Developer can both read and operate it, so it is the
    # convenient acting unit for behaviour tests (the Resident's grants are tested
    # separately in test_auth_rbac).
    return client.get("/api/devices", headers=dev_headers).json()


def device_of(devices, dtype):
    return next(d for d in devices if d["type"] == dtype)
