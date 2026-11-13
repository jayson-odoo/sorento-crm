"""Spare part request: an Order Inquiry type raised without a sales order.

SPARE-PART-ORDER-REQUEST (plan documentation/plans/purchasing/PLAN-spare-part-order-request-12nov.md,
"Build contract" / Data). Additive only:

* `projects.order_inquiries`: `inquiry_type` (default `sales_order`, CHECK), the request's own
  fields, and `project_sales_order_id` DROP NOT NULL behind a CHECK that keeps a sales order
  required for a `sales_order` inquiry. Both CHECKs go in NOT VALID and are then VALIDATEd, so
  the ALTER takes only a brief lock and the scan runs under a weaker one.
* `projects.order_inquiry_rows`: product, description, unit price and the submitted qty / unit
  price. All nullable.
* Permissions `procurement.spare_part_requests.create` and `.view` (the approver / purchasing
  read, as `procurement.purchase_requests.view`), granted to the admin roles (a permission
  granted to nobody reads as a broken feature).

Idempotent (`IF NOT EXISTS`, `ON CONFLICT DO NOTHING`).

Revision ID: spr_0001_spare_part_request
Revises: pimp_0001_import_value_maps
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "spr_0001_spare_part_request"
down_revision = "pimp_0001_import_value_maps"
branch_labels = None
depends_on = None

_PERMISSIONS = (
    (
        "procurement.spare_part_requests.create",
        "Create Spare Part Requests",
        "Raise, edit, submit and revise your own spare part requests, and open them on the Order "
        "Inquiries page. Approval runs on the spare part request stages in Form SLA configuration.",
    ),
    (
        "procurement.spare_part_requests.view",
        "View Spare Part Requests",
        "Open the Spare Part Requests list and the requests you can decide on as an approver of "
        "their current stage in Form SLA configuration.",
    ),
)
_ADMIN_ROLES = ("superadmin", "admin")

_HEADER_COLUMNS = (
    "ADD COLUMN IF NOT EXISTS inquiry_type VARCHAR(32) NOT NULL DEFAULT 'sales_order'",
    "ADD COLUMN IF NOT EXISTS currency VARCHAR(3)",
    "ADD COLUMN IF NOT EXISTS requested_by VARCHAR(100) REFERENCES users(id) ON DELETE SET NULL",
    "ADD COLUMN IF NOT EXISTS needed_by DATE",
    "ADD COLUMN IF NOT EXISTS default_location VARCHAR(80)",
    "ADD COLUMN IF NOT EXISTS reason TEXT",
    "ADD COLUMN IF NOT EXISTS submitted_at TIMESTAMP WITHOUT TIME ZONE",
    "ADD COLUMN IF NOT EXISTS approved_at TIMESTAMP WITHOUT TIME ZONE",
    "ADD COLUMN IF NOT EXISTS approved_by VARCHAR(100) REFERENCES users(id) ON DELETE SET NULL",
    "ADD COLUMN IF NOT EXISTS reject_reason TEXT",
)

_ROW_COLUMNS = (
    "ADD COLUMN IF NOT EXISTS product_id UUID REFERENCES products(id) ON DELETE SET NULL",
    "ADD COLUMN IF NOT EXISTS description TEXT",
    "ADD COLUMN IF NOT EXISTS unit_price NUMERIC(15, 4)",
    "ADD COLUMN IF NOT EXISTS requested_qty NUMERIC(15, 4)",
    "ADD COLUMN IF NOT EXISTS requested_unit_price NUMERIC(15, 4)",
    # The order the requester entered the lines in (1-based); NULL on a sales-order row.
    "ADD COLUMN IF NOT EXISTS line_no INTEGER",
)

_CHECKS = (
    ("ck_order_inquiries_type", "inquiry_type IN ('sales_order', 'spare_part_request')"),
    (
        "ck_order_inquiries_type_needs_so",
        "inquiry_type <> 'sales_order' OR project_sales_order_id IS NOT NULL",
    ),
)


def upgrade() -> None:
    bind = op.get_bind()
    op.execute("ALTER TABLE projects.order_inquiries " + ", ".join(_HEADER_COLUMNS))
    op.execute("ALTER TABLE projects.order_inquiry_rows " + ", ".join(_ROW_COLUMNS))
    for name, predicate in _CHECKS:
        exists = bind.execute(
            sa.text("SELECT 1 FROM pg_constraint WHERE conname = :n"), {"n": name}
        ).first()
        if exists is None:
            op.execute(
                f"ALTER TABLE projects.order_inquiries ADD CONSTRAINT {name} "
                f"CHECK ({predicate}) NOT VALID"
            )
        op.execute(f"ALTER TABLE projects.order_inquiries VALIDATE CONSTRAINT {name}")
    op.execute(
        "ALTER TABLE projects.order_inquiries ALTER COLUMN project_sales_order_id DROP NOT NULL"
    )

    for slug, name, desc in _PERMISSIONS:
        bind.execute(
            sa.text(
                """
                INSERT INTO user_permissions (id, slug, name, description, created_at)
                VALUES (gen_random_uuid()::text, :slug, :name, :desc, now())
                ON CONFLICT (slug) DO NOTHING
                """
            ),
            {"slug": slug, "name": name, "desc": desc},
        )
        bind.execute(
            sa.text(
                """
                INSERT INTO user_role_permissions (id, role_id, permission_id, assigned_at)
                SELECT gen_random_uuid()::text, r.id, p.id, now()
                  FROM user_roles r
                  JOIN user_permissions p ON p.slug = :slug
                 WHERE r.slug = ANY(:roles)
                ON CONFLICT (role_id, permission_id) DO NOTHING
                """
            ),
            {"slug": slug, "roles": list(_ADMIN_ROLES)},
        )


def downgrade() -> None:
    bind = op.get_bind()
    slugs = [slug for slug, _, _ in _PERMISSIONS]
    bind.execute(
        sa.text(
            "DELETE FROM user_role_permissions WHERE permission_id IN "
            "(SELECT id FROM user_permissions WHERE slug = ANY(:slugs))"
        ),
        {"slugs": slugs},
    )
    bind.execute(sa.text("DELETE FROM user_permissions WHERE slug = ANY(:slugs)"), {"slugs": slugs})
    # A spare part request has no sales order; it cannot survive NOT NULL coming back.
    op.execute("DELETE FROM projects.order_inquiries WHERE project_sales_order_id IS NULL")
    op.execute(
        "ALTER TABLE projects.order_inquiries ALTER COLUMN project_sales_order_id SET NOT NULL"
    )
    for name, _ in _CHECKS:
        op.execute(f"ALTER TABLE projects.order_inquiries DROP CONSTRAINT IF EXISTS {name}")
    op.execute(
        "ALTER TABLE projects.order_inquiry_rows "
        + ", ".join(
            f"DROP COLUMN IF EXISTS {c}"
            for c in (
                "product_id", "description", "unit_price", "requested_qty",
                "requested_unit_price", "line_no",
            )
        )
    )
    op.execute(
        "ALTER TABLE projects.order_inquiries "
        + ", ".join(
            f"DROP COLUMN IF EXISTS {c}"
            for c in (
                "inquiry_type", "currency", "requested_by", "needed_by", "default_location",
                "reason", "submitted_at", "approved_at", "approved_by", "reject_reason",
            )
        )
    )
