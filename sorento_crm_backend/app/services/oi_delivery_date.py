"""The one rule for an order inquiry row's delivery date (OI-ONE-DELIVERY-DATE).

An OI row's delivery date IS its SO line's date: the core `sales_order_lines.required_date`,
else the project mirror line's `delivery_date` when no core line is linked, else the row's own
stored date (no SO line, or a line with no date at all). The stored column
`order_inquiry_rows.delivery_date` is the TOLD date, the date purchasing was last told; it
feeds the DELAY / ADVANCE email diff and the Was below, and nothing else reads it as "the
delivery date". 2030-01-01 is printed as it is (owner, 3 Nov 2026).

Plan: `documentation/plans/scm/PLAN-oi-one-delivery-date-03nov.md`. This module is the only
place the rule lives: SQL readers call `line_date_sql` / `line_date_expr`, Python readers call
`resolve`.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, Iterable, Optional

from sqlalchemy import and_, case, func, select
from sqlalchemy.orm import Session, aliased

from app.models.order import SalesOrderLine
from app.models.project_so import OrderInquiryRow, ProjectSalesOrderLine


@dataclass(frozen=True)
class OiDate:
    """`date` is what every screen prints; `was` is the Was half of the Was / Now table."""

    date: Optional[date]
    was: Optional[date]


def pick(
    core_date: Optional[date], mirror_date: Optional[date], told: Optional[date] = None
) -> Optional[date]:
    """The rule for callers that already hold the two line dates: core first, then the
    mirror's, then the told date."""
    for value in (core_date, mirror_date, told):
        if value is not None:
            return value
    return None


def was_of(
    told: Optional[date], previous: Optional[date], line_date: Optional[date]
) -> Optional[date]:
    """The told date when it differs from the line date, else `previous` when that differs,
    else None. No line date means nothing to compare with."""
    if line_date is None:
        return None
    if told is not None and told != line_date:
        return told
    if previous is not None and previous != line_date:
        return previous
    return None


def line_date_expr(row_table: Any, mirror: Any, core: Any):
    """The rule as a SQL expression over a query that already joins `mirror` and `core`."""
    return func.coalesce(core.required_date, mirror.delivery_date, row_table.delivery_date)


def was_expr(row_table: Any, line_date: Any):
    """`was_of` as SQL, for a projection that already has the line date expression."""
    return case(
        (line_date.is_(None), None),
        (
            and_(row_table.delivery_date.isnot(None), row_table.delivery_date != line_date),
            row_table.delivery_date,
        ),
        (
            and_(
                row_table.previous_delivery_date.isnot(None),
                row_table.previous_delivery_date != line_date,
            ),
            row_table.previous_delivery_date,
        ),
        else_=None,
    )


def line_date_sql(row_table: Any = OrderInquiryRow):
    """The rule as a self-contained expression: a correlated scalar subquery over its own
    aliased outer joins, usable in any query that selects from `row_table` (filters, sort,
    month buckets, raw legs) without joining the two line tables itself."""
    mirror = aliased(ProjectSalesOrderLine)
    core = aliased(SalesOrderLine)
    line = (
        select(func.coalesce(core.required_date, mirror.delivery_date))
        .select_from(mirror)
        .outerjoin(core, core.id == mirror.core_sales_order_line_id)
        .where(mirror.id == row_table.so_line_id)
        .correlate(row_table)
        .scalar_subquery()
    )
    return func.coalesce(line, row_table.delivery_date)


def resolve(db: Session, rows: Iterable[Any]) -> Dict[str, OiDate]:
    """`{str(row.id): OiDate}` for `rows` (anything with id, so_line_id, delivery_date and
    previous_delivery_date), one batched read for all of them."""
    rows = list(rows)
    line_ids = {str(r.so_line_id) for r in rows if getattr(r, "so_line_id", None)}
    found: Dict[str, Optional[date]] = {}  # line id -> the line's own date, None if undated
    if line_ids:
        query = (
            db.query(
                ProjectSalesOrderLine.id,
                SalesOrderLine.required_date,
                ProjectSalesOrderLine.delivery_date,
            )
            .outerjoin(
                SalesOrderLine,
                SalesOrderLine.id == ProjectSalesOrderLine.core_sales_order_line_id,
            )
            .filter(ProjectSalesOrderLine.id.in_(line_ids))
        )
        found = {
            str(line_id): pick(core_date, mirror_date)
            for line_id, core_date, mirror_date in query.all()
        }
    out: Dict[str, OiDate] = {}
    for r in rows:
        told = r.delivery_date
        line_date = found.get(str(r.so_line_id)) if getattr(r, "so_line_id", None) else None
        shown = line_date if line_date is not None else told
        out[str(r.id)] = OiDate(
            date=shown, was=was_of(told, getattr(r, "previous_delivery_date", None), shown)
        )
    return out


def line_date_raw(alias: str = "oir") -> str:
    """The rule as a SQL fragment for hand-written queries over `projects.order_inquiry_rows
    <alias>`: a correlated subquery over its own aliases (`oidm`, `oidc`), so it fits any leg
    whatever the leg already joins. Interpolate it into an f-string."""
    return (
        "COALESCE((SELECT COALESCE(oidc.required_date, oidm.delivery_date) "
        "FROM projects.sales_order_lines oidm "
        "LEFT JOIN sales_order_lines oidc ON oidc.id = oidm.core_sales_order_line_id "
        f"WHERE oidm.id = {alias}.so_line_id), {alias}.delivery_date)"
    )
