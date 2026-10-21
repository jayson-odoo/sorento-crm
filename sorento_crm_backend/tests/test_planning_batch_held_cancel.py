"""PLAN-BATCH-HELD-CANCEL (owner ruling (a) + crew rulings Q1/Q2, 21 Oct 2026).

SO394881's shape: an AutoCount book upload cancelled the order's old lines (`cancelled` rows)
and added replacement lines (`added` rows: `project_line_id` NULL, `core_line_id` set,
`held_json` NULL). CS confirmed most replacement lines through ordinary presses, which left
their `added` rows pending, and saved Cancel SO on 12 of them. ONE press must:

- transfer the 12 Cancel SO lines and close their `added` rows ("the sales-order line is
  cancelled");
- retire the old lines by taking ONLY them out of the active revision (Q1): every other
  confirmed line stays confirmed, whether or not the press also composed a line;
- close an `added` row whose line the active revision already covers, as applied (Q2), and
  never one whose line is not covered;
- so the batch closes (`applied_at`) and holds nothing any more.

Plan: `documentation/plans/scm/PLAN-batch-held-cancel-21oct.md`. Postgres only; every test
seeds its own chain.
"""
from __future__ import annotations

import uuid

import pytest

from app.models.order import SalesOrderLine
from app.models.planning_change import PlanningChangeBatch, PlanningChangeRow
from app.models.project_so import DECISION_ACTIVE, SOSupplyDecision

from .test_so_cancel_line import REASON, _confirm_all
from .test_so_supply_confirmation import (  # noqa: F401 - `api` is a fixture
    BASE,
    _core_line,
    _core_so,
    _line_payload,
    _project_line,
    _project_so,
    api,
)

QTY = "40"


def _covered(db, order) -> set:
    db.expire_all()
    active = (
        db.query(SOSupplyDecision)
        .filter(
            SOSupplyDecision.project_sales_order_id == order.id,
            SOSupplyDecision.state == DECISION_ACTIVE,
        )
        .one_or_none()
    )
    if active is None:
        return set()
    return {str(s.get("project_line_id")) for s in (active.line_snapshots or [])}


def _line(db, core_so, order, world, line_no):
    core = _core_line(db, core_so, world.product, world.own_wh, qty_ordered=QTY)
    return core, _project_line(db, order, line_no=line_no, product=world.product, core_line=core)


def _row(db, batch, order, core, mirror, kind):
    """A pending batch row the way the book upload writes it: an `added` row carries no
    `project_line_id` (only its proposal names the mirror line), a `cancelled` one does."""
    row = PlanningChangeRow(
        id=str(uuid.uuid4()),
        batch_id=batch.id,
        project_sales_order_id=order.id,
        project_line_id=mirror.id if kind == "cancelled" else None,
        core_line_id=core.id,
        line_no=mirror.line_no,
        item_code="ZZT-ITEM",
        kind=kind,
        facts_json={},
        # As the book upload writes them (dev batch a0df3624): the new line's qty and status.
        to_json={"qty": QTY, "status": "open", "item_code": None} if kind == "added" else None,
        proposal_json={"project_line_id": str(mirror.id)} if kind == "added" else None,
        applied_state="pending",
    )
    db.add(row)
    return row


def _world(client, world, *, n_old, n_cancel, n_covered, n_open, autocount=False):
    """Old lines confirmed, then the book cancels them and adds `n_cancel + n_covered +
    n_open` replacement lines. `n_covered` of those are confirmed afterwards by an ordinary
    press (their `added` rows stay pending), `n_cancel` carry a saved Cancel SO, `n_open`
    are undecided."""
    db = world.db
    core_so = _core_so(db, world.company_id)
    order = _project_so(db, world.project, so_id=core_so.id)
    line_no = iter(range(1, 1000))
    old = [_line(db, core_so, order, world, next(line_no)) for _ in range(n_old)]
    cancel = [_line(db, core_so, order, world, next(line_no)) for _ in range(n_cancel)]
    covered = [_line(db, core_so, order, world, next(line_no)) for _ in range(n_covered)]
    still_open = [_line(db, core_so, order, world, next(line_no)) for _ in range(n_open)]
    db.commit()
    if old or covered:
        assert _confirm_all(
            client,
            order,
            lines=[_line_payload(m.id, buy_qty=QTY) for _c, m in [*old, *covered]],
        )["ok"]
    batch = PlanningChangeBatch(id=str(uuid.uuid4()), source_kind="so_manual_edit", applied_at=None)
    db.add(batch)
    db.flush()
    rows = {}
    for core, mirror in old:
        core.line_status = "cancelled"
        rows[mirror.id] = _row(db, batch, order, core, mirror, "cancelled")
    for core, mirror in [*cancel, *covered, *still_open]:
        rows[mirror.id] = _row(db, batch, order, core, mirror, "added")
    if autocount:
        # An AutoCount Cancel SO document cancelled these lines afterwards; the ingest saved
        # Transfer to Cancel SO on each (`propose_autocount_cancel`): `awaits_cancel_so`.
        for core, _m in cancel:
            core.line_status = "cancelled"
            core.cancelled_by_cancel_doc = True
    db.commit()
    return {
        "order": order,
        "batch_id": str(batch.id),
        "old": old,
        "cancel": cancel,
        "covered": covered,
        "open": still_open,
        "rows": rows,
    }


def _press(client, w, *, lines=(), cancel=(), reason=REASON):
    response = client.post(
        f"{BASE}/fulfilment-planning/confirm-all",
        json={
            "orders": [
                {
                    "pso_id": w["order"].id,
                    "batch_id": w["batch_id"],
                    "lines": list(lines),
                    "cancelled_lines": [
                        {"project_line_id": m.id, "reason": reason} for _c, m in cancel
                    ],
                }
            ]
        },
    )
    assert response.status_code == 200, response.text
    result = response.json()["results"][0]
    assert result["ok"] is True, result
    return result


def _states(db, w, group):
    db.expire_all()
    return {db.get(PlanningChangeRow, w["rows"][m.id].id).applied_state for _c, m in w[group]}


@pytest.mark.parametrize("source", ["board", "autocount_cancel"])
def test_so394881_one_press_applies_the_change_and_sends_the_held_cancels(api, source):
    """10 cancelled + 30 added rows; 12 with Cancel SO, the other 18 already confirmed. The
    Cancel SO is either saved on the board or the draft an AutoCount Cancel SO document left
    (reason "AutoCount Cancel SO <doc>"), which the results echo per line."""
    client, world = api
    db = world.db
    autocount = source == "autocount_cancel"
    w = _world(client, world, n_old=10, n_cancel=12, n_covered=18, n_open=0, autocount=autocount)
    reason = "AutoCount Cancel SO CSO-0001" if autocount else REASON

    result = _press(client, w, cancel=w["cancel"], reason=reason)

    assert {r["reason"] for r in result["lines_cancelled"]} == {reason}

    assert sorted(r["line_no"] for r in result["lines_cancelled"]) == [
        m.line_no for _c, m in w["cancel"]
    ]
    assert result["planning_change_applied"] is True
    assert sorted(r["line_no"] for r in result["lines_retired"]) == [
        m.line_no for _c, m in w["old"]
    ]
    # Q1: only the retired lines left the revision; the 18 confirmed lines stay confirmed.
    assert _covered(db, w["order"]) == {str(m.id) for _c, m in w["covered"]}
    for core, _m in w["cancel"]:
        assert db.get(SalesOrderLine, str(core.id)).line_status == "cancelled"
    assert _states(db, w, "old") == {"applied"}
    assert _states(db, w, "covered") == {"applied"}
    assert _states(db, w, "cancel") == {"superseded"}
    reasons = {db.get(PlanningChangeRow, w["rows"][m.id].id).applied_reason for _c, m in w["cancel"]}
    assert reasons == {"the sales-order line is cancelled"}
    assert db.get(PlanningChangeBatch, w["batch_id"]).applied_at is not None


@pytest.mark.parametrize("composed", [False, True], ids=["retire-only", "with-a-composed-line"])
def test_q1_a_retire_uncovers_only_the_retired_lines_with_or_without_a_composed_line(api, composed):
    """Q1 (crew ruling a): the same outcome whether or not the press composed a line. Was: a
    retire-only press superseded the WHOLE revision (planning_change_service.py:4743)."""
    client, world = api
    db = world.db
    w = _world(client, world, n_old=1, n_cancel=0, n_covered=1, n_open=1)
    (_oc, old), (_kc, kept), (_pc, opened) = w["old"][0], w["covered"][0], w["open"][0]

    lines = [_line_payload(opened.id, buy_qty=QTY)] if composed else []
    result = _press(client, w, lines=lines)

    assert [r["line_no"] for r in result["lines_retired"]] == [old.line_no]
    expected = {str(kept.id), str(opened.id)} if composed else {str(kept.id)}
    assert _covered(db, w["order"]) == expected
    assert _states(db, w, "old") == {"applied"}
    assert _states(db, w, "covered") == {"applied"}
    # The composed added line routes through its own row (linked to its mirror line), so the
    # row is applied; an uncomposed one stays pending (Q2: never close an uncovered line).
    assert _states(db, w, "open") == ({"applied"} if composed else {"pending"})


def test_crew_item_3_a_press_that_only_retires_an_uncovered_line_is_not_refused(api):
    """Reviewer round 1: the board posts `{batch_id, lines: [], cancelled_lines: []}` for an
    order whose only counted line is one the book cancelled. When no revision covers that
    line the apply writes no revision, and the press read "Nothing on this planning change
    could be confirmed" although it had applied the row."""
    client, world = api
    db = world.db
    w = _world(client, world, n_old=0, n_cancel=0, n_covered=1, n_open=1)
    _core, line = w["open"][0]
    # The book cancelled the uncovered line: a `cancelled` row on it, nothing confirmed there.
    row = w["rows"][line.id]
    row.kind = "cancelled"
    row.project_line_id = line.id
    db.commit()

    result = _press(client, w)

    assert result["planning_change_applied"] is True
    assert [r["line_no"] for r in result["lines_retired"]] == [line.line_no]
    assert _states(db, w, "open") == {"applied"}


def test_q2_an_added_row_on_a_line_nobody_confirmed_stays_pending(api):
    """Q2: never close a row whose line is not covered; the batch then stays open for it."""
    client, world = api
    db = world.db
    w = _world(client, world, n_old=1, n_cancel=1, n_covered=1, n_open=1)

    _press(client, w, cancel=w["cancel"])

    assert _states(db, w, "open") == {"pending"}
    assert _states(db, w, "covered") == {"applied"}
    assert db.get(PlanningChangeBatch, w["batch_id"]).applied_at is None


# --------------------------------------------------------------------------- #
# Owner ruling (a), 21 Oct 2026 ~16:00 MYT (crew relay): ONLY the press this fix enables is
# silent. An order whose Cancel SO a pending AutoCount change held (board-saved or an AutoCount
# Cancel SO draft) gets the change applied and those cancels sent with NO cancel or retire line
# in any automated email and no changed-with-links automation; purchasing sees the rows
# cancelled in the CRM and keeps the in-app "Planning change applied" notice. A normal Cancel SO
# still emails its CANCEL list (8 Oct rule, #1530) and a batch retire without held cancels still
# prints its CANCEL ALL lines (#1806).
# --------------------------------------------------------------------------- #

CHANGED_WITH_LINKS = "order_inquiry_changed_with_links"


def _outbox_count(db) -> int:
    from sqlalchemy import func

    from app.models.email_outbox import EmailOutbox

    db.expire_all()
    return db.query(func.count(EmailOutbox.id)).scalar()


def _live_row_on(world, w, mirror):
    """A raised ORDER row on a line CS is about to transfer to Cancel SO."""
    from app.models.project_so import OrderInquiry

    from .test_oi_cancelled_line_used_confirm import _inquiry, _oi_row

    db = world.db
    inquiry = (
        db.query(OrderInquiry)
        .filter(
            OrderInquiry.project_sales_order_id == w["order"].id,
            OrderInquiry.amendment_id.is_(None),
        )
        .one_or_none()
    ) or _inquiry(db, world.company_id, w["order"].id)
    row = _oi_row(db, world.company_id, inquiry.id, mirror.id, "ZZT-ITEM", QTY)
    db.commit()
    return row


@pytest.mark.parametrize("source", ["board", "autocount_cancel"])
def test_the_press_with_held_cancels_sends_no_automated_email(api, monkeypatch, source):
    from app.models.project_so import INQUIRY_CANCELLED, OrderInquiryRow

    from .test_order_inquiry_handover_automation import (
        _captured_dispatches,
        _handover_calls,
        _register,
    )

    client, world = api
    db = world.db
    _register(world)
    calls = _captured_dispatches(monkeypatch)
    w = _world(
        client, world, n_old=2, n_cancel=2, n_covered=1, n_open=0,
        autocount=source == "autocount_cancel",
    )
    rows = [_live_row_on(world, w, m) for _c, m in w["cancel"]]
    old_rows = (
        db.query(OrderInquiryRow)
        .filter(OrderInquiryRow.so_line_id.in_([m.id for _c, m in w["old"]]))
        .all()
    )
    assert old_rows, "the confirmed old lines raised ORDER rows the retire must cancel"
    calls.clear()
    outbox_before = _outbox_count(db)

    result = _press(client, w, cancel=w["cancel"])

    assert result["planning_change_applied"] is True
    assert _handover_calls(calls) == []
    assert [c for c in calls if c["trigger_type"] == CHANGED_WITH_LINKS] == []
    assert _outbox_count(db) == outbox_before
    # Purchasing still sees it in the CRM: every row on a cancelled or retired line is cancelled.
    db.expire_all()
    for row in [*rows, *old_rows]:
        assert db.get(OrderInquiryRow, row.id).state == INQUIRY_CANCELLED


def _spy(api, monkeypatch):
    from .test_order_inquiry_handover_automation import _captured_dispatches, _register

    _client, world = api
    _register(world)
    return _captured_dispatches(monkeypatch)


def _mail(calls, db, outbox_before):
    """What went out: handover dispatches, changed-with-links dispatches, new outbox rows."""
    from .test_order_inquiry_handover_automation import _handover_calls

    return (
        _handover_calls(calls),
        [c for c in calls if c["trigger_type"] == CHANGED_WITH_LINKS],
        _outbox_count(db) - outbox_before,
    )


@pytest.mark.parametrize("source", ["board", "autocount_cancel"])
def test_control_a_normal_cancel_so_press_still_emails(api, monkeypatch, source):
    """No pending change: a manual Cancel SO, or confirming an AutoCount-cancel draft, still
    hands its CANCEL list to purchasing (8 Oct rule, #1530)."""
    from .test_order_inquiry_handover_automation import _handover_calls

    client, world = api
    calls = _spy(api, monkeypatch)
    w = _world(
        client, world, n_old=0, n_cancel=1, n_covered=1, n_open=0,
        autocount=source == "autocount_cancel",
    )
    _live_row_on(world, w, w["cancel"][0][1])
    calls.clear()

    response = client.post(
        f"{BASE}/fulfilment-planning/confirm-all",
        json={
            "orders": [
                {
                    "pso_id": w["order"].id,
                    "lines": [],
                    "cancelled_lines": [
                        {"project_line_id": w["cancel"][0][1].id, "reason": REASON}
                    ],
                }
            ]
        },
    )

    assert response.status_code == 200, response.text
    assert len(_handover_calls(calls)) == 1


def test_control_a_batch_retire_without_held_cancels_still_emails(api, monkeypatch):
    """The book cancelled two confirmed lines and nothing was held: #1806's retire lines go."""
    from .test_order_inquiry_handover_automation import _handover_calls

    client, world = api
    calls = _spy(api, monkeypatch)
    w = _world(client, world, n_old=2, n_cancel=0, n_covered=1, n_open=0)
    calls.clear()

    result = _press(client, w)

    assert result["planning_change_applied"] is True
    assert len(_handover_calls(calls)) == 1
