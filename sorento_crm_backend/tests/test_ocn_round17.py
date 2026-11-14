"""OCN-ORDER-CHANGE-NOTICE round 17 (crew re-pass on 4d8dbe72), pinned.

FAIL 1 (owner rule: every picker searchable): the notice's Customer Name picker called the
purchase request lookup, which the purchase-request own-scope guard refuses a `.view_own`
salesperson. The notice answers its own `GET /order-change-notices/lookups/customers`, the SAME
lookup function (`debtor_type.lookup_customers`), under the notice's create / edit rule and the
caller's company.

Postgres only, every row seeded.
"""
from __future__ import annotations

import uuid

from ._forms_chain_support import SORENTO, grant, user, world  # noqa: F401
from ._ocn_support import OCN, customer, ocn  # noqa: F401  (fixture)

LOOKUP = f"{OCN}/lookups/customers"


def _names(res):
    assert res.status_code == 200, res.text
    return [r["debtor_name"] for r in res.json()]


def test_r17_a_view_own_salesperson_searches_customers(ocn):
    tag = uuid.uuid4().hex[:6].upper()
    customer(ocn.db, name=f"ZZT {tag} Builders")
    ocn.db.commit()
    got = _names(ocn.as_(ocn.own).get(LOOKUP, params={"q": tag}))
    assert got == [f"ZZT {tag} Builders"]


def test_r17_no_notice_grant_is_refused(ocn):
    assert ocn.as_(ocn.stranger).get(LOOKUP, params={"q": "a"}).status_code == 403


def test_r17_a_reader_without_create_or_edit_is_refused(ocn):
    """The picker is for raising or editing a notice: `.view` alone does not open it."""
    assert ocn.as_(ocn.viewer).get(LOOKUP, params={"q": "a"}).status_code == 403


def test_r17_another_companys_customer_never_appears(ocn):
    from app.models.base import company_scope

    from ._sample_request_seed import second_company

    tag = uuid.uuid4().hex[:6].upper()
    other = second_company(ocn.db)
    with company_scope(ocn.db, None):
        customer(ocn.db, company_id=other, name=f"ZZT {tag} Foreign")
    customer(ocn.db, name=f"ZZT {tag} Local")
    ocn.db.commit()
    got = _names(ocn.as_(ocn.own).get(LOOKUP, params={"q": tag}))
    assert got == [f"ZZT {tag} Local"]
