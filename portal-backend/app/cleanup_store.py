"""
Category B scan-report / quarantine state store.

PERSISTENCE (changed this session): previously an in-memory dict that did
NOT survive a portal-backend restart. Now backed by SQLite (stdlib
`sqlite3`, zero new dependencies) via a write-through cache:

  - a module-level cache holds live ScanReport objects (so the returned
    objects share identity with the store, preserving existing test
    behaviour), and
  - every mutation is synchronously written to the DB, so a restart does
    not lose state.

By default the DB is in-memory (`AADITECH_DB_PATH` unset — keeps the
existing single-process/test behaviour). In production set
`AADITECH_DB_PATH` to a path on a persistent volume (see
docker-compose.yml) so state survives container restarts.

Function signatures are unchanged from the original design, so swapping
to a heavier store (e.g. Postgres) later still only touches this file.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import StrEnum


class ItemStatus(StrEnum):
    PENDING_APPROVAL = "pending_approval"
    QUARANTINED = "quarantined"
    RESTORED = "restored"
    PURGED = "purged"
    SKIPPED = "skipped"


class HoldType(StrEnum):
    STANDARD = "standard_hold"       # 7 days default (§3.5)
    EMERGENCY = "emergency_hold"     # 24 hours default, low-disk-space triggered scans


@dataclass
class ScanItem:
    item_id: str
    category: str          # e.g. "windows_temp", "prefetch", "recycle_bin", "windows_edb", ...
    path: str
    size_bytes: int
    last_modified: str
    hold_type: HoldType
    status: ItemStatus = ItemStatus.PENDING_APPROVAL
    quarantine_path: str | None = None
    quarantine_expires_at: str | None = None


@dataclass
class ScanReport:
    report_id: str
    endpoint_id: str
    endpoint_name: str
    triggered_by: str      # "scheduled" | "low_disk_space"
    created_at: str
    items: list[ScanItem] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Persistence (sqlite3)
# ---------------------------------------------------------------------------

_DB_PATH = os.environ.get("AADITECH_DB_PATH", "")  # "" => in-memory
_conn: sqlite3.Connection | None = None
_cache: dict[str, ScanReport] | None = None
_conn_lock = threading.RLock()  # FastAPI runs sync handlers on a threadpool; sqlite needs serialized access


def init_db(path: str = "") -> None:
    """Point the store at a persistent DB file (e.g. /data/aaditech.db).
    Pass "" (or omit) to use in-memory storage. Resets the write-through cache."""
    global _conn, _cache, _DB_PATH
    if _conn is not None:
        _conn.close()
    _conn = None
    _cache = None
    _DB_PATH = path
    _get_conn()


def _get_conn() -> sqlite3.Connection:
    global _conn
    with _conn_lock:
        if _conn is None:
            _conn = sqlite3.connect(
                _DB_PATH or ":memory:",
                check_same_thread=False,  # handlers run on FastAPI's threadpool
            )
            _conn.execute(
                "CREATE TABLE IF NOT EXISTS scan_reports "
                "(report_id TEXT PRIMARY KEY, data TEXT NOT NULL)"
            )
            _conn.commit()
        return _conn


def _ensure_cache() -> dict[str, ScanReport]:
    global _cache
    with _conn_lock:
        if _cache is None:
            _cache = {}
            conn = _get_conn()
            rows = conn.execute("SELECT data FROM scan_reports").fetchall()
            for (data,) in rows:
                report = _deserialize_report(json.loads(data))
                _cache[report.report_id] = report
        return _cache


def _save_report(report: ScanReport) -> None:
    conn = _get_conn()
    with _conn_lock:
        conn.execute(
            "INSERT OR REPLACE INTO scan_reports (report_id, data) VALUES (?, ?)",
            (report.report_id, json.dumps(_serialize_report(report))),
        )
        conn.commit()


def _serialize_item(item: ScanItem) -> dict:
    return {
        "item_id": item.item_id,
        "category": item.category,
        "path": item.path,
        "size_bytes": item.size_bytes,
        "last_modified": item.last_modified,
        "hold_type": item.hold_type.value,
        "status": item.status.value,
        "quarantine_path": item.quarantine_path,
        "quarantine_expires_at": item.quarantine_expires_at,
    }


def _deserialize_item(data: dict) -> ScanItem:
    return ScanItem(
        item_id=data["item_id"],
        category=data["category"],
        path=data["path"],
        size_bytes=data["size_bytes"],
        last_modified=data["last_modified"],
        hold_type=HoldType(data["hold_type"]),
        status=ItemStatus(data["status"]),
        quarantine_path=data["quarantine_path"],
        quarantine_expires_at=data["quarantine_expires_at"],
    )


def _serialize_report(report: ScanReport) -> dict:
    return {
        "report_id": report.report_id,
        "endpoint_id": report.endpoint_id,
        "endpoint_name": report.endpoint_name,
        "triggered_by": report.triggered_by,
        "created_at": report.created_at,
        "items": [_serialize_item(i) for i in report.items],
    }


def _deserialize_report(data: dict) -> ScanReport:
    return ScanReport(
        report_id=data["report_id"],
        endpoint_id=data["endpoint_id"],
        endpoint_name=data["endpoint_name"],
        triggered_by=data["triggered_by"],
        created_at=data["created_at"],
        items=[_deserialize_item(i) for i in data["items"]],
    )


# ---------------------------------------------------------------------------
# Public API (signatures unchanged)
# ---------------------------------------------------------------------------

def create_scan_report(endpoint_id: str, endpoint_name: str, triggered_by: str, items: list[dict]) -> ScanReport:
    report_id = str(uuid.uuid4())
    hold_type = HoldType.EMERGENCY if triggered_by == "low_disk_space" else HoldType.STANDARD

    scan_items = [
        ScanItem(
            item_id=str(uuid.uuid4()),
            category=i["category"],
            path=i["path"],
            size_bytes=i["size_bytes"],
            last_modified=i["last_modified"],
            hold_type=hold_type,
        )
        for i in items
    ]

    report = ScanReport(
        report_id=report_id,
        endpoint_id=endpoint_id,
        endpoint_name=endpoint_name,
        triggered_by=triggered_by,
        created_at=datetime.now(timezone.utc).isoformat(),
        items=scan_items,
    )
    _ensure_cache()[report_id] = report
    _save_report(report)
    return report


def get_scan_report(report_id: str) -> ScanReport | None:
    return _ensure_cache().get(report_id)


def list_scan_reports() -> list[ScanReport]:
    return list(_ensure_cache().values())


def approve_items(
    report_id: str,
    item_ids: list[str],
    quarantine_root: str,
    standard_hold_days: int,
    emergency_hold_hours: int,
) -> list[ScanItem]:
    """
    Moves approved items from PENDING_APPROVAL to QUARANTINED, computing the
    quarantine path (off-volume by default, §3.5 v1.2) and expiry per the
    item's hold type. Items NOT in item_ids remain pending/are treated as
    skipped by the caller (the engineer unchecked them in the UI).
    """
    report = _ensure_cache().get(report_id)
    if not report:
        raise KeyError(f"No such scan report: {report_id}")

    approved = []
    now = datetime.now(timezone.utc)

    for item in report.items:
        if item.item_id not in item_ids:
            continue
        if item.status != ItemStatus.PENDING_APPROVAL:
            continue

        hold_delta = (
            timedelta(hours=emergency_hold_hours)
            if item.hold_type == HoldType.EMERGENCY
            else timedelta(days=standard_hold_days)
        )
        item.status = ItemStatus.QUARANTINED
        item.quarantine_path = f"{quarantine_root.rstrip('/')}/{report.endpoint_id}/{item.item_id}"
        item.quarantine_expires_at = (now + hold_delta).isoformat()
        approved.append(item)

    _save_report(report)
    return approved


def restore_item(report_id: str, item_id: str) -> ScanItem:
    report = _ensure_cache().get(report_id)
    if not report:
        raise KeyError(f"No such scan report: {report_id}")

    for item in report.items:
        if item.item_id == item_id:
            if item.status != ItemStatus.QUARANTINED:
                raise ValueError(f"Item {item_id} is not in quarantine (status={item.status})")
            item.status = ItemStatus.RESTORED
            _save_report(report)
            return item

    raise KeyError(f"No such item: {item_id}")


def mark_item_purged(item_id: str) -> ScanItem:
    """Final QUARANTINED → PURGED transition (finding 5.5): called once the
    endpoint's agent confirms the purge deletion actually ran. Without this,
    an item's portal status would stay 'quarantined' forever even though the
    file is gone — the store must reflect reality."""
    for report in _ensure_cache().values():
        for item in report.items:
            if item.item_id != item_id:
                continue
            if item.status != ItemStatus.QUARANTINED:
                raise ValueError(
                    f"Item {item_id} is not in quarantine (status={item.status})"
                )
            item.status = ItemStatus.PURGED
            _save_report(report)
            return item
    raise KeyError(f"No such item: {item_id}")


def find_expired_quarantine_items() -> list[tuple[ScanReport, ScanItem]]:
    """Used by the ILM-driven purge job (§3.3, §7.4) to find items whose hold window has passed."""
    now = datetime.now(timezone.utc)
    expired = []
    for report in _ensure_cache().values():
        for item in report.items:
            if item.status == ItemStatus.QUARANTINED and item.quarantine_expires_at:
                expires = datetime.fromisoformat(item.quarantine_expires_at)
                if now >= expires:
                    expired.append((report, item))
    return expired
