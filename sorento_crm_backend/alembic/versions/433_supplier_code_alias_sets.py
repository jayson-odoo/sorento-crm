"""F12 / R19-R21: a supplier code can name a product SET, not only a product.

Revision ID: 433_supplier_code_alias_sets
Revises: 436_pl_workbook_fields
Create Date: 2026-08-27

Suppliers sell the whole WC. `CWC605-RL` is our set - pedestal `CWCX605-RL` plus cistern
`CWCY605` - and NO product carries that code, so the ladder could never bind it however many
rungs it grew: every rung compares against `products.product_code`. 2,308 open sales-order
lines sit on the members of sets like this one, so the demand is real and the loading plan
simply could not see it.

Three nullable columns, one per place a code's answer is recorded:

  * `scm.supplier_product_code_alias.product_set_id` - the RULING, automatic or by hand;
  * `scm.supplier_inventory.product_set_id` - the stock row the ruling binds;
  * `scm.proforma_invoice_line.product_set_id` - the invoice line the ruling binds.

The alias's two checks are replaced rather than added to, because both of them are about the
same fact and that fact has changed shape. `(source = 'dismissed') = (product_id IS NULL)`
would now refuse every set match: a set-bound row carries no product, and it is not a
dismissal. So the dismissal check reads "names NOTHING", and a second check refuses a row
naming a product AND a set - one code means one thing, and a row claiming both could not be
re-bound, since the stock row and the invoice line each carry one of the two.

Nothing to backfill. Every alias on file names a product or is a dismissal, and both pass the
new checks unchanged; a set binding exists only once somebody (or the ladder) makes one.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "433_supplier_code_alias_sets"
down_revision = "436_pl_workbook_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "supplier_product_code_alias",
        sa.Column("product_set_id", UUID(as_uuid=False), nullable=True),
        schema="scm",
    )
    op.create_foreign_key(
        "fk_scm_supplier_code_alias_set",
        "supplier_product_code_alias",
        "product_sets",
        ["product_set_id"],
        ["id"],
        source_schema="scm",
        referent_schema="public",
        ondelete="CASCADE",
    )
    op.create_index(
        "ix_scm_supplier_code_alias_set",
        "supplier_product_code_alias",
        ["product_set_id"],
        schema="scm",
    )

    op.drop_constraint(
        "ck_scm_supplier_code_alias_dismissed",
        "supplier_product_code_alias",
        type_="check",
        schema="scm",
    )
    op.create_check_constraint(
        "ck_scm_supplier_code_alias_dismissed",
        "supplier_product_code_alias",
        "(source = 'dismissed') = (product_id IS NULL AND product_set_id IS NULL)",
        schema="scm",
    )
    op.create_check_constraint(
        "ck_scm_supplier_code_alias_one_target",
        "supplier_product_code_alias",
        "NOT (product_id IS NOT NULL AND product_set_id IS NOT NULL)",
        schema="scm",
    )

    for table in ("supplier_inventory", "proforma_invoice_line"):
        op.add_column(
            table,
            sa.Column("product_set_id", UUID(as_uuid=False), nullable=True),
            schema="scm",
        )
        op.create_foreign_key(
            f"fk_scm_{table}_set",
            table,
            "product_sets",
            ["product_set_id"],
            ["id"],
            source_schema="scm",
            referent_schema="public",
            # SET NULL rather than CASCADE: a set being deleted must not take the supplier's
            # own stock row or a priced invoice line with it. The row goes back to unmatched,
            # which is exactly what it is once the set it named is gone.
            ondelete="SET NULL",
        )
    op.create_index(
        "ix_scm_supplier_inventory_set", "supplier_inventory", ["product_set_id"], schema="scm"
    )
    op.create_index(
        "ix_scm_proforma_invoice_line_set",
        "proforma_invoice_line",
        ["product_set_id"],
        schema="scm",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_scm_proforma_invoice_line_set", table_name="proforma_invoice_line", schema="scm"
    )
    op.drop_index(
        "ix_scm_supplier_inventory_set", table_name="supplier_inventory", schema="scm"
    )
    for table in ("proforma_invoice_line", "supplier_inventory"):
        op.drop_constraint(f"fk_scm_{table}_set", table, type_="foreignkey", schema="scm")
        op.drop_column(table, "product_set_id", schema="scm")

    # The set bindings go first: they are the only rows that cannot exist under the old
    # checks, and leaving them would make the dismissal check fail rather than the schema
    # go back.
    op.execute(
        "DELETE FROM scm.supplier_product_code_alias WHERE product_set_id IS NOT NULL"
    )
    op.drop_constraint(
        "ck_scm_supplier_code_alias_one_target",
        "supplier_product_code_alias",
        type_="check",
        schema="scm",
    )
    op.drop_constraint(
        "ck_scm_supplier_code_alias_dismissed",
        "supplier_product_code_alias",
        type_="check",
        schema="scm",
    )
    op.create_check_constraint(
        "ck_scm_supplier_code_alias_dismissed",
        "supplier_product_code_alias",
        "(source = 'dismissed') = (product_id IS NULL)",
        schema="scm",
    )
    op.drop_index(
        "ix_scm_supplier_code_alias_set",
        table_name="supplier_product_code_alias",
        schema="scm",
    )
    op.drop_constraint(
        "fk_scm_supplier_code_alias_set",
        "supplier_product_code_alias",
        type_="foreignkey",
        schema="scm",
    )
    op.drop_column("supplier_product_code_alias", "product_set_id", schema="scm")
