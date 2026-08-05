"""Remote access session control — backed by MeshCentral."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.roles import require_support_engineer
from app.audit import AuditAction, write_audit_entry
from app.config import settings
from app.integrations.meshcentral_client import MeshCentralClient

router = APIRouter(prefix="/remote", tags=["remote"])


def get_mesh_client() -> MeshCentralClient:
    return MeshCentralClient(base_url=settings.meshcentral_api_url, api_key=settings.meshcentral_api_key)


class SessionRequest(BaseModel):
    device_id: str


@router.post("/session")
async def start_session(payload: SessionRequest, user: dict = Depends(require_support_engineer)):
    """Starts a remote session and returns an embeddable session reference for the portal frontend."""
    client = get_mesh_client()
    result = await client.start_remote_session(device_id=payload.device_id, requested_by=user["username"])
    write_audit_entry(
        AuditAction.REMOTE_SESSION_STARTED,
        actor=user["username"],
        details={"device_id": payload.device_id},
    )
    return result


@router.get("/devices/{device_id}/status")
async def device_status(device_id: str, user: dict = Depends(require_support_engineer)):
    client = get_mesh_client()
    return await client.get_device_status(device_id)


@router.delete("/session/{session_id}")
async def end_session(session_id: str, user: dict = Depends(require_support_engineer)):
    client = get_mesh_client()
    await client.end_session(session_id)
    return {"status": "ended"}
