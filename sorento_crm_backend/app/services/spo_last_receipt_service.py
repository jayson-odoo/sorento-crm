"""SPO allocations last SPO line per product (A6, chatbot-growth-r1; reworded 8 Sep 2026,
chatbot-warehouse-entity-and-last-in).

`documentation/plans/chatbot/PLAN-chatbot-warehouse-entity-and-last-in.md` section "Last
in"; `chatbot-warehouse-entity-and-last-in-acceptance-criteria.md` AC-4..AC-9b.

One focused module, same reason as `purchase_order_service.py` - this reads,
never writes.

Owner ruling verbatim, 8 Sep 2026: "last in should be per product, if we resolve to
entire family then return the latest receipt for each of the product"; "last in doesn't
relate to GR actually, it is purely last SPO ... based on the delivery date column at the
SPO"; "ignore GR entirely, i am okay with the gate allowed, yes expected date, yes one row
per product". The ORDERING is therefore the SPO's own date and nothing else - no
`receipt_status` filter, no inbound-shipment arrival column (those belong to the `incoming`
domain).

Second ruling the same day, against the rendered answer: a row reads product code, SPO
quantity, GR quantity if any, SPO date, GR date if any, warehouse. So the GR figures come
BACK as reported fields - what "ignore GR entirely" rules out is GR deciding WHICH line
answers, not GR being shown on the line that did.

Ordering key per line (`spo_date`): `expected_date` (the SPO line's promised delivery),
falling back to `issue_date`, then `created_at::date` for the ~3% of lines with neither.
`spo_date_source` names which column answered ("expected" / "issued" / "recorded") so the
presenter never labels a bookkeeping timestamp as a promised delivery. `created_at DESC` is
a deterministic TIEBREAK only, for lines sharing the same date - it carries no business
meaning of its own.

`gr_quantity` is `quantity_received`, and it is None when zero: the column defaults to 0
and is never null, so zero means "nothing received", which is absence rather than a figure
worth printing beside the ordered quantity.

`gr_date` is `picking_headers.picking_date` reached through `picking_lines.spo_allocation_id`,
`picking_status = 'approved'` only. Measured on the local prod copy `sorento_ai_automation_0907`
(8 Sep 2026): 987 of 987 approved headers carry a `picking_date`, 2,043 allocations have at
least one approved GRN line, and NONE has more than one distinct approved header - so
`max(picking_date)` per allocation is the whole rule, taken as ONE grouped join rather than
a per-row lookup. 74,300 allocations carry `quantity_received > 0` with no approved GRN row
at all (the ESB-stated path): those show a GR quantity and no GR date, which is what "if
any" means.

A RETIRED line never answers (#753). `spo_supply.visible_line_clauses()` is applied to
both branches, before the per-product window, so the line this tool calls "the last SPO
line" is one the SPO document itself still shows. Reused rather than restated as
`retired_at IS NULL`: that predicate is stricter than every other listing and would hide a
retired line carrying a receipt, which #753 keeps visible on purpose (R2 - stock
physically arrived against it, and this is the one question that is about receipts).

Follow-up (8 Sep 2026): one row per product only applies when the caller actually NAMED
products. `product_ids` empty is an unscoped ask - the tool is reachable directly by the
AI assistant, not gated behind a resolved product - and one row per product across the
whole table is thousands of rows. With no `product_ids`, `top_n` is instead a plain cap
over the same ordering, across every product, so an unscoped call costs exactly `top_n`
rows regardless of how many products exist.
"""
from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import Date, case, cast, func
from sqlalchemy.orm import Session

from app.models.base import get_company_scope
from app.models.inventory import Warehouse
from app.models.procurement import PickingHeader, PickingLine, SPOAllocation
from app.models.product import Product
from app.services.company_scope import build_company_predicate
from app.services.scm.spo_supply import visible_line_clauses


def _plain_number(v: Any) -> Any:
    if v is None:
        return None
    from decimal import Decimal

    try:
        d = Decimal(str(v))
    except Exception:  # noqa: BLE001
        return v
    return int(d) if d == d.to_integral_value() else float(d)


def _gr_date_subquery(db: Session):
    """`allocation_id -> max(approved picking_date)`, ONE grouped read, never per row.

    COMPANY SCOPE, EXPLICITLY, on both tables: `.subquery()` loses the
    `with_loader_criteria` the session's `do_orm_execute` listener injects, and the outer
    queries below name neither `PickingLine` nor `PickingHeader`, so without this a GRN
    date from another company could reach the answer. Same hand-ANDed predicate, same
    reason, as `order_service.py`'s `_order_summary`.
    """
    q = (
        db.query(
            PickingLine.spo_allocation_id.label("allocation_id"),
            func.max(PickingHeader.picking_date).label("gr_date"),
        )
        .join(PickingHeader, PickingHeader.id == PickingLine.picking_header_id)
        .filter(
            PickingHeader.picking_status == "approved",
            PickingLine.spo_allocation_id.isnot(None),
        )
    )
    for model in (PickingLine, PickingHeader):
        predicate = build_company_predicate(model, get_company_scope(db))
        if predicate is not None:
            q = q.filter(predicate)
    return q.group_by(PickingLine.spo_allocation_id).subquery()


def last_receipt_rows(
    db: Session,
    *,
    product_ids: Optional[list[str]] = None,
    warehouse_ids: Optional[list[str]] = None,
    top_n: int = 1,
) -> list[dict]:
    """The last `top_n` SPO lines PER PRODUCT (default 1) when `product_ids` is given.
    With NO `product_ids`, `top_n` is instead a plain cap over ALL products - the same
    ordering key, newest first, any product - so an unscoped call (the AI assistant can
    reach this tool without a resolved product) costs exactly `top_n` rows rather than one
    per product across the whole table.

    `warehouse_ids` filters lines to those warehouses BEFORE the pick, so a line at an
    excluded warehouse never displaces one at an included warehouse. In the per-product
    case, rows are grouped product by product, in `product_code` order; within a product
    (or, unscoped, within the single overall list), newest key first, `created_at DESC`
    breaking a tie on the same date.

    A line hidden from the SPO listings by #753 (`visible_line_clauses()`: retired AND
    never received) is excluded from BOTH branches, before the window - so a retired line
    can never be picked as the newest and then displace the newest visible one.

    Row keys: `spo_number`, `container_number` (None when the line was not ingested from a
    shipping order naming its container), `product_id`, `product_code`, `product_name`,
    `spo_quantity`, `gr_quantity` (None when nothing received), `spo_date`,
    `spo_date_source`, `gr_date` (None when no approved GRN line), `warehouse`.
    """
    top_n = max(int(top_n or 1), 1)
    key_expr = func.coalesce(
        SPOAllocation.expected_date, SPOAllocation.issue_date, cast(SPOAllocation.created_at, Date)
    )
    source_expr = case(
        (SPOAllocation.expected_date.isnot(None), "expected"),
        (SPOAllocation.issue_date.isnot(None), "issued"),
        else_="recorded",
    )
    gr = _gr_date_subquery(db)

    if product_ids:
        rn = (
            func.row_number()
            .over(
                partition_by=SPOAllocation.product_id,
                order_by=(key_expr.desc().nulls_last(), SPOAllocation.created_at.desc()),
            )
            .label("rn")
        )

        numbered = db.query(
            SPOAllocation.id.label("allocation_id"),
            SPOAllocation.spo_number,
            SPOAllocation.container_number,
            SPOAllocation.product_id,
            SPOAllocation.warehouse_id,
            SPOAllocation.allocated_quantity,
            SPOAllocation.quantity_received,
            key_expr.label("spo_date"),
            source_expr.label("spo_date_source"),
            rn,
        ).filter(SPOAllocation.product_id.in_(product_ids), *visible_line_clauses())
        if warehouse_ids:
            numbered = numbered.filter(SPOAllocation.warehouse_id.in_(warehouse_ids))
        # COMPANY SCOPE, EXPLICITLY. `.subquery()` loses the `with_loader_criteria` the
        # session's `do_orm_execute` listener injects, and the outer query below names
        # only `Product` / `Warehouse` - so nothing else in this branch scopes the LINES.
        # Measured 8 Sep 2026: under a Mocha scope this returned a Sorento-owned line on
        # a Mocha product. Same hand-ANDed predicate, same reason, as
        # `order_service.py`'s `_order_summary`. The unscoped branch below needs none:
        # it names `SPOAllocation` as an entity, so the listener fires there.
        predicate = build_company_predicate(SPOAllocation, get_company_scope(db))
        if predicate is not None:
            numbered = numbered.filter(predicate)
        sub = numbered.subquery()

        rows = (
            db.query(
                sub.c.spo_number,
                sub.c.container_number,
                sub.c.allocated_quantity,
                sub.c.quantity_received,
                sub.c.spo_date,
                sub.c.spo_date_source,
                gr.c.gr_date,
                Product.id.label("product_id"),
                Product.product_code,
                Product.product_name,
                Warehouse.warehouse_code,
            )
            .join(Product, Product.id == sub.c.product_id)
            .outerjoin(Warehouse, Warehouse.id == sub.c.warehouse_id)
            .outerjoin(gr, gr.c.allocation_id == sub.c.allocation_id)
            .filter(sub.c.rn <= top_n)
            .order_by(Product.product_code.asc(), sub.c.rn.asc())
            .all()
        )
    else:
        # Unscoped: NOT windowed per product - a plain top_n over every line, newest first.
        q = (
            db.query(
                SPOAllocation.spo_number,
                SPOAllocation.container_number,
                SPOAllocation.allocated_quantity,
                SPOAllocation.quantity_received,
                key_expr.label("spo_date"),
                source_expr.label("spo_date_source"),
                gr.c.gr_date,
                Product.id.label("product_id"),
                Product.product_code,
                Product.product_name,
                Warehouse.warehouse_code,
            )
            .join(Product, Product.id == SPOAllocation.product_id)
            .outerjoin(Warehouse, Warehouse.id == SPOAllocation.warehouse_id)
            .outerjoin(gr, gr.c.allocation_id == SPOAllocation.id)
            .filter(*visible_line_clauses())
        )
        if warehouse_ids:
            q = q.filter(SPOAllocation.warehouse_id.in_(warehouse_ids))
        rows = (
            q.order_by(key_expr.desc().nulls_last(), SPOAllocation.created_at.desc())
            .limit(top_n)
            .all()
        )

    out: list[dict] = []
    for row in rows:
        received = _plain_number(row.quantity_received)
        out.append(
            {
                "spo_number": row.spo_number,
                "container_number": row.container_number,
                "product_id": str(row.product_id),
                "product_code": row.product_code,
                "product_name": row.product_name,
                "spo_quantity": _plain_number(row.allocated_quantity),
                # Zero is ABSENCE, not a figure: the column defaults to 0 and is never
                # null, and the zero rows are the OPEN lines this tool exists to surface.
                "gr_quantity": received if (received is not None and received > 0) else None,
                "spo_date": row.spo_date.isoformat() if row.spo_date else None,
                "spo_date_source": row.spo_date_source,
                "gr_date": row.gr_date.isoformat() if row.gr_date else None,
                "warehouse": row.warehouse_code,
            }
        )
    return out
