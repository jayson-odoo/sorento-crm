"""SCM purchasing + fulfilment shared base (S0): every migration for the whole build.

Deliberately ONE migration for the entire feature's DDL. Four worktrees fork from this
revision and none of them may author a migration, because two independent heads is the
alembic dual-head that has already cost us a deploy. Confining the DDL here is what makes
the parallel schedule safe.

Five columns, one new table, one new scm policy table, and three seeds:

  * `sales_order_lines.required_date` - netting is impossible without a PER-LINE date. The
    header's `requested_delivery_date` is not enough: the order inquiry the business works
    from states a delivery date per line and one SO routinely carries several. See ADR-0011.
  * `sales_orders.demand_class` - project vs retail, resolved from the customer's market
    segment at import. Fulfilment priority is decided by it, so it belongs on the demand.
  * `spo_allocations.po_line_id` - the chain is PO -> SPO -> GRN and the table carried NO
    PO reference at all; only `picking_lines.po_line_id` existed, which is one step too
    late (goods-received, after the allocation decision was already made). NULLABLE because
    860 existing rows have no PO to point at and because stock can arrive against no PO.
  * `warehouses.counts_as_available` - is this location's stock available at all. Config,
    DEFAULT TRUE for every row: seeding it from the code naming convention would bake one
    client's convention into the engine AND silently exclude stock.
  * `warehouses.pool_warehouse_id` - which shared pool this location may draw on. The
    STRUCTURAL half, and what makes "use BRW" possible. Seeded from the convention but
    stored, never parsed at runtime, so a client whose codes look nothing like Sorento's
    repoints rows instead of needing code.

The two warehouse columns answer two different questions and must not be collapsed into
one flag: `BRW-BB` stock IS sellable but can only serve customer BB, so "sellable" cannot
also mean "may cover another location's demand". Collapsing them reintroduces the
per-warehouse netting defect that ADR-0011's amendment exists to fix.

Revision ID: 311_scm_purchasing_base
Revises: 310_form_sla_skip_stage
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "311_scm_purchasing_base"
down_revision = "310_form_sla_skip_stage"
branch_labels = None
depends_on = None


# Locations whose stock is held for one customer or is in a non-sellable state. Used ONLY
# to seed pool membership, never to decide availability - see the docstring.
_STATE_SUFFIXES = ("HOLD", "REWO", "RSV", "DFCT", "DISP", "CLR")


# Views this revision redefines. Module-level constants because `scripts/bootstrap_env`
# builds a fresh database by executing the view DDL straight out of the migration files
# instead of running migration bodies, so it has to be able to import the CURRENT
# definition. Migration 274 stays frozen as the original: it has already run everywhere,
# and editing a shipped migration's DDL would change history without changing any
# existing database. Ordered on_order_v and committed_v before net_position_v, which
# selects from both.
_ON_ORDER_V = """
CREATE VIEW scm.on_order_v AS
SELECT pol.product_id, pol.warehouse_id,
       SUM(pol.qty_ordered - pol.qty_received) AS on_order
FROM purchase_order_lines pol
JOIN purchase_orders po ON po.id = pol.purchase_order_id
WHERE po.status IN ('active', 'received', 'partial', 'closed')  -- placed POs only; drafts are NOT supply (M4-D5)
  AND pol.line_status = 'open'   -- a line that left the order book is no longer incoming
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
  AND sol.line_status = 'open'   -- a line closed short is no longer a commitment
  AND sol.qty_ordered > sol.qty_delivered
GROUP BY sol.product_id, sol.warehouse_id;
"""

# Recreated unchanged from migration 274. Dropping committed_v with CASCADE takes
# net_position_v with it, and net_position_v is what every downstream consumer reads.
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
       COALESCE(s.quantity_on_hand, 0) + COALESCE(oo.on_order, 0)
           - COALESCE(cm.committed, 0) AS net_position
FROM keys k
LEFT JOIN stock s ON s.product_id = k.product_id AND s.warehouse_id = k.warehouse_id
LEFT JOIN scm.on_order_v oo
  ON oo.product_id = k.product_id AND oo.warehouse_id = k.warehouse_id
LEFT JOIN scm.committed_v cm
  ON cm.product_id = k.product_id AND cm.warehouse_id = k.warehouse_id;
"""

_REDEFINED_VIEWS = (_ON_ORDER_V, _COMMITTED_V, _NET_POSITION_V)


# --- data seeds, callable from outside a migration run ------------------------------
# Both of these are reference data the module cannot function without: with no aliases the
# importer resolves no column headers, and with no priority policy nothing can be ranked.
# `scripts/bootstrap_env` builds a database with create_all + stamp and never executes a
# migration body, so a seed that lives only inside `upgrade()` silently does not exist on
# CI or on any freshly built environment. Exposed as functions taking a bind so the
# migration and the bootstrapper run the SAME code rather than two copies that drift.
# Both are idempotent, so calling them on an already-seeded database is a no-op.

def seed_import_field_aliases(bind) -> int:
    """Header aliases for the import channel. Returns rows inserted."""
    # Guarded inside rather than at the call site, so the bootstrapper cannot skip a check
    # the migration performs. Name resolution happens at call time, so `_has_table` being
    # defined further down the module is fine.
    if not _has_table(bind, "import_field_alias"):
        return 0
    inserted = 0
    for doc_type, field, alias, locale in _ALIASES:
        res = bind.execute(
            sa.text(
                """
                INSERT INTO import_field_alias (doc_type, field, alias, locale)
                VALUES (:d, :f, :a, :l)
                ON CONFLICT (doc_type, field, alias) DO NOTHING
                """
            ),
            {"d": doc_type, "f": field, "a": alias, "l": locale},
        )
        inserted += res.rowcount or 0
    return inserted


def seed_priority_policy(bind) -> int:
    """The day-one fulfilment ranking rule. Returns rows inserted (0 or 1)."""
    import json

    if not _has_table(bind, "priority_policy", schema="scm"):
        return 0
    exists = bind.execute(
        sa.text("SELECT 1 FROM scm.priority_policy WHERE is_active LIMIT 1")
    ).scalar()
    if exists:
        return 0
    bind.execute(
        sa.text(
            """
            INSERT INTO scm.priority_policy
                (name, is_active, factors, demand_class_weights, notes)
            VALUES (:n, true, CAST(:f AS jsonb), CAST(:d AS jsonb), :o)
            """
        ),
        {
            "n": "Today's rule (PO document sequence)",
            "f": json.dumps(_PRIORITY_FACTORS),
            "d": json.dumps({"project": 1.0, "retail": 0.4}),
            "o": (
                "Seeded to reproduce the manual answer so week-one output is "
                "checkable against what Ms Tee would have done by hand. The fairer "
                "need-by-within-demand-class weighting ships in the same release "
                "but is not active until someone switches it after reviewing the "
                "rank-delta preview."
            ),
        },
    )
    return 1

# Seeded so day-one ranking reproduces today's manual answer (PO document sequence
# dominant). The fairer need-by-within-class weighting ships in the same release but off,
# so Ms Tee can check the system against her own working before changing the rule.
_PRIORITY_FACTORS = {
    "po_document_sequence": 1.0,
    "demand_class": 0.0,
    "need_by_date": 0.0,
    "document_age": 0.0,
}

# (doc_type, field, alias, locale). Header wording varies and both English and Chinese
# appear in real files, so the importers resolve columns through this table instead of a
# literal tuple in code. Onboarding a client becomes INSERTs plus a re-run.
_ALIASES = [
    # outstanding sales orders
    ("outstanding_so", "so_number", "S/O NO", "en"),
    ("outstanding_so", "so_number", "SO NO", "en"),
    ("outstanding_so", "so_date", "SO DATE", "en"),
    ("outstanding_so", "debtor_code", "DEBTOR CODE", "en"),
    ("outstanding_so", "customer_name", "PROJECT/CUSTOMER", "en"),
    ("outstanding_so", "item_code", "ITEM CODE", "en"),
    ("outstanding_so", "item_code", "型号", "zh"),
    ("outstanding_so", "uom", "UOM", "en"),
    ("outstanding_so", "qty_outstanding", "QTY", "en"),
    ("outstanding_so", "required_date", "DELIVERY DATE", "en"),
    ("outstanding_so", "stock_location", "STOCK LOCATION", "en"),
    ("outstanding_so", "remark", "REMARK", "en"),
    # outstanding purchase orders
    ("outstanding_po", "po_number", "PO NO", "en"),
    ("outstanding_po", "po_date", "PO DATE", "en"),
    ("outstanding_po", "creditor_code", "CREDITOR CODE", "en"),
    ("outstanding_po", "supplier_name", "SUPPLIER", "en"),
    ("outstanding_po", "item_code", "ITEM CODE", "en"),
    ("outstanding_po", "uom", "UOM", "en"),
    ("outstanding_po", "qty_ordered", "QTY ORDERED", "en"),
    ("outstanding_po", "qty_received", "QTY RECEIVED", "en"),
    ("outstanding_po", "expected_date", "ETA", "en"),
    ("outstanding_po", "expected_date", "EXPECTED DATE", "en"),
    ("outstanding_po", "stock_location", "STOCK LOCATION", "en"),
    ("outstanding_po", "unit_cost", "UNIT COST", "en"),
    ("outstanding_po", "currency", "CURRENCY", "en"),
    # supplier inventory status (库存明细)
    ("supplier_inventory", "item_code", "型号", "zh"),
    ("supplier_inventory", "item_code", "MODEL", "en"),
    ("supplier_inventory", "brand", "商标", "zh"),
    ("supplier_inventory", "spec", "规格", "zh"),
    ("supplier_inventory", "product_name", "品名", "zh"),
    ("supplier_inventory", "qty_packed", "包装好库存", "zh"),
    ("supplier_inventory", "qty_unfinished", "空瓷", "zh"),
    ("supplier_inventory", "cbm_per_unit", "体积(cbm)", "zh"),
    ("supplier_inventory", "cbm_total", "总体积(cbm)", "zh"),
    ("supplier_inventory", "remark", "备注", "zh"),
    # pre-load / packing list (预装清单)
    ("packing_list", "item_code", "产品型号", "zh"),
    ("packing_list", "product_name", "品名", "zh"),
    ("packing_list", "spec", "规格", "zh"),
    ("packing_list", "qty", "数量", "zh"),
    ("packing_list", "cartons", "箱数", "zh"),
    ("packing_list", "net_weight", "净重", "zh"),
    ("packing_list", "gross_weight", "毛重", "zh"),
    ("packing_list", "cbm_per_unit", "体积(cbm)", "zh"),
    ("packing_list", "cbm_total", "总体积(cbm)", "zh"),
    ("packing_list", "unit_price", "RMB", "zh"),
    ("packing_list", "amount", "金额（rmb）", "zh"),
    ("packing_list", "brand", "商标", "zh"),
    ("packing_list", "container_no", "货柜号", "zh"),
    ("packing_list", "bl_no", "提单号", "zh"),
    ("packing_list", "remark", "备注", "zh"),
]


def _has_column(bind, table: str, column: str, schema: str = "public") -> bool:
    return bool(
        bind.execute(
            sa.text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_schema = :s AND table_name = :t AND column_name = :c"
            ),
            {"s": schema, "t": table, "c": column},
        ).scalar()
    )


def _has_table(bind, table: str, schema: str = "public") -> bool:
    return bool(
        bind.execute(
            sa.text(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_schema = :s AND table_name = :t"
            ),
            {"s": schema, "t": table},
        ).scalar()
    )


def upgrade() -> None:
    bind = op.get_bind()

    # --- 1. demand side: a per-line required date + the demand class ----------------
    if not _has_column(bind, "sales_order_lines", "required_date"):
        op.add_column(
            "sales_order_lines",
            sa.Column("required_date", sa.Date(), nullable=True),
        )
        op.create_index(
            "ix_sales_order_lines_required_date",
            "sales_order_lines",
            ["required_date"],
        )

    if not _has_column(bind, "sales_orders", "demand_class"):
        op.add_column(
            "sales_orders",
            sa.Column("demand_class", sa.String(length=32), nullable=True),
        )
        op.create_index("ix_sales_orders_demand_class", "sales_orders", ["demand_class"])

    # --- 2. the missing PO reference on the SPO allocation --------------------------
    if not _has_column(bind, "spo_allocations", "po_line_id"):
        op.add_column(
            "spo_allocations",
            sa.Column("po_line_id", postgresql.UUID(as_uuid=False), nullable=True),
        )
        op.create_foreign_key(
            "fk_spo_allocations_po_line_id",
            "spo_allocations",
            "purchase_order_lines",
            ["po_line_id"],
            ["id"],
            ondelete="SET NULL",
        )
        op.create_index(
            "ix_spo_allocations_po_line_id", "spo_allocations", ["po_line_id"]
        )

    # --- 3. availability (config) and pool membership (structural) ------------------
    if not _has_column(bind, "warehouses", "counts_as_available"):
        op.add_column(
            "warehouses",
            sa.Column(
                "counts_as_available",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("true"),
            ),
        )

    if not _has_column(bind, "warehouses", "pool_warehouse_id"):
        op.add_column(
            "warehouses",
            sa.Column("pool_warehouse_id", postgresql.UUID(as_uuid=False), nullable=True),
        )
        op.create_foreign_key(
            "fk_warehouses_pool_warehouse_id",
            "warehouses",
            "warehouses",
            ["pool_warehouse_id"],
            ["id"],
            ondelete="SET NULL",
        )
        op.create_index(
            "ix_warehouses_pool_warehouse_id", "warehouses", ["pool_warehouse_id"]
        )

    # Seed pool membership from the SITE-SUFFIX convention: a suffixed code points at its
    # bare site, a bare code points at itself. Idempotent JOIN-based "set to the correct
    # value where it differs" rather than "set where NULL", so a re-run corrects a prior
    # wrong value instead of leaving it. State-suffixed bins point at their site too: they
    # are excluded from planning by `counts_as_available`, not by having no pool.
    op.execute(
        sa.text(
            """
            UPDATE warehouses w
               SET pool_warehouse_id = pool.id
              FROM warehouses pool
             WHERE pool.warehouse_code = split_part(w.warehouse_code, '-', 1)
               AND (w.pool_warehouse_id IS DISTINCT FROM pool.id)
            """
        )
    )

    # --- 4. import column aliases ---------------------------------------------------
    if not _has_table(bind, "import_field_alias"):
        op.create_table(
            "import_field_alias",
            sa.Column(
                "id",
                postgresql.UUID(as_uuid=False),
                primary_key=True,
                server_default=sa.text("gen_random_uuid()"),
            ),
            sa.Column("doc_type", sa.String(length=64), nullable=False),
            sa.Column("field", sa.String(length=64), nullable=False),
            sa.Column("alias", sa.String(length=255), nullable=False),
            sa.Column("locale", sa.String(length=8), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=False),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.UniqueConstraint(
                "doc_type", "field", "alias", name="uq_import_field_alias_triple"
            ),
        )
        op.create_index(
            "ix_import_field_alias_doc_type_field",
            "import_field_alias",
            ["doc_type", "field"],
        )

    seed_import_field_aliases(bind)

    # --- 5. fulfilment priority policy (scm schema: advice dies with the module) -----
    if _has_table(bind, "reorder_policy", schema="scm") and not _has_table(
        bind, "priority_policy", schema="scm"
    ):
        op.create_table(
            "priority_policy",
            sa.Column(
                "id",
                postgresql.UUID(as_uuid=False),
                primary_key=True,
                server_default=sa.text("gen_random_uuid()"),
            ),
            sa.Column("name", sa.String(length=120), nullable=False),
            sa.Column(
                "is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")
            ),
            # Factor weights, keyed by factor name. JSONB rather than one column per factor
            # so adding a factor (or a demand class) is a data change, never a migration.
            sa.Column(
                "factors",
                postgresql.JSONB(),
                nullable=False,
                server_default=sa.text("'{}'::jsonb"),
            ),
            # Per demand-class multipliers, same reasoning: a third class is a row here.
            sa.Column(
                "demand_class_weights",
                postgresql.JSONB(),
                nullable=False,
                server_default=sa.text("'{}'::jsonb"),
            ),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=False),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=False),
                server_default=sa.func.now(),
                nullable=False,
            ),
            schema="scm",
        )
        # Only ONE active policy at a time, enforced by the database rather than by
        # remembering to check - the same lesson as the system_settings singleton.
        op.create_index(
            "uq_scm_priority_policy_one_active",
            "priority_policy",
            ["is_active"],
            unique=True,
            postgresql_where=sa.text("is_active"),
            schema="scm",
        )

    seed_priority_policy(bind)

    # --- 8. one definition of committed demand, and of incoming supply --------------
    # `scm.committed_v` (migration 274) counted every outstanding line on an open sales
    # order, with no line-level predicate. The Coverage Timeline resolver requires
    # `line_status = 'open'`, because a line closed short is no longer a commitment:
    # its remaining quantity will never be delivered. Two readers disagreeing about
    # what "committed" means is the failure that makes a planning report untrustworthy
    # (the dashboard and the plan would print different figures for one SKU), so the
    # view is aligned to the resolver rather than the divergence being left latent.
    #
    # Numerically a no-op on today's data: every outstanding line on an open SO is
    # already `open`, verified before writing this. It changes behaviour only once
    # cancelled or short-closed lines exist, which is precisely when the old view
    # would have started over-counting.
    #
    # `scm.on_order_v` gains the SAME predicate on `purchase_order_lines.line_status`, and
    # for the same reason on the supply side. Closing a PO line is how the importer records
    # a line leaving the supplier's order book, and the alternatives are both worse: flipping
    # the ORDER's status would erase every other line still coming on that purchase order,
    # and setting `qty_received = qty_ordered` would fabricate a receipt no GRN supports,
    # which `scm.receipt_lead_v` and the picking reconciliation both read. Without this
    # predicate a closed line keeps counting as incoming supply forever, and overstated
    # supply is what stops a purchase that should have been made.
    op.execute("DROP VIEW IF EXISTS scm.net_position_v CASCADE")
    op.execute("DROP VIEW IF EXISTS scm.committed_v CASCADE")
    # No CASCADE: net_position_v is the only dependent and it is already gone, so anything
    # else that has grown a dependency on this view should fail loudly rather than be dropped
    # silently.
    op.execute("DROP VIEW IF EXISTS scm.on_order_v")
    for ddl in _REDEFINED_VIEWS:
        op.execute(ddl)


def downgrade() -> None:
    bind = op.get_bind()

    if _has_table(bind, "priority_policy", schema="scm"):
        op.drop_index(
            "uq_scm_priority_policy_one_active", table_name="priority_policy", schema="scm"
        )
        op.drop_table("priority_policy", schema="scm")

    if _has_table(bind, "import_field_alias"):
        op.drop_index("ix_import_field_alias_doc_type_field", table_name="import_field_alias")
        op.drop_table("import_field_alias")

    if _has_column(bind, "warehouses", "pool_warehouse_id"):
        op.drop_index("ix_warehouses_pool_warehouse_id", table_name="warehouses")
        op.drop_constraint("fk_warehouses_pool_warehouse_id", "warehouses", type_="foreignkey")
        op.drop_column("warehouses", "pool_warehouse_id")

    if _has_column(bind, "warehouses", "counts_as_available"):
        op.drop_column("warehouses", "counts_as_available")

    if _has_column(bind, "spo_allocations", "po_line_id"):
        op.drop_index("ix_spo_allocations_po_line_id", table_name="spo_allocations")
        op.drop_constraint(
            "fk_spo_allocations_po_line_id", "spo_allocations", type_="foreignkey"
        )
        op.drop_column("spo_allocations", "po_line_id")

    if _has_column(bind, "sales_orders", "demand_class"):
        op.drop_index("ix_sales_orders_demand_class", table_name="sales_orders")
        op.drop_column("sales_orders", "demand_class")

    if _has_column(bind, "sales_order_lines", "required_date"):
        op.drop_index("ix_sales_order_lines_required_date", table_name="sales_order_lines")
        op.drop_column("sales_order_lines", "required_date")
