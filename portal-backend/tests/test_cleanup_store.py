"""Tests for cleanup_store. Pure stdlib — run with: pytest, or directly via
`PYTHONPATH=. python3 tests/test_cleanup_store.py`"""
from datetime import datetime, timedelta, timezone

from app.cleanup_store import (
    HoldType,
    ItemStatus,
    approve_items,
    create_scan_report,
    find_expired_quarantine_items,
    get_scan_report,
    restore_item,
)


def _sample_items():
    return [
        {"category": "windows_temp", "path": r"C:\Windows\Temp", "size_bytes": 1_500_000, "last_modified": "2026-07-01"},
        {"category": "recycle_bin", "path": r"C:\$Recycle.Bin", "size_bytes": 500_000, "last_modified": "2026-07-15"},
    ]


def test_scheduled_scan_gets_standard_hold():
    report = create_scan_report("ep-1", "DESKTOP-01", "scheduled", _sample_items())

    assert all(i.hold_type == HoldType.STANDARD for i in report.items)
    assert all(i.status == ItemStatus.PENDING_APPROVAL for i in report.items)


def test_low_disk_space_scan_gets_emergency_hold():
    report = create_scan_report("ep-1", "DESKTOP-01", "low_disk_space", _sample_items())

    assert all(i.hold_type == HoldType.EMERGENCY for i in report.items)


def test_approve_moves_to_quarantine_with_offvolume_path():
    report = create_scan_report("ep-2", "DESKTOP-02", "scheduled", _sample_items())
    item_ids = [i.item_id for i in report.items]

    approved = approve_items(
        report.report_id, item_ids,
        quarantine_root="\\\\fileserver\\aaditech-quarantine",
        standard_hold_days=7, emergency_hold_hours=24,
    )

    assert len(approved) == 2
    for item in approved:
        assert item.status == ItemStatus.QUARANTINED
        assert item.quarantine_path.startswith("\\\\fileserver\\aaditech-quarantine/ep-2/")
        assert item.quarantine_expires_at is not None


def test_approve_standard_hold_expires_in_7_days():
    report = create_scan_report("ep-3", "DESKTOP-03", "scheduled", _sample_items())
    item_ids = [report.items[0].item_id]

    approved = approve_items(report.report_id, item_ids, "/quarantine", 7, 24)
    expires = datetime.fromisoformat(approved[0].quarantine_expires_at)
    delta = expires - datetime.now(timezone.utc)

    assert timedelta(days=6, hours=23) < delta <= timedelta(days=7, minutes=1)


def test_approve_emergency_hold_expires_in_24_hours():
    report = create_scan_report("ep-4", "DESKTOP-04", "low_disk_space", _sample_items())
    item_ids = [report.items[0].item_id]

    approved = approve_items(report.report_id, item_ids, "/quarantine", 7, 24)
    expires = datetime.fromisoformat(approved[0].quarantine_expires_at)
    delta = expires - datetime.now(timezone.utc)

    assert timedelta(hours=23) < delta <= timedelta(hours=24, minutes=1)


def test_unselected_items_stay_pending():
    report = create_scan_report("ep-5", "DESKTOP-05", "scheduled", _sample_items())
    only_first_id = [report.items[0].item_id]

    approve_items(report.report_id, only_first_id, "/quarantine", 7, 24)
    refreshed = get_scan_report(report.report_id)

    assert refreshed.items[0].status == ItemStatus.QUARANTINED
    assert refreshed.items[1].status == ItemStatus.PENDING_APPROVAL


def test_restore_within_window():
    report = create_scan_report("ep-6", "DESKTOP-06", "scheduled", _sample_items())
    item_ids = [report.items[0].item_id]
    approve_items(report.report_id, item_ids, "/quarantine", 7, 24)

    restored = restore_item(report.report_id, item_ids[0])

    assert restored.status == ItemStatus.RESTORED


def test_cannot_restore_item_not_in_quarantine():
    report = create_scan_report("ep-7", "DESKTOP-07", "scheduled", _sample_items())

    try:
        restore_item(report.report_id, report.items[0].item_id)
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_find_expired_quarantine_items():
    report = create_scan_report("ep-8", "DESKTOP-08", "scheduled", _sample_items())
    item_ids = [i.item_id for i in report.items]
    approved = approve_items(report.report_id, item_ids, "/quarantine", 7, 24)

    # Manually backdate one item's expiry to simulate window passing
    approved[0].quarantine_expires_at = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()

    expired = find_expired_quarantine_items()
    expired_ids = [item.item_id for _, item in expired]

    assert approved[0].item_id in expired_ids
    assert approved[1].item_id not in expired_ids


if __name__ == "__main__":
    import sys
    import traceback

    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    failures = 0
    for t in tests:
        try:
            t()
            print(f"PASS: {t.__name__}")
        except Exception:
            failures += 1
            print(f"FAIL: {t.__name__}")
            traceback.print_exc()
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    sys.exit(1 if failures else 0)
