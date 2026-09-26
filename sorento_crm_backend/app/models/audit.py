"""Audit log model for system-wide change tracking."""
from sqlalchemy import Column, String, DateTime, Text, Index, event, text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.database import Base
import uuid


class AuditLog(Base):
    """Records INSERT/UPDATE/DELETE on audited entities with old/new values and actor."""
    __tablename__ = "audit_logs"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    entity_type = Column(String(100), nullable=False, index=True)
    # Polymorphic: holds whatever the audited entity's PK is, which is NOT always a
    # UUID (e.g. MarketSegment's PK is a `code` like 'MSEG-A'). Must stay text - 
    # production currently types this column `uuid`, which silently rejects those
    # rows, so market-segment changes have never been audited. See migration 297.
    entity_id = Column(String(100), nullable=False, index=True)
    action = Column(String(20), nullable=False)  # INSERT | UPDATE | DELETE
    user_id = Column(UUID(as_uuid=False), nullable=True)  # system, or user id when available
    # Acting contact (respond_contacts.id) for portal/public-link writes where there is
    # no staff user_id. NULL for staff writes and the `system` automation principal.
    # Display resolves this to the contact name BEFORE the user_id -> staff / "System" fallback.
    contact_id = Column(String(100), nullable=True, index=True)
    # clock_timestamp(), not now(): now() is the TRANSACTION's start, so every row one request
    # wrote shared a timestamp and a record's history came back in random order (#1281 S0).
    changed_at = Column(DateTime(timezone=False), server_default=text("clock_timestamp()"), nullable=False)
    old_values = Column(JSONB, nullable=True)
    new_values = Column(JSONB, nullable=True)
    description = Column(Text, nullable=True)
    ip_address = Column(String(100), nullable=True)
    # Per-request correlation id (Sub-plan D Tier-2): all rows written during one
    # HTTP request share this, so a multi-row change is traceable as one action.
    trace_id = Column(String(64), nullable=True, index=True)
    # Multi-company: copied from the CHANGED entity's own company_id by the flush
    # listener (see audit_service._session_before_flush). DELIBERATELY NOT a
    # CompanyScopedMixin - it is written by the global audit listener and must not
    # be auto-stamped/auto-filtered. NULL => the audited entity has no company_id
    # (or a historical row from before this column existed). Filtered ONLY by the
    # admin audit listing via ``admin_listing_company_filter``.
    company_id = Column(UUID(as_uuid=False), nullable=True, index=True)

    # --- Audit standard S0 (#1281, PLAN-audit-standard-26sep.md) ---
    # The record an operator opens to see this change (a child rolls up to its header via
    # the child model's ``__audit_parent__``); a parentless row is its own root.
    root_entity_type = Column(String(100), nullable=True)
    root_entity_id = Column(String(100), nullable=True)
    # Business verb, dotted (``scm.po.confirm``); NULL = plain CRUD.
    event = Column(String(100), nullable=True, index=True)
    # Who authenticated: user | contact | api_key | worker | scheduler | system.
    principal_type = Column(String(20), nullable=True)
    principal_id = Column(String(100), nullable=True)
    # Whose intent it was when that differs from user_id (the impersonation target).
    on_behalf_of_user_id = Column(UUID(as_uuid=False), nullable=True)
    # ui | portal | chatbot | mcp | n8n | external_api | import | worker | scheduler.
    # Derived server side, never read from a caller header.
    source = Column(String(20), nullable=True)
    reason = Column(Text, nullable=True)
    # One per business action across processes: a job inherits its request's.
    correlation_id = Column(String(64), nullable=True, index=True)

    __table_args__ = (
        Index("ix_audit_logs_entity_type_entity_id", "entity_type", "entity_id"),
        Index("ix_audit_logs_changed_at", "changed_at"),
        Index("ix_audit_logs_user_id", "user_id"),
        Index("ix_audit_logs_root_entity", "root_entity_type", "root_entity_id"),
    )


# Append-only, enforced by Postgres. Any UPDATE, DELETE or TRUNCATE raises unless the
# transaction ran ``SET LOCAL sorento.audit_maintenance = 'on'`` (the retention job, a scrub
# migration). SET LOCAL only, inside an explicit transaction: a plain session-level SET would
# leave a pooled connection in bypass mode for every later request. Migration aud_0001_audit_standard_s0 installs it on existing databases; this hook
# installs it wherever ``create_all`` builds the table (CI's bootstrap_env, the blank test
# schema), so the two cannot drift.
APPEND_ONLY_FUNCTION_SQL = """
CREATE OR REPLACE FUNCTION {schema}audit_logs_append_only() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF coalesce(current_setting('sorento.audit_maintenance', true), '') = 'on' THEN
        IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
        IF TG_OP = 'UPDATE' THEN RETURN NEW; END IF;
        RETURN NULL;
    END IF;
    RAISE EXCEPTION 'audit_logs is append-only (% refused)', TG_OP
        USING ERRCODE = 'insufficient_privilege';
END
$$
"""
APPEND_ONLY_TRIGGERS_SQL = (
    "CREATE TRIGGER audit_logs_append_only_row BEFORE UPDATE OR DELETE ON {schema}audit_logs "
    "FOR EACH ROW EXECUTE FUNCTION {schema}audit_logs_append_only()",
    "CREATE TRIGGER audit_logs_append_only_truncate BEFORE TRUNCATE ON {schema}audit_logs "
    "FOR EACH STATEMENT EXECUTE FUNCTION {schema}audit_logs_append_only()",
)


@event.listens_for(AuditLog.__table__, "after_create")
def _install_append_only_trigger(target, connection, **kw):  # noqa: ANN001
    translate = connection.get_execution_options().get("schema_translate_map") or {}
    schema = translate.get(target.schema)
    prefix = f'"{schema}".' if schema else ""
    # text(), not exec_driver_sql: the RAISE format's `%` would read as a DBAPI placeholder.
    connection.execute(text(APPEND_ONLY_FUNCTION_SQL.format(schema=prefix)))
    for statement in APPEND_ONLY_TRIGGERS_SQL:
        connection.execute(text(statement.format(schema=prefix)))
