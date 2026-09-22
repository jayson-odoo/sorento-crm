"""Edges the main handshake suite does not reach (`PLAN-scm-oi-handshake.md`, UAC
AC-H1..H15). `tests/test_order_inquiry_handshake.py` pins the shape of every rule; this
file is the seams between them: a REAL purchase-order confirm rather than the shortcut
`_open_po_line` gives an already-open line, a second press, a second company, a third
product left alone, and the facets/summary read together rather than one state at a time.

Reuses that file's harness wholesale (`world` / `api` fixtures: one CS user, one
purchasing user, one project, one product, one warehouse per test; `_raise_one_row`,
`_open_po_line`, `_as_purchasing`, `_settle`) rather than rebuilding it - the seeding
chain is the same one, and importing the fixtures is how pytest is meant to share them.

Runs on the REAL database (rolled back), for the same reason that file does:
`scm.committed_v` and the acknowledgement columns both live in the migrated schema, and
a blank scratch schema carries neither. Every row is seeded here behind the `ZZT` marker
- CI's database has no data.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.models.procurement import PurchaseOrder, PurchaseOrderLine
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
    SOSupplyDecision,
)
from app.services.project_order_inquiry_service import ProjectOrderInquiryService
from app.services.project_service import register_project
from app.services.scm.purchase_order_service import PurchaseOrderService

from .test_order_inquiry_handshake import (
    ACK_URL,
    LINK_NOW,
    LIST,
    MARKER,
    NOW,
    _as_purchasing,
    _links_of,
    _open_po_line,
    _product,
    _project_committed,
    _raise_one_row,
    _settle,
    _supplier,
    _uid,
    api,
    world,
)

__all__ = ["api", "world"]  # re-exported fixtures; keeps linters from calling them unused


# ---------------------------------------------------------------------------
# AC-H11: a REAL purchase-order confirm, not the `_open_po_line` shortcut
# ---------------------------------------------------------------------------


def _active_revision_no(world, order):
    """The revision number of the order's ACTIVE decision, or None when it has none.

    What a refusal MUST NOT move when it is refused: `reject_row` uncovers the line, and
    uncovering writes a revision, so a rejection that got as far as that on a row it
    should have turned away would leave the board re-deciding for no reason.
    """
    decision = (
        world.db.query(SOSupplyDecision)
        .filter(
            SOSupplyDecision.project_sales_order_id == order.id,
            SOSupplyDecision.state == "active",
        )
        .one_or_none()
    )
    return decision.revision_no if decision else None


def _draft_po_line(world, *, qty, product=None, warehouse=None):
    """A `draft_recommendation` PO with one line - what `bulk_confirm` actually confirms.

    `_open_po_line` in the sibling file builds an already-`active` line, which is right
    for Acknowledge and Link now (both cascade against lines already open) but says
    nothing about the THIRD trigger: confirming a plan-generated purchase order. That
    trigger runs `PurchaseOrderService.bulk_confirm`, and it only has anything to cascade
    once a `draft_recommendation` PO exists to be confirmed.
    """
    supplier = _supplier(world)
    po = PurchaseOrder(
        id=_uid(),
        company_id=world.company_id,
        po_number=f"ZZT-PO-{_uid()[:8]}",
        supplier_id=supplier.id,
        issue_date=date(2026, 6, 1),
        status="draft_recommendation",
        currency="MYR",
        source_system="scm_recommendation",
    )
    world.db.add(po)
    world.db.flush()
    line = PurchaseOrderLine(
        id=_uid(),
        company_id=world.company_id,
        purchase_order_id=po.id,
        product_id=(product or world.product).id,
        warehouse_id=(warehouse or world.warehouse).id,
        qty_ordered=Decimal(str(qty)),
        qty_received=Decimal("0"),
        expected_date=date(2026, 8, 10),
        line_status="open",
    )
    world.db.add(line)
    world.db.commit()
    return po, line


def test_po_confirm_cascade_links_an_unread_row_too(api):
    """Linking never waits for confirm (`PLAN-oi-confirm-per-so.md` S1's own measured
    fact: `include_awaiting=True` on every cascade door, unchanged by this lane): a
    plan-generated purchase order's confirm cascades onto BOTH rows firmly, whether or
    not either one was ever pressed through Acknowledge - the row nobody pressed is left
    `awaiting`, exactly as it was born, its link a DRAFT rather than proof anybody read it.
    """
    _client, world = api
    acknowledged = _raise_one_row(api, qty="5")
    never_pressed = _raise_one_row(api, qty="5")

    with _as_purchasing(world) as buyer:
        response = buyer.post(ACK_URL, json={"row_ids": [str(acknowledged["row"].id)]})
    assert response.status_code == 200, response.text
    world.db.commit()
    world.db.refresh(never_pressed["row"])
    assert never_pressed["row"].ack_state == ACK_AWAITING, "never pressed, still awaiting"

    po, _line = _draft_po_line(world, qty=20)

    out = PurchaseOrderService(world.db).bulk_confirm([po.id], actor=world.buyer)
    world.db.commit()

    assert out["confirmed_count"] == 1
    assert _links_of(world, acknowledged["row"]), "the confirm cascaded to the pressed row"
    assert _links_of(world, never_pressed["row"]), "and to the row nobody ever pressed"
    world.db.refresh(never_pressed["row"])
    assert never_pressed["row"].ack_state == ACK_AWAITING


# ---------------------------------------------------------------------------
# AC-H3: the batch and product-scoped shapes the single-row 403 does not cover
# ---------------------------------------------------------------------------


def test_a_cs_user_is_refused_a_batch_acknowledge_and_a_populated_link_now(api):
    """The main suite's 403 test sends one row and an empty `link-now` body. Neither
    shape proves CS is refused when there IS something for the grant to act on."""
    cs_client, world = api
    first = _raise_one_row(api, qty="4")
    second = _raise_one_row(api, qty="6")

    batch = cs_client.post(
        ACK_URL, json={"row_ids": [str(first["row"].id), str(second["row"].id)]}
    )
    assert batch.status_code == 403

    populated = cs_client.post(LINK_NOW, json={"product_ids": [str(world.product.id)]})
    assert populated.status_code == 403

    world.db.refresh(first["row"])
    world.db.refresh(second["row"])
    assert first["row"].ack_state == ACK_AWAITING
    assert second["row"].ack_state == ACK_AWAITING


# ---------------------------------------------------------------------------
# Acknowledging a row nobody is acting on any more
# ---------------------------------------------------------------------------


def test_acknowledging_a_cancelled_row_is_refused(api):
    """Plan section 7 (what shipped): 'The row checkbox refuses a CANCELLED or ACTIONED
    row as well as an acknowledged or rejected one ... found in the browser, where the
    first press took on three cancelled rows.' The SERVICE refuses it too - the checkbox
    can be bypassed by a second tab, a replayed request or a future caller, and none of
    those may take on work nobody is doing.
    """
    _client, world = api
    fixture = _raise_one_row(api)
    row = fixture["row"]
    born_by = row.acknowledged_by
    row.state = INQUIRY_CANCELLED
    world.db.commit()

    with _as_purchasing(world) as buyer:
        response = buyer.post(ACK_URL, json={"row_ids": [str(row.id)]})

    assert response.status_code == 422, response.text
    world.db.refresh(row)
    assert row.ack_state == ACK_AWAITING, "the born stamp, untouched"
    assert row.acknowledged_by == born_by, "the buyer's press was refused, not stamped"


def test_one_cancelled_row_refuses_the_whole_batch_and_stamps_none_of_it(api):
    """A batch is one press and one decision: half of it landing would leave the buyer
    reading a toast for two rows and finding one."""
    _client, world = api
    live = _raise_one_row(api, qty="4")
    dead = _raise_one_row(api, qty="6")
    dead["row"].state = INQUIRY_CANCELLED
    world.db.commit()

    with _as_purchasing(world) as buyer:
        response = buyer.post(
            ACK_URL, json={"row_ids": [str(live["row"].id), str(dead["row"].id)]}
        )

    assert response.status_code == 422, response.text
    world.db.refresh(live["row"])
    assert live["row"].ack_state == ACK_AWAITING


def test_rejecting_a_row_that_is_no_longer_open_is_refused_and_writes_nothing(api):
    """A cancelled row is past refusing: nobody is buying it, and a rejection would
    uncover its line - writing a revision for a refusal of work that had already stopped.
    """
    _client, world = api
    fixture = _raise_one_row(api)
    row = fixture["row"]
    row.state = INQUIRY_CANCELLED
    world.db.commit()
    before = _active_revision_no(world, fixture["order"])

    with _as_purchasing(world) as buyer:
        response = buyer.post(
            f"{LIST}/{row.id}/reject", json={"reason": "Factory closed until November"}
        )

    assert response.status_code == 422, response.text
    world.db.refresh(row)
    assert row.ack_state == ACK_AWAITING
    assert row.rejected_reason is None
    assert _active_revision_no(world, fixture["order"]) == before, (
        "and the line's decision was left exactly as it stood"
    )


def test_rejecting_a_fully_linked_row_takes_its_documents_back(api):
    """REVERSED by `PLAN-scm-oi-draft-links.md` 5.6.

    A fully linked row could not be refused while a link meant purchasing had already
    bought. With DRAFTS the same state means the opposite - a row raised a minute ago is
    fully linked and nobody has agreed to anything - so the rule refused most of the page.
    The links come down first instead, which is what a refusal IS: the quantity goes back
    to the document for whoever needs it next.
    """
    _client, world = api
    _po, line = _open_po_line(world, qty=50)
    fixture = _raise_one_row(api)
    row = fixture["row"]

    with _as_purchasing(world) as buyer:
        assert buyer.post(ACK_URL, json={"row_ids": [str(row.id)]}).status_code == 200
        world.db.commit()
        world.db.refresh(row)
        assert row.state == INQUIRY_PLACED, "the cascade covered it whole"
        response = buyer.post(f"{LIST}/{row.id}/reject", json={"reason": "Too late"})

    assert response.status_code == 200, response.text
    world.db.commit()
    world.db.refresh(row)
    assert row.ack_state == ACK_REJECTED
    assert _links_of(world, row) == []
    by_po, _by_spo = ProjectOrderInquiryService(world.db)._linked_by_target()
    assert by_po.get(str(line.id), Decimal("0")) == Decimal("0")


def test_rejecting_a_partly_linked_row_takes_its_half_back_too(api):
    """The same rule from the other side, and the same reversal: a refusal leaves the row
    holding nothing, whether it was covered wholly or in part.

    SLICE D, 8 Sep 2026: the AUTOMATIC pass no longer leaves a row PARTLY LINKED - 4 of 10
    cascadable is short of the whole 10, so acknowledging links nothing and the row stays
    `raised` (AC-D1). `partly_linked` is still a real, reachable state (AC-D4/AC-H7); it
    now comes from a PERSON naming a partial by hand in the Link dialog, which is what this
    test writes directly to keep testing what it always meant to - a refusal giving back
    whatever a row was holding, however it got there.
    """
    _client, world = api
    _po, po_line = _open_po_line(world, qty=4)
    fixture = _raise_one_row(api, qty="10")
    row = fixture["row"]

    with _as_purchasing(world) as buyer:
        assert buyer.post(ACK_URL, json={"row_ids": [str(row.id)]}).status_code == 200
        world.db.commit()
        # AC-D1: 4 of the 10 needed is short of the whole row, so the automatic cascade
        # links nothing and the row stays raised.
        world.db.refresh(row)
        assert row.state == INQUIRY_RAISED

        # AC-D4: a buyer may still take a partial by hand.
        ProjectOrderInquiryService(world.db).place_on_po_allocations(
            str(row.id), [{"po_line_id": po_line.id, "qty": "4"}],
            actor_user_id=world.buyer,
        )
        world.db.commit()
        world.db.refresh(row)
        assert row.state == INQUIRY_PARTLY_LINKED

        response = buyer.post(
            f"{LIST}/{row.id}/reject", json={"reason": "No supplier for the rest"}
        )

    assert response.status_code == 200, response.text
    world.db.commit()
    world.db.refresh(row)
    assert row.ack_state == ACK_REJECTED
    assert _links_of(world, row) == [], "a refused row keeps no claim on anybody's order"


# ---------------------------------------------------------------------------
# A second press changes nothing further
# ---------------------------------------------------------------------------


def test_acknowledging_an_already_acknowledged_row_twice_never_moves_the_stamp(api):
    """The guard is TOLERANT once a row is genuinely acknowledged, not refusing: a
    duplicate id inside ONE batch, and a wholly separate second press, are BOTH no-ops on
    the stamp. 'Idempotent' here means neither press moves who took the row on or when,
    and neither doubles the cascade. A row is born `awaiting`
    (`PLAN-oi-confirm-per-so.md` S1), so the FIRST press below is the genuine transition
    this test's own duplicate-id/second-press cases are pinned against.
    """
    _client, world = api
    _open_po_line(world, qty=50)
    fixture = _raise_one_row(api)
    row = fixture["row"]
    assert row.ack_state == ACK_AWAITING

    with _as_purchasing(world) as buyer:
        genuine = buyer.post(ACK_URL, json={"row_ids": [str(row.id)]})
    assert genuine.status_code == 200, genuine.text
    assert genuine.json()["acknowledged"] == 1
    world.db.commit()
    world.db.refresh(row)
    born_by, born_at = row.acknowledged_by, row.acknowledged_at
    assert born_by and born_at

    with _as_purchasing(world) as buyer:
        first = buyer.post(ACK_URL, json={"row_ids": [str(row.id), str(row.id)]})
    assert first.status_code == 200, first.text
    # 0, not 1 (nit, review of PR #471): the row was ALREADY acknowledged, so nothing
    # TRANSITIONED - a repeated id inside the batch changes that not at all.
    assert first.json()["acknowledged"] == 0, "already acknowledged, so nothing transitioned"
    world.db.commit()

    world.db.refresh(row)
    assert row.acknowledged_by == born_by
    assert row.acknowledged_at == born_at, "the buyer's press did not move the stamp"
    linked_before = sum(Decimal(str(link.qty)) for link in _links_of(world, row))
    assert linked_before > 0, "the FIRST acknowledge already cascaded, against the open line"

    with _as_purchasing(world) as buyer:
        second = buyer.post(ACK_URL, json={"row_ids": [str(row.id)]})
    assert second.status_code == 200, second.text

    world.db.refresh(row)
    assert row.acknowledged_by == born_by
    assert row.acknowledged_at == born_at, "a tolerant second press must not move the stamp"
    linked_after = sum(Decimal(str(link.qty)) for link in _links_of(world, row))
    assert linked_after == linked_before, "no double-linking from a repeated cascade"


# ---------------------------------------------------------------------------
# A reject does not refuse itself a second reason
# ---------------------------------------------------------------------------


def test_rejecting_an_already_rejected_row_is_refused(api):
    _client, world = api
    fixture = _raise_one_row(api)
    row = fixture["row"]

    with _as_purchasing(world) as buyer:
        first = buyer.post(f"{LIST}/{row.id}/reject", json={"reason": "No stock"})
        assert first.status_code == 200, first.text
        world.db.commit()
        second = buyer.post(f"{LIST}/{row.id}/reject", json={"reason": "Still no stock"})

    assert second.status_code == 422, second.text
    world.db.refresh(row)
    assert row.rejected_reason == "No stock", "the refused second reject left the first reason"


def test_rejecting_the_only_row_on_a_single_covered_line_order_retires_the_revision_and_leaves_the_row_as_it_was(api):
    """Owner case, 22 Sep 2026 (`PLAN-board-reject-on-confirmed-line.md`, fix round):
    purchasing's OWN refusal reaches the SAME whole-revision `uncover_lines` seam a board
    Reject does, on an order where this row's line is the ONLY one covered - `_raise_one_row`
    builds exactly that shape. Two things the fix must not get wrong at once:

    * the order's active decision is genuinely retired (this line is undecided again, the
      whole point of a refusal); and
    * this row itself, whose `ack_state` the reject already stamped `rejected`, is left
      EXACTLY as it was otherwise - `_retire_uncovered_rows`' new `only_line_ids` mode skips
      a row `ack_state == ACK_REJECTED` on purpose, because cancelling it here dropped it out
      of the ack summary's `rejected` facet (`_acks` hides `state == cancelled` rows), caught
      by `test_the_summary_ack_facet_carries_all_four_keys_by_name`.
    """
    _client, world = api
    fixture = _raise_one_row(api)
    row = fixture["row"]
    before_state = row.state
    before_revision = _active_revision_no(world, fixture["order"])
    assert before_revision is not None, "sanity: the line starts covered"

    with _as_purchasing(world) as buyer:
        response = buyer.post(f"{LIST}/{row.id}/reject", json={"reason": "No stock"})

    assert response.status_code == 200, response.text
    world.db.commit()
    world.db.refresh(row)
    assert row.ack_state == ACK_REJECTED
    assert row.state == before_state, "the row purchasing just rejected is left exactly as it was"
    assert _active_revision_no(world, fixture["order"]) is None, (
        "the line's only decision retires - it is undecided again"
    )


# ---------------------------------------------------------------------------
# Company scope: refused, not silently skipped
# ---------------------------------------------------------------------------


def test_row_ids_naming_another_companys_row_are_refused_not_skipped(api):
    """`CompanyScopedMixin`'s `do_orm_execute` filter (`app/services/company_scope.py`)
    makes a foreign-company row invisible to the query `_rows_or_404` runs under the
    current scope, so it comes back as MISSING, and the whole batch is refused with a
    404 - never a partial success that quietly acknowledges the row it could see and
    drops the one it could not."""
    _client, world = api
    mine = _raise_one_row(api)
    row = mine["row"]

    other_company_id = _uid()
    world.db.execute(
        text("INSERT INTO companies (id, name, code) VALUES (:i, :n, :c)"),
        {
            "i": other_company_id,
            "n": f"{MARKER} Other Co",
            "c": f"ZZT{uuid.uuid4().hex[:6]}",
        },
    )
    foreign_row_id = _uid()
    world.db.execute(
        text(
            "INSERT INTO projects.order_inquiry_rows (id, company_id, order_inquiry_id, "
            "so_line_id, qty, verb, ack_state, created_at) VALUES "
            "(:i, :c, :inq, :l, :q, :v, 'awaiting', now())"
        ),
        {
            "i": foreign_row_id,
            "c": other_company_id,
            "inq": str(row.order_inquiry_id),
            "l": str(row.so_line_id),
            "q": Decimal("5"),
            "v": IV_ORDER,
        },
    )
    world.db.commit()

    with _as_purchasing(world) as buyer:
        response = buyer.post(ACK_URL, json={"row_ids": [str(row.id), foreign_row_id]})

    assert response.status_code == 404, response.text
    world.db.refresh(row)
    assert row.ack_state == ACK_AWAITING, "the whole batch was refused, not partly applied"


# ---------------------------------------------------------------------------
# Link now: scoped to the products it is given, and to no others
# ---------------------------------------------------------------------------


def test_link_now_named_products_leave_every_other_products_rows_untouched(api):
    """Three products, each with an acknowledged unlinked row and its own open line;
    naming only one must not touch either of the other two - not their links, and not
    their acknowledgement."""
    _client, world = api
    other_a = _product(world.db)
    other_b = _product(world.db)
    world.db.commit()

    named = _raise_one_row(api, qty="10")
    left_a = _raise_one_row(api, qty="10", product=other_a)
    left_b = _raise_one_row(api, qty="10", product=other_b)

    with _as_purchasing(world) as buyer:
        assert (
            buyer.post(
                ACK_URL,
                json={
                    "row_ids": [
                        str(named["row"].id),
                        str(left_a["row"].id),
                        str(left_b["row"].id),
                    ]
                },
            ).status_code
            == 200
        )
        world.db.commit()
        # Nothing was open yet, so acknowledging linked nothing; unplace is a no-op
        # safety net if it somehow did, keeping the fixture identical either way.
        for fixture in (named, left_a, left_b):
            if _links_of(world, fixture["row"]):
                ProjectOrderInquiryService(world.db).unplace(
                    str(fixture["row"].id), actor_user_id=world.buyer
                )
        world.db.commit()

        _open_po_line(world, qty=100)
        _open_po_line(world, qty=100, product=other_a)
        _open_po_line(world, qty=100, product=other_b)

        response = buyer.post(LINK_NOW, json={"product_ids": [str(world.product.id)]})
    assert response.status_code == 200, response.text
    assert response.json()["placed_rows"] == 1
    world.db.commit()

    assert _links_of(world, named["row"]), "the named product's row was linked"
    assert _links_of(world, left_a["row"]) == [], "an un-named product was not touched"
    assert _links_of(world, left_b["row"]) == [], "neither was the other one"
    world.db.refresh(left_a["row"])
    world.db.refresh(left_b["row"])
    assert left_a["row"].ack_state == ACK_ACKNOWLEDGED, "untouched means untouched, not un-acknowledged"
    assert left_b["row"].ack_state == ACK_ACKNOWLEDGED


# ---------------------------------------------------------------------------
# The ack facet drops its own filter, but honours the others
# ---------------------------------------------------------------------------


def test_the_ack_facet_drops_its_own_filter_but_honours_a_project_filter(api):
    """AC-H4/AC-H14. `_acks` recomputes with `ack` dropped, the way every other axis on
    this screen drops its own - but a DIFFERENT control (here, `project_id`) still
    narrows it, exactly as it narrows the list itself."""
    client, world = api
    other_project = register_project(
        world.db,
        company_id=world.company_id,
        actor_user_id=world.cs_user,
        developer_party_id=None,
        title=f"{MARKER} Other Pursuit {_uid()[:12]}",
    )
    world.db.commit()

    here = _raise_one_row(api)
    elsewhere = _raise_one_row(api)
    # Move the second fixture's order onto the other project. `_raise_one_row` always
    # raises against `world.project`; this is the cheapest way to get a row that reads
    # as belonging to a DIFFERENT one without rebuilding the whole seeding chain.
    elsewhere["order"].project_id = other_project.id
    world.db.commit()

    with _as_purchasing(world) as buyer:
        assert (
            buyer.post(ACK_URL, json={"row_ids": [str(here["row"].id)]}).status_code
            == 200
        )
        assert (
            buyer.post(
                f"{LIST}/{elsewhere['row'].id}/reject", json={"reason": "wrong pursuit"}
            ).status_code
            == 200
        )
    world.db.commit()

    summary = client.get(
        f"{LIST}/summary",
        params={"ack": "acknowledged", "project_id": str(world.project.id)},
    ).json()
    assert summary["ack"]["acknowledged"] >= 1, "own project's acknowledged row is counted"
    assert summary["ack"]["rejected"] == 0, (
        "the rejected row belongs to the OTHER project, which the project_id filter "
        "still excludes even though the ack filter itself was dropped for the facet"
    )


# ---------------------------------------------------------------------------
# Every ack facet key survives the wire, all four at once
# ---------------------------------------------------------------------------


def test_the_summary_ack_facet_carries_all_four_keys_by_name(api):
    """AC-H14, the summary's own half. `OrderInquiryAckCounts` is declared field by
    field (`app/schemas/project_order_inquiry.py`) so a typo in the schema or in the
    service key it reads would show up here as a missing key, not a silently-dropped
    zero - and this is the one place all four states are proven to coexist and to be
    counted correctly at once, rather than one state at a time.

    All four states are reachable through the API again (`PLAN-oi-confirm-per-so.md` S1):
    a row is born `awaiting`, an explicit Confirm press reads `acknowledged`, and
    `changed` is left literally on the row by a settle after that - the facet reads the
    grouped `ack_state` for all four now, `changed` included, never `changed_at IS NOT
    NULL` (which would over-count a `changed` row later re-acknowledged, since its
    `changed_at` stays as history).
    """
    client, world = api
    acknowledged = _raise_one_row(api, qty="1")
    awaiting = _raise_one_row(api, qty="1")
    to_change = _raise_one_row(api, qty="1")
    to_reject = _raise_one_row(api, qty="1")

    with _as_purchasing(world) as buyer:
        assert (
            buyer.post(
                ACK_URL, json={"row_ids": [str(acknowledged["row"].id)]}
            ).status_code
            == 200
        )
    world.db.commit()

    to_change["row"].ack_state = ACK_CHANGED
    to_change["row"].changed_at = datetime.utcnow()
    world.db.commit()

    with _as_purchasing(world) as buyer:
        assert (
            buyer.post(
                f"{LIST}/{to_reject['row'].id}/reject", json={"reason": "no capacity"}
            ).status_code
            == 200
        )
    world.db.commit()

    summary = client.get(
        f"{LIST}/summary", params={"project_id": str(world.project.id)}
    ).json()
    for key in ("awaiting", "acknowledged", "changed", "rejected"):
        assert key in summary["ack"], f"OrderInquiryAckCounts dropped `{key}`"
    assert summary["ack"]["awaiting"] >= 1
    assert summary["ack"]["acknowledged"] >= 1
    assert summary["ack"]["changed"] >= 1
    assert summary["ack"]["rejected"] >= 1

    world.db.refresh(awaiting["row"])
    assert awaiting["row"].ack_state == ACK_AWAITING


# ---------------------------------------------------------------------------
# AC-H10: committed_v and the plan, told apart by one cell carrying all three states
# ---------------------------------------------------------------------------


def test_committed_v_and_the_plan_agree_only_on_acknowledged_and_changed(api):
    """Three rows at the SAME cell - awaiting, changed and rejected - so the view's own
    rule (drop rejected, keep awaiting) and the plan's narrower one (acknowledged and
    changed only) can be told apart in one assertion.

    `awaiting` and `changed` are reachable through the API again
    (`PLAN-oi-confirm-per-so.md` S1: a row is born `awaiting`, and a settle after
    acknowledgement leaves it `changed` rather than auto-reacknowledging) - forced
    directly here only because a single confirm cannot naturally produce all three states
    on three DIFFERENT rows in one press. The plan page's own awaiting chip is back too
    (S1); `awaiting_acknowledgement_rows` is the read both `committed_v` and the plan
    disagree with, asserted here beside them.
    """
    from app.services.scm.reorder_run_service import awaiting_acknowledgement_rows

    _client, world = api
    before_awaiting = awaiting_acknowledgement_rows(world.db)

    awaiting = _raise_one_row(api, qty="7")
    to_change = _raise_one_row(api, qty="9")
    to_reject = _raise_one_row(api, qty="11")

    awaiting["row"].ack_state = ACK_AWAITING
    awaiting["row"].acknowledged_by = None
    awaiting["row"].acknowledged_at = None
    to_change["row"].ack_state = ACK_CHANGED
    world.db.commit()

    with _as_purchasing(world) as buyer:
        assert (
            buyer.post(
                f"{LIST}/{to_reject['row'].id}/reject", json={"reason": "no supply"}
            ).status_code
            == 200
        )
    world.db.commit()

    # committed_v: everything still owed except the rejected row (awaiting + changed).
    assert _project_committed(world, planned=False) == Decimal("7") + Decimal("9")
    # the plan's own SELECT: acknowledged + changed only - the awaiting row is nothing
    # to buy against yet.
    assert _project_committed(world, planned=True) == Decimal("9")
    # The count both readings disagree with - the row nobody has read AND the row CS
    # amended since (`changed`), the two states `ACK_ACKNOWLEDGEABLE` used to gate.
    assert awaiting_acknowledgement_rows(world.db) == before_awaiting + 2

    world.db.refresh(awaiting["row"])
    assert awaiting["row"].ack_state == ACK_AWAITING
