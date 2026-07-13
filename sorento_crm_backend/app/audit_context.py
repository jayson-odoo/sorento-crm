"""Request-scoped audit context for automatic audit logging.

Holds the *real* user id (always the JWT principal) plus the *effective* user id
(the impersonation target when active, otherwise same as real). Audit-log rows
and ``created_by_user_id`` / ``updated_by_user_id`` columns track the real user,
while authorization uses the effective user.
"""
import contextvars
from typing import Optional

_audit_context: contextvars.ContextVar[
    tuple[Optional[str], Optional[str], Optional[str]]
] = contextvars.ContextVar(
    "audit_context",
    default=(None, None, None),
)


def set_audit_context(
    user_id: Optional[str],
    ip_address: Optional[str],
    effective_user_id: Optional[str] = None,
) -> None:
    """Set the current request's audit context. ``user_id`` is the real (audit) actor.

    ``effective_user_id`` is the impersonation target when active; defaults to ``user_id``.
    """
    _audit_context.set((user_id, ip_address, effective_user_id or user_id))


def get_audit_context() -> tuple[Optional[str], Optional[str]]:
    """Return (real_user_id, ip_address). Used by the audit event listener."""
    real, ip, _eff = _audit_context.get()
    return real, ip


def get_real_and_effective_user_ids() -> tuple[Optional[str], Optional[str]]:
    """Return (real_user_id, effective_user_id) for the current request."""
    real, _ip, eff = _audit_context.get()
    return real, eff


# Per-request correlation id (Sub-plan D Tier-2). Kept in a SEPARATE contextvar
# so the (user, ip, effective) tuple and its callers are untouched. The
# LoggingMiddleware stamps one id per request; the audit listener copies it onto
# every AuditLog row so all changes from one request are correlatable.
_trace_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "audit_trace_id", default=None
)


def set_trace_id(trace_id: Optional[str]) -> None:
    """Set the current request's trace/correlation id."""
    _trace_id.set(trace_id)


def get_trace_id() -> Optional[str]:
    """Return the current request's trace/correlation id (None outside a request)."""
    return _trace_id.get()


# Acting contact for unauthenticated portal/public-link writes (System Health WS2a).
# Separate contextvar (like trace_id) so the (user, ip, effective) tuple is untouched.
# Portal / public-approval routes set this to the resolved respond_contacts.id; the
# audit listener stamps it onto AuditLog.contact_id so the row attributes to the
# contact by name instead of the ambiguous "System" fallback.
_actor_contact_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "audit_actor_contact_id", default=None
)


def set_actor_contact_id(contact_id: Optional[str]) -> None:
    """Set the acting contact (respond_contacts.id) for the current request."""
    _actor_contact_id.set(contact_id)


def get_actor_contact_id() -> Optional[str]:
    """Return the acting contact id for the current request (None if not a contact write)."""
    return _actor_contact_id.get()
