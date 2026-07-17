"""SCM M0 demo seed (CP3) — curated demo on REAL products, idempotent.

Lays a curated, re-runnable demo on top of the local prod-copy DB so the M0
position/consumption views (``scm.net_position_v``, ``scm.committed_v``,
``scm.on_order_v``, ``scm.receipt_lead_v``, ``scm.consumption_v``) return
non-trivial numbers and the M1+ engine has realistic inputs.

Everything this script writes is tagged ``source_system='seed'`` (on tables that
carry the column) or with an ``SCM-SEED-`` code prefix (suppliers, goods-receipts)
so a re-run first tears its own rows down and re-inserts — counts stay stable,
no duplicates.

DATA REALITY honored here (confirmed against the live copy):
- ``stock_ledger`` is snapshot/bulk-import only — it carries NO per-DO outflow.
  Real consumption lives in ``order_lines`` (delivery orders). SKU movement is
  therefore picked from ``order_lines``, never the ledger.
- EVERY product ships with null/0 ``cost_price``. Valuation / ABC / cash all
  need a cost, so the ~20 demo SKUs get one. When ``list_price > 0`` we use
  ``cost_price = round(list_price * 0.60, 2)``; but many fast movers have
  ``list_price = 0/NULL``, so those get a DETERMINISTIC RM 20-300 fallback keyed
  off a stable md5 of the product_code (re-runs identical). A re-run resets
  these back to NULL first. This keeps ``product_suppliers.unit_cost``, stock
  valuation and ABC value non-zero for every demo SKU.
- ``market_segments`` has ``retail`` + ``project`` with null ``demand_nature`` —
  step 1 fills them (retail→continuous, project→spike).

Run (from sorento_crm_backend/, DB up):

    venv/bin/python scripts/seed_scm_demo.py

Idempotent — run it twice; the second run prints identical counts.
"""
from __future__ import annotations

import calendar
import hashlib
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import text

from app.database import SessionLocal
from app.models.order import SalesOrder, SalesOrderLine
from app.models.procurement import (
    Supplier,
    ProductSupplier,
    PurchaseOrder,
    PurchaseOrderLine,
    PickingHeader,
    PickingLine,
)
from app.models.scm import (
    ReorderPolicy,
    AbcXyzPolicy,
    SupplierScoringPolicy,
    CashRankingPolicy,
    PurchasingBudget,
    OverrideReason,
    ReasonActionMap,
)
from app.services.numbering_service import NumberingService

SEED = "seed"
SUPPLIER_CODE_PREFIX = "SCM-SEED-"
GRN_PREFIX = "SCM-SEED-GRN-"

# Deterministic reference "today" comes from the DB clock at run time.
TODAY = date.today()


def _d(x) -> Decimal:
    return Decimal(str(x))


def _cost_for(list_price, product_code: str) -> Decimal:
    """Demo cost_price for a SKU.

    Most SKUs carry a real ``list_price`` → cost = 60% of it. But many fast
    movers (WESERP10B, CWCY605, M-FH12-BLUE, ...) have ``list_price = 0/NULL``
    in the prod copy, which would zero out valuation / unit_cost / ABC / cash —
    a demo killer. For those we assign a DETERMINISTIC plausible fallback in
    RM 20-300 keyed off a STABLE hash of the product_code (md5, NOT Python's
    salted ``hash()``) so re-runs stay identical.
    """
    lp = _d(list_price) if list_price is not None else _d(0)
    if lp > 0:
        return (lp * Decimal("0.60")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    h = int(hashlib.md5((product_code or "").encode()).hexdigest(), 16)
    return (_d(20) + _d(h % 281)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------------------
# 1. Representative SKU selection (deterministic — stable ORDER BY + product_code
#    tie-break so re-runs pick the same set). Returns ordered, de-duplicated list
#    of dicts: {product_id, product_code, list_price, warehouse_id, pattern}.
# ---------------------------------------------------------------------------

def _primary_warehouse(db, product_id: str) -> str | None:
    """The SKU's primary warehouse = highest on-hand stock row; fall back to the
    warehouse it was most delivered from; else any stock row."""
    row = db.execute(
        text(
            """
            SELECT warehouse_id FROM stock
            WHERE product_id = :pid
            ORDER BY quantity_on_hand DESC, warehouse_id
            LIMIT 1
            """
        ),
        {"pid": product_id},
    ).fetchone()
    if row:
        return row[0]
    row = db.execute(
        text(
            """
            SELECT ol.warehouse_id
            FROM order_lines ol JOIN orders o ON o.id = ol.order_id AND o.is_cancelled = false
            WHERE ol.product_id = :pid
            GROUP BY ol.warehouse_id
            ORDER BY SUM(ol.quantity) DESC, ol.warehouse_id
            LIMIT 1
            """
        ),
        {"pid": product_id},
    ).fetchone()
    return row[0] if row else None


def pick_demo_skus(db) -> list[dict]:
    picked: dict[str, dict] = {}

    def add(rows, pattern, limit):
        n = 0
        for r in rows:
            if n >= limit:
                break
            pid = r[0]
            if pid in picked:
                continue
            picked[pid] = {
                "product_id": pid,
                "product_code": r[1],
                "list_price": r[2],
                "pattern": pattern,
            }
            n += 1

    # 6 fast movers — top by SUM(order_lines.quantity) on non-cancelled DOs,
    # restricted to genuinely high-frequency SKUs (>= 50 DOs) so a lumpy
    # big-qty/few-DO SKU doesn't masquerade as fast.
    fast = db.execute(
        text(
            """
            SELECT p.id, p.product_code, p.list_price
            FROM order_lines ol
            JOIN orders o ON o.id = ol.order_id AND o.is_cancelled = false
            JOIN products p ON p.id = ol.product_id
            GROUP BY p.id, p.product_code, p.list_price
            HAVING COUNT(DISTINCT ol.order_id) >= 50
            ORDER BY SUM(ol.quantity) DESC, p.product_code
            LIMIT 6
            """
        )
    ).fetchall()
    add(fast, "fast", 6)

    # 4 multi-warehouse — on-hand > 0 across >= 2 warehouses.
    multi = db.execute(
        text(
            """
            SELECT p.id, p.product_code, p.list_price
            FROM stock s JOIN products p ON p.id = s.product_id
            WHERE s.quantity_on_hand > 0
            GROUP BY p.id, p.product_code, p.list_price
            HAVING COUNT(DISTINCT s.warehouse_id) >= 2
            ORDER BY COUNT(DISTINCT s.warehouse_id) DESC, SUM(s.quantity_on_hand) DESC, p.product_code
            LIMIT 8
            """
        )
    ).fetchall()
    add(multi, "multi_warehouse", 4)

    # 4 stockout-with-history — total on-hand = 0 everywhere but has DO history.
    stockout = db.execute(
        text(
            """
            SELECT p.id, p.product_code, p.list_price
            FROM products p
            JOIN order_lines ol ON ol.product_id = p.id
            JOIN orders o ON o.id = ol.order_id AND o.is_cancelled = false
            WHERE COALESCE((SELECT SUM(s.quantity_on_hand) FROM stock s WHERE s.product_id = p.id), 0) = 0
              AND p.product_code <> 'TRANSPORT'
            GROUP BY p.id, p.product_code, p.list_price
            ORDER BY SUM(ol.quantity) DESC, p.product_code
            LIMIT 8
            """
        )
    ).fetchall()
    add(stockout, "stockout", 4)

    # 3 dead — on-hand > 0, never appeared on any order line.
    dead = db.execute(
        text(
            """
            SELECT p.id, p.product_code, p.list_price
            FROM stock s JOIN products p ON p.id = s.product_id
            WHERE s.quantity_on_hand > 0
              AND NOT EXISTS (SELECT 1 FROM order_lines ol WHERE ol.product_id = p.id)
            GROUP BY p.id, p.product_code, p.list_price
            ORDER BY SUM(s.quantity_on_hand) DESC, p.product_code
            LIMIT 8
            """
        )
    ).fetchall()
    add(dead, "dead", 3)

    # 3 lumpy/normal — big qty spread over few DOs (bursty demand signal).
    lumpy = db.execute(
        text(
            """
            SELECT p.id, p.product_code, p.list_price
            FROM order_lines ol
            JOIN orders o ON o.id = ol.order_id AND o.is_cancelled = false
            JOIN products p ON p.id = ol.product_id
            GROUP BY p.id, p.product_code, p.list_price
            HAVING SUM(ol.quantity) > 2000 AND COUNT(DISTINCT ol.order_id) BETWEEN 3 AND 30
            ORDER BY (SUM(ol.quantity) / COUNT(DISTINCT ol.order_id)) DESC, p.product_code
            LIMIT 8
            """
        )
    ).fetchall()
    add(lumpy, "lumpy", 3)

    skus = list(picked.values())
    for s in skus:
        s["warehouse_id"] = _primary_warehouse(db, s["product_id"])
    return skus


def pick_top_customers(db, limit: int = 8) -> list[dict]:
    rows = db.execute(
        text(
            """
            SELECT c.id, c.customer_code, c.customer_name, COUNT(DISTINCT o.id) dos
            FROM customers c
            JOIN orders o ON o.customer_id = c.id AND o.is_cancelled = false
            GROUP BY c.id, c.customer_code, c.customer_name
            ORDER BY dos DESC, c.customer_code
            LIMIT :lim
            """
        ),
        {"lim": limit},
    ).fetchall()
    return [{"id": r[0], "code": r[1], "name": r[2], "dos": r[3]} for r in rows]


def _segment_for(name: str) -> str:
    """Big steady distributors → retail; project/sanitaryware-style names → project."""
    n = (name or "").upper()
    project_kw = ("SANITARYWARE", "MOTION", "PROJECT", "CONSTRUCTION", "ENGINEERING")
    if any(k in n for k in project_kw):
        return "project"
    return "retail"


# ---------------------------------------------------------------------------
# Cleanup — remove this script's own prior output so a re-run is idempotent.
# ---------------------------------------------------------------------------

_SCM_SEED_TABLES = [
    "scm.reorder_policy",
    "scm.abc_xyz_policy",
    "scm.supplier_scoring_policy",
    "scm.cash_ranking_policy",
    "scm.purchasing_budget",
    "scm.override_reason",
    "scm.reason_action_map",
    "scm.demand_nature_map",
    "scm.supplier_performance",
    "scm.item_classification",
    "scm.demand_stat",
    "scm.reorder_recommendation",
    "scm.reorder_run",
    "scm.market_research_topic",
    "scm.market_signal",
    "scm.scm_analytics_run",
    "scm.market_research_run",
]


def cleanup(db) -> None:
    # 1. Reset cost_price on any product carried by a seeded supplier back to NULL.
    db.execute(
        text(
            """
            UPDATE products SET cost_price = NULL
            WHERE id IN (
                SELECT ps.product_id FROM product_suppliers ps
                JOIN suppliers su ON su.id = ps.supplier_id
                WHERE su.supplier_code LIKE :pfx
            )
            """
        ),
        {"pfx": SUPPLIER_CODE_PREFIX + "%"},
    )
    # 2. Reset segment tags on the recomputed top-N demo customers.
    for cust in pick_top_customers(db):
        db.execute(
            text("UPDATE customers SET market_segment_code = NULL WHERE id = :id AND market_segment_code IS NOT NULL"),
            {"id": cust["id"]},
        )
    # 3. Goods-receipts (picking_headers) this script created — cascade drops lines.
    db.execute(
        text("DELETE FROM picking_headers WHERE picking_number LIKE :pfx"),
        {"pfx": GRN_PREFIX + "%"},
    )
    # 4. scm.* seed rows (policies / vocab / config).
    for tbl in _SCM_SEED_TABLES:
        db.execute(text(f"DELETE FROM {tbl} WHERE source_system = :s"), {"s": SEED})
    # 5. Seed SO / PO (lines cascade via FK ondelete CASCADE).
    db.execute(text("DELETE FROM sales_orders WHERE source_system = :s"), {"s": SEED})
    db.execute(text("DELETE FROM purchase_orders WHERE source_system = :s"), {"s": SEED})
    # 6. Seed suppliers. The live supplier_id FK is ON DELETE RESTRICT (not the
    #    CASCADE the model declares), so drop the product_suppliers rows first.
    db.execute(
        text(
            """
            DELETE FROM product_suppliers
            WHERE supplier_id IN (SELECT id FROM suppliers WHERE supplier_code LIKE :pfx)
            """
        ),
        {"pfx": SUPPLIER_CODE_PREFIX + "%"},
    )
    db.execute(
        text("DELETE FROM suppliers WHERE supplier_code LIKE :pfx"),
        {"pfx": SUPPLIER_CODE_PREFIX + "%"},
    )
    db.flush()


# ---------------------------------------------------------------------------
# Seed
# ---------------------------------------------------------------------------

def seed(db) -> dict:
    counts: dict[str, int] = {}
    skus = pick_demo_skus(db)
    customers = pick_top_customers(db)

    # --- Step 1: market segment demand nature --------------------------------
    db.execute(text("UPDATE market_segments SET demand_nature = 'continuous' WHERE code = 'retail'"))
    db.execute(text("UPDATE market_segments SET demand_nature = 'spike' WHERE code = 'project'"))

    # --- Step 2 (cost): cost_price on the demo SKUs --------------------------
    # 60% of list_price when priced; deterministic RM 20-300 fallback for the
    # (many) SKUs whose real list_price is 0/NULL so nothing valuations to zero.
    for s in skus:
        cost = _cost_for(s["list_price"], s["product_code"])
        db.execute(
            text("UPDATE products SET cost_price = :c WHERE id = :id"),
            {"c": cost, "id": s["product_id"]},
        )
        s["cost_price"] = cost
    counts["products.cost_price_set"] = len(skus)

    # --- Step 3: suppliers + product_suppliers -------------------------------
    suppliers = [
        {"code": SUPPLIER_CODE_PREFIX + "001", "name": "Demo Ceramics Supply Sdn Bhd", "currency": "MYR",
         "country": "Malaysia", "city": "Klang"},
        {"code": SUPPLIER_CODE_PREFIX + "002", "name": "Demo Sanitary Trading", "currency": "MYR",
         "country": "Malaysia", "city": "Johor Bahru"},
        {"code": SUPPLIER_CODE_PREFIX + "003", "name": "Demo Overseas Fixtures Co", "currency": "CNY",
         "country": "China", "city": "Foshan"},
    ]
    sup_objs: list[Supplier] = []
    for sp in suppliers:
        obj = Supplier(
            supplier_code=sp["code"],
            supplier_name=sp["name"],
            contact_name="Demo Contact",
            email=f"sales@{sp['code'].lower()}.example",
            phone_number="+60-3-0000-0000",
            city=sp["city"],
            country=sp["country"],
            payment_terms_days=30,
            is_active=True,
        )
        db.add(obj)
        sup_objs.append(obj)
    db.flush()
    counts["suppliers"] = len(sup_objs)

    ps_count = 0
    for i, s in enumerate(skus):
        primary = sup_objs[i % 3]
        cost = s["cost_price"]
        db.add(
            ProductSupplier(
                product_id=s["product_id"],
                supplier_id=primary.id,
                standard_lead_time_days=14 + (i * 7) % 32,          # 14..45
                moq=50 + (i * 25) % 151,                            # 50..200
                order_multiple=6 + (i % 4) * 6,                     # 6/12/18/24
                unit_cost=cost,
                currency=suppliers[i % 3]["currency"],
                is_primary_supplier=True,
                lead_time_variability_days=_d(2 + (i % 9)),         # 2..10
            )
        )
        ps_count += 1
        s["primary_supplier"] = primary
    # A couple of SKUs get a SECOND (overseas) supplier to exercise selection.
    overseas = sup_objs[2]
    for s in skus[:2]:
        if s["primary_supplier"].id == overseas.id:
            continue
        db.add(
            ProductSupplier(
                product_id=s["product_id"],
                supplier_id=overseas.id,
                standard_lead_time_days=45,
                moq=100,
                order_multiple=12,
                unit_cost=s["cost_price"],
                currency="CNY",
                is_primary_supplier=False,
                lead_time_variability_days=_d(10),
            )
        )
        ps_count += 1
    db.flush()
    counts["product_suppliers"] = ps_count

    # --- Step 4: customer segment tags ---------------------------------------
    for cust in customers:
        db.execute(
            text("UPDATE customers SET market_segment_code = :code WHERE id = :id"),
            {"code": _segment_for(cust["name"]), "id": cust["id"]},
        )
    counts["customers.tagged"] = len(customers)

    numbering = NumberingService(db)

    # --- Step 5: open sales orders (committed demand) ------------------------
    # Use SKUs that have a warehouse (stock-backed preferred) so committed_v ties
    # into net_position_v. Take the first ~10 demo SKUs with a warehouse.
    so_skus = [s for s in skus if s["warehouse_id"]][:10]
    order_types = ["dealer", "project"]
    priorities = ["high", "medium", "low"]
    so_count = sol_count = 0
    for i, s in enumerate(so_skus):
        cust = customers[i % len(customers)]
        so_no = numbering.get_next_number("sales_order", commit_rule=False)
        so = SalesOrder(
            so_number=so_no,
            customer_id=cust["id"],
            order_date=TODAY - timedelta(days=i),
            order_type=order_types[i % 2],
            priority=priorities[i % 3],
            status="open",
            source_system=SEED,
            source_ref=f"demo-so-{i+1}",
        )
        db.add(so)
        db.flush()
        db.add(
            SalesOrderLine(
                sales_order_id=so.id,
                product_id=s["product_id"],
                warehouse_id=s["warehouse_id"],
                qty_ordered=_d(100 + (i * 40) % 320),   # 100..420
                qty_delivered=_d(0),
                priority=priorities[i % 3],
                line_status="open",
                source_system=SEED,
                source_ref=f"demo-so-{i+1}-1",
            )
        )
        so_count += 1
        sol_count += 1

    # --- Step 5b: committed demand ON a stockout SKU (attention signal) -------
    # A stockout WITH open committed demand is the sharpest reorder signal —
    # on-hand 0 everywhere but real customers are already waiting. The general
    # step-5 loop only reaches the first ~10 (fast+multi) SKUs, so the stockout
    # bucket (e.g. C-FH24) never gets an SO. Give every stockout demo SKU its
    # own open, high-priority SO to a real customer → committed_v > 0 for it.
    any_wh = db.execute(
        text("SELECT id FROM warehouses ORDER BY warehouse_code LIMIT 1")
    ).scalar()
    stockout_so_skus: list[dict] = []
    for i, s in enumerate(x for x in skus if x["pattern"] == "stockout"):
        cust = customers[i % len(customers)]
        wh = s["warehouse_id"] or any_wh
        so = SalesOrder(
            so_number=numbering.get_next_number("sales_order", commit_rule=False),
            customer_id=cust["id"],
            order_date=TODAY - timedelta(days=i),
            order_type="project",
            priority="high",
            status="open",
            source_system=SEED,
            source_ref=f"demo-stockout-so-{i+1}",
        )
        db.add(so)
        db.flush()
        db.add(
            SalesOrderLine(
                sales_order_id=so.id,
                product_id=s["product_id"],
                warehouse_id=wh,
                qty_ordered=_d(200 + (i * 50) % 300),   # 200..500
                qty_delivered=_d(0),
                priority="high",
                line_status="open",
                source_system=SEED,
                source_ref=f"demo-stockout-so-{i+1}-1",
            )
        )
        s["so_warehouse_id"] = wh
        stockout_so_skus.append(s)
        so_count += 1
        sol_count += 1
    # Fold stockout SKUs into the committed-demand set the verifier checks.
    so_skus = so_skus + stockout_so_skus
    counts["sales_orders"] = so_count
    counts["sales_order_lines"] = sol_count

    # --- Step 6: purchase orders + goods-receipt history ---------------------
    fast_skus = [s for s in skus if s["pattern"] == "fast" and s["warehouse_id"]]
    multi_skus = [s for s in skus if s["pattern"] == "multi_warehouse" and s["warehouse_id"]]
    # fall back to any warehouse-backed SKU if a bucket is short
    backfill = [s for s in skus if s["warehouse_id"]]

    def nth_fast(n):
        return fast_skus[n] if n < len(fast_skus) else backfill[n % len(backfill)]

    def nth_multi(n):
        return multi_skus[n] if n < len(multi_skus) else backfill[-(n + 1)]

    po_count = pol_count = grn_count = grl_count = 0

    # PO1 — ACTIVE, one open line on a FAST mover → non-zero on_order.
    po1_sku = nth_fast(0)
    po1_no = numbering.get_next_number("purchase_order", commit_rule=False)
    po1 = PurchaseOrder(
        po_number=po1_no,
        supplier_id=sup_objs[0].id,
        issue_date=TODAY - timedelta(days=10),
        expected_date=TODAY + timedelta(days=20),
        status="active",
        currency="MYR",
        source_system=SEED,
        source_ref="demo-po-active",
    )
    db.add(po1)
    db.flush()
    db.add(
        PurchaseOrderLine(
            purchase_order_id=po1.id,
            product_id=po1_sku["product_id"],
            warehouse_id=po1_sku["warehouse_id"],
            qty_ordered=_d(500),
            qty_received=_d(0),               # fully open → on_order = 500
            unit_cost=po1_sku["cost_price"],
            currency="MYR",
            expected_date=TODAY + timedelta(days=20),
            line_status="open",
            source_system=SEED,
            source_ref="demo-po-active-1",
        )
    )
    po_count += 1
    pol_count += 1

    # PO2/3/4 — fully received, each with a matching goods-receipt whose lead time
    # (picking_date - issue_date) is staggered so receipt_lead_v varies by supplier.
    received_specs = [
        # (supplier_idx, lead_days, [(sku, qty, reject)])
        (0, 12, [(nth_fast(1), 300, 0), (nth_fast(2), 200, 0)]),
        (1, 25, [(nth_fast(3), 400, 5), (nth_multi(0), 150, 0)]),
        (2, 40, [(nth_fast(4), 250, 8), (nth_multi(1), 120, 4)]),
    ]
    for j, (sidx, lead, lines) in enumerate(received_specs, start=2):
        issue = TODAY - timedelta(days=lead + 20 * (j - 1))
        receipt = issue + timedelta(days=lead)
        po = PurchaseOrder(
            po_number=numbering.get_next_number("purchase_order", commit_rule=False),
            supplier_id=sup_objs[sidx].id,
            issue_date=issue,
            expected_date=receipt,
            status="received",
            currency=suppliers[sidx]["currency"],
            source_system=SEED,
            source_ref=f"demo-po-recv-{j}",
        )
        db.add(po)
        db.flush()
        gh = PickingHeader(
            picking_number=f"{GRN_PREFIX}{j:03d}",
            picking_type="goods_received",
            source_entity_type="purchase_order",
            source_entity_id=po.id,
            picking_date=receipt,
            inspection_status="passed" if all(r == 0 for _, _, r in lines) else "partial_pass",
            picking_status="posted",
            notes=f"Seed goods-receipt for {po.po_number}",
        )
        db.add(gh)
        db.flush()
        for k, (sku, qty, reject) in enumerate(lines):
            pol = PurchaseOrderLine(
                purchase_order_id=po.id,
                product_id=sku["product_id"],
                warehouse_id=sku["warehouse_id"],
                qty_ordered=_d(qty),
                qty_received=_d(qty),          # fully received
                unit_cost=sku["cost_price"],
                currency=suppliers[sidx]["currency"],
                expected_date=receipt,
                line_status="received",
                source_system=SEED,
                source_ref=f"demo-po-recv-{j}-{k+1}",
            )
            db.add(pol)
            db.flush()
            db.add(
                PickingLine(
                    picking_header_id=gh.id,
                    po_line_id=pol.id,
                    product_id=sku["product_id"],
                    quantity_expected=qty,
                    quantity_picked=qty,
                    qty_accepted=qty - reject,
                    qty_rejected=reject,
                    picked_condition="good" if reject == 0 else "damaged",
                    unit_cost=sku["cost_price"],
                    destination_warehouse_id=sku["warehouse_id"],
                )
            )
            pol_count += 1
            grl_count += 1
        # ON-GR TRIGGER INTEGRATION POINT (AC-M2.11): this loop is the only writer of
        # the SCM PO→GR link (picking_type='goods_received' + source_entity_type=
        # 'purchase_order' + picking_lines.po_line_id) until M4's runtime create-GR-from-PO
        # lands. A runtime GR post would fire
        # ``analytics_service.on_goods_receipt_posted(db, po.supplier_id, pol.product_id)``
        # here to refresh just this supplier×product. The seed skips per-GR refresh on
        # purpose — callers run one full ``run_analytics`` after seeding instead.
        po_count += 1
        grn_count += 1
    counts["purchase_orders"] = po_count
    counts["purchase_order_lines"] = pol_count
    counts["goods_receipts"] = grn_count
    counts["goods_receipt_lines"] = grl_count

    # --- Step 7: policies + config -------------------------------------------
    db.add(
        ReorderPolicy(
            scope_type="global", scope_ref=None, policy_type="reorder_point",
            service_level=_d("0.95"), safety_stock_method="fixed_days", safety_days=_d(7),
            forecast_window_days=90, baseline_source="continuous_only",
            spike_handling="committed_only", buy_scope="network",
            dead_stock_days=180, overstock_days=120, is_active=True, priority=0,
            source_system=SEED, source_ref="demo-policy-global",
        )
    )
    # product-class policy: periodic-review, scoped to a real category code shared
    # by several fast movers (CB-FT).
    class_ref = db.execute(
        text(
            """
            SELECT pc.category_code
            FROM products p JOIN product_categories pc ON pc.id = p.category_id
            WHERE p.id = :pid
            """
        ),
        {"pid": next((s["product_id"] for s in skus if s["pattern"] == "fast"), skus[0]["product_id"])},
    ).scalar()
    db.add(
        ReorderPolicy(
            scope_type="product_class", scope_ref=class_ref, policy_type="periodic_review",
            service_level=_d("0.90"), safety_stock_method="fixed_days", safety_days=_d(10),
            review_period_days=30, forecast_window_days=90, baseline_source="continuous_only",
            spike_handling="committed_only", buy_scope="network",
            dead_stock_days=180, overstock_days=120, is_active=True, priority=10,
            source_system=SEED, source_ref="demo-policy-class",
        )
    )
    # SKU policy: statistical safety stock, higher service level.
    sku_policy_pid = next((s["product_id"] for s in skus if s["pattern"] == "fast"), skus[0]["product_id"])
    db.add(
        ReorderPolicy(
            scope_type="sku", scope_ref=sku_policy_pid, policy_type="reorder_point",
            service_level=_d("0.98"), safety_stock_method="statistical",
            forecast_window_days=90, baseline_source="continuous_only",
            spike_handling="committed_only", buy_scope="warehouse",
            dead_stock_days=180, overstock_days=120, is_active=True, priority=20,
            source_system=SEED, source_ref="demo-policy-sku",
        )
    )
    counts["reorder_policies"] = 3

    db.add(
        AbcXyzPolicy(
            # M2-locked convention: CUMULATIVE percent cut points (A<=80%, B<=95%).
            abc_a_pct=_d("80"), abc_b_pct=_d("95"),
            xyz_x_max=_d("0.50"), xyz_y_max=_d("1.00"),
            is_active=True, source_system=SEED, source_ref="demo-abcxyz",
        )
    )
    db.add(
        SupplierScoringPolicy(
            # M2-locked weights: even split delivery / quality.
            delivery_weight=_d("0.50"), quality_weight=_d("0.50"),
            grace_days=2, min_sample_size=3,
            is_active=True, source_system=SEED, source_ref="demo-supplier-scoring",
        )
    )
    db.add(
        CashRankingPolicy(
            weight_urgency=_d("0.40"), weight_margin=_d("0.30"), weight_abc=_d("0.10"),
            weight_priority=_d("0.10"), weight_committed=_d("0.10"),
            is_active=True, source_system=SEED, source_ref="demo-cash-ranking",
        )
    )
    period_start = TODAY.replace(day=1)
    period_end = TODAY.replace(day=calendar.monthrange(TODAY.year, TODAY.month)[1])
    db.add(
        PurchasingBudget(
            period_start=period_start, period_end=period_end,
            budget_amount=_d("500000.00"), currency="MYR", scope_type="global",
            note="Demo monthly purchasing budget.",
            source_system=SEED, source_ref="demo-budget",
        )
    )
    counts["abc_xyz_policy"] = 1
    counts["supplier_scoring_policy"] = 1
    counts["cash_ranking_policy"] = 1
    counts["purchasing_budget"] = 1

    # --- Step 8: feedback vocabulary -----------------------------------------
    reasons = [
        ("incoming_project", "Incoming project demand"),
        ("colour_dying", "Colour / SKU dying out"),
        ("cash", "Cash constraint"),
        ("supplier_deal", "Supplier deal / bulk discount"),
        ("too_much", "Recommended too much"),
        ("discontinued", "Product discontinued"),
        ("other", "Other"),
    ]
    for code, label in reasons:
        db.add(
            OverrideReason(
                reason_code=code, label=label, is_active=True,
                source_system=SEED, source_ref="demo-reason",
            )
        )
    counts["override_reasons"] = len(reasons)

    action_maps = [
        # discontinued → immediate mark-discontinued
        dict(reason_code="discontinued", suggested_action="mark_discontinued",
             trigger_type="immediate"),
        # too_much → pattern: lower the service level after N overrides in window
        dict(reason_code="too_much", suggested_action="lower_service_level",
             target_policy_field="service_level", trigger_type="pattern",
             threshold_n=3, window_days=90),
        # colour_dying → pattern: flag as dead stock
        dict(reason_code="colour_dying", suggested_action="flag_dead",
             trigger_type="pattern", threshold_n=3, window_days=90),
    ]
    for am in action_maps:
        db.add(ReasonActionMap(source_system=SEED, source_ref="demo-action-map", **am))
    counts["reason_action_maps"] = len(action_maps)

    return counts, skus, customers, so_skus, po1_sku


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------

def verify(db, skus, so_skus, po1_sku) -> None:
    print("\n=== VERIFICATION ===")

    so_pids = tuple(s["product_id"] for s in so_skus)
    committed_rows = db.execute(
        text(
            """
            SELECT COUNT(*) FROM scm.committed_v
            WHERE product_id = ANY(:pids) AND committed > 0
            """
        ),
        {"pids": list(so_pids)},
    ).scalar()
    print(f"committed_v rows with committed>0 for SO'd SKUs: {committed_rows} (expect >= 1)")

    on_order = db.execute(
        text("SELECT COALESCE(SUM(on_order),0) FROM scm.on_order_v WHERE product_id = :pid"),
        {"pid": po1_sku["product_id"]},
    ).scalar()
    print(f"on_order for active-PO SKU {po1_sku['product_code']}: {on_order} (expect > 0)")

    demo_pids = [s["product_id"] for s in skus]
    val = db.execute(
        text(
            """
            SELECT COUNT(*) FROM stock s JOIN products p ON p.id = s.product_id
            WHERE s.product_id = ANY(:pids) AND p.cost_price IS NOT NULL
            """
        ),
        {"pids": demo_pids},
    ).scalar()
    print(f"demo SKU stock rows with non-null cost_price (valuation-ready): {val}")

    lead_rows = db.execute(
        text(
            """
            SELECT supplier_id, product_id, lead_days, qty_accepted, qty_rejected
            FROM scm.receipt_lead_v
            ORDER BY lead_days
            """
        )
    ).fetchall()
    lead_vals = sorted({int(r[2]) for r in lead_rows if r[2] is not None})
    print(f"receipt_lead_v rows: {len(lead_rows)}; distinct lead_days: {lead_vals} (expect varied)")

    # sample net-position row for a fast mover in its primary warehouse
    fast = next((s for s in skus if s["pattern"] == "fast" and s["warehouse_id"]), None)
    if fast:
        row = db.execute(
            text(
                """
                SELECT p.product_code, w.warehouse_code, np.quantity_on_hand,
                       np.on_order, np.committed, np.net_position
                FROM scm.net_position_v np
                JOIN products p ON p.id = np.product_id
                JOIN warehouses w ON w.id = np.warehouse_id
                WHERE np.product_id = :pid AND np.warehouse_id = :wid
                """
            ),
            {"pid": fast["product_id"], "wid": fast["warehouse_id"]},
        ).fetchone()
        print("\nSample net_position_v row for fast mover:")
        if row:
            print(f"  product={row[0]} warehouse={row[1]} on_hand={row[2]} "
                  f"on_order={row[3]} committed={row[4]} net_position={row[5]}")
        else:
            print(f"  (no net_position_v row for {fast['product_code']} in its primary warehouse)")

    # --- Targeted cost/valuation checks for the named zero-list-price SKUs ----
    print("\n=== NAMED-SKU COST / VALUATION CHECKS ===")
    for code in ("WESERP10B", "CWCY605"):
        prow = db.execute(
            text("SELECT id, cost_price, list_price FROM products WHERE product_code = :c"),
            {"c": code},
        ).fetchone()
        if not prow:
            print(f"  {code}: NOT FOUND (not in demo set this run)")
            continue
        pid, cost_price, list_price = prow[0], prow[1], prow[2]
        val_row = db.execute(
            text(
                """
                SELECT np.warehouse_id, np.quantity_on_hand,
                       (np.quantity_on_hand * p.cost_price) AS valuation
                FROM scm.net_position_v np
                JOIN products p ON p.id = np.product_id
                WHERE np.product_id = :pid AND np.quantity_on_hand > 0
                ORDER BY np.quantity_on_hand DESC
                LIMIT 1
                """
            ),
            {"pid": pid},
        ).fetchone()
        unit_cost = db.execute(
            text(
                """
                SELECT ps.unit_cost
                FROM product_suppliers ps
                JOIN suppliers su ON su.id = ps.supplier_id
                WHERE ps.product_id = :pid AND ps.is_primary_supplier = true
                  AND su.supplier_code LIKE :pfx
                LIMIT 1
                """
            ),
            {"pid": pid, "pfx": SUPPLIER_CODE_PREFIX + "%"},
        ).scalar()
        print(f"  {code}: list_price={list_price} cost_price={cost_price} "
              f"primary product_suppliers.unit_cost={unit_cost}")
        if val_row:
            print(f"    net_position_v: warehouse={val_row[0]} on_hand={val_row[1]} "
                  f"valuation(on_hand*cost)={val_row[2]}  (expect > 0)")
        else:
            print("    net_position_v: no on-hand>0 row (SKU carries no positive stock)")

    # --- Stockout-with-committed-demand check (C-FH24) -----------------------
    print("\n=== STOCKOUT + COMMITTED CHECK ===")
    for code in ("C-FH24",):
        crow = db.execute(
            text(
                """
                SELECT COALESCE(SUM(cv.committed), 0)
                FROM scm.committed_v cv
                JOIN products p ON p.id = cv.product_id
                WHERE p.product_code = :c
                """
            ),
            {"c": code},
        ).scalar()
        onhand = db.execute(
            text(
                """
                SELECT COALESCE(SUM(s.quantity_on_hand), 0)
                FROM stock s JOIN products p ON p.id = s.product_id
                WHERE p.product_code = :c
                """
            ),
            {"c": code},
        ).scalar()
        print(f"  {code}: on_hand={onhand} committed(scm.committed_v)={crow} "
              f"(expect committed > 0 with on_hand ~0)")


def _guard_not_prod() -> None:
    """Refuse to run unless explicitly opted in AND pointed at a local DB.

    This is a DEMO seed: it writes cost_price onto real product rows and tags
    market_segments / customers. That is fine on the local prod-copy but must
    NEVER touch real production. Deploy applies migrations 273/274 + the CREATE
    grant only — never this script.
    """
    import os
    import re

    if os.environ.get("SCM_DEMO_SEED") != "1":
        raise SystemExit(
            "[seed_scm_demo] REFUSED. This mutates real product/customer rows (demo only).\n"
            "  Set SCM_DEMO_SEED=1 to confirm you are on a LOCAL/demo database, then re-run."
        )
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        for line in open(os.path.join(os.path.dirname(__file__), "..", ".env")):
            if line.startswith("DATABASE_URL"):
                url = line.split("=", 1)[1].strip().strip('"').strip("'")
                break
    host = ""
    m = re.search(r"@([^:/]+)[:/]", url)
    if m:
        host = m.group(1)
    if host not in ("localhost", "127.0.0.1", "::1"):
        raise SystemExit(
            f"[seed_scm_demo] REFUSED. DATABASE_URL host is '{host or '<unparseable>'}', not a recognized local host.\n"
            "  This demo seed only runs against a local/demo DB. Aborting to protect prod."
        )


def main() -> None:
    _guard_not_prod()
    db = SessionLocal()
    try:
        print(f"[seed_scm_demo] reference date = {TODAY}")
        cleanup(db)
        counts, skus, customers, so_skus, po1_sku = seed(db)
        db.commit()

        print("\n=== SEEDED COUNTS ===")
        for k in sorted(counts):
            print(f"  {k}: {counts[k]}")

        print("\n=== DEMO SKUs (by pattern) ===")
        by_pat: dict[str, list[str]] = {}
        for s in skus:
            by_pat.setdefault(s["pattern"], []).append(s["product_code"])
        for pat in ("fast", "multi_warehouse", "stockout", "dead", "lumpy"):
            print(f"  {pat}: {', '.join(by_pat.get(pat, []))}")

        print("\n=== TAGGED CUSTOMERS ===")
        for c in customers:
            print(f"  {c['name']} → {_segment_for(c['name'])} ({c['dos']} DOs)")

        verify(db, skus, so_skus, po1_sku)
        print("\n[seed_scm_demo] done.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
