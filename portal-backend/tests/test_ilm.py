"""Tests for the ILM scheduler (app/ilm.py) and the QUARANTINED→PURGED
transition — both were documented but never existed (findings 2.8, 5.5)."""
import os
from datetime import datetime, timedelta, timezone

from app import ilm
from app.cleanup_store import (
    ItemStatus,
    approve_items,
    create_scan_report,
    init_db,
    mark_item_purged,
)
from app.agent_commands import CommandType, complete_command, get_command, init_db as init_cmd_db


def _seed_expired_item():
    init_db("")
    init_cmd_db("")
    report = create_scan_report("ep-ilm", "PC-ILM", "scheduled", [
        {"category": "windows_temp", "path": "C:\\Temp", "size_bytes": 1000, "last_modified": "2026-07-01"}
    ])
    approved = approve_items(
        report.report_id, [i.item_id for i in report.items],
        quarantine_root="\\\\fileserver\\q",
        standard_hold_days=7, emergency_hold_hours=24,
    )
    item = approved[0]
    # Force the item past its hold window.
    item.quarantine_expires_at = (
        datetime.now(timezone.utc) - timedelta(hours=1)
    ).isoformat()
    return report, item


def test_run_purge_cycle_enqueues_purge_commands():
    report, item = _seed_expired_item()

    result = ilm.run_purge_cycle()

    assert result["purged_count"] == 1
    command = get_command(result["items"][0]["command_id"])
    assert command is not None
    assert command.command_type == CommandType.PURGE
    assert command.payload["item_id"] == item.item_id


def test_mark_item_purged_transitions_status():
    report, item = _seed_expired_item()

    updated = mark_item_purged(item.item_id)

    assert updated.status == ItemStatus.PURGED


def test_mark_item_purged_rejects_non_quarantined():
    report, item = _seed_expired_item()
    from app.cleanup_store import restore_item

    restore_item(report.report_id, item.item_id)  # -> RESTORED

    try:
        mark_item_purged(item.item_id)
        assert False, "should raise ValueError"
    except ValueError:
        pass


def test_complete_purge_command_marks_store_purged():
    from fastapi.testclient import TestClient

    from app.main import app
    from app.auth import create_access_token

    report, item = _seed_expired_item()
    result = ilm.run_purge_cycle()
    command_id = result["items"][0]["command_id"]

    token = create_access_token("viewer", ["viewer"])
    resp = TestClient(app).post(
        f"/cleanup/agent/commands/{command_id}/complete",
        headers={"Authorization": f"Bearer {token}"},
        json={"success": True, "result": "purged"},
    )
    assert resp.status_code == 200

    # The PURGE completion should have flowed through to the store.
    from app.cleanup_store import get_scan_report
    fresh = get_scan_report(report.report_id)
    assert fresh.items[0].status == ItemStatus.PURGED