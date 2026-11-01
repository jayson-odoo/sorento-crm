"""Default-deny company scope for catalog tools (SEC-MCP-AUTH, 16 Oct 2026).

The backend resolves an X-API-Key call with no `contact_id` + `space_id` to EVERY company
(`sorento_crm_backend/app/services/company_scope_resolver.py::_resolve_api_key_scope`), and with
both present through `resolve_contact_company_scope`, which is fail-closed. So the one decision
left to this server is whether to ask at all: a tool that declares the pair is company-scoped, and
a call to it without both values is refused here, before any backend request.

The in-app staff AI assistant has no contact and opts out explicitly with `X-MCP-Scope: staff`
(set by the backend's `MCPRuntimeClient(staff=True)`, only at the assistant's own call sites). The
header only matters on an authenticated request, and a caller holding the token already holds the
key that reads every company, so the opt-out grants nothing new.

AGENTIC-UNIFY PR 1: a staff-marked read runs as the staff member, not the key's act-as user. The
assistant names them in `X-MCP-Staff-User`, a staff-marked read without that id is refused, and
`CRMClient.request` forwards the id to the CRM as `X-Staff-User` (`forwarded_staff_id`).
"""
from __future__ import annotations

import json
import logging
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Iterator

logger = logging.getLogger(__name__)

SCOPE_PARAMS = ("contact_id", "space_id")
STAFF_HEADER = "x-mcp-scope"
STAFF_VALUE = "staff"
# The staff user the assistant is answering. A staff-marked read needs it, and it reaches the CRM
# as CRM_STAFF_HEADER (`forwarded_staff_id`).
STAFF_USER_HEADER = "x-mcp-staff-user"
CRM_STAFF_HEADER = "X-Staff-User"

# True while a compiled catalog READ tool is talking to the CRM. Everything else leaves it False, so
# a hand-written tool (the writes in `record_actions.py`, `ideation.py`) never carries the identity.
_serving_read_tool: ContextVar[bool] = ContextVar("serving_read_tool", default=False)


def is_scoped(spec: Any) -> bool:
    declared = set(spec.query_params) | set(spec.body_params)
    return all(p in declared for p in SCOPE_PARAMS)


def _request_headers(ctx: Any) -> Any:
    request = getattr(getattr(ctx, "request_context", None), "request", None)
    return getattr(request, "headers", None)


def is_staff_request(ctx: Any) -> bool:
    headers = _request_headers(ctx)
    if headers is None:
        return False
    return str(headers.get(STAFF_HEADER) or "").strip().lower() == STAFF_VALUE


def _staff_user_id(headers: Any) -> str:
    return str(headers.get(STAFF_USER_HEADER) or "").strip() if headers is not None else ""


@contextmanager
def serving_tool(spec: Any) -> Iterator[None]:
    """Around one compiled tool's CRM calls: says whether the tool is a read, by the same catalog
    rule as the staff opt-out, so `CRMClient.request` need not guess it from the HTTP method."""
    token = _serving_read_tool.set(staff_may_skip(spec))
    try:
        yield
    finally:
        _serving_read_tool.reset(token)


def forwarded_staff_id() -> str | None:
    """The id `CRMClient.request` sends as `X-Staff-User`, or None.

    Read from the library's request contextvar, so a helper with no `ctx`, however deep in the
    tool, is covered. Only the assistant's `X-MCP-Staff-User`, only beside `X-MCP-Scope: staff`,
    only during a read tool. An inbound `X-Staff-User` is never looked at, and `auth.py` has already
    stripped the two `x-mcp-*` headers from a caller that did not prove it holds the token."""
    if not _serving_read_tool.get():
        return None
    # Imported here: the backend imports this module through `http_client` without the `mcp` package.
    from mcp.server.lowlevel.server import request_ctx

    headers = getattr(getattr(request_ctx.get(None), "request", None), "headers", None)
    if headers is None or str(headers.get(STAFF_HEADER) or "").strip().lower() != STAFF_VALUE:
        return None
    return _staff_user_id(headers) or None


def _present(value: Any) -> bool:
    """A scope id counts only as one non-blank scalar. A list (`[""]`, `["x", ""]`) is refused:
    httpx sends every element and the backend reads the LAST one, so a blank tail would
    resolve to every company."""
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        return False
    return bool(str(value).strip())


def _missing_scope(query: dict[str, Any] | None, body: Any) -> list[str]:
    sources = [query or {}]
    if isinstance(body, dict):
        sources.append(body)
    return [p for p in SCOPE_PARAMS if not any(_present(src.get(p)) for src in sources)]


def check_scope(spec: Any, query: dict[str, Any] | None, body: Any, ctx: Any) -> str | None:
    """The one scope check every catalog tool call runs (`server._compile_tool`).

    Returns the refusal to answer with, or None to go ahead. A staff-marked read of any tool with no
    staff id is refused: it could only run as the key's act-as user.
    A staff opt-out that skipped a contact refusal is logged (tool, staff user id)."""
    staff = is_staff_request(ctx)
    if staff and staff_may_skip(spec):
        staff_user = _staff_user_id(_request_headers(ctx))
        if not staff_user:
            return json.dumps(
                {
                    "error": "scope_required",
                    "detail": f"Tool '{spec.name}' reads as the staff member and needs their id.",
                    "missing": [STAFF_USER_HEADER],
                    "data": [],
                    "total": 0,
                }
            )
        if is_scoped(spec) and _missing_scope(query, body):
            logger.info(
                "staff-scope MCP call without a contact: tool=%s staff_user=%s",
                spec.name,
                staff_user[:64],
            )
    return scope_refusal(spec, query, body, staff=staff)


def required_missing(spec: Any, required: Any, query: dict[str, Any], ctx: Any) -> list[str]:
    """The required query parameters a call left blank. A staff-marked read the opt-out allows is not held
    to the contact pair (`SCOPE_PARAMS`): `check_scope` answers for it, with `scope_required` when the
    staff id is missing. Every other caller, and a scoped write, keeps the plain check."""
    missing = [k for k in required if query.get(k) in (None, "")]
    if missing and is_staff_request(ctx) and staff_may_skip(spec):
        return [k for k in missing if k not in SCOPE_PARAMS]
    return missing


def staff_may_skip(spec: Any) -> bool:
    """The staff opt-out covers reads only: a GET, or a POST the catalog marks `read_only`.
    A scoped write (`crm_sales_opportunity_log`) still needs the contact, even from staff."""
    return spec.method == "GET" or bool(getattr(spec, "read_only", False))


def scope_refusal(spec: Any, query: dict[str, Any] | None, body: Any, *, staff: bool) -> str | None:
    """The refusal to return instead of calling the backend, or None to go ahead."""
    if (staff and staff_may_skip(spec)) or not is_scoped(spec):
        return None
    missing = _missing_scope(query, body)
    if not missing:
        return None
    return json.dumps(
        {
            "error": "scope_required",
            "detail": (
                f"Tool '{spec.name}' reads company-owned data and needs the calling contact: "
                "pass contact_id and space_id."
            ),
            "missing": missing,
            "data": [],
            "total": 0,
        }
    )
