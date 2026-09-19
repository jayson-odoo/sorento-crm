"""A re-upload rebuilds the rows planning worked on; a rollback keeps them.

Contract: `documentation/plans/scm/oi-rollback-recover-planning-rows-acceptance-criteria.md`,
AC-RB-1 to AC-RB-21 (round 1, RB-22/23 are the captain's own rehearsal/regression runs, not a
test file) and AC-RB-24 to AC-RB-30 (round 2, slice S5, "Shapes found on the full 18 Sep copy",
rulings R7/R8). Plan: `documentation/plans/scm/PLAN-oi-rollback-recover-planning-rows.md`,
section 3.1 for the seams and section 3.2 for round 1's test list; round 2's test list travels
in the captain's own message rather than a plan-file update.

TEST-FIRST, written before the importer, `follow_book_for_rows` or the rollback script carry
any of 2.1/2.2/2.3 (round 1) or R7/R8 (round 2, S5). The red state is therefore a missing
outcome code, a `redirected_to_pool` row that never gets raised (the importer still answers
`already_raised` and skips), a link that stays on the wrong row, or a rollback script with no
`kept` count - never an import error or a fixture typo. A handful of criteria (named in each
test's own docstring) may legitimately already be green: today's plain re-raise, the existing
`already_raised` skip and the existing demand-exclusion read do not need 2.1/2.2/2.3 or R7/R8
to hold. Round 2's own tests are asserted straight off the UAC wording, not off round 2's
implementation (there is none yet when this file is written).

Harness: `World` / `world()` from `test_project_order_inquiry_import_migration.py`, `_apply` /
`_rollback` / `_rows_of` from `test_oi_sheet_pairing_repair.py` - imported, never copied, so
this file cannot drift about what a seeded world or a rollback run is. CI's database is empty:
every test seeds its own order, lines, PO/SPO/claim chain, `Replaces N used` sibling, notice row
and supply decision. Postgres only, via `blank_session` (never sqlite).

A `Replaces N used` row, a DELAY notice row and an active decision are seeded DIRECTLY, matching
prod's own state today - only AC-RB-21 drives the real `ProjectSupplyService.confirm`, per the
plan's own instruction.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

import pytest
import sqlalchemy as sa

from app.models.base import company_scope
from app.models.project_so import (
    ACK_CHANGED,
    DECISION_ACTIVE,
    DECISION_SUPERSEDED,
    INQUIRY_CANCELLED,
    IV_DELAY,
    IV_RESERVE_AND_ORDER,
    OrderInquiryLink,
    OrderInquiryRow,
    ProjectSalesOrder,
    SOSupplyDecision,
)
from app.models.scm import OrderLinkClaim
from app.schemas.project_supply import ConfirmLine, ConfirmSupplyBody
from app.services import import_outcome_codes as oc
from app.services import project_order_inquiry_import_service as importer
from app.services.project_order_inquiry_service import ProjectOrderInquiryService
from app.services.project_so_adoption_service import ProjectSOAdoptionService
from app.services.project_supply_service import ProjectSupplyService

from ._pg_fixture import blank_session
from .test_oi_sheet_pairing_repair import _apply, _rollback, _rows_of
from .test_project_order_inquiry_import_migration import (
    D_OCT,
    MARKER,
    World,
    _n,
    _uid,
    sheet,
    world,
)


# --------------------------------------------------------------------------- #
# local fixture vocabulary                                                     #
# --------------------------------------------------------------------------- #


def _ref() -> str:
    """The shape AutoCount writes into `sales_order_lines.source_ref`, in the same family
    `test_oi_sheet_pairing_repair._ref` mints (never a test-looking special case)."""
    return f"AED_SORENTO:{41576559 + _n()}:{41604391 + _n()}"


def _adopted_mirror(w: World, order, line):
    """The mirror line for `line`, adopted directly (no upload) - the shape a `Replaces N
    used` row or a decision needs to exist BEFORE a sheet ever names the line."""
    ProjectSOAdoptionService(w.db).adopt(str(order.id), w.actor)
    return w.mirror_of(line)


def _used_sibling(
    w: World,
    mirror,
    *,
    qty: str,
    delivery_date: date,
    previous_qty: str,
    previous_delivery_date: date,
    note: str | None = None,
) -> OrderInquiryRow:
    """A live `Replaces N used` row exactly as `project_order_inquiry_service.py` (~1104 to
    1185) writes one when a replan redirects a received line: born from the release, carrying
    the released row's own qty/date as `previous_qty` / `previous_delivery_date`, and a note
    starting "Replaces N used". Seeded directly - CI's DB is empty and the plan says only
    AC-RB-21 drives the real confirm."""
    row = w.board_row(mirror, qty=qty)
    row.delivery_date = delivery_date
    row.previous_qty = Decimal(previous_qty)
    row.previous_delivery_date = previous_delivery_date
    row.note = note or f"Replaces {previous_qty} used"
    w.db.flush()
    return row


def _decision(
    w: World,
    mirror,
    core_line,
    *,
    buy_qty: str,
    required_date: date | None,
    revision_no: int = 1,
    state: str = DECISION_ACTIVE,
    confirmed_at: datetime | None = None,
) -> SOSupplyDecision:
    """One `so_supply_decisions` row with a single `line_snapshots` entry for `mirror`, in
    `ProjectSupplyService._snapshot`'s own real shape (`project_line_id` = the row's own
    `so_line_id`, `core_line_id`, `buy_qty`, `required_date` - `PLAN` section 3.1)."""
    snapshot = {
        "line_no": 1,
        "project_line_id": str(mirror.id),
        "core_line_id": str(core_line.id),
        "item_code": core_line.product_id and w.product.product_code,
        "location": w.warehouse.warehouse_code,
        "required_date": required_date.isoformat() if required_date else None,
        "open_qty": "0",
        "timely_spo_qty": "0",
        "timely_spo_refs": [],
        "reserve_qty": "0",
        "borrow_qty": "0",
        "buy_qty": str(buy_qty),
        "components": [],
        "proposed_components": [],
    }
    decision = SOSupplyDecision(
        id=_uid(),
        company_id=w.company_id,
        project_sales_order_id=str(mirror.project_sales_order_id),
        revision_no=revision_no,
        state=state,
        line_snapshots=[snapshot],
        confirmed_at=confirmed_at,
    )
    w.db.add(decision)
    w.db.flush()
    return decision


def _row_snapshot(row: OrderInquiryRow) -> dict:
    """Every column two "same row, before and after" assertions in this file compare."""
    return {
        "qty": str(Decimal(str(row.qty))),
        "delivery_date": row.delivery_date,
        "redirected_to_pool": row.redirected_to_pool,
        "previous_qty": (
            str(Decimal(str(row.previous_qty))) if row.previous_qty is not None else None
        ),
        "previous_delivery_date": row.previous_delivery_date,
        "note": row.note,
        "state": row.state,
        "ack_state": row.ack_state,
        "changed_at": row.changed_at,
        "supply_decision_id": row.supply_decision_id,
    }


class _Capture:
    """A stand-in `ImportOutcome`, entirely in memory - no DB write, so a new outcome code
    can be pinned without ever persisting a real `import_job_rows` row into the shared
    database. Duck-types every method `apply()` calls on its `outcome` argument."""

    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    def success(self, **kwargs):
        self.calls.append(("success", kwargs))

    def updated(self, **kwargs):
        kwargs.setdefault("code", oc.UPDATED)
        self.calls.append(("updated", kwargs))

    def unchanged(self, **kwargs):
        kwargs.setdefault("code", oc.UNCHANGED)
        self.calls.append(("unchanged", kwargs))

    def skip(self, **kwargs):
        self.calls.append(("skip", kwargs))

    def fail(self, **kwargs):
        self.calls.append(("fail", kwargs))

    def codes(self) -> list[str]:
        return [kwargs.get("code") for _kind, kwargs in self.calls]

    def by_code(self, code: str) -> list[dict]:
        return [kwargs for _kind, kwargs in self.calls if kwargs.get("code") == code]


def _pre_recovery_line(
    w: World, *, used_qty: str = "182", fresh_qty: str = "220", link_qty: str, received: bool,
    allocation_qty: str | None = None,
):
    """The prod shape section 0 measured: a line covered by an ACTIVE decision, one live
    `Replaces N used` fresh row with no used sibling, and a link ALREADY sitting on the FRESH
    row (what `follow_book` wrote after the old rollback deleted the used row) - AutoCount's
    own document, reached through the ref (R1), never through the sheet's remark.

    `allocation_qty` defaults to `link_qty` (the whole document already claimed, no spare
    capacity for anything else to reach) - AC-RB-31's own fixture sets it LARGER than
    `link_qty`, so the document still has capacity the upload's ordinary book pairing could
    independently reach for the used row, alongside the move."""
    order = w.order()
    line = w.line(order, qty_ordered="500", required_date=date(2027, 3, 1))
    ref = _ref()
    line.source_ref = ref
    w.db.flush()
    mirror = _adopted_mirror(w, order, line)
    old_date = date(2026, 6, 1)
    fresh = _used_sibling(
        w,
        mirror,
        qty=fresh_qty,
        delivery_date=date(2027, 3, 1),
        previous_qty=used_qty,
        previous_delivery_date=old_date,
        note=f"Replaces {used_qty} used; SPO-2026/08-0104 received in full",
    )
    alloc_qty = allocation_qty if allocation_qty is not None else link_qty
    allocation = w.spo_allocation(
        quantity=int(Decimal(alloc_qty)),
        received=int(Decimal(alloc_qty)) if received else 0,
        from_so_line_ref=ref,
    )
    claim = w.claim(
        order=order, core_line=line, document=allocation.spo_number, allocation=allocation
    )
    link = OrderInquiryLink(
        id=_uid(),
        company_id=w.company_id,
        row_id=fresh.id,
        spo_allocation_id=allocation.id,
        document=allocation.spo_number,
        qty=Decimal(link_qty),
        linked_by=w.actor,
        linked_at=datetime(2026, 6, 3, 9, 0, 0),
        auto=True,
        claim_id=claim.id,
    )
    w.db.add(link)
    w.db.flush()
    return order, line, mirror, fresh, allocation, claim, link


def _stamped_row(w: World, *, file_name: str, trait: str | None):
    """One row a sheet upload raised, then given ONE of the three planning traits a guard
    must keep (`redirected_to_pool`, `changed_at`, `supply_decision_id`), or none - the plain
    control a rollback must still delete."""
    order = w.order()
    line = w.line(order, qty_ordered="50")
    ref = _ref()
    line.source_ref = ref
    po, po_line = w.po_line(qty_ordered="50")
    po_line.from_so_line_ref = ref
    w.db.flush()
    result = _apply(
        w,
        sheet([
            (order.so_number, w.product.product_code, 30, D_OCT, w.warehouse.warehouse_code, ""),
        ]),
        file_name=file_name,
    )
    assert result["rows_raised"] == 1, result
    # `_rows_of` carries no ORDER BY, and this helper is called more than once with the
    # SAME `file_name` in one world (`test_rollback_keeps_planning_rows`) - `[0]` is not
    # this call's own row, it is whichever row postgres happens to return first. Picked by
    # THIS call's own line instead, which is unambiguous.
    mirror = w.mirror_of(line)
    matches = [r for r in _rows_of(w, file_name) if str(r.so_line_id) == str(mirror.id)]
    assert len(matches) == 1, matches
    row = matches[0]
    if trait == "redirected_to_pool":
        row.redirected_to_pool = True
    elif trait == "changed_at":
        row.changed_at = datetime(2026, 9, 19, 9, 0, 0)
    elif trait == "supply_decision_id":
        decision = _decision(w, mirror, line, buy_qty="30", required_date=D_OCT)
        row.supply_decision_id = decision.id
    elif trait is not None:
        raise AssertionError(f"unknown trait {trait!r}")
    w.db.flush()
    return order, line, row


# --------------------------------------------------------------------------- #
# AC-RB-1 to AC-RB-5: used rows                                                #
# --------------------------------------------------------------------------- #


def test_sheet_row_beside_replaces_row_is_raised_used():
    """AC-RB-1. The sheet row 182 @ 2026-06-01 exactly matches the fresh row's OWN
    `previous_qty` / `previous_delivery_date`, so it is raised as the USED row (2.1(a)) rather
    than skipped as already-raised."""
    with world() as w:
        order = w.order()
        line = w.line(order, qty_ordered="220", required_date=date(2027, 3, 1))
        mirror = _adopted_mirror(w, order, line)
        old_date = date(2026, 6, 1)
        fresh = _used_sibling(
            w, mirror, qty="220", delivery_date=date(2027, 3, 1),
            previous_qty="182", previous_delivery_date=old_date,
            note="Replaces 182 used; SPO-2026/08-0104 received in full",
        )
        capture = _Capture()
        data = sheet([
            (order.so_number, w.product.product_code, 182, old_date,
             w.warehouse.warehouse_code, ""),
        ])

        _apply(w, data, outcome=capture, file_name="journey.xlsx")

        assert oc.ALREADY_RAISED not in capture.codes(), capture.calls
        rows = w.rows()
        assert len(rows) == 2, [(str(r.id), str(r.qty), r.delivery_date) for r in rows]
        used = next(r for r in rows if str(r.id) != str(fresh.id))
        assert used.redirected_to_pool is True
        assert Decimal(str(used.qty)) == Decimal("182")
        assert used.delivery_date == old_date
        assert (used.note or "").startswith(f"{importer._MIGRATION_STAMP} journey.xlsx")


@pytest.mark.parametrize("order_in_file", [("a", "b"), ("b", "a")])
def test_two_same_qty_deliveries_pair_by_date(order_in_file):
    """AC-RB-2. The CB2807-DIY shape: two `Replaces 182 used` fresh rows on ONE mirror,
    told apart only by date. Each sheet row becomes the used row of the fresh row whose
    `previous_delivery_date` it equals, whichever order the file states them in."""
    with world() as w:
        order = w.order()
        line = w.line(order, qty_ordered="600", required_date=date(2027, 6, 1))
        mirror = _adopted_mirror(w, order, line)
        date_a = date(2026, 6, 1)
        date_b = date(2026, 9, 1)
        _used_sibling(
            w, mirror, qty="220", delivery_date=date(2027, 3, 1),
            previous_qty="182", previous_delivery_date=date_a,
            note="Replaces 182 used; SPO-A received",
        )
        _used_sibling(
            w, mirror, qty="280", delivery_date=date(2027, 4, 1),
            previous_qty="182", previous_delivery_date=date_b,
            note="Replaces 182 used; SPO-B received",
        )
        by_label = {"a": date_a, "b": date_b}
        rows_in_order = [
            (order.so_number, w.product.product_code, 182, by_label[label],
             w.warehouse.warehouse_code, "")
            for label in order_in_file
        ]
        data = sheet(rows_in_order)

        _apply(w, data, file_name="journey.xlsx")

        rows = w.rows()
        assert len(rows) == 4, [(str(r.qty), r.delivery_date, r.redirected_to_pool) for r in rows]
        used_rows = [r for r in rows if r.redirected_to_pool]
        assert len(used_rows) == 2, [(str(r.qty), r.delivery_date) for r in used_rows]
        by_date = {r.delivery_date: r for r in used_rows}
        assert date_a in by_date and date_b in by_date, by_date
        assert Decimal(str(by_date[date_a].qty)) == Decimal("182")
        assert Decimal(str(by_date[date_b].qty)) == Decimal("182")


@pytest.mark.parametrize("mismatch", ["qty_off", "date_off"])
def test_no_exact_match_raises_nothing_and_is_reported(mismatch):
    """AC-RB-3 (R6). Neither the quantity nor the date is a GUESS: a sheet row matching
    neither exactly raises no used row and no other row, and is reported with its own
    outcome code naming item, quantity, date and sales order.

    `oc.NO_USED_DELIVERY_MATCH` does not exist yet (plan section 3.1's "new report code");
    referencing it directly inside the test body reds only this test with an AttributeError,
    never the whole module."""
    with world() as w:
        order = w.order()
        line = w.line(order, qty_ordered="220", required_date=date(2027, 3, 1))
        mirror = _adopted_mirror(w, order, line)
        matched_date = date(2026, 6, 1)
        fresh = _used_sibling(
            w, mirror, qty="220", delivery_date=date(2027, 3, 1),
            previous_qty="182", previous_delivery_date=matched_date,
            note="Replaces 182 used; SPO-A received",
        )
        if mismatch == "qty_off":
            sheet_qty, sheet_date = 183, matched_date
        else:
            sheet_qty, sheet_date = 182, date(2026, 7, 1)
        capture = _Capture()
        data = sheet([
            (order.so_number, w.product.product_code, sheet_qty, sheet_date,
             w.warehouse.warehouse_code, ""),
        ])

        _apply(w, data, outcome=capture, file_name="journey.xlsx")

        rows = w.rows()
        assert len(rows) == 1, [(str(r.qty), r.delivery_date) for r in rows]
        assert str(rows[0].id) == str(fresh.id), "no new row may be raised"

        matching = capture.by_code(oc.NO_USED_DELIVERY_MATCH)
        assert len(matching) == 1, capture.calls
        identity = matching[0].get("identity") or {}
        assert identity.get("doc_no") == order.so_number, identity
        assert identity.get("item_code") == w.product.product_code, identity
        assert identity.get("delivery_date") == sheet_date.isoformat(), identity
        # The UAC also asks the report to name the QUANTITY - `_identity()` carries no such
        # key today (`project_order_inquiry_import_service.py:2205`), so this is deliberately
        # permissive about WHERE it surfaces: an identity key, the tracked `value`, or the
        # message text. Whichever the coder picks, this assertion is the contract.
        named_qty = (
            identity.get("qty") == str(sheet_qty)
            or str(sheet_qty) in str(matching[0].get("value") or "")
            or str(sheet_qty) in str(matching[0].get("message") or "")
        )
        assert named_qty, matching[0]


def test_second_upload_leaves_used_pair_alone():
    """AC-RB-4. A line that already carries the used row (same qty and date,
    `redirected_to_pool = true`) is left alone: a second upload of the same book raises
    nothing on it and changes no column of either row."""
    with world() as w:
        order = w.order()
        line = w.line(order, qty_ordered="220", required_date=date(2027, 3, 1))
        mirror = _adopted_mirror(w, order, line)
        old_date = date(2026, 6, 1)
        _used_sibling(
            w, mirror, qty="220", delivery_date=date(2027, 3, 1),
            previous_qty="182", previous_delivery_date=old_date,
            note="Replaces 182 used; SPO-2026/08-0104 received",
        )
        data = sheet([
            (order.so_number, w.product.product_code, 182, old_date,
             w.warehouse.warehouse_code, ""),
        ])
        _apply(w, data, file_name="journey.xlsx")
        rows_before = {str(r.id): _row_snapshot(r) for r in w.rows()}
        assert len(rows_before) == 2, rows_before

        result = _apply(w, data, file_name="journey.xlsx")

        assert result["rows_raised"] == 0, result
        rows_after = {str(r.id): _row_snapshot(r) for r in w.rows()}
        assert rows_after == rows_before, (rows_before, rows_after)


def test_rebuilt_used_row_is_outside_demand():
    """AC-RB-5. The rebuilt used row is excluded from demand exactly where a confirm-made
    used row already is: no new link from the cascade (`auto_place_for_products`), the same
    read `test_oi_one_header.py::TestCascadeSkipsUsedRows` asserts on for AC-OH-10."""
    with world() as w:
        order = w.order()
        line = w.line(order, qty_ordered="220", required_date=date(2027, 3, 1))
        mirror = _adopted_mirror(w, order, line)
        old_date = date(2026, 6, 1)
        _used_sibling(
            w, mirror, qty="220", delivery_date=date(2027, 3, 1),
            previous_qty="182", previous_delivery_date=old_date,
            note="Replaces 182 used; SPO-2026/08-0104 received",
        )
        data = sheet([
            (order.so_number, w.product.product_code, 182, old_date,
             w.warehouse.warehouse_code, ""),
        ])
        _apply(w, data, file_name="journey.xlsx")
        used = next((r for r in w.rows() if r.redirected_to_pool), None)
        assert used is not None, "AC-RB-1 must raise the used row for this test to mean anything"
        before_links = len(w.links(used))

        # An open SPO for the same product/warehouse, real cascade capacity.
        w.spo_allocation(quantity=50)

        ProjectOrderInquiryService(w.db).auto_place_for_products(
            [str(w.product.id)], actor_user_id=w.actor, trigger="test-rb-5",
            include_awaiting=True,
        )
        w.db.flush()
        w.db.refresh(used)

        assert len(w.links(used)) == before_links, "no new link on the used row"


# --------------------------------------------------------------------------- #
# AC-RB-6 to AC-RB-10: received goods sit on the used row only                 #
# --------------------------------------------------------------------------- #


def test_received_link_moves_from_fresh_row_to_used_row():
    """AC-RB-6/AC-RB-10. The fresh row holds a link to a RECEIVED allocation (what
    `follow_book` wrote on prod after the used row was deleted). Raising the used row moves
    that link and its claim onto it, through the one link writer - the claim is REUSED
    (`claim_placed_on_po` fills but never repoints), so the claim COUNT in the database is
    unchanged, not merely non-zero."""
    with world() as w:
        order, line, mirror, fresh, allocation, claim, link = _pre_recovery_line(
            w, used_qty="182", fresh_qty="220", link_qty="182", received=True
        )
        claim_count_before = w.db.query(OrderLinkClaim).count()
        data = sheet([
            (order.so_number, w.product.product_code, 182, date(2026, 6, 1),
             w.warehouse.warehouse_code, ""),
        ])

        _apply(w, data, file_name="journey.xlsx")

        used = next((r for r in w.rows() if r.redirected_to_pool), None)
        assert used is not None, "AC-RB-1 must raise the used row for this test to mean anything"
        w.db.refresh(fresh)
        fresh_links = w.links(fresh)
        used_links = w.links(used)
        assert fresh_links == [], "the received link must leave the fresh row"
        assert len(used_links) == 1, used_links
        assert used_links[0].document == allocation.spo_number
        assert Decimal(str(used_links[0].qty)) == Decimal("182")
        assert w.db.query(OrderLinkClaim).count() == claim_count_before, (
            "the claim must be reused, not duplicated or orphaned"
        )
        # AC-RB-31's own invariant, pinned here too: the used row's links never total more
        # than its own quantity.
        assert sum(Decimal(str(l.qty)) for l in used_links) <= Decimal(str(used.qty))


def test_received_link_move_is_capped_at_used_qty():
    """AC-RB-7. A received link larger than the used row's own quantity moves only that
    quantity: 200 received, used row 182, so the used row holds 182 and the fresh row keeps
    the remaining 18."""
    with world() as w:
        order, line, mirror, fresh, allocation, claim, link = _pre_recovery_line(
            w, used_qty="182", fresh_qty="220", link_qty="200", received=True
        )
        data = sheet([
            (order.so_number, w.product.product_code, 182, date(2026, 6, 1),
             w.warehouse.warehouse_code, ""),
        ])

        _apply(w, data, file_name="journey.xlsx")

        used = next((r for r in w.rows() if r.redirected_to_pool), None)
        assert used is not None, "AC-RB-1 must raise the used row for this test to mean anything"
        w.db.refresh(fresh)
        used_qty_linked = sum(
            Decimal(str(l.qty)) for l in w.links(used) if l.document == allocation.spo_number
        )
        fresh_qty_linked = sum(
            Decimal(str(l.qty)) for l in w.links(fresh) if l.document == allocation.spo_number
        )
        assert used_qty_linked == Decimal("182"), used_qty_linked
        assert fresh_qty_linked == Decimal("18"), fresh_qty_linked
        # AC-RB-31's own invariant, pinned here too: the used row's links never total more
        # than its own quantity.
        assert used_qty_linked <= Decimal(str(used.qty))


def test_open_link_on_fresh_row_never_moves():
    """AC-RB-8. A link on the fresh row to a document that is NOT received (an open PO)
    never moves, whatever else the recovery does to the used side of the line."""
    with world() as w:
        order, line, mirror, fresh, allocation, claim, link = _pre_recovery_line(
            w, used_qty="182", fresh_qty="220", link_qty="182", received=True
        )
        po, po_line = w.po_line(qty_ordered="38", qty_received="0")
        open_link = OrderInquiryLink(
            id=_uid(), company_id=w.company_id, row_id=fresh.id, po_line_id=po_line.id,
            document=po.po_number, qty=Decimal("38"), linked_by=w.actor,
            linked_at=datetime(2026, 6, 3, 9, 0, 0), auto=True,
        )
        w.db.add(open_link)
        w.db.flush()
        open_link_id = str(open_link.id)

        data = sheet([
            (order.so_number, w.product.product_code, 182, date(2026, 6, 1),
             w.warehouse.warehouse_code, ""),
        ])
        _apply(w, data, file_name="journey.xlsx")

        w.db.refresh(open_link)
        assert str(open_link.row_id) == str(fresh.id)
        assert Decimal(str(open_link.qty)) == Decimal("38")
        used = next((r for r in w.rows() if r.redirected_to_pool), None)
        assert used is not None, "AC-RB-1 must raise the used row for this test to mean anything"
        assert all(str(l.id) != open_link_id for l in w.links(used))


def test_follow_book_leaves_received_link_on_used_row():
    """AC-RB-9 (R5, test-first). With the used row present, running `follow_book_for_rows`
    over the fresh row must not re-offer the received document to it: the link stays on the
    used row, none on the fresh row. May already be green once AC-RB-6 is green - the
    document's own remaining capacity is 0 once the move happened, which `pair_needs` would
    naturally starve regardless of any dedicated guard; report which."""
    with world() as w:
        order, line, mirror, fresh, allocation, claim, link = _pre_recovery_line(
            w, used_qty="182", fresh_qty="220", link_qty="182", received=True
        )
        data = sheet([
            (order.so_number, w.product.product_code, 182, date(2026, 6, 1),
             w.warehouse.warehouse_code, ""),
        ])
        _apply(w, data, file_name="journey.xlsx")
        used = next((r for r in w.rows() if r.redirected_to_pool), None)
        assert used is not None, "AC-RB-1 must raise the used row for this test to mean anything"
        w.db.refresh(fresh)

        ProjectOrderInquiryService(w.db).follow_book_for_rows(
            [str(fresh.id)], trigger="test-rb-9", company_id=w.company_id,
            actor_user_id=w.actor,
        )
        w.db.flush()

        w.db.refresh(used)
        w.db.refresh(fresh)
        assert [l.document for l in w.links(fresh)] == []
        used_docs = [l.document for l in w.links(used)]
        assert allocation.spo_number in used_docs, used_docs


def test_rebuilt_links_are_autocounts_not_the_sheets():
    """AC-RB-10 (R1). The used row's own link is one AutoCount's book names for the line
    (through the ref), never the sheet's own cited PO in the REMARK column."""
    with world() as w:
        order = w.order()
        line = w.line(order, qty_ordered="220", required_date=date(2027, 3, 1))
        ref = _ref()
        line.source_ref = ref
        w.db.flush()
        mirror = _adopted_mirror(w, order, line)
        old_date = date(2026, 6, 1)
        _used_sibling(
            w, mirror, qty="220", delivery_date=date(2027, 3, 1),
            previous_qty="182", previous_delivery_date=old_date,
            note="Replaces 182 used; SPO-2026/08-0104 received",
        )
        po, po_line = w.po_line(qty_ordered="182")
        po_line.from_so_line_ref = ref
        w.db.flush()
        sheets_cited_po = "SHEET-CITED-PO-999"
        data = sheet([
            (order.so_number, w.product.product_code, 182, old_date,
             w.warehouse.warehouse_code, sheets_cited_po),
        ])

        _apply(w, data, file_name="journey.xlsx")

        used = next((r for r in w.rows() if r.redirected_to_pool), None)
        assert used is not None, "AC-RB-1 must raise the used row for this test to mean anything"
        links = w.links(used)
        assert links, "the used row must take AutoCount's own link"
        assert links[0].document == po.po_number
        for row in w.rows():
            assert sheets_cited_po not in [l.document for l in w.links(row)], (
                "the sheet's own cited PO must never appear as a link"
            )


# --------------------------------------------------------------------------- #
# AC-RB-11 to AC-RB-16: restated rows                                          #
# --------------------------------------------------------------------------- #


def test_row_on_decided_line_is_raised_settled():
    """AC-RB-11 (and AC-RB-38's own `changed_at` half). A line with NO live row, covered by
    an ACTIVE decision whose snapshot differs from the sheet: the row is raised already
    settled (Now from the decision, Was from the sheet, `supply_decision_id` / `changed_at`
    set, `ack_state = changed`), and it still takes AutoCount's own link (R1). `changed_at`
    is the DECISION's own `confirmed_at` - seeded to a fixed instant distinct from "now" so a
    write that merely stamps `utcnow()` cannot pass by coincidence."""
    with world() as w:
        order = w.order()
        line = w.line(order, qty_ordered="280", required_date=date(2026, 10, 15))
        ProjectSOAdoptionService(w.db).adopt(str(order.id), w.actor)
        mirror = w.mirror_of(line)
        confirmed_at = datetime(2026, 9, 1, 3, 30, 0)
        decision = _decision(
            w, mirror, line, buy_qty="280", required_date=date(2027, 3, 1),
            confirmed_at=confirmed_at,
        )
        ref = _ref()
        line.source_ref = ref
        po, po_line = w.po_line(qty_ordered="280")
        po_line.from_so_line_ref = ref
        w.db.flush()
        old_date = date(2026, 6, 1)
        data = sheet([
            (order.so_number, w.product.product_code, 182, old_date,
             w.warehouse.warehouse_code, ""),
        ])

        _apply(w, data, file_name="journey.xlsx")

        row = w.one_row()
        assert Decimal(str(row.qty)) == Decimal("280")
        assert row.delivery_date == date(2027, 3, 1)
        assert Decimal(str(row.previous_qty)) == Decimal("182")
        assert row.previous_delivery_date == old_date
        assert str(row.supply_decision_id) == str(decision.id)
        assert row.changed_at is not None
        assert row.changed_at == confirmed_at, (row.changed_at, confirmed_at)
        assert row.ack_state == ACK_CHANGED
        assert (row.note or "").startswith(f"{importer._MIGRATION_STAMP} journey.xlsx")
        assert f"Was 182 on {old_date.isoformat()}" in (row.note or ""), row.note
        links = w.links(row)
        assert len(links) == 1, links
        assert links[0].document == po.po_number


def test_decision_equal_to_sheet_raises_plain():
    """AC-RB-12. The decision equals the sheet exactly (same qty, same date): the row is
    raised plain, no Was, no `changed_at`. May already be green: today's importer never
    reads a decision at all, so a matching decision changes nothing either way."""
    with world() as w:
        order = w.order()
        line = w.line(order, qty_ordered="280", required_date=date(2027, 3, 1))
        ProjectSOAdoptionService(w.db).adopt(str(order.id), w.actor)
        mirror = w.mirror_of(line)
        _decision(w, mirror, line, buy_qty="280", required_date=date(2027, 3, 1))
        data = sheet([
            (order.so_number, w.product.product_code, 280, date(2027, 3, 1),
             w.warehouse.warehouse_code, ""),
        ])

        _apply(w, data, file_name="journey.xlsx")

        row = w.one_row()
        assert Decimal(str(row.qty)) == Decimal("280")
        assert row.previous_qty is None
        assert row.previous_delivery_date is None
        assert row.changed_at is None


def test_buy_zero_decision_raises_plain():
    """AC-RB-13 (R4). The CSA150 shape: an active decision's buy_qty is 0 for the line - the
    sheet row is raised PLAIN exactly as today, never greyed, no Was/Now. May already be
    green for the same reason as AC-RB-12."""
    with world() as w:
        order = w.order()
        line = w.line(order, qty_ordered="36", required_date=date(2026, 12, 28))
        ProjectSOAdoptionService(w.db).adopt(str(order.id), w.actor)
        mirror = w.mirror_of(line)
        _decision(w, mirror, line, buy_qty="0", required_date=date(2026, 12, 28))
        data = sheet([
            (order.so_number, w.product.product_code, 36, date(2026, 12, 28),
             w.warehouse.warehouse_code, ""),
        ])

        _apply(w, data, file_name="journey.xlsx")

        row = w.one_row()
        assert Decimal(str(row.qty)) == Decimal("36")
        assert row.previous_qty is None
        assert row.redirected_to_pool is False


def test_superseded_decision_is_ignored():
    """AC-RB-14, half 1. A SUPERSEDED decision is never read: the row is raised plain, as
    if there were no decision at all."""
    with world() as w:
        order = w.order()
        line = w.line(order, qty_ordered="182", required_date=date(2026, 6, 1))
        ProjectSOAdoptionService(w.db).adopt(str(order.id), w.actor)
        mirror = w.mirror_of(line)
        _decision(
            w, mirror, line, buy_qty="280", required_date=date(2027, 3, 1),
            revision_no=1, state=DECISION_SUPERSEDED,
        )
        data = sheet([
            (order.so_number, w.product.product_code, 182, date(2026, 6, 1),
             w.warehouse.warehouse_code, ""),
        ])

        _apply(w, data, file_name="journey.xlsx")

        row = w.one_row()
        assert Decimal(str(row.qty)) == Decimal("182")
        assert row.previous_qty is None


def test_order_without_decision_unchanged():
    """AC-RB-14, half 2. A sales order with no decision at all behaves exactly as today.
    Already green - there is nothing for a decision-reading rule to have changed."""
    with world() as w:
        order = w.order()
        line = w.line(order, qty_ordered="182", required_date=date(2026, 6, 1))
        data = sheet([
            (order.so_number, w.product.product_code, 182, date(2026, 6, 1),
             w.warehouse.warehouse_code, ""),
        ])

        _apply(w, data, file_name="journey.xlsx")

        row = w.one_row()
        assert Decimal(str(row.qty)) == Decimal("182")
        assert row.previous_qty is None


def test_line_with_live_row_is_never_restated():
    """AC-RB-15 (must not change, prod TPE-9204 / SRTWC8605-SC-RL). A line that already
    carries a live row is never restated, whatever the active decision says: the second
    upload of the same book is left alone by the SAME `already_raised` rule that stands
    today. Already green: the importer's `_already_raised` skip does not read decisions."""
    with world() as w:
        order = w.order()
        line = w.line(order, qty_ordered="182", required_date=date(2026, 6, 1))
        data = sheet([
            (order.so_number, w.product.product_code, 182, date(2026, 6, 1),
             w.warehouse.warehouse_code, ""),
        ])
        _apply(w, data, file_name="first.xlsx")
        row = w.one_row()
        mirror = w.mirror_of(line)
        _decision(w, mirror, line, buy_qty="280", required_date=date(2027, 3, 1))
        before = _row_snapshot(row)

        result = _apply(w, data, file_name="first.xlsx")

        assert result["rows_raised"] == 0, result
        after = _row_snapshot(w.one_row())
        assert before == after, (before, after)


def test_second_upload_leaves_settled_row_alone():
    """AC-RB-16 (and AC-RB-33's own outcome-code half). A second upload of the same book
    changes no field of a row AC-RB-11 raised: its Now is not pulled back to the sheet's own
    figure, and the report is `already_raised` alone."""
    with world() as w:
        order = w.order()
        line = w.line(order, qty_ordered="280", required_date=date(2026, 10, 15))
        ProjectSOAdoptionService(w.db).adopt(str(order.id), w.actor)
        mirror = w.mirror_of(line)
        _decision(w, mirror, line, buy_qty="280", required_date=date(2027, 3, 1))
        old_date = date(2026, 6, 1)
        data = sheet([
            (order.so_number, w.product.product_code, 182, old_date,
             w.warehouse.warehouse_code, ""),
        ])
        _apply(w, data, file_name="journey.xlsx")
        before = _row_snapshot(w.one_row())

        capture = _Capture()
        result = _apply(w, data, outcome=capture, file_name="journey.xlsx")

        assert result["rows_raised"] == 0, result
        after = _row_snapshot(w.one_row())
        assert before == after, (before, after)
        # AC-RB-33: the second upload's report is `already_raised` and NOTHING else - no
        # mismatch code fires on a line whose live stamped row already equals this sheet
        # row on (previous quantity, previous date).
        assert capture.codes() == [oc.ALREADY_RAISED], capture.calls


# --------------------------------------------------------------------------- #
# AC-RB-17 to AC-RB-20: the rollback guard                                     #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("trait", ["redirected_to_pool", "changed_at", "supply_decision_id"])
def test_rollback_keeps_planning_rows(trait):
    """AC-RB-17. `rollback_oi_sheet_upload` keeps a stamped row planning has worked on, each
    trait on its own: the row, its links and its claims are all still there after `--apply`,
    and a plain sibling of the same upload still goes."""
    with world() as w:
        _order, _line, kept = _stamped_row(w, file_name="a.xlsx", trait=trait)
        _plain_order, _plain_line, plain = _stamped_row(w, file_name="a.xlsx", trait=None)
        kept_links = w.links(kept)
        kept_link_ids = [str(l.id) for l in kept_links]
        kept_claim_ids = [str(l.claim_id) for l in kept_links if l.claim_id]
        kept_id = str(kept.id)
        plain_id = str(plain.id)

        counts = _rollback().run(w.db, file_name="a.xlsx", apply=True)

        assert w.db.query(OrderInquiryRow).filter(
            OrderInquiryRow.id == kept_id
        ).count() == 1, f"the {trait} row must survive the rollback"
        assert w.db.query(OrderInquiryLink).filter(
            OrderInquiryLink.id.in_(kept_link_ids)
        ).count() == len(kept_link_ids), "the kept row's links must survive too"
        if kept_claim_ids:
            assert w.db.query(OrderLinkClaim).filter(
                OrderLinkClaim.id.in_(kept_claim_ids)
            ).count() == len(kept_claim_ids), "the kept row's claims must survive too"
        assert w.db.query(OrderInquiryRow).filter(
            OrderInquiryRow.id == plain_id
        ).count() == 0, "the plain row of the same upload must still go"
        assert counts.get("kept") == 1, counts


def test_rollback_still_deletes_plain_rows():
    """AC-RB-18. A stamped row with none of the three traits is deleted exactly as today,
    links included."""
    with world() as w:
        _order, _line, plain = _stamped_row(w, file_name="a.xlsx", trait=None)
        plain_links = w.links(plain)
        plain_id = str(plain.id)
        link_ids = [str(l.id) for l in plain_links]

        counts = _rollback().run(w.db, file_name="a.xlsx", apply=True)

        assert counts["rows"] == 1, counts
        assert w.db.query(OrderInquiryRow).filter(OrderInquiryRow.id == plain_id).count() == 0
        assert w.db.query(OrderInquiryLink).filter(OrderInquiryLink.id.in_(link_ids)).count() == 0


def test_rollback_names_kept_rows():
    """AC-RB-19. The dry run and the `--apply` output both state how many rows were kept
    and name each one (sales order, item, quantity, date, which trait kept it); the removed
    count excludes them, and a dry run answers exactly what `--apply` would.

    Assumed shape (the coder builds to it, per the brief): `run()` returns the existing four
    counts plus `"kept"` (an int) and `"kept_rows"` (a list of dicts carrying at least
    `so_number`, `item_code`, `qty`, `delivery_date`, `trait`)."""
    with world() as w:
        order, _line, _kept = _stamped_row(w, file_name="a.xlsx", trait="redirected_to_pool")
        _plain_order, _plain_line, _plain = _stamped_row(w, file_name="a.xlsx", trait=None)

        dry = _rollback().run(w.db, file_name="a.xlsx", apply=False)
        applied = _rollback().run(w.db, file_name="a.xlsx", apply=True)

        assert dry == applied, (dry, applied)
        assert dry.get("kept") == 1, dry
        assert dry.get("rows") == 1, "the removed count must exclude the kept row"
        kept_rows = dry.get("kept_rows") or []
        assert len(kept_rows) == 1, kept_rows
        named = kept_rows[0]
        assert named.get("so_number") == order.so_number, named
        assert named.get("item_code") == w.product.product_code, named
        assert Decimal(str(named.get("qty"))) == Decimal("30"), named
        assert named.get("trait") == "redirected_to_pool", named


def test_rollback_then_reupload_changes_nothing_kept():
    """AC-RB-20. Rollback then re-upload, with a kept row on the line: the kept row is not
    duplicated and not altered - AC-RB-4 and AC-RB-16 hold across a rollback."""
    with world() as w:
        order, _line, kept = _stamped_row(w, file_name="a.xlsx", trait="redirected_to_pool")
        before = _row_snapshot(kept)
        kept_id = str(kept.id)
        row_count_before = w.db.query(OrderInquiryRow).count()

        _rollback().run(w.db, file_name="a.xlsx", apply=True)
        assert w.db.query(OrderInquiryRow).filter(
            OrderInquiryRow.id == kept_id
        ).count() == 1, "AC-RB-17's guard must keep this row through the rollback"
        _apply(
            w,
            sheet([
                (order.so_number, w.product.product_code, 30, D_OCT,
                 w.warehouse.warehouse_code, ""),
            ]),
            file_name="a.xlsx",
        )

        w.db.refresh(kept)
        after = _row_snapshot(kept)
        assert before == after, (before, after)
        assert w.db.query(OrderInquiryRow).count() == row_count_before, (
            "no duplicate row was raised"
        )


# --------------------------------------------------------------------------- #
# AC-RB-21: the whole journey                                                  #
# --------------------------------------------------------------------------- #


def _old_style_delete(w: World, file_name: str) -> None:
    """What `rollback_oi_sheet_upload.py` did before the 2.3 guard existed (and, until the
    coder builds it, still does): every row carrying the stamp goes, planning traits or not
    (plan section 0). Written independently of the module under test, deliberately NOT by
    calling `rollback_oi_sheet_upload.run()` - once the guard ships, that stops being the old
    behaviour, and this helper must keep being it so AC-RB-21 still starts from the real
    19 Sep 2026 damage."""
    stamp = f"{importer._MIGRATION_STAMP} {file_name}"
    rows = [
        row for row in w.db.query(OrderInquiryRow).all()
        if (row.note or "").startswith(stamp)
    ]
    for row in rows:
        w.db.delete(row)
    w.db.flush()


def test_journey_upload_confirm_old_delete_rollback_reupload():
    """AC-RB-21. Upload raises three rows (line A, line B, line C). A real confirm produces
    a used+fresh pair on line A (its row already holds a received link) and restates line B
    in place; line C stays covered by a buy-0 decision and untouched. Every stamped row is
    then deleted the way the pre-fix rollback did, the new rollback runs over what is left
    (nothing to guard), and the sheet is uploaded again: the used row, the fresh row, the
    restated row and every link read exactly as they did before the deletion, and line C's
    row is plain."""
    with world() as w:
        order = w.order()
        product_b = w.product_row()
        product_c = w.product_row()
        line_a = w.line(order, qty_ordered="220", required_date=date(2027, 3, 1))
        line_b = w.line(
            order, product=product_b, qty_ordered="280", required_date=date(2027, 4, 1)
        )
        line_c = w.line(
            order, product=product_c, qty_ordered="36", required_date=date(2026, 12, 28)
        )
        # `ProjectSupplyService.confirm` refuses a line at a bin flagged out of fulfilment
        # planning (`fulfilment_planning`, default False on a freshly seeded warehouse -
        # `test_planning_changes._warehouse` sets it True for the same reason).
        w.warehouse.fulfilment_planning = True
        w.db.flush()
        file_name = "journey.xlsx"
        sheet_date_a = date(2026, 6, 1)
        sheet_date_b = date(2026, 9, 1)
        data = sheet([
            (order.so_number, w.product.product_code, 182, sheet_date_a,
             w.warehouse.warehouse_code, ""),
            (order.so_number, product_b.product_code, 182, sheet_date_b,
             w.warehouse.warehouse_code, ""),
            (order.so_number, product_c.product_code, 36, date(2026, 12, 28),
             w.warehouse.warehouse_code, ""),
        ])

        first = _apply(w, data, file_name=file_name)
        assert first["rows_raised"] == 3, first

        mirror_a = w.mirror_of(line_a)
        mirror_b = w.mirror_of(line_b)
        mirror_c = w.mirror_of(line_c)
        row_a = next(r for r in w.rows() if str(r.so_line_id) == str(mirror_a.id))
        row_b = next(r for r in w.rows() if str(r.so_line_id) == str(mirror_b.id))

        # A received document already sits on line A's row - exactly the pre-recovery prod
        # shape (`follow_book`'s own history), seeded directly rather than through the
        # importer's own pairing, which names no document for an unrefed line.
        allocation = w.spo_allocation(quantity=182, received=182)
        received_claim = w.claim(
            order=order, core_line=line_a, document=allocation.spo_number,
            allocation=allocation,
        )
        w.db.add(OrderInquiryLink(
            id=_uid(), company_id=w.company_id, row_id=row_a.id,
            spo_allocation_id=allocation.id, document=allocation.spo_number,
            qty=Decimal("182"), linked_by=w.actor,
            linked_at=datetime(2026, 6, 3, 9, 0, 0), auto=True, claim_id=received_claim.id,
        ))
        w.db.flush()
        ProjectOrderInquiryService(w.db).refresh_link_state([row_a])
        w.db.flush()

        pso = (
            w.db.query(ProjectSalesOrder)
            .filter(ProjectSalesOrder.id == mirror_a.project_sales_order_id)
            .one()
        )
        line_a.qty_ordered = Decimal("220")
        line_a.required_date = date(2027, 3, 1)
        line_b.qty_ordered = Decimal("280")
        line_b.required_date = date(2027, 4, 1)
        mirror_a.qty = Decimal("220")
        mirror_a.delivery_date = date(2027, 3, 1)
        mirror_b.qty = Decimal("280")
        mirror_b.delivery_date = date(2027, 4, 1)
        w.db.flush()

        confirm_body = ConfirmSupplyBody(lines=[
            ConfirmLine(
                project_line_id=str(mirror_a.id), timely_spo_qty="0",
                reserve=[], borrow=[], buy_qty="220",
            ),
            ConfirmLine(
                project_line_id=str(mirror_b.id), timely_spo_qty="0",
                reserve=[], borrow=[], buy_qty="280",
            ),
        ])
        ProjectSupplyService(w.db).confirm(
            pso, confirm_body, actor_user_id=w.actor,
            settle_in_place_line_ids=[str(mirror_a.id), str(mirror_b.id)],
        )
        w.db.flush()

        # Line C: covered by the SAME active decision (buy 0, "all from stock" - CS's own
        # front-planning fact), injected directly into the revision the confirm just wrote
        # rather than through a second `confirm()` call, which the one-active-decision
        # partial unique index would refuse. Its own sheet-raised row is never named in
        # `settle_in_place_line_ids` and is never touched.
        decision = ProjectSupplyService(w.db).active_decision(str(pso.id))
        assert decision is not None, "the confirm above must have written the revision"
        c_snapshot = {
            "line_no": 3,
            "project_line_id": str(mirror_c.id),
            "core_line_id": str(line_c.id),
            "item_code": product_c.product_code,
            "location": w.warehouse.warehouse_code,
            "required_date": line_c.required_date.isoformat(),
            "open_qty": "36",
            "timely_spo_qty": "0",
            "timely_spo_refs": [],
            "reserve_qty": "36",
            "borrow_qty": "0",
            "buy_qty": "0",
            "components": [],
            "proposed_components": [],
        }
        decision.line_snapshots = list(decision.line_snapshots) + [c_snapshot]
        w.db.flush()

        w.db.refresh(row_a)
        used_row = row_a
        assert used_row.redirected_to_pool is True, "fixture sanity: line A must redirect"
        fresh_row = next(
            r for r in w.rows()
            if str(r.so_line_id) == str(mirror_a.id) and str(r.id) != str(used_row.id)
        )
        w.db.refresh(row_b)
        restated_row = row_b
        assert Decimal(str(restated_row.qty)) == Decimal("280"), "fixture sanity: line B settled"
        plain_row = next(r for r in w.rows() if str(r.so_line_id) == str(mirror_c.id))

        before = {
            "used": _row_snapshot(used_row),
            "fresh": _row_snapshot(fresh_row),
            "restated": _row_snapshot(restated_row),
            "plain": _row_snapshot(plain_row),
        }
        before_used_links = {
            (l.document, str(Decimal(str(l.qty)))) for l in w.links(used_row)
        }
        before_fresh_links = {
            (l.document, str(Decimal(str(l.qty)))) for l in w.links(fresh_row)
        }

        _old_style_delete(w, file_name)
        assert _rows_of(w, file_name) == [], "the old-style delete must take every stamped row"

        rollback_counts = _rollback().run(w.db, file_name=file_name, apply=True)
        assert rollback_counts["rows"] == 0, rollback_counts

        _apply(w, data, file_name=file_name)

        mirror_a2 = w.mirror_of(line_a)
        mirror_b2 = w.mirror_of(line_b)
        mirror_c2 = w.mirror_of(line_c)
        rows_a = [r for r in w.rows() if str(r.so_line_id) == str(mirror_a2.id)]
        used_after = next((r for r in rows_a if r.redirected_to_pool), None)
        assert used_after is not None, "the used row must come back on re-upload"
        fresh_after = next(r for r in rows_a if not r.redirected_to_pool)
        restated_after = next(
            r for r in w.rows() if str(r.so_line_id) == str(mirror_b2.id)
        )
        plain_after = next(
            r for r in w.rows() if str(r.so_line_id) == str(mirror_c2.id)
        )

        after = {
            "used": _row_snapshot(used_after),
            "fresh": _row_snapshot(fresh_after),
            "restated": _row_snapshot(restated_after),
            "plain": _row_snapshot(plain_after),
        }
        assert after["used"]["redirected_to_pool"] is True
        assert after["used"]["qty"] == before["used"]["qty"]
        assert after["used"]["delivery_date"] == before["used"]["delivery_date"]
        assert after["fresh"]["qty"] == before["fresh"]["qty"]
        assert after["fresh"]["previous_qty"] == before["fresh"]["previous_qty"]
        assert (
            after["fresh"]["previous_delivery_date"] == before["fresh"]["previous_delivery_date"]
        )
        assert after["restated"]["qty"] == before["restated"]["qty"]
        assert after["restated"]["previous_qty"] == before["restated"]["previous_qty"]
        assert after["restated"]["changed_at"] is not None
        assert after["plain"]["previous_qty"] is None
        assert after["plain"]["redirected_to_pool"] is False
        assert Decimal(after["plain"]["qty"]) == Decimal("36")

        after_used_links = {
            (l.document, str(Decimal(str(l.qty)))) for l in w.links(used_after)
        }
        after_fresh_links = {
            (l.document, str(Decimal(str(l.qty)))) for l in w.links(fresh_after)
        }
        assert after_used_links == before_used_links, (before_used_links, after_used_links)
        assert after_fresh_links == before_fresh_links, (before_fresh_links, after_fresh_links)


# --------------------------------------------------------------------------- #
# AC-RB-24 to AC-RB-30: notice rows and the top-up shape (R7/R8, slice S5)      #
# --------------------------------------------------------------------------- #
#
# "Shapes found on the full 18 Sep copy" (UAC), rulings R7/R8 (plan section 1). Written
# straight off the UAC wording, not off round 2's implementation - there is none yet.


def _delay_notice(w: World, mirror, *, qty: str, delivery_date: date, note: str) -> OrderInquiryRow:
    """A DELAY notice: what a date-moved-later amendment raises, verb DELAY - never ORDER
    or ORDER BACK, and never (R7) a stand-in for the line's own still-owed row. Built on
    `board_row`'s own header/row plumbing, verb and note overwritten after, exactly as
    `_used_sibling` overwrites a plain board row into a `Replaces N used` shape."""
    row = w.board_row(mirror, qty=qty)
    row.verb = IV_DELAY
    row.delivery_date = delivery_date
    row.note = note
    w.db.flush()
    return row


def test_delay_notice_does_not_block_the_line():
    """AC-RB-24 (R7), the TPE-9204 (a) shape. A line whose only live row is a DELAY notice
    is NOT "already raised": AC-RB-11 applies to it exactly as it would to a line with no
    live row at all - raised already settled (280, was 182), and the notice's own presence
    changes nothing about that."""
    with world() as w:
        order = w.order()
        line = w.line(order, qty_ordered="280", required_date=date(2027, 4, 1))
        mirror = _adopted_mirror(w, order, line)
        decision = _decision(w, mirror, line, buy_qty="280", required_date=date(2027, 4, 1))
        notice = _delay_notice(
            w, mirror, qty="280", delivery_date=date(2027, 4, 1), note="Was 2026-09-01",
        )
        ref = _ref()
        line.source_ref = ref
        po, po_line = w.po_line(qty_ordered="280")
        po_line.from_so_line_ref = ref
        w.db.flush()
        old_date = date(2026, 9, 1)
        capture = _Capture()
        data = sheet([
            (order.so_number, w.product.product_code, 182, old_date,
             w.warehouse.warehouse_code, ""),
        ])

        _apply(w, data, outcome=capture, file_name="journey.xlsx")

        assert oc.ALREADY_RAISED not in capture.codes(), capture.calls
        rows = [r for r in w.rows() if str(r.so_line_id) == str(mirror.id)]
        assert len(rows) == 2, [(r.verb, str(r.qty), r.delivery_date) for r in rows]
        settled = next(r for r in rows if str(r.id) != str(notice.id))
        assert Decimal(str(settled.qty)) == Decimal("280")
        assert settled.delivery_date == date(2027, 4, 1)
        assert Decimal(str(settled.previous_qty)) == Decimal("182")
        assert settled.previous_delivery_date == old_date
        assert str(settled.supply_decision_id) == str(decision.id)
        assert settled.changed_at is not None
        assert settled.ack_state == ACK_CHANGED
        assert (settled.note or "").startswith(f"{importer._MIGRATION_STAMP} journey.xlsx")
        assert f"Was 182 on {old_date.isoformat()}" in (settled.note or ""), settled.note


def test_delay_notice_line_without_decision_raises_plain():
    """AC-RB-24 (R7), no decision. The same DELAY-notice-only line, with no active decision
    covering it: the sheet row is raised plain, exactly as a line with no live row and no
    decision is today."""
    with world() as w:
        order = w.order()
        line = w.line(order, qty_ordered="182", required_date=date(2026, 9, 1))
        mirror = _adopted_mirror(w, order, line)
        notice = _delay_notice(
            w, mirror, qty="280", delivery_date=date(2027, 4, 1), note="Was 2026-09-01",
        )
        capture = _Capture()
        data = sheet([
            (order.so_number, w.product.product_code, 182, date(2026, 9, 1),
             w.warehouse.warehouse_code, ""),
        ])

        _apply(w, data, outcome=capture, file_name="journey.xlsx")

        assert oc.ALREADY_RAISED not in capture.codes(), capture.calls
        rows = [r for r in w.rows() if str(r.so_line_id) == str(mirror.id)]
        assert len(rows) == 2, [(r.verb, str(r.qty), r.delivery_date) for r in rows]
        plain = next(r for r in rows if str(r.id) != str(notice.id))
        assert Decimal(str(plain.qty)) == Decimal("182")
        assert plain.previous_qty is None


def test_notice_row_is_never_touched():
    """AC-RB-25 (R7). The notice row itself is never altered, re-raised or cancelled by
    the upload: every column equal before and after, whatever the upload does to the rest
    of the line."""
    with world() as w:
        order = w.order()
        line = w.line(order, qty_ordered="280", required_date=date(2027, 4, 1))
        mirror = _adopted_mirror(w, order, line)
        _decision(w, mirror, line, buy_qty="280", required_date=date(2027, 4, 1))
        notice = _delay_notice(
            w, mirror, qty="280", delivery_date=date(2027, 4, 1), note="Was 2026-09-01",
        )
        # Refreshed before snapshotting - see the note on the same pattern in
        # `test_board_row_without_active_decision_still_already_raised`.
        w.db.refresh(notice)
        before = _row_snapshot(notice)
        data = sheet([
            (order.so_number, w.product.product_code, 182, date(2026, 9, 1),
             w.warehouse.warehouse_code, ""),
        ])

        _apply(w, data, file_name="journey.xlsx")

        w.db.refresh(notice)
        after = _row_snapshot(notice)
        assert before == after, (before, after)
        assert notice.state != INQUIRY_CANCELLED


def test_top_up_shape_raises_sheet_row_plain():
    """AC-RB-26 (R8), the SRTWC8605-SC-RL shape. The line's live ORDER row (38) carries the
    active decision's own `supply_decision_id`, and the sheet's 182 plus that 38 equals the
    decision's buy_qty (220): the sheet row is raised PLAIN - no Was/Now, not greyed - and
    still takes AutoCount's own link; the top-up row is untouched."""
    with world() as w:
        order = w.order()
        line = w.line(order, qty_ordered="500", required_date=date(2027, 1, 4))
        mirror = _adopted_mirror(w, order, line)
        decision = _decision(w, mirror, line, buy_qty="220", required_date=date(2027, 1, 4))
        top_up = w.board_row(mirror, qty="38")
        top_up.supply_decision_id = decision.id
        w.db.flush()
        # Refreshed before snapshotting (see the same note in
        # `test_board_row_without_active_decision_still_already_raised`): the AFTER read is
        # off the database, and an unrefreshed BEFORE would disagree with it on `Decimal`
        # formatting alone.
        w.db.refresh(top_up)
        top_up_before = _row_snapshot(top_up)
        ref = _ref()
        line.source_ref = ref
        po, po_line = w.po_line(qty_ordered="182")
        po_line.from_so_line_ref = ref
        w.db.flush()
        data = sheet([
            (order.so_number, w.product.product_code, 182, date(2027, 1, 4),
             w.warehouse.warehouse_code, ""),
        ])

        _apply(w, data, file_name="journey.xlsx")

        rows = [r for r in w.rows() if str(r.so_line_id) == str(mirror.id)]
        assert len(rows) == 2, [(r.verb, str(r.qty), r.delivery_date) for r in rows]
        plain = next(r for r in rows if str(r.id) != str(top_up.id))
        assert Decimal(str(plain.qty)) == Decimal("182")
        assert plain.previous_qty is None
        assert plain.previous_delivery_date is None
        assert plain.changed_at is None
        assert plain.redirected_to_pool is False
        links = w.links(plain)
        assert len(links) == 1, links
        assert links[0].document == po.po_number
        w.db.refresh(top_up)
        assert _row_snapshot(top_up) == top_up_before, "the top-up row must be untouched"


@pytest.mark.parametrize("scenario", ["sheet_180", "decision_230"])
def test_top_up_sum_mismatch_raises_nothing_and_is_reported(scenario):
    """AC-RB-27 (R8). Same top-up shape, but the sum does not equal the decision's buy_qty
    - either the sheet's own quantity is off (180, not 182) or the decision's buy_qty is off
    (230, not 220): nothing is raised, and the upload report names the sheet row with its own
    outcome code, as AC-RB-3 does.

    `oc.TOP_UP_SUM_MISMATCH` does not exist yet; referencing it directly reds only this test
    with an AttributeError, never the whole module."""
    with world() as w:
        order = w.order()
        line = w.line(order, qty_ordered="500", required_date=date(2027, 1, 4))
        mirror = _adopted_mirror(w, order, line)
        buy_qty = "230" if scenario == "decision_230" else "220"
        decision = _decision(w, mirror, line, buy_qty=buy_qty, required_date=date(2027, 1, 4))
        top_up = w.board_row(mirror, qty="38")
        top_up.supply_decision_id = decision.id
        w.db.flush()
        sheet_qty = 180 if scenario == "sheet_180" else 182
        sheet_date = date(2027, 1, 4)
        capture = _Capture()
        data = sheet([
            (order.so_number, w.product.product_code, sheet_qty, sheet_date,
             w.warehouse.warehouse_code, ""),
        ])

        _apply(w, data, outcome=capture, file_name="journey.xlsx")

        rows = [r for r in w.rows() if str(r.so_line_id) == str(mirror.id)]
        assert len(rows) == 1, [(r.verb, str(r.qty), r.delivery_date) for r in rows]
        assert str(rows[0].id) == str(top_up.id), "no new row may be raised"

        matching = capture.by_code(oc.TOP_UP_SUM_MISMATCH)
        assert len(matching) == 1, capture.calls
        identity = matching[0].get("identity") or {}
        assert identity.get("doc_no") == order.so_number, identity
        assert identity.get("item_code") == w.product.product_code, identity
        assert identity.get("delivery_date") == sheet_date.isoformat(), identity
        named_qty = (
            identity.get("qty") == str(sheet_qty)
            or str(sheet_qty) in str(matching[0].get("value") or "")
            or str(sheet_qty) in str(matching[0].get("message") or "")
        )
        assert named_qty, matching[0]


@pytest.mark.parametrize("shape", ["no_decision", "superseded_decision"])
def test_board_row_without_active_decision_still_already_raised(shape):
    """AC-RB-28. A line whose live ORDER row carries no `supply_decision_id` of the ACTIVE
    decision - either none at all (a board row raised before the migration, the original D2
    case) or one that points at a SUPERSEDED decision - is still left alone: `already_raised`,
    exactly as today, row unchanged. May already be green: today's `_already_raised` never
    reads `supply_decision_id` at all."""
    with world() as w:
        order = w.order()
        line = w.line(order, qty_ordered="182", required_date=date(2026, 6, 1))
        mirror = _adopted_mirror(w, order, line)
        board_row = w.board_row(mirror, qty="182")
        board_row.delivery_date = date(2026, 6, 1)
        if shape == "superseded_decision":
            stale = _decision(
                w, mirror, line, buy_qty="182", required_date=date(2026, 6, 1),
                state=DECISION_SUPERSEDED,
            )
            board_row.supply_decision_id = stale.id
        w.db.flush()
        # Refreshed rather than snapshotted straight from the in-memory object: Postgres'
        # NUMERIC(15,4) round-trips `Decimal("182")` as `Decimal("182.0000")`, and the AFTER
        # snapshot below is read fresh off the database - an unrefreshed BEFORE would fail
        # the comparison on formatting alone, never on behaviour.
        w.db.refresh(board_row)
        before = _row_snapshot(board_row)
        capture = _Capture()
        data = sheet([
            (order.so_number, w.product.product_code, 182, date(2026, 6, 1),
             w.warehouse.warehouse_code, ""),
        ])

        result = _apply(w, data, outcome=capture, file_name="journey.xlsx")

        assert result["rows_raised"] == 0, result
        matching = capture.by_code(oc.ALREADY_RAISED)
        assert len(matching) == 1, capture.calls
        rows = [r for r in w.rows() if str(r.so_line_id) == str(mirror.id)]
        assert len(rows) == 1, rows
        w.db.refresh(board_row)
        after = _row_snapshot(board_row)
        assert before == after, (before, after)


@pytest.mark.parametrize("sibling_kind", ["supply_decision_id", "replaces_used", "delay_notice"])
def test_rollback_keeps_stamped_row_on_a_planning_line(sibling_kind):
    """AC-RB-29. Rollback also keeps a stamped row whose LINE (not the row itself) carries a
    live sibling planning made - a row with `supply_decision_id`, a `Replaces N used` row, or
    a DELAY notice - trait `planning_row_on_line` in the kept listing. A stamped plain row on
    a line with NO such sibling is still deleted, in the same run."""
    with world() as w:
        order = w.order()
        line = w.line(order, qty_ordered="220", required_date=date(2027, 3, 1))
        ref = _ref()
        line.source_ref = ref
        po, po_line = w.po_line(qty_ordered="182")
        po_line.from_so_line_ref = ref
        w.db.flush()
        result = _apply(
            w,
            sheet([
                (order.so_number, w.product.product_code, 182, date(2026, 6, 1),
                 w.warehouse.warehouse_code, ""),
            ]),
            file_name="a.xlsx",
        )
        assert result["rows_raised"] == 1, result
        mirror = w.mirror_of(line)
        stamped = next(
            r for r in _rows_of(w, "a.xlsx") if str(r.so_line_id) == str(mirror.id)
        )

        if sibling_kind == "supply_decision_id":
            decision = _decision(w, mirror, line, buy_qty="220", required_date=date(2027, 3, 1))
            sibling = w.board_row(mirror, qty="38")
            sibling.supply_decision_id = decision.id
            w.db.flush()
        elif sibling_kind == "replaces_used":
            _used_sibling(
                w, mirror, qty="220", delivery_date=date(2027, 3, 1),
                previous_qty="182", previous_delivery_date=date(2026, 6, 1),
                note="Replaces 182 used; SPO-2026/08-0104 received",
            )
        else:
            _delay_notice(
                w, mirror, qty="220", delivery_date=date(2027, 3, 1), note="Was 2026-09-01",
            )

        # The control: a stamped plain row on a DIFFERENT line of the SAME upload, with no
        # planning sibling of its own - still goes.
        _control_order, _control_line, control = _stamped_row(w, file_name="a.xlsx", trait=None)

        stamped_id = str(stamped.id)
        control_id = str(control.id)

        counts = _rollback().run(w.db, file_name="a.xlsx", apply=True)

        assert w.db.query(OrderInquiryRow).filter(
            OrderInquiryRow.id == stamped_id
        ).count() == 1, (
            f"the stamped row on a line carrying a {sibling_kind} sibling must survive"
        )
        assert w.db.query(OrderInquiryRow).filter(
            OrderInquiryRow.id == control_id
        ).count() == 0, "a stamped plain row with no planning sibling on its line must still go"
        kept_rows = counts.get("kept_rows") or []
        named = next(
            (row for row in kept_rows if row.get("so_number") == order.so_number), None
        )
        assert named is not None, kept_rows
        assert named.get("trait") == "planning_row_on_line", named


@pytest.mark.parametrize("shape", ["delay_notice", "top_up"])
def test_second_upload_changes_nothing_on_s5_lines(shape):
    """AC-RB-30 (and AC-RB-33's own outcome-code half). A second upload after AC-RB-24 (the
    notice shape) or AC-RB-26 (the top-up shape) changes nothing on those lines: 0 raised,
    every column of every row on the line equal before and after, and the report is
    `already_raised` alone - never a mismatch code on a line the sheet restates exactly."""
    with world() as w:
        order = w.order()
        line = w.line(order, qty_ordered="500", required_date=date(2027, 4, 1))
        mirror = _adopted_mirror(w, order, line)
        if shape == "delay_notice":
            _decision(w, mirror, line, buy_qty="280", required_date=date(2027, 4, 1))
            _delay_notice(
                w, mirror, qty="280", delivery_date=date(2027, 4, 1), note="Was 2026-09-01",
            )
            sheet_qty, sheet_date = 182, date(2026, 9, 1)
        else:
            decision = _decision(w, mirror, line, buy_qty="220", required_date=date(2027, 1, 4))
            top_up = w.board_row(mirror, qty="38")
            top_up.supply_decision_id = decision.id
            w.db.flush()
            sheet_qty, sheet_date = 182, date(2027, 1, 4)
        data = sheet([
            (order.so_number, w.product.product_code, sheet_qty, sheet_date,
             w.warehouse.warehouse_code, ""),
        ])
        first = _apply(w, data, file_name="journey.xlsx")
        rows_before = {
            str(r.id): _row_snapshot(r)
            for r in w.rows() if str(r.so_line_id) == str(mirror.id)
        }
        assert len(rows_before) == 2, rows_before

        capture = _Capture()
        second = _apply(w, data, outcome=capture, file_name="journey.xlsx")

        assert second["rows_raised"] == 0, second
        rows_after = {
            str(r.id): _row_snapshot(r)
            for r in w.rows() if str(r.so_line_id) == str(mirror.id)
        }
        assert rows_after == rows_before, (rows_before, rows_after)
        # AC-RB-33: `already_raised`, and no other code - a mismatch code (`top_up_sum_
        # mismatch` for the top-up arm, in particular) must not fire on a line the sheet is
        # re-stating exactly.
        assert capture.codes() == [oc.ALREADY_RAISED], capture.calls


# --------------------------------------------------------------------------- #
# AC-RB-31 to AC-RB-41: review round (reviewer + security-reviewer, S6)        #
# --------------------------------------------------------------------------- #
#
# Asserted straight off the UAC's own words, not off the round-2 implementation both
# reviewers reproduced these against (head db49703f6) - AC-RB-40 is review-verified only,
# no test here.


def test_used_row_links_never_exceed_its_qty():
    """AC-RB-31 (blocker B1). The received-link move is capped at the row's quantity MINUS
    what the upload's own book pairing already linked onto it - not merely at the row's raw
    quantity. Fixture: a 400 received allocation, the fresh row already holds 182 of it
    (218 unclaimed), and the SAME document is the book's own pairing for the line (via ref),
    so the upload's ordinary auto-link walk can ALSO reach it independently of the move.
    Today: two links land on the used row (the moved 182 and a second, freshly book-paired
    182), summing to 364 - more than the row's own 182."""
    with world() as w:
        order, line, mirror, fresh, allocation, claim, link = _pre_recovery_line(
            w, used_qty="182", fresh_qty="220", link_qty="182", received=True,
            allocation_qty="400",
        )
        data = sheet([
            (order.so_number, w.product.product_code, 182, date(2026, 6, 1),
             w.warehouse.warehouse_code, ""),
        ])

        _apply(w, data, file_name="journey.xlsx")

        used = next((r for r in w.rows() if r.redirected_to_pool), None)
        assert used is not None, "AC-RB-1 must raise the used row for this test to mean anything"
        used_links = w.links(used)
        total_linked = sum(Decimal(str(l.qty)) for l in used_links)
        assert total_linked == Decimal("182"), (
            total_linked, [(l.document, str(l.qty)) for l in used_links],
        )
        assert total_linked <= Decimal(str(used.qty))


def test_two_sheet_rows_on_one_decided_line_are_raised_plain():
    """AC-RB-32, first half. Two sheet rows landing on ONE line an active decision covers:
    AC-RB-11 does not fire for either - the same refusal `_settle_row_in_place` makes for
    two live rows - both are raised PLAIN, as today. Today both come back settled to the
    decision's own 280."""
    with world() as w:
        order = w.order()
        line = w.line(order, qty_ordered="500", required_date=date(2027, 3, 1))
        mirror = _adopted_mirror(w, order, line)
        _decision(w, mirror, line, buy_qty="280", required_date=date(2027, 3, 1))
        data = sheet([
            (order.so_number, w.product.product_code, 182, date(2026, 6, 1),
             w.warehouse.warehouse_code, ""),
            (order.so_number, w.product.product_code, 100, date(2026, 7, 1),
             w.warehouse.warehouse_code, ""),
        ])

        _apply(w, data, file_name="journey.xlsx")

        rows = [r for r in w.rows() if str(r.so_line_id) == str(mirror.id)]
        assert len(rows) == 2, [(str(r.qty), r.delivery_date) for r in rows]
        qtys = sorted(Decimal(str(r.qty)) for r in rows)
        assert qtys == [Decimal("100"), Decimal("182")], qtys
        for row in rows:
            assert row.previous_qty is None, _row_snapshot(row)
            assert row.changed_at is None, _row_snapshot(row)
            assert row.supply_decision_id is None, _row_snapshot(row)


def test_two_sheet_rows_on_a_top_up_line_stay_already_raised():
    """AC-RB-32, second half. Two sheet rows landing on a top-up line: AC-RB-26 does not
    fire, they read `already_raised`, no mismatch code."""
    with world() as w:
        order = w.order()
        line = w.line(order, qty_ordered="500", required_date=date(2027, 1, 4))
        mirror = _adopted_mirror(w, order, line)
        decision = _decision(w, mirror, line, buy_qty="220", required_date=date(2027, 1, 4))
        top_up = w.board_row(mirror, qty="38")
        top_up.supply_decision_id = decision.id
        w.db.flush()
        capture = _Capture()
        data = sheet([
            (order.so_number, w.product.product_code, 91, date(2027, 1, 4),
             w.warehouse.warehouse_code, ""),
            (order.so_number, w.product.product_code, 91, date(2027, 2, 4),
             w.warehouse.warehouse_code, ""),
        ])

        result = _apply(w, data, outcome=capture, file_name="journey.xlsx")

        assert result["rows_raised"] == 0, result
        rows = [r for r in w.rows() if str(r.so_line_id) == str(mirror.id)]
        assert len(rows) == 1, [(str(r.qty), r.delivery_date) for r in rows]
        assert str(rows[0].id) == str(top_up.id)
        codes = capture.codes()
        assert codes.count(oc.ALREADY_RAISED) == 2, capture.calls
        assert oc.TOP_UP_SUM_MISMATCH not in codes, capture.calls


@pytest.mark.parametrize("shape", ["qty_equal", "qty_differs"])
def test_snapshot_without_required_date_proposes_no_date_change(shape):
    """AC-RB-34. A decision snapshot with no `required_date` proposes no date change:
    quantity equal to the sheet raises PLAIN; quantity different settles the quantity and
    keeps the sheet's own date. Today the qty-equal arm writes a false `Was 280 on ...` with
    `changed_at` even though nothing about the date changed."""
    with world() as w:
        order = w.order()
        line = w.line(order, qty_ordered="500", required_date=date(2027, 3, 1))
        mirror = _adopted_mirror(w, order, line)
        sheet_date = date(2026, 6, 1)
        buy_qty = "182" if shape == "qty_equal" else "280"
        _decision(w, mirror, line, buy_qty=buy_qty, required_date=None)
        data = sheet([
            (order.so_number, w.product.product_code, 182, sheet_date,
             w.warehouse.warehouse_code, ""),
        ])

        _apply(w, data, file_name="journey.xlsx")

        row = w.one_row()
        if shape == "qty_equal":
            assert Decimal(str(row.qty)) == Decimal("182")
            assert row.delivery_date == sheet_date
            assert row.previous_qty is None, _row_snapshot(row)
            assert row.changed_at is None, _row_snapshot(row)
        else:
            assert Decimal(str(row.qty)) == Decimal("280")
            assert row.delivery_date == sheet_date
            assert Decimal(str(row.previous_qty)) == Decimal("182")


def test_reserve_and_order_row_is_the_lines_own_row():
    """AC-RB-35 (R7 refined). The line's own row means a live ORDER, ORDER BACK or RESERVE
    AND ORDER row - a line whose only live row is RESERVE AND ORDER reads `already_raised`,
    exactly as an ORDER row would, and the top-up sum counts it when it carries the active
    decision's own id."""
    with world() as w:
        order = w.order()
        line = w.line(order, qty_ordered="182", required_date=date(2026, 6, 1))
        mirror = _adopted_mirror(w, order, line)
        reserve_row = w.board_row(mirror, qty="182")
        reserve_row.verb = IV_RESERVE_AND_ORDER
        reserve_row.delivery_date = date(2026, 6, 1)
        w.db.flush()
        capture = _Capture()
        data = sheet([
            (order.so_number, w.product.product_code, 182, date(2026, 6, 1),
             w.warehouse.warehouse_code, ""),
        ])

        result = _apply(w, data, outcome=capture, file_name="journey.xlsx")

        assert result["rows_raised"] == 0, result
        assert capture.codes() == [oc.ALREADY_RAISED], capture.calls
        rows = [r for r in w.rows() if str(r.so_line_id) == str(mirror.id)]
        assert len(rows) == 1, rows
        assert str(rows[0].id) == str(reserve_row.id)

    with world() as w:
        # Second arm: a RESERVE AND ORDER row carrying the active decision's own id, on a
        # top-up line - it counts in the sum exactly as an ORDER row would.
        order = w.order()
        line = w.line(order, qty_ordered="500", required_date=date(2027, 1, 4))
        mirror = _adopted_mirror(w, order, line)
        decision = _decision(w, mirror, line, buy_qty="220", required_date=date(2027, 1, 4))
        reserve_row = w.board_row(mirror, qty="38")
        reserve_row.verb = IV_RESERVE_AND_ORDER
        reserve_row.supply_decision_id = decision.id
        w.db.flush()
        ref = _ref()
        line.source_ref = ref
        po, po_line = w.po_line(qty_ordered="182")
        po_line.from_so_line_ref = ref
        w.db.flush()
        data = sheet([
            (order.so_number, w.product.product_code, 182, date(2027, 1, 4),
             w.warehouse.warehouse_code, ""),
        ])

        _apply(w, data, file_name="journey.xlsx")

        rows = [r for r in w.rows() if str(r.so_line_id) == str(mirror.id)]
        assert len(rows) == 2, [(r.verb, str(r.qty)) for r in rows]
        plain = next(r for r in rows if str(r.id) != str(reserve_row.id))
        assert Decimal(str(plain.qty)) == Decimal("182")
        assert plain.previous_qty is None


def test_used_row_is_not_counted_in_top_up_sum():
    """AC-RB-36. A used row is never counted in the top-up sum, even when it carries the
    active decision's own `supply_decision_id` (deliberately set here, so the guard cannot
    pass by that column being absent): only the genuine top-up ORDER row's 38 counts, and
    182 + 38 = 220 raises the sheet row plain."""
    with world() as w:
        order = w.order()
        line = w.line(order, qty_ordered="500", required_date=date(2027, 1, 4))
        mirror = _adopted_mirror(w, order, line)
        decision = _decision(w, mirror, line, buy_qty="220", required_date=date(2027, 1, 4))
        # A genuine USED row (`redirected_to_pool = true`), not `_used_sibling`'s own shape
        # (the FRESH row a used row sits BESIDE) - this is the row AC-RB-36 says must be
        # excluded from the sum.
        used = w.board_row(mirror, qty="50")
        used.redirected_to_pool = True
        used.delivery_date = date(2026, 1, 1)
        used.previous_qty = Decimal("50")
        used.previous_delivery_date = date(2026, 1, 1)
        used.note = "Replaces 50 used; SPO received"
        used.supply_decision_id = decision.id
        top_up = w.board_row(mirror, qty="38")
        top_up.supply_decision_id = decision.id
        w.db.flush()
        ref = _ref()
        line.source_ref = ref
        po, po_line = w.po_line(qty_ordered="182")
        po_line.from_so_line_ref = ref
        w.db.flush()
        data = sheet([
            (order.so_number, w.product.product_code, 182, date(2027, 1, 4),
             w.warehouse.warehouse_code, ""),
        ])

        _apply(w, data, file_name="journey.xlsx")

        rows = [r for r in w.rows() if str(r.so_line_id) == str(mirror.id)]
        assert len(rows) == 3, [(r.verb, r.redirected_to_pool, str(r.qty)) for r in rows]
        plain = next(
            r for r in rows if str(r.id) not in (str(used.id), str(top_up.id))
        )
        assert Decimal(str(plain.qty)) == Decimal("182")
        assert plain.previous_qty is None


@pytest.mark.parametrize("bad_field", ["required_date", "buy_qty"])
def test_malformed_snapshot_never_aborts_the_upload(bad_field):
    """AC-RB-37. A malformed snapshot entry (unreadable `buy_qty` or `required_date`) never
    aborts the upload: today the whole `apply()` call raises, taking every other row in the
    same sheet down with it. That sheet row is raised plain instead, and a second, healthy
    row in the same upload is processed normally."""
    with world() as w:
        order = w.order()
        bad_line = w.line(order, qty_ordered="182", required_date=date(2026, 6, 1))
        healthy_product = w.product_row()
        healthy_line = w.line(
            order, product=healthy_product, qty_ordered="50", required_date=date(2026, 7, 1),
        )
        ProjectSOAdoptionService(w.db).adopt(str(order.id), w.actor)
        bad_mirror = w.mirror_of(bad_line)
        healthy_mirror = w.mirror_of(healthy_line)
        buy_qty = "abc" if bad_field == "buy_qty" else "280"
        required_date = "not-a-date" if bad_field == "required_date" else "2027-03-01"
        snapshot = {
            "line_no": 1,
            "project_line_id": str(bad_mirror.id),
            "core_line_id": str(bad_line.id),
            "item_code": w.product.product_code,
            "location": w.warehouse.warehouse_code,
            "required_date": required_date,
            "open_qty": "0",
            "timely_spo_qty": "0",
            "timely_spo_refs": [],
            "reserve_qty": "0",
            "borrow_qty": "0",
            "buy_qty": buy_qty,
            "components": [],
            "proposed_components": [],
        }
        decision = SOSupplyDecision(
            id=_uid(), company_id=w.company_id,
            project_sales_order_id=str(bad_mirror.project_sales_order_id),
            revision_no=1, state=DECISION_ACTIVE, line_snapshots=[snapshot],
        )
        w.db.add(decision)
        w.db.flush()
        data = sheet([
            (order.so_number, w.product.product_code, 182, date(2026, 6, 1),
             w.warehouse.warehouse_code, ""),
            (order.so_number, healthy_product.product_code, 50, date(2026, 7, 1),
             w.warehouse.warehouse_code, ""),
        ])

        result = _apply(w, data, file_name="journey.xlsx")

        assert result["rows_raised"] == 2, result
        bad_row = next(r for r in w.rows() if str(r.so_line_id) == str(bad_mirror.id))
        assert Decimal(str(bad_row.qty)) == Decimal("182")
        assert bad_row.previous_qty is None
        healthy_row = next(
            r for r in w.rows() if str(r.so_line_id) == str(healthy_mirror.id)
        )
        assert Decimal(str(healthy_row.qty)) == Decimal("50")


def test_rollback_company_refusal_covers_kept_rows():
    """AC-RB-39. The more-than-one-company refusal is evaluated over EVERY stamped row,
    kept ones included, not only the removable ones: a second company whose ONLY stamped
    row is a KEPT one (a planning trait set directly on it) still trips the refusal, and
    without `--all-companies` nothing of that company is deleted, returned or counted as
    kept. Mirrors `test_oi_sheet_pairing_repair.test_ac_r_20_rollback_refuses_a_run_
    spanning_companies`'s own assertion shape - the only difference is that the far
    company's row is KEPT rather than removable."""
    with blank_session() as db:
        srt = db.execute(sa.text("select id from companies where code = 'SRT'")).scalar()
        other = _uid()
        db.execute(
            sa.text(
                "insert into companies (id, name, code, is_active) "
                "values (:id, :name, :code, true)"
            ),
            {"id": other, "name": f"{MARKER} other company", "code": f"ZZTC{_n():04d}"},
        )

        with company_scope(db, frozenset({other})):
            far = World(db, other)
            far_order = far.order()
            far.line(far_order, qty_ordered="50")
            far_result = importer.apply(
                db,
                sheet([
                    (far_order.so_number, far.product.product_code, 30, D_OCT,
                     far.warehouse.warehouse_code, ""),
                ]),
                actor=far.actor,
                file_name="a.xlsx",
            )
            assert far_result["rows_raised"] == 1, far_result
            far_row = far.one_row()
            far_row.redirected_to_pool = True
            db.flush()
            far_row_id = str(far_row.id)

        with company_scope(db, frozenset({srt})):
            near = World(db, srt)
            near_order = near.order()
            near.line(near_order, qty_ordered="50")
            near_result = importer.apply(
                db,
                sheet([
                    (near_order.so_number, near.product.product_code, 30, D_OCT,
                     near.warehouse.warehouse_code, ""),
                ]),
                actor=near.actor,
                file_name="a.xlsx",
            )
            assert near_result["rows_raised"] == 1, near_result

        stamp = f"{importer._MIGRATION_STAMP} a.xlsx"
        with company_scope(db, None):
            def stamped() -> int:
                return (
                    db.query(OrderInquiryRow)
                    .filter(OrderInquiryRow.note.startswith(stamp, autoescape=True))
                    .count()
                )

            assert stamped() == 2, "the premise: one stamp, two companies, one kept"

            with pytest.raises(ValueError):
                _rollback().run(db, file_name="a.xlsx", apply=True)

            assert stamped() == 2, "the refused run deleted rows anyway"
            assert db.query(OrderInquiryRow).filter(
                OrderInquiryRow.id == far_row_id
            ).count() == 1, "the refused run must not have touched the far company's row"

            counts = _rollback().run(
                db, file_name="a.xlsx", apply=True, all_companies=True
            )

            assert counts["rows"] == 1, counts
            assert db.query(OrderInquiryRow).filter(
                OrderInquiryRow.id == far_row_id
            ).count() == 1, "the far company's kept row must survive even with --all-companies"
            kept_rows = counts.get("kept_rows") or []
            assert len(kept_rows) == 1, kept_rows
            assert stamped() == 1


def test_preview_names_rows_to_look_at_by_hand():
    """AC-RB-41. The upload preview's "already carries an order inquiry" warning counts
    `no_used_delivery_match` and `top_up_sum_mismatch` rows on their OWN line of text,
    separate from the plain "left alone" count - two sheet rows that need a person's eye
    read as two different things from "correctly skipped".

    Substring chosen for the coder to build to: "could not be matched automatically".
    """
    with world() as w:
        # Line A: the AC-RB-3 shape - a `Replaces N used` fresh row, sheet row matching
        # neither its quantity nor its date.
        order_a = w.order()
        line_a = w.line(order_a, qty_ordered="220", required_date=date(2027, 3, 1))
        mirror_a = _adopted_mirror(w, order_a, line_a)
        _used_sibling(
            w, mirror_a, qty="220", delivery_date=date(2027, 3, 1),
            previous_qty="182", previous_delivery_date=date(2026, 6, 1),
            note="Replaces 182 used; SPO-A received",
        )
        # Line B: the AC-RB-27 shape - a top-up ORDER row under the active decision, sheet
        # row whose sum with the top-up does not equal the decision's buy_qty.
        product_b = w.product_row()
        order_b = w.order()
        line_b = w.line(
            order_b, product=product_b, qty_ordered="500", required_date=date(2027, 1, 4),
        )
        mirror_b = _adopted_mirror(w, order_b, line_b)
        decision_b = _decision(
            w, mirror_b, line_b, buy_qty="230", required_date=date(2027, 1, 4),
        )
        top_up = w.board_row(mirror_b, qty="38")
        top_up.supply_decision_id = decision_b.id
        w.db.flush()

        data = sheet([
            (order_a.so_number, w.product.product_code, 183, date(2026, 6, 1),
             w.warehouse.warehouse_code, ""),
            (order_b.so_number, product_b.product_code, 182, date(2027, 1, 4),
             w.warehouse.warehouse_code, ""),
        ])

        result = importer.validate(w.db, data)

        substring = "could not be matched automatically"
        matching = [
            line for line in result["warnings"] if line and substring in line
        ]
        assert len(matching) == 1, result["warnings"]
        assert "2" in matching[0], matching[0]
