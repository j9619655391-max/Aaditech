"""
Category B — Approval-Required Cleanup (spec §3.5).

Endpoints (Aaditech Agent → portal, and portal → engineer):
  POST /cleanup/scan-reports              agent submits a scan report
  GET  /cleanup/scan-reports               list all reports (Viewer+)
  GET  /cleanup/scan-reports/{id}          view one report (Viewer+)
  POST /cleanup/scan-reports/{id}/approve  approve selected items → quarantine
                                            (Cleanup Approver ONLY — closes R-8)
  POST /cleanup/items/{report_id}/{item_id}/restore   restore within window
                                            (Cleanup Approver ONLY)

The "Approve & Execute" action never deletes anything directly — it moves
approved items into quarantine (§3.5 step 6) with a hold window sized by
whether the triggering scan was scheduled (7-day standard) or low-disk-space
(24-hour emergency, off-volume by default — v1.2). Approving an item flips
the portal-side status AND enqueues a QUARANTINE command that the owning
endpoint's agent picks up (self-healing/agent-command-poller.ps1 →
category-b-cleanup-execute.ps1) to actually move the file into the
quarantine volume. Permanent purge happens automatically at window expiry
via the existing ILM job (§3.3), not here.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.agent_commands import (
    CommandType,
    ack_command,
    complete_command,
    enqueue_command,
    list_pending_commands,
)
from app.audit import AuditAction, write_audit_entry
from app.cleanup_store import (
    approve_items,
    create_scan_report,
    find_expired_quarantine_items,
    get_scan_report,
    list_scan_reports,
    restore_item,
)
from app.config import settings
from app.roles import require_cleanup_approver, require_viewer

router = APIRouter(prefix="/cleanup", tags=["cleanup"])


class CommandResultPayload(BaseModel):
    success: bool
    result: str


class ScanItemPayload(BaseModel):
    category: str
    path: str
    size_bytes: int
    last_modified: str


class ScanReportPayload(BaseModel):
    endpoint_id: str
    endpoint_name: str
    triggered_by: str  # "scheduled" | "low_disk_space"
    items: list[ScanItemPayload]


class ApproveRequest(BaseModel):
    item_ids: list[str]


@router.post("/scan-reports")
async def submit_scan_report(payload: ScanReportPayload, user: dict = Depends(require_viewer)):
    """
    Called by the Aaditech Agent (self-healing/category-b-cleanup-scan.ps1)
    after it completes a scan. Requires at least Viewer-level auth (agent
    uses a service credential in production — see docs/DEPLOYMENT.md).
    """
    report = create_scan_report(
        endpoint_id=payload.endpoint_id,
        endpoint_name=payload.endpoint_name,
        triggered_by=payload.triggered_by,
        items=[i.model_dump() for i in payload.items],
    )
    return report


@router.get("/scan-reports")
async def get_all_reports(user: dict = Depends(require_viewer)):
    return list_scan_reports()


@router.get("/scan-reports/{report_id}")
async def get_report(report_id: str, user: dict = Depends(require_viewer)):
    report = get_scan_report(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Scan report not found")
    return report


@router.post("/scan-reports/{report_id}/approve")
async def approve_and_quarantine(
    report_id: str,
    payload: ApproveRequest,
    user: dict = Depends(require_cleanup_approver),
):
    """
    Moves selected items into quarantine. Requires the Cleanup Approver
    role (§7.1, closes risk R-8) — a plain authenticated SSO session is
    NOT sufficient. Every approval is audit-logged with engineer identity,
    files, and timestamp per §3.5 step 7.
    """
    quarantine_root = settings.quarantine_network_share or "/local-quarantine"
    try:
        approved = approve_items(
            report_id,
            payload.item_ids,
            quarantine_root=quarantine_root,
            standard_hold_days=settings.quarantine_standard_hold_days,
            emergency_hold_hours=settings.quarantine_emergency_hold_hours,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    write_audit_entry(
        AuditAction.CATEGORY_B_APPROVE_EXECUTE,
        actor=user["username"],
        details={
            "report_id": report_id,
            "items": [
                {"item_id": i.item_id, "path": i.path, "size_bytes": i.size_bytes,
                 "quarantine_path": i.quarantine_path, "expires_at": i.quarantine_expires_at,
                 "hold_type": i.hold_type.value}
                for i in approved
            ],
        },
    )

    commands = []
    if approved:
        report = get_scan_report(report_id)
        commands = [
            enqueue_command(
                endpoint_id=report.endpoint_id,
                command_type=CommandType.QUARANTINE,
                payload={
                    "item_id": i.item_id,
                    "path": i.path,
                    "quarantine_path": i.quarantine_path,
                },
            )
            for i in approved
        ]

    return {
        "approved_count": len(approved),
        "items": approved,
        "command_ids": [c.command_id for c in commands],
    }


@router.post("/items/{report_id}/{item_id}/restore")
async def restore_quarantined_item(
    report_id: str, item_id: str, user: dict = Depends(require_cleanup_approver)
):
    """
    Restores a quarantined item within its hold window. Audit-logged with
    the same identity/timestamp rigor as the original deletion (§3.5).

    Flips the item's DB status AND enqueues a command for the owning
    endpoint's agent to actually move the file back (closes the gap
    documented in self-healing/category-b-restore.ps1: the portal previously
    only updated status without telling any agent to act). The agent picks
    this up via GET /cleanup/agent/{endpoint_id}/commands.
    """
    report = get_scan_report(report_id)
    if not report:
        raise HTTPException(status_code=404, detail=f"No such scan report: {report_id}")

    try:
        item = restore_item(report_id, item_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    write_audit_entry(
        AuditAction.CATEGORY_B_RESTORE,
        actor=user["username"],
        details={"report_id": report_id, "item_id": item_id, "path": item.path},
    )

    command = enqueue_command(
        endpoint_id=report.endpoint_id,
        command_type=CommandType.RESTORE,
        payload={
            "item_id": item_id,
            "quarantine_path": item.quarantine_path,
            "original_path": item.path,
        },
    )
    return {"item": item, "command_id": command.command_id}


@router.post("/purge-expired")
async def purge_expired_quarantine_items():
    """
    Driven by the existing ILM cron job (§3.3, §7.4) — NOT engineer-triggered.
    Finds every quarantined item whose hold window has passed and marks it
    for permanent purge. The actual file deletion happens on the endpoint
    (agent picks up the purge list); this endpoint owns the authoritative
    "which items are past their window" decision and the audit trail.

    No RBAC role check here deliberately — this is a system/cron-triggered
    action (called with a service credential, not a user session), distinct
    from the human "Approve & Execute" and "Restore" actions above which
    both require the Cleanup Approver role.
    """
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


# --- Agent-facing command channel -------------------------------------------
# Closes the gap documented in self-healing/category-b-restore.ps1: restore
# and purge now hand off an actual instruction to the owning endpoint's
# agent, rather than only updating portal-side status. Agent auth uses the
# same service-credential pattern as scan-report submission above (Viewer-
# level token in production — see docs/DEPLOYMENT.md).

@router.get("/agent/{endpoint_id}/commands")
async def get_pending_commands(endpoint_id: str, user: dict = Depends(require_viewer)):
    """Polled by self-healing/agent-command-poller.ps1 on each endpoint."""
    return list_pending_commands(endpoint_id)


@router.post("/agent/commands/{command_id}/ack")
async def acknowledge_command(command_id: str, user: dict = Depends(require_viewer)):
    """Agent calls this immediately after picking a command off the queue,
    before running the corresponding script, so a crashed agent doesn't
    leave a command silently stuck as pending forever without any trace
    that it was ever picked up."""
    try:
        return ack_command(command_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/agent/commands/{command_id}/complete")
async def complete_command_route(
    command_id: str, payload: CommandResultPayload, user: dict = Depends(require_viewer)
):
    """Agent calls this after category-b-restore.ps1 / the purge deletion
    actually ran, reporting success or failure. Failures stay visible here
    rather than silently vanishing — the portal audit trail already has the
    approval/restore decision; this closes the loop on whether the endpoint
    action actually happened."""
    try:
        return complete_command(command_id, success=payload.success, result=payload.result)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
