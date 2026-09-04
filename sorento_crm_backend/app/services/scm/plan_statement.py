"""Which rows are a loading plan's OWN statement, and when a plan has none (S6).

Migration 454 stamped both statement tables with the plan their upload was applied into and
re-keyed the stock snapshot to `(company, supplier, coalesce(loading_plan_id, nil),
item_code)`. One supplier can therefore hold the same model number many times over: once per
plan, plus the standalone stock-list page's own row. Every reader that used to select "this
supplier's rows" now selects a UNION, and a reader keyed by item code collapses that union
onto whichever row it saw last - which is how another plan's figures reach the factory.

Two questions, one answer each, in one place because four readers ask them:

* **Does this plan have a statement of its own?** `has_stock_rows` / `has_invoices`, and both
  are asked about ROWS, never about matched holdings. A plan whose upload wrote 115 stamped
  rows that bound to nothing HAS a statement; it just says nothing about our catalogue. Read
  the other way round - "no holdings, so no statement" - the plan fell through to the
  supplier-wide read and showed another upload's numbers under its own name.
* **Which rows may this reader see?** `stock_scope`, a WHERE fragment: this plan's rows when
  it has any, the pre-454 supplier-wide rows (`loading_plan_id IS NULL`) when it has none,
  and no restriction at all when there is no plan in scope. A plan in scope therefore never
  reads another plan's row, whatever else is on file for the supplier.
"""
from __future__ import annotations

from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.scm import ProformaInvoice, SupplierInventory


def has_stock_rows(db: Session, loading_plan_id: Optional[str]) -> bool:
    """Did an upload write stock-list rows into this plan - matched or not."""
    if not loading_plan_id:
        return False
    return bool(
        db.query(SupplierInventory)
        .filter(SupplierInventory.loading_plan_id == str(loading_plan_id))
        .count()
    )


def has_invoices(db: Session, loading_plan_id: Optional[str]) -> bool:
    """Is any proforma invoice bound to this plan - its lines matched or not."""
    if not loading_plan_id:
        return False
    return bool(
        db.query(ProformaInvoice)
        .filter(ProformaInvoice.loading_plan_id == str(loading_plan_id))
        .count()
    )


def stock_scope(db: Session, loading_plan_id: Optional[str]) -> Optional[Any]:
    """The stock-row predicate for a reader working on behalf of `loading_plan_id`.

    `None` means "add nothing": there is no plan in scope, so the caller keeps whatever
    supplier-wide read it always did. With a plan in scope the answer is always a filter, so
    no reader can see a row belonging to a different plan.
    """
    if not loading_plan_id:
        return None
    if has_stock_rows(db, loading_plan_id):
        return SupplierInventory.loading_plan_id == str(loading_plan_id)
    # Nothing of its own: a legacy plan that predates 454, or a plan whose statement is a
    # proforma. Either way the honest wider answer is the supplier-wide snapshot the
    # standalone page maintains - never the rows some other plan uploaded.
    return SupplierInventory.loading_plan_id.is_(None)
