"""SPARE-PART-ORDER-REQUEST hand-test round (owner 13 Nov), red-first (Phase 2).

Contract: the "Hand-test round (owner 13 Nov ...)" section (G1-G5) of
documentation/plans/purchasing/spare-part-order-request-12nov-acceptance-criteria.md.

B1 (G3) GET /project-sales/spare-part-requests: the request's own list. A requester sees only
   their own (drafts included); a stage approver sees the pending ones they can decide but no
   one else's draft; an admin sees every one; `state` is multi-value; the server sorts by
   inquiry_no and submitted_at; it pages.
B2 (G5) PUT while Pending approval by the requester: 200, approval restarts at the first
   level (a second level that was open is voided), the submitted values are refreshed, and
   History says the approval restarted. Anyone else still 403; a raised request still 409.
B3 (G1) A line's description is accepted on create / update and returned on the detail;
   omitted, it is the product's name.
B4 (G3) The approver's stage notification and the SLA form link open the spare part
   request's own record page, /procurement-management/spare-part-requests/<id>.

Postgres only (`blank_session`); every row is seeded here, nothing borrowed.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from ._forms_chain_support import open_tracker, trackers
from ._spare_part_request_support import (  # noqa: F401  (fixtures)
    HEADERS,
    KIND,
    SPR,
    approve,
    body,
    create,
    line,
    raised,
    reload,
    row_for,
    rows_of,
    sent,
    staged,
    submitted,
    svc,
    two_staged,
    world,
)

RECORD = "/procurement-management/spare-part-requests"
ITEM_KEYS = {
    "id", "inquiry_no", "state", "requested_by_name", "needed_by", "line_count", "total",
    "submitted_at",
}


# =============================================================================
# B1 - the spare part requests list
# =============================================================================


def _list(w, user_id, **params) -> dict:
    res = w.as_user(user_id).get(SPR, params={"limit": 100, **params})
    assert res.status_code == 200, res.text
    return res.json()


def _ids(payload) -> list:
    return [item["id"] for item in payload["data"]]


def _create_as(w, who, **over):
    from ._spare_part_request_support import as_inquiry

    result = svc().create(w.db, body(w, **over), who)
    w.db.commit()
    return as_inquiry(w.db, result)


def _submit_as(w, inquiry, who):
    svc().submit(w.db, inquiry, who)
    w.db.commit()
    return reload(w.db, inquiry)


def _reject(w, inquiry, reason="Too dear"):
    svc().reject(w.db, inquiry, w.stage1.tier1, reason)
    w.db.commit()
    return reload(w.db, inquiry)


@pytest.fixture
def listed(staged):
    """The requester's draft / pending / rejected / raised, plus the outsider's draft and
    pending (the outsider is a second requester who sits on no stage team).

    The requester here is a fresh user holding only the create grant: the shared `staged`
    world puts its requester on stage 1's team (for A2 "never the requester"), which would let
    them decide the outsider's pending one and so list it (lead ruling: the list shows what the
    caller can decide, matching who can open the record)."""
    from ._forms_chain_support import user
    from ._spare_part_request_support import CREATE, role_grant

    w = staged
    w.requester = user(w.db, "spr requester, on no stage team")
    role_grant(w.db, w.requester, CREATE)
    w.db.commit()
    w.state["user"] = w.requester
    w.mine_draft = create(w)
    w.mine_pending = submitted(w)
    w.mine_rejected = _reject(w, submitted(w))
    w.mine_raised = raised(w)
    w.other_draft = _create_as(w, w.outsider)
    w.other_pending = _submit_as(w, _create_as(w, w.outsider), w.outsider)
    return w


def test_B1_the_list_route_answers_with_the_datagrid_shape(listed):
    w = listed
    payload = _list(w, w.requester)
    assert set(payload) >= {"data", "pagination"}
    assert payload["pagination"]["total"] == 4
    item = next(i for i in payload["data"] if i["id"] == str(w.mine_pending.id))
    assert ITEM_KEYS <= set(item), f"missing keys: {ITEM_KEYS - set(item)}"
    assert item["inquiry_no"] == w.mine_pending.inquiry_no
    assert item["state"] == "pending_approval"
    assert item["line_count"] == 2
    assert Decimal(str(item["total"])) == Decimal("300"), "10 x 25 + 4 x 12.50, the requester sees it"
    assert item["requested_by_name"] and "spr requester" in item["requested_by_name"]
    assert item["needed_by"] == "2026-12-15"
    assert item["submitted_at"] is not None


def test_B1_a_requester_sees_only_their_own_drafts_included(listed):
    w = listed
    ids = set(_ids(_list(w, w.requester)))
    assert ids == {
        str(w.mine_draft.id), str(w.mine_pending.id), str(w.mine_rejected.id), str(w.mine_raised.id),
    }
    other = set(_ids(_list(w, w.outsider)))
    assert other == {str(w.other_draft.id), str(w.other_pending.id)}, "the outsider sees only theirs"


def test_B1_a_stage_approver_sees_the_pending_they_can_decide_never_a_draft(listed):
    w = listed
    ids = set(_ids(_list(w, w.stage1.tier1)))
    assert str(w.mine_pending.id) in ids
    assert str(w.other_pending.id) in ids
    assert str(w.mine_draft.id) not in ids, "never another user's draft"
    assert str(w.other_draft.id) not in ids, "never another user's draft"


def test_B1_an_admin_sees_every_submitted_request(listed):
    w = listed
    ids = set(_ids(_list(w, w.admin)))
    assert {
        str(w.mine_pending.id), str(w.mine_rejected.id), str(w.mine_raised.id), str(w.other_pending.id),
    } <= ids


def test_B1_the_state_filter_is_multi_value(listed):
    w = listed
    ids = set(_ids(_list(w, w.requester, state=["draft", "rejected"])))
    assert ids == {str(w.mine_draft.id), str(w.mine_rejected.id)}
    ids = set(_ids(_list(w, w.requester, state=["pending_approval"])))
    assert ids == {str(w.mine_pending.id)}


@pytest.fixture
def three_pending(staged):
    """Three pending requests created A, B, C and submitted B, A, C, so the inquiry_no order
    (A, B, C) and the submitted_at order (B, A, C) differ."""
    w = staged
    a, b, c = create(w), create(w), create(w)
    for inquiry in (b, a, c):
        _submit_as(w, inquiry, w.requester)
    w.trio = [reload(w.db, x) for x in (a, b, c)]
    return w


def test_B1_server_sort_by_inquiry_no_both_ways(three_pending):
    w = three_pending
    a, b, c = w.trio
    by_no = [str(x.id) for x in sorted(w.trio, key=lambda x: x.inquiry_no)]
    assert _ids(_list(w, w.requester, state=["pending_approval"], sort="inquiry_no", dir="asc")) == by_no
    assert _ids(_list(w, w.requester, state=["pending_approval"], sort="inquiry_no", dir="desc")) == by_no[::-1]


def test_B1_server_sort_by_submitted_at_both_ways(three_pending):
    w = three_pending
    a, b, c = w.trio
    expected = [str(b.id), str(a.id), str(c.id)]
    assert _ids(_list(w, w.requester, state=["pending_approval"], sort="submitted_at", dir="asc")) == expected
    assert _ids(_list(w, w.requester, state=["pending_approval"], sort="submitted_at", dir="desc")) == expected[::-1]


def test_B1_the_list_pages(three_pending):
    w = three_pending
    params = {"state": ["pending_approval"], "sort": "inquiry_no", "dir": "asc", "limit": 2}
    first = _list(w, w.requester, page=1, **params)
    second = _list(w, w.requester, page=2, **params)
    assert first["pagination"]["total"] == 3
    assert len(first["data"]) == 2 and len(second["data"]) == 1
    assert set(_ids(first)) | set(_ids(second)) == {str(x.id) for x in w.trio}


# =============================================================================
# B2 - the requester edits while Pending approval: approval restarts
# =============================================================================


def _edit_body(w, inquiry, qty_a="12"):
    a = row_for(w.db, inquiry, w.product_a)
    b = row_for(w.db, inquiry, w.product_b)
    return body(
        w,
        lines=[
            {**line(w.product_a, w.loc_a, qty=qty_a, unit_price="25.00"), "id": str(a.id)},
            {**line(w.product_b, w.loc_b, qty="4", unit_price="12.50"), "id": str(b.id)},
        ],
    )


def _audit_descriptions(w, inquiry) -> list:
    from app.models.audit import AuditLog

    w.db.expire_all()
    return [
        str(r.description or "")
        for r in w.db.query(AuditLog)
        .filter(AuditLog.entity_type == "project_order_inquiries", AuditLog.entity_id == str(inquiry.id))
        .all()
    ]


def test_B2_the_requester_may_edit_while_pending(staged):
    w = staged
    inquiry = submitted(w)
    detail = w.as_user(w.requester).get(f"{SPR}/{inquiry.id}").json()
    assert detail["can_edit"] is True, "G5: the requester can edit while Pending approval"


def test_B2_an_edit_at_level_two_restarts_approval_at_level_one(two_staged):
    w = two_staged
    inquiry = submitted(w)
    inquiry = approve(w, inquiry, w.stage1.tier1)
    stage2_tracker = open_tracker(w.db, KIND, inquiry.id)
    assert stage2_tracker.assigned_to_id == w.stage2.tier1, "precondition: level two is open"

    res = w.as_user(w.requester).put(f"{SPR}/{inquiry.id}", json=_edit_body(w, inquiry))
    assert res.status_code == 200, res.text
    assert res.json()["state"] == "pending_approval"

    reopened = open_tracker(w.db, KIND, inquiry.id)
    assert reopened.assigned_to_id == w.stage1.tier1, "level one is the open stage again"
    voided = [t for t in trackers(w.db, KIND, inquiry.id) if str(t.id) == str(stage2_tracker.id)]
    assert voided and voided[0].voided_at is not None, "level two's open stage is voided"
    assert svc().can_decide(w.db, reload(w.db, inquiry), w.stage2.tier1) is False
    assert svc().can_decide(w.db, reload(w.db, inquiry), w.stage1.tier1) is True


def test_B2_an_edit_at_level_one_starts_a_fresh_level_one(staged):
    w = staged
    inquiry = submitted(w)
    before = open_tracker(w.db, KIND, inquiry.id)

    res = w.as_user(w.requester).put(f"{SPR}/{inquiry.id}", json=_edit_body(w, inquiry))
    assert res.status_code == 200, res.text

    after = open_tracker(w.db, KIND, inquiry.id)
    assert str(after.id) != str(before.id), "approval restarted: a new level-one stage"
    old = [t for t in trackers(w.db, KIND, inquiry.id) if str(t.id) == str(before.id)][0]
    assert old.voided_at is not None


def test_B2_the_restart_refreshes_the_submitted_values(staged):
    w = staged
    inquiry = submitted(w)
    res = w.as_user(w.requester).put(f"{SPR}/{inquiry.id}", json=_edit_body(w, inquiry, qty_a="12"))
    assert res.status_code == 200, res.text
    row = row_for(w.db, inquiry, w.product_a)
    assert Decimal(row.qty) == Decimal("12")
    assert Decimal(row.requested_qty) == Decimal("12"), "the submitted qty is the edited one"


def test_B2_history_says_the_approval_restarted(staged):
    w = staged
    inquiry = submitted(w)
    res = w.as_user(w.requester).put(f"{SPR}/{inquiry.id}", json=_edit_body(w, inquiry))
    assert res.status_code == 200, res.text

    descriptions = " | ".join(_audit_descriptions(w, inquiry)).lower()
    assert "approval restarted" in descriptions, descriptions
    history = w.as_user(w.admin).get(f"{HEADERS}/{inquiry.id}/history")
    assert history.status_code == 200, history.text
    assert "approval restarted" in str(history.json()).lower()


def test_B2_anyone_but_the_requester_is_still_refused_while_pending(staged):
    w = staged
    inquiry = submitted(w)
    res = w.as_user(w.stage1.tier1).put(f"{SPR}/{inquiry.id}", json=_edit_body(w, inquiry))
    assert res.status_code == 403, res.text
    assert reload(w.db, inquiry).state == "pending_approval"


def test_B2_a_raised_request_is_still_not_editable(staged):
    w = staged
    inquiry = raised(w)
    res = w.as_user(w.requester).put(f"{SPR}/{inquiry.id}", json=_edit_body(w, inquiry))
    assert res.status_code == 409, res.text


# =============================================================================
# B3 - a line's description
# =============================================================================


def test_B3_a_line_description_is_stored_and_returned(staged):
    w = staged
    first = {**line(w.product_a, w.loc_a, qty="10", unit_price="25.00"), "description": "Left seal, blue rubber"}
    second = line(w.product_b, w.loc_b, qty="4", unit_price="12.50")
    res = w.as_user(w.requester).post(SPR, json=body(w, lines=[first, second]))
    assert res.status_code == 201, res.text
    created = res.json()

    detail = w.as_user(w.requester).get(f"{SPR}/{created['id']}").json()
    by_product = {ln["product_id"]: ln for ln in detail["lines"]}
    assert by_product[str(w.product_a.id)]["description"] == "Left seal, blue rubber"
    from ._spare_part_request_support import as_inquiry

    inquiry = as_inquiry(w.db, created)
    assert row_for(w.db, inquiry, w.product_a).description == "Left seal, blue rubber"


def test_B3_an_omitted_description_is_the_product_name(staged):
    w = staged
    res = w.as_user(w.requester).post(SPR, json=body(w))
    assert res.status_code == 201, res.text
    by_product = {ln["product_id"]: ln for ln in res.json()["lines"]}
    assert by_product[str(w.product_b.id)]["description"] == w.product_b.product_name


def test_B3_an_update_changes_the_description(staged):
    w = staged
    inquiry = create(w)
    new_body = _edit_body(w, inquiry)
    new_body["lines"][1]["description"] = "Hinge set, stainless"
    res = w.as_user(w.requester).put(f"{SPR}/{inquiry.id}", json=new_body)
    assert res.status_code == 200, res.text
    by_product = {ln["product_id"]: ln for ln in res.json()["lines"]}
    assert by_product[str(w.product_b.id)]["description"] == "Hinge set, stainless"


# =============================================================================
# B4 - the approver's links open the request's own record page
# =============================================================================


def test_B4_the_stage_assignment_link_opens_the_spare_part_request_record(staged, monkeypatch):
    from app.services.notification_service import NotificationService

    seen: list = []
    monkeypatch.setattr(
        NotificationService, "create_with_channel_preferences", lambda self, *a, **kw: seen.append(kw)
    )
    inquiry = submitted(staged)
    assigned = [kw for kw in seen if kw.get("type") == "form_sla" and kw.get("user_id") == staged.stage1.tier1]
    assert assigned, "the stage-1 assignee is told"
    data = assigned[0]["data"]
    assert data["link"] == f"{RECORD}/{inquiry.id}", data["link"]
    form_url = data["whatsapp_context_vars"]["form_url"]
    assert form_url.endswith(f"{RECORD}/{inquiry.id}"), form_url
    assert "/project-sales/order-inquiries" not in form_url


def test_B4_the_sla_form_link_for_a_spare_part_request_is_its_record_page():
    from app.services.form_sla_service import _form_detail_link, _full_form_link

    assert _form_detail_link(KIND, "abc") == f"{RECORD}/abc"
    assert _full_form_link(KIND, "abc").endswith(f"{RECORD}/abc")
