"""Discovery tools for the Sorento CRM MCP server.

Exposes one tool the n8n agent must call BEFORE any UUID-typed domain tool when
the user mentions an entity by code/name (not UUID):

    crm_find_entity(query) → {candidates[], ambiguous, unresolved, suggested_tools}

Proxies the backend `/api/v1/system/references/resolve` endpoint, which runs the
deterministic SQL resolver (exact → prefix ILIKE → substring ILIKE; trgm for
typo tolerance) across products, customers, orders, transporters, shipments,
SPOs, GRNs, warehouses, suppliers, promotions, forms, and attachments. Returns
the entity UUID alongside the canonical_code so the agent can paste it into
the matching domain tool's `<entity>_ids` param.

n8n already does RAG over tool descriptions for tool selection, so we ship
only the data-resolution tool here — n8n RAG can't resolve "TT440" → a product
UUID because that's data, not tool metadata.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

from sorento_crm_mcp.catalog import CATALOG, ToolSpec
from sorento_crm_mcp.http_client import CRMClient
from sorento_crm_mcp.settings import Settings


logger = logging.getLogger(__name__)


# Hand-curated map: resolver entity_type → MCP tools the agent should consider
# next. Each entry lists tools in priority order (most-specific first).
_SUGGEST_TOOLS: dict[str, tuple[str, ...]] = {
    "product": ("crm_master_products_get", "crm_master_products_list", "crm_inventory_stock_balance_list", "crm_incoming_stock_by_product"),
    "customer_order": ("crm_order_management_orders_get", "crm_order_management_orders_list"),
    "customer": ("crm_master_customers_get", "crm_order_management_orders_list"),
    "inbound_shipment": ("crm_incoming_stock_shipments", "crm_incoming_stock_shipment_products"),
    "grn": ("crm_incoming_stock_grn",),
    "warehouse": ("crm_inventory_warehouses_get", "crm_inventory_stock_balance_list"),
    "supplier": ("crm_incoming_stock_shipments",),
    "promotion": ("crm_marketing_promotions_get", "crm_marketing_promotion_products_list"),
    "transporter": ("crm_order_management_orders_list",),
    "form": ("crm_forms_management_forms_get",),
    "attachment": ("crm_resource_attachments_get", "crm_master_product_attachments_by_product"),
    "spo_allocation": ("crm_incoming_stock_grn",),
}


_DISCOVERY_FIND_SPEC = ToolSpec(
    name="crm_find_entity",
    description=(
        "DATA RESOLUTION — call FIRST whenever the user mentions a product, order, "
        "customer, promotion, shipment, GRN, warehouse, supplier, transporter, "
        "form, or attachment by code, name, or descriptive phrase (NOT UUID). "
        "Returns canonical UUIDs the agent should paste into the matching domain "
        "tool's `<entity>_ids` / `<entity>_id` parameter.\n\n"
        "TWO MODES:\n"
        "  • `match_mode=or` (default) — each token resolves independently. Use when "
        "you have ONE reference (e.g. 'TT440'). Returns per-token candidates + "
        "`ambiguous` flag when a single token has >1 match.\n"
        "  • `match_mode=and` — cross-token intersection. Use when the user names "
        "MULTIPLE attributes for the SAME entity (e.g. 'cabana filter tap promo' = "
        "promotion / attachment containing BOTH 'cabana' AND 'filter tap'). Pass each "
        "attribute as a separate token in `query` (one comma-separated string per "
        "attribute, or repeated arg). AND-mode runs a single SQL per entity type "
        "with all tokens AND'd across the entity's concatenated searchable columns. "
        "Skips code-only entities (SPO / GRN / inbound shipment).\n\n"
        "Examples:\n"
        "  • or:  'TT440' → product UUID(s)\n"
        "  • or:  'fira ventures' → customer UUID\n"
        "  • or:  'gt delivery' → transporter UUID\n"
        "  • and: ['cabana', 'filter tap'] → attachments named CABANA FILTER TAP PROMO\n"
        "  • and: ['sorento', 'kitchen sink'] → kitchen-sink promotions branded sorento\n\n"
        "ALLOWED_ENTITY_TYPES (set filter, cross product):\n"
        "  `allowed_entity_types` is ALWAYS a whitelist — every token is resolved "
        "against EVERY supplied type. There is no positional 1:1 pairing.\n"
        "  • tokens=['Sorento water closet','latest promo'], allowed_entity_types=['product','promotion']\n"
        "    → BOTH tokens are probed against BOTH product and promotion.\n"
        "  If you need strict 1:1 pairing (token[i] only against type[i]), issue "
        "one call per (token, type) pair.\n\n"
        "Response shape (or mode):\n"
        "  candidates: [{type, id, code, label, match_field, display}]\n"
        "  ambiguous: true when ANY token has >1 candidate (ask user to pick)\n"
        "  unresolved: tokens with zero matches (tell user 'no record')\n\n"
        "Response shape (and mode):\n"
        "  intersection: [{type, id, code, label, match_field, display, ...}]\n"
        "  by_entity_type: {<type>: [...]}  — grouped for filtering UX\n"
        "  empty: true when no row contains every token\n\n"
        "DO NOT call this when the user already provided a UUID — call the domain "
        "tool directly with `<entity>_ids=<uuid>`."
    ),
    path="/api/v1/system/references/resolve",
    path_params=(),
    query_params=("query", "hint_types", "match_mode"),
    method="GET",
    external=True,
    domain="discovery",
    related_tools=("crm_master_products_list", "crm_order_management_orders_list", "crm_marketing_promotions_list"),
)


def _build_label(ent: dict[str, Any]) -> str:
    display = ent.get("display") or {}
    for key in (
        "product_name", "customer_name", "debtor_name", "name", "supplier_name",
        "filename", "shipment_number", "grn_number", "spo_number", "description",
        "warehouse_name", "form_name",
    ):
        val = display.get(key)
        if val:
            return str(val)
    return str(ent.get("canonical_code") or "")


def _suggest_tools_for(candidates: list[dict[str, Any]]) -> dict[str, list[str]]:
    seen_types: set[str] = set()
    out: dict[str, list[str]] = {}
    for c in candidates:
        t = c.get("type")
        if not t or t in seen_types:
            continue
        seen_types.add(t)
        tools = _SUGGEST_TOOLS.get(t)
        if tools:
            out[t] = list(tools)
    return out


def register_discovery_tools(mcp, settings: Settings, catalog: tuple[ToolSpec, ...]) -> None:
    """Register `crm_find_entity` against the FastMCP app.

    Mirrors the user_guides.py registration pattern — bypasses _compile_tool so we
    can shape the response on the MCP side rather than relying on the HTTP-tool
    template.
    """

    async def crm_find_entity(
        query: str,
        hint_types: Optional[list[str]] = None,
        match_mode: str = "or",
        tokens: Optional[list[str]] = None,
        allowed_entity_types: Optional[list[str]] = None,
    ) -> str:
        """Resolve free-text entity references to canonical UUIDs.

        See tool description for full semantics. `match_mode=and` requires explicit
        `tokens` — pass each attribute as a separate token; we fall back to
        splitting `query` on commas when no tokens are supplied.

        Positional pairing: pass `allowed_entity_types` with the SAME length as
        `tokens` to pin each token to a single entity type. Example:
            tokens=["Fira Ventures", "DO"],
            allowed_entity_types=["customer", "delivery_order"]
        → "Fira Ventures" is searched ONLY as a customer; "DO" ONLY as a
        delivery_order. Different lengths fall back to the legacy global filter.
        """
        mode = (match_mode or "or").strip().lower()
        if mode not in {"or", "and"}:
            return json.dumps({
                "status": "error",
                "error": {"message": f"match_mode must be 'or' or 'and', got {match_mode!r}"},
                "provenance": {"tool": "crm_find_entity", "source_route": _DISCOVERY_FIND_SPEC.path},
            })
        prepared_tokens: list[str] = []
        if tokens:
            prepared_tokens = [t.strip() for t in tokens if t and t.strip()]
        elif mode == "and" and query:
            # Best-effort token split on commas when caller passed a string but
            # asked for AND. Multi-word phrases should ideally arrive as a list.
            prepared_tokens = [t.strip() for t in query.split(",") if t.strip()]

        prepared_types: list[str] = (
            [t.strip() for t in allowed_entity_types if t and t.strip()]
            if allowed_entity_types
            else []
        )

        client = CRMClient(settings)
        try:
            req_query: dict[str, Any] = {"match_mode": mode}
            if prepared_tokens:
                req_query["tokens"] = prepared_tokens
            else:
                req_query["query"] = query
            if prepared_types:
                req_query["allowed_entity_types"] = prepared_types
            body = await client.get(
                "/api/v1/system/references/resolve",
                query=req_query,
                tool_name="crm_find_entity",
            )
        except Exception as exc:
            logger.exception("crm_find_entity: backend resolve failed for query=%s", query)
            return json.dumps({
                "status": "error",
                "error": {"message": f"backend resolver failed: {exc}"},
                "provenance": {"tool": "crm_find_entity", "source_route": _DISCOVERY_FIND_SPEC.path},
            })
        finally:
            await client.aclose()

        try:
            resolver = json.loads(body) if isinstance(body, (str, bytes, bytearray)) else body
        except json.JSONDecodeError:
            logger.warning("crm_find_entity: backend returned non-JSON: %r", body[:200] if body else b"")
            return json.dumps({
                "status": "error",
                "error": {"message": "backend resolver returned non-JSON"},
                "provenance": {"tool": "crm_find_entity", "source_route": _DISCOVERY_FIND_SPEC.path},
            })

        hint_set = set(hint_types or [])
        is_and_mode = resolver.get("match_mode") == "and" or mode == "and"
        candidates: list[dict[str, Any]] = []
        unresolved: list[str] = []
        ambiguous = False

        if is_and_mode:
            for m in resolver.get("intersection", []) or []:
                etype = m.get("entity_type")
                if hint_set and etype not in hint_set:
                    continue
                candidates.append({
                    "type": etype,
                    "id": m.get("uuid"),
                    "code": m.get("canonical_code"),
                    "label": _build_label(m),
                    "match_field": m.get("match_field"),
                    "match_tier": m.get("match_tier"),
                    "display": m.get("display"),
                })
            unresolved = list(resolver.get("unresolved_tokens") or [])
            # AND-mode: multiple intersection hits IS legitimate (different access
            # levels of same promo etc.) but agent should still narrow before
            # acting. Mark ambiguous when >1 hit AND the agent has not supplied
            # `hint_types` to narrow further.
            ambiguous = len(candidates) > 1
        else:
            unresolved = list(resolver.get("unresolved_tokens") or [])
            for token_res in resolver.get("resolutions", []) or []:
                matches = token_res.get("matches") or []
                if not matches:
                    continue
                if token_res.get("ambiguous"):
                    ambiguous = True
                for m in matches:
                    etype = m.get("entity_type")
                    if hint_set and etype not in hint_set:
                        continue
                    candidates.append({
                        "type": etype,
                        "id": m.get("uuid"),
                        "code": m.get("canonical_code"),
                        "label": _build_label(m),
                        "match_field": m.get("match_field"),
                        "match_tier": m.get("match_tier"),
                        "similarity": m.get("similarity"),
                        "display": m.get("display"),
                    })

        suggested = _suggest_tools_for(candidates)

        envelope_on = settings.mcp_response_envelope == "v2"
        if not envelope_on:
            payload: dict[str, Any] = {
                "match_mode": mode,
                "candidates": candidates,
                "ambiguous": ambiguous,
                "unresolved": unresolved,
                "suggested_tools": suggested,
            }
            if is_and_mode:
                payload["by_entity_type"] = resolver.get("by_entity_type") or {}
                payload["empty"] = resolver.get("empty", not candidates)
            return json.dumps(payload)

        if not candidates and not unresolved:
            status = "not_found"
        elif ambiguous:
            status = "needs_clarification"
        else:
            status = "ok"
        envelope: dict[str, Any] = {
            "status": status,
            "provenance": {
                "tool": "crm_find_entity",
                "source_route": _DISCOVERY_FIND_SPEC.path,
                "elapsed_ms": resolver.get("elapsed_ms"),
                "match_mode": mode,
            },
        }
        if status == "ok":
            envelope["data"] = {
                "candidates": candidates,
                "unresolved": unresolved,
                "suggested_tools": suggested,
            }
            if is_and_mode:
                envelope["data"]["by_entity_type"] = resolver.get("by_entity_type") or {}
        elif status == "needs_clarification":
            envelope["questions"] = [{
                "code": "ambiguous_entity",
                "message": "Multiple candidates matched; please pick one.",
                "candidates": [{"label": c["label"], "value": c["id"], "type": c["type"]} for c in candidates if c.get("id")],
            }]
            envelope["data"] = {
                "candidates": candidates,
                "unresolved": unresolved,
                "suggested_tools": suggested,
            }
            if is_and_mode:
                envelope["data"]["by_entity_type"] = resolver.get("by_entity_type") or {}
        else:  # not_found
            envelope["data"] = {"candidates": [], "unresolved": unresolved, "suggested_tools": {}}
        return json.dumps(envelope)

    mcp.add_tool(
        crm_find_entity,
        name=_DISCOVERY_FIND_SPEC.name,
        description=_DISCOVERY_FIND_SPEC.description,
    )
    logger.debug("Registered discovery tool crm_find_entity")
