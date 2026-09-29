"""A production-like volume of sales orders, lines and linked DO lines, generated in SQL.

Used by `test_sales_achievement_perf.py` (#1319) and, with larger counts, to seed a private
database for EXPLAIN (ANALYZE, BUFFERS) by hand. Raw SQL over `generate_series`, so a hundred
thousand lines take seconds, not the minutes the ORM helpers would. Every code starts `ZZTV`.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import List

from sqlalchemy import text


@dataclass
class Volume:
    agent_ids: List[str]
    category_ids: List[str]
    product_ids: List[str]
    sales_orders: int
    sales_order_lines: int
    do_lines: int


def seed_volume(
    db,
    company_id: str,
    *,
    orders: int,
    lines_per_order: int = 4,
    agents: int = 30,
    products: int = 200,
    start: date = date(2023, 1, 1),
    days: int = 1460,
    do_every: int = 2,
) -> Volume:
    """`orders` sales orders of `agents` agents (one in 20 with no agent, one in 25 cancelled),
    spread evenly over `days` days from `start`, `lines_per_order` lines each on `products`
    products in a three-level category tree, and one linked DO line on every `do_every`th
    line, dated seven days after its order."""
    params = {"c": company_id, "start": start, "days": days}
    agent_ids = [
        r[0]
        for r in db.execute(
            text(
                "insert into sales_agents (id, sales_agent, description, is_active, follow_up, source, company_id) "
                "select gen_random_uuid(), 'ZZTV' || g || '-' || substr(md5(random()::text), 1, 6), "
                "'ZZTV agent ' || g, true, false, 'manual', :c from generate_series(1, :n) g returning id"
            ),
            {**params, "n": agents},
        )
    ]
    uom_id = db.execute(
        text(
            "insert into units_of_measure (id, uom_code, uom_name, decimal_places, is_active) "
            "values (gen_random_uuid(), 'ZZTV' || substr(md5(random()::text), 1, 8), 'ZZTV', 0, true) returning id"
        )
    ).scalar()
    # A root, three children and nine grandchildren: products hang off the grandchildren.
    def category(parent_id, n):
        return db.execute(
            text(
                "insert into product_categories (id, company_id, category_code, category_name, parent_category_id, "
                "is_active, search_synonyms, is_searchable) values (gen_random_uuid(), :c, "
                "'ZZTV' || substr(md5(random()::text), 1, 8), :name, :p, true, '[]'::jsonb, true) returning id"
            ),
            {**params, "name": f"ZZTV Cat {n}", "p": parent_id},
        ).scalar()

    root = category(None, "root")
    children = [category(root, f"c{i}") for i in range(3)]
    leaves = [category(child, f"c{i}{j}") for i, child in enumerate(children) for j in range(3)]
    product_ids = [
        r[0]
        for r in db.execute(
            text(
                "insert into products (id, company_id, product_code, product_name, category_id, base_uom_id, "
                "list_price, currency, variant_link_manual, has_serial_tracking, has_batch_tracking, is_active, "
                "is_searchable, is_discontinued, exclude_from_planning) "
                "select gen_random_uuid(), :c, 'ZZTV' || g || '-' || substr(md5(random()::text), 1, 6), "
                "'ZZTV product ' || g, (:leaves)[1 + g % cardinality(:leaves)], :uom, 0, 'MYR', "
                "false, false, false, true, true, false, false from generate_series(1, :n) g returning id"
            ),
            {**params, "n": products, "leaves": leaves, "uom": uom_id},
        )
    ]
    warehouse_id = db.execute(
        text(
            "insert into warehouses (id, company_id, warehouse_code, is_active, counts_as_available, "
            "fulfilment_planning) values (gen_random_uuid(), :c, 'ZZTV' || substr(md5(random()::text), 1, 8), "
            "true, true, false) returning id"
        ),
        params,
    ).scalar()

    db.execute(
        text(
            "insert into sales_orders (id, company_id, so_number, order_date, status, sales_agent_id) "
            "select gen_random_uuid(), :c, 'ZZTV' || g || '-' || substr(md5(random()::text), 1, 6), "
            ":start + (g % :days), case when g % 25 = 0 then 'cancelled' else 'open' end, "
            "case when g % 20 = 0 then null else (:agents)[1 + g % cardinality(:agents)] end "
            "from generate_series(1, :n) g"
        ),
        {**params, "n": orders, "agents": agent_ids},
    )
    db.execute(
        text(
            "insert into sales_order_lines (id, company_id, sales_order_id, product_id, qty_ordered, "
            "qty_delivered, line_total, line_status, purchasing_status) "
            "select gen_random_uuid(), :c, so.id, (:products)[1 + (abs(hashtext(so.id::text)) + k) % cardinality(:products)], "
            "10, 10, 100, 'open', 'not_reviewed' "
            "from sales_orders so cross join generate_series(1, :k) k "
            "where so.company_id = :c and so.so_number like 'ZZTV%'"
        ),
        {**params, "k": lines_per_order, "products": product_ids},
    )
    db.execute(
        text(
            "create temporary table zztv_do on commit drop as "
            "select row_number() over () as n, sol.id as sol_id, sol.product_id, so.order_date + 7 as do_date "
            "from sales_order_lines sol join sales_orders so on so.id = sol.sales_order_id "
            "where so.company_id = :c and so.so_number like 'ZZTV%'"
        ),
        params,
    )
    db.execute(text("delete from zztv_do where n % :e <> 0"), {"e": do_every})
    db.execute(
        text(
            "insert into orders (id, company_id, order_number, order_date, is_cancelled, kpi_warning, "
            "subtotal_amount, discount_amount, tax_amount, total_amount, synced_to_excel) "
            "select md5('zztv' || sol_id::text)::uuid, :c, 'ZZTV' || n || '-' || substr(md5(random()::text), 1, 6), "
            "do_date, false, false, 0, 0, 0, 0, false from zztv_do"
        ),
        params,
    )
    db.execute(
        text(
            "insert into order_lines (id, company_id, line_sequence, order_id, product_id, warehouse_id, "
            "quantity, sales_order_line_id) "
            "select gen_random_uuid(), :c, 1, md5('zztv' || sol_id::text)::uuid, product_id, :w, 10, sol_id "
            "from zztv_do"
        ),
        {**params, "w": warehouse_id},
    )
    counts = db.execute(
        text(
            "select (select count(*) from sales_orders where so_number like 'ZZTV%'), "
            "(select count(*) from sales_order_lines sol join sales_orders so on so.id = sol.sales_order_id "
            " where so.so_number like 'ZZTV%'), "
            "(select count(*) from zztv_do)"
        )
    ).one()
    return Volume(
        [str(a) for a in agent_ids],
        [str(c) for c in (root, *children, *leaves)],
        [str(p) for p in product_ids],
        *counts,
    )
