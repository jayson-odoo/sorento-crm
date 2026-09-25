"""A link is a DRAFT until purchasing confirms (`PLAN-scm-oi-draft-links.md`).

The handshake made linking purchasing's word and stopped the board from linking anything.
This reverses ONE half of that on purpose: the cascade runs again the moment CS confirms,
but what it writes is a DRAFT - a link on a row nobody has confirmed yet - and it stays a
draft until the row's own `ack_state` reads `acknowledged`. There is no state column on the
link (R1): the row IS the answer.

What is pinned here, one test each:

* AC-D1 a board confirm raises rows To confirm WITH their documents already found;
* AC-D2b an ORDER row (not only an ORDER BACK) drafts onto an SPO, SPO before PO, and only
  from a POOL location (R5, R11);
* AC-D3 a draft occupies the document's remaining quantity, so the next row is offered the
  rest and Confirm can never fail for want of quantity;
* AC-D4 the reorder plan still ignores a To confirm row's remainder;
* AC-D5 Confirm stamps the row and moves no link;
* AC-D6 Reject unplaces every link first, and the batch takes ONE reason;
* AC-D9 Auto link all re-deals a DRAFT onto a nearer document and never touches a confirmed
  row's link;
* AC-D11 a purchase-order confirm drafts To confirm rows;
* AC-D12 the `to_confirm` filter, its facet and the export;
* AC-D16/AC-D17 the SPO location and `late_days` on the wire;
* AC-D18/AC-D19 the two lightboxes.

Reuses `tests/test_order_inquiry_handshake.py`'s harness wholesale (`world` / `api`), for
the reason that file states: the seeding chain is the same one, `scm.committed_v` lives in
the migrated schema, and every row is seeded behind the `ZZT` marker because CI's database
has no data.
"""
from __future__ import annotations

import io
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from urllib.parse import quote

import pytest

from app.models.inventory import Warehouse
from app.models.procurement import (
    InboundShipment,
    PurchaseOrder,
    PurchaseOrderLine,
    SPOAllocation,
)
from app.models.project_so import (
    ACK_ACKNOWLEDGED,
    ACK_AWAITING,
    ACK_CHANGED,
    ACK_REJECTED,
    INQUIRY_CANCELLED,
    INQUIRY_PARTLY_LINKED,
    INQUIRY_PLACED,
    INQUIRY_RAISED,
    IV_ORDER,
    OrderInquiryLink,
    OrderInquiryRow,
)
from app.services.project_order_inquiry_service import ProjectOrderInquiryService

from .test_order_inquiry_handshake import (
    ACK_URL,
    BASE,
    FAR,
    HORIZON,
    LINK_NOW,
    LIST,
    MARKER,
    NOW,
    PURCHASING,
    WAS,
    _as_purchasing,
    _client,
    _confirm,
    _line_payload,
    _links_of,
    _open_po_line,
    _order_row,
    _product,
    _project_committed,
    _raise_one_row,
    _raise_two_rows,
    _restore,
    _settle,
    _suggested_of,
    _supplier,
    _uid,
    _warehouse,
    api,
    world,
)

REJECT_BATCH = f"{LIST}/reject"
#: "Auto link all" - the worklist-wide re-deal (AC-D9), distinct from `LINK_NOW` (which the
#: page only offers after an upload and which reaches acknowledged rows via a narrower
#: seam). Named here rather than imported: the handshake test module defines its own
#: `AUTO_PLACE` mid-file, past the block this module already imports from.
AUTO_PLACE = f"{LIST}/auto-place"

#: A document that lands twelve days after the row needs it (AC-D17). `WAS` is the row's
#: own delivery date, so the number in the test is the arithmetic, not a magic constant.
LATE_BY = 12
LATE_ARRIVAL = WAS + timedelta(days=LATE_BY)


# ---------------------------------------------------------------------------
# seeding helpers this file owns
# ---------------------------------------------------------------------------


def _pooled(world) -> Warehouse:
    """Turn the world's own warehouse into a site that has a POOL above it.

    The world fixture builds one warehouse per test with no pool, and R11 is entirely
    about the pool set: an SPO line is linkable only at a pool location. Re-coding the
    fixture's own row (rather than seeding a second chain) keeps `_raise_one_row` and every
    location the rows already carry in step with it.
    """
    tag = uuid.uuid4().hex[:6].upper()
    # No `segment`, so this really is a SITE POOL: `pool_predicate.is_site_pool` reads
    # the segment, and a pool tagged `project` is a contradiction the fixture used to
    # carry - it made every SPO candidate at "the pool" a project-bin line G12 refuses to
    # the automatic pass (corrected 2 Sep 2026).
    pool = _warehouse(world.db, f"ZZP{tag}")
    world.warehouse.warehouse_code = f"ZZP{tag}-IB"
    world.warehouse.pool_warehouse_id = pool.id
    world.db.flush()
    world.db.commit()
    return pool


def _spo_line(
    world,
    *,
    qty,
    warehouse,
    expected_date=date(2026, 8, 10),
    product=None,
    spo_number=None,
    line_no=1,
    shipment=None,
    location_code=None,
) -> SPOAllocation:
    """One OPEN shipping-order allocation - the shape the outstanding book now writes."""
    supplier = _supplier(world)
    allocation = SPOAllocation(
        id=_uid(),
        company_id=world.company_id,
        spo_number=spo_number or f"SPO-2026/08-{uuid.uuid4().hex[:4].upper()}",
        spo_line_number=line_no,
        product_id=(product or world.product).id,
        warehouse_id=warehouse.id if warehouse is not None else None,
        location_code=(
            location_code
            if location_code is not None
            else (warehouse.warehouse_code if warehouse is not None else None)
        ),
        allocated_quantity=Decimal(str(qty)),
        quantity_received=Decimal("0"),
        receipt_status="pending",
        line_status="open",
        source_system="scm_upload",
        issue_date=date(2026, 6, 1),
        expected_date=expected_date,
        supplier_id=supplier.id,
        inbound_shipment_id=shipment.id if shipment is not None else None,
    )
    world.db.add(allocation)
    world.db.flush()
    world.db.commit()
    return allocation


def _listed(client, row, **params):
    body = client.get(LIST, params={"limit": 200, **params}).json()
    return next(item for item in body["data"] if item["id"] == str(row.id))


def _link_documents(world, row) -> list:
    return [link.document for link in _links_of(world, row)]


def _suggested_documents(world, row) -> list:
    """S3 (`PLAN-oi-links-autocount-truth-24sep.md`): the same question `_link_documents`
    answers for real links, for the cascade walk's own guesses."""
    return [suggestion.document for suggestion in _suggested_of(world, row)]


# ---------------------------------------------------------------------------
# AC-D1: the board confirm finds the documents
# ---------------------------------------------------------------------------


def test_a_board_confirm_raises_a_row_that_already_holds_its_document(api):
    """AC-D1, still true after `PLAN-oi-confirm-per-so.md` S1 reverses G4's own change:
    purchasing opens the page and the answer is on the row - the raise-time cascade never
    waited on the handshake either side of that lane, so the document it finds reaches
    the row from the moment it is written, DRAFT or not. The row itself is born AWAITING
    again (S1).

    S3 reversal: the open line carries no book match, so what the raise-time cascade
    writes is a SUGGESTION now, never a real link.
    """
    _client, world = api
    po, _line = _open_po_line(world, qty=50)

    fixture = _raise_one_row(api)
    row = fixture["row"]

    assert row.ack_state == ACK_AWAITING
    assert _link_documents(world, row) == []
    assert _suggested_documents(world, row) == [po.po_number]


def test_a_row_nothing_can_cover_still_comes_out_unlinked(api):
    """AC-D2. No candidate is not an error, it is "Not found (new order)"."""
    _client, world = api

    row = _raise_one_row(api)["row"]

    assert row.ack_state == ACK_AWAITING
    assert _links_of(world, row) == []


def test_the_row_carries_its_own_link_and_no_column_on_the_link(api):
    """R1: the link table gains no state column; a reader asks the row's OWN link's
    `auto` flag, never `ack_state` - which reads `awaiting` the instant the row exists
    again (`PLAN-oi-confirm-per-so.md` S1), same as it always could.

    S3: the open line carries no book match, so the raise-time cascade only SUGGESTS
    it now - a real `OrderInquiryLink` for R1's own shape check is seeded directly
    here, through `place_on_po_allocations`, the same manual path a buyer's own press
    takes.
    """
    _client, world = api
    _po, line = _open_po_line(world, qty=50)
    row = _raise_one_row(api)["row"]
    ProjectOrderInquiryService(world.db).place_on_po_allocations(
        str(row.id), [{"po_line_id": str(line.id), "qty": "10"}], actor_user_id=None,
    )
    world.db.commit()

    link = _links_of(world, row)[0]

    assert not hasattr(link, "status"), "a link state column is exactly what R1 refused"
    world.db.refresh(row)
    assert row.ack_state == ACK_AWAITING


# ---------------------------------------------------------------------------
# AC-D2b / R5 / R11: the SPO side
# ---------------------------------------------------------------------------


def test_an_order_row_drafts_onto_a_shipping_order_before_any_purchase_order(api):
    """R5: "SPO link is always one, always SPO first then PO". Not only an ORDER BACK.

    S3 reversal: neither document carries a book match, so what the cascade offers
    is a SUGGESTION, never a real link.
    """
    _client, world = api
    pool = _pooled(world)
    allocation = _spo_line(world, qty=50, warehouse=pool)
    _open_po_line(world, qty=50)

    row = _raise_one_row(api)["row"]

    assert row.verb == IV_ORDER
    assert _link_documents(world, row) == []
    assert _suggested_documents(world, row) == [allocation.spo_number]


def test_a_shipping_order_line_outside_the_pool_is_never_drafted(api):
    """R11: every location is SHOWN, only a pool location is TAKEN."""
    _client, world = api
    _pooled(world)
    off_pool = _warehouse(world.db, f"ZZO{uuid.uuid4().hex[:6].upper()}-BB")
    world.db.commit()
    allocation = _spo_line(world, qty=50, warehouse=off_pool)

    row = _raise_one_row(api)["row"]

    assert _links_of(world, row) == []
    # ... and it is still readable in the lightbox, which is the other half of R11.
    with _as_purchasing(world) as buyer:
        body = buyer.get(
            f"{LIST}/spo/{quote(allocation.spo_number, safe='')}"
        ).json()
    assert body["lines"][0]["location"] == off_pool.warehouse_code


# ---------------------------------------------------------------------------
# AC-D3: a draft occupies the quantity
# ---------------------------------------------------------------------------


def test_two_rows_are_never_drafted_onto_the_same_units(api):
    """SLICE D, 8 Sep 2026 (S5, review of PR): the first row's own take covers the
    line's whole balance up to its own need - 12 covers its 10 in full, leaving exactly
    2 - and the SECOND row needs exactly that 2, so the all-or-nothing rule (AC-D2,
    covered in full) offers it the remainder and no more. Sized this way rather than at
    10 so the test keeps a POSITIVE assertion: the second row takes exactly what is
    left, proving the two never draft onto the same units, rather than a vacuous "gets
    nothing" that a row needing more than the whole line would read the same either way.

    S3 reversal: no book match, so both takes are SUGGESTIONS, never real links.
    """
    _client, world = api
    _open_po_line(world, qty=12)

    first = _raise_one_row(api, qty="10")["row"]
    second = _raise_one_row(api, qty="2")["row"]

    assert _links_of(world, first) == []
    assert _links_of(world, second) == []
    assert sum(Decimal(str(s.qty)) for s in _suggested_of(world, first)) == Decimal("10")
    assert sum(Decimal(str(s.qty)) for s in _suggested_of(world, second)) == Decimal("2")


# ---------------------------------------------------------------------------
# AC-D4: the plan is unmoved
# ---------------------------------------------------------------------------


def test_the_plan_still_ignores_a_to_confirm_rows_remainder(api):
    """A draft is not a decision, and the plan counts acknowledged and changed rows only."""
    _client, world = api
    _open_po_line(world, qty=50)

    _raise_one_row(api)

    assert _project_committed(world, planned=True) == Decimal("0")


# ---------------------------------------------------------------------------
# AC-D5: Confirm
# ---------------------------------------------------------------------------


def test_confirm_stamps_the_row_and_moves_no_link(api):
    """S3 reversal: the open line carries no book match, so what the raise found is a
    SUGGESTION - "moves no link" is what `_same_placement` guarantees for it too: an
    unchanged answer is not deleted and rewritten, so the same suggestion (same id)
    survives Confirm's own cascade pass untouched."""
    _client, world = api
    po, _line = _open_po_line(world, qty=50)
    row = _raise_one_row(api)["row"]
    before = [str(link.id) for link in _links_of(world, row)]
    before_suggested = [str(s.id) for s in _suggested_of(world, row)]

    with _as_purchasing(world) as buyer:
        response = buyer.post(ACK_URL, json={"row_ids": [str(row.id)]})
    assert response.status_code == 200, response.text
    world.db.commit()

    world.db.refresh(row)
    assert row.ack_state == ACK_ACKNOWLEDGED
    assert [str(link.id) for link in _links_of(world, row)] == before
    assert [str(s.id) for s in _suggested_of(world, row)] == before_suggested
    assert _suggested_documents(world, row) == [po.po_number]


def test_confirm_fills_a_remainder_a_draft_could_not_cover_in_full(api):
    """The press still cascades. SLICE D, 8 Sep 2026: the raise itself now suggests
    NOTHING when 4 falls short of the row's 10 (AC-D1) - there is no half-covered
    guess left to finish. Once a second line brings the total to 10, Confirm's own
    cascade covers the row in full in one pass.

    S3 reversal: neither line carries a book match, so what Confirm's cascade writes
    is a SUGGESTION, never a real link.
    """
    _client, world = api
    _open_po_line(world, qty=4)
    row = _raise_one_row(api, qty="10")["row"]
    assert sum(Decimal(str(l.qty)) for l in _links_of(world, row)) == Decimal("0")
    assert _suggested_of(world, row) == []

    _open_po_line(world, qty=6)
    with _as_purchasing(world) as buyer:
        assert buyer.post(ACK_URL, json={"row_ids": [str(row.id)]}).status_code == 200
    world.db.commit()

    assert sum(Decimal(str(l.qty)) for l in _links_of(world, row)) == Decimal("0")
    assert sum(Decimal(str(s.qty)) for s in _suggested_of(world, row)) == Decimal("10")


# ---------------------------------------------------------------------------
# AC-D6: Reject
# ---------------------------------------------------------------------------


def test_reject_unplaces_every_link_and_gives_the_quantity_back(api):
    """Today's reject refused a fully linked row outright, which with drafts is most of
    them. It takes the links down first instead, and the purchase order is free again.

    S3: the open line carries no book match, so the raise-time cascade only SUGGESTS
    it now - the real link this test's own subject (reject giving the quantity back)
    needs is seeded directly here, through `place_on_po_allocations`, the same manual
    path a buyer's own press takes.
    """
    _client, world = api
    _po, line = _open_po_line(world, qty=50)
    row = _raise_one_row(api, qty="10")["row"]
    ProjectOrderInquiryService(world.db).place_on_po_allocations(
        str(row.id), [{"po_line_id": str(line.id), "qty": "10"}], actor_user_id=None,
    )
    world.db.commit()
    world.db.refresh(row)
    assert _links_of(world, row), "the link has to exist for the test to mean anything"
    assert row.state == INQUIRY_PLACED

    with _as_purchasing(world) as buyer:
        response = buyer.post(
            f"{LIST}/{row.id}/reject", json={"reason": "Factory closed"}
        )
    assert response.status_code == 200, response.text
    world.db.commit()

    world.db.refresh(row)
    assert row.ack_state == ACK_REJECTED
    assert _links_of(world, row) == []
    service = ProjectOrderInquiryService(world.db)
    by_po, _by_spo = service._linked_by_target()
    assert by_po.get(str(line.id), Decimal("0")) == Decimal("0")


def test_reject_on_a_placed_row_frees_the_pos_remaining_for_the_next_candidate(api):
    """Not just a number on a report: the freed quantity is real enough for a SECOND
    row's own take to take it on the next re-deal. The first row takes the whole line,
    so a second row raised straight after it is left with nothing - the proof the
    reject really freed something rather than merely zeroing a count.

    S3: the line carries no book match, so the FIRST row's whole-line hold is seeded
    directly here (through `place_on_po_allocations`) rather than relied on from the
    raise-time cascade, which would only suggest it - the reject's own subject (real
    capacity given back) needs a real hold to take back in the first place. The
    SECOND row's own take, after the reject frees the line, is a SUGGESTION.
    """
    _client, world = api
    _po, line = _open_po_line(world, qty=10)
    first = _raise_one_row(api, qty="10")["row"]
    ProjectOrderInquiryService(world.db).place_on_po_allocations(
        str(first.id), [{"po_line_id": str(line.id), "qty": "10"}], actor_user_id=None,
    )
    world.db.commit()
    assert sum(Decimal(str(l.qty)) for l in _links_of(world, first)) == Decimal("10")

    second = _raise_one_row(api, qty="5")["row"]
    assert _links_of(world, second) == [], "nothing was left for it while the first held it"
    assert _suggested_of(world, second) == []

    with _as_purchasing(world) as buyer:
        assert (
            buyer.post(
                f"{LIST}/{first.id}/reject", json={"reason": "Cancelled by customer"}
            ).status_code
            == 200
        )
        world.db.commit()
        assert buyer.post(AUTO_PLACE, json={}).status_code == 200
    world.db.commit()

    world.db.refresh(second)
    assert _links_of(world, second) == []
    assert sum(Decimal(str(s.qty)) for s in _suggested_of(world, second)) == Decimal("5")


def test_the_batch_reject_takes_one_reason_for_every_row(api):
    _client, world = api
    _open_po_line(world, qty=50)
    first = _raise_one_row(api, qty="4")["row"]
    second = _raise_one_row(api, qty="6")["row"]

    with _as_purchasing(world) as buyer:
        response = buyer.post(
            REJECT_BATCH,
            json={"row_ids": [str(first.id), str(second.id)], "reason": "Discontinued"},
        )
    assert response.status_code == 200, response.text
    world.db.commit()

    body = response.json()
    assert body["rejected"] == 2
    assert {entry["row_id"] for entry in body["results"]} == {
        str(first.id),
        str(second.id),
    }
    assert all(entry["ok"] for entry in body["results"])
    for row in (first, second):
        world.db.refresh(row)
        assert row.ack_state == ACK_REJECTED
        assert row.rejected_reason == "Discontinued"


def test_the_batch_reject_refuses_an_empty_reason(api):
    _client, world = api
    row = _raise_one_row(api)["row"]

    with _as_purchasing(world) as buyer:
        response = buyer.post(
            REJECT_BATCH, json={"row_ids": [str(row.id)], "reason": "   "}
        )

    assert response.status_code == 422, response.text


def test_the_batch_reject_refuses_the_whole_batch_when_one_row_cannot_be_refused(api):
    """A batch that half-happened is worse than one that did not: the buyer pressed once."""
    _client, world = api
    good = _raise_one_row(api, qty="4")["row"]
    already = _raise_one_row(api, qty="6")["row"]
    with _as_purchasing(world) as buyer:
        assert (
            buyer.post(
                f"{LIST}/{already.id}/reject", json={"reason": "First refusal"}
            ).status_code
            == 200
        )
        world.db.commit()
        response = buyer.post(
            REJECT_BATCH,
            json={"row_ids": [str(good.id), str(already.id)], "reason": "Second"},
        )

    assert response.status_code == 422, response.text
    world.db.rollback()
    world.db.refresh(good)
    assert good.ack_state == ACK_AWAITING, "nothing was written for the batch"


def test_the_batch_reject_refuses_the_whole_batch_when_one_row_is_cancelled(api):
    """A different branch of `_assert_rejectable` from the already-rejected case above -
    `order_inquiry_row_not_rejectable` rather than `order_inquiry_already_rejected` - and
    the same ALL-OR-NOTHING rule has to hold for it too."""
    _client, world = api
    good = _raise_one_row(api, qty="4")["row"]
    cancelled = _raise_one_row(api, qty="6")["row"]
    cancelled.state = INQUIRY_CANCELLED
    world.db.commit()

    with _as_purchasing(world) as buyer:
        response = buyer.post(
            REJECT_BATCH,
            json={"row_ids": [str(good.id), str(cancelled.id)], "reason": "Whole batch"},
        )

    assert response.status_code == 422, response.text
    world.db.rollback()
    world.db.refresh(good)
    assert good.ack_state == ACK_AWAITING, "nothing was written for the batch"


def test_a_cs_user_may_not_reject_a_batch(api):
    """AC-D8. Reject is purchasing's, on the acknowledge grant like every other press."""
    client, world = api
    row = _raise_one_row(api)["row"]

    response = client.post(
        REJECT_BATCH, json={"row_ids": [str(row.id)], "reason": "Not mine to say"}
    )

    assert response.status_code == 403


# ---------------------------------------------------------------------------
# AC-D9: the re-deal
# ---------------------------------------------------------------------------


def test_auto_link_all_moves_a_draft_onto_a_nearer_document(api):
    """R2: `ack_state` cannot tell a draft from a promise, whether a row is born
    `awaiting` (`PLAN-oi-confirm-per-so.md` S1) or born acknowledged (the world G4 made
    and this lane retires) - so the fact that survives is `_only_cascade_links`. A row
    nobody has MANUALLY linked is still the cascade's own guess, whatever its ack_state
    says, and a better document arriving is still reason enough to move it.

    S3 reversal: neither document carries a book match, so the "draft" is a
    SUGGESTION now - which moves for free on every pass (`_write_suggested_links`
    always re-derives it), `redeal_drafts` or not.
    """
    _client, world = api
    far, _far_line = _open_po_line(world, qty=50, expected_date=date(2026, 12, 1))
    row = _raise_one_row(api)["row"]
    assert row.ack_state == ACK_AWAITING, "not the signal `_only_cascade_links` reads either"
    assert _link_documents(world, row) == []
    assert _suggested_documents(world, row) == [far.po_number]

    near, _near_line = _open_po_line(world, qty=50, expected_date=date(2026, 7, 1))
    with _as_purchasing(world) as buyer:
        response = buyer.post(LINK_NOW, json={})
    assert response.status_code == 200, response.text
    world.db.commit()

    assert _link_documents(world, row) == []
    assert _suggested_documents(world, row) == [near.po_number]


def test_auto_link_all_never_moves_a_manually_linked_rows_link(api):
    """The other half of R2, and the one that matters: a link a PERSON made by hand is a
    promise, whether or not anybody ever pressed the now-tolerant Acknowledge (S1) - a
    manual link, not `ack_state`, is what freezes a row against the re-deal.

    S3 reversal: the raise-time cascade only SUGGESTS the far document now - there is
    no real "draft" to take down first any more, AC-LT-15's own trim does that the
    moment the manual link below lands on the same target.
    """
    _client, world = api
    far, far_line = _open_po_line(world, qty=50, expected_date=date(2026, 12, 1))
    row = _raise_one_row(api)["row"]
    assert _link_documents(world, row) == [], "the raise-time cascade only suggests"
    assert _suggested_documents(world, row) == [far.po_number]

    # Link it BY HAND, so the row's one link is genuinely a person's choice rather than
    # the walk's - the suggestion above is trimmed automatically the moment this lands.
    ProjectOrderInquiryService(world.db).place_on_po_allocations(
        row.id, [{"po_line_id": str(far_line.id), "qty": "10"}], actor_user_id=world.buyer,
    )
    world.db.commit()
    assert _suggested_documents(world, row) == []

    with _as_purchasing(world) as buyer:
        _open_po_line(world, qty=50, expected_date=date(2026, 7, 1))
        assert buyer.post(LINK_NOW, json={}).status_code == 200
    world.db.commit()

    assert _link_documents(world, row) == [far.po_number]


# ---------------------------------------------------------------------------
# AC-D11: the purchase-order confirm
# ---------------------------------------------------------------------------


def test_a_purchase_order_confirm_links_an_awaiting_row(api):
    """A plan-generated purchase order is confirmed and the rows that sized it read it,
    even though the row itself is born `awaiting` (`PLAN-oi-confirm-per-so.md` S1) and
    never pressed: this cascade never waited on the handshake, R6.

    S3 reversal: the plan-generated line carries no book match, so the confirm's own
    cascade SUGGESTS it, it never writes a real link.
    """
    from app.services.scm.purchase_order_service import PurchaseOrderService

    _client, world = api
    row = _raise_one_row(api)["row"]
    assert _links_of(world, row) == []

    supplier = _supplier(world)
    po = PurchaseOrder(
        id=_uid(),
        company_id=world.company_id,
        po_number=f"ZZT-DRAFT-{_uid()[:8]}",
        supplier_id=supplier.id,
        status="draft_recommendation",
    )
    world.db.add(po)
    world.db.flush()
    world.db.add(
        PurchaseOrderLine(
            id=_uid(),
            company_id=world.company_id,
            purchase_order_id=po.id,
            product_id=world.product.id,
            warehouse_id=world.warehouse.id,
            qty_ordered=Decimal("50"),
            qty_received=Decimal("0"),
            expected_date=date(2026, 8, 10),
            line_status="open",
        )
    )
    world.db.commit()

    PurchaseOrderService(world.db).bulk_confirm([str(po.id)], actor=world.buyer)

    world.db.expire_all()
    row = world.db.query(OrderInquiryRow).filter(OrderInquiryRow.id == row.id).one()
    assert row.ack_state == ACK_AWAITING
    assert _links_of(world, row) == []
    assert len(_suggested_of(world, row)) == 1


# ---------------------------------------------------------------------------
# AC-D12: the To confirm filter
# ---------------------------------------------------------------------------


def test_the_to_confirm_filter_is_awaiting_and_changed(api):
    """A row is born `awaiting` again (`PLAN-oi-confirm-per-so.md` S1), so `awaiting`
    needs no forcing here; `changed` still needs a direct write to seed without a whole
    settle chain, and `confirmed` needs a genuine Confirm press to leave `to_confirm`."""
    client, world = api
    awaiting = _raise_one_row(api, qty="4")["row"]
    changed = _raise_one_row(api, qty="6")["row"]
    confirmed = _raise_one_row(api, qty="8")["row"]

    changed.ack_state = ACK_CHANGED
    changed.changed_at = datetime.utcnow()
    world.db.commit()

    with _as_purchasing(world) as buyer:
        assert (
            buyer.post(ACK_URL, json={"row_ids": [str(confirmed.id)]}).status_code == 200
        )
    world.db.commit()

    body = client.get(LIST, params={"ack": "to_confirm", "limit": 200}).json()
    ids = {item["id"] for item in body["data"]}

    assert str(awaiting.id) in ids
    assert str(changed.id) in ids
    assert str(confirmed.id) not in ids


def test_the_summary_facet_to_confirm_stays_the_sum_and_moves_on_confirm_and_change(api):
    """S3: `to_confirm` is `awaiting + changed`, always - that identity never breaks. A
    fresh raise is born `awaiting` again (`PLAN-oi-confirm-per-so.md` S1), so it moves the
    facet UP by one; purchasing's own Confirm press moves it back DOWN by one (into
    `acknowledged`, off `to_confirm`); a later settle on that confirmed row moves it back
    UP again (into `changed`). Asserted as a DELTA, not an absolute count: this suite runs
    against a real Postgres database that already carries historical rows."""
    client, world = api
    _open_po_line(world, qty=50)
    before = client.get(f"{LIST}/summary").json()["ack"]
    assert before["to_confirm"] == before["awaiting"] + before["changed"]

    fresh = _raise_one_row(api, qty="4")
    _raise_one_row(api, qty="6")

    after_raise = client.get(f"{LIST}/summary").json()["ack"]
    assert after_raise["to_confirm"] == after_raise["awaiting"] + after_raise["changed"]
    assert after_raise["to_confirm"] == before["to_confirm"] + 2, (
        "two freshly-raised rows are born awaiting - both move the facet"
    )

    with _as_purchasing(world) as buyer:
        assert (
            buyer.post(ACK_URL, json={"row_ids": [str(fresh["row"].id)]}).status_code
            == 200
        )
    world.db.commit()

    after_confirm = client.get(f"{LIST}/summary").json()["ack"]
    assert after_confirm["to_confirm"] == before["to_confirm"] + 1, (
        "the confirmed row leaves to_confirm; the other fresh raise stays on it"
    )

    # A genuine settle on the now-confirmed row: it goes BACK to To confirm as `changed`.
    _settle(world, fresh, qty="9")
    world.db.commit()

    settled = client.get(f"{LIST}/summary").json()["ack"]
    assert settled["changed"] == after_confirm["changed"] + 1
    assert settled["to_confirm"] == settled["awaiting"] + settled["changed"]
    assert settled["to_confirm"] == before["to_confirm"] + 2


def test_the_export_accepts_to_confirm(api):
    """Not a status check alone: `to_confirm` FILTERS the sheet the same way it filters the
    list - a freshly-raised row (`PLAN-oi-confirm-per-so.md` S1) is on it with no forcing
    needed, and one a genuine Confirm press has taken on is off it."""
    client, world = api
    to_confirm = _raise_one_row(api, qty="4")
    confirmed = _raise_one_row(api, qty="6")
    with _as_purchasing(world) as buyer:
        assert (
            buyer.post(
                ACK_URL, json={"row_ids": [str(confirmed["row"].id)]}
            ).status_code
            == 200
        )
    world.db.commit()

    export = client.get(f"{LIST}/export", params={"ack": "to_confirm"})

    assert export.status_code == 200, export.text
    import openpyxl

    book = openpyxl.load_workbook(io.BytesIO(export.content))
    assert book.sheetnames
    numbers: set[str] = set()
    for name in book.sheetnames:
        for row in book[name].iter_rows(min_row=3, values_only=True):
            if row and row[1]:
                numbers.add(str(row[1]))
    assert to_confirm["core_so"].so_number in numbers
    assert confirmed["core_so"].so_number not in numbers


def test_an_unknown_acknowledgement_filter_is_still_refused(api):
    client, _world = api

    assert client.get(LIST, params={"ack": "maybe"}).status_code == 422


# ---------------------------------------------------------------------------
# AC-D16 / AC-D17: what the column reads
# ---------------------------------------------------------------------------


def test_a_late_document_says_how_many_days_late_it_is(api):
    """S3 reversal: the open line carries no book match, so the raise-time cascade
    only SUGGESTS it - `late_days` is on the `suggested_links` wire shape too (plan
    3.5), `late` (a real-link-only field) is not."""
    client, world = api
    _open_po_line(world, qty=50, expected_date=LATE_ARRIVAL)
    row = _raise_one_row(api)["row"]

    listed = _listed(client, row)
    assert listed["links"] == []
    suggestion = listed["suggested_links"][0]

    assert suggestion["late_days"] == LATE_BY


def test_a_document_that_lands_in_time_states_no_day_count(api):
    """S3 reversal: no book match, so the row's own take is a suggestion."""
    client, world = api
    _open_po_line(world, qty=50, expected_date=date(2026, 8, 1))
    row = _raise_one_row(api)["row"]

    listed = _listed(client, row)
    assert listed["links"] == []
    suggestion = listed["suggested_links"][0]

    assert suggestion["late_days"] is None


def test_an_spo_link_reads_its_pool_location_rather_than_a_line_number(api):
    """S3 reversal: the SPO allocation carries no book match, so the row's own take is
    a suggestion - `suggested_links` carries `location` (plan 3.5), never `line_label`,
    which is a real-link-only field (a suggestion is not a commitment to one line)."""
    client, world = api
    pool = _pooled(world)
    _spo_line(world, qty=50, warehouse=pool, line_no=14)
    row = _raise_one_row(api)["row"]

    listed = _listed(client, row)
    assert listed["links"] == []
    suggestion = listed["suggested_links"][0]

    assert suggestion["kind"] == "spo"
    assert suggestion["location"] == pool.warehouse_code


def test_an_spo_link_with_no_warehouse_falls_back_to_the_books_own_code(api):
    """The banded history book states no warehouse; the code it printed is still a fact."""
    client, world = api
    _pooled(world)
    row = _raise_one_row(api)["row"]
    allocation = _spo_line(
        world, qty=50, warehouse=None, location_code="BRW-NOWHERE"
    )
    # Written straight, not through the cascade: this pins the SERIALIZER's fallback, and
    # a line at a code we hold no warehouse for is never a candidate (R11) by design.
    world.db.add(
        OrderInquiryLink(
            id=_uid(),
            company_id=world.company_id,
            row_id=row.id,
            spo_allocation_id=allocation.id,
            document=allocation.spo_number,
            qty=Decimal("10"),
        )
    )
    world.db.commit()

    link = _listed(client, row)["links"][0]

    assert link["location"] == "BRW-NOWHERE"


def test_the_sales_order_detail_carries_the_day_count_too(api):
    """The SO detail is a second reader of the same link, and `response_model` drops a
    field it has not been told about just as silently there.

    S3 reversal: the open line carries no book match, so the row's own take is a
    suggestion (AC-LT-33: `suggested_links` on the wire too, same field)."""
    client, world = api
    _open_po_line(world, qty=50, expected_date=LATE_ARRIVAL)
    fixture = _raise_one_row(api)

    body = client.get(
        f"{BASE}/sales-orders/{fixture['order'].id}/order-inquiry"
    ).json()
    row = next(item for item in body["rows"] if item["id"] == str(fixture["row"].id))

    assert row["links"] == []
    assert row["suggested_links"][0]["late_days"] == LATE_BY


# ---------------------------------------------------------------------------
# AC-D18 / AC-D19: the lightboxes
# ---------------------------------------------------------------------------


def test_the_purchase_order_lightbox_names_who_is_holding_the_quantity(api):
    """No manual press ever happens here, so the row is born `awaiting`
    (`PLAN-oi-confirm-per-so.md` S1) - the panel reads the link off it either way, since
    the raise-time cascade never waited on the handshake.

    S3 reversal: the open line carries no book match, so what lands on the row is a
    SUGGESTION, never a real link - `allocations` (real links only) stays empty.

    Review round 2 Should fix 5 (AC-LT-34, amended): the lightbox's own "Suggested
    for" panel is retired - R13 replaced it with the Lines tab's own Allocated/
    Suggested columns, the WHOLE answer now, so `suggested_links` never reaches
    this wire at all any more.
    """
    client, world = api
    po, _line = _open_po_line(world, qty=50)
    _raise_one_row(api, qty="10")

    body = client.get(f"{LIST}/po/{po.id}").json()

    assert body["allocations"] == [], "no real link sits on the suggested-only line"
    assert "suggested_links" not in body, "the retired lightbox panel is gone from the wire"


def test_the_purchase_order_lightbox_reads_a_manual_acknowledge_press_as_confirmed_too(api):
    """A redundant press over an already-acknowledged row is a tolerant no-op (G4) - the
    panel reads it as confirmed either way.

    S3: the open line carries no book match, so acknowledging only refreshes the row's
    own suggestion - the REAL link this test's own subject (the panel's `ack_state`
    reading) needs is seeded directly here, through `place_on_po_allocations`, the
    same manual path a buyer's own press takes.
    """
    client, world = api
    po, line = _open_po_line(world, qty=50)
    row = _raise_one_row(api, qty="10")["row"]
    with _as_purchasing(world) as buyer:
        assert buyer.post(ACK_URL, json={"row_ids": [str(row.id)]}).status_code == 200
    world.db.commit()
    ProjectOrderInquiryService(world.db).place_on_po_allocations(
        str(row.id), [{"po_line_id": str(line.id), "qty": "10"}], actor_user_id=world.buyer,
    )
    world.db.commit()

    body = client.get(f"{LIST}/po/{po.id}").json()

    assert body["allocations"][0]["ack_state"] == ACK_ACKNOWLEDGED


def test_the_shipping_order_lightbox_answers_its_lines(api):
    client, world = api
    pool = _pooled(world)
    shipment = InboundShipment(
        id=_uid(),
        company_id=world.company_id,
        shipment_number=f"ZZT-SHIP-{_uid()[:8]}",
        shipment_date=date(2026, 8, 1),
        shipping_container_number=f"ZZTU{_uid()[:7].upper()}",
    )
    world.db.add(shipment)
    world.db.flush()
    allocation = _spo_line(world, qty=50, warehouse=pool, shipment=shipment)

    response = client.get(f"{LIST}/spo/{quote(allocation.spo_number, safe='')}")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["spo_number"] == allocation.spo_number
    assert body["shipment_ref"] == shipment.shipment_number
    assert body["container_no"] == shipment.shipping_container_number
    line = body["lines"][0]
    assert line["sku"] == world.product.product_code
    assert line["allocated"] == "50"
    assert line["received"] == "0"
    assert line["remaining"] == "50"
    assert line["location"] == pool.warehouse_code


def test_the_shipping_order_lightbox_names_who_is_holding_it(api):
    """No manual press ever happens here, so the row is born `awaiting`
    (`PLAN-oi-confirm-per-so.md` S1) - the panel reads the link off it either way, since
    the raise-time cascade never waited on the handshake.

    S3 reversal: the allocation carries no book match, so what lands on the row is a
    SUGGESTION, never a real link - `allocations` stays empty.

    Review round 2 Should fix 5 (AC-LT-34, amended): same reversal as the PO
    lightbox's own sibling test above - the "Suggested for" panel is retired.
    """
    client, world = api
    pool = _pooled(world)
    allocation = _spo_line(world, qty=50, warehouse=pool)
    _raise_one_row(api, qty="10")

    body = client.get(f"{LIST}/spo/{quote(allocation.spo_number, safe='')}").json()

    assert body["allocations"] == [], "no real link sits on the suggested-only allocation"
    assert "suggested_links" not in body, "the retired lightbox panel is gone from the wire"


# ---------------------------------------------------------------------------
# Issue #1215 point 2: the lightbox names WHICH line an allocation sits on, and
# the PO lines grid states each line's own Allocated total.
# ---------------------------------------------------------------------------


def test_the_purchase_order_lightbox_allocation_names_the_line_its_own_qty_sits_on(api):
    """S3: the open line carries no book match, so the raise-time cascade only
    SUGGESTS it - `po_line_id` on a real allocation and a line's own `allocated`
    total (Issue #1215 point 2) are both real-link concepts, so the link this test's
    subject needs is seeded directly here, through `place_on_po_allocations`."""
    client, world = api
    po, line = _open_po_line(world, qty=50)
    row = _raise_one_row(api, qty="10")["row"]
    ProjectOrderInquiryService(world.db).place_on_po_allocations(
        str(row.id), [{"po_line_id": str(line.id), "qty": "10"}], actor_user_id=None,
    )
    world.db.commit()

    body = client.get(f"{LIST}/po/{po.id}").json()

    assert body["allocations"][0]["po_line_id"] == line.id
    detail_line = body["lines"][0]
    assert detail_line["id"] == line.id
    assert detail_line["allocated"] == "10"


def test_the_purchase_order_lines_grid_allocated_is_per_line_not_the_whole_document(api):
    """A PO with two lines of the SAME item is exactly what made the OLD panel
    ambiguous (diagnosis point 2: the Item column happened to identify the line only
    because the PO had one line per product). Only the line an order inquiry row is
    actually linked to reads a non-zero Allocated; the other line of the same item
    reads zero.

    S3: a line's own `allocated` total is a real-link concept - the raise-time
    cascade would only SUGGEST here, so the real link this test's subject needs is
    seeded directly, through `place_on_po_allocations`.
    """
    client, world = api
    po, taken_line = _open_po_line(world, qty=50)
    free_line = PurchaseOrderLine(
        id=str(uuid.uuid4()),
        company_id=world.company_id,
        purchase_order_id=po.id,
        product_id=world.product.id,
        warehouse_id=world.warehouse.id,
        qty_ordered=Decimal("30"),
        qty_received=Decimal("0"),
        expected_date=date(2026, 9, 1),
        line_status="open",
    )
    world.db.add(free_line)
    world.db.commit()
    row = _raise_one_row(api, qty="10")["row"]
    ProjectOrderInquiryService(world.db).place_on_po_allocations(
        str(row.id), [{"po_line_id": str(taken_line.id), "qty": "10"}], actor_user_id=None,
    )
    world.db.commit()

    body = client.get(f"{LIST}/po/{po.id}").json()

    lines_by_id = {line["id"]: line for line in body["lines"]}
    assert lines_by_id[taken_line.id]["allocated"] == "10"
    assert lines_by_id[free_line.id]["allocated"] == "0"


def test_the_shipping_order_lightbox_line_carries_its_own_id(api):
    """R15 (owner rulings, 25 Sep 2026, hand test on stack C): the SPO lightbox never
    highlighted its own linked line the way the PO lightbox does (issue #1215 point 2) -
    `get_po_detail` sends each line's own `id`, `get_spo_detail` never did. Without it
    the FE has no field to match a link's `spo_allocation_id` against."""
    client, world = api
    pool = _pooled(world)
    allocation = _spo_line(world, qty=50, warehouse=pool)

    body = client.get(f"{LIST}/spo/{quote(allocation.spo_number, safe='')}").json()

    assert body["lines"][0]["id"] == allocation.id


def test_the_shipping_order_lightbox_highlights_the_real_linked_line_not_by_product(api):
    """R15: the SPO lightbox must highlight the SPO line the OI row's own real link
    names - `OrderInquiryLink.spo_allocation_id`, the exact allocation the cascade or a
    person resolved through the SO line / PO line chain - never a re-match by product or
    by source PO number on the frontend. Two lines of the SAME product prove the
    identity is the FK, not a product guess."""
    client, world = api
    pool = _pooled(world)
    taken = _spo_line(world, qty=50, warehouse=pool, spo_number="SPO-2026/09-ZZT1", line_no=1)
    _other = _spo_line(
        world, qty=30, warehouse=pool, spo_number="SPO-2026/09-ZZT1", line_no=2,
    )
    row = _raise_one_row(api, qty="10")["row"]
    ProjectOrderInquiryService(world.db).place_on_po_allocations(
        str(row.id), [{"spo_allocation_id": str(taken.id), "qty": "10"}], actor_user_id=None,
    )
    world.db.commit()

    body = client.get(f"{LIST}/spo/{quote(taken.spo_number, safe='')}").json()
    wire_link = next(
        link for link in _links_of(world, row) if link.spo_allocation_id == taken.id
    )

    assert wire_link.spo_allocation_id == taken.id
    lines_by_id = {line["id"]: line for line in body["lines"]}
    assert taken.id in lines_by_id
    assert _other.id in lines_by_id
    assert taken.id != _other.id


def test_the_shipping_order_lightbox_404s_on_a_number_nobody_holds(api):
    client, _world = api

    response = client.get(f"{LIST}/spo/{quote('SPO-2026/08-NOPE', safe='')}")

    assert response.status_code == 404


def test_the_shipping_order_lightbox_denies_a_user_without_the_view_grant(world):
    pool = _pooled(world)
    allocation = _spo_line(world, qty=50, warehouse=pool)
    client, originals = _client(world.db, world.buyer, [])
    try:
        response = client.get(f"{LIST}/spo/{quote(allocation.spo_number, safe='')}")
    finally:
        _restore(originals)

    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Review round (28 Aug): the re-deal never costs a row the links it already has
# ---------------------------------------------------------------------------


def test_auto_link_all_keeps_the_draft_of_a_row_that_is_now_past_the_cut_off(api):
    """B1. The unplace used to run over the WHOLE scope before the per-row guards, so a
    drafted row the buyer had since moved past the cut off lost its documents and was
    reported as merely "held back". A press that leaves a row alone must leave its links
    alone: the cut off says "do not deal this one", not "take back what it holds".

    S3 reversal: the open line carries no book match, so the raise found a
    SUGGESTION, not a real link - the horizon guard (`_after_horizon`, checked before
    any candidate walk) `continue`s before `_write_suggested_links` ever runs, so the
    guarantee holds identically: the same suggestion, untouched.
    """
    _client, world = api
    _po, _line = _open_po_line(world, qty=50)
    row = _raise_one_row(api, qty="10")["row"]
    before = [str(s.id) for s in _suggested_of(world, row)]
    assert before, "the suggestion has to exist for the test to mean anything"

    row.delivery_date = FAR
    world.db.flush()
    world.db.commit()

    with _as_purchasing(world) as buyer:
        response = buyer.post(AUTO_PLACE, json={"link_up_to": HORIZON.isoformat()})
    assert response.status_code == 200, response.text
    world.db.commit()

    # `>= 1`: this suite runs on the shared prod-copy database, whose own rows are past
    # this cut off too. What matters is that THIS row was counted and left alone.
    assert response.json()["after_horizon"] >= 1
    assert [str(s.id) for s in _suggested_of(world, row)] == before


def test_auto_link_all_drops_the_suggestion_when_the_document_has_since_closed(api):
    """B1, the other half - REVERSED by review round 2 Blocking 5 (AC-LT-19, dated 25
    Sep 2026). The old B1 reason ("the old answer is still the best one anybody has")
    applied to a real DRAFT link the row actually held - taking it down really did
    lose the row its document. A SUGGESTION is a guess, never a placement, and a
    closed line offered to a row is the exact defect behind issue #1215 point 3: the
    honest end of a stale guess is that it goes, not that it lingers because nothing
    else was found to replace it with.

    S3 reversal, now reversed again: the open line carries no book match, so the
    raise found a SUGGESTION - the walk `continue`s the moment candidates come back
    empty, and now drops the row's stale suggestion there rather than leaving it
    standing.
    """
    _client, world = api
    _po, line = _open_po_line(world, qty=50)
    row = _raise_one_row(api, qty="10")["row"]
    before = [str(s.id) for s in _suggested_of(world, row)]
    assert before

    line.line_status = "closed"
    world.db.flush()
    world.db.commit()

    with _as_purchasing(world) as buyer:
        assert buyer.post(AUTO_PLACE, json={}).status_code == 200
    world.db.commit()

    assert _suggested_of(world, row) == []
    assert _suggested_documents(world, row) == []


def test_two_presses_of_auto_link_all_change_nothing_at_all(api):
    """S4. The re-deal deleted and rewrote identical links on every press, and wrote
    "Unlinked from X; Re-dealt by worklist" onto the row's note each time - so a buyer who
    pressed the button twice read a row that looked like it had moved twice. The take is
    computed first, and a take that matches what the row already holds is skipped."""
    _client, world = api
    _open_po_line(world, qty=50)
    row = _raise_one_row(api, qty="10")["row"]

    with _as_purchasing(world) as buyer:
        assert buyer.post(AUTO_PLACE, json={}).status_code == 200
        world.db.commit()
        world.db.refresh(row)
        first = [str(link.id) for link in _links_of(world, row)]
        note = row.note
        assert buyer.post(AUTO_PLACE, json={}).status_code == 200
    world.db.commit()

    world.db.refresh(row)
    assert [str(link.id) for link in _links_of(world, row)] == first
    assert row.note == note


# ---------------------------------------------------------------------------
# B2: a re-confirm of a DRAFTED row settles it rather than netting it as bought
# ---------------------------------------------------------------------------


def test_a_reconfirm_with_a_new_date_moves_the_drafted_row_onto_that_date(api):
    """B2, as refined in the CI round (28 Aug). A draft made the row `placed`, and the
    reconfirm netted it as supply already bought - so a board re-confirm carrying a new
    delivery date did nothing at all and the row went on saying the old one. A row nobody
    has confirmed is an instruction, not supply, so it SETTLES IN PLACE: the same row takes
    the new date, keeps the document the raise found for it, and says what it was before.

    It settles rather than being superseded and re-raised, because the same apply may have
    just SHIFTED a closed line's placement onto this row (AC-P3-6) and a re-raise would
    hand that placement straight back to a stranger.

    S3 reversal: the open line carries no book match, so the raise found a
    SUGGESTION, not a real link - the row is `raised`, never `placed`, and
    `_settle_row_in_place`'s own widened gate (`named_raised`, AC-R2-10/11) still
    reaches a plain raised row with no real links, settling it the same way.

    Review round 2 Blocking 5, "decide it the same way" as the closed-line reversal
    beside this one: the settle itself touches no suggestion, but this SAME confirm
    also runs `_draft_links_for_decision`'s fresh cascade pass straight after the
    handoff (`ProjectSupplyService.confirm`), scoped to this decision's own rows -
    so the suggestion IS re-derived here, not merely left alone. It reads unchanged
    (same id, same `suggested_at`, via `_same_placement`) because the PO line is
    still a valid, in-window candidate under the new date - the honest answer, not
    a stale one surviving by accident. Had the date change pushed the line outside
    the window, Blocking 5's own fix would drop it exactly as the closed-line test
    beside this one now expects.
    """
    _client, world = api
    po, _line = _open_po_line(world, qty=50)
    fixture = _raise_one_row(api)
    row = fixture["row"]
    assert _suggested_of(world, row), "the suggestion has to exist for the test to mean anything"

    fixture["core_line"].required_date = NOW
    fixture["line"].delivery_date = NOW
    world.db.flush()
    response = _confirm(
        _client, fixture["order"].id, [_line_payload(fixture["line"].id, buy_qty="10")]
    )
    assert response.status_code == 200, response.text
    world.db.commit()

    world.db.refresh(row)
    assert row.state == INQUIRY_RAISED, "no real document, never placed"
    survivor = _order_row(world, fixture["line"])
    assert str(survivor.id) == str(row.id), "the same instruction, not a second one"
    assert survivor.delivery_date == NOW
    assert _link_documents(world, survivor) == []
    assert _suggested_documents(world, survivor) == [po.po_number], (
        "the document the raise found for it is kept, never re-dealt"
    )
    assert survivor.previous_delivery_date == WAS, "and the row says what it was before"


def test_a_reconfirm_that_lowers_a_drafted_rows_quantity_raises_no_exception(api):
    """B2. `placed > need` wrote a CANCEL_BALANCE exception - "purchasing bought 10, CS now
    wants 4" - about a purchase nobody had agreed to.

    S3 reversal: the open line carries no book match, so the raise only SUGGESTED it -
    there is no real link for the settle to give back."""
    _client, world = api
    _open_po_line(world, qty=50)
    fixture = _raise_one_row(api, qty="10")
    row = fixture["row"]

    fixture["core_line"].qty_ordered = Decimal("4")
    fixture["line"].qty = Decimal("4")
    world.db.flush()
    response = _confirm(
        _client, fixture["order"].id, [_line_payload(fixture["line"].id, buy_qty="4")]
    )
    assert response.status_code == 200, response.text
    world.db.commit()

    assert response.json()["exceptions"] == []
    assert _cancel_balance_rows(world, fixture["line"]) == []
    live = _live_rows(world, fixture["line"])
    assert [str(item.qty) for item in live] == ["4.0000"]
    assert _links_of(world, live[0]) == []


def test_a_reconfirm_that_raises_a_drafted_rows_quantity_leaves_one_row(api):
    """B2. The netting split the line: 10 already "placed" plus a fresh 5, two rows in
    front of purchasing for one instruction. One row of 15, drafted.

    S3 reversal: the open line carries no book match, so the raise only SUGGESTED it -
    there is no real link for the settled row to carry."""
    _client, world = api
    _open_po_line(world, qty=50)
    fixture = _raise_one_row(api, qty="10")

    fixture["core_line"].qty_ordered = Decimal("15")
    fixture["line"].qty = Decimal("15")
    world.db.flush()
    response = _confirm(
        _client, fixture["order"].id, [_line_payload(fixture["line"].id, buy_qty="15")]
    )
    assert response.status_code == 200, response.text
    world.db.commit()

    live = _live_rows(world, fixture["line"])
    assert [str(item.qty) for item in live] == ["15.0000"]
    assert _links_of(world, live[0]) == []


def test_a_confirmed_rows_links_survive_a_reconfirm_untouched(api):
    """The other side of B2, and the rule it must not break: purchasing said yes, so the
    row IS supply and a reconfirm nets it exactly as it always did.

    S3: the open line carries no book match, so acknowledging only suggests it - the
    row's own REAL link, the fact this test's subject (a confirmed row's promise
    surviving a reconfirm) depends on, is seeded directly here, through
    `place_on_po_allocations`, the same manual path a buyer's own press takes.
    """
    _client, world = api
    po, line = _open_po_line(world, qty=50)
    fixture = _raise_one_row(api, qty="10")
    row = fixture["row"]
    with _as_purchasing(world) as buyer:
        assert buyer.post(ACK_URL, json={"row_ids": [str(row.id)]}).status_code == 200
    world.db.commit()
    ProjectOrderInquiryService(world.db).place_on_po_allocations(
        str(row.id), [{"po_line_id": str(line.id), "qty": "10"}], actor_user_id=world.buyer,
    )
    world.db.commit()
    before = [str(link.id) for link in _links_of(world, row)]

    response = _confirm(
        _client, fixture["order"].id, [_line_payload(fixture["line"].id, buy_qty="10")]
    )
    assert response.status_code == 200, response.text
    world.db.commit()

    world.db.refresh(row)
    assert row.ack_state == ACK_ACKNOWLEDGED
    assert row.state == INQUIRY_PLACED
    assert [str(link.id) for link in _links_of(world, row)] == before
    assert _link_documents(world, row) == [po.po_number]


# ---------------------------------------------------------------------------
# B3: a drafted row whose line leaves the revision is retired with it
# ---------------------------------------------------------------------------


def test_a_drafted_row_is_retired_when_its_line_leaves_the_revision(api):
    """B3. The retirement read `raised` only, and a drafted row is `placed` - so a line CS
    took back out of the decision left its row alive, holding purchase-order quantity for
    an instruction that no longer exists.

    S3 reversal: the open line carries no book match, so both rows only hold
    SUGGESTIONS - `_retire_uncovered_rows`'s own RAISED branch cancels a raised row
    unconditionally regardless of what it holds, so the retirement itself is
    unaffected; only the fixture-check and the "kept" assertion move to the
    suggested-links table."""
    from app.services.project_supply_service import ProjectSupplyService

    _client, world = api
    _po, line = _open_po_line(world, qty=50)
    fixture = _raise_two_rows(api)
    dropped = fixture["first"]["row"]
    kept = fixture["second"]["row"]
    assert _suggested_of(world, dropped), "the suggestion has to exist for the test to mean anything"

    ProjectSupplyService(world.db).uncover_lines(
        fixture["order"],
        [str(fixture["first"]["line"].id)],
        actor_user_id=world.cs_user,
        reason="CS took the line back.",
    )
    world.db.commit()

    world.db.refresh(dropped)
    assert dropped.state == INQUIRY_CANCELLED
    assert _links_of(world, dropped) == []
    assert _live_rows(world, fixture["first"]["line"]) == []
    assert _suggested_of(world, _order_row(world, fixture["second"]["line"])), (
        "the line the revision kept keeps its own suggestion"
    )
    assert kept is not None


def test_a_manually_linked_row_survives_retire_when_its_line_leaves_the_revision(api):
    """S1/S7 (review of PR #471). The other half of B3: `_cascade_only` is what decides
    a row is retirable now, not `ack_state` - and a row a PERSON has manually linked
    (`place_on_po`, not the raise-time cascade) is exactly what that check has to leave
    alone. A retirement that swept it up anyway would take a promise a buyer made back
    from them without asking.

    S3 reversal: the open line carries no book match, so the raise-time cascade only
    SUGGESTS it - there is no real "draft" to take down first any more, so the row is
    linked BY HAND directly, the same technique
    `test_auto_link_all_never_moves_a_manually_linked_rows_link` uses. `_cascade_only`
    then reads a lone MANUAL link the same way it always did - the row must be
    `placed`, not `raised`, or the retirement's own unconditional RAISED branch would
    cancel it regardless of what it holds.
    """
    from app.services.project_supply_service import ProjectSupplyService

    _client, world = api
    po, po_line = _open_po_line(world, qty=50)
    fixture = _raise_two_rows(api)
    dropped = fixture["first"]["row"]
    assert _suggested_of(world, dropped), "the raise-time cascade has to have suggested it first"

    ProjectOrderInquiryService(world.db).place_on_po(
        str(dropped.id), str(po_line.id), actor_user_id=world.buyer
    )
    world.db.commit()
    world.db.refresh(dropped)
    assert dropped.state == INQUIRY_PLACED, "a manual link covering it whole"

    ProjectSupplyService(world.db).uncover_lines(
        fixture["order"],
        [str(fixture["first"]["line"].id)],
        actor_user_id=world.cs_user,
        reason="CS took the line back.",
    )
    world.db.commit()

    world.db.refresh(dropped)
    assert dropped.state != INQUIRY_CANCELLED, "a manual link is a promise, left exactly as it is"
    assert _link_documents(world, dropped) == [po.po_number]


def test_a_linkless_placed_row_is_skipped_by_retire_not_swept_up(api):
    """S1/S7 (review of PR #471). `all()` over an EMPTY link list is vacuously True, which
    used to read a row purchasing placed through a path that writes no link row (the
    SO349754/WESERP10B shape - `_settle_row_in_place`'s own guard exists for the identical
    reason) as "cascade-only" and free to retire. `_cascade_only` refuses an empty list
    outright, so a linkless placed row is left standing when its line drops."""
    from app.services.project_supply_service import ProjectSupplyService

    _client, world = api
    fixture = _raise_two_rows(api)
    dropped = fixture["first"]["row"]
    assert _links_of(world, dropped) == [], (
        "linkless has to be true for this test to mean anything - no PO was ever opened"
    )
    dropped.state = INQUIRY_PLACED
    world.db.commit()

    ProjectSupplyService(world.db).uncover_lines(
        fixture["order"],
        [str(fixture["first"]["line"].id)],
        actor_user_id=world.cs_user,
        reason="CS took the line back.",
    )
    world.db.commit()

    world.db.refresh(dropped)
    assert dropped.state == INQUIRY_PLACED, "left standing, not retired out from under it"


# ---------------------------------------------------------------------------
# B4: a batch reject over two lines of ONE order
# ---------------------------------------------------------------------------


def _raise_three_rows(api):
    """One order, THREE lines, all confirmed as Buy - the shape a batch reject needs.

    Two lines are refused and the third is not, so the un-decide has a surviving line to
    carry: that is what makes the press write a revision at all (an order whose every
    covered line is refused is superseded outright, and there is no "one revision per
    order" to count).
    """
    from .test_planning_changes import _core_line, _core_so, _project_line, _project_so

    client, world = api
    db = world.db
    core_so = _core_so(db, world.company_id)
    order = _project_so(
        db, world.project, so_id=core_so.id, autocount_doc_no=core_so.so_number
    )
    made = []
    for index, qty in enumerate(("10", "6", "4"), start=1):
        core_line = _core_line(
            db, core_so, world.product, world.warehouse, qty_ordered=qty,
            required_date=WAS,
        )
        line = _project_line(
            db, order, line_no=index, product=world.product, core_line=core_line
        )
        made.append({"line": line, "core_line": core_line, "qty": qty})
    db.commit()

    response = _confirm(
        client,
        order.id,
        [_line_payload(entry["line"].id, buy_qty=entry["qty"]) for entry in made],
    )
    assert response.status_code == 200, response.text
    db.commit()
    for entry in made:
        entry["row"] = _order_row(world, entry["line"])
    return {"order": order, "lines": made}


def test_the_batch_reject_of_two_lines_of_one_order_refuses_both(api):
    """B4. Each row was uncovered on its own, and uncovering ONE line writes a revision
    that cancels and re-raises the OTHER lines' rows - so the second refusal stamped a row
    that had just been superseded, and its live replacement went on sitting in front of
    purchasing as if nobody had refused it. The batch uncovers a whole order in one call:
    one revision, and every refused line named in it.
    """
    _client, world = api
    _open_po_line(world, qty=50)
    fixture = _raise_three_rows(api)
    first, second, kept = (entry["row"] for entry in fixture["lines"])
    # S3 reversal: the open line carries no book match, so the raise only SUGGESTED it.
    assert _suggested_of(world, first), "the suggestions have to exist for the test to mean anything"
    revisions_before = _revision_count(world, fixture["order"])

    with _as_purchasing(world) as buyer:
        response = buyer.post(
            REJECT_BATCH,
            json={"row_ids": [str(first.id), str(second.id)], "reason": "No supplier"},
        )
    assert response.status_code == 200, response.text
    world.db.commit()

    for row in (first, second):
        world.db.refresh(row)
        assert row.ack_state == ACK_REJECTED, (
            "a mid-batch revision moved the row this press was refusing"
        )
        assert _links_of(world, row) == []
    for entry in fixture["lines"][:2]:
        left = [
            item
            for item in _live_rows(world, entry["line"])
            if item.ack_state != ACK_REJECTED
        ]
        assert left == [], "a line the batch refused still has a row nobody refused"
    assert _revision_count(world, fixture["order"]) == revisions_before + 1, (
        "one press, one revision per order"
    )
    assert _live_rows(world, fixture["lines"][2]["line"]), (
        "the line nobody refused is still purchasing's work"
    )
    assert kept is not None


def _live_rows(world, line) -> list:
    """Every row of this line the page still shows - what `_order_row` asks for, without
    its "exactly one" demand, because half of these tests are about how many there are."""
    return (
        world.db.query(OrderInquiryRow)
        .filter(
            OrderInquiryRow.so_line_id == line.id,
            OrderInquiryRow.verb == IV_ORDER,
            OrderInquiryRow.state != INQUIRY_CANCELLED,
        )
        .order_by(OrderInquiryRow.created_at.asc())
        .all()
    )


def _cancel_balance_rows(world, line) -> list:
    """The "purchasing bought more than CS now wants" exception rows on this line."""
    from app.models.project_so import IV_CANCEL_BALANCE

    return (
        world.db.query(OrderInquiryRow)
        .filter(
            OrderInquiryRow.so_line_id == line.id,
            OrderInquiryRow.verb == IV_CANCEL_BALANCE,
            OrderInquiryRow.state != INQUIRY_CANCELLED,
        )
        .all()
    )


def _revision_count(world, order) -> int:
    from app.models.project_so import SOSupplyDecision

    return (
        world.db.query(SOSupplyDecision)
        .filter(SOSupplyDecision.project_sales_order_id == order.id)
        .count()
    )


# ---------------------------------------------------------------------------
# S1: the day count on the SCM sales order's own Linked to column
# ---------------------------------------------------------------------------


def test_the_scm_sales_order_detail_states_the_day_count_too(api):
    """S1. `SalesOrderLineLink` is a third `response_model` over the same link, and the SO
    detail's Lines tab already prints "arrives late" off it - so the number of days has to
    survive that schema as well, or the badge there says less than the same badge two
    screens away.

    S3: the open line carries no book match, so the raise-time cascade only SUGGESTS
    it - and AC-LT-38 pins the SCM sales-order detail as a real-links-only reader (no
    code change in this lane), so this test's own subject (`late_days` surviving this
    THIRD schema) needs a real link, seeded directly here through
    `place_on_po_allocations`.
    """
    _client, world = api
    _po, line = _open_po_line(world, qty=50, expected_date=LATE_ARRIVAL)
    fixture = _raise_one_row(api)
    ProjectOrderInquiryService(world.db).place_on_po_allocations(
        str(fixture["row"].id), [{"po_line_id": str(line.id), "qty": "10"}],
        actor_user_id=None,
    )
    world.db.commit()

    with _as_purchasing(world, permissions=[*PURCHASING, "scm.dashboard.view"]) as buyer:
        response = buyer.get(f"/api/v1/scm/sales-orders/{fixture['core_so'].id}")
    assert response.status_code == 200, response.text

    lines = {line["id"]: line for line in response.json()["lines"]}
    link = lines[str(fixture["core_line"].id)]["linked_to"][0]
    assert link["late"] is True
    assert link["late_days"] == LATE_BY


# ---------------------------------------------------------------------------
# S5: a plan purchase order takes the draft it was bought for
# ---------------------------------------------------------------------------


def _po_at(world, *, qty, issue_date, expected_date, status="active"):
    """One purchase order and one line, with the dates the walk sorts on stated."""
    supplier = _supplier(world)
    po = PurchaseOrder(
        id=_uid(),
        company_id=world.company_id,
        po_number=f"ZZT-PO-{_uid()[:8]}",
        supplier_id=supplier.id,
        issue_date=issue_date,
        status=status,
    )
    world.db.add(po)
    world.db.flush()
    line = PurchaseOrderLine(
        id=_uid(),
        company_id=world.company_id,
        purchase_order_id=po.id,
        product_id=world.product.id,
        warehouse_id=world.warehouse.id,
        qty_ordered=Decimal(str(qty)),
        qty_received=Decimal("0"),
        expected_date=expected_date,
        line_status="open",
    )
    world.db.add(line)
    world.db.flush()
    world.db.commit()
    return po, line


def test_a_plan_purchase_order_confirm_moves_the_draft_it_was_bought_for(api):
    """S5. The purchase-order confirm is one of the four re-deal doors (section 5.4): the
    plan bought THIS order for these rows, so its own document beats the far one the raise
    could reach at the time. Only a draft moves.

    S3 reversal: neither document carries a book match, so the "draft" is a
    SUGGESTION - which moves for free on every pass (`_write_suggested_links` always
    re-derives it).
    """
    from app.services.scm.purchase_order_service import PurchaseOrderService

    _client, world = api
    far, _far_line = _po_at(
        world, qty=50, issue_date=date(2026, 7, 1), expected_date=date(2027, 1, 1)
    )
    row = _raise_one_row(api, qty="10")["row"]
    assert _link_documents(world, row) == []
    assert _suggested_documents(world, row) == [far.po_number]

    plan_po, _line = _po_at(
        world,
        qty=50,
        issue_date=date(2026, 6, 1),
        expected_date=date(2026, 8, 10),
        status="draft_recommendation",
    )
    PurchaseOrderService(world.db).bulk_confirm([str(plan_po.id)], actor=world.buyer)
    world.db.commit()

    world.db.expire_all()
    row = world.db.query(OrderInquiryRow).filter(OrderInquiryRow.id == row.id).one()
    assert _link_documents(world, row) == []
    assert _suggested_documents(world, row) == [plan_po.po_number]


def test_a_plan_purchase_order_confirm_never_moves_a_manually_linked_rows_link(api):
    """The same press, on a row a PERSON has manually linked: its link is a promise -
    `ack_state` no longer tells the two apart (S1), a manual link does.

    S3 reversal: the open line carries no book match, so the raise-time cascade only
    SUGGESTS it - there is no real "draft" to take down first any more, AC-LT-15's
    own trim does that the moment the manual link below lands on the same target.
    """
    from app.services.scm.purchase_order_service import PurchaseOrderService

    _client, world = api
    far, far_line = _po_at(
        world, qty=50, issue_date=date(2026, 7, 1), expected_date=date(2027, 1, 1)
    )
    row = _raise_one_row(api, qty="10")["row"]
    ProjectOrderInquiryService(world.db).place_on_po_allocations(
        row.id, [{"po_line_id": str(far_line.id), "qty": "10"}], actor_user_id=world.buyer,
    )
    world.db.commit()

    plan_po, _line = _po_at(
        world,
        qty=50,
        issue_date=date(2026, 6, 1),
        expected_date=date(2026, 8, 10),
        status="draft_recommendation",
    )
    PurchaseOrderService(world.db).bulk_confirm([str(plan_po.id)], actor=world.buyer)
    world.db.commit()

    world.db.expire_all()
    row = world.db.query(OrderInquiryRow).filter(OrderInquiryRow.id == row.id).one()
    assert _link_documents(world, row) == [far.po_number]


# ---------------------------------------------------------------------------
# S6: SUPERSEDED - the plan page's chip is gone (S1, AC-1.8)
# ---------------------------------------------------------------------------


def test_a_drafted_placed_row_still_moves_the_to_confirm_count(api):
    """S6's count moves on a fresh raise again (`PLAN-oi-confirm-per-so.md` S1, the plan
    page's own chip restored): a row is born `awaiting` whether or not the raise-time
    cascade already found it a document - "waiting" is the ACK STATE alone
    (`awaiting_acknowledgement_rows`' own docstring), never `row.state`, so the row is
    purchasing's to confirm either way.

    S3 reversal: the open line carries no book match, so what the raise-time cascade
    finds is a SUGGESTION, not a real link - the row stays `raised`, which the count
    itself was never keyed on anyway.
    """
    from app.services.scm import reorder_run_service

    _client, world = api
    _open_po_line(world, qty=50)
    before = reorder_run_service.awaiting_acknowledgement_rows(world.db)

    row = _raise_one_row(api, qty="10")["row"]
    assert row.state == INQUIRY_RAISED, "no book match - only a suggestion"
    assert _suggested_of(world, row), "the suggestion has to exist for the test to mean anything"

    assert reorder_run_service.awaiting_acknowledgement_rows(world.db) == before + 1


# ---------------------------------------------------------------------------
# AC-RL-10 to AC-RL-14: a replan does not carry a received document forward
# (`PLAN-oi-replan-received-links.md`, S2). TEST-FIRST: no writer of
# `redirected_to_pool` exists yet outside `planning_change_service`'s own
# `_apply_placed_redirect`, and `_settle_row_in_place` keeps every link across a
# replan today - the red state is a row that settles in place holding a link to a
# document that has already shipped to somebody else's order, never an import error.
# ---------------------------------------------------------------------------

#: The confirmation this whole scenario replans to - SO314593's own worked example
#: (`oi-replan-received-links-acceptance-criteria.md` journey): buy 220, needed 1 Mar 2027.
REPLAN_QTY = "220"
REPLAN_DATE = date(2027, 3, 1)


def _received_spo(world, *, qty, warehouse=None) -> SPOAllocation:
    """A CLOSED, fully-received SPO allocation - `spo_supply.open_incoming_clauses()`
    fails on it twice over (closed line, received status), which is the AC-RL-10 fact
    a replan has to recognise. Seeded directly, never through the cascade: a fully
    received document has zero cascade capacity (`_candidates_for_row`), so the
    cascade itself could never be the one to write this link - it stands in for a
    placement purchasing made before the goods came in.
    """
    allocation = _spo_line(world, qty=qty, warehouse=warehouse or world.warehouse)
    allocation.quantity_received = Decimal(str(qty))
    allocation.receipt_status = "fully_received"
    allocation.line_status = "closed"
    world.db.flush()
    world.db.commit()
    return allocation


def _link_row_to(
    world, row, *, qty, document, allocation=None, po_line=None
) -> OrderInquiryLink:
    """Seed one link DIRECTLY on `row`, bypassing `_write_link` - the fixtures below
    need a link to a document the cascade could never place (a received one), and a
    plain open one seeded the same way for the mixed case (AC-RL-12)."""
    link = OrderInquiryLink(
        id=_uid(),
        company_id=row.company_id,
        row_id=row.id,
        spo_allocation_id=allocation.id if allocation is not None else None,
        po_line_id=po_line.id if po_line is not None else None,
        document=document,
        qty=Decimal(str(qty)),
    )
    world.db.add(link)
    world.db.flush()
    ProjectOrderInquiryService(world.db).refresh_link_state([row])
    world.db.commit()
    return link


def _rows_for_line(world, line) -> list:
    """Every LIVE row of this SO line, oldest first - a redirect leaves TWO on the
    line where today there is one, so `_order_row`'s own `.one()` cannot answer here."""
    return (
        world.db.query(OrderInquiryRow)
        .filter(
            OrderInquiryRow.so_line_id == line.id,
            OrderInquiryRow.state != INQUIRY_CANCELLED,
        )
        .order_by(OrderInquiryRow.created_at.asc(), OrderInquiryRow.id.asc())
        .all()
    )


def _redirected_fixture(
    api,
    *,
    row_qty="182",
    receive_qty="158",
    open_qty=None,
    buy_qty=REPLAN_QTY,
    required_date=REPLAN_DATE,
):
    """AC-RL-10 to AC-RL-14/18's own scenario, shrunk to the fixture world: a row of
    `row_qty`, `partly_linked`, one link to an SPO the client already received in full
    - optionally a second OPEN link too (AC-RL-12's mixed case) - replanned to
    `buy_qty` on `required_date` exactly as SO314593's confirmation did.
    """
    _client, world = api
    fixture = _raise_one_row(api, qty=row_qty)
    row = fixture["row"]
    allocation = _received_spo(world, qty=receive_qty)
    _link_row_to(world, row, qty=receive_qty, document=allocation.spo_number, allocation=allocation)
    open_line = None
    if open_qty is not None:
        po, open_line = _open_po_line(world, qty=open_qty)
        _link_row_to(world, row, qty=open_qty, document=po.po_number, po_line=open_line)
    world.db.refresh(row)
    assert row.state == INQUIRY_PARTLY_LINKED, (
        "the fixture must build a still-owed row for `_settle_row_in_place` to see"
    )
    fixture["received_allocation"] = allocation
    fixture["open_po_line"] = open_line
    _settle(world, fixture, qty=buy_qty, required_date=required_date)
    world.db.refresh(row)
    fixture["redirected_row"] = row
    fixture["new_row"] = next(
        r for r in _rows_for_line(world, fixture["line"]) if str(r.id) != str(row.id)
    )
    return fixture


def test_settle_redirects_row_when_every_link_is_received(api):
    """AC-RL-10: settle does NOT carry the row forward - it is redirected, its own
    figures and links left exactly as they were, and its note names the release."""
    _client, world = api
    fixture = _redirected_fixture(api)
    row = fixture["redirected_row"]

    assert row.redirected_to_pool is True
    assert Decimal(str(row.qty)) == Decimal("182")
    assert row.delivery_date == WAS
    links = _links_of(world, row)
    assert len(links) == 1
    assert links[0].spo_allocation_id == fixture["received_allocation"].id
    assert "released at revision" in (row.note or "")


def test_settle_raises_fresh_order_row_for_full_need(api):
    """AC-RL-11, Was/Now added by R3 (PLAN-oi-worklist-one-header.md, AC-OH-40): a
    fresh ORDER row carries the full replanned need, linkless, and now names what
    old supply it replaces rather than carrying no previous value."""
    _client, world = api
    fixture = _redirected_fixture(api)
    new_row = fixture["new_row"]

    assert new_row.verb == IV_ORDER
    assert Decimal(str(new_row.qty)) == Decimal("220")
    assert new_row.delivery_date == REPLAN_DATE
    assert new_row.state == INQUIRY_RAISED
    assert _links_of(world, new_row) == []
    assert Decimal(str(new_row.previous_qty)) == Decimal("182")
    assert new_row.previous_delivery_date == WAS


def test_settle_mixed_links_frees_open_link(api):
    """AC-RL-12: the received link stays on the redirected row; the still-open one is
    removed through `_remove_links`, so its capacity returns to the target."""
    _client, world = api
    fixture = _redirected_fixture(api, open_qty="20")
    row = fixture["redirected_row"]
    open_line = fixture["open_po_line"]

    links = _links_of(world, row)
    assert len(links) == 1
    assert links[0].spo_allocation_id == fixture["received_allocation"].id

    by_po, _by_spo = ProjectOrderInquiryService(world.db)._linked_by_target()
    assert str(open_line.id) not in by_po, "the freed PO line must show no claimed quantity"


def test_settle_keeps_row_with_only_open_links_in_place(api):
    """AC-RL-13: unchanged behaviour when nothing on the row is received - settle in
    place, links kept, the previous value carried, and no second row raised."""
    _client, world = api
    fixture = _raise_one_row(api, qty="182")
    row = fixture["row"]
    po, open_line = _open_po_line(world, qty="158")
    _link_row_to(world, row, qty="158", document=po.po_number, po_line=open_line)
    world.db.refresh(row)
    assert row.state == INQUIRY_PARTLY_LINKED

    _settle(world, fixture, qty=REPLAN_QTY, required_date=REPLAN_DATE)

    world.db.refresh(row)
    assert row.redirected_to_pool is False
    assert Decimal(str(row.qty)) == Decimal("220")
    assert row.delivery_date == REPLAN_DATE
    assert Decimal(str(row.previous_qty)) == Decimal("182")
    assert row.previous_delivery_date == WAS
    links = _links_of(world, row)
    assert len(links) == 1
    assert links[0].po_line_id == open_line.id
    assert [str(r.id) for r in _rows_for_line(world, fixture["line"])] == [str(row.id)]


def test_cascade_writes_nothing_onto_redirected_row_or_received_document(api):
    """AC-RL-14 (writer 1 of 2): the next bulk cascade pass must not touch the
    redirected row, and the received document's own zero capacity means the fresh row
    gets nothing from it either - there is nothing else to link it to here."""
    _client, world = api
    fixture = _redirected_fixture(api)
    row = fixture["redirected_row"]
    new_row = fixture["new_row"]

    ProjectOrderInquiryService(world.db).auto_place_for_products(
        [str(world.product.id)], actor_user_id=world.cs_user, trigger="test-ac-rl-14"
    )
    world.db.commit()

    world.db.refresh(row)
    world.db.refresh(new_row)
    assert len(_links_of(world, row)) == 1
    assert _links_of(world, new_row) == []
