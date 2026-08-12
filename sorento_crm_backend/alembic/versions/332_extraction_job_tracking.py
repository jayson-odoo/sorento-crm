"""Record WHICH job is reading a document, and WHEN it started (S20).

Four nullable columns, two on each of the document version tables:

* ``extraction_job_id``   - the RQ job that is reading this version.
* ``extraction_started_at`` - the moment the reader actually picked the document up.

Both exist because of one thing measured on 2026-08-08: a customer PO sat on screen as
"Waiting to be read", 10 pages, 0 lines, indefinitely. The RQ work-horse had been killed
with signal 15 and RQ had correctly moved the job to its FailedJobRegistry, but the row
still said ``running``, because the task writes its failure inside an ``except`` block and
an ``except`` block never runs when the process is killed. Nothing inside a dying process
can report its own death, so something outside has to, and the only honest way to tell a
dead read from a slow one is to ask RQ about the job itself - which needs the job's id on
the row. ``extraction_started_at`` is the fallback for rows carrying no job id, and is also
what lets the screen say "4 minutes so far" rather than showing an unbounded spinner.

**No backfill, deliberately.** Existing rows genuinely have no job id and no start time -
the information was never recorded and cannot be reconstructed, and inventing one would
make the reconciler trust a fiction. Rows that predate this take the age path in
``project_extraction_recovery_service``, which measures from ``created_at`` (already on
both tables) against a floor set past the RQ job timeout. So the existing stranded rows are
recovered by the same code that prevents new ones, without a one-off script.

Defensively re-runnable, because the dev database is a copy of production and this branch's
revisions have been applied there by hand.

Revision ID: 332_extraction_job_tracking
Revises: dd96502280be
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy import text


revision = "332_extraction_job_tracking"
down_revision = "331_project_series_products"
branch_labels = None
depends_on = None


_TABLES = ("project_po_versions", "delivery_schedule_versions")
_COLUMNS = (
    ("extraction_job_id", sa.String(length=64)),
    ("extraction_started_at", sa.DateTime(timezone=False)),
)


def _has_column(table: str, column: str) -> bool:
    return bool(
        op.get_bind()
        .execute(
            text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = :t AND column_name = :c"
            ),
            {"t": table, "c": column},
        )
        .scalar()
    )


def upgrade() -> None:
    for table in _TABLES:
        for name, type_ in _COLUMNS:
            if not _has_column(table, name):
                op.add_column(table, sa.Column(name, type_, nullable=True))


def downgrade() -> None:
    for table in _TABLES:
        for name, _type in _COLUMNS:
            if _has_column(table, name):
                op.drop_column(table, name)
