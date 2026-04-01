"""FastMCP server (streamable HTTP) with catalog-registered read-only tools."""
from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from sorento_crm_mcp.catalog import CATALOG, ToolSpec
from sorento_crm_mcp.http_client import CRMClient
from sorento_crm_mcp.settings import Settings

logger = logging.getLogger(__name__)


def _compile_tool(spec: ToolSpec):
    """Build async (ctx, ...) -> str for one catalog entry; Context carries CRMClient from lifespan."""
    pp_sig = ", ".join(f"{p}: str" for p in spec.path_params)
    qp_sig = ", ".join(f"{q}: str | None = None" for q in spec.query_params)
    if pp_sig and qp_sig:
        sig = f"{pp_sig}, {qp_sig}"
    elif pp_sig:
        sig = pp_sig
    elif qp_sig:
        sig = qp_sig
    else:
        sig = ""

    pp_dict = "{" + ", ".join(f'"{p}": {p}' for p in spec.path_params) + "}"
    q_dict = "{" + ", ".join(f'"{q}": {q}' for q in spec.query_params) + "}"

    fname = f"_impl_{spec.name}"
    code = (
        f"async def {fname}(ctx: Context, {sig}):\n"
        f"    client = ctx.request_context.lifespan_context['client']\n"
        f"    _pp = {pp_dict}\n"
        f"    _qq = {q_dict}\n"
        f"    q = {{k: v for k, v in _qq.items() if v is not None}}\n"
        f"    return await client.get({spec.path!r}, path_params=_pp, query=q)\n"
    )
    ns: dict[str, Any] = {"Context": Context}
    exec(code, ns)  # noqa: S102 — catalog-only templates
    return ns[fname]


def create_mcp_app(settings: Settings) -> FastMCP:
    @asynccontextmanager
    async def lifespan(_app: FastMCP) -> AsyncIterator[dict[str, Any]]:
        c = CRMClient(settings)
        try:
            yield {"client": c}
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

    for spec in CATALOG:
        impl = _compile_tool(spec)
        mcp.add_tool(impl, name=spec.name, description=spec.description)
        logger.debug("Registered MCP tool %s", spec.name)

    return mcp
