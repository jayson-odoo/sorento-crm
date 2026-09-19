"""Sales report: confirmed vs outstanding sales, by month.

`documentation/plans/chatbot/PLAN-chatbot-sales-report.md` ("Backend contract");
`documentation/plans/chatbot/chatbot-sales-report-acceptance-criteria.md`
AC-1620 to AC-1632, rulings S15 to S19 (S19: 19 Sep 2026 live-testing fix
round - `product_code` is now a PREFIX, `_resolve_products`, not a single
exact match).

AGGREGATED IN SQL, not rolled up from raw rows in Python (SEC-B2/ruling S17): a
big dealer is 1,230 SOs over 37 months (UAC "Measured"), thousands of lines - too
many to read into the request process for one WhatsApp reply. THREE grouped
queries, each `GROUP BY`, so a total can never drift from the SAME per-line SQL
expressions:

* `_months_and_breakdown_query` - one row per (month, breakdown key), or per
  month alone when neither breakdown is wanted (both subjects named). Month
  TOTALS are the Python sum of that month's breakdown rows - summing already-
  computed SQL sums, not re-deriving them from raw lines.
* `_so_count_query` - one row per month, `COUNT(DISTINCT sales_order_id)`. A
  SEPARATE query because a DISTINCT count cannot be summed from the breakdown
  rows above (the same SO can carry lines under more than one product/customer
  in the same month, and `so_count` must still count it once).
* `_so_rows_query` - one row per SO, computed ONLY when `detail == "so"`
  (a big dealer is 1,230 SOs, never built unasked).

Per line (S2, S15, S16 rulings), expressed as SQL so every aggregate is a SUM of
figures already at cent precision, never an exact fraction rounded once at the
end:

* `bucket` = `required_date`, else the SO's `order_date` (S3). A line with
  NEITHER is excluded from EVERYTHING - not just `months[]` but `so_rows[]` too
  (S16) - via a `WHERE bucket IS NOT NULL`, no further fallback to `created_at`.
* `confirmed_qty = LEAST(qty_delivered, qty_ordered)` - never more than ordered.
* `confirmed_value = ROUND(line_total * confirmed_qty / NULLIF(qty_ordered, 0), 2)`,
  0 when `qty_ordered` is 0 or `line_total` is NULL (never a division error) -
  rounded to the cent PER LINE (S15), so every total is a SUM of cents.
* `outstanding_qty` / `outstanding_value` are the REST of the line, counted
  ONLY while the header is `status='open'` AND the line is `line_status='open'`
  - a closed-but-underdelivered line (a data anomaly, not a real one in this
  schema) simply reports less than its `line_total`, rather than raising.
* `ordered = confirmed + outstanding`, by construction (S2).

Company scoping still applies: every query below is a plain ORM query over the
mapped, company-scoped classes (`SalesOrder`, `SalesOrderLine`, ...), so the
`do_orm_execute` scope listener injects its own criteria the same way a raw
Python-rollup query would have - never raw text SQL, which that listener cannot
see.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, Optional

from sqlalchemy import and_, case, func, literal_column
from sqlalchemy.dialects.postgresql import aggregate_order_by
from sqlalchemy.orm import Session

from app.models.inventory import Warehouse
from app.models.order import Customer, SalesOrder, SalesOrderLine
from app.models.product import Product
from app.services.error_handler import handle_not_found
from app.services.order_service import resolve_warehouse_ids
from app.services.outstanding_report_service import _customer_echo

DateLike = Optional[datetime]

# Same reasoning outstanding_report_service.py gives for its own copy: the
# canonical escaper lives on `product_code_resolution.py` but is module-private,
# so a tiny local copy beats reaching across modules for five lines of LIKE
# escaping.
_LIKE_ESCAPE = "\\"


def _escape_like(value: str) -> str:
    return (
        value.replace(_LIKE_ESCAPE, _LIKE_ESCAPE * 2)
        .replace("%", _LIKE_ESCAPE + "%")
        .replace("_", _LIKE_ESCAPE + "_")
    )


def _dec(v: Any) -> Decimal:
    if v is None:
        return Decimal(0)
    try:
        return Decimal(str(v))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(0)


def _qty(v: Any) -> int:
    """Every quantity on this report is a WHOLE unit (the schema declares `int`
    and the reply prints thousands-separated units), but `qty_ordered` /
    `qty_delivered` are `Numeric(15,4)`, so a fraction is storable. Rounded HALF
    UP - never Python's `round`, whose bankers' rounding would print 2 for 2.5
    and 4 for 3.5 in the same reply."""
    return int(_dec(v).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def _money_edge(v: Any) -> float:
    """Quantise to 2 places AT THE RESPONSE EDGE and hand back a `float`, so it
    serialises as a JSON NUMBER (captain ruling, S2 fix round) - a `Decimal`
    field serialises as a STRING through `model_dump(mode="json")`, which is
    not the contract. Every internal accumulation before this point stays
    `Decimal` (SEC-B2/S15: the SQL layer already rounded `confirmed_value` to
    the cent PER LINE, so this is only ever formatting a SUM of already-quantised
    cents, never a fresh rounding decision)."""
    return float(_dec(v).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _as_date(v: DateLike) -> Optional[date]:
    if isinstance(v, datetime):
        return v.date()
    return v


def _resolve_products(db: Session, product_code: Optional[str]) -> list[Product]:
    """S19 (owner ruling from live testing, 19 Sep 2026): `product_code` matches
    the typed code AND every product whose code STARTS WITH it, case-
    insensitively - "Srt5674 August total sale quantity" answered "No sales
    found." because every August sale sat on the sibling SRT5674-N. The
    OUTSTANDING report keeps its own exact-code rule (AC-1119) and does not
    share this helper. LIKE metacharacters in the typed code are escaped
    (`_escape_like`, reused from the exact-match rule this replaces) so a
    literal `%` or `_` in what the customer typed can never wildcard-match."""
    code = (product_code or "").strip()
    if not code:
        return []
    pattern = _escape_like(code.lower()) + "%"
    return (
        db.query(Product)
        .filter(func.lower(Product.product_code).like(pattern, escape=_LIKE_ESCAPE))
        .all()
    )


def _rank_breakdown(rows: list[dict], *, name_key: str) -> list[dict]:
    """S6: ranked by `ordered_value` descending, ties by `ordered_qty`
    descending, then name ascending. Sorted HERE, once - the presenter's
    contract is "print them in the order given" (AC-1608), never re-sort."""
    return sorted(
        rows,
        key=lambda r: (
            -r["ordered_value"],
            -r["ordered_qty"],
            str(r.get(name_key) or ""),
        ),
    )


def _new_figures() -> dict:
    return {
        "ordered_qty": Decimal(0), "ordered_value": Decimal(0),
        "confirmed_qty": Decimal(0), "confirmed_value": Decimal(0),
        "outstanding_qty": Decimal(0), "outstanding_value": Decimal(0),
    }


def _accumulate(acc: dict, row) -> None:
    """Sums figures that are ALREADY SQL sums of per-line, cent-rounded values
    (S15) - never a fresh rounding decision, only Decimal addition."""
    acc["ordered_qty"] += _dec(row.ordered_qty)
    acc["ordered_value"] += _dec(row.ordered_value)
    acc["confirmed_qty"] += _dec(row.confirmed_qty)
    acc["confirmed_value"] += _dec(row.confirmed_value)
    acc["outstanding_qty"] += _dec(row.outstanding_qty)
    acc["outstanding_value"] += _dec(row.outstanding_value)


def _quantised_figures(acc: dict) -> dict:
    return {
        "ordered_qty": _qty(acc["ordered_qty"]), "ordered_value": _money_edge(acc["ordered_value"]),
        "confirmed_qty": _qty(acc["confirmed_qty"]), "confirmed_value": _money_edge(acc["confirmed_value"]),
        "outstanding_qty": _qty(acc["outstanding_qty"]), "outstanding_value": _money_edge(acc["outstanding_value"]),
    }


def _month_key(dt) -> str:
    d = _as_date(dt)
    return f"{d.year:04d}-{d.month:02d}"


def _bucket_expr():
    """S3/S16: a line's own `required_date`, else its SO's `order_date`. NO
    further fallback to `created_at` - a line with neither is excluded from
    everything by the `IS NOT NULL` filter this expression feeds."""
    return func.coalesce(SalesOrderLine.required_date, SalesOrder.order_date)


def _per_line_exprs():
    """The S2/S15 per-line figures, as SQL expressions - `confirmed_value`
    rounded to the cent HERE, per line, so every aggregate downstream is a SUM
    of cents rather than an exact fraction rounded once at the end."""
    confirmed_qty = func.least(SalesOrderLine.qty_delivered, SalesOrderLine.qty_ordered)
    line_total = func.coalesce(SalesOrderLine.line_total, 0)
    confirmed_value = func.coalesce(
        func.round(
            (line_total * confirmed_qty) / func.nullif(SalesOrderLine.qty_ordered, 0),
            2,
        ),
        0,
    )
    is_open = and_(SalesOrder.status == "open", SalesOrderLine.line_status == "open")
    outstanding_qty = case((is_open, SalesOrderLine.qty_ordered - confirmed_qty), else_=0)
    outstanding_value = case((is_open, line_total - confirmed_value), else_=0)
    ordered_qty = confirmed_qty + outstanding_qty
    ordered_value = confirmed_value + outstanding_value
    return {
        "confirmed_qty": confirmed_qty, "confirmed_value": confirmed_value,
        "outstanding_qty": outstanding_qty, "outstanding_value": outstanding_value,
        "ordered_qty": ordered_qty, "ordered_value": ordered_value,
    }


def _figure_sum_labels(exprs: dict) -> list:
    """`func.sum(...)` over each per-line expression - every aggregate below is a
    SUM of figures already at cent precision (S15), computed by the database."""
    return [
        func.sum(exprs["ordered_qty"]).label("ordered_qty"),
        func.sum(exprs["ordered_value"]).label("ordered_value"),
        func.sum(exprs["confirmed_qty"]).label("confirmed_qty"),
        func.sum(exprs["confirmed_value"]).label("confirmed_value"),
        func.sum(exprs["outstanding_qty"]).label("outstanding_qty"),
        func.sum(exprs["outstanding_value"]).label("outstanding_value"),
    ]


def _common_filters(
    *, product_ids, customer_query, customer_ids, channel, warehouse_ids, date_from, date_to,
    bucket_expr,
) -> list:
    filters = [
        SalesOrder.status != "cancelled",
        SalesOrderLine.line_status != "cancelled",
        # S16: a line bucketed by neither required_date nor order_date is
        # excluded from EVERYTHING, not just months[] - never falls back to
        # created_at.
        bucket_expr.isnot(None),
    ]
    if product_ids:
        # S19: the product SUBJECT is now a SET (the typed code plus every
        # sibling whose code starts with it) - filtered by id, resolved once
        # up front in `_resolve_products`, so this stays a plain IN() and no
        # query below needs its own Product join just to filter.
        filters.append(SalesOrderLine.product_id.in_(product_ids))
    if customer_query:
        filters.append(
            Customer.customer_name.ilike(
                f"%{_escape_like(customer_query)}%", escape=_LIKE_ESCAPE
            )
        )
    if customer_ids is not None:
        filters.append(SalesOrder.customer_id.in_(customer_ids))
    if warehouse_ids is not None:
        filters.append(SalesOrderLine.warehouse_id.in_(warehouse_ids))
    if channel == "dealer":
        filters.append(SalesOrder.demand_class == "retail")
    elif channel == "project":
        filters.append(SalesOrder.demand_class == "project")
    if date_from is not None:
        filters.append(bucket_expr >= _as_date(date_from))
    if date_to is not None:
        filters.append(bucket_expr <= _as_date(date_to))
    return filters


def sales_report(
    db: Session,
    *,
    product_code: Optional[str] = None,
    customer_query: Optional[str] = None,
    customer_ids: Optional[list[str]] = None,
    channel: Optional[str] = None,
    warehouse_codes: Optional[list[str]] = None,
    date_from: DateLike = None,
    date_to: DateLike = None,
    detail: Optional[str] = None,
) -> dict:
    """S7: the SUBJECT is a product, a customer, or both - never neither (the
    ROUTE raises 422 `subject_required` before calling this). `channel` is
    already normalised to `"dealer"` / `"project"` / `None` by the route (S8);
    `detail` is `"so"` or `None` - `so_rows` is computed ONLY when it is `"so"`
    (captain ruling: a big dealer is 1,230 SOs, never build that unasked).

    S19: `product_code` is a PREFIX - `_resolve_products` returns every
    product whose code starts with it, case-insensitively (the typed code
    itself included, since every code "starts with" itself). 404 only when
    NOTHING starts with it (the route's own 422 `product_code_too_short`
    guards the pathological single-character case before this ever runs)."""
    product_code_stripped = (product_code or "").strip()
    matched_products = _resolve_products(db, product_code_stripped) if product_code_stripped else []
    if product_code_stripped and not matched_products:
        raise handle_not_found("Product", product_code)
    product_ids = [p.id for p in matched_products]

    warehouse_ids = resolve_warehouse_ids(db, warehouse_codes)
    customer_ids = [str(c).strip() for c in (customer_ids or []) if str(c).strip()] or None
    has_customer = bool(customer_ids) or bool((customer_query or "").strip())
    has_product = bool(matched_products)
    # S6/AC-1628: customer subject -> By product; product subject -> By customer;
    # both named -> neither breakdown.
    want_by_product = has_customer and not has_product
    want_by_customer = has_product and not has_customer
    want_so_rows = (detail or "").strip().lower() == "so"

    bucket_expr = _bucket_expr()
    filters = _common_filters(
        product_ids=product_ids, customer_query=customer_query, customer_ids=customer_ids,
        channel=channel, warehouse_ids=warehouse_ids, date_from=date_from, date_to=date_to,
        bucket_expr=bucket_expr,
    )
    figure_exprs = _per_line_exprs()
    month_expr = func.date_trunc("month", bucket_expr)

    # ----------------------------------------------------------------- months + breakdown
    # ONE grouped query: GROUP BY month and the breakdown key (product_code, customer_name,
    # or nothing when both subjects are named) - month TOTALS are the Python sum of a
    # month's own breakdown rows below (summing SQL sums, not raw lines).
    select_cols: list = [month_expr.label("month_dt")]
    group_cols: list = [month_expr]
    breakdown_col = None
    if want_by_product:
        breakdown_col = Product.product_code
        select_cols.append(Product.product_code.label("breakdown_key"))
        group_cols.append(Product.product_code)
    elif want_by_customer:
        breakdown_col = Customer.customer_name
        select_cols.append(Customer.customer_name.label("breakdown_key"))
        group_cols.append(Customer.customer_name)

    q1 = (
        db.query(*select_cols, *_figure_sum_labels(figure_exprs))
        .select_from(SalesOrderLine)
        .join(SalesOrder, SalesOrder.id == SalesOrderLine.sales_order_id)
        .outerjoin(Customer, Customer.id == SalesOrder.customer_id)
    )
    if want_by_product:
        q1 = q1.join(Product, Product.id == SalesOrderLine.product_id)
    q1 = q1.filter(*filters).group_by(*group_cols)

    months_acc: dict[str, dict] = {}
    breakdown_acc: dict[str, dict[str, dict]] = {}
    for row in q1.all():
        month_key = _month_key(row.month_dt)
        if breakdown_col is not None:
            key = row.breakdown_key
            fig = breakdown_acc.setdefault(month_key, {}).setdefault(key, _new_figures())
            _accumulate(fig, row)
        else:
            fig = months_acc.setdefault(month_key, _new_figures())
            _accumulate(fig, row)

    if breakdown_col is not None:
        for month_key, keyed in breakdown_acc.items():
            totals = months_acc.setdefault(month_key, _new_figures())
            for fig in keyed.values():
                for k in totals:
                    totals[k] += fig[k]

    # ----------------------------------------------------------------- so_count per month
    # A SEPARATE query (a DISTINCT count cannot be summed from the breakdown rows
    # above: the same SO can carry lines under more than one product/customer in
    # the same month, and so_count must still count it once).
    q2 = (
        db.query(month_expr.label("month_dt"), func.count(func.distinct(SalesOrder.id)).label("so_count"))
        .select_from(SalesOrderLine)
        .join(SalesOrder, SalesOrder.id == SalesOrderLine.sales_order_id)
        .outerjoin(Customer, Customer.id == SalesOrder.customer_id)
    )
    if want_by_product:
        q2 = q2.join(Product, Product.id == SalesOrderLine.product_id)
    q2 = q2.filter(*filters).group_by(month_expr)
    so_counts = {_month_key(r.month_dt): int(r.so_count or 0) for r in q2.all()}

    months: list[dict] = []
    for month_key in sorted(months_acc.keys(), reverse=True):
        entry = {
            "month": month_key,
            "so_count": so_counts.get(month_key, 0),
            **_quantised_figures(months_acc[month_key]),
        }
        if want_by_product:
            rows = [
                {"product_code": code, **_quantised_figures(fig)}
                for code, fig in breakdown_acc.get(month_key, {}).items()
            ]
            entry["by_product"] = _rank_breakdown(rows, name_key="product_code")
        if want_by_customer:
            rows = [
                {"customer_name": name, **_quantised_figures(fig)}
                for name, fig in breakdown_acc.get(month_key, {}).items()
            ]
            entry["by_customer"] = _rank_breakdown(rows, name_key="customer_name")
        months.append(entry)

    # ------------------------------------------------------- product_codes (S19,
    # second fix round: owner ruling from live testing, 19 Sep 2026 - "why it says
    # SRT5674 (SRT5674-N) so weird, it should just be comma separated"). The header
    # echoes every code the typed stem COVERS - the family `_resolve_products`
    # already found, still company-scoped by that query's own scope listener -
    # NOT only the codes that happen to have a row in this filtered report. A
    # covered code with zero rows in this window (e.g. no sales at all, or none
    # inside a narrowed date/channel/warehouse filter) still belongs to the
    # family the customer's typed prefix names, so it still appears here; the
    # per-SO `product_codes` on a `so_rows` row (below) is a DIFFERENT thing -
    # the codes actually on that one SO - and is unaffected.
    product_codes: list[str] = sorted(p.product_code for p in matched_products)

    # ----------------------------------------------------------------- so_rows (detail=so)
    so_rows: Optional[list[dict]] = None
    if want_so_rows:
        # S9-shaped, S15's own instruction: distinct warehouse codes, comma joined,
        # ORDERED - `string_agg(DISTINCT col, sep ORDER BY col)` renders correctly
        # only with the ORDER BY wrapping the SEPARATOR argument (Postgres syntax
        # places ORDER BY after every value argument, not between DISTINCT and the
        # separator).
        location_expr = func.string_agg(
            Warehouse.warehouse_code.distinct(),
            aggregate_order_by(literal_column("', '"), Warehouse.warehouse_code),
        )
        select_cols_so: list = [
            SalesOrder.so_number,
            SalesOrder.order_date,
            Customer.customer_name,
            location_expr.label("location"),
        ]
        if has_product:
            # S19/AC-1633: this SO's own distinct matched codes, comma joined -
            # the same `string_agg(DISTINCT ...)` idiom as `location` above.
            # ONLY selected/joined when a product filter is active - a
            # customer-subject report has no matched-code family to name.
            product_codes_expr = func.string_agg(
                Product.product_code.distinct(),
                aggregate_order_by(literal_column("', '"), Product.product_code),
            )
            select_cols_so.append(product_codes_expr.label("product_codes"))
        q3 = (
            db.query(*select_cols_so, *_figure_sum_labels(figure_exprs))
            .select_from(SalesOrderLine)
            .join(SalesOrder, SalesOrder.id == SalesOrderLine.sales_order_id)
            .outerjoin(Customer, Customer.id == SalesOrder.customer_id)
            .outerjoin(Warehouse, Warehouse.id == SalesOrderLine.warehouse_id)
        )
        if has_product:
            q3 = q3.join(Product, Product.id == SalesOrderLine.product_id)
        q3 = q3.filter(*filters).group_by(
            SalesOrder.id, SalesOrder.so_number, SalesOrder.order_date, Customer.customer_name
        )
        rows = [
            {
                "so_number": r.so_number,
                "customer_name": r.customer_name,
                "location": r.location,
                "order_date": r.order_date,
                **({"product_codes": r.product_codes} if has_product else {}),
                **_quantised_figures({
                    "ordered_qty": _dec(r.ordered_qty), "ordered_value": _dec(r.ordered_value),
                    "confirmed_qty": _dec(r.confirmed_qty), "confirmed_value": _dec(r.confirmed_value),
                    "outstanding_qty": _dec(r.outstanding_qty), "outstanding_value": _dec(r.outstanding_value),
                }),
            }
            for r in q3.all()
        ]
        # AC-1629: order_date descending, ties by so_number descending, undated
        # last - the same two-step stable-sort idiom
        # `outstanding_report_service.py` uses for its own `so_rows`/`do_rows`.
        rows.sort(
            key=lambda r: (r["order_date"] is None, r["order_date"] or date.min, r["so_number"]),
            reverse=True,
        )
        rows.sort(key=lambda r: r["order_date"] is None)
        so_rows = rows

    return {
        "customer_name": _customer_echo(db, customer_query, customer_ids),
        # S19: echoes what the customer TYPED (upper-cased, as the exact-match
        # rule always did - a real code is stored upper-case), never a single
        # resolved product's own code - there is no longer one, the subject is
        # a whole family.
        "product_code": product_code_stripped.upper() if product_code_stripped else None,
        "product_codes": product_codes,
        "channel": channel,
        "warehouse_codes": [str(c).strip() for c in (warehouse_codes or []) if str(c).strip()],
        "date_from": _as_date(date_from),
        "date_to": _as_date(date_to),
        "months": months,
        "so_rows": so_rows,
    }
