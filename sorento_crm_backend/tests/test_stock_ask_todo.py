"""Sales asks as a to-do list (lane SALES-ASKS-TODO), service level: AC-ST103 to AC-ST110.

`app.services.stock_ask_service` (todo_for_agent, _apply_update, today_start_utc). Postgres
only (`blank_session`), every test seeds its own agents, customers and asks.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.models.base import company_scope

from . import _ask_todo_seed as seed
from ._ask_todo_seed import NOW, SORENTO, TODAY_START
from ._pg_fixture import blank_session


@pytest.fixture
def w():
    with blank_session() as db:
        with company_scope(db, frozenset({SORENTO})):
            world = seed.world(db)
            world["db"] = db
            yield world


def _svc():
    from app.services import stock_ask_service

    return stock_ask_service


# ---- AC-ST103 ---------------------------------------------------------------------------


def test_apply_update_stamps_done_and_clears_on_reopen(w):
    svc, db = _svc(), w["db"]
    row = seed.ask(db, w["x"], w["dealer"], "SRT-103")

    svc._apply_update(db, row, {"note": "x"}, actor="Sean", now=NOW)
    assert (row.done_at, row.done_by) == (None, None)

    svc._apply_update(db, row, {"state": "done"}, actor="Sean", now=NOW)
    assert row.done_at == NOW
    assert row.done_by == "Sean"

    later = NOW + timedelta(hours=2)
    svc._apply_update(db, row, {"state": "done"}, actor="Someone Else", now=later)
    assert (row.done_at, row.done_by) == (NOW, "Sean")

    svc._apply_update(db, row, {"note": "y"}, actor="Someone Else", now=later)
    assert (row.done_at, row.done_by) == (NOW, "Sean")
    assert row.note == "y"

    svc._apply_update(db, row, {"state": "open"}, actor="Sean", now=later)
    assert (row.state, row.done_at, row.done_by) == ("open", None, None)


def test_public_update_functions_take_an_actor_and_stamp(w):
    svc, db = _svc(), w["db"]
    a1 = seed.ask(db, w["x"], w["dealer"], "SRT-C")
    a2 = seed.ask(db, w["x"], w["dealer"], "SRT-A")
    by_customer = svc.update_for_customer(db, w["x"].id, a1.id, {"state": "done"}, actor="Office Olive")
    by_agent = svc.update_for_agent(db, w["a"].id, a2.id, {"state": "done"}, actor="Agent Alpha")
    assert by_customer.done_by == "Office Olive" and by_customer.done_at is not None
    assert by_agent.done_by == "Agent Alpha" and by_agent.done_at is not None


# ---- AC-ST104 ---------------------------------------------------------------------------


def test_response_carries_done_fields(w):
    svc, db = _svc(), w["db"]
    row = seed.ask(db, w["x"], w["dealer"], "SRT-104")
    svc._apply_update(db, row, {"state": "done"}, actor="Sean", now=NOW)
    dumped = svc.serialize(db, [row])[0].model_dump()
    assert "done_at" in dumped and "done_by" in dumped
    assert dumped["done_by"] == "Sean"
    assert dumped["done_at"] == NOW
    assert dumped.get("agent_code", "missing") is None


# ---- AC-ST105 / 106 ---------------------------------------------------------------------


def test_todo_scope_is_my_customers_only(w):
    svc, db = _svc(), w["db"]
    ax = seed.ask(db, w["x"], w["dealer"], "SRT-X")
    ay = seed.ask(db, w["y"], w["dealer"], "SRT-Y")
    seed.ask(db, w["z"], w["dealer"], "SRT-Z")
    seed.ask(db, None, w["dealer"], "SRT-NOCUST")
    seed.ask(db, w["x"], w["dealer"], "SRT-DONE", state="done", done_at=NOW)
    out = svc.todo_for_agent(db, w["a"].id, now=NOW)
    assert {r.id for r in out["open"]} == {ax.id, ay.id}


def test_todo_excludes_incoming_branch(w):
    svc, db = _svc(), w["db"]
    kept = [seed.ask(db, w["x"], w["dealer"], f"SRT-{b}", branch=b) for b in ("too_big", "in_stock", "no_incoming")]
    seed.ask(db, w["x"], w["dealer"], "SRT-INC", branch="incoming")
    out = svc.todo_for_agent(db, w["a"].id, now=NOW)
    assert {r.id for r in out["open"]} == {r.id for r in kept}
    assert svc.TODO_BRANCHES == frozenset({"too_big", "in_stock", "no_incoming"})


# ---- AC-ST107 ---------------------------------------------------------------------------


def test_todo_ordering(w):
    svc, db = _svc(), w["db"]
    t = NOW - timedelta(days=1)
    newest = seed.ask(db, w["x"], w["dealer"], "N", created_at=NOW - timedelta(minutes=5))
    tie_b = seed.ask(db, w["x"], w["dealer"], "TB", created_at=t, id="00000000-0000-0000-0000-00000000000b")
    tie_a = seed.ask(db, w["x"], w["dealer"], "TA", created_at=t, id="00000000-0000-0000-0000-00000000000a")
    oldest = seed.ask(db, w["y"], w["dealer"], "O", created_at=NOW - timedelta(days=5))
    d1 = seed.ask(db, w["x"], w["dealer"], "D1", state="done", done_at=NOW - timedelta(hours=2))
    d2 = seed.ask(db, w["x"], w["dealer"], "D2", state="done", done_at=NOW - timedelta(minutes=10))
    out = svc.todo_for_agent(db, w["a"].id, now=NOW)
    assert [r.id for r in out["open"]] == [oldest.id, tie_a.id, tie_b.id, newest.id]
    assert [r.id for r in out["done_today"]] == [d2.id, d1.id]


# ---- AC-ST108 ---------------------------------------------------------------------------


def test_today_start_is_malaysia_midnight_utc(w):
    svc, db = _svc(), w["db"]
    assert svc.today_start_utc(datetime(2026, 9, 29, 3, 0)) == datetime(2026, 9, 28, 16, 0)
    assert svc.today_start_utc(datetime(2026, 9, 28, 15, 59)) == datetime(2026, 9, 27, 16, 0)
    assert svc.todo_for_agent(db, w["a"].id, now=NOW)["today_start"] == TODAY_START
    assert svc.todo_for_agent(db, w["a"].id, now=datetime(2026, 9, 28, 15, 59))["today_start"] == datetime(
        2026, 9, 27, 16, 0
    )


# ---- AC-ST109 ---------------------------------------------------------------------------


def test_done_today_window(w):
    svc, db = _svc(), w["db"]
    at_start = seed.ask(db, w["x"], w["dealer"], "AT", state="done", done_at=TODAY_START)
    seed.ask(db, w["x"], w["dealer"], "BEFORE", state="done", done_at=TODAY_START - timedelta(seconds=1))
    reopened = seed.ask(db, w["x"], w["dealer"], "REOPEN", state="open", done_at=None)
    seed.ask(db, w["z"], w["dealer"], "OTHER", state="done", done_at=NOW)
    out = svc.todo_for_agent(db, w["a"].id, now=NOW)
    assert [r.id for r in out["done_today"]] == [at_start.id]
    assert reopened.id in {r.id for r in out["open"]}


# ---- AC-ST110 ---------------------------------------------------------------------------


def _bulk(db, w, n):
    base = NOW - timedelta(days=30)
    rows = [
        seed.StockAsk(
            id=seed.uid(),
            company_id=SORENTO,
            customer_id=w["x"].id,
            contact_id=w["dealer"],
            product_code=f"SRT-{i}",
            quantity=1,
            branch="in_stock",
            answer_summary="a",
            created_at=base + timedelta(minutes=i),
        )
        for i in range(n)
    ]
    db.add_all(rows)
    db.flush()
    return rows


def test_todo_cap_500_and_truncated_flag(w):
    svc, db = _svc(), w["db"]
    assert svc.TODO_CAP == 500
    rows = _bulk(db, w, 501)
    out = svc.todo_for_agent(db, w["a"].id, now=NOW)
    assert len(out["open"]) == 500
    assert out["truncated"] is True
    assert rows[-1].id not in {r.id for r in out["open"]}  # the newest is the one left out
    assert out["open"][0].id == rows[0].id


def test_todo_at_exactly_500_is_not_truncated(w):
    svc, db = _svc(), w["db"]
    _bulk(db, w, 500)
    out = svc.todo_for_agent(db, w["a"].id, now=NOW)
    assert len(out["open"]) == 500
    assert out["truncated"] is False
