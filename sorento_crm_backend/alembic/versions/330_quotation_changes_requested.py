"""The customer's other answer: "not as it stands".

S17. A counter-sign page that only offers Accept sends every customer who wants a lower price out
of the system to say so, and the feedback never comes back. These three columns capture it on the
ISSUE, beside `accepted_at`, because both are decisions about the same revision.

No backfill: an issue that was never sent back for changes has genuinely never been sent back for
changes, and NULL is the honest reading of every existing row.

Revision ID: 330_quotation_changes_req
Revises: 329_quotation_templates
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy import text


revision = "330_quotation_changes_req"
down_revision = "329_quotation_templates"
branch_labels = None
depends_on = None

TABLE = "project_quotation_issues"

COLUMNS = (
    ("changes_requested_at", sa.Column("changes_requested_at", sa.DateTime(), nullable=True)),
    ("changes_requested_note", sa.Column("changes_requested_note", sa.Text(), nullable=True)),
    (
        "changes_requested_by_name",
        sa.Column("changes_requested_by_name", sa.String(200), nullable=True),
    ),
)


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    return bool(
        bind.execute(
            text(
                "select 1 from information_schema.columns "
                "where table_name = :t and column_name = :c"
            ),
            {"t": table, "c": column},
        ).scalar()
    )


def upgrade() -> None:
    for name, column in COLUMNS:
        if not _has_column(TABLE, name):
            op.add_column(TABLE, column)


def downgrade() -> None:
    for name, _column in reversed(COLUMNS):
        if _has_column(TABLE, name):
            op.drop_column(TABLE, name)
