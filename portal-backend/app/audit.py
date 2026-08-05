"""
Audit logging.

Every action that spec §3.5 and §7.1 require to be audit-logged (Category B
approve/execute, restore-from-quarantine, and portal RBAC role-membership
changes) goes through this module. Entries are written as structured JSON
Lines to a local log file that Wazuh's log collector (already configured to
watch the endpoint/agent log paths — see §7.4) picks up and forwards to
central OpenSearch storage, giving audit entries the same searchability and
retention (via the existing ILM policy, §3.3) as every other platform log —
no separate audit datastore to maintain.
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path

_CONFIGURED_AUDIT_LOG_PATH = Path(os.environ.get("AADITECH_AUDIT_LOG_PATH", "/var/log/aaditech/audit.jsonl"))
# Resolved on first write so an unwritable default (e.g. /var/log as non-root)
# degrades gracefully to a per-user temp location instead of 500ing the request.
_resolved_audit_log_path: Path | None = None


def _get_audit_log_path() -> Path:
    global _resolved_audit_log_path
    if _resolved_audit_log_path is not None:
        return _resolved_audit_log_path
    try:
        _CONFIGURED_AUDIT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(_CONFIGURED_AUDIT_LOG_PATH, "a", encoding="utf-8") as _f:
            _f.write("")
        _resolved_audit_log_path = _CONFIGURED_AUDIT_LOG_PATH
    except OSError:
        fallback = Path(tempfile.gettempdir()) / "aaditech" / "audit.jsonl"
        fallback.parent.mkdir(parents=True, exist_ok=True)
        _resolved_audit_log_path = fallback
    return _resolved_audit_log_path


class AuditAction(StrEnum):
    CATEGORY_B_APPROVE_EXECUTE = "category_b_approve_execute"
    CATEGORY_B_RESTORE = "category_b_restore"
    CATEGORY_B_PURGE = "category_b_purge"
    ROLE_GRANTED = "role_granted"
    ROLE_REVOKED = "role_revoked"
    TICKET_CREATED = "ticket_created"
    REMOTE_SESSION_STARTED = "remote_session_started"


def write_audit_entry(
    action: AuditAction,
    actor: str,
    details: dict,
) -> dict:
    """
    Appends one audit entry. Every entry carries the same identity/timestamp
    shape regardless of action type, per spec §3.5's requirement that
    restoration be "audit-logged with the same identity/timestamp fields as
    deletion."
    """
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": action.value,
        "actor": actor,
        "details": details,
    }

    path = _get_audit_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")

    return entry


def read_audit_entries(limit: int = 100, action: AuditAction | None = None) -> list[dict]:
    """Reads recent audit entries (newest first). Used by the portal's audit trail view."""
    path = _get_audit_log_path()
    if not path.exists():
        return []

    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)
            if action is None or entry.get("action") == action.value:
                entries.append(entry)

    return list(reversed(entries))[:limit]
