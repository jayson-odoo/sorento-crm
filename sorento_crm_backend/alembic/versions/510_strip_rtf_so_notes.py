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

Batched by id (`BATCH_SIZE` rows per round), not one `SELECT ... WHERE left(...)`
sweep: `strip_rtf`'s own fallback (app/utils/rtf.py) leaves a row's note
UNCHANGED when `rtf_to_text` cannot parse it, so re-running the same WHERE
clause after writing that row back would select it again forever. Paginating
by `id > last_id` guarantees the cursor moves forward every round regardless
of whether any given row's content actually changed.
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
BATCH_SIZE = 1000


def strip_rtf_notes(connection, batch_size: int = BATCH_SIZE) -> int:
    """Rewrite every RTF-wrapped note to plain text. Returns the row count visited.

    A module-level function (rather than inline in `upgrade()`) so the test suite
    can call it directly against its own session/connection.
    """
    total = 0
    last_id = ""
    while True:
        rows = connection.execute(
            sa.text(
                f"""
                SELECT id, internal_note FROM {_TABLE}
                WHERE left(internal_note, 5) = '{{\\rtf' AND id::text > :last_id
                ORDER BY id
                LIMIT :batch_size
                """
            ),
            {"last_id": last_id, "batch_size": batch_size},
        ).fetchall()
        if not rows:
            break
        for row in rows:
            connection.execute(
                sa.text(f"UPDATE {_TABLE} SET internal_note = :note WHERE id = :id"),
                {"note": strip_rtf(row.internal_note), "id": row.id},
            )
            total += 1
        last_id = str(rows[-1].id)
    return total


def upgrade() -> None:
    strip_rtf_notes(op.get_bind())


def downgrade() -> None:
    # No-op - see module docstring.
    pass
