"""STOCKDEBT-PERF PR2 (AC-SDP-B1, B2): a product is walked once per distinct pin set.

WRITTEN BEFORE THE IMPLEMENTATION EXISTS (Phase 2 is test-first). Plan:
documentation/plans/scm/stockdebt-perf-acceptance-criteria.md, section PR2.

Seeded: P_PLAIN (open SO line, no hold) and P_PINNED (two confirmed own pins at an in-span
bin, plus one unpinned later line). P_LANDED (a product that gains a landed hold in the
landed pass) is NOT seeded: it needs a PO line carrying `from_so_line_ref` received on an SPO
at the bin, which is not a cheap chain, so B1's "<= 2 for a changing pin set" arm is skipped.
"""
from __future__ import annotations

from collections import Counter
from datetime import timedelta

from app.services.scm.supply_assignment import month_key
from tests.scm.conftest import requires_pg
from tests.scm.test_stock_debt_routes import (
    _client,
    _demand,
    _months_ahead,
    _product,
    _row_of,
    _u,
    _warehouse,
)
from tests.scm.test_stock_debt_stale_pin import _at, _pinned_line, _stock

pytestmark = requires_pg


def _seed(db):
    marker = f"ZZTWO{_u()[:6]}".upper()
    bin_ = _warehouse(db, f"ZZTBRW{_u()[:4]}-BB")
    plain = _product(db, f"{marker}-PLAIN")
    pinned = _product(db, f"{marker}-PINNED")
    m1, m2, m3 = _months_ahead(1), _months_ahead(2), _months_ahead(3)

    _demand(db, plain, bin_, qty=5, required_date=m2, so_number=f"{marker}-SO1")

    _stock(db, pinned, bin_, on_hand=5)
    # Confirmed first (minute 0) = line A; second (minute 1) = line B: hold order A, B.
    line_a = _pinned_line(db, pinned, bin_, qty=3, due=m1, so_number=f"{marker}-SO2",
                          confirmed_at=_at(0))
    line_b = _pinned_line(db, pinned, bin_, qty=2, due=m1 + timedelta(days=3),
                          so_number=f"{marker}-SO3", confirmed_at=_at(1))
    _demand(db, pinned, bin_, qty=4, required_date=m3, so_number=f"{marker}-SO4")
    db.flush()
    return marker, plain, pinned, (line_a, line_b), (m1, m2, m3)


def _spy(monkeypatch):
    import app.services.scm.stock_debt_service as mod

    calls: list = []
    real = mod.assign

    def wrapper(product_id, *a, **k):
        calls.append((str(product_id), list(k.get("pinned") or [])))
        return real(product_id, *a, **k)

    monkeypatch.setattr(mod, "assign", wrapper)
    return calls


def _list(db, marker, **kw):
    from app.services.scm.stock_debt_service import StockDebtService

    kw.setdefault("only_debt", True)
    return StockDebtService(db).list(query=marker, **kw)


def test_each_product_is_walked_once_when_its_pins_do_not_change(scm_app, monkeypatch):
    """AC-SDP-B1: P_PLAIN once, P_PINNED once (today three: base, landed, book-SO)."""
    app, db = _client(scm_app)
    marker, plain, pinned, _lines, _m = _seed(db)
    calls = _spy(monkeypatch)

    _list(db, marker)

    count = Counter(pid for pid, _pins in calls)
    assert count[str(plain.id)] == 1, dict(count)
    assert count[str(pinned.id)] == 1, dict(count)


def test_the_final_walk_gets_exactly_the_products_holds_in_hold_order(scm_app, monkeypatch):
    """AC-SDP-B2: the pinned set is the holds on the product's own lines, A then B (the
    order they were confirmed in), and nothing else; P_PLAIN gets none.

    Read on the BOARD's path (`assignments_for`): since STOCKDEBT-NO-PLAN-REACH (owner 28
    Oct 2026) the view hands no decision to the walk, so its pin set here is empty."""
    from app.models.inventory import Warehouse
    from app.services.scm.stock_debt_service import StockDebtService

    app, db = _client(scm_app)
    marker, plain, pinned, (line_a, line_b), _m = _seed(db)
    bin_ = db.query(Warehouse).filter(Warehouse.id == line_a.warehouse_id).one()
    calls = _spy(monkeypatch)

    _list(db, marker)
    assert all(pins == [] for _pid, pins in calls), calls
    calls.clear()

    StockDebtService(db).assignments_for(
        [str(plain.id), str(pinned.id)], {str(bin_.id): bin_}
    )

    final = {pid: pins for pid, pins in calls}  # the last call per product wins
    pins = final[str(pinned.id)]
    assert [h.line_key for h in pins] == [str(line_a.id), str(line_b.id)], \
        [h.line_key for h in pins]
    assert [float(h.qty) for h in pins] == [3.0, 2.0]
    assert final[str(plain.id)] == []


def test_pinned_row_numbers_are_pinned(scm_app):
    """Numbers pin: the two pins draw the 5 on hand, the unpinned 4 due in month 3 is short,
    nothing is TBA, so months are 0 except month 3 = -4 and total = -4."""
    app, db = _client(scm_app)
    marker, plain, pinned, _lines, (_m1, _m2, m3) = _seed(db)

    body = _list(db, marker)

    row = _row_of(body, pinned.product_code)
    balances = {m["key"]: m["balance"] for m in row["months"]}
    assert balances[month_key(m3)] == -4
    assert sum(v for k, v in balances.items() if k != month_key(m3)) == 0
    assert row["tba"] == 0
    assert row["total"] == -4
    plain_row = _row_of(body, plain.product_code)
    assert plain_row["total"] == -5
