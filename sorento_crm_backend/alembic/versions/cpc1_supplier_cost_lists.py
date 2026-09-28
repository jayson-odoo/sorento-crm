"""Cost price from the supplier's price list (#1288, Lane A).

Plan: documentation/plans/purchasing/PLAN-cost-price-supplier-26sep.md section 4.
Tables: `product_supplier_costs` (dated cost lists), `cost_price_change_sets` +
`cost_price_change_lines` (one upload/submission and its rows), `supplier_price_links`
(Lane B's share link, created empty here). `system_settings.cost_price_verification_enabled`
(off by default). `audit_logs.action` widens to `varchar(40)` - the named events this lane
writes (`SUPPLIER_COST_LIST_EDIT`, `COST_VERIFICATION_SETTING`) do not fit the old 20.

Permissions (plan section 10): `procurement.cost_price_changes.{upload,view,verify}` and
`procurement.suppliers.price_link` are swept onto every "purchasing role" (whoever holds
`scm.proforma_invoice.upload` today, `integration_%` excluded) plus granted to `admin` and
`superadmin` by name. `procurement.product_suppliers.{view,add,edit,delete}` (already in the
permission registry, never enforced before this lane) is swept the same way, PLUS onto any
role that already holds `.view` - AC-S2-14's "no role that writes a link today loses it".

Every step is defensive against a schema already built by `Base.metadata.create_all` (a
`blank_session()` test schema, or `scripts/bootstrap_env`) rather than by this file's own
`upgrade()` - the ORM columns/tables already match what is written here, so this migration's
job on such a database is only the permission grants and the data seeds.

Revision ID: cpc1_supplier_cost_lists
Revises: merge_28sep_batch2
Create Date: 2026-09-27
"""
from __future__ import annotations

import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "cpc1_supplier_cost_lists"
down_revision = "merge_28sep_batch2"
branch_labels = None
depends_on = None

#: The permission every purchasing role holds today (AC-S1-25's "purchasing roles" source).
_PURCHASING_SOURCE_PERM = "scm.proforma_invoice.upload"
_EXCLUDED_ROLE_PREFIX = "integration\\_%"
_GRANT_ROLE_SLUGS = ("admin", "superadmin")

_NEW_PERMS = (
    ("procurement.cost_price_changes.upload", "Upload Cost Price Changes", "Upload a supplier price list, map/skip its codes, discard a draft, and apply it while verification is off."),
    ("procurement.cost_price_changes.view", "View Cost Price Changes", "View cost-price change sets, their lines, history and source file."),
    ("procurement.cost_price_changes.verify", "Verify Cost Price Changes", "Decide lines, return or apply a cost-price change set pending verification."),
    ("procurement.suppliers.price_link", "Share Supplier Price Page", "Issue, view and revoke a supplier's own price-page link."),
    ("procurement.product_suppliers.view", "View Product-Suppliers", "Permission to view Product-Suppliers."),
    ("procurement.product_suppliers.add", "Add Product-Suppliers", "Permission to add Product-Suppliers."),
    ("procurement.product_suppliers.edit", "Edit Product-Suppliers", "Permission to edit Product-Suppliers."),
    ("procurement.product_suppliers.delete", "Delete Product-Suppliers", "Permission to delete Product-Suppliers."),
)

#: (target slug, source slug) - every role holding `source` is swept onto `target`.
_PURCHASING_SWEEP = (
    ("procurement.cost_price_changes.upload", _PURCHASING_SOURCE_PERM),
    ("procurement.cost_price_changes.view", _PURCHASING_SOURCE_PERM),
    ("procurement.cost_price_changes.verify", _PURCHASING_SOURCE_PERM),
    ("procurement.suppliers.price_link", _PURCHASING_SOURCE_PERM),
    # A purchasing role also gets product-suppliers view+write (AC-S2-14): granted through
    # `.view` first, so the second sweep below (view -> add/edit/delete) picks it up too.
    ("procurement.product_suppliers.view", _PURCHASING_SOURCE_PERM),
)
#: Whoever already holds `.view` gains write, so no role that could see a link before this
#: migration loses the ability to add/change/delete one now that it is finally enforced.
_PRODUCT_SUPPLIER_WRITE_SWEEP = (
    ("procurement.product_suppliers.add", "procurement.product_suppliers.view"),
    ("procurement.product_suppliers.edit", "procurement.product_suppliers.view"),
    ("procurement.product_suppliers.delete", "procurement.product_suppliers.view"),
)
#: Whoever could reach a link through the product screens before this lane keeps it (AC-S2-14,
#: Should fix 1 of the review at 232e5706): a products viewer keeps the product Suppliers tab,
#: a products editor keeps the supplier section of the product form. Runs AFTER the sweep
#: above, so a products viewer gains `.view` without inheriting the writes.
_PRODUCT_ROLE_SWEEP = (
    ("procurement.product_suppliers.view", "master_data.products.view"),
    ("procurement.product_suppliers.add", "master_data.products.edit"),
    ("procurement.product_suppliers.edit", "master_data.products.edit"),
    ("procurement.product_suppliers.delete", "master_data.products.edit"),
)
_ADMIN_GRANT_SLUGS = (
    "procurement.cost_price_changes.upload",
    "procurement.cost_price_changes.view",
    "procurement.cost_price_changes.verify",
    "procurement.suppliers.price_link",
)

_ALIAS_SEEDS = (
    # (field, alias)
    ("item_code", "型号"), ("item_code", "型號"), ("item_code", "model"),
    ("item_code", "item"), ("item_code", "code"),
    ("unit_price", "价格"), ("unit_price", "單價"), ("unit_price", "单价"),
    ("unit_price", "price"), ("unit_price", "unit price"),
    ("description", "产品配置"), ("description", "配置"), ("description", "description"),
    ("description", "specification"),
    ("line_no", "序号"), ("line_no", "no"), ("line_no", "s/n"),
)


def _has_table(bind, name: str) -> bool:
    return sa.inspect(bind).has_table(name)


def _insert_permission(bind, slug: str, name: str, description: str) -> None:
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


def _sweep(bind, target: str, source: str, *, skip_product_viewers: bool = False) -> None:
    """`skip_product_viewers` leaves out a role holding `master_data.products.view` without
    `.edit` or the purchasing source: `_PRODUCT_ROLE_SWEEP` gives such a role `.view` only,
    and without this a second run would read that `.view` back as a reason to grant writes."""
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
              AND NOT (
                :skip_product_viewers
                AND EXISTS (
                    SELECT 1 FROM user_role_permissions v
                    JOIN user_permissions vp ON vp.id = v.permission_id
                    WHERE v.role_id = rp.role_id AND vp.slug = 'master_data.products.view'
                )
                AND NOT EXISTS (
                    SELECT 1 FROM user_role_permissions w
                    JOIN user_permissions wp ON wp.id = w.permission_id
                    WHERE w.role_id = rp.role_id
                      AND wp.slug IN ('master_data.products.edit', :purchasing)
                )
              )
            ON CONFLICT (role_id, permission_id) DO NOTHING
            """
        ),
        {
            "source": source, "target": target, "excluded": _EXCLUDED_ROLE_PREFIX,
            "skip_product_viewers": skip_product_viewers, "purchasing": _PURCHASING_SOURCE_PERM,
        },
    )


def _grant_to_roles(bind, slug: str, role_slugs: tuple[str, ...]) -> None:
    bind.execute(
        sa.text(
            """
            INSERT INTO user_role_permissions (id, role_id, permission_id, assigned_at)
            SELECT gen_random_uuid()::text, r.id, p.id, now()
            FROM user_roles r
            CROSS JOIN user_permissions p
            WHERE p.slug = :slug AND r.slug = ANY(:roles)
            ON CONFLICT (role_id, permission_id) DO NOTHING
            """
        ),
        {"slug": slug, "roles": list(role_slugs)},
    )


def upgrade() -> None:
    bind = op.get_bind()

    # ------------------------------------------------------------------------- tables
    if not _has_table(bind, "cost_price_change_sets"):
        op.create_table(
            "cost_price_change_sets",
            sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
            sa.Column("company_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("companies.id"), nullable=True),
            sa.Column("code", sa.String(length=30), nullable=False),
            sa.Column("supplier_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("suppliers.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("channel", sa.String(length=20), nullable=False, server_default=sa.text("'staff_upload'")),
            sa.Column("status", sa.String(length=24), nullable=False, server_default=sa.text("'draft'")),
            sa.Column("currency", sa.String(length=3), nullable=False),
            sa.Column("start_date", sa.Date(), nullable=True),
            sa.Column("end_date", sa.Date(), nullable=True),
            sa.Column("file_name", sa.String(length=255), nullable=True),
            sa.Column("source_file_bytes", sa.LargeBinary(), nullable=True),
            sa.Column("source_file_size", sa.Integer(), nullable=True),
            sa.Column("source_meta", postgresql.JSONB(), nullable=True),
            sa.Column("created_by_user_id", sa.String(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("submitted_by_user_id", sa.String(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("submitted_at", sa.DateTime(), nullable=True),
            sa.Column("submitted_via_link_id", postgresql.UUID(as_uuid=False), nullable=True),
            sa.Column("returned_reason", sa.Text(), nullable=True),
            sa.Column("returned_by_user_id", sa.String(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("returned_at", sa.DateTime(), nullable=True),
            sa.Column("applied_by_user_id", sa.String(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("applied_at", sa.DateTime(), nullable=True),
            sa.Column("verified", sa.Boolean(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
            sa.CheckConstraint("channel IN ('staff_upload', 'supplier_page', 'supplier_upload')", name="ck_cost_price_change_sets_channel"),
            sa.CheckConstraint("status IN ('draft', 'pending_verification', 'applied')", name="ck_cost_price_change_sets_status"),
        )
        op.create_index("ix_cost_price_change_sets_supplier", "cost_price_change_sets", ["supplier_id"])
        op.create_index("ix_cost_price_change_sets_company_id", "cost_price_change_sets", ["company_id"])
        op.create_index("ix_cost_price_change_sets_code", "cost_price_change_sets", ["company_id", "code"])
        op.create_index(
            "uq_cost_price_change_sets_open_per_supplier", "cost_price_change_sets",
            ["company_id", "supplier_id"], unique=True,
            postgresql_where=sa.text("status IN ('draft', 'pending_verification')"),
        )

    if not _has_table(bind, "cost_price_change_lines"):
        op.create_table(
            "cost_price_change_lines",
            sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
            sa.Column("change_set_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("cost_price_change_sets.id", ondelete="CASCADE"), nullable=False),
            sa.Column("sheet", sa.String(length=255), nullable=False),
            sa.Column("row_no", sa.Integer(), nullable=False),
            sa.Column("line_no", sa.String(length=20), nullable=True),
            sa.Column("supplier_code_raw", sa.String(length=255), nullable=False),
            sa.Column("supplier_code", sa.String(length=255), nullable=False),
            sa.Column("code_note", sa.String(length=255), nullable=True),
            sa.Column("configuration", sa.Text(), nullable=True),
            sa.Column("flags", postgresql.ARRAY(sa.String()), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("match_outcome", sa.String(length=20), nullable=False, server_default=sa.text("'unmatched'")),
            sa.Column("match_rung", sa.String(length=20), nullable=True),
            sa.Column("product_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("products.id"), nullable=True),
            sa.Column("mapped_by_user_id", sa.String(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("current_unit_cost", sa.Numeric(12, 2), nullable=True),
            sa.Column("current_currency", sa.String(length=3), nullable=True),
            sa.Column("new_unit_cost", sa.Numeric(12, 2), nullable=True),
            sa.Column("line_state", sa.String(length=20), nullable=False, server_default=sa.text("'needs_attention'")),
            sa.Column("skipped", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("skip_reason", sa.Text(), nullable=True),
            sa.Column("new_link_lead_time_days", sa.Integer(), nullable=True),
            sa.Column("decision", sa.String(length=20), nullable=True),
            sa.Column("decision_reason", sa.Text(), nullable=True),
            sa.Column("decided_by_user_id", sa.String(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("decided_at", sa.DateTime(), nullable=True),
            sa.Column("stale_live_unit_cost", sa.Numeric(12, 2), nullable=True),
            sa.Column("stale_live_currency", sa.String(length=3), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
            sa.CheckConstraint("match_outcome IN ('exact', 'alias', 'ladder', 'manual', 'unmatched')", name="ck_cost_price_change_lines_match_outcome"),
            sa.CheckConstraint("line_state IN ('changed', 'unchanged', 'new_link', 'needs_attention', 'skipped')", name="ck_cost_price_change_lines_line_state"),
            sa.CheckConstraint("decision IS NULL OR decision IN ('accepted', 'rejected')", name="ck_cost_price_change_lines_decision"),
        )
        op.create_index("ix_cost_price_change_lines_set", "cost_price_change_lines", ["change_set_id"])
        op.create_index("ix_cost_price_change_lines_product", "cost_price_change_lines", ["product_id"])

    if not _has_table(bind, "product_supplier_costs"):
        op.create_table(
            "product_supplier_costs",
            sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
            sa.Column("company_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("companies.id"), nullable=True),
            sa.Column("product_supplier_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("product_suppliers.id", ondelete="CASCADE"), nullable=False),
            sa.Column("unit_cost", sa.Numeric(12, 2), nullable=False),
            sa.Column("currency", sa.String(length=3), nullable=False),
            sa.Column("start_date", sa.Date(), nullable=True),
            sa.Column("end_date", sa.Date(), nullable=True),
            sa.Column("source_change_line_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("cost_price_change_lines.id", ondelete="SET NULL"), nullable=True),
            sa.Column("created_by_user_id", sa.String(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
            sa.CheckConstraint("unit_cost >= 0", name="ck_product_supplier_costs_unit_cost_nonneg"),
            sa.CheckConstraint("end_date IS NULL OR start_date IS NULL OR end_date >= start_date", name="ck_product_supplier_costs_end_after_start"),
        )
        op.create_index("ix_product_supplier_costs_link_start", "product_supplier_costs", ["product_supplier_id", "start_date"])
        op.create_index("ix_product_supplier_costs_company_id", "product_supplier_costs", ["company_id"])

    if not _has_table(bind, "supplier_price_links"):
        op.create_table(
            "supplier_price_links",
            sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
            sa.Column("company_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("companies.id"), nullable=True),
            sa.Column("supplier_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=False),
            sa.Column("token", sa.String(length=64), nullable=False),
            sa.Column("recipient_name", sa.String(length=255), nullable=True),
            sa.Column("expires_at", sa.DateTime(), nullable=True),
            sa.Column("revoked_at", sa.DateTime(), nullable=True),
            sa.Column("issued_by_user_id", sa.String(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("revoked_by_user_id", sa.String(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("last_opened_at", sa.DateTime(), nullable=True),
            sa.Column("open_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        )
        op.create_index("uq_supplier_price_links_token", "supplier_price_links", ["token"], unique=True)
        op.create_index("ix_supplier_price_links_supplier", "supplier_price_links", ["supplier_id"])
        op.create_index("ix_supplier_price_links_company_id", "supplier_price_links", ["company_id"])

    # ------------------------------------------------------------------------- columns
    op.execute(
        "ALTER TABLE system_settings ADD COLUMN IF NOT EXISTS "
        "cost_price_verification_enabled boolean NOT NULL DEFAULT false"
    )
    op.execute("ALTER TABLE audit_logs ALTER COLUMN action TYPE VARCHAR(40)")

    # ------------------------------------------------------------------------- permissions
    for slug, name, descr in _NEW_PERMS:
        _insert_permission(bind, slug, name, descr)
    for target, source in _PURCHASING_SWEEP:
        _sweep(bind, target, source)
    for target, source in _PRODUCT_SUPPLIER_WRITE_SWEEP:
        _sweep(bind, target, source, skip_product_viewers=True)
    for target, source in _PRODUCT_ROLE_SWEEP:
        _sweep(bind, target, source)
    for slug in _ADMIN_GRANT_SLUGS:
        _grant_to_roles(bind, slug, _GRANT_ROLE_SLUGS)

    # ------------------------------------------------------------------------- seeds
    if _has_table(bind, "import_field_alias"):
        for field, alias in _ALIAS_SEEDS:
            bind.execute(
                sa.text(
                    """
                    INSERT INTO import_field_alias (id, doc_type, field, alias, created_at)
                    SELECT gen_random_uuid(), 'supplier_price_list', :field, :alias, now()
                    WHERE NOT EXISTS (
                        SELECT 1 FROM import_field_alias
                        WHERE doc_type = 'supplier_price_list' AND field = :field
                          AND alias = :alias AND supplier_id IS NULL
                    )
                    """
                ),
                {"field": field, "alias": alias},
            )

    if _has_table(bind, "document_numbering_rules"):
        from app.services.numbering_defaults import seed_cost_price_change_set_rule

        seed_cost_price_change_set_rule(bind)


def downgrade() -> None:
    """Removes only what `upgrade()` added. The four `procurement.product_suppliers.*` slugs
    predate this revision (`permission_registry._crud`, synced at startup) and were never
    enforced before it, so they and every grant on them stay: deleting them would also take
    grants admin and custom roles held before cpc1 (Blocking 3 of the review at 232e5706)."""
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "DELETE FROM user_role_permissions WHERE permission_id IN "
            "(SELECT id FROM user_permissions WHERE slug = ANY(:slugs))"
        ),
        {"slugs": list(_ADMIN_GRANT_SLUGS)},
    )
    bind.execute(sa.text("DELETE FROM user_permissions WHERE slug = ANY(:slugs)"), {"slugs": list(_ADMIN_GRANT_SLUGS)})
    bind.execute(sa.text("DELETE FROM import_field_alias WHERE doc_type = 'supplier_price_list'"))
    if _has_table(bind, "document_numbering_rules"):
        bind.execute(sa.text("DELETE FROM document_numbering_rules WHERE doc_type = 'cost_price_change_set'"))

    # `product_supplier_costs.source_change_line_id` references the lines table: drop it first.
    for table in ("product_supplier_costs", "cost_price_change_lines", "cost_price_change_sets", "supplier_price_links"):
        if _has_table(bind, table):
            op.drop_table(table)
    op.execute("ALTER TABLE system_settings DROP COLUMN IF EXISTS cost_price_verification_enabled")
