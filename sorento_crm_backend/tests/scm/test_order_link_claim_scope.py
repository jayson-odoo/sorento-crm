"""A claim's identity belongs to a COMPANY, and the guard and the constraint must agree.

The bug this pins, from the real screen: uploading the purchase-history book from a second
company died on

    duplicate key ... uq_scm_order_link_claim_identity
    Key (so_number, po_number, coalesce(item_code, ''))=(175592, PO-2020/01-0010, )

Every READ of `order_link_claim` is company-scoped, because the model carries
`CompanyScopedMixin` and the ORM filter applies. So the "does this claim already exist?"
guard in both feeds looks only inside the caller's company, finds nothing, inserts - and the
index rejects it because ANOTHER company holds that pairing. The guard was right and the
constraint was too wide.

Both halves are asserted here, because fixing one alone re-breaks the other: two companies
must be able to hold the same pairing, and one company must still not hold it twice.
"""
from __future__ import annotations

import uuid
from datetime import datetime

import pytest

from app.models.base import set_company_scope
from app.models.company import Company
from app.models.scm import OrderLinkClaim
from tests._pg_fixture import pg_session

MARKER = "ZZTCLAIM"

#: The pairing from the real failure, so the test reads as the incident it came from.
SO_NUMBER = "175592"
PO_NUMBER = "PO-2020/01-0010"


def _u() -> str:
    return str(uuid.uuid4())


@pytest.fixture()
def db():
    with pg_session() as s:
        yield s


def _company(db) -> str:
    cid = _u()
    db.add(Company(id=cid, name=f"{MARKER} {cid[:8]}",
                   code=f"{MARKER}-{uuid.uuid4().hex[:6]}".upper()[:50], is_active=True))
    db.flush()
    return cid


def _claim(db, *, so=SO_NUMBER, po=PO_NUMBER, item=None) -> OrderLinkClaim:
    row = OrderLinkClaim(
        id=_u(), so_number=so, po_number=po, item_code=item,
        source="po_history", claimed_at=datetime(2026, 8, 5, 12, 0, 0),
    )
    db.add(row)
    db.flush()
    return row


def test_two_companies_can_claim_the_same_pairing(db):
    """Mocha's purchase order is not Sorento's, whatever the numbers happen to be.

    This is the upload that failed: the same book, loaded by a second company.
    """
    first, second = _company(db), _company(db)

    set_company_scope(db, frozenset({first}))
    _claim(db)

    set_company_scope(db, frozenset({second}))
    _claim(db)   # must not raise

    held = db.execute(
        OrderLinkClaim.__table__.select().where(
            OrderLinkClaim.__table__.c.so_number == SO_NUMBER,
            OrderLinkClaim.__table__.c.po_number == PO_NUMBER,
        )
    ).fetchall()
    companies = {str(r.company_id) for r in held}
    assert {first, second} <= companies, "each company must hold its own claim"


def test_one_company_still_cannot_hold_the_same_pairing_twice(db):
    """The other half. Widening the constraint must not turn it off.

    A duplicate here would mean the same pairing claimed twice by one company, and the
    resolver would report a phantom open link for ever.
    """
    from sqlalchemy.exc import IntegrityError

    only = _company(db)
    set_company_scope(db, frozenset({only}))
    _claim(db)

    with pytest.raises(IntegrityError):
        _claim(db)


def test_the_item_code_still_separates_two_claims_on_one_pairing(db):
    """A line-level claim and an order-level claim are different claims.

    `coalesce(item_code, '')` is what makes the NULL side collide with itself rather than
    inserting again on every re-upload; it must not also collide with a stated item.
    """
    only = _company(db)
    set_company_scope(db, frozenset({only}))

    _claim(db, item=None)
    _claim(db, item="CWB242")   # must not raise

    rows = db.query(OrderLinkClaim).filter(
        OrderLinkClaim.so_number == SO_NUMBER, OrderLinkClaim.po_number == PO_NUMBER
    ).all()
    assert {r.item_code for r in rows} == {None, "CWB242"}
