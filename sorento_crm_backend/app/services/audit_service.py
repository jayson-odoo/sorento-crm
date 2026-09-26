"""Audit log service for recording and querying change history."""
import weakref

from sqlalchemy.orm import Session
from sqlalchemy import inspect
from sqlalchemy.orm.attributes import get_history
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
    from app.audit_context import get_actor, get_trace_id

    # The stamped actor (identity S0, plan 8): who, how they signed in, and through
    # what. Nothing stamped (a script, a test, a bare service call) is `system`.
    actor = get_actor(db)
    if actor is None and (user_id is not None or contact_id is not None):
        # An explicit caller with nothing stamped (a service method, a script): the
        # row belongs to whoever it names, so the screen keeps showing their name.
        # Only no user and no contact at all is `system`.
        from app.audit_context import AuditActor

        if user_id is not None:
            actor = AuditActor(actor_type="user", user_id=str(user_id), real_user_id=str(user_id))
        else:
            actor = AuditActor(actor_type="contact", contact_id=str(contact_id))
    if description is None and actor is not None and actor.tool_name:
        description = f"Tool: {actor.tool_name}"
    entry = AuditLog(
        entity_type=entity_type,
        entity_id=entity_id,
        action=action.upper(),
        user_id=user_id,  # None for system/public actions (e.g. approval via public link)
        contact_id=contact_id if contact_id is not None else (actor.contact_id if actor else None),
        old_values=old_values,
        new_values=new_values,
        description=description,
        ip_address=ip_address if ip_address is not None else (actor.ip_address if actor else None),
        company_id=company_id,
        trace_id=get_trace_id(),
        actor_type=actor.actor_type if actor is not None else "system",
        real_user_id=_uuid_or_none(actor.real_user_id) if actor is not None else None,
        auth_method=actor.auth_method if actor is not None else None,
        session_id=_uuid_or_none(actor.session_id) if actor is not None else None,
        integration_id=_uuid_or_none(actor.integration_id) if actor is not None else None,
        job_id=(actor.job_id[:128] if actor is not None and actor.job_id else None),
        user_agent=actor.user_agent if actor is not None else None,
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
        # Plan 8.1: an impersonated write carries the target as user_id and the admin
        # as real_user_id, so filtering by a person finds both kinds of row.
        from sqlalchemy import or_

        q = q.filter(or_(AuditLog.user_id == user_id, AuditLog.real_user_id == user_id))
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


def _uuid_or_none(value: Any) -> Optional[str]:
    """A UUID column value, or None. A non-UUID actor id (a test's "REAL_ADMIN",
    the legacy `system` principal) must not fail the audited write."""
    if value is None:
        return None
    text_value = str(value)
    return text_value if _is_uuid(text_value) else None


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


def _session_before_flush(session: Session, _flush_context: Any, _instances: Any) -> None:
    """Collect audit payloads from session.new, session.dirty, session.deleted for tracked models."""
    pending = session.info.setdefault("audit_pending", [])
    # Skip if we're already inside an audit flush (avoid recursion)
    if session.info.get("audit_flushing"):
        return
    # created_by / updated_by keep the EFFECTIVE user during impersonation; the
    # audit row's real_user_id says who was at the keyboard (identity S0, plan 8.2).
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
        # Same timing gap as company_id, unresolved: a column whose value comes from
        # a Python-side or server DEFAULT is still None here, so the CREATE snapshot
        # reads null for it (e.g. customers.customer_type, server_default "company").
        # Left as-is deliberately: a server default is SQL text, not a value we can
        # evaluate without a round-trip, and half-resolving only the Python-side ones
        # would make the snapshot inconsistent per column rather than uniformly
        # "unset at creation". UPDATE rows read the real stored value.
        new_values = _model_to_audit_dict(obj)
        if cols is not None:
            new_values = {k: v for k, v in new_values.items() if k in cols}
        pending.append((entity_type, entity_id, "CREATE", None, new_values, _company_id_for_new(obj)))
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
    from app.audit_context import get_actor
    # session.info wins over the contextvar (get_actor): FastAPI runs a sync
    # dependency in a SEPARATE threadpool thread from the path op, so a contextvar
    # it mutated is not visible here, while session.info lives on the shared Session.
    actor = get_actor(session)
    user_id = _uuid_or_none(actor.user_id) if actor is not None else None
    ip_address = actor.ip_address if actor is not None else None
    contact_id = session.info.get("actor_contact_id") or (actor.contact_id if actor is not None else None)
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

    Idempotent: the listeners are global on ``Session``, so registering twice
    would write every audit row twice. Production calls this once at startup,
    but a test process can reach it from both the app's startup event and a
    fixture, and a doubled history is worse than none.
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

    # Set last: if registering ever raises, a retry must be able to finish the job
    # rather than find the flag already claiming the listeners are installed.
    _listeners_registered = True
