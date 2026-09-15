"""The chatbot's policy, as data: `chatbot_domains` and `chatbot_entity_kinds` CRUD.

Chatbot turn re-architecture S5 backend (AC-1561). These two tables ARE the engine's
routing and narrowing policy (AC-1501/AC-1502) - `turn/policy.py::load_policy` reads
them once per turn - so editing a row here changes what the next turn does, which is why
writes need their own grant (`system.chatbot_config.manage`) rather than riding the read
grant an operator holds to look at a customer's conversation.

**What is validated, and why only this much.** Three things are checked because getting
them wrong is silent: a tool name that is not in `mcp_tools` (the lane would pick a tool
that does not exist and the turn would answer nothing), a team code outside
`SUGGESTED_TEAMS` (the escalation lane would route to a team the assigner cannot find),
and a narrowing policy outside the seven the narrower implements (the narrower would
fall through its `optional_filter` default and quietly stop asking). Everything else -
labels, switch words, intents - is free text the owner is entitled to get wrong and fix.

The prompt is NOT republished on save. AC-1552's staleness banner is what tells the
owner the published parser and the rows have diverged; publishing on every keystroke
would rewrite a version somebody has already graded.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.dependencies import get_db, require_permission
from app.models.access import McpTool
from app.models.chatbot_policy import ChatbotDomain, ChatbotEntityKind
from app.schemas.common import ListResponse, PaginationResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chatbot")

VIEW = "system.chat_history.view"
MANAGE = "system.chatbot_config.manage"

# The seven the narrower implements (`turn/narrow.py`). Declared as a Literal so an
# unknown value is a 422 naming the field, never a row that reads as "optional_filter"
# at the one point it matters.
NarrowingPolicy = Literal[
    "must_narrow_one",
    "narrow_to_code",
    "narrow_by_type",
    "narrow_by_tier",
    "optional_filter",
    "list_all",
    "not_applicable",
]

_DOMAIN_SORTS = {"name", "label", "sort_order", "supported", "updated_at"}
_KIND_SORTS = {"kind", "resolver_source", "default_narrowing", "updated_at"}


class ChatbotDomainBody(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=128)
    intents: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    primary_tool: str | None = None
    escalation_team_code: str | None = None
    switch_words: list[str] = Field(default_factory=list)
    narrowing: dict[str, NarrowingPolicy] = Field(default_factory=dict)
    takes_date_filter: bool = False
    reveal_key: str | None = None
    supported: bool = True
    ladder: list[str] = Field(default_factory=list)
    sort_order: int = 0


class ChatbotDomainResponse(ChatbotDomainBody):
    id: str
    # AC-1510's "Updated" column: the row already carries the column
    # (`ChatbotDomain.updated_at`), just not surfaced until the FE list needed it.
    updated_at: datetime

    model_config = {"from_attributes": True}


class ChatbotEntityKindBody(BaseModel):
    kind: str = Field(min_length=1, max_length=64)
    label: str | None = None
    resolver_source: str = ""
    did_you_mean: bool = True
    default_narrowing: NarrowingPolicy = "optional_filter"
    family_grouping: str | None = None
    base_property_words: dict[str, str] = Field(default_factory=dict)


class ChatbotEntityKindResponse(ChatbotEntityKindBody):
    model_config = {"from_attributes": True}


def _unprocessable(message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=message)


def _validate_domain(db: Session, body: ChatbotDomainBody) -> None:
    from app.services.chatbot.lanes.escalation import ESCALATION_TEAMS

    wanted = [t for t in (body.tools or []) if t]
    if body.primary_tool:
        wanted.append(body.primary_tool)
    if wanted:
        known = {
            row[0]
            for row in db.query(McpTool.tool_name).filter(McpTool.tool_name.in_(set(wanted)))
        }
        missing = sorted(set(wanted) - known)
        if missing:
            raise _unprocessable(
                f"Unknown MCP tool(s): {', '.join(missing)}. A domain may only name tools "
                f"the MCP catalog actually serves."
            )
    if body.escalation_team_code and body.escalation_team_code not in ESCALATION_TEAMS:
        raise _unprocessable(
            f"Unknown escalation team {body.escalation_team_code!r}. Expected one of: "
            f"{', '.join(ESCALATION_TEAMS)}."
        )


def _domain_out(row: ChatbotDomain) -> ChatbotDomainResponse:
    return ChatbotDomainResponse(
        id=str(row.id),
        name=row.name,
        label=row.label,
        intents=list(row.intents or []),
        tools=list(row.tools or []),
        primary_tool=row.primary_tool,
        escalation_team_code=row.escalation_team_code,
        switch_words=list(row.switch_words or []),
        narrowing=dict(row.narrowing or {}),
        takes_date_filter=bool(row.takes_date_filter),
        reveal_key=row.reveal_key,
        supported=bool(row.supported),
        ladder=list(row.ladder or []),
        sort_order=int(row.sort_order or 0),
        updated_at=row.updated_at,
    )


def _kind_out(row: ChatbotEntityKind) -> ChatbotEntityKindResponse:
    return ChatbotEntityKindResponse(
        kind=row.kind,
        label=row.label,
        resolver_source=row.resolver_source or "",
        did_you_mean=bool(row.did_you_mean),
        default_narrowing=row.default_narrowing,
        family_grouping=row.family_grouping,
        base_property_words=dict(row.base_property_words or {}),
    )


def _find_domain(db: Session, domain_id: str) -> ChatbotDomain:
    """By id OR by name. A domain's NAME is what every other surface calls it by - the
    parser block, the trace, the settings ladder - so a caller holding a name should not
    have to look up a uuid to read the row it belongs to."""
    row = (
        db.query(ChatbotDomain)
        .filter((ChatbotDomain.name == domain_id) | (func.cast(ChatbotDomain.id, __import__("sqlalchemy").Text) == domain_id))
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail=f"No chatbot domain {domain_id!r}.")
    return row


@router.get("/domains", response_model=ListResponse[ChatbotDomainResponse])
def list_domains(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    sort: str = Query("sort_order"),
    dir: str = Query("asc"),
    query: str | None = Query(None),
    supported: bool | None = Query(None),
    team: str | None = Query(None),
    current_user: dict = Depends(require_permission(VIEW)),
    db: Session = Depends(get_db),
):
    _ = current_user
    rows = db.query(ChatbotDomain)
    if query:
        needle = f"%{query.strip().lower()}%"
        rows = rows.filter(
            func.lower(ChatbotDomain.name).like(needle) | func.lower(ChatbotDomain.label).like(needle)
        )
    if supported is not None:
        rows = rows.filter(ChatbotDomain.supported.is_(supported))
    if team:
        rows = rows.filter(ChatbotDomain.escalation_team_code == team)

    total = rows.count()
    column = getattr(ChatbotDomain, sort if sort in _DOMAIN_SORTS else "sort_order")
    rows = rows.order_by(column.desc() if dir == "desc" else column.asc())
    page_rows = rows.offset((page - 1) * limit).limit(limit).all()
    return ListResponse[ChatbotDomainResponse](
        data=[_domain_out(r) for r in page_rows],
        pagination=PaginationResponse(total=total, page=page, limit=limit),
        empty=total == 0,
    )


@router.get("/domains/{domain_id}", response_model=ChatbotDomainResponse)
def get_domain(
    domain_id: str,
    current_user: dict = Depends(require_permission(VIEW)),
    db: Session = Depends(get_db),
):
    _ = current_user
    return _domain_out(_find_domain(db, domain_id))


@router.post("/domains", response_model=ChatbotDomainResponse, status_code=status.HTTP_201_CREATED)
def create_domain(
    body: ChatbotDomainBody,
    current_user: dict = Depends(require_permission(MANAGE)),
    db: Session = Depends(get_db),
):
    _ = current_user
    _validate_domain(db, body)
    if db.query(ChatbotDomain).filter(ChatbotDomain.name == body.name).first() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A chatbot domain named {body.name!r} already exists.",
        )
    row = ChatbotDomain(**body.model_dump())
    db.add(row)
    db.flush()
    db.refresh(row)  # server_default `updated_at`/`created_at` are not on `row` until reloaded
    return _domain_out(row)


@router.put("/domains/{domain_id}", response_model=ChatbotDomainResponse)
def update_domain(
    domain_id: str,
    body: ChatbotDomainBody,
    current_user: dict = Depends(require_permission(MANAGE)),
    db: Session = Depends(get_db),
):
    _ = current_user
    row = _find_domain(db, domain_id)
    _validate_domain(db, body)
    for field, value in body.model_dump().items():
        setattr(row, field, value)
    db.flush()
    db.refresh(row)  # `onupdate=func.now()` is server-side - reload it before responding
    return _domain_out(row)


@router.delete("/domains/{domain_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_domain(
    domain_id: str,
    current_user: dict = Depends(require_permission(MANAGE)),
    db: Session = Depends(get_db),
):
    """Hard delete (D7). A domain nobody routes to answers nothing, so there is no
    archived state worth keeping - the row is the policy, not a record of anything."""
    _ = current_user
    db.delete(_find_domain(db, domain_id))
    db.flush()
    return None


def _find_kind(db: Session, kind: str) -> ChatbotEntityKind:
    row = db.query(ChatbotEntityKind).filter(ChatbotEntityKind.kind == kind).first()
    if row is None:
        raise HTTPException(status_code=404, detail=f"No chatbot entity kind {kind!r}.")
    return row


@router.get("/entity-kinds", response_model=ListResponse[ChatbotEntityKindResponse])
def list_entity_kinds(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    sort: str = Query("kind"),
    dir: str = Query("asc"),
    query: str | None = Query(None),
    current_user: dict = Depends(require_permission(VIEW)),
    db: Session = Depends(get_db),
):
    _ = current_user
    rows = db.query(ChatbotEntityKind)
    if query:
        needle = f"%{query.strip().lower()}%"
        rows = rows.filter(func.lower(ChatbotEntityKind.kind).like(needle))
    total = rows.count()
    column = getattr(ChatbotEntityKind, sort if sort in _KIND_SORTS else "kind")
    rows = rows.order_by(column.desc() if dir == "desc" else column.asc())
    page_rows = rows.offset((page - 1) * limit).limit(limit).all()
    return ListResponse[ChatbotEntityKindResponse](
        data=[_kind_out(r) for r in page_rows],
        pagination=PaginationResponse(total=total, page=page, limit=limit),
        empty=total == 0,
    )


@router.get("/entity-kinds/{kind}", response_model=ChatbotEntityKindResponse)
def get_entity_kind(
    kind: str,
    current_user: dict = Depends(require_permission(VIEW)),
    db: Session = Depends(get_db),
):
    _ = current_user
    return _kind_out(_find_kind(db, kind))


@router.post(
    "/entity-kinds", response_model=ChatbotEntityKindResponse, status_code=status.HTTP_201_CREATED
)
def create_entity_kind(
    body: ChatbotEntityKindBody,
    current_user: dict = Depends(require_permission(MANAGE)),
    db: Session = Depends(get_db),
):
    _ = current_user
    if db.query(ChatbotEntityKind).filter(ChatbotEntityKind.kind == body.kind).first() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A chatbot entity kind named {body.kind!r} already exists.",
        )
    values: dict[str, Any] = body.model_dump()
    values["label"] = values.get("label") or body.kind.replace("_", " ").title()
    row = ChatbotEntityKind(**values, sort_order=0)
    db.add(row)
    db.flush()
    return _kind_out(row)


@router.put("/entity-kinds/{kind}", response_model=ChatbotEntityKindResponse)
def update_entity_kind(
    kind: str,
    body: ChatbotEntityKindBody,
    current_user: dict = Depends(require_permission(MANAGE)),
    db: Session = Depends(get_db),
):
    _ = current_user
    row = _find_kind(db, kind)
    values = body.model_dump()
    values["label"] = values.get("label") or row.label
    for field, value in values.items():
        setattr(row, field, value)
    db.flush()
    return _kind_out(row)


@router.delete("/entity-kinds/{kind}", status_code=status.HTTP_204_NO_CONTENT)
def delete_entity_kind(
    kind: str,
    current_user: dict = Depends(require_permission(MANAGE)),
    db: Session = Depends(get_db),
):
    _ = current_user
    db.delete(_find_kind(db, kind))
    db.flush()
    return None
