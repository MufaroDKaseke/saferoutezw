from fastapi.testclient import TestClient

from app.main import app


def test_health_without_external_services(monkeypatch):
    for key in ("POSTGRES_USER", "POSTGRES_PASSWORD"):
        monkeypatch.delenv(key, raising=False)
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "saferoutezw-api",
        "version": "0.1.0",
    }
