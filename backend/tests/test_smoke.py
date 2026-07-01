"""Smoke tests for the bootstrap skeleton."""

from __future__ import annotations

from fastapi.testclient import TestClient

from payment_tracking_agent import __version__
from payment_tracking_agent.main import app


def test_health_endpoint_returns_ok() -> None:
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": __version__}
