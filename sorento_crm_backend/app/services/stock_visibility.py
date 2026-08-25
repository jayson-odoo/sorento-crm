"""Which locations a chatbot contact may be told about, and in which shape.

Three tiers, resolved here and enforced in ``StockService.list_stock``:

    contact override  >  contact access type  >  global default

Same doctrine as ``app.services.field_access``: the preflight endpoint
(``GET /inventory/stock-visibility/effective``) is a CONVENIENCE for n8n, never
the mechanism. Forgetting to call it must not be the difference between safe and
leaking, so the data endpoint applies the policy itself.

**Most restrictive wins across access types.** A contact tagged both `dealer`
(availability, dealer pool) and `end_user` (detailed, everywhere) must come out
as a dealer: modes rank ``availability > compact > detailed`` and warehouse sets
INTERSECT, with NULL read as "all" so it never widens anybody. The looser tag
otherwise undoes the dealer rule the moment somebody adds a second label.

**Fail closed on an unresolvable contact.** ``resolve_policy`` answers ``None``,
which the caller turns into zero rows and NO visibility block - exactly what
company scope already does when contact params name nobody. Returning the
default instead would answer a stranger's question with everyone's data.

**The floor is code, not data.** The default row is seeded by migration 416, but
a database built by ``create_all`` (CI) has no seeds, so ``default_policy``
falls back to detailed / all warehouses rather than to nothing.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

#: The whole vocabulary, loosest first. Nothing outside this reaches the table
#: (CHECK constraint) or the API (Literal on the request schema).
MODES: tuple[str, ...] = ("detailed", "compact", "availability")

#: Higher = more restrictive. Drives the merge when a contact holds several
#: access types.
_MODE_RANK = {mode: rank for rank, mode in enumerate(MODES)}

DEFAULT_MODE = "detailed"

SOURCE_CONTACT = "contact"
SOURCE_ACCESS_TYPE = "access_type"
SOURCE_DEFAULT = "default"


@dataclass(frozen=True)
class Policy:
    """What one caller may be told.

    ``warehouse_ids`` None = every active warehouse their company scope allows;
    an empty frozenset = none at all. ``source_label`` carries the access type's
    NAME (not its code) so the admin badge can read "Access type: Dealer".
    """

    mode: str
    warehouse_ids: Optional[frozenset[str]]
    source: str
    source_label: Optional[str] = None


def _row_warehouse_ids(row) -> Optional[frozenset[str]]:
    if row.warehouse_ids is None:
        return None
    return frozenset(str(w) for w in row.warehouse_ids)


def _policy_from_row(row, source: str, source_label: Optional[str] = None) -> Policy:
    return Policy(
        mode=row.mode,
        warehouse_ids=_row_warehouse_ids(row),
        source=source,
        source_label=source_label,
    )


def default_policy(db: Session) -> Policy:
    """The global default row, or the inert detailed/all policy when absent."""
    from app.models.access import StockVisibilityPolicy

    row = (
        db.query(StockVisibilityPolicy)
        .filter(
            StockVisibilityPolicy.contact_id.is_(None),
            StockVisibilityPolicy.access_type_code.is_(None),
        )
        .first()
    )
    if row is None:
        return Policy(mode=DEFAULT_MODE, warehouse_ids=None, source=SOURCE_DEFAULT)
    return _policy_from_row(row, SOURCE_DEFAULT)


def contact_override(db: Session, resolved_contact_id: str):
    """The row stored AT the contact tier, or None when the contact inherits."""
    from app.models.access import StockVisibilityPolicy

    return (
        db.query(StockVisibilityPolicy)
        .filter(StockVisibilityPolicy.contact_id == resolved_contact_id)
        .first()
    )


def access_type_override(db: Session, access_type_code: str):
    """The row stored AT one access type, or None when that type inherits."""
    from app.models.access import StockVisibilityPolicy

    return (
        db.query(StockVisibilityPolicy)
        .filter(StockVisibilityPolicy.access_type_code == access_type_code)
        .first()
    )


def _merge_access_type_rows(rows: list[tuple[Any, Optional[str]]]) -> Policy:
    """Most restrictive mode, intersection of warehouses (NULL = all)."""
    mode = max((row.mode for row, _ in rows), key=lambda m: _MODE_RANK.get(m, 0))

    merged: Optional[frozenset[str]] = None
    for row, _ in rows:
        ids = _row_warehouse_ids(row)
        if ids is None:
            continue
        merged = ids if merged is None else (merged & ids)

    # The label names the row that decided the MODE; with several at the same
    # rank the lowest code wins, so the badge is stable rather than order-dependent.
    deciding = sorted(
        (pair for pair in rows if pair[0].mode == mode),
        key=lambda pair: str(pair[0].access_type_code),
    )[0]
    return Policy(
        mode=mode,
        warehouse_ids=merged,
        source=SOURCE_ACCESS_TYPE,
        source_label=deciding[1],
    )


def access_type_policy(db: Session, resolved_contact_id: str) -> Optional[Policy]:
    """The merged access-type tier for a contact, or None when no type has a row."""
    from app.models.access import (
        ContactAccessType,
        StockVisibilityPolicy,
        respond_contact_access_types,
    )

    rows = (
        db.query(StockVisibilityPolicy, ContactAccessType.name)
        .join(
            ContactAccessType,
            ContactAccessType.code == StockVisibilityPolicy.access_type_code,
        )
        .join(
            respond_contact_access_types,
            respond_contact_access_types.c.access_type_code == ContactAccessType.code,
        )
        .filter(respond_contact_access_types.c.contact_id == resolved_contact_id)
        .all()
    )
    if not rows:
        return None
    return _merge_access_type_rows([(row, name) for row, name in rows])


def resolve_policy(
    db: Session, contact_id: str, space_id: Optional[str] = None
) -> Optional[Policy]:
    """The policy that applies to one contact, or None when nobody resolved.

    ``contact_id`` is accepted in either id space (internal ``respond_contacts.id``
    or the Respond.io id), with ``space_id`` disambiguating the latter - the same
    rule ``field_access.resolve_contact_id`` already applies, and guessing wrong
    would answer with a stranger's policy.
    """
    from app.services.field_access import resolve_contact_id

    resolved = resolve_contact_id(db, contact_id, space_id)
    if not resolved:
        return None

    override = contact_override(db, resolved)
    if override is not None:
        return _policy_from_row(override, SOURCE_CONTACT)

    merged = access_type_policy(db, resolved)
    if merged is not None:
        return merged

    return default_policy(db)


def effective_policy_for_access_type(db: Session, access_type_code: str) -> Policy:
    """What a contact holding ONLY this access type would get."""
    from app.models.access import ContactAccessType

    row = access_type_override(db, access_type_code)
    if row is None:
        return default_policy(db)
    name = (
        db.query(ContactAccessType.name)
        .filter(ContactAccessType.code == access_type_code)
        .scalar()
    )
    return _policy_from_row(row, SOURCE_ACCESS_TYPE, name)


# ------------------------------------------------------------------- admin writes


def validated_warehouse_ids(db: Session, warehouse_ids) -> Optional[list[str]]:
    """Reject an id that is not a warehouse before it is stored.

    A dangling id would silently narrow the policy to fewer locations than the
    admin picked, and nothing on the card could show them why.
    """
    from app.models.inventory import Warehouse
    from app.services.error_handler import handle_unprocessable

    if warehouse_ids is None:
        return None
    wanted = [str(w) for w in warehouse_ids]
    if not wanted:
        return []
    found = {
        str(row_id)
        for (row_id,) in db.query(Warehouse.id).filter(Warehouse.id.in_(wanted)).all()
    }
    missing = [w for w in wanted if w not in found]
    if missing:
        raise handle_unprocessable(
            f"Unknown warehouse: {', '.join(missing)}"
        )
    # De-duplicated, order-insensitive: the set is a membership test, never a list
    # the reader sees in this order.
    return sorted(found)


def upsert_policy(
    db: Session,
    *,
    mode: str,
    warehouse_ids,
    contact_id: Optional[str] = None,
    access_type_code: Optional[str] = None,
):
    """Create or replace the row AT one tier. `warehouse_ids` replaces wholesale."""
    import uuid as _uuid

    from app.models.access import StockVisibilityPolicy

    if contact_id:
        row = contact_override(db, contact_id)
    elif access_type_code:
        row = access_type_override(db, access_type_code)
    else:
        row = (
            db.query(StockVisibilityPolicy)
            .filter(
                StockVisibilityPolicy.contact_id.is_(None),
                StockVisibilityPolicy.access_type_code.is_(None),
            )
            .first()
        )

    if row is None:
        row = StockVisibilityPolicy(
            id=str(_uuid.uuid4()),
            contact_id=contact_id,
            access_type_code=access_type_code,
        )
        db.add(row)
    # setattr rather than plain assignment: the mapped attribute is typed
    # `Column[...]` at rest, and pyright rejects the direct form.
    setattr(row, "mode", mode)
    setattr(row, "warehouse_ids", warehouse_ids)
    db.commit()
    db.refresh(row)
    return row


def delete_policy(
    db: Session,
    *,
    contact_id: Optional[str] = None,
    access_type_code: Optional[str] = None,
) -> bool:
    """Hard delete of one tier's row. Missing is not an error - the tier already
    inherits, which is the state the caller asked for."""
    from app.models.access import StockVisibilityPolicy

    q = db.query(StockVisibilityPolicy)
    if contact_id:
        q = q.filter(StockVisibilityPolicy.contact_id == contact_id)
    elif access_type_code:
        q = q.filter(StockVisibilityPolicy.access_type_code == access_type_code)
    else:  # pragma: no cover - the default tier has no DELETE route
        raise ValueError("The default policy row cannot be deleted.")
    deleted = q.delete(synchronize_session=False)
    db.commit()
    return bool(deleted)


def policy_warehouses(db: Session, warehouse_ids: Optional[frozenset[str]]):
    """Resolve stored ids to `{id, code, name}`, ordered by code.

    Resolved server-side so the card renders `CODE - name` without a second round
    trip and without a UUID ever reaching the screen.
    """
    from app.models.inventory import Warehouse

    if warehouse_ids is None:
        return None
    if not warehouse_ids:
        return []
    rows = (
        db.query(Warehouse)
        .filter(Warehouse.id.in_(list(warehouse_ids)))
        .order_by(Warehouse.warehouse_code.asc())
        .all()
    )
    return [
        {"id": str(row.id), "code": row.warehouse_code, "name": row.warehouse_name}
        for row in rows
    ]


def policy_payload(db: Session, policy: Policy) -> dict:
    """One Policy as the API returns it."""
    return {
        "mode": policy.mode,
        "warehouses": policy_warehouses(db, policy.warehouse_ids),
        "source": policy.source,
        "source_label": policy.source_label,
    }
