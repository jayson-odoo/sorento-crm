"""Replace UNIQUE(customer_code) with composite functional UNIQUE on
(lower(btrim(customer_code)), lower(btrim(customer_name))).

Real Sage data ties a single debtor code to multiple distinct trading names:

    300-D093  →  Deluxe Home Center (KTN)
    300-D093  →  Deluxe Home Center AC (I)

The original unique constraint on `customer_code` forced the seed migration to
keep one row per code, collapsing those two debtors into one. This migration:

  1. Drops the column-level UNIQUE on customer_code (kept the plain index for
     lookups via migration 169 trigram + ix_customers_customer_code).
  2. Adds a functional UNIQUE INDEX on
     (lower(btrim(customer_code)), lower(btrim(customer_name))).

Migration 219 (re-sync) is updated below as well — both migrations should run
once before this one for the data to be clean enough to add the new index.

Revision ID: 220_customers_composite_unique
Revises: 219_resync_orders_customer_transporter
Create Date: 2026-06-01
"""
from __future__ import annotations

from alembic import op


revision = "220_customers_composite_unique"
down_revision = "219_resync_orders_customer_transporter"
branch_labels = None
depends_on = None


# Postgres auto-names the UNIQUE constraint on a column flagged unique=True as
# `<table>_<column>_key`. SQLAlchemy used the same convention when the table
# was originally created via Base.metadata.create_all, so we drop by that name.
_LEGACY_UNIQUE_CONSTRAINT = "customers_customer_code_key"
_NEW_UNIQUE_INDEX = "uq_customers_code_name_lower"


def upgrade() -> None:
    # 1. Drop the legacy column-level UNIQUE. Use IF EXISTS so a freshly-built
    #    DB (no legacy constraint) doesn't fail this migration.
    op.execute(
        f'ALTER TABLE customers DROP CONSTRAINT IF EXISTS {_LEGACY_UNIQUE_CONSTRAINT};'
    )

    # 2. Dedupe existing rows BEFORE the unique index is created. Production
    #    DBs already contain duplicate (lower(btrim(code)), lower(btrim(name)))
    #    pairs from earlier seed runs + manual edits — without merging them
    #    first the CREATE UNIQUE INDEX below fails with UniqueViolation.
    #
    #    Strategy per dup group:
    #      a. Pick canonical id = oldest created_at (ties broken by id ASC).
    #      b. Re-point EVERY FK that references customers.id (dynamically
    #         discovered via pg_catalog so future child tables don't need this
    #         migration revised).
    #      c. Delete the losing duplicate rows.
    op.execute(
        """
        DO $do$
        DECLARE
            grp RECORD;
            canonical_id uuid;
            losing_ids uuid[];
            fk RECORD;
        BEGIN
            -- For every duplicate (lower(btrim(code)), lower(btrim(name))) group:
            FOR grp IN
                SELECT
                    lower(btrim(customer_code))  AS code_key,
                    lower(btrim(customer_name))  AS name_key
                FROM customers
                GROUP BY 1, 2
                HAVING count(*) > 1
            LOOP
                -- Canonical = oldest row in the group.
                SELECT id INTO canonical_id
                FROM customers
                WHERE lower(btrim(customer_code)) = grp.code_key
                  AND lower(btrim(customer_name)) = grp.name_key
                ORDER BY created_at ASC NULLS LAST, id ASC
                LIMIT 1;

                -- All other rows in the group are losers.
                SELECT array_agg(id) INTO losing_ids
                FROM customers
                WHERE lower(btrim(customer_code)) = grp.code_key
                  AND lower(btrim(customer_name)) = grp.name_key
                  AND id <> canonical_id;

                IF losing_ids IS NULL OR array_length(losing_ids, 1) IS NULL THEN
                    CONTINUE;
                END IF;

                -- Re-point every FK referencing customers(id) to canonical.
                -- Discovered dynamically — covers orders, customer_contacts,
                -- and any future child table without revising this migration.
                FOR fk IN
                    SELECT
                        c.conrelid::regclass::text AS child_table,
                        att.attname                AS child_column
                    FROM pg_constraint c
                    JOIN pg_attribute att
                      ON att.attrelid = c.conrelid
                     AND att.attnum  = ANY (c.conkey)
                    WHERE c.contype = 'f'
                      AND c.confrelid = 'customers'::regclass
                LOOP
                    EXECUTE format(
                        'UPDATE %s SET %I = $1 WHERE %I = ANY($2)',
                        fk.child_table, fk.child_column, fk.child_column
                    )
                    USING canonical_id, losing_ids;
                END LOOP;

                -- Drop the losing rows.
                DELETE FROM customers WHERE id = ANY(losing_ids);
            END LOOP;
        END
        $do$;
        """
    )

    # 3. Composite functional UNIQUE — case + whitespace normalized so casing
    #    drift in Sage exports doesn't sneak duplicates past the constraint.
    #    CREATE INDEX (not CONCURRENTLY) so it stays inside the migration
    #    transaction; table is small enough that the brief lock is acceptable.
    op.execute(
        f"""
        CREATE UNIQUE INDEX IF NOT EXISTS {_NEW_UNIQUE_INDEX}
        ON customers (lower(btrim(customer_code)), lower(btrim(customer_name)));
        """
    )


def downgrade() -> None:
    op.execute(f"DROP INDEX IF EXISTS {_NEW_UNIQUE_INDEX};")
    # Re-creating the legacy column UNIQUE would fail if duplicates now exist —
    # leave it off on downgrade. Operators that need it back must reconcile
    # data first then add it manually.
