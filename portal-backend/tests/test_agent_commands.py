"""Tests for agent_commands (the portal->agent restore/purge command queue).
Pure stdlib — run with: pytest, or directly via:
`PYTHONPATH=. python3 tests/test_agent_commands.py`"""
from app.agent_commands import (
    CommandStatus,
    CommandType,
    ack_command,
    complete_command,
    enqueue_command,
    get_command,
    list_pending_commands,
)


def test_enqueue_creates_pending_command():
    cmd = enqueue_command("ep-1", CommandType.RESTORE, {"item_id": "i1"})
    assert cmd.status == CommandStatus.PENDING
    assert cmd.endpoint_id == "ep-1"
    assert cmd.command_type == CommandType.RESTORE


def test_list_pending_only_returns_that_endpoints_pending_commands():
    enqueue_command("ep-2", CommandType.RESTORE, {"item_id": "a"})
    enqueue_command("ep-2", CommandType.PURGE, {"item_id": "b"})
    enqueue_command("ep-3", CommandType.RESTORE, {"item_id": "c"})

    pending = list_pending_commands("ep-2")
    assert len(pending) == 2
    assert all(c.endpoint_id == "ep-2" for c in pending)


def test_ack_moves_command_out_of_pending_list():
    cmd = enqueue_command("ep-4", CommandType.RESTORE, {"item_id": "d"})
    ack_command(cmd.command_id)

    assert get_command(cmd.command_id).status == CommandStatus.ACKED
    assert cmd.command_id not in [c.command_id for c in list_pending_commands("ep-4")]


def test_complete_success_sets_done_and_result():
    cmd = enqueue_command("ep-5", CommandType.PURGE, {"item_id": "e"})
    ack_command(cmd.command_id)
    completed = complete_command(cmd.command_id, success=True, result="purged")

    assert completed.status == CommandStatus.DONE
    assert completed.result == "purged"
    assert completed.completed_at is not None


def test_complete_failure_sets_failed_status():
    cmd = enqueue_command("ep-6", CommandType.RESTORE, {"item_id": "f"})
    completed = complete_command(cmd.command_id, success=False, result="access denied")

    assert completed.status == CommandStatus.FAILED
    assert completed.result == "access denied"


def test_ack_unknown_command_raises_keyerror():
    try:
        ack_command("does-not-exist")
        assert False, "expected KeyError"
    except KeyError:
        pass


def test_quarantine_is_a_supported_command_type():
    cmd = enqueue_command(
        "ep-7",
        CommandType.QUARANTINE,
        {"item_id": "g", "path": "C:\\Temp\\x", "quarantine_path": "Q:/ep-7/g"},
    )
    assert cmd.command_type == CommandType.QUARANTINE
    assert cmd.status == CommandStatus.PENDING
    pending = list_pending_commands("ep-7")
    assert cmd.command_id in [c.command_id for c in pending]


def test_quarantine_command_full_lifecycle():
    cmd = enqueue_command(
        "ep-8",
        CommandType.QUARANTINE,
        {"item_id": "h", "path": "C:\\Temp\\y", "quarantine_path": "Q:/ep-8/h"},
    )
    ack_command(cmd.command_id)
    done = complete_command(cmd.command_id, success=True, result="quarantined")

    assert done.status == CommandStatus.DONE
    assert done.result == "quarantined"


if __name__ == "__main__":
    # Allows direct execution without pytest installed: python3 tests/test_agent_commands.py
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
