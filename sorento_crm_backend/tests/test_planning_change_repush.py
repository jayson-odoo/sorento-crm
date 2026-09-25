"""Issue #1240, `PLAN-esb-change-row-refresh.md` / `esb-change-row-refresh-acceptance-
criteria.md`. Tester-first, RED before the coder's slice lands - no implementation exists
yet for S1 (build_batch retiring a stale row) or S2 (mirror follows core).

SO419122 measured cause: an AutoCount re-push moves a line the FIRST push's `added` row
already described, but the second push's own change fails the per-line held-or-inquiry
gate (the line is still undecided) - `_build_row` returns `None` and the loop drops the
entry BEFORE ever looking at the older row, so the stale `added` row keeps describing the
FIRST date forever. Postgres only (`tests/_pg_fixture.py`), every FK seeded here or by the
reused fixtures below - never a borrowed row.

T1/T2/T3/T6 drive `planning_change_service.build_batch` directly with hand-built `Diff`s -
the row logic under test lives entirely inside that function, and this is the same seam
`tests/test_planning_changes.py` and `tests/scm/test_ingest_planning_diff_line_identity.py`
already use for it. A mirror `ProjectSalesOrderLine` for the line push 1 ADDS is seeded
BEFORE that push, matching front-planning reconciliation running ahead of the ESB
(`project_so_reconciliation_service.py`'s own docstring: project lines commonly exist
before the matching core line does) - `build_batch`'s own `entries` construction reads
`project_lines_by_core` for every change it can, so a pre-existing mirror is what lets a
later push correlate back to the first one at all.

T4 (mirror follows core, ESB path) and T5 (same, manual edit) need the REAL write path -
`DocumentIngestService` sales-order apply and `SalesOrderService.update` - reusing
`tests/test_ingest_documents.py`'s `env` fixture and `tests/scm/test_planning_change_diff_
parity.py`'s `api` fixture respectively, exactly as the tester brief names them.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.orm import Session as OrmSession

from app.models.order import SalesOrderLine
from app.models.planning_change import PlanningChangeRow
from app.models.project_so import (
    IV_ORDER,
    SO_STATUS_ADOPTED,
    OrderInquiry,
    OrderInquiryRow,
    ProjectSalesOrder,
    ProjectSalesOrderLine,
)
from app.schemas.scm_orders import SalesOrderUpdate
from app.services import planning_change_service
from app.services.scm.outstanding_diff import ADDED, DATE_MOVED, PRODUCT_CHANGED, Change, Diff, Line
from app.services.scm.sales_order_service import SalesOrderService

from tests.scm.test_planning_change_diff_parity import (  # noqa: F401 - fixtures reused
    _core_line,
    _freeze_with_a_full_buy,
    _linked_line,
    _product,
    _project_line,
    _rows_for,
    api,
)
from tests.test_ingest_documents import INGEST_SO, _so_line, _so_record, env  # noqa: F401

MARKER = "zzt-esbrepush"

# D1: where push 1 (or the first move) leaves the line. D2: where push 2 moves it to.
D1 = date(2027, 1, 15)
D2 = date(2026, 12, 1)


def _added_change(so_number: str, item_code: str, location: str, *, qty, required_date) -> Change:
    return Change(
        ADDED, so_number, item_code, location,
        before=None,
        after=Line(
            doc_number=so_number, item_code=item_code, location=location,
            qty=float(qty), required_date=required_date, row_ref="1",
        ),
    )


def _moved_change(so_number: str, item_code: str, location: str, core_line_id, *,
                   old_date, new_date, qty=10.0) -> Change:
    return Change(
        DATE_MOVED, so_number, item_code, location,
        before=Line(
            doc_number=so_number, item_code=item_code, location=location,
            qty=qty, required_date=old_date, row_ref=str(core_line_id),
        ),
        after=Line(
            doc_number=so_number, item_code=item_code, location=location,
            qty=qty, required_date=new_date, row_ref=str(core_line_id),
        ),
    )


def _product_changed(so_number: str, old_item_code: str, new_item_code: str, location: str,
                      core_line_id, *, qty=10.0, required_date) -> Change:
    """A `PRODUCT_CHANGED` change on the SAME core line - same qty, same date, only the
    item code differs. `Change.item_code` is the AFTER side (`_from_to`'s own comment:
    "Change.item_code is built from the after side")."""
    return Change(
        PRODUCT_CHANGED, so_number, new_item_code, location,
        before=Line(
            doc_number=so_number, item_code=old_item_code, location=location,
            qty=qty, required_date=required_date, row_ref=str(core_line_id),
        ),
        after=Line(
            doc_number=so_number, item_code=new_item_code, location=location,
            qty=qty, required_date=required_date, row_ref=str(core_line_id),
        ),
    )


# --------------------------------------------------------------------------- #
# S1: build_batch retires a stale row a later push's own change cannot describe
# --------------------------------------------------------------------------- #


def test_repush_supersedes_stale_added_row_when_line_moves_again(api):
    """T1 (AC-1) + AC-2. Push 1 adds a new line to an order that already carries a held
    line - the order-level gate `_build_row` asks of an ADDED change - and keeps one
    pending `added` row describing D1. Push 2 moves the SAME line while it is still
    undecided: the per-line gate refuses a row for D2, and the fix must retire the D1 row
    rather than leave it pending forever.
    """
    world, project = api
    db = world.db
    core_so, held_core_line, held_product, order, held_mirror = _linked_line(
        world, project, qty_ordered=72,
    )
    _freeze_with_a_full_buy(db, world, order, held_mirror)

    new_product = _product(db)
    new_core_line = _core_line(
        db, core_so, new_product, world.own_wh, qty_ordered="10", required_date=D1,
    )
    # A mirror line for the line push 1 is about to ADD already exists, matching
    # front-planning reconciliation running ahead of the ESB (see module docstring).
    _project_line(db, order, line_no=2, product=new_product, core_line=new_core_line)
    db.commit()

    push1_change = _added_change(
        core_so.so_number, new_product.product_code, world.own_wh.warehouse_code,
        qty=10, required_date=D1,
    )
    batch1 = planning_change_service.build_batch(
        db, Diff(scope_documents=(core_so.so_number,), changes=[push1_change]),
        applied_line_ids={id(push1_change): str(new_core_line.id)},
        order_ids={core_so.so_number: str(core_so.id)},
        actor=world.actor, import_job_id=None, file_name="push1.xlsx",
    )
    db.commit()
    assert batch1 is not None, "AC-1: an order with a held line must keep the added row"
    rows_after_push1 = [
        r for r in _rows_for(db, batch1.id) if r.item_code == new_product.product_code
    ]
    assert len(rows_after_push1) == 1, [r.kind for r in rows_after_push1]
    added_row = rows_after_push1[0]
    assert added_row.kind == "added"
    assert added_row.to_json["required_date"] == D1.isoformat()
    assert added_row.applied_state == "pending"

    # Write-first: production always writes the book before building the batch off it.
    new_core_line.required_date = D2
    db.flush()
    push2_change = _moved_change(
        core_so.so_number, new_product.product_code, world.own_wh.warehouse_code,
        new_core_line.id, old_date=D1, new_date=D2,
    )
    planning_change_service.build_batch(
        db, Diff(scope_documents=(core_so.so_number,), changes=[push2_change]),
        applied_line_ids={id(push2_change): str(new_core_line.id)},
        order_ids={core_so.so_number: str(core_so.id)},
        actor=world.actor, import_job_id=None, file_name="push2.xlsx",
    )
    db.commit()

    db.expire_all()
    stale = db.get(PlanningChangeRow, added_row.id)
    assert stale.applied_state == "superseded", (
        "AC-2: a re-push that moves an undecided line again must retire the older "
        "`added` row instead of leaving it pending at the stale date"
    )
    assert stale.applied_reason == "Line changed again; the row no longer describes it"

    still_for_l = [
        r for r in _rows_for(db, batch1.id) if r.item_code == new_product.product_code
    ]
    assert len(still_for_l) == 1, (
        "AC-2: an undecided line's move raises no NEW row - only the retirement of the old one"
    )

    db.refresh(new_core_line)
    assert new_core_line.required_date == D2


def test_repush_with_identical_facts_leaves_the_added_row_pending(api):
    """T2 (AC-3): a re-push that changes nothing about the line must not disturb the row
    a still-open batch already carries for it - only a push that actually differs (kind,
    qty or date) may retire the older row. Constructed as a `DATE_MOVED` Change whose two
    sides are equal, bypassing `diff_lines`'s own separate "unchanged" filter on purpose,
    so this exercises the fix's OWN idempotency guard rather than that unrelated exit.
    """
    world, project = api
    db = world.db
    core_so, held_core_line, held_product, order, held_mirror = _linked_line(
        world, project, qty_ordered=72,
    )
    _freeze_with_a_full_buy(db, world, order, held_mirror)

    new_product = _product(db)
    new_core_line = _core_line(
        db, core_so, new_product, world.own_wh, qty_ordered="10", required_date=D1,
    )
    _project_line(db, order, line_no=2, product=new_product, core_line=new_core_line)
    db.commit()

    push1_change = _added_change(
        core_so.so_number, new_product.product_code, world.own_wh.warehouse_code,
        qty=10, required_date=D1,
    )
    batch1 = planning_change_service.build_batch(
        db, Diff(scope_documents=(core_so.so_number,), changes=[push1_change]),
        applied_line_ids={id(push1_change): str(new_core_line.id)},
        order_ids={core_so.so_number: str(core_so.id)},
        actor=world.actor, import_job_id=None, file_name="push1.xlsx",
    )
    db.commit()
    added_row_id = [
        r for r in _rows_for(db, batch1.id) if r.item_code == new_product.product_code
    ][0].id

    identical_change = _moved_change(
        core_so.so_number, new_product.product_code, world.own_wh.warehouse_code,
        new_core_line.id, old_date=D1, new_date=D1,
    )
    planning_change_service.build_batch(
        db, Diff(scope_documents=(core_so.so_number,), changes=[identical_change]),
        applied_line_ids={id(identical_change): str(new_core_line.id)},
        order_ids={core_so.so_number: str(core_so.id)},
        actor=world.actor, import_job_id=None, file_name="push2.xlsx",
    )
    db.commit()

    db.expire_all()
    row = db.get(PlanningChangeRow, added_row_id)
    assert row.applied_state == "pending", (
        "AC-3: identical facts on the second push must leave the row untouched"
    )
    assert row.applied_reason is None


def test_repush_moving_an_inquired_line_still_replaces_in_place(api):
    """T3 (AC-4), a regression pin: an INQUIRED line already goes through the EXISTING
    replace-in-place mechanism (`build_batch`, the `if older is not None` branch reached
    when `_build_row` DOES return a row) - a re-push's row replaces the older one in place
    with "Replaced by a later change". Nothing in this slice may change that.
    """
    world, project = api
    db = world.db
    core_so, core_line, product, order, mirror_line = _linked_line(world, project, qty_ordered=72)
    db.commit()

    inquiry = OrderInquiry(
        id=str(uuid.uuid4()), company_id=world.company_id, project_sales_order_id=order.id,
    )
    db.add(inquiry)
    db.flush()
    db.add(OrderInquiryRow(
        id=str(uuid.uuid4()), company_id=world.company_id, order_inquiry_id=inquiry.id,
        so_line_id=mirror_line.id, item_code=product.product_code, qty=Decimal("72"),
        verb=IV_ORDER,
    ))
    db.commit()

    first_move = _moved_change(
        core_so.so_number, product.product_code, world.own_wh.warehouse_code,
        core_line.id, old_date=date(2026, 8, 20), new_date=D1, qty=72.0,
    )
    batch1 = planning_change_service.build_batch(
        db, Diff(scope_documents=(core_so.so_number,), changes=[first_move]),
        applied_line_ids={id(first_move): str(core_line.id)},
        order_ids={core_so.so_number: str(core_so.id)},
        actor=world.actor, import_job_id=None, file_name="push1.xlsx",
    )
    db.commit()
    assert batch1 is not None
    first_row = _rows_for(db, batch1.id)[0]
    assert first_row.kind == "delayed"
    assert first_row.applied_state == "pending"

    core_line.required_date = D2
    db.flush()
    second_move = _moved_change(
        core_so.so_number, product.product_code, world.own_wh.warehouse_code,
        core_line.id, old_date=D1, new_date=D2, qty=72.0,
    )
    planning_change_service.build_batch(
        db, Diff(scope_documents=(core_so.so_number,), changes=[second_move]),
        applied_line_ids={id(second_move): str(core_line.id)},
        order_ids={core_so.so_number: str(core_so.id)},
        actor=world.actor, import_job_id=None, file_name="push2.xlsx",
    )
    db.commit()

    db.expire_all()
    stale = db.get(PlanningChangeRow, first_row.id)
    assert stale.applied_state == "superseded"
    assert stale.applied_reason == "Replaced by a later change"
    rows = _rows_for(db, batch1.id)
    assert len(rows) == 2, [r.kind for r in rows]
    new_row = next(r for r in rows if r.id != first_row.id)
    # D2 sits BEFORE D1 (the SO419122 book moved lines both earlier and later), so this
    # second move reads "advanced" rather than "delayed" - the kind label is not what this
    # regression pin is about; the replace-in-place mechanics are.
    assert new_row.kind == "advanced"
    assert new_row.applied_state == "pending"
    assert new_row.to_json["required_date"] == D2.isoformat()


def test_repush_supersedes_via_the_core_line_id_fallback_when_push_1_had_no_mirror(api):
    """Reviewer coverage residual (round 3): the SO419122 shape at its most literal - push 1
    ADDS a line with NO mirror yet at all, so the `added` row lands with `project_line_id`
    NULL (`build_batch`'s ADDED branch never resolves one). The mirror is only created
    AFTERWARDS, between push 1 and push 2 (the ordinary front-planning reconciliation
    timing). Push 2 then moves the line: the per-line gate fails, and `older` can only be
    found through the `core_line_id` fallback (`open_pending_by_core_by_batch`,
    `planning_change_service.py` ~1126) - the `project_line_id` lookup alone would miss it,
    since the OLDER row never had one.
    """
    world, project = api
    db = world.db
    core_so, held_core_line, held_product, order, held_mirror = _linked_line(
        world, project, qty_ordered=72,
    )
    _freeze_with_a_full_buy(db, world, order, held_mirror)

    new_product = _product(db)
    new_core_line = _core_line(
        db, core_so, new_product, world.own_wh, qty_ordered="10", required_date=D1,
    )
    # NO mirror yet - push 1 ADDS a line the project side has never heard of.
    db.commit()

    push1_change = _added_change(
        core_so.so_number, new_product.product_code, world.own_wh.warehouse_code,
        qty=10, required_date=D1,
    )
    batch1 = planning_change_service.build_batch(
        db, Diff(scope_documents=(core_so.so_number,), changes=[push1_change]),
        applied_line_ids={id(push1_change): str(new_core_line.id)},
        order_ids={core_so.so_number: str(core_so.id)},
        actor=world.actor, import_job_id=None, file_name="push1.xlsx",
    )
    db.commit()
    assert batch1 is not None
    added_row = [
        r for r in _rows_for(db, batch1.id) if r.item_code == new_product.product_code
    ][0]
    assert added_row.project_line_id is None, (
        "the premise: push 1 has no mirror to resolve, so the row is stored with no "
        "project_line_id at all - only core_line_id can ever find it again"
    )

    # Reconciliation runs between the two pushes and gives the line its mirror.
    _project_line(db, order, line_no=2, product=new_product, core_line=new_core_line)
    db.commit()

    new_core_line.required_date = D2
    db.flush()
    push2_change = _moved_change(
        core_so.so_number, new_product.product_code, world.own_wh.warehouse_code,
        new_core_line.id, old_date=D1, new_date=D2,
    )
    planning_change_service.build_batch(
        db, Diff(scope_documents=(core_so.so_number,), changes=[push2_change]),
        applied_line_ids={id(push2_change): str(new_core_line.id)},
        order_ids={core_so.so_number: str(core_so.id)},
        actor=world.actor, import_job_id=None, file_name="push2.xlsx",
    )
    db.commit()

    db.expire_all()
    stale = db.get(PlanningChangeRow, added_row.id)
    assert stale.applied_state == "superseded", (
        "the core_line_id fallback must find the older row even though it never carried "
        "a project_line_id"
    )
    assert stale.applied_reason == "Line changed again; the row no longer describes it"
    still_for_l = [
        r for r in _rows_for(db, batch1.id) if r.item_code == new_product.product_code
    ]
    assert len(still_for_l) == 1


def test_repush_with_a_product_change_supersedes_the_stale_added_row(api):
    """Reviewer coverage residual (round 3): push 2 changes the PRODUCT on the same core
    line (same qty, same date) rather than the date - `_entry_differs_from_older_row`
    treats `PRODUCT_CHANGED` as always different from what the older row describes
    (review round 1, S6), so this must supersede exactly like a date move does.
    """
    world, project = api
    db = world.db
    core_so, held_core_line, held_product, order, held_mirror = _linked_line(
        world, project, qty_ordered=72,
    )
    _freeze_with_a_full_buy(db, world, order, held_mirror)

    old_product = _product(db)
    new_core_line = _core_line(
        db, core_so, old_product, world.own_wh, qty_ordered="10", required_date=D1,
    )
    _project_line(db, order, line_no=2, product=old_product, core_line=new_core_line)
    db.commit()

    push1_change = _added_change(
        core_so.so_number, old_product.product_code, world.own_wh.warehouse_code,
        qty=10, required_date=D1,
    )
    batch1 = planning_change_service.build_batch(
        db, Diff(scope_documents=(core_so.so_number,), changes=[push1_change]),
        applied_line_ids={id(push1_change): str(new_core_line.id)},
        order_ids={core_so.so_number: str(core_so.id)},
        actor=world.actor, import_job_id=None, file_name="push1.xlsx",
    )
    db.commit()
    assert batch1 is not None
    added_row = [
        r for r in _rows_for(db, batch1.id) if r.item_code == old_product.product_code
    ][0]
    assert added_row.applied_state == "pending"

    # Write-first: the book renames this line's product, same qty, same date.
    new_product = _product(db)
    new_core_line.product_id = new_product.id
    db.flush()
    push2_change = _product_changed(
        core_so.so_number, old_product.product_code, new_product.product_code,
        world.own_wh.warehouse_code, new_core_line.id, qty=10.0, required_date=D1,
    )
    planning_change_service.build_batch(
        db, Diff(scope_documents=(core_so.so_number,), changes=[push2_change]),
        applied_line_ids={id(push2_change): str(new_core_line.id)},
        order_ids={core_so.so_number: str(core_so.id)},
        actor=world.actor, import_job_id=None, file_name="push2.xlsx",
    )
    db.commit()

    db.expire_all()
    stale = db.get(PlanningChangeRow, added_row.id)
    assert stale.applied_state == "superseded", (
        "a PRODUCT_CHANGED re-push must retire the older row too, even with the same qty "
        "and date - `_entry_differs_from_older_row` treats a product swap as always "
        "different from what the older row describes"
    )
    assert stale.applied_reason == "Line changed again; the row no longer describes it"


def test_apply_after_a_gate_failed_repush_raises_no_oi_for_the_confirmed_stale_row(api):
    """T6 (AC-11), made real (reviewer S5): a row staying `pending` with no decision ever
    reaches `apply` in the first place - `_apply_one_order`'s own `accepted` filter already
    skips a row nobody confirmed, whatever its `applied_state`, so that alone proves nothing
    about the S1 fix. The board's real Confirm flow pre-marks every changed row and posts a
    decision for it (`set_row_decision`) BEFORE Apply ever runs - so this confirms the
    `added` row from push 1 exactly like a planner pressing Confirm would, THEN pushes the
    move that fails the per-line gate. Apply must still raise no order-inquiry row at the
    stale D1 date: the S1 supersede is what keeps a CONFIRMED-but-stale row out of
    `_apply_one_order`'s `accepted` list (it filters on `applied_state == PENDING`, not on
    whether a decision was ever taken).
    """
    world, project = api
    db = world.db
    core_so, held_core_line, held_product, order, held_mirror = _linked_line(
        world, project, qty_ordered=72,
    )
    _freeze_with_a_full_buy(db, world, order, held_mirror)

    new_product = _product(db)
    new_core_line = _core_line(
        db, core_so, new_product, world.own_wh, qty_ordered="10", required_date=D1,
    )
    new_mirror = _project_line(db, order, line_no=2, product=new_product, core_line=new_core_line)
    db.commit()

    push1_change = _added_change(
        core_so.so_number, new_product.product_code, world.own_wh.warehouse_code,
        qty=10, required_date=D1,
    )
    batch1 = planning_change_service.build_batch(
        db, Diff(scope_documents=(core_so.so_number,), changes=[push1_change]),
        applied_line_ids={id(push1_change): str(new_core_line.id)},
        order_ids={core_so.so_number: str(core_so.id)},
        actor=world.actor, import_job_id=None, file_name="push1.xlsx",
    )
    db.commit()
    assert batch1 is not None
    added_row = [
        r for r in _rows_for(db, batch1.id) if r.item_code == new_product.product_code
    ][0]

    # The planner presses Confirm on the still-open batch before push 2 ever lands - the
    # same write `set_row_decision` makes for a real board Confirm.
    planning_change_service.set_row_decision(db, batch1.id, added_row.id, "confirm")
    db.commit()
    db.expire_all()
    confirmed_row = db.get(PlanningChangeRow, added_row.id)
    assert confirmed_row.decision == "confirm"
    assert confirmed_row.applied_state == "pending"

    new_core_line.required_date = D2
    db.flush()
    push2_change = _moved_change(
        core_so.so_number, new_product.product_code, world.own_wh.warehouse_code,
        new_core_line.id, old_date=D1, new_date=D2,
    )
    planning_change_service.build_batch(
        db, Diff(scope_documents=(core_so.so_number,), changes=[push2_change]),
        applied_line_ids={id(push2_change): str(new_core_line.id)},
        order_ids={core_so.so_number: str(core_so.id)},
        actor=world.actor, import_job_id=None, file_name="push2.xlsx",
    )
    db.commit()

    db.expire_all()
    stale = db.get(PlanningChangeRow, added_row.id)
    assert stale.applied_state == "superseded"
    # The decision itself is left alone - S1 retires the ROW, not the earlier decision on it.
    assert stale.decision == "confirm"

    before_count = (
        db.query(OrderInquiryRow).filter(OrderInquiryRow.so_line_id == new_mirror.id).count()
    )
    assert before_count == 0

    planning_change_service.apply(db, batch1.id, world.actor)
    db.commit()

    after_count = (
        db.query(OrderInquiryRow)
        .filter(OrderInquiryRow.so_line_id == new_mirror.id, OrderInquiryRow.delivery_date == D1)
        .count()
    )
    assert after_count == 0, (
        "AC-11: apply must raise no OI row at the stale date for L, even though the row was "
        "confirmed before the re-push superseded it"
    )


# --------------------------------------------------------------------------- #
# S2: the mirror line follows the core line's required_date / qty_ordered
# --------------------------------------------------------------------------- #


def test_mirror_follows_core_after_an_esb_repush(env):
    """T4 (AC-6): once the ESB moves a line's date/qty on a re-push, the mirror
    `projects.sales_order_lines` row front-planning reconciliation already pointed at this
    core line must read the SAME values - today it is written once, at creation, and
    never touched again (`PLAN-esb-change-row-refresh.md` S2).
    """
    keep = _so_line(env, qty_ordered=10, required_date=D1.isoformat())
    record = _so_record(env, lines=[keep])
    res = env.post(INGEST_SO, [record])
    assert res.json()["records"][0]["outcome"] == "created", res.text

    header = env.header("sales_orders", record["source_ref"])
    core_line = env.so_lines(header["id"])[0]
    product_id = env.refs.resolve(entity_type="products", source_ref=env.product_ref)

    order = ProjectSalesOrder(
        id=str(uuid.uuid4()), company_id=env.company_a, project_id=None,
        provisional_ref=f"{MARKER}-{uuid.uuid4().hex[:8]}", status=SO_STATUS_ADOPTED,
        so_id=str(header["id"]), autocount_doc_no=record["so_number"],
    )
    env.db.add(order)
    env.db.flush()
    mirror = ProjectSalesOrderLine(
        id=str(uuid.uuid4()), company_id=env.company_a, project_sales_order_id=order.id,
        core_sales_order_line_id=str(core_line["id"]), line_no=1, product_id=product_id,
        qty=Decimal("10"), delivery_date=D1,
    )
    env.db.add(mirror)
    env.db.commit()

    second = dict(record, lines=[dict(keep, qty_ordered=25, required_date=D2.isoformat())])
    res2 = env.post(INGEST_SO, [second])
    assert res2.json()["records"][0]["outcome"] == "updated", res2.text

    env.db.expire_all()
    refreshed = env.db.get(ProjectSalesOrderLine, mirror.id)
    core_after = env.so_lines(header["id"])[0]
    assert str(core_after["required_date"]) == D2.isoformat()
    assert refreshed.delivery_date == D2, (
        "AC-6: the mirror line's delivery_date must follow the core line's required_date"
    )
    assert refreshed.qty == Decimal(str(core_after["qty_ordered"])), (
        "AC-6: the mirror line's qty must follow the core line's qty_ordered"
    )


def test_manual_edit_updates_the_mirror_lines_required_date_and_qty(api):
    """T5 (AC-7): `SalesOrderService.update` (`sales_order_service.py`'s matched-line
    branch, ~1788-1804) writes `required_date`/`qty_ordered` on the CORE line only today -
    the mirror line the board actually reads drifts behind it on every manual edit.
    """
    world, project = api
    db = world.db
    core_so, core_line, product, order, mirror_line = _linked_line(world, project, qty_ordered=72)
    db.commit()

    SalesOrderService(db).update(
        core_so.id,
        SalesOrderUpdate(lines=[
            {"id": core_line.id, "sku": product.product_code, "qty_ordered": 40,
             "required_date": D2.isoformat()},
        ]),
        user_id=world.actor,
    )

    db.expire_all()
    refreshed = db.get(ProjectSalesOrderLine, mirror_line.id)
    assert refreshed.delivery_date == D2, (
        "AC-7: a manual SO edit that moves required_date must update the mirror too"
    )
    assert refreshed.qty == Decimal("40"), (
        "AC-7: a manual SO edit that changes qty_ordered must update the mirror too"
    )


def test_manual_edit_commits_the_supersede_even_when_the_second_call_keeps_no_new_row(api):
    """Reviewer coverage residual (round 3), `sales_order_service.py` ~1628: when
    `build_batch` keeps no new row (the moved line is still undecided, so `update()` returns
    `planning_change_batch: None`), the OLDER row's supersede - real work `build_batch` did
    on this session - still has to be committed rather than left for whatever the caller
    does next. `_propagate_planning_change`'s own `if batch is None: self.db.commit()`
    (right after the `build_batch` call) is what makes that stick.

    A plain `db.expire_all()` on the SAME session the write went through cannot tell a real
    commit apart from a mutation merely sitting on this session's own pending work - the
    session autoflushes, so even an uncommitted change already reads back as superseded
    through its own identity map. What actually distinguishes a commit under
    `blank_session`'s `join_transaction_mode="create_savepoint"` is whether it SURVIVES a
    later `rollback()` on the same session (a released savepoint does; a pending one is
    undone) - checked here two ways: an explicit `db.rollback()` right after `update()`
    returns, simulating an unrelated later failure in the same request, and then a
    genuinely SEPARATE `Session` on the same connection, bypassing `db`'s own identity map
    entirely, reading the row fresh.
    """
    world, project = api
    db = world.db
    core_so, held_core_line, held_product, order, held_mirror = _linked_line(
        world, project, qty_ordered=72,
    )
    _freeze_with_a_full_buy(db, world, order, held_mirror)

    new_product = _product(db)
    result1 = SalesOrderService(db).update(
        core_so.id,
        SalesOrderUpdate(lines=[
            {"id": held_core_line.id, "sku": held_product.product_code, "qty_ordered": 72},
            {"sku": new_product.product_code, "qty_ordered": 10,
             "required_date": D1.isoformat()},
        ]),
        user_id=world.actor,
    )
    batch1_envelope = result1["planning_change_batch"]
    assert batch1_envelope is not None
    batch1_id = batch1_envelope["id"]
    added_row = next(
        r for r in _rows_for(db, batch1_id) if r.item_code == new_product.product_code
    )
    assert added_row.kind == "added"
    added_row_id = added_row.id

    new_core_line_id = next(
        ln["id"] for ln in result1["lines"] if str(ln["id"]) != str(held_core_line.id)
    )
    # Reconciliation runs between the two edits and gives the new line its mirror - the
    # same premise the core-id-fallback test above uses, and needed for the SAME reason:
    # a non-ADDED entry with no mirror at all is dropped before `build_batch` ever asks
    # about an older row for it.
    new_core_line = db.query(SalesOrderLine).filter(SalesOrderLine.id == new_core_line_id).one()
    _project_line(db, order, line_no=2, product=new_product, core_line=new_core_line)
    db.commit()

    result2 = SalesOrderService(db).update(
        core_so.id,
        SalesOrderUpdate(lines=[
            {"id": held_core_line.id, "sku": held_product.product_code, "qty_ordered": 72},
            {"id": new_core_line_id, "sku": new_product.product_code, "qty_ordered": 10,
             "required_date": D2.isoformat()},
        ]),
        user_id=world.actor,
    )
    assert result2["planning_change_batch"] is None, (
        "the moved line is still undecided, so no NEW row is kept - only the older one's "
        "supersede, which is what this test is about"
    )

    # A later, unrelated failure elsewhere in the SAME request rolls the session back to
    # its last commit - exactly why the supersede has to be committed here rather than left
    # for whatever the caller writes next. If `_propagate_planning_change`'s own commit
    # were missing, this would undo the supersede along with it.
    db.rollback()

    # A genuinely SEPARATE session on the same connection, reading with plain SQL rather
    # than through the ORM: `CompanyScopedMixin`'s scope is stored ON THE SESSION INSTANCE
    # (`set_company_scope`/`company_scope`, `app/models/base.py`), so a brand-new `Session`
    # object carries none and an ORM query on it would see nothing at all, whatever the
    # database actually holds - raw SQL is what genuinely proves the DATABASE's own state,
    # independent of both sessions' identity maps and scoping.
    fresh = OrmSession(bind=db.connection())
    try:
        row = fresh.execute(
            text("select applied_state, applied_reason from planning_change_rows where id = :i"),
            {"i": added_row_id},
        ).mappings().first()
        assert row is not None, "the row must still exist after the rollback"
        assert row["applied_state"] == "superseded", (
            "the supersede from a gate-failed manual edit must be committed, not left "
            "pending for whatever the caller does next"
        )
        assert row["applied_reason"] == "Line changed again; the row no longer describes it"
    finally:
        fresh.close()
