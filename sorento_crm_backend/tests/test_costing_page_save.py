"""RED tests B8: PATCH /api/v1/master-data/costing/rows, the page's one Save. PRODUCT-COSTING.
AC-CG-08, AC-CG-14, AC-LC-06 (selected only as a product override), AC-PC-09.

Contract 4.3. Body: {"party_id": <customer id> | null, "changes": [{"product_id", + any of
markup_pct, transport_mode, transport_value, cost_method, cost_method_supplier_id}]}.

Choices the contract leaves open (the coder follows these):
  * "cell" = Mark-up (1), Transport (mode + value together = 1), Cost method (method + its supplier
    together = 1). `{"updated": N}` counts cells whose value actually changed; a key sent with the
    value the row already has is not a changed cell and writes nothing, not even an audit row.
  * Audit: markup cells land on `customer_costing_products` (entity_id = its id); transport and
    method cells land on `costing_product_overrides` (entity_id = product_id). A change that
    touches only one of those rows writes no audit row on the other.
  * Validation failures are 422; an unknown product or party is 404 or 422 (accepted either way) and
    in every failing case NOTHING is written.
  * Switching a product from `selected` to another method clears `cost_method_supplier_id`.
"""
from __future__ import annotations

import uuid

import pytest

from tests.support.costing_env import COST_VIEW, MANAGE, costing_env  # noqa: F401

A = pytest.approx


def _env(costing_env):
    e = costing_env
    w = e.workbook()
    e.as_user(e.manager())
    return e, w


def _override(e, product):
    from app.models.costing import CostingProductOverride

    e.db.expire_all()
    return e.db.query(CostingProductOverride).filter_by(product_id=product.id).one_or_none()


def _pp(e, row):
    from app.models.costing import CustomerCostingProduct

    e.db.expire_all()
    return e.db.query(CustomerCostingProduct).filter_by(id=row.id).one()


def _patch(e, w, *changes, party=True):
    return e.patch_rows({"party_id": w.customer.id if party else None, "changes": list(changes)})


# ------------------------------------------------------------------ AC-CG-08 happy paths


def test_ac_cg_08_a_markup_cell_updates_the_party_row_and_is_audited_old_to_new(costing_env):
    e, w = _env(costing_env)
    r = _patch(e, w, {"product_id": w.wb.id, "markup_pct": 12})
    assert r.status_code == 200, r.text
    assert r.json() == {"updated": 1}
    assert float(_pp(e, w.pp_wb).markup_pct) == 12.0

    audits = _changes(e, "customer_costing_products", w.pp_wb.id)
    assert [a.action for a in audits] == ["UPDATE"]
    assert audits[0].old_values["markup_pct"] is None
    assert float(audits[0].new_values["markup_pct"]) == 12.0
    assert set(audits[0].new_values) == {"markup_pct"}  # only the changed cell
    assert audits[0].user_id == e.principal["id"]

    row = e.row_of(e.rows(party_id=w.customer.id, as_of="2026-11-11"), "CGB9032B")
    assert row["markup_pct"] == A(12.0) and row["markup_source"] == "row"
    assert row["final"] == A(31.71875 * 1.12, abs=1e-6)


def test_ac_cg_08_a_second_edit_audits_the_old_value(costing_env):
    e, w = _env(costing_env)
    r = _patch(e, w, {"product_id": w.jac.id, "markup_pct": 15})  # was 10
    assert r.json() == {"updated": 1}
    audits = e.audit_rows("customer_costing_products", w.pp_jac.id)
    assert float(audits[-1].old_values["markup_pct"]) == 10.0
    assert float(audits[-1].new_values["markup_pct"]) == 15.0


def test_ac_cg_08_transport_and_method_cells_write_the_product_override(costing_env):
    e, w = _env(costing_env)
    r = _patch(e, w, {"product_id": w.wb.id, "transport_mode": "add", "transport_value": 20,
                      "cost_method": "selected", "cost_method_supplier_id": w.sup_b.id})
    assert r.status_code == 200, r.text
    assert r.json() == {"updated": 2}  # one transport cell + one method cell
    o = _override(e, w.wb)
    assert (o.transport_mode, float(o.transport_value)) == ("add", 20.0)
    assert (o.cost_method, o.cost_method_supplier_id) == ("selected", w.sup_b.id)

    audited = e.audit_rows("costing_product_overrides", w.wb.id)
    assert audited, "override writes are audited"
    seen = {}
    for a in audited:
        seen.update(a.new_values or {})
    assert seen["transport_mode"] == "add"
    assert float(seen["transport_value"]) == 20.0
    assert seen["cost_method"] == "selected"
    assert seen["cost_method_supplier_id"] == w.sup_b.id

    row = e.row_of(e.rows(party_id=w.customer.id, as_of="2026-11-11"), "CGB9032B")
    assert row["transport_source"] == "product" and row["cost_method"] == "selected"
    assert row["cost_method_source"] == "product" and row["supplier_code"] == "SUP-B07"
    assert row["landing"] == A(38 * 0.625 * 1.1 + 20, abs=1e-6)  # 46.125


def test_ac_cg_08_one_batch_many_products_counts_every_changed_cell(costing_env):
    e, w = _env(costing_env)
    r = _patch(
        e, w,
        {"product_id": w.wb.id, "markup_pct": 12, "transport_mode": "multiply", "transport_value": 1.5,
         "cost_method": "average"},
        {"product_id": w.jac.id, "markup_pct": 9},
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"updated": 4}
    assert float(_pp(e, w.pp_wb).markup_pct) == 12.0
    assert float(_pp(e, w.pp_jac).markup_pct) == 9.0
    assert _override(e, w.jac) is None  # a markup-only change creates no override row


def test_ac_cg_08_only_changed_cells_are_written(costing_env):
    """KILL TEST (backend half of 'Save sends every row'): untouched cells and rows leave no trace."""
    e, w = _env(costing_env)
    e.override(w.wb, transport_mode="add", transport_value="15")
    e.db.commit()
    before_override = len(e.audit_rows("costing_product_overrides", w.wb.id))
    before_jac = len(e.audit_rows("customer_costing_products", w.pp_jac.id))

    r = _patch(e, w, {"product_id": w.wb.id, "markup_pct": 12})
    assert r.json() == {"updated": 1}
    assert len(e.audit_rows("costing_product_overrides", w.wb.id)) == before_override
    assert len(e.audit_rows("customer_costing_products", w.pp_jac.id)) == before_jac
    o = _override(e, w.wb)
    assert (o.transport_mode, float(o.transport_value)) == ("add", 15.0)  # untouched


def test_ac_cg_08_sending_the_value_a_cell_already_has_is_not_a_change(costing_env):
    e, w = _env(costing_env)
    before = len(e.audit_rows("customer_costing_products", w.pp_jac.id))
    r = _patch(e, w, {"product_id": w.jac.id, "markup_pct": 10})  # already 10
    assert r.status_code == 200, r.text
    assert r.json() == {"updated": 0}
    assert len(e.audit_rows("customer_costing_products", w.pp_jac.id)) == before


def test_ac_cg_08_an_empty_change_list_is_a_noop_200(costing_env):
    e, w = _env(costing_env)
    r = e.patch_rows({"party_id": w.customer.id, "changes": []})
    assert r.status_code == 200 and r.json() == {"updated": 0}


# ------------------------------------------------------------------ clearing restores the inherited value


def test_ac_cg_08_clearing_a_row_markup_restores_the_partys(costing_env):
    e, w = _env(costing_env)
    r = _patch(e, w, {"product_id": w.jac.id, "markup_pct": None})
    assert r.json() == {"updated": 1}
    assert _pp(e, w.pp_jac).markup_pct is None
    row = e.row_of(e.rows(party_id=w.customer.id, as_of="2026-11-11"), "JAC-5001")
    assert (row["markup_pct"], row["markup_source"]) == (A(8.0), "party")


def test_ac_cg_08_clearing_transport_restores_the_category_rule_and_drops_an_empty_override(costing_env):
    e, w = _env(costing_env)
    e.override(w.wb, transport_mode="add", transport_value="20")
    e.db.commit()
    r = _patch(e, w, {"product_id": w.wb.id, "transport_mode": None, "transport_value": None})
    assert r.status_code == 200, r.text
    assert r.json() == {"updated": 1}
    assert _override(e, w.wb) is None  # row deleted when every field is cleared
    row = e.row_of(e.rows(as_of="2026-11-11"), "CGB9032B")
    assert row["transport_source"] == "category" and row["transport_value"] == A(8.0)
    assert row["landing"] == A(31.71875, abs=1e-6)


def test_ac_cg_08_clearing_the_method_restores_party_or_company(costing_env):
    e, w = _env(costing_env)
    e.override(w.wb, transport_mode="add", transport_value="20", cost_method="average")
    e.db.commit()
    r = _patch(e, w, {"product_id": w.wb.id, "cost_method": None})
    assert r.json() == {"updated": 1}
    o = _override(e, w.wb)
    assert o is not None and o.cost_method is None and o.transport_mode == "add"  # transport kept
    row = e.row_of(e.rows(as_of="2026-11-11"), "CGB9032B")
    assert (row["cost_method"], row["cost_method_source"]) == ("primary", "company")


def test_ac_lc_06_leaving_selected_clears_the_supplier(costing_env):
    e, w = _env(costing_env)
    e.override(w.wb, cost_method="selected", cost_method_supplier_id=w.sup_b.id)
    e.db.commit()
    r = _patch(e, w, {"product_id": w.wb.id, "cost_method": "average", "cost_method_supplier_id": None})
    assert r.status_code == 200, r.text
    o = _override(e, w.wb)
    assert o.cost_method == "average" and o.cost_method_supplier_id is None


# ------------------------------------------------------------------ validation (422, nothing written)


def _changes(e, entity_type, entity_id):
    """Audit rows written after the fixture: its own CREATE rows are not a change."""
    return [a for a in e.audit_rows(entity_type, entity_id) if a.action != "CREATE"]


def _nothing_written(e, w):
    from app.models.costing import CostingProductOverride

    e.db.expire_all()
    assert e.db.query(CostingProductOverride).count() == 0
    assert float(_pp(e, w.pp_jac).markup_pct) == 10.0
    assert _pp(e, w.pp_wb).markup_pct is None
    # The fixture's own link rows carry their CREATE audit row; nothing after it.
    assert _changes(e, "customer_costing_products", w.pp_wb.id) == []
    assert _changes(e, "customer_costing_products", w.pp_jac.id) == []
    assert _changes(e, "costing_product_overrides", w.wb.id) == []


def test_ac_cg_08_markup_in_company_standard_is_422(costing_env):
    e, w = _env(costing_env)
    r = _patch(e, w, {"product_id": w.wb.id, "markup_pct": 12}, party=False)
    assert r.status_code == 422, r.text
    _nothing_written(e, w)


def test_ac_cg_08_markup_for_a_product_not_on_the_party_is_422(costing_env):
    e, w = _env(costing_env)
    r = _patch(e, w, {"product_id": w.tap.id, "markup_pct": 12})
    assert r.status_code == 422, r.text
    _nothing_written(e, w)


def test_ac_cg_08_transport_and_method_can_be_saved_in_company_standard(costing_env):
    e, w = _env(costing_env)
    r = _patch(e, w, {"product_id": w.tap.id, "transport_mode": "multiply", "transport_value": 1.2,
                      "cost_method": "average"}, party=False)
    assert r.status_code == 200, r.text
    assert r.json() == {"updated": 2}
    assert _override(e, w.tap).cost_method == "average"


@pytest.mark.parametrize("field,value", [
    ("unit_cost", 10), ("rate", 0.7), ("rate_to_base", 0.7), ("sst_factor", 1.2), ("list_price", 99),
    ("landing", 1), ("final", 1), ("currency", "USD"), ("supplier_id", "x"), ("anything_else", True),
])
def test_ac_cg_08_cost_rate_sst_and_price_fields_are_422(costing_env, field, value):
    e, w = _env(costing_env)
    r = _patch(e, w, {"product_id": w.wb.id, "markup_pct": 12, field: value})
    assert r.status_code == 422, r.text
    _nothing_written(e, w)


def test_ac_cg_08_an_unknown_top_level_key_is_422(costing_env):
    e, w = _env(costing_env)
    r = e.patch_rows({"party_id": w.customer.id, "sst_factor": 1.3, "changes": []})
    assert r.status_code == 422, r.text


@pytest.mark.parametrize("change", [
    {"transport_mode": "add"},
    {"transport_value": 8},
    {"transport_mode": "add", "transport_value": 0},
    {"transport_mode": "add", "transport_value": -3},
    {"transport_mode": "halve", "transport_value": 2},
    {"transport_mode": None, "transport_value": 8},
    {"transport_mode": "add", "transport_value": None},
    {"markup_pct": -1},
    {"cost_method": "bogus"},
    {"cost_method": "selected"},  # no supplier named
])
def test_ac_cg_08_invalid_cells_are_422_and_nothing_is_written(costing_env, change):
    e, w = _env(costing_env)
    r = _patch(e, w, {"product_id": w.wb.id, **change})
    assert r.status_code == 422, r.text
    _nothing_written(e, w)


def test_ac_lc_06_selected_needs_a_current_link_of_the_product(costing_env):
    e, w = _env(costing_env)
    stranger = e.source("SUP-ZZ99")  # a supplier, but not linked to WB 245
    e.db.commit()
    r = _patch(e, w, {"product_id": w.wb.id, "cost_method": "selected", "cost_method_supplier_id": stranger.id})
    assert r.status_code == 422, r.text
    _nothing_written(e, w)

    ok = _patch(e, w, {"product_id": w.wb.id, "cost_method": "selected", "cost_method_supplier_id": w.sup_l.id})
    assert ok.status_code == 200, ok.text
    assert _override(e, w.wb).cost_method_supplier_id == w.sup_l.id


def test_ac_cg_08_all_or_nothing_one_invalid_change_writes_nothing(costing_env):
    e, w = _env(costing_env)
    r = _patch(
        e, w,
        {"product_id": w.wb.id, "markup_pct": 12, "transport_mode": "add", "transport_value": 20},
        {"product_id": w.jac.id, "markup_pct": 9},
        {"product_id": w.tap.id, "markup_pct": 5},  # not on the party: invalid
    )
    assert r.status_code == 422, r.text
    _nothing_written(e, w)


def test_ac_cg_08_unknown_product_or_party_writes_nothing(costing_env):
    e, w = _env(costing_env)
    bad_product = _patch(e, w, {"product_id": str(uuid.uuid4()), "transport_mode": "add", "transport_value": 5})
    assert bad_product.status_code in (404, 422), bad_product.text
    bad_party = e.patch_rows({"party_id": str(uuid.uuid4()),
                              "changes": [{"product_id": w.wb.id, "markup_pct": 5}]})
    assert bad_party.status_code in (404, 422), bad_party.text
    _nothing_written(e, w)


def test_ac_cg_08_a_party_without_a_profile_takes_no_markup_edit(costing_env):
    e, w = _env(costing_env)
    stranger = e.customer(code="304-R999", name="NO PROFILE LTD")
    e.db.commit()
    r = e.patch_rows({"party_id": stranger.id, "changes": [{"product_id": w.wb.id, "markup_pct": 5}]})
    assert r.status_code in (404, 422), r.text
    _nothing_written(e, w)


# ------------------------------------------------------------------ permissions


def test_ac_cg_08_saving_needs_manage_and_cost_view(costing_env):
    e, w = _env(costing_env)
    change = {"product_id": w.wb.id, "markup_pct": 12}
    for principal in (e.viewer(), e.user(MANAGE), e.user()):
        e.as_user(principal)
        r = _patch(e, w, change)
        assert r.status_code == 403, r.text
    _nothing_written(e, w)

    e.as_user(e.manager())
    assert _patch(e, w, change).status_code == 200


# ------------------------------------------------------------------ AC-CG-14 the price is never written


def test_ac_cg_14_save_leaves_list_price_alone_and_calls_no_autocount_client(costing_env, monkeypatch):
    from app.models.product import Product
    from app.services.foundryx_autocount_client import FoundryxAutocountClient

    def _boom(*a, **k):
        raise AssertionError("a costing save must not call AutoCount")

    monkeypatch.setattr(FoundryxAutocountClient, "_request", _boom)
    monkeypatch.setattr(FoundryxAutocountClient, "write", _boom)

    e, w = _env(costing_env)
    r = _patch(
        e, w,
        {"product_id": w.wb.id, "markup_pct": 50, "transport_mode": "add", "transport_value": 99},
        {"product_id": w.jac.id, "markup_pct": 99, "cost_method": "average"},
    )
    assert r.status_code == 200, r.text
    e.db.expire_all()
    assert float(e.db.get(Product, w.wb.id).list_price) == 79.0
    assert float(e.db.get(Product, w.jac.id).list_price) == 3998.93
    row = e.row_of(e.rows(party_id=w.customer.id, as_of="2026-11-11"), "CGB9032B")
    assert row["list_price"] == A(79.0)  # the page shows it, the save never moves it
