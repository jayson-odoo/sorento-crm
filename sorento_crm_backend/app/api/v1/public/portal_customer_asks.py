"""Portal "Customer asks" (chatbot stock ask v2 S6, PLAN-chatbot-stock-ask-v2-24sep.md, R9).

Mounted at ``/api/v1/public/portal`` beside the price tag routes. Auth: the portal token.

The page belongs to a portal contact linked to a sales agent (`sales_agent_for_contact`, the
same resolution the debtor lookup uses). It lists the stock asks of the customers assigned to
that agent (`customers.sales_agent_id`), never the agent's order debtors, and edits the same
`state` and `note` the CRM customer's Asks tab edits. A contact linked to no agent gets 403
`NOT_A_SALES_AGENT`; an ask outside the agent's customers is a 404.

Fix round 5 (owner, 29 Sep): Customer asks is also a per-contact switch, the
`contact_portal_form_overrides` row Price Tag Request is switched by (Contact page -> Portal
forms), off by default. A linked agent whose switch is off gets 403 `FORM_TYPE_NOT_VISIBLE`.
"""
from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.v1.public.portal import get_portal_token
from app.database import get_db
from app.models.portal import PortalToken
from app.models.user import User
from app.schemas.common import ListResponse, MAX_PAGE_LIMIT
from app.schemas.stock_ask import StockAskConversationResponse, StockAskResponse, StockAskTodoResponse, StockAskUpdate
from app.services import price_tag_request_service, stock_ask_service
from app.services.error_handler import AppException
from app.services.portal_form_visibility_service import switched_form_types
from app.services.portal_service import CUSTOMER_ASKS_FORM_TYPE
from app.services.uuid_path_param import validate_uuid_path

router = APIRouter(tags=["public-portal-customer-asks"])


def _agent_id(db: Session, token: PortalToken) -> str:
    agent = price_tag_request_service.sales_agent_for_contact(db, token.contact_id)
    if agent is None:
        raise AppException(
            status_code=403,
            message="Customer asks are for sales agents only.",
            code="NOT_A_SALES_AGENT",
        )
    if CUSTOMER_ASKS_FORM_TYPE not in switched_form_types(db, token.contact_id):
        raise AppException(
            status_code=403,
            message="Customer asks is not available for your account.",
            code="FORM_TYPE_NOT_VISIBLE",
        )
    return agent.id


@router.get("/customer-asks", response_model=ListResponse[StockAskResponse])
def portal_list_customer_asks(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=MAX_PAGE_LIMIT),
    q: Optional[str] = Query(None, max_length=100),
    state: Optional[Literal["open", "done"]] = Query(None),
    token: PortalToken = Depends(get_portal_token),
    db: Session = Depends(get_db),
):
    agent_id = _agent_id(db, token)
    return stock_ask_service.list_for_agent(db, agent_id, page=page, limit=limit, q=q, state=state)


@router.get("/customer-asks/todo", response_model=StockAskTodoResponse)
def portal_customer_asks_todo(
    token: PortalToken = Depends(get_portal_token),
    db: Session = Depends(get_db),
):
    """The salesperson's to-do (sales-asks-todo S1): open asks oldest first plus what was
    cleared today, grouped on the client from `today_start`."""
    return stock_ask_service.todo_for_agent(db, _agent_id(db, token))


@router.get("/customer-asks/{ask_id}/conversation", response_model=StockAskConversationResponse, response_model_exclude_unset=True)
def portal_customer_ask_conversation(
    ask_id: str,
    whole_day: bool = Query(False),
    token: PortalToken = Depends(get_portal_token),
    db: Session = Depends(get_db),
):
    """The chat around one ask, for the opened card. Same gate and scope as the PATCH."""
    agent_id = _agent_id(db, token)
    validate_uuid_path(ask_id, resource="Stock ask")
    ask = stock_ask_service.get_ask_in_scope(db, agent_id, ask_id)
    payload = stock_ask_service.conversation_for_ask(db, ask, whole_day=whole_day)
    payload.pop("contact_id", None)  # the CRM's "Open in Conversations" link only
    return payload


@router.patch("/customer-asks/{ask_id}", response_model=StockAskResponse)
def portal_update_customer_ask(
    ask_id: str,
    body: StockAskUpdate,
    token: PortalToken = Depends(get_portal_token),
    db: Session = Depends(get_db),
):
    agent_id = _agent_id(db, token)
    validate_uuid_path(ask_id, resource="Stock ask")
    # Who cleared it: the portal contact, and the CRM user that contact is (if any).
    user_id = db.query(User.id).filter(User.respond_contact_id == token.contact_id).scalar()
    return stock_ask_service.update_for_agent(
        db,
        agent_id,
        ask_id,
        body.model_dump(exclude_unset=True),
        actor_contact_id=token.contact_id,
        actor_user_id=user_id,
    )
