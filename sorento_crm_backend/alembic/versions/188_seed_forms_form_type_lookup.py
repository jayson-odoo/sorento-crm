"""Seed configurable form type lookup set.

Revision ID: 188_forms_form_type_lookup
Revises: 187_respond_contact_access_types_m2m
Create Date: 2026-05-12
"""
import sqlalchemy as sa
from alembic import op


revision = "188_forms_form_type_lookup"
down_revision = "187_respond_contact_access_types_m2m"
branch_labels = None
depends_on = None


FORM_TYPE_OPTIONS = (
    ("marketing", "Marketing", 10),
    ("registration", "Registration", 20),
    ("application", "Application", 30),
    ("feedback", "Feedback", 40),
    ("survey", "Survey", 50),
    ("complaint", "Complaint", 60),
    ("internal", "Internal", 70),
    ("other", "Other", 80),
)


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            INSERT INTO lookup_sets (id, tenant_id, set_key, name, description, is_active)
            SELECT
                gen_random_uuid(),
                NULL,
                'forms_form_type',
                'Forms - Form Types',
                'Configurable form type values used by Forms Management and MCP responses.',
                TRUE
            WHERE NOT EXISTS (
                SELECT 1 FROM lookup_sets
                WHERE tenant_id IS NULL AND set_key = 'forms_form_type'
            )
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE lookup_sets
            SET name = 'Forms - Form Types',
                description = 'Configurable form type values used by Forms Management and MCP responses.',
                is_active = TRUE,
                updated_at = now()
            WHERE tenant_id IS NULL AND set_key = 'forms_form_type'
            """
        )
    )

    for value, label, sort_order in FORM_TYPE_OPTIONS:
        op.execute(
            sa.text(
                """
                INSERT INTO lookup_options (id, set_id, value, label, sort_order, is_active)
                SELECT gen_random_uuid(), s.id, :value, :label, :sort_order, TRUE
                FROM (
                    SELECT id
                    FROM lookup_sets
                    WHERE tenant_id IS NULL AND set_key = 'forms_form_type'
                    ORDER BY created_at ASC, id ASC
                    LIMIT 1
                ) s
                ON CONFLICT (set_id, lower(value)) DO UPDATE
                SET label = EXCLUDED.label,
                    sort_order = EXCLUDED.sort_order,
                    is_active = TRUE,
                    updated_at = now()
                """
            ).bindparams(value=value, label=label, sort_order=sort_order)
        )

    op.execute(
        sa.text(
            """
            UPDATE lookup_bindings b
            SET set_id = s.id,
                updated_at = now()
            FROM (
                SELECT id
                FROM lookup_sets
                WHERE tenant_id IS NULL AND set_key = 'forms_form_type'
                ORDER BY created_at ASC, id ASC
                LIMIT 1
            ) s
            WHERE b.tenant_id IS NULL
              AND b.table_name = 'forms'
              AND b.column_name = 'form_type'
            """
        )
    )
    op.execute(
        sa.text(
            """
            INSERT INTO lookup_bindings (id, tenant_id, set_id, table_name, column_name)
            SELECT gen_random_uuid(), NULL, s.id, 'forms', 'form_type'
            FROM (
                SELECT id
                FROM lookup_sets
                WHERE tenant_id IS NULL AND set_key = 'forms_form_type'
                ORDER BY created_at ASC, id ASC
                LIMIT 1
            ) s
            WHERE NOT EXISTS (
                SELECT 1 FROM lookup_bindings b
                WHERE b.tenant_id IS NULL
                  AND b.table_name = 'forms'
                  AND b.column_name = 'form_type'
            )
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            DELETE FROM lookup_bindings
            WHERE tenant_id IS NULL
              AND table_name = 'forms'
              AND column_name = 'form_type'
              AND set_id IN (
                  SELECT id FROM lookup_sets
                  WHERE tenant_id IS NULL AND set_key = 'forms_form_type'
              )
            """
        )
    )
    op.execute(
        sa.text(
            """
            DELETE FROM lookup_sets
            WHERE tenant_id IS NULL AND set_key = 'forms_form_type'
            """
        )
    )
