"""OI-LINE-SPLIT AC-G18 / AC-G19 (UAC section G, lead 19 Oct): refer back reads every applied
change whatever its batch says, and a confirmed New-line plan re-planned into the card plan.

Contract: `documentation/plans/scm/oi-line-split-16oct-acceptance-criteria.md` AC-G18 and AC-G19,
with the AC-G1, AC-G3, AC-G6, AC-G10, AC-G13 and AC-G14 they cite. Found on the owner's real
SO417636 before the hand test. The board Confirm applies one order at a time and stamps the
AutoCount batch's `applied_at` only when nothing in the WHOLE batch is still pending
(`planning_change_service.py` ~:5178), and a line AutoCount added and then changed inside one
open batch carries an empty `from` on its later change row. Seeded here:

* T1 (AC-G18, open batch): the round-3 owner seed (`test_line_splits_round3._seed`, the
  owner's plan), its batch also holding a still-reachable pending row of a SECOND order, so
  SO-1's Confirm leaves the batch's `applied_at` NULL.
* T2 (AC-G18, empty `from`): the dev DB's shape as stored (SO417636 CSK14B, read off the shared
  dev DB read-only on 19 Oct): each line's older `added` row (no mirror line, its
  `core_line_id`, superseded) carries the before in its `to`; the later change rows carry a
  null-valued `from`, are applied by SO-1's Confirm and sit in a batch whose `applied_at`
  stays NULL; the owner's stored splits (480 = 14 own + 236 and 167 @ 20/01/2026 on New line;
  752 = 37 own @ 02/01/2027 + 467 @ 20/12/2026 on New line).
* T3 (AC-G19): from T2's confirmed state, the card plan saved through the sheet's PUT and
  confirmed leaves purchasing the same live rows as the card plan confirmed from scratch on a
  twin order.

Every row is seeded here (CI's database is empty) on the REAL database, rolled back
(`test_planning_change_apply_on_board.world`).
"""
from __future__ import annotations

from datetime import date, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from app.models.planning_change import (
    PLANNING_CHANGE_KIND_ADDED,
    PLANNING_CHANGE_KIND_DELAYED,
    PLANNING_CHANGE_STATE_APPLIED,
    PLANNING_CHANGE_STATE_PENDING,
    PLANNING_CHANGE_STATE_SUPERSEDED,
    PlanningChangeBatch,
    PlanningChangeRow,
)
from app.services.scm.outstanding_diff import QTY_CHANGED
from tests.scm.test_line_splits_outputs import emails  # noqa: F401 - the SENT handover
from tests.scm.test_line_splits_round3 import (
    D_480_NEW,
    D_608,
    D_752,
    D_752_NEW,
    EXCEL_608,
    EXCEL_752,
    EXPECTED_FIGURES,
    OWNER_CASE,
    _cancel_balances,
    _confirm_batch,
    _d,
    _excel_rows,
    _figures,
    _get,
    _has_block,
    _line,
    _live_by_line,
    _owner_plan,
    _owner_total,
    _printed,
    _q,
    _reconfirm,
    _save,
    _seed,
    _sent_remarks,
    _worklist,
)
from tests.test_oi_handover_excel import stored  # noqa: F401 - autouse storage stub
from tests.test_planning_change_apply_on_board import (  # noqa: F401 - fixtures reused
    _build,
    _change,
    _confirm,
    _link,
    _order_row,
    _po_line,
    _supplier,
    api,
    world,
)
from tests.test_planning_changes import (
    _core_line,
    _core_so,
    _line_payload,
    _product,
    _project_line,
    _project_so,
)

#: The owner's stored 167 date (the AC-G8 mistype, as the dev DB holds it).
D_167_STORED = date(2026, 1, 20)
D_OTHER = date(2026, 12, 1)

#: SO417636 CSK14B's splits as the dev DB stores them (AC-G18).
STORED_PLAN = {
    480: [(14, D_480_NEW, 480, ""), (236, D_608, "new", ""), (167, D_167_STORED, "new", "")],
    752: [(37, D_752_NEW, 752, ""), (467, D_752, "new", "")],
}

#: `from_json` of the dev DB's applied change rows: every field null (`_from_to` of an ADDED
#: change, carried onto the later row by `build_batch`'s fold).
NULL_SIDE = {"qty": None, "status": None, "item_code": None, "required_date": None}


# ---------------------------------------------------------------------------
# seeding
# ---------------------------------------------------------------------------


def _so1_rows(s):
    """SO-1's live (not superseded) change rows in its batch, by line no (`_seed` writes one
    per line)."""
    by_line = {str(s.line[no].id): no for no in OWNER_CASE}
    rows = (
        s.db.query(PlanningChangeRow)
        .filter(
            PlanningChangeRow.batch_id == str(s.batch.id),
            PlanningChangeRow.project_line_id.in_(list(by_line)),
            PlanningChangeRow.applied_state != PLANNING_CHANGE_STATE_SUPERSEDED,
        )
        .all()
    )
    out = {by_line[str(r.project_line_id)]: r for r in rows}
    assert sorted(out) == sorted(OWNER_CASE), ("premise: one change row per line", out)
    return out


def _hold_the_batch_open(s):
    """A second order (its own item, one line confirmed as Buy 10) whose AutoCount line then
    goes 10 -> 25. Its pending row joins SO-1's batch, the way one upload naming both orders
    writes it. Nobody confirms it, so SO-1's Confirm leaves the batch's `applied_at` NULL."""
    db, world = s.db, s.world
    core_so = _core_so(db, world.company_id)
    order = _project_so(db, world.project, so_id=core_so.id, autocount_doc_no=core_so.so_number)
    item = _product(db)
    core = _core_line(db, core_so, item, world.own_wh, qty_ordered="10", required_date=D_OTHER)
    line = _project_line(db, order, line_no=1, product=item, core_line=core)
    db.commit()
    r = _confirm(s.client, order.id, [_line_payload(line.id, buy_qty="10")])
    assert r.status_code == 200, f"premise: the second order's Confirm saves: {r.text}"
    core.qty_ordered, line.qty = Decimal("25"), Decimal("25")
    db.commit()
    built = _build(world, [_change(QTY_CHANGED, core, so_number=core_so.so_number,
                                   old_date=D_OTHER, new_date=D_OTHER, old_qty="10",
                                   new_qty="25")], core_so, [str(core.id)])
    assert built is not None, "premise: the second order's change is a pending row"
    rows = db.query(PlanningChangeRow).filter(PlanningChangeRow.batch_id == str(built.id)).all()
    assert len(rows) == 1, ("premise: one pending row for the second order", rows)
    rows[0].batch_id = str(s.batch.id)
    db.commit()
    s.other_row_id = str(rows[0].id)


def _assert_batch_left_open(s):
    """Premise after SO-1's Confirm: SO-1's rows applied, the second order's row still pending,
    so the batch reads NOT applied (`applied_at` NULL)."""
    s.db.expire_all()
    batch = s.db.get(PlanningChangeBatch, str(s.batch.id))
    assert batch.applied_at is None, (
        "premise: the batch stays open while the second order's row is pending", batch.applied_at)
    other = s.db.get(PlanningChangeRow, s.other_row_id)
    assert other.applied_state == PLANNING_CHANGE_STATE_PENDING, (
        "premise: the second order's row is still pending", other.applied_state)
    states = {no: r.applied_state for no, r in _so1_rows(s).items()}
    assert set(states.values()) == {PLANNING_CHANGE_STATE_APPLIED}, (
        "premise: SO-1's Confirm applied its own rows", states)


def _as_the_dev_db_stores_it(s):
    """SO-1's pending rows reshaped to the dev DB's SO417636 CSK14B: each line's older `added`
    row (no mirror line, matched by `core_line_id`, superseded "Replaced by a later change")
    carries the before (417 @ 20/10/2026, 192 @ 20/11/2026, 504 @ 20/12/2026) in its `to`,
    and the later change row's `from` is null-valued. 752 also keeps the dev DB's superseded
    middle edit (`delayed`, to 670 @ 02/01/2027): an older row of the line that is NOT its
    `added` row."""
    rows = _so1_rows(s)
    for no, ((qty, when), _after) in OWNER_CASE.items():
        row = rows[no]
        s.db.add(PlanningChangeRow(
            company_id=row.company_id, batch_id=row.batch_id,
            project_sales_order_id=row.project_sales_order_id, project_line_id=None,
            core_line_id=row.core_line_id, line_no=None, item_code=row.item_code,
            product_name=row.product_name, kind=PLANNING_CHANGE_KIND_ADDED,
            from_json=dict(NULL_SIDE),
            to_json={"qty": str(qty), "status": "open", "item_code": None,
                     "required_date": when.isoformat()},
            facts_json=dict(row.facts_json or {}),
            applied_state=PLANNING_CHANGE_STATE_SUPERSEDED,
            applied_reason="Replaced by a later change",
            created_at=row.created_at - timedelta(days=19),
        ))
        if no == 752:
            s.db.add(PlanningChangeRow(
                company_id=row.company_id, batch_id=row.batch_id,
                project_sales_order_id=row.project_sales_order_id,
                project_line_id=row.project_line_id, core_line_id=row.core_line_id,
                line_no=row.line_no, item_code=row.item_code, product_name=row.product_name,
                kind=PLANNING_CHANGE_KIND_DELAYED, from_json=dict(NULL_SIDE),
                to_json={"qty": "670", "status": "open", "item_code": None,
                         "required_date": D_752_NEW.isoformat()},
                facts_json=dict(row.facts_json or {}), held_json=row.held_json,
                applied_state=PLANNING_CHANGE_STATE_SUPERSEDED,
                applied_reason="Replaced by a later change",
                created_at=row.created_at - timedelta(minutes=19),
            ))
        row.from_json = dict(NULL_SIDE)
    s.db.commit()


def _link_owner_rows(s):
    """480's ORDER row linked to a PO for its 417, 752's to another PO for its 504."""
    out = {}
    for no, qty, expected in ((480, 417, date(2026, 10, 10)), (752, 504, date(2026, 12, 10))):
        _po, po_line = _po_line(s.world, _supplier(s.world), qty=qty, expected_date=expected)
        _link(s.world, _order_row(s.world, s.line[no]), po_line, qty=qty,
              document=f"ZZT-S0{no}-{str(s.order.id)[:4]}")
        out[no] = po_line
    s.db.commit()
    return out


def _dev_db_case(api, emails, *, linked=False):
    """SO417636 as the dev DB holds it, confirmed: the owner seed, the batch held open by a
    second order, SO-1's rows reshaped (empty `from`, older `added` rows), the stored splits
    saved through the sheet's PUT, then SO-1's batch Confirm. Returns (s, PO lines or None)."""
    s = _seed(api)
    po_lines = _link_owner_rows(s) if linked else None
    _hold_the_batch_open(s)
    _as_the_dev_db_stores_it(s)
    _save(s, STORED_PLAN)
    pending = _get(s)
    for no, expected in EXPECTED_FIGURES.items():
        assert _figures(_line(pending, s, no)) == expected, (
            no, "premise: the pending read (UAC B2) finds the before on the line's added row",
            _figures(_line(pending, s, no)))
    _confirm_batch(s, emails)
    _assert_batch_left_open(s)
    rows = _so1_rows(s)
    assert all((r.from_json or {}).get("qty") is None for r in rows.values()), (
        "premise: the applied change rows carry an empty from",
        {no: r.from_json for no, r in rows.items()})
    return s, po_lines


def _malaysia_day_of_last_confirm(s):
    from sqlalchemy import func

    from app.models.project_so import SOSupplyDecision

    when = (
        s.db.query(func.max(SOSupplyDecision.confirmed_at))
        .filter(SOSupplyDecision.project_sales_order_id == str(s.order.id))
        .scalar()
    )
    assert when is not None, "premise: a Confirm on record"
    return when.replace(tzinfo=timezone.utc).astimezone(ZoneInfo("Asia/Kuala_Lumpur")).date().isoformat()


def _snapshot(s):
    """Every OI row of 480 / 608 / 752: (line no, id, verb, state, qty, date)."""
    from app.models.project_so import OrderInquiryRow

    return sorted(
        (no, str(r.id), r.verb, r.state, Decimal(str(r.qty)).normalize(), r.delivery_date)
        for no in OWNER_CASE
        for r in s.db.query(OrderInquiryRow).filter(OrderInquiryRow.so_line_id == s.line[no].id)
    )


def _linked(s, no, po_line):
    """What line `no`'s live rows hold of `po_line`."""
    from app.models.project_so import INQUIRY_CANCELLED, OrderInquiryRow
    from app.services.project_order_inquiry_service import ProjectOrderInquiryService

    svc = ProjectOrderInquiryService(s.db)
    total = Decimal(0)
    for row in s.db.query(OrderInquiryRow).filter(
        OrderInquiryRow.so_line_id == s.line[no].id, OrderInquiryRow.state != INQUIRY_CANCELLED
    ):
        total += sum(
            (Decimal(str(link.qty)) for link in svc._links_of(row.id)
             if link.po_line_id == po_line.id),
            Decimal(0),
        )
    return total


# ---------------------------------------------------------------------------
# AC-G18 (a): the Confirm left the batch open
# ---------------------------------------------------------------------------


def test_g18_refer_back_holds_when_the_confirm_leaves_the_batch_open(api, emails):
    """The owner's plan confirmed from a batch that also holds a second order's pending row:
    SO-1's rows are applied but the batch's `applied_at` stays NULL. The sheet still reads
    the AC-G1 figures after the Confirm, 752's plan reads applied (not stale), and with
    nothing on SO-1 pending the status line carries the Confirm's Malaysia date."""
    s = _seed(api)
    _hold_the_batch_open(s)
    _save(s, _owner_plan())
    before = _get(s)
    assert before["confirmed_at"] is None, "a change is pending on SO-1: no Confirmed date"
    for no, expected in EXPECTED_FIGURES.items():
        assert _figures(_line(before, s, no)) == expected, (no, "before Confirm")

    _confirm_batch(s, emails)
    _assert_batch_left_open(s)
    after = _get(s)
    for no, expected in EXPECTED_FIGURES.items():
        assert _figures(_line(after, s, no)) == expected, (
            no, "AC-G18: after a Confirm that left the batch open the change still reads "
            "base -> new", _figures(_line(after, s, no)))
    assert _line(after, s, 752)["split_state"] == "applied", (
        "AC-G18: 752's plan is applied, not stale", _line(after, s, 752)["split_state"])
    assert after["confirmed_at"] == _malaysia_day_of_last_confirm(s), (
        "AC-G1 / AC-G13: nothing on SO-1 pending: Confirmed <Malaysia date>",
        after["confirmed_at"])


# ---------------------------------------------------------------------------
# AC-G18 (b): the applied change row has an empty `from`
# ---------------------------------------------------------------------------


def test_g18_refer_back_reads_an_applied_change_with_an_empty_from(api, emails):
    """The dev DB's SO417636 as stored: the applied change rows carry an empty `from`, their
    before sits on each line's own older `added` row, the batch is open. The sheet reads 480
    417 | 14 | 20/10/2026 | 20/09/2026; 608 192 | 632 | 20/11/2026 | blank; 752 504 | 649 |
    20/12/2026 | 02/01/2027 with its plan applied and an extra 649 - 37 - 467 = 145 ("ORDER
    145"); 608 has nothing dropped on it, so its REMARK is "ORDER 440"; 480 and 608 show no
    extra. A second Confirm with nothing changed writes no OI row and sends no email
    (AC-G13)."""
    s, _po = _dev_db_case(api, emails)
    out = _get(s)
    for no, expected in EXPECTED_FIGURES.items():
        assert _figures(_line(out, s, no)) == expected, (
            no, "AC-G18: the applied change with an empty from still reads base -> new",
            _figures(_line(out, s, no)))
    l480, l608, l752 = (_line(out, s, no) for no in (480, 608, 752))
    assert l752["split_state"] == "applied", ("AC-G18: 752's plan is applied, not stale",
                                              l752["split_state"])
    assert _q(l752["extra_qty"]) == _d("145"), ("649 - 37 - 467", l752["extra_qty"])
    assert l752["extra_remark"] == "ORDER 145", l752["extra_remark"]
    assert l608["remark_generated"] == "ORDER 440", (
        "nothing dropped on 608: its 192 -> 632 reads ORDER 440", l608["remark_generated"])
    assert l480["extra_qty"] is None, ("14 + 236 + 167 = 417: no extra", l480["extra_qty"])
    assert l608["extra_qty"] is None, ("608 is not split: no extra row", l608["extra_qty"])

    before = _snapshot(s)
    start = len(emails)
    _reconfirm(s)
    assert _snapshot(s) == before, ("AC-G13: a second Confirm changes no OI row", before,
                                    _snapshot(s))
    resent = [(ln["qty"], ln["remark"]) for h in emails[start:] for ln in h.get("lines") or []]
    assert emails[start:] == [], ("AC-G13: a second Confirm sends no email", resent)


# ---------------------------------------------------------------------------
# AC-G19: re-plan the confirmed New-line plan into the card plan
# ---------------------------------------------------------------------------


def test_g19_re_planning_the_stored_plan_into_the_card_plan_equals_it_from_scratch(api, emails):
    """From the stored plan above, confirmed (480 and 752 linked to their POs), staff drag 236
    and 167 (date fixed to 20/11/2029) and 752's 37 onto line 608, Save through the sheet's
    PUT (every line sent, 608 with no splits) and Confirm. Purchasing's live OI rows then
    equal the card plan confirmed from scratch on a twin order (live total 1295, 608 totals
    632, no 37 left on 752), 752 shows its extra 182 "ORDER 182", 608 reads REMAIN, the moved
    rows keep their links (nothing bought twice) and no CANCEL appears in the worklist, the
    email or the Excel."""
    scratch = _seed(api)
    _link_owner_rows(scratch)
    _save(scratch, _owner_plan())
    _confirm_batch(scratch, emails)
    want = _live_by_line(scratch)
    assert _owner_total(scratch) == _d("1295"), ("premise: the card plan from scratch", want)

    s, po = _dev_db_case(api, emails, linked=True)
    _save(s, {**_owner_plan(), 608: []})
    start = len(emails)
    _reconfirm(s)
    sent = list(emails[start:])

    live = _live_by_line(s)
    rows = {no: _worklist(s, s.line[no]) for no in OWNER_CASE}
    assert live == want, ("AC-G19: the live OI rows equal the card plan from scratch", live, want)
    assert _owner_total(s) == _d("1295"), ("nothing bought twice: 14 + 632 + 649", live)
    assert sum((q for q, _when in live[608]), Decimal(0)) == _d("632"), rows[608]
    assert not [q for q, _when in live[752] if q == _d("37")], ("the 37 left 752", rows[752])

    out = _get(s)
    l608, l752 = _line(out, s, 608), _line(out, s, 752)
    assert _q(l752["extra_qty"]) == _d("182"), ("649 - 467", l752["extra_qty"])
    assert l752["extra_remark"] == "ORDER 182", l752["extra_remark"]
    assert l608["remark_generated"] == "REMAIN", l608["remark_generated"]

    got = {
        "480 on 480": _linked(s, 480, po[480]), "480 on 608": _linked(s, 608, po[480]),
        "752 on 752": _linked(s, 752, po[752]), "752 on 608": _linked(s, 608, po[752]),
    }
    assert got == {
        "480 on 480": _d("14"), "480 on 608": _d("403"),
        "752 on 752": _d("467"), "752 on 608": _d("37"),
    }, ("the moved rows keep their links", got)

    for no in OWNER_CASE:
        assert _cancel_balances(rows[no]) == [], ("no CANCEL on the worklist", no, rows[no])
    assert not [x for x in _sent_remarks(sent) if "CANCEL" in x], _sent_remarks(sent)
    if sent:
        printed = _printed(sent)
        assert not [r for r in printed if any("CANCEL" in c for c in r)], printed
    excel = _excel_rows(s)
    assert not [r for r in excel if "CANCEL" in str(r[4])], ("no CANCEL in the Excel", excel)
    assert _has_block(excel, EXCEL_752), ("752: 37 / 467 / extra 182", excel)
    assert EXCEL_608 in excel, ("608: 192 -> 632 REMAIN", excel)
