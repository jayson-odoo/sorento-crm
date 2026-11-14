"""SPARE-PART-ORDER-REQUEST fix round 2, red-first (Phase 2). Review report (scratchpad review.md).

R1 (M1 follow-up) `FormSLAOrchestrator.resolve_stage` / `next_stage_config` find a tracker's
   config by `team_set_code` + `.first()`: two stages on the SAME team set (different agents)
   must still advance stage 1 -> stage 2 -> raised. Run in both insertion orders so whichever
   row `.first()` returns, one order exposes a wrong pick.
R3 (S3) the stage assignee's notice link opens the OI page (`_FE_RECORD_ROUTES`).
R4 (S4) Revise after purchasing rejected a line: CLEAN SLATE (the lead's pick) - the line returns
   to draft, ack_state awaiting, rejected_by / rejected_at / rejected_reason cleared, and it stays
   clear through resubmit and approval.
R5 (S5) the requester's edit writes History with old -> new per changed field and line (qty,
   unit price, product, location, currency, needed by, reason), never a bare "Edited".
R6 (S6) `/order-inquiry-headers` sorts by `inquiry_type` on the server (asc / desc).
R8 (S10) `oi_row_visibility.live_row_clause` / `is_live_row` exclude a draft row: a direct guard
   that fails if the draft exclusion is removed (verified by a scratch mutation run, see report).

Postgres only (`blank_session`); every row seeded here.
"""
from __future__ import annotations

import re

import pytest

from ._forms_chain_support import open_tracker, sla_chain, trackers, unique_code
from ._spare_part_request_support import (  # noqa: F401  (fixtures)
    CREATE,
    HEADERS,
    KIND,
    VIEW,
    approve,
    body,
    create,
    line,
    make_product,
    raised,
    reload,
    role_grant,
    row_for,
    rows_of,
    sent,
    staged,
    submitted,
    svc,
    world,
)


# =============================================================================
# R1 - two stages on the same team set still chain correctly
# =============================================================================


def _same_team_set(w, *, second_inserted_first: bool):
    code = unique_code("ts-same")
    first = {"start_event": "submitted", "resolve_event": "approved,rejected",
             "advance_on_event": "approved", "team_set_code": code}
    second = {"start_event": "spare_part_level_two", "resolve_event": "approved,rejected",
              "team_set_code": code}
    if second_inserted_first:
        stage2 = sla_chain(w.db, KIND, [second]).stages[0]
        stage1 = sla_chain(w.db, KIND, [first]).stages[0]
    else:
        stage1 = sla_chain(w.db, KIND, [first]).stages[0]
        stage2 = sla_chain(w.db, KIND, [second]).stages[0]
    stage1.config.next_config_id = stage2.config.id
    for stage in (stage1, stage2):
        role_grant(w.db, stage.tier1, VIEW, CREATE)
        role_grant(w.db, stage.tier2, VIEW, CREATE)
    w.db.commit()
    assert stage1.team_set == stage2.team_set == code
    return stage1, stage2


@pytest.mark.parametrize("second_inserted_first", [False, True])
def test_R1_two_stages_on_one_team_set_advance_one_then_two(world, second_inserted_first):
    w = world
    stage1, stage2 = _same_team_set(w, second_inserted_first=second_inserted_first)
    inquiry = submitted(w)
    assert open_tracker(w.db, KIND, inquiry.id).assigned_to_id == stage1.tier1

    inquiry = approve(w, inquiry, stage1.tier1)
    assert inquiry.state == "pending_approval", "stage 2 has not decided"
    tracker = open_tracker(w.db, KIND, inquiry.id)
    assert tracker.assigned_to_id == stage2.tier1, "stage 2 (its own agent's team) is the open stage"
    assert svc().can_decide(w.db, inquiry, stage1.tier1) is False
    assert svc().can_decide(w.db, inquiry, stage2.tier1) is True

    inquiry = approve(w, inquiry, stage2.tier1)
    assert inquiry.state == "raised"
    every = trackers(w.db, KIND, inquiry.id)
    assert len(every) == 2 and all(t.is_resolved for t in every)


# =============================================================================
# R3 - the assignee's notice opens the OI page
# =============================================================================


def test_R3_the_stage_assignment_link_opens_the_spare_part_request_page(staged, monkeypatch):
    from app.services.notification_service import NotificationService

    seen: list = []
    monkeypatch.setattr(
        NotificationService, "create_with_channel_preferences", lambda self, *a, **kw: seen.append(kw)
    )
    inquiry = submitted(staged)
    assigned = [kw for kw in seen if kw.get("type") == "form_sla" and kw.get("user_id") == staged.stage1.tier1]
    assert assigned, "the stage-1 assignee is told"
    form_url = assigned[0]["data"]["whatsapp_context_vars"]["form_url"]
    # Hand-test round G3 (owner 13 Nov): the request's own record page, not the OI page.
    assert form_url.endswith(f"/procurement-management/spare-part-requests/{inquiry.id}"), form_url
    assert "?ticket=" not in form_url
    assert assigned[0]["data"]["whatsapp_context_vars"]["entity_number"] == inquiry.inquiry_no


def test_R3_spare_part_request_is_a_routed_record_type():
    """`_FE_RECORD_ROUTES` must match MyPendingSLAWidget.ENTITY_ROUTES (which lists it)."""
    import inspect

    from app.services import form_sla_service as f

    source = inspect.getsource(f)
    block = source[source.index("_FE_RECORD_ROUTES = {"):]
    block = block[: block.index("}") + 1]
    assert '"spare_part_request"' in block


# =============================================================================
# R4 - Revise after a purchasing rejection. SPARE-PART-OR-B (owner 14 Nov, U4.2): Revise no
# longer resets the rows to a clean draft; it opens a revision and leaves every row, its
# purchasing refusal included, exactly as it is until the revision's final approval.
# =============================================================================


def test_R4_revise_after_a_rejected_line_keeps_purchasings_refusal(staged):
    from app.services.project_order_inquiry_service import ProjectOrderInquiryService

    w = staged
    inquiry = raised(w)
    row = row_for(w.db, inquiry, w.product_a)
    ProjectOrderInquiryService(w.db).reject_row(str(row.id), reason="Supplier discontinued it", actor_user_id=w.buyer)
    w.db.commit()
    row = row_for(w.db, inquiry, w.product_a)
    assert row.ack_state == "rejected" and row.rejected_reason == "Supplier discontinued it"

    svc().revise(w.db, reload(w.db, inquiry), w.requester)
    w.db.commit()
    inquiry = reload(w.db, inquiry)
    assert inquiry.state == "raised" and inquiry.revision_state == "draft"
    row = row_for(w.db, inquiry, w.product_a)
    assert row.state == "raised"
    assert row.ack_state == "rejected"
    assert row.rejected_reason == "Supplier discontinued it"


# =============================================================================
# R5 - the requester's edit is History with old -> new
# =============================================================================


def _history(w, inquiry) -> dict:
    res = w.as_user(w.admin).get(f"{HEADERS}/{inquiry.id}/history")
    assert res.status_code == 200, res.text
    return res.json()


def _moved(text: str, old: str, new: str) -> bool:
    return re.search(rf"{re.escape(old)}(\.0+)?\s*(->|→|to)\s*{re.escape(new)}(\.0+)?\b", text) is not None


def test_R5_an_edit_writes_old_to_new_for_every_changed_field_and_line(staged):
    w = staged
    product_c = make_product(w.db, "gasket kit")
    w.db.commit()
    inquiry = create(w)
    a = row_for(w.db, inquiry, w.product_a)
    b = row_for(w.db, inquiry, w.product_b)
    line_a = {**line(w.product_a, w.loc_b, qty="12", unit_price="30"), "id": str(a.id)}
    line_b = {**line(product_c, w.loc_b, qty="4", unit_price="12.50"), "id": str(b.id)}
    svc().update(
        w.db, inquiry,
        body(w, currency="SGD", needed_by="2027-01-20", reason="Seals wore out faster",
             lines=[line_a, line_b]),
        w.requester,
    )
    w.db.commit()

    events = _history(w, inquiry)
    text = str(events)
    assert _moved(text, "MYR", "SGD"), "currency old -> new"
    assert _moved(text, "Spare parts for the service van", "Seals wore out faster"), "reason old -> new"
    assert ("2027-01-20" in text or "20/01/2027" in text), "needed by new value"
    assert _moved(text, "10", "12"), "line qty old -> new"
    assert _moved(text, "25", "30"), "line unit price old -> new (admin holds cost view)"
    assert w.loc_a.warehouse_code in text and w.loc_b.warehouse_code in text, "line location old -> new"
    assert w.product_b.product_code in text and product_c.product_code in text, "line product old -> new"

    flat = events.get("events", events) if isinstance(events, dict) else events
    edited = [e for e in flat if e.get("kind") == "edited"]
    assert edited, "the edit is on History"
    assert all(e.get("lines") or e.get("title") != "Edited" for e in edited), "never a bare Edited"


def test_R5_an_edit_that_changes_nothing_adds_no_change_lines(staged):
    w = staged
    inquiry = create(w)
    rows = {str(r.product_id): str(r.id) for r in rows_of(w.db, inquiry)}
    same = body(w)
    same["lines"] = [{**ln, "id": rows[ln["product_id"]]} for ln in same["lines"]]
    svc().update(w.db, inquiry, same, w.requester)
    w.db.commit()
    text = str(_history(w, inquiry))
    assert not _moved(text, "MYR", "MYR")
    assert not _moved(text, "10", "10")


# =============================================================================
# R6 - the header list sorts by type on the server
# =============================================================================


def test_R6_header_list_sorts_by_inquiry_type_both_ways(staged):
    from .test_oi_header_list import _header

    w = staged
    spare = raised(w)
    sales = _header(w.db, w.company_id)["inquiry"]
    ids = {str(spare.id), str(sales.id)}

    def order(direction):
        res = w.as_user(w.admin).get(
            HEADERS, params={"state": "all", "limit": 100, "sort": "inquiry_type", "dir": direction}
        )
        assert res.status_code == 200, res.text
        return [item["id"] for item in res.json()["data"] if item["id"] in ids]

    assert order("asc") == [str(sales.id), str(spare.id)]  # sales_order < spare_part_request
    assert order("desc") == [str(spare.id), str(sales.id)]


# =============================================================================
# R8 - a draft row is never live
# =============================================================================


def test_R8_live_row_clause_excludes_a_draft_spare_part_row_beside_a_live_so_row(staged):
    from app.models.project_so import OrderInquiryRow
    from app.services import oi_row_visibility as v

    from .test_oi_header_list import _header

    w = staged
    so_row = _header(w.db, w.company_id)["rows"][0]
    draft_rows = rows_of(w.db, create(w))
    pending_rows = rows_of(w.db, submitted(w))
    seeded = [str(so_row.id)] + [str(r.id) for r in draft_rows + pending_rows]

    live = {
        rid for (rid,) in w.db.query(OrderInquiryRow.id)
        .filter(OrderInquiryRow.id.in_(seeded), v.live_row_clause())
        .all()
    }
    assert live == {str(so_row.id)}, "draft spare part rows are nobody's work yet"
    assert v.is_live_row(so_row) is True
    assert not any(v.is_live_row(r) for r in draft_rows + pending_rows)
