"""SCM LIVE demo seed - additive-only, production-safe, fully reversible.

Unlike ``scripts/seed_scm_demo.py`` (which MUTATES real ``products.cost_price`` /
``customers.market_segment_code`` / ``market_segments.demand_nature`` and is hard-locked
to localhost), this script writes **only net-new rows** and NEVER touches an existing
(real) record. That makes it safe to run against a real production DB to stage a live SCM
reorder demo, then tear the whole thing back out with a single ``cleanup()`` keyed purely
on stable demo prefixes.

WHAT IT CREATES (all net-new, all tagged):
  * 1 isolation warehouse  ``warehouse_code = 'SCM-DEMO-WH'`` - ALL demo stock + all demo
    delivery-order (consumption) history lives here, so nothing bleeds into real warehouses.
  * 1 product category ``SCM-DEMO-CAT`` (namespace for the demo SKUs).
  * 6 suppliers   ``supplier_code LIKE 'SCM-DEMO-SUP-%'`` (realistic MYR/CNY lead profiles).
  * 4 customers   ``customer_code LIKE 'SCM-DEMO-CUS-%'``.
  * 13 products   ``product_code LIKE 'SCM-DEMO-P-%'`` staged into 4 engine scenarios
    (buy / stockout+committed / overstock / dead) + their ``product_suppliers`` sourcing rows.
  * stock rows in SCM-DEMO-WH, delivery-order demand history (``orders`` numbered
    ``SCM-DEMO-DO-%`` + ``order_lines``), open sales orders (committed demand) + received
    purchase orders with goods-received pickings (``picking_number LIKE 'SCM-DEMO-GRN-%'``)
    for supplier lead-time / quality scoring.
  * ``sales_orders`` / ``purchase_orders`` / ``scm.*`` policy rows carry
    ``source_system = 'scm_demo'``.

WHAT IT NEVER DOES:
  * Never SELECTs a real SKU / customer / supplier as a demo subject.
  * Never UPDATEs / DELETEs an existing row. Every scm.* policy insert is guarded on
    existence so it never duplicates what a migration already seeded.
  * Never runs analytics or a reorder run - it only stages inputs. The operator runs
    ``analytics_service.run_analytics(db)`` then triggers a reorder run afterward (printed
    reminder at the end).

SCENARIOS (numbers chosen so the deterministic engine, after analytics, emits the
intended outcome under the locked global policy - fixed_days SS 7d, service 0.95,
overstock 120d, dead 180d):
  * BUY (6):        low on-hand + steady recent DO history → net_position <= ROP → buy rec.
  * STOCKOUT (2):   on-hand 0 + recent DO history + an OPEN sales-order line (committed>0)
                    → net negative → strongest buy.
  * OVERSTOCK (3):  high on-hand + only light recent DO history → days_of_cover > 120 →
                    hold/overstock disposition (buy suppressed).
  * DEAD (2):       on-hand > 0 + exactly one DO dated > 180 days ago and nothing since →
                    last_movement > 180 → discontinue/dead disposition.

Run (from sorento_crm_backend/, DB reachable):

    SCM_LIVE_DEMO_SEED=1 venv/bin/python scripts/seed_scm_live_demo.py

Idempotent - a re-run tears its own rows down first (by prefix / source_system) and
re-inserts, so counts stay stable and nothing duplicates.
"""
from __future__ import annotations

import calendar
import os
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from sqlalchemy import text

from app.database import SessionLocal
from app.models.base import set_company_scope
from app.services.company_scope import register_company_scope_listeners
from app.models.inventory import Stock, Warehouse
from app.models.order import (
    Customer,
    Order,
    OrderLine,
    SalesOrder,
    SalesOrderLine,
)
from app.models.procurement import (
    PickingHeader,
    PickingLine,
    ProductSupplier,
    PurchaseOrder,
    PurchaseOrderLine,
    Supplier,
)
from app.models.product import Product, ProductCategory
from app.models.scm import CashRankingPolicy, PurchasingBudget, ReorderPolicy

# --- stable demo tags (the ONLY thing cleanup keys on) ----------------------
SOURCE = "scm_demo"
#: The company every demo row belongs to. Sorento is the only company with SCM data.
SORENTO_COMPANY_ID = "00000000-0000-0000-0000-000000000001"
WAREHOUSE_CODE = "SCM-DEMO-WH"
CATEGORY_CODE = "SCM-DEMO-CAT"
PRODUCT_PREFIX = "SCM-DEMO-P-"
SUPPLIER_PREFIX = "SCM-DEMO-SUP-"
CUSTOMER_PREFIX = "SCM-DEMO-CUS-"
DO_PREFIX = "SCM-DEMO-DO-"
SO_PREFIX = "SCM-DEMO-SO-"
PO_PREFIX = "SCM-DEMO-PO-"
GRN_PREFIX = "SCM-DEMO-GRN-"

TODAY = date.today()


def _d(x) -> Decimal:
    return Decimal(str(x))


def _cost(list_price) -> Decimal:
    return (_d(list_price) * Decimal("0.60")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------------------
# Demo data definitions
# ---------------------------------------------------------------------------

# lead = declared standard_lead_time_days on the product_supplier row.
SUPPLIERS: list[dict[str, Any]] = [
    dict(code="001", name="Kilang Seramik Klang Sdn Bhd", currency="MYR",
         city="Klang", state="Selangor", country="Malaysia", lead=14, terms=30,
         contact="Rahman Ibrahim", phone="+60-3-3345-1200"),
    dict(code="002", name="Selangor Sanitaryware Trading", currency="MYR",
         city="Shah Alam", state="Selangor", country="Malaysia", lead=18, terms=45,
         contact="Lim Wei Sheng", phone="+60-3-5510-8842"),
    dict(code="003", name="Foshan Ceramic Fixtures Co., Ltd", currency="CNY",
         city="Foshan", state="Guangdong", country="China", lead=40, terms=60,
         contact="Chen Jian", phone="+86-757-8320-9911"),
    dict(code="004", name="Johor Bathware Distributors Sdn Bhd", currency="MYR",
         city="Johor Bahru", state="Johor", country="Malaysia", lead=21, terms=30,
         contact="Nurul Aziz", phone="+60-7-3556-4400"),
    dict(code="005", name="Guangzhou Sanitary Imports Ltd", currency="CNY",
         city="Guangzhou", state="Guangdong", country="China", lead=38, terms=60,
         contact="Wang Lei", phone="+86-20-8388-2277"),
    dict(code="006", name="Penang Tile & Fixtures Sdn Bhd", currency="MYR",
         city="George Town", state="Penang", country="Malaysia", lead=16, terms=30,
         contact="Tan Mei Ling", phone="+60-4-2261-7788"),
]

# scenario buckets. ``sup`` = index into SUPPLIERS (primary sourcing supplier).
# buy/stockout: ``weekly`` qty repeated across 12 trailing weekly DOs (steady demand).
# stockout: ``committed`` = open sales-order qty (net goes negative).
# overstock: ``event`` qty on each of 3 light recent DOs; huge ``on_hand``.
# dead: ``event`` qty on a single DO ``dead_days_ago`` in the past; nothing since.
PRODUCTS: list[dict[str, Any]] = [
    # --- BUY (6) ---
    dict(code="001", name="Rimless Wall-Hung WC", scenario="buy", list=850,
         sup=0, moq=20, mult=10, on_hand=30, weekly=40),
    dict(code="002", name="Close-Coupled Toilet Suite", scenario="buy", list=620,
         sup=1, moq=12, mult=6, on_hand=20, weekly=30),
    dict(code="003", name="Wall-Mounted Basin 600mm", scenario="buy", list=240,
         sup=5, moq=24, mult=12, on_hand=60, weekly=55),
    dict(code="004", name="Chrome Basin Mixer Tap", scenario="buy", list=180,
         sup=1, moq=50, mult=25, on_hand=80, weekly=90),
    dict(code="005", name="Rain Shower Head 300mm", scenario="buy", list=320,
         sup=3, moq=30, mult=10, on_hand=40, weekly=45),
    dict(code="006", name="Concealed Cistern Frame", scenario="buy", list=540,
         sup=0, moq=15, mult=5, on_hand=15, weekly=25),
    # --- STOCKOUT + COMMITTED (2) ---
    dict(code="007", name="Freestanding Bathtub 1700mm", scenario="stockout", list=2600,
         sup=2, moq=10, mult=5, on_hand=0, weekly=12, committed=40),
    dict(code="008", name="Thermostatic Shower Valve", scenario="stockout", list=780,
         sup=4, moq=20, mult=10, on_hand=0, weekly=20, committed=60),
    # --- OVERSTOCK / HOLD (3) ---
    dict(code="009", name="Ceramic Soap Dispenser", scenario="overstock", list=60,
         sup=5, moq=100, mult=50, on_hand=1500, event=8),
    dict(code="010", name="Towel Rail 600mm Chrome", scenario="overstock", list=90,
         sup=1, moq=60, mult=30, on_hand=1200, event=10),
    dict(code="011", name="Toilet Brush Holder Set", scenario="overstock", list=45,
         sup=3, moq=120, mult=60, on_hand=900, event=6),
    # --- DEAD / DISCONTINUE (2) ---
    dict(code="012", name="Vintage Pedestal Basin (Legacy Line)", scenario="dead", list=380,
         sup=0, moq=10, mult=5, on_hand=220, event=30, dead_days_ago=205),
    dict(code="013", name="Brass Bidet Mixer (Legacy Line)", scenario="dead", list=460,
         sup=2, moq=10, mult=5, on_hand=140, event=20, dead_days_ago=200),
]

CUSTOMERS: list[dict[str, Any]] = [
    dict(code="001", name="Bina Ceramics Retail Sdn Bhd"),
    dict(code="002", name="Metro Bathroom Gallery"),
    dict(code="003", name="Skyline Construction Supplies Sdn Bhd"),
    dict(code="004", name="Harmony Home Renovation"),
]

# received PO + goods-received specs for supplier lead-time / quality scoring.
# lines = [(product_code_suffix, qty_received, qty_rejected)].
RECV_POS: list[dict[str, Any]] = [
    dict(sup=0, lead=12, grn="001", lines=[("001", 200, 0), ("006", 150, 0)]),
    dict(sup=1, lead=20, grn="002", lines=[("002", 180, 0), ("004", 220, 5)]),
    dict(sup=2, lead=42, grn="003", lines=[("007", 100, 8)]),
    dict(sup=3, lead=22, grn="004", lines=[("005", 120, 0)]),
    dict(sup=4, lead=39, grn="005", lines=[("008", 90, 4)]),
    dict(sup=5, lead=15, grn="006", lines=[("003", 200, 0), ("009", 300, 0)]),
]


# ---------------------------------------------------------------------------
# Cleanup - remove this script's own prior output (idempotent, prefix-keyed).
# ---------------------------------------------------------------------------

# Product / supplier id sub-selects reused across the analytics-teardown deletes.
_DEMO_PRODUCTS = f"SELECT id FROM products WHERE product_code LIKE '{PRODUCT_PREFIX}%'"
_DEMO_SUPPLIERS = f"SELECT id FROM suppliers WHERE supplier_code LIKE '{SUPPLIER_PREFIX}%'"


def cleanup(db) -> None:
    """Delete strictly the rows this script created, in FK-safe order.

    Keyed ONLY on the demo prefixes / warehouse / ``source_system='scm_demo'`` - it can
    never touch a real row. Also removes any analytics-derived rows the operator's
    ``run_analytics`` / reorder run produced FOR the demo products/suppliers (they carry
    ``source_system='engine'``/``'scm'`` so they are matched by demo product/supplier id,
    not by source tag) so a re-seed + re-run starts clean and uninstall is complete.
    """
    stmts = [
        # 1. delivery-order demand history (order_lines cascade on the order delete).
        f"DELETE FROM orders WHERE order_number LIKE '{DO_PREFIX}%'",
        # 2. open sales orders (committed demand) - lines cascade.
        f"DELETE FROM sales_orders WHERE source_system = '{SOURCE}'",
        # 3. goods-received pickings (picking_lines cascade) BEFORE their POs.
        f"DELETE FROM picking_headers WHERE picking_number LIKE '{GRN_PREFIX}%'",
        # 4. purchase orders - lines cascade.
        f"DELETE FROM purchase_orders WHERE source_system = '{SOURCE}'",
        # 5. analytics artifacts for demo subjects (recommendations, demand, class, perf).
        f"DELETE FROM scm.reorder_recommendation WHERE product_id IN ({_DEMO_PRODUCTS})",
        f"DELETE FROM scm.demand_stat WHERE product_id IN ({_DEMO_PRODUCTS})",
        f"DELETE FROM scm.item_classification WHERE product_id IN ({_DEMO_PRODUCTS})",
        f"DELETE FROM scm.supplier_performance "
        f"WHERE supplier_id IN ({_DEMO_SUPPLIERS}) OR product_id IN ({_DEMO_PRODUCTS})",
        # 6. stock rows (demo product OR demo warehouse).
        f"DELETE FROM stock WHERE product_id IN ({_DEMO_PRODUCTS}) "
        f"OR warehouse_id IN (SELECT id FROM warehouses WHERE warehouse_code = '{WAREHOUSE_CODE}')",
        # 7. sourcing rows.
        f"DELETE FROM product_suppliers "
        f"WHERE supplier_id IN ({_DEMO_SUPPLIERS}) OR product_id IN ({_DEMO_PRODUCTS})",
        # 8. products, then their namespace category.
        f"DELETE FROM products WHERE product_code LIKE '{PRODUCT_PREFIX}%'",
        f"DELETE FROM product_categories WHERE category_code = '{CATEGORY_CODE}'",
        # 9. customers + suppliers.
        f"DELETE FROM customers WHERE customer_code LIKE '{CUSTOMER_PREFIX}%'",
        f"DELETE FROM suppliers WHERE supplier_code LIKE '{SUPPLIER_PREFIX}%'",
        # 10. isolation warehouse.
        f"DELETE FROM warehouses WHERE warehouse_code = '{WAREHOUSE_CODE}'",
        # 11. scm.* policy rows this script may have seeded (only the demo-tagged ones).
        f"DELETE FROM scm.reorder_policy WHERE source_system = '{SOURCE}'",
        f"DELETE FROM scm.cash_ranking_policy WHERE source_system = '{SOURCE}'",
        f"DELETE FROM scm.purchasing_budget WHERE source_system = '{SOURCE}'",
    ]
    for sql in stmts:
        db.execute(text(sql))
    db.flush()


# ---------------------------------------------------------------------------
# Seed
# ---------------------------------------------------------------------------

def _get_or_create_warehouse(db) -> Warehouse:
    wh = db.query(Warehouse).filter(Warehouse.warehouse_code == WAREHOUSE_CODE).first()
    if wh:
        return wh
    wh = Warehouse(
        warehouse_code=WAREHOUSE_CODE,
        warehouse_name="SCM Demo Warehouse",
        location="Demo staging (SCM reorder co-pilot)",
        is_active=True,
    )
    db.add(wh)
    db.flush()
    return wh


def _get_or_create_category(db) -> ProductCategory:
    cat = db.query(ProductCategory).filter(ProductCategory.category_code == CATEGORY_CODE).first()
    if cat:
        return cat
    cat = ProductCategory(
        category_code=CATEGORY_CODE,
        category_name="Bathroom Fixtures (SCM Demo)",
        description="Net-new demo SKUs staged for the SCM reorder co-pilot.",
        is_active=True,
    )
    db.add(cat)
    db.flush()
    return cat


def _uom_id(db) -> str:
    uom = db.execute(text(
        "SELECT id FROM units_of_measure WHERE is_active = true ORDER BY uom_code LIMIT 1"
    )).scalar()
    if not uom:
        uom = db.execute(text("SELECT id FROM units_of_measure ORDER BY uom_code LIMIT 1")).scalar()
    if not uom:
        raise SystemExit("[seed_scm_live_demo] No units_of_measure row exists to reference. Aborting.")
    return uom


def seed(db) -> dict:
    counts: dict[str, int] = {}
    wh = _get_or_create_warehouse(db)
    cat = _get_or_create_category(db)
    uom_id = _uom_id(db)

    # --- suppliers ------------------------------------------------------------
    sup_objs: list[Supplier] = []
    for sp in SUPPLIERS:
        obj = Supplier(
            supplier_code=SUPPLIER_PREFIX + sp["code"],
            supplier_name=sp["name"],
            contact_name=sp["contact"],
            email=f"sales@{SUPPLIER_PREFIX.lower()}{sp['code']}.example",
            phone_number=sp["phone"],
            city=sp["city"],
            state=sp["state"],
            country=sp["country"],
            payment_terms_days=sp["terms"],
            is_active=True,
        )
        db.add(obj)
        sup_objs.append(obj)
    db.flush()
    counts["suppliers"] = len(sup_objs)

    # --- customers ------------------------------------------------------------
    cust_objs: list[Customer] = []
    for c in CUSTOMERS:
        obj = Customer(
            customer_code=CUSTOMER_PREFIX + c["code"],
            customer_name=c["name"],
            is_active=True,
            customer_type="company",
            country="Malaysia",
        )
        db.add(obj)
        cust_objs.append(obj)
    db.flush()
    counts["customers"] = len(cust_objs)

    # --- products + stock + product_suppliers --------------------------------
    prod_by_code: dict[str, Product] = {}
    ps_count = stock_count = 0
    for spec in PRODUCTS:
        cost = _cost(spec["list"])
        p = Product(
            product_code=PRODUCT_PREFIX + spec["code"],
            product_name=spec["name"],
            category_id=cat.id,
            base_uom_id=uom_id,
            list_price=_d(spec["list"]),
            cost_price=cost,
            currency="MYR",
            is_active=True,
            is_discontinued=False,
        )
        db.add(p)
        db.flush()
        prod_by_code[spec["code"]] = p

        db.add(Stock(
            product_id=p.id,
            warehouse_id=wh.id,
            quantity_on_hand=int(spec["on_hand"]),
            quantity_reserved=0,
        ))
        stock_count += 1

        sup = sup_objs[int(spec["sup"])]
        db.add(ProductSupplier(
            product_id=p.id,
            supplier_id=sup.id,
            standard_lead_time_days=SUPPLIERS[int(spec["sup"])]["lead"],
            moq=int(spec["moq"]),
            order_multiple=int(spec["mult"]),
            unit_cost=cost,
            currency=SUPPLIERS[spec["sup"]]["currency"],
            is_primary_supplier=True,
            lead_time_variability_days=_d(3),
        ))
        ps_count += 1
    counts["products"] = len(prod_by_code)
    counts["stock_rows"] = stock_count
    counts["product_suppliers"] = ps_count

    # --- delivery-order demand history (consumption) -------------------------
    do_seq = 0
    do_count = ol_count = 0

    def add_do(day_ago: int, lines: list[tuple[Product, int]]) -> None:
        nonlocal do_seq, do_count, ol_count
        if not lines:
            return
        do_seq += 1
        cust = cust_objs[(do_seq - 1) % len(cust_objs)]
        order = Order(
            order_number=f"{DO_PREFIX}{do_seq:03d}",
            order_date=datetime.combine(TODAY - timedelta(days=day_ago), datetime.min.time()) + timedelta(hours=10),
            customer_id=cust.id,
            is_cancelled=False,
            order_type="dealer",
            remarks="SCM live demo delivery order (net-new).",
        )
        db.add(order)
        db.flush()
        for seq, (prod, qty) in enumerate(lines, start=1):
            db.add(OrderLine(
                order_id=order.id,
                line_sequence=seq,
                product_id=prod.id,
                warehouse_id=wh.id,
                quantity=_d(qty),
                unit_price=prod.list_price,
            ))
            ol_count += 1
        do_count += 1

    frequent = [s for s in PRODUCTS if s["scenario"] in ("buy", "stockout")]
    overstock = [s for s in PRODUCTS if s["scenario"] == "overstock"]
    dead = [s for s in PRODUCTS if s["scenario"] == "dead"]

    # Steady demand: one DO per trailing week (12 weeks) carrying every frequent SKU.
    for i in range(12):
        lines = [(prod_by_code[s["code"]], int(s["weekly"])) for s in frequent]
        add_do(7 * i + 3, lines)

    # Light recent demand for overstock SKUs: 3 sparse small DOs.
    for day_ago in (8, 30, 58):
        lines = [(prod_by_code[s["code"]], int(s["event"])) for s in overstock]
        add_do(day_ago, lines)

    # Dead SKUs: a single DO in the distant past, nothing since (last_movement > 180d).
    for s in dead:
        add_do(int(s["dead_days_ago"]), [(prod_by_code[s["code"]], int(s["event"]))])

    counts["delivery_orders"] = do_count
    counts["delivery_order_lines"] = ol_count

    # --- open sales orders (committed demand on the stockout SKUs) ------------
    so_count = sol_count = 0
    for idx, spec in enumerate([s for s in PRODUCTS if s["scenario"] == "stockout"], start=1):
        p = prod_by_code[spec["code"]]
        cust = cust_objs[(idx - 1) % len(cust_objs)]
        so = SalesOrder(
            so_number=f"{SO_PREFIX}{idx:03d}",
            customer_id=cust.id,
            order_date=TODAY - timedelta(days=idx),
            order_type="project",
            priority="high",
            status="open",
            source_system=SOURCE,
            source_ref=f"live-demo-stockout-{idx}",
        )
        db.add(so)
        db.flush()
        db.add(SalesOrderLine(
            sales_order_id=so.id,
            product_id=p.id,
            warehouse_id=wh.id,
            qty_ordered=_d(spec["committed"]),
            qty_delivered=_d(0),
            priority="high",
            line_status="open",
            source_system=SOURCE,
            source_ref=f"live-demo-stockout-{idx}-1",
        ))
        so_count += 1
        sol_count += 1
    counts["sales_orders"] = so_count
    counts["sales_order_lines"] = sol_count

    # --- received purchase orders + goods-received pickings ------------------
    # Fully received (qty_received == qty_ordered) so they DO NOT inflate on_order, and
    # picking_type='goods_received' + source_entity_type='purchase_order' + po_line_id so
    # analytics scores supplier lead-time / quality the way scm.receipt_lead_v reads it.
    po_count = pol_count = grn_count = grl_count = 0
    for idx, rp in enumerate(RECV_POS, start=1):
        sup = sup_objs[int(rp["sup"])]
        issue = TODAY - timedelta(days=int(rp["lead"]) + 18)
        receipt = issue + timedelta(days=int(rp["lead"]))
        po = PurchaseOrder(
            po_number=f"{PO_PREFIX}{idx:03d}",
            supplier_id=sup.id,
            issue_date=issue,
            expected_date=receipt,
            status="received",
            currency=SUPPLIERS[int(rp["sup"])]["currency"],
            source_system=SOURCE,
            source_ref=f"live-demo-recv-{idx}",
        )
        db.add(po)
        db.flush()
        any_reject = any(rej for _, _, rej in rp["lines"])
        gh = PickingHeader(
            picking_number=f"{GRN_PREFIX}{rp['grn']}",
            picking_type="goods_received",
            source_entity_type="purchase_order",
            source_entity_id=po.id,
            picking_date=receipt,
            inspection_status="partial_pass" if any_reject else "passed",
            picking_status="posted",
            notes=f"SCM live demo goods-receipt for {po.po_number}.",
        )
        db.add(gh)
        db.flush()
        for k, (code, qty, reject) in enumerate(rp["lines"], start=1):
            p = prod_by_code[code]
            pol = PurchaseOrderLine(
                purchase_order_id=po.id,
                product_id=p.id,
                warehouse_id=wh.id,
                qty_ordered=_d(qty),
                qty_received=_d(qty),
                unit_cost=p.cost_price,
                currency=SUPPLIERS[int(rp["sup"])]["currency"],
                expected_date=receipt,
                line_status="received",
                source_system=SOURCE,
                source_ref=f"live-demo-recv-{idx}-{k}",
            )
            db.add(pol)
            db.flush()
            db.add(PickingLine(
                picking_header_id=gh.id,
                po_line_id=pol.id,
                product_id=p.id,
                quantity_expected=int(qty),
                quantity_picked=int(qty),
                qty_accepted=int(qty - reject),
                qty_rejected=int(reject),
                picked_condition="good" if reject == 0 else "damaged",
                unit_cost=p.cost_price,
                destination_warehouse_id=wh.id,
            ))
            pol_count += 1
            grl_count += 1
        po_count += 1
        grn_count += 1
    counts["purchase_orders"] = po_count
    counts["purchase_order_lines"] = pol_count
    counts["goods_receipts"] = grn_count
    counts["goods_receipt_lines"] = grl_count

    # --- scm.* policies (guarded - only create when absent; never duplicate) --
    counts["reorder_policy_created"] = _ensure_reorder_policy(db)
    counts["cash_ranking_policy_created"] = _ensure_cash_ranking_policy(db)
    counts["purchasing_budget_created"] = _ensure_purchasing_budget(db)

    return counts


def _ensure_reorder_policy(db) -> int:
    """Seed ONE global reorder policy only when no global row exists (migrations /
    the engine's ensure-defaults may already have seeded one). Never duplicates."""
    has_global = db.execute(text(
        "SELECT 1 FROM scm.reorder_policy WHERE scope_type = 'global' LIMIT 1"
    )).first()
    if has_global:
        return 0
    db.add(ReorderPolicy(
        scope_type="global", scope_ref=None, policy_type="reorder_point",
        service_level=_d("0.95"), safety_stock_method="fixed_days", safety_days=_d(7),
        review_period_days=30, forecast_window_days=90, baseline_source="continuous_only",
        spike_handling="committed_only", buy_scope="network",
        dead_stock_days=180, overstock_days=120, is_active=True, priority=0,
        source_system=SOURCE, source_ref="live-demo-policy-global",
    ))
    db.flush()
    return 1


def _ensure_cash_ranking_policy(db) -> int:
    """Seed a cash-ranking policy only when none active exists (migration 278 seeds one)."""
    has_cash = db.execute(text(
        "SELECT 1 FROM scm.cash_ranking_policy WHERE is_active = true LIMIT 1"
    )).first()
    if has_cash:
        return 0
    db.add(CashRankingPolicy(
        weight_urgency=_d("0.40"), weight_margin=_d("0.30"), weight_abc=_d("0.10"),
        weight_priority=_d("0.10"), weight_committed=_d("0.10"),
        is_active=True, source_system=SOURCE, source_ref="live-demo-cash-ranking",
    ))
    db.flush()
    return 1


def _ensure_purchasing_budget(db) -> int:
    """Seed a demo monthly purchasing budget only when no demo budget already exists."""
    has_budget = db.execute(text(
        f"SELECT 1 FROM scm.purchasing_budget WHERE source_system = '{SOURCE}' LIMIT 1"
    )).first()
    if has_budget:
        return 0
    period_start = TODAY.replace(day=1)
    period_end = TODAY.replace(day=calendar.monthrange(TODAY.year, TODAY.month)[1])
    db.add(PurchasingBudget(
        period_start=period_start, period_end=period_end,
        budget_amount=_d("500000.00"), currency="MYR", scope_type="global",
        note="SCM live demo monthly purchasing budget.",
        source_system=SOURCE, source_ref="live-demo-budget",
    ))
    db.flush()
    return 1


# ---------------------------------------------------------------------------
# Guard + entry point
# ---------------------------------------------------------------------------

def _banner() -> None:
    print("=" * 78)
    print("SCM LIVE DEMO SEED - additive-only, production-safe")
    print("-" * 78)
    print("Creates NET-NEW rows only; NEVER updates or deletes a real row.")
    print(f"  warehouse   : {WAREHOUSE_CODE}")
    print(f"  category    : {CATEGORY_CODE}")
    print(f"  suppliers   : {SUPPLIER_PREFIX}NNN   ({len(SUPPLIERS)})")
    print(f"  customers   : {CUSTOMER_PREFIX}NNN   ({len(CUSTOMERS)})")
    print(f"  products    : {PRODUCT_PREFIX}NNN     ({len(PRODUCTS)}: 6 buy / 2 stockout / 3 overstock / 2 dead)")
    print(f"  delivery DOs: {DO_PREFIX}NNN   (demand history in {WAREHOUSE_CODE})")
    print(f"  sales orders: {SO_PREFIX}NNN + purchase orders {PO_PREFIX}NNN (source_system='{SOURCE}')")
    print(f"  goods recv  : {GRN_PREFIX}NNN")
    print(f"  scm policies: reorder / cash-ranking / budget (source_system='{SOURCE}', guarded)")
    print("=" * 78)


def _guard() -> None:
    if os.environ.get("SCM_LIVE_DEMO_SEED") != "1":
        raise SystemExit(
            "[seed_scm_live_demo] REFUSED. Set SCM_LIVE_DEMO_SEED=1 to run.\n"
            "  This seed is ADDITIVE-ONLY (safe on production) but the flag is required to\n"
            "  confirm intent. It creates net-new demo rows and never mutates a real row."
        )


def main() -> None:
    _guard()
    _banner()
    # Owned rows are stamped with the session's company scope by an ORM `before_insert`
    # listener that `app/main.py` installs at startup. A script never imports main, so the
    # listener was absent, every insert below arrived with a NULL company_id, and the seed
    # died on the NOT NULL. Install it here, then say which company this is: the demo
    # belongs to Sorento, the same company the rest of these numbers describe.
    register_company_scope_listeners()
    db = SessionLocal()
    set_company_scope(db, frozenset({SORENTO_COMPANY_ID}))
    try:
        print(f"[seed_scm_live_demo] reference date = {TODAY}")
        cleanup(db)
        counts = seed(db)
        db.commit()

        print("\n=== SEEDED COUNTS ===")
        for k in sorted(counts):
            print(f"  {k}: {counts[k]}")

        print("\n=== SCENARIOS (product_code → expected engine outcome) ===")
        labels = {
            "buy": "BUY (net ≤ ROP)",
            "stockout": "STOCKOUT + committed (net < 0, strongest buy)",
            "overstock": "OVERSTOCK / hold (days-of-cover > 120)",
            "dead": "DEAD / discontinue (last movement > 180d)",
        }
        for scen in ("buy", "stockout", "overstock", "dead"):
            codes = [PRODUCT_PREFIX + s["code"] for s in PRODUCTS if s["scenario"] == scen]
            print(f"  {labels[scen]}:\n    {', '.join(codes)}")

        print("\n=== CLEANUP KEYS (to fully remove this demo) ===")
        print(f"  products      product_code   LIKE '{PRODUCT_PREFIX}%'")
        print(f"  suppliers     supplier_code  LIKE '{SUPPLIER_PREFIX}%'")
        print(f"  customers     customer_code  LIKE '{CUSTOMER_PREFIX}%'")
        print(f"  delivery DOs  order_number   LIKE '{DO_PREFIX}%'")
        print(f"  goods recv    picking_number LIKE '{GRN_PREFIX}%'")
        print(f"  warehouse     warehouse_code =    '{WAREHOUSE_CODE}'")
        print(f"  category      category_code  =    '{CATEGORY_CODE}'")
        print(f"  sales/purchase orders + scm.* policies  source_system = '{SOURCE}'")
        print("  Re-run this script (it calls cleanup() first) to tear down + re-seed.")

        print("\n=== NEXT STEPS (operator runs these - the seed does NOT) ===")
        print("  1. Refresh analytics so demand_stat / classification / supplier scores populate:")
        print("       from app.services.scm import analytics_service")
        print("       analytics_service.run_analytics(db)")
        print("  2. Trigger a reorder run (network scope) to emit buy / disposition recs:")
        print("       from app.services.scm import reorder_run_service")
        print("       run = reorder_run_service.create_run(db, warehouse_codes=None)")
        print("       # worker drains it, or call run_reorder(run['run_id']) synchronously.")
        print("\n[seed_scm_live_demo] done.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
