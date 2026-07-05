"""Record-action write tools for the MCP server.

Wraps existing internal-staff CRM endpoints so an n8n agent (or the in-app AI
assistant) can operate the system by chat — "close complaint C-1042", "approve
PR-88", "cancel this order". Four tools are registered:

- ``crm_complaint_close``            → POST  /complaints-management/complaints/{id}/close
- ``crm_order_cancel``               → PUT   /order-management/orders/{id}   (is_cancelled=true)
- ``crm_purchase_request_approve``   → POST  /procurement/purchase-requests/{id}/approval-decision (action=approved)
- ``crm_purchase_request_reject``    → POST  /procurement/purchase-requests/{id}/approval-decision (action=rejected)

These are ``external=True`` catalog specs (see ``catalog.py``): the compiled
HTTP template can't inject a *fixed* decision field (close / cancel /
action=approved|rejected), so each tool is registered here with a dedicated
handler that fills it in and only asks the caller for the entity UUID plus an
optional note. The path + method + description come from the shared ToolSpec so
there is a single source of truth; the fixed body is the only tool-specific bit.

The tool names carry a write-verb suffix (_close / _cancel / _approve /
_reject) so the in-app assistant's write-confirmation gate halts them until the
user explicitly confirms — nothing here bypasses that.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from mcp.server.fastmcp import Context

from sorento_crm_mcp.catalog import CATALOG
from sorento_crm_mcp.settings import Settings

logger = logging.getLogger(__name__)

_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)

RECORD_ACTION_TOOLS: tuple[str, ...] = (
    "crm_complaint_close",
    "crm_order_cancel",
    "crm_purchase_request_approve",
    "crm_purchase_request_reject",
)

_SPECS = {s.name: s for s in CATALOG if s.name in RECORD_ACTION_TOOLS}


def _invalid_uuid(param: str, value: Any, tool_name: str) -> str:
    """Return a JSON error string when an id argument is not a canonical UUID.

    The assistant's UUID-coercion layer resolves codes → UUIDs upstream, but a
    non-UUID here would only trigger a 500 UUID-cast error at the backend, so we
    short-circuit with an actionable message instead.
    """
    return json.dumps(
        {
            "error": f"Parameter '{param}' expects a canonical UUID for tool '{tool_name}'.",
            "code": "INVALID_IDENTIFIER_FORMAT",
            "received": str(value)[:120],
            "suggestion": (
                "Resolve the human code (e.g. C-1042 / PR-88 / an order number) to its UUID "
                "with a list/get tool first, then pass that UUID."
            ),
        }
    )


async def _post_record_action(
    client: Any,
    *,
    tool_name: str,
    id_param: str,
    id_value: str,
    body: dict[str, Any],
) -> str:
    """Execute one record-action request against the backend and return raw text.

    ``client`` is the lifespan ``CRMClient`` (carries X-API-Key, timeout, size
    guard, logging). Path + method are read from the shared ToolSpec so they can
    never drift from the catalog the admin sees.
    """
    if not id_value or not _UUID_RE.match(str(id_value)):
        return _invalid_uuid(id_param, id_value, tool_name)
    spec = _SPECS[tool_name]
    return await client.request(
        spec.method,
        spec.path,
        path_params={id_param: id_value},
        body=body,
        tool_name=tool_name,
    )


def register_record_action_tools(mcp: Any, settings: Settings) -> None:
    """Register the four record-action write tools on the given FastMCP instance."""

    async def crm_complaint_close(
        ctx: Context, complaint_id: str, note: str | None = None
    ) -> str:
        """Close / resolve a complaint (status='closed').

        ``complaint_id`` is the canonical complaint UUID. ``note`` is an optional
        closing remark relayed to the contact.
        """
        client = ctx.request_context.lifespan_context["client"]
        body: dict[str, Any] = {}
        if note:
            body["note"] = note
        return await _post_record_action(
            client,
            tool_name="crm_complaint_close",
            id_param="complaint_id",
            id_value=complaint_id,
            body=body,
        )

    async def crm_order_cancel(
        ctx: Context, order_id: str, reason: str | None = None
    ) -> str:
        """Cancel an order.

        Posts to the dedicated ``/cancel`` endpoint, which sets is_cancelled=true
        server-side and runs the complaint re-evaluation. ``order_id`` is the
        canonical order UUID. ``reason`` is an optional free-text remark stored on
        the order.
        """
        client = ctx.request_context.lifespan_context["client"]
        body: dict[str, Any] = {}
        if reason:
            body["reason"] = reason
        return await _post_record_action(
            client,
            tool_name="crm_order_cancel",
            id_param="order_id",
            id_value=order_id,
            body=body,
        )

    async def crm_purchase_request_approve(
        ctx: Context, purchase_request_id: str, comments: str | None = None
    ) -> str:
        """Approve a pending purchase request / sponsorship form (action=approved).

        ``purchase_request_id`` is the canonical PR UUID. ``comments`` is an
        optional approval remark.
        """
        client = ctx.request_context.lifespan_context["client"]
        body: dict[str, Any] = {"action": "approved"}
        if comments:
            body["comments"] = comments
        return await _post_record_action(
            client,
            tool_name="crm_purchase_request_approve",
            id_param="purchase_request_id",
            id_value=purchase_request_id,
            body=body,
        )

    async def crm_purchase_request_reject(
        ctx: Context, purchase_request_id: str, reason: str | None = None
    ) -> str:
        """Reject a pending purchase request / sponsorship form (action=rejected).

        ``purchase_request_id`` is the canonical PR UUID. ``reason`` is an
        optional rejection comment.
        """
        client = ctx.request_context.lifespan_context["client"]
        body: dict[str, Any] = {"action": "rejected"}
        if reason:
            body["comments"] = reason
        return await _post_record_action(
            client,
            tool_name="crm_purchase_request_reject",
            id_param="purchase_request_id",
            id_value=purchase_request_id,
            body=body,
        )

    handlers = {
        "crm_complaint_close": crm_complaint_close,
        "crm_order_cancel": crm_order_cancel,
        "crm_purchase_request_approve": crm_purchase_request_approve,
        "crm_purchase_request_reject": crm_purchase_request_reject,
    }
    for name, fn in handlers.items():
        spec = _SPECS[name]
        mcp.add_tool(fn, name=name, description=spec.description)
        logger.debug("Registered record-action MCP tool %s", name)
