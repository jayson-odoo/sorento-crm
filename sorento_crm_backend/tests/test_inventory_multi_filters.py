"""FILTER-MULTISELECT PR4: Stock balance (Warehouse, Status), Stock batches Status, Stock ledger
Transaction type and Stock transfers (State, Source, From, To, Item) take several values (OR within a
filter, AND across). The param rides comma-joined; repeated and single stay accepted. Red first;
Postgres only; every row seeded here into a blank schema.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.models.base import company_scope
from app.models.inventory import Stock, StockBatch, StockLedger, Warehouse
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.stock_transfer import StockTransfer
from tests._multi_filter_client import SORENTO, get, ok_ids, open_client
from tests._pg_fixture import blank_session, unique_code

BALANCE = "/api/v1/inventory/stock/balance"
BATCHES = "/api/v1/inventory/stock-batches/"
LEDGER = "/api/v1/inventory/stock-ledger/"
TRANSFERS = "/api/v1/inventory/stock-transfers"


def _uid() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


@pytest.fixture
def client(db, monkeypatch):
    with open_client(db, monkeypatch) as (c, _actor):
        yield c


def _refs(db):
    cat = ProductCategory(id=_uid(), category_code=unique_code("cat"), category_name="ZZT cat")
    uom = UnitOfMeasure(id=_uid(), uom_code=unique_code("uom"), uom_name="ZZT uom")
    db.add_all([cat, uom])
    db.flush()
    return cat, uom


def _product(db, refs, tag, key, reorder=None):
    row = Product(
        id=_uid(), product_code=f"{tag}-{key}", product_name=f"{tag} {key}", category_id=refs[0].id,
        base_uom_id=refs[1].id, list_price=Decimal("1.00"), reorder_level=reorder,
    )
    db.add(row)
    db.flush()
    return row


def _warehouse(db, key):
    row = Warehouse(id=_uid(), warehouse_code=unique_code(key), warehouse_name=f"ZZT {key}", is_active=True)
    db.add(row)
    db.flush()
    return row


def _values(resp, key):
    assert resp.status_code == 200, resp.text
    return {row[key] for row in resp.json()["data"]}


# ---- Stock balance: Warehouse (already a list on the backend) and Status buckets -------------------------

@pytest.fixture
def balance(db):
    refs = _refs(db)
    tag = unique_code("BAL", alpha=True)
    w1, w2, w3 = _warehouse(db, "w1"), _warehouse(db, "w2"), _warehouse(db, "w3")
    p = _product(db, refs, tag, "p", reorder=10)
    rows = {}
    for key, wh in (("a", w1), ("b", w2), ("c", w3)):
        s = Stock(id=_uid(), product_id=p.id, warehouse_id=wh.id, quantity_on_hand=5)
        db.add(s)
        db.flush()
        rows[key] = s
    # Status buckets, reorder level 10: critical 0, low 5, normal 12, overstock 50 (also >= reorder)
    buckets = {}
    for key, qty in (("critical", 0), ("low", 5), ("normal", 12), ("overstock", 50)):
        bp = _product(db, refs, tag, key, reorder=10)
        s = Stock(id=_uid(), product_id=bp.id, warehouse_id=w1.id, quantity_on_hand=qty)
        db.add(s)
        db.flush()
        buckets[key] = bp.id
    return dict(tag=tag, p=p, w=(w1, w2, w3), rows=rows, buckets=buckets)


def _bal(client, s, pairs, key="id"):
    return get(client, BALANCE, [("limit", 200), ("query", s["tag"]), *pairs])


def test_balance_warehouse_guard_list_forms(client, balance):
    s = balance
    w1, w2, w3 = (w.id for w in s["w"])
    only_p = ("product_id", s["p"].id)
    got = _values(_bal(client, s, [only_p, ("warehouse_ids", f"{w1},{w2}")]), "id")
    assert got == {s["rows"]["a"].id, s["rows"]["b"].id}
    got = _values(_bal(client, s, [only_p, ("warehouse_ids", w2), ("warehouse_ids", w3)]), "id")
    assert got == {s["rows"]["b"].id, s["rows"]["c"].id}
    assert _values(_bal(client, s, [only_p, ("warehouse_ids", w3)]), "id") == {s["rows"]["c"].id}
    assert _values(_bal(client, s, [only_p, ("warehouse_id", w1)]), "id") == {s["rows"]["a"].id}


def test_balance_warehouse_guard_malformed_id_refused(client, balance):
    resp = _bal(client, balance, [("warehouse_ids", "not-a-uuid")])
    assert resp.status_code in (400, 422), resp.text


def _bucket_products(client, s, status):
    resp = _bal(client, s, [("status", status)] if status else [])
    assert resp.status_code == 200, resp.text
    pids = {row["product_id"] for row in resp.json()["data"]}
    names = {k: v for k, v in s["buckets"].items() if v in pids}
    return set(names)


def test_balance_status_single_still_works(client, balance):
    assert _bucket_products(client, balance, "critical") == {"critical"}
    assert _bucket_products(client, balance, "low") == {"low"}


def test_balance_status_union_comma_joined(client, balance):
    assert _bucket_products(client, balance, "critical,low") == {"critical", "low"}
    assert _bucket_products(client, balance, "low,overstock") == {"low", "overstock"}


def test_balance_status_overlapping_buckets_are_or_ed(client, balance):
    # normal (>= reorder) also holds the overstock row; asking for both returns each row once
    assert _bucket_products(client, balance, "critical,normal") == {"critical", "normal", "overstock"}


def test_balance_status_repeated_param(client, balance):
    s = balance
    resp = _bal(client, s, [("status", "critical"), ("status", "low")])
    assert resp.status_code == 200, resp.text
    pids = {row["product_id"] for row in resp.json()["data"]}
    assert {k for k, v in s["buckets"].items() if v in pids} == {"critical", "low"}


def test_balance_status_and_warehouse_are_and_ed(client, balance):
    s = balance
    w2 = s["w"][1].id
    resp = _bal(client, s, [("status", "critical,low"), ("warehouse_ids", w2)])
    assert resp.status_code == 200, resp.text
    # the three bucket products live in warehouse 1 only; the p rows (qty 5, reorder 10) are 'low' in w2
    assert {row["id"] for row in resp.json()["data"]} == {s["rows"]["b"].id}


# ---- Stock batches: Status (declared nowhere today) ------------------------------------------------------

@pytest.fixture
def batches(db):
    refs = _refs(db)
    tag = unique_code("BAT", alpha=True)
    w1, w2 = _warehouse(db, "bw1"), _warehouse(db, "bw2")
    p = _product(db, refs, tag, "p")
    rows = {}
    for key, status, wh in (("a", "AVAILABLE", w1), ("b", "RESERVED", w1), ("c", "DAMAGED", w2), ("d", "AVAILABLE", w2)):
        b = StockBatch(
            id=_uid(), product_id=p.id, warehouse_id=wh.id, batch_code=f"{tag}-{key}", quantity=1,
            received_date=date(2026, 1, 1), status=status,
        )
        db.add(b)
        db.flush()
        rows[key] = b
    return dict(p=p, w=(w1, w2), **rows)


def _batches(client, s, pairs):
    return ok_ids(get(client, BATCHES, [("limit", 200), ("product_id", s["p"].id), *pairs]))


def test_batches_status_single_is_honoured(client, batches):
    s = batches
    assert _batches(client, s, [("status", "DAMAGED")]) == {s["c"].id}
    assert _batches(client, s, [("status", "AVAILABLE")]) == {s["a"].id, s["d"].id}


def test_batches_status_union(client, batches):
    s = batches
    assert _batches(client, s, [("status", "RESERVED,DAMAGED")]) == {s["b"].id, s["c"].id}
    got = _batches(client, s, [("status", "RESERVED"), ("status", "DAMAGED")])
    assert got == {s["b"].id, s["c"].id}


def test_batches_status_is_matched_case_insensitively(client, batches):
    # the screen sends lowercase (available, damaged, ...); stored statuses are the upper-case enum
    s = batches
    assert _batches(client, s, [("status", "damaged")]) == {s["c"].id}
    assert _batches(client, s, [("status", "reserved,damaged")]) == {s["b"].id, s["c"].id}


def test_batches_status_and_warehouse(client, batches):
    s = batches
    got = _batches(client, s, [("status", "AVAILABLE,DAMAGED"), ("warehouse_id", s["w"][1].id)])
    assert got == {s["c"].id, s["d"].id}


# ---- Stock ledger: Transaction type ----------------------------------------------------------------------

@pytest.fixture
def ledger(db):
    refs = _refs(db)
    tag = unique_code("LED", alpha=True)
    w1, w2 = _warehouse(db, "lw1"), _warehouse(db, "lw2")
    p = _product(db, refs, tag, "p")
    rows = {}
    for key, ttype, wh in (("a", "AUTOCOUNT_PUSH", w1), ("b", "BULK_IMPORT", w1), ("c", "SYSTEM_ADJUSTMENT", w2), ("d", "AUTOCOUNT_PUSH", w2)):
        r = StockLedger(
            id=_uid(), product_id=p.id, warehouse_id=wh.id, transaction_type=ttype, quantity_change=1,
            previous_quantity=0, new_quantity=1,
        )
        db.add(r)
        db.flush()
        rows[key] = r
    return dict(p=p, w=(w1, w2), **rows)


def _ledger(client, s, pairs):
    return ok_ids(get(client, LEDGER, [("limit", 200), ("product_id", s["p"].id), *pairs]))


def test_ledger_type_single(client, ledger):
    s = ledger
    assert _ledger(client, s, [("transaction_type", "AUTOCOUNT_PUSH")]) == {s["a"].id, s["d"].id}


def test_ledger_type_union(client, ledger):
    s = ledger
    assert _ledger(client, s, [("transaction_type", "SALE,ADJUSTMENT")]) == {s["b"].id, s["c"].id}
    got = _ledger(client, s, [("transaction_type", "BULK_IMPORT"), ("transaction_type", "SYSTEM_ADJUSTMENT")])
    assert got == {s["b"].id, s["c"].id}


def test_ledger_type_and_warehouse(client, ledger):
    s = ledger
    got = _ledger(client, s, [("transaction_type", "RECEIPT,ADJUSTMENT"), ("warehouse_id", s["w"][1].id)])
    assert got == {s["c"].id, s["d"].id}


# ---- Stock transfers: State (guard), Source, From, To, Item ----------------------------------------------

@pytest.fixture
def transfers(db):
    from app.models.stock_transfer import TRANSFER_PROPOSED  # noqa: F401
    from app.services import project_seed_service
    from app.services.project_service import register_project
    from tests.test_so_supply_confirmation import _project_so, _user

    refs = _refs(db)
    tag = unique_code("TRF", alpha=True)
    project_seed_service.run(db, company_id=SORENTO)
    actor = _user(db, f"{tag} Eling")
    project = register_project(
        db, company_id=SORENTO, actor_user_id=actor, developer_party_id=None, title=f"{tag} Tower",
    )
    mirror = _project_so(db, project)
    wa, wb, wc = _warehouse(db, "ta"), _warehouse(db, "tb"), _warehouse(db, "tc")
    p1, p2, p3 = (_product(db, refs, tag, k) for k in ("p1", "p2", "p3"))
    spec = {
        "t1": (p1, "own_group", "proposed", wa, wb),
        "t2": (p2, "pool", "approved", wb, wc),
        "t3": (p3, "borrow", "moved", wc, wa),
        "t4": (p1, "borrow", "proposed", wa, wc),
    }
    out = dict(tag=tag, p=(p1, p2, p3), w=(wa, wb, wc))
    with company_scope(db, frozenset({SORENTO})):
        for key, (prod, kind, state, src, dst) in spec.items():
            row = StockTransfer(
                id=_uid(), company_id=SORENTO, transfer_no=f"{tag[-6:]}-{key}", project_sales_order_id=mirror.id,
                product_id=prod.id, from_warehouse_id=src.id, to_warehouse_id=dst.id, qty=Decimal("3"),
                kind=kind, state=state,
            )
            db.add(row)
            db.flush()
            out[key] = row
    db.commit()
    return out


def _tr(client, pairs):
    return ok_ids(get(client, TRANSFERS, [("limit", 200), *pairs]))


def test_transfer_state_guard_forms(client, transfers):
    s = transfers
    assert _tr(client, [("state", "proposed,approved")]) == {s["t1"].id, s["t2"].id, s["t4"].id}
    assert _tr(client, [("state", "moved")]) == {s["t3"].id}


def test_transfer_state_unknown_is_refused(client, transfers):
    assert get(client, TRANSFERS, [("state", "proposed,teleported")]).status_code == 422


def test_transfer_source_union_and_single(client, transfers):
    s = transfers
    assert _tr(client, [("kind", "pool")]) == {s["t2"].id}
    assert _tr(client, [("kind", "own_group,pool")]) == {s["t1"].id, s["t2"].id}
    assert _tr(client, [("kind", "pool"), ("kind", "borrow")]) == {s["t2"].id, s["t3"].id, s["t4"].id}


def test_transfer_source_unknown_is_refused(client, transfers):
    assert get(client, TRANSFERS, [("kind", "own_group,sideways")]).status_code == 422


def test_transfer_from_to_item_union(client, transfers):
    s = transfers
    wa, wb, wc = (w.id for w in s["w"])
    p1, p2, p3 = (p.id for p in s["p"])
    assert _tr(client, [("from_warehouse_id", f"{wa},{wb}")]) == {s["t1"].id, s["t2"].id, s["t4"].id}
    assert _tr(client, [("from_warehouse_id", wb), ("from_warehouse_id", wc)]) == {s["t2"].id, s["t3"].id}
    assert _tr(client, [("to_warehouse_id", f"{wb},{wc}")]) == {s["t1"].id, s["t2"].id, s["t4"].id}
    assert _tr(client, [("product_id", f"{p2},{p3}")]) == {s["t2"].id, s["t3"].id}
    assert _tr(client, [("product_id", p1)]) == {s["t1"].id, s["t4"].id}


def test_transfer_and_across_filters(client, transfers):
    s = transfers
    wa, wb, _wc = (w.id for w in s["w"])
    got = _tr(client, [("state", "proposed,approved"), ("kind", "own_group,borrow"), ("from_warehouse_id", f"{wa},{wb}")])
    assert got == {s["t1"].id, s["t4"].id}


def test_transfer_malformed_ids_are_refused(client, transfers):
    for key in ("from_warehouse_id", "to_warehouse_id", "product_id"):
        resp = get(client, TRANSFERS, [(key, f"{_uid()},not-a-uuid")])
        assert resp.status_code == 422, (key, resp.text)
