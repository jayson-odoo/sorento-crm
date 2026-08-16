"""Audit log service for recording and querying change history."""
import weakref

from sqlalchemy.orm import Session
from sqlalchemy import inspect
from sqlalchemy.orm.attributes import get_history
from sqlalchemy.orm.base import PASSIVE_NO_FETCH
from typing import Optional, Any
from datetime import datetime, date
from decimal import Decimal
from uuid import UUID
from app.models.audit import AuditLog


def _is_uuid(value: str) -> bool:
    """True if ``value`` parses as a UUID (for guarding UUID-typed filter columns)."""
    try:
        UUID(str(value))
        return True
    except (ValueError, AttributeError, TypeError):
        return False


# Declarative audit: set on the model class:
#   __audit_track__ = True
#   __audit_entity_type__ = "entity_type"  # optional, default __tablename__
#   __audit_columns__ = ["col1", "col2"]   # optional, default all columns
def _is_audited(obj: Any) -> bool:
    if obj is None:
        return False
    cls = obj.__class__
    if cls is AuditLog:
        return False
    return bool(getattr(cls, "__audit_track__", False))


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


def _dirty_has_real_changes(obj: Any, columns: Optional[list[str]] = None) -> bool:
    """Whether at least one audited column of a `session.dirty` object actually
    changed value - the noise guard for UPDATE rows.

    Deliberately NOT ``old_values == new_values`` off ``_old_new_from_dirty``'s
    output: those dicts fall back to the CURRENT (new) value for "old" whenever
    SQLAlchemy's default ``active_history=False`` didn't capture the prior
    value (e.g. the attribute was expired - the common case right after an
    earlier commit in the same session, before anything re-reads it). In that
    case old_values and new_values come back identical FOR A COLUMN THAT DID
    CHANGE, so comparing the dicts would wrongly treat a real change as a
    no-op and drop its audit row. ``History.has_changes()`` does not have that
    blind spot: it is True whenever SQLAlchemy recorded an add/delete for the
    key at all, regardless of whether the pre-image value was ever loaded.

    ``passive=PASSIVE_NO_FETCH`` keeps the guard from emitting SQL inside
    ``before_flush``: an expired or deferred column would otherwise lazy-load
    mid-flush. An untouched expired column correctly reports no history, and an
    assigned one still reports its `added` entry, because SQLAlchemy records
    that at SET time without needing a fetch.
    """
    insp = inspect(obj)
    mapper = insp.mapper
    keys = columns if columns is not None else [c.key for c in mapper.column_attrs]
    return any(
        get_history(obj, key, passive=PASSIVE_NO_FETCH).has_changes() for key in keys
    )


def _old_new_from_dirty(obj: Any, columns: Optional[list[str]] = None) -> tuple[dict, dict]:
    """Build old_values and new_values for a dirty (updated) object using attribute history."""
    insp = inspect(obj)
    mapper = insp.mapper
    keys = columns if columns is not None else [c.key for c in mapper.column_attrs]
    old_values: dict[str, Any] = {}
    new_values: dict[str, Any] = {}
    for key in keys:
        hist = get_history(obj, key)
        old_val = hist.deleted[0] if hist.deleted else (hist.unchanged[0] if hist.unchanged else getattr(obj, key, None))
        new_val = hist.added[0] if hist.added else (hist.unchanged[0] if hist.unchanged else getattr(obj, key, None))
        old_values[key] = _json_serial(old_val)
        new_values[key] = _json_serial(new_val)
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
        skip_flush: If True, don't flush (useful when already inside a flush operation).
    """
    from app.audit_context import get_trace_id, get_actor_contact_id

    entry = AuditLog(
        entity_type=entity_type,
        entity_id=entity_id,
        action=action.upper(),
        user_id=user_id,  # None for system/public actions (e.g. approval via public link)
        contact_id=contact_id if contact_id is not None else get_actor_contact_id(),
        old_values=old_values,
        new_values=new_values,
        description=description,
        ip_address=ip_address,
        company_id=company_id,
        trace_id=get_trace_id(),
    )
    db.add(entry)
    if not skip_flush:
        db.flush()  # so entry.id is available if needed
    return entry


def log_import_audit(
    db: Session,
    *,
    entity_type: str,
    label: str,
    row_count: int,
    user_id: Optional[str] = None,
    entity_id: Optional[str] = None,
    status: str = "success",
) -> AuditLog:
    """Write ONE coarse job-level audit row for a bulk import.

    Bulk imports persist via ``bulk_insert_mappings`` / raw SQL which BYPASS the
    ORM flush listener, so per-row audit never fires. This records a single
    ``IMPORT`` event at the job boundary instead. Best-effort by contract: the
    caller MUST wrap this (and the commit) in try/except so an audit-write
    failure never breaks the import.

    ``status`` other than ``"success"`` appends a suffix to the description:
    ``"partial"`` -> ``(partial)``, anything else -> ``(failed)``.
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

    ``entity_id`` and ``user_id`` are UUID columns — a non-UUID value (e.g. a
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


def _session_before_flush(session: Session, _flush_context: Any, _instances: Any) -> None:
    """Collect audit payloads from session.new, session.dirty, session.deleted for tracked models."""
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
        entity_id = _entity_id_str(obj)
        if not entity_id:
            continue  # Pending object with no PK yet (e.g. DB-generated); skip to avoid invalid UUID ""
        if _should_skip(entity_type, entity_id):
            continue
        cols = getattr(cls, "__audit_columns__", None)
        new_values = _model_to_audit_dict(obj)
        if cols is not None:
            new_values = {k: v for k, v in new_values.items() if k in cols}
        pending.append((entity_type, entity_id, "CREATE", None, new_values, getattr(obj, "company_id", None)))
    for obj in session.dirty:
        if not _is_audited(obj):
            continue
        cls = obj.__class__
        entity_type = _audit_entity_type(cls)
        entity_id = _entity_id_str(obj)
        if _should_skip(entity_type, entity_id):
            continue
        cols = getattr(cls, "__audit_columns__", None)
        # Noise guard: SQLAlchemy's default `session.dirty` membership does NOT
        # imply an AUDITED column actually changed value - reassigning a
        # column to the value it already holds, or a flush triggered by a
        # dirty column outside `__audit_columns__`, still lands the object
        # here. Checked via real per-column history (see
        # `_dirty_has_real_changes`), not by comparing `_old_new_from_dirty`'s
        # output dicts - those can read as equal for a column that DID change
        # (the `active_history=False` blind spot documented there), and a
        # dict-equality guard would wrongly drop that row.
        if not _dirty_has_real_changes(obj, columns=cols):
            continue
        old_values, new_values = _old_new_from_dirty(obj, columns=cols)
        pending.append((entity_type, entity_id, "UPDATE", old_values, new_values, getattr(obj, "company_id", None)))
    for obj in session.deleted:
        if not _is_audited(obj):
            continue
        cls = obj.__class__
        entity_type = _audit_entity_type(cls)
        entity_id = _entity_id_str(obj)
        if _should_skip(entity_type, entity_id):
            continue
        cols = getattr(cls, "__audit_columns__", None)
        old_values = _model_to_audit_dict(obj)
        if cols is not None:
            old_values = {k: v for k, v in old_values.items() if k in cols}
        pending.append((entity_type, entity_id, "DELETE", old_values, None, getattr(obj, "company_id", None)))

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
    from app.audit_context import get_audit_context, get_actor_contact_id
    user_id, ip_address = get_audit_context()
    # Acting contact for portal/public writes. Prefer session.info (set by the portal
    # token dependency) over the contextvar: FastAPI runs sync dependencies in a
    # SEPARATE threadpool thread from the path op, so a contextvar mutated in the
    # dependency is NOT visible here — but session.info lives on the shared Session
    # object and survives across threads. Fall back to the contextvar for in-thread callers.
    contact_id = session.info.get("actor_contact_id") or get_actor_contact_id()
    session.info["audit_flushing"] = True
    try:
        for entity_type, entity_id, action, old_values, new_values, entity_company_id in pending:
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
                skip_flush=True,
            )
    finally:
        session.info.pop("audit_flushing", None)
        session.info.pop("audit_pending", None)


def _session_after_flush(session: Session, _flush_context: Any) -> None:
    """Clear audit pending (entries were already added in before_flush)."""
    session.info.pop("audit_pending", None)


_listeners_registered = False


def register_audit_listeners() -> None:
    """Register SQLAlchemy session listeners for automatic audit logging.

    Idempotent. ``app.main``'s startup event calls this unconditionally on
    every app startup, and a TestClient used as a context manager (the
    dominant pattern across this suite - see ``test_dealer_kit_edition_routes.py``)
    re-runs that startup event on every ``with TestClient(app) as client:``.
    ``Session`` is a process-global class, so without this guard each of those
    entries stacks ANOTHER ``before_flush``/``after_flush`` listener onto it,
    and every flush for the rest of the pytest process fires once per
    accumulated registration - N audit rows for one real change, growing with
    every test that has already opened a TestClient. Harmless where nothing
    counts audit rows; silently multiplies them where something does (see
    ``test_dealer_kit_edition_audit.py``, written against a real Edition
    workflow specifically to catch it).
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

    _listeners_registered = True
