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
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.services.reports.datasets import delivery_order_lines, sales_order_lines_ask
from app.services.sales_report_delivered import (
    _CHANNEL_CLASS,
    _allowed,
    _policy_location_ids,
    _warehouse_ids_by_code,
    refusal_message,
)
from app.services.sales_report_service import _money_edge, _qty

_DIMENSION_KEYS = {
    "customer": "customer",
    "product": "product",
    "brand": "brand",
    "category": "category",
    "sales_agent": "sales_agent",
    "location": "location",
    "channel": "channel",
    "month": "month",
}
_FILTER_KEYS = {
    "customer": "customer",
    "product": "product",
    "brand": "brand",
    "category": "category",
    "sales_agent": "sales_agent",
    "location": "location",
    "channel": "channel",
}

#: One entry per basis, over the spec's words. Both bases speak the same words.
CATALOGUE: dict[str, dict[str, Any]] = {
    "delivered": {
        "definition": delivery_order_lines.DEFINITION,
        "label": "delivered sales",
        "dimensions": dict(_DIMENSION_KEYS),
        "filters": dict(_FILTER_KEYS),
    },
    "ordered": {
        "definition": sales_order_lines_ask.DEFINITION,
        "label": "ordered sales",
        "dimensions": dict(_DIMENSION_KEYS),
        "filters": dict(_FILTER_KEYS),
    },
}

#: What a customer-scoped contact (a dealer) may group or filter by (PLAN section 0, Q1/Q2).
DEALER_KEYS = frozenset({"product", "brand", "category", "month"})

GROUP_LABELS = {
    "customer": "Customer",
    "product": "Product",
    "brand": "Brand",
    "category": "Category",
    "sales_agent": "Sales agent",
    "location": "Location",
    "channel": "Channel",
    "month": "Month",
}

#: The delivered dataset's raw channel values, as the ordered dataset already prints them.
_CHANNEL_NAMES = {"retail": "Dealer", "project": "Project team"}

MEASURES = ("amount", "qty")


def _empty(status: str = "ok", message: Optional[str] = None) -> dict[str, Any]:
    return {
        "status": status,
        "message": message,
        "rows": [],
        "more": 0,
        "total_count": 0,
        "total": {"qty": 0, "amount": 0.0},
    }


def _resolve_locations(
    db: Session, named_codes: list[str], policy: Any
) -> tuple[Optional[list[str]], Optional[dict[str, Any]]]:
    """(location ids or None for no cap, an answer already complete or None). A contact always
    asks here, so a missing policy fails closed."""
    if policy is None:
        return None, _empty()
    if named_codes:
        by_code = _warehouse_ids_by_code(db, named_codes)
        for named in named_codes:
            if any(not _allowed(policy, wid) for wid in by_code[named]):
                return None, _empty("refused", refusal_message(named))
        ids = sorted({wid for found in by_code.values() for wid in found})
        return ids, (None if ids else _empty())
    ids = _policy_location_ids(db, policy)
    if ids is not None and not ids:
        return None, _empty()
    return ids, None


def run_ask(
    db: Session,
    *,
    basis: str,
    measure: str,
    group_by: Optional[str],
    date_from: date,
    date_to: date,
    filters: dict[str, list[str]],
    warehouse_codes: list[str],
    policy: Any,
    sort: str = "desc",
    top_n: Optional[int] = None,
) -> dict[str, Any]:
    """The ranked rows, their cut and the whole set's total. `filters` maps a spec word to
    RESOLVED ids (channel: `dealer` / `project`); `warehouse_codes` are the raw codes named."""
    from app.schemas.report import ReportViewConfig
    from app.services.reports import engine

    entry = CATALOGUE[basis]
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
        params[entry["filters"][word]] = list(values)

    location_ids, answer = _resolve_locations(db, warehouse_codes, policy)
    if answer is not None:
        return answer
    if location_ids is not None:
        params[entry["filters"]["location"]] = location_ids

    # The engine refuses rows == cols, so the one-total shape groups by month and reads the
    # grand total only.
    rows_key = entry["dimensions"][group_by or "month"]
    view = ReportViewConfig.model_validate(
        {
            "params": params,
            "detail": {"columns": [], "order": []},
            "pivot": {"rows": rows_key, "cols": "all", "measures": list(MEASURES)},
        }
    )
    pivot = engine.run_summary(db, definition, params, view)

    grand = pivot.grand_total or {}
    body = _empty()
    body["total"] = {"qty": _qty(grand.get("qty")), "amount": _money_edge(grand.get("amount"))}
    if not group_by:
        return body

    ranked = []
    for value in pivot.row_values:
        totals = pivot.row_totals.get(value) or {}
        qty, amount = Decimal(totals.get("qty") or 0), Decimal(totals.get("amount") or 0)
        if not qty and not amount:
            continue
        name = _CHANNEL_NAMES.get(value, value) if group_by == "channel" else value
        ranked.append((name, qty, amount))

    sign = -1 if sort == "desc" else 1
    first, second = (2, 1) if measure == "amount" else (1, 2)
    ranked.sort(key=lambda r: (sign * r[first], sign * r[second], r[0]))

    shown = ranked[:top_n] if top_n else ranked
    body["rows"] = [
        {"rank": i, "name": name, "qty": _qty(qty), "amount": _money_edge(amount)}
        for i, (name, qty, amount) in enumerate(shown, start=1)
    ]
    body["total_count"] = len(ranked)
    body["more"] = len(ranked) - len(shown)
    return body
