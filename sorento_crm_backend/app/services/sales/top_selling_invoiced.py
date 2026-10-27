"""The top selling route's invoiced basis (SALES-UNIFIED AC-25, AC-30): the Top selling items
report (`reports/definitions/top_selling_items.py`) run through the engine, read into the
route's own response shape. No second query: the route's figures ARE the report's.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.services.error_handler import AppException

KEY = "top_selling_items"


def _names(db: Session, model: Any, column: Any, ids: Optional[List[str]]) -> Optional[str]:
    if not ids:
        return None
    rows = db.query(column).filter(model.id.in_(ids)).all()
    return ", ".join(sorted(str(r[0]) for r in rows if r[0])) or None


def top_selling_invoiced(
    db: Session,
    *,
    rank_by: str,
    n: Optional[int],
    direction: str,
    customer_ids: Optional[List[str]],
    category_ids: Optional[List[str]],
    sales_agent_ids: Optional[List[str]],
    brand_ids: Optional[List[str]],
    channel: Optional[str],
    date_from: date,
    date_to: date,
    dealer_scoped: bool,
) -> Dict[str, Any]:
    from app.models.order import Customer
    from app.models.product import Brand, ProductCategory
    from app.models.sales_agent import SalesAgent
    from app.schemas.report import ReportViewConfig
    from app.services.reports import engine, registry as reg
    from app.services.sales.invoiced_sales import SALES_TYPE_LABELS, normalise_sales_types

    definition = reg.get(KEY)
    if definition is None:  # pragma: no cover - registered at import
        raise AppException(500, "Top selling items report is not registered", code="report_missing")
    params: Dict[str, Any] = {
        "date_basis": "order_date",
        "period": {"kind": "custom", "from": date_from.isoformat(), "to": date_to.isoformat()},
        "channel": normalise_sales_types([channel]) if channel else [],
    }
    for key, values in (
        ("customer", customer_ids),
        ("category", category_ids),
        ("agent", sales_agent_ids),
        ("brand", brand_ids),
    ):
        if values:
            params[key] = list(values)
    view = ReportViewConfig.model_validate({
        "params": params,
        "detail": {"columns": [], "order": []},
        "pivot": {"rows": "item_code", "cols": "year", "measures": ["quantity", "sales_value"]},
    })
    pivot = engine.run_summary(db, definition, params, view)

    ranked = []
    for value in pivot.row_values:
        totals = pivot.row_totals.get(value) or {}
        qty = Decimal(totals.get("quantity") or 0)
        amount = Decimal(totals.get("sales_value") or 0)
        if not qty and not amount:
            continue
        ranked.append((None if value == engine.BLANK_VALUE else value, qty, amount))
    metric = 1 if rank_by == "quantity" else 2
    sign = -1 if direction == "top" else 1
    ranked.sort(key=lambda r: (sign * r[metric], sign * r[3 - metric], r[0] or ""))
    shown = ranked[:n] if n else ranked

    grand = pivot.grand_total or {}
    return {
        "rank_by": rank_by,
        "basis": "invoiced",
        "group": "item",
        "direction": direction,
        "n": n,
        "date_from": date_from,
        "date_to": date_to,
        "filters": {
            "customer_name": _names(db, Customer, Customer.customer_name, customer_ids),
            "category_name": _names(db, ProductCategory, ProductCategory.category_name, category_ids),
            "brand_name": _names(db, Brand, Brand.brand_name, brand_ids),
            "sales_agent": _names(db, SalesAgent, SalesAgent.sales_agent, sales_agent_ids),
            "channel": SALES_TYPE_LABELS.get(normalise_sales_types([channel])[0]) if channel else None,
            "dealer_scoped": dealer_scoped,
        },
        "total_count": len(ranked),
        "rows": [
            {"rank": i, "code": code, "quantity": int(qty), "amount": float(amount)}
            for i, (code, qty, amount) in enumerate(shown, start=1)
        ],
        "totals": {
            "quantity": int(Decimal(grand.get("quantity") or 0)),
            "amount": float(Decimal(grand.get("sales_value") or 0)),
        },
    }
