"""PS-QUOTE-MATRIX: quotation grid scopes and customer feedback notes

* ``projects.quotation_versions.matrix_columns`` JSONB NULL (the scope's column headers).
* ``projects.quotation_lines.qty_cells`` JSONB NULL (a quantity per leaf column).
* ``projects.quotation_amendment_request_rows``: cell_key / note / hint_text / handled_at /
  handled_by; ``field`` also allows ``model_swap`` and ``note``; the (request, line, field)
  unique constraint becomes a unique index that also looks at cell_key. Decided rows are
  backfilled as handled.
* ``uq_quotation_amendment_requests_open`` is dropped: a customer may send feedback again.

Plan: documentation/plans/project-sales/PLAN-ps-quote-matrix-02nov.md. Additive and guarded so
a re-run, or a dev DB built by create_all, is harmless.

Revision ID: pqm_0001_quote_matrix
Revises: sask_0002_span_supplier
"""
from alembic import op

revision = "pqm_0001_quote_matrix"
down_revision = "sask_0002_span_supplier"
branch_labels = None
depends_on = None

ROWS = "projects.quotation_amendment_request_rows"


def upgrade() -> None:
    op.execute("ALTER TABLE projects.quotation_versions ADD COLUMN IF NOT EXISTS matrix_columns JSONB")
    op.execute("ALTER TABLE projects.quotation_lines ADD COLUMN IF NOT EXISTS qty_cells JSONB")
    op.execute(
        f"""
        ALTER TABLE {ROWS}
            ADD COLUMN IF NOT EXISTS cell_key VARCHAR(40),
            ADD COLUMN IF NOT EXISTS note TEXT,
            ADD COLUMN IF NOT EXISTS hint_text VARCHAR(200),
            ADD COLUMN IF NOT EXISTS handled_at TIMESTAMP,
            ADD COLUMN IF NOT EXISTS handled_by VARCHAR(100)
                REFERENCES public.users (id) ON DELETE SET NULL
        """
    )
    op.execute(f"ALTER TABLE {ROWS} DROP CONSTRAINT IF EXISTS ck_quotation_amendment_rows_field")
    op.execute(
        f"""
        ALTER TABLE {ROWS} ADD CONSTRAINT ck_quotation_amendment_rows_field
            CHECK (field IN ('quantity', 'unit_price', 'remove', 'model_swap', 'note'))
        """
    )
    op.execute(f"ALTER TABLE {ROWS} DROP CONSTRAINT IF EXISTS uq_quotation_amendment_rows_line_field")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_quotation_amendment_rows_line_field "
        f"ON {ROWS} (request_id, line_id, field, (COALESCE(cell_key, '')))"
    )
    # A row somebody already decided reads as handled.
    op.execute(
        f"""
        UPDATE {ROWS}
           SET handled_at = COALESCE(decided_at, created_at), handled_by = decided_by
         WHERE decision <> 'pending' AND handled_at IS NULL
        """
    )
    op.execute("DROP INDEX IF EXISTS projects.uq_quotation_amendment_requests_open")


def downgrade() -> None:
    # Several open requests per issue are normal now; the old index allows one, so all but the
    # newest open request of each issue are closed as superseded before it comes back.
    op.execute(
        """
        UPDATE projects.quotation_amendment_requests
           SET status = 'superseded'
         WHERE status = 'open'
           AND id NOT IN (
                SELECT DISTINCT ON (issue_id) id
                  FROM projects.quotation_amendment_requests
                 WHERE status = 'open'
                 ORDER BY issue_id, submitted_at DESC, id DESC
           )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_quotation_amendment_requests_open "
        "ON projects.quotation_amendment_requests (issue_id) WHERE status = 'open'"
    )
    # Rows of the new kinds, or pointing at a cell, cannot live under the old constraints.
    op.execute(f"DELETE FROM {ROWS} WHERE field IN ('model_swap', 'note') OR cell_key IS NOT NULL")
    op.execute(f"DROP INDEX IF EXISTS projects.uq_quotation_amendment_rows_line_field")
    op.execute(
        f"ALTER TABLE {ROWS} ADD CONSTRAINT uq_quotation_amendment_rows_line_field "
        "UNIQUE (request_id, line_id, field)"
    )
    op.execute(f"ALTER TABLE {ROWS} DROP CONSTRAINT IF EXISTS ck_quotation_amendment_rows_field")
    op.execute(
        f"""
        ALTER TABLE {ROWS} ADD CONSTRAINT ck_quotation_amendment_rows_field
            CHECK (field IN ('quantity', 'unit_price', 'remove'))
        """
    )
    op.execute(
        f"""
        ALTER TABLE {ROWS}
            DROP COLUMN IF EXISTS handled_by,
            DROP COLUMN IF EXISTS handled_at,
            DROP COLUMN IF EXISTS hint_text,
            DROP COLUMN IF EXISTS note,
            DROP COLUMN IF EXISTS cell_key
        """
    )
    op.execute("ALTER TABLE projects.quotation_lines DROP COLUMN IF EXISTS qty_cells")
    op.execute("ALTER TABLE projects.quotation_versions DROP COLUMN IF EXISTS matrix_columns")
