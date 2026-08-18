"""Does this supplier exist, for THIS company, and is the value even an id.

Both SCM upload channels take the supplier on the form, because neither document names it
reliably, and both then hand that value to the database. So the check belongs in one place:
the proforma channel had it and the packing-list channel did not, which is how the same
non-id value became a clean 422 on one route and a 500 with an aborted session on the other
(`invalid input syntax for type uuid` out of a UUID column comparison).

Company scope is reproduced in raw SQL rather than through the ORM because `suppliers` is an
owned table and a raw SELECT bypasses the ORM's filter. Unscoped, an upload could be filed
against another company's supplier and their name shown back as confirmation that it was the
right one.
"""
from __future__ import annotations

import uuid
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.company_scope_sql import company_sql_predicate
from app.services.error_handler import AppException


def is_uuid(value: Any) -> bool:
    try:
        uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        return False
    return True


def supplier_row(db: Session, supplier_id: Optional[str]) -> Optional[Any]:
    """One supplier as `(supplier_code, supplier_name)`, scoped to the caller's company.

    A value that is not an id at all returns None rather than reaching the UUID column: the
    comparison raises `InvalidTextRepresentation`, which is not an `AppException`, so the
    caller is told the server broke and the session is left aborted.
    """
    if not supplier_id or not is_uuid(supplier_id):
        return None
    predicate, params = company_sql_predicate(db, "s.company_id", param_prefix="c")
    return db.execute(
        text(
            "SELECT s.supplier_code, s.supplier_name FROM suppliers s "
            " WHERE s.id = :i "
            f"   AND {predicate or 'true'}"
        ),
        {"i": str(supplier_id), **params},
    ).first()


def supplier_label(db: Session, supplier_id: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    row = supplier_row(db, supplier_id)
    return (row[0], row[1]) if row else (None, None)


def assert_supplier(db: Session, supplier_id: str) -> None:
    """A file uploaded against a supplier we do not hold is a form mistake, not a 500.

    Without this the insert dies on the foreign key (or on `invalid input syntax for type
    uuid` when the field is not an id at all) and the operator is told the server broke.
    Company-scoped, so another company's supplier is "does not exist" here too.
    """
    if supplier_row(db, supplier_id) is None:
        raise AppException(422, "That supplier does not exist.", detail="supplier_id")
