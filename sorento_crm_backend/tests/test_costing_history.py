"""RED tests B11: GET /api/v1/master-data/costing/rows/{product_id}/history?party_id. PRODUCT-COSTING.
AC-CG-11, AC-PC-09, AC-AX-01.

Contract 4.4: `{"data": [{changed_at, user_name, field, old, new}]}`, newest first, built from the
audit rows of that product's `costing_product_overrides` row and, with `party_id`, that party's
`customer_costing_products` row. Nothing from other rows.

Choices the contract leaves open (the coder follows these):
  * `field` is the column name: markup_pct, transport_mode, transport_value, cost_method,
    cost_method_supplier_id. One entry per changed column per audit row.
  * `old` / `new` are the raw audit values (numbers may be floats or numeric strings; the tests
    convert); an insert reads old null, a clear reads new null.
  * `user_name` is the acting user's name.
"""
from __future__ import annotations

import pytest

from tests.support.costing_env import COST_VIEW, MANAGE, costing_env  # noqa: F401


def _num(v):
    return None if v is None else float(v)


def _hist(e, product, party=None):
    r = e.get(f"/rows/{product.id}/history", party_id=party.id if party else None)
    assert r.status_code == 200, r.text
    return r.json()["data"]


def _entries(data, field):
    return [(d["user_name"], d["old"], d["new"]) for d in data if d["field"] == field]


def _setup(costing_env):
    e = costing_env
    w = e.workbook()
    alice = e.user(COST_VIEW, MANAGE, name="Alice")
    bob = e.user(COST_VIEW, MANAGE, name="Bob")
    return e, w, alice, bob


def test_ac_cg_11_history_lists_markup_transport_and_method_changes_old_to_new(costing_env):
    e, w, alice, bob = _setup(costing_env)
    e.as_user(alice)
    assert e.patch_rows({"party_id": w.customer.id, "changes": [
        {"product_id": w.wb.id, "markup_pct": 12, "transport_mode": "add", "transport_value": 20}]}).status_code == 200
    e.as_user(bob)
    assert e.patch_rows({"party_id": w.customer.id, "changes": [
        {"product_id": w.wb.id, "markup_pct": 14, "cost_method": "average"}]}).status_code == 200

    e.as_user(e.viewer())
    data = _hist(e, w.wb, w.customer)

    markup = [(u, _num(o), _num(n)) for u, o, n in _entries(data, "markup_pct")]
    assert markup == [("Bob", 12.0, 14.0), ("Alice", None, 12.0)]  # newest first
    assert [(u, o, _num(n)) for u, o, n in _entries(data, "transport_value")] == [("Alice", None, 20.0)]
    assert _entries(data, "transport_mode") == [("Alice", None, "add")]
    assert _entries(data, "cost_method") == [("Bob", None, "average")]

    stamps = [d["changed_at"] for d in data]
    assert stamps == sorted(stamps, reverse=True)
    assert all(set(d) >= {"changed_at", "user_name", "field", "old", "new"} for d in data)


def test_ac_cg_11_without_party_id_only_the_product_override_shows(costing_env):
    e, w, alice, bob = _setup(costing_env)
    e.as_user(alice)
    e.patch_rows({"party_id": w.customer.id, "changes": [
        {"product_id": w.wb.id, "markup_pct": 12, "transport_mode": "multiply", "transport_value": 1.5}]})
    e.as_user(e.viewer())
    data = _hist(e, w.wb)
    assert {d["field"] for d in data} == {"transport_mode", "transport_value"}
    assert _hist(e, w.wb, w.customer) != data  # the party view adds the mark-up entry


def test_ac_cg_11_a_clear_reads_new_null_and_a_cleared_override_row_still_has_its_history(costing_env):
    e, w, alice, bob = _setup(costing_env)
    e.as_user(alice)
    e.patch_rows({"party_id": None, "changes": [{"product_id": w.tap.id, "transport_mode": "add", "transport_value": 5}]})
    e.patch_rows({"party_id": None, "changes": [{"product_id": w.tap.id, "transport_mode": None, "transport_value": None}]})
    e.as_user(e.viewer())
    data = _hist(e, w.tap)
    tv = _entries(data, "transport_value")
    assert [(_num(o), _num(n)) for _u, o, n in tv] == [(5.0, None), (None, 5.0)]


def test_ac_cg_11_nothing_from_other_rows_leaks_in(costing_env):
    e, w, alice, bob = _setup(costing_env)
    other_party = e.customer(code="304-R200", name="OTHER PARTY SDN BHD")
    e.profile(other_party, markup_pct=9)
    e.party_product(other_party, w.wb)
    e.db.commit()

    e.as_user(alice)
    # WB 245 under Bath Plus
    e.patch_rows({"party_id": w.customer.id, "changes": [{"product_id": w.wb.id, "markup_pct": 12}]})
    # the same product under ANOTHER party, a different product under the same party, and a
    # different product's override: none of these belong to WB 245 @ Bath Plus
    e.patch_rows({"party_id": other_party.id, "changes": [{"product_id": w.wb.id, "markup_pct": 77}]})
    e.patch_rows({"party_id": w.customer.id, "changes": [{"product_id": w.jac.id, "markup_pct": 66}]})
    e.patch_rows({"party_id": None, "changes": [{"product_id": w.tap.id, "transport_mode": "add", "transport_value": 55}]})

    e.as_user(e.viewer())
    data = _hist(e, w.wb, w.customer)
    assert [(_num(o), _num(n)) for _u, o, n in _entries(data, "markup_pct")] == [(None, 12.0)]
    assert {d["field"] for d in data} == {"markup_pct"}
    seen = {_num(d["new"]) for d in data if isinstance(d["new"], (int, float, str)) and str(d["new"]).replace(".", "", 1).isdigit()}
    assert seen.isdisjoint({77.0, 66.0, 55.0})


def test_ac_cg_11_a_row_with_no_changes_has_an_empty_history(costing_env):
    e, w, alice, bob = _setup(costing_env)
    e.as_user(e.viewer())
    r = e.get(f"/rows/{w.sink.id}/history")
    assert r.status_code == 200, r.text
    assert r.json() == {"data": []}


def test_ac_cg_11_unknown_product_is_404(costing_env):
    import uuid

    e, w, alice, bob = _setup(costing_env)
    e.as_user(e.viewer())
    assert e.get(f"/rows/{uuid.uuid4()}/history").status_code == 404


def test_ac_ax_01_history_needs_cost_view(costing_env):
    e, w, alice, bob = _setup(costing_env)
    e.as_user(e.user())
    assert e.get(f"/rows/{w.wb.id}/history").status_code == 403
    e.as_user(e.user(MANAGE))
    assert e.get(f"/rows/{w.wb.id}/history", party_id=w.customer.id).status_code == 403
    e.as_user(e.viewer())
    assert e.get(f"/rows/{w.wb.id}/history").status_code == 200
