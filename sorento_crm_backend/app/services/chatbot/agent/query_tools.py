"""`crm_query` and `crm_describe`: the agent's general read over the assistant registry (AI-QUERY-CORE).

Two `UserRead`s, run in process as the user (`writes.run_as_user`), on the panel and on a WhatsApp turn whose
contact has a linked active user; never for a contact principal (`writes.permitted_user_reads`). The read needs no
slug of its own beyond holding one registered entity's view or own slug: each entity's screen slug, own-row
rule, field slugs and module switch are checked inside (`assistant_registry.query`). Linked-only: when a console operator acts for someone else, a group total cannot be
cut down to what both people may see, so the tools are not offered then.
"""
from __future__ import annotations

from typing import Any

from app.services.assistant_registry import ENTITIES
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


def _available(db, ctx) -> bool:
    """Off the panel, a contact narrowed to its linked customers (no office access type) keeps that narrowing
    today on every WhatsApp read; these tools run as the linked user and cannot narrow by customer, so they
    are not offered to it. Fail closed: a lookup that fails offers nothing."""
    from app.services.chatbot import principal as staff_principal

    if staff_principal.current() is not None:
        return True
    from app.services.contact_customer_scope import contact_customer_scope

    # A savepoint, so a failed lookup does not leave the turn's transaction aborted for every later call.
    savepoint = db.begin_nested()
    try:
        enforced = contact_customer_scope(db, str(ctx.contact_pk)).enforced
    except Exception:  # noqa: BLE001
        savepoint.rollback()
        return False
    savepoint.commit()
    return not enforced


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


QUERY_SCHEMA = {
    "type": "function",
    "function": {
        "name": QUERY,
        "description": (
            "Read CRM records as their screens show them: rows, or totals with group_by. Entity keys and fields "
            "come from crm_describe; a field may go through a relation (supplier.name). "
            "filters: [{field, op, value}], op one of eq ne in not_in lt lte gt gte between contains starts_with "
            "is_null is_not_null. group_by: [field or {field, bucket: day|week|month|quarter|year}]. "
            "aggregates: [{fn: count|count_distinct|sum|avg|min|max, field}]. sort: [{field, dir}] (a group "
            f"sorts by its key or an aggregate alias such as sum_total_amount). At most {MAX_ROWS} rows or "
            f"{MAX_GROUPS} groups; total and truncated say if there are more. Dates are Malaysian, YYYY-MM-DD."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "entity": {"type": "string"},
                "fields": {"type": "array", "items": {"type": "string"}},
                "filters": {"type": "array", "items": {"type": "object"}},
                "group_by": {"type": "array"},
                "aggregates": {"type": "array", "items": {"type": "object"}},
                "sort": {"type": "array", "items": {"type": "object"}},
                "limit": {"type": "integer"},
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
        "parameters": {"type": "object", "properties": {"entity": {"type": "string"}}},
    },
}

#: Offered to a user who may read at least one registered entity (its view or own slug); each entity's own
#: slugs are checked again inside every call.
ANY_ENTITY = tuple(sorted({
    slug for e in ENTITIES.values() for slug in (e.view_permission, e.own_permission) if slug
}))

writes.USER_READS[QUERY] = writes.UserRead(
    name=QUERY, user_permission=ANY_ENTITY, schema=QUERY_SCHEMA, run=_query, linked_only=True, available=_available,
)
writes.USER_READS[DESCRIBE] = writes.UserRead(
    name=DESCRIBE, user_permission=ANY_ENTITY, schema=DESCRIBE_SCHEMA, run=_describe, linked_only=True, available=_available,
)
TOOL_LABELS.setdefault(QUERY, "reading CRM records, totals and groupings")
TOOL_LABELS.setdefault(DESCRIBE, "listing the CRM records you can read")
