"""Partial identity index: only a CURRENT proforma invoice occupies its identity slot.

S1 follow-up (supplier documents / PI-first lane, 9 Sep 2026, AC-E7): a revision keeps its
predecessor's `supplier_ref` verbatim - the diff (`_diff`) and the detail's `revision_of_
pi_number` both read the chain by it - so `uq_scm_proforma_invoice_identity` (company,
supplier, supplier_ref), made unconditional by migration 499, refused every revision INSERT
the moment it was written: the superseded predecessor still carries the same `supplier_ref`,
and a superseded row is not a claim on that identity any more - it is read-only and is not
the current word on the container (`ProformaInvoice.status`'s own docstring). Scoping the
index to `status = 'current'` matches that: any number of superseded rows may now share a
`supplier_ref`, but only one CURRENT row ever will, which is exactly the constraint AC-A3's
"one live document per (supplier, reference)" is about.

`uq_scm_proforma_invoice_number` (pi_number) is untouched - a minted number is never reused
by any row, current or superseded (AC-A1/A4).

Revision ID: 500_scm_pi_identity_current
Revises: 499_scm_pi_supplier_ref
Create Date: 2026-09-09
"""
from alembic import op
import sqlalchemy as sa

revision = "500_scm_pi_identity_current"
down_revision = "499_scm_pi_supplier_ref"
branch_labels = None
depends_on = None

_NIL_COMPANY = "00000000-0000-0000-0000-000000000000"


def upgrade() -> None:
    op.drop_index("uq_scm_proforma_invoice_identity", table_name="proforma_invoice", schema="scm")
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
        postgresql_where=sa.text("status = 'current'"),
    )


def downgrade() -> None:
    op.drop_index("uq_scm_proforma_invoice_identity", table_name="proforma_invoice", schema="scm")
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
