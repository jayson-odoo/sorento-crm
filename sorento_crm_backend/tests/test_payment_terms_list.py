"""QUOTE-TERMS-SELECT owner hand test (10 Nov): a read-only list page of the synced payment
terms. `GET /api/v1/master-data/payment-terms/` - DataGrid envelope, search, sort, gated by
`master_data.payment_terms.view`, scoped to the caller's companies. No write route exists.

Substrate: the item-class ingest suite's ``env`` fixture (blank scratch schema).
"""
from __future__ import annotations

from app.models.payment_term import PaymentTerm

from .test_ingest_item_classes import env  # noqa: F401  (env is a fixture)

LIST = "/api/v1/master-data/payment-terms/"


def _seed(env):
    rows = [
        PaymentTerm(company_id=env.company_a, term_code="CASH BEFORE DELIVERY", term_rule="C.O.D."),
        PaymentTerm(company_id=env.company_a, term_code="Net 30 days", term_rule="Net 0th Next 1 Month"),
        PaymentTerm(company_id=env.company_a, term_code="*Net 60 days", term_rule="Net 60 days", is_active=False),
        PaymentTerm(company_id=env.company_b, term_code="Cash", term_rule="C.O.D."),
    ]
    env.db.add_all(rows)
    env.db.commit()
    return rows


def test_the_list_shows_term_rule_company_and_active(env):
    _seed(env)
    response = env.client.get(LIST, params={"sort": "term_code", "dir": "asc"})
    assert response.status_code == 200, response.text
    body = response.json()
    by_term = {row["term_code"]: row for row in body["data"]}
    assert by_term["Net 30 days"]["term_rule"] == "Net 0th Next 1 Month"
    assert by_term["Net 30 days"]["company_code"] == env.company_a_code
    assert by_term["Net 30 days"]["is_active"] is True
    # Inactive terms are listed too (it is a view of the master, not the picker).
    assert by_term["*Net 60 days"]["is_active"] is False
    assert body["pagination"]["total"] == len(body["data"])
    assert set(by_term["Net 30 days"]) == {
        "id", "term_code", "term_rule", "company_code", "is_active", "updated_at",
    }


def test_search_matches_the_term_or_the_rule(env):
    _seed(env)
    by_rule = env.client.get(LIST, params={"query": "next 1 month"}).json()["data"]
    assert [row["term_code"] for row in by_rule] == ["Net 30 days"]
    by_term = env.client.get(LIST, params={"query": "cash before"}).json()["data"]
    assert [row["term_code"] for row in by_term] == ["CASH BEFORE DELIVERY"]


def test_sort_by_term_descending(env):
    _seed(env)
    rows = env.client.get(LIST, params={"sort": "term_code", "dir": "desc"}).json()["data"]
    codes = [row["term_code"] for row in rows]
    assert codes == sorted(codes, reverse=True)


def test_there_is_no_write_route(env):
    assert env.client.post(LIST, json={"term_code": "X"}).status_code in (404, 405)
