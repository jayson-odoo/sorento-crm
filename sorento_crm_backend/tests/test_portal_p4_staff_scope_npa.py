"""PORTAL-P4-REQUESTS S5 red tests: the STAFF routes of New Product Application for a salesperson
(`view_own` + `create`, never `view` / `approve` / `open_code`): only their own rows, in the portal's
shape, and every staff write refused. Staff behave as before (control).
"""
from __future__ import annotations

from decimal import Decimal

from tests import _portal_p4_support as s
from tests._portal_p4_npa_support import (  # noqa: F401
    NPA,
    NPA_APPROVE,
    NPA_CREATE,
    NPA_OPEN,
    NPA_VIEW,
    SUB,
    create,
    npa_row,
    scene,
    world,
)


def test_p4_npa_staff_list_shows_every_status_of_their_own_rows_and_nothing_foreign(world):
    w = world
    draft = create(w.rep.portal, w)["id"]
    submitted = create(w.rep.portal, w)["id"]
    s.ok(w.rep.portal.call("POST", f"{SUB}/{submitted}/submit"))
    cancelled = create(w.rep.portal, w)["id"]
    s.ok(w.rep.portal.call("POST", f"{SUB}/{cancelled}/cancel"))
    foreign = create(w.other.portal, w)["id"]
    listed = s.ok(w.staff(w.rep.actor, "GET", NPA)).json()
    got = {r["id"] for r in listed["items"]}
    assert got == {draft, submitted, cancelled}, f"foreign leaked={foreign in got}"
    only = s.ok(w.staff(w.rep.actor, "GET", NPA, params={"status": "cancelled"})).json()
    assert {r["id"] for r in only["items"]} == {cancelled}


def test_p4_npa_staff_detail_foreign_is_404_own_is_200(world):
    w = world
    own, foreign = create(w.rep.portal, w)["id"], create(w.other.portal, w)["id"]
    assert s.ok(w.staff(w.rep.actor, "GET", f"{NPA}/{own}")).json()["id"] == own
    r = w.staff(w.rep.actor, "GET", f"{NPA}/{foreign}")
    assert r.status_code == 404, r.text
    s.not_a_missing_route(r)


def _linked_row(w):
    """An application of `rep` whose first line is linked to a real product (item group, UOM, list price)."""
    from tests._sample_request_seed import make_product

    d = create(w.rep.portal, w)
    product = make_product(w.sc.db)
    row = npa_row(w, d["id"])
    row.lines[0].opened_product_id = product.id
    w.sc.db.commit()
    return d["id"], product


def test_p4_npa_staff_detail_for_a_salesperson_hides_item_group_uom_and_list_price(world):
    w = world
    aid, product = _linked_row(w)
    got = s.ok(w.staff(w.rep.actor, "GET", f"{NPA}/{aid}")).json()
    line = got["lines"][0]
    assert line["opened_product_id"] == product.id  # the link itself is theirs to read
    assert not {"opened_category_name", "opened_base_uom_name", "opened_list_price"} & set(line), line
    assert "Piece" not in str(got) and "100.00" not in str(got)
    # the same shape the portal answers
    assert got == s.ok(w.rep.portal.call("GET", f"{SUB}/{aid}")).json()


def test_p4_npa_staff_detail_for_staff_still_shows_item_group_uom_and_list_price(world):
    w = world
    aid, product = _linked_row(w)
    staff = s.make_user(w.sc.db, perms=[NPA_VIEW], name="ZZT Staff")
    line = s.ok(w.staff(staff, "GET", f"{NPA}/{aid}")).json()["lines"][0]
    assert line["opened_category_name"]
    assert line["opened_base_uom_name"] == "Piece"
    assert Decimal(str(line["opened_list_price"])) == Decimal("100")


def test_p4_npa_staff_write_routes_refuse_a_salesperson(world):
    w = world
    own = create(w.rep.portal, w)["id"]
    s.ok(w.rep.portal.call("POST", f"{SUB}/{own}/submit"))
    draft = create(w.rep.portal, w)["id"]
    before = (npa_row(w, own).status, npa_row(w, draft).status, npa_row(w, draft).remark)
    line_id = npa_row(w, own).lines[0].id
    calls = [
        ("POST", NPA, w.body()),
        ("PUT", f"{NPA}/{draft}", w.body(remark="ZZT staff edit")),
        ("POST", f"{NPA}/{draft}/submit", None),
        ("POST", f"{NPA}/{own}/revise", {"reason": "ZZT staff revise"}),
        ("POST", f"{NPA}/{own}/cancel", None),
        ("POST", f"{NPA}/{own}/approve", None),
        ("POST", f"{NPA}/{own}/reject", {"reason": "ZZT no"}),
        ("POST", f"{NPA}/{own}/lines/{line_id}/close", {"reason": "ZZT no"}),
        ("POST", f"{NPA}/{own}/lines/{line_id}/undo", None),
        ("PUT", f"{NPA}/{own}/feedback", {"lead_time": "3 weeks"}),
        ("POST", f"{NPA}/{draft}/attachments", {"attachment_id": s.uid()}),
        ("GET", f"{NPA}/prefill", None),
    ]
    for method, path, body in calls:
        kw = {"json": body} if body is not None else {}
        if path.endswith("/prefill"):
            kw = {"params": {"stock_inquiry_id": s.uid()}}
        r = w.staff(w.rep.actor, method, path, **kw)
        assert r.status_code == 403, (method, path, r.status_code, r.text)
        s.not_a_missing_route(r)
    after = (npa_row(w, own).status, npa_row(w, draft).status, npa_row(w, draft).remark)
    assert after == before
    from app.models.new_product_application import NewProductApplication

    assert w.sc.db.query(NewProductApplication).filter(NewProductApplication.contact_id == w.rep.contact.id).count() == 2


def test_p4_npa_staff_create_submit_and_edit_are_unchanged_for_a_create_holder(world):
    w = world
    staff = s.make_user(w.sc.db, perms=[NPA_VIEW, NPA_CREATE], name="ZZT Staff")
    r = w.staff(staff, "POST", NPA, json=w.body())
    assert r.status_code == 201, r.text
    assert r.json()["source"] == "staff"
    aid = r.json()["id"]
    assert w.staff(staff, "PUT", f"{NPA}/{aid}", json=w.body(remark="ZZT edit")).status_code == 200
    assert w.staff(staff, "POST", f"{NPA}/{aid}/submit").json()["status"] == "submitted"


def test_p4_npa_staff_approver_and_purchasing_are_unchanged(world):
    w = world
    aid = create(w.rep.portal, w)["id"]
    s.ok(w.rep.portal.call("POST", f"{SUB}/{aid}/submit"))
    approver = s.make_user(w.sc.db, perms=[NPA_VIEW, NPA_APPROVE, NPA_OPEN], name="ZZT Approver")
    assert w.staff(approver, "POST", f"{NPA}/{aid}/approve").json()["status"] == "approved"
    assert w.staff(approver, "PUT", f"{NPA}/{aid}/feedback", json={"lead_time": "3 weeks"}).status_code == 200
