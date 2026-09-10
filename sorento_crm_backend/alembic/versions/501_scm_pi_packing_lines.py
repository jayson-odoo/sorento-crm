"""Supplier packing rows on the invoice - table + one new header alias.

S2 (supplier documents / PI-first lane, 9 Sep 2026, AC-B1): `scm.proforma_invoice_packing_line`
- one row per supplier packing-list row, verbatim, matched onto a `proforma_invoice_line`
(nullable) by resolved product rather than merged with it - the grains differ today (Kailu
writes 12 packing rows against 11 priced lines; Jiexia's lid row prices nothing and is a
packing row with no invoice line at all).

The one new alias: Kailu's packing list states its own date as a bare `Date：2026-07-30`
label (`packing_list.invoice_date` already resolves the Chinese `日期` and the Jiexia
`INVOICE NO.` for `pi_number` - migration 483 - but not the bare English "Date" this
supplier's own file uses). AC-B5's attach resolution needs it: a packing-list-alone upload
matches the one PI of the supplier sharing the file's own stated date.

Revision ID: 501_scm_pi_packing_lines
Revises: 500_scm_pi_identity_current
Create Date: 2026-09-09
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "501_scm_pi_packing_lines"
down_revision = "500_scm_pi_identity_current"
branch_labels = None
depends_on = None

_ALIAS = ("packing_list", "invoice_date", "Date", "en")


def upgrade() -> None:
    op.create_table(
        "proforma_invoice_packing_line",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "company_id",
            UUID(as_uuid=False),
            sa.ForeignKey("companies.id", name="fk_scm_pi_packing_line_company_id"),
            nullable=True,
        ),
        sa.Column(
            "proforma_invoice_id",
            UUID(as_uuid=False),
            sa.ForeignKey("scm.proforma_invoice.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "proforma_invoice_line_id",
            UUID(as_uuid=False),
            sa.ForeignKey("scm.proforma_invoice_line.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("row_no", sa.Integer(), nullable=False),
        sa.Column("item_code", sa.String(100), nullable=False),
        sa.Column("supplier_code", sa.String(100), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "product_id", UUID(as_uuid=False),
            sa.ForeignKey("products.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column(
            "product_set_id", UUID(as_uuid=False),
            sa.ForeignKey("product_sets.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column("qty", sa.Numeric(), nullable=False),
        sa.Column("cartons", sa.Numeric(), nullable=True),
        sa.Column("pcs_per_carton", sa.Numeric(15, 4), nullable=True),
        sa.Column("carton_length_cm", sa.Numeric(10, 2), nullable=True),
        sa.Column("carton_width_cm", sa.Numeric(10, 2), nullable=True),
        sa.Column("carton_height_cm", sa.Numeric(10, 2), nullable=True),
        sa.Column("cbm_per_carton", sa.Numeric(12, 6), nullable=True),
        sa.Column("cbm_total", sa.Numeric(12, 6), nullable=True),
        sa.Column("net_weight", sa.Numeric(15, 4), nullable=True),
        sa.Column("gross_weight", sa.Numeric(15, 4), nullable=True),
        sa.Column("total_net_weight", sa.Numeric(15, 4), nullable=True),
        sa.Column("total_gross_weight", sa.Numeric(15, 4), nullable=True),
        sa.Column("material", sa.String(255), nullable=True),
        sa.Column("container_no", sa.String(100), nullable=True),
        sa.Column("remark", sa.Text(), nullable=True),
        sa.Column(
            "match_state", sa.String(20), nullable=False, server_default=sa.text("'unmatched'")
        ),
        sa.CheckConstraint(
            "match_state IN ('matched', 'unmatched', 'dismissed')",
            name="ck_scm_pi_packing_line_match_state",
        ),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.func.now(),
            onupdate=sa.func.now(), nullable=False,
        ),
        schema="scm",
    )
    op.create_index(
        "ix_scm_pi_packing_line_invoice", "proforma_invoice_packing_line",
        ["proforma_invoice_id"], schema="scm",
    )
    op.create_index(
        "ix_scm_pi_packing_line_line", "proforma_invoice_packing_line",
        ["proforma_invoice_line_id"], schema="scm",
    )
    op.create_index(
        "ix_scm_pi_packing_line_company_id", "proforma_invoice_packing_line",
        ["company_id"], schema="scm",
    )

    bind = op.get_bind()
    doc_type, field, alias, locale = _ALIAS
    bind.execute(
        sa.text(
            "INSERT INTO import_field_alias (doc_type, field, alias, locale) "
            "VALUES (:d, :f, :a, :l) "
            "ON CONFLICT (doc_type, field, alias) DO NOTHING"
        ),
        {"d": doc_type, "f": field, "a": alias, "l": locale},
    )


def downgrade() -> None:
    bind = op.get_bind()
    doc_type, field, alias, _locale = _ALIAS
    bind.execute(
        sa.text(
            "DELETE FROM import_field_alias WHERE doc_type = :d AND field = :f AND alias = :a"
        ),
        {"d": doc_type, "f": field, "a": alias},
    )
    op.drop_table("proforma_invoice_packing_line", schema="scm")
