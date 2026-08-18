"""G3b: the proforma invoice becomes a document we hold, with priced lines.

Revision ID: 375_scm_proforma_invoice
Revises: 374_merge_proj_media_flyer
Create Date: 2026-08-17

Written against two heads on main and renumbered onto their merge (`374_merge_proj_media_flyer`)
after rebasing, so this revision is a plain single-parent one and 375 is the only head.

What it adds:

* `scm.proforma_invoice` + `scm.proforma_invoice_line` - the supplier's own priced document.
  A price was already parsed out of the pre-loading list by the packing-list reader and then
  dropped on the floor; from here it has a home of record (and the shipment line keeps its
  copy, so allocation-time cost capture sees it too).
* the `proforma_invoice` alias doc type. Both real shapes are covered by one type because
  both are, structurally, labelled cells above a header row above lines - Jinbaichuan's
  19-column pre-loading list and Kailu's seven-column invoice.
* the `scm.proforma_invoice.upload` permission, swept onto every role that already holds
  `scm.reorder.run` (AC-P4.3). Same sweep shape as 361: `integration\\_%` roles are excluded,
  because they are API-key principals reading the module, never operators uploading to it.

The permission is ALSO declared in `app/rbac/permission_registry.py`, because a database
built the way CI builds one (create_all + registry sync, no migration body) never runs this.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "375_scm_proforma_invoice"
down_revision = "374_merge_proj_media_flyer"
branch_labels = None
depends_on = None

DOC_TYPE = "proforma_invoice"

_NIL_COMPANY = "00000000-0000-0000-0000-000000000000"

#: (field, alias). Every spelling the two real documents use, plus the English ones an
#: export in another language would use. Stored as written; `normalize_header` strips case,
#: spacing, newlines and full-width brackets, so `单价(元)` also covers `单价（元）` and
#: `Date 日期：` resolves whole (which is what stops the labelled-cell scanner reading the
#: NEXT label as this label's value).
_ALIASES = [
    # --- line columns ----------------------------------------------------------
    ("item_code", "产品型号"),
    ("item_code", "编号"),
    ("item_code", "型号"),
    ("item_code", "ITEM CODE"),
    ("item_code", "MODEL"),
    ("item_code", "Item No"),
    ("description", "品名"),
    ("description", "DESCRIPTION"),
    ("description", "Description"),
    ("description", "货名"),
    ("spec", "规格"),
    ("qty", "数量"),
    ("qty", "产品数量"),
    ("qty", "QTY"),
    ("qty", "Quantity"),
    ("uom", "单位"),
    ("uom", "UOM"),
    ("uom", "Unit"),
    ("unit_price", "RMB"),
    ("unit_price", "单价(元)"),
    ("unit_price", "单价"),
    ("unit_price", "UNIT PRICE"),
    ("unit_price", "Unit Price"),
    ("unit_price", "PRICE"),
    ("amount", "金额（rmb）"),
    ("amount", "金额"),
    ("amount", "总价（元）"),
    ("amount", "总价"),
    ("amount", "AMOUNT"),
    ("amount", "Amount"),
    ("amount", "TOTAL"),
    ("po_ref", "其他"),
    ("po_ref", "PO NO"),
    ("po_ref", "PO No."),
    ("po_ref", "PO"),
    ("po_ref", "订单号"),
    ("po_ref", "客户订单号"),
    ("po_ref", "Order No"),
    ("remark", "备注"),
    ("remark", "REMARK"),
    ("remark", "Remarks"),
    ("brand", "商标"),
    ("cartons", "箱数"),
    # --- document (labelled cell) fields ---------------------------------------
    ("pi_number", "货单号"),
    ("pi_number", "发票号"),
    ("pi_number", "PI NO"),
    ("pi_number", "Invoice No"),
    ("pi_number", "Proforma No"),
    ("pi_number", "PI No."),
    ("invoice_date", "日期"),
    ("invoice_date", "Date"),
    ("invoice_date", "Date 日期"),
    ("invoice_date", "Invoice Date"),
    ("container_no", "货柜号"),
    ("container_no", "Container No"),
    ("container_no", "Container No 货柜号"),
    ("bl_no", "提单号"),
    ("bl_no", "B/L NO"),
    ("bl_no", "BL No"),
    ("currency", "币种"),
    ("currency", "Currency"),
    ("currency", "CURRENCY"),
]

_PERMISSION = (
    "scm.proforma_invoice.upload",
    "Upload proforma invoices",
    "Upload, apply and delete supplier proforma invoices.",
)
#: Whoever already runs the module's uploads gets this one too.
_SOURCE_PERMISSION = "scm.reorder.run"
#: Matched with LIKE against `user_roles.slug`. API-key principals, never uploaders.
_EXCLUDED_ROLE_PREFIX = "integration\\_%"


def seed(bind) -> int:
    """Insert the aliases. Idempotent through the table's own unique constraint, so a re-run
    on an already-seeded database is a no-op. Mirrors migration 358's `seed`, and is
    importable because `scripts/bootstrap_env` replays it onto a create_all database, which
    never executes a migration body."""
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


def grant_upload_permission(bind) -> None:
    """Create the permission when absent and sweep it onto the operator roles. Idempotent."""
    slug, name, description = _PERMISSION
    bind.execute(
        sa.text(
            """
            INSERT INTO user_permissions (id, slug, name, description, created_at)
            SELECT gen_random_uuid()::text, :slug, :name, :descr, now()
            WHERE NOT EXISTS (SELECT 1 FROM user_permissions WHERE slug = :slug)
            """
        ),
        {"slug": slug, "name": name, "descr": description},
    )
    bind.execute(
        sa.text(
            """
            INSERT INTO user_role_permissions (id, role_id, permission_id, assigned_at)
            SELECT gen_random_uuid()::text, rp.role_id, tgt.id, now()
            FROM user_role_permissions rp
            JOIN user_permissions src ON src.id = rp.permission_id AND src.slug = :source
            JOIN user_roles r ON r.id = rp.role_id
            CROSS JOIN user_permissions tgt
            WHERE tgt.slug = :target
              AND r.slug NOT LIKE :excluded
            ON CONFLICT (role_id, permission_id) DO NOTHING
            """
        ),
        {"source": _SOURCE_PERMISSION, "target": slug, "excluded": _EXCLUDED_ROLE_PREFIX},
    )


def upgrade() -> None:
    op.create_table(
        "proforma_invoice",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        # Owned (`CompanyScopedMixin`): the FK and the index are what the ORM's own
        # `create_all` produces, so a migrated database and a CI one are the same shape.
        sa.Column(
            "company_id",
            UUID(as_uuid=False),
            sa.ForeignKey("companies.id", name="fk_scm_proforma_invoice_company_id"),
            nullable=True,
        ),
        sa.Column(
            "supplier_id",
            UUID(as_uuid=False),
            sa.ForeignKey("suppliers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("pi_number", sa.String(100), nullable=False),
        sa.Column("invoice_date", sa.Date(), nullable=True),
        sa.Column("currency", sa.String(3), nullable=True),
        sa.Column("container_ref", sa.String(100), nullable=True),
        sa.Column("bl_ref", sa.String(100), nullable=True),
        sa.Column("total_amount", sa.Numeric(), nullable=True),
        sa.Column("line_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("source_ref", sa.String(), nullable=True),
        sa.Column("block_index", sa.Integer(), nullable=True),
        sa.Column("uploaded_by", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        schema="scm",
    )
    op.create_index(
        "ix_scm_proforma_invoice_supplier", "proforma_invoice", ["supplier_id"], schema="scm"
    )
    op.create_index(
        "ix_scm_proforma_invoice_company_id", "proforma_invoice", ["company_id"], schema="scm"
    )
    # One invoice per document number per supplier per company. Company is coalesced for the
    # same reason as the supplier snapshot: the column is nullable on legacy rows and
    # Postgres treats NULLs as distinct, so without it a re-upload inserts a second copy of
    # every invoice in the file instead of replacing the lines of the one already held.
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

    op.create_table(
        "proforma_invoice_line",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "company_id",
            UUID(as_uuid=False),
            sa.ForeignKey("companies.id", name="fk_scm_proforma_invoice_line_company_id"),
            nullable=True,
        ),
        sa.Column(
            "invoice_id",
            UUID(as_uuid=False),
            sa.ForeignKey("scm.proforma_invoice.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("line_no", sa.Integer(), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=True),
        sa.Column("item_code", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("qty", sa.Numeric(), nullable=False),
        sa.Column("uom", sa.String(20), nullable=True),
        sa.Column("unit_price", sa.Numeric(), nullable=True),
        sa.Column("amount", sa.Numeric(), nullable=True),
        sa.Column("po_ref", sa.String(100), nullable=True),
        sa.Column("remark", sa.Text(), nullable=True),
        sa.Column(
            "product_id",
            UUID(as_uuid=False),
            sa.ForeignKey("products.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        schema="scm",
    )
    op.create_index(
        "ix_scm_proforma_invoice_line_invoice", "proforma_invoice_line", ["invoice_id"],
        schema="scm",
    )
    # The PO reference is how the verification task (PI versus PO) finds its counterpart, and
    # it is read across invoices rather than within one, so it is indexed on its own.
    op.create_index(
        "ix_scm_proforma_invoice_line_po_ref", "proforma_invoice_line", ["po_ref"], schema="scm"
    )
    op.create_index(
        "ix_scm_proforma_invoice_line_company_id", "proforma_invoice_line", ["company_id"],
        schema="scm",
    )

    bind = op.get_bind()
    seed(bind)
    grant_upload_permission(bind)


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            DELETE FROM user_role_permissions
            WHERE permission_id IN (SELECT id FROM user_permissions WHERE slug = :slug)
            """
        ),
        {"slug": _PERMISSION[0]},
    )
    bind.execute(
        sa.text("DELETE FROM user_permissions WHERE slug = :slug"), {"slug": _PERMISSION[0]}
    )
    for field, alias in _ALIASES:
        bind.execute(
            sa.text(
                "DELETE FROM import_field_alias "
                "WHERE doc_type = :d AND field = :f AND alias = :a"
            ),
            {"d": DOC_TYPE, "f": field, "a": alias},
        )
    op.drop_table("proforma_invoice_line", schema="scm")
    op.drop_table("proforma_invoice", schema="scm")
