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
