"""
Agent update pilot-ring assignment (spec §7.2.1).

"Phased rollout by default: updates pushed to a pilot ring first, then the
full fleet, to catch agent-side regressions before they're fleet-wide."
This module owns the "which ring is this endpoint in, and has the pilot
ring finished its bake period" decision. The actual push (GPO/Intune) is
outside this codebase's scope per spec §7.2 — this module tells the
deployment automation WHICH endpoints to target at each stage, and
version_drift.py (already wired) reports back whether the push succeeded.

Ring assignment is deterministic (hash of endpoint_id), not random, so:
  - re-running assignment for the same fleet is stable/reproducible
  - a given endpoint is consistently a pilot across successive rollouts,
    so pilot-ring signal accumulates meaningfully over time instead of
    being diluted across the whole fleet release-to-release
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum


class Ring(StrEnum):
    PILOT = "pilot"
    FLEET = "fleet"


DEFAULT_PILOT_PERCENT = 10          # % of fleet in the pilot ring
DEFAULT_BAKE_PERIOD_HOURS = 48      # minimum pilot soak time before fleet promotion


@dataclass
class RolloutDecision:
    ring: Ring
    eligible_now: bool
    reason: str


def assign_ring(endpoint_id: str, pilot_percent: int = DEFAULT_PILOT_PERCENT) -> Ring:
    """
    Deterministically buckets an endpoint into PILOT or FLEET based on a
    stable hash of its id, so ring membership doesn't shuffle between runs.
    """
    if not 0 <= pilot_percent <= 100:
        raise ValueError("pilot_percent must be between 0 and 100")

    digest = hashlib.sha256(endpoint_id.encode("utf-8")).hexdigest()
    bucket = int(digest[:8], 16) % 100
    return Ring.PILOT if bucket < pilot_percent else Ring.FLEET


def plan_rollout(
    endpoint_ids: list[str],
    pilot_started_at: datetime | None,
    now: datetime,
    pilot_percent: int = DEFAULT_PILOT_PERCENT,
    bake_period_hours: int = DEFAULT_BAKE_PERIOD_HOURS,
    pilot_stale_agents: int = 0,
) -> dict[str, RolloutDecision]:
    """
    Decides, per endpoint, whether it's eligible for the update push right now.

    - pilot_started_at=None  -> no pilot has been pushed yet: only PILOT ring
      is eligible now, FLEET waits.
    - pilot_started_at set, bake period not yet elapsed -> FLEET still waits,
      regardless of how clean the pilot looks so far (minimum soak time is a
      floor, not a target to skip when things look fine early).
    - pilot_started_at set, bake period elapsed, AND pilot_stale_agents == 0
      -> FLEET is eligible (no regressions detected on the pilot ring).
    - pilot_started_at set, bake period elapsed, but pilot_stale_agents > 0
      -> FLEET stays blocked: the pilot itself surfaced version-drift/failure
      signal (via version_drift.py) that needs investigation before fleet-wide push.
    """
    decisions: dict[str, RolloutDecision] = {}

    if pilot_started_at is None:
        fleet_eligible = False
        fleet_reason = "pilot ring has not been pushed yet"
    else:
        bake_elapsed = now - pilot_started_at >= timedelta(hours=bake_period_hours)
        if not bake_elapsed:
            fleet_eligible = False
            fleet_reason = (
                f"pilot bake period not yet elapsed "
                f"({bake_period_hours}h minimum since {pilot_started_at.isoformat()})"
            )
        elif pilot_stale_agents > 0:
            fleet_eligible = False
            fleet_reason = (
                f"{pilot_stale_agents} pilot agent(s) show version drift/failure — "
                "investigate before fleet-wide push"
            )
        else:
            fleet_eligible = True
            fleet_reason = "bake period elapsed with no pilot regressions"

    for endpoint_id in endpoint_ids:
        ring = assign_ring(endpoint_id, pilot_percent=pilot_percent)
        if ring == Ring.PILOT:
            decisions[endpoint_id] = RolloutDecision(
                ring=Ring.PILOT, eligible_now=True, reason="pilot ring is always eligible immediately"
            )
        else:
            decisions[endpoint_id] = RolloutDecision(
                ring=Ring.FLEET, eligible_now=fleet_eligible, reason=fleet_reason
            )

    return decisions


def summarize_rollout(decisions: dict[str, RolloutDecision]) -> dict:
    pilot = [e for e, d in decisions.items() if d.ring == Ring.PILOT]
    fleet_eligible = [e for e, d in decisions.items() if d.ring == Ring.FLEET and d.eligible_now]
    fleet_waiting = [e for e, d in decisions.items() if d.ring == Ring.FLEET and not d.eligible_now]
    return {
        "pilot_count": len(pilot),
        "fleet_eligible_count": len(fleet_eligible),
        "fleet_waiting_count": len(fleet_waiting),
        "pilot_endpoints": pilot,
        "fleet_eligible_endpoints": fleet_eligible,
    }
