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
* AC-G19's cases (round 2): a re-Confirm right after that Confirm changes nothing; a partial
  re-plan (only 236 onto 608) moves only what moved; a move onto a target that cannot take
  links is declined as in AC-G12; an origin received in full buys nothing twice; a plan with
  no `split_plan` stamp on its decision (as the dev DB holds it) re-plans like a stamped one.

Every row is seeded here (CI's database is empty) on the REAL database, rolled back
(`test_planning_change_apply_on_board.world`).
"""
from __future__ import annotations

from datetime import date, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

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
    D_167,
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
    """Every OI row of 480 / 608 / 752 with its links: (line no, id, verb, state, qty, date,
    links as (PO line, qty))."""
    from app.models.project_so import OrderInquiryRow
    from app.services.project_order_inquiry_service import ProjectOrderInquiryService

    svc = ProjectOrderInquiryService(s.db)
    return sorted(
        (no, str(r.id), r.verb, r.state, Decimal(str(r.qty)).normalize(), r.delivery_date,
         tuple(sorted((str(link.po_line_id), str(Decimal(str(link.qty)).normalize()))
                      for link in svc._links_of(r.id))))
        for no in OWNER_CASE
        for r in s.db.query(OrderInquiryRow).filter(OrderInquiryRow.so_line_id == s.line[no].id)
    )


def _assert_a_re_confirm_changes_nothing(s, emails):
    """AC-G13: a plain re-Confirm with no edit writes no OI row, moves no link and sends no
    handover email."""
    before = _snapshot(s)
    start = len(emails)
    _reconfirm(s)
    after = _snapshot(s)
    assert after == before, ("AC-G13: a second Confirm changes no OI row or link", before, after)
    resent = [(ln["qty"], ln["remark"]) for h in emails[start:] for ln in h.get("lines") or []]
    assert emails[start:] == [], ("AC-G13: a second Confirm sends no email", resent)


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


def _po_links(s, po):
    """Where the two owner POs' links sit: 480's PO on 480 / 608, 752's PO on 752 / 608."""
    return {
        "480 on 480": _linked(s, 480, po[480]), "480 on 608": _linked(s, 608, po[480]),
        "752 on 752": _linked(s, 752, po[752]), "752 on 608": _linked(s, 608, po[752]),
    }


def _card_replan():
    """AC-G19's drag, as the sheet saves it (every line sent, 608 with no splits): 236 and
    167 (date fixed to 20/11/2029) and 752's 37 onto 608, 467 back on 752 @ 02/01/2027."""
    return {**_owner_plan(), 608: []}


def _partial_replan():
    """AC-G19 partial: only 236 onto 608; 167 stays on New line at its stored date, 752's
    stored plan is sent as it stands."""
    return {
        480: [(14, D_480_NEW, 480, ""), (236, D_608, 608, ""), (167, D_167_STORED, "new", "")],
        608: [],
        752: STORED_PLAN[752],
    }


def _replan(s, emails, plan):
    """Save `plan` through the sheet's PUT, then the board's plain Confirm (nothing pending on
    the order, so no batch). Returns the handovers that Confirm sent."""
    _save(s, plan)
    start = len(emails)
    _reconfirm(s)
    return list(emails[start:])


def _scratch_card_plan(api, emails):
    """The card plan confirmed from scratch on a twin order (480 and 752 linked the same way):
    what AC-G19's re-plan must leave purchasing with."""
    scratch = _seed(api)
    _link_owner_rows(scratch)
    _save(scratch, _owner_plan())
    _confirm_batch(scratch, emails)
    want = _live_by_line(scratch)
    assert _owner_total(scratch) == _d("1295"), ("premise: the card plan from scratch", want)
    return want


def _strip_split_plan_stamps(s):
    """The dev DB's SO417636 decisions carry no `split_plan` stamp on any line snapshot (read
    off the shared dev DB, 19 Oct: 0 of 3, 3, 4 snapshots): drop the ones the Confirm wrote."""
    from sqlalchemy.orm.attributes import flag_modified

    from app.models.project_so import SOSupplyDecision

    decisions = (
        s.db.query(SOSupplyDecision)
        .filter(SOSupplyDecision.project_sales_order_id == str(s.order.id))
        .all()
    )
    for decision in decisions:
        if decision.line_snapshots:
            decision.line_snapshots = [
                {k: v for k, v in snapshot.items() if k != "split_plan"}
                for snapshot in decision.line_snapshots
            ]
            flag_modified(decision, "line_snapshots")
    s.db.commit()
    s.db.expire_all()
    stamped = [
        snapshot for decision in s.db.query(SOSupplyDecision)
        .filter(SOSupplyDecision.project_sales_order_id == str(s.order.id)).all()
        for snapshot in decision.line_snapshots or [] if "split_plan" in snapshot
    ]
    assert stamped == [], ("premise: no decision snapshot carries a split_plan stamp", stamped)


def _assert_no_cancel_anywhere(s, sent):
    """AC-G4: no CANCEL BALANCE on purchasing's worklist for 480 / 608 / 752, and no CANCEL in
    the email that Confirm sent or in the worklist Excel. Returns the Excel rows."""
    for no in OWNER_CASE:
        rows = _worklist(s, s.line[no])
        assert _cancel_balances(rows) == [], ("no CANCEL on the worklist", no, rows)
    assert not [x for x in _sent_remarks(sent) if "CANCEL" in x], _sent_remarks(sent)
    if sent:
        printed = _printed(sent)
        assert not [r for r in printed if any("CANCEL" in c for c in r)], printed
    excel = _excel_rows(s)
    assert not [r for r in excel if "CANCEL" in str(r[4])], ("no CANCEL in the Excel", excel)
    return excel


def _assert_the_card_plan(s, po, sent, want):
    """AC-G19: purchasing's live OI rows equal the card plan confirmed from scratch (`want`),
    1295 in all, 608 totals 632, no 37 left on 752, 752's extra 182 "ORDER 182", 608 REMAIN,
    the moved rows keep their links, no CANCEL anywhere."""
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

    got = _po_links(s, po)
    assert got == {
        "480 on 480": _d("14"), "480 on 608": _d("403"),
        "752 on 752": _d("467"), "752 on 608": _d("37"),
    }, ("the moved rows keep their links", got)

    excel = _assert_no_cancel_anywhere(s, sent)
    assert _has_block(excel, EXCEL_752), ("752: 37 / 467 / extra 182", excel)
    assert EXCEL_608 in excel, ("608: 192 -> 632 REMAIN", excel)


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

    _assert_a_re_confirm_changes_nothing(s, emails)


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
    want = _scratch_card_plan(api, emails)
    s, po = _dev_db_case(api, emails, linked=True)
    sent = _replan(s, emails, _card_replan())
    _assert_the_card_plan(s, po, sent, want)


def test_g19_a_re_confirm_after_the_card_re_plan_changes_nothing(api, emails):
    """AC-G19 / AC-G13: right after the Confirm that applied the card re-plan, a second
    Confirm with no edit writes no OI row, moves no link and sends no email."""
    s, _po = _dev_db_case(api, emails, linked=True)
    _replan(s, emails, _card_replan())
    _assert_a_re_confirm_changes_nothing(s, emails)


def test_g19_a_partial_re_plan_moves_only_what_moved(api, emails):
    """AC-G19 partial: from the confirmed stored plan only 236 is dragged onto 608 (167 stays
    on New line, 752's plan is sent as it stands). After Save + Confirm, 480 holds 14 and 167
    at their dates, 608 holds its own 192 plus the 236 and its extra 204 (632 in all, read
    "ORDER 204"), 752 is untouched, the 236 takes its link to 608 and nothing says CANCEL.
    The live total is 14 + 167 + 632 + 649 = 1462: AutoCount's 1295 plus the 167 still
    planned as a New-line delivery (AC-G10, lead ruling 19 Oct)."""
    s, po = _dev_db_case(api, emails, linked=True)
    before_752 = _live_by_line(s)[752]
    sent = _replan(s, emails, _partial_replan())

    live = _live_by_line(s)
    rows = {no: _worklist(s, s.line[no]) for no in OWNER_CASE}
    assert live[480] == sorted([(_d("14"), D_480_NEW), (_d("167"), D_167_STORED)]), (
        "480 holds 14 and 167 at their dates", rows[480])
    assert sum((q for q, _when in live[608]), Decimal(0)) == _d("632"), (
        "608 = own 192 + 236 + extra 204", rows[608])
    assert live[752] == before_752, ("a partial re-plan moves only what moved: 752 untouched",
                                     before_752, rows[752])
    assert _owner_total(s) == _d("1462"), (
        "live total = AutoCount 1295 + the 167 New-line delivery", live)

    l608 = _line(_get(s), s, 608)
    assert _q(l608["extra_qty"]) == _d("204"), ("632 - 192 - 236", l608["extra_qty"])
    assert l608["extra_remark"] == "ORDER 204", l608["extra_remark"]

    got = _po_links(s, po)
    assert got == {
        "480 on 480": _d("181"), "480 on 608": _d("236"),
        "752 on 752": _d("504"), "752 on 608": _d("0"),
    }, ("the links follow the moved 236 only", got)
    _assert_no_cancel_anywhere(s, sent)


def _target_cannot_take_links(s, case):
    """AC-G12's two declines, as round 3 sets them (`test_line_splits_confirm`): 608's live
    ORDER row is placed with no link, or linked to a document received in full."""
    from app.models.project_so import INQUIRY_PLACED

    row = _order_row(s.world, s.line[608])
    if case == "target_placed_no_link":
        row.state = INQUIRY_PLACED
    else:
        _po, po_line = _po_line(s.world, _supplier(s.world), qty=row.qty,
                                expected_date=date(2026, 11, 10))
        _link(s.world, row, po_line, qty=row.qty, document=f"ZZT-S0608-{str(s.order.id)[:4]}")
        po_line.qty_received = Decimal(str(row.qty))
    s.db.commit()


def _held_cancels(s, no):
    """The CANCEL BALANCE qty line `no` still holds on purchasing's worklist (not cancelled)."""
    from app.models.project_so import INQUIRY_CANCELLED

    return [q for state, q in _cancel_balances(_worklist(s, s.line[no]))
            if state != INQUIRY_CANCELLED]


@pytest.mark.parametrize("case", ["target_placed_no_link", "target_received_in_full"])
def test_g19_a_re_plan_onto_a_target_that_cannot_take_links_is_declined(api, emails, case):
    """AC-G19 / AC-G12, crew ruling (a) 19 Oct (owner rule: no CANCEL from splits, ever):
    608's row cannot take links when 236 is dragged onto it, and 608 already holds a placed
    or received 632. The move is declined: 480 keeps its rows (14 / 236 / 167) and the PO's 417
    of links, no link reaches 608, and 608 keeps the 632 it holds (its need never drops below
    what it holds). No CANCEL BALANCE on the worklist, no CANCEL in the email or the Excel, no
    ORDER raised, and the live total stays 14 + 236 + 167 + 632 + 649 = 1698."""
    from app.models.project_so import INQUIRY_CANCELLED, IV_ORDER, OrderInquiryRow

    def orders():
        return {
            str(r.id): Decimal(str(r.qty))
            for no in OWNER_CASE
            for r in s.db.query(OrderInquiryRow).filter(
                OrderInquiryRow.so_line_id == s.line[no].id,
                OrderInquiryRow.verb == IV_ORDER,
                OrderInquiryRow.state != INQUIRY_CANCELLED,
            )
        }

    s, po = _dev_db_case(api, emails, linked=True)
    _target_cannot_take_links(s, case)
    before = _live_by_line(s)
    before_orders = orders()
    for no in OWNER_CASE:
        assert _held_cancels(s, no) == [], ("premise: no CANCEL BALANCE yet", case, no)
    sent = _replan(s, emails, _partial_replan())

    live = _live_by_line(s)
    assert live[480] == before[480], ("AC-G12: the origin keeps its rows", case, before[480],
                                      live[480])
    assert sorted(q for q, _when in live[480]) == [_d("14"), _d("167"), _d("236")], (
        "480 holds 14 / 236 / 167", case, live[480])
    assert _linked(s, 480, po[480]) == _d("417"), ("AC-G12: the origin keeps its links", case,
                                                   _po_links(s, po))
    assert _linked(s, 608, po[480]) == _d("0"), ("no link moves onto 608", case, _po_links(s, po))
    assert live[608] == before[608], ("608 keeps the 632 it holds", case, before[608], live[608])
    assert sum((q for q, _when in live[608]), Decimal(0)) == _d("632"), (case, live[608])

    for no in OWNER_CASE:
        assert _held_cancels(s, no) == [], ("no CANCEL BALANCE from the declined move", case,
                                            no, _worklist(s, s.line[no]))
    told = [(ln["qty"], ln["remark"]) for h in sent for ln in h.get("lines") or []]
    assert not [x for x in told if "CANCEL" in str(x[1])], ("no CANCEL in the email", case, told)
    if sent:
        printed = _printed(sent)
        assert not [r for r in printed if any("CANCEL" in c for c in r)], (case, printed)
    xl = _excel_rows(s)
    assert not [r for r in xl if "CANCEL" in str(r[4])], ("no CANCEL in the Excel", case, xl)

    after_orders = orders()
    raised = {i: q for i, q in after_orders.items()
              if i not in before_orders or q > before_orders[i]}
    assert raised == {}, ("nothing is ordered: no new or grown ORDER row", case, raised)
    assert _owner_total(s) == _d("1698"), (
        "live total 14 + 236 + 167 + 632 + 649", case, _owner_total(s), live)


def test_g19_a_re_plan_off_an_origin_received_in_full_buys_nothing_twice(api, emails):
    """AC-G19: 480's PO (417, linked across its 14 / 236 / 167 rows) is received in full, then
    the card re-plan drags 236 and 167 onto 608. Nothing is bought twice (live OI total =
    AutoCount 1295), nothing is cancelled, and the worklist and the Excel agree (the Excel's
    TOTAL QTY is the live total).

    The UAC pins no rows for this case, so only these invariants are asserted; "the email
    agrees" is checked as no CANCEL in it, nothing finer."""
    from tests.scm.test_line_splits_round3 import _sheet

    s, po = _dev_db_case(api, emails, linked=True)
    po[480].qty_received = Decimal("417")
    s.db.commit()
    sent = _replan(s, emails, _card_replan())

    live = _live_by_line(s)
    assert _owner_total(s) == _d("1295"), ("nothing bought twice: live OI = AutoCount", live)
    _assert_no_cancel_anywhere(s, sent)
    heads, rows = _sheet(s)
    at = heads.index("TOTAL QTY")
    totals = [r[at] for r in rows if r[at] not in (None, "")]
    assert totals == [float(_owner_total(s))], ("the Excel's TOTAL QTY is the live total",
                                                totals, live)


def test_g19_an_unstamped_applied_plan_re_planned_into_the_card_plan(api, emails):
    """AC-G19, stamped or not: the dev DB's SO417636 decisions carry no `split_plan` stamp. A
    plan with none counts as re-planned once: the card re-plan leaves purchasing the card plan
    from scratch row for row (as test_g19 above), and a re-Confirm with no edit right after
    changes nothing."""
    want = _scratch_card_plan(api, emails)
    s, po = _dev_db_case(api, emails, linked=True)
    _strip_split_plan_stamps(s)
    sent = _replan(s, emails, _card_replan())
    _assert_the_card_plan(s, po, sent, want)
    _assert_a_re_confirm_changes_nothing(s, emails)


# ---------------------------------------------------------------------------
# AC-G19 review round on e984225feb (reviewer NOT READY; lead rulings in the UAC at 3214f8ef0a)
# ---------------------------------------------------------------------------


def _uncover(s, nos):
    """The board's Reject of these lines, the call `fulfilment_planning.py` (~:1416) makes for
    a withdrawal-only press: `ProjectSupplyService.uncover_lines` with the joined reason and
    each line's own."""
    from app.services.project_supply_service import ProjectSupplyService

    ids = [str(s.line[no].id) for no in nos]
    covered = ProjectSupplyService(s.db).uncover_lines(
        s.order, ids, actor_user_id=s.world.actor,
        reason="; ".join(f"Line {no} rejected: site on hold" for no in nos),
        reason_by_line={line_id: "Site on hold" for line_id in ids},
    )
    assert covered, "premise: the active decision covers the rejected lines"
    s.db.commit()
    s.db.expire_all()


@pytest.mark.parametrize("re_confirm", [False, True],
                         ids=["guard_after_the_confirm", "after_a_standing_re_confirm"])
def test_g19_a_board_reject_after_a_standing_re_confirm_retires_every_row(api, emails, re_confirm):
    """Reviewer B1 / AC-G19: the owner's plan confirmed (live 14 / 632 / 649), then a plain
    re-Confirm with no edit (every line stands, AC-G13), then the board's Reject of 480, 608
    and 752. Every live OI row of the three lines is retired, the way it is without the
    standing re-Confirm (the guard). It stood RAISED at 14, 632 and 649."""
    s = _seed(api)
    _save(s, _owner_plan())
    _confirm_batch(s, emails)
    assert _owner_total(s) == _d("1295"), ("premise: the owner's plan applied",
                                           _live_by_line(s))
    if re_confirm:
        _assert_a_re_confirm_changes_nothing(s, emails)
    _uncover(s, list(OWNER_CASE))
    live = _live_by_line(s)
    assert live == {480: [], 608: [], 752: []}, (
        "the Reject retires every live OI row of 480 / 608 / 752", re_confirm,
        {no: _worklist(s, s.line[no]) for no in OWNER_CASE})


def _link_each_480_row(s):
    """480's live ORDER rows (14 / 236 / 167 after the stored plan's Confirm), each linked to
    a PO of its own for its own qty. Returns {qty: PO line}."""
    from app.models.project_so import INQUIRY_CANCELLED, IV_ORDER, OrderInquiryRow

    rows = (
        s.db.query(OrderInquiryRow)
        .filter(OrderInquiryRow.so_line_id == s.line[480].id, OrderInquiryRow.verb == IV_ORDER,
                OrderInquiryRow.state != INQUIRY_CANCELLED)
        .all()
    )
    by_qty = {int(Decimal(str(r.qty))): r for r in rows}
    assert sorted(by_qty) == [14, 167, 236], ("premise: 480 holds a 14, a 236 and a 167 row",
                                              _worklist(s, s.line[480]))
    out = {}
    for qty, row in by_qty.items():
        _po, po_line = _po_line(s.world, _supplier(s.world), qty=qty,
                                expected_date=date(2026, 10, 10))
        _link(s.world, row, po_line, qty=qty, document=f"ZZT-S0480-{qty}-{str(s.order.id)[:4]}")
        out[qty] = po_line
    s.db.commit()
    return out


def _rows_480(s):
    """480's live rows: (qty, date) -> (row id, links as (PO line, qty))."""
    from app.models.project_so import INQUIRY_CANCELLED, IV_CANCEL_BALANCE, OrderInquiryRow
    from app.services.project_order_inquiry_service import ProjectOrderInquiryService

    svc = ProjectOrderInquiryService(s.db)
    return {
        (Decimal(str(r.qty)).normalize(), r.delivery_date): (
            str(r.id),
            tuple(sorted((str(link.po_line_id), Decimal(str(link.qty)).normalize())
                         for link in svc._links_of(r.id))),
        )
        for r in s.db.query(OrderInquiryRow).filter(
            OrderInquiryRow.so_line_id == s.line[480].id,
            OrderInquiryRow.state != INQUIRY_CANCELLED,
            OrderInquiryRow.verb != IV_CANCEL_BALANCE,
        )
    }


def test_g19_a_re_plan_whose_split_row_is_received_is_declined_and_moves_nothing_else(
    api, emails
):
    """Reviewer B2 / AC-G19: from the confirmed stored plan, each of 480's rows (14 / 236 /
    167) is linked to a PO of its own, and only the 236's is received in full. 236 is then
    dragged onto 608 (167 stays on New line). The 236's row cannot move, so the move is
    declined (AC-G12): 480 keeps the 14 and the 167 on the same rows with their own links,
    nothing of 480's reaches 608, and any 14 or 167 the email tells is a row the worklist
    holds at that date."""
    s, _po = _dev_db_case(api, emails)
    pos = _link_each_480_row(s)
    pos[236].qty_received = Decimal("236")
    s.db.commit()
    before = _rows_480(s)
    sent = _replan(s, emails, _partial_replan())

    after = _rows_480(s)
    for key in ((_d("14"), D_480_NEW), (_d("167"), D_167_STORED)):
        assert after.get(key) == before[key], (
            "480 keeps the row and its links", key, before[key], after.get(key))
    assert _live_by_line(s)[480] == sorted(before), (
        "AC-G12: the declined 236 stays on 480 too", sorted(before), _worklist(s, s.line[480]))
    moved = {qty: _linked(s, 608, pos[qty]) for qty in pos}
    assert moved == {14: _d("0"), 167: _d("0"), 236: _d("0")}, (
        "nothing of 480's moves onto 608", moved)
    held = {(str(q.normalize()) if q == q.to_integral_value() else str(q), when.strftime("%d/%m/%Y"))
            for q, when in _live_by_line(s)[480]}
    told = [(ln["qty"], ln["delivery_date"]) for h in sent for ln in h.get("lines") or []
            if ln["qty"] in ("14", "167")]
    assert [x for x in told if x not in held] == [], (
        "the email tells 14 / 167 as the worklist holds them", told, sorted(held))


def test_g19_re_planning_one_moved_split_moves_only_its_links(api, emails):
    """Reviewer B2 / AC-G19: the card plan confirmed from scratch (links 480 on 480 14, on
    608 403; 752 on 752 467, on 608 37), then the 167 re-planned from 608 onto 752 and
    confirmed. Only the 167's links move, 608 -> 752. 480's own 14 stays on the same row with
    its link, and no fresh unlinked ORDER 14 appears on 480."""
    s = _seed(api)
    po = _link_owner_rows(s)
    _save(s, _owner_plan())
    _confirm_batch(s, emails)
    assert _po_links(s, po) == {
        "480 on 480": _d("14"), "480 on 608": _d("403"),
        "752 on 752": _d("467"), "752 on 608": _d("37"),
    }, ("premise: the card plan's links", _po_links(s, po))
    own_14 = _rows_480(s)
    assert list(own_14) == [(_d("14"), D_480_NEW)], ("premise: 480 holds its 14 row", own_14)

    _replan(s, emails, {
        480: [(14, D_480_NEW, 480, ""), (236, D_608, 608, ""), (167, D_167, 752, "")],
        752: [(37, D_608, 608, ""), (467, D_752_NEW, 752, "")],
        608: [],
    })
    got = {**_po_links(s, po), "480 on 752": _linked(s, 752, po[480])}
    assert got == {
        "480 on 480": _d("14"), "480 on 608": _d("236"), "480 on 752": _d("167"),
        "752 on 752": _d("467"), "752 on 608": _d("37"),
    }, ("only the 167's links move from 608 to 752", got)
    assert _rows_480(s) == own_14, (
        "480's own 14 stays on its row with its link; no fresh unlinked ORDER 14", own_14,
        _rows_480(s), _worklist(s, s.line[480]))


@pytest.mark.parametrize("case", ["target_placed_no_link", "target_received_in_full"])
def test_g19_a_re_confirm_after_a_declined_move_changes_nothing(api, emails, case):
    """Reviewer B3 / AC-G19, crew ruling (a): after the re-plan whose move onto 608 was
    declined (no CANCEL, nothing ordered), a plain re-Confirm with no edit changes nothing:
    the same rows and links, no CANCEL of any kind (no CANCEL BALANCE, no "CANCEL ALL"), and
    no email."""
    s, _po = _dev_db_case(api, emails, linked=True)
    _target_cannot_take_links(s, case)
    _replan(s, emails, _partial_replan())
    before = _snapshot(s)

    start = len(emails)
    _reconfirm(s)
    after = _snapshot(s)
    told = [(ln["qty"], ln["remark"]) for h in emails[start:] for ln in h.get("lines") or []]
    for no in OWNER_CASE:
        assert _held_cancels(s, no) == [], ("no CANCEL BALANCE", case, no,
                                            _worklist(s, s.line[no]))
    assert not [x for x in told if "CANCEL" in str(x[1])], (
        "no CANCEL of any kind (CANCEL ALL included)", case, told)
    assert after == before, ("AC-G13: a re-Confirm changes no OI row or link", case, before,
                             after)
    assert emails[start:] == [], ("AC-G13: a re-Confirm sends no email", case, told)


def test_g19_a_kept_row_that_moves_whole_leaves_nothing_behind(api, emails):
    """Reviewer S2 / AC-G19: 752's 37 is a kept row of its own (the owner seed with 752 = 37
    own @ 20/11/2026 + 467 own @ 02/01/2027, 480 on the card plan, all confirmed, 752's PO
    for 504 linked across 37 + 467; the 467 is saved first so 752's AutoCount extra 145 joins
    its row, not the 37's). The 37 is then dragged whole onto 608 (the card plan)
    and confirmed: no live 37 row is left on 752, 608 holds the 37 with its link, and nothing
    is raised twice (608 632, 752 649, live total 1295)."""
    s = _seed(api)
    po = _link_owner_rows(s)
    _save(s, {**_owner_plan(), 752: [(467, D_752_NEW, 752, ""), (37, D_608, 752, "")]})
    _confirm_batch(s, emails)
    assert (_d("37"), D_608) in _live_by_line(s)[752], (
        "premise: 752's 37 is a row of its own", _worklist(s, s.line[752]))
    assert _linked(s, 752, po[752]) == _d("504"), ("premise: 752 holds its PO's 504",
                                                   _po_links(s, po))

    _replan(s, emails, _card_replan())
    live = _live_by_line(s)
    assert not [q for q, _when in live[752] if q == _d("37")], (
        "the whole 37 row leaves 752", _worklist(s, s.line[752]))
    assert _linked(s, 608, po[752]) == _d("37"), ("608 holds the 37 with its link",
                                                  _po_links(s, po))
    assert _linked(s, 752, po[752]) == _d("467"), ("752 keeps 467 of its PO", _po_links(s, po))
    assert sum((q for q, _when in live[608]), Decimal(0)) == _d("632"), _worklist(s, s.line[608])
    assert sum((q for q, _when in live[752]), Decimal(0)) == _d("649"), _worklist(s, s.line[752])
    assert _owner_total(s) == _d("1295"), ("nothing raised twice", live)
