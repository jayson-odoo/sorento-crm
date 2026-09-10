"""strip RTF wrapper off sales_orders.internal_note for rows already landed

Revision ID: 510_strip_rtf_so_notes
Revises: 509_merge_508_summary_exclwh
Create Date: 2026-09-10

AutoCount's note control pushes the field wrapped in raw RTF
(`{\\rtf1\\ansi...}`); `CanonicalSalesOrder`'s validator (app/utils/rtf.py)
now cleans every future push, but rows that landed before that validator
existed still carry the RTF verbatim. This backfills them once.

`left(internal_note, 5) = '{\\rtf'` rather than `LIKE '{\\rtf%'`: Postgres's
LIKE treats a bare backslash in the pattern as an escape character (it
swallows itself), so that pattern silently matches NOTHING - the plain
prefix comparison is what actually finds the rows.

Downgrade is a no-op: the original RTF is not kept anywhere, so there is
nothing to restore it from.
"""
from alembic import op
import sqlalchemy as sa

from app.utils.rtf import strip_rtf

# revision identifiers, used by Alembic.
revision = "510_strip_rtf_so_notes"
down_revision = "509_merge_508_summary_exclwh"
branch_labels = None
depends_on = None

_TABLE = "sales_orders"


def strip_rtf_notes(connection) -> int:
    """Rewrite every RTF-wrapped note to plain text. Returns the row count touched.

    A module-level function (rather than inline in `upgrade()`) so the test suite
    can call it directly against the pg fixture's own scratch schema.
    """
    rows = connection.execute(
        sa.text(f"SELECT id, internal_note FROM {_TABLE} WHERE left(internal_note, 5) = '{{\\rtf'")
    ).fetchall()
    for row in rows:
        connection.execute(
            sa.text(f"UPDATE {_TABLE} SET internal_note = :note WHERE id = :id"),
            {"note": strip_rtf(row.internal_note), "id": row.id},
        )
    return len(rows)


def upgrade() -> None:
    strip_rtf_notes(op.get_bind())


def downgrade() -> None:
    # No-op - see module docstring.
    pass
