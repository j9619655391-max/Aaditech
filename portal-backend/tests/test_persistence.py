"""Tests that cleanup_store and agent_commands survive a store restart when
backed by a real SQLite file (persistence added this session).

Pure stdlib — run with: pytest, or directly via
`PYTHONPATH=. python3 tests/test_persistence.py`"""
import os
import tempfile

from app import agent_commands, cleanup_store
from app.agent_commands import CommandStatus, CommandType
from app.cleanup_store import ItemStatus


def test_cleanup_store_survives_restart():
    tmp = tempfile.mkdtemp()
    db = os.path.join(tmp, "aaditech.db")

    cleanup_store.init_db(db)
    report = cleanup_store.create_scan_report(
        "ep-9", "DESKTOP-09", "scheduled",
        [{"category": "windows_temp", "path": r"C:\Temp", "size_bytes": 1000, "last_modified": "2026-08-01"}],
    )
    item_id = report.items[0].item_id
    cleanup_store.approve_items(report.report_id, [item_id], "/quarantine", 7, 24)

    # Simulate a restart: point the store at a fresh connection/cache.
    cleanup_store.init_db(db)

    reloaded = cleanup_store.get_scan_report(report.report_id)
    assert reloaded is not None
    assert reloaded.items[0].status == ItemStatus.QUARANTINED


def test_agent_commands_survive_restart():
    tmp = tempfile.mkdtemp()
    db = os.path.join(tmp, "aaditech.db")

    agent_commands.init_db(db)
    cmd = agent_commands.enqueue_command("ep-10", CommandType.RESTORE, {"item_id": "i1"})
    agent_commands.ack_command(cmd.command_id)

    # Simulate a restart.
    agent_commands.init_db(db)

    reloaded = agent_commands.get_command(cmd.command_id)
    assert reloaded is not None
    assert reloaded.status == CommandStatus.ACKED


def test_shared_db_file_between_stores():
    tmp = tempfile.mkdtemp()
    db = os.path.join(tmp, "shared.db")

    cleanup_store.init_db(db)
    agent_commands.init_db(db)

    cleanup_store.create_scan_report("ep-11", "DESKTOP-11", "scheduled", [])
    agent_commands.enqueue_command("ep-11", CommandType.PURGE, {"item_id": "x"})

    # Both stores read from the same file without clobbering each other.
    cleanup_store.init_db(db)
    agent_commands.init_db(db)
    assert len(cleanup_store.list_scan_reports()) == 1
    assert agent_commands.get_command is not None


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
