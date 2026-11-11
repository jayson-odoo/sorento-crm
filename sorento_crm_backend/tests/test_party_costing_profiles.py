"""RED tests B10: party costing profiles and their products. PRODUCT-COSTING.
AC-PC-01, AC-PC-02, AC-PC-09, AC-LC-06, AC-CG-12, AC-AX-01.

Routes (contract 4.7), under /api/v1/master-data/costing:
    GET    /parties/{customer_id}                 -> Party
    PUT    /parties/{customer_id}   (manage)      {markup_pct, cost_method, is_active} upsert -> Party
    POST   /parties/{customer_id}/products (manage)  {product_ids: [...]} (max 500) -> {added, already}
Record action `costing_party_product.unlink`: entity type `costing_party_product`, entity id =
`customer_costing_products.id`, WINDOW_REVERSIBLE, permission `products.party_costing.manage`.

Choices the contract leaves open (the coder follows these):
  * PUT answers 200 (create and update alike) with the Party JSON.
  * POST answers 200 or 201; an unknown customer or no profile is 404; an unknown product id is
    404 or 422 and adds nothing at all.
  * `already` counts ids that were already on the party, `added` the new ones (a repeated id inside
    one request counts once).
  * Audit entity types: `customer_costing_profiles` (entity_id = customer_id) and
    `customer_costing_products` (entity_id = its id).
"""
from __future__ import annotations

import uuid

import pytest

from tests.support.costing_env import COST_VIEW, MANAGE, costing_env  # noqa: F401

A = pytest.approx


def _manager_env(costing_env):
    e = costing_env
    w = e.workbook()
    e.as_user(e.manager())
    return e, w


def _fresh_customer(e, code="304-R100", name="FRESH TRADING SDN BHD"):
    c = e.customer(code=code, name=name)
    e.db.commit()
    return c


def _count(e, model_name, **flt):
    import app.models.costing as m

    e.db.expire_all()
    return e.db.query(getattr(m, model_name)).filter_by(**flt).count()


# ------------------------------------------------------------------ AC-PC-01 the profile


def test_ac_pc_01_a_customer_starts_without_a_profile(costing_env):
    e, w = _manager_env(costing_env)
    c = _fresh_customer(e)
    r = e.get(f"/parties/{c.id}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["has_profile"] is False
    assert (body["customer_id"], body["customer_code"], body["customer_name"]) == (
        c.id, "304-R100", "FRESH TRADING SDN BHD")
    assert body["markup_pct"] is None and body["product_count"] == 0


def test_ac_pc_01_put_creates_a_profile_and_a_second_put_updates_the_same_one(costing_env):
    e, w = _manager_env(costing_env)
    c = _fresh_customer(e)
    r = e.put(f"/parties/{c.id}", {"markup_pct": 8, "cost_method": None, "is_active": True})
    assert r.status_code == 200, r.text
    assert r.json() == {
        "customer_id": c.id, "customer_code": "304-R100", "customer_name": "FRESH TRADING SDN BHD",
        "has_profile": True, "markup_pct": 8.0, "cost_method": None, "is_active": True, "product_count": 0,
    }

    r2 = e.put(f"/parties/{c.id}", {"markup_pct": 12.5, "cost_method": "average", "is_active": False})
    assert r2.status_code == 200, r2.text
    assert (r2.json()["markup_pct"], r2.json()["cost_method"], r2.json()["is_active"]) == (12.5, "average", False)
    assert _count(e, "CustomerCostingProfile", customer_id=c.id) == 1  # at most one per customer
    assert e.get(f"/parties/{c.id}").json()["markup_pct"] == 12.5


@pytest.mark.parametrize("method", [None, "primary", "average", "last_po"])
def test_ac_pc_01_the_allowed_methods(costing_env, method):
    e, w = _manager_env(costing_env)
    c = _fresh_customer(e)
    r = e.put(f"/parties/{c.id}", {"markup_pct": 5, "cost_method": method, "is_active": True})
    assert r.status_code == 200, r.text
    assert r.json()["cost_method"] == method


@pytest.mark.parametrize("body", [
    {"markup_pct": 5, "cost_method": "selected", "is_active": True},  # AC-LC-06
    {"markup_pct": 5, "cost_method": "bogus", "is_active": True},
    {"markup_pct": -0.1, "cost_method": None, "is_active": True},
    {"cost_method": None, "is_active": True},  # mark-up is required
    {"markup_pct": None, "cost_method": None, "is_active": True},
])
def test_ac_pc_01_and_lc_06_invalid_profiles_are_422_and_nothing_is_stored(costing_env, body):
    e, w = _manager_env(costing_env)
    c = _fresh_customer(e)
    assert e.put(f"/parties/{c.id}", body).status_code == 422
    assert _count(e, "CustomerCostingProfile", customer_id=c.id) == 0


def test_ac_pc_01_zero_markup_is_allowed(costing_env):
    e, w = _manager_env(costing_env)
    c = _fresh_customer(e)
    assert e.put(f"/parties/{c.id}", {"markup_pct": 0, "cost_method": None, "is_active": True}).status_code == 200


def test_ac_pc_01_unknown_customer_is_404(costing_env):
    e, w = _manager_env(costing_env)
    ghost = str(uuid.uuid4())
    assert e.get(f"/parties/{ghost}").status_code == 404
    assert e.put(f"/parties/{ghost}", {"markup_pct": 5, "cost_method": None, "is_active": True}).status_code == 404


def test_ac_cg_12_the_profile_edit_changes_every_row_in_the_party_view(costing_env):
    e, w = _manager_env(costing_env)
    r = e.put(f"/parties/{w.customer.id}", {"markup_pct": 20, "cost_method": None, "is_active": True})
    assert r.status_code == 200, r.text
    row = e.row_of(e.rows(party_id=w.customer.id, as_of="2026-11-11"), "CGB9032B")
    assert row["markup_pct"] == A(20.0) and row["final"] == A(31.71875 * 1.2, abs=1e-6)
    assert e.get(f"/parties/{w.customer.id}").json()["product_count"] == 2


# ------------------------------------------------------------------ AC-PC-02 the product set


def test_ac_pc_02_add_products_and_adding_twice_is_a_noop(costing_env):
    e, w = _manager_env(costing_env)
    c = _fresh_customer(e)
    e.put(f"/parties/{c.id}", {"markup_pct": 8, "cost_method": None, "is_active": True})

    r = e.post(f"/parties/{c.id}/products", {"product_ids": [w.wb.id, w.tap.id]})
    assert r.status_code in (200, 201), r.text
    assert r.json() == {"added": 2, "already": 0}

    again = e.post(f"/parties/{c.id}/products", {"product_ids": [w.wb.id, w.tap.id]})
    assert again.status_code in (200, 201), again.text
    assert again.json() == {"added": 0, "already": 2}

    mixed = e.post(f"/parties/{c.id}/products", {"product_ids": [w.tap.id, w.sink.id]})
    assert mixed.json() == {"added": 1, "already": 1}
    assert _count(e, "CustomerCostingProduct", customer_id=c.id) == 3
    assert e.get(f"/parties/{c.id}").json()["product_count"] == 3


def test_ac_pc_02_a_repeated_id_inside_one_request_adds_once(costing_env):
    e, w = _manager_env(costing_env)
    c = _fresh_customer(e)
    e.put(f"/parties/{c.id}", {"markup_pct": 8, "cost_method": None, "is_active": True})
    r = e.post(f"/parties/{c.id}/products", {"product_ids": [w.sink.id, w.sink.id]})
    assert r.status_code in (200, 201), r.text
    assert r.json()["added"] == 1
    assert _count(e, "CustomerCostingProduct", customer_id=c.id, product_id=w.sink.id) == 1


def test_ac_pc_02_an_added_product_takes_the_partys_markup_until_a_row_markup_is_set(costing_env):
    e, w = _manager_env(costing_env)
    c = _fresh_customer(e)
    e.put(f"/parties/{c.id}", {"markup_pct": 8, "cost_method": None, "is_active": True})
    e.post(f"/parties/{c.id}/products", {"product_ids": [w.tap.id]})
    row = e.row_of(e.rows(party_id=c.id, as_of="2026-11-11"), "T-1001")
    assert (row["markup_pct"], row["markup_source"]) == (A(8.0), "party")
    assert row["final"] == A(88.275 * 1.08, abs=1e-6)
    from app.models.costing import CustomerCostingProduct

    assert e.db.query(CustomerCostingProduct).filter_by(customer_id=c.id).one().markup_pct is None


def test_ac_cg_12_more_than_500_ids_is_422_and_adds_nothing(costing_env):
    e, w = _manager_env(costing_env)
    r = e.post(f"/parties/{w.customer.id}/products", {"product_ids": [str(uuid.uuid4()) for _ in range(501)]})
    assert r.status_code == 422, r.text
    assert _count(e, "CustomerCostingProduct", customer_id=w.customer.id) == 2


def test_ac_cg_12_a_batch_of_500_is_accepted(costing_env):
    """The cap is inclusive: exactly 500 real products are accepted."""
    e, w = _manager_env(costing_env)
    c = _fresh_customer(e)
    e.put(f"/parties/{c.id}", {"markup_pct": 8, "cost_method": None, "is_active": True})
    ids = [e.item(f"CAP-{i:03d}", category=w.cat_taps, list_price="1").id for i in range(500)]
    e.db.commit()
    r = e.post(f"/parties/{c.id}/products", {"product_ids": ids})
    assert r.status_code in (200, 201), r.text
    assert r.json() == {"added": 500, "already": 0}


def test_ac_cg_12_adding_to_a_customer_without_a_profile_is_404(costing_env):
    e, w = _manager_env(costing_env)
    c = _fresh_customer(e)
    r = e.post(f"/parties/{c.id}/products", {"product_ids": [w.wb.id]})
    assert r.status_code == 404, r.text
    assert _count(e, "CustomerCostingProduct", customer_id=c.id) == 0


def test_ac_cg_12_an_unknown_product_id_adds_nothing(costing_env):
    e, w = _manager_env(costing_env)
    c = _fresh_customer(e)
    e.put(f"/parties/{c.id}", {"markup_pct": 8, "cost_method": None, "is_active": True})
    r = e.post(f"/parties/{c.id}/products", {"product_ids": [w.wb.id, str(uuid.uuid4())]})
    assert r.status_code in (404, 422), r.text
    assert _count(e, "CustomerCostingProduct", customer_id=c.id) == 0


def test_ac_pc_02_one_product_can_sit_on_many_parties(costing_env):
    e, w = _manager_env(costing_env)
    other = _fresh_customer(e)
    e.put(f"/parties/{other.id}", {"markup_pct": 15, "cost_method": None, "is_active": True})
    r = e.post(f"/parties/{other.id}/products", {"product_ids": [w.wb.id]})
    assert r.json() == {"added": 1, "already": 0}

    bath = e.row_of(e.rows(party_id=w.customer.id, as_of="2026-11-11"), "CGB9032B")
    fresh = e.row_of(e.rows(party_id=other.id, as_of="2026-11-11"), "CGB9032B")
    assert bath["final"] == A(31.71875 * 1.08, abs=1e-6)
    assert fresh["final"] == A(31.71875 * 1.15, abs=1e-6)
    assert bath["party_product_id"] != fresh["party_product_id"]


# ------------------------------------------------------------------ unlink (deferred action)


def test_ac_cg_12_unlink_is_a_registered_reversible_deferred_action(costing_env):
    import app.services.record_actions  # noqa: F401
    from app.models.costing import CustomerCostingProduct
    from app.services.form_action_grace import WINDOW_REVERSIBLE
    from app.services.form_action_registry import get_action

    action = get_action("costing_party_product.unlink")
    assert action is not None
    assert action.entity_types == ("costing_party_product",)
    assert action.window == WINDOW_REVERSIBLE
    assert action.permission == MANAGE

    e, w = _manager_env(costing_env)
    action.execute(e.db, {"entity_id": w.pp_wb.id})
    e.db.flush()
    remaining = {r.product_id for r in e.db.query(CustomerCostingProduct).filter_by(customer_id=w.customer.id)}
    assert remaining == {w.jac.id}  # only the unlinked pair is gone; the product itself stays
    from app.models.product import Product

    assert e.db.get(Product, w.wb.id) is not None

    action.execute(e.db, {"entity_id": w.pp_wb.id})  # already gone: not an error


def test_ac_pc_09_link_and_unlink_are_audited(costing_env):
    import app.services.record_actions  # noqa: F401
    from app.services.form_action_registry import get_action

    e, w = _manager_env(costing_env)
    c = _fresh_customer(e)
    e.put(f"/parties/{c.id}", {"markup_pct": 8, "cost_method": None, "is_active": True})
    e.post(f"/parties/{c.id}/products", {"product_ids": [w.sink.id]})
    from app.models.costing import CustomerCostingProduct

    link = e.db.query(CustomerCostingProduct).filter_by(customer_id=c.id).one()
    assert [a.action for a in e.audit_rows("customer_costing_products", link.id)] == ["CREATE"]

    get_action("costing_party_product.unlink").execute(e.db, {"entity_id": link.id})
    e.db.commit()
    assert [a.action for a in e.audit_rows("customer_costing_products", link.id)] == ["CREATE", "DELETE"]


# ------------------------------------------------------------------ AC-PC-09 profile audit and masking


def test_ac_pc_09_profile_create_and_edit_are_audited_old_to_new(costing_env):
    e, w = _manager_env(costing_env)
    c = _fresh_customer(e)
    e.put(f"/parties/{c.id}", {"markup_pct": 8, "cost_method": None, "is_active": True})
    e.put(f"/parties/{c.id}", {"markup_pct": 9, "cost_method": "average", "is_active": True})
    audits = e.audit_rows("customer_costing_profiles", c.id)
    assert [a.action for a in audits] == ["CREATE", "UPDATE"]
    assert float(audits[-1].old_values["markup_pct"]) == 8.0
    assert float(audits[-1].new_values["markup_pct"]) == 9.0
    assert audits[-1].old_values["cost_method"] is None and audits[-1].new_values["cost_method"] == "average"
    assert audits[-1].user_id == e.principal["id"]


def test_ac_pc_09_markup_is_a_cost_audit_key_so_history_masks_it():
    """KILL TEST 'mark-up dropped from History masking'. `COST_AUDIT_KEYS` is SUPPLIER-COST-ACCESS's
    (#2319, app/services/cost_access.py); mark-up is on it, so the shared masking hides it."""
    from app.services.cost_access import COST_AUDIT_KEYS, HIDDEN, mask_audit_values

    assert "markup_pct" in COST_AUDIT_KEYS
    old, new, masked = mask_audit_values({"markup_pct": "8.000"}, {"markup_pct": "12.000"})
    assert old == {"markup_pct": HIDDEN} and new == {"markup_pct": HIDDEN} and masked == ["markup_pct"]


def test_ac_pc_09_the_generic_audit_log_never_shows_a_markup_to_a_non_admin(costing_env):
    """A mark-up change sits in `audit_logs`. The generic History route serves a row's history only
    to the entity types it knows (a per-record view permission) and otherwise to audit admins: a
    costing row is not one of the first, so a reader without `products.cost.view` (and a holder who
    is not an admin) is refused and sees no value; an admin reads it."""
    e, w = _manager_env(costing_env)
    assert e.patch_rows({"party_id": w.customer.id, "changes": [{"product_id": w.jac.id, "markup_pct": 15}]}).status_code == 200
    url = "/api/v1/audit/logs/"
    params = {"entity_type": "customer_costing_products", "entity_id": w.pp_jac.id}

    for principal in (e.user(), e.viewer()):
        e.as_user(principal)
        r = e.client.get(url, params=params)
        assert r.status_code == 403, r.text
        assert "15" not in r.text

    e.as_user(e.admin())
    r = e.client.get(url, params=params)
    assert r.status_code == 200, r.text
    assert any(float(x["new_values"]["markup_pct"]) == 15.0 for x in r.json()["data"] if x["action"] == "UPDATE")


def test_ac_pc_09_a_reader_without_cost_view_gets_no_markup_from_history(costing_env):
    e, w = _manager_env(costing_env)
    e.patch_rows({"party_id": w.customer.id, "changes": [{"product_id": w.jac.id, "markup_pct": 15}]})
    e.as_user(e.user())  # no cost view
    r = e.get(f"/rows/{w.jac.id}/history", party_id=w.customer.id)
    assert r.status_code == 403
    assert "15" not in r.text


# ------------------------------------------------------------------ gates


def test_ac_ax_01_profile_routes_need_cost_view_to_read_and_manage_plus_cost_view_to_write(costing_env):
    e, w = _manager_env(costing_env)
    c = _fresh_customer(e)
    body = {"markup_pct": 8, "cost_method": None, "is_active": True}

    e.as_user(e.user())
    assert e.get(f"/parties/{c.id}").status_code == 403

    for principal in (e.viewer(), e.user(MANAGE)):
        e.as_user(principal)
        assert e.put(f"/parties/{c.id}", body).status_code == 403
        assert e.post(f"/parties/{w.customer.id}/products", {"product_ids": [w.tap.id]}).status_code == 403
    assert _count(e, "CustomerCostingProfile", customer_id=c.id) == 0
    assert _count(e, "CustomerCostingProduct", customer_id=w.customer.id) == 2

    e.as_user(e.viewer())
    assert e.get(f"/parties/{w.customer.id}").status_code == 200
