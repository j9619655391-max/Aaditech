"""Integration tests for the Category B cleanup router. Run with: pytest tests/test_cleanup_router.py"""
from fastapi.testclient import TestClient

from app.auth import create_access_token
from app.main import app

client = TestClient(app)


def _headers(roles):
    token = create_access_token("test-engineer", roles)
    return {"Authorization": f"Bearer {token}"}


def test_submit_scan_report_requires_auth():
    resp = client.post("/cleanup/scan-reports", json={
        "endpoint_id": "ep-1", "endpoint_name": "PC1", "triggered_by": "scheduled", "items": []
    })
    assert resp.status_code == 403


def test_viewer_can_submit_and_view_but_not_approve():
    headers = _headers(["viewer"])
    submit = client.post(
        "/cleanup/scan-reports",
        headers=headers,
        json={
            "endpoint_id": "ep-2",
            "endpoint_name": "PC2",
            "triggered_by": "scheduled",
            "items": [
                {"category": "windows_temp", "path": "C:\\Windows\\Temp",
                 "size_bytes": 1000, "last_modified": "2026-08-01"}
            ],
        },
    )
    assert submit.status_code == 200
    report_id = submit.json()["report_id"]

    view = client.get(f"/cleanup/scan-reports/{report_id}", headers=headers)
    assert view.status_code == 200

    approve = client.post(
        f"/cleanup/scan-reports/{report_id}/approve",
        headers=headers,
        json={"item_ids": [view.json()["items"][0]["item_id"]]},
    )
    assert approve.status_code == 403  # Viewer cannot approve — closes risk R-8


def test_cleanup_approver_can_approve_and_restore():
    headers = _headers(["cleanup_approver"])
    submit = client.post(
        "/cleanup/scan-reports",
        headers=headers,
        json={
            "endpoint_id": "ep-3",
            "endpoint_name": "PC3",
            "triggered_by": "low_disk_space",
            "items": [
                {"category": "recycle_bin", "path": "C:\\$Recycle.Bin",
                 "size_bytes": 5000, "last_modified": "2026-08-01"}
            ],
        },
    )
    report_id = submit.json()["report_id"]
    item_id = submit.json()["items"][0]["item_id"]

    approve = client.post(
        f"/cleanup/scan-reports/{report_id}/approve",
        headers=headers,
        json={"item_ids": [item_id]},
    )
    assert approve.status_code == 200
    body = approve.json()
    assert body["approved_count"] == 1
    assert body["items"][0]["hold_type"] == "emergency_hold"  # low_disk_space -> emergency (§3.5 v1.2)

    restore = client.post(f"/cleanup/items/{report_id}/{item_id}/restore", headers=headers)
    assert restore.status_code == 200
    body = restore.json()
    assert body["item"]["status"] == "restored"
    assert body["command_id"]  # a restore command was enqueued for the agent

    pending = client.get(f"/cleanup/agent/ep-3/commands", headers=headers)
    assert pending.status_code == 200
    assert any(c["command_id"] == body["command_id"] for c in pending.json())


def test_purge_expired_has_no_rbac_gate_but_is_system_only_by_convention():
    # No auth header at all — purge is meant to be called by the ILM cron
    # job with a service credential, not a user session; documented as such
    # in the router. This test just confirms the endpoint responds cleanly.
    resp = client.post("/cleanup/purge-expired")
    assert resp.status_code == 200
    assert "purged_count" in resp.json()
