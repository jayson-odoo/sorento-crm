"""portal submission revisions - tables, config seed, denormalized counters

S1 of PLAN-portal-submission-revisions. Strictly additive:

1. `portal_form_revisions` - one row per submitted version of a portal submission.
2. `portal_revision_configs` - per-type policy, seeded with all four portal types so
   turning one on is a checkbox and never another migration.
3. `system_settings.portal_revisions_enabled` / `portal_max_revisions` - the global
   kill switch and the fallback cap.
4. `revision_no` / `last_revised_at` on `stock_inquiries` and `purchase_requests`
   (the latter covers both purchase_request and sponsorship_form - one table).
5. `conversation_sla_tracking.voided_at` / `void_reason` - the tracker had no void
   concept, and `is_resolved` must not be overloaded to mean "cancelled".

Allowed statuses per UAC A5, read off the actual chains rather than invented:
  stock_inquiry    pending_project_sales -> pending_purchasing -> responded
                   (revisable even after purchasing answered, explicit user decision;
                    excludes new/draft and the terminal rejected/voided/closed)
  purchase_request submitted -> approved
  sponsorship_form submitted -> approved
                   (`submitted` spans the project-sales stage and the pending-approval
                    stage, which is an approval_status sub-state, not a lifecycle status.
                    `processed_by_cs`, `closed`, `rejected` and `voided` are terminal -
                    see ProcurementService._VOID_BLOCKED_STATUSES - so they are excluded.)
  complaint        disabled with an empty list, present and flippable.

Revision ID: portal_rev_0001
Revises: 311m_spec_tables_uuid_id
Create Date: 2026-08-10
"""
import json

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "portal_rev_0001"
down_revision = "311m_spec_tables_uuid_id"
branch_labels = None
depends_on = None


# (source_entity_type, is_enabled, allowed_statuses)
_CONFIG_SEED: tuple[tuple[str, bool, tuple[str, ...]], ...] = (
    ("stock_inquiry", True, ("pending_project_sales", "pending_purchasing", "responded")),
    ("purchase_request", True, ("submitted", "approved")),
    ("sponsorship_form", True, ("submitted", "approved")),
    ("complaint", False, ()),
)


def _json_array(values: tuple[str, ...]) -> str:
    """Render a status tuple as a JSON array literal for the jsonb cast in the seed."""
    return json.dumps(list(values))


def upgrade() -> None:
    op.create_table(
        "portal_form_revisions",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("source_entity_type", sa.String(length=50), nullable=False),
        sa.Column("source_entity_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("revision_no", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("invalidated_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "snapshot_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "attachments_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        # The PRIMARY (newest) voided stage plus its handler, and the full list of
        # every stage the revision voided (a form can have two stages open at once).
        sa.Column("voided_stage_code", sa.String(length=100), nullable=True),
        sa.Column("voided_assignee_user_id", sa.Text(), nullable=True),
        sa.Column("voided_stages_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=False), server_default=sa.func.now(), nullable=False),
        sa.Column("submitted_by_contact_id", sa.Text(), nullable=True),
        sa.Column("is_reconstructed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=False), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["submitted_by_contact_id"], ["respond_contacts.id"], ondelete="SET NULL"
        ),
        # version_no is unique per entity; revision_no deliberately is NOT - a
        # resubmission after an office rejection repeats the current revision_no.
        sa.UniqueConstraint(
            "source_entity_type",
            "source_entity_id",
            "version_no",
            name="uq_portal_form_revisions_entity_version",
        ),
    )
    op.create_index(
        "ix_portal_form_revisions_source_entity",
        "portal_form_revisions",
        ["source_entity_type", "source_entity_id"],
    )

    op.create_table(
        "portal_revision_configs",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("source_entity_type", sa.String(length=50), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("max_revisions", sa.Integer(), nullable=True),
        sa.Column(
            "allowed_statuses",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("restart_stage_code", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=False), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=False), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_entity_type", name="uq_portal_revision_configs_type"),
    )

    # Seed one row per portal type. Idempotent, so a partially-applied run and the
    # shared dev database both re-run cleanly.
    for entity_type, is_enabled, statuses in _CONFIG_SEED:
        op.execute(
            sa.text(
                "INSERT INTO portal_revision_configs "
                "(id, source_entity_type, is_enabled, max_revisions, allowed_statuses, restart_stage_code) "
                "VALUES (gen_random_uuid(), :t, :e, NULL, CAST(:s AS jsonb), NULL) "
                "ON CONFLICT (source_entity_type) DO NOTHING"
            ).bindparams(
                t=entity_type,
                e=is_enabled,
                s=_json_array(statuses),
            )
        )

    op.add_column(
        "system_settings",
        sa.Column("portal_revisions_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.add_column(
        "system_settings",
        sa.Column("portal_max_revisions", sa.Integer(), nullable=False, server_default=sa.text("2")),
    )

    for table in ("stock_inquiries", "purchase_requests"):
        op.add_column(
            table,
            sa.Column("revision_no", sa.Integer(), nullable=False, server_default=sa.text("0")),
        )
        op.add_column(table, sa.Column("last_revised_at", sa.DateTime(timezone=False), nullable=True))

    op.add_column(
        "conversation_sla_tracking",
        sa.Column("voided_at", sa.DateTime(timezone=False), nullable=True),
    )
    op.add_column(
        "conversation_sla_tracking",
        sa.Column("void_reason", sa.String(length=50), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("conversation_sla_tracking", "void_reason")
    op.drop_column("conversation_sla_tracking", "voided_at")

    for table in ("purchase_requests", "stock_inquiries"):
        op.drop_column(table, "last_revised_at")
        op.drop_column(table, "revision_no")

    op.drop_column("system_settings", "portal_max_revisions")
    op.drop_column("system_settings", "portal_revisions_enabled")

    op.drop_table("portal_revision_configs")
    op.drop_index("ix_portal_form_revisions_source_entity", table_name="portal_form_revisions")
    op.drop_table("portal_form_revisions")
