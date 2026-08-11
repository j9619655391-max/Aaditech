"""Ticket lifecycle — backed by GLPI."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.roles import require_support_engineer
from app.config import settings
from app.audit import AuditAction, write_audit_entry
from app.integrations.glpi_client import GLPIClient

router = APIRouter(prefix="/tickets", tags=["tickets"])


def get_glpi_client() -> GLPIClient:
    return GLPIClient(
        base_url=settings.glpi_api_url,
        app_token=settings.glpi_app_token,
        user_token=settings.glpi_user_token,
        verify=settings.tls_verify(),
    )


class TicketCreateRequest(BaseModel):
    title: str = Field(..., min_length=3, max_length=200)
    description: str = Field(..., min_length=1)
    urgency: int = Field(3, ge=1, le=5)
    category_id: int | None = None


@router.post("/")
async def create_ticket(payload: TicketCreateRequest, user: dict = Depends(require_support_engineer)):
    client = get_glpi_client()
    full_description = f"{payload.description}\n\n--\nRaised via Aaditech Portal by {user['username']}"
    result = await client.create_ticket(
        title=payload.title,
        description=full_description,
        urgency=payload.urgency,
        category_id=payload.category_id,
    )
    # Finding 3.10: log only a sanitized summary, NEVER the raw GLPI response
    # body (it can carry server internals / sensitive ticket content into the
    # audit trail).
    glpi_id = None
    if isinstance(result, dict):
        glpi_id = result.get("id")
    write_audit_entry(
        AuditAction.TICKET_CREATED,
        actor=user["username"],
        details={"ticket_title": payload.title, "glpi_ticket_id": glpi_id},
    )
    return result


@router.get("/open")
async def list_open(user: dict = Depends(require_support_engineer)):
    client = get_glpi_client()
    raw = await client.list_open_tickets()
    # Finding 5.8: GLPI may return a bare list OR a pagination envelope
    # ({"0": {...}, "1": {...}, ...} with a "count" key). The frontend always
    # consumes a plain array via .map(), so normalize both shapes here.
    if isinstance(raw, dict) and "count" in raw:
        raw = [v for k, v in raw.items() if k != "count"]
    return raw


@router.get("/{ticket_id}")
async def get_ticket(ticket_id: int, user: dict = Depends(require_support_engineer)):
    client = get_glpi_client()
    return await client.get_ticket(ticket_id)
