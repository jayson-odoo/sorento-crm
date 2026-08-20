"""portal revision drafts

Captain 2026-08-20: Revise on a portal submission was client-side only - nothing
persisted until Send revision, so the form's "Draft" status pill promised a save
that did not exist. `portal_revision_drafts` makes it real: one open draft per
submission, keyed the same way `portal_form_revisions` is (`source_entity_type`,
`source_entity_id`), deliberately NOT company-scoped for the same reason (see
`app.models.portal.PortalRevisionDraft`).

Revision ID: b6d2f4a8c7e1
Revises: f3a8c6d9e1b2
Create Date: 2026-08-20 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'b6d2f4a8c7e1'
down_revision = 'f3a8c6d9e1b2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'portal_revision_drafts',
        sa.Column('id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('source_entity_type', sa.String(length=50), nullable=False),
        sa.Column('source_entity_id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('contact_id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('base_revision_no', sa.Integer(), nullable=False),
        sa.Column(
            'payload_json',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=False), server_default=sa.func.now(), nullable=False),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=False),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'source_entity_type', 'source_entity_id', name='uq_portal_revision_drafts_entity'
        ),
    )
    op.create_index(
        'ix_portal_revision_drafts_contact_id', 'portal_revision_drafts', ['contact_id']
    )


def downgrade() -> None:
    op.drop_index('ix_portal_revision_drafts_contact_id', table_name='portal_revision_drafts')
    op.drop_table('portal_revision_drafts')
