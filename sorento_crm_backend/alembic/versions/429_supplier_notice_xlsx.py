"""F4: a container request keeps the supplier's own sheet beside its PDF.

Revision ID: 429_supplier_notice_xlsx
Revises: 428_scm_pi_cbm_adjust_revision
Create Date: 2026-08-26

The notice already stores ONE document (`document_filename` / `storage_provider` /
`storage_key`, the PDF). F4 sends a second file in the same email: the supplier's stock list
handed back with a `需装数量 / Qty to load` column (AC-C1, AC-C2).

Three columns rather than a documents table. A notice has exactly two files, both minted in
one act by one writer, and neither is ever added to afterwards - a child table would buy
nothing today and cost a join on every read (`PRINCIPLES.md`, simplest thing that works). The
condition that would change that: a notice needing an OPEN-ENDED set of attachments, e.g. the
supplier replying onto the same record.

STORED, not regenerated on demand. The supplier's stock list is a full-replace snapshot, so
rebuilding the sheet a month later would answer with today's holdings under the quantities we
asked for in July. A notice is a copy, not a view - the rule `supplier_notice.py` opens with.

Nothing to backfill: the notices already on file were sent with a PDF alone, and inventing an
xlsx for them would claim a supplier received a file they never did. They read as "no
spreadsheet", which is exactly true.
"""
import sqlalchemy as sa
from alembic import op

revision = "429_supplier_notice_xlsx"
down_revision = "428_scm_pi_cbm_adjust_revision"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "supplier_notices", sa.Column("xlsx_filename", sa.String(255), nullable=True)
    )
    op.add_column(
        "supplier_notices", sa.Column("xlsx_storage_provider", sa.String(16), nullable=True)
    )
    op.add_column(
        "supplier_notices", sa.Column("xlsx_storage_key", sa.String(512), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("supplier_notices", "xlsx_storage_key")
    op.drop_column("supplier_notices", "xlsx_storage_provider")
    op.drop_column("supplier_notices", "xlsx_filename")
