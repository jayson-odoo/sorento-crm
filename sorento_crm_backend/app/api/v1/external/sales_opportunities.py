"""External API: log a sales opportunity over the chat (SALES-TARGET-CHAT slice 2).

`documentation/plans/sales/PLAN-sales-opportunity-chat-25oct.md`, "Backend". The chatbot's
opportunity lane calls these two routes through the MCP tools
`crm_sales_opportunity_customer_options` (read) and `crm_sales_opportunity_log` (write).

Auth is the integration API key holding `integration.sales_opportunity.log`
(`require_external_permission`, here and at the mount), then the per-contact gate in
`opportunity_chat.gate`, as on the portal (a salesperson, not revoked, with an active agent, who
may see the portal "sales_opportunity" form).
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.v1.external.permissions import EXTERNAL_ENDPOINT_PERMISSIONS, require_external_permission
from app.database import get_db
from app.services.sales import opportunity_chat

router = APIRouter()

#: One guard object for the mount and the handlers, so FastAPI checks the slug once per request.
SLUG_GUARD = require_external_permission(EXTERNAL_ENDPOINT_PERMISSIONS["sales-opportunities"])


class ChatOpportunityCreate(BaseModel):
    contact_id: Optional[str] = None
    space_id: Optional[str] = None
    customer_id: Optional[str] = None
    prospect_name: Optional[str] = None
    title: Optional[str] = None
    expected_amount: Optional[Decimal] = None
    expected_close_date: Optional[date] = None
    dry_run: bool = False


@router.get("/customer-options")
def chat_opportunity_customer_options(
    contact_id: Optional[str] = Query(None),
    space_id: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    current_user: dict = Depends(SLUG_GUARD),
    db: Session = Depends(get_db),
):
    _ = current_user
    _contact, agents = opportunity_chat.gate(db, contact_id=contact_id, space_id=space_id)
    return opportunity_chat.customer_options(db, agents, q)


@router.post("", status_code=status.HTTP_201_CREATED)
def chat_opportunity_create(
    payload: ChatOpportunityCreate,
    current_user: dict = Depends(SLUG_GUARD),
    db: Session = Depends(get_db),
):
    _ = current_user
    contact, agents = opportunity_chat.gate(db, contact_id=payload.contact_id, space_id=payload.space_id)
    return opportunity_chat.create(
        db,
        contact_id=contact,
        agents=agents,
        customer_id=payload.customer_id,
        prospect_name=payload.prospect_name,
        title=payload.title,
        expected_amount=payload.expected_amount,
        expected_close_date=payload.expected_close_date,
        dry_run=payload.dry_run,
    )
