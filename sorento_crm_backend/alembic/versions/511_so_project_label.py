"""add sales_orders.project_label / project_label_source, backfill from existing notes

Revision ID: 511_so_project_label
Revises: 510_strip_rtf_so_notes
Create Date: 2026-09-10

PLAN-so-project-label.md. Two columns, no table, no registry - see
`app/services/project_label_rules.py` for the precedence rules and every writer.

The backfill reads the plain-text `internal_note` every row already carries (this chains
on `510_strip_rtf_so_notes`, so the RTF has already been stripped) and, for a note that
starts `Order Inquiry project:` (the importer's own marker), applies rule 1 to the
remainder with source `inquiry`; every other note goes through `label_from_note` (rule 2).
Rule 3 (`Ref`) has no backfill source - `Ref` is not on the AutoCount push contract until
this same lane adds it, so no row in this book carries one yet.

Batched by id, same shape as `510_strip_rtf_so_notes`: `id > last_id`, `BATCH_SIZE` rows a
round, never one `fetchall()` of the whole table. `backfill_project_labels` is a module
function so a test can call it directly.

Downgrade drops both columns - the labels are re-derivable from the note, so there is
nothing to lose.
"""
from types import SimpleNamespace

from alembic import op
import sqlalchemy as sa

from app.services.project_label_rules import (
    apply_project_label,
    label_from_inquiry_cell,
    label_from_note,
)

# revision identifiers, used by Alembic.
revision = "511_so_project_label"
down_revision = "510_strip_rtf_so_notes"
branch_labels = None
depends_on = None

_TABLE = "sales_orders"
BATCH_SIZE = 1000

#: The importer's own marker (`project_order_inquiry_import_service.py`) for a provisional
#: order it created and could not match to a customer - the whole Order Inquiry cell rides
#: after the colon, so rule 1 (customer/project split) applies to it, not rule 2 (note).
_INQUIRY_NOTE_PREFIX = "Order Inquiry project:"


def _label_and_source_for_note(note: str | None) -> tuple[str | None, str | None]:
    if note and note.strip().startswith(_INQUIRY_NOTE_PREFIX):
        cell = note.strip()[len(_INQUIRY_NOTE_PREFIX) :].strip()
        label = label_from_inquiry_cell(cell)
        return (label, "inquiry") if label else (None, None)
    return label_from_note(note)


def backfill_project_labels(connection, batch_size: int = BATCH_SIZE) -> int:
    """Derives `project_label`/`project_label_source` from every row's existing note.

    Returns the row count visited. Idempotent and precedence-respecting: a row that
    already carries a higher-ranked label (`apply_project_label`'s own gate) is read but
    left unwritten, so re-running this after a manual correction or a later importer run
    cannot regress it.
    """
    total = 0
    last_id = ""
    while True:
        rows = connection.execute(
            sa.text(
                f"""
                SELECT id, internal_note, project_label, project_label_source
                FROM {_TABLE}
                WHERE id::text > :last_id
                ORDER BY id
                LIMIT :batch_size
                """
            ),
            {"last_id": last_id, "batch_size": batch_size},
        ).fetchall()
        if not rows:
            break
        for row in rows:
            label, source = _label_and_source_for_note(row.internal_note)
            holder = SimpleNamespace(
                project_label=row.project_label,
                project_label_source=row.project_label_source,
            )
            if apply_project_label(holder, label, source):
                connection.execute(
                    sa.text(
                        f"""
                        UPDATE {_TABLE}
                        SET project_label = :label, project_label_source = :source
                        WHERE id = :id
                        """
                    ),
                    {"label": holder.project_label, "source": holder.project_label_source, "id": row.id},
                )
            total += 1
        last_id = str(rows[-1].id)
    return total


def upgrade() -> None:
    op.add_column(_TABLE, sa.Column("project_label", sa.Text(), nullable=True))
    op.add_column(_TABLE, sa.Column("project_label_source", sa.String(length=16), nullable=True))
    backfill_project_labels(op.get_bind())


def downgrade() -> None:
    op.drop_column(_TABLE, "project_label_source")
    op.drop_column(_TABLE, "project_label")
