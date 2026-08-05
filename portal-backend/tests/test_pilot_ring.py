"""Tests for pilot_ring (§7.2.1 phased agent rollout). Pure stdlib — run with:
pytest, or directly via: `PYTHONPATH=. python3 tests/test_pilot_ring.py`"""
from datetime import datetime, timedelta, timezone

from app.integrations.pilot_ring import (
    Ring,
    assign_ring,
    plan_rollout,
    summarize_rollout,
)


def test_assignment_is_deterministic():
    assert assign_ring("ep-123") == assign_ring("ep-123")


def test_roughly_expected_pilot_proportion():
    endpoints = [f"ep-{i}" for i in range(2000)]
    pilots = [e for e in endpoints if assign_ring(e, pilot_percent=10) == Ring.PILOT]
    # Not an exact 10% (hash bucketing), but should be in a sane range.
    assert 100 < len(pilots) < 400


def test_zero_percent_pilot_puts_everyone_in_fleet():
    endpoints = [f"ep-{i}" for i in range(200)]
    assert all(assign_ring(e, pilot_percent=0) == Ring.FLEET for e in endpoints)


def test_no_pilot_push_yet_blocks_fleet():
    now = datetime.now(timezone.utc)
    decisions = plan_rollout(["a", "b", "c"], pilot_started_at=None, now=now)
    fleet_decisions = [d for d in decisions.values() if d.ring == Ring.FLEET]
    assert fleet_decisions  # sanity: at least one endpoint landed in fleet
    assert all(not d.eligible_now for d in fleet_decisions)


def test_fleet_blocked_before_bake_period_elapses():
    now = datetime.now(timezone.utc)
    started = now - timedelta(hours=5)
    decisions = plan_rollout(
        [f"ep-{i}" for i in range(50)], pilot_started_at=started, now=now, bake_period_hours=48
    )
    fleet_decisions = [d for d in decisions.values() if d.ring == Ring.FLEET]
    assert all(not d.eligible_now for d in fleet_decisions)


def test_fleet_eligible_after_bake_period_with_no_regressions():
    now = datetime.now(timezone.utc)
    started = now - timedelta(hours=72)
    decisions = plan_rollout(
        [f"ep-{i}" for i in range(50)],
        pilot_started_at=started,
        now=now,
        bake_period_hours=48,
        pilot_stale_agents=0,
    )
    fleet_decisions = [d for d in decisions.values() if d.ring == Ring.FLEET]
    assert fleet_decisions
    assert all(d.eligible_now for d in fleet_decisions)


def test_fleet_stays_blocked_if_pilot_shows_regressions():
    now = datetime.now(timezone.utc)
    started = now - timedelta(hours=72)
    decisions = plan_rollout(
        [f"ep-{i}" for i in range(50)],
        pilot_started_at=started,
        now=now,
        bake_period_hours=48,
        pilot_stale_agents=2,
    )
    fleet_decisions = [d for d in decisions.values() if d.ring == Ring.FLEET]
    assert fleet_decisions
    assert all(not d.eligible_now for d in fleet_decisions)
    assert "drift" in fleet_decisions[0].reason


def test_pilot_ring_always_eligible_immediately():
    now = datetime.now(timezone.utc)
    decisions = plan_rollout([f"ep-{i}" for i in range(50)], pilot_started_at=None, now=now)
    pilot_decisions = [d for d in decisions.values() if d.ring == Ring.PILOT]
    assert pilot_decisions
    assert all(d.eligible_now for d in pilot_decisions)


def test_summarize_rollout_counts():
    now = datetime.now(timezone.utc)
    started = now - timedelta(hours=72)
    decisions = plan_rollout(
        [f"ep-{i}" for i in range(100)], pilot_started_at=started, now=now, bake_period_hours=48
    )
    summary = summarize_rollout(decisions)
    assert summary["pilot_count"] + summary["fleet_eligible_count"] + summary["fleet_waiting_count"] == 100


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
