"""A flyer somebody uploaded, kept as a READING rather than as a report.

`dealer_kit.flyer_reading` holds what the extractor read off the PDF: the pages,
the cards, the printed rows, the artwork. It deliberately does NOT hold the match
report - what each code resolved to, what missed, what the linked promotion does
not carry. That is derived from this reading against the product master and
recomputed on every read.

Storing the report would freeze an answer that is only true for the master it was
computed against. Create one of the products it listed as missing and the stored
answer is wrong, in the direction that costs money: it tells marketing to close
gaps that are already closed, and nothing on the screen says the number is stale.
Recomputing the real flyer's 998 codes costs 0.4s and three statements.

The bytes are not kept either. `sha256` answers "is this the same PDF as
Tuesday's" without a file store, and the original document lives wherever
marketing keeps it.

**Applied to the shared dev database by hand, NOT stamped.** That database is
stamped at another worktree's revision, so `alembic upgrade` cannot run here and
the DDL below was executed against it directly. Every statement is therefore
idempotent (IF NOT EXISTS / a pg_constraint probe), so this revision is a no-op
where it has already been applied and still correct on a database that has never
seen it.

Revision ID: 316_dealer_kit_flyer_reading
Revises: 315_dealer_kit_page_promotion
"""

from alembic import op

revision = "316_dealer_kit_flyer_reading"
down_revision = "315_dealer_kit_page_promotion"
branch_labels = None
depends_on = None

COMPANY_FK = "fk_dealer_kit_flyer_reading_company"


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS dealer_kit.flyer_reading (
            id            uuid PRIMARY KEY,
            filename      varchar(255) NOT NULL,
            byte_size     integer NOT NULL,
            sha256        varchar(64) NOT NULL,
            reading_json  jsonb NOT NULL,
            created_by    uuid,
            company_id    uuid,
            created_at    timestamp without time zone NOT NULL DEFAULT now()
        )
        """
    )
    # Postgres has no ADD CONSTRAINT IF NOT EXISTS, so probe the catalog.
    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = '{COMPANY_FK}'
            ) THEN
                ALTER TABLE dealer_kit.flyer_reading
                ADD CONSTRAINT {COMPANY_FK}
                FOREIGN KEY (company_id) REFERENCES companies (id);
            END IF;
        END
        $$
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_dealer_kit_flyer_reading_company_id
        ON dealer_kit.flyer_reading (company_id)
        """
    )
    # The list screen's only query: this company's readings, newest first.
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_dealer_kit_flyer_reading_company_created
        ON dealer_kit.flyer_reading (company_id, created_at)
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS dealer_kit.flyer_reading")
