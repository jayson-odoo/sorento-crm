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


def _defs(*rows: tuple[str, str]) -> dict[str, ToolDef]:
    return {name: ToolDef(name, slug) for name, slug in rows}


REGISTRY: dict[str, ToolDef] = _defs(
    ("crm_report_ask", "order_management.orders.view"),
    ("crm_inventory_stock_balance_list", "inventory.stock.view"),
    ("crm_incoming_stock_by_product", "procurement.packing_lists.view"),
    ("crm_incoming_stock_shipments", "procurement.packing_lists.view"),
    ("crm_procurement_grn_summary", "procurement.grn.view"),
    ("crm_procurement_po_last_cost_list", "scm.purchase_orders.view"),
    ("crm_procurement_po_placed_list", "scm.purchase_orders.view"),
    ("crm_procurement_spo_allocations_last_receipt_list", "procurement.spo_allocations.view"),
    ("crm_order_management_orders_by_product_list", "order_management.orders.view"),
    ("crm_lookup_resolve", "master_data.products.view"),
)


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
        out.append(mcp_schema_to_openai_tool(tool.name, meta))
    return out


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
    meta = catalog.get(name)
    if not isinstance(meta, dict):
        return ToolResult("error", message=f"{name} is not available right now.")
    if not isinstance(args, dict):
        return ToolResult("invalid", message="Arguments must be an object of named values.")
    schema = meta.get("inputSchema") if isinstance(meta.get("inputSchema"), dict) else {}
    allowed = set((schema.get("properties") or {}).keys()) | set(GUARD_PARAMS)
    unknown = sorted(k for k in args if k not in allowed)
    if unknown:
        return ToolResult("invalid", message=f"Unknown argument(s): {', '.join(map(str, unknown))}.")

    clean = {k: v for k, v in args.items() if k not in GUARD_PARAMS}
    clean["contact_id"] = ctx.contact_respond_id
    if ctx.space_id is not None:
        clean["space_id"] = ctx.space_id

    try:
        raw = call(name, clean)
    except ToolNotAllowed as exc:
        return ToolResult("denied", message=str(exc) or f"{name} is not allowed for this contact.")
    except TimeoutError:
        return ToolResult("timeout", message=f"{name} did not answer in time.")
    except Exception as exc:  # noqa: BLE001 - a tool failure is a result the model can work around
        if is_timeout(exc):
            return ToolResult("timeout", message=f"{name} did not answer in time.")
        logger.warning("agent: tool %s failed", name, exc_info=True)
        return ToolResult("error", message=f"{name} failed: {str(exc)[:200] or type(exc).__name__}.")

    data = _as_data(raw)
    if isinstance(data, dict):
        axis = clean.get("group_by")
        drop_restricted_fields(data, set(ctx.grants), axis if isinstance(axis, str) else None)
    data, more = cap_result(data)
    return ToolResult("ok", data=data, more=more)
