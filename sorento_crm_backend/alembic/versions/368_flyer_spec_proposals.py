"""What a flyer says about the products it names, kept as a reviewable batch (PR 5).

Two tables, in `public` with normal cross-schema foreign keys.

`product_spec_flyer_batches` is one proposal pass over one flyer reading: the dealer
kit reads the paper, this records master data's answer to "what does it SAY about
these products". It is not a column on `dealer_kit.flyer_reading` because it has its
own lifecycle (proposing / proposed / failed, its own counts, its own applied stamp),
and master-data lifecycle on a table another module owns and may drop is a coupling
nobody can see until the module is uninstalled.

`product_spec_flyer_proposals` is one key the flyer states about one product. The rows
are STORED rather than recomputed on read for two reasons: the apply request names
proposal ids and never values (so nothing on that path can put a figure of its own into
the product master), and a row remembers its own `outcome` after somebody has decided
about it.

UNIQUE on `flyer_reading_id`: one batch per reading. Re-proposing deletes the batch's
proposals and recomputes them against the master as it is NOW rather than accumulating a
second set; the record of what was ever applied lives in the spec provenance, which
survives the delete.

Both foreign keys CASCADE. A reading is working material a designer may delete, and a
proposal about a product that no longer exists is not an answer to anything. Nothing
that was APPLIED is lost with them - an applied value is on `product_specifications`,
written through the choke point, with the printed words as its evidence.

Every statement is idempotent (IF NOT EXISTS / a `pg_constraint` probe) so this is a
no-op on a database where it has already been applied by hand.

Revision ID: 368_flyer_spec_proposals
Revises: 367_promote_flyer_provenance
"""

from alembic import op

revision = "368_flyer_spec_proposals"
down_revision = "367_promote_flyer_provenance"
branch_labels = None
depends_on = None

_BATCHES = "product_spec_flyer_batches"
_PROPOSALS = "product_spec_flyer_proposals"

_FK_COMPANY = "fk_product_spec_flyer_batches_company"
_FK_READING = "fk_product_spec_flyer_batches_reading"
_FK_BATCH = "fk_product_spec_flyer_proposals_batch"
_FK_PRODUCT = "fk_product_spec_flyer_proposals_product"


def _add_constraint(table: str, name: str, clause: str) -> None:
    """ADD CONSTRAINT, skipped when it is already there.

    Postgres has no `ADD CONSTRAINT IF NOT EXISTS`, so the catalog is probed - the
    same shape migration 316 uses for this module's other cross-schema keys.
    """
    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = '{name}'
            ) THEN
                ALTER TABLE {table} ADD CONSTRAINT {name} {clause};
            END IF;
        END
        $$
        """
    )


def upgrade() -> None:
    op.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {_BATCHES} (
            id                uuid PRIMARY KEY,
            flyer_reading_id  uuid NOT NULL UNIQUE,
            status            varchar(16) NOT NULL DEFAULT 'proposing',
            error_message     text,
            job_id            varchar(64),
            product_count     integer NOT NULL DEFAULT 0,
            proposal_count    integer NOT NULL DEFAULT 0,
            new_count         integer NOT NULL DEFAULT 0,
            change_count      integer NOT NULL DEFAULT 0,
            conflict_count    integer NOT NULL DEFAULT 0,
            unchanged_count   integer NOT NULL DEFAULT 0,
            suppressed_count  integer NOT NULL DEFAULT 0,
            applied_count     integer NOT NULL DEFAULT 0,
            created_by        uuid,
            company_id        uuid,
            created_at        timestamp without time zone NOT NULL DEFAULT now(),
            finished_at       timestamp without time zone,
            applied_at        timestamp without time zone,
            applied_by        uuid
        )
        """
    )
    _add_constraint(
        _BATCHES,
        "ck_product_spec_flyer_batches_status",
        "CHECK (status IN ('proposing', 'proposed', 'failed'))",
    )
    _add_constraint(
        _BATCHES, _FK_COMPANY, "FOREIGN KEY (company_id) REFERENCES companies (id)"
    )
    _add_constraint(
        _BATCHES,
        _FK_READING,
        "FOREIGN KEY (flyer_reading_id) REFERENCES dealer_kit.flyer_reading (id) "
        "ON DELETE CASCADE",
    )
    op.execute(
        f"CREATE INDEX IF NOT EXISTS ix_{_BATCHES}_company_id ON {_BATCHES} (company_id)"
    )
    # The Master Data list's only query: every batch, newest first.
    op.execute(
        f"CREATE INDEX IF NOT EXISTS ix_product_spec_flyer_batches_created "
        f"ON {_BATCHES} (created_at)"
    )

    op.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {_PROPOSALS} (
            id             uuid PRIMARY KEY,
            batch_id       uuid NOT NULL,
            product_id     uuid NOT NULL,
            product_code   varchar(100) NOT NULL,
            pages          jsonb NOT NULL DEFAULT '[]'::jsonb,
            spec_key       varchar(100) NOT NULL,
            value          jsonb NOT NULL,
            unit           varchar(32),
            evidence       text NOT NULL DEFAULT '',
            kind           varchar(16) NOT NULL,
            stored_value   jsonb,
            stored_unit    varchar(32),
            stored_source  varchar(32),
            outcome        varchar(32),
            applied_at     timestamp without time zone,
            applied_by     uuid,
            created_at     timestamp without time zone NOT NULL DEFAULT now()
        )
        """
    )
    _add_constraint(
        _PROPOSALS,
        "ck_product_spec_flyer_proposals_kind",
        "CHECK (kind IN ('new', 'change', 'conflict', 'unchanged', 'suppressed'))",
    )
    _add_constraint(
        _PROPOSALS,
        _FK_BATCH,
        f"FOREIGN KEY (batch_id) REFERENCES {_BATCHES} (id) ON DELETE CASCADE",
    )
    _add_constraint(
        _PROPOSALS,
        _FK_PRODUCT,
        "FOREIGN KEY (product_id) REFERENCES products (id) ON DELETE CASCADE",
    )
    # One row per key per product per batch. A flyer printing a code on two pages is
    # one product, so the second card must not produce a row nobody can tell from the
    # first.
    _add_constraint(
        _PROPOSALS,
        "uq_product_spec_flyer_proposal",
        "UNIQUE (batch_id, product_id, spec_key)",
    )
    op.execute(
        f"CREATE INDEX IF NOT EXISTS ix_product_spec_flyer_proposals_batch "
        f"ON {_PROPOSALS} (batch_id)"
    )


def downgrade() -> None:
    # Proposals first: they hold the FK onto the batches.
    op.execute(f"DROP TABLE IF EXISTS {_PROPOSALS}")
    op.execute(f"DROP TABLE IF EXISTS {_BATCHES}")
