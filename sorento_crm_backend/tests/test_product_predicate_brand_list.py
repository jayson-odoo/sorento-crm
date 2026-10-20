"""CHAT-STATE r4 R4-A: `resolve_product_set` with several brands (the re-run of a two-brand pick).

The tests above read only the set_key; this reads the predicate path itself. `brand=[a, b]` must
fetch both brands' products (and a third brand's none), the set total is the sum, and a single brand
returns exactly what a bare string did before.
"""
from __future__ import annotations

import uuid

from app.models.product import Brand
from app.services.product_predicate_service import resolve_product_set
from tests.test_product_predicate_service import _REFS, _product, _stock, db  # noqa: F401


def _brand(db, name):
    row = Brand(id=str(uuid.uuid4()), brand_code=f"ZZT{name.upper()}{uuid.uuid4().hex[:4]}", brand_name=name)
    db.add(row)
    db.flush()
    return row


def _seed(db):
    brands = {n: _brand(db, n) for n in ("ZztAlpha", "ZztBeta", "ZztGamma")}
    ids: dict[str, list] = {}
    codes: dict[str, set] = {}
    for n, count in (("ZztAlpha", 3), ("ZztBeta", 2), ("ZztGamma", 4)):
        ids[n], codes[n] = [], set()
        for i in range(count):
            p = _product(db, f"ZZT-{n.upper()}-{i}", f"ZZT {n} item {i}")
            p.brand_id = brands[n].id
            db.flush()
            _stock(db, p, 5)
            ids[n].append(p.id)
            codes[n].add(p.product_code)
    return ids, codes


def _run(db, ids, brand):
    return resolve_product_set(db, require={"stock": True}, product_ids=[i for v in ids.values() for i in v], brand=brand)


def test_two_brands_fetch_both_and_not_a_third_and_the_total_is_the_sum(db):
    ids, codes = _seed(db)
    out = _run(db, ids, ["ZztAlpha", "ZztBeta"])
    got = {c["product_code"] for c in out["candidates"]}
    assert got == codes["ZztAlpha"] | codes["ZztBeta"], got
    assert out["qualifying_total"] == 5, out["qualifying_total"]


def test_two_brands_each_contribute_their_own_products(db):
    ids, codes = _seed(db)
    out = _run(db, ids, ["ZztBeta", "ZztGamma"])
    got = {c["product_code"] for c in out["candidates"]}
    assert got == codes["ZztBeta"] | codes["ZztGamma"], got
    assert out["qualifying_total"] == 6, out["qualifying_total"]


def test_a_single_brand_returns_exactly_what_it_did_before(db):
    ids, codes = _seed(db)
    as_text = _run(db, ids, "ZztAlpha")
    as_list = _run(db, ids, ["ZztAlpha"])
    assert {c["product_code"] for c in as_text["candidates"]} == codes["ZztAlpha"]
    assert as_text["qualifying_total"] == 3
    assert as_list["qualifying_total"] == as_text["qualifying_total"]
    assert {c["product_code"] for c in as_list["candidates"]} == {c["product_code"] for c in as_text["candidates"]}
