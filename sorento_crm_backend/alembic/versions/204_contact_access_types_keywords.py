"""Add keywords JSONB column to contact_access_types for fuzzy access-level resolution.

Revision ID: 204_contact_access_types_keywords
Revises: 203_email_outbox_event_configs
Create Date: 2026-05-17

Admin-curated synonym list per access level. The MCP/backend matcher
(``ContactAccessTypeService.enforce_access_levels_for_contact``) consults this
list when resolving free-text AI / user phrasing - e.g. "customer" or
"homeowner" → ``end_user``; "reseller" → ``dealer`` - so admins do NOT have to
rename catalog rows to accommodate every caller variant.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "204_contact_access_types_keywords"
down_revision = "203_email_outbox_event_configs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "contact_access_types",
        sa.Column(
            "keywords",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    # Seed defaults for legacy bootstrap rows. Idempotent - only overwrites
    # when the existing value is still the empty JSONB array.
    op.execute(
        sa.text("""
            UPDATE contact_access_types
            SET keywords = CAST(:kw AS JSONB)
            WHERE code = 'end_user' AND keywords = '[]'::jsonb
        """).bindparams(kw='["customer","consumer","homeowner","b2c","end-user","enduser","user","client"]')
    )
    op.execute(
        sa.text("""
            UPDATE contact_access_types
            SET keywords = CAST(:kw AS JSONB)
            WHERE code = 'dealer' AND keywords = '[]'::jsonb
        """).bindparams(kw='["reseller","shop","retailer","distributor","b2b","trade"]')
    )


def downgrade() -> None:
    op.drop_column("contact_access_types", "keywords")
