"""Audit log service for recording and querying change history.

Standard (#1281, PLAN-audit-standard-26sep.md): every mapped table is audited by default; a
model opts OUT with ``__audit_skip__ = "<reason>"``. Writes that skip the unit of work (bulk ORM
``update()`` / ``delete()``) are caught by a ``do_orm_execute`` listener. Secrets are redacted
here, before a value can reach ``old_values`` / ``new_values``. Business verbs label rows through
``@audit_event``; a side effect that changes no row is written with ``record()``.
"""
import functools
import inspect as _pyinspect
import logging
import weakref

from sqlalchemy.orm import Session
from sqlalchemy import inspect, select, func
from sqlalchemy.orm.attributes import get_history
from sqlalchemy.sql.elements import BindParameter
from typing import Optional, Any, Iterable
from datetime import datetime, date
from decimal import Decimal
from uuid import UUID
from app.models.audit import AuditLog

logger = logging.getLogger(__name__)

EXPRESSION = "[expression]"
# Per bulk statement: this many itemised rows, then one summary row with the remainder's count.
BULK_AUDIT_CAP = 500

# Columns stamped on every touch. An UPDATE that changes only these writes no row, and they
# never appear in a diff: integrations.last_used_at moves on every API-key call and
# users.last_sign_in_at on every login, which would otherwise be the two loudest writers.
_TOUCH_COLUMNS = frozenset(
    {"updated_at", "last_used_at", "last_sign_in_at", "last_seen_at", "last_activity_at"}
)


def _is_uuid(value: str) -> bool:
    """True if ``value`` parses as a UUID (for guarding UUID-typed filter columns)."""
    try:
        UUID(str(value))
        return True
    except (ValueError, AttributeError, TypeError):
        return False


# Declarative audit, set on the model class:
#   __audit_skip__ = "reason"              # opt OUT (derived, high-churn or log tables)
#   __audit_entity_type__ = "entity_type"  # optional, default __tablename__
#   __audit_columns__ = ["col1", "col2"]   # optional, default all columns
#   __audit_parent__ = "fk_column"         # optional, the record an operator opens
# ``__audit_track__ = True`` predates default-on and is now a no-op marker.
def _is_audited_cls(cls: type) -> bool:
    if cls is AuditLog:
        return False
    return not getattr(cls, "__audit_skip__", None)
# Secret keys are dropped either way (see _redact_secrets).


def _is_audited(obj: Any) -> bool:
    if obj is None:
        return False
    return _is_audited_cls(obj.__class__)


def _audit_entity_type(cls: type) -> str:
    return getattr(cls, "__audit_entity_type__", None) or getattr(cls, "__tablename__", "entity")


def _entity_id_str(obj: Any) -> str:
    """Return the entity's primary key as a string. For pending (new) objects, identity
    is not set yet; we read PK from the object's attributes (e.g. obj.id) when present.
    """
    if obj is None:
        return ""
    insp = inspect(obj)
    pk = insp.identity
    if pk is not None and len(pk) == 1:
        v = pk[0]
        return str(v) if v is not None else ""
    if pk is not None:
        return "_".join(str(v) for v in pk)
    # Pending (new) object: identity not set until after flush. Read PK from attributes.
    mapper = insp.mapper
    pk_cols = mapper.primary_key
    if not pk_cols:
        return ""
    if len(pk_cols) == 1:
        v = getattr(obj, pk_cols[0].key, None)
        return str(v) if v is not None else ""
    parts = [str(getattr(obj, c.key, None) or "") for c in pk_cols]
    return "_".join(parts) if all(p for p in parts) else ""


def _old_new_from_dirty(obj: Any, columns: Optional[list[str]] = None) -> tuple[dict, dict]:
    """old_values / new_values for a dirty object: ONLY the keys whose value changed.

    Touch columns are left out, so an UPDATE that only stamped ``updated_at`` comes back empty
    and the caller writes nothing.
    """
    insp = inspect(obj)
    mapper = insp.mapper
    keys = columns if columns is not None else [c.key for c in mapper.column_attrs]
    old_values: dict[str, Any] = {}
    new_values: dict[str, Any] = {}
    for key in keys:
        if key in _TOUCH_COLUMNS:
            continue
        hist = get_history(obj, key)
        if not hist.has_changes():
            continue
        old_val = _json_serial(hist.deleted[0]) if hist.deleted else None
        new_val = _json_serial(hist.added[0]) if hist.added else None
        if old_val == new_val and hist.deleted:
            continue
        old_values[key] = old_val
        new_values[key] = new_val
    return old_values, new_values


def _json_serial(value: Any) -> Any:
    """Convert a value to a JSON-serializable form."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, (UUID, Decimal)):
        return str(value)
    return value


def _model_to_audit_dict(obj: Any) -> dict[str, Any]:
    """Serialize an ORM model to a JSON-friendly dict for audit old_values/new_values."""
    if obj is None:
        return {}
    try:
        insp = inspect(obj)
        d = {}
        for c in insp.mapper.column_attrs:
            v = getattr(obj, c.key, None)
            d[c.key] = _json_serial(v)
        return d
    except Exception:
        return {}


# Keys that never enter audit_logs, whichever model or caller produced the payload
# (issue #1281). `__audit_columns__` is opt-in per model and a model without it
# snapshots every column, so the deny list is the backstop: `users.password` (a
# bcrypt hash) and `project_quotation_issues.sign_token` (a bearer link token) were
# both written verbatim before it. A new secret column on an audited model belongs here.
AUDIT_SECRET_KEYS = frozenset({
    "password",
    "password_hash",
    "hashed_password",
    "sign_token",
    "token",
    "access_token",
    "refresh_token",
    "api_key",
    "key_hash",
    "secret",
    "client_secret",
})


# S0 (#1281) widens the exact list with name patterns, because default-on auditing reaches
# tables no one listed: system_settings.smtp_password, the *_ciphertext columns
# (respond_workspaces, ai_assistant_configs), integration_api_keys.key_hash,
# portal_otp_codes.code_hash, integrations.credentials_json, public_token on share links.
_SECRET_EXTRA = frozenset({"code_hash", "credentials_json"})
_SECRET_SUFFIXES = ("_password", "_secret", "_token", "_ciphertext")
_SECRET_PREFIXES = ("api_key",)


def _is_secret_key(key: Any) -> bool:
    k = str(key).lower()
    return (
        k in AUDIT_SECRET_KEYS
        or k in _SECRET_EXTRA
        or k.endswith(_SECRET_SUFFIXES)
        or k.startswith(_SECRET_PREFIXES)
    )


def _redact_secrets(values: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """Drop secret keys. Used by log_audit and the bulk path, so every writer goes through it."""
    if not values:
        return values
    return {k: v for k, v in values.items() if not _is_secret_key(k)}


def log_audit(
    db: Session,
    entity_type: str,
    entity_id: str,
    action: str,
    *,
    old_values: Optional[dict[str, Any]] = None,
    new_values: Optional[dict[str, Any]] = None,
    user_id: Optional[str] = None,
    contact_id: Optional[str] = None,
    description: Optional[str] = None,
    ip_address: Optional[str] = None,
    company_id: Optional[str] = None,
    event: Optional[str] = None,
    reason: Optional[str] = None,
    root_entity_type: Optional[str] = None,
    root_entity_id: Optional[str] = None,
    skip_flush: bool = False,
) -> AuditLog:
    """Write one audit log entry. Call from API layer after create/update/delete.

    Args:
        contact_id: Acting contact (respond_contacts.id) for portal/public-link writes
            with no staff ``user_id``. Defaults to the request's actor-contact context,
            so auto-tracked ORM rows attribute to the contact by name instead of "System".
        company_id: Company of the CHANGED entity (multi-company). NULL when the audited
            entity has no company_id column/value. Used ONLY by the admin audit listing
            filter; never auto-stamped (audit_logs is not an owned mixin).
        event, reason: default to the current context's (set by ``@audit_event``).
        root_entity_type, root_entity_id: default to the entity itself.
        skip_flush: If True, don't flush (useful when already inside a flush operation).

    Principal, source, on-behalf-of, request id and correlation id always come from the
    current ``AuditContext``; old / new values are redacted here, whoever the caller is.
    """
    from app.audit_context import current_audit_context

    ctx = current_audit_context()
    entry = AuditLog(
        entity_type=entity_type,
        entity_id=entity_id,
        action=action.upper(),
        user_id=user_id,  # None for system/public actions (e.g. approval via public link)
        contact_id=contact_id if contact_id is not None else (ctx.contact_id if ctx else None),
        old_values=_redact_secrets(old_values),
        new_values=_redact_secrets(new_values),
        description=description,
        ip_address=ip_address,
        company_id=company_id,
        **_context_columns(ctx, event=event, reason=reason),
        root_entity_type=root_entity_type or entity_type,
        root_entity_id=root_entity_id if root_entity_id is not None else entity_id,
    )
    db.add(entry)
    if not skip_flush:
        db.flush()  # so entry.id is available if needed
    return entry


def _context_columns(ctx: Any, *, event: Optional[str] = None, reason: Optional[str] = None) -> dict:
    """The audit_logs columns the current context owns."""
    if ctx is None:
        return {"principal_type": "system", "event": event, "reason": reason}
    return {
        "trace_id": ctx.request_id,
        "correlation_id": ctx.correlation_id,
        "principal_type": ctx.principal_type or "system",
        "principal_id": ctx.principal_id,
        "on_behalf_of_user_id": ctx.on_behalf_of_user_id,
        "source": ctx.source,
        "event": event or ctx.event,
        "reason": reason or ctx.reason,
    }


def record(
    db: Session,
    *,
    event: str,
    entity_type: str,
    entity_id: str,
    reason: Optional[str] = None,
    old_values: Optional[dict[str, Any]] = None,
    new_values: Optional[dict[str, Any]] = None,
    description: Optional[str] = None,
    company_id: Optional[str] = None,
    skip_flush: bool = False,
) -> AuditLog:
    """Write one ``EVENT`` row for a side effect that changed no row (a download, a send, a
    login), attributed to the current context. The one explicit call for non-service code."""
    from app.audit_context import current_audit_context

    ctx = current_audit_context()
    return log_audit(
        db,
        entity_type,
        str(entity_id),
        "EVENT",
        old_values=old_values,
        new_values=new_values,
        user_id=ctx.user_id if ctx else None,
        ip_address=ctx.ip_address if ctx else None,
        description=description,
        company_id=company_id,
        event=event,
        reason=reason,
        skip_flush=skip_flush,
    )


def audit_event(
    event: str,
    *,
    entity: Optional[str] = None,
    ids: Optional[str] = None,
    reason: Optional[str] = None,
):
    """Label every audit row written inside the decorated call with a business verb.

    ``reason`` names the argument carrying the user's reason. ``entity`` + ``ids`` (the name of
    an argument holding one id or a list) make the call write one ``EVENT`` row for each id the
    call changed nothing on, so a pure side effect still leaves a trace. The session is the
    ``db`` argument or ``self.db``. The context's previous event and reason come back afterwards,
    also when the call raises.
    """

    def deco(fn):
        sig = _pyinspect.signature(fn)

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            from app.audit_context import audit_context_scope, current_audit_context

            bound = sig.bind_partial(*args, **kwargs)
            ctx = current_audit_context()
            if ctx is None:
                with audit_context_scope():
                    return wrapper(*args, **kwargs)
            saved = (ctx.event, ctx.reason, ctx.event_hits)
            ctx.event = event
            if reason and bound.arguments.get(reason):
                ctx.reason = str(bound.arguments[reason])
            ctx.event_hits = set()
            try:
                result = fn(*args, **kwargs)
                if entity and ids:
                    _record_untouched(bound.arguments, entity, ids, event, ctx)
                return result
            finally:
                ctx.event, ctx.reason, ctx.event_hits = saved

        return wrapper

    return deco


def _record_untouched(arguments: dict, entity: str, ids_arg: str, event: str, ctx: Any) -> None:
    db = arguments.get("db") or getattr(arguments.get("self"), "db", None)
    if db is None:
        logger.warning("audit_event %s: no session (db or self.db) to record on", event)
        return
    raw = arguments.get(ids_arg)
    id_list: Iterable = raw if isinstance(raw, (list, tuple, set)) else ([raw] if raw else [])
    # Flush first, so rows the call only staged are written, and labelled, inside the event.
    db.flush()
    for entity_id in id_list:
        if (entity, str(entity_id)) not in ctx.event_hits:
            record(db, event=event, entity_type=entity, entity_id=str(entity_id))


def log_import_audit(
    db: Session,
    *,
    entity_type: str,
    label: str,
    row_count: int,
    user_id: Optional[str] = None,
    entity_id: Optional[str] = None,
    status: str = "success",
    details: Optional[dict[str, Any]] = None,
) -> AuditLog:
    """Write ONE coarse job-level audit row for a bulk import.

    Bulk imports persist via ``bulk_insert_mappings`` / raw SQL which BYPASS the
    ORM flush listener, so per-row audit never fires. An import of an AUDITED
    model (e.g. customers) suppresses the per-row listener instead, via
    ``session.info["skip_audit_entity_types"]``, because a worker has no request
    actor and would log N rows as "System". Either way this records a single
    ``IMPORT`` event at the job boundary. Best-effort by contract: the caller
    MUST wrap this (and the commit) in try/except so an audit-write failure
    never breaks the import.

    ``status`` other than ``"success"`` appends a suffix to the description:
    ``"partial"`` -> ``(partial)``, anything else -> ``(failed)``.

    ``details`` lands in ``new_values``: what the run did, and the job id that
    reaches the per-row outcomes in ``import_job_rows``. One coarse row is only
    worth having if it leads back to the rows it stands for.
    """
    description = f"{label}, {row_count} rows"
    if status == "partial":
        description += " (partial)"
    elif status != "success":
        description += " (failed)"
    return log_audit(
        db,
        entity_type,
        entity_id or "",
        "IMPORT",
        new_values=details,
        user_id=user_id,
        description=description,
    )


def list_audit_logs(
    db: Session,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    user_id: Optional[str] = None,
    action: Optional[str] = None,
    trace_id: Optional[str] = None,
    changed_from: Optional[datetime] = None,
    changed_to: Optional[datetime] = None,
    page: int = 1,
    limit: int = 50,
) -> tuple[list[AuditLog], int]:
    """List audit logs with optional filters. Returns (items, total).

    ``entity_id`` and ``user_id`` are UUID columns - a non-UUID value (e.g. a
    typed name in the User filter) would raise a Postgres DataError (500). Guard
    both: an unparseable value can never match a row, so short-circuit to empty.
    """
    q = db.query(AuditLog)
    if entity_type:
        q = q.filter(AuditLog.entity_type == entity_type)
    if entity_id:
        if not _is_uuid(entity_id):
            return [], 0
        q = q.filter(AuditLog.entity_id == entity_id)
    if user_id:
        if not _is_uuid(user_id):
            return [], 0
        q = q.filter(AuditLog.user_id == user_id)
    if action:
        q = q.filter(AuditLog.action == action.upper())
    if trace_id:
        q = q.filter(AuditLog.trace_id == trace_id)
    # Multi-company: staff audit listing shows only the active company's rows
    # (+ legacy-null / entity-has-no-company rows). audit_logs is not an owned
    # mixin; filter by hand. See admin_listing_company_filter for the four states.
    from app.services.company_scope import admin_listing_company_filter
    scope_filter = admin_listing_company_filter(db, AuditLog.company_id)
    if scope_filter is not None:
        q = q.filter(scope_filter)
    if changed_from:
        q = q.filter(AuditLog.changed_at >= changed_from)
    if changed_to:
        q = q.filter(AuditLog.changed_at <= changed_to)
    q = q.order_by(AuditLog.changed_at.desc())
    total = q.count()
    offset = (page - 1) * limit
    items = q.offset(offset).limit(limit).all()
    return items, total


_ACTOR_FIELDS_INSERT = ("created_by_user_id", "created_by", "updated_by_user_id", "updated_by")
_ACTOR_FIELDS_UPDATE = ("updated_by_user_id", "updated_by")


def _swap_actor_fields_during_impersonation(session: Session) -> None:
    """When the current request is impersonating, rewrite any ``created_by`` /
    ``updated_by`` fields on new/dirty rows from the effective (target) user id
    back to the real admin id. No-op outside impersonation.
    """
    from app.audit_context import get_real_and_effective_user_ids

    real_id, effective_id = get_real_and_effective_user_ids()
    if not real_id or not effective_id or real_id == effective_id:
        return
    for obj in session.new:
        for field in _ACTOR_FIELDS_INSERT:
            if hasattr(obj, field) and getattr(obj, field, None) == effective_id:
                setattr(obj, field, real_id)
    for obj in session.dirty:
        for field in _ACTOR_FIELDS_UPDATE:
            if hasattr(obj, field) and getattr(obj, field, None) == effective_id:
                setattr(obj, field, real_id)


_audit_table_cache: "weakref.WeakKeyDictionary[Any, bool]" = weakref.WeakKeyDictionary()


def _audit_table_exists(bind: Any) -> bool:
    """Whether `audit_logs` exists on this bind. Cached per-engine (has_table is
    a round-trip; the flush path is hot). Prod engines always return True."""
    if bind is None:
        return False
    # Keyed by the engine OBJECT via a weak map, never by id(engine):
    # CPython recycles id() once an object is collected, so a short-lived
    # engine (every sqlite test file makes its own, each with a different
    # subset schema) could land on a dead engine's address and inherit its
    # cached answer. Measured: 60 engines produced only 23 distinct ids.
    # A weak map drops the entry when the engine dies, so no reuse.
    key = bind.engine if hasattr(bind, "engine") else bind
    cached = _audit_table_cache.get(key)
    if cached is None:
        from sqlalchemy import inspect as _sa_inspect

        try:
            cached = _sa_inspect(bind).has_table("audit_logs")
        except Exception:
            cached = False
        _audit_table_cache[key] = cached
    return cached


def _company_id_for_new(obj: Any) -> Any:
    """The company an about-to-be-inserted audited row belongs to.

    ``company_id`` on a brand new owned row is still ``None`` here: the stamp is a
    mapper-level ``before_insert`` hook, which runs AFTER this ``before_flush``
    listener. Recording that ``None`` would not just lose the company, it would
    publish the row - ``admin_listing_company_filter`` shows company-less audit rows
    to every company, so another company's staff could read the created entity's
    values out of the audit list. Ask the scope for the value the stamp is about to
    write; ``None`` back means the insert has no company to land in (and will raise),
    so leave it null rather than guess.
    """
    company_id = getattr(obj, "company_id", None)
    if company_id is not None:
        return company_id
    from app.services.company_scope import pending_company_id

    return pending_company_id(obj)


def _parent_of(cls: type) -> Optional[tuple[str, str]]:
    """(parent audit entity type, fk attribute key) for a class declaring ``__audit_parent__``."""
    fk_col = getattr(cls, "__audit_parent__", None)
    if not fk_col:
        return None
    cached = _parent_cache.get(cls)
    if cached is not None:
        return cached
    mapper = inspect(cls)
    column = mapper.columns[fk_col]
    (fk,) = column.foreign_keys
    parent_table = fk.column.table
    parent_cls = _class_for_table(parent_table)
    parent_type = _audit_entity_type(parent_cls) if parent_cls is not None else parent_table.name
    cached = (parent_type, mapper.get_property_by_column(column).key)
    _parent_cache[cls] = cached
    return cached


_parent_cache: dict = {}
_table_class_cache: dict = {}


def _class_for_table(table: Any) -> Optional[type]:
    """The mapped class whose local table is ``table`` (Core DML carries no mapper)."""
    if not _table_class_cache:
        from app.database import Base

        for mapper in Base.registry.mappers:
            _table_class_cache.setdefault(mapper.local_table, mapper.class_)
    return _table_class_cache.get(table)


def _root(cls: type, entity_type: str, entity_id: str, values: Optional[dict]) -> tuple[str, str]:
    parent = _parent_of(cls)
    if parent is not None and values and values.get(parent[1]) is not None:
        return parent[0], str(values[parent[1]])
    return entity_type, entity_id


def _session_before_flush(session: Session, _flush_context: Any, _instances: Any) -> None:
    """Collect audit payloads from session.new, session.dirty, session.deleted for audited models."""
    pending = session.info.setdefault("audit_pending", [])
    # Skip if we're already inside an audit flush (avoid recursion)
    if session.info.get("audit_flushing"):
        return
    # Rewrite created_by/updated_by from effective→real user during impersonation
    # *before* we snapshot model state for audit, so the audit log captures the
    # corrected actor too.
    _swap_actor_fields_during_impersonation(session)
    skip_set = set(session.info.get("skip_audit_for") or [])
    # Entity-type-level suppression: bulk jobs that persist a tracked model per-row
    # (e.g. attachment bulk import via ORM create_attachment in a worker with no
    # request actor) set this so they emit ONE coarse job-level audit row instead
    # of N per-row rows attributed to "System".
    skip_types = set(session.info.get("skip_audit_entity_types") or [])

    def _should_skip(etype: str, eid: str) -> bool:
        return etype in skip_types or (etype, eid) in skip_set

    for obj in session.new:
        if not _is_audited(obj):
            continue
        cls = obj.__class__
        entity_type = _audit_entity_type(cls)
        entity_id = _entity_id_str(obj) or _apply_python_pk_default(obj)
        if not entity_id:
            # A DB-generated key (serial / identity): known only after the INSERT, so the
            # CREATE row is written in after_flush instead.
            if entity_type not in skip_types:
                session.info.setdefault("audit_pending_new", []).append(obj)
            continue
        if _should_skip(entity_type, entity_id):
            continue
        cols = getattr(cls, "__audit_columns__", None)
        # Same timing gap as company_id, unresolved: a column whose value comes from
        # a Python-side or server DEFAULT is still None here, so the CREATE snapshot
        # reads null for it (e.g. customers.customer_type, server_default "company").
        # Left as-is deliberately: a server default is SQL text, not a value we can
        # evaluate without a round-trip, and half-resolving only the Python-side ones
        # would make the snapshot inconsistent per column rather than uniformly
        # "unset at creation". UPDATE rows read the real stored value.
        snapshot = _model_to_audit_dict(obj)
        new_values = {k: v for k, v in snapshot.items() if k in cols} if cols is not None else snapshot
        root = _root(cls, entity_type, entity_id, snapshot)
        pending.append((entity_type, entity_id, "CREATE", None, new_values, _company_id_for_new(obj), root))
    for obj in session.dirty:
        if not _is_audited(obj):
            continue
        cls = obj.__class__
        entity_type = _audit_entity_type(cls)
        entity_id = _entity_id_str(obj)
        if _should_skip(entity_type, entity_id):
            continue
        cols = getattr(cls, "__audit_columns__", None)
        old_values, new_values = _old_new_from_dirty(obj, columns=cols)
        if not old_values and not new_values:
            continue
        root = _root(cls, entity_type, entity_id, _model_to_audit_dict(obj))
        pending.append((entity_type, entity_id, "UPDATE", old_values, new_values, getattr(obj, "company_id", None), root))
    for obj in session.deleted:
        if not _is_audited(obj):
            continue
        cls = obj.__class__
        entity_type = _audit_entity_type(cls)
        entity_id = _entity_id_str(obj)
        if _should_skip(entity_type, entity_id):
            continue
        cols = getattr(cls, "__audit_columns__", None)
        snapshot = _model_to_audit_dict(obj)
        old_values = {k: v for k, v in snapshot.items() if k in cols} if cols is not None else snapshot
        root = _root(cls, entity_type, entity_id, snapshot)
        pending.append((entity_type, entity_id, "DELETE", old_values, None, getattr(obj, "company_id", None), root))

    # Add audit log rows in the same flush (so we never call flush from inside an event)
    if not pending:
        return
    # Resilience: some unit tests bind to a sqlite engine whose schema is a
    # subset that excludes `audit_logs` (the audit listener is global and fires
    # on any tracked insert). Writing there raises "no such table" and fails
    # otherwise-unrelated tests. Production always has the table, so this guard
    # is a no-op in prod.
    if not _audit_table_exists(session.get_bind()):
        session.info.pop("audit_pending", None)
        return
    from app.audit_context import current_audit_context, get_audit_context, get_actor_contact_id
    user_id, ip_address = get_audit_context()
    # Acting contact for portal/public writes. Prefer session.info (set by the portal
    # token dependency) over the contextvar: FastAPI runs sync dependencies in a
    # SEPARATE threadpool thread from the path op, so a contextvar mutated in the
    # dependency is NOT visible here - but session.info lives on the shared Session
    # object and survives across threads. Fall back to the contextvar for in-thread callers.
    contact_id = session.info.get("actor_contact_id") or get_actor_contact_id()
    ctx = current_audit_context()
    session.info["audit_flushing"] = True
    try:
        for entity_type, entity_id, action, old_values, new_values, entity_company_id, root in pending:
            log_audit(
                session,
                entity_type,
                entity_id,
                action,
                old_values=old_values,
                new_values=new_values,
                user_id=user_id,
                contact_id=contact_id,
                ip_address=ip_address,
                company_id=entity_company_id,
                root_entity_type=root[0],
                root_entity_id=root[1],
                skip_flush=True,
            )
            if ctx is not None and ctx.event:
                ctx.event_hits.add((entity_type, entity_id))
    finally:
        session.info.pop("audit_flushing", None)
        session.info.pop("audit_pending", None)


def _apply_python_pk_default(obj: Any) -> str:
    """Give a new object its primary key now, from the column's Python-side default.

    SQLAlchemy only runs ``default=lambda: str(uuid.uuid4())`` at INSERT time, so a new row
    whose code never set ``id`` reached this listener with no id and its CREATE was silently
    dropped. Running the same default here is exactly what the INSERT would have done.
    """
    mapper = inspect(obj).mapper
    if len(mapper.primary_key) != 1:
        return ""
    column = mapper.primary_key[0]
    default = column.default
    if default is None or not (default.is_scalar or default.is_callable):
        return ""
    value = default.arg(None) if default.is_callable else default.arg
    if value is None:
        return ""
    setattr(obj, mapper.get_property_by_column(column).key, value)
    return str(value)


def _session_after_flush(session: Session, _flush_context: Any) -> None:
    """Write CREATE rows for DB-generated keys (see before_flush); clear the pending list."""
    session.info.pop("audit_pending", None)
    pending_new = session.info.pop("audit_pending_new", None)
    if not pending_new:
        return
    from app.audit_context import current_audit_context, get_audit_context, get_actor_contact_id

    ctx = current_audit_context()
    user_id, ip_address = get_audit_context()
    contact_id = session.info.get("actor_contact_id") or get_actor_contact_id()
    skip_set = set(session.info.get("skip_audit_for") or [])
    rows = []
    for obj in pending_new:
        insp = inspect(obj)
        if insp.identity is None:
            continue
        cls = obj.__class__
        entity_type = _audit_entity_type(cls)
        entity_id = _entity_id_str(obj)
        if not entity_id or (entity_type, entity_id) in skip_set:
            continue
        # Loaded state only: an attribute read here must not issue a SELECT mid-flush.
        snapshot = {c.key: _json_serial(insp.dict.get(c.key)) for c in insp.mapper.column_attrs}
        cols = getattr(cls, "__audit_columns__", None)
        new_values = {k: v for k, v in snapshot.items() if k in cols} if cols is not None else snapshot
        root = _root(cls, entity_type, entity_id, snapshot)
        rows.append({
            "entity_type": entity_type,
            "entity_id": entity_id,
            "action": "CREATE",
            "user_id": user_id,
            "contact_id": contact_id,
            "ip_address": ip_address,
            "old_values": None,
            "new_values": _redact_secrets(new_values),
            "description": None,
            "company_id": snapshot.get("company_id"),
            "root_entity_type": root[0],
            "root_entity_id": root[1],
            **_context_columns(ctx),
        })
    if rows:
        conn = session.connection()
        if _audit_table_exists(conn):
            conn.execute(AuditLog.__table__.insert(), rows)


def _bulk_value(value: Any) -> Any:
    if isinstance(value, BindParameter) and value.callable is None:
        return _json_serial(value.value)
    return EXPRESSION


def _session_do_orm_execute(state: Any) -> None:
    """Audit ``update()`` / ``delete()`` statements, which never reach ``before_flush``.

    Covers ``query().update()/delete()``, ORM ``update(Model)/delete(Model)`` and Core DML on a
    mapped table, all issued through ``Session.execute``. The matching rows are read first
    (primary key, the SET columns' old values or, for a delete, the whole row), capped at
    ``BULK_AUDIT_CAP`` itemised rows plus one summary row, and written straight to the table on
    the statement's own connection. Raw ``text()`` DML and ``bulk_*_mappings`` are not seen
    here; they are allowlisted by name (S3).
    """
    if not (state.is_update or state.is_delete):
        return
    session = state.session
    if session.info.get("audit_flushing"):
        return
    statement = state.statement
    table = getattr(statement, "table", None)
    # An ORM statement names its mapper; Core DML on a mapped table is looked up by table.
    cls = state.bind_mapper.class_ if state.bind_mapper is not None else _class_for_table(table)
    if cls is None or not _is_audited_cls(cls):
        return
    entity_type = _audit_entity_type(cls)
    if entity_type in set(session.info.get("skip_audit_entity_types") or []):
        return
    if isinstance(state.parameters, (list, tuple)) and state.parameters:
        # executemany ("bulk UPDATE by primary key"): the rows live in the parameter list, not
        # in a WHERE clause, so the pre-select below would match the whole table. Same class
        # as bulk_*_mappings: allowlisted by name in S3.
        logger.info("audit: executemany on %s not itemised", entity_type)
        return
    conn = session.connection(bind_arguments=state.bind_arguments)
    if not _audit_table_exists(conn):
        return
    try:
        # A savepoint, so a failed capture cannot abort the transaction the write runs in.
        with conn.begin_nested():
            _write_bulk_rows(session, conn, cls, entity_type, statement, state.is_delete)
    except Exception:
        # Never let the trail break the write it is recording; say so loudly instead.
        logger.exception("audit: bulk capture failed for %s", entity_type)


def _write_bulk_rows(session: Session, conn: Any, cls: type, entity_type: str, statement: Any, is_delete: bool) -> None:
    from app.audit_context import current_audit_context, get_audit_context, get_actor_contact_id

    mapper = inspect(cls)
    table = mapper.local_table
    pk_cols = list(mapper.primary_key)
    key_of = {col: prop.key for prop in mapper.column_attrs for col in prop.columns if col.table is table}
    allowed = getattr(cls, "__audit_columns__", None)
    if is_delete:
        value_cols = [c for c in table.columns if c in key_of]
        set_values = {}
    else:
        raw = dict(getattr(statement, "_values", None) or {})
        raw.update(dict(getattr(statement, "_ordered_values", None) or []))
        set_values = {}
        for col, value in raw.items():
            col = table.c.get(col) if isinstance(col, str) else col
            if col is None or col not in key_of or key_of[col] in _TOUCH_COLUMNS:
                continue
            if allowed is not None and key_of[col] not in allowed:
                continue
            set_values[col] = value
        if not set_values:
            return
        value_cols = list(set_values)
    parent = _parent_of(cls)
    extra = [c for c in table.columns if c.key == "company_id" or (parent and key_of.get(c) == parent[1])]
    wanted = list(dict.fromkeys(pk_cols + value_cols + extra))
    query = select(*wanted)
    for criterion in getattr(statement, "_where_criteria", ()):
        query = query.where(criterion)
    cap = BULK_AUDIT_CAP
    rows = conn.execute(query.limit(cap + 1)).mappings().all()
    remaining = 0
    if len(rows) > cap:
        remaining = conn.execute(select(func.count()).select_from(query.subquery())).scalar() - cap
        rows = rows[:cap]
    if not rows:
        return

    skip_set = set(session.info.get("skip_audit_for") or [])
    ctx = current_audit_context()
    user_id, ip_address = get_audit_context()
    contact_id = session.info.get("actor_contact_id") or get_actor_contact_id()
    common = {
        "entity_type": entity_type,
        "action": "DELETE" if is_delete else "UPDATE",
        "user_id": user_id,
        "contact_id": contact_id,
        "ip_address": ip_address,
        **_context_columns(ctx),
    }
    out = []
    for row in rows:
        entity_id = "_".join(str(row[c]) for c in pk_cols)
        if (entity_type, entity_id) in skip_set:
            continue
        snapshot = {key_of[c]: _json_serial(row[c]) for c in wanted if c in key_of}
        if is_delete:
            old_values = snapshot if allowed is None else {k: v for k, v in snapshot.items() if k in allowed}
            new_values = None
        else:
            old_values = {key_of[c]: _json_serial(row[c]) for c in value_cols}
            new_values = {key_of[c]: _bulk_value(v) for c, v in set_values.items()}
        root = _root(cls, entity_type, entity_id, snapshot)
        out.append({
            **common,
            "entity_id": entity_id,
            "old_values": _redact_secrets(old_values),
            "new_values": _redact_secrets(new_values),
            "company_id": snapshot.get("company_id"),
            "root_entity_type": root[0],
            "root_entity_id": root[1],
        })
        if ctx is not None and ctx.event:
            ctx.event_hits.add((entity_type, entity_id))
    if remaining > 0:
        out.append({
            **common,
            "entity_id": "*",
            "old_values": None,
            "new_values": None,
            "company_id": None,
            "root_entity_type": entity_type,
            "root_entity_id": "*",
            "description": f"Bulk {common['action'].lower()} on {entity_type}: {remaining} more rows not itemised",
        })
    if out:
        for entry in out:
            entry.setdefault("description", None)
        conn.execute(AuditLog.__table__.insert(), out)


_listeners_registered = False


def register_audit_listeners() -> None:
    """Register SQLAlchemy session listeners for automatic audit logging.

    Idempotent: the listeners are global on ``Session``, so registering twice
    would write every audit row twice. Production calls this once at startup
    (the API's startup event and ``worker.py``), but a test process can reach it
    from both the app's startup event and a fixture, and a doubled history is
    worse than none.
    """
    global _listeners_registered
    if _listeners_registered:
        return

    from sqlalchemy import event

    @event.listens_for(Session, "before_flush")
    def before_flush(session, flush_context, instances):
        _session_before_flush(session, flush_context, instances)

    @event.listens_for(Session, "after_flush")
    def after_flush(session, flush_context):
        _session_after_flush(session, flush_context)

    @event.listens_for(Session, "do_orm_execute")
    def do_orm_execute(orm_execute_state):
        _session_do_orm_execute(orm_execute_state)

    # Set last: if registering ever raises, a retry must be able to finish the job
    # rather than find the flag already claiming the listeners are installed.
    _listeners_registered = True
