"""`crm_query` and `crm_describe`: the agent's general read over the assistant registry (AI-QUERY-CORE).

Two `UserRead`s, run in process as the user (`writes.run_as_user`), on the panel and on a WhatsApp turn whose
contact has a linked active user; never for a contact principal (`writes.permitted_user_reads`). The read needs no
slug of its own: each entity's screen slug, own-row rule, field slugs and module switch are checked inside
(`assistant_registry.query`). Linked-only: when a console operator acts for someone else, a group total cannot be
cut down to what both people may see, so the tools are not offered then.
"""
from __future__ import annotations

from typing import Any

from app.services.assistant_registry.query import MAX_GROUPS, MAX_ROWS, QueryRefused, describe, run_query
from app.services.chatbot.agent import writes
from app.services.chatbot.agent.tools import TOOL_LABELS, ToolResult, cap_result

QUERY = "crm_query"
DESCRIBE = "crm_describe"

_REFUSAL_STATUS = {
    "no_access": "denied",
    "restricted": "denied",
    "own_only_unsupported": "denied",
    "module_disabled": "denied",
    "timeout": "timeout",
}


def _refused(exc: QueryRefused) -> ToolResult:
    return ToolResult(_REFUSAL_STATUS.get(exc.code, "invalid"), message=exc.message)


def _as_user(db, ctx, name: str, fn) -> ToolResult:
    if getattr(ctx, "principal", "user") == "contact" or not ctx.user_id:
        return ToolResult("denied", message=f"{name} is not a tool you may use.")
    try:
        data = writes.run_as_user(db, ctx, lambda user: fn(str(user["id"])), tool_name=name)
    except QueryRefused as exc:
        return _refused(exc)
    except Exception as exc:  # noqa: BLE001
        return writes._route_failure(exc)
    shaped, more = cap_result(data)
    return ToolResult("ok", data=shaped, more=more)


def _query(db, ctx, args: dict) -> ToolResult:
    return _as_user(db, ctx, QUERY, lambda user_id: run_query(db, user_id, args))


def _describe(db, ctx, args: dict) -> ToolResult:
    unknown = sorted(str(k) for k in args if k != "entity")
    if unknown:
        return ToolResult("invalid", message=f"Unknown argument(s): {', '.join(unknown)}.")
    entity: Any = args.get("entity") or None
    return _as_user(db, ctx, DESCRIBE, lambda user_id: describe(db, user_id, entity))


_FIELD = {"type": "string"}
_SCALAR = {"type": ["string", "number", "boolean", "null"]}

QUERY_SCHEMA = {
    "type": "function",
    "function": {
        "name": QUERY,
        "description": (
            "Read CRM records as the screens show them: rows, filters, totals and group-by over one entity. "
            "Call crm_describe first for the entity keys and fields. Fields may go through relations "
            "(supplier.name). With group_by or aggregates you get groups, else rows (each with id and link). "
            f"At most {MAX_ROWS} rows or {MAX_GROUPS} groups; `total` and `truncated` say if there are more. "
            "Dates are Malaysian dates (YYYY-MM-DD)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "entity": _FIELD,
                "fields": {"type": "array", "items": _FIELD},
                "filters": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "field": _FIELD,
                            "op": {"type": "string", "enum": [
                                "eq", "ne", "in", "not_in", "lt", "lte", "gt", "gte", "between", "contains",
                                "starts_with", "is_null", "is_not_null",
                            ]},
                            "value": {"anyOf": [_SCALAR, {"type": "array", "items": _SCALAR}]},
                        },
                        "required": ["field", "op"],
                    },
                },
                "group_by": {
                    "type": "array",
                    "items": {"anyOf": [_FIELD, {
                        "type": "object",
                        "properties": {
                            "field": _FIELD,
                            "bucket": {"type": "string", "enum": ["day", "week", "month", "quarter", "year"]},
                        },
                        "required": ["field"],
                    }]},
                },
                "aggregates": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "fn": {"type": "string", "enum": ["count", "count_distinct", "sum", "avg", "min", "max"]},
                            "field": _FIELD,
                        },
                        "required": ["fn"],
                    },
                },
                "sort": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {"field": _FIELD, "dir": {"type": "string", "enum": ["asc", "desc"]}},
                        "required": ["field"],
                    },
                },
                "limit": {"type": "integer", "minimum": 1},
            },
            "required": ["entity"],
        },
    },
}

DESCRIBE_SCHEMA = {
    "type": "function",
    "function": {
        "name": DESCRIBE,
        "description": (
            "Without entity: the CRM entities this user may read with crm_query. With entity: its fields "
            "(type, restricted), relations, filter ops, date buckets, aggregates and limits."
        ),
        "parameters": {"type": "object", "properties": {"entity": _FIELD}},
    },
}

writes.USER_READS[QUERY] = writes.UserRead(
    name=QUERY, user_permission="", schema=QUERY_SCHEMA, run=_query, linked_only=True,
)
writes.USER_READS[DESCRIBE] = writes.UserRead(
    name=DESCRIBE, user_permission="", schema=DESCRIBE_SCHEMA, run=_describe, linked_only=True,
)
TOOL_LABELS.setdefault(QUERY, "reading CRM records, totals and groupings")
TOOL_LABELS.setdefault(DESCRIBE, "listing the CRM records you can read")
