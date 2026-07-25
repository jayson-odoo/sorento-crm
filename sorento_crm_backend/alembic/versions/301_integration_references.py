"""Integration reference table: which records came from an upstream system

Phase B (UAC Group D). Replaces the plan's per-table source_system/source_ref
columns with one polymorphic mapping table.

Why the shape changed from the plan: the nine consumed tables hold ~110k rows
(order_lines 68k, orders 25k, products 11k). Adding two columns to each would
mean nine migrations plus a backfill writing 'manual' into every existing row --
110k rows carrying no information, and an invariant every future manual create
would have to maintain or quietly break. A mapping table keeps the business
tables untouched, makes "what came from AutoCount?" one query instead of nine,
and lets a tenth entity type arrive with no DDL at all.

**No backfill.** Absence of a reference means the record was created locally.
That satisfies what AC-AC-23 was protecting against -- no row left in a state
that breaks a later sync -- without materialising rows that say nothing.

**No foreign key on entity_id**, because it points at one of nine tables.
Integrity is enforced in IntegrationReferenceService: entity_type is checked
against an allowlist before it ever reaches SQL, and a reference whose target
has been deleted is treated as absent and cleaned up when read.

Revision ID: 301_integration_references
Revises: 300_env_key_belongs_to_n8n
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "301_integration_references"
down_revision = "300_env_key_belongs_to_n8n"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    if "integration_references" in set(sa.inspect(conn).get_table_names()):
        return

    op.create_table(
        "integration_references",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        # Which business table, and which row in it. No FK: entity_id points at
        # one of nine tables. The service validates entity_type against an
        # allowlist before it is ever interpolated into SQL.
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("entity_id", sa.String(), nullable=False),
        sa.Column(
            "source_system", sa.String(30), nullable=False, server_default="autocount"
        ),
        # AutoCount's stable DocKey -- never DocNo, which is mutable (NewDocNo
        # exists), so correlating on it would create a duplicate the first time
        # a document is renumbered.
        sa.Column("source_ref", sa.String(255), nullable=False),
        # Display only, expected to change.
        sa.Column("source_doc_no", sa.String(100), nullable=True),
        sa.Column(
            "integration_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("integrations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "first_seen_at", sa.DateTime(timezone=False), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "last_synced_at", sa.DateTime(timezone=False), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=False), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=False), nullable=False, server_default=sa.func.now()
        ),
        # One external document -> one local record. This constraint is what
        # makes ingest idempotent; without it a re-push could create a second
        # mapping and later syncs would update whichever they found first.
        sa.UniqueConstraint(
            "source_system", "entity_type", "source_ref", name="uq_integration_ref_source"
        ),
        # ...and one local record -> one origin, so per-field ownership rules
        # later have an unambiguous answer to "where did this come from?".
        sa.UniqueConstraint("entity_type", "entity_id", name="uq_integration_ref_entity"),
    )

    # This table grows with every synced document, so the hot lookups get their
    # own indexes rather than relying on a scan of a table that only gets bigger.
    op.create_index(
        "ix_integration_references_entity",
        "integration_references",
        ["entity_type", "entity_id"],
    )
    op.create_index(
        "ix_integration_references_source_ref", "integration_references", ["source_ref"]
    )
    op.create_index(
        "ix_integration_references_integration_id", "integration_references", ["integration_id"]
    )
    op.create_index(
        "ix_integration_references_last_synced_at", "integration_references", ["last_synced_at"]
    )


def downgrade():
    conn = op.get_bind()
    if "integration_references" not in set(sa.inspect(conn).get_table_names()):
        return
    for index in (
        "ix_integration_references_last_synced_at",
        "ix_integration_references_integration_id",
        "ix_integration_references_source_ref",
        "ix_integration_references_entity",
    ):
        op.drop_index(index, table_name="integration_references")
    op.drop_table("integration_references")
