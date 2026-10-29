"""The filter params the six ask definitions show on the "Sales & outstanding" screen (REPORT-UNIFY slice 4,
`documentation/plans/reports/PLAN-report-unify-27oct.md` section 3b).

The ask definitions (`datasets/sales_order_lines_ask`, `billing_document_lines.ASK_DEFINITION`,
`delivery_order_lines.PENDING_DEFINITION`, `unpaid_documents`) are the ones `ask.CATALOGUE` runs for the chatbot; the
screen registers THE SAME objects, so the option lists and the `spec` condition below are what staff see and what the
route's own filters mean. Customer, agent, brand and category options reuse the helpers of the Top selling items and
Sales by debtor type reports.
"""
from __future__ import annotations

from typing import Any, List, Optional, Sequence, Tuple

from sqlalchemy import false

from app.models.order import Customer
from app.models.product import ProductCategory
from app.services.reports import spec_set


def customer_options(db: Any) -> List[Tuple[str, str]]:
    rows = db.query(Customer.id, Customer.customer_name).filter(Customer.customer_name.isnot(None)).all()
    return sorted(((str(i), str(n)) for i, n in rows), key=lambda r: r[1].casefold())


def agent_options(db: Any) -> List[Tuple[str, str]]:
    from app.services.reports.definitions.sales_by_debtor_type import agent_options as options

    return options(db)


def brand_options(db: Any) -> List[Tuple[str, str]]:
    from app.services.reports.definitions.top_selling_items import brand_options as options

    return options(db)


def category_options(db: Any) -> List[Tuple[str, str]]:
    rows = db.query(ProductCategory.id, ProductCategory.category_name).filter(ProductCategory.category_name.isnot(None)).all()
    return sorted(((str(i), str(n)) for i, n in rows), key=lambda r: r[1].casefold())


def spec_options(db: Any) -> List[Tuple[str, str]]:
    """One option per enum value of the spec registry: value `key:value` (the route's own `spec=` form), label
    "<registry label>: <value label>"."""
    from app.services.product_spec_registry import display_spec_value, merged_allowed_values

    out: List[Tuple[str, str]] = []
    for row in sorted(spec_set.registry(db).values(), key=lambda r: (str(r.label or r.spec_key).casefold(), r.spec_key)):
        if (row.data_type or "").lower() != "enum":
            continue
        labels = dict(getattr(row, "value_labels", None) or {})
        # The registry's allowed values, then any value staff gave only a label (a label is an offered word too).
        values = list(merged_allowed_values(row))
        values += [v for v in labels if v not in values]
        for value in values:
            out.append((f"{row.spec_key}:{value}", f"{row.label}: {display_spec_value(value, labels)}"))
    return out


def spec_condition(ctx: Any, values: Sequence[str]) -> Optional[Any]:
    """`product_id IN (the products holding the chosen spec values)`: the resolution the route's `spec` param uses
    (different keys ANDed, the values of one key ORed). A term that cannot narrow matches nothing, never the whole set."""
    column = ctx.dataset.product_id_column
    if column is None:
        return None
    try:
        terms = spec_set.parse(list(values))
    except ValueError:
        return false()
    grants = ctx.company_grants
    ids, _echo, _not_applied = spec_set.resolve(ctx.db, terms, set(), None if grants is None else set(grants))
    return column.in_(ids) if ids else false()


#: The Detail tab's default columns of the line-level asks (the Top selling items report's shape: what, who, how much).
DETAIL_COLUMNS = ("month", "customer", "product", "sales_agent", "qty", "amount")
#: An unpaid invoice has no product and no quantity.
UNPAID_DETAIL_COLUMNS = ("month", "customer", "sales_agent", "amount")
