"""NPA-FROM-SI staff surface, red-first: PRODUCT CODES -> the ONE new product code (lineage, mock v3), the exact-set reuse
suggestion, the lineage read and the prefill of current codes.

Card: documentation/plans/procurement/CARD-npa-from-si-07nov.md (rules 3-6). The world fixture
and helpers are the NEW-PRODUCT-APP suite's (same harness, same seeds). Postgres only.
"""
from __future__ import annotations

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
