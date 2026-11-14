"""Allow two files of the same name in one folder (FILES-MOVE-DUPLICATE).

Owner ruling, 12 Nov 2026: "files we should allow same name, google drive also can".
Migration 198 created ``ux_attachments_dir_lower_filename_active``, a partial UNIQUE index on
(directory_id, lower(original_filename)) for active rows. It made a move into a folder holding
the same name a 500, and its rule no longer exists. The app now asks the user (Keep both /
Rename / Replace / Skip) whenever an action would put a second file of the same visible name
into a folder; nothing in the database enforces it any more.

Dropped CONCURRENTLY in an autocommit block, so no write to ``attachments`` waits on it.
Nothing is rewritten: the drop only removes the index. ``ix_attachments_directory_id`` still
serves the per-folder name checks.

Downgrade recreates the index. It FAILS if the folder now holds same-name pairs (allowed since
this revision); rename or move those first.

Revision ID: fmd_0001_drop_dir_name_unique
Revises: spr_0001_spare_part_request
"""
from alembic import op


revision = "fmd_0001_drop_dir_name_unique"
down_revision = "spr_0001_spare_part_request"
branch_labels = None
depends_on = None

INDEX_NAME = "ux_attachments_dir_lower_filename_active"


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {INDEX_NAME}")


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(
            f"""
            CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS {INDEX_NAME}
            ON attachments (directory_id, lower(original_filename))
            WHERE directory_id IS NOT NULL AND is_deleted = false
            """
        )
