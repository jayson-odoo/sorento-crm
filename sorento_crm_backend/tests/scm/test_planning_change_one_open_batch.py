"""Red tests for the SO400884 walk defects (captain's rulings R1-R4, 13 Sep browser
verification round). `documentation/plans/scm/scm-change-management-one-engine-acceptance-
criteria.md` is the contract; these are NOT from a UAC id list but from the captain's direct
rulings after a real end-to-end walk surfaced the gaps, so each test docstring restates the
ruling it pins rather than an AC id.

R1 (one open batch per order): `build_batch` mints a brand-new `PlanningChangeBatch` on
EVERY call today (`planning_change_service.py` ~938-943) - there is no lookup of an existing
unapplied pending batch for the order. `test_a_second_save_...appends_to_it` and
`test_a_second_change...supersedes` are red against that gap.

R2 (never carry a changed line): `_apply_one_order`'s `undecided_changed_line_ids`
(planning_change_service.py ~3878-3885) is built ONLY from `order_rows` - the rows of the
batch being applied - so a pending row sitting in a DIFFERENT, still-unapplied batch of the
same order is invisible to it. The line is then left unnamed in the confirm payload, and
`ProjectSupplyService._carried_lines`'s "the union is the server's" rule (project_supply_
service.py ~4196) carries its STALE snapshot into the new revision verbatim - UNLESS
`_carry_snapshot_has_drifted` (~4225) catches it first, which measured reading shows it does
NOT: it compares `core_line_id`, `open_qty` and `required_date` only, never `product_id`,
and `open_qty` is fed by `_open_of` (~374), which does not floor a `line_status="cancelled"`
core line to zero (see R2c below) - so neither a renamed product nor a cancelled line is
detected as drift today.

R2c is written directly against `_open_of` (AC-B01's own open-quantity primitive, the single
function the drift check and the board queue both read): a cancelled core line's
`qty_ordered - qty_delivered` is not floored to zero by `line_status`, which is the
measured root of both R2's carry-forward defect and the board's "Outstanding" figure not
reading zero for a cancelled line.

Postgres only (`tests/_pg_fixture.py` via the `api` fixture's own `blank_session`), every FK
seeded here, never a borrowed row.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.models.planning_change import PlanningChangeRow
from app.models.project_so import SOLineAllocation
from app.services import planning_change_service
from app.services.project_fulfilment_board_service import FulfilmentBoardService
from app.services.project_supply_service import _open_of
from app.services.scm.front_planning_engine import qty_text
from app.services.scm.outstanding_diff import CLOSED, PRODUCT_CHANGED, QTY_CHANGED, Change, Diff, Line

from tests.test_planning_changes import (  # noqa: F401  (api is the fixture)
    BASE,
    api,
    _confirm,
    _core_line,
    _core_so,
    _line_payload,
    _product,
    _project_line,
    _project_so,
    _stock,
)
from tests.scm.test_planning_change_delta_seam import (
    _active_decision,
    _change_and_batch,
    _held_reserve_world,
    _only_row,
)

MARKER = "zzt-oneopenbatch"


# --------------------------------------------------------------------------- #
# R1a: a second save on an order with a pending batch appends to it
# --------------------------------------------------------------------------- #

def test_a_second_save_on_an_order_with_a_pending_batch_appends_to_it(api):
    """Two manual edits, on two DIFFERENT held lines of the same order, made one after the
    other (two separate `build_batch` calls, the shape a manual SO edit produces - each Save
    is its own call) must land in ONE unapplied batch with two pending rows, per R1: `build_
    batch` for an order that already has an unapplied batch with pending rows APPENDS its
    rows to that batch rather than minting a new one."""
    client, world = api
    db = world.db
    core_so = _core_so(db, world.company_id)
    order = _project_so(db, world.project, so_id=core_so.id, autocount_doc_no=core_so.so_number)
    line_a = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="40",
                         required_date=date(2027, 3, 1))
    line_b = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="25",
                         required_date=date(2027, 3, 1))
    plan_a = _project_line(db, order, line_no=1, product=world.product, core_line=line_a)
    plan_b = _project_line(db, order, line_no=2, product=world.product, core_line=line_b)
    db.commit()
    _stock(db, world.product, world.own_wh, on_hand="65")
    _confirm(client, order.id, {"lines": [
        _line_payload(plan_a.id, reserve=[{"warehouse_id": world.own_wh.id, "qty": "40"}]),
        _line_payload(plan_b.id, reserve=[{"warehouse_id": world.own_wh.id, "qty": "25"}]),
    ]})

    # Save 1: line A's quantity is raised.
    line_a.qty_ordered = Decimal("55")
    db.flush()
    before_a = Line(doc_number=core_so.so_number, item_code=world.product.product_code,
                     location=world.own_wh.warehouse_code, qty=40.0,
                     required_date=date(2027, 3, 1), row_ref=str(line_a.id))
    after_a = Line(doc_number=core_so.so_number, item_code=world.product.product_code,
                    location=world.own_wh.warehouse_code, qty=55.0,
                    required_date=date(2027, 3, 1), row_ref=str(line_a.id))
    change_a = Change(QTY_CHANGED, core_so.so_number, world.product.product_code,
                       world.own_wh.warehouse_code, before=before_a, after=after_a)
    batch_1 = planning_change_service.build_batch(
        db, Diff(scope_documents=(core_so.so_number,), changes=[change_a]),
        applied_line_ids={id(change_a): str(line_a.id)},
        order_ids={core_so.so_number: str(core_so.id)}, actor=world.actor,
        import_job_id=None, file_name="book.xlsx",
    )
    db.commit()
    assert batch_1 is not None

    # Save 2: line B's quantity is raised too - a SEPARATE build_batch call, the same as a
    # second Save on the SO edit screen.
    line_b.qty_ordered = Decimal("30")
    db.flush()
    before_b = Line(doc_number=core_so.so_number, item_code=world.product.product_code,
                     location=world.own_wh.warehouse_code, qty=25.0,
                     required_date=date(2027, 3, 1), row_ref=str(line_b.id))
    after_b = Line(doc_number=core_so.so_number, item_code=world.product.product_code,
                    location=world.own_wh.warehouse_code, qty=30.0,
                    required_date=date(2027, 3, 1), row_ref=str(line_b.id))
    change_b = Change(QTY_CHANGED, core_so.so_number, world.product.product_code,
                       world.own_wh.warehouse_code, before=before_b, after=after_b)
    batch_2 = planning_change_service.build_batch(
        db, Diff(scope_documents=(core_so.so_number,), changes=[change_b]),
        applied_line_ids={id(change_b): str(line_b.id)},
        order_ids={core_so.so_number: str(core_so.id)}, actor=world.actor,
        import_job_id=None, file_name="book.xlsx",
    )
    db.commit()
    assert batch_2 is not None

    # R1: one open batch per order - the second save must APPEND to the first, not mint a
    # second unapplied batch.
    assert batch_2.id == batch_1.id, (
        f"expected the second save to append to the existing pending batch {batch_1.id!r}, "
        f"but build_batch minted a new batch {batch_2.id!r} instead"
    )

    from app.models.planning_change import PlanningChangeRow

    rows = (
        db.query(PlanningChangeRow)
        .filter(PlanningChangeRow.batch_id == batch_1.id)
        .all()
    )
    assert {str(r.project_line_id) for r in rows} == {str(plan_a.id), str(plan_b.id)}, (
        "the board payload for one open batch must carry both pending rows"
    )

    pending = planning_change_service.pending_batch_id_by_sales_order(db, [str(core_so.id)])
    assert pending.get(str(core_so.id)) == str(batch_1.id)


# --------------------------------------------------------------------------- #
# R1b: a second change on the SAME line supersedes the pending row
# --------------------------------------------------------------------------- #

def test_a_second_change_on_the_same_line_supersedes_the_pending_row():
    """Two successive edits to the SAME held line (qty 36 -> 60, then 60 -> 80) must leave
    ONE live pending row - the newest - whose from/to reads the LATEST edit's own before/
    after (60 -> 80, since `_change_and_batch` always diffs against the core line's value at
    the moment it is called, which is already 60 by the second call), with the older row
    (36 -> 60) marked `applied_state = 'superseded'`, reason "Replaced by a later change"
    (R1, landed). The second edit's row lands in a FRESH batch (a line can only have one
    live pending row at a time, so the open batch is not where the replacement goes) -
    `batch_1.id != batch_2.id` is expected, not a defect.

    No `api` fixture parameter: this test builds its own `blank_session()` directly (it
    needs two successive `build_batch` calls against one hand-built world, not the HTTP
    client `api` provides) - an earlier draft declared `api` anyway and never used it,
    which left a second, unused scratch-schema connection open for the whole test and was
    the reproducible cause of a `psycopg2.OperationalError: server closed the connection
    unexpectedly` at teardown (3/3 runs) once the shared dev Postgres was under any
    concurrent-agent load.
    """
    from tests._pg_fixture import blank_session

    with blank_session() as db:
        world = _held_reserve_world(db, qty="36")
        batch_1 = _change_and_batch(db, world, new_qty="60")
        row_1 = _only_row(db, batch_1)
        assert row_1.from_json["qty"] == "36", row_1.from_json
        assert row_1.to_json["qty"] == "60", row_1.to_json

        batch_2 = _change_and_batch(db, world, new_qty="80")
        row_2 = _only_row(db, batch_2)
        # Observed: `_change_and_batch` diffs from the core line's CURRENT value (60, after
        # the first edit was written), so the newest row's from/to is 60 -> 80, not 36 -> 80.
        assert row_2.from_json["qty"] == "60", row_2.from_json
        assert row_2.to_json["qty"] == "80", row_2.to_json

        db.refresh(row_1)
        assert row_1.applied_state == "superseded", (
            f"expected the older pending row to be superseded once a later change on the "
            f"same line landed, but applied_state is {row_1.applied_state!r}"
        )
        assert row_1.applied_reason == "Replaced by a later change", row_1.applied_reason


# --------------------------------------------------------------------------- #
# R2a/R2b: apply never carries a cancelled or renamed line
# --------------------------------------------------------------------------- #

def _row_for_line(db, batch_id, project_line_id) -> PlanningChangeRow:
    """The batch's own row for ONE line.

    R1 (one open batch per order) collapses a multi-save fixture like `_so400884_shape`
    into a SINGLE open batch carrying several pending rows - a later save on a line the
    open batch has not seen yet joins it rather than raising a new one - so `_only_row`
    (which asserts exactly one row per batch) no longer applies to it. This finds the row
    for the specific line a test means to decide, the same way a real board picks one row
    out of several pending on the same batch.
    """
    return (
        db.query(PlanningChangeRow)
        .filter(PlanningChangeRow.batch_id == batch_id,
                PlanningChangeRow.project_line_id == project_line_id)
        .one()
    )


def _so400884_shape(api):
    """Four held Reserve lines on one order - the SO400884 shape from the browser walk.
    Three SEPARATE `build_batch` calls follow (one per edit), matching real multi-save
    usage. Under R1 (one open batch per order, landed 13 Sep) the second and third calls
    APPEND their rows into the FIRST call's still-open batch rather than raising a new one
    each time - none of the three edits touches a line the open batch has already seen, so
    `batch1`, `batch2` and `batch4` below all resolve to the SAME batch, now carrying three
    pending rows. The R2 assertions this fixture backs (nothing carried for the cancelled/
    renamed lines) still exercise the real thing worth pinning: `_apply_one_order` deciding
    ONE line of a batch must never carry the OTHERS' stale state into the new revision,
    same-batch or not."""
    client, world = api
    db = world.db
    core_so = _core_so(db, world.company_id)
    order = _project_so(db, world.project, so_id=core_so.id, autocount_doc_no=core_so.so_number)

    qtys = ["36", "50", "20", "60"]
    required = date(2026, 12, 28)
    core_lines = []
    plan_lines = []
    for i, qty in enumerate(qtys, start=1):
        cl = _core_line(db, core_so, world.product, world.own_wh, qty_ordered=qty,
                         required_date=required)
        pl = _project_line(db, order, line_no=i, product=world.product, core_line=cl)
        core_lines.append(cl)
        plan_lines.append(pl)
    db.commit()
    _stock(db, world.product, world.own_wh, on_hand=str(sum(Decimal(q) for q in qtys)))
    _confirm(client, order.id, {"lines": [
        _line_payload(pl.id, reserve=[{"warehouse_id": world.own_wh.id, "qty": qty}])
        for pl, qty in zip(plan_lines, qtys)
    ]})

    line1, line2, line3, line4 = core_lines
    plan1, plan2, plan3, plan4 = plan_lines

    # Save A: line 1 is removed from the book - cancelled.
    line1.line_status = "cancelled"
    db.flush()
    before1 = Line(doc_number=core_so.so_number, item_code=world.product.product_code,
                    location=world.own_wh.warehouse_code, qty=float(qtys[0]),
                    required_date=required, row_ref=str(line1.id))
    change1 = Change(CLOSED, core_so.so_number, world.product.product_code,
                      world.own_wh.warehouse_code, before=before1, after=None)
    batch1 = planning_change_service.build_batch(
        db, Diff(scope_documents=(core_so.so_number,), changes=[change1]),
        applied_line_ids={id(change1): str(line1.id)},
        order_ids={core_so.so_number: str(core_so.id)}, actor=world.actor,
        import_job_id=None, file_name="book.xlsx",
    )
    db.commit()
    assert batch1 is not None

    # Save B: line 2's product is renamed.
    new_product = _product(db)
    old_item_code = world.product.product_code
    line2.product_id = new_product.id
    db.flush()
    before2 = Line(doc_number=core_so.so_number, item_code=old_item_code,
                    location=world.own_wh.warehouse_code, qty=float(qtys[1]),
                    required_date=required, row_ref=str(line2.id))
    after2 = Line(doc_number=core_so.so_number, item_code=new_product.product_code,
                   location=world.own_wh.warehouse_code, qty=float(qtys[1]),
                   required_date=required, row_ref=str(line2.id))
    change2 = Change(PRODUCT_CHANGED, core_so.so_number, new_product.product_code,
                      world.own_wh.warehouse_code, before=before2, after=after2)
    batch2 = planning_change_service.build_batch(
        db, Diff(scope_documents=(core_so.so_number,), changes=[change2]),
        applied_line_ids={id(change2): str(line2.id)},
        order_ids={core_so.so_number: str(core_so.id)}, actor=world.actor,
        import_job_id=None, file_name="book.xlsx",
    )
    db.commit()
    assert batch2 is not None

    # Save C: line 4's quantity is raised - the ONLY row the planner confirms below.
    line4.qty_ordered = Decimal("80")
    db.flush()
    before4 = Line(doc_number=core_so.so_number, item_code=world.product.product_code,
                    location=world.own_wh.warehouse_code, qty=float(qtys[3]),
                    required_date=required, row_ref=str(line4.id))
    after4 = Line(doc_number=core_so.so_number, item_code=world.product.product_code,
                   location=world.own_wh.warehouse_code, qty=80.0,
                   required_date=required, row_ref=str(line4.id))
    change4 = Change(QTY_CHANGED, core_so.so_number, world.product.product_code,
                      world.own_wh.warehouse_code, before=before4, after=after4)
    batch4 = planning_change_service.build_batch(
        db, Diff(scope_documents=(core_so.so_number,), changes=[change4]),
        applied_line_ids={id(change4): str(line4.id)},
        order_ids={core_so.so_number: str(core_so.id)}, actor=world.actor,
        import_job_id=None, file_name="book.xlsx",
    )
    db.commit()
    assert batch4 is not None

    # R1: one open batch per order - all three saves landed in the SAME batch.
    assert batch2.id == batch1.id, (batch1.id, batch2.id)
    assert batch4.id == batch1.id, (batch1.id, batch4.id)
    rows_in_batch = (
        db.query(PlanningChangeRow)
        .filter(PlanningChangeRow.batch_id == batch1.id)
        .all()
    )
    assert len(rows_in_batch) == 3, [r.kind for r in rows_in_batch]

    return {
        "world": world, "order": order, "core_so": core_so, "new_product": new_product,
        "line1": line1, "line2": line2, "line3": line3, "line4": line4,
        "plan1": plan1, "plan2": plan2, "plan3": plan3, "plan4": plan4,
        "batch1": batch1, "batch2": batch2, "batch4": batch4,
    }


def test_apply_of_one_row_never_carries_a_cancelled_line(api):
    """R2: applying batch4 (line 4's qty raise, the only row confirmed) must never carry
    line 1 (cancelled, pending in batch1) or line 2 (renamed, pending in batch2) into the
    new revision. Today `_apply_one_order` only sees batch4's own rows, so neither line 1
    nor line 2 is named or uncovered - `ProjectSupplyService`'s carry-forward rule copies
    both stale snapshots into the new revision verbatim."""
    shape = _so400884_shape(api)
    db = shape["world"].db
    order = shape["order"]

    row4 = _row_for_line(db, shape["batch4"].id, shape["plan4"].id)
    planning_change_service.set_row_decision(db, str(shape["batch4"].id), str(row4.id), "confirm")
    db.commit()
    planning_change_service.apply(db, str(shape["batch4"].id), shape["world"].actor)
    db.commit()

    active = _active_decision(db, order.id)
    snapshots = active.line_snapshots or []
    by_line = {str(s.get("project_line_id")): s for s in snapshots}

    # The cancelled line must not have a home in the new revision's snapshots at all.
    assert str(shape["plan1"].id) not in by_line, (
        f"line 1 was cancelled by an unapplied batch but was still carried into revision "
        f"{active.revision_no}: {by_line.get(str(shape['plan1'].id))}"
    )

    # The renamed line, if carried at all, must carry the NEW product - never the old one.
    line2_snapshot = by_line.get(str(shape["plan2"].id))
    assert line2_snapshot is not None, (
        "line 2 (renamed) dropped out of the revision entirely - acceptable only if it is "
        "uncovered and back on the board; assert `so_supply_decisions` and the board queue "
        "agree it is undecided rather than silently lost"
    )
    assert line2_snapshot.get("product_id") == str(shape["new_product"].id), (
        f"line 2's carried snapshot still names the OLD product "
        f"{line2_snapshot.get('product_id')!r}, not the renamed product "
        f"{shape['new_product'].id!r}"
    )

    # No stock is held for the cancelled line under the new decision.
    line1_allocs = (
        db.query(SOLineAllocation)
        .filter(SOLineAllocation.so_line_id == shape["plan1"].id,
                SOLineAllocation.decision_id == active.id)
        .all()
    )
    assert line1_allocs == [], [str(a.id) for a in line1_allocs]


def test_a_renamed_products_demand_gets_a_decision_or_a_buy_row_on_the_next_confirm(api):
    """Confirming line 2's OWN product_changed row must raise demand for the NEW product (a
    Buy/Reserve component) and drop the hold on the OLD product - not leave the old
    product's allocation standing beside a new, unrelated one.

    R1: `batch2` and `batch4` are now the SAME open batch (`_so400884_shape`'s own
    invariant), so both rows are DECIDED before the one `apply()` that settles the batch -
    `apply()` stamps the whole batch's `applied_at` once it has revised the order with no
    pending row of a WANTED order left out, so a second `apply()` call on this same batch
    (the previous test's two-call shape) would 409 'This batch has already been applied.'
    """
    shape = _so400884_shape(api)
    db = shape["world"].db
    order = shape["order"]
    world = shape["world"]

    row4 = _row_for_line(db, shape["batch4"].id, shape["plan4"].id)
    planning_change_service.set_row_decision(db, str(shape["batch4"].id), str(row4.id), "confirm")
    db.commit()

    # Stock exists for the NEW product too, so the engine has something to compose with.
    _stock(db, shape["new_product"], world.own_wh, on_hand="50")
    db.commit()

    row2 = _row_for_line(db, shape["batch2"].id, shape["plan2"].id)
    planning_change_service.set_row_decision(db, str(shape["batch2"].id), str(row2.id), "confirm")
    db.commit()

    planning_change_service.apply(db, str(shape["batch4"].id), world.actor)
    db.commit()

    active = _active_decision(db, order.id)
    snapshots = active.line_snapshots or []
    by_line = {str(s.get("project_line_id")): s for s in snapshots}
    line2_snapshot = by_line.get(str(shape["plan2"].id))
    assert line2_snapshot is not None, "line 2 must still be covered after its own confirm"
    components = line2_snapshot.get("components") or []
    assert components, "confirming the renamed line must compose SOMETHING for the new product"

    # `SOLineAllocation` carries no `product_id` (grepped `app/models/project_so.py` -
    # absent) and `Stock.quantity_reserved` is not the live ledger either (measured: it
    # stays 0 throughout this fixture - the ladder reads `SOLineAllocation` rows, not this
    # column) - neither can tell an OLD-product hold apart from a NEW one on the SAME
    # so_line_id. What CAN be measured, and is the real point of "raises demand for the new
    # product": the line's own confirmed snapshot names the NEW product, not the old one -
    # there is exactly one product on a line, so this and "the old hold is gone" are the
    # same fact.
    assert line2_snapshot.get("product_id") == str(shape["new_product"].id), (
        f"line 2's own confirmed snapshot still names "
        f"{line2_snapshot.get('product_id')!r}, not the renamed product "
        f"{shape['new_product'].id!r}"
    )


# --------------------------------------------------------------------------- #
# R2c: a cancelled core line reads zero open qty everywhere
# --------------------------------------------------------------------------- #

def test_a_cancelled_core_line_reads_zero_open_qty(api):
    """`_open_of` (AC-B01's own open-quantity primitive - the figure the drift check in
    `_carried_lines`/`_carry_snapshot_has_drifted` and the board both read) does not floor a
    `line_status='cancelled'` line to zero: it reads `qty_ordered - qty_delivered` alone.
    Measured directly against the function, no HTTP/board round trip needed - `_open_of`
    takes only `qty_ordered`/`qty_delivered`/nothing-else as far as this reads, so a
    lightweight stand-in line object exercises the same code path a real
    `SalesOrderLine` would."""
    client, world = api
    db = world.db
    core_so = _core_so(db, world.company_id)
    core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="40",
                            qty_delivered="0", required_date=date(2027, 3, 1))
    core_line.line_status = "cancelled"
    db.flush()
    db.commit()

    assert _open_of(core_line) == Decimal("0"), (
        f"a cancelled core line's open qty should read 0 everywhere the board and the "
        f"decision read it, but _open_of returned {_open_of(core_line)!r} "
        f"(qty_ordered={core_line.qty_ordered!r}, qty_delivered={core_line.qty_delivered!r})"
    )


# --------------------------------------------------------------------------- #
# R3: a cancelled line with a pending change row has a home on the board
# --------------------------------------------------------------------------- #

def _one_held_line_cancelled(api):
    """One held Reserve line, then the book removes it - `line_status` written 'cancelled'
    first (write-first), then a CLOSED `Change` fed to `build_batch` so a real pending
    'cancelled' `PlanningChangeRow` exists, exactly the shape a manual SO edit or a book
    re-upload produces (Slice A rule 5)."""
    client, world = api
    db = world.db
    core_so = _core_so(db, world.company_id)
    core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="72",
                            required_date=date(2026, 12, 28))
    order = _project_so(db, world.project, so_id=core_so.id, autocount_doc_no=core_so.so_number)
    line = _project_line(db, order, line_no=1, product=world.product, core_line=core_line)
    db.commit()
    _stock(db, world.product, world.own_wh, on_hand="72")
    _confirm(client, order.id, {"lines": [
        _line_payload(line.id, reserve=[{"warehouse_id": world.own_wh.id, "qty": "72"}]),
    ]})

    core_line.line_status = "cancelled"
    db.flush()
    before = Line(doc_number=core_so.so_number, item_code=world.product.product_code,
                  location=world.own_wh.warehouse_code, qty=72.0,
                  required_date=date(2026, 12, 28), row_ref=str(core_line.id))
    change = Change(CLOSED, core_so.so_number, world.product.product_code,
                     world.own_wh.warehouse_code, before=before, after=None)
    batch = planning_change_service.build_batch(
        db, Diff(scope_documents=(core_so.so_number,), changes=[change]),
        applied_line_ids={id(change): str(core_line.id)},
        order_ids={core_so.so_number: str(core_so.id)}, actor=world.actor,
        import_job_id=None, file_name="book.xlsx",
    )
    db.commit()
    assert batch is not None
    return client, world, order, core_so, core_line, line, batch


def test_board_payload_carries_a_cancelled_line_with_a_pending_change_row(api):
    """Captain's R3 ruling (13 Sep, board-display round): a cancelled changed line has a
    home on the board - `FulfilmentBoardService.build`'s `contributions` list (`_contribution`,
    the list the FE List view reads per its own comment at project_fulfilment_board_service
    .py ~730) is built from `_demand_rows`, which filters on `is_open_demand()`
    (`SalesOrderLine.line_status == "open"`) - a cancelled core line never becomes a `_Row`
    at all, so it is not merely wrong today, it is ABSENT. This is the genuine red: no
    `cancelled`/`pending_change_batch_id` key exists on `_contribution`'s dict yet either
    (grepped - neither name appears in the function), so the coder may need to name the
    board-side flag differently than `cancelled`; write the assertion against `cancelled`
    and note here it may need renaming to match whatever the coder actually calls it.
    """
    client, world, order, core_so, core_line, line, batch = _one_held_line_cancelled(api)
    db = world.db

    board = FulfilmentBoardService(db).build([core_so.so_number])
    contributions = board["contributions"]
    mine = [c for c in contributions if c["line_id"] == str(core_line.id)]
    assert mine, (
        f"the cancelled line ({core_line.id}) has a PENDING change row (batch "
        f"{batch.id}) but is entirely absent from the board's contributions - "
        f"is_open_demand() filters it out of _demand_rows before _contribution ever runs"
    )
    contrib = mine[0]
    assert contrib["qty"] == qty_text(Decimal("0")), contrib
    assert contrib["qty_outstanding"] == qty_text(Decimal("0")), contrib
    # The board-side flag name is the coder's call - `cancelled` is the best-guess name
    # from the captain's ruling; rename this assertion to match whatever key lands.
    assert contrib.get("cancelled") is True, contrib
    assert contrib.get("pending_change_batch_id") == str(batch.id), contrib

    # Apply the batch (retire path) - the cancelled line is fully done and must NOT
    # reappear on the board once nothing is pending for it any more.
    planning_change_service.set_row_decision(
        db, str(batch.id), str(_only_row(db, batch).id), "confirm",
    )
    db.commit()
    planning_change_service.apply(db, str(batch.id), world.actor)
    db.commit()

    board_after = FulfilmentBoardService(db).build([core_so.so_number])
    still_there = [
        c for c in board_after["contributions"] if c["line_id"] == str(core_line.id)
    ]
    assert still_there == [], (
        "a cancelled line with no pending row left (already applied) must not appear on "
        f"the board - found {still_there}"
    )


def test_confirm_all_counts_and_applies_the_cancelled_row(api):
    """The board's Confirm (N) / Approve-all posts `POST .../fulfilment-planning/confirm-
    all` with the order's own `batch_id` and no composed lines for a cancelled row (nothing
    to compose FOR - `_confirm_a_planning_change` skips straight to `continue` on a
    `kind == 'cancelled'` row). The row still applies through the retire path and must be
    counted in `lines_decided`."""
    client, world, order, core_so, core_line, line, batch = _one_held_line_cancelled(api)
    db = world.db

    response = client.post(f"{BASE}/fulfilment-planning/confirm-all", json={
        "orders": [{"pso_id": order.id, "lines": [], "batch_id": str(batch.id)}],
    })
    assert response.status_code == 200, response.text
    body = response.json()
    results = body["results"]
    assert len(results) == 1, results
    result = results[0]
    assert result["ok"] is True, result
    assert (result.get("lines_decided") or 0) >= 1, (
        f"the cancelled row's retire must count as a decided line, got {result}"
    )

    row = _only_row(db, batch)
    db.refresh(row)
    assert row.applied_state == "applied", row.applied_state
