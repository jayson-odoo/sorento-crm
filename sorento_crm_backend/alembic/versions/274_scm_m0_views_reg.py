"""SCM M0 CP2 — position/consumption views + module registration (numbering, RBAC, catalog).

Builds on 273 (the scm schema + brain/public tables). Adds:
- 5 read-model views in the `scm` schema (decoupled: read only canonical public
  tables + the scm SO/PO tables — never inbound_shipments/spo_allocations/picking
  for on_order). Consumption reads DO `order_lines` because `stock_ledger` is
  snapshot/bulk-import only and carries no per-DO sales rows.
- Numbering rules for `sales_order` / `purchase_order` (SO-YYYY/MM-#### monthly).
- RBAC: 5 scm permission slugs granted to admin/superadmin + a new `purchasing` role.
- App-Store catalog row for `scm` (dormant: catalog row present, no tenant_modules row).

Revision ID: 274_scm_m0_views_reg
Revises: 273_scm_module_schema
Create Date: 2026-07-15
"""
import uuid
from datetime import datetime

from alembic import op
import sqlalchemy as sa


revision = "274_scm_m0_views_reg"
down_revision = "273_scm_module_schema"
branch_labels = None
depends_on = None


# --- view SQL (decoupling boundary; AC-M0.11) -------------------------------

_ON_ORDER_V = """
CREATE VIEW scm.on_order_v AS
SELECT pol.product_id, pol.warehouse_id,
       SUM(pol.qty_ordered - pol.qty_received) AS on_order
FROM purchase_order_lines pol
JOIN purchase_orders po ON po.id = pol.purchase_order_id
WHERE po.status IN ('active', 'received', 'partial', 'closed')  -- placed POs only; drafts are NOT supply (M4-D5)
  AND pol.qty_ordered > pol.qty_received
GROUP BY pol.product_id, pol.warehouse_id;
"""

_COMMITTED_V = """
CREATE VIEW scm.committed_v AS
SELECT sol.product_id, sol.warehouse_id,
       SUM(sol.qty_ordered - sol.qty_delivered) AS committed
FROM sales_order_lines sol
JOIN sales_orders so ON so.id = sol.sales_order_id
WHERE so.status = 'open'
  AND sol.qty_ordered > sol.qty_delivered
GROUP BY sol.product_id, sol.warehouse_id;
"""

_CONSUMPTION_V = """
CREATE VIEW scm.consumption_v AS
SELECT ol.product_id, ol.warehouse_id, o.order_date::date AS day,
       SUM(ol.quantity) AS qty_out, ms.demand_nature
FROM order_lines ol
JOIN orders o ON o.id = ol.order_id
LEFT JOIN customers c ON c.id = o.customer_id
LEFT JOIN market_segments ms ON ms.code = c.market_segment_code
WHERE o.is_cancelled = false
GROUP BY ol.product_id, ol.warehouse_id, o.order_date::date, ms.demand_nature;
"""

_NET_POSITION_V = """
CREATE VIEW scm.net_position_v AS
WITH keys AS (
    SELECT product_id, warehouse_id FROM stock
    UNION
    SELECT product_id, warehouse_id FROM scm.on_order_v
    UNION
    SELECT product_id, warehouse_id FROM scm.committed_v
)
SELECT k.product_id, k.warehouse_id,
       COALESCE(s.quantity_on_hand, 0) AS quantity_on_hand,
       COALESCE(oo.on_order, 0) AS on_order,
       COALESCE(cm.committed, 0) AS committed,
       COALESCE(s.quantity_on_hand, 0) + COALESCE(oo.on_order, 0) - COALESCE(cm.committed, 0) AS net_position
FROM keys k
LEFT JOIN stock s ON s.product_id = k.product_id AND s.warehouse_id = k.warehouse_id
LEFT JOIN scm.on_order_v oo ON oo.product_id = k.product_id AND oo.warehouse_id = k.warehouse_id
LEFT JOIN scm.committed_v cm ON cm.product_id = k.product_id AND cm.warehouse_id = k.warehouse_id;
"""

_RECEIPT_LEAD_V = """
CREATE VIEW scm.receipt_lead_v AS
SELECT po.id AS po_id, po.supplier_id, pl.product_id,
       po.issue_date, ph.picking_date AS receipt_date,
       (ph.picking_date - po.issue_date) AS lead_days,
       ph.inspection_status, pl.qty_accepted, pl.qty_rejected
FROM picking_headers ph
JOIN picking_lines pl ON pl.picking_header_id = ph.id
JOIN purchase_order_lines pol ON pol.id = pl.po_line_id
JOIN purchase_orders po ON po.id = pol.purchase_order_id
WHERE ph.picking_type = 'goods_received'
  AND ph.source_entity_type = 'purchase_order';
"""


# --- RBAC constants ---------------------------------------------------------

_SCM_PERMS = [
    ("scm.dashboard.view", "View SCM dashboard", "View the supply-chain / reorder dashboard and position views."),
    ("scm.reorder.run", "Run reorder engine", "Trigger a reorder run that produces recommendations."),
    ("scm.recommendation.manage", "Manage reorder recommendations", "Review, override, approve, or reject reorder recommendations."),
    ("scm.policy.manage", "Manage reorder policies", "Create, update, and delete reorder / scoring / demand policies."),
    ("scm.config.manage", "Manage SCM configuration", "Manage SCM module configuration, budgets, and reason vocabularies."),
]
_GRANT_ROLE_SLUGS = ("admin", "superadmin", "purchasing")
_PURCHASING_ROLE_SLUG = "purchasing"


def upgrade() -> None:
    conn = op.get_bind()
    now = datetime.utcnow()

    # --- a. views (dependency order: leaves before net_position_v) ---
    op.execute(_ON_ORDER_V)
    op.execute(_COMMITTED_V)
    op.execute(_CONSUMPTION_V)
    op.execute(_RECEIPT_LEAD_V)
    op.execute(_NET_POSITION_V)

    # --- b. numbering rules (monthly reset; {month:02d} => zero-padded MM) ---
    for doc_type, prefix in (
        ("sales_order", "SO-{year}/{month:02d}-"),
        ("purchase_order", "PO-{year}/{month:02d}-"),
    ):
        conn.execute(
            sa.text(
                """
                INSERT INTO document_numbering_rules
                    (id, doc_type, enabled, prefix_template, number_digits,
                     next_value, start_value, reset_policy, created_at, updated_at)
                VALUES (:id, :dt, true, :prefix, 4, 1, 1, 'monthly', :now, :now)
                ON CONFLICT (doc_type) DO NOTHING
                """
            ),
            {"id": str(uuid.uuid4()), "dt": doc_type, "prefix": prefix, "now": now},
        )

    # --- c. RBAC: purchasing role + 5 scm slugs + grants ---
    role = conn.execute(
        sa.text("SELECT id FROM user_roles WHERE slug = :s"),
        {"s": _PURCHASING_ROLE_SLUG},
    ).fetchone()
    if role is None:
        conn.execute(
            sa.text(
                """
                INSERT INTO user_roles (id, slug, name, description, is_trashed,
                                        is_protected, is_default, created_at)
                VALUES (:id, :slug, :name, :desc, false, false, false, :now)
                ON CONFLICT (slug) DO NOTHING
                """
            ),
            {
                "id": str(uuid.uuid4()),
                "slug": _PURCHASING_ROLE_SLUG,
                "name": "Purchasing",
                "desc": "Supply-chain / purchasing operators: reorder dashboard, runs, recommendations.",
                "now": now,
            },
        )

    perm_ids: list[str] = []
    for slug, name, desc in _SCM_PERMS:
        row = conn.execute(
            sa.text("SELECT id FROM user_permissions WHERE slug = :s"), {"s": slug}
        ).fetchone()
        if row is None:
            pid = str(uuid.uuid4())
            conn.execute(
                sa.text(
                    """
                    INSERT INTO user_permissions (id, slug, name, description, created_at)
                    VALUES (:id, :slug, :name, :desc, :now)
                    ON CONFLICT (slug) DO NOTHING
                    """
                ),
                {"id": pid, "slug": slug, "name": name, "desc": desc, "now": now},
            )
            # re-read in case of a concurrent/ON CONFLICT no-op
            row = conn.execute(
                sa.text("SELECT id FROM user_permissions WHERE slug = :s"), {"s": slug}
            ).fetchone()
        perm_ids.append(row.id)

    role_ids = [
        r.id
        for r in conn.execute(
            sa.text("SELECT id FROM user_roles WHERE slug = ANY(:slugs)"),
            {"slugs": list(_GRANT_ROLE_SLUGS)},
        ).fetchall()
    ]
    for rid in role_ids:
        for pid in perm_ids:
            conn.execute(
                sa.text(
                    """
                    INSERT INTO user_role_permissions (id, role_id, permission_id, assigned_at)
                    VALUES (:id, :r, :p, :now)
                    ON CONFLICT (role_id, permission_id) DO NOTHING
                    """
                ),
                {"id": str(uuid.uuid4()), "r": rid, "p": pid, "now": now},
            )

    # --- d. App-Store catalog row (dormant: row present, no tenant_modules row) ---
    conn.execute(
        sa.text(
            """
            INSERT INTO app_modules_catalog
                (id, module_key, display_name, description, sort_order, is_core, dependencies)
            VALUES (:id, 'scm', :name, :desc, :sort, false,
                    CAST(:deps AS jsonb))
            ON CONFLICT (module_key) DO NOTHING
            """
        ),
        {
            "id": str(uuid.uuid4()),
            "name": "Supply Chain & Inventory Optimisation",
            "desc": "Reorder engine, net-position views, demand classification, supplier performance.",
            "sort": "900",
            "deps": '["base", "inventory", "order", "procurement", "product"]',
        },
    )


def downgrade() -> None:
    conn = op.get_bind()

    # --- d. catalog row (cascades any tenant_modules rows via FK) ---
    conn.execute(sa.text("DELETE FROM app_modules_catalog WHERE module_key = 'scm'"))

    # --- c. RBAC grants + slugs + purchasing role ---
    slugs = [p[0] for p in _SCM_PERMS]
    perm_ids = [
        r.id
        for r in conn.execute(
            sa.text("SELECT id FROM user_permissions WHERE slug = ANY(:s)"),
            {"s": slugs},
        ).fetchall()
    ]
    if perm_ids:
        conn.execute(
            sa.text("DELETE FROM user_role_permissions WHERE permission_id = ANY(:p)"),
            {"p": perm_ids},
        )
        conn.execute(
            sa.text("DELETE FROM user_permissions WHERE id = ANY(:p)"),
            {"p": perm_ids},
        )
    # Remove the purchasing role (grants already gone; cascade covers user_role_assignments).
    conn.execute(
        sa.text("DELETE FROM user_roles WHERE slug = :s"),
        {"s": _PURCHASING_ROLE_SLUG},
    )

    # --- b. numbering rules ---
    conn.execute(
        sa.text("DELETE FROM document_numbering_rules WHERE doc_type = ANY(:d)"),
        {"d": ["sales_order", "purchase_order"]},
    )

    # --- a. views (dependents first) ---
    op.execute("DROP VIEW IF EXISTS scm.net_position_v CASCADE")
    op.execute("DROP VIEW IF EXISTS scm.on_order_v CASCADE")
    op.execute("DROP VIEW IF EXISTS scm.committed_v CASCADE")
    op.execute("DROP VIEW IF EXISTS scm.consumption_v CASCADE")
    op.execute("DROP VIEW IF EXISTS scm.receipt_lead_v CASCADE")
