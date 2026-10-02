"""Smoke tests for the API process."""

from app.main import app
from fastapi.testclient import TestClient


def test_health_check_returns_ok() -> None:
    """The liveness route is available without external services."""
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
