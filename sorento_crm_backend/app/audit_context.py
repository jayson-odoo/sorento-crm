"""Request-scoped audit context for automatic audit logging (#1281 S0).

One mutable ``AuditContext`` object per request (or job run, or scheduler tick) lives in a
contextvar. ``LoggingMiddleware`` puts a fresh one there at the start of every request, and every
auth dependency MUTATES it rather than calling ``.set()``. That is the point of the object:
FastAPI runs a sync dependency (``get_current_user_or_api_key``) on a COPIED context in a
threadpool, so a ``.set()`` made there never reached the endpoint and every audited write behind
an API key recorded ``user_id = NULL``. A copied context still holds a reference to the same
object, so a mutation is visible everywhere the request runs.

It holds the *real* user id (always the authenticated principal) plus the *effective* user id
(the impersonation target when active, otherwise the same). Audit rows and ``created_by`` /
``updated_by`` columns track the real user; authorization uses the effective one.

The old function API (``set_audit_context``, ``get_audit_context``, ``set_trace_id``, ...) is
kept as thin wrappers over the object, so its callers did not change.
"""
from __future__ import annotations

import contextvars
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from typing import Iterator, Optional

# Every id column on audit_logs is String(64); an inbound header is caller-controlled.
_ID_MAX = 64

# API-key integration type -> audit source. Anything unlisted is a generic external caller.
_SOURCE_BY_INTEGRATION_TYPE = {"automation": "n8n", "mcp": "mcp"}
_CHATBOT_PATH_PREFIX = "/api/v1/external/chat/"  # not /chat-history


def _clamp(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    value = str(value)
    return value[:_ID_MAX] if value else None


@dataclass
class AuditContext:
    user_id: Optional[str] = None
    effective_user_id: Optional[str] = None
    ip_address: Optional[str] = None
    contact_id: Optional[str] = None
    principal_type: Optional[str] = None
    principal_id: Optional[str] = None
    source: Optional[str] = None
    request_id: Optional[str] = None
    correlation_id: Optional[str] = None
    reason: Optional[str] = None
    event: Optional[str] = None
    # An inbound X-Correlation-Id, held aside: it becomes correlation_id only once an
    # integration key authenticates (MCP and n8n are the real producers), so an ordinary
    # caller cannot stitch its writes into someone else's business action.
    inbound_correlation_id: Optional[str] = field(default=None, repr=False)
    # (entity_type, entity_id) pairs the flush listener wrote while ``event`` was set, so the
    # ``@audit_event`` decorator can tell which ids got no row. Not carried into jobs.
    event_hits: set = field(default_factory=set, repr=False)

    @property
    def on_behalf_of_user_id(self) -> Optional[str]:
        if self.effective_user_id and self.effective_user_id != self.user_id:
            return self.effective_user_id
        return None


_ctx: contextvars.ContextVar[Optional[AuditContext]] = contextvars.ContextVar(
    "audit_context", default=None
)


def current_audit_context() -> Optional[AuditContext]:
    """The context of the current request / job / tick, or None outside all of them."""
    return _ctx.get()


def _ensure() -> AuditContext:
    ctx = _ctx.get()
    if ctx is None:
        # Outside a request (a script, a test, a thread with no inherited context). A
        # ``.set()`` here only reaches this context, which is exactly the scope that asked.
        ctx = AuditContext()
        _ctx.set(ctx)
    return ctx


@contextmanager
def audit_context_scope(**fields) -> Iterator[AuditContext]:
    """Run the block under a fresh ``AuditContext``; the previous one comes back after."""
    for key in ("request_id", "correlation_id"):
        if key in fields:
            fields[key] = _clamp(fields[key])
    token = _ctx.set(AuditContext(**fields))
    try:
        yield _ctx.get()
    finally:
        _ctx.reset(token)


def start_request_context(
    ip_address: Optional[str], request_id: str, correlation_id: Optional[str] = None
) -> AuditContext:
    """Called once per request by ``LoggingMiddleware``: a fresh object, never a shared one.

    ``correlation_id`` is the caller's X-Correlation-Id; it is trusted only after an API key
    authenticates (``set_api_key_principal``). Until then the correlation id is the request id.
    """
    request_id = _clamp(request_id)
    ctx = AuditContext(
        ip_address=ip_address,
        request_id=request_id,
        correlation_id=request_id,
        inbound_correlation_id=_clamp(correlation_id),
    )
    _ctx.set(ctx)
    return ctx


def set_audit_context(
    user_id: Optional[str],
    ip_address: Optional[str],
    effective_user_id: Optional[str] = None,
) -> None:
    """Record the authenticated staff user. ``user_id`` is the real (audit) actor.

    ``effective_user_id`` is the impersonation target when active; defaults to ``user_id``.
    """
    ctx = _ensure()
    ctx.user_id = user_id
    ctx.ip_address = ip_address
    ctx.effective_user_id = effective_user_id or user_id
    if user_id:
        # A job or tick that names a user keeps its own principal: the worker still did it.
        if ctx.principal_type not in ("api_key", "worker", "scheduler"):
            ctx.principal_type = "user"
            ctx.principal_id = str(user_id)
            ctx.source = ctx.source or "ui"
    elif ctx.principal_type in ("user", "api_key"):
        ctx.principal_type = ctx.principal_id = ctx.source = None


def set_api_key_principal(
    integration_id: Optional[str], integration_type: Optional[str], path: Optional[str] = None
) -> None:
    """Record that an integration key authenticated. Source is derived here, never taken from
    the caller's ``X-Source`` header."""
    ctx = _ensure()
    ctx.principal_type = "api_key"
    ctx.principal_id = str(integration_id) if integration_id else None
    if ctx.inbound_correlation_id:
        ctx.correlation_id = ctx.inbound_correlation_id
    if path and path.startswith(_CHATBOT_PATH_PREFIX):
        ctx.source = "chatbot"
    else:
        ctx.source = _SOURCE_BY_INTEGRATION_TYPE.get(integration_type or "", "external_api")


def get_audit_context() -> tuple[Optional[str], Optional[str]]:
    """Return (real_user_id, ip_address). Used by the audit event listener."""
    ctx = _ctx.get()
    return (ctx.user_id, ctx.ip_address) if ctx else (None, None)


def get_real_and_effective_user_ids() -> tuple[Optional[str], Optional[str]]:
    """Return (real_user_id, effective_user_id) for the current request."""
    ctx = _ctx.get()
    return (ctx.user_id, ctx.effective_user_id) if ctx else (None, None)


def set_trace_id(trace_id: Optional[str]) -> None:
    """Set the current request id (``audit_logs.trace_id``), clamped to the column width."""
    _ensure().request_id = _clamp(trace_id)


def get_trace_id() -> Optional[str]:
    """Return the current request id (None outside a request)."""
    ctx = _ctx.get()
    return ctx.request_id if ctx else None


def set_actor_contact_id(contact_id: Optional[str]) -> None:
    """Set the acting portal contact (respond_contacts.id) for the current request.

    A contact is the principal only when no staff user authenticated: an admin impersonating a
    contact in the portal stays the principal (``contact_impersonation.py``).
    """
    ctx = _ensure()
    ctx.contact_id = contact_id
    if contact_id:
        ctx.source = "portal"
        if not ctx.user_id:
            ctx.principal_type = "contact"
            ctx.principal_id = str(contact_id)
    elif ctx.principal_type == "contact":
        ctx.principal_type = ctx.principal_id = None
        ctx.source = None


def get_actor_contact_id() -> Optional[str]:
    """Return the acting contact id for the current request (None if not a contact write)."""
    ctx = _ctx.get()
    return ctx.contact_id if ctx else None


# --- Jobs -------------------------------------------------------------------------

_JOB_FIELDS = ("user_id", "effective_user_id", "contact_id", "correlation_id", "request_id")


def snapshot_for_job() -> dict:
    """What an enqueued job inherits from the request that queued it."""
    ctx = _ctx.get()
    if ctx is None:
        return {}
    data = asdict(ctx)
    return {k: data[k] for k in _JOB_FIELDS if data.get(k) is not None}


@contextmanager
def restore_from_job_meta(meta: Optional[dict], queue_name: str, job_id: str) -> Iterator[AuditContext]:
    """Run a job under the context its request stamped into ``job.meta``.

    The person and the business action carry over (user, on-behalf-of, contact, correlation
    id); the principal becomes the worker, the request id becomes the job id.
    """
    data = (meta or {}).get("audit_context") or {}
    job_id = _clamp(job_id)
    with audit_context_scope(
        user_id=data.get("user_id"),
        effective_user_id=data.get("effective_user_id") or data.get("user_id"),
        contact_id=data.get("contact_id"),
        principal_type="worker",
        principal_id=queue_name,
        source="import" if queue_name == "imports" else "worker",
        request_id=job_id,
        correlation_id=data.get("correlation_id") or job_id,
    ) as ctx:
        yield ctx
