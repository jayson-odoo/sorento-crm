"""REPORT-SMART-1021 step 4 (stretch): `compare_to` on the report ask.

`compare_to=previous_period` compares with the same number of days just before the period;
`last_year` with the same dates one year earlier. Every row and the total carry the earlier
figures (`prev`) and the change on the sort measure in percent (`change_pct`, None when the
earlier figure is zero). The ranking is the period's own; the earlier window never adds rows.

    agent  product  September      August       Sep 2025
    A1     P1       1000 / 10      500 / 5      800 / 8
    A2     P1        600 / 6       -            -
    A3     P1        -             900 / 9      -
"""
from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from app.services.company_scope import DEFAULT_COMPANY_ID
from tests._pg_fixture import unique_code
from tests._sales_report_do_seed import (  # noqa: F401  (client / db are fixtures)
    client,
    db,
    seed_agent,
    seed_customer,
    warehouse,
)
from tests.test_report_ask_route import AUG, SEP, _ask, _full, _ok, _prod, _sale


def _world(db):
    w = SimpleNamespace()
    w.cust = seed_customer(db, name=unique_code("Cmp"))
    w.wh = warehouse(db, company_id=DEFAULT_COMPANY_ID, code=unique_code("WH"))
    w.p1 = _prod(db, "ZZTCMP-1")
    w.a1, w.a2, w.a3 = (seed_agent(db, code=f"ZZT-CMP-{n}") for n in "123")
    kw = dict(cust=w.cust, wh=w.wh, prod=w.p1)
    _sale(db, agent=w.a1, qty=10, total="1000.00", when=SEP, **kw)
    _sale(db, agent=w.a2, qty=6, total="600.00", when=SEP, **kw)
    _sale(db, agent=w.a1, qty=5, total="500.00", when=AUG, **kw)
    _sale(db, agent=w.a3, qty=9, total="900.00", when=AUG, **kw)
    _sale(db, agent=w.a1, qty=8, total="800.00", when=date(2025, 9, 10), **kw)
    db.commit()
    return w


def test_previous_period_is_the_same_length_just_before(client, db):
    _world(db)
    body = _ok(client, _full(db), group_by="sales_agent", top_n=10, product_code="ZZTCMP", compare_to="previous_period")
    assert body["compare_to"] == "previous_period", body
    assert body["compare_from"] == "2026-08-02" and body["compare_until"] == "2026-08-31", body  # 30 days back
    rows = {r["name"]: r for r in body["rows"]}
    assert set(rows) == {"ZZT-CMP-1", "ZZT-CMP-2"}, rows  # A3 sold only in August: not a row
    assert rows["ZZT-CMP-1"]["prev"]["amount"] == 500.0 and rows["ZZT-CMP-1"]["change_pct"] == 100.0, rows
    assert rows["ZZT-CMP-2"]["prev"]["amount"] == 0.0 and rows["ZZT-CMP-2"]["change_pct"] is None, rows
    assert body["total"]["prev"]["amount"] == 1400.0, body["total"]
    assert round(body["total"]["change_pct"], 1) == 14.3, body["total"]


def test_last_year_is_the_same_dates_a_year_earlier(client, db):
    _world(db)
    body = _ok(client, _full(db), product_code="ZZTCMP", compare_to="last_year", measure="qty")
    assert body["compare_from"] == "2025-09-01" and body["compare_until"] == "2025-09-30", body
    assert body["total"]["qty"] == 16 and body["total"]["prev"]["qty"] == 8, body["total"]
    assert body["total"]["change_pct"] == 100.0, body["total"]  # on the sort measure (qty)


def test_no_compare_carries_nothing(client, db):
    _world(db)
    body = _ok(client, _full(db), group_by="sales_agent", top_n=10, product_code="ZZTCMP")
    # Review S3: the keys are ABSENT, so the body is what every caller read before.
    for key in ("compare_to", "compare_from", "compare_until"):
        assert key not in body, body
    assert not {"prev", "change_pct", "count"} & set(body["total"]), body["total"]
    assert body["rows"] and all(not {"prev", "change_pct", "count"} & set(r) for r in body["rows"]), body["rows"]


def test_an_unknown_compare_is_refused(client, db):
    resp = _ask(client, _full(db), compare_to="last_week")
    assert resp.status_code == 422 and resp.json().get("code") == "unknown_compare_to", resp.text


def test_a_month_breakdown_is_never_compared_month_against_unmatched_month(client, db):
    """Review S1: month rows are named by month, so the earlier window's months never match; refused."""
    _world(db)
    resp = _ask(client, _full(db), group_by="month", top_n=12, product_code="ZZTCMP", compare_to="last_year")
    assert resp.status_code == 422 and resp.json().get("code") == "compare_by_month", resp.text
