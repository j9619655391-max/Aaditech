"""
App-level smoke tests. Verifies the FastAPI app boots, all routers are
wired, and protected routes correctly reject unauthenticated requests.
Run with: pytest tests/test_main.py
"""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_endpoint():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_alerts_requires_auth():
    resp = client.get("/alerts/")
    assert resp.status_code == 403  # HTTPBearer rejects missing credentials


def test_metrics_requires_auth():
    resp = client.get("/metrics/hosts")
    assert resp.status_code == 403


def test_tickets_requires_auth():
    resp = client.post("/tickets/", json={"title": "x", "description": "y"})
    assert resp.status_code == 403


def test_ticket_validation_rejects_short_title():
    from app.auth import create_access_token

    token = create_access_token("jdoe", ["support_engineer"])
    resp = client.post(
        "/tickets/",
        json={"title": "ab", "description": "valid description"},
        headers={"Authorization": f"Bearer {token}"},
    )
    # title min_length=3 → "ab" should fail validation before hitting GLPI
    assert resp.status_code == 422


def test_openapi_docs_available():
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    assert resp.json()["info"]["title"].startswith("Aaditech")
