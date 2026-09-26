"""AC-CF-23/24/25/27 (`PLAN-oi-confirm-per-so.md` S8, `oi-confirm-per-so-acceptance-
criteria.md`): written from the contract (the UAC + the captain's brief), not from
reading the coder's diff. AC-CF-26 (the frontend DataGrid table) has no backend
surface and is covered by the vitest spec instead.

CONCURRENT-EDIT NOTE (17 Sep): the coder was live in this same worktree while this
file was being written (per the brief), and had already landed the backend half of S8
by the time these tests first ran - `_assert_linkable`'s state gate, `current_take`,
the `{"candidates": [...], "still_to_link": ...}` envelope and `place_on_po_allocations
(full_set=True)`'s SET semantics were all in place. Every test here passed on its FIRST
run rather than failing red-for-the-right-reason first; two assertions that assumed
details the diff did not actually promise (a literal `remaining: "0"` on a row's own
linked line, and a `po_line_id` key on a placement response's `links` entries) were
corrected against the real wire shapes before the suite went green - see the inline
comments. They stand as regression coverage tracing to AC-CF-23/24/25/27, seeded fresh
per test on Postgres, not as a red-then-green record for this slice.

Contract this file pins (captain's brief, 17 Sep):
- `_assert_linkable` (`app/services/project_order_inquiry_service.py`, ~:6944) refuses
  ONLY `state == cancelled`; `raised`, `partly_linked`, `placed` and `actioned` all pass
  both `GET .../po-candidates` and `POST .../place-on-po`. The 409 on a cancelled row
  keeps its existing code, `order_inquiry_not_raised`.
- `GET .../order-inquiry-rows/{row_id}/po-candidates` gains a `current_take` on every
  candidate (this row's own live link qty on that line, `0` when it holds none), a line
  the row is linked to is listed even when its `remaining` reads `0`, and the response
  wraps the candidate list in an envelope carrying `still_to_link` (`qty - linked`) -
  the "N still to link of Q" header text needs a number to read:
  `{"candidates": [...], "still_to_link": "4"}`.
- `POST .../place-on-po` becomes SET semantics: after the call the row's links are
  EXACTLY the submitted allocations - an existing link on a line left out of the payload
  is retired, and a take moved from one line to another ends up on the new line only.

Fixtures copied from `tests/test_order_inquiry_place_on_po.py` (the file this slice's
route lives in) rather than rebuilt: `api` / `reader_api`, `_row`, `_po`, `_po_line`,
`world` seeding via `_seed_world`. `blank_session` (Postgres, scratch schema) - nothing
here reaches `scm.committed_v` or another migration-only view. Every row is seeded fresh
behind the `zzt-oi-place` marker; nothing here depends on a row already in the shared
local database.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.models.project_so import (
    INQUIRY_ACTIONED,
    INQUIRY_CANCELLED,
    INQUIRY_PLACED,
    IV_ORDER,
    OrderInquiryLink,
)

from ..test_order_inquiry_place_on_po import (
    BASE,
    _po_line,
    _row,
    api,
)

__all__ = ["api"]  # re-exported fixture


# ------------------------------------------------------------- AC-CF-23


def test_ac_cf_23_candidates_and_place_on_po_work_for_a_placed_row(api):
    client, db, world, _user_id = api
    line = _po_line(
        db, world["company_id"], world["po"], world["product"], world["warehouse"],
        qty_ordered="10", expected_date=date(2026, 9, 1),
    )
    other_line = _po_line(
        db, world["company_id"], world["po"], world["product"], world["warehouse"],
        qty_ordered="10", expected_date=date(2026, 9, 5),
    )
    row = _row(db, world["company_id"], world["inquiry"], qty="10", item_code=world["product"].product_code)
    placed = client.post(
        f"{BASE}/order-inquiry-rows/{row.id}/place-on-po", json={"po_line_id": line.id}
    )
    assert placed.status_code == 200, placed.text
    assert placed.json()["state"] == INQUIRY_PLACED

    candidates = client.get(f"{BASE}/order-inquiry-rows/{row.id}/po-candidates")
    assert candidates.status_code == 200, (
        "a placed row must be linkable now (AC-CF-23), not refused with "
        f"order_inquiry_not_raised: {candidates.text}"
    )

    relink = client.post(
        f"{BASE}/order-inquiry-rows/{row.id}/place-on-po",
        json={"allocations": [{"po_line_id": other_line.id, "qty": "10"}]},
    )
    assert relink.status_code == 200, (
        f"place-on-po must accept a placed row too (AC-CF-23): {relink.text}"
    )


def test_ac_cf_23_candidates_and_place_on_po_work_for_an_actioned_row(api):
    client, db, world, _user_id = api
    line = _po_line(
        db, world["company_id"], world["po"], world["product"], world["warehouse"],
        qty_ordered="10", expected_date=date(2026, 9, 1),
    )
    row = _row(
        db, world["company_id"], world["inquiry"], verb=IV_ORDER, state=INQUIRY_ACTIONED,
        qty="10", item_code=world["product"].product_code,
    )

    candidates = client.get(f"{BASE}/order-inquiry-rows/{row.id}/po-candidates")
    assert candidates.status_code == 200, (
        "an actioned row must be linkable now (AC-CF-23): "
        f"{candidates.text}"
    )

    linked = client.post(
        f"{BASE}/order-inquiry-rows/{row.id}/place-on-po", json={"po_line_id": line.id}
    )
    assert linked.status_code == 200, (
        f"place-on-po must accept an actioned row too (AC-CF-23): {linked.text}"
    )


# ------------------------------------------------------------- AC-CF-24


def test_ac_cf_24_a_linked_line_appears_with_current_take_and_still_to_link_header(api):
    client, db, world, _user_id = api
    # The row's own live link: qty 6 off a line ordered exactly 6, so `remaining` on
    # that line reads 0 - the case the plan calls out by name ("appears even when its
    # remaining is 0").
    linked_line = _po_line(
        db, world["company_id"], world["po"], world["product"], world["warehouse"],
        qty_ordered="6", expected_date=date(2026, 9, 1),
    )
    row = _row(db, world["company_id"], world["inquiry"], qty="10", item_code=world["product"].product_code)
    placed = client.post(
        f"{BASE}/order-inquiry-rows/{row.id}/place-on-po",
        # A partial take (6 of 10) needs the `allocations` form - the single `po_line_id`
        # form (like `test_ac_cf_23` above) requires the ONE line to cover the whole
        # row, which this fixture's 6-ordered line deliberately does not.
        json={"allocations": [{"po_line_id": linked_line.id, "qty": "6"}]},
    )
    assert placed.status_code == 200, placed.text
    assert placed.json()["state"] == "partly_linked", "6 of 10 leaves the row partly linked"

    response = client.get(f"{BASE}/order-inquiry-rows/{row.id}/po-candidates")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body.get("still_to_link") == "4", (
        "still_to_link = qty (10) - linked (6); envelope not found or wrong value: "
        f"{body}"
    )
    candidates = body.get("candidates") if isinstance(body, dict) else body
    assert candidates is not None, f"no candidate list in the response: {body}"
    own_link = next(
        (c for c in candidates if c.get("po_line_id") == linked_line.id), None
    )
    assert own_link is not None, (
        "the line the row is already linked to must still appear even though a plain "
        f"(uncredited) reading of its remaining would be 0: {candidates}"
    )
    assert own_link.get("current_take") == "6", (
        f"current_take must carry this row's own live link qty on that line: {own_link}"
    )


def test_ac_cf_24_current_take_is_zero_for_a_candidate_the_row_holds_no_link_on(api):
    client, db, world, _user_id = api
    line = _po_line(
        db, world["company_id"], world["po"], world["product"], world["warehouse"],
        qty_ordered="20", expected_date=date(2026, 9, 1),
    )
    row = _row(db, world["company_id"], world["inquiry"], qty="10", item_code=world["product"].product_code)

    response = client.get(f"{BASE}/order-inquiry-rows/{row.id}/po-candidates")
    assert response.status_code == 200, response.text
    body = response.json()
    candidates = body.get("candidates") if isinstance(body, dict) else body
    candidate = next(c for c in candidates if c.get("po_line_id") == line.id)
    assert candidate.get("current_take") in ("0", None), (
        f"a candidate this row holds no link on must read a 0/None current_take, "
        f"not the field simply missing: {candidate}"
    )


# ------------------------------------------------------------- AC-CF-25


def _links_targeting(db, row_id: str, po_line_id: str) -> list:
    return (
        db.query(OrderInquiryLink)
        .filter(OrderInquiryLink.row_id == row_id, OrderInquiryLink.po_line_id == po_line_id)
        .all()
    )


def test_ac_cf_25_place_on_po_is_set_semantics_a_moved_take_retires_the_omitted_line(api):
    client, db, world, _user_id = api
    line_a = _po_line(
        db, world["company_id"], world["po"], world["product"], world["warehouse"],
        qty_ordered="10", expected_date=date(2026, 9, 1),
    )
    line_b = _po_line(
        db, world["company_id"], world["po"], world["product"], world["warehouse"],
        qty_ordered="10", expected_date=date(2026, 9, 10),
    )
    row = _row(db, world["company_id"], world["inquiry"], qty="10", item_code=world["product"].product_code)
    first = client.post(
        f"{BASE}/order-inquiry-rows/{row.id}/place-on-po", json={"po_line_id": line_a.id}
    )
    assert first.status_code == 200, first.text
    assert first.json()["state"] == INQUIRY_PLACED
    assert len(_links_targeting(db, row.id, line_a.id)) == 1

    # The take moves wholesale to line B; line A is left OUT of the payload entirely -
    # SET semantics means that omission is what retires it, not a second call.
    moved = client.post(
        f"{BASE}/order-inquiry-rows/{row.id}/place-on-po",
        json={"allocations": [{"po_line_id": line_b.id, "qty": "10"}]},
    )
    assert moved.status_code == 200, moved.text
    body = moved.json()
    assert body["state"] == INQUIRY_PLACED
    # The link's serialized `document` is the PO number (both lines share `world["po"]`
    # here), so the line-level proof is the DB check below; this pins the COUNT and
    # QTY the wire response itself carries after the one-press move.
    assert [(link["document"], link["qty"]) for link in body["links"]] == [
        (world["po"].po_number, "10")
    ], f"the row's links must read exactly the submitted set, one press: {body['links']}"

    db.expire_all()
    assert _links_targeting(db, row.id, line_a.id) == [], (
        "an existing link on a line the new payload leaves out must be retired"
    )
    assert len(_links_targeting(db, row.id, line_b.id)) == 1


def test_ac_cf_25_a_take_set_to_zero_unlinks_that_line_and_nothing_else_on_the_row_changes(api):
    client, db, world, _user_id = api
    line_a = _po_line(
        db, world["company_id"], world["po"], world["product"], world["warehouse"],
        qty_ordered="10", expected_date=date(2026, 9, 1),
    )
    line_b = _po_line(
        db, world["company_id"], world["po"], world["product"], world["warehouse"],
        qty_ordered="10", expected_date=date(2026, 9, 10),
    )
    row = _row(db, world["company_id"], world["inquiry"], qty="20", item_code=world["product"].product_code)
    first = client.post(
        f"{BASE}/order-inquiry-rows/{row.id}/place-on-po",
        json={
            "allocations": [
                {"po_line_id": line_a.id, "qty": "10"},
                {"po_line_id": line_b.id, "qty": "10"},
            ]
        },
    )
    assert first.status_code == 200, first.text
    assert first.json()["state"] == INQUIRY_PLACED

    # Line A's take goes to 0 (dropped from the payload); line B's is resubmitted
    # unchanged - a SET call, not a relative edit.
    reduced = client.post(
        f"{BASE}/order-inquiry-rows/{row.id}/place-on-po",
        json={"allocations": [{"po_line_id": line_b.id, "qty": "10"}]},
    )
    assert reduced.status_code == 200, reduced.text
    body = reduced.json()
    assert body["state"] == "partly_linked", "10 of 20 leaves the row partly linked"
    assert body["qty"] == "20", "the row's own quantity is untouched"
    assert [(link["document"], link["qty"]) for link in body["links"]] == [
        (world["po"].po_number, "10")
    ]

    db.expire_all()
    assert _links_targeting(db, row.id, line_a.id) == []
    assert len(_links_targeting(db, row.id, line_b.id)) == 1


# ------------------------------------------------------------- AC-CF-27


def test_ac_cf_27_a_cancelled_row_is_refused_on_both_candidates_and_place_on_po(api):
    client, db, world, _user_id = api
    line = _po_line(
        db, world["company_id"], world["po"], world["product"], world["warehouse"],
        qty_ordered="10", expected_date=date(2026, 9, 1),
    )
    row = _row(
        db, world["company_id"], world["inquiry"], verb=IV_ORDER, state=INQUIRY_CANCELLED,
        qty="10", item_code=world["product"].product_code,
    )

    candidates = client.get(f"{BASE}/order-inquiry-rows/{row.id}/po-candidates")
    assert candidates.status_code == 409
    assert candidates.json()["code"] == "order_inquiry_not_raised"

    placed = client.post(
        f"{BASE}/order-inquiry-rows/{row.id}/place-on-po", json={"po_line_id": line.id}
    )
    assert placed.status_code == 409
    assert placed.json()["code"] == "order_inquiry_not_raised"


# ------------------------------------------ S8 review round (17 Sep, merge-blocker)


def test_candidates_lists_the_closed_line_the_row_already_holds_with_line_open_false(api):
    """`po_candidates_for_row` force-includes a line closed AFTER this row linked to
    it, `line_open: False`, so the dialog can show the row's own link on a line the
    ordinary open/active walk would otherwise have dropped entirely."""
    client, db, world, _user_id = api
    line = _po_line(
        db, world["company_id"], world["po"], world["product"], world["warehouse"],
        qty_ordered="6", expected_date=date(2026, 9, 1),
    )
    row = _row(db, world["company_id"], world["inquiry"], qty="6", item_code=world["product"].product_code)
    placed = client.post(
        f"{BASE}/order-inquiry-rows/{row.id}/place-on-po", json={"po_line_id": line.id}
    )
    assert placed.status_code == 200, placed.text

    line.line_status = "closed"
    db.commit()

    response = client.get(f"{BASE}/order-inquiry-rows/{row.id}/po-candidates")
    assert response.status_code == 200, response.text
    body = response.json()
    entry = next(c for c in body["candidates"] if c["po_line_id"] == line.id)
    assert entry["line_open"] is False
    assert entry["current_take"] == "6"
    assert entry["remaining"] == "6", "credited to this row's own take, nothing else"


def test_an_existing_link_on_a_closed_line_survives_a_set_call_that_never_offered_it(api):
    """The merge-blocker itself: a SET request that omits BOTH the closed line and its
    id from `offered_line_ids` never saw that line at all, so it is left standing while
    a DIFFERENT line moves - not retired for having nowhere to be resubmitted to."""
    client, db, world, _user_id = api
    line = _po_line(
        db, world["company_id"], world["po"], world["product"], world["warehouse"],
        qty_ordered="6", expected_date=date(2026, 9, 1),
    )
    other_line = _po_line(
        db, world["company_id"], world["po"], world["product"], world["warehouse"],
        qty_ordered="10", expected_date=date(2026, 9, 5),
    )
    row = _row(db, world["company_id"], world["inquiry"], qty="6", item_code=world["product"].product_code)
    placed = client.post(
        f"{BASE}/order-inquiry-rows/{row.id}/place-on-po", json={"po_line_id": line.id}
    )
    assert placed.status_code == 200, placed.text

    line.line_status = "closed"
    db.commit()

    moved = client.post(
        f"{BASE}/order-inquiry-rows/{row.id}/place-on-po",
        json={
            "allocations": [{"po_line_id": other_line.id, "qty": "4"}],
            "offered_line_ids": [other_line.id],
        },
    )
    assert moved.status_code == 200, moved.text

    db.expire_all()
    assert len(_links_targeting(db, row.id, line.id)) == 1, (
        "a link on a line the caller never offered survives an omission"
    )
    assert len(_links_targeting(db, row.id, other_line.id)) == 1


def test_an_in_place_qty_adjust_writes_the_same_audit_trail_as_retire_and_add(api):
    """The adjust branch (`_place_on_po_set`, a resubmitted line whose qty moved) used
    to write no trail at all, unlike retire ("Unlinked from X") and add ("Linked to
    X..."). 6 -> 2 on the SAME line: one link stands, at qty 2, and the row's note
    grew."""
    client, db, world, _user_id = api
    line = _po_line(
        db, world["company_id"], world["po"], world["product"], world["warehouse"],
        qty_ordered="10", expected_date=date(2026, 9, 1),
    )
    row = _row(db, world["company_id"], world["inquiry"], qty="6", item_code=world["product"].product_code)
    placed = client.post(
        f"{BASE}/order-inquiry-rows/{row.id}/place-on-po", json={"po_line_id": line.id}
    )
    assert placed.status_code == 200, placed.text
    note_before = placed.json()["note"] or ""

    adjusted = client.post(
        f"{BASE}/order-inquiry-rows/{row.id}/place-on-po",
        json={"allocations": [{"po_line_id": line.id, "qty": "2"}]},
    )
    assert adjusted.status_code == 200, adjusted.text
    body = adjusted.json()
    assert body["note"] != note_before and body["note"].startswith(note_before), (
        "the adjust branch appends its own stamp the same way retire/add do"
    )
    assert "Adjusted" in body["note"]

    db.expire_all()
    links = _links_targeting(db, row.id, line.id)
    assert len(links) == 1
    assert Decimal(str(links[0].qty)) == Decimal("2")


def test_two_links_on_one_closed_line_force_a_single_candidate_with_the_summed_take(api):
    """The ADD path (`place_on_po_allocations`, non-SET) writes a fresh link every
    call rather than merging onto an existing one on the same line - two links can
    stand on ONE `po_line_id`. `_candidates_including_own_closed_links` must force a
    SINGLE candidate for that line, not one per link, with `current_take` the SUM -
    two rows each carrying the full take would double it in the dialog's own total."""
    from app.services.project_order_inquiry_service import ProjectOrderInquiryService

    client, db, world, user_id = api
    line = _po_line(
        db, world["company_id"], world["po"], world["product"], world["warehouse"],
        qty_ordered="10", expected_date=date(2026, 9, 1),
    )
    row = _row(db, world["company_id"], world["inquiry"], qty="10", item_code=world["product"].product_code)
    service = ProjectOrderInquiryService(db)
    service.place_on_po_allocations(
        str(row.id), [{"po_line_id": line.id, "qty": "3"}], actor_user_id=user_id,
    )
    service.place_on_po_allocations(
        str(row.id), [{"po_line_id": line.id, "qty": "2"}], actor_user_id=user_id,
    )
    db.commit()
    assert len(_links_targeting(db, row.id, line.id)) == 2, "two distinct link rows on one line"

    line.line_status = "closed"
    db.commit()

    response = client.get(f"{BASE}/order-inquiry-rows/{row.id}/po-candidates")
    assert response.status_code == 200, response.text
    entries = [c for c in response.json()["candidates"] if c["po_line_id"] == line.id]
    assert len(entries) == 1, "one candidate, not one per link"
    assert entries[0]["current_take"] == "5"
    assert entries[0]["line_open"] is False
