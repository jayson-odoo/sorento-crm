"""COMBO-FREE-PART: a combo part can also be listed as that combo's free item.

Plan: `documentation/plans/dealer-kit/PLAN-combo-free-part-09nov.md`. Written test-FIRST.
Owner, 9 Nov: the 2026 flyer "5 IN 1 BATHROOM FURNITURE" lists the basin cold tap as a part and
prints the same tap in its FREE box. So:
  * PUT /product-combos/{id}/accessories accepts a part (by explicit pick); the host is still refused.
  * The tag shows it in the parts section AND in the free box; the combo's LP / SP never change.
  * Copy-to-products carries it (the seed import: test_combo_free_part_import.py).
Synthetic names only.
"""
from __future__ import annotations

import uuid

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402,F401
from app.models.accessory import ProductComboAccessory
from app.models.base import company_scope
from tests import _ptag_combo_seed as seed
from tests.test_accessories import COMBO_LIST, _items, db, _scope_listeners  # noqa: F401
from tests.test_product_combo_copy_to_products import _combos_on, _copy, _free
from tests.test_product_combos import (  # noqa: F401  (_clear_overrides autouse, storage fixture)
    EDIT,
    VIEW,
    _caller,
    _clear_overrides,
    _combo,
    _part,
    _product,
    storage,
)


def _free_rows(db, combo_id):
    db.expire_all()
    with company_scope(db, None):
        return [
            (r.item_product_id, r.accessory_id)
            for r in db.query(ProductComboAccessory)
            .filter(ProductComboAccessory.combo_id == combo_id)
            .order_by(ProductComboAccessory.sort_order)
            .all()
        ]


# --------------------------------------------------------------------------- API


def test_a_part_can_be_saved_as_the_combos_free_item(db, monkeypatch):
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    host = _product(db, "ZZCAB")
    tap = _product(db, "ZZTAP")
    combo = _combo(db, host, "ZZT 5 in 1")
    _part(db, combo, tap)

    put = client.put(COMBO_LIST.format(combo_id=combo.id), json=_items(products=[(0, tap.id)]))
    assert put.status_code == 200, put.text
    (entry,) = put.json()
    assert entry["kind"] == "product" and entry["id"] == tap.id
    assert _free_rows(db, combo.id) == [(tap.id, None)]
    got = client.get(COMBO_LIST.format(combo_id=combo.id))
    assert [e["id"] for e in got.json()] == [tap.id]


def test_the_host_is_still_never_its_own_free_item(db, monkeypatch):
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    host = _product(db, "ZZCAB")
    combo = _combo(db, host, "ZZT 5 in 1")
    put = client.put(COMBO_LIST.format(combo_id=combo.id), json=_items(products=[(0, host.id)]))
    assert put.status_code == 422, put.text
    assert "own product" in put.text


# --------------------------------------------------------------------------- tag render


def test_the_tag_shows_the_part_in_the_parts_and_in_the_free_box_and_keeps_the_prices(db):
    host = seed.product(db, "ZZBF")
    tap = seed.product(db, "ZZTAP", list_price="200.00")
    cb = seed.combo(db, host, "ZZT 5 in 1", parts=[{"product": tap}], list_price="2715.00", sell_price="2400.00")

    def _tag():
        request = seed.submit_one(db, host, cb, [{"product_id": tap.id}])
        db.flush()
        (row,) = seed.rows(db, request)
        return row

    before = _tag()
    db.add(ProductComboAccessory(id=str(uuid.uuid4()), combo_id=cb.id, item_product_id=tap.id, sort_order=0))
    db.flush()
    row = _tag()

    assert [p["product_id"] for p in row["parts"]] == [tap.id], "still a part"
    assert [(e["kind"], e["id"]) for e in row["combo"]["accessories"]] == [("product", tap.id)], "and free"
    assert row["list_price"] == before["list_price"] == 2715.0
    assert row["sell_price"] == before["sell_price"]


# --------------------------------------------------------------------------- copy to products (#2284)


def test_copy_to_products_keeps_a_part_that_is_also_the_free_item(db, monkeypatch):
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    host = _product(db, "ZZCAB")
    tap = _product(db, "ZZTAP")
    combo = _combo(db, host, "ZZT 5 in 1")
    _part(db, combo, tap)
    db.add(ProductComboAccessory(id=str(uuid.uuid4()), combo_id=combo.id, item_product_id=tap.id, sort_order=0))
    db.flush()
    target = _product(db, "ZZCAB2")

    response = _copy(client, combo, [target])
    assert response.status_code == 200, response.text
    [copy] = _combos_on(db, target)
    assert _free(db, copy.id) == _free(db, combo.id)
    assert [row[1] for row in _free(db, copy.id)] == [tap.id]
