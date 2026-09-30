"""Customer identity: the debtor code alone, within a company.

CUSTOMER-CODE-IDENTITY (owner decision, 30 Sep 2026; supersedes D13): AutoCount
keys a debtor by code, and matching on the (code, name) pair let every
differently spelled document name fork a second customer row - 300-1001 existed
three times. Every matcher goes through `pick_customer_by_code` here - the ESB
resolver (`master_ref_resolver`), the document back-create
(`customer_back_create`), the masters push (`master_ingest_service`), the order
import's debtor upsert and the manual create (`order_service`), and the customer
listing import - so a code can never resolve two different ways. The key is the
same one `uq_customers_company_code_lower` compares: `lower(btrim(code))`.

Names are labels. A document keeps the name it was issued under on itself
(`sales_orders.debtor_name`, `orders.debtor_name`); only the customer master
feeds (ESB masters push, listing import) rename the master, and a name they
replace is kept on the row as an alias (`record_name_alias`).
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.integration_reference import IntegrationReference
from app.models.order import Customer, Order, SalesOrder


def customer_code_key(code: Optional[str]) -> str:
    """The unique index's own comparison key for a debtor code: `lower(btrim(code))`."""
    return (code or "").strip().lower()


def pick_customer_by_code(
    db: Session, code: Optional[str], company_id: Optional[str]
) -> tuple[Optional[str], bool]:
    """`(customer_id, ambiguous)` for a debtor code, within `company_id` - or within
    the session's ambient company scope when `company_id` is None (the ORM scope
    filter applies to the query).

    One row holds the code: `(its id, False)`. None: `(None, False)`. More than one
    (legacy duplicates the merge migration has not folded yet): never a random
    pick - the row the integration already knows (an `integration_references`
    row), else the one with the most orders (`orders` + `sales_orders`), else the
    oldest - and `ambiguous=True` so the caller can say so (`customer_ambiguous`).
    Unreachable once `uq_customers_company_code_lower` is in place.
    """
    key = customer_code_key(code)
    if not key:
        return None, False
    query = db.query(Customer.id, Customer.created_at).filter(
        func.lower(func.btrim(Customer.customer_code)) == key
    )
    if company_id is not None:
        query = query.filter(Customer.company_id == company_id)
    rows = query.all()
    if not rows:
        return None, False
    if len(rows) == 1:
        return str(rows[0][0]), False

    ids = [str(r[0]) for r in rows]
    with_ref = {
        str(r[0])
        for r in db.query(IntegrationReference.entity_id)
        .filter(
            IntegrationReference.entity_type == Customer.__tablename__,
            IntegrationReference.entity_id.in_(ids),
        )
        .all()
    }
    order_counts: dict[str, int] = {i: 0 for i in ids}
    for model in (Order, SalesOrder):
        for customer_id, n in (
            db.query(model.customer_id, func.count(model.id))
            .filter(model.customer_id.in_(ids))
            .group_by(model.customer_id)
            .all()
        ):
            order_counts[str(customer_id)] += int(n)
    ranked = sorted(
        rows,
        key=lambda r: (
            0 if str(r[0]) in with_ref else 1,
            -order_counts[str(r[0])],
            r[1] is None,
            r[1],
            str(r[0]),
        ),
    )
    return str(ranked[0][0]), True


def _same_label(a: Optional[str], b: Optional[str]) -> bool:
    return (a or "").strip().lower() == (b or "").strip().lower()


def record_name_alias(customer: Customer, name: Optional[str]) -> bool:
    """Keep `name` on the customer as a former/other name. `True` when it was added.

    Order-preserving and case/space-insensitively distinct; the current
    `customer_name` is never an alias of itself. Assigns a NEW list so the JSONB
    column is flagged dirty (an in-place append is invisible to the ORM).
    """
    label = (name or "").strip()
    if not label or _same_label(label, customer.customer_name):
        return False
    aliases = list(customer.name_aliases or [])
    if any(_same_label(label, existing) for existing in aliases):
        return False
    customer.name_aliases = aliases + [label]
    return True


def fold_market_segment(db: Session, code: Optional[str]) -> Optional[str]:
    """A market segment spelling folded onto a real `market_segments.code`, or
    dropped (D16/S2, moved from `customer_import_service._resolve_market_segments`
    so the ESB masters push and the customer importer never drift on this rule).

    `market_segment_code` is a foreign key, so an unrecognised value would fail
    the whole customer on insert - losing a row over one optional column. The
    caller drops the value and warns `segment_unknown` instead (the same "name
    it, do not guess" rule the importer's unmapped-header report follows).
    Case/whitespace-insensitive, matching the importer's own `_key`.
    """
    if not code or not code.strip():
        return None
    from app.models.access import MarketSegment

    row = (
        db.query(MarketSegment.code)
        .filter(func.lower(func.btrim(MarketSegment.code)) == code.strip().lower())
        .first()
    )
    return row[0] if row else None


def back_create_customer(
    db: Session,
    *,
    code: str,
    name: str,
    segment: Optional[str] = None,
    region: Optional[str] = None,
    company_id: Optional[str] = None,
) -> Optional[Customer]:
    """Wraps `customer_back_create.get_or_create` (D8/D16): both channels
    that back-create a customer off a document - the ESB's `MasterRefResolver`
    and the outstanding SO upload - go through this one function, so a
    segment/region carried on the source document lands the same way from
    either.

    Fill-only (D16): `segment`/`region` are written ONLY when the resolved
    row does not already hold one - true for a freshly created row by
    definition, and for an existing match it is exactly the "never overwrite
    a hand-set segment" rule the masters push also follows.

    `segment` folds through the SAME `fold_market_segment` the masters push
    uses (review B5) - it used to be written STRAIGHT onto
    `market_segment_code`, a foreign key, so an unrecognised spelling would
    have failed on flush rather than dropping quietly the way every other
    entry point into this column already does. An unresolved spelling is
    silently dropped here (no document/verdict for THIS function's own
    caller to warn on - `document_ingest_service._apply_customer_segment_and_region`
    is the caller that has one, and folds `customer_segment` itself before
    ever reaching here).
    """
    # Imported here, not at module level: `customer_back_create` matches
    # through `pick_customer_by_code` above, so the two modules would
    # otherwise import each other.
    from app.services.scm import customer_back_create

    customer = customer_back_create.get_or_create(db, code=code, name=name, company_id=company_id)
    if customer is None:
        return None
    if segment and not customer.market_segment_code:
        canonical = fold_market_segment(db, segment)
        if canonical:
            customer.market_segment_code = canonical
    if region and not customer.region:
        customer.region = region
    return customer
