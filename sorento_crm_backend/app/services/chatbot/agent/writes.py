"""The agent's write tools and its in-process reads as the user (AGENTIC-P3 plan section 1).

A write tool is one existing screen operation: `execute` calls the route function the screen
calls, in process, as the contact's linked user. Nothing is written when the model calls a write:
`propose_step` only checks the call and reads the record as it is now; `actions.confirm` runs the
steps later. The route's `Depends(require_permission(...))` does not run on a direct call, so the
slug is checked here at exposure, proposal and execution.
"""
from __future__ import annotations

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
    #: The route's own slug: checked at exposure, proposal and execution.
    user_permission: str
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
    #: "" = no slug beyond the agent switch.
    user_permission: str
    schema: dict
    #: (db, ctx, args) -> ToolResult
    run: Callable[[Any, Any, dict], ToolResult]


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
    return [w for w in WRITES.values() if _permitted(db, ctx.user_id, w.user_permission)]


def permitted_user_reads(db, ctx) -> list[UserRead]:
    return [r for r in USER_READS.values() if not r.user_permission or _permitted(db, ctx.user_id, r.user_permission)]


def run_user_read(db, ctx, name: str, args: Any, seen_ids: set[str]) -> ToolResult:
    """One in-process read as the user. The ids in its result join the turn's seen ids."""
    read = USER_READS.get(name)
    if read is None:
        return ToolResult("denied", message=f"{name} is not a tool you may use.")
    if read.user_permission and not _permitted(db, ctx.user_id, read.user_permission):
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
        if spec.get("type") == "string" and not isinstance(value, str):
            return f"`{key}` must be text."
        if "enum" in spec and value not in spec["enum"]:
            return f"`{key}` must be one of: {', '.join(spec['enum'])}."
        if "maxLength" in spec and len(value) > spec["maxLength"]:
            return f"`{key}` is too long."
    return None


def propose_step(db, ctx, name: str, args: Any, *, seen_ids: set[str]) -> tuple[ToolResult, dict | None]:
    """Check a write call and read the record as it is now. Never writes. Success returns the
    "proposed" result and the step to store; any failure returns a typed result and no step."""
    definition = WRITES.get(name) if isinstance(name, str) else None
    if definition is None:
        return ToolResult("denied", message=f"{name} is not a tool you may use."), None
    if not _permitted(db, ctx.user_id, definition.user_permission):
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
    summary = definition.summary(args, before)
    step = {"tool": name, "args": dict(args), "before": before, "summary": summary, "status": "proposed"}
    return ToolResult("proposed", data={"summary": summary}), step
