"""Sales > Customer asks: the salesperson's to-do of their customers' stock asks
(PLAN-sales-asks-todo-29sep, S2). Plain `def` handlers, nothing here awaits.

"Me" is the sales agent the signed-in user is (`users.respond_contact_id` ->
`sales_agents.contact_id`); a user linked to no agent gets an empty to-do (200), not a 403.
`sales.customer_asks.view_all` lets a caller read one other agent (`agent_id=<id>`), every
agent (`agent_id=all`) and the agents list, and clear an ask on an agent's behalf. An ask
outside the caller's scope is a 404, never a 403, so ids cannot be probed.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission
from app.models.sales_agent import SalesAgent
from app.schemas.stock_ask import (
    StockAskAgentCount,
    StockAskResponse,
    StockAskTodoResponse,
    StockAskUpdate,
)
from app.services import stock_ask_service
from app.services.error_handler import AppException, handle_not_found
from app.services.sales.portal_agent import agent_for_user
from app.services.user_service import UserPermissionService
from app.services.uuid_path_param import validate_uuid_path

router = APIRouter()

VIEW = "sales.customer_asks.view"
EDIT = "sales.customer_asks.edit"
VIEW_ALL = "sales.customer_asks.view_all"
ALL_AGENTS = "all"


def _has_view_all(db: Session, user: dict) -> bool:
    return UserPermissionService(db).check_user_has_permission(user["id"], VIEW_ALL)


def _require_view_all(db: Session, user: dict) -> None:
    if not _has_view_all(db, user):
        raise AppException(
            status_code=403, message=f"Permission required: {VIEW_ALL}", code="FORBIDDEN"
        )


def _agent_ref(agent: SalesAgent) -> dict:
    return {"code": agent.sales_agent, "name": agent.person_label or agent.sales_agent}


@router.get("/todo", response_model=StockAskTodoResponse)
def customer_asks_todo(
    agent_id: Optional[str] = Query(None, max_length=64),
    current_user: dict = Depends(require_permission(VIEW)),
    db: Session = Depends(get_db),
):
    if agent_id == ALL_AGENTS:
        _require_view_all(db, current_user)
        return stock_ask_service.todo_for_agent(db, None, with_agent=True)
    if agent_id:
        _require_view_all(db, current_user)
        validate_uuid_path(agent_id, resource="Sales agent")
        agent = db.query(SalesAgent).filter(SalesAgent.id == agent_id).first()
        if agent is None:
            raise handle_not_found("Sales agent", agent_id)
    else:
        agent = agent_for_user(db, current_user["id"])
        if agent is None:
            return {
                "today_start": stock_ask_service.today_start_utc(datetime.utcnow()),
                "open": [],
                "done_today": [],
                "truncated": False,
                "agent": None,
            }
    payload = stock_ask_service.todo_for_agent(db, agent.id)
    payload["agent"] = _agent_ref(agent)
    return payload


@router.get("/agents", response_model=list[StockAskAgentCount])
def customer_asks_agents(
    current_user: dict = Depends(require_permission(VIEW)),
    db: Session = Depends(get_db),
):
    _require_view_all(db, current_user)
    return stock_ask_service.agent_counts(db)


@router.patch("/{ask_id}", response_model=StockAskResponse)
def customer_asks_update(
    ask_id: str,
    body: StockAskUpdate,
    current_user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    validate_uuid_path(ask_id, resource="Stock ask")
    if _has_view_all(db, current_user):
        agent_id: Optional[str] = None
    else:
        mine = agent_for_user(db, current_user["id"])
        if mine is None:
            raise handle_not_found("Stock ask", ask_id)
        agent_id = mine.id
    return stock_ask_service.update_for_sales(
        db,
        ask_id,
        body.model_dump(exclude_unset=True),
        agent_id=agent_id,
        actor_user_id=current_user["id"],
    )
