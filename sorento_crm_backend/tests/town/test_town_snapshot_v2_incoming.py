"""TOWN-V2 slice 1: the `incoming` block of `app.services.town.snapshot` (UAC 7-10, rules 6-9).

Red until `_incoming()` exists and `build_snapshot` returns it under `"incoming"`.
Postgres only (`blank_session`); every row is seeded here, codes carry the ZZT prefix.
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest

from app.models.base import set_company_scope
from app.models.procurement import InboundShipment, InboundShipmentLine, Supplier
from app.services.company_scope import DEFAULT_COMPANY_ID
from tests._mc_lookup_seed import MOCHA_ID, product, seed_mocha
from tests._pg_fixture import blank_session, unique_code
from tests.town._town_seed import DAY, NOW, deep, fake_full

TODAY = DAY


@pytest.fixture
def db():
    with blank_session() as s:
        set_company_scope(s, None)
        seed_mocha(s)
        yield s


def _incoming(db, company_id=DEFAULT_COMPANY_ID, day=TODAY):
    from app.services.town.snapshot import _incoming as fn

    return fn(db, company_id, day)


def _supplier(db, name, company_id=DEFAULT_COMPANY_ID):
    row = Supplier(
        id=str(uuid.uuid4()), supplier_code=unique_code("ZZT")[:50], supplier_name=name, company_id=company_id
    )
    db.add(row)
    db.flush()
    return row


def _ship(db, number, *, eta=None, delay=None, status="in_transit", lines=((10, 0, "in_transit"),),
          supplier=None, container=None, company_id=DEFAULT_COMPANY_ID, products=None, flush=True):
    """One shipment. `lines` = (quantity_shipped, quantity_received, line_status) per line, each on
    its own product unless `products` supplies them."""
    ship = InboundShipment(
        id=str(uuid.uuid4()), shipment_number=number, shipment_date=TODAY - timedelta(days=30),
        estimated_arrival_date=eta, eta_delay_date=delay, shipment_status=status,
        supplier_id=supplier.id if supplier else None, shipping_container_number=container,
        company_id=company_id,
    )
    db.add(ship)
    db.flush()
    for i, (shipped, received, line_status) in enumerate(lines):
        prod = products[i] if products else product(db, company_id=company_id)
        db.add(InboundShipmentLine(
            id=str(uuid.uuid4()), shipment_id=ship.id, product_id=prod.id, quantity_shipped=shipped,
            quantity_received=received, line_status=line_status, company_id=company_id,
        ))
    if flush:
        db.flush()
    return ship


def _num(tag):
    return unique_code(f"ZZT-{tag}")[:50]


def test_counts_use_effective_eta_and_next_eta(db):
    d = TODAY
    _ship(db, _num("A"), eta=d + timedelta(days=3))
    _ship(db, _num("B"), eta=None)
    _ship(db, _num("C"), eta=d - timedelta(days=5))
    _ship(db, _num("D"), eta=d - timedelta(days=2), delay=d + timedelta(days=9))  # delayed into the future
    _ship(db, _num("E"), eta=d + timedelta(days=4), delay=d - timedelta(days=1))  # delay date already past
    out = _incoming(db)
    assert out["incoming"] == 3
    assert out["late"] == 2
    assert out["next_eta"] == (d + timedelta(days=3)).isoformat()


def test_eta_on_the_day_is_incoming_not_late(db):
    _ship(db, _num("T"), eta=TODAY)
    out = _incoming(db)
    assert (out["incoming"], out["late"]) == (1, 0)
    assert out["next_eta"] == TODAY.isoformat()


def test_next_eta_none_when_nothing_ahead(db):
    _ship(db, _num("N"), eta=None)
    _ship(db, _num("L"), eta=TODAY - timedelta(days=1))
    assert _incoming(db)["next_eta"] is None


def test_excluded_shipments_are_not_counted_or_listed(db):
    d = TODAY + timedelta(days=2)
    keep = _ship(db, _num("KEEP"), eta=d)
    _ship(db, _num("DRAFT"), eta=d, status="draft")
    _ship(db, _num("FULL"), eta=d, lines=((10, 10, "in_transit"),))
    _ship(db, _num("OVER"), eta=d, lines=((10, 12, "in_transit"),))
    _ship(db, _num("RCVD"), eta=d, lines=((10, 0, "received"),))
    _ship(db, _num("OTHER"), eta=d, company_id=MOCHA_ID)
    out = _incoming(db)
    assert out["incoming"] == 1 and out["late"] == 0
    assert [r["shipment_number"] for r in out["shipments"]] == [keep.shipment_number]


def test_row_fields(db):
    sup = _supplier(db, "ZZT Supplier Co")
    p1, p2, p3 = (product(db, company_id=DEFAULT_COMPANY_ID) for _ in range(3))
    eta = TODAY + timedelta(days=6)
    number = _num("ROW")
    # p1 is on both still-incoming lines (counted once); p2 is over-received and p3 fully received, so
    # neither is still incoming: one distinct product.
    _ship(db, number, eta=eta, supplier=sup, container="ZZTU1234567", products=[p1, p1, p2, p3],
          lines=((10, 4, "in_transit"), (5, 0, "in_transit"), (7, 20, "in_transit"), (9, 9, "in_transit")))
    late = _ship(db, _num("LATE"), eta=TODAY - timedelta(days=3), lines=((3, 0, "in_transit"),))
    out = _incoming(db)
    rows = {r["shipment_number"]: r for r in out["shipments"]}
    row = rows[number]
    assert row["supplier"] == "ZZT Supplier Co"
    assert row["container"] == "ZZTU1234567"
    assert row["eta"] == eta.isoformat()
    assert row["products"] == 1
    assert row["quantity"] == 6 + 5  # (10-4) + 5; the over-received and the fully received lines add nothing
    assert row["late"] is False
    assert rows[late.shipment_number]["late"] is True
    assert rows[late.shipment_number]["supplier"] is None


def test_no_eta_row_has_none_eta(db):
    num = _num("NOETA")
    _ship(db, num, eta=None)
    row = _incoming(db)["shipments"][0]
    assert row["shipment_number"] == num and row["eta"] is None


def test_ordering_and_caps(db):
    d = TODAY
    prod = product(db, company_id=DEFAULT_COMPANY_ID)
    # 32 incoming: 30 with ETAs, 2 with none; 31 late.
    for i in range(30):
        _ship(db, f"ZZT-I{i:03d}", eta=d + timedelta(days=i + 1), products=[prod], flush=False)
    _ship(db, "ZZT-N002", eta=None, products=[prod], flush=False)
    _ship(db, "ZZT-N001", eta=None, products=[prod], flush=False)
    for i in range(31):
        _ship(db, f"ZZT-L{i:03d}", eta=d - timedelta(days=i + 1), products=[prod], flush=False)
    db.flush()
    out = _incoming(db)
    assert out["incoming"] == 32 and out["late"] == 31
    nums = [r["shipment_number"] for r in out["shipments"]]
    assert len(nums) == 60
    # 30 incoming, soonest first (the 2 no-ETA rows are cut by the cap, NULL sorts last)
    assert nums[:30] == [f"ZZT-I{i:03d}" for i in range(30)]
    assert not any(r["late"] for r in out["shipments"][:30])
    # then 30 late, most recently late first
    assert nums[30:] == [f"ZZT-L{i:03d}" for i in range(30)]
    assert all(r["late"] for r in out["shipments"][30:])


def test_null_eta_last_and_tie_by_number(db):
    d = TODAY + timedelta(days=1)
    prod = product(db, company_id=DEFAULT_COMPANY_ID)
    _ship(db, "ZZT-Z9", eta=None, products=[prod])
    _ship(db, "ZZT-B2", eta=d, products=[prod])
    _ship(db, "ZZT-A1", eta=d, products=[prod])
    _ship(db, "ZZT-C3", eta=d + timedelta(days=1), products=[prod])
    nums = [r["shipment_number"] for r in _incoming(db)["shipments"]]
    assert nums == ["ZZT-A1", "ZZT-B2", "ZZT-C3", "ZZT-Z9"]


def test_empty(db):
    assert _incoming(db) == {"incoming": 0, "late": 0, "next_eta": None, "shipments": []}


def test_build_snapshot_includes_incoming(db):
    from app.services.town.snapshot import build_snapshot

    num = _num("BS")
    _ship(db, num, eta=TODAY + timedelta(days=1))
    snap = build_snapshot(db, DEFAULT_COMPANY_ID, TODAY, now=NOW)
    assert "incoming" in snap
    assert snap["incoming"]["incoming"] == 1
    assert [r["shipment_number"] for r in snap["incoming"]["shipments"]] == [num]


def _with_incoming():
    full = fake_full()
    full["incoming"] = {
        "incoming": 2, "late": 1, "next_eta": "2026-11-05",
        "shipments": [
            {"shipment_number": "ZZT-1", "container": "C1", "supplier": "Acme Ltd", "eta": "2026-11-05",
             "products": 2, "quantity": 30, "late": False},
            {"shipment_number": "ZZT-2", "container": None, "supplier": "Beta Ltd", "eta": None,
             "products": 1, "quantity": 5, "late": False},
            {"shipment_number": "ZZT-3", "container": "C3", "supplier": None, "eta": "2026-11-01",
             "products": 1, "quantity": 9, "late": True},
        ],
    }
    return full


@pytest.mark.parametrize("fn_name", ["redact", "strip_names"])
def test_variants_drop_supplier_keep_the_rest(fn_name):
    from app.services.town import snapshot as mod

    full = _with_incoming()
    out = getattr(mod, fn_name)(full)
    inc = out["incoming"]
    assert (inc["incoming"], inc["late"], inc["next_eta"]) == (2, 1, "2026-11-05")
    assert len(inc["shipments"]) == 3
    for row in inc["shipments"]:
        assert "supplier" not in row
    assert [r["shipment_number"] for r in inc["shipments"]] == ["ZZT-1", "ZZT-2", "ZZT-3"]
    assert inc["shipments"][0]["quantity"] == 30 and inc["shipments"][0]["container"] == "C1"
    assert full["incoming"]["shipments"][0]["supplier"] == "Acme Ltd"  # input not mutated


@pytest.mark.parametrize("fn_name", ["redact", "strip_names"])
def test_variants_pass_a_snapshot_without_incoming(fn_name):
    from app.services.town import snapshot as mod

    full = fake_full()
    assert "incoming" not in full
    out = getattr(mod, fn_name)(full)
    assert "incoming" not in out
