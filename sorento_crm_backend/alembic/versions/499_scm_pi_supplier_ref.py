"""Our own PI number - `pi_number` stops being the supplier's own text, `supplier_ref` holds it.

S1 (supplier documents / PI-first lane, 9 Sep 2026, AC-A1-A4): `scm.proforma_invoice.
pi_number` used to be the supplier's own document number, verbatim, or the derived
`PI-<file stem>-<block>` fallback when the file stated none. From this migration on it is
OURS - a monthly running number (`PI-{yy}{month:02d}-{NNN}`, `app.services.numbering_
defaults.PROFORMA_INVOICE_DOC_TYPE`), minted once at apply and never re-derived from the
file. The supplier's own reference moves to the new `supplier_ref` column, which is what a
re-upload now matches on (identity: company, supplier, supplier_ref) - `pi_number` gets its
own, separate uniqueness (company, pi_number), since two different suppliers' invoices can
no longer collide the way two different suppliers' OWN document numbers never did either.

`app.services.scm.proforma_invoice_numbering_backfill.backfill_pi_numbers` does the data
migration: every existing row's old `pi_number` is kept as `supplier_ref` unless it matches
the derived form (`^PI-.+-\\d+$`, in which case it never named a real supplier document and
is dropped to NULL), then every row is re-numbered per company, oldest first, with the
month key taken from its own `created_at` - exactly as if it had been numbered on the day
it arrived. Each company's numbering rule is seeded first (every company, not only the ones
with an existing invoice - a company created after this migration must not be refused
`numbering_rule_missing` on its first proforma invoice) and left with `next_value`/
`last_reset_key` at the state the backfill's own last row put it in, so the first LIVE
upload after this migration continues the same series.

Revision ID: 499_scm_pi_supplier_ref
Revises: 498_committed_v_bundled_qty
Create Date: 2026-09-09
"""
import logging

from alembic import op
import sqlalchemy as sa

from app.services.numbering_defaults import seed_proforma_invoice_rule
from app.services.scm.proforma_invoice_numbering_backfill import backfill_pi_numbers

revision = "499_scm_pi_supplier_ref"
down_revision = "498_committed_v_bundled_qty"
branch_labels = None
depends_on = None

logger = logging.getLogger(__name__)

_NIL_COMPANY = "00000000-0000-0000-0000-000000000000"


def upgrade() -> None:
    bind = op.get_bind()

    op.add_column(
        "proforma_invoice",
        sa.Column("supplier_ref", sa.String(100), nullable=True),
        schema="scm",
    )

    # Every company, not only the ones with an existing invoice (see the module docstring).
    seed_proforma_invoice_rule(bind)

    minted = backfill_pi_numbers(bind)
    for key, count in sorted(minted.items()):
        logger.info("proforma_invoice_numbering_backfill: %s minted %d", key, count)

    op.drop_index("uq_scm_proforma_invoice_identity", table_name="proforma_invoice", schema="scm")
    # Identity moved from `pi_number` (now ours) to `supplier_ref` (AC-A3/A4) - a NULL ref
    # never conflicts with another NULL, a plain unique index's default behaviour.
    op.create_index(
        "uq_scm_proforma_invoice_identity",
        "proforma_invoice",
        [
            sa.text(f"coalesce(company_id, '{_NIL_COMPANY}'::uuid)"),
            "supplier_id",
            "supplier_ref",
        ],
        unique=True,
        schema="scm",
    )
    # `pi_number` is ours and minted once - it must never collide within a company
    # regardless of supplier (AC-A1/A4).
    op.create_index(
        "uq_scm_proforma_invoice_number",
        "proforma_invoice",
        [sa.text(f"coalesce(company_id, '{_NIL_COMPANY}'::uuid)"), "pi_number"],
        unique=True,
        schema="scm",
    )


def downgrade() -> None:
    op.drop_index("uq_scm_proforma_invoice_number", table_name="proforma_invoice", schema="scm")
    op.drop_index("uq_scm_proforma_invoice_identity", table_name="proforma_invoice", schema="scm")
    # The pre-S1 identity, on `pi_number` - the data itself (which text landed in
    # `pi_number` vs `supplier_ref`) is not un-migrated; a downgrade restores the SCHEMA,
    # same convention every other migration here follows.
    op.create_index(
        "uq_scm_proforma_invoice_identity",
        "proforma_invoice",
        [
            sa.text(f"coalesce(company_id, '{_NIL_COMPANY}'::uuid)"),
            "supplier_id",
            "pi_number",
        ],
        unique=True,
        schema="scm",
    )
    op.drop_column("proforma_invoice", "supplier_ref", schema="scm")
