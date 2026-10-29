"""The agent's tool registry and its dispatch permission layer (AGENTIC-P1 card sections 2, 3).

An explicit table of the read-only MCP tools the agent may call, each with the permission
slug the linked user must hold. The model-facing schema comes from the MCP catalogue with the
server-injected `contact_id` / `space_id` removed. `dispatch` re-checks everything at call
time, because showing a tool to the model is not a guard.
"""
from __future__ import annotations

import copy
import json
import logging
from dataclasses import dataclass
from typing import Any, Callable

from app.services.ai_assistant_service import mcp_schema_to_openai_tool

logger = logging.getLogger(__name__)

#: Server-injected, never model-chosen.
GUARD_PARAMS = ("contact_id", "space_id")
#: Characters of JSON one tool result may carry back to the model.
RESULT_CHAR_CAP = 12_000


@dataclass(frozen=True)
class ToolDef:
    name: str
    user_permission: str
    #: The reveal the contact must hold before today's bot calls this tool's domain
    #: (`turn/policy_rows.py`, `answer.DOMAIN_GRANT_REQUIRED`, `turn/sub_asks.GRANT`); None
    #: where today's bot requires none.
    contact_grant: str | None = None
    #: True for a presenter tool (`sorento_crm_mcp.presenters.PRESENTER_TOOLS`): it is called
    #: with `view=render`, its answer is a render envelope carrying `restricted_fields`, and
    #: anything else is refused. The two non-presenter tools answer the route's raw JSON.
    #: Both were checked in the MCP catalogue: neither declares `restricted_fields`, so there
    #: is no field-level drop to lose by skipping the render view for them.
    render: bool = True


def _defs(*rows: tuple[str, str, str | None]) -> dict[str, ToolDef]:
    return {
        name: ToolDef(name, slug, grant, render=name not in NON_RENDER_TOOLS)
        for name, slug, grant in rows
    }


NON_RENDER_TOOLS = frozenset({"crm_lookup_resolve", "crm_procurement_grn_summary"})


# crm_report_ask: the sales / outstanding reveal is decided by the route itself from the
# contact id (salesperson book and open pending delivery are exceptions it already knows),
# so the tool carries none; the chat dataset is gated below in ARG_CONTACT_GRANTS.
REGISTRY: dict[str, ToolDef] = _defs(
    ("crm_report_ask", "order_management.orders.view", None),
    ("crm_inventory_stock_balance_list", "inventory.stock.view", None),
    ("crm_incoming_stock_by_product", "procurement.packing_lists.view", None),
    ("crm_incoming_stock_shipments", "procurement.packing_lists.view", None),
    ("crm_procurement_grn_summary", "procurement.grn.view", "purchase_orders.placed"),
    ("crm_procurement_po_last_cost_list", "scm.purchase_orders.view", "purchase_orders.cost"),
    ("crm_procurement_po_placed_list", "scm.purchase_orders.view", "purchase_orders.placed"),
    ("crm_procurement_spo_allocations_last_receipt_list", "procurement.spo_allocations.view", "purchase_orders.placed"),
    ("crm_order_management_orders_by_product_list", "order_management.orders.view", None),
    ("crm_lookup_resolve", "master_data.products.view", None),
)

#: Tools that read stock: today's bot refuses them for a contact with `chatbot_stock_allowed` off.
STOCK_TOOLS = frozenset({"crm_inventory_stock_balance_list"})

#: Argument values that need more than the tool's own slug, on `crm_report_ask`
#: (`order_management/report_ask.py`: unpaid needs `finance.billing_documents.view` on the
#: act-as user; the chat dataset is the analytics screen's data).
ARG_PERMISSIONS: dict[tuple[str, str], str] = {
    ("basis", "unpaid"): "finance.billing_documents.view",
    ("dataset", "chat"): "chatbot.analytics.view",
}
ARG_CONTACT_GRANTS: dict[tuple[str, str], str] = {
    ("dataset", "chat"): "chatbot.analytics",
}
#: `view=render` is what makes the MCP attach `restricted_fields`; it is never the model's choice.
VIEW_PARAM = "view"
SELLABLE_PARAM = "include_sellable"
SELLABLE_GRANT = "inventory.sellable"
#: Keys the presenter envelope always carries one of; a raw route payload carries none.
ENVELOPE_KEYS = ("has_result", "result_type", "items", "answers", "response")
FIXED_ERROR = "The tool failed."
FIXED_TIMEOUT = "The tool did not answer in time."
FIXED_NOT_ENVELOPE = "The tool returned an unexpected shape, so its data was not used."


@dataclass
class ToolResult:
    status: str  # "ok" | "denied" | "invalid" | "error" | "timeout"
    data: Any = None
    more: int = 0
    message: str = ""

    def to_json(self) -> str:
        return json.dumps(
            {"status": self.status, "data": self.data, "more": self.more, "message": self.message},
            default=str,
        )


def tool_schemas(tools: list[ToolDef], catalog: dict[str, dict]) -> list[dict]:
    """OpenAI-style function tools for `tools`, from the MCP catalogue, guards stripped."""
    out: list[dict] = []
    for tool in tools:
        meta = catalog.get(tool.name)
        if not isinstance(meta, dict):
            continue
        schema = mcp_schema_to_openai_tool(tool.name, meta)
        params = schema["function"]["parameters"]
        # The model never chooses the view: dispatch always sends render.
        params["properties"] = {k: v for k, v in params["properties"].items() if k != VIEW_PARAM}
        params["required"] = [r for r in params.get("required") or [] if r != VIEW_PARAM]
        out.append(schema)
    return out


def contact_allows(ctx: Any, tool: ToolDef) -> bool:
    """The contact side of a tool: its reveal grant, and the stock switch for stock tools."""
    if tool.contact_grant and tool.contact_grant not in ctx.grants:
        return False
    if tool.name in STOCK_TOOLS and not getattr(ctx, "stock_allowed", True):
        return False
    return True


def _arg_value(args: dict, key: str) -> str:
    value = args.get(key)
    return value.strip().lower() if isinstance(value, str) else ""


def _gated_keys() -> set[str]:
    return {k for k, _ in ARG_PERMISSIONS} | {k for k, _ in ARG_CONTACT_GRANTS}


def _plain_string(value: Any) -> bool:
    """A gated argument must be one plain string: a list, a number or a JSON-looking string
    could carry the gated value past the comparison."""
    return isinstance(value, str) and not value.strip().startswith(("[", "{"))


def clip_args(args: Any, limit: int = 500) -> Any:
    """`args` as stored in the digest and the trace: at most `limit` characters of JSON."""
    try:
        raw = json.dumps(args, default=str, ensure_ascii=False)
    except (TypeError, ValueError):
        return {"_unreadable": True}
    return args if len(raw) <= limit else {"_clipped": raw[:limit]}

def _permitted(db: Any, user_id: str, slug: str) -> bool:
    from app.services.user_service import UserPermissionService

    try:
        return bool(UserPermissionService(db).check_user_has_permission(user_id, slug))
    except Exception:  # noqa: BLE001 - a failed check is a refusal, never a pass
        logger.warning("agent: permission check failed for %s", slug, exc_info=True)
        return False


def _as_data(raw: Any) -> Any:
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except ValueError:
            return raw
    return copy.deepcopy(raw)


def _size(data: Any) -> int:
    return len(json.dumps(data, default=str))


def cap_result(data: Any, limit: int = RESULT_CHAR_CAP) -> tuple[Any, int]:
    """`data` under `limit` characters of JSON. List values are cut by whole items from the
    back, largest list first; the second value counts the items cut."""
    if _size(data) <= limit:
        return data, 0
    more = 0
    if isinstance(data, list):
        holder: dict[str, Any] = {"v": data}
        shaped, more = cap_result(holder, limit)
        return shaped["v"], more
    if isinstance(data, dict):
        lists = sorted(
            (k for k, v in data.items() if isinstance(v, list) and v),
            key=lambda k: -len(data[k]),
        )
        for key in lists:
            if _size(data) <= limit:
                break
            rows = data[key]
            lo, hi = 0, len(rows)  # largest k with rows[:k] fitting
            while lo < hi:
                mid = (lo + hi + 1) // 2
                data[key] = rows[:mid]
                if _size(data) <= limit:
                    lo = mid
                else:
                    hi = mid - 1
            data[key] = rows[:lo]
            more += len(rows) - lo
    if _size(data) > limit:
        # Nothing left to cut by whole items: say so rather than cut a row in half.
        return {"truncated": True, "note": "result too large to show"}, more
    return data, more


def dispatch(
    db: Any,
    ctx: Any,
    name: str,
    args: Any,
    *,
    call: Callable[[str, dict], Any],
    catalog: dict[str, dict],
    timeout: float,
) -> ToolResult:
    """One tool call, checked in the order the contract names. Never raises."""
    from app.services.chatbot.lanes.business.fetch import ToolNotAllowed, drop_restricted_fields
    from app.services.llm_provider import is_timeout

    tool = REGISTRY.get(name) if isinstance(name, str) else None
    if tool is None:
        return ToolResult("denied", message=f"{name} is not a tool you may use.")
    if not _permitted(db, ctx.user_id, tool.user_permission):
        return ToolResult("denied", message=f"{name} is outside this user's access.")
    if not contact_allows(ctx, tool):
        return ToolResult("denied", message=f"{name} is outside this contact's access.")
    meta = catalog.get(name)
    if not isinstance(meta, dict):
        return ToolResult("error", message=f"{name} is not available right now.")
    if not isinstance(args, dict):
        return ToolResult("invalid", message="Arguments must be an object of named values.")
    schema = meta.get("inputSchema") if isinstance(meta.get("inputSchema"), dict) else {}
    allowed = set((schema.get("properties") or {}).keys()) | set(GUARD_PARAMS) | {VIEW_PARAM}
    unknown = sorted(k for k in args if k not in allowed)
    if unknown:
        return ToolResult("invalid", message=f"Unknown argument(s): {', '.join(map(str, unknown))}.")

    if name == "crm_report_ask":
        args = {k: v for k, v in args.items() if not (k in _gated_keys() and v is None)}
        for key in _gated_keys():
            if key in args and not _plain_string(args[key]):
                return ToolResult("invalid", message=f"{key} must be a single plain value.")
        for (key, value), slug in ARG_PERMISSIONS.items():
            if _arg_value(args, key) == value and not _permitted(db, ctx.user_id, slug):
                return ToolResult("denied", message=f"{key}={value} is outside this user's access.")
        for (key, value), grant in ARG_CONTACT_GRANTS.items():
            if _arg_value(args, key) == value and grant not in ctx.grants:
                return ToolResult("denied", message=f"{key}={value} is outside this contact's access.")

    clean = {k: v for k, v in args.items() if k not in GUARD_PARAMS and k != VIEW_PARAM}
    if SELLABLE_GRANT not in ctx.grants:
        clean.pop(SELLABLE_PARAM, None)
    clean["contact_id"] = ctx.contact_respond_id
    if ctx.space_id is not None:
        clean["space_id"] = ctx.space_id
    # Only the render view carries `restricted_fields`, which the field drop below relies on.
    if tool.render:
        clean[VIEW_PARAM] = "render"

    try:
        raw = call(name, clean)
    except ToolNotAllowed as exc:
        return ToolResult("denied", message=str(exc) or f"{name} is not allowed for this contact.")
    except TimeoutError:
        return ToolResult("timeout", message=FIXED_TIMEOUT)
    except Exception as exc:  # noqa: BLE001 - a tool failure is a result the model can work around
        if is_timeout(exc):
            return ToolResult("timeout", message=FIXED_TIMEOUT)
        logger.warning("agent: tool %s failed", name, exc_info=True)
        return ToolResult("error", message=FIXED_ERROR)

    data = _as_data(raw)
    if tool.render:
        # Fail closed: a presenter tool's result that is not a render envelope has not been
        # through the presenter, so nothing in it can be trusted to be field-scoped.
        if not (isinstance(data, dict) and any(k in data for k in ENVELOPE_KEYS)):
            logger.warning("agent: %s returned a non-envelope result", name)
            return ToolResult("error", message=FIXED_NOT_ENVELOPE)
        axis = clean.get("group_by")
        drop_restricted_fields(data, set(ctx.grants), axis if isinstance(axis, str) else None)
    data, more = cap_result(data)
    return ToolResult("ok", data=data, more=more)
