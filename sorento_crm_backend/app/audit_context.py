"""Request-scoped audit context (user_id, ip_address) for automatic audit logging."""
import contextvars
from typing import Optional

_audit_context: contextvars.ContextVar[tuple[Optional[str], Optional[str]]] = contextvars.ContextVar(
    "audit_context",
    default=(None, None),
)


def set_audit_context(user_id: Optional[str], ip_address: Optional[str]) -> None:
    """Set the current request's audit context. Call from auth dependency or middleware."""
    _audit_context.set((user_id, ip_address))


def get_audit_context() -> tuple[Optional[str], Optional[str]]:
    """Return (user_id, ip_address) for the current request. Used by audit event listener."""
    return _audit_context.get()
