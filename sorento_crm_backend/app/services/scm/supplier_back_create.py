"""Creating a supplier a purchase file names that the master has never seen.

ONE rule, shared by the two channels that read a purchase book from AutoCount - the
outstanding purchase-order upload (`outstanding_import_service`) and the purchase-history
upload (`po_history_service`). It lives here because the two must agree: a creditor the
outstanding book creates and the history book leaves unlinked is the same supplier held
twice as far as anybody reading either screen is concerned, and the whole point of an
expediting list is being able to say who is late.

Why creating is right here and creating a PRODUCT is not: a supplier named on a real
purchase order is evidence the supplier exists, and an order with no creditor cannot be
reconciled or chased. An item code the catalogue does not hold is a code that arrives with
no category, no UOM and no price, so it is counted and named and never invented.

`suppliers` carries no source columns, so the provenance of a back-created creditor lives on
the orders that name it rather than on the supplier row.
"""
from __future__ import annotations

import logging
import re
from typing import Optional

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.procurement import Supplier

logger = logging.getLogger(__name__)

#: How many back-created supplier codes a job report names outright before it switches to
#: "... and N more". The COUNT is never capped - only the list an operator would actually
#: read is, the same trade the diff evidence samples make.
CREATED_SUPPLIERS_LISTED = 20

#: `suppliers.supplier_code` is String(50) (see the model); a slug longer than this is
#: truncated to leave room for the `-2`/`-3` disambiguator below.
SUPPLIER_SLUG_MAX = 50


def supplier_slug(db: Session, name: str, *, party: type = Supplier,
                  code_col: str = "supplier_code") -> str:
    """A deterministic `supplier_code` for a creditor the file names but gives no code for.

    Upper-cased alphanumerics only - punctuation and spaces dropped rather than kept, so
    `XIAMEN TAIYANG TECHNOLOGY CO.,LTD` becomes `XIAMENTAIYANGTECHNOLOGYCOLTD` - truncated to
    fit the column. A code already held in this company (another supplier whose name happens
    to slug the same way; by construction this is never the SAME name, since a matching
    existing name would have resolved before creation was ever considered) gets a numeric
    `-2`, `-3`, ... suffix rather than colliding on the unique constraint.
    """
    base = re.sub(r"[^A-Z0-9]", "", name.upper()) or "SUPPLIER"
    column = getattr(party, code_col)
    candidate = base[:SUPPLIER_SLUG_MAX]
    suffix = 1
    while db.query(party.id).filter(func.upper(column) == candidate).first() is not None:
        suffix += 1
        tail = f"-{suffix}"
        candidate = base[: max(SUPPLIER_SLUG_MAX - len(tail), 0)] + tail
    return candidate


def back_create_supplier(db: Session, *, code: str, name: str, party: type = Supplier,
                         code_col: str = "supplier_code",
                         name_col: str = "supplier_name") -> Optional[Supplier]:
    """Create one minimal supplier row, or answer None when the code is already taken.

    Company scope is the caller's ambient scope and nothing else: `company_id` is stamped by
    the `before_insert` listener on `CompanyScopedMixin`, so a row created here belongs to
    the company the upload is running as. `supplier_code` is unique per COMPANY (migration
    305), so a code another company already holds is created here too, as its own row.

    Flushed, because the caller needs the id immediately to link the document it is writing.

    Inside a SAVEPOINT, because a losing insert must not poison the transaction: a concurrent
    upload creating the same code for this same company, or a schema still on the model's
    bare column-level unique (a `create_all` scratch schema rather than a migrated one),
    would otherwise take down a whole 27,000-row job. The code is left exactly as unresolved
    as it already was instead.
    """
    try:
        with db.begin_nested():
            created = party(**{code_col: code, name_col: name, "is_active": True})
            db.add(created)
            db.flush()
    except IntegrityError:
        logger.warning(
            "could not back-create %s %r from a purchase upload (the code already exists)",
            party.__name__.lower(), code)
        return None
    return created
