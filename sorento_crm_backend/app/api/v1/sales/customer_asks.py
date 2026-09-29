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
from app.models.sales import SalesTeam, SalesTeamMember
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


def _agent_ref(agent: SalesAgent) -> dict:
    return {"code": agent.sales_agent, "name": agent.person_label or agent.sales_agent}


def _not_your_agent() -> AppException:
    return AppException(
        status_code=403, message="That sales agent is not in your team.", code="NOT_YOUR_AGENT"
    )


def _led_agent_ids(db: Session, agent_id: str) -> set[str]:
    """The current members (and the leader) of the active teams this agent leads. Empty when
    the agent leads none. `valid_to IS NULL` is the same "current member" predicate
    `team_service.list_teams` uses."""
    team_ids = [
        t_id
        for (t_id,) in db.query(SalesTeam.id).filter(
            SalesTeam.leader_sales_agent_id == agent_id, SalesTeam.is_active.is_(True)
        )
    ]
    if not team_ids:
        return set()
    members = {
        m
        for (m,) in db.query(SalesTeamMember.sales_agent_id).filter(
            SalesTeamMember.sales_team_id.in_(team_ids), SalesTeamMember.valid_to.is_(None)
        )
    }
    return members | {agent_id}


@router.get("/todo", response_model=StockAskTodoResponse)
def customer_asks_todo(
    agent_id: Optional[str] = Query(None, max_length=64),
    current_user: dict = Depends(require_permission(VIEW)),
    db: Session = Depends(get_db),
):
    view_all = _has_view_all(db, current_user)
    mine = agent_for_user(db, current_user["id"])
    led = _led_agent_ids(db, mine.id) if mine else set()

    if agent_id == ALL_AGENTS:
        if view_all:
            return stock_ask_service.todo_for_agent(db, None, with_agent=True)
        if not led:  # a plain user has only themself to pick
            raise _not_your_agent()
        return stock_ask_service.todo_for_agent(db, led, with_agent=True)

    if agent_id:
        validate_uuid_path(agent_id, resource="Sales agent")
        agent = db.query(SalesAgent).filter(SalesAgent.id == agent_id).first()
        if agent is None:
            raise handle_not_found("Sales agent", agent_id)
        if not view_all and agent.id not in (led | ({mine.id} if mine else set())):
            raise _not_your_agent()
    else:
        agent = mine
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
    """The agents the caller may pick: view_all -> every agent with an open ask; a team leader
    -> every current member of the teams they lead (0 open allowed); otherwise `[]` (200)."""
    if _has_view_all(db, current_user):
        return stock_ask_service.agent_counts(db)
    mine = agent_for_user(db, current_user["id"])
    led = _led_agent_ids(db, mine.id) if mine else set()
    if not led:
        return []
    return stock_ask_service.agent_counts(db, agent_ids=led, include_idle=True)


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
