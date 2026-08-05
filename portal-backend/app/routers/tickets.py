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
    write_audit_entry(
        AuditAction.TICKET_CREATED,
        actor=user["username"],
        details={"ticket_title": payload.title, "glpi_response": result},
    )
    return result


@router.get("/open")
async def list_open(user: dict = Depends(require_support_engineer)):
    client = get_glpi_client()
    return await client.list_open_tickets()


@router.get("/{ticket_id}")
async def get_ticket(ticket_id: int, user: dict = Depends(require_support_engineer)):
    client = get_glpi_client()
    return await client.get_ticket(ticket_id)
