"""SALES-LEADERBOARD security gap: a customer-scoped (dealer) contact may not group the ask by sales person."""
from __future__ import annotations

from tests.test_report_ask_account_type import (  # noqa: F401  (client / db are fixtures)
    PERIOD,
    _anchors,
    _ask,
    _code,
    _dealer,
    _ledger,
    _sale,
    client,
    db,
)


def test_a_customer_scoped_contact_is_refused_group_by_sales_person(client, db):
    _anchors(db)
    own = _ledger(db, "IV", "CABANA")
    _sale(db, "invoiced", own, "100.00")
    db.commit()
    resp = _ask(client, _dealer(db, own), group_by="sales_person", top_n=5, period=PERIOD)
    assert resp.status_code == 403, resp.text
    assert _code(resp) == "report_dimension_not_allowed", resp.text
