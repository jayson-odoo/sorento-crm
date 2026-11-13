"""SPARE-PART-ORDER-REQUEST review round 2 (review-2.md M1, M2, S2, S3, S5), red-first.

Contract: the "Hand-test round" section of
documentation/plans/purchasing/spare-part-order-request-12nov-acceptance-criteria.md, plus the
owner standing rules the review cites ("every column header sorts, server-side").

R1 (M1) the admin's list never shows another user's draft. GUARD: green today. It kills the
   review's mutation (service `list_requests` admin clause `OrderInquiry.state != INQUIRY_DRAFT`
   replaced by `OrderInquiry.id.isnot(None)`): the outsider's and the requester's drafts would
   then be in the admin's ids and both `not in ids` asserts go red.
R2 (M2) the list sorts server-side by Requested by (`sort=requested_by_name`) and by Total
   (`sort=total`), both ways. The seed makes the name order, the total order and the
   submitted_at fallback order all differ, so an unknown sort key cannot pass by accident.
R5 (S2) a stale decision: the approve / reject body carries the `submitted_at` the approver's
   page rendered (the detail returns it). After the requester's pending edit restarted
   approval, a decision sent with the pre-edit value answers 409 with a plain message and
   changes nothing; one sent with the current value goes through.
R6 (S3 c, d) GUARDS: a pending-edit restart sends no purchasing notice (and the approval that
   follows does, so the capture is live); the requester's photo upload while pending is 403
   (and the approver's is not, so the route is live).
R8 (S5) an approver who holds projects.projects.view but not the create grant reaches the list
   route and sees the request they can decide. GUARD on the backend (the route's read
   dependency already accepts either grant); the sidebar half is the FE test.

Postgres only (`blank_session`); every row is seeded here, nothing borrowed.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from ._forms_chain_support import user
from ._spare_part_request_support import (  # noqa: F401  (fixtures)
    CREATE,
    KIND,
    OI_RAISED_NOTICE,
    ROW_ATT,
    SPR,
    TINY_PNG,
    VIEW,
    approve,
    as_inquiry,
    body,
    create,
    line,
    reload,
    role_grant,
    row_for,
    sent,
    staged,
    stub_storage,
    submitted,
    svc,
    world,
)
from .test_spare_part_request_handtest import (  # noqa: F401  (fixture)
    _edit_body,
    _ids,
    _list,
    listed,
)


def _message(res) -> str:
    payload = res.json()
    if isinstance(payload, dict):
        return str(payload.get("message") or payload.get("detail") or "")
    return str(payload)


# =============================================================================
# R1 (M1) - drafts are private, the admin's list included
# =============================================================================


def test_R1_an_admin_never_sees_another_users_draft(listed):
    w = listed
    ids = set(_ids(_list(w, w.admin)))
    assert str(w.other_draft.id) not in ids, "the outsider's draft is private"
    assert str(w.mine_draft.id) not in ids, "the requester's draft is private"
    assert {
        str(w.mine_pending.id), str(w.mine_rejected.id), str(w.mine_raised.id), str(w.other_pending.id),
    } <= ids, "every submitted one is still there"


def test_R1_an_admin_sees_their_own_draft(listed):
    from ._spare_part_request_support import as_inquiry as _as

    w = listed
    own = _as(w.db, svc().create(w.db, body(w), w.admin))
    w.db.commit()
    ids = set(_ids(_list(w, w.admin)))
    assert str(own.id) in ids, "an admin's own draft is theirs, like anyone's"


# =============================================================================
# R2 (M2) - server sort by Requested by and Total
# =============================================================================


@pytest.fixture
def three_requesters(staged):
    """Three pending requests by Carol (total 300), Alice (50) and Bob (1000), created and
    submitted in that order. Name order A, B, C; total order A, C, B; submitted order C, A, B:
    no two agree, so the unknown-key fallback (submitted_at) never passes a name or total sort."""
    w = staged
    people = {}
    lines_for = {
        "carol": None,  # body()'s default: 10 x 25 + 4 x 12.50 = 300
        "alice": [line(w.product_a, w.loc_a, qty="2", unit_price="25.00")],
        "bob": [line(w.product_a, w.loc_a, qty="40", unit_price="25.00")],
    }
    for who in ("carol", "alice", "bob"):
        uid = user(w.db, f"spr {who}")
        role_grant(w.db, uid, CREATE)
        w.db.commit()
        over = {"lines": lines_for[who]} if lines_for[who] else {}
        inquiry = as_inquiry(w.db, svc().create(w.db, body(w, **over), uid))
        w.db.commit()
        svc().submit(w.db, inquiry, uid)
        w.db.commit()
        people[who] = reload(w.db, inquiry)
    w.people = people
    return w


def _sorted_ids(w, sort, direction):
    return _ids(_list(w, w.admin, state=["pending_approval"], sort=sort, dir=direction))


def test_R2_server_sort_by_requested_by_both_ways(three_requesters):
    w = three_requesters
    p = w.people
    by_name = [str(p["alice"].id), str(p["bob"].id), str(p["carol"].id)]
    assert _sorted_ids(w, "requested_by_name", "asc") == by_name
    assert _sorted_ids(w, "requested_by_name", "desc") == by_name[::-1]


def test_R2_server_sort_by_total_both_ways(three_requesters):
    w = three_requesters
    p = w.people
    by_total = [str(p["alice"].id), str(p["carol"].id), str(p["bob"].id)]
    payload = _list(w, w.admin, state=["pending_approval"], sort="total", dir="asc")
    assert _ids(payload) == by_total, [i.get("total") for i in payload["data"]]
    assert _sorted_ids(w, "total", "desc") == by_total[::-1]


def test_R2_the_sorted_totals_are_the_line_sums(three_requesters):
    """The precondition the total sort rests on: the totals are 50, 300 and 1000."""
    w = three_requesters
    payload = _list(w, w.admin, state=["pending_approval"])
    totals = {item["id"]: Decimal(str(item["total"])) for item in payload["data"]}
    p = w.people
    assert totals[str(p["alice"].id)] == Decimal("50")
    assert totals[str(p["carol"].id)] == Decimal("300")
    assert totals[str(p["bob"].id)] == Decimal("1000")


# =============================================================================
# R5 (S2) - a decision on a request that changed under the approver is refused
# =============================================================================


def _seen_submitted_at(w, inquiry, who) -> str:
    detail = w.as_user(who).get(f"{SPR}/{inquiry.id}")
    assert detail.status_code == 200, detail.text
    value = detail.json()["submitted_at"]
    assert value, "the detail returns the submitted_at the page renders"
    return value


@pytest.fixture
def restarted(staged):
    """A pending request the approver opened at qty 10, then the requester edited it to
    qty 100 (approval restarted at level one, same approver)."""
    w = staged
    inquiry = submitted(w)
    w.stale = _seen_submitted_at(w, inquiry, w.stage1.tier1)
    res = w.as_user(w.requester).put(f"{SPR}/{inquiry.id}", json=_edit_body(w, inquiry, qty_a="100"))
    assert res.status_code == 200, res.text
    w.inquiry = reload(w.db, inquiry)
    w.fresh = _seen_submitted_at(w, w.inquiry, w.stage1.tier1)
    assert w.fresh != w.stale, "precondition: the restart moved submitted_at"
    return w


def test_R5_a_stale_approve_answers_409_and_approves_nothing(restarted):
    w = restarted
    res = w.as_user(w.stage1.tier1).post(
        f"{SPR}/{w.inquiry.id}/approve", json={"note": None, "submitted_at": w.stale}
    )
    assert res.status_code == 409, res.text
    message = _message(res)
    assert message and "submitted_at" not in message, f"a plain message, got {message!r}"
    assert reload(w.db, w.inquiry).state == "pending_approval", "nothing was approved"


def test_R5_a_stale_reject_answers_409_and_rejects_nothing(restarted):
    w = restarted
    res = w.as_user(w.stage1.tier1).post(
        f"{SPR}/{w.inquiry.id}/reject", json={"reason": "Too dear", "submitted_at": w.stale}
    )
    assert res.status_code == 409, res.text
    message = _message(res)
    assert message and "submitted_at" not in message, f"a plain message, got {message!r}"
    assert reload(w.db, w.inquiry).state == "pending_approval", "nothing was rejected"


def test_R5_an_approve_with_the_current_submitted_at_goes_through(restarted):
    w = restarted
    res = w.as_user(w.stage1.tier1).post(
        f"{SPR}/{w.inquiry.id}/approve", json={"note": None, "submitted_at": w.fresh}
    )
    assert res.status_code == 200, res.text
    assert reload(w.db, w.inquiry).state == "raised"


def test_R5_a_reject_with_the_current_submitted_at_goes_through(restarted):
    w = restarted
    res = w.as_user(w.stage1.tier1).post(
        f"{SPR}/{w.inquiry.id}/reject", json={"reason": "Too dear", "submitted_at": w.fresh}
    )
    assert res.status_code == 200, res.text
    assert reload(w.db, w.inquiry).state == "rejected"


# =============================================================================
# R6 (S3 c, d) - guards on the pending-edit restart
# =============================================================================


def _purchasing_notices(w, inquiry) -> list:
    return [s for s in w.sent if s[1] == OI_RAISED_NOTICE]


def test_R6_a_pending_edit_restart_sends_no_purchasing_notice(staged):
    w = staged
    inquiry = submitted(w)
    w.sent.clear()
    res = w.as_user(w.requester).put(f"{SPR}/{inquiry.id}", json=_edit_body(w, inquiry))
    assert res.status_code == 200, res.text
    assert _purchasing_notices(w, inquiry) == [], f"purchasing is not told of a restart: {w.sent}"

    # Control: the approval that follows does tell purchasing, so the capture above is live.
    approve(w, reload(w.db, inquiry), w.stage1.tier1)
    assert _purchasing_notices(w, inquiry), f"the approval tells purchasing: {w.sent}"


@pytest.fixture
def photos(staged, monkeypatch):
    from app.models.resources import AttachmentType

    from ._forms_chain_support import uid

    stub_storage(monkeypatch)
    staged.db.add(
        AttachmentType(
            id=uid(), type_name="Sales Order Line Attachment", code="so_line_attachment",
            allowed_extensions="jpg,jpeg,png,webp,gif,pdf,xlsx,xls", max_file_size_mb=10,
        )
    )
    staged.db.commit()
    return staged


def _upload(w, user_id, row_id, name="seal.png"):
    return w.as_user(user_id).post(
        f"{ROW_ATT}/{row_id}/attachments", files=[("files", (name, TINY_PNG, "image/png"))]
    )


def test_R6_the_requester_cannot_upload_a_photo_while_pending(photos):
    w = photos
    pending = submitted(w)
    row = row_for(w.db, pending, w.product_a)
    res = _upload(w, w.requester, row.id)
    assert res.status_code == 403, res.text

    # Control: the current approver may, so the 403 above is the rule, not a dead route.
    res = _upload(w, w.stage1.tier1, row.id)
    assert res.status_code in (200, 201), res.text


# =============================================================================
# R8 (S5) - an approver with the view grant only reaches the list
# =============================================================================


def test_R8_a_view_only_approver_reaches_the_list_and_sees_what_they_decide(staged):
    from app.models.access import AgentTeam, TeamMember

    from ._forms_chain_support import uid

    w = staged
    approver = user(w.db, "spr view-only approver")
    role_grant(w.db, approver, VIEW)
    tier1_team = (
        w.db.query(AgentTeam)
        .filter(AgentTeam.code == w.stage1.team_set, AgentTeam.tier == 1)
        .one()
    )
    w.db.add(TeamMember(id=uid(), team_id=tier1_team.team_id, user_id=approver, sort_order=9))
    w.db.commit()
    inquiry = submitted(w)
    assert svc().can_decide(w.db, reload(w.db, inquiry), approver) is True, "precondition"

    res = w.as_user(approver).get(SPR, params={"limit": 100})
    assert res.status_code == 200, res.text
    assert str(inquiry.id) in [i["id"] for i in res.json()["data"]]
