import pytest
from fastapi.testclient import TestClient


def test_live_returns_request_id(client: TestClient) -> None:
    response = client.get("/health/live", headers={"x-request-id": "req-smoke"})
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["x-request-id"] == "req-smoke"


def test_live_replaces_unsafe_request_id(client: TestClient) -> None:
    response = client.get("/health/live", headers={"x-request-id": "bad id"})
    assert response.status_code == 200
    assert response.headers["x-request-id"] != "bad id"


def test_ready_reports_connected_database(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.api.health.probe_database", lambda _engine: True)
    response = client.get("/health/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "connected"
    assert body["rules_loaded"] is True
    assert body["recommendations_enabled"] is False


def test_ready_fails_closed_when_database_is_down(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.api.health.probe_database", lambda _engine: False)
    response = client.get("/health/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "unavailable"
    assert body["database"] == "unavailable"
    assert body["recommendations_enabled"] is False
