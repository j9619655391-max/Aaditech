"""
Agent version/patch drift detection (spec §7.2.1).

v1.0 covered initial agent install but not fleet-wide version drift over
time as Wazuh, Zabbix, and MeshCentral ship agent updates independently.
This module compares each endpoint's reported agent version against the
current manager/expected version and flags endpoints more than the
configured threshold behind — routed through the alerting backbone
(§3.6), not left to manual audit.

Version comparison uses simple (major, minor) tuples — sufficient for a
"how many minor versions behind" threshold check without needing a full
semver library.
"""
from __future__ import annotations

from dataclasses import dataclass

MISMATCH_THRESHOLD_MINOR_VERSIONS = 2


@dataclass
class VersionDriftResult:
    agent_id: str
    agent_name: str
    installed_version: str
    expected_version: str
    minor_versions_behind: int
    is_stale: bool


def _parse_minor(version: str) -> tuple[int, int]:
    """Parses 'v4.9.0' or '4.9.0' into (major, minor). Falls back to (0, 0) if unparseable."""
    cleaned = version.lstrip("v")
    parts = cleaned.split(".")
    try:
        return int(parts[0]), int(parts[1])
    except (IndexError, ValueError):
        return (0, 0)


def check_version_drift(
    agents: list[dict],
    expected_version: str,
    threshold: int = MISMATCH_THRESHOLD_MINOR_VERSIONS,
) -> list[VersionDriftResult]:
    """
    agents: list of {"id": ..., "name": ..., "version": ...} as returned by
    WazuhClient.get_agents_with_versions(). Returns a drift result per agent,
    with is_stale=True for any agent more than `threshold` minor versions
    behind the expected/manager version.
    """
    exp_major, exp_minor = _parse_minor(expected_version)
    results = []

    for agent in agents:
        installed = agent.get("version", "unknown")
        inst_major, inst_minor = _parse_minor(installed)

        if inst_major != exp_major:
            # Major version mismatch is always considered stale regardless of threshold
            behind = threshold + 1
        else:
            behind = max(0, exp_minor - inst_minor)

        results.append(
            VersionDriftResult(
                agent_id=agent.get("id", "unknown"),
                agent_name=agent.get("name", "unknown"),
                installed_version=installed,
                expected_version=expected_version,
                minor_versions_behind=behind,
                is_stale=behind > threshold,
            )
        )

    return results


def summarize_drift(results: list[VersionDriftResult]) -> dict:
    stale = [r for r in results if r.is_stale]
    return {
        "total_agents": len(results),
        "stale_agents": len(stale),
        "stale_agent_names": [r.agent_name for r in stale],
    }
