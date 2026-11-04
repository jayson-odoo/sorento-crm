"""Target commission view + commission statement (lane TARGET-COMMISSION-VIEW).
Plan: documentation/plans/sales/PLAN-target-commission-view-04nov.md (UAC alongside).

The statement is the screen's own computation (`target_service.target_detail`) plus the
documents behind each period's "Achieved" and the tier table used, so a stakeholder checks the
same numbers the owner sees. Seeds and fixtures are the S1 file's; today is 20 Oct 2026.
"""
from __future__ import annotations

import io
from datetime import date
from decimal import Decimal

from openpyxl import load_workbook

from .test_dealer_targets_api import _customer, _dealer_body, _period, _product_id, _sale
from .test_sales_targets_s1 import (  # noqa: F401  (fixtures)
    BASE,
    TODAY,
    _agent,
    _client,
    _do_line,
    _restore,
    _uid,
    _so_line,
    _warehouse,
    api,
    world,
)

STATEMENT = f"{BASE}/commission-statement"


def _tgt8(client, db, company_id):
    """TGT-000008 in miniature: one account, quarterly, own tiers per period, highest tier pays.
    Q1 6% from 60,000 (8% from 72,000); Q2 5% from 60,000; Q3 not reached; Q4 current."""
    pid = _product_id(db, company_id)
    a = _customer(db, company_id, "ZZT A CRAFT IDEA SDN BHD", level=1)
    so1, _ = _sale(db, company_id, a, "18220.50", date(2026, 1, 8), product_id=pid)
    so2, _ = _sale(db, company_id, a, "25004.00", date(2026, 2, 14), product_id=pid)
    so3, _ = _sale(db, company_id, a, "18127.14", date(2026, 3, 21), product_id=pid)
    _sale(db, company_id, a, "64740.40", date(2026, 5, 2), product_id=pid)
    _sale(db, company_id, a, "23460.00", date(2026, 8, 9), product_id=pid)
    _sale(db, company_id, a, "1235.58", date(2026, 10, 2), product_id=pid)
    # Not counted: cancelled.
    _sale(db, company_id, a, "99999.00", date(2026, 1, 9), product_id=pid, status="cancelled")
    tiers = [
        {"period_start": "2026-01-01", "threshold": 60000, "rate": 6},
        {"period_start": "2026-01-01", "threshold": 72000, "rate": 8},
        {"period_start": "2026-04-01", "threshold": 60000, "rate": 5},
        {"period_start": "2026-07-01", "threshold": 60000, "rate": 5},
        {"period_start": "2026-10-01", "threshold": 60000, "rate": 5},
    ]
    res = client.post(BASE, json=_dealer_body([a], payout_customer_id=a.id, tiers=tiers))
    assert res.status_code == 201, res.text
    return res.json(), a, (so1, so2, so3)


# --------------------------------------------------------------------------------------- #
# the screen: tier rate per period, earned to date, current so far
# --------------------------------------------------------------------------------------- #


def test_detail_carries_rate_of_tier_reached_and_earned_to_date(api):
    client, db, company_id = api
    body, a, _ = _tgt8(client, db, company_id)
    q1, q2, q3, q4 = (_period(body, d) for d in ("2026-01-01", "2026-04-01", "2026-07-01", "2026-10-01"))
    assert q1["achieved_value"] == 61351.64
    assert q1["tier_reached"] == 1
    assert q1["tier_rates"] == [{"label": None, "rate": 6.0}]
    assert q1["commission_earned"] == 3681.10
    assert q2["tier_rates"] == [{"label": None, "rate": 5.0}]
    assert q2["commission_earned"] == 3237.02
    assert q3["tier_reached"] is None and q3["tier_rates"] == []
    assert q4["is_current"] is True
    # Earned to date: ended periods only (Q1 + Q2 + Q3 0), the current one apart.
    assert body["commission_to_date"] == 6918.12
    assert body["commission_current"] == 0
    assert body["payout_account"]["code"] == a.customer_code


def test_tier_selection_highest_tier_sets_the_rate(api):
    client, db, company_id = api
    pid = _product_id(db, company_id)
    a = _customer(db, company_id, "ZZT HIGH", level=1)
    _sale(db, company_id, a, "75000", date(2026, 2, 1), product_id=pid)
    res = client.post(BASE, json=_dealer_body([a], tiers=[
        {"period_start": "2026-01-01", "threshold": 60000, "rate": 6},
        {"period_start": "2026-01-01", "threshold": 72000, "rate": 8},
    ]))
    q1 = _period(res.json(), "2026-01-01")
    assert q1["tier_reached"] == 2
    assert q1["tier_rates"] == [{"label": None, "rate": 8.0}]
    assert q1["commission_earned"] == 6000.0


def test_per_account_rates_are_labelled(api):
    client, db, company_id = api
    pid = _product_id(db, company_id)
    a1 = _customer(db, company_id, "ZZT R1", level=1)
    a3 = _customer(db, company_id, "ZZT R3", level=3)
    _sale(db, company_id, a1, "50000", date(2026, 2, 1), product_id=pid)
    res = client.post(BASE, json=_dealer_body([a1, a3], tiers=[
        {"period_start": "2026-01-01", "threshold": 40000,
         "account_rates": [{"customer_id": a1.id, "rate": 2}, {"customer_id": a3.id, "rate": 3}]},
    ]))
    q1 = _period(res.json(), "2026-01-01")
    assert q1["tier_rates"] == [{"label": "A/C I", "rate": 2.0}, {"label": "A/C III", "rate": 3.0}]


def test_no_commission_method_has_no_earned_to_date(api):
    client, db, company_id = api
    a = _customer(db, company_id, "ZZT NONE", level=1)
    body = client.post(BASE, json=_dealer_body([a])).json()
    assert body["commission_to_date"] is None
    assert body["commission_current"] is None


# --------------------------------------------------------------------------------------- #
# the statement: one computation with the screen
# --------------------------------------------------------------------------------------- #


def test_statement_totals_equal_screen_totals_equal_documents(api):
    from app.services.sales import target_service

    client, db, company_id = api
    body, a, (so1, so2, so3) = _tgt8(client, db, company_id)
    target = target_service.get_target_or_404(db, body["id"])
    [statement] = target_service.commission_statements(db, [target], on=TODAY)
    screen = client.get(f"{BASE}/{body['id']}").json()

    assert statement["commission_to_date"] == screen["commission_to_date"] == 6918.12
    for mine, theirs in zip(statement["periods"], screen["periods"]):
        for key in ("achieved_value", "achieved_pct", "commission_earned", "bonus_earned", "tier_reached", "tier_rates"):
            assert mine[key] == theirs[key], key
        # The documents add up to Achieved, to the cent.
        total = sum((Decimal(str(d["amount"])) for d in mine["documents"]), Decimal("0"))
        assert total == Decimal(str(mine["achieved_value"])), mine["period_start"]

    q1 = statement["periods"][0]
    assert [(d["doc_no"], d["doc_date"], d["account_code"], d["amount"]) for d in q1["documents"]] == [
        (so1.so_number, date(2026, 1, 8), a.customer_code, 18220.50),
        (so2.so_number, date(2026, 2, 14), a.customer_code, 25004.00),
        (so3.so_number, date(2026, 3, 21), a.customer_code, 18127.14),
    ]
    # The tier table used: the period's own tiers, the reached one marked.
    assert [(t["tier"], t["threshold_rm"], t["rates"], t["reached"]) for t in q1["tier_table"]] == [
        (1, 60000.0, [{"label": None, "rate": 6.0}], True),
        (2, 72000.0, [{"label": None, "rate": 8.0}], False),
    ]


def test_statement_documents_follow_the_delivered_basis_by_do_date(api):
    """A Delivered target counts the DO-dated part of a line in the DO's period: the documents
    of each period still add up to that period's Achieved."""
    from app.services.sales import target_service

    client, db, company_id = api
    pid = _product_id(db, company_id)
    wh = _warehouse(db, company_id)
    a = _customer(db, company_id, "ZZT DELIV", level=1)
    so, line = _so_line(
        db, company_id, customer_id=a.id, order_date=date(2026, 3, 20), line_total=Decimal("1000"),
        product_id=pid, qty_ordered=10, qty_delivered=10,
    )
    _do_line(db, company_id, pid, wh.id, line.id, quantity=4, order_date=date(2026, 3, 25))
    _do_line(db, company_id, pid, wh.id, line.id, quantity=6, order_date=date(2026, 4, 5))
    res = client.post(BASE, json=_dealer_body([a], basis="delivered", tiers=[
        {"period_start": "2026-01-01", "threshold": 100, "rate": 1},
    ]))
    assert res.status_code == 201, res.text
    target = target_service.get_target_or_404(db, res.json()["id"])
    [statement] = target_service.commission_statements(db, [target], on=TODAY)
    q1, q2 = statement["periods"][0], statement["periods"][1]
    assert q1["achieved_value"] == 400 and q2["achieved_value"] == 600
    assert [(d["doc_no"], d["amount"]) for d in q1["documents"]] == [(so.so_number, 400.0)]
    assert [(d["doc_no"], d["amount"]) for d in q2["documents"]] == [(so.so_number, 600.0)]


def test_statement_works_for_an_agent_target(api):
    from app.services.sales import target_service

    client, db, company_id = api
    pid = _product_id(db, company_id)
    agent = _agent(db, "STMT")
    so, _ = _so_line(db, company_id, agent_id=agent.id, order_date=date(2026, 2, 3),
                     line_total=Decimal("500"), product_id=pid)
    res = client.post(BASE, json={
        "subject_kind": "agent", "sales_agent_id": agent.id, "name": "ZZT agent stmt",
        "metric": "amount", "basis": "ordered", "product_scope": "all",
        "start_date": "2026-01-01", "end_date": "2026-03-31", "target_value": 1000,
    })
    assert res.status_code == 201, res.text
    target = target_service.get_target_or_404(db, res.json()["id"])
    [statement] = target_service.commission_statements(db, [target], on=TODAY)
    assert [(d["doc_no"], d["amount"]) for d in statement["periods"][0]["documents"]] == [(so.so_number, 500.0)]


# --------------------------------------------------------------------------------------- #
# the export: xlsx, one or many targets
# --------------------------------------------------------------------------------------- #


class _NoCloseSession:
    """The task's own `SessionLocal()` reuses the test's session (it cannot see uncommitted
    seed data otherwise); the test owns its lifetime. Shape of tests/test_oi_export_async.py."""

    def __init__(self, inner):
        self._inner = inner

    def close(self):
        return None

    def __getattr__(self, name):
        return getattr(self._inner, name)


def _values(ws):
    return [[c for c in row] for row in ws.iter_rows(values_only=True)]


def _export(client, db, monkeypatch, ids, expect=200):
    """The statement through My Downloads (owner hand test, 4 Nov): the POST creates a
    `user_downloads` row and enqueues the render; the RQ task (run here inline) stores the file
    and marks the row ready. Returns `(workbook, download row, POST body)`."""
    from app.services import queue_service
    from app.services.download_service import DownloadService
    from app.tasks import export_tasks

    queued = []

    def _fake_enqueue(func, *args, **kwargs):
        queued.append((func, args, kwargs))

        class _Job:
            id = "fake-job"

        return _Job()

    monkeypatch.setattr(queue_service, "enqueue_job", _fake_enqueue)
    res = client.post(STATEMENT, json={"ids": ids})
    assert res.status_code == expect, res.text
    if expect != 200:
        return None, None, res
    body = res.json()
    assert body["kind"] == "commission_statement_xlsx" and body["status"] == "pending", body
    [(func, args, kwargs)] = queued
    assert func is export_tasks.generate_commission_statement_xlsx
    assert kwargs.get("queue_name") == "imports"

    stored = {}

    class _FakeBackend:
        def upload_file(self, *, file_content, file_path, content_type):
            stored.update(bytes=file_content, key=file_path, content_type=content_type)
            return (file_path, None)

    monkeypatch.setattr(export_tasks, "SessionLocal", lambda: _NoCloseSession(db))
    monkeypatch.setattr(export_tasks, "default_provider", lambda: "s3")
    monkeypatch.setattr(export_tasks, "get_backend", lambda provider: _FakeBackend())
    task_kwargs = {k: v for k, v in kwargs.items() if k not in ("queue_name", "job_timeout")}
    result = func(*args, **task_kwargs)
    assert result["status"] == "ready", result

    row = DownloadService(db).get(body["id"])
    assert row.status == "ready" and row.storage_key == stored["key"]
    assert row.filename == body["filename"]
    assert stored["content_type"].startswith("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    return load_workbook(io.BytesIO(stored["bytes"])), row, body


def test_statement_export_goes_through_my_downloads(api, monkeypatch):
    """The download is a My Downloads job: the row is the user's, tied to the target, named as
    before, and listed by GET /downloads once ready."""
    import re

    client, db, company_id = api
    body, _a, _ = _tgt8(client, db, company_id)
    _wb, row, posted = _export(client, db, monkeypatch, [body["id"]])
    assert re.fullmatch(rf"commission-statement-{body['target_no']}-\d{{8}}\.xlsx", row.filename), row.filename
    assert (row.source_entity_type, str(row.source_entity_id)) == ("sales_target", body["id"])
    listed = client.get("/api/v1/downloads").json()["downloads"]
    mine = next(d for d in listed if d["id"] == posted["id"])
    assert (mine["status"], mine["filename"], mine["kind"]) == ("ready", row.filename, "commission_statement_xlsx")


def test_statement_xlsx_one_target(api, monkeypatch):
    client, db, company_id = api
    body, a, (so1, _so2, _so3) = _tgt8(client, db, company_id)
    wb, _row, _ = _export(client, db, monkeypatch, [body["id"]])
    assert wb.sheetnames[0] == "Summary"
    summary = _values(wb["Summary"])
    row = next(r for r in summary if body["target_no"] in r)
    assert 6918.12 in row
    ws = wb[body["target_no"]]
    rows = _values(ws)
    flat = [v for r in rows for v in r if v is not None]
    assert so1.so_number in flat
    assert 61351.64 in flat and 3681.10 in flat
    assert any(isinstance(v, str) and a.customer_code in v for v in flat)
    # Dates are real dates shown dd/mm/yyyy; money cells show 2 decimals.
    date_cells = [c for r in ws.iter_rows() for c in r if c.value is not None and hasattr(c.value, "year")]
    assert date_cells and all(c.number_format == "dd/mm/yyyy" for c in date_cells)
    money = next(c for r in ws.iter_rows() for c in r if c.value == 61351.64)
    assert money.number_format == "#,##0.00"


def test_statement_xlsx_many_targets_one_file(api, monkeypatch):
    import re

    client, db, company_id = api
    first, _a, _ = _tgt8(client, db, company_id)
    other = _customer(db, company_id, "ZZT OTHER DEALER", level=1)
    second = client.post(BASE, json=_dealer_body([other])).json()
    wb, row, _ = _export(client, db, monkeypatch, [first["id"], second["id"]])
    assert wb.sheetnames == ["Summary", first["target_no"], second["target_no"]]
    assert re.fullmatch(r"commission-statement-2-targets-\d{8}\.xlsx", row.filename), row.filename
    assert row.source_entity_type is None


def test_statement_refuses_none_and_too_many_before_any_download_row(api, monkeypatch):
    from sqlalchemy import text

    client, db, company_id = api
    before = db.execute(text("select count(*) from user_downloads")).scalar()
    _export(client, db, monkeypatch, [], expect=422)
    ids = ["00000000-0000-4000-8000-%012d" % i for i in range(51)]
    _export(client, db, monkeypatch, ids, expect=422)
    assert db.execute(text("select count(*) from user_downloads")).scalar() == before


def test_statement_unknown_target_is_404(api, monkeypatch):
    client, db, company_id = api
    _export(client, db, monkeypatch, ["00000000-0000-4000-8000-000000000001"], expect=404)


def test_statement_needs_view_permission(world):
    db, company_id = world
    client, originals = _client(db, [])
    try:
        res = client.post(STATEMENT, json={"ids": ["00000000-0000-4000-8000-000000000001"]})
        assert res.status_code == 403
    finally:
        _restore(originals)


# --------------------------------------------------------------------------------------- #
# review round 1: kill tests the first set let through, and company scope
# --------------------------------------------------------------------------------------- #


def test_earned_to_date_counts_ended_periods_only_current_apart(api):
    """A period ending the day before `on` is ended; the current period's own commission is
    `commission_current`, never part of `commission_to_date`."""
    from app.services.sales import target_service

    client, db, company_id = api
    pid = _product_id(db, company_id)
    a = _customer(db, company_id, "ZZT EARNED", level=1)
    _sale(db, company_id, a, "1000", date(2026, 9, 10), product_id=pid)   # Sep, ended
    _sale(db, company_id, a, "2000", date(2026, 10, 5), product_id=pid)   # Oct, current
    _sale(db, company_id, a, "4000", date(2026, 11, 5), product_id=pid)   # Nov, future to `on`
    res = client.post(BASE, json=_dealer_body(
        [a], start_date="2026-09-01", end_date="2026-11-30", split_every=1,
        tiers=[{"period_start": s, "threshold": 500, "rate": 10}
               for s in ("2026-09-01", "2026-10-01", "2026-11-01")],
    ))
    assert res.status_code == 201, res.text
    target = target_service.get_target_or_404(db, res.json()["id"])
    # On 1 Oct, September (ended 30 Sep, the day before) is earned; October is current.
    detail = target_service.target_detail(db, target, on=date(2026, 10, 1))
    assert detail["commission_to_date"] == 100.0
    assert detail["commission_current"] == 200.0
    # On TODAY (20 Oct) the same; November has not ended and is not current.
    detail = target_service.target_detail(db, target, on=TODAY)
    assert (detail["commission_to_date"], detail["commission_current"]) == (100.0, 200.0)


def test_statement_has_one_row_per_sales_order_not_per_line(api):
    from app.models.order import SalesOrderLine
    from app.services.sales import target_service

    client, db, company_id = api
    pid = _product_id(db, company_id)
    a = _customer(db, company_id, "ZZT TWO LINES", level=1)
    so, _ = _sale(db, company_id, a, "100.25", date(2026, 2, 3), product_id=pid)
    db.add(SalesOrderLine(
        id=_uid(), company_id=company_id, sales_order_id=so.id, product_id=pid,
        qty_ordered=1, qty_delivered=1, line_total=Decimal("200.50"), line_status="open",
    ))
    db.flush()
    res = client.post(BASE, json=_dealer_body([a], tiers=[{"period_start": "2026-01-01", "threshold": 100, "rate": 1}]))
    target = target_service.get_target_or_404(db, res.json()["id"])
    [statement] = target_service.commission_statements(db, [target], on=TODAY)
    assert [(d["doc_no"], d["amount"]) for d in statement["periods"][0]["documents"]] == [(so.so_number, 300.75)]


def test_tier_table_marks_every_tier_up_to_the_one_reached(api):
    from app.services.sales import target_service

    client, db, company_id = api
    pid = _product_id(db, company_id)
    a = _customer(db, company_id, "ZZT THREE TIERS", level=1)
    _sale(db, company_id, a, "75000", date(2026, 2, 1), product_id=pid)
    res = client.post(BASE, json=_dealer_body([a], tiers=[
        {"period_start": "2026-01-01", "threshold": 60000, "rate": 6},
        {"period_start": "2026-01-01", "threshold": 72000, "rate": 8},
        {"period_start": "2026-01-01", "threshold": 90000, "rate": 10},
    ]))
    target = target_service.get_target_or_404(db, res.json()["id"])
    [statement] = target_service.commission_statements(db, [target], on=TODAY)
    q1 = statement["periods"][0]
    assert q1["tier_reached"] == 2
    assert [(t["tier"], t["reached"]) for t in q1["tier_table"]] == [(1, True), (2, True), (3, False)]


def test_statement_documents_respect_the_product_scope(api):
    from app.services.sales import target_service

    from .test_sales_targets_s1 import _category, _product

    client, db, company_id = api
    cat = _category(db, company_id)
    inside = _product(db, company_id, cat.id).id
    outside = _product_id(db, company_id)
    a = _customer(db, company_id, "ZZT SCOPED", level=1)
    so_in, _ = _sale(db, company_id, a, "700", date(2026, 2, 1), product_id=inside)
    _sale(db, company_id, a, "900", date(2026, 2, 2), product_id=outside)
    res = client.post(BASE, json=_dealer_body(
        [a], product_scope="categories", category_ids=[cat.id],
        tiers=[{"period_start": "2026-01-01", "threshold": 100, "rate": 1}],
    ))
    assert res.status_code == 201, res.text
    target = target_service.get_target_or_404(db, res.json()["id"])
    [statement] = target_service.commission_statements(db, [target], on=TODAY)
    q1 = statement["periods"][0]
    assert q1["achieved_value"] == 700
    assert [(d["doc_no"], d["amount"]) for d in q1["documents"]] == [(so_in.so_number, 700.0)]


def test_statement_of_another_company_s_target_is_404(api, monkeypatch):
    from app.models.base import company_scope

    client, db, company_id = api
    from app.models.company import Company

    other = _uid()
    db.add(Company(id=other, name="ZZT Other Co", code=f"Z{_uid()[:8]}"))
    db.flush()
    with company_scope(db, frozenset({other})):
        theirs_account = _customer(db, other, "ZZT THEIRS", level=1)
        theirs = client.post(BASE, json=_dealer_body([theirs_account]))
        assert theirs.status_code == 201, theirs.text
    _export(client, db, monkeypatch, [theirs.json()["id"]], expect=404)


def test_statement_cells_never_start_a_formula(api, monkeypatch):
    """A name typed by staff or synced from AutoCount is text in the workbook, never a live
    formula in a file sent to stakeholders."""
    client, db, company_id = api
    a = _customer(db, company_id, "=HYPERLINK(\"http://x\",\"Open\")", level=1)
    body = client.post(BASE, json=_dealer_body([a], name="=1+1 quarterly")).json()
    wb, _row, _ = _export(client, db, monkeypatch, [body["id"]])
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for cell in row:
                assert cell.data_type != "f", (ws.title, cell.coordinate, cell.value)
    summary = _values(wb["Summary"])
    assert any("=1+1 quarterly" in row for row in summary)
