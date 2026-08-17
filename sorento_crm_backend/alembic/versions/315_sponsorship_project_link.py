"""Sponsorship-to-project link and the per-contact rollout flag (S4, AC-F3/AC-F4).

Revision ID: 315_sponsorship_link
Revises: 314_project_samples_pos

Two columns, both additive and both nullable-or-defaulted, so every existing sponsorship
and every existing contact keeps behaving exactly as it does today:

- ``purchase_requests.project_id`` -- ONE form, not two (AC-F3). ``project_title`` stays
  as the display fallback (AC-F6): the ~28 real rows are linked BY HAND afterwards, and
  no fuzzy backfill writes a link nobody checked.
- ``respond_contacts.requires_registered_project`` -- the rollout switch, per contact
  (AC-F4). Defaults to false, which is what makes this deployable without a flag day.

ON DELETE SET NULL rather than CASCADE: deleting a project must never delete a
sponsorship form, which is an approved spend document with its own audit trail.
"""
from alembic import op

revision = "315_sponsorship_link"
down_revision = "314_project_samples_pos"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE purchase_requests
            ADD COLUMN IF NOT EXISTS project_id UUID
            REFERENCES projects(id) ON DELETE SET NULL;
        -- Partial: only sponsorship rows carry a link worth indexing, and the rollup
        -- always filters on request_type anyway.
        CREATE INDEX IF NOT EXISTS ix_purchase_requests_project
            ON purchase_requests (project_id)
            WHERE project_id IS NOT NULL;

        ALTER TABLE respond_contacts
            ADD COLUMN IF NOT EXISTS requires_registered_project BOOLEAN
            NOT NULL DEFAULT false;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP INDEX IF EXISTS ix_purchase_requests_project;
        ALTER TABLE purchase_requests DROP COLUMN IF EXISTS project_id;
        ALTER TABLE respond_contacts DROP COLUMN IF EXISTS requires_registered_project;
        """
    )
