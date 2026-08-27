"""F5 / F5b / F8: the proforma invoice carries volume, is adjustable, and can be revised.

Revision ID: 428_scm_pi_cbm_adjust_revision
Revises: 427_sales_agents_class_backfill
Create Date: 2026-08-26

ONE revision for all three workstreams because they are one contract two coder slots read
at the same time (`PLAN-scm-fulfilment-feedback.md` section 3, "One migration for F5 + F5b
+ F8 columns, authored first"). Splitting it would have slot B's PI work and slot A's
supplier-request page chasing two heads across two branches for no gain.

What it adds:

* **`scm.proforma_invoice_line` volume** - `cartons`, `cbm_per_unit`, `cbm_total`. The
  pre-loading list has stated all three since the first upload (箱数 / 体积(cbm) /
  总体积(cbm)) and the reader parsed only the cartons; the rest went on the floor, so a
  container's fill could never be answered from the document that decides it (AC-D1).
* **`scm.proforma_invoice_line` supplier figures** - `supplier_qty`, `supplier_unit_price`,
  frozen at import. Sorento adjusts `qty` to fit the box; the supplier's own number is never
  overwritten, which is the rule the whole fulfilment journey rests on (AC-E2).
* **`scm.proforma_invoice` adjustment + container** - `adjusted_by` / `adjusted_at` and
  `container_size_id`, so the fill bar states what it is measuring against and an operator
  can say "this one is going in a 40GP" without a release (AC-D4).
* **`scm.proforma_invoice` revision chain** - `revision_of_id`, `revision_no`, `status`
  (`current` / `superseded`). A supplier resending the same container with new prices is a
  revision of one document, not a second document, and only the current revision is a cost
  or a conversion source (AC-E7, AC-E9, AC-E10).
* **`supplier_notices` public token** - `public_token` + `public_token_expires_at` (30 days,
  stamped by the sender, not here). Same shape as the quotation counter-sign link
  (`project_quotation_issues.sign_token`, migration 328): random, single-purpose, expiring,
  and it identifies the DOCUMENT, never a user (F8, AC-C6, AC-C7).
* **The 40HQ seed drops 68 -> 65 cbm** (Q3, ruled by the captain 26 Aug). A data change, not
  a new size row: Ms Tee plans containers to 65 and a second 40HQ row would leave every
  existing screen pointing at the wrong one. Guarded on the OLD value so a client who has
  already tuned the figure by hand keeps theirs.
* **The `体积(cbm)` / `总体积(cbm)` aliases on the `proforma_invoice` doc type.** They exist
  for `packing_list` and `supplier_inventory` (migration 311) and not for this channel, so
  without them the new columns would exist and every upload would leave them empty for ever.
  `seed()` is importable for the same reason 375's is: a CI database is built with
  `create_all` and never runs a migration body.

The columns are ALSO declared on the models (`app/models/scm.py`,
`app/models/supplier_notice.py`), so a create_all database is the same shape as a migrated
one; `336_scm_supplier_inventory_loading_plan._CONTAINER_SIZES` carries the 65 as well, so a
database seeded from scratch never sees 68 at all and the UPDATE below no-ops on it.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "428_scm_pi_cbm_adjust_revision"
down_revision = "427_sales_agents_class_backfill"
branch_labels = None
depends_on = None

DOC_TYPE = "proforma_invoice"

#: (field, alias). Only the volume columns: everything else this channel reads was seeded by
#: 375. Spellings copied from migration 311's `packing_list` rows, so the two channels read
#: the SAME file the same way - `normalize_header` strips the bracketed unit, which is why
#: `体积(cbm)` and `体积（cbm）` are one key and `总体积(cbm)` is a different one.
_ALIASES = [
    ("cbm_per_unit", "体积(cbm)"),
    ("cbm_per_unit", "CBM"),
    ("cbm_per_unit", "Volume"),
    ("cbm_total", "总体积(cbm)"),
    ("cbm_total", "Total CBM"),
    ("cbm_total", "Total Volume"),
]

#: What a 40ft high cube is planned to. 68 was the seeded guess; 65 is what Ms Tee loads to.
_OLD_40HQ_CBM = 68
_NEW_40HQ_CBM = 65


def seed(bind) -> int:
    """Insert the volume aliases. Idempotent, importable - mirrors migration 375's `seed`."""
    inserted = 0
    for field, alias in _ALIASES:
        res = bind.execute(
            sa.text(
                """
                INSERT INTO import_field_alias (doc_type, field, alias, locale)
                VALUES (:d, :f, :a, 'en')
                ON CONFLICT (doc_type, field, alias) DO NOTHING
                """
            ),
            {"d": DOC_TYPE, "f": field, "a": alias},
        )
        inserted += res.rowcount or 0
    return inserted


def set_default_container_cbm(bind) -> int:
    """Move the 40HQ seed to 65 cbm. Idempotent, importable, and guarded on the OLD value.

    "Set where it still reads 68" rather than "set where it is not 65": the row is editable
    on purpose (`ContainerSize`'s docstring - the loadable volume of a container is a
    commercial fact, not a constant), so a client who has already tuned theirs must not have
    it overwritten by a migration correcting somebody else's default.
    """
    res = bind.execute(
        sa.text(
            "UPDATE scm.container_size SET cbm = :new, updated_at = now() "
            "WHERE upper(code) = '40HQ' AND cbm = :old"
        ),
        {"new": _NEW_40HQ_CBM, "old": _OLD_40HQ_CBM},
    )
    return res.rowcount or 0


def upgrade() -> None:
    # --- F5: the proforma line carries volume, and the supplier's own figures ----------
    op.add_column(
        "proforma_invoice_line", sa.Column("cartons", sa.Numeric(), nullable=True), schema="scm"
    )
    op.add_column(
        "proforma_invoice_line",
        sa.Column("cbm_per_unit", sa.Numeric(), nullable=True),
        schema="scm",
    )
    op.add_column(
        "proforma_invoice_line", sa.Column("cbm_total", sa.Numeric(), nullable=True), schema="scm"
    )
    op.add_column(
        "proforma_invoice_line",
        sa.Column("supplier_qty", sa.Numeric(), nullable=True),
        schema="scm",
    )
    op.add_column(
        "proforma_invoice_line",
        sa.Column("supplier_unit_price", sa.Numeric(), nullable=True),
        schema="scm",
    )

    # Backfill: every line already on file WAS the supplier's statement - nobody has been
    # able to adjust one until this revision. Without this, "Supplier: 408" reads blank on
    # every existing invoice and the was/now comparison silently has no "was".
    op.execute(
        """
        UPDATE scm.proforma_invoice_line
        SET supplier_qty = qty,
            supplier_unit_price = unit_price
        WHERE supplier_qty IS NULL
        """
    )

    # --- F5: the invoice knows what box it is being fitted into, and who adjusted it ----
    op.add_column(
        "proforma_invoice",
        sa.Column(
            "container_size_id",
            UUID(as_uuid=False),
            sa.ForeignKey("scm.container_size.id", ondelete="SET NULL"),
            nullable=True,
        ),
        schema="scm",
    )
    op.add_column(
        "proforma_invoice", sa.Column("adjusted_by", sa.String(200), nullable=True), schema="scm"
    )
    op.add_column(
        "proforma_invoice",
        sa.Column("adjusted_at", sa.DateTime(timezone=False), nullable=True),
        schema="scm",
    )

    # --- F5b: the revision chain --------------------------------------------------------
    op.add_column(
        "proforma_invoice",
        sa.Column(
            "revision_of_id",
            UUID(as_uuid=False),
            sa.ForeignKey("scm.proforma_invoice.id", ondelete="SET NULL"),
            nullable=True,
        ),
        schema="scm",
    )
    op.add_column(
        "proforma_invoice",
        sa.Column("revision_no", sa.Integer(), nullable=False, server_default=sa.text("1")),
        schema="scm",
    )
    op.add_column(
        "proforma_invoice",
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'current'")),
        schema="scm",
    )
    op.create_check_constraint(
        "ck_scm_proforma_invoice_status",
        "proforma_invoice",
        "status IN ('current', 'superseded')",
        schema="scm",
    )
    op.create_index(
        "ix_scm_proforma_invoice_revision_of",
        "proforma_invoice",
        ["revision_of_id"],
        schema="scm",
    )

    # --- F8: the tokenised supplier request link ----------------------------------------
    op.add_column(
        "supplier_notices", sa.Column("public_token", sa.String(255), nullable=True)
    )
    op.add_column(
        "supplier_notices",
        sa.Column("public_token_expires_at", sa.DateTime(timezone=False), nullable=True),
    )
    op.create_index(
        "uq_supplier_notices_public_token", "supplier_notices", ["public_token"], unique=True
    )

    # --- Q3: a 40HQ is planned to 65 cbm, not 68 ----------------------------------------
    set_default_container_cbm(op.get_bind())

    # --- The volume columns need a header spelling to land in ---------------------------
    seed(op.get_bind())


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "DELETE FROM import_field_alias WHERE doc_type = :d AND field IN "
            "('cbm_per_unit', 'cbm_total')"
        ),
        {"d": DOC_TYPE},
    )
    bind.execute(
        sa.text(
            "UPDATE scm.container_size SET cbm = :old, updated_at = now() "
            "WHERE upper(code) = '40HQ' AND cbm = :new"
        ),
        {"new": _NEW_40HQ_CBM, "old": _OLD_40HQ_CBM},
    )

    op.drop_index("uq_supplier_notices_public_token", table_name="supplier_notices")
    op.drop_column("supplier_notices", "public_token_expires_at")
    op.drop_column("supplier_notices", "public_token")

    op.drop_index(
        "ix_scm_proforma_invoice_revision_of", table_name="proforma_invoice", schema="scm"
    )
    op.drop_constraint(
        "ck_scm_proforma_invoice_status", "proforma_invoice", schema="scm", type_="check"
    )
    op.drop_column("proforma_invoice", "status", schema="scm")
    op.drop_column("proforma_invoice", "revision_no", schema="scm")
    op.drop_column("proforma_invoice", "revision_of_id", schema="scm")
    op.drop_column("proforma_invoice", "adjusted_at", schema="scm")
    op.drop_column("proforma_invoice", "adjusted_by", schema="scm")
    op.drop_column("proforma_invoice", "container_size_id", schema="scm")

    op.drop_column("proforma_invoice_line", "supplier_unit_price", schema="scm")
    op.drop_column("proforma_invoice_line", "supplier_qty", schema="scm")
    op.drop_column("proforma_invoice_line", "cbm_total", schema="scm")
    op.drop_column("proforma_invoice_line", "cbm_per_unit", schema="scm")
    op.drop_column("proforma_invoice_line", "cartons", schema="scm")
