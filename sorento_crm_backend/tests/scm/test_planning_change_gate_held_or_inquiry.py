"""A planning change is raised only for a line someone has decided on.

`documentation/plans/scm/PLAN-scm-planning-change-gate-held-or-inquiry.md`, AC-G1 to G5.
Supersedes AC-R01 / AC-R03 of `PLAN-so-book-diff-replanning.md`: on the 10 Sep 2026 live copy
1,307 of 1,308 pending rows sat on lines nobody had decided on, so the `Changed` pill sent the
reader to a board with nothing to re-decide.

Helpers are imported from `tests/test_planning_changes.py` (same world, same Postgres chain)
rather than copied: this slice owns both files.
"""
from __future__ import annotations

from datetime import date

from app.models.planning_change import (
    PLANNING_CHANGE_STATE_PENDING,
    PLANNING_CHANGE_STATE_SUPERSEDED,
    PlanningChangeBatch,
    PlanningChangeRow,
)
from app.models.project_so import DECISION_CHALLENGED, ProjectSalesOrder, SOSupplyDecision
from app.services import planning_change_service
from app.services.scm.outstanding_diff import CLOSED, DATE_MOVED, QTY_CHANGED, Diff
from app.services.scm.sales_order_service import SalesOrderService

from tests.test_planning_changes import (  # noqa: F401  (api is the fixture)
    _confirm,
    _core_line,
    _core_so,
    _diff_change,
    _line_payload,
    _project_line,
    _project_so,
    _stock,
    api,
)

OLD = date(2026, 8, 20)
NEW = date(2026, 9, 3)


def _adopted_line(db, world, *, qty="72", line_no=1, core_so=None):
    core_so = core_so or _core_so(db, world.company_id)
    core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered=qty,
                           required_date=OLD)
    order = (
        db.query(ProjectSalesOrder).filter_by(so_id=core_so.id).one_or_none()
        or _project_so(db, world.project, so_id=core_so.id, autocount_doc_no=core_so.so_number)
    )
    line = _project_line(db, order, line_no=line_no, product=world.product, core_line=core_line)
    db.commit()
    return core_so, core_line, order, line


def _build(db, world, core_so, changes):
    return planning_change_service.build_batch(
        db,
        Diff(scope_documents=(core_so.so_number,), changes=[c for c, _ in changes]),
        applied_line_ids={id(c): str(core_line.id) for c, core_line in changes},
        order_ids={core_so.so_number: str(core_so.id)},
        actor=world.actor, import_job_id=None, file_name="book.xlsx",
    )


def _change(kind, core_so, core_line, *, old_qty="72", new_qty="72", new_date=NEW, item="ZZT-ITEM"):
    return _diff_change(
        kind, core_line, doc_number=core_so.so_number, item_code=item, location="ZZT-OWN",
        old_date=OLD, new_date=new_date, old_qty=old_qty, new_qty=new_qty,
    )


# --------------------------------------------------------------------------- #
# AC-G1: an undecided line is silent, whatever changed
# --------------------------------------------------------------------------- #


def test_ac_g1_undecided_line_raises_no_batch_for_date_qty_or_close(api):
    _client, world = api
    db = world.db
    core_so, core_line, _order, _line = _adopted_line(db, world)

    for change in (
        _change(DATE_MOVED, core_so, core_line),
        _change(QTY_CHANGED, core_so, core_line, new_qty="90", new_date=OLD),
        _change(CLOSED, core_so, core_line),
    ):
        assert _build(db, world, core_so, [(change, core_line)]) is None, change.kind
    assert db.query(PlanningChangeBatch).count() == 0
    assert db.query(PlanningChangeRow).count() == 0


# --------------------------------------------------------------------------- #
# AC-G2: a held line still raises, with the rule table untouched
# --------------------------------------------------------------------------- #


def test_ac_g2_held_line_raises_one_row_with_held_json(api):
    client, world = api
    db = world.db
    _stock(db, world.product, world.pool_wh, on_hand=100)
    core_so, core_line, order, line = _adopted_line(db, world, qty="40")
    _confirm(client, order.id, {"lines": [
        _line_payload(line.id, reserve=[{"warehouse_id": world.pool_wh.id, "qty": "40"}]),
    ]})

    change = _change(DATE_MOVED, core_so, core_line, old_qty="40", new_qty="40",
                     new_date=date(2027, 3, 10))
    batch = _build(db, world, core_so, [(change, core_line)])
    db.commit()
    assert batch is not None
    assert batch.line_count == 1 and batch.order_count == 1
    row = db.query(PlanningChangeRow).filter_by(batch_id=batch.id).one()
    assert row.held_json is not None
    assert row.suggested == "release"  # rule 2: delay beyond the window, not hot, not discontinued


# --------------------------------------------------------------------------- #
# AC-G3: an inquiry row keeps the line in scope even after its decision lapsed
# --------------------------------------------------------------------------- #


def test_ac_g3_inquiry_row_without_active_decision_still_raises(api):
    client, world = api
    db = world.db
    core_so, core_line, order, line = _adopted_line(db, world, qty="30")
    _confirm(client, order.id, {"lines": [
        _line_payload(line.id, buy_qty="30", buy_reason="ZZT no stock anywhere"),
    ]})
    # The decision drifted out from under the line (what `challenge_if_drifted` writes),
    # but the Buy row it raised is still open with the supplier: that is the commitment.
    decision = (
        db.query(SOSupplyDecision)
        .filter(SOSupplyDecision.project_sales_order_id == order.id)
        .one()
    )
    decision.state = DECISION_CHALLENGED
    db.commit()

    change = _change(QTY_CHANGED, core_so, core_line, old_qty="30", new_qty="20", new_date=OLD)
    batch = _build(db, world, core_so, [(change, core_line)])
    db.commit()
    assert batch is not None
    row = db.query(PlanningChangeRow).filter_by(batch_id=batch.id).one()
    assert row.held_json is None
    assert row.inquiry_rows_json, "the raised Buy row is why this line is still in scope"
    assert row.kind == "qty_down"


# --------------------------------------------------------------------------- #
# AC-G4: a mixed order keeps only the held line and counts only that
# --------------------------------------------------------------------------- #


def test_ac_g4_mixed_order_counts_only_the_held_row(api):
    client, world = api
    db = world.db
    _stock(db, world.product, world.pool_wh, on_hand=100)
    core_so, held_core, order, held_line = _adopted_line(db, world, qty="40")
    _, loose_core, _, _loose_line = _adopted_line(db, world, qty="10", line_no=2, core_so=core_so)
    _confirm(client, order.id, {"lines": [
        _line_payload(held_line.id, reserve=[{"warehouse_id": world.pool_wh.id, "qty": "40"}]),
    ]})

    batch = _build(db, world, core_so, [
        (_change(DATE_MOVED, core_so, held_core, old_qty="40", new_qty="40"), held_core),
        (_change(DATE_MOVED, core_so, loose_core, old_qty="10", new_qty="10", item="ZZT-ITEM-2"),
         loose_core),
    ])
    db.commit()
    assert batch is not None
    assert batch.line_count == 1
    assert batch.order_count == 1
    rows = db.query(PlanningChangeRow).filter_by(batch_id=batch.id).all()
    assert [str(r.core_line_id) for r in rows] == [str(held_core.id)]


# --------------------------------------------------------------------------- #
# AC-G5: the SO-list pill reads pending rows, not merely an unapplied batch
# --------------------------------------------------------------------------- #


def test_ac_g5_pill_ignores_a_batch_whose_rows_are_all_superseded(api):
    client, world = api
    db = world.db
    _stock(db, world.product, world.pool_wh, on_hand=100)
    core_so, core_line, order, line = _adopted_line(db, world, qty="40")
    _confirm(client, order.id, {"lines": [
        _line_payload(line.id, reserve=[{"warehouse_id": world.pool_wh.id, "qty": "40"}]),
    ]})
    batch = _build(db, world, core_so, [
        (_change(DATE_MOVED, core_so, core_line, old_qty="40", new_qty="40"), core_line),
    ])
    db.commit()
    assert batch is not None

    def pill():
        rows = SalesOrderService(db).with_planning_changes([{"id": str(core_so.id)}])
        return rows[0]["planning_change_batch_id"]

    assert pill() == str(batch.id)

    row = db.query(PlanningChangeRow).filter_by(batch_id=batch.id).one()
    assert row.applied_state == PLANNING_CHANGE_STATE_PENDING
    row.applied_state = PLANNING_CHANGE_STATE_SUPERSEDED
    row.applied_reason = "ZZT superseded by the test"
    db.commit()
    assert batch.applied_at is None  # the batch itself is still open ...
    assert pill() is None  # ... but nothing in it is pending, so no pill
