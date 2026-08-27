"""Stage 1 of the Loading Plan: the container request before CBM is fitted.

`PLAN-scm-loading-plan-demand-first.md` section 1 - Ms Tee's actual flow puts a request to the
supplier ahead of any container math: pick the supplier, look at what their stock list
identifies as theirs, ask for the full outstanding customer need against it (never capped by
what they already hold - that is shown beside the ask, never as a ceiling), send. Only once the
supplier reverts with a packing list does CBM matter, and that stage is unchanged
(`loading_plan_service`).

Two moves, two functions:

* `build` - a pure read. The candidate product set comes off the supplier's current stock
  list (`SupplierInventory` is a full-replace snapshot, so "current" already means "latest" -
  there is nothing to pick a most-recent-of), the quantity to ask for off the outstanding
  sales-order book, and the order off the ACTIVE Fulfilment Priority policy through
  `priority.factors_for_demand_rows` - the same call the fulfilment board makes, so a product
  cannot rank differently on the two screens (AC-H5).

  The row scope is the WHOLE stock list, not just the products with open SO need against it:
  the captain's ask is one table, because a separate "supplier inventory" table below the
  suggestion grid let a product with real stock but no open order silently drop off the
  screen Ms Tee was actually looking at. A stock-list product with no open need gets a
  demand-shaped row anyway - `suggested_qty` 0, no rank, `has_demand: false` - rather than
  being left for a second table. Demand rows keep ranks 1..N exactly as before (AC-H5 is
  unchanged); no-demand rows sort after them, by item code, because there is no priority
  score to order them by. A stock-list row with neither packed nor unfinished quantity AND
  no open need names nothing worth asking about or holding, so it is left out exactly as it
  always was.

  `suggested_qty` is NETTED (captain decision) against `on_hand` and `incoming_spo` only -
  `open_so_need - on_hand - incoming_spo`, floored at zero. `outstanding_po` (placed with a
  supplier but not yet allocated to a shipment, `scm.po_ordered_v`) is deliberately NOT
  subtracted (captain, 20 Aug follow-up, CWCY604 worked example): "don't need to deduct
  outstanding PO, need to deduct outstanding SPO" - an outstanding PO is not supply this
  container can count on, because it is often the very demand this request is asking the
  supplier to pack in the first place, whereas an SPO allocation is real incoming stock
  already on the water. `outstanding_po` still travels on every row (real context, and the
  PO column on screen stays) - only the subtraction is gone. This is a container-request-only
  rule; the reorder run's own netting is a separate question and untouched here. The gross
  figure stays on the row as `open_so_need` so the arithmetic is visible on screen
  (need - stock - incoming = suggestion); the project/retail/unclassified split is also
  gross, because it explains the NEED, not the netted ask. `include_lines=True` additionally
  returns the open SO lines behind every demand row, flat, so a caller can bucket them by
  date (a schedule matrix) or show "which order does this cover" beside the aggregate - see
  the invariant on `build`.
* `send` - hands the reviewed lines to `supplier_notice_service.request_and_notify`, which is
  the S8 notice machinery (document, email, outbox row) with the wording this stage needs and
  no Loading Plan behind it.
"""
from __future__ import annotations

import uuid
from datetime import date
from typing import Any, Optional

from sqlalchemy import case, func, text
from sqlalchemy.orm import Session

from app.models.order import SalesOrder, SalesOrderLine
from app.models.procurement import ProductSupplier
from app.models.product import Product
from app.models.scm import ProformaInvoiceLine, SupplierInventory
from app.services.company_scope_sql import company_sql_predicate
from app.services.error_handler import AppException
from app.services.scm import priority, supplier_notice_service
from app.services.scm.customer_label import CUSTOMER_JOIN_ON, CUSTOMER_LABEL_SQL
from app.services.scm.demand import (
    PLAN_DEMAND_LINE_SQL,
    demand_qty,
    is_open_demand,
    is_plan_demand_line,
    is_plan_demand_order,
)
from app.services.scm.history_sources import PO_HISTORY_SOURCE, SPO_HISTORY_SOURCE
from app.services.scm.supplier_scope import is_uuid, supplier_row
from app.services.scm.trajectory import month_shift


def _pool_predicate(alias: str = "w") -> str:
    """The site-pool test, character for character the reorder engine's own
    (`reorder_run_service._positions_for_run`): a location with no segment stated IS a site
    pool, because a warehouse nobody has classified is not assumed to be a project bin.

    Takes its alias so the one rule can be written into any of this module's queries without
    a second spelling of it existing anywhere.
    """
    return f"(COALESCE({alias}.segment, 'dealer') <> 'project')"


def _supplier(db: Session, supplier_id: str) -> dict:
    """Company-scoped, injection-safe supplier lookup.

    A bare `SELECT ... FROM suppliers WHERE id = :i` (no company predicate, no id-shape
    check) let a caller in company A ask about a supplier in company B and get back their
    code and name in the 200 response - the exact leak `supplier_scope.py` exists to close,
    and a non-uuid value used to reach the column comparison and 500 instead of 404.
    `supplier_row` is the shared, tested helper the upload channels already use; reused here
    rather than reproduced by hand so this module's company boundary cannot drift from
    theirs.
    """
    row = supplier_row(db, supplier_id)
    if row is None:
        raise AppException(404, "Supplier not found")
    return {"supplier_code": row[0], "supplier_name": row[1]}


#: What a SET's holdings are filed under, so one dict can carry both kinds of row without
#: a product id and a set id ever being mistaken for one another (F12, R19).
_SET_PREFIX = "set:"


def _set_key(set_id: Any) -> str:
    return f"{_SET_PREFIX}{set_id}"


def _set_id_of(key: str) -> Optional[str]:
    """The set behind a holdings key, or None when the key names a product."""
    return key[len(_SET_PREFIX):] if key.startswith(_SET_PREFIX) else None


def _stock_list(db: Session, supplier_id: str) -> tuple[Optional[Any], dict[str, dict]]:
    """The supplier's identified goods: current stock, aggregated by what each row names.

    Keyed by product id, or by `set:<id>` for a row bound to one of our product SETS (R19) -
    the supplier sells the whole WC under a code no product carries, and a dict that could
    only be keyed on a product id had nowhere to put it.

    Rows the supplier's own model number could not be matched to anything are real stock but
    cannot be asked against a sales-order line (that is keyed on our product id), so they are
    left out here the same way `loading_plan_service` leaves them out of a plan.

    `cbm_per_unit` and `as_of` live on the model per row, not per product - a product could
    in principle be behind more than one of the supplier's own item codes. Both are carried
    through here as "whatever the stock list says for this product": `cbm_per_unit` from the
    first row that states one (it is a per-unit measure, not a quantity - summing it would be
    wrong, and rows for one product rarely disagree on it), `row_as_of` as the latest, same
    rule as the list-level `as_of` above.
    """
    rows = (
        db.query(SupplierInventory)
        .filter(
            SupplierInventory.supplier_id == supplier_id,
            SupplierInventory.product_id.isnot(None)
            | SupplierInventory.product_set_id.isnot(None),
        )
        .all()
    )
    if not rows:
        return None, {}
    as_of = max((r.as_of for r in rows if r.as_of is not None), default=None)
    stock: dict[str, dict] = {}
    for r in rows:
        pid = _set_key(r.product_set_id) if r.product_set_id else str(r.product_id)
        cur = stock.setdefault(
            pid,
            {
                "qty_packed": 0.0,
                "qty_unfinished": 0.0,
                "cbm_per_unit": None,
                "row_as_of": None,
            },
        )
        cur["qty_packed"] += float(r.qty_packed or 0)
        cur["qty_unfinished"] += float(r.qty_unfinished or 0)
        if cur["cbm_per_unit"] is None and r.cbm_per_unit is not None:
            cur["cbm_per_unit"] = float(r.cbm_per_unit)
        if r.as_of is not None and (cur["row_as_of"] is None or r.as_of > cur["row_as_of"]):
            cur["row_as_of"] = r.as_of
    return as_of, stock


def _linked_products(db: Session, supplier_id: str) -> set[str]:
    """Every product we buy from this supplier - the universe's first leg (F1, AC-A1).

    `product_suppliers` is the sourcing link the reorder engine already reads, so "what does
    this supplier make for us" has one answer across the module. Company scope comes free:
    the ORM's loader criteria apply to `Product`, and a link to a foreign company's product
    therefore names nothing here.

    Without this leg the universe was the supplier's stock list ALONE, which is why a
    supplier who had never sent one produced an empty screen on the very page that exists to
    say what to ask them for.
    """
    rows = (
        db.query(ProductSupplier.product_id)
        .join(Product, Product.id == ProductSupplier.product_id)
        .filter(ProductSupplier.supplier_id == supplier_id)
        .all()
    )
    return {str(r.product_id) for r in rows}


def _standin_proforma(db: Session, supplier_id: str) -> Optional[dict]:
    """The newest un-converted proforma for this supplier, as a holdings statement (Q2).

    Consulted ONLY when there is no stock list (AC-A3): the stock list is what they hold
    today, a proforma is what they promised for one container, and reading both would answer
    one question twice.

    "Un-converted" is both halves of the word: no `proforma_invoice_shipment_link` row (its
    goods have already become a packing list, so what it said they could pack is spent) and
    `status = 'current'` (a superseded revision is history - F5b's chain).

    The order is TOTAL - `invoice_date DESC, created_at DESC, id DESC` - because two
    proformas uploaded from one file share an invoice date and a transaction timestamp, and a
    non-total order would pick a different one on every refresh.
    """
    scope, params = company_sql_predicate(db, "pi.company_id", param_prefix="spi")
    sql = f"""
        SELECT pi.id::text AS id, pi.pi_number, pi.invoice_date
        FROM scm.proforma_invoice pi
        WHERE pi.supplier_id = CAST(:sid AS uuid)
          AND COALESCE(pi.status, 'current') = 'current'
          AND NOT EXISTS (
              SELECT 1 FROM scm.proforma_invoice_shipment_link l
              WHERE l.proforma_invoice_id = pi.id)
          {("AND " + scope) if scope else ""}
        ORDER BY pi.invoice_date DESC NULLS LAST, pi.created_at DESC, pi.id DESC
        LIMIT 1
    """
    head = db.execute(text(sql), {"sid": str(supplier_id), **params}).mappings().first()
    if head is None:
        return None

    lines = (
        db.query(ProformaInvoiceLine)
        .filter(
            ProformaInvoiceLine.invoice_id == head["id"],
            ProformaInvoiceLine.product_id.isnot(None)
            | ProformaInvoiceLine.product_set_id.isnot(None),
        )
        .all()
    )
    holdings: dict[str, dict] = {}
    for ln in lines:
        pid = _set_key(ln.product_set_id) if ln.product_set_id else str(ln.product_id)
        cur = holdings.setdefault(pid, {"qty": 0.0, "cbm_per_unit": None})
        cur["qty"] += float(ln.qty or 0)
        if cur["cbm_per_unit"] is None and ln.cbm_per_unit is not None:
            cur["cbm_per_unit"] = float(ln.cbm_per_unit)
    if not holdings:
        return None
    return {
        "pi_number": head["pi_number"],
        "as_of": head["invoice_date"],
        "holdings": holdings,
    }


#: The quantity still owed on a sales-order line - `demand.demand_qty()`, spelled in SQL for
#: this module's raw queries so the project leg, the line list and `_open_need` cannot drift
#: from one another.
_OPEN_QTY_SQL = (
    "GREATEST(COALESCE(sol.qty_required, sol.qty_ordered) "
    "       - COALESCE(sol.qty_delivered, 0), 0)"
)

#: What CS has already placed against a core sales-order LINE - a purchase order or an SPO,
#: which is the same thing to this screen: supply somebody has already committed to.
#:
#: The walk is core line -> its project mirror (`projects.sales_order_lines`, unique on
#: `core_sales_order_line_id`) -> the Order Inquiry rows CS raised against that mirror line ->
#: their `projects.order_inquiry_links`. The link IS the placement (`order_inquiry_links.qty`,
#: one row per document), so a half-placed requirement nets by half, exactly as
#: `scm.committed_v` nets its own project legs. Never matched on a document number or an item
#: code.
_PLACED_ON_LINE_SQL = """
    LEFT JOIN LATERAL (
        SELECT COALESCE(SUM(l.qty), 0) AS placed
        FROM projects.order_inquiry_links l
        JOIN projects.order_inquiry_rows oir ON oir.id = l.row_id
        JOIN projects.sales_order_lines psl ON psl.id = oir.so_line_id
        WHERE psl.core_sales_order_line_id = sol.id
    ) lk ON TRUE
"""


def _project_open_need(
    db: Session, product_ids: set[str], *, horizon: Optional[date] = None
) -> dict[str, dict]:
    """Project need per product: the open project SO book, less what CS already placed.

    R15 (captain, 27 Aug), and it supersedes R1 for THIS screen only. Project demand used to
    be read here off `projects.order_inquiry_rows` alone, the way the fulfilment board reads
    it (P3) - but on the dev copy 22,238 open project sales-order lines carry no inquiry row
    at all, so purchasing opened the loading plan and was shown nothing to ask for. So the
    loading plan reads the ONE book that has the requirement in it, the same book the retail
    leg reads, and nets each line by the placements against it (`_PLACED_ON_LINE_SQL`) so a
    requirement already on a PO or an SPO is not asked for twice.

    `demand.py`, `scm.committed_v` and the fulfilment board are untouched: they keep P3, where
    CS confirms per inquiry row. The two screens answer different questions - "what is still
    to buy" here, "what has CS decided" there - and only this one may read the book.

    The openness predicate is the retail leg's, condition for condition (`_open_need` /
    `_open_lines`): open order, open line, not covered, something still owed, and the same
    "Plan until" cutoff on `sales_order_lines.required_date`. The DATE comes off the same
    rows as the quantity - `MIN(required_date)` over the lines that survived the netting - so
    a requirement somebody has already bought cannot make the product rank as urgent.

    No company predicate of its own: `product_ids` was resolved company-scoped upstream
    (`_linked_products` / `_stock_list` / `_standin_proforma`), and a product id belongs to
    exactly one company, so filtering on it IS the scope.
    """
    if not product_ids:
        return {}
    sql = f"""
        SELECT product_id, SUM(qty) AS qty, MIN(required_date) AS needed,
               COUNT(DISTINCT so_id) AS so_count
        FROM (
            SELECT sol.product_id::text AS product_id,
                   so.id AS so_id,
                   sol.required_date AS required_date,
                   GREATEST({_OPEN_QTY_SQL} - COALESCE(lk.placed, 0), 0) AS qty
            FROM sales_order_lines sol
            JOIN sales_orders so ON so.id = sol.sales_order_id
            {_PLACED_ON_LINE_SQL}
            WHERE sol.product_id::text = ANY(:pids)
              AND so.demand_class = 'project'
              AND so.status = 'open'
              AND sol.line_status = 'open'
              AND sol.purchasing_status <> 'covered'
              AND {_OPEN_QTY_SQL} > 0
              AND (CAST(:horizon AS date) IS NULL OR sol.required_date IS NULL
                   OR sol.required_date <= CAST(:horizon AS date))
        ) p
        WHERE qty > 0
        GROUP BY product_id
    """
    rows = db.execute(
        text(sql), {"pids": list(product_ids), "horizon": horizon}
    ).mappings().all()
    return {
        r["product_id"]: {
            "qty": float(r["qty"] or 0),
            "needed": r["needed"],
            "so_count": int(r["so_count"] or 0),
        }
        for r in rows
    }


def _earliest_need_by(need_row: Any, project_date: Any) -> Any:
    """The soonest date either channel is owed on, or None when neither states one."""
    dates = [
        d
        for d in (getattr(need_row, "earliest_required_date", None) if need_row else None,
                  project_date)
        if d is not None
    ]
    return min(dates) if dates else None


def _is_held(holding: dict) -> bool:
    """Whether the supplier's statement says they have ANYTHING of this product.

    Packed OR unfinished on a stock-list row - both, because they are two different asks and
    only one of them is loadable today. A supplier holding 500 unfired bodies and nothing
    packed is the whole reason the production ask exists, and testing the packed figure alone
    dropped that row from the grid, from the xlsx we send them and from their own page.
    A proforma row has one quantity and that is the test.
    """
    return bool(
        holding.get("qty_packed")
        or holding.get("qty_unfinished")
        or holding.get("holding_qty")
    )


def _empty_holding() -> dict:
    """What "they hold" reads on a product neither statement names (AC-A1).

    `holding_qty` is None, never 0: "we have no statement from them" and "they told us they
    have none" are different answers, and only one of them means the plan can proceed on the
    supplier's word.
    """
    return {
        "holding_source": "none",
        "holding_qty": None,
        "holding_as_of": None,
        "qty_packed": 0.0,
        "qty_unfinished": 0.0,
        "cbm_per_unit": None,
        "row_as_of": None,
    }


def _holdings(stock: dict[str, dict], proforma: Optional[dict]) -> dict[str, dict]:
    """One shape for "what they hold", whichever document said it.

    `qty_packed` / `qty_unfinished` stay the STOCK LIST's own two figures and are 0 on a
    proforma row, because a proforma states one quantity per line and inventing an unfinished
    half of it would be a number the supplier never wrote. `holding_qty` is the one the screen
    reads: packed on a stock-list row, the invoiced quantity on a proforma row.
    """
    if stock:
        return {
            pid: {
                "holding_source": "stock_list",
                "holding_qty": v["qty_packed"],
                "holding_as_of": v["row_as_of"].isoformat() if v["row_as_of"] else None,
                "qty_packed": v["qty_packed"],
                "qty_unfinished": v["qty_unfinished"],
                "cbm_per_unit": v["cbm_per_unit"],
                "row_as_of": v["row_as_of"].isoformat() if v["row_as_of"] else None,
            }
            for pid, v in stock.items()
        }
    if proforma:
        as_of = proforma["as_of"].isoformat() if proforma["as_of"] else None
        return {
            pid: {
                "holding_source": "proforma",
                "holding_qty": v["qty"],
                "holding_as_of": as_of,
                "qty_packed": 0.0,
                "qty_unfinished": 0.0,
                "cbm_per_unit": v["cbm_per_unit"],
                "row_as_of": as_of,
            }
            for pid, v in proforma["holdings"].items()
        }
    return {}


def _set_rows(db: Session, holdings: dict[str, dict]) -> dict[str, dict]:
    """Per SET named by the supplier's statement, what its row needs to say (F12, R19).

    `{holdings key: {product_set_id, set_code, set_name, driver_product_id,
    driver_quantity}}`. Every FIGURE the row shows is the driver's - the member in the fewest
    sets - because a set is never stocked, never ordered and never costed; its members are.
    Shared parts are ignored on purpose: `CWCY605` sits in six sets, so a minimum across
    members would understate every one of them and a sum would count that cistern six times.

    A set with no members yet is left out entirely rather than shown with nobody's numbers -
    a row whose every column is a dash is worse than no row, because it reads as stock we
    cannot see rather than as a set nobody has finished authoring.
    """
    keys = {key: _set_id_of(key) for key in holdings}
    set_ids = [sid for sid in keys.values() if sid]
    if not set_ids:
        return {}

    from app.models.product_set import ProductSet
    from app.services.product_set_service import driver_members

    drivers = driver_members(db, set_ids)
    named = {
        str(row.id): row
        for row in db.query(ProductSet).filter(ProductSet.id.in_(set_ids)).all()
    }

    out: dict[str, dict] = {}
    for key, set_id in keys.items():
        driver = drivers.get(str(set_id)) if set_id else None
        product_set = named.get(str(set_id)) if set_id else None
        if driver is None or product_set is None:
            continue
        out[key] = {
            "product_set_id": str(product_set.id),
            "set_code": product_set.set_code,
            "set_name": product_set.name,
            "driver_product_id": str(driver.product_id),
            "driver_quantity": float(driver.quantity or 1),
        }
    return out


def _identity(info: dict, entry: Optional[dict]) -> dict:
    """What the row calls itself: the product's own code, or the SET's with its driver named.

    `product_id` stays the driver's on a set row, deliberately. Every figure on the row is
    the driver's, the SO drill and the twelve-month history are keyed on it, and a second id
    to key those off would be a second thing to keep in step. `row_key` is what makes the
    grid's rows unique - two sets may share a driver - and `driver_item_code` is what the
    cell prints under the set code so nobody has to guess whose numbers these are.
    """
    if entry is None:
        return {
            "row_kind": "product",
            "product_set_id": None,
            "set_code": None,
            "set_name": None,
            "driver_product_id": None,
            "driver_item_code": None,
            "driver_product_name": None,
        }
    return {
        "row_kind": "set",
        "item_code": entry["set_code"],
        "product_name": entry["set_name"],
        "product_set_id": entry["product_set_id"],
        "set_code": entry["set_code"],
        "set_name": entry["set_name"],
        "driver_product_id": entry["driver_product_id"],
        "driver_item_code": info.get("item_code"),
        "driver_product_name": info.get("product_name"),
    }


def _open_need(
    db: Session, product_ids: set[str], *, horizon: Optional[date] = None
) -> dict[str, Any]:
    """Outstanding SO need per product, split by demand class.

    The same "still owed" rule the sales-order book's own `outstanding` filter reads
    (`app.services.scm.demand.is_open_demand`), so this screen and the SO list cannot
    disagree about what is still owed. `is_plan_demand_order()` / `is_plan_demand_line()`
    (the same pair `coverage_timeline.py` applies) are ALSO applied, so this screen does not
    ask for stock twice: a project-class order the Order Inquiry never named is not
    purchasing demand yet (S13b), and a line an active supply decision already covers is
    already being handled through that decision - see `demand.py`.

    The class split follows the repo's own rule, not a literal string match:
    "project" is `demand_class == 'project'`, "retail" is anything stated that is NOT
    project (`demand_class IS NOT NULL AND demand_class <> 'project'`), and
    "unclassified" is nothing stated at all. Any class besides "project"/"retail" that a
    future feed introduces lands in retail rather than silently vanishing from every bucket.

    ``horizon`` is "Plan until" (captain, 20 Aug), the same cutoff the reorder run carries as
    `plan_horizon_date` - mirrored here off `sol.required_date` exactly the way
    `demand.horizon_committed_select_sql` narrows its own sheet leg: a stated required date
    past the cutoff drops out, a line with no required date at all always stays in. `None`
    (the default) applies no filter at all, so an un-horizoned call reads byte-identical to
    before this parameter existed.
    """
    if not product_ids:
        return {}
    qty = demand_qty()
    query = (
        db.query(
            SalesOrderLine.product_id.label("product_id"),
            func.sum(qty).label("total_qty"),
            func.sum(
                case((SalesOrder.demand_class == "project", qty), else_=0)
            ).label("project_qty"),
            func.sum(
                case(
                    (
                        (SalesOrder.demand_class.isnot(None))
                        & (SalesOrder.demand_class != "project"),
                        qty,
                    ),
                    else_=0,
                )
            ).label("retail_qty"),
            func.sum(
                case((SalesOrder.demand_class.is_(None), qty), else_=0)
            ).label("unclassified_qty"),
            func.min(SalesOrderLine.required_date).label("earliest_required_date"),
            func.min(SalesOrder.order_date).label("oldest_order_date"),
            func.count(func.distinct(SalesOrder.id)).label("so_count"),
        )
        .join(SalesOrder, SalesOrder.id == SalesOrderLine.sales_order_id)
        .filter(
            SalesOrderLine.product_id.in_(list(product_ids)),
            SalesOrder.status == "open",
            is_open_demand(),
            is_plan_demand_order(),
            is_plan_demand_line(),
        )
    )
    if horizon is not None:
        query = query.filter(
            SalesOrderLine.required_date.is_(None) | (SalesOrderLine.required_date <= horizon)
        )
    rows = query.group_by(SalesOrderLine.product_id).all()
    return {str(r.product_id): r for r in rows}


def _product_catalogue(db: Session, product_ids: list[str]) -> dict[str, dict]:
    if not product_ids:
        return {}
    rows = (
        db.query(Product.id, Product.product_code, Product.product_name)
        .filter(Product.id.in_(product_ids))
        .all()
    )
    return {str(r.id): {"item_code": r.product_code, "product_name": r.product_name} for r in rows}


def _open_lines(
    db: Session,
    product_ids: list[str],
    catalogue: dict[str, dict],
    *,
    horizon: Optional[date] = None,
) -> list[dict]:
    """The open SO lines behind the demand rows, at line grain - CHANGE 2.

    Same predicates `_open_need` and `_project_open_need` aggregate - `is_open_demand()`
    (open line, not covered, positive net qty) and `SalesOrder.status == 'open'` on both
    channels, `is_plan_demand_line()` on the retail one and the placement netting on the
    project one - raw SQL rather than the ORM only because the customer label needs
    `customer_label.py`'s shared COALESCE fragment, which is written as SQL. Keeping the
    predicates textually identical to those two is what keeps `sum(qty)` per product here
    equal to that product's `open_so_need` (the invariant `build`'s docstring states) - a
    second, drifting definition of "open" would break it silently, and that includes both
    the horizon predicate and the netting below.

    BOTH channels since R15: a project requirement is a sales-order line again, so it has a
    line to list here, and it is listed at its REMAINDER - the same figure the Project column
    counts, net of what CS already placed. `PLAN_DEMAND_LINE_SQL` (the active-decision test)
    stays on the retail half alone, because on the project half the placement links are what
    say a requirement is already handled.

    Raw SQL bypasses the ORM's automatic company-scope loader criteria, so the predicate is
    reproduced by hand via `company_sql_predicate` (same pattern as
    `demand_breakdown_service.demand_for_recommendation`).

    ``horizon`` mirrors `demand.horizon_committed_select_sql`'s own bind-and-CAST shape
    rather than `_open_need`'s Python-level branch, because this query is already raw SQL:
    a NULL bind reproduces the unfiltered query exactly, so `horizon=None` is always sent
    through rather than short-circuited in Python.
    """
    if not product_ids:
        return []
    co, co_params = company_sql_predicate(db, "so.company_id", param_prefix="crl")
    qty = _OPEN_QTY_SQL
    # `demand.py`'s line fragment, unmodified: it is already written for the aliases
    # `so`/`sol` this query uses, so using it (rather than restating the rule) keeps this in
    # lockstep with `is_plan_demand_line()` above.
    sql = f"""
        SELECT * FROM (
            SELECT sol.product_id::text AS product_id, so.so_number, so.demand_class,
                   so.order_date, sol.required_date,
                   {CUSTOMER_LABEL_SQL} AS customer_label,
                   pj.title AS project_title,
                   COALESCE(NULLIF(sa.person_label, ''), NULLIF(sa.sales_agent, '')) AS agent_label,
                   sol.unit_price AS unit_price,
                   CASE WHEN so.demand_class = 'project'
                        THEN GREATEST({qty} - COALESCE(lk.placed, 0), 0)
                        ELSE {qty} END AS qty
            FROM sales_order_lines sol
            JOIN sales_orders so ON so.id = sol.sales_order_id
            LEFT JOIN customers c ON {CUSTOMER_JOIN_ON}
            -- The person, then the code: `person_label` is who the buyer would name, and
            -- `sales_agent` is the AutoCount code every row has - so a row that carries only
            -- the code still says something rather than nothing.
            LEFT JOIN sales_agents sa ON sa.id = so.sales_agent_id
            -- The project this order was published for (R15's own book): at most one project
            -- SO per core order (`uq_projects_so_core_order`), so the join cannot multiply a
            -- line and cannot move the total the dialog foots. Company-matched by hand
            -- because raw SQL sees no scoped loader. Blank for an adopted order, which
            -- carries no registration at all.
            LEFT JOIN projects.sales_orders pso
                   ON pso.so_id = so.id AND pso.company_id = so.company_id
            LEFT JOIN projects.projects pj ON pj.id = pso.project_id
            {_PLACED_ON_LINE_SQL}
            WHERE sol.product_id::text = ANY(:pids)
              AND so.status = 'open'
              AND sol.line_status = 'open'
              AND sol.purchasing_status <> 'covered'
              AND {qty} > 0
              AND (so.demand_class = 'project' OR {PLAN_DEMAND_LINE_SQL})
              -- Planning horizon (captain, 20 Aug): same shape as
              -- `demand.horizon_committed_select_sql`'s sheet leg - a stated required_date
              -- past the cutoff is excluded, no date at all is always in, a NULL horizon is
              -- a no-op.
              AND (CAST(:horizon AS date) IS NULL OR sol.required_date IS NULL
                   OR sol.required_date <= CAST(:horizon AS date))
              {("AND " + co) if co else ""}
        ) l
        -- A project line placed in full has nothing left to ask for, so it is not a line on
        -- this request either - the same `> 0` test the Project column applies.
        WHERE qty > 0
        ORDER BY required_date NULLS LAST, so_number
    """
    rows = db.execute(
        text(sql), {"pids": product_ids, "horizon": horizon, **co_params}
    ).mappings().all()
    return [
        {
            "product_id": r["product_id"],
            "item_code": catalogue.get(r["product_id"], {}).get("item_code"),
            "so_number": r["so_number"],
            "customer_label": r["customer_label"],
            # Who this is for, who sold it and at what price - the three columns AC-B2 asks
            # of the Project / Retail lightbox beside the customer. All three are labels, so
            # a row that has none of them still lists.
            "project_title": r["project_title"],
            "agent_label": r["agent_label"],
            "unit_price": float(r["unit_price"]) if r["unit_price"] is not None else None,
            "demand_class": r["demand_class"],
            "order_date": r["order_date"].isoformat() if r["order_date"] else None,
            "required_date": r["required_date"].isoformat() if r["required_date"] else None,
            "qty": float(r["qty"] or 0),
        }
        for r in rows
    ]


def _empty_context() -> dict:
    """The shape every row carries, whether or not the product appears anywhere.

    Missing a product entirely (no stock, no allocation, no packing list) is a real zero, not
    absent data, and the breakdown dialog reads the same keys on every row - a no-demand row
    that carried half of them would break the dialog on half the grid.
    """
    return {
        "on_hand": 0.0,
        "on_hand_group": 0.0,
        "incoming_spo": 0.0,
        "incoming_spo_group": 0.0,
        "incoming_pl": 0.0,
        "outstanding_po": 0.0,
        "sites": [],
        "group_locations": {
            "count": 0,
            "on_hand": 0.0,
            "incoming_spo": 0.0,
            "warehouse_codes": [],
        },
        "incoming_pl_shipments": [],
        "outstanding_po_lines": [],
    }


#: How many group locations to name on the muted line before it becomes "... (N)". The count
#: is always exact; the codes are there to say what KIND of location holds the rest.
_GROUP_CODES_SHOWN = 6


def _pool_warehouses(db: Session) -> list[str]:
    """Every ACTIVE site pool, in code order - the rows the location table always shows.

    Zero-filled on purpose (AC-B3): "BRW 0" says we looked and there is none there, which is
    what the reader is actually asking; a missing row says nothing and reads as data that
    failed to load. Inactive locations are left out - a closed warehouse is not a site she can
    ask stock from, and there are eleven of them.
    """
    scope, params = company_sql_predicate(db, "company_id", param_prefix="cpw")
    rows = db.execute(
        text(
            "SELECT warehouse_code FROM warehouses "
            f"WHERE is_active AND {_pool_predicate('warehouses')} "
            f"AND {scope or 'true'} ORDER BY warehouse_code"
        ),
        params,
    ).all()
    return [r[0] for r in rows]


def _stock_context(db: Session, product_ids: list[str]) -> dict[str, dict]:
    """What we already hold or have coming, per product - SITE POOLS ONLY for the netting.

    THE NETTING RULE THIS FUNCTION IS THE RECORD OF (F2, captain 26 Aug):

        suggested_qty = open_so_need - on_hand(site pools) - incoming_spo(site pools)

    and nothing else is ever subtracted.

    * `on_hand` / `incoming_spo` count only locations where `COALESCE(w.segment,'dealer') <>
      'project'` - the reorder engine's own pool predicate (`reorder_run_service`), and the
      reason this function changed at all: it used to sum all 82 warehouses, so stock sitting
      in a `-BB` project bin (spoken for by an order already promised) silently cancelled an
      ask this container needed. That stock is not hidden - it travels as `on_hand_group` /
      `incoming_spo_group` and is shown, muted, in the row breakdown.
    * `incoming_pl` (unreceived packing-list quantity on shipments that have not arrived) is
      REFERENCE ONLY and is never subtracted (Q1): a packing list names no destination, so
      there is no way to tell whether it lands in a pool or in a group bin, and netting it
      would be a guess. It is shown beside the ask, with the shipments behind it.
    * `outstanding_po` is likewise shown and never subtracted (captain, 20 Aug, CWCY604): a PO
      placed but not yet allocated to a shipment is often the very demand this request is
      asking the supplier to pack.

    Raw SQL for the same reason `reorder_run_service` reads these views in raw SQL: they are
    plain views with no ORM mapping, so there is nothing to scope automatically. Both joined
    sides are company-scoped by hand (the views carry no `company_id`).
    """
    if not product_ids:
        return {}

    prod_scope, prod_params = company_sql_predicate(db, "p.company_id", param_prefix="scp")
    wh_scope, wh_params = company_sql_predicate(db, "w.company_id", param_prefix="scw")
    where = ["np.product_id::text = ANY(:pids)"]
    if prod_scope:
        where.append(prod_scope)
    if wh_scope:
        where.append(wh_scope)
    # Per location, not per product: the split and the breakdown are the same reading of one
    # set of rows, so they cannot disagree about what is in a pool.
    sql = f"""
        SELECT np.product_id::text AS product_id,
               w.warehouse_code,
               {_pool_predicate()} AS is_pool,
               COALESCE(np.quantity_on_hand, 0) AS on_hand,
               COALESCE(np.on_order, 0) AS incoming_spo
        FROM scm.net_position_v np
        JOIN products p ON p.id = np.product_id
        JOIN warehouses w ON w.id = np.warehouse_id
        WHERE {' AND '.join(where)}
    """
    rows = db.execute(
        text(sql), {"pids": product_ids, **prod_params, **wh_params}
    ).mappings().all()

    pool_codes = _pool_warehouses(db)
    out: dict[str, dict] = {}
    per_site: dict[str, dict[str, dict]] = {}
    for r in rows:
        pid = r["product_id"]
        ctx = out.setdefault(pid, _empty_context())
        on_hand = float(r["on_hand"] or 0)
        spo = float(r["incoming_spo"] or 0)
        if r["is_pool"]:
            ctx["on_hand"] += on_hand
            ctx["incoming_spo"] += spo
            site = per_site.setdefault(pid, {}).setdefault(
                r["warehouse_code"],
                {"warehouse_code": r["warehouse_code"], "on_hand": 0.0, "incoming_spo": 0.0},
            )
            site["on_hand"] += on_hand
            site["incoming_spo"] += spo
        else:
            ctx["on_hand_group"] += on_hand
            ctx["incoming_spo_group"] += spo
            group = ctx["group_locations"]
            if on_hand or spo:
                group["count"] += 1
                group["on_hand"] += on_hand
                group["incoming_spo"] += spo
                group["warehouse_codes"].append(r["warehouse_code"])

    for pid, ctx in out.items():
        sites = per_site.get(pid, {})
        for code in pool_codes:
            sites.setdefault(
                code, {"warehouse_code": code, "on_hand": 0.0, "incoming_spo": 0.0}
            )
        ctx["sites"] = sorted(sites.values(), key=lambda s: s["warehouse_code"])
        ctx["group_locations"]["warehouse_codes"] = sorted(
            ctx["group_locations"]["warehouse_codes"]
        )[:_GROUP_CODES_SHOWN]

    for pid, incoming in _incoming_packing_lists(db, product_ids).items():
        ctx = out.setdefault(pid, _empty_context())
        ctx["incoming_pl_shipments"] = incoming
        ctx["incoming_pl"] = sum(s["qty"] for s in incoming)

    for pid, lines in _outstanding_po_lines(db, product_ids).items():
        ctx = out.setdefault(pid, _empty_context())
        ctx["outstanding_po_lines"] = lines
        ctx["outstanding_po"] = sum(line["qty"] for line in lines)

    # A product that appears in no view at all still needs its site rows, or its breakdown
    # opens on an empty location table and reads as a failed load.
    for pid in product_ids:
        ctx = out.setdefault(pid, _empty_context())
        if not ctx["sites"]:
            ctx["sites"] = [
                {"warehouse_code": code, "on_hand": 0.0, "incoming_spo": 0.0}
                for code in pool_codes
            ]
    return out


def _incoming_packing_lists(db: Session, product_ids: list[str]) -> dict[str, list[dict]]:
    """Unreceived packing-list quantity per product, by shipment - the Incoming PL reference.

    "Not arrived" is BOTH `actual_arrival_date IS NULL` and a status that is not a finished
    one: a shipment that has landed is already counted in `on_hand`, and counting it here too
    would show the same units twice on one row.

    A draft carries no number yet; it is emitted as a null so the screen can say "draft"
    rather than invent one.
    """
    if not product_ids:
        return {}
    scope, params = company_sql_predicate(db, "s.company_id", param_prefix="ipl")
    remaining = (
        "GREATEST(COALESCE(l.quantity_shipped, 0) - COALESCE(l.quantity_received, 0), 0)"
    )
    sql = f"""
        SELECT l.product_id::text AS product_id,
               s.id::text AS shipment_id,
               s.shipment_number,
               s.estimated_arrival_date,
               SUM({remaining}) AS qty
        FROM inbound_shipment_lines l
        JOIN inbound_shipments s ON s.id = l.shipment_id
        WHERE l.product_id::text = ANY(:pids)
          AND s.actual_arrival_date IS NULL
          AND s.shipment_status NOT IN ('fully_received', 'closed')
          AND {remaining} > 0
          {("AND " + scope) if scope else ""}
        GROUP BY l.product_id, s.id, s.shipment_number, s.estimated_arrival_date
        ORDER BY s.estimated_arrival_date NULLS LAST, s.shipment_number NULLS FIRST
    """
    rows = db.execute(text(sql), {"pids": product_ids, **params}).mappings().all()
    out: dict[str, list[dict]] = {}
    for r in rows:
        out.setdefault(r["product_id"], []).append(
            {
                "shipment_id": r["shipment_id"],
                "shipment_number": r["shipment_number"],
                "estimated_arrival_date": (
                    r["estimated_arrival_date"].isoformat()
                    if r["estimated_arrival_date"]
                    else None
                ),
                "qty": float(r["qty"] or 0),
            }
        )
    return out


def _outstanding_po_lines(db: Session, product_ids: list[str]) -> dict[str, list[dict]]:
    """Open PO quantity per product, by PO - the same predicate `scm.po_ordered_v` uses.

    The total on the row is the SUM of these lines rather than a separate read of the view.
    They cannot then disagree, and it fixes a quirk of the old join: the view was LEFT JOINed
    to `net_position_v` on (product, warehouse), so a PO for a location the product has no
    stock/on-order row at was dropped from the figure entirely.
    """
    if not product_ids:
        return {}
    scope, params = company_sql_predicate(db, "po.company_id", param_prefix="opo")
    sql = f"""
        SELECT pol.product_id::text AS product_id,
               po.po_number,
               pol.expected_date,
               SUM(pol.qty_ordered - pol.qty_received) AS qty
        FROM purchase_order_lines pol
        JOIN purchase_orders po ON po.id = pol.purchase_order_id
        WHERE pol.product_id = ANY(CAST(:pids AS uuid[]))
          AND po.status IN ('active', 'received', 'partial', 'closed')
          AND pol.line_status = 'open'
          AND pol.qty_ordered > pol.qty_received
          {("AND " + scope) if scope else ""}
        GROUP BY pol.product_id, po.po_number, pol.expected_date
        ORDER BY pol.expected_date NULLS LAST, po.po_number
    """
    rows = db.execute(text(sql), {"pids": product_ids, **params}).mappings().all()
    out: dict[str, list[dict]] = {}
    for r in rows:
        out.setdefault(r["product_id"], []).append(
            {
                "po_number": r["po_number"],
                "expected_date": (
                    r["expected_date"].isoformat() if r["expected_date"] else None
                ),
                "qty": float(r["qty"] or 0),
            }
        )
    return out


#: Job types that touch each document family, oldest write path last - CHANGE 5. Kept as
#: constants beside `_sources` rather than inline so the next importer this module gains only
#: has to extend one tuple.
_SO_BOOK_JOB_TYPES = ("outstanding_so_import", "sales_history_import")
_PO_BOOK_JOB_TYPES = ("outstanding_po_import", "po_history_import")

#: `source_system` stamp the live weekly upload writes (`outstanding_import_service._build`),
#: as opposed to the closed-history stamps in `history_sources.py`.
_LIVE_UPLOAD_SOURCE = "scm_upload"


def _sources(
    db: Session,
    *,
    stock_list_as_of: Optional[str],
    proforma: Optional[dict] = None,
) -> dict:
    """The latest ingest per document family, so the screen can say "as of when" for every
    number it shows (CHANGE 5) - trust, not just a value.

    Preferred source is `import_jobs`: it is stamped the moment a human uploaded a file, which
    answers "when did we last load this" honestly and survives a book whose rows have since
    been reconciled or deleted. Falls back to the row data itself
    (`COALESCE(updated_at, created_at)`) only when no job row exists yet - a database seeded
    before job tracking, or built with `create_all` in a dev/test environment that never ran a
    real upload.

    SO book / PO book: the live weekly upload (`outstanding_so_import` / `outstanding_po_import`,
    `outstanding_import_service`) is what this slice's demand and outstanding-PO figures are
    built from; a later structured-history load (`sales_history_import` / `po_history_import`)
    touches the same tables, so it counts as "the book moved" too - hence both job types per
    family, and the table fallback checks both the live stamp and the matching history stamp.

    SPO book: the structured purchase-history upload writes BOTH families into
    `purchase_orders` in the SAME job, told apart only by `source_system`
    (`scm_po_history` vs `scm_spo_history` - `history_sources.py`). There is no separate SPO
    job type to key on, so its freshness is read off the rows it actually wrote rather than
    the job row.
    """
    jobs_co, jobs_params = company_sql_predicate(db, "company_id", param_prefix="srcj")

    def _job_max(job_types: tuple[str, ...]) -> Optional[str]:
        row = db.execute(
            text(
                "SELECT max(created_at) FROM import_jobs "
                f"WHERE job_type = ANY(:jt) AND {jobs_co or 'true'}"
            ),
            {"jt": list(job_types), **jobs_params},
        ).first()
        return row[0].isoformat() if row and row[0] else None

    def _table_max(table: str, source_systems: tuple[str, ...]) -> Optional[str]:
        co, params = company_sql_predicate(db, "company_id", param_prefix="srct")
        row = db.execute(
            text(
                f"SELECT max(COALESCE(updated_at, created_at)) FROM {table} "
                f"WHERE source_system = ANY(:ss) AND {co or 'true'}"
            ),
            {"ss": list(source_systems), **params},
        ).first()
        return row[0].isoformat() if row and row[0] else None

    so_book_as_of = _job_max(_SO_BOOK_JOB_TYPES) or _table_max(
        "sales_orders", (_LIVE_UPLOAD_SOURCE, "scm_so_history")
    )
    po_book_as_of = _job_max(_PO_BOOK_JOB_TYPES) or _table_max(
        "purchase_orders", (_LIVE_UPLOAD_SOURCE, PO_HISTORY_SOURCE)
    )
    spo_as_of = _table_max("purchase_orders", (SPO_HISTORY_SOURCE,))

    return {
        "so_book_as_of": so_book_as_of,
        "po_book_as_of": po_book_as_of,
        "spo_as_of": spo_as_of,
        "stock_list_as_of": stock_list_as_of,
        # The stand-in, so the freshness strip can say "PI 31/07" rather than nothing at all
        # (AC-A2). Null whenever a stock list exists, because the proforma is then not
        # consulted and naming it would suggest the numbers came from it.
        "proforma_as_of": (
            proforma["as_of"].isoformat() if proforma and proforma["as_of"] else None
        ),
        "proforma_pi_number": proforma["pi_number"] if proforma else None,
    }


def _plan_or_404(db: Session, plan_id: str):
    """The plan row this build belongs to (R2). `ValueError` when it is not this caller's.

    A malformed id takes the same branch as an unknown one: the column is a uuid, so letting
    the value reach the query turns a typo in a URL into a 500.
    """
    from app.models.scm import LoadingPlan

    try:
        uuid.UUID(str(plan_id))
    except (ValueError, AttributeError, TypeError):
        raise ValueError("Loading plan not found")
    plan = db.query(LoadingPlan).filter(LoadingPlan.id == plan_id).first()
    if plan is None:
        raise ValueError("Loading plan not found")
    return plan


def build_for_plan(db: Session, *, plan_id: str, include_lines: bool = False) -> dict:
    """The same read, scoped to a plan (R2).

    Supplier and cut-off are read off the ROW rather than the request, the plan's saved
    quantities are applied to `suggested_qty` before the payload leaves, and the engine's own
    answer rides along as `engine_qty` so the formula tooltip and `Save (N)` still have it.

    The supplier stock snapshot stays per supplier and is replaced whole (the S7 rule), so a
    newer stock list changes an older open plan's numbers. That is the correct reading - the
    plan asks for what the supplier holds NOW - and it is why a plan somebody is done with is
    cancelled rather than left open.

    The totals are stamped back onto the row for the list's "To request" column: it is a cache
    of a derived figure, because re-deriving it per listed row is one full suggestion run per
    row of the grid.
    """
    from app.services.scm import loading_plan_service

    plan = _plan_or_404(db, plan_id)
    out = build(
        db,
        supplier_id=str(plan.supplier_id),
        include_lines=include_lines,
        plan_horizon_date=plan.plan_horizon_date,
    )
    edits = plan.line_edits or {}
    total_qty = 0.0
    total_cbm = 0.0
    for row in out["rows"]:
        row["engine_qty"] = row["suggested_qty"]
        if row["row_key"] in edits:
            row["suggested_qty"] = float(edits[row["row_key"]])
        total_qty += row["suggested_qty"]
        if row.get("cbm_per_unit") is not None:
            total_cbm += row["suggested_qty"] * float(row["cbm_per_unit"])
    loading_plan_service.stamp_request_totals(db, plan, qty=total_qty, cbm=total_cbm)
    db.commit()
    out["plan"] = loading_plan_service.record_dict(db, plan)
    return out


def build(
    db: Session,
    *,
    supplier_id: str,
    include_lines: bool = False,
    plan_horizon_date: Optional[date] = None,
) -> dict:
    """What to ask this supplier for, ranked. Pure read - persists nothing.

    Row scope is the FULL stock list, not just the products carrying open SO need - see the
    module docstring ("one table"). `include_lines=True` adds the flat open-SO-line detail
    behind the demand rows (CHANGE 2), one extra query, off by default because most callers
    (e.g. the send flow) only need the aggregate.

    ``plan_horizon_date`` is "Plan until" (captain, 20 Aug): "SOs needed in 2030 a buyer never
    asked about should not distort a plan they only want through December" - the same request
    the reorder run answers with its own `plan_horizon_date` column
    (`demand.horizon_committed_select_sql`). This build has no stored run row to carry a
    column on (it recomputes on every call), so the horizon travels as a plain request
    parameter instead, threaded to `_open_need`/`_open_lines` so `open_so_need`,
    `suggested_qty`, the class split, the ranked table AND the schedule matrix (which reads
    `lines`) all narrow together. `None` (the default) applies no filter, byte-identical to
    before this parameter existed; a stated date excludes demand due strictly after it, and a
    line carrying no required date at all is always counted, matching the reorder rule
    exactly rather than inventing a second one.

    INVARIANT this endpoint guarantees when `include_lines` is set: for every demand row,
    `sum(l["qty"] for l in lines if l["product_id"] == row["product_id"]) == row["open_so_need"]`.
    The flat lines are the sales-order BOOK, and since R15 both channels are read off it - a
    project requirement is a sales-order line again, listed at the remainder the Project column
    counts. It footed to `retail_qty` alone for one day (R1, when project need was the Order
    Inquiry and had no book line to list). Every number still comes off the identical predicate
    (`_open_need` / `_project_open_need` aggregate it, `_open_lines` emits it at line grain),
    and the horizon does not disturb it: every side applies it identically.
    """
    _supplier(db, supplier_id)
    as_of, stock = _stock_list(db, supplier_id)
    stock_list_as_of = as_of.isoformat() if as_of else None

    # THE UNIVERSE (F1, AC-A1): what we buy from them, what customers are owed on it, and
    # whatever their own latest statement names. The statement is the stock list when there
    # is one and the newest un-converted proforma when there is not (Q2, AC-A3) - never both,
    # because they answer the same question about the same warehouse.
    proforma = _standin_proforma(db, supplier_id) if not stock else None
    holdings = _holdings(stock, proforma)
    holding_source = "stock_list" if stock else "proforma" if proforma else "none"

    # A statement naming one of our SETS (R19) becomes ONE row, and every figure on it is
    # read off the set's DRIVER member. `sets` maps a holdings key to what the row needs to
    # say: whose numbers these are, and what to call them.
    sets = _set_rows(db, holdings)
    #: The driver of every set on this statement. Its own row is suppressed (AC-F12.4): when
    #: the supplier's statement names the set, the set row IS the ask, and a second row for
    #: the pedestal would have somebody ordering the same demand twice.
    driver_ids = {entry["driver_product_id"] for entry in sets.values()}

    product_holdings = {k: v for k, v in holdings.items() if _set_id_of(k) is None}
    universe = (
        _linked_products(db, supplier_id) | set(product_holdings) | driver_ids
    ) - {None}
    need = _open_need(db, universe, horizon=plan_horizon_date)
    project = _project_open_need(db, universe, horizon=plan_horizon_date)

    def _owed(pid: Optional[str]) -> bool:
        return bool(pid) and (pid in need or pid in project)

    demand_ids = sorted(
        pid for pid in universe if _owed(pid) and pid not in driver_ids
    )
    # Held but not owed: named by their own statement, carrying real quantity, no open need.
    # A zero-quantity, zero-need row names nothing worth asking about or holding, so it is
    # left out exactly as it always was.
    no_demand_ids = sorted(
        pid
        for pid in product_holdings
        if not _owed(pid) and pid not in driver_ids and _is_held(product_holdings[pid])
    )
    set_demand_keys = sorted(
        (key for key, entry in sets.items() if _owed(entry["driver_product_id"])),
        key=lambda key: sets[key]["set_code"] or "",
    )
    set_no_demand_keys = sorted(
        (
            key
            for key, entry in sets.items()
            if not _owed(entry["driver_product_id"]) and _is_held(holdings[key])
        ),
        key=lambda key: sets[key]["set_code"] or "",
    )
    # The DRIVERS are catalogued and stock-contexted too, even though they get no row of
    # their own: every figure a set row shows is theirs, and the SO drill is keyed on the
    # driver's product id.
    figure_ids = demand_ids + no_demand_ids + sorted(driver_ids)
    catalogue = _product_catalogue(db, figure_ids)
    stock_context = _stock_context(db, figure_ids)

    #: Every row this build will emit, as `(row key, whose figures, the set it names)`. A
    #: set row's key is its own, never the driver's: two sets are allowed to share a driver,
    #: and a key collision would silently drop one of them off the grid.
    demand_entries = [(pid, pid, None) for pid in demand_ids] + [
        (key, sets[key]["driver_product_id"], sets[key]) for key in set_demand_keys
    ]
    no_demand_entries = [(pid, pid, None) for pid in no_demand_ids] + [
        (key, sets[key]["driver_product_id"], sets[key]) for key in set_no_demand_keys
    ]

    prepared: list[dict] = []
    if demand_entries:
        demand_rows = []
        for row_key, pid, _entry in demand_entries:
            n = need.get(pid)
            p = project.get(pid)
            project_qty = p["qty"] if p else 0.0
            retail_qty = float(getattr(n, "retail_qty", 0) or 0) if n else 0.0
            klass = "project" if project_qty > 0 else "retail" if retail_qty > 0 else "unclassified"
            demand_rows.append(
                {
                    "row_key": row_key,
                    "required_date": _earliest_need_by(n, p["needed"] if p else None),
                    "order_date": getattr(n, "oldest_order_date", None) if n else None,
                    # Absent, per the module's own rule: a product row spans every customer
                    # behind it, so no single payment-terms figure applies (priority.py's
                    # docstring on `factors_for_demand_rows`).
                    "payment_terms_days": None,
                    "demand_class": klass,
                }
            )

        factors_by_row = priority.factors_for_demand_rows(db, demand_rows)
        scores = priority.scores_for(factors_by_row)

        for row_key, pid, entry in demand_entries:
            n = need.get(pid)
            info = catalogue.get(pid, {})
            held = holdings.get(row_key) or _empty_holding()
            ctx = stock_context.get(pid) or _empty_context()
            # The two channels, both off the sales-order book since R15, told apart by
            # `demand_class` - the project half net of what CS already placed.
            p = project.get(pid)
            retail_qty = float(getattr(n, "retail_qty", 0) or 0) if n else 0.0
            unclassified_qty = float(getattr(n, "unclassified_qty", 0) or 0) if n else 0.0
            project_qty = p["qty"] if p else 0.0
            open_so_need = retail_qty + unclassified_qty + project_qty
            # Site pools only, and neither the packing list nor the outstanding PO is
            # subtracted - `_stock_context`'s docstring is the record of that rule.
            suggested_qty = max(open_so_need - ctx["on_hand"] - ctx["incoming_spo"], 0.0)
            need_by = _earliest_need_by(n, p["needed"] if p else None)
            prepared.append(
                {
                    "product_id": pid,
                    # What the grid keys its rows on. The product id for a product row, the
                    # set's own key for a set row: two sets are allowed to share a driver,
                    # and a key collision would silently drop one of them off the grid.
                    "row_key": row_key,
                    "item_code": info.get("item_code"),
                    "product_name": info.get("product_name"),
                    "open_so_need": open_so_need,
                    "suggested_qty": suggested_qty,
                    # `_empty_context` IS the shape (see its docstring), so the row spreads it
                    # whole rather than re-listing its keys - a list that could drift.
                    **ctx,
                    # Gross split - it explains the NEED, not the netted suggestion above.
                    "project_qty": project_qty,
                    "retail_qty": retail_qty,
                    "unclassified_qty": unclassified_qty,
                    "earliest_required_date": need_by.isoformat() if need_by else None,
                    # Both channels, because since R15 both are sales orders: the "Open SOs"
                    # cell drills into `lines`, and a count that named the retail half alone
                    # would disagree with the list it opens. An order carries one
                    # `demand_class`, so the two counts cannot overlap.
                    "so_count": (int(getattr(n, "so_count", 0) or 0) if n else 0)
                    + (p["so_count"] if p else 0),
                    **held,
                    "rank_score": scores[row_key],
                    "rank_factors": [f.as_dict() for f in factors_by_row[row_key]],
                    "has_demand": True,
                    **_identity(info, entry),
                }
            )

        # Highest score first, ties broken on item code then row key so the order is TOTAL -
        # a non-total rule gives a different order on every refresh.
        prepared.sort(key=lambda p: (-p["rank_score"], str(p["item_code"] or ""), p["row_key"]))
        for i, p in enumerate(prepared, start=1):
            p["rank"] = i

    no_demand_rows = []
    for row_key, pid, entry in no_demand_entries:
        info = catalogue.get(pid, {})
        ctx = stock_context.get(pid) or _empty_context()
        no_demand_rows.append(
            {
                "product_id": pid,
                "row_key": row_key,
                "item_code": info.get("item_code"),
                "product_name": info.get("product_name"),
                "open_so_need": 0.0,
                "suggested_qty": 0.0,
                **ctx,
                "project_qty": 0.0,
                "retail_qty": 0.0,
                "unclassified_qty": 0.0,
                "earliest_required_date": None,
                "so_count": 0,
                **(holdings.get(row_key) or _empty_holding()),
                "rank": None,
                "rank_score": None,
                "rank_factors": [],
                "has_demand": False,
                **_identity(info, entry),
            }
        )
    # Ranked rows already carry a total order (see above); rows with nothing to rank sort
    # after them, by item code - the only stable key they have.
    no_demand_rows.sort(key=lambda p: (str(p["item_code"] or ""), p["row_key"]))

    result = {
        "supplier_id": str(supplier_id),
        "stock_list_as_of": stock_list_as_of,
        "rows": prepared + no_demand_rows,
        "sources": _sources(db, stock_list_as_of=stock_list_as_of, proforma=proforma),
        "plan_horizon_date": plan_horizon_date.isoformat() if plan_horizon_date else None,
    }
    if include_lines:
        # The drivers too: the "Open SOs" cell on a set row drills into this list keyed on
        # the row's `product_id`, which IS the driver's, so leaving them out would open an
        # empty drawer under a row showing a count.
        result["lines"] = _open_lines(
            db,
            sorted(set(demand_ids) | {sets[key]["driver_product_id"] for key in set_demand_keys}),
            catalogue,
            horizon=plan_horizon_date,
        )
    return result


#: How many whole months of order history the loading plan reads (AC-B6/B7).
_HISTORY_MONTHS = 12


def _month_label(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def _series(buckets: list[str], qty_by_month: dict[str, float]) -> dict:
    """One zero-filled series: twelve buckets, its peak, its mean and its total.

    Zero-filled because a month with no order is a fact about the product; a chart that skips
    it turns four scattered orders into a solid year. The mean is over the twelve buckets,
    zeros included - a mean over "months that had an order" flatters a seasonal product.
    """
    months = [{"month": b, "qty": qty_by_month.get(b, 0.0)} for b in buckets]
    total = sum(m["qty"] for m in months)
    peak = max(months, key=lambda m: m["qty"]) if months else None
    return {
        "months": months,
        "total": total,
        "avg": total / len(buckets) if buckets else 0.0,
        # There is no peak of nothing: an empty series says so rather than naming the first
        # bucket, which would read as "it peaked in August at zero".
        "peak_month": peak["month"] if peak and peak["qty"] > 0 else None,
        "peak_qty": peak["qty"] if peak and peak["qty"] > 0 else 0.0,
    }


def history(
    db: Session,
    *,
    supplier_id: str,
    product_ids: list[str],
    as_of: Optional[date] = None,
) -> dict:
    """What these products were ORDERED, per month, for the last twelve full months.

    A SIDECAR to `build`, not a column on it (AC-B8): it is asked for the products on screen,
    so a 120-product stock list does not pay for 240 monthly series to read one page of 25.

    THE WINDOW is the twelve FULL months before this one, the same rule
    `trajectory_service` reads its own trailing windows by (`until` = the first of this
    month). The current, part-finished month is deliberately out: a half month drawn beside
    twelve whole ones reads as a collapse in demand every time the page is opened before the
    28th.

    THE SPLIT is `sales_orders.demand_class` - project against everything else - which is both
    the field `trajectory_service` splits its own channels on and the field the row's own
    Project / Retail columns are counted from, so the history can never contradict the columns
    it sits beside. (The UAC first said "by warehouse segment"; measured on the dev copy, 100%
    of the last twelve months' SO lines carry a demand_class while 6,004 lines carry no
    warehouse at all and would have been silently counted as project. The UAC was corrected.)

    "ORDERED", never "sold": the source is the order book by `order_date`, whatever became of
    the order since, matching `trajectory_service.demand_context_for_product`. Every requested
    product comes back, zero-filled if it has no orders at all, so the screen can say "No
    orders in 12 months" rather than sit on a spinner waiting for a row that is never coming.
    """
    _supplier(db, supplier_id)
    # `month_shift(d, 0)` is the first of d's own month - the floor, and the same
    # arithmetic `trajectory_service` and `purchase_trend_service` already share.
    until = month_shift(as_of or date.today(), 0)
    since = month_shift(until, -_HISTORY_MONTHS)
    buckets = [
        _month_label(month_shift(since, i)) for i in range(_HISTORY_MONTHS)
    ]
    result = {
        "from_month": buckets[0],
        "to_month": buckets[-1],
        "products": [],
    }
    if not product_ids:
        return result

    co, co_params = company_sql_predicate(db, "so.company_id", param_prefix="crh")
    sql = f"""
        SELECT sol.product_id::text AS product_id,
               CASE WHEN so.demand_class = 'project' THEN 'project' ELSE 'retail' END
                   AS series,
               to_char(date_trunc('month', so.order_date), 'YYYY-MM') AS month,
               SUM(COALESCE(sol.qty_ordered, 0)) AS qty
        FROM sales_order_lines sol
        JOIN sales_orders so ON so.id = sol.sales_order_id
        WHERE sol.product_id = ANY(CAST(:pids AS uuid[]))
          AND so.order_date >= :since AND so.order_date < :until
          {("AND " + co) if co else ""}
        GROUP BY 1, 2, 3
    """
    # Id-SHAPED values only. These arrive off a query string, so "nope" is a caller's typo
    # rather than a server error - the same rule `list_for_supplier` follows - and the filter
    # below casts to `uuid[]` (for the index on a 90k-row table), which is a good deal less
    # forgiving than the text comparison it replaced. A value that never parsed simply
    # matches nothing, and the zero-fill below still answers for it.
    rows = db.execute(
        text(sql),
        {
            "pids": [p for p in product_ids if is_uuid(p)],
            "since": since,
            "until": until,
            **co_params,
        },
    ).mappings().all()

    by_product: dict[str, dict[str, dict[str, float]]] = {}
    for r in rows:
        series = by_product.setdefault(r["product_id"], {"project": {}, "retail": {}})
        series[r["series"]][r["month"]] = float(r["qty"] or 0)

    # Answer in the order asked, so the caller can zip the answer onto its own rows.
    for pid in product_ids:
        found = by_product.get(pid, {"project": {}, "retail": {}})
        result["products"].append(
            {
                "product_id": pid,
                "project": _series(buckets, found["project"]),
                "retail": _series(buckets, found["retail"]),
            }
        )
    return result


def send(
    db: Session,
    *,
    plan_id: str,
    lines: list[dict],
    actor: Optional[str] = None,
    channel: str = "email",
    recipients: Optional[list] = None,
    chat_contact_id: Optional[str] = None,
    note: Optional[str] = None,
) -> dict:
    """Send the reviewed request for one plan. Thin wrapper - the S8 notice machinery lives in
    `supplier_notice_service.request_and_notify`, so a request and a Loading Plan approval
    cannot drift into two different ways of talking to a supplier.

    The plan is what is sent, not a supplier (R2): its notices carry `loading_plan_id`, so the
    list can say when and on which channel the ask went out, and the row flips to `sent`. The
    supplier is re-checked here too (company-scoped, same as `build`), so a plan whose supplier
    moved company between the two calls fails cleanly before anything is rendered or queued.
    """
    from datetime import datetime as _datetime

    from app.services.scm import loading_plan_service

    plan = _plan_or_404(db, plan_id)
    supplier_id = str(plan.supplier_id)
    _supplier(db, supplier_id)
    out = supplier_notice_service.request_and_notify(
        db,
        supplier_id=supplier_id,
        lines=lines,
        actor=actor,
        loading_plan_id=plan_id,
        channel=channel,
        recipients=recipients,
        chat_contact_id=chat_contact_id,
        note=note,
    )
    # After the notices, never before: a send that failed to render must not leave a plan
    # claiming it went out.
    plan.status = "sent"
    plan.sent_at = _datetime.utcnow()
    db.commit()
    out["plan"] = loading_plan_service.record_dict(db, plan)
    return out
