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

  `suggested_qty` is NETTED (captain decision): the gross open SO need less what we already
  hold or have coming - `on_hand`, `incoming_spo` (SPO on the water,
  `scm.net_position_v.on_order`) and `outstanding_po` (placed but not yet allocated to a
  shipment, `scm.po_ordered_v`) - floored at zero. The gross figure stays on the row as
  `open_so_need` so the arithmetic is visible on screen (need - stock - incoming =
  suggestion); the project/retail/unclassified split is also gross, because it explains the
  NEED, not the netted ask. `include_lines=True` additionally returns the open SO lines
  behind every demand row, flat, so a caller can bucket them by date (a schedule matrix) or
  show "which order does this cover" beside the aggregate - see the invariant on `build`.
* `send` - hands the reviewed lines to `supplier_notice_service.request_and_notify`, which is
  the S8 notice machinery (document, email, outbox row) with the wording this stage needs and
  no Loading Plan behind it.
"""
from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import case, func, text
from sqlalchemy.orm import Session

from app.models.order import SalesOrder, SalesOrderLine
from app.models.product import Product
from app.models.scm import SupplierInventory
from app.services.company_scope_sql import company_sql_predicate
from app.services.error_handler import AppException
from app.services.scm import priority, supplier_notice_service
from app.services.scm.customer_label import CUSTOMER_JOIN_ON, CUSTOMER_LABEL_SQL
from app.services.scm.demand import (
    PLAN_DEMAND_LINE_SQL,
    PLAN_DEMAND_ORDER_SQL,
    demand_qty,
    is_open_demand,
    is_plan_demand_line,
    is_plan_demand_order,
)
from app.services.scm.history_sources import PO_HISTORY_SOURCE, SPO_HISTORY_SOURCE
from app.services.scm.supplier_scope import supplier_row


def _f(v) -> Optional[float]:
    return None if v is None else float(v)


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


def _stock_list(db: Session, supplier_id: str) -> tuple[Optional[Any], dict[str, dict]]:
    """The supplier's identified products: current stock, aggregated by product id.

    Rows the supplier's own model number could not be matched to a product are real stock
    but cannot be asked against a sales-order line (that is keyed on our product id), so they
    are left out here the same way `loading_plan_service` leaves them out of a plan.

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
            SupplierInventory.product_id.isnot(None),
        )
        .all()
    )
    if not rows:
        return None, {}
    as_of = max((r.as_of for r in rows if r.as_of is not None), default=None)
    stock: dict[str, dict] = {}
    for r in rows:
        pid = str(r.product_id)
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


def _open_need(db: Session, product_ids: set[str]) -> dict[str, Any]:
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
    """
    if not product_ids:
        return {}
    qty = demand_qty()
    rows = (
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
        .group_by(SalesOrderLine.product_id)
        .all()
    )
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


def _open_lines(db: Session, product_ids: list[str], catalogue: dict[str, dict]) -> list[dict]:
    """The open SO lines behind the demand rows, at line grain - CHANGE 2.

    Same predicates `_open_need` aggregates - `is_open_demand()` (open line, not covered,
    positive net qty), `SalesOrder.status == 'open'`, AND `is_plan_demand_order()` /
    `is_plan_demand_line()` - raw SQL rather than the ORM only because the customer label
    needs `customer_label.py`'s shared COALESCE fragment, which is written as SQL. Keeping
    the predicates textually identical to `_open_need` is what keeps `sum(qty)` per product
    here equal to that product's `open_so_need` (the invariant `build`'s docstring states) -
    a second, drifting definition of "open" would break it silently.

    Raw SQL bypasses the ORM's automatic company-scope loader criteria, so the predicate is
    reproduced by hand via `company_sql_predicate` (same pattern as
    `demand_breakdown_service.demand_for_recommendation`).
    """
    if not product_ids:
        return []
    co, co_params = company_sql_predicate(db, "so.company_id", param_prefix="crl")
    qty = (
        "GREATEST(COALESCE(sol.qty_required, sol.qty_ordered) "
        "         - COALESCE(sol.qty_delivered, 0), 0)"
    )
    # `demand.py`'s two SQL fragments, unmodified: they are already written for the aliases
    # `so`/`sol` this query uses, so using them (rather than restating the rule) keeps this
    # in lockstep with `is_plan_demand_order()`/`is_plan_demand_line()` above.
    sql = f"""
        SELECT sol.product_id::text AS product_id, so.so_number, so.demand_class,
               so.order_date, sol.required_date,
               {CUSTOMER_LABEL_SQL} AS customer_label,
               {qty} AS qty
        FROM sales_order_lines sol
        JOIN sales_orders so ON so.id = sol.sales_order_id
        LEFT JOIN customers c ON {CUSTOMER_JOIN_ON}
        WHERE sol.product_id::text = ANY(:pids)
          AND so.status = 'open'
          AND sol.line_status = 'open'
          AND sol.purchasing_status <> 'covered'
          AND {qty} > 0
          AND {PLAN_DEMAND_ORDER_SQL}
          AND {PLAN_DEMAND_LINE_SQL}
          {("AND " + co) if co else ""}
        ORDER BY sol.required_date NULLS LAST, so.so_number
    """
    rows = db.execute(text(sql), {"pids": product_ids, **co_params}).mappings().all()
    return [
        {
            "product_id": r["product_id"],
            "item_code": catalogue.get(r["product_id"], {}).get("item_code"),
            "so_number": r["so_number"],
            "customer_label": r["customer_label"],
            "demand_class": r["demand_class"],
            "order_date": r["order_date"].isoformat() if r["order_date"] else None,
            "required_date": r["required_date"].isoformat() if r["required_date"] else None,
            "qty": float(r["qty"] or 0),
        }
        for r in rows
    ]


def _stock_context(db: Session, product_ids: list[str]) -> dict[str, dict]:
    """What we already hold or have coming, per product, company-wide (CHANGE 4).

    Same figures the reorder engine reads, on purpose: `on_hand` is
    `scm.net_position_v.quantity_on_hand`, `incoming_spo` is
    `scm.net_position_v.on_order` (SPO allocations on the water, since migration 337),
    `outstanding_po` is `scm.po_ordered_v.ordered` (placed with a supplier but not yet
    allocated to a shipment) - summed ACROSS every warehouse, because this screen asks one
    supplier for one company-wide quantity, not a per-location one. Missing a product
    entirely (no stock, on-order or committed row anywhere) is a real zero, not absent data.

    Raw SQL for the same reason `reorder_run_service` reads these views in raw SQL: they are
    plain views with no ORM mapping. Company-scoped by hand on the JOINED `products` /
    `warehouses` (the views themselves carry no `company_id`), mirroring
    `reorder_run_service._positions_for_run`'s own note on why both sides need it.
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
    sql = f"""
        SELECT np.product_id::text AS product_id,
               SUM(COALESCE(np.quantity_on_hand, 0)) AS on_hand,
               SUM(COALESCE(np.on_order, 0)) AS incoming_spo,
               SUM(COALESCE(po.ordered, 0)) AS outstanding_po
        FROM scm.net_position_v np
        JOIN products p ON p.id = np.product_id
        JOIN warehouses w ON w.id = np.warehouse_id
        LEFT JOIN scm.po_ordered_v po
          ON po.product_id = np.product_id AND po.warehouse_id = np.warehouse_id
        WHERE {' AND '.join(where)}
        GROUP BY np.product_id
    """
    rows = db.execute(
        text(sql), {"pids": product_ids, **prod_params, **wh_params}
    ).mappings().all()
    return {
        r["product_id"]: {
            "on_hand": float(r["on_hand"] or 0),
            "incoming_spo": float(r["incoming_spo"] or 0),
            "outstanding_po": float(r["outstanding_po"] or 0),
        }
        for r in rows
    }


#: Job types that touch each document family, oldest write path last - CHANGE 5. Kept as
#: constants beside `_sources` rather than inline so the next importer this module gains only
#: has to extend one tuple.
_SO_BOOK_JOB_TYPES = ("outstanding_so_import", "sales_history_import")
_PO_BOOK_JOB_TYPES = ("outstanding_po_import", "po_history_import")

#: `source_system` stamp the live weekly upload writes (`outstanding_import_service._build`),
#: as opposed to the closed-history stamps in `history_sources.py`.
_LIVE_UPLOAD_SOURCE = "scm_upload"


def _sources(db: Session, *, stock_list_as_of: Optional[str]) -> dict:
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
    }


def build(db: Session, *, supplier_id: str, include_lines: bool = False) -> dict:
    """What to ask this supplier for, ranked. Pure read - persists nothing.

    Row scope is the FULL stock list, not just the products carrying open SO need - see the
    module docstring ("one table"). `include_lines=True` adds the flat open-SO-line detail
    behind the demand rows (CHANGE 2), one extra query, off by default because most callers
    (e.g. the send flow) only need the aggregate.

    INVARIANT this endpoint guarantees when `include_lines` is set: for every demand row,
    `sum(l["qty"] for l in lines if l["product_id"] == row["product_id"]) == row["open_so_need"]`
    - the GROSS need, not the netted `suggested_qty` (CHANGE 4 nets stock/incoming/outstanding
    off the ask, which the line-level SO book knows nothing about). Both numbers come off the
    identical predicate (`_open_need` aggregates it, `_open_lines` emits it at line grain), so
    a caller building a schedule matrix off `lines` can trust its per-product total to foot to
    `open_so_need` without re-summing anything itself.
    """
    _supplier(db, supplier_id)
    as_of, stock = _stock_list(db, supplier_id)
    stock_list_as_of = as_of.isoformat() if as_of else None
    if not stock:
        # No stock list uploaded yet for this supplier - the FE reads a null `stock_list_as_of`
        # as the cue for its "upload a stock list first" empty state (PLAN section 5).
        result = {
            "supplier_id": str(supplier_id),
            "stock_list_as_of": None,
            "rows": [],
            "sources": _sources(db, stock_list_as_of=None),
        }
        if include_lines:
            result["lines"] = []
        return result

    need = _open_need(db, set(stock.keys()))
    demand_ids = [pid for pid in stock if pid in need]
    # Held but not owed: on the stock list, carrying real quantity, but no open SO need.
    # Zero-quantity, zero-need rows are left out - they name nothing worth asking about or
    # holding, same as before this change.
    no_demand_ids = [
        pid
        for pid in stock
        if pid not in need and (stock[pid]["qty_packed"] or stock[pid]["qty_unfinished"])
    ]
    catalogue = _product_catalogue(db, demand_ids + no_demand_ids)
    stock_context = _stock_context(db, demand_ids + no_demand_ids)
    empty_context = {"on_hand": 0.0, "incoming_spo": 0.0, "outstanding_po": 0.0}

    prepared: list[dict] = []
    if demand_ids:
        demand_rows = []
        for pid in demand_ids:
            n = need[pid]
            project_qty = float(n.project_qty or 0)
            retail_qty = float(n.retail_qty or 0)
            klass = "project" if project_qty > 0 else "retail" if retail_qty > 0 else "unclassified"
            demand_rows.append(
                {
                    "row_key": pid,
                    "required_date": n.earliest_required_date,
                    "order_date": n.oldest_order_date,
                    # Absent, per the module's own rule: a product row spans every customer
                    # behind it, so no single payment-terms figure applies (priority.py's
                    # docstring on `factors_for_demand_rows`).
                    "payment_terms_days": None,
                    "demand_class": klass,
                }
            )

        factors_by_row = priority.factors_for_demand_rows(db, demand_rows)
        scores = priority.scores_for(factors_by_row)

        for pid in demand_ids:
            n = need[pid]
            info = catalogue.get(pid, {})
            s = stock[pid]
            ctx = stock_context.get(pid, empty_context)
            open_so_need = _f(n.total_qty) or 0.0
            suggested_qty = max(
                open_so_need - ctx["on_hand"] - ctx["incoming_spo"] - ctx["outstanding_po"], 0.0
            )
            prepared.append(
                {
                    "product_id": pid,
                    "item_code": info.get("item_code"),
                    "product_name": info.get("product_name"),
                    "open_so_need": open_so_need,
                    "suggested_qty": suggested_qty,
                    "on_hand": ctx["on_hand"],
                    "incoming_spo": ctx["incoming_spo"],
                    "outstanding_po": ctx["outstanding_po"],
                    # Gross split - it explains the NEED, not the netted suggestion above.
                    "project_qty": _f(n.project_qty) or 0.0,
                    "retail_qty": _f(n.retail_qty) or 0.0,
                    "unclassified_qty": _f(n.unclassified_qty) or 0.0,
                    "earliest_required_date": (
                        n.earliest_required_date.isoformat() if n.earliest_required_date else None
                    ),
                    "so_count": int(n.so_count or 0),
                    "qty_packed": s["qty_packed"],
                    "qty_unfinished": s["qty_unfinished"],
                    "cbm_per_unit": s["cbm_per_unit"],
                    "row_as_of": s["row_as_of"].isoformat() if s["row_as_of"] else None,
                    "rank_score": scores[pid],
                    "rank_factors": [f.as_dict() for f in factors_by_row[pid]],
                    "has_demand": True,
                }
            )

        # Highest score first, ties broken on item code then product id so the order is TOTAL -
        # a non-total rule gives a different order on every refresh.
        prepared.sort(key=lambda p: (-p["rank_score"], str(p["item_code"] or ""), p["product_id"]))
        for i, p in enumerate(prepared, start=1):
            p["rank"] = i

    no_demand_rows = []
    for pid in no_demand_ids:
        info = catalogue.get(pid, {})
        s = stock[pid]
        ctx = stock_context.get(pid, empty_context)
        no_demand_rows.append(
            {
                "product_id": pid,
                "item_code": info.get("item_code"),
                "product_name": info.get("product_name"),
                "open_so_need": 0.0,
                "suggested_qty": 0.0,
                "on_hand": ctx["on_hand"],
                "incoming_spo": ctx["incoming_spo"],
                "outstanding_po": ctx["outstanding_po"],
                "project_qty": 0.0,
                "retail_qty": 0.0,
                "unclassified_qty": 0.0,
                "earliest_required_date": None,
                "so_count": 0,
                "qty_packed": s["qty_packed"],
                "qty_unfinished": s["qty_unfinished"],
                "cbm_per_unit": s["cbm_per_unit"],
                "row_as_of": s["row_as_of"].isoformat() if s["row_as_of"] else None,
                "rank": None,
                "rank_score": None,
                "rank_factors": [],
                "has_demand": False,
            }
        )
    # Ranked rows already carry a total order (see above); rows with nothing to rank sort
    # after them, by item code - the only stable key they have.
    no_demand_rows.sort(key=lambda p: (str(p["item_code"] or ""), p["product_id"]))

    result = {
        "supplier_id": str(supplier_id),
        "stock_list_as_of": stock_list_as_of,
        "rows": prepared + no_demand_rows,
        "sources": _sources(db, stock_list_as_of=stock_list_as_of),
    }
    if include_lines:
        result["lines"] = _open_lines(db, demand_ids, catalogue)
    return result


def send(db: Session, *, supplier_id: str, lines: list[dict], actor: Optional[str] = None) -> dict:
    """Send the reviewed request. Thin wrapper - the S8 notice machinery lives in
    `supplier_notice_service.request_and_notify`, so a request and a Loading Plan approval
    cannot drift into two different ways of talking to a supplier.

    The supplier is re-checked here too (company-scoped, same as `build`), even though
    `request_and_notify` checks it again internally: a caller that skipped `build` (or whose
    supplier moved company between the two calls) still gets a clean 404 before anything is
    rendered or queued, rather than reaching the notice machinery on a value this stage never
    validated.
    """
    _supplier(db, supplier_id)
    return supplier_notice_service.request_and_notify(
        db, supplier_id=supplier_id, lines=lines, actor=actor
    )
