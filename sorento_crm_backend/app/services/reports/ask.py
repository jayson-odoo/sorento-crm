"""The chatbot's report ask: one catalogue, one executor (lane REPORT-ENGINE, slice 1a;
`documentation/plans/chatbot/PLAN-report-engine.md` section 10).

`CATALOGUE` maps the words a caller may use (a dimension to group by, a filter to apply) onto
each basis definition's own column keys and param keys, so the SQL stays in the dataset.
`run_ask` runs ONE `engine.run_summary` (rows = the group column or `all`, cols = `all`,
measures amount and qty), ranks the whole grouping in Python and cuts it to `top_n`.

The engine reads an EMPTY select as "no filter" (`engine._predicates`), so every filter that
resolves to nothing is answered HERE with zero rows, never handed to the engine as `[]`.
"""
from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.services.reports import spec_set
from app.services.reports.datasets import (
    billing_document_lines,
    chat_asks,
    chat_report_ask,
    delivery_order_lines,
    sales_order_lines_ask,
    unpaid_documents,
)
from app.services.sales_report_delivered import _CHANNEL_CLASS, resolve_locations
from app.services.sales_report_service import _money_edge, _qty

#: The words a caller may group by and filter by. Every word is named the same as the column or
#: param key behind it, so one list each serves every basis (a word that differs from its key
#: earns a mapping then).
DIMENSIONS = ("customer", "product", "brand", "category", "sales_agent", "location", "channel", "month", "year")
FILTERS = ("customer", "product", "brand", "category", "sales_agent", "customer_agent", "location", "channel")

#: The datasets a caller may ask over; the first is the default (a call naming none is sales).
DATASETS = ("sales", "chat")

#: The chat words (CA-3). Every word is named the same as the column or param key behind it.
CHAT_DIMENSIONS = (
    "topic", "subject", "product", "customer", "outcome", "failure_reason", "week", "month", "day", "language",
    "asker", "salesperson", "category", "brand",
)
CHAT_MEASURES = ("asks", "failed", "failure_rate", "contacts")
#: The dimensions that are a run of time: a trend lists every bucket, oldest first.
CHAT_TRENDS = frozenset({"week", "month", "day"})

#: Dataset -> basis -> entry. Sales: `invoiced` (SALES-UNIFIED: the one sales definition, on the
#: billing lines the Top selling items report reads, so the two cannot disagree) and one entry
#: per order basis over sales order lines. Chat: `asks` counts every ask, `turns` each message once.
CATALOGUE: dict[str, dict[str, dict[str, Any]]] = {
    "sales": {
        "invoiced": {
            "definition": billing_document_lines.ASK_DEFINITION,
            "label": "invoiced sales",
            "dimensions": DIMENSIONS,
            "filters": FILTERS,
        },
        **{
            basis: {
                "definition": sales_order_lines_ask.DEFINITIONS[basis],
                "label": label,
                "dimensions": (*DIMENSIONS, "sales_order") if basis == "outstanding" else DIMENSIONS,
                "filters": FILTERS,
            }
            for basis, label in (
                ("delivered", "delivered sales"),
                ("ordered", "ordered sales"),
                ("outstanding", "outstanding orders"),
            )
        },
        # REPORT-UNIFY: delivery order lines of DOs not yet delivered, and unpaid invoices (per document).
        "pending_delivery": {
            "definition": delivery_order_lines.PENDING_DEFINITION,
            "label": "pending delivery",
            # REPORT-OUTSTANDING-SUMMARY: "Reply 1 for the delivery order list." lists the figure's own DOs.
            "dimensions": (*DIMENSIONS, "delivery_order"),
            "filters": FILTERS,
        },
        "unpaid": {
            "definition": unpaid_documents.DEFINITION,
            "label": "unpaid invoices",
            "dimensions": ("customer", "sales_agent", "month", "year"),
            "filters": ("customer", "sales_agent", "customer_agent"),
        },
    },
    "chat": {
        basis: {
            "definition": chat_report_ask.DEFINITIONS[basis],
            "label": label,
            "dimensions": CHAT_DIMENSIONS,
            "filters": ("subject", "product", "customer", "asker", "category", "brand"),
        }
        for basis, label in (("asks", "asks"), ("turns", "turns"))
    },
}

#: The bases a caller may leave the period off (REPORT-UNIFY: absent = every date); both dates or neither.
OPEN_BASES = frozenset({"outstanding", "pending_delivery", "unpaid"})
#: The filter words a document-level basis (`unpaid`) cannot apply: a document has no product, place or channel.
PER_DOCUMENT_FILTERS = ("product", "brand", "category", "spec", "location", "channel")
#: `group_by=spec:<key>`: the prefix of a ranking by a product spec's value.
SPEC_GROUP = "spec:"

#: What a customer-scoped contact (a dealer) may group or filter by (PLAN section 0, Q1/Q2).
DEALER_KEYS = frozenset({"product", "brand", "category", "month", "year", "sales_order", "delivery_order"})
#: REPORT-OUTSTANDING-SUMMARY item 1: what a dealer may also name or group by on undelivered orders and pending delivery.
DEALER_OUTSTANDING_KEYS = frozenset({"location"})
CHAT_DEALER_KEYS = frozenset({"topic", "subject", "product", "month"})

GROUP_LABELS = {
    "customer": "Customer",
    "product": "Product",
    "brand": "Brand",
    "category": "Category",
    "sales_agent": "Sales agent",
    "location": "Location",
    "channel": "Channel",
    "month": "Month",
    "year": "Year",
    "sales_order": "Sales order",
    "delivery_order": "Delivery order",
}

CHAT_GROUP_LABELS = {
    "topic": "Topic",
    "subject": "Subject",
    "product": "Product",
    "customer": "Customer",
    "outcome": "Outcome",
    "failure_reason": "Failure reason",
    "week": "Week",
    "month": "Month",
    "day": "Day",
    "language": "Language",
    "asker": "Asked by",
    "salesperson": "Salesperson",
    "category": "Category",
    "brand": "Brand",
}
CHAT_FILTER_LABELS = {
    "subject": "Subject", "product": "Product", "customer": "Customer", "asker": "Asked by",
    "category": "Category", "brand": "Brand",
}
#: The axes whose blank bucket (no reason, no customer, no salesperson, no brand) is not a row.
CHAT_NAMED_AXES = frozenset({"failure_reason", "customer", "salesperson", "brand", "category"})
#: The axes read through the item grain (one row per product an ask NAMED).
CHAT_ITEM_AXES = frozenset({"product", "category", "brand"})

#: The filter words' labels, as the route echoes them: the dimensions' own, plus the customer
#: card link a drill down uses (REPORT-DRILLDOWN, owner 8 Oct 2026), named so the reply says it.
FILTER_LABELS = {**GROUP_LABELS, "customer_agent": "Customers assigned to", "spec": "Specification", "company": "Company"}

NO_AGENT_KEY = sales_order_lines_ask.NO_AGENT_KEY

# ----------------------------------------------------------------------- drill down
#
# REPORT-DRILLDOWN (`documentation/plans/chatbot/PLAN-report-drilldown-08oct.md`): a follow-up
# ranking of the rows a ranking printed. Each printed row carries `keys`, the ids its name
# stands for, and a declared link per axis pair turns those keys into the follow-up's filter.

#: The route param each drill source's keys go to: the source row's own filter on the sales
#: order line. Channel and month are not sources (a channel or a month is named in words).
DRILL_PARAMS = {
    "sales_agent": "sales_agent_ids",
    "customer": "customer_ids",
    "product": "product_ids",
    "brand": "brand_ids",
    "category": "category_ids",
    "location": "warehouse_codes",
}

#: The pairs whose link is NOT the source's own filter. Agent -> customer is the customer card
#: (owner Q1, 8 Oct 2026): the customers assigned to those agents, whoever sold the order.
DRILL_LINKS = {("sales_agent", "customer"): "customer_agent_ids"}


def drill_param(source: str, target: str) -> Optional[str]:
    """The route param a drill from `source` rows to a `target` ranking filters by; None when
    `source` is not a drill source."""
    return DRILL_LINKS.get((source, target)) or DRILL_PARAMS.get(source)


def _row_keys(db: Session, group_by: str, names: list[str], company_grants: Any) -> dict[str, list[str]]:
    """The ids each printed name stands for, inside the contact's companies (a name shared by
    several rows, one brand per company, is one row and the union of their ids). The
    "(no agent)" row is `NO_AGENT_KEY`; a location's key is its code."""
    from app.models.base import company_scope
    from app.models.order import Customer
    from app.models.product import Brand, Product, ProductCategory
    from app.models.sales_agent import SalesAgent
    from app.services.reports.datasets.delivery_order_lines import NO_AGENT

    from app.services.reports.engine import BLANK_VALUE

    if group_by == "location":
        # "(blank)" is lines with no location: no code to narrow by (the lane says so).
        return {n: ([] if n == BLANK_VALUE else [n]) for n in names}
    lookups = {
        "sales_agent": (SalesAgent, SalesAgent.sales_agent),
        "customer": (Customer, Customer.customer_name),
        "product": (Product, Product.product_code),
        "brand": (Brand, Brand.brand_name),
        "category": (ProductCategory, ProductCategory.category_name),
    }
    if group_by not in lookups:
        return {}
    model, name_column = lookups[group_by]
    out: dict[str, list[str]] = {n: [] for n in names}
    if group_by == "sales_agent" and NO_AGENT in out:
        out[NO_AGENT] = [NO_AGENT_KEY]
    grants = sorted(str(c) for c in company_grants or ())
    wanted = [n for n in names if not out[n]]
    if wanted and grants:
        with company_scope(db, None):
            rows = (
                db.query(model.id, name_column)
                .filter(name_column.in_(wanted), (model.company_id.in_(grants)) | (model.company_id.is_(None)))
                .all()
            )
        for row_id, name in rows:
            out[name].append(str(row_id))
    return {n: sorted(set(ids)) for n, ids in out.items()}


def _category_codes(db: Session, names: list[str], company_grants: Any) -> dict[str, str]:
    """The category code beside each printed category name (REPORT-SMART-L R3a: the top selling reply
    printed a category by its code), inside the contact's companies; a name with no code is absent."""
    from app.models.base import company_scope
    from app.models.product import ProductCategory

    grants = sorted(str(c) for c in company_grants or ())
    if not names or not grants:
        return {}
    with company_scope(db, None):
        rows = (
            db.query(ProductCategory.category_name, ProductCategory.category_code)
            .filter(ProductCategory.category_name.in_(names),
                    (ProductCategory.company_id.in_(grants)) | (ProductCategory.company_id.is_(None)))
            .order_by(ProductCategory.category_code)
            .all()
        )
    out: dict[str, str] = {}
    for name, code in rows:
        if code and name not in out:
            out[name] = str(code)
    return out


#: The delivered dataset's raw channel values, as the ordered dataset already prints them.
_CHANNEL_NAMES = {"retail": "Dealer", "project": "Project team", "other": "Other"}

MEASURES = ("amount", "qty")
#: REPORT-SMART-1021: distinct counts, ranked by the count (ties by amount, then quantity).
#: Each row and the total carry `count` beside the amount and quantity.
COUNT_MEASURES = tuple(key for key, _label, _column in sales_order_lines_ask.COUNT_COLUMNS)
#: Every measure a sales ask may name.
SALES_MEASURES = MEASURES + COUNT_MEASURES


def _empty(status: str = "ok", message: Optional[str] = None) -> dict[str, Any]:
    return {
        "status": status,
        "message": message,
        "rows": [],
        "more": 0,
        "total_count": 0,
        "total": {"qty": 0, "amount": 0.0},
    }


def run_ask(
    db: Session,
    *,
    dataset: str = "sales",
    basis: str,
    measure: str,
    group_by: Optional[str],
    date_from: date,
    date_to: date,
    filters: dict[str, list[str]],
    warehouse_codes: list[str],
    policy: Any,
    company_grants: Any = None,
    sort: str = "desc",
    top_n: Optional[int] = None,
    scope_customers: Optional[list[str]] = None,
    also: tuple[str, ...] = (),
) -> dict[str, Any]:
    """The ranked rows, their cut and the whole set's total. `filters` maps a spec word to
    RESOLVED ids (channel: `dealer` / `project`); `warehouse_codes` are the raw codes named.
    `company_grants` is the contact's own company ids (fail closed: none, no rows). `also`: more
    summed measures of the definition, carried as whole numbers on every row and the total."""
    from app.schemas.report import ReportViewConfig
    from app.services.reports import engine

    if dataset == "chat":
        return _run_chat(
            db, basis=basis, measure=measure, group_by=group_by, date_from=date_from, date_to=date_to,
            filters=filters, sort=sort, top_n=top_n, scope_customers=scope_customers,
        )
    entry = CATALOGUE["sales"][basis]
    definition = entry["definition"]

    params: dict[str, Any] = {
        "date_basis": "order_date",
        "period": {"kind": "custom", "from": date_from.isoformat(), "to": date_to.isoformat()},
    }
    for word, values in filters.items():
        if not values:
            return _empty()
        if word == "channel":
            values = [_CHANNEL_CLASS[v] for v in values]
        params[word] = list(values)

    if "location" in entry["filters"]:  # a document-level basis has no location to cap
        location_ids, refusal, nothing = resolve_locations(db, warehouse_codes, policy)
        if refusal is not None:
            return _empty("refused", refusal)
        if nothing:
            return _empty()
        if location_ids is not None:
            params["location"] = location_ids

    # The engine refuses rows == cols, so the one-total shape groups by month and reads the
    # grand total only.
    by_spec = bool(group_by) and group_by.startswith(SPEC_GROUP)
    rows_key = "product" if by_spec else (group_by or "month")
    counted = measure in COUNT_MEASURES
    view = ReportViewConfig.model_validate(
        {
            "params": params,
            "detail": {"columns": [], "order": []},
            "pivot": {"rows": rows_key, "cols": "all", "measures": [*MEASURES, *((measure,) if counted else ()), *also]},
        }
    )
    pivot = engine.run_summary(
        db, definition, params, view, company_grants=frozenset(str(c) for c in company_grants or ())
    )

    grand = pivot.grand_total or {}
    body = _empty()
    body["total"] = {"qty": _qty(grand.get("qty")), "amount": _money_edge(grand.get("amount"))}
    if counted:
        body["total"]["count"] = int(Decimal(grand.get(measure) or 0))
    for key in also:
        body["total"][key] = _qty(grand.get(key))
    if not group_by:
        return body

    ranked = []
    for value in pivot.row_values:
        totals = pivot.row_totals.get(value) or {}
        qty, amount = Decimal(totals.get("qty") or 0), Decimal(totals.get("amount") or 0)
        if not qty and not amount:
            continue
        name = _CHANNEL_NAMES.get(value, value) if group_by == "channel" else value
        ranked.append((name, qty, amount, Decimal(totals.get(measure) or 0) if counted else Decimal(0)))

    if by_spec:
        # A product ranking folded to the value each product holds (a count measure is refused by the route).
        ids = _row_keys(db, "product", [r[0] for r in ranked], company_grants)
        ranked = spec_set.fold_by_key(db, group_by[len(SPEC_GROUP):], ranked, ids)

    sign = -1 if sort == "desc" else 1
    order = {"amount": (2, 1), "qty": (1, 2)}.get(measure, (3, 2))
    ranked.sort(key=lambda r: (sign * r[order[0]], sign * r[order[1]], r[0]))

    shown = ranked[:top_n] if top_n else ranked
    keys = _row_keys(db, group_by, [r[0] for r in shown], company_grants)
    codes = _category_codes(db, [r[0] for r in shown], company_grants) if group_by == "category" else {}
    body["rows"] = [
        {
            "rank": i, "name": name, "qty": _qty(qty), "amount": _money_edge(amount), "keys": keys.get(name, []),
            **({"count": int(count)} if counted else {}),
            **({"code": codes[name]} if codes.get(name) else {}),
            **{key: _qty((pivot.row_totals.get(name) or {}).get(key)) for key in also},
        }
        for i, (name, qty, amount, count) in enumerate(shown, start=1)
    ]
    body["total_count"] = len(ranked)
    body["more"] = len(ranked) - len(shown)
    return body


# ----------------------------------------------------------------------- summary (REPORT-OUTSTANDING-SUMMARY)

#: The outstanding kinds that carry a summary (`report-outstanding-summary-behaviour-card.md`), and for each the
#: grouping that counts its documents, the one that dates them, and the extra measures its lines print.
SUMMARY_BASES: dict[str, dict[str, Any]] = {
    "outstanding": {"documents": "sales_order", "day": "order_day", "also": ("ordered_qty",)},
    "pending_delivery": {"documents": "delivery_order", "day": "day", "also": ()},
}


#: The groupings that list an outstanding figure's documents ("Reply 1 for the ... list."): never a summary.
DOCUMENT_GROUPS = frozenset({"sales_order", "delivery_order"})
#: The axes that are a run of time: their rows read oldest first, whatever the sort.
TIME_AXES = frozenset({"month", "year"})


def outstanding_summary(
    db: Session, *, basis: str, axes: list[str], date_from: date, date_to: date, sort: str = "desc",
    top_n: Optional[int] = None, **run: Any,
) -> dict[str, Any]:
    """The pre-#1922 outstanding summary, on this engine: the document count, the totals, the document date range and
    one breakdown per axis in `axes` (by default location, then customer or product; the user's own axis instead when
    one was named, owner 29 Oct; that axis keeps the ask's own `sort` and `top_n`, and a month or year axis reads oldest
    first). Every figure is `run_ask` over the SAME definition and filters as the total, so the
    summary cannot disagree with it. `run` is the total's own `run_ask` keywords, less the grouping."""
    shape = SUMMARY_BASES[basis]
    also = shape["also"]
    named_measure = run.pop("measure", None)
    run = {**run, "basis": basis}

    def grouped(group_by: str, *, measure: str = "qty", order: str = "desc", cut: Optional[int] = None) -> dict[str, Any]:
        return run_ask(
            db, group_by=group_by, date_from=date_from, date_to=date_to, top_n=cut, also=also, measure=measure,
            sort=order, **run,
        )

    total = grouped(None)
    days = sorted(r["name"] for r in grouped(shape["day"])["rows"])
    groups = []
    for axis in axes:
        if top_n is not None and axis not in TIME_AXES:
            # The user's own axis: its ranking as asked (its measure, direction and count).
            got = grouped(axis, measure=named_measure if named_measure in MEASURES else "qty", order=sort, cut=top_n)["rows"]
        else:
            got = grouped(axis)["rows"]
        if axis in TIME_AXES:
            got = sorted(got, key=lambda r: r["name"])
        rows = [{"name": r["name"], "qty": r["qty"], "amount": r["amount"], **{k: r.get(k, 0) for k in also}} for r in got]
        groups.append({"axis": axis, "label": GROUP_LABELS.get(axis, axis), "rows": rows})
    return {
        "documents": grouped(shape["documents"])["total_count"],
        **{k: v for k, v in total["total"].items() if k in ("qty", "amount", *also)},
        "date_first": days[0] if days else None,
        "date_last": days[-1] if days else None,
        "groups": groups,
    }


# ----------------------------------------------------------------------- compare (REPORT-SMART-1021)

#: What a sales ask may be compared with: the same number of days just before the period, or
#: the same dates a year earlier.
COMPARE_TO = ("previous_period", "last_year")
#: The sales channels a sales report filters by: the route, the parser schema and the parser's
#: `Sales channels:` line all read this one tuple.
SALES_CHANNELS = ("dealer", "project")


def compare_window(compare_to: str, date_from: date, date_to: date) -> tuple[date, date]:
    """The earlier window `compare_to` names. A 29 Feb a year back is 28 Feb."""
    from datetime import timedelta

    if compare_to == "previous_period":
        until = date_from - timedelta(days=1)
        return until - (date_to - date_from), until

    def year_back(d: date) -> date:
        try:
            return d.replace(year=d.year - 1)
        except ValueError:
            return d.replace(year=d.year - 1, day=28)

    return year_back(date_from), year_back(date_to)


def _change_pct(now: Any, before: Any) -> Optional[float]:
    now, before = Decimal(str(now or 0)), Decimal(str(before or 0))
    if not before:
        return None
    return float(((now - before) * 100 / before).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def attach_compare(body: dict[str, Any], earlier: dict[str, Any], measure: str) -> dict[str, Any]:
    """The earlier window's figures on every row of `body` (by name; a row the earlier window
    did not sell is zero there) and on the total, with the change on the sort measure. The
    ranking stays the period's own: a row only the earlier window has is not added."""
    key = "count" if measure in COUNT_MEASURES else measure
    zero = {"qty": 0, "amount": 0.0, **({"count": 0} if key == "count" else {})}
    by_name = {r["name"]: r for r in earlier.get("rows") or []}
    for row in body.get("rows") or []:
        before = by_name.get(row["name"])
        prev = {k: before.get(k, 0) for k in zero} if before else dict(zero)
        row["prev"] = prev
        row["change_pct"] = _change_pct(row.get(key), prev.get(key))
    total = body.get("total") or {}
    prev_total = {k: (earlier.get("total") or {}).get(k, 0) for k in zero}
    total["prev"] = prev_total
    total["change_pct"] = _change_pct(total.get(key), prev_total.get(key))
    body["total"] = total
    return body


# ----------------------------------------------------------------------- chat (CA-3)

NO_ASKS = f"No asks in that period. Chat data starts {chat_asks.TRACES_BEGIN.day} Sep 2026."


def _earliest_day(db: Session) -> date:
    """The day chat data starts: the earliest fact's day (CA-4's own `default_period`)."""
    return date.fromisoformat(chat_asks.default_period(db)["from"])


def _no_asks(db: Session) -> str:
    d = _earliest_day(db)
    return f"No asks in that period. Chat data starts {d.day} {d.strftime('%b %Y')}."


NO_MATCH = "No asks match those filters in that period."


def _chat_value(measure: str, totals: dict) -> Optional[dict[str, Any]]:
    """One row's (or the total's) figures, or None for a row that prints nothing: a rate over
    no turns, or a count of nothing."""
    if measure == "failure_rate":
        num, den = int(Decimal(totals.get("failed") or 0)), int(Decimal(totals.get("asks") or 0))
        if not den:
            return None
        pct = (Decimal(num) * 100 / Decimal(den)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
        return {"value": float(pct), "numerator": num, "denominator": den}
    value = int(Decimal(totals.get(measure) or 0))
    return {"value": value} if value else None


def _none_found(
    db: Session, definition: Any, period: dict, filters: dict[str, list[str]], scope_customers: Any = None
) -> str:
    """Nothing to show: the period holds asks but the filters match none, or the period is empty.
    "Holds asks" is read inside the caller's own scope, never across other customers."""
    if filters and chat_report_ask.period_has_asks(db, definition, period, scope_customers):
        return NO_MATCH
    return _no_asks(db)


def _run_chat(
    db: Session,
    *,
    basis: str,
    measure: str,
    group_by: Optional[str],
    date_from: date,
    date_to: date,
    filters: dict[str, list[str]],
    sort: str,
    top_n: Optional[int],
    scope_customers: Optional[list[str]] = None,
) -> dict[str, Any]:
    """The chat dataset's ranked rows, their cut and the whole set's total, with the coverage
    of topic labels. The period opens no earlier than the traces do."""
    from app.schemas.report import ReportViewConfig
    from app.services.reports import engine

    date_from = max(date_from, _earliest_day(db))
    body: dict[str, Any] = {
        "status": "ok",
        "message": None,
        "rows": [],
        "more": 0,
        "total_count": 0,
        "total": {"value": 0},
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "coverage": {"percent": 0, "taxonomy_version": None, "line": chat_asks.coverage_line(0, None)},
    }
    definition = CATALOGUE["chat"][basis]["definition"]
    params: dict[str, Any] = {
        "date_basis": "asked_at",
        "period": {"kind": "custom", "from": date_from.isoformat(), "to": date_to.isoformat()},
    }
    asker_split = group_by in ("asker", "salesperson") or "asker" in filters
    body["unclassified_askers"] = 0 if asker_split else None
    for word, values in filters.items():
        if not values:  # a filter resolving to nothing is zero rows, never "no filter"
            body["message"] = _none_found(db, definition, params["period"], filters, scope_customers)
            return body
        params[word] = list(values)
    unclassified = (
        chat_report_ask.unclassified_contacts(db, definition, params) if asker_split else None
    )
    body["unclassified_askers"] = unclassified
    body["unclassified_left_out"] = None
    if "asker" not in params:
        # The default asker filter (read now, so one switch changes it): staff and unclassified
        # out. A salesperson ranking is of salespeople only.
        params["asker"] = ["salesperson"] if group_by == "salesperson" else list(chat_report_ask.DEFAULT_ASKERS)
        # Only a default that itself leaves unclassified out says so (the salesperson axis narrows to
        # salespeople by its nature, which is not a default exclusion).
        if "unclassified" not in chat_report_ask.DEFAULT_ASKERS:
            # How many unclassified contacts the default left out, under the other filters.
            body["unclassified_left_out"] = chat_report_ask.unclassified_contacts(db, definition, params)
    coverage_ctx = engine.resolve(db, definition, params)
    percent, version = chat_asks.topics_coverage(coverage_ctx)
    body["coverage"] = {
        "percent": percent, "taxonomy_version": version, "line": chat_asks.coverage_line(percent, version, ctx=coverage_ctx)
    }
    if date_to < date_from:
        body["message"] = _no_asks(db)
        return body

    if group_by in CHAT_ITEM_AXES:
        params["grain"] = ["products"]
    measures = list(dict.fromkeys([measure, "asks", *(("failed",) if measure == "failure_rate" else ())]))
    view = ReportViewConfig.model_validate(
        {
            "params": params,
            "detail": {"columns": [], "order": []},
            "pivot": {
                # A customer axis groups by customer (name and id), so two customers sharing a
                # name stay two rows; the printed name is the part before the separator.
                "rows": "customer_ref" if group_by == "customer" else (group_by or "month"),
                "cols": "all",
                "measures": measures,
            },
        }
    )
    pivot = engine.run_summary(db, definition, params, view)

    grand = pivot.grand_total or {}
    if not int(Decimal(grand.get("asks") or 0)):
        body["message"] = _none_found(db, definition, params["period"], filters, scope_customers)
        return body
    body["total"] = _chat_value(measure, grand) or {"value": 0}
    if not group_by:
        return body

    ranked = []
    for name in pivot.row_values:
        if group_by in CHAT_NAMED_AXES and name == engine.BLANK_VALUE:
            continue  # no row for "nobody": only a failed ask has a reason, only some asks name a customer, a brand
        figures = _chat_value(measure, pivot.row_totals.get(name) or {})
        if figures is not None:
            ranked.append((name, figures))
    sign = -1 if sort == "desc" else 1
    if group_by in CHAT_TRENDS and top_n is None:
        ranked.sort(key=lambda r: r[0])
    else:
        ranked.sort(key=lambda r: (sign * r[1]["value"], r[0]))
    shown = ranked[:top_n] if top_n else ranked
    if group_by == "customer":
        refs = [name.partition(chat_report_ask.CUSTOMER_SEP) for name, _f in shown]
        agents = chat_report_ask.card_agents(db, [ref[2] for ref in refs])
        body["rows"] = [
            {"rank": i, "name": ref[0], **figures, "agent": agents.get(ref[2])}
            for i, ((_n, figures), ref) in enumerate(zip(shown, refs), start=1)
        ]
    else:
        body["rows"] = [{"rank": i, "name": name, **figures} for i, (name, figures) in enumerate(shown, start=1)]
    body["total_count"] = len(ranked)
    body["more"] = len(ranked) - len(shown)
    return body
