"""NPA-FROM-SI staff surface, red-first: PRODUCT CODES -> the ONE new product code (lineage, mock v3), the exact-set reuse
suggestion, the lineage read and the prefill of current codes.

Card: documentation/plans/procurement/CARD-npa-from-si-07nov.md (rules 3-6). The world fixture
and helpers are the NEW-PRODUCT-APP suite's (same harness, same seeds). Postgres only.
"""
from __future__ import annotations

import pytest

from app.models.base import company_scope

from ._sample_request_seed import MARKER, make_product, second_company
from .test_new_product_application import (  # noqa: F401  (fixtures by import)
    NPA,
    _act,
    _get,
    _inquiry,
    _line,
    sent,
    world,
)


def _make(w, sources, *, user=None, inquiry=None, **line_over):
    body = {
        "stock_inquiry_id": (inquiry or w.inquiry).id,
        "customer_name": f"{MARKER} EXAMPLE DEVELOPER SDN BHD",
        "current_product_ids": sources,
        "lines": [_line(w, **line_over)],
    }
    return w.api.as_(user or w.sales).post(NPA, json=body)


def _draft(w, sources, **kw):
    res = _make(w, sources, **kw)
    assert res.status_code == 201, res.text
    return res.json()


def _approved_with(w, sources, **kw):
    d = _draft(w, sources, **kw)
    assert _act(w, d["id"], "submit", w.sales).status_code == 200
    assert _act(w, d["id"], "approve", w.manager).status_code == 200
    return d


def _new_code(w, aid, action, **json):
    return w.api.as_(w.buyer).post(f"{NPA}/{aid}/new-code/{action}", json=json or None)


def _completed(w, sources, new_product, **kw):
    """An application whose ONE new product code purchasing linked to ``new_product``."""
    d = _approved_with(w, sources, **kw)
    res = _new_code(w, d["id"], "link", product_id=new_product.id)
    assert res.status_code == 200, res.text
    return res.json()


def _suggest(w, ids, user=None):
    res = w.api.as_(user or w.sales).get(f"{NPA}/reuse-suggestions", params={"product_ids": ",".join(ids)})
    assert res.status_code == 200, res.text
    return res.json()


# ------------------------------------------------------------------ PRODUCT CODES (rule 4, mock v3)


def test_product_codes_round_trip_in_the_order_picked(world):
    d = _draft(world, [world.product2.id, world.product.id])
    assert [c["id"] for c in d["current_products"]] == [world.product2.id, world.product.id]
    assert [c["product_code"] for c in d["current_products"]] == ["ZZT-KS2406", "ZZT-KS2433"]
    assert set(d["current_products"][0]) >= {"id", "product_code", "product_name", "is_active"}


def test_the_product_table_is_unchanged_and_takes_no_codes(world):
    res = world.api.as_(world.sales).post(
        NPA, json={"lines": [_line(world, current_product_ids=[world.product.id])]}
    )
    assert res.status_code == 422  # the line keeps today's fields only (extra="forbid")


def test_an_application_without_product_codes_is_allowed(world):
    assert _draft(world, [])["current_products"] == []


def test_the_same_product_code_twice_is_422(world):
    res = _make(world, [world.product.id, world.product.id])
    assert res.status_code == 422
    assert "ZZT-KS2433 is already one of the product codes" in res.text


def test_a_product_code_of_another_company_is_422(world):
    other = second_company(world.db)
    with company_scope(world.db, frozenset({other})):
        foreign = make_product(world.db)
    assert _make(world, [foreign.id]).status_code == 422


def test_an_edit_that_leaves_product_codes_out_keeps_them_and_an_empty_list_clears(world):
    d = _draft(world, [world.product.id])
    res = world.api.as_(world.sales).put(f"{NPA}/{d['id']}", json={"remark": "x"})
    assert res.status_code == 200, res.text
    assert [c["id"] for c in res.json()["current_products"]] == [world.product.id]
    res = world.api.as_(world.sales).put(f"{NPA}/{d['id']}", json={"current_product_ids": []})
    assert res.json()["current_products"] == []


def test_product_codes_are_locked_while_submitted(world):
    d = _draft(world, [world.product.id])
    assert _act(world, d["id"], "submit", world.sales).status_code == 200
    res = world.api.as_(world.sales).put(f"{NPA}/{d['id']}", json={"current_product_ids": []})
    assert res.status_code == 422
    assert "locked" in res.text


def test_the_applicant_can_search_products_to_pick_codes(world):
    res = world.api.as_(world.sales).get(f"{NPA}/products", params={"q": "zzt ks2433"})
    assert res.status_code == 200, res.text
    assert [p["product_code"] for p in res.json()] == ["ZZT-KS2433"]


def test_an_empty_product_search_lists_the_first_active_products(world):
    """Owner hand test 8 Nov 20:45: the Link / current-code pickers open with something to pick."""
    from app.models.product import Product

    rows = world.api.as_(world.buyer).get(f"{NPA}/products", params={"q": ""}).json()
    assert 0 < len(rows) <= 20
    codes = [r["product_code"] for r in rows]
    assert codes == sorted(codes)
    active = {
        pid for (pid,) in world.db.query(Product.id).filter(Product.id.in_([r["id"] for r in rows]),
                                                            Product.is_active.is_(True))
    }
    assert active == {r["id"] for r in rows}
    # The applicant's current-code cell uses the same search.
    assert world.api.as_(world.sales).get(f"{NPA}/products", params={"q": ""}).json() == rows


def test_the_sample_request_keeps_its_empty_search_rule(world):
    from app.services import sample_request_service

    assert sample_request_service.search_products(world.db, "") == []


# ------------------------------------------------------------------ the ONE new product code (Q1')


def test_purchasing_links_the_one_new_code_and_the_application_completes(world):
    newp = make_product(world.db, code="ZZT-KS2496")
    d = _approved_with(world, [world.product.id])
    res = _new_code(world, d["id"], "link", product_id=newp.id)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "completed"
    assert body["new_product_code"] == "ZZT-KS2496"
    assert body["new_code_by_name"] == f"{MARKER} purchasing"
    assert body["new_code_at"]


def test_only_purchasing_links_and_only_on_an_approved_application(world):
    newp = make_product(world.db)
    d = _draft(world, [world.product.id])
    assert _new_code(world, d["id"], "link", product_id=newp.id).status_code == 409
    a = _approved_with(world, [world.product.id])
    res = world.api.as_(world.sales).post(f"{NPA}/{a['id']}/new-code/link", json={"product_id": newp.id})
    assert res.status_code == 403


def test_not_opening_needs_a_reason_and_completes(world):
    d = _approved_with(world, [world.product.id])
    assert _new_code(world, d["id"], "close", reason="").status_code == 422
    res = _new_code(world, d["id"], "close", reason="supplier dropped it")
    assert res.status_code == 200
    assert res.json()["status"] == "completed"
    assert res.json()["new_code_closed_reason"] == "supplier dropped it"


def test_undo_returns_to_approved_and_a_second_link_needs_undo_first(world):
    newp, other = make_product(world.db), make_product(world.db)
    done = _completed(world, [world.product.id], newp)
    assert _new_code(world, done["id"], "link", product_id=other.id).status_code == 409
    res = _new_code(world, done["id"], "undo")
    assert res.status_code == 200
    assert res.json()["status"] == "approved"
    assert res.json()["new_product_id"] is None


def test_a_completed_application_cannot_be_revised_or_cancelled(world):
    newp = make_product(world.db)
    done = _completed(world, [world.product.id], newp)
    assert _act(world, done["id"], "revise", world.sales, reason="change").status_code == 409
    assert _act(world, done["id"], "cancel", world.sales).status_code == 409


# ------------------------------------------------------------------ reuse before create (rule 6)


def test_an_exact_set_suggests_the_code_created_before(world):
    newp = make_product(world.db, code="ZZT-KS2499", name=f"{MARKER} sink no tap hole")
    done = _completed(world, [world.product.id], newp, description="use the existing model but no tap hole")
    [s] = _suggest(world, [world.product.id])
    assert s["product_id"] == newp.id
    assert s["product_code"] == "ZZT-KS2499"
    assert s["application_id"] == done["id"]
    assert s["application_no"] == done["application_no"]
    assert s["description"] == "use the existing model but no tap hole"
    assert s["created_at"]


def test_order_of_the_product_codes_does_not_matter(world):
    newp = make_product(world.db)
    _completed(world, [world.product.id, world.product2.id], newp)
    assert [s["product_id"] for s in _suggest(world, [world.product2.id, world.product.id])] == [newp.id]


def test_a_subset_or_superset_is_not_suggested(world):
    newp = make_product(world.db)
    _completed(world, [world.product.id, world.product2.id], newp)
    assert _suggest(world, [world.product.id]) == []
    extra = make_product(world.db)
    assert _suggest(world, [world.product.id, world.product2.id, extra.id]) == []


def test_no_codes_suggest_nothing(world):
    newp = make_product(world.db)
    _completed(world, [], newp)
    assert _suggest(world, []) == []


def test_an_open_or_not_opened_application_is_not_suggested(world):
    d = _approved_with(world, [world.product.id])
    assert _suggest(world, [world.product.id]) == []
    assert _new_code(world, d["id"], "close", reason="supplier dropped").status_code == 200
    assert _suggest(world, [world.product.id]) == []


def test_undoing_the_link_stops_the_suggestion(world):
    newp = make_product(world.db)
    done = _completed(world, [world.product.id], newp)
    assert _new_code(world, done["id"], "undo").status_code == 200
    assert _suggest(world, [world.product.id]) == []


def test_newest_first_and_at_most_three(world):
    made = []
    for _ in range(4):
        newp = make_product(world.db)
        _completed(world, [world.product.id], newp)
        made.append(newp.id)
    assert [s["product_id"] for s in _suggest(world, [world.product.id])] == list(reversed(made))[:3]


def test_the_detail_carries_its_suggestions_and_never_applies_them(world):
    newp = make_product(world.db)
    _completed(world, [world.product.id], newp)
    d = _draft(world, [world.product.id], user=world.sales_b)
    detail = _get(world, d["id"])
    assert [s["product_code"] for s in detail["suggestions"]] == [newp.product_code]
    assert detail["new_product_id"] is None  # shown, never applied


def test_an_application_is_not_suggested_to_itself(world):
    newp = make_product(world.db)
    done = _completed(world, [world.product.id], newp)
    assert _get(world, done["id"])["suggestions"] == []


# ------------------------------------------------------------------ lineage (rule 5)


def test_lineage_of_the_new_code_and_of_its_source(world):
    newp = make_product(world.db, code="ZZT-KS2498")
    done = _completed(world, [world.product.id, world.product2.id], newp, description="basin + cabinet set")
    res = world.api.as_(world.viewer).get(f"{NPA}/lineage", params={"product_id": newp.id})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["made_from_this"] == []
    [row] = body["created_from"]
    assert [c["product_code"] for c in row["current_products"]] == ["ZZT-KS2433", "ZZT-KS2406"]
    assert row["application_no"] == done["application_no"]
    assert row["application_id"] == done["id"]
    assert row["description"] == "basin + cabinet set"
    assert row["product_code"] == "ZZT-KS2498"
    src = world.api.as_(world.viewer).get(f"{NPA}/lineage", params={"product_id": world.product.id}).json()
    assert src["created_from"] == []
    assert [r["product_code"] for r in src["made_from_this"]] == ["ZZT-KS2498"]


def test_lineage_hides_the_application_from_a_product_viewer_without_npa_access(world):
    newp = make_product(world.db)
    _completed(world, [world.product.id], newp)
    res = world.api.as_(world.stranger).get(f"{NPA}/lineage", params={"product_id": newp.id})
    assert res.status_code == 403


# ------------------------------------------------------------------ prefill (rule 3, Q3 (a))


def test_prefill_picks_the_product_code_only_on_an_exact_single_code(world):
    exact = _inquiry(world.db, product_code="  zzt-ks2433 ")
    body = world.api.as_(world.sales).get(f"{NPA}/prefill", params={"stock_inquiry_id": exact.id}).json()
    assert body["current_product_ids"] == [world.product.id]
    assert [p["product_code"] for p in body["current_products"]] == ["ZZT-KS2433"]
    assert body["lines"][0]["proposed_code"] == "zzt-ks2433"  # today's line field, unchanged
    several = world.api.as_(world.sales).get(f"{NPA}/prefill", params={"stock_inquiry_id": world.inquiry.id}).json()
    assert several["current_product_ids"] == []
    near = _inquiry(world.db, product_code="ZZT-KS243")
    assert world.api.as_(world.sales).get(f"{NPA}/prefill", params={"stock_inquiry_id": near.id}).json()[
        "current_product_ids"
    ] == []


def test_prefill_copies_the_inquiry_remark(world):
    si = _inquiry(world.db, remark="Customer wants matte finish")
    body = world.api.as_(world.sales).get(f"{NPA}/prefill", params={"stock_inquiry_id": si.id}).json()
    assert body["remark"] == "Customer wants matte finish"


# ------------------------------------------------------------------ purchasing's ask on the SI (rules 1-2)

SI = "/api/v1/procurement/stock-inquiries"


def _put_si(w, si, user, **body):
    return w.api.as_(user).put(f"{SI}/{si.id}", json=body)


def test_purchasing_asks_for_an_npa_and_the_server_stamps_who_and_when(world):
    si = _inquiry(world.db)
    res = _put_si(world, si, world.buyer, npa_requested=True)
    assert res.status_code == 200, res.text
    world.db.refresh(si)
    assert si.npa_requested is True
    assert si.npa_requested_by == world.buyer
    assert si.npa_requested_at is not None
    detail = world.api.as_(world.buyer).get(f"{SI}/{si.id}").json()
    assert detail["npa_requested"] is True
    assert detail["npa_requested_by_name"] == f"{MARKER} purchasing"


def test_unticking_clears_who_and_when(world):
    si = _inquiry(world.db)
    assert _put_si(world, si, world.buyer, npa_requested=True).status_code == 200
    assert _put_si(world, si, world.buyer, npa_requested=False).status_code == 200
    world.db.refresh(si)
    assert (si.npa_requested, si.npa_requested_by, si.npa_requested_at) == (False, None, None)


def test_the_ask_is_a_response_write_refused_outside_the_response_stage(world):
    si = _inquiry(world.db, status="pending_project_sales")
    res = _put_si(world, si, world.buyer, npa_requested=True)
    assert res.status_code == 422
    world.db.refresh(si)
    assert si.npa_requested is False
    # An echo of the current value is not a write (the edit form posts the whole entity).
    assert _put_si(world, si, world.buyer, npa_requested=False).status_code == 200


def test_the_reply_sentence_follows_the_ask_until_a_live_application_exists(world):
    from app.services import new_product_application_service as svc

    si = _inquiry(world.db)
    assert svc.npa_next_step_sentence(world.db, si) is None
    si.npa_requested = True
    world.db.flush()
    assert svc.npa_next_step_sentence(world.db, si) == svc.NPA_NEXT_STEP
    d = _draft(world, [], inquiry=si)
    assert svc.npa_next_step_sentence(world.db, si) is None
    assert _act(world, d["id"], "cancel", world.sales, reason="customer left").status_code == 200
    assert svc.npa_next_step_sentence(world.db, si) == svc.NPA_NEXT_STEP


def test_the_summary_lists_each_created_code_with_its_current_codes(world):
    newp = make_product(world.db, code="ZZT-KS2497")
    done = _completed(world, [world.product.id], newp)
    listed = world.api.as_(world.admin).get(NPA, params={"stock_inquiry_id": world.inquiry.id}).json()["items"]
    row = next(r for r in listed if r["id"] == done["id"])
    [code] = row["created_codes"]
    assert code["product_code"] == "ZZT-KS2497"
    assert code["current_codes"] == ["ZZT-KS2433"]
    assert code["created_at"]


def test_the_detail_carries_its_stock_inquiry_for_the_tab(world):
    d = _draft(world, [])
    si = _get(world, d["id"])["stock_inquiry"]
    assert si["id"] == world.inquiry.id
    assert si["inquiry_number"] == world.inquiry.inquiry_number
    assert si["status"] == "responded"
    assert si["purchasing_response"] == world.inquiry.purchasing_response
    no_si = world.api.as_(world.sales).post(NPA, json={"lines": [_line(world)]}).json()
    assert _get(world, no_si["id"])["stock_inquiry"] is None


def test_the_new_code_carries_the_values_autocount_set(world):
    newp = make_product(world.db)
    done = _completed(world, [world.product.id], newp)
    facts = _get(world, done["id"])["new_product_facts"]
    assert set(facts) == {"opened_category_name", "opened_base_uom_name", "opened_list_price", "opened_supplier_name"}
    assert facts["opened_list_price"] == "100.00"
    assert _get(world, _draft(world, [])["id"])["new_product_facts"] is None


def test_lineage_hides_application_detail_from_a_product_viewer(world, monkeypatch):
    from app.api.v1.procurement import new_product_applications as route

    newp = make_product(world.db)
    _completed(world, [world.product.id], newp)
    monkeypatch.setattr(route, "permission_slugs", lambda db, uid: {route.PRODUCTS_VIEW})
    world_perms_viewer = world.viewer  # holds VIEW in the route gate; the actor reads products view only
    [row] = world.api.as_(world_perms_viewer).get(f"{NPA}/lineage", params={"product_id": newp.id}).json()["created_from"]
    assert not ({"application_id", "customer_name", "project_name", "expected_qty"} & set(row))
    assert row["application_no"]


@pytest.mark.parametrize(
    "method,path,code",
    [
        ("get", "/products?q=x", 403),
        ("get", "/reuse-suggestions?product_ids=", 403),
        ("post", "/{aid}/new-code/link", 404),
        ("post", "/{aid}/purchasing-response/reply", 404),
    ],
)
def test_own_only_staff_are_refused_the_new_staff_routes_by_the_guard(world, method, path, code):
    """`view_own` + `create`: `create` alone passes each route's own permission check, so only the
    own-scope guard (`new_product_application_own_scope`) can refuse."""
    from app.services.user_service import UserPermissionService

    d = _draft(world, [])  # raised by sales A, not the caller
    held = {"procurement.new_product_applications.view_own", "procurement.new_product_applications.create"}
    names = ("get_user_permission_slugs", "check_user_has_permission", "check_user_has_any_permission")
    # Swapped and put back by hand: a monkeypatch undo would run after the world fixture's own
    # restore and leave these fakes on the class for the next test in the worker.
    saved = {n: getattr(UserPermissionService, n) for n in names}
    UserPermissionService.get_user_permission_slugs = lambda self, uid: set(held)
    UserPermissionService.check_user_has_permission = lambda self, uid, s: s in held
    UserPermissionService.check_user_has_any_permission = lambda self, uid, ss: bool(held & set(ss))
    try:
        url = f"{NPA}{path.format(aid=d['id'])}"
        kw = {"json": {"product_id": world.product.id, "purchasing_response": "x"}} if method == "post" else {}
        res = getattr(world.api.as_(world.stranger), method)(url, **kw)
    finally:
        for n, f in saved.items():
            setattr(UserPermissionService, n, f)
    assert res.status_code == code, res.text


def test_undoing_an_old_per_row_link_keeps_a_new_code_application_completed(world):
    newp, rowp = make_product(world.db), make_product(world.db)
    body = {"current_product_ids": [world.product.id], "lines": [_line(world), _line(world, proposed_code="B")]}
    d = world.api.as_(world.sales).post(NPA, json=body).json()
    assert _act(world, d["id"], "submit", world.sales).status_code == 200
    assert _act(world, d["id"], "approve", world.manager).status_code == 200
    line = d["lines"][0]["id"]
    assert world.api.as_(world.buyer).post(f"{NPA}/{d['id']}/lines/{line}/link", json={"product_id": rowp.id}).status_code == 200
    assert _new_code(world, d["id"], "link", product_id=newp.id).json()["status"] == "completed"
    res = world.api.as_(world.buyer).post(f"{NPA}/{d['id']}/lines/{line}/undo")
    assert res.status_code == 200
    assert res.json()["status"] == "completed"
    assert res.json()["new_product_id"] == newp.id


def test_an_undone_reply_restores_who_and_when_with_the_ask(world):
    import app.services.form_actions  # noqa: F401  (declares the actions)
    from app.services.form_action_registry import get_action

    si = _inquiry(world.db)
    action = get_action("si.purchasing_respond")
    prior = action.capture(world.db, {"inquiry_id": si.id, "inquiry_data": {"npa_requested": True}})
    assert {"npa_requested", "npa_requested_by", "npa_requested_at"} <= set(prior)
    assert "npa_requested_by" not in action.capture(world.db, {"inquiry_id": si.id, "inquiry_data": {}})


def test_saving_an_older_line_without_brand_keeps_its_brand(world):
    res = world.api.as_(world.sales).post(NPA, json={"lines": [_line(world)]})  # _line sends brand_id
    d = res.json()
    line = d["lines"][0]
    assert line["brand_id"] == world.refs.brand
    kept = {k: line[k] for k in ("id", "proposed_code", "description", "expected_qty")}
    res = world.api.as_(world.sales).put(f"{NPA}/{d['id']}", json={"lines": [kept]})
    assert res.status_code == 200, res.text
    assert res.json()["lines"][0]["brand_id"] == world.refs.brand
    res = world.api.as_(world.sales).put(f"{NPA}/{d['id']}", json={"lines": [{**kept, "brand_id": None}]})
    assert res.json()["lines"][0]["brand_id"] is None  # an explicit null still clears


# ------------------------------------------------------------------ owner hand test 8 Nov: no product table from an SI,
# purchasing answers in ONE dialog (PUT /{id}/purchasing-response)


def _si_draft(w, sources=(), **over):
    body = {"stock_inquiry_id": w.inquiry.id, "current_product_ids": list(sources), "remark": "mirror 600 x 900", **over}
    res = w.api.as_(w.sales).post(NPA, json=body)
    assert res.status_code == 201, res.text
    return res.json()


def _si_approved(w, sources=(), **over):
    d = _si_draft(w, sources, **over)
    res = _act(w, d["id"], "submit", w.sales)
    assert res.status_code == 200, res.text
    assert _act(w, d["id"], "approve", w.manager).status_code == 200
    return d


def _respond(w, aid, user=None, **body):
    return w.api.as_(user or w.buyer).put(f"{NPA}/{aid}/purchasing-response", json=body)


def test_an_application_from_a_stock_inquiry_submits_without_product_rows(world):
    d = _si_draft(world, [world.product.id])
    assert d["lines"] == []
    assert _act(world, d["id"], "submit", world.sales).status_code == 200


def test_a_standalone_application_needs_its_remark(world):
    # Owner hand test 9 Nov: product rows are gone; REMARK says what new product is wanted.
    d = world.api.as_(world.sales).post(NPA, json={"current_product_ids": [world.product.id]}).json()
    res = _act(world, d["id"], "submit", world.sales)
    assert res.status_code == 422
    assert "REMARK" in res.text


def test_purchasing_links_an_existing_code_with_lead_time_and_cost_in_one_save(world):
    newp = make_product(world.db, code="ZZT-KS2495")
    d = _si_approved(world, [world.product.id])
    res = _respond(world, d["id"], outcome="link", product_id=newp.id, lead_time="8 weeks", cost_price="210.50")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "completed"
    assert body["new_product_id"] == newp.id
    assert body["new_product_code"] == "ZZT-KS2495"
    assert body["new_code_text"] is None
    assert body["lead_time"] == "8 weeks"
    assert body["cost_price"] == "210.50"
    assert body["feedback_by_name"] == f"{MARKER} purchasing"
    assert body["new_code_by_name"] == f"{MARKER} purchasing"


def test_a_new_code_purchasing_types_completes_and_resolves_once_autocount_sends_it(world):
    d = _si_approved(world, [world.product.id])
    res = _respond(world, d["id"], outcome="new", new_code="zzt-mir-6090")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "completed"
    assert body["new_product_id"] is None
    assert body["new_code_text"] == "zzt-mir-6090"
    assert body["new_product_code"] == "zzt-mir-6090"
    assert _suggest(world, [world.product.id])[0]["product_code"] == "zzt-mir-6090"
    # AutoCount sends it: the typed code now names that product (exact code, case folded).
    later = make_product(world.db, code="ZZT-MIR-6090")
    detail = _get(world, d["id"])
    assert detail["new_product_id"] == later.id
    assert detail["new_product_code"] == "ZZT-MIR-6090"
    lineage = world.api.as_(world.viewer).get(f"{NPA}/lineage", params={"product_id": later.id}).json()
    assert [r["application_no"] for r in lineage["created_from"]] == [d["application_no"]]
    assert lineage["created_from"][0]["description"] == "mirror 600 x 900"  # why: the remark (no rows)


def test_a_typed_code_that_already_exists_links_that_product(world):
    d = _si_approved(world, [world.product.id])
    res = _respond(world, d["id"], outcome="new", new_code=" zzt-ks2406 ")
    assert res.json()["new_product_id"] == world.product2.id


def test_a_new_code_needs_the_code_and_not_opening_is_no_longer_an_outcome(world):
    """Owner 8 Nov 09:30: "not opening should be considered Reject" -> the Reject button."""
    d = _si_approved(world)
    assert _respond(world, d["id"], outcome="new", new_code="  ").status_code == 422
    assert _respond(world, d["id"], outcome="not_opening", reason="supplier cannot make it").status_code == 422
    assert _get(world, d["id"])["status"] == "approved"


def test_clearing_the_outcome_returns_to_approved_and_keeps_lead_time(world):
    newp = make_product(world.db)
    d = _si_approved(world)
    assert _respond(world, d["id"], outcome="link", product_id=newp.id, lead_time="2 weeks").status_code == 200
    res = _respond(world, d["id"], outcome=None)
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "approved"
    assert (body["new_product_id"], body["new_code_text"], body["new_code_closed_reason"]) == (None, None, None)
    assert body["lead_time"] == "2 weeks"


def test_lead_time_and_cost_alone_do_not_complete(world):
    d = _si_approved(world)
    res = _respond(world, d["id"], lead_time="3 weeks", cost_price="99")
    assert res.status_code == 200
    assert res.json()["status"] == "approved"
    assert res.json()["cost_price"] == "99.00"


def test_only_purchasing_and_only_on_approved_or_completed(world):
    d = _si_draft(world)
    assert _respond(world, d["id"], outcome="new", new_code="ZZT-X").status_code == 409
    a = _si_approved(world)
    assert _respond(world, a["id"], user=world.sales, outcome="new", new_code="ZZT-X").status_code == 403


def test_a_standalone_application_takes_one_cost_per_row_in_the_same_save(world):
    body = {"lines": [_line(world), _line(world, proposed_code="B")]}
    d = world.api.as_(world.sales).post(NPA, json=body).json()
    assert _act(world, d["id"], "submit", world.sales).status_code == 200
    assert _act(world, d["id"], "approve", world.manager).status_code == 200
    ids = [l["id"] for l in d["lines"]]
    res = _respond(world, d["id"], lines=[{"id": ids[0], "cost_price": "12.5"}, {"id": ids[1], "cost_price": None}])
    assert res.status_code == 200, res.text
    assert [l["cost_price"] for l in res.json()["lines"]] == ["12.50", None]


def test_the_excel_of_an_application_from_an_si_reads_the_inquiry(world):
    from io import BytesIO

    import openpyxl

    from app.models.new_product_application import NewProductApplication
    from app.services.npa_xlsx import to_xlsx

    d = _si_approved(world, [world.product.id])
    assert _respond(world, d["id"], lead_time="8 weeks", cost_price="210").status_code == 200
    app_row = world.db.get(NewProductApplication, d["id"])
    data, _name = to_xlsx(world.db, app_row)
    ws = openpyxl.load_workbook(BytesIO(data)).worksheets[0]
    rows = {ws.cell(row=r, column=1).value: ws.cell(row=r, column=2).value for r in range(1, ws.max_row + 1)}
    assert rows["PRODUCT CODE:"] == world.inquiry.product_code
    assert rows["PRODUCT TYPE:"] == world.inquiry.item_description
    assert rows["QTY:"] == 55
    assert rows["COST:"] == 210
    assert rows["LEADTIME:"] == "8 weeks"


# ------------------------------------------------------------------ security round 3: another salesperson's REMARK


def test_the_remark_why_is_for_npa_viewers_only(world, monkeypatch):
    from app.api.v1.procurement import new_product_applications as route

    d = _si_approved(world, [world.product.id], remark="for Hotel X, level 3 fit-out")
    assert _respond(world, d["id"], outcome="new", new_code="ZZT-MIR-7070").status_code == 200
    later = make_product(world.db, code="ZZT-MIR-7070")
    # an NPA viewer sees the remark
    full = world.api.as_(world.viewer).get(f"{NPA}/lineage", params={"product_id": later.id}).json()
    assert full["created_from"][0]["description"] == "for Hotel X, level 3 fit-out"
    # a product viewer gets the inquiry's product text instead, never the remark
    monkeypatch.setattr(route, "permission_slugs", lambda db, uid: {route.PRODUCTS_VIEW})
    row = world.api.as_(world.viewer).get(f"{NPA}/lineage", params={"product_id": later.id}).json()["created_from"][0]
    assert "Hotel X" not in str(row)
    assert row["description"] == world.inquiry.item_description


def test_a_create_only_salesperson_does_not_see_another_salespersons_remark(world):
    d = _si_approved(world, [world.product.id], remark="for Hotel X, level 3 fit-out")
    assert _respond(world, d["id"], outcome="new", new_code="ZZT-MIR-7171").status_code == 200
    got = _suggest(world, [world.product.id], user=world.sales_b)  # create only
    assert "Hotel X" not in str(got)
    assert got[0]["description"] == world.inquiry.item_description



# ------------------------------------------------------------------ owner 8 Nov 09:30: purchasing Reject (like the SI)


def _reject(w, aid, user=None, **body):
    return w.api.as_(user or w.buyer).post(f"{NPA}/{aid}/purchasing-reject", json=body)


def test_purchasing_rejects_an_approved_application_with_a_reason(world):
    d = _si_approved(world)
    world.sent.clear()
    res = _reject(world, d["id"], reason="supplier cannot make it")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "rejected"
    assert body["status_label"] == "Rejected"
    assert body["reject_reason"] == "supplier cannot make it"
    assert body["decided_by_name"] == f"{MARKER} purchasing"
    assert any(t == "new_product_application_rejected" or "reject" in str(t) for (_u, t, e) in world.sent if e == d["id"])


def test_purchasing_reject_needs_a_reason_open_code_and_an_approved_application(world):
    d = _si_approved(world)
    assert _reject(world, d["id"], reason="  ").status_code == 422
    assert _reject(world, d["id"], user=world.sales, reason="x").status_code == 403
    draft = _si_draft(world)
    assert _reject(world, draft["id"], reason="x").status_code == 409


def test_a_purchasing_rejected_application_is_fixed_and_submitted_again_by_the_applicant(world):
    d = _si_approved(world)
    assert _reject(world, d["id"], reason="wrong size").status_code == 200
    res = world.api.as_(world.sales).put(f"{NPA}/{d['id']}", json={"remark": "size 600 x 1000"})
    assert res.status_code == 200, res.text
    assert _act(world, d["id"], "submit", world.sales).status_code == 200


def test_an_older_not_opening_result_reads_as_rejected(world):
    d = _si_approved(world)
    assert _new_code(world, d["id"], "close", reason="supplier dropped it").status_code == 200
    body = _get(world, d["id"])
    assert body["status"] == "completed"
    assert body["status_label"] == "Rejected"
    assert body["display_status"] == "rejected"  # the pill colour and the filters follow it
    listed = world.api.as_(world.admin).get(NPA, params={"stock_inquiry_id": world.inquiry.id}).json()["items"]
    row = next(r for r in listed if r["id"] == d["id"])
    assert (row["status_label"], row["display_status"]) == ("Rejected", "rejected")


def test_an_older_not_opening_result_no_longer_answers_the_inquirys_ask(world):
    from app.services import new_product_application_service as svc

    si = _inquiry(world.db)
    si.npa_requested = True
    world.db.flush()
    d = _si_approved(world, stock_inquiry_id=si.id)
    assert svc.npa_next_step_sentence(world.db, si) is None  # a live application answers it
    assert _new_code(world, d["id"], "close", reason="supplier dropped it").status_code == 200
    assert svc.npa_next_step_sentence(world.db, si) == svc.NPA_NEXT_STEP


# ------------------------------------------------------------------ owner 8 Nov 15:10: the SI's Edit purchasing response
# (Save only / Update & Reply, the same dialog component; the reply goes through the SI's conversation)


@pytest.fixture()
def reply_spy(monkeypatch):
    """Captures the respond_io enqueue. Owner 8 Nov 17:35: the NPA's Update & Reply sends its own
    use case (new_product_application_update) through the shared worker send."""
    from app.services import queue_service, respond_identifier

    sent = []
    monkeypatch.setattr(respond_identifier, "resolve_send_identifier", lambda db, raw: raw)

    class _Job:
        id = "job-1"

    def capture(fn, *args, **kwargs):
        sent.append((fn, args, kwargs))
        return _Job()

    monkeypatch.setattr(queue_service, "enqueue_job", capture)
    return sent


def test_the_purchasing_response_text_is_saved_like_the_sis(world):
    d = _si_approved(world)
    res = _respond(world, d["id"], purchasing_response="Supplier can cut 600 x 900.", lead_time="8 weeks")
    assert res.status_code == 200, res.text
    assert res.json()["purchasing_response"] == "Supplier can cut 600 x 900."
    assert res.json()["status"] == "approved"  # text alone answers nothing


USE_CASE = "new_product_application_update"


def test_the_npa_update_is_its_own_template_use_case():
    """Owner 8 Nov 17:35 (Q1, Q2): its own use case, mapped on WhatsApp Templates like the SI's,
    with the variables any approved template can map."""
    from app.models.respond_template import TEMPLATE_DEFAULT_USE_CASES
    from app.services.respond_template_service import PARAM_VARIABLES

    assert USE_CASE in TEMPLATE_DEFAULT_USE_CASES
    for var in (
        "entity_number", "inquiry_number", "customer", "project", "product_code",
        "new_product_code", "lead_time", "update", "portal_url", "status", "reason",
    ):
        assert var in PARAM_VARIABLES, var


def _fake_portal_links(monkeypatch):
    """PortalService.submission_link, recorded; like the real one, no contact means no link."""
    from app.services.portal_service import PortalService

    links = []

    def link(self, contact_id, submission_type, entity_id=None, base_url=None, space_id=None):
        links.append((contact_id, submission_type, entity_id, space_id))
        if not contact_id:
            return None
        return f"https://portal.example.com/portal/c/slug/{submission_type}/{entity_id}"

    monkeypatch.setattr(PortalService, "submission_link", link)
    return links


def _raised_in_portal(world, aid, space_id="space-npa"):
    """Owner 8 Nov 17:50: the salesperson raises the NPA in the portal, so it carries their contact."""
    import uuid

    from app.models.access import RespondContact
    from app.models.new_product_application import NewProductApplication

    contact = RespondContact(phone_number=f"+6019{uuid.uuid4().int % 10**8:08d}", name=f"{MARKER} salesperson")
    world.db.add(contact)
    world.db.flush()
    row = world.db.get(NewProductApplication, aid)
    row.contact_id, row.space_id, row.source = contact.id, space_id, "portal"
    world.db.commit()
    return contact.id


def test_update_and_reply_sends_the_npa_use_case_with_the_npa_link(world, reply_spy, monkeypatch):
    from app.tasks.respond_io_tasks import send_new_product_application_respond_message

    links = _fake_portal_links(monkeypatch)
    world.inquiry.respond_inbox_url = "https://app.respond.io/space/1/inbox/901234"
    world.db.flush()
    newp = make_product(world.db, code="ZZT-RPL-1")
    d = _si_approved(world)
    contact_id = _raised_in_portal(world, d["id"])
    assert _get(world, d["id"])["can_reply"] is True
    res = world.api.as_(world.buyer).post(
        f"{NPA}/{d['id']}/purchasing-response/reply",
        json={"purchasing_response": "Code opened.", "outcome": "link", "product_id": newp.id, "lead_time": "8 weeks"},
    )
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "completed"
    [(fn, args, kwargs)] = reply_spy
    assert fn is send_new_product_application_respond_message
    assert kwargs.get("queue_name") == "respond_io"
    inquiry_id, identifier, text = args[:3]
    extra = args[6]
    # Logged, mirrored and webhooked on the SI's conversation exactly as the SI's reply (review
    # should-fix 1); only the template use case is the NPA's.
    assert (inquiry_id, identifier) == (str(world.inquiry.id), "901234")
    # Q3 + 17:50: View opens the NPA portal page for the contact who raised it, the SI's link mechanism.
    assert links == [(contact_id, "new_product_application", d["id"], "space-npa")]
    npa_url = f"https://portal.example.com/portal/c/slug/new_product_application/{d['id']}"
    assert extra["update"] == "Code opened."
    assert extra["portal_url"] == npa_url
    assert extra["entity_number"] == d["application_no"]
    assert extra["new_product_code"] == "ZZT-RPL-1" and extra["lead_time"] == "8 weeks"
    assert extra["status"] == "Completed"
    # Q4: an unmapped use case sends this text in the window, as the SI's does; it never says Stock Inquiry.
    assert "stock inquiry" not in text.lower()
    assert text.splitlines()[0] == "There is a response to your new product application:"
    assert f"{d['application_no']}: Code opened." in text
    assert "New product code: ZZT-RPL-1" in text and "Lead time: 8 weeks" in text
    assert text.rstrip().endswith(npa_url)


def test_a_text_only_si_chat_reply_moves_the_npa_to_responded_like_the_si(world, reply_spy, monkeypatch):
    """Owner re-test 9 Nov ~12:35: the SI goes Responded on Update & Reply
    (procurement_service.update_inquiry_and_reply); the NPA does the same, and says so in the reply."""
    _fake_portal_links(monkeypatch)
    world.inquiry.respond_inbox_url = "https://app.respond.io/space/1/inbox/901234"
    world.db.flush()
    d = _si_approved(world)
    _raised_in_portal(world, d["id"])
    res = world.api.as_(world.buyer).post(
        f"{NPA}/{d['id']}/purchasing-response/reply", json={"purchasing_response": "Supplier quotes 6 weeks."}
    )
    assert res.status_code == 200, res.text
    assert (res.json()["status"], res.json()["status_label"]) == ("responded", "Responded")
    [(_fn, args, _kw)] = reply_spy
    assert args[6]["status"] == "Responded"


def test_a_staff_raised_npa_gets_no_link_and_no_si_fallback(world, reply_spy, monkeypatch):
    """Owner 8 Nov 17:50: staff do not raise NPAs; no contact copy, no SI fallback."""
    links = _fake_portal_links(monkeypatch)
    world.inquiry.respond_inbox_url = "https://app.respond.io/space/1/inbox/901234"
    world.db.flush()
    d = _si_approved(world)
    res = world.api.as_(world.buyer).post(
        f"{NPA}/{d['id']}/purchasing-response/reply", json={"purchasing_response": "Noted."}
    )
    assert res.status_code == 200, res.text
    assert [t for (_c, t, _e, _s) in links] == ["new_product_application"]
    [(_fn, args, _kw)] = reply_spy
    assert args[6]["portal_url"] == ""


def test_the_worker_sends_the_npa_use_case_on_the_sis_conversation(monkeypatch):
    from app.tasks import respond_io_tasks

    seen = {}
    monkeypatch.setattr(respond_io_tasks, "_send_and_log", lambda **kw: seen.update(kw) or {"ok": True})
    respond_io_tasks.send_new_product_application_respond_message(
        "si-1", "901234", "text", "ru-1", "u-1", "space-1", {"update": "x"}
    )
    assert seen["use_case"] == USE_CASE
    # The SI's conversation: same outbox row, n8n webhook table and SLA assignee lookup as the SI's reply.
    assert (seen["business_table"], seen["business_id"]) == ("stock_inquiries", "si-1")
    assert seen["sla_entity_type"] == "stock_inquiry"
    assert seen["extra_context_vars"] == {"update": "x"}


def test_the_npa_template_variables_come_from_the_application(world):
    newp = make_product(world.db, code="ZZT-VAR-NEW")
    d = _si_approved(world, [world.product.id], customer_name="Example Customer", project_name="Tower B")
    assert _respond(
        world, d["id"], purchasing_response="ok", outcome="link", product_id=newp.id, lead_time="6 weeks"
    ).status_code == 200
    from app.models.new_product_application import NewProductApplication
    from app.services import new_product_application_service as svc

    out = svc.template_vars(world.db, world.db.get(NewProductApplication, d["id"]))
    assert out["entity_number"] == d["application_no"]
    assert out["inquiry_number"] == d["stock_inquiry_number"]
    assert out["customer"] == "Example Customer"
    assert out["project"] == "Tower B"
    assert out["product_code"] == world.product.product_code
    assert out["new_product_code"] == "ZZT-VAR-NEW"
    assert out["lead_time"] == "6 weeks"
    assert out["status"] == "Completed"


def test_reply_needs_the_response_text_and_an_inquiry_conversation(world, reply_spy):
    d = _si_approved(world)
    url = f"{NPA}/{d['id']}/purchasing-response/reply"
    assert world.api.as_(world.buyer).post(url, json={"purchasing_response": "  "}).status_code == 422
    standalone = world.api.as_(world.sales).post(NPA, json={"lines": [_line(world)]}).json()
    assert _act(world, standalone["id"], "submit", world.sales).status_code == 200
    assert _act(world, standalone["id"], "approve", world.manager).status_code == 200
    assert _get(world, standalone["id"])["can_reply"] is False
    res = world.api.as_(world.buyer).post(f"{NPA}/{standalone['id']}/purchasing-response/reply", json={"purchasing_response": "x"})
    assert res.status_code == 422
    assert reply_spy == []


def test_reply_is_purchasing_only(world, reply_spy):
    d = _si_approved(world)
    res = world.api.as_(world.sales).post(f"{NPA}/{d['id']}/purchasing-response/reply", json={"purchasing_response": "x"})
    assert res.status_code == 403
    assert reply_spy == []


def _closed_si_refusal(world, monkeypatch):
    """The SI's own Update & Reply on a closed inquiry: its 422 sentence."""
    from app.schemas.procurement import StockInquiryUpdate
    from app.services.error_handler import AppException
    from app.services.procurement_service import StockInquiryService

    with pytest.raises(AppException) as refused:
        StockInquiryService(world.db).update_inquiry_and_reply(
            str(world.inquiry.id), StockInquiryUpdate(purchasing_response="x"), respond_user_id="u-1"
        )
    world.db.rollback()
    assert refused.value.status_code == 422
    return refused.value.message


def test_update_and_reply_refuses_like_the_si_outside_its_response_stage(world, reply_spy, monkeypatch):
    """Crew answer 8 Nov (same component as the SI): the SI's guard, the SI's sentence, nothing saved or queued."""
    world.inquiry.respond_inbox_url = "https://app.respond.io/space/1/inbox/901234"
    world.db.flush()
    d = _si_approved(world)
    assert _get(world, d["id"])["can_reply"] is True
    world.inquiry.status = "closed"
    world.db.commit()
    # As the SI's page: Update & Reply is drawn only while the SI takes a response.
    assert _get(world, d["id"])["can_reply"] is False
    res = world.api.as_(world.buyer).post(
        f"{NPA}/{d['id']}/purchasing-response/reply", json={"purchasing_response": "Code opened.", "lead_time": "9 weeks"}
    )
    assert res.status_code == 422, res.text
    after = _get(world, d["id"])
    assert (after["purchasing_response"], after["lead_time"]) == (None, None)
    assert reply_spy == []
    si_message = _closed_si_refusal(world, monkeypatch)
    assert si_message and res.json()["message"] == si_message


def test_save_only_stays_allowed_on_a_closed_si(world, reply_spy):
    d = _si_approved(world)
    world.inquiry.status = "closed"
    world.db.commit()
    res = _respond(world, d["id"], purchasing_response="Noted for the record.")
    assert res.status_code == 200, res.text
    assert res.json()["purchasing_response"] == "Noted for the record."
    assert reply_spy == []


def test_a_reply_that_cannot_be_sent_saves_nothing(world, reply_spy):
    world.inquiry.respond_inbox_url = None  # the SI's own refusal: no conversation to reply into
    world.db.flush()
    d = _si_approved(world)
    res = world.api.as_(world.buyer).post(
        f"{NPA}/{d['id']}/purchasing-response/reply", json={"purchasing_response": "Code opened.", "lead_time": "9 weeks"}
    )
    assert res.status_code == 422
    after = _get(world, d["id"])
    assert (after["purchasing_response"], after["lead_time"]) == (None, None)
    assert reply_spy == []


def test_save_only_sends_nothing(world, reply_spy):
    world.inquiry.respond_inbox_url = "https://app.respond.io/space/1/inbox/901234"
    world.db.flush()
    d = _si_approved(world)
    assert _respond(world, d["id"], purchasing_response="Supplier can cut 600 x 900.").status_code == 200
    assert reply_spy == []


# ------------------------------------------------------------------ crew pass 8 Nov: long project names


LONG_PROJECT = ("CADANGAN PEMBANGUNAN BERCAMPUR 2 BLOK PANGSAPURI SERVIS 38 TINGKAT " * 9).strip()


def test_a_project_name_over_255_characters_is_stored_in_full(world):
    assert len(LONG_PROJECT) > 500
    d = _si_draft(world, project_name=LONG_PROJECT)
    assert _get(world, d["id"])["project_name"] == LONG_PROJECT


def test_an_application_raised_from_an_si_with_a_long_project_name_saves(world):
    world.inquiry.project_name = LONG_PROJECT
    world.db.flush()
    prefill = world.api.as_(world.sales).get(f"{NPA}/prefill", params={"stock_inquiry_id": world.inquiry.id})
    assert prefill.status_code == 200, prefill.text
    assert prefill.json()["project_name"] == LONG_PROJECT
    d = _si_draft(world, project_name=prefill.json()["project_name"])
    assert _get(world, d["id"])["project_name"] == LONG_PROJECT
