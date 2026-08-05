"""
Portal & agent health event log (spec §7.4, referenced by §7.1.1 and §7.2.1).

A single place to record operational health events that aren't security
alerts (Wazuh) or infra triggers (Zabbix) but still need to be visible on
the Aaditech Portal's health dashboard — e.g. a Grafana embed panel that
failed to load even after retry, or an agent version-drift warning
(§7.2.1). Distinct from app.audit, which is for compliance-relevant
actions (deletions, approvals, role changes); this module is for
operational/diagnostic events.
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

_CONFIGURED_HEALTH_LOG_PATH = Path(
    os.environ.get("AADITECH_HEALTH_LOG_PATH", "/var/log/aaditech/health.jsonl")
)
# Resolved on first write so an unwritable default (e.g. /var/log as non-root)
# degrades gracefully to a per-user temp location instead of 500ing the request.
_resolved_health_log_path: Path | None = None


def _get_health_log_path() -> Path:
    global _resolved_health_log_path
    if _resolved_health_log_path is not None:
        return _resolved_health_log_path
    try:
        _CONFIGURED_HEALTH_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(_CONFIGURED_HEALTH_LOG_PATH, "a", encoding="utf-8") as _f:
            _f.write("")
        _resolved_health_log_path = _CONFIGURED_HEALTH_LOG_PATH
    except OSError:
        fallback = Path(tempfile.gettempdir()) / "aaditech" / "health.jsonl"
        fallback.parent.mkdir(parents=True, exist_ok=True)
        _resolved_health_log_path = fallback
    return _resolved_health_log_path


def log_health_event(component: str, severity: str, message: str, reported_by: str | None = None) -> dict:
    """severity: 'info' | 'warning' | 'error'"""
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "component": component,
        "severity": severity,
        "message": message,
        "reported_by": reported_by,
    }
    path = _get_health_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def read_health_events(limit: int = 100, severity: str | None = None) -> list[dict]:
    path = _get_health_log_path()
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)
            if severity is None or entry.get("severity") == severity:
                entries.append(entry)
    return list(reversed(entries))[:limit]
