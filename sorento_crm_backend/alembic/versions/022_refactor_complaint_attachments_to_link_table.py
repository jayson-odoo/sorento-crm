"""Refactor complaint_attachments to link table (complaint_id + attachment_id)

Revision ID: 022_complaint_attachments_link
Revises: 021_attachment_type_code
Create Date: 2026-01-29 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "022_complaint_attachments_link"
down_revision = "021_attachment_type_code"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    tables = inspector.get_table_names()

    if "complaint_attachments" not in tables:
        return

    # 1. Create new link table complaint_attachments_new
    op.create_table(
        "complaint_attachments_new",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("complaint_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("complaints.id", ondelete="CASCADE"), nullable=False),
        sa.Column("attachment_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("attachments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("sort_order", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=False), nullable=True),
    )
    op.create_index("ix_complaint_attachments_new_complaint_id", "complaint_attachments_new", ["complaint_id"])
    op.create_index("ix_complaint_attachments_new_attachment_id", "complaint_attachments_new", ["attachment_id"])
    op.create_unique_constraint("uq_complaint_attachment", "complaint_attachments_new", ["complaint_id", "attachment_id"])

    # 2. Get complaint_document attachment type id
    result = connection.execute(text("SELECT id FROM attachment_types WHERE code = 'complaint_document' LIMIT 1"))
    type_row = result.fetchone()
    if not type_row:
        # No type yet; skip data migration (021 may not have run or type was not created)
        op.drop_table("complaint_attachments")
        op.rename_table("complaint_attachments_new", "complaint_attachments")
        return

    type_id = type_row[0]

    # 3. Migrate data: for each old row, create Attachment and link
    old_rows = connection.execute(
        text("SELECT id, complaint_id, file_name, file_url, file_size_bytes, uploaded_at FROM complaint_attachments")
    ).fetchall()

    for row in old_rows:
        old_id, complaint_id, file_name, file_url, file_size_bytes, uploaded_at = row
        file_name = file_name or "document"
        file_url = file_url or ""
        # stored_filename: use file_name or generate
        stored_filename = file_name[:255] if file_name else "document"
        if len(stored_filename) > 255:
            stored_filename = stored_filename[:255]
        file_path = (file_url[:500]) if file_url else "/"
        size_int = int(file_size_bytes) if file_size_bytes is not None else None

        # Insert attachment (attachments table has uploaded_at, no created_at)
        ins_att = text(
            "INSERT INTO attachments (id, attachment_type_id, original_filename, stored_filename, file_path, file_size_bytes, uploaded_at) "
            "VALUES (gen_random_uuid(), :type_id, :orig, :stored, :path, :size, COALESCE(:up_at, now() AT TIME ZONE 'utc')) "
            "RETURNING id"
        )
        r = connection.execute(
            ins_att,
            {
                "type_id": type_id,
                "orig": file_name[:255],
                "stored": stored_filename,
                "path": file_path,
                "size": size_int,
                "up_at": uploaded_at,
            },
        )
        att_row = r.fetchone()
        if not att_row:
            continue
        attachment_id = att_row[0]

        # Insert link
        connection.execute(
            text(
                "INSERT INTO complaint_attachments_new (id, complaint_id, attachment_id, is_primary, sort_order, created_at) "
                "VALUES (gen_random_uuid(), :complaint_id, :attachment_id, true, 0, COALESCE(:up_at, now() AT TIME ZONE 'utc'))"
            ),
            {"complaint_id": complaint_id, "attachment_id": attachment_id, "up_at": uploaded_at},
        )

    # 4. Drop old table and rename new one
    op.drop_table("complaint_attachments")
    op.rename_table("complaint_attachments_new", "complaint_attachments")


def downgrade() -> None:
    # Recreating the old structure would require extracting file data from attachments
    # and losing the link; for safety we only drop the link table and recreate the old shape empty.
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    tables = inspector.get_table_names()

    if "complaint_attachments" not in tables:
        return

    op.drop_table("complaint_attachments")
    op.create_table(
        "complaint_attachments",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("complaint_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("complaints.id", ondelete="CASCADE"), nullable=False),
        sa.Column("file_name", sa.Text(), nullable=True),
        sa.Column("file_url", sa.Text(), nullable=True),
        sa.Column("file_size_bytes", sa.Numeric(20, 0), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_complaint_attachments_complaint_id", "complaint_attachments", ["complaint_id"])
