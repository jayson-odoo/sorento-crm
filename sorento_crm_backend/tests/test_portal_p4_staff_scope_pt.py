"""PORTAL-P4-REQUESTS S7 red tests: the STAFF routes of the Price Tag Request for a salesperson
(`dealer_kit.price_tag_requests.view_own`, never `.view` or `.process`): only their own rows, drafts included;
the designer, claim, transition / void, line price, print-by override and export stay refused (403). Staff
(`.view`) behave as before (control).
"""
from __future__ import annotations

from tests import _portal_p4_support as s
from tests._portal_p4_pt_support import (  # noqa: F401
    PT_CREATE,
    PT_PROCESS,
    PT_VIEW,
    STAFF,
    SUB,
    create,
    pt_row,
    scene,
    submitted,
    world,
)


def test_p4_pt_staff_list_shows_own_rows_drafts_included_and_nothing_foreign(world):
    w = world
    draft = create(w.rep.portal, w)["id"]
    sent = submitted(w.rep.portal, w)
    foreign_draft, foreign_sent = create(w.other.portal, w)["id"], submitted(w.other.portal, w)
    got = s.ok(w.staff(w.rep.actor, "GET", STAFF)).json()
    ids = {r["id"] for r in got["data"]}
    assert ids == {draft, sent}, f"foreign leaked: {ids & {foreign_draft, foreign_sent}}; own draft hidden: {draft not in ids}"
    assert got["pagination"]["total"] == 2
    portal_ids = {r["id"] for r in s.ok(w.rep.portal.call("GET", SUB)).json()["items"]}
    assert ids == portal_ids
    row = next(r for r in got["data"] if r["id"] == draft)
    assert row["portal_draft_at"], "the list must say which row is a draft"


def test_p4_pt_staff_list_draft_status_filter_narrows_to_drafts(world):
    w = world
    draft = create(w.rep.portal, w)["id"]
    sent = submitted(w.rep.portal, w)
    only = s.ok(w.staff(w.rep.actor, "GET", STAFF, params={"status": "draft"})).json()
    assert {r["id"] for r in only["data"]} == {draft}
    assert sent not in {r["id"] for r in only["data"]}
    search = s.ok(w.staff(w.rep.actor, "GET", STAFF, params={"query": pt_row(w, sent).doc_number})).json()
    assert {r["id"] for r in search["data"]} == {sent}


def test_p4_pt_staff_user_default_list_is_unchanged_submitted_rows_of_everyone(world):
    w = world
    mine_draft, mine_sent = create(w.rep.portal, w)["id"], submitted(w.rep.portal, w)
    theirs_sent = submitted(w.other.portal, w)
    staff = s.make_user(w.sc.db, perms=[PT_VIEW, PT_PROCESS], name="ZZT Staff")
    got = {r["id"] for r in s.ok(w.staff(staff, "GET", STAFF)).json()["data"]}
    assert {mine_sent, theirs_sent} <= got and mine_draft not in got


def test_p4_pt_staff_detail_own_is_200_foreign_is_404_staff_sees_both(world):
    w = world
    own, foreign = create(w.rep.portal, w)["id"], create(w.other.portal, w)["id"]
    assert s.ok(w.staff(w.rep.actor, "GET", f"{STAFF}/{own}")).json()["id"] == own
    r = w.staff(w.rep.actor, "GET", f"{STAFF}/{foreign}")
    assert r.status_code == 404, r.text
    s.not_a_missing_route(r)
    staff = s.make_user(w.sc.db, perms=[PT_VIEW], name="ZZT Staff")
    assert w.staff(staff, "GET", f"{STAFF}/{foreign}").status_code == 200


def test_p4_pt_staff_designer_and_process_routes_refuse_a_salesperson(world):
    w = world
    rid = submitted(w.rep.portal, w)
    line_id = s.ok(w.staff(w.rep.actor, "GET", f"{STAFF}/{rid}")).json()["lines"][0]["id"]
    before = (pt_row(w, rid).status, pt_row(w, rid).print_by, pt_row(w, rid).assigned_to_id)
    calls = [
        ("POST", f"{STAFF}/{rid}/claim", None),
        ("POST", f"{STAFF}/{rid}/transition", {"status": "void"}),
        ("PATCH", f"{STAFF}/{rid}", {"print_by": "self"}),
        ("PATCH", f"{STAFF}/{rid}/lines/{line_id}", {"manual_sell_price": "10"}),
        ("POST", f"{STAFF}/{rid}/export", {}),
        ("GET", f"{STAFF}/{rid}/design", None),
        ("PUT", f"{STAFF}/{rid}/design/draft", {"doc": {}}),
        ("POST", f"{STAFF}/line-pricing", {"lines": []}),
    ]
    for method, path, body in calls:
        r = w.staff(w.rep.actor, method, path, **({"json": body} if body is not None else {}))
        assert r.status_code == 403, (method, path, r.status_code, r.text)
        s.not_a_missing_route(r)
    assert (pt_row(w, rid).status, pt_row(w, rid).print_by, pt_row(w, rid).assigned_to_id) == before


def test_p4_pt_staff_process_is_unchanged_for_a_process_holder(world):
    w = world
    rid = submitted(w.rep.portal, w)
    staff = s.make_user(w.sc.db, perms=[PT_VIEW, PT_PROCESS], name="ZZT Marketer")
    r = w.staff(staff, "POST", f"{STAFF}/{rid}/claim")
    assert r.status_code == 200, r.text
    assert pt_row(w, rid).status == "designing"


def test_p4_pt_view_own_alone_is_enough_but_create_alone_is_not(world):
    w = world
    creator = s.make_user(w.sc.db, perms=[PT_CREATE], contact=s.own_contact(w.sc)[0], name="ZZT Create only")
    r = w.staff(creator, "GET", STAFF)
    assert r.status_code == 403, r.text
    s.not_a_missing_route(r)
