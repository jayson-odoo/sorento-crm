"""Creating a customer a sales document names that the master has never seen.

The buying-side twin of `supplier_back_create.py`, for a document ingest reason
that module does not have: `order_service._upsert_customer_from_debtor` already
back-creates customers off a debtor name/code pair, and this is the same rule -
match key is the (code, name) PAIR, not the code alone (D2), because one
AutoCount debtor code routinely carries more than one legal name and the
composite unique index (migration 220) is on the pair. A code-only row would
collide with the first NAMED row that comes along under the same code later.

Fires only when BOTH code and name are sent (`document_ingest_service`'s
caller) - a code-only miss lands the order unlinked with `debtor_code` written
and a warning instead; inventing a name to satisfy the pair key would be worse
than leaving the order unlinked.
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.order import Customer

logger = logging.getLogger(__name__)


def get_or_create(db: Session, *, code: str, name: str) -> Optional[Customer]:
    """The customer this (code, name) pair names, created if nobody holds it.

    Company scope is the caller's ambient scope and nothing else, exactly like
    `supplier_back_create.back_create_supplier`: `company_id` is stamped by the
    `CompanyScopedMixin` `before_insert` listener from the session's active
    company, which the ingest route has already pinned to the request's anchor.

    Inside a SAVEPOINT, for the same reason `back_create_supplier` uses one: a
    losing insert (a concurrent push creating the same pair) must not poison
    the whole document's transaction.
    """
    existing = (
        db.query(Customer)
        .filter(
            func.upper(func.btrim(Customer.customer_code)) == code.strip().upper(),
            func.upper(func.btrim(Customer.customer_name)) == name.strip().upper(),
        )
        .order_by(Customer.id.desc())
        .first()
    )
    if existing is not None:
        return existing
    try:
        with db.begin_nested():
            created = Customer(
                customer_code=code,
                customer_name=name,
                customer_type="company",
                is_active=True,
            )
            db.add(created)
            db.flush()
    except IntegrityError:
        logger.warning(
            "could not back-create customer %r/%r from a document push "
            "(the pair already exists)",
            code,
            name,
        )
        return None
    return created
