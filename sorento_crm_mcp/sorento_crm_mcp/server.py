"""FastMCP server (streamable HTTP) with catalog-registered read-only tools."""
from __future__ import annotations

import logging
import json
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date, datetime
from typing import Any

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from sorento_crm_mcp.access_guard import check_access, deny_payload
from sorento_crm_mcp.catalog import CATALOG, ToolSpec
from sorento_crm_mcp.http_client import CRMClient
from sorento_crm_mcp.module_loader import merged_catalog
from sorento_crm_mcp.settings import Settings

logger = logging.getLogger(__name__)

TOOL_QUERY_ALIASES: dict[str, dict[str, tuple[str, ...]]] = {
    # Normalize frequent caller habit: sending `query` instead of `q`.
    "crm_workflow_forms_definitions_list": {"q": ("query",)},
}

TOOL_REQUIRED_QUERY_HINTS: dict[str, tuple[str, ...]] = {
    # Forms scope requirements for external API key flows.
    "crm_forms_stock_inquiries_list": ("contact_id", "space_id"),
    "crm_forms_stock_inquiries_get": ("contact_id", "space_id"),
    "crm_forms_purchase_requests_list": ("contact_id", "space_id"),
    "crm_forms_purchase_requests_get": ("contact_id", "space_id"),
    "crm_forms_management_forms_get": ("contact_id", "space_id"),
}

TOOL_DEFAULT_QUERY_PARAMS: dict[str, dict[str, str]] = {
    # Promotion list must always return active promotions only.
    "crm_marketing_promotions_list": {"status": "active"},
    # Orders list (DO discovery) should surface the latest order first by default.
    # UI grid passes its own sort/dir, so this only affects MCP/agent calls that omit them.
    "crm_order_management_orders_list": {"sort": "order_date", "dir": "desc"},
}

PROMOTION_TOOL_NAMES: set[str] = {
    "crm_marketing_promotions_list",
    "crm_marketing_promotions_get",
    "crm_marketing_promotion_products_nested",
    "crm_marketing_promotion_products_list",
    "crm_marketing_promotion_attachments_list",
    "crm_marketing_promotion_attachments_get",
    "crm_marketing_promotion_attachments_by_promotion",
}

UUID_REGEX = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$"
)

_INCOMING_SHIPMENT_DETAIL_TOOLS: set[str] = {
    "crm_incoming_stock_shipment_products",
    "crm_incoming_stock_shipment_attachment",
}


def _normalize_query_value(value: str | None) -> str | None:
    if value is None:
        return None
    if value in {"True", "False"}:
        return value.lower()
    return value


def _looks_like_uuid(value: str | None) -> bool:
    if not value:
        return False
    return UUID_REGEX.match(value) is not None


def _list_spec_by_path(path: str) -> ToolSpec | None:
    for s in CATALOG:
        if s.path == path:
            return s
    return None


def _json_loads_safe(payload: str) -> Any:
    try:
        return json.loads(payload)
    except Exception:
        return None


def _parse_iso_date(value: str | None) -> date | None:
    if not value:
        return None
    s = value.strip()
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        pass
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _extract_incoming_rows(raw: str) -> list[dict[str, Any]]:
    data = _json_loads_safe(raw)
    if not isinstance(data, dict):
        return []
    rows = data.get("data")
    if not isinstance(rows, list):
        return []
    return [r for r in rows if isinstance(r, dict)]


def _shipment_row_ref(row: dict[str, Any]) -> str | None:
    shipment_number = row.get("shipment_number")
    if isinstance(shipment_number, str) and shipment_number.strip():
        return shipment_number.strip()
    return None


def _match_incoming_shipment_candidates(rows: list[dict[str, Any]], identifier: str) -> list[dict[str, Any]]:
    key = identifier.strip().lower()
    if not key:
        return []

    eta = _parse_iso_date(identifier)
    if eta is not None:
        eta_str = eta.isoformat()
        eta_matches = []
        for row in rows:
            eta_val = row.get("estimated_arrival_date")
            if isinstance(eta_val, str) and eta_val.startswith(eta_str):
                eta_matches.append(row)
        if eta_matches:
            return eta_matches

    exact_matches = []
    partial_matches = []
    for row in rows:
        fields = [
            row.get("shipment_number"),
            row.get("shipping_container_number"),
        ]
        normalized = [f.strip().lower() for f in fields if isinstance(f, str) and f.strip()]
        if key in normalized:
            exact_matches.append(row)
            continue
        if any(key in f for f in normalized):
            partial_matches.append(row)
    if exact_matches:
        return exact_matches
    return partial_matches


async def _resolve_incoming_shipment_reference(client: Any, identifier: str) -> str | None:
    candidate = identifier.strip()
    if not candidate:
        return None

    list_raw = await client.get(
        "/api/v1/incoming-stock/shipments",
        path_params={},
        query={"query": candidate, "page": "1", "limit": "20"},
        tool_name="crm_incoming_stock_shipments",
    )
    rows = _extract_incoming_rows(list_raw)
    matches = _match_incoming_shipment_candidates(rows, candidate)
    if len(matches) == 1:
        return _shipment_row_ref(matches[0])
    if len(matches) > 1:
        return None

    parsed_eta = _parse_iso_date(candidate)
    if parsed_eta is None:
        return None

    eta_raw = await client.get(
        "/api/v1/incoming-stock/shipments",
        path_params={},
        query={
            "eta_from": parsed_eta.isoformat(),
            "eta_to": parsed_eta.isoformat(),
            "page": "1",
            "limit": "20",
        },
        tool_name="crm_incoming_stock_shipments",
    )
    eta_rows = _extract_incoming_rows(eta_raw)
    if len(eta_rows) == 1:
        return _shipment_row_ref(eta_rows[0])
    return None


def _is_active_promotion_obj(obj: Any) -> bool:
    if not isinstance(obj, dict):
        return False
    if isinstance(obj.get("is_active"), bool):
        return obj["is_active"]
    status = obj.get("status")
    if isinstance(status, str):
        return status.strip().lower() == "active"
    return False


async def _ensure_promotion_active(client: Any, promotion_id: str | None) -> str | None:
    if not promotion_id:
        return None
    try:
        raw = await client.get(f"/api/v1/marketing/promotions/{promotion_id}", path_params={}, query={})
    except Exception:
        return None
    data = _json_loads_safe(raw)
    if isinstance(data, dict) and not _is_active_promotion_obj(data):
        return json.dumps(
            {
                "message": "Promotion is inactive.",
                "code": "PROMOTION_INACTIVE",
                "promotion_id": str(promotion_id),
            }
        )
    return None


def _filter_active_promotion_records(tool_name: str, raw: str) -> str:
    if tool_name not in PROMOTION_TOOL_NAMES:
        return raw
    data = _json_loads_safe(raw)
    if data is None:
        return raw

    # Single-promotion details: block inactive promotion records.
    if tool_name == "crm_marketing_promotions_get":
        if isinstance(data, dict) and not _is_active_promotion_obj(data):
            return json.dumps({"message": "Promotion is inactive.", "code": "PROMOTION_INACTIVE"})
        return raw

    # Single linked records (e.g. promotion attachment get): block if linked promotion inactive.
    if isinstance(data, dict) and isinstance(data.get("promotion"), dict):
        if not _is_active_promotion_obj(data.get("promotion")):
            return json.dumps({"message": "Promotion is inactive.", "code": "PROMOTION_INACTIVE"})
        return raw

    # List-like responses: keep only rows with active promotion context.
    if isinstance(data, dict) and isinstance(data.get("data"), list):
        rows = data["data"]
        filtered = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            if _is_active_promotion_obj(row):
                filtered.append(row)
                continue
            promotion = row.get("promotion")
            if _is_active_promotion_obj(promotion):
                filtered.append(row)
        data["data"] = filtered
        return json.dumps(data)

    return raw


async def _execute_tool_request(spec: ToolSpec, client: Any, path_params: dict[str, Any], query: dict[str, Any]) -> str:
    # Recovery path: if a *_get tool receives non-UUID id text (e.g. "bathtubs"),
    # route to sibling list endpoint with query search instead of throwing DB UUID errors.
    for p_name, p_val in path_params.items():
        if p_name.endswith("_id") and isinstance(p_val, str) and not _looks_like_uuid(p_val):
            if spec.name in _INCOMING_SHIPMENT_DETAIL_TOOLS and p_name == "shipment_id":
                resolved_ref = await _resolve_incoming_shipment_reference(client, p_val)
                if resolved_ref:
                    path_params[p_name] = resolved_ref
                # Let backend resolver still try direct business identifiers
                # (shipment number / container / BOL / invoice) even when MCP
                # cannot resolve this input to one candidate.
                continue
            base_path = spec.path.replace(f"/{{{p_name}}}", "")
            list_spec = _list_spec_by_path(base_path)
            if list_spec:
                fallback_query: dict[str, Any] = {}
                # Preserve overlapping query filters (e.g. contact_id/space_id scope)
                # when auto-falling back from *_get(non-UUID id) to sibling list endpoint.
                for qk, qv in (query or {}).items():
                    if qk in list_spec.query_params and qv not in (None, ""):
                        fallback_query[qk] = qv
                if "query" in list_spec.query_params:
                    fallback_query["query"] = p_val
                elif "q" in list_spec.query_params:
                    fallback_query["q"] = p_val
                if "limit" in list_spec.query_params:
                    fallback_query.setdefault("limit", "10")
                if "page" in list_spec.query_params:
                    fallback_query.setdefault("page", "1")
                # If sibling list endpoint has no free-text query, still return a bounded first page
                # so callers get a useful response instead of a UUID cast failure.
                return await client.get(list_spec.path, path_params={}, query=fallback_query, tool_name=spec.name)
            return json.dumps(
                {
                    "message": f"Parameter '{p_name}' expects a UUID for tool '{spec.name}'.",
                    "suggestion": f"Use a list/search tool with query='{p_val}' to find the correct id first.",
                    "code": "INVALID_IDENTIFIER_FORMAT",
                }
            )
    if spec.name == "crm_marketing_promotions_get":
        inactive_msg = await _ensure_promotion_active(client, path_params.get("promotion_id"))
        if inactive_msg is not None:
            return inactive_msg
    elif spec.name in {
        "crm_marketing_promotion_products_nested",
        "crm_marketing_promotion_attachments_by_promotion",
    }:
        inactive_msg = await _ensure_promotion_active(client, path_params.get("promotion_id"))
        if inactive_msg is not None:
            return inactive_msg
    elif spec.name in {"crm_marketing_promotion_products_list", "crm_marketing_promotion_attachments_list"}:
        # List endpoints may be used as broad search (e.g., by SKU text). Do not hard-block
        # on promotion activity precheck here; inactive rows are filtered from response payload.
        pass

    response = await client.request(
        spec.method,
        spec.path,
        path_params=path_params,
        query=query,
        tool_name=spec.name,
    )
    return _filter_active_promotion_records(spec.name, response)


async def _execute_tool_request_with_body(
    spec: ToolSpec,
    client: Any,
    path_params: dict[str, Any],
    query: dict[str, Any],
    body: Any,
) -> str:
    if spec.method.upper() == "GET":
        return await _execute_tool_request(spec, client, path_params, query)
    return await client.request(
        spec.method,
        spec.path,
        path_params=path_params,
        query=query,
        body=body,
        tool_name=spec.name,
    )


_GUARD_PARAM_NAMES = ("contact_id", "space_id")


def _compile_tool(spec: ToolSpec):
    """Build async (ctx, ...) -> str for one catalog entry; Context carries CRMClient from lifespan."""
    pp_sig = ", ".join(f"{p}: str" for p in spec.path_params)
    query_params_with_aliases = list(spec.query_params)
    aliases = TOOL_QUERY_ALIASES.get(spec.name, {})
    for _canonical, alias_names in aliases.items():
        for alias_name in alias_names:
            if alias_name not in query_params_with_aliases:
                query_params_with_aliases.append(alias_name)
    # Strip guard param names from the generated signature — they're already
    # required as guard inputs (contact_id, space_id). For tools whose backend
    # endpoint accepts them as query filters, we re-inject the guard values
    # into _qq below so the forwarded request still carries them.
    qp_for_sig = [q for q in query_params_with_aliases if q not in _GUARD_PARAM_NAMES]
    bp_for_sig = [b for b in spec.body_params if b not in _GUARD_PARAM_NAMES]
    forward_contact_id_query = "contact_id" in query_params_with_aliases
    forward_space_id_query = "space_id" in query_params_with_aliases
    forward_contact_id_body = "contact_id" in spec.body_params
    forward_space_id_body = "space_id" in spec.body_params
    qp_sig = ", ".join(f"{q}: str | None = None" for q in qp_for_sig)
    bp_sig = ", ".join(f"{b}: str" for b in bp_for_sig)
    guard_sig = "contact_id: str, space_id: str"
    if pp_sig and qp_sig:
        sig = f"{guard_sig}, {pp_sig}, {qp_sig}"
    elif pp_sig:
        sig = f"{guard_sig}, {pp_sig}"
    elif qp_sig:
        sig = f"{guard_sig}, {qp_sig}"
    else:
        sig = guard_sig
    if bp_sig:
        sig = f"{sig}, {bp_sig}"

    pp_dict = "{" + ", ".join(f'"{p}": {p}' for p in spec.path_params) + "}"
    q_dict = "{" + ", ".join(f'"{q}": {q}' for q in qp_for_sig) + "}"
    b_dict = "{" + ", ".join(f'"{b}": {b}' for b in bp_for_sig) + "}"
    aliases_repr = repr(aliases)
    required_hints = repr(TOOL_REQUIRED_QUERY_HINTS.get(spec.name, ()))
    default_q = repr(TOOL_DEFAULT_QUERY_PARAMS.get(spec.name, {}))

    fname = f"_impl_{spec.name}"
    code = (
        f"async def {fname}(ctx: Context, {sig}):\n"
        f"    client = ctx.request_context.lifespan_context['client']\n"
        f"    _settings = ctx.request_context.lifespan_context['settings']\n"
        f"    _decision = await _check_access(_spec.name, contact_id, space_id, api_url=_settings.crm_base_url, api_key=_settings.external_api_key)\n"
        f"    if not _decision.allowed:\n"
        f"        return _deny_payload(_decision)\n"
        f"    _pp = {pp_dict}\n"
        f"    _qq = {q_dict}\n"
        f"    if {forward_contact_id_query!r}: _qq['contact_id'] = contact_id\n"
        f"    if {forward_space_id_query!r}: _qq['space_id'] = space_id\n"
        f"    _bb = {b_dict}\n"
        f"    if {forward_contact_id_body!r}: _bb['contact_id'] = contact_id\n"
        f"    if {forward_space_id_body!r}: _bb['space_id'] = space_id\n"
        f"    _aliases = {aliases_repr}\n"
        f"    _required = {required_hints}\n"
        f"    _defaults = {default_q}\n"
        f"    for _canonical, _alias_names in _aliases.items():\n"
        f"        if _qq.get(_canonical) is None:\n"
        f"            for _alias in _alias_names:\n"
        f"                if _qq.get(_alias) is not None:\n"
        f"                    _qq[_canonical] = _qq[_alias]\n"
        f"                    break\n"
        f"    for _k, _v in list(_qq.items()):\n"
        f"        _qq[_k] = _normalize_query_value(_v)\n"
        f"    q = {{k: v for k, v in _qq.items() if v is not None}}\n"
        f"    for _dk, _dv in _defaults.items():\n"
        f"        if q.get(_dk) in (None, ''):\n"
        f"            q[_dk] = _dv\n"
        f"    body = None\n"
        f"    if _bb:\n"
        f"        _decoded = {{}}\n"
        f"        for _bk, _bv in _bb.items():\n"
        f"            if _bv is None:\n"
        f"                continue\n"
        f"            if not isinstance(_bv, str):\n"
        f"                _decoded[_bk] = _bv\n"
        f"                continue\n"
        f"            try:\n"
        f"                _decoded[_bk] = json.loads(_bv)\n"
        f"            except Exception:\n"
        f"                _decoded[_bk] = _bv\n"
        f"        if 'payload_json' in _decoded:\n"
        f"            _payload = _decoded.get('payload_json')\n"
        f"            if isinstance(_payload, dict):\n"
        f"                for _k, _v in _decoded.items():\n"
        f"                    if _k == 'payload_json':\n"
        f"                        continue\n"
        f"                    if _k not in _payload:\n"
        f"                        _payload[_k] = _v\n"
        f"            body = _payload\n"
        f"        else:\n"
        f"            body = _decoded\n"
        f"    _missing = [k for k in _required if q.get(k) in (None, '')]\n"
        f"    if _missing:\n"
        f"        raise ValueError('Missing required query parameter(s): ' + ', '.join(_missing))\n"
        f"    return await _execute_tool_request_with_body(_spec, client, _pp, q, body)\n"
    )
    ns: dict[str, Any] = {
        "Context": Context,
        "_normalize_query_value": _normalize_query_value,
        "_execute_tool_request": _execute_tool_request,
        "_execute_tool_request_with_body": _execute_tool_request_with_body,
        "_check_access": check_access,
        "_deny_payload": deny_payload,
        "json": json,
        "_spec": spec,
    }
    exec(code, ns)  # noqa: S102 — catalog-only templates
    return ns[fname]


def create_mcp_app(settings: Settings) -> FastMCP:
    @asynccontextmanager
    async def lifespan(_app: FastMCP) -> AsyncIterator[dict[str, Any]]:
        c = CRMClient(settings)
        try:
            yield {"client": c, "settings": settings}
        finally:
            await c.aclose()

    mcp = FastMCP(
        "Sorento CRM (read-only)",
        instructions=(
            "Read-only tools that mirror Sorento CRM GET APIs. "
            "Use pagination (page, limit). Pass filter ids and codes as strings. "
            "Combine multiple tools to answer cross-entity questions."
        ),
        host=settings.mcp_host,
        port=settings.mcp_port,
        log_level=settings.log_level.upper(),  # type: ignore[arg-type]
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
        stateless_http=True,
        lifespan=lifespan,
    )

    for spec in merged_catalog(CATALOG):
        impl = _compile_tool(spec)
        mcp.add_tool(impl, name=spec.name, description=spec.description)
        logger.debug("Registered MCP tool %s", spec.name)

    return mcp
