"""FORMS-LAST-ACTIVITY: ``last_activity_at`` on the seven form tables, indexed and backfilled.

The column is the time of the newest person activity on a record (a person's History row on it or
on one of its lines, a file linked or unlinked, a non-system comment), else its creation time. It
is stamped from then on by ``app.services.audit_service`` and ``form_comment_service``; this
migration only adds the column and fills it once for existing rows.

Additive and idempotent (``IF NOT EXISTS``) so the shared dev DB, which converges through
``create_all``, can take it in any order. Self-contained on purpose: the entity type map below is a
copy, not an import, so a later change to app code cannot alter what this revision did.

It also widens the ``entity_conversation_messages`` entity_type CHECK to accept ``sample_request``:
``FORM_COMMENT_KINDS`` lists it, but ``fcom_0002`` never allowed it, so a comment on a sample
request failed the CHECK. Every value allowed before is still allowed.

Plan: documentation/plans/forms/PLAN-forms-last-activity-12nov.md.

Revision ID: fla_0001_last_activity_at
Revises: qdp_0001_duplicate_party
Create Date: 2026-11-12
"""
from alembic import op

revision = "fla_0001_last_activity_at"
down_revision = "qdp_0001_duplicate_party"
branch_labels = None
depends_on = None

# table, schema module (None = public), audit entity types, attachment-link types, comment types
_FORMS = (
    ("complaints", None, ("complaint",), ("complaint",), ("complaint",)),
    (
        "purchase_requests", None,
        ("purchase_request", "sponsorship_form"),
        ("purchase_request", "sponsorship_form"),
        ("purchase_request", "sponsorship_form"),
    ),
    ("price_tag_requests", None, ("price_tag_requests",), ("price_tag_request", "price_tag_requests"), ()),
    ("sample_requests", "projects", ("project_sample_requests",), ("sample_request", "project_sample_requests"), ("sample_request",)),
    ("new_product_applications", None, ("new_product_application",), ("new_product_application",), ()),
    ("stock_inquiries", None, ("stock_inquiry",), ("stock_inquiry",), ("stock_inquiry",)),
    ("workflow_submissions", None, ("workflow_submissions",), ("workflow_submissions",), ()),
)
# Pre-stamp rows carry actor_type 'legacy' (staff edits); worker, scheduler, system and
# integration rows are not a person.
_PERSON = "('user', 'contact', 'public_link', 'legacy')"


_CK = "ck_entity_conversation_messages_entity_type"
_COMMENT_TYPES = (
    "'commercial_project','commercial_master_quotation','commercial_project_task',"
    "'commercial_master_quotation_task','commercial_lead',"
    "'complaint','stock_inquiry','purchase_request','sponsorship_form'"
)


def _set_comment_types(values: str) -> None:
    op.execute(f"ALTER TABLE entity_conversation_messages DROP CONSTRAINT IF EXISTS {_CK}")
    op.execute(f"ALTER TABLE entity_conversation_messages ADD CONSTRAINT {_CK} CHECK (entity_type IN ({values}))")


def _schema(bind, module: str) -> str:
    """Where a module's tables live, for RAW SQL, under BOTH substrates (see
    `sds_0001_stock_debt_snapshots`)."""
    current = bind.exec_driver_sql("SELECT current_schema()").scalar()
    return module if current in (None, "public") else f"{current}_{module}"


def _qualified(bind, table: str, module) -> str:
    return f'"{_schema(bind, module)}".{table}' if module else table


def _in(values) -> str:
    return "(" + ", ".join(f"'{v}'" for v in values) + ")"


def backfill_last_activity(bind) -> None:
    """One UPDATE per table: the newest of person audit rows (entity or root is the record),
    linked-file times and non-system comments, else ``created_at``."""
    for table, module, audit_types, link_types, comment_types in _FORMS:
        name = _qualified(bind, table, module)
        parts = [
            f"""(SELECT max(a.changed_at) FROM audit_logs a
                 WHERE a.actor_type IN {_PERSON}
                   AND ((a.entity_type IN {_in(audit_types)} AND a.entity_id = t.id::text)
                     OR (a.root_entity_type IN {_in(audit_types)} AND a.root_entity_id = t.id::text)))""",
            f"""(SELECT max(l.created_at) FROM entity_attachment_links l
                 WHERE l.entity_type IN {_in(link_types)} AND l.entity_id = t.id::text)""",
        ]
        if comment_types:
            parts.append(
                f"""(SELECT max(m.created_at) FROM entity_conversation_messages m
                     WHERE m.scope = 'form_comment' AND m.is_system = false
                       AND m.entity_type IN {_in(comment_types)} AND m.entity_id = t.id::text)"""
            )
        parts.append("t.created_at")
        bind.exec_driver_sql(f"UPDATE {name} t SET last_activity_at = GREATEST({', '.join(parts)})")


def upgrade() -> None:
    bind = op.get_bind()
    for table, module, *_ in _FORMS:
        name = _qualified(bind, table, module)
        op.execute(f"ALTER TABLE {name} ADD COLUMN IF NOT EXISTS last_activity_at TIMESTAMP NULL")
        op.execute(f"CREATE INDEX IF NOT EXISTS ix_{table}_last_activity_at ON {name} (last_activity_at)")
    _set_comment_types(_COMMENT_TYPES + ",'sample_request'")
    # Literal for the one table whose model-vs-migration tests read the DDL text.
    op.execute("ALTER TABLE new_product_applications ADD COLUMN IF NOT EXISTS last_activity_at TIMESTAMP NULL")
    backfill_last_activity(bind)


def downgrade() -> None:
    bind = op.get_bind()
    _set_comment_types(_COMMENT_TYPES)
    for table, module, *_ in _FORMS:
        name = _qualified(bind, table, module)
        schema_prefix = f'"{_schema(bind, module)}".' if module else ""
        op.execute(f"DROP INDEX IF EXISTS {schema_prefix}ix_{table}_last_activity_at")
        op.execute(f"ALTER TABLE {name} DROP COLUMN IF EXISTS last_activity_at")
