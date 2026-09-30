"""Creating a customer a sales document names that the master has never seen.

The buying-side twin of `supplier_back_create.py`. The match key is the debtor
CODE alone, within the company (CUSTOMER-CODE-IDENTITY, owner decision 30 Sep
2026): AutoCount keys a debtor by code, and matching on the (code, name) pair -
the rule this replaced - forked a second customer row every time a document
spelled the name differently, which is how 300-1001 came to exist three times.
The name a document carries stays on the document (`sales_orders.debtor_name`);
the master's own name is never touched from here.

Fires only when BOTH code and name are sent (`document_ingest_service`'s
caller) - a code-only miss lands the order unlinked with `debtor_code` written
and a warning instead; inventing a name for a new master row would be worse
than leaving the order unlinked.
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.exc import DataError, IntegrityError
from sqlalchemy.orm import Session

from app.models.order import Customer
from app.services.rules.customer_rules import pick_customer_by_code

logger = logging.getLogger(__name__)


def get_or_create(
    db: Session, *, code: str, name: str, company_id: Optional[str] = None
) -> Optional[Customer]:
    """The customer this code names, created under `name` if nobody holds it.

    Company scope is the caller's ambient scope and nothing else, exactly like
    `supplier_back_create.back_create_supplier`: `company_id` is stamped by the
    `CompanyScopedMixin` `before_insert` listener from the session's active
    company, which the ingest route has already pinned to the request's anchor.

    `company_id` (S8 review fix) is an EXPLICIT filter on the existing-match
    query, not left to ambient ORM scoping alone: this function is called
    from inside a document ingest's own savepoint, where the caller already
    knows its anchor company and passing it here is one extra keyword rather
    than trusting a session-global filter to be active for this exact query -
    a code another company happens to hold must never be handed back as a
    match for THIS company's document.

    Legacy duplicates (more than one row still holding the code, before the
    merge migration ran) are resolved by `pick_customer_by_code`'s own rule -
    the ref holder, else the row with orders, else the oldest - never by
    creating a third.

    Inside a SAVEPOINT, for the same reason `back_create_supplier` uses one: a
    losing insert (a concurrent push creating the same code) must not poison
    the whole document's transaction.
    """
    existing_id, _ambiguous = pick_customer_by_code(db, code, company_id)
    if existing_id is not None:
        return db.get(Customer, existing_id)
    try:
        with db.begin_nested():
            created = Customer(
                customer_code=code.strip(),
                customer_name=name.strip(),
                customer_type="company",
                is_active=True,
            )
            db.add(created)
            db.flush()
    except (IntegrityError, DataError):
        logger.warning(
            "could not back-create customer %r/%r from a document push "
            "(the code already exists, or the value does not fit the column)",
            code,
            name,
        )
        return None
    return created
