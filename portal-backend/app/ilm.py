"""
ILM scheduler — the "existing ILM cron job" the spec (§3.3, §7.4) and docs
reference but that never actually ran anywhere. Runs purge-expired on a timer
inside the portal backend process (a background asyncio task started from
app.main's lifespan), so expired quarantine items are actually purged without
relying on an external cron that was never installed.

The same cycle is exposed over HTTP (POST /cleanup/purge-expired, service-token
guarded) so an external scheduler — or an operator — can trigger it manually;
both paths funnel through `run_purge_cycle()` so behaviour is identical.
"""
from __future__ import annotations

import asyncio
import os

from app.audit import AuditAction, write_audit_entry
from app.cleanup_store import find_expired_quarantine_items
from app.agent_commands import CommandType, enqueue_command

# Interval between cycles (seconds). Env-tunable; 6h default matches the
# documented ILM cadence.
_ILM_INTERVAL_SECONDS = int(os.environ.get("AADITECH_ILM_INTERVAL_SECONDS", "21600"))

# One-time marker so a fresh process doesn't purge immediately on boot before
# stores are ready (main.py init_db runs first, so this is mostly belt-and-braces).
_msg_queue: asyncio.Queue[str] | None = None


def run_purge_cycle() -> dict:
    """Finds quarantined items past their hold window, audits the decision and
    enqueues a PURGE command for the owning endpoint's agent. Shared by the
    HTTP endpoint and the ILM background task — one source of truth."""
    expired = find_expired_quarantine_items()

    purge_list = []
    for report, item in expired:
        write_audit_entry(
            AuditAction.CATEGORY_B_PURGE,
            actor="system:ilm-cron",
            details={
                "report_id": report.report_id,
                "item_id": item.item_id,
                "quarantine_path": item.quarantine_path,
                "hold_type": item.hold_type.value,
                "expired_at": item.quarantine_expires_at,
            },
        )
        command = enqueue_command(
            endpoint_id=report.endpoint_id,
            command_type=CommandType.PURGE,
            payload={"item_id": item.item_id, "quarantine_path": item.quarantine_path},
        )
        purge_list.append({
            "quarantine_path": item.quarantine_path,
            "item_id": item.item_id,
            "command_id": command.command_id,
        })

    return {"purged_count": len(purge_list), "items": purge_list}


async def ilm_loop(stop: asyncio.Event | None = None) -> None:
    """Background task: run purge-expired every AADITECH_ILM_INTERVAL_SECONDS.
    Swallows exceptions per-cycle (a transient store/DB error must not kill
    the loop or the whole portal), logging survives via audit entries."""
    while True:
        try:
            run_purge_cycle()
        except Exception:
            # Intentional broad catch — the ILM loop must be resilient.
            pass
        try:
            await asyncio.wait_for(
                (stop.wait() if stop else asyncio.sleep(_ILM_INTERVAL_SECONDS)),
                timeout=_ILM_INTERVAL_SECONDS,
            )
            if stop and stop.is_set():
                return
        except (asyncio.TimeoutError, asyncio.CancelledError):
            if stop and stop.is_set():
                return


def start_ilm_background_task() -> asyncio.Task | None:
    """Launch the ILM loop as a process-wide background task (idempotent).
    Returns None when the env explicitly disables it (tests/dev)."""
    if os.environ.get("AADITECH_ILM_DISABLED") == "1":
        return None
    global _msg_queue
    if _msg_queue is not None:
        return None  # already started
    stop = asyncio.Event()
    _msg_queue = asyncio.Queue()  # marker
    task = asyncio.create_task(ilm_loop(stop))
    return task