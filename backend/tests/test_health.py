from fastapi.testclient import TestClient

from backend.app.main import app


def test_health_endpoint() -> None:
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["service"] == "arix-local-bridge"


def test_memory_snapshot_exposes_anchor_nodes() -> None:
    with TestClient(app) as client:
        response = client.get("/api/memory/snapshot")

    assert response.status_code == 200
    payload = response.json()
    assert {"ai_root", "user_root"}.issubset(payload["nodes"])
    assert payload["anchors"] == {"ai_root": True, "user_root": True}
