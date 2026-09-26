"""Request-, job- and tick-scoped audit actor for automatic audit logging.

One ``AuditActor`` says who did a write (identity S0, #1280; plan section 8):

- ``user_id`` is the EFFECTIVE actor (the impersonation target when an admin is
  impersonating), ``real_user_id`` is who was at the keyboard. They differ only
  under impersonation; ``created_by`` / ``updated_by`` columns keep the effective
  user and ``real_user_id`` records the admin (plan 8.2).
- ``actor_type`` is user | contact | integration | worker | scheduler |
  public_link | system.

Carriers. ``stamp_actor`` writes the actor to three places at once:

- the contextvar, for code on the same context (async dependencies, the path op,
  an RQ job run in-process, a scheduler tick);
- ``db.info["audit_actor"]``, which lives on the Session object and so survives
  FastAPI running a sync dependency in a different threadpool thread from the
  path op and the flush (the AC-12 gap);
- ``request.state.audit_actor``, read by the API call log middleware.

``get_actor(db)`` prefers ``db.info`` over the contextvar.

``get_audit_context`` is the one older reader kept, for its service callers.
"""
from __future__ import annotations

import contextvars
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterator, Optional

ACTOR_TYPES = ("user", "contact", "integration", "worker", "scheduler", "public_link", "system")

_USER_AGENT_MAX = 512
_DB_INFO_KEY = "audit_actor"


@dataclass
class AuditActor:
    actor_type: str  # user | contact | integration | worker | scheduler | public_link | system
    user_id: Optional[str] = None  # effective actor
    real_user_id: Optional[str] = None  # at the keyboard; equals user_id unless impersonating
    auth_method: Optional[str] = None  # password | phone_otp | portal_link | portal_token | api_key | impersonation
    session_id: Optional[str] = None
    integration_id: Optional[str] = None
    contact_id: Optional[str] = None
    job_id: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None  # truncated to 512
    tool_name: Optional[str] = None  # MCP X-Tool-Name, written into description when the row has none

    def __post_init__(self) -> None:
        if self.user_agent is not None:
            self.user_agent = str(self.user_agent)[:_USER_AGENT_MAX] or None


_actor: contextvars.ContextVar[Optional[AuditActor]] = contextvars.ContextVar(
    "audit_actor", default=None
)


def stamp_actor(actor: AuditActor, *, db: Any = None, request: Any = None) -> None:
    """Record ``actor`` as the author of every audited write that follows."""
    _actor.set(actor)
    if db is not None:
        try:
            db.info[_DB_INFO_KEY] = actor
        except Exception:
            pass
    if request is not None:
        try:
            request.state.audit_actor = actor
        except Exception:
            pass


def get_actor(db: Any = None) -> Optional[AuditActor]:
    """The current actor. ``db.info["audit_actor"]`` wins over the contextvar."""
    if db is not None:
        try:
            stamped = db.info.get(_DB_INFO_KEY)
        except Exception:
            stamped = None
        if stamped is not None:
            return stamped
    return _actor.get()


def clear_actor(db: Any = None) -> None:
    """Forget the stamped actor (the contextvar, and ``db.info`` when given)."""
    _actor.set(None)
    if db is not None:
        try:
            db.info.pop(_DB_INFO_KEY, None)
        except Exception:
            pass


@contextmanager
def actor_scope(actor: AuditActor, *, db: Any = None) -> Iterator[AuditActor]:
    """Stamp ``actor`` for the body, then restore whatever was stamped before.

    For jobs and ticks, which run on long-lived threads: without the restore, a
    worker or scheduler actor would outlive its job on that thread.
    """
    token = _actor.set(actor)
    previous_db_actor = None
    if db is not None:
        previous_db_actor = db.info.get(_DB_INFO_KEY)
        db.info[_DB_INFO_KEY] = actor
    try:
        yield actor
    finally:
        _actor.reset(token)
        if db is not None:
            if previous_db_actor is None:
                db.info.pop(_DB_INFO_KEY, None)
            else:
                db.info[_DB_INFO_KEY] = previous_db_actor


# --------------------------------------------------------------------------- #
# Older reader, kept for its service callers.                                  #
# --------------------------------------------------------------------------- #
def get_audit_context() -> tuple[Optional[str], Optional[str]]:
    """Return (user_id, ip_address): the effective actor, as audit rows record it."""
    actor = _actor.get()
    if actor is None:
        return None, None
    return actor.user_id, actor.ip_address


# Per-request correlation id (Sub-plan D Tier-2). The LoggingMiddleware stamps one
# id per request (a job carries its enqueuer's); the audit listener copies it onto
# every AuditLog row so all changes from one action are correlatable.
_trace_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "audit_trace_id", default=None
)


def set_trace_id(trace_id: Optional[str]) -> None:
    """Set the current request's trace/correlation id."""
    _trace_id.set(trace_id)


def get_trace_id() -> Optional[str]:
    """Return the current request's trace/correlation id (None outside a request)."""
    return _trace_id.get()
