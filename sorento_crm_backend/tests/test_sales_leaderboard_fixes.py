"""SALES-LEADERBOARD fix round 1: behaviour fixes and security gaps (reviewer / security-reviewer findings).

Uses the world helpers of `tests/test_sales_leaderboard.py`. Postgres only, every row seeded here.
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest

from app.services.company_scope import DEFAULT_COMPANY_ID

from tests._mc_lookup_seed import MOCHA_ID
from tests._sales_unified_seed import cust
from tests.test_sales_leaderboard import (  # noqa: F401  (db is a fixture)
    LB,
    OPTIONS,
    ROUTE,
    _agent,
    _board,
    _get,
    _sale,
    db,
    make_client,
)
from tests._pg_fixture import unique_code


def test_the_same_code_as_two_persons_in_two_companies_shows_the_code_on_both_rows(db):
    s = unique_code("X", alpha=True)[-8:]
    code = f"ZZT-X-{s}"
    a, b = f"ZZTPERSONA {s}", f"ZZTPERSONB {s}"
    ax = _agent(db, code, person=a, company_id=DEFAULT_COMPANY_ID)
    bx = _agent(db, code, person=b, company_id=MOCHA_ID)
    _sale(db, "invoice", "300.00", date(2026, 10, 5), agent=ax, customer=cust(db))
    _sale(db, "invoice", "200.00", date(2026, 10, 6), agent=bx, customer=cust(db, company_id=MOCHA_ID),
          company=MOCHA_ID)
    db.commit()
    with make_client(db) as client:
        rows = {r["person"]: r for r in _board(client)["rows"]}
    assert rows[a]["codes"] == [code]
    assert rows[b]["codes"] == [code]


def test_options_without_the_permission_is_403(db):
    with make_client(db, allow=("sales.reports.view",)) as client:
        assert client.get(OPTIONS).status_code == 403


@pytest.mark.parametrize("param", ["brand", "category"])
def test_a_non_uuid_brand_or_category_is_422(db, param):
    with make_client(db) as client:
        resp = _get(client, **{param: "not-a-uuid"})
    assert resp.status_code == 422, resp.text
    assert resp.json().get("code") == "REPORT_INVALID_PARAMS"


def test_a_person_label_padded_with_spaces_still_marks_me(db):
    from app.models.access import RespondContact

    s = unique_code("P", alpha=True)[-8:]
    name = f"ZZTPAD {s}"
    agent = _agent(db, f"ZZT-P-{s}", person=name, company_id=DEFAULT_COMPANY_ID)
    contact = RespondContact(id=str(uuid.uuid4()), respond_io_id=unique_code("C"),
                             phone_number=f"+6010{uuid.uuid4().hex[:7]}", name="ZZT Pad")
    db.add(contact)
    db.flush()
    agent.contact_id = contact.id
    _sale(db, "invoice", "50.00", date(2026, 10, 5), agent=agent, customer=cust(db))
    db.commit()
    with make_client(db, contact=contact) as client:
        body = _board(client)
    assert body["me"] is not None and body["me"]["person"] == name
