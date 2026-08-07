"""Per-contact attachment-type grants.

`crm_resource_attachments_list` serves only types flagged `is_direct_access` - one
global boolean, so a document is either dealer-downloadable for everyone or
reachable by nobody. Today that means exactly 9 files out of 3,348.

That is too blunt for the Container Status workbook: the office needs it, dealers
must not have it, and there is no third setting. This adds the missing axis - a
contact may be granted additional types beyond the global baseline:

    visible types = types flagged is_direct_access        (unchanged for everyone)
                  ∪ types granted to this contact         (new)

**Inert by construction.** The baseline is untouched, so no contact loses a
document; grants only ever add. Chosen over enforcing `access_levels` per contact
(narrow-never-widen) precisely because that would change what existing callers
receive - anything omitting the parameter gets everything today - and a security
fix that also looks like a regression is hard to ship.

Note this does NOT close that gap: within a visible type, a contact still sees
every file regardless of `access_levels`. For Container Status the whole type is
sensitive, so type-level is the right granularity; for mixed types it is not, and
the enforcement remains worth building.

Revision ID: 315_contact_attachment_types
Revises: 314_eta_single_field
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "315_contact_attachment_types"
down_revision = "314_eta_single_field"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if "contact_attachment_types" in sa.inspect(bind).get_table_names():
        return

    op.create_table(
        "contact_attachment_types",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("contact_id", sa.Text(), nullable=False),
        sa.Column(
            "attachment_type_id",
            sa.dialects.postgresql.UUID(as_uuid=False),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=False),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("created_by", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["contact_id"], ["respond_contacts.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["attachment_type_id"], ["attachment_types.id"], ondelete="CASCADE"
        ),
        # A grant is present or absent - there is no "granted twice".
        sa.UniqueConstraint(
            "contact_id", "attachment_type_id", name="uq_contact_attachment_type"
        ),
    )
    op.create_index(
        "ix_contact_attachment_types_contact",
        "contact_attachment_types",
        ["contact_id"],
    )


def downgrade() -> None:
    op.drop_table("contact_attachment_types")
