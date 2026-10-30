"""The agent's write tools and its in-process reads as the user (AGENTIC-P3 plan section 1).

A write tool is one existing screen operation: `execute` calls the route function the screen
calls, in process, as the contact's linked user. Nothing is written when the model calls a write:
`propose_step` only checks the call and reads the record as it is now; `actions.confirm` runs the
steps later. The route's `Depends(require_permission(...))` does not run on a direct call, so the
slug is checked here at exposure, proposal and execution.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Callable

from fastapi import HTTPException

from app.services.chatbot.agent.tools import ToolResult, _check_ids, _collect_uuids, _permitted, cap_result, clean_detail

logger = logging.getLogger(__name__)

MAX_NOTE_CHARS = 4000
SUMMARY_NOTE_CHARS = 80


@dataclass(frozen=True)
class WriteDef:
    name: str
    #: The route's own slug (a tuple = any one of them): checked at exposure, proposal and execution.
    user_permission: str | tuple[str, ...]
    #: Model-facing function schema (ids must come from this turn's results).
    schema: dict
    #: (db, user, args) -> the record as it is now: the precondition and the summary input.
    read_before: Callable[[Any, dict, dict], dict]
    #: (args, before) -> one plain line, built by code.
    summary: Callable[[dict, dict], str]
    #: (db, user, args) -> {"id", "after"}; calls the route function.
    execute: Callable[[Any, dict, dict], dict]
    #: The arg naming the record ("ask_id"); "" for a create.
    record_key: str


@dataclass(frozen=True)
class UserRead:
    name: str
    #: "" = no slug beyond the agent switch; a tuple = any one of them.
    user_permission: str | tuple[str, ...]
    schema: dict
    #: (db, ctx, args) -> ToolResult
    run: Callable[[Any, Any, dict], ToolResult]


def holds(db, user_id: str, permission: str | tuple[str, ...]) -> bool:
    """Does the user hold the slug (or any one of a tuple of slugs)? "" needs none."""
    if not permission:
        return True
    slugs = (permission,) if isinstance(permission, str) else permission
    return any(_permitted(db, user_id, slug) for slug in slugs)


def _body(model, data: dict):
    """`model(**data)`, with a validation failure as a 422 carrying the first problem."""
    from pydantic import ValidationError

    from app.services.error_handler import AppException

    try:
        return model(**data)
    except ValidationError as exc:
        first = exc.errors()[0]
        where = ".".join(str(p) for p in first.get("loc", ()))
        raise AppException(status_code=422, message=f"{where}: {first.get('msg')}", code="VALIDATION_ERROR")


def _plain(value: Any) -> Any:
    """`value` as plain JSON data (Decimals, dates and datetimes become text)."""
    return json.loads(json.dumps(value, default=str))


# ------------------------------------------------------------------ running as the user


def run_as_user(db, ctx, fn: Callable[[dict], Any], *, tool_name: str | None = None) -> Any:
    """`fn(user_dict)` under the linked user's company scope and audit actor. The previous scope and
    actor come back even when `fn` raises."""
    from app.audit_context import AuditActor, actor_scope
    from app.dependencies import _load_user_dict_from_db
    from app.models.base import get_company_scope, set_company_scope
    from app.services import company_scope_resolver
    from app.services.error_handler import AppException

    user = _load_user_dict_from_db(db, ctx.user_id)
    if user is None:
        raise AppException(status_code=403, message="The linked user is no longer available.", code="USER_GONE")
    previous = get_company_scope(db)
    actor = AuditActor(
        actor_type="user",
        user_id=str(ctx.user_id),
        real_user_id=str(ctx.user_id),
        auth_method="agent",
        contact_id=str(ctx.contact_pk),
        tool_name=tool_name,
    )
    set_company_scope(db, company_scope_resolver._scope_for_user(db, ctx.user_id, None))
    try:
        with actor_scope(actor, db=db):
            return fn(user)
    finally:
        set_company_scope(db, previous)


def error_text(exc: Exception) -> str:
    """The status and message of a route's exception, no internals."""
    if isinstance(exc, HTTPException):
        detail = exc.detail
        message = detail.get("message") or detail.get("detail") if isinstance(detail, dict) else detail
        return clean_detail(message) or f"The request was refused ({exc.status_code})."
    return "The change could not be made."


def _route_failure(exc: Exception) -> ToolResult:
    if isinstance(exc, HTTPException):
        if exc.status_code in (403, 404):
            return ToolResult("denied", message=error_text(exc))
        if 400 <= exc.status_code < 500:
            return ToolResult("invalid", message=error_text(exc))
    logger.warning("agent: in-process route call failed", exc_info=True)
    return ToolResult("error", message="The tool failed.")


# ------------------------------------------------------------------ W1 customer asks

ASK_VIEW = "sales.customer_asks.view"
ASK_EDIT = "sales.customer_asks.edit"
UPDATE_ASK = "crm_customer_ask_update"
LIST_ASKS = "crm_customer_asks_list"
RECENT_ACTIONS = "crm_agent_actions_recent"

_ASK_FIELDS = ("id", "customer_name", "contact_name", "product_code", "product_name", "quantity", "branch", "state", "note")


def _ask_row(ask: Any) -> dict:
    data = ask.model_dump(mode="json") if hasattr(ask, "model_dump") else dict(ask)
    row = {k: data.get(k) for k in _ASK_FIELDS}
    row["created_at"] = data.get("created_at")
    row["updated_at"] = data.get("updated_at")
    return row


def _ask_read_before(db, user: dict, args: dict) -> dict:
    """The ask as the screen shows it now, inside the caller's scope (404 outside it)."""
    from app.api.v1.sales.customer_asks import _patch_scope
    from app.services import stock_ask_service
    from app.services.error_handler import AppException

    if args.get("state") is None and args.get("note") is None:
        raise AppException(status_code=422, message="Give a state or a note to change.", code="VALIDATION_ERROR")
    ask_id = str(args["ask_id"])
    ask = stock_ask_service.get_ask_in_scope(db, _patch_scope(db, user, ask_id), ask_id)
    return _ask_row(stock_ask_service.serialize(db, [ask])[0])


def _clip(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "..."


def _ask_summary(args: dict, before: dict) -> str:
    changes = []
    if args.get("state") == "done":
        changes.append("mark done")
    elif args.get("state") == "open":
        changes.append("reopen")
    if args.get("note") is not None:
        note = _clip(str(args["note"]), SUMMARY_NOTE_CHARS)
        changes.append(f'set the note to "{note}"' if note else "clear the note")
    who = before.get("customer_name") or before.get("contact_name")
    target = f"the ask for {before.get('product_code')}" + (f" from {who}" if who else "")
    return f"{' and '.join(changes).capitalize()} on {target}"


def _ask_execute(db, user: dict, args: dict) -> dict:
    from app.api.v1.sales.customer_asks import customer_asks_update
    from app.schemas.stock_ask import StockAskUpdate

    body = StockAskUpdate(**{k: args[k] for k in ("state", "note") if args.get(k) is not None})
    out = _ask_row(customer_asks_update(ask_id=str(args["ask_id"]), body=body, current_user=user, db=db))
    return {"id": out["id"], "after": {"state": out["state"], "note": out["note"]}}


WRITES: dict[str, WriteDef] = {
    UPDATE_ASK: WriteDef(
        name=UPDATE_ASK,
        user_permission=ASK_EDIT,
        schema={
            "type": "function",
            "function": {
                "name": UPDATE_ASK,
                "description": (
                    "Propose marking one customer ask done or open and/or setting its note. Nothing is "
                    "changed until the user confirms. ask_id must come from crm_customer_asks_list. "
                    "Call once per ask."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "ask_id": {"type": "string"},
                        "state": {"type": "string", "enum": ["open", "done"]},
                        "note": {"type": "string", "maxLength": MAX_NOTE_CHARS},
                    },
                    "required": ["ask_id"],
                },
            },
        },
        read_before=_ask_read_before,
        summary=_ask_summary,
        execute=_ask_execute,
        record_key="ask_id",
    ),
}


def _asks_list(db, ctx, args: dict) -> ToolResult:
    from app.api.v1.sales.customer_asks import customer_asks_todo

    unknown = sorted(k for k in args if k != "all_agents")
    if unknown:
        return ToolResult("invalid", message=f"Unknown argument(s): {', '.join(map(str, unknown))}.")
    every = args.get("all_agents", False)
    if not isinstance(every, bool):
        return ToolResult("invalid", message="all_agents must be true or false.")
    try:
        payload = run_as_user(
            db, ctx,
            lambda user: customer_asks_todo(agent_id="all" if every else None, current_user=user, db=db),
            tool_name=LIST_ASKS,
        )
    except Exception as exc:  # noqa: BLE001 - a route refusal is a result the model can read
        return _route_failure(exc)
    rows = {key: [_ask_row(r) for r in payload.get(key) or []] for key in ("open", "done_today")}
    data, more = cap_result({**rows, "truncated": bool(payload.get("truncated"))})
    return ToolResult("ok", data=data, more=more)


def _recent_actions(db, ctx, args: dict) -> ToolResult:
    from app.models.chatbot_agent import AgentAction

    if args:
        return ToolResult("invalid", message="This tool takes no arguments.")
    rows = (
        db.query(AgentAction)
        .filter(AgentAction.contact_respond_id == ctx.contact_respond_id)
        .order_by(AgentAction.created_at.desc(), AgentAction.id.desc())
        .limit(10)
        .all()
    )
    actions = [
        {
            "status": r.status,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "steps": [
                {k: s.get(k) for k in ("summary", "status", "error", "record_id", "before", "after")}
                for s in r.steps or []
            ],
        }
        for r in rows
    ]
    data, more = cap_result({"actions": actions})
    return ToolResult("ok", data=data, more=more)


USER_READS: dict[str, UserRead] = {
    LIST_ASKS: UserRead(
        name=LIST_ASKS,
        user_permission=ASK_VIEW,
        schema={
            "type": "function",
            "function": {
                "name": LIST_ASKS,
                "description": (
                    "The user's customer asks to-do: open asks and those done today, with the ask_id "
                    "to use in crm_customer_ask_update. all_agents lists every agent's asks when the "
                    "user may see them."
                ),
                "parameters": {"type": "object", "properties": {"all_agents": {"type": "boolean"}}},
            },
        },
        run=_asks_list,
    ),
    RECENT_ACTIONS: UserRead(
        name=RECENT_ACTIONS,
        user_permission="",
        schema={
            "type": "function",
            "function": {
                "name": RECENT_ACTIONS,
                "description": (
                    "The last changes you proposed for this user with their outcome and the record "
                    "before and after each step. Use it to see what was done, or to prepare the inverse."
                ),
                "parameters": {"type": "object", "properties": {}},
            },
        },
        run=_recent_actions,
    ),
}


# ------------------------------------------------------------------ exposure and proposal


def permitted_writes(db, ctx) -> list[WriteDef]:
    """WRITES the linked user holds the slug for, in registry order."""
    return [w for w in WRITES.values() if holds(db, ctx.user_id, w.user_permission)]


def permitted_user_reads(db, ctx) -> list[UserRead]:
    return [r for r in USER_READS.values() if holds(db, ctx.user_id, r.user_permission)]


def run_user_read(db, ctx, name: str, args: Any, seen_ids: set[str]) -> ToolResult:
    """One in-process read as the user. The ids in its result join the turn's seen ids."""
    read = USER_READS.get(name)
    if read is None:
        return ToolResult("denied", message=f"{name} is not a tool you may use.")
    if not holds(db, ctx.user_id, read.user_permission):
        return ToolResult("denied", message=f"{name} is outside this user's access.")
    if not isinstance(args, dict):
        return ToolResult("invalid", message="Arguments must be an object of named values.")
    out = read.run(db, ctx, args)
    if out.status == "ok":
        _collect_uuids(out.data, seen_ids)
    return out


def _args_problem(definition: WriteDef, args: Any) -> str | None:
    if not isinstance(args, dict):
        return "Arguments must be an object of named values."
    props = definition.schema["function"]["parameters"].get("properties") or {}
    unknown = sorted(k for k in args if k not in props)
    if unknown:
        return f"Unknown argument(s): {', '.join(map(str, unknown))}."
    for key in definition.schema["function"]["parameters"].get("required") or []:
        if args.get(key) in (None, ""):
            return f"`{key}` is required."
    for key, value in args.items():
        spec = props[key]
        if value is None:
            continue
        kind = spec.get("type")
        if kind == "string" and not isinstance(value, str):
            return f"`{key}` must be text."
        if kind == "boolean" and not isinstance(value, bool):
            return f"`{key}` must be true or false."
        if kind == "number" and (isinstance(value, bool) or not isinstance(value, (int, float))):
            return f"`{key}` must be a number."
        if kind == "array" and not (isinstance(value, list) and all(isinstance(v, str) for v in value)):
            return f"`{key}` must be a list of text values."
        if "enum" in spec and value not in spec["enum"]:
            return f"`{key}` must be one of: {', '.join(spec['enum'])}."
        if "maxLength" in spec and isinstance(value, str) and len(value) > spec["maxLength"]:
            return f"`{key}` is too long."
    return None


def propose_step(db, ctx, name: str, args: Any, *, seen_ids: set[str]) -> tuple[ToolResult, dict | None]:
    """Check a write call and read the record as it is now. Never writes. Success returns the
    "proposed" result and the step to store; any failure returns a typed result and no step."""
    definition = WRITES.get(name) if isinstance(name, str) else None
    if definition is None:
        return ToolResult("denied", message=f"{name} is not a tool you may use."), None
    if not holds(db, ctx.user_id, definition.user_permission):
        return ToolResult("denied", message=f"{name} is outside this user's access."), None
    problem = _args_problem(definition, args)
    if problem:
        return ToolResult("invalid", message=problem), None
    bad_id = _check_ids(args, seen_ids)
    if bad_id is not None:
        return bad_id, None
    try:
        before = run_as_user(db, ctx, lambda user: definition.read_before(db, user, args), tool_name=name)
    except Exception as exc:  # noqa: BLE001
        return _route_failure(exc), None
    # `_show` holds what the summary needs but the re-check must not compare (names looked up now).
    shown = before.pop("_show", {})
    summary = definition.summary(args, {**before, **shown})
    step = {"tool": name, "args": dict(args), "before": before, "summary": summary, "status": "proposed"}
    return ToolResult("proposed", data={"summary": summary}), step


# ------------------------------------------------------------------ W2 sales opportunities

OPP_VIEW = ("sales.opportunities.view", "sales.opportunities.view_own")
OPP_ADD = "sales.opportunities.add"
OPP_EDIT = "sales.opportunities.edit"
CREATE_OPP = "crm_opportunity_create"
UPDATE_OPP = "crm_opportunity_update"
LIST_OPPS = "crm_opportunities_list"
OPP_META = "crm_opportunity_meta"
MAX_LIST = 50

_OPP_KEYS = (
    "title", "customer_id", "customer_code", "prospect_name", "status_id", "stage_label", "outcome",
    "expected_amount", "expected_close_date", "lost_reason",
)
_OPP_LIST_KEYS = (
    "id", "opportunity_no", "title", "customer_id", "customer_code", "customer_name", "prospect_name",
    "sales_agent_label", "status_id", "stage_label", "outcome", "expected_amount", "expected_close_date",
    "lost_reason",
)
_OPP_LABELS = {
    "title": "title", "expected_close_date": "close date", "expected_amount": "amount",
    "prospect_name": "prospect", "lost_reason": "lost reason",
}
_OPP_FIELDS = {
    "title": {"type": "string", "maxLength": 200},
    "expected_close_date": {"type": "string", "description": "YYYY-MM-DD"},
    "expected_amount": {"type": "number"},
    "customer_id": {"type": "string"},
    "prospect_name": {"type": "string", "maxLength": 200},
}


def _customer_code(db, customer_id: str) -> str:
    from app.models.order import Customer
    from app.services.error_handler import handle_not_found

    row = db.query(Customer.customer_code).filter(Customer.id == customer_id).first()
    if row is None:
        raise handle_not_found("Customer", customer_id)
    return row[0]


def _stage_label(db, status_id: str) -> str:
    from app.models.status import Status
    from app.services.error_handler import handle_not_found

    row = db.get(Status, status_id)
    if row is None:
        raise handle_not_found("Stage", status_id)
    return row.label


def _opp_create_read_before(db, user: dict, args: dict) -> dict:
    from app.schemas.sales import SalesOpportunityCreate
    from app.services.error_handler import AppException

    _body(SalesOpportunityCreate, args)
    if not args.get("customer_id") and not args.get("prospect_name"):
        raise AppException(status_code=422, message="Give a customer or a prospect name.", code="VALIDATION_ERROR")
    target = _customer_code(db, args["customer_id"]) if args.get("customer_id") else args["prospect_name"]
    return {"_show": {"target": target}}


def _opp_create_summary(args: dict, before: dict) -> str:
    return f'Create opportunity "{args["title"]}" for {before["target"]}, close {args["expected_close_date"]}'


def _opp_create_execute(db, user: dict, args: dict) -> dict:
    from app.api.v1.sales.opportunities import create_opportunity
    from app.schemas.sales import SalesOpportunityCreate

    out = create_opportunity(payload=SalesOpportunityCreate(**args), current_user=user, db=db)
    return {"id": out["id"], "after": {k: _plain(out.get(k)) for k in _OPP_KEYS}}


def _opp_update_read_before(db, user: dict, args: dict) -> dict:
    from app.api.v1.sales.opportunities import _load
    from app.schemas.sales import SalesOpportunityUpdate
    from app.services.error_handler import AppException
    from app.services.sales import opportunity_service

    fields = {k: v for k, v in args.items() if k != "opportunity_id" and v is not None}
    if not fields:
        raise AppException(status_code=422, message="Give a field to change.", code="VALIDATION_ERROR")
    _body(SalesOpportunityUpdate, fields)
    row = opportunity_service.serialize(db, _load(db, user, str(args["opportunity_id"])))
    before = {k: _plain(row.get(k)) for k in _OPP_KEYS}
    shown: dict = {"title": row.get("title"), "customer": row.get("customer_code") or row.get("prospect_name")}
    if "status_id" in fields:
        shown["new_stage"] = _stage_label(db, fields["status_id"])
    if "customer_id" in fields:
        shown["new_customer"] = _customer_code(db, fields["customer_id"])
    return {**before, "_show": shown}


def _opp_update_summary(args: dict, before: dict) -> str:
    def was(value: Any) -> str:
        return "none" if value in (None, "") else str(value)

    parts = []
    for key, value in args.items():
        if key == "opportunity_id" or value is None:
            continue
        if key == "status_id":
            parts.append(f"stage {was(before.get('stage_label'))} -> {before['new_stage']}")
        elif key == "customer_id":
            parts.append(f"customer {was(before.get('customer'))} -> {before['new_customer']}")
        else:
            parts.append(f"{_OPP_LABELS.get(key, key)} {was(before.get(key))} -> {value}")
    return f'Opportunity "{before["title"]}": ' + "; ".join(parts)


def _opp_update_execute(db, user: dict, args: dict) -> dict:
    from app.api.v1.sales.opportunities import update_opportunity
    from app.schemas.sales import SalesOpportunityUpdate

    body = SalesOpportunityUpdate(**{k: v for k, v in args.items() if k != "opportunity_id" and v is not None})
    out = update_opportunity(opportunity_id=str(args["opportunity_id"]), payload=body, current_user=user, db=db)
    return {"id": out["id"], "after": {k: _plain(out.get(k)) for k in _OPP_KEYS}}


def _opp_list(db, ctx, args: dict) -> ToolResult:
    from app.api.v1.sales.opportunities import list_opportunities

    allowed = {"query", "status_ids", "customer_ids", "close_from", "close_to", "outcome", "limit"}
    unknown = sorted(k for k in args if k not in allowed)
    if unknown:
        return ToolResult("invalid", message=f"Unknown argument(s): {', '.join(map(str, unknown))}.")
    limit = args.get("limit", MAX_LIST)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_LIST:
        return ToolResult("invalid", message=f"limit must be a whole number from 1 to {MAX_LIST}.")
    try:
        from datetime import date

        close = {k: date.fromisoformat(args[k]) if args.get(k) else None for k in ("close_from", "close_to")}
        payload = run_as_user(
            db, ctx,
            lambda user: list_opportunities(
                query=args.get("query"), status_id=args.get("status_ids") or None, sales_agent_id=None,
                customer_id=args.get("customer_ids") or None, outcome=args.get("outcome"), page=1, limit=limit,
                sort="created_at", dir="desc", _user=user, db=db, **close,
            ),
            tool_name=LIST_OPPS,
        )
    except ValueError:
        return ToolResult("invalid", message="Dates must be YYYY-MM-DD.")
    except Exception as exc:  # noqa: BLE001
        return _route_failure(exc)
    rows = [{k: _plain(r.get(k)) for k in _OPP_LIST_KEYS} for r in payload["data"]]
    data, more = cap_result({"opportunities": rows, "total": payload["pagination"]["total"]})
    return ToolResult("ok", data=data, more=more)


def _opp_meta(db, ctx, args: dict) -> ToolResult:
    from app.api.v1.sales.opportunities import get_meta

    if args:
        return ToolResult("invalid", message="This tool takes no arguments.")
    try:
        meta = run_as_user(db, ctx, lambda user: get_meta(_user=user, db=db), tool_name=OPP_META)
    except Exception as exc:  # noqa: BLE001
        return _route_failure(exc)
    data = _plain(meta.model_dump(mode="json") if hasattr(meta, "model_dump") else meta)
    return ToolResult("ok", data=data)


WRITES[CREATE_OPP] = WriteDef(
    name=CREATE_OPP,
    user_permission=OPP_ADD,
    schema={
        "type": "function",
        "function": {
            "name": CREATE_OPP,
            "description": (
                "Propose logging a new sales opportunity. Nothing is created until the user confirms. "
                "Give customer_id (from crm_opportunities_list or crm_resolve) or prospect_name."
            ),
            "parameters": {
                "type": "object",
                "properties": _OPP_FIELDS,
                "required": ["title", "expected_close_date"],
            },
        },
    },
    read_before=_opp_create_read_before,
    summary=_opp_create_summary,
    execute=_opp_create_execute,
    record_key="",
)
WRITES[UPDATE_OPP] = WriteDef(
    name=UPDATE_OPP,
    user_permission=OPP_EDIT,
    schema={
        "type": "function",
        "function": {
            "name": UPDATE_OPP,
            "description": (
                "Propose a change to one sales opportunity: its stage (status_id from crm_opportunity_meta, "
                "with lost_reason when Lost), dates, amount, title or customer. Nothing changes until the "
                "user confirms. opportunity_id must come from crm_opportunities_list. Call once per opportunity."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "opportunity_id": {"type": "string"},
                    **_OPP_FIELDS,
                    "status_id": {"type": "string"},
                    "lost_reason": {"type": "string", "maxLength": 150},
                },
                "required": ["opportunity_id"],
            },
        },
    },
    read_before=_opp_update_read_before,
    summary=_opp_update_summary,
    execute=_opp_update_execute,
    record_key="opportunity_id",
)
USER_READS[LIST_OPPS] = UserRead(
    name=LIST_OPPS,
    user_permission=OPP_VIEW,
    schema={
        "type": "function",
        "function": {
            "name": LIST_OPPS,
            "description": (
                "The user's sales opportunities (newest first), with the opportunity_id and stage to use in "
                "crm_opportunity_update. Filter by query text, stage ids, customer ids, close dates, outcome."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "status_ids": {"type": "array", "items": {"type": "string"}},
                    "customer_ids": {"type": "array", "items": {"type": "string"}},
                    "close_from": {"type": "string"},
                    "close_to": {"type": "string"},
                    "outcome": {"type": "string", "enum": ["open", "won", "lost"]},
                    "limit": {"type": "integer"},
                },
            },
        },
    },
    run=_opp_list,
)
USER_READS[OPP_META] = UserRead(
    name=OPP_META,
    user_permission=OPP_VIEW,
    schema={
        "type": "function",
        "function": {
            "name": OPP_META,
            "description": "The sales opportunity stages with their ids, and the lost reasons.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    run=_opp_meta,
)


# ------------------------------------------------------------------ W0 dealer-contact access

CONTACT_EDIT = "user_management.contacts.edit"
CONTACT_EDIT_OWN = "user_management.contacts.edit_own"
CONTACT_SLUGS = (CONTACT_EDIT_OWN, CONTACT_EDIT)
FIND_CONTACTS = "crm_contacts_find"
UPDATE_CONTACT = "crm_contact_access_update"
CONTACT_EVENT = "contact.access_agent"
MAX_PHONES = 20


def _own_agent_ids(db, user_id: str) -> list[str]:
    from app.models.user import User
    from app.services.sales.portal_agent import agents_for_contact

    contact_id = db.query(User.respond_contact_id).filter(User.id == user_id).scalar()
    return [str(a.id) for a in agents_for_contact(db, contact_id)] if contact_id else []


def contact_in_scope(db, user_id: str, contact_pk: str) -> bool:
    """May this user change this dealer contact's access? The `.edit` holder: any contact; otherwise a
    contact linked to a customer of the user's own active sales agents. Never the user's own contact."""
    from app.models.access import RespondContactCustomer
    from app.models.base import company_scope
    from app.models.order import Customer
    from app.models.user import User

    if str(db.query(User.respond_contact_id).filter(User.id == user_id).scalar() or "") == str(contact_pk):
        return False
    if _permitted(db, user_id, CONTACT_EDIT):
        return True
    agents = _own_agent_ids(db, user_id)
    if not agents:
        return False
    with company_scope(db, None):
        return (
            db.query(RespondContactCustomer.id)
            .join(Customer, Customer.id == RespondContactCustomer.customer_id)
            .filter(RespondContactCustomer.contact_id == str(contact_pk), Customer.sales_agent_id.in_(agents))
            .first()
            is not None
        )


def _owner_types(codes) -> set[str]:
    from app.services.contact_access_sheet_service import TEMPLATE

    return {t for code in codes for t in TEMPLATE["owner_types"].get(code, ())}


def _company_label(code: str) -> str:
    from app.services.contact_access_sheet_service import TEMPLATE

    names = {c: n for n, c in TEMPLATE["companies"].items()}
    return names.get(code, code).removesuffix(" Sdn Bhd")


def _contact_facts(db, contact) -> dict:
    """The contact as the access tools see it: access types, company codes, role and links."""
    from app.models.access import RespondContactCustomer
    from app.models.base import company_scope
    from app.models.company import Company, RespondContactCompany
    from app.services.contact_access_sheet_service import TEMPLATE

    types = {t.code for t in contact.access_types}
    codes = sorted(
        code for (code,) in db.query(Company.code)
        .join(RespondContactCompany, RespondContactCompany.company_id == Company.id)
        .filter(RespondContactCompany.respond_contact_id == contact.id)
    )
    template_codes = [c for c in codes if c in TEMPLATE["owner_types"]]
    owner = types & _owner_types(template_codes)
    role = "owner" if owner else ("employee" if TEMPLATE["base_type"] in types else "none")
    with company_scope(db, None):
        links = sorted(
            str(cid) for (cid,) in db.query(RespondContactCustomer.customer_id)
            .filter(RespondContactCustomer.contact_id == contact.id)
        )
    return {"types": types, "codes": codes, "template_codes": template_codes, "role": role, "links": links}


def _role_label(role: str, template_codes: list[str]) -> str:
    if role == "owner":
        return f"Business owner ({', '.join(_company_label(c) for c in template_codes)})"
    return "Employee" if role == "employee" else "No role"


def _relinkable(db, user_id: str, contact_id: str, customer_id: str) -> bool:
    """Did this user's own executed action unlink this contact from this customer (the undo of a resign)?"""
    from app.models.chatbot_agent import AgentAction

    rows = (
        db.query(AgentAction.steps)
        .filter(AgentAction.user_id == str(user_id), AgentAction.status.in_(("executed", "partial")))
        .order_by(AgentAction.created_at.desc())
        .limit(200)
        .all()
    )
    return any(
        step.get("tool") == UPDATE_CONTACT
        and step.get("status") == "done"
        and (step.get("args") or {}).get("contact_id") == str(contact_id)
        and str(customer_id) in ((step.get("args") or {}).get("unlink_customer_ids") or [])
        for (steps,) in rows
        for step in steps or []
    )


def _own_customer_codes(db, user_id: str, ids: list[str]) -> dict[str, str]:
    """{customer id: code} for customers of the user's own agents (any customer for a `.edit` holder)."""
    from app.models.base import company_scope
    from app.models.order import Customer
    from app.services.error_handler import AppException, handle_not_found

    if not ids:
        return {}
    broad = _permitted(db, user_id, CONTACT_EDIT)
    agents = _own_agent_ids(db, user_id)
    with company_scope(db, None):
        rows = {
            str(r.id): r
            for r in db.query(Customer.id, Customer.customer_code, Customer.sales_agent_id).filter(Customer.id.in_(ids))
        }
    out = {}
    for cid in ids:
        row = rows.get(str(cid))
        if row is None:
            raise handle_not_found("Customer", cid)
        if not broad and str(row.sales_agent_id or "") not in agents:
            raise AppException(status_code=403, message="That customer is not one of your own.", code="FORBIDDEN")
        out[str(cid)] = row.customer_code
    return out


def _contact_plan(db, user: dict, args: dict) -> dict:
    """What the call would change, after every scope check. Raises the route-shaped error otherwise."""
    from app.models.access import RespondContact
    from app.services.error_handler import AppException, handle_not_found

    contact = db.get(RespondContact, str(args["contact_id"]))
    if contact is None:
        raise handle_not_found("Contact", args["contact_id"])
    uid = str(user["id"])
    role, ai = args.get("role"), args.get("chatbot_allowed")
    link_ids, unlink_ids = list(args.get("link_customer_ids") or []), list(args.get("unlink_customer_ids") or [])
    if set(link_ids) & set(unlink_ids):
        raise AppException(status_code=422, message="A customer cannot be both linked and unlinked.", code="VALIDATION_ERROR")
    if not contact_in_scope(db, uid, contact.id):
        # Only the undo of this user's own resign: put the AI replies and the links back.
        undo = bool(link_ids) and not unlink_ids and role is None and all(
            _relinkable(db, uid, contact.id, c) for c in link_ids
        )
        if not undo:
            raise AppException(status_code=403, message="That contact is not one of yours.", code="FORBIDDEN")
    codes = _own_customer_codes(db, uid, [*link_ids, *unlink_ids])
    facts = _contact_facts(db, contact)
    phone = contact.phone_number
    add: set[str] = set()
    remove: set[str] = set()
    lines: list[str] = []
    if role is not None and role != facts["role"]:
        if not facts["codes"]:
            raise AppException(
                status_code=422, message="This contact has no company, so its role cannot be set.", code="VALIDATION_ERROR"
            )
        if not facts["template_codes"]:
            raise AppException(
                status_code=422, message="This contact's companies have no owner role to set.", code="VALIDATION_ERROR"
            )
        from app.services.contact_access_sheet_service import TEMPLATE

        owner = _owner_types(facts["template_codes"])
        add = {TEMPLATE["base_type"]} | (owner if role == "owner" else set())
        remove = owner if role == "employee" else set()
        lines.append(
            f"{_role_label(facts['role'], facts['template_codes'])} -> {_role_label(role, facts['template_codes'])}"
        )
    if ai is not None and ai != bool(contact.chatbot_allowed):
        lines.append(f"AI replies {'on' if contact.chatbot_allowed else 'off'} -> {'on' if ai else 'off'}")
    else:
        ai = None
    link = [c for c in link_ids if c not in facts["links"]]
    unlink = [c for c in unlink_ids if c in facts["links"]]
    lines += [f"linked to {codes[c]}" for c in link] + [f"unlinked from {codes[c]}" for c in unlink]
    if not lines:
        raise AppException(status_code=422, message=f"Nothing to change for {phone}.", code="VALIDATION_ERROR")
    return {
        "contact": contact, "facts": facts, "add": add, "remove": remove, "ai": ai,
        "link": link, "unlink": unlink, "lines": lines, "phone": phone,
    }


def _contact_state(contact, facts: dict) -> dict:
    return {"role": facts["role"], "chatbot_allowed": bool(contact.chatbot_allowed), "links": facts["links"]}


def _contact_read_before(db, user: dict, args: dict) -> dict:
    plan = _contact_plan(db, user, args)
    contact = plan["contact"]
    return {
        **_contact_state(contact, plan["facts"]),
        "_show": {"phone": plan["phone"], "name": contact.name or "", "changes": plan["lines"]},
    }


def _contact_summary(args: dict, before: dict) -> str:
    return f"{before['phone']} {before['name']}: ".replace("  ", " ") + "; ".join(before["changes"])


def _contact_execute(db, user: dict, args: dict) -> dict:
    from app.models.access import ContactAccessType
    from app.services import audit_service
    from app.services.contact_customer_service import link_customer, unlink_customer
    from app.services.error_handler import AppException

    plan = _contact_plan(db, user, args)
    contact, facts = plan["contact"], plan["facts"]
    before = _contact_state(contact, facts)
    if plan["add"] or plan["remove"]:
        wanted = (facts["types"] | plan["add"]) - plan["remove"]
        rows = [db.get(ContactAccessType, code) for code in sorted(wanted)]
        if any(r is None for r in rows):
            raise AppException(status_code=422, message="An access type this role needs is missing.", code="VALIDATION_ERROR")
        contact.access_types = rows
    if plan["ai"] is not None:
        contact.chatbot_allowed = plan["ai"]
    for customer_id in plan["link"]:
        link_customer(db, contact.id, customer_id, source="agent", linked_by=str(user["id"]))
    for customer_id in plan["unlink"]:
        unlink_customer(db, contact.id, customer_id)
    db.flush()
    db.expire(contact)
    after = _contact_state(contact, _contact_facts(db, contact))
    audit_service.record(
        db,
        event=CONTACT_EVENT,
        entity_type="respond_contacts",
        entity_id=contact.id,
        old_values={k: v for k, v in before.items() if v != after[k]},
        new_values={k: v for k, v in after.items() if v != before[k]},
        description="Contact access set by the agent",
    )
    db.commit()
    return {"id": str(args["contact_id"]), "after": after}


def _contacts_find(db, ctx, args: dict) -> ToolResult:
    from app.models.access import RespondContact, RespondContactCustomer
    from app.models.base import company_scope
    from app.models.order import Customer
    from app.services.contact_setup_engine import _find_contacts, normalise_phone

    unknown = sorted(k for k in args if k != "phones")
    if unknown:
        return ToolResult("invalid", message=f"Unknown argument(s): {', '.join(map(str, unknown))}.")
    phones = args.get("phones")
    if not (isinstance(phones, list) and 1 <= len(phones) <= MAX_PHONES and all(isinstance(p, str) for p in phones)):
        return ToolResult("invalid", message=f"phones must be 1 to {MAX_PHONES} phone numbers.")
    normal = {p: normalise_phone(p) for p in phones}
    found, ambiguous = _find_contacts(
        db, {n for n in normal.values() if n},
        columns=(RespondContact.id, RespondContact.name, RespondContact.phone_number, RespondContact.chatbot_allowed),
    )
    broad = _permitted(db, ctx.user_id, CONTACT_EDIT)
    agents = _own_agent_ids(db, ctx.user_id)
    out = []
    for phone in phones:
        n = normal[phone]
        if n is None:
            out.append({"status": "invalid_phone", "phone": phone})
        elif n in ambiguous:
            out.append({"status": "ambiguous", "phone": phone})
        elif n not in found:
            out.append({"status": "not_found", "phone": phone})
        elif not contact_in_scope(db, ctx.user_id, found[n].id):
            out.append({"status": "not_yours", "phone": phone})
        else:
            contact = db.get(RespondContact, found[n].id)
            facts = _contact_facts(db, contact)
            with company_scope(db, None):
                accounts = [
                    {"customer_id": str(c.id), "code": c.customer_code, "name": c.customer_name}
                    for c in db.query(Customer)
                    .join(RespondContactCustomer, RespondContactCustomer.customer_id == Customer.id)
                    .filter(RespondContactCustomer.contact_id == contact.id)
                    .order_by(Customer.customer_code)
                    if broad or str(c.sales_agent_id or "") in agents
                ]
            out.append({
                "status": "found", "contact_id": str(contact.id), "name": contact.name, "phone": contact.phone_number,
                "companies": facts["codes"], "role": facts["role"], "chatbot_allowed": bool(contact.chatbot_allowed),
                "accounts": accounts,
            })
    return ToolResult("ok", data=out)


WRITES[UPDATE_CONTACT] = WriteDef(
    name=UPDATE_CONTACT,
    user_permission=CONTACT_SLUGS,
    schema={
        "type": "function",
        "function": {
            "name": UPDATE_CONTACT,
            "description": (
                "Propose a change to one dealer contact's access: role (owner = Business owner, employee), "
                "chatbot_allowed (AI replies), and customer links. To resign a contact, set chatbot_allowed "
                "false and unlink its accounts. Nothing changes until the user confirms. contact_id and "
                "customer ids must come from crm_contacts_find. Call once per contact."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "contact_id": {"type": "string"},
                    "role": {"type": "string", "enum": ["owner", "employee"]},
                    "chatbot_allowed": {"type": "boolean"},
                    "link_customer_ids": {"type": "array", "items": {"type": "string"}},
                    "unlink_customer_ids": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["contact_id"],
            },
        },
    },
    read_before=_contact_read_before,
    summary=_contact_summary,
    execute=_contact_execute,
    record_key="contact_id",
)
USER_READS[FIND_CONTACTS] = UserRead(
    name=FIND_CONTACTS,
    user_permission=CONTACT_SLUGS,
    schema={
        "type": "function",
        "function": {
            "name": FIND_CONTACTS,
            "description": (
                "Look up dealer contacts by phone number (up to 20). Each phone is found, not_found, "
                "ambiguous, invalid_phone or not_yours (not one of the user's contacts). A found contact "
                "carries its contact_id, role, AI replies and accounts."
            ),
            "parameters": {
                "type": "object",
                "properties": {"phones": {"type": "array", "items": {"type": "string"}}},
                "required": ["phones"],
            },
        },
    },
    run=_contacts_find,
)
