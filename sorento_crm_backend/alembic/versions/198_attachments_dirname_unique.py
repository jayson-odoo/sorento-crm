"""Google-Drive style dup-name guard on attachments.

Adds a partial UNIQUE index on (directory_id, lower(original_filename)) for
non-deleted attachments where directory_id IS NOT NULL. Existing duplicates
are renamed in-place with a " - copy", " - copy (2)", ... suffix on
``original_filename`` so the index can be created without violating uniqueness.

Revision ID: 198_attachments_dirname_unique
Revises: 197_system_setting_excel_extensions
Create Date: 2026-05-16
"""
from alembic import op


revision = "198_attachments_dirname_unique"
down_revision = "197_system_setting_excel_extensions"
branch_labels = None
depends_on = None


INDEX_NAME = "ux_attachments_dir_lower_filename_active"


def upgrade() -> None:
    bind = op.get_bind()

    # Rename existing duplicates so the partial UNIQUE index can be created
    # cleanly. For each (directory_id, lower(original_filename)) group with
    # >1 active row, keep the earliest-uploaded row's filename and rename
    # every subsequent sibling by appending " - copy", " - copy (2)", ...
    # right before the extension. Repeats until no collisions remain (handles
    # cascading collisions, e.g. an already-existing "x - copy.pdf").
    while True:
        result = bind.execute(
            __import__("sqlalchemy").text(
                """
                WITH dups AS (
                    SELECT id,
                           directory_id,
                           original_filename,
                           uploaded_at,
                           ROW_NUMBER() OVER (
                               PARTITION BY directory_id, lower(original_filename)
                               ORDER BY uploaded_at, id
                           ) AS rn
                    FROM attachments
                    WHERE is_deleted = false
                      AND directory_id IS NOT NULL
                )
                SELECT id, original_filename
                FROM dups
                WHERE rn > 1
                LIMIT 500
                """
            )
        ).fetchall()
        if not result:
            break
        for row in result:
            att_id = row[0]
            fname = row[1] or "file"
            new_name = _suffix_copy(fname)
            # Loop until a free name is found in the same directory.
            while _name_taken(bind, att_id, new_name):
                new_name = _suffix_copy(new_name)
            bind.execute(
                __import__("sqlalchemy").text(
                    "UPDATE attachments SET original_filename = :n WHERE id = :i"
                ),
                {"n": new_name, "i": att_id},
            )

    op.execute(
        f"""
        CREATE UNIQUE INDEX IF NOT EXISTS {INDEX_NAME}
        ON attachments (directory_id, lower(original_filename))
        WHERE directory_id IS NOT NULL AND is_deleted = false
        """
    )


def downgrade() -> None:
    op.execute(f"DROP INDEX IF EXISTS {INDEX_NAME}")


def _suffix_copy(name: str) -> str:
    """Append ' - copy' (or bump existing ' - copy (n)') before the extension."""
    import re

    if "." in name:
        base, _, ext = name.rpartition(".")
        ext = "." + ext
    else:
        base, ext = name, ""
    m = re.match(r"^(.*) - copy(?: \((\d+)\))?$", base)
    if m:
        stem = m.group(1)
        n = int(m.group(2) or "1") + 1
        return f"{stem} - copy ({n}){ext}"
    return f"{base} - copy{ext}"


def _name_taken(bind, current_id, candidate: str) -> bool:
    import sqlalchemy as sa

    row = bind.execute(
        sa.text(
            """
            SELECT 1
            FROM attachments
            WHERE is_deleted = false
              AND directory_id IS NOT NULL
              AND directory_id = (SELECT directory_id FROM attachments WHERE id = :i)
              AND lower(original_filename) = lower(:n)
              AND id != :i
            LIMIT 1
            """
        ),
        {"i": current_id, "n": candidate},
    ).fetchone()
    return row is not None
