"""Record who created a GRN, and how.

The reported problem: a Mocha GRN existed as a Sorento row and nobody could say
who put it there. `picking_headers` recorded no author, so provenance could only
be guessed by bracketing `created_at` against `import_jobs` - and that guess is
wrong in two ways:

* A re-import UPDATES an existing header, and the import reported every success as
  `created`, so the last person to re-run the file looked like its author.
* The external (n8n / AutoCount) path - `POST /api/v1/external/grn/` - creates
  GRNs with no import job, no user and no audit row at all, so bracketing finds
  nothing. Worse, an external call with no `contact_id`/`space_id` resolves to the
  all-companies scope and the insert auto-stamp then files the row under the
  INCUMBENT company (Sorento). That is how Mocha documents became Sorento rows.

Three columns, written ONCE on insert and never touched by a re-import, so the
answer survives an overwrite:

  created_by      staff user id; NULL for external-API writes
  source_system   'ui' | 'import' | 'external_api'
  import_job_id   the job -> its file, uploader, and company snapshot

No backfill. Historical rows genuinely do not know, and inventing an author from
the nearest import job would bake in exactly the wrong guess this migration
exists to stop. They stay NULL, which reads as "unknown" rather than as a lie.

Revision ID: 318_picking_header_provenance
Revises: 317_picking_header_spo_width
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "318_picking_header_provenance"
down_revision = "317_picking_header_spo_width"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("picking_headers", sa.Column("created_by", UUID(as_uuid=False), nullable=True))
    op.add_column("picking_headers", sa.Column("source_system", sa.String(length=30), nullable=True))
    op.add_column("picking_headers", sa.Column("import_job_id", UUID(as_uuid=False), nullable=True))
    op.create_foreign_key(
        "fk_picking_headers_import_job_id",
        "picking_headers",
        "import_jobs",
        ["import_job_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_picking_headers_import_job_id", "picking_headers", ["import_job_id"])
    op.create_index("ix_picking_headers_created_by", "picking_headers", ["created_by"])


def downgrade() -> None:
    op.drop_index("ix_picking_headers_created_by", table_name="picking_headers")
    op.drop_index("ix_picking_headers_import_job_id", table_name="picking_headers")
    op.drop_constraint("fk_picking_headers_import_job_id", "picking_headers", type_="foreignkey")
    op.drop_column("picking_headers", "import_job_id")
    op.drop_column("picking_headers", "source_system")
    op.drop_column("picking_headers", "created_by")
