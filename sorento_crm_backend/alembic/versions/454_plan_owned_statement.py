"""A loading plan owns its statement (PLAN-scm-loading-plan-feedback-2sep.md S6, AC-F1).

Both statement tables gain the plan they belong to, and the stock snapshot's identity is
re-keyed to include it.

The defect this closes was measured on prod, 2 Sep: a ROYAL MIRROR plan started with NO file
showed 79 unknown supplier codes and a full set of holdings, because `supplier_inventory` was
one snapshot per SUPPLIER and the supplier carried a 115-row stock list somebody had uploaded
from a different plan. The record's own subtitle said "No file" while it quietly ran on that
snapshot. The proforma side failed the same way from the other end: one sheet holds five
stacked invoice blocks, and a plan read exactly ONE of them, picked by ``ORDER BY invoice_date
DESC, created_at DESC, id DESC LIMIT 1`` - which, over five rows sharing an invoice date and a
transaction timestamp, is decided by the UUID.

1. ``scm.proforma_invoice.loading_plan_id`` - UUID, NULL, FK ``scm.loading_plan.id`` ON DELETE
   SET NULL, indexed. Every invoice an upload creates or revises INTO a plan is stamped with
   it, so the plan's holdings are the sum over its own blocks.
2. ``scm.supplier_inventory.loading_plan_id`` - the same column, for the stock list.
3. ``uq_scm_supplier_inventory_identity`` is rebuilt as ``(coalesce(company_id, nil),
   supplier_id, coalesce(loading_plan_id, nil), item_code)``. The plan is coalesced for the
   same reason the company already is: Postgres treats every NULL as distinct, so a plain
   column in the key would not hold the identity across the plan-less rows. Without the plan
   in the key at all, the second plan to upload one model number for a supplier collides with
   the first and the upload fails.

NO BACKFILL, on purpose. A row that predates this migration belongs to the legacy
supplier-wide snapshot and there is no honest plan to name: guessing one (the supplier's
newest open plan, say) would silently bind a stale file to a record that never uploaded it,
which is the very defect above. NULL is read as "legacy", and
``container_request_service.build`` keeps the supplier-wide path for a plan with nothing
stamped, so no open plan goes blank. That path retires once every plan predating 454 is
cancelled or sent.

Revision ID: 454_plan_owned_statement
Revises: 453_shared_brand_attach
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "454_plan_owned_statement"
down_revision = "453_shared_brand_attach"
branch_labels = None
depends_on = None

_NIL = "00000000-0000-0000-0000-000000000000"


def _add_plan_column(table: str, index_name: str, fk_name: str) -> None:
    """The column, its FK and its index - each guarded, so a re-run is a no-op."""
    op.execute(
        f"ALTER TABLE scm.{table} ADD COLUMN IF NOT EXISTS loading_plan_id uuid"
    )
    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = '{fk_name}'
            ) THEN
                ALTER TABLE scm.{table}
                    ADD CONSTRAINT {fk_name}
                    FOREIGN KEY (loading_plan_id)
                    REFERENCES scm.loading_plan (id) ON DELETE SET NULL;
            END IF;
        END $$;
        """
    )
    op.execute(
        f"CREATE INDEX IF NOT EXISTS {index_name} ON scm.{table} (loading_plan_id)"
    )


def upgrade() -> None:
    _add_plan_column(
        "proforma_invoice",
        "ix_scm_proforma_invoice_loading_plan",
        "fk_scm_proforma_invoice_loading_plan",
    )
    _add_plan_column(
        "supplier_inventory",
        "ix_scm_supplier_inventory_loading_plan",
        "fk_scm_supplier_inventory_loading_plan",
    )

    # The identity, re-keyed. Dropped and recreated rather than altered: an expression index
    # cannot be extended in place, and the window between the two is one statement inside
    # this transaction.
    op.execute("DROP INDEX IF EXISTS scm.uq_scm_supplier_inventory_identity")
    op.execute(
        f"""
        CREATE UNIQUE INDEX uq_scm_supplier_inventory_identity
            ON scm.supplier_inventory (
                coalesce(company_id, '{_NIL}'::uuid),
                supplier_id,
                coalesce(loading_plan_id, '{_NIL}'::uuid),
                item_code
            )
        """
    )


def downgrade() -> None:
    # Back to one snapshot per supplier. Any plan-scoped row that would now collide with
    # another under the narrower key has to go first, or the index cannot be built - the
    # plan's rows are a derived copy of a file, never a document of record.
    op.execute(
        """
        DELETE FROM scm.supplier_inventory a
         WHERE a.loading_plan_id IS NOT NULL
           AND EXISTS (
               SELECT 1 FROM scm.supplier_inventory b
                WHERE b.id <> a.id
                  AND coalesce(b.company_id, '00000000-0000-0000-0000-000000000000'::uuid)
                      = coalesce(a.company_id, '00000000-0000-0000-0000-000000000000'::uuid)
                  AND b.supplier_id = a.supplier_id
                  AND b.item_code = a.item_code
                  AND (b.loading_plan_id IS NULL OR b.id < a.id)
           )
        """
    )
    op.execute("DROP INDEX IF EXISTS scm.uq_scm_supplier_inventory_identity")
    op.execute(
        f"""
        CREATE UNIQUE INDEX uq_scm_supplier_inventory_identity
            ON scm.supplier_inventory (
                coalesce(company_id, '{_NIL}'::uuid), supplier_id, item_code
            )
        """
    )
    for table, index, fk in (
        ("supplier_inventory", "ix_scm_supplier_inventory_loading_plan",
         "fk_scm_supplier_inventory_loading_plan"),
        ("proforma_invoice", "ix_scm_proforma_invoice_loading_plan",
         "fk_scm_proforma_invoice_loading_plan"),
    ):
        op.execute(f"DROP INDEX IF EXISTS scm.{index}")
        op.execute(f"ALTER TABLE scm.{table} DROP CONSTRAINT IF EXISTS {fk}")
        op.execute(f"ALTER TABLE scm.{table} DROP COLUMN IF EXISTS loading_plan_id")
