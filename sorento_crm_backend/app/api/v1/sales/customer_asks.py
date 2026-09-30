"""Sales > Customer asks: the salesperson's to-do of their customers' stock asks
(PLAN-sales-asks-todo-29sep, S2). Plain `def` handlers, nothing here awaits.

"Me" is the sales agent the signed-in user is (`users.respond_contact_id` ->
`sales_agents.contact_id`); a user linked to no agent gets an empty to-do (200), not a 403.
`sales.customer_asks.view_all` lets a caller read one other agent (`agent_id=<id>`), every
agent (`agent_id=all`) and the agents list, and clear an ask on an agent's behalf. A team
leader reaches their team's current members the same way. The GETs answer 404 for an id that is
no agent and 403 NOT_YOUR_AGENT for an agent outside the caller's pickable set (plan 3.4); the
PATCH answers 404 for both, so an ask id cannot be probed.
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
    StockAskConversationResponse,
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


def _patch_scope(db: Session, user: dict, ask_id: str) -> Optional[set[str]]:
    """The agents whose asks the caller may act on (PATCH and conversation scope): everyone with
    view_all (None), else self plus a led team's current members. A caller linked to no agent
    has no scope: 404 (never a 403, so an ask id cannot be probed)."""
    if _has_view_all(db, user):
        return None
    mine = agent_for_user(db, user["id"])
    if mine is None:
        raise handle_not_found("Stock ask", ask_id)
    return _led_agent_ids(db, mine.id) | {mine.id}


@router.get("/{ask_id}/conversation", response_model=StockAskConversationResponse, response_model_exclude_unset=True)
def customer_asks_conversation(
    ask_id: str,
    whole_day: bool = Query(False),
    current_user: dict = Depends(require_permission(VIEW)),
    db: Session = Depends(get_db),
):
    validate_uuid_path(ask_id, resource="Stock ask")
    ask = stock_ask_service.get_ask_in_scope(db, _patch_scope(db, current_user, ask_id), ask_id)
    return stock_ask_service.conversation_for_ask(db, ask, whole_day=whole_day)


@router.get("/{ask_id}/conversation/page")
def customer_asks_conversation_page(
    ask_id: str,
    before: Optional[str] = Query(None, description="Message id to page OLDER than (exclusive)"),
    after: Optional[str] = Query(None, description="Message id to page NEWER than (exclusive)"),
    around: Optional[str] = Query(None, description="Message id to centre the window on"),
    limit: int = Query(50, ge=1, le=200),
    current_user: dict = Depends(require_permission(VIEW)),
    db: Session = Depends(get_db),
):
    """One scroll-back window of the ask's contact thread (ASKS-UX item 3), the shape of the
    ticket-keyed `GET .../conversation-sla-tracking/{id}/conversation/page`. Scope: the PATCH
    scope, like the sibling `/conversation` (404 outside it)."""
    validate_uuid_path(ask_id, resource="Stock ask")
    if len([c for c in (before, after, around) if c]) > 1:
        raise AppException(status_code=422, message="Pass at most one of before, after, around.", code="VALIDATION_ERROR")
    ask = stock_ask_service.get_ask_in_scope(db, _patch_scope(db, current_user, ask_id), ask_id)
    return stock_ask_service.conversation_page_for_ask(db, ask, before=before, after=after, around=around, limit=limit)


@router.get("/{ask_id}/conversation/search")
def customer_asks_conversation_search(
    ask_id: str,
    q: str = Query("", description="Free text searched inside this contact's messages"),
    limit: int = Query(100, ge=1, le=200),
    current_user: dict = Depends(require_permission(VIEW)),
    db: Session = Depends(get_db),
):
    """In-thread search over the ask's contact thread, same shape as the ticket-keyed twin."""
    validate_uuid_path(ask_id, resource="Stock ask")
    ask = stock_ask_service.get_ask_in_scope(db, _patch_scope(db, current_user, ask_id), ask_id)
    return stock_ask_service.conversation_search_for_ask(db, ask, q=q, limit=limit)


@router.patch("/{ask_id}", response_model=StockAskResponse)
def customer_asks_update(
    ask_id: str,
    body: StockAskUpdate,
    current_user: dict = Depends(require_permission(EDIT)),
    db: Session = Depends(get_db),
):
    validate_uuid_path(ask_id, resource="Stock ask")
    return stock_ask_service.update_for_sales(
        db,
        ask_id,
        body.model_dump(exclude_unset=True),
        agent_id=_patch_scope(db, current_user, ask_id),
        actor_user_id=current_user["id"],
    )
