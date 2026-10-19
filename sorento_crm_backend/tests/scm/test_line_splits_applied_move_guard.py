"""OI-LINE-SPLIT: Save refuses moving a confirmed split to another line until the AC-G19 lane.

Contract: `documentation/plans/scm/oi-line-split-16oct-acceptance-criteria.md`, AC-G19 "DEFERRED"
header, paragraph "Until that lane ships" (lead, 19 Oct): for a line whose plan a Confirm applied, a
Save may not change how much of that line sits on any OTHER SO line (dropping a split onto another
line, taking one off, or moving it between other lines). The Save answers 422 "Line <n>: a confirmed
split cannot move to another line." and stores nothing. The line's own-line and New-line rows can
still be edited (qty, date, remark), added or dropped (AC-G15, AC-G16, AC-G17). A plan never applied
can still be laid out freely (round 3).

Every Save goes through the sheet's own PUT (`_put`, the body `_save` builds). Seeded with the
round-3 owner case and the dev-DB shape of `test_line_splits_refer_back_applied`; Postgres only,
every row seeded here.
"""
from __future__ import annotations

from datetime import date

import pytest

from tests.scm.test_line_splits_api import _put, _sp
from tests.scm.test_line_splits_outputs import emails  # noqa: F401 - the SENT handover
from tests.scm.test_line_splits_refer_back_applied import (
    _card_replan,
    _dev_db_case,
    _snapshot,
    _strip_split_plan_stamps,
)
from tests.scm.test_line_splits_round3 import (
    D_167,
    D_480_NEW,
    D_608,
    D_752_NEW,
    TYPED,
    _confirm_batch,
    _new_line_plan,
    _on,
    _owner_plan,
    _save,
    _seed,
)
from tests.test_oi_handover_excel import stored  # noqa: F401 - autouse storage stub
from tests.test_planning_change_apply_on_board import api, world  # noqa: F401 - fixtures

PHRASE = "a confirmed split cannot move to another line"
D_167_EDIT = date(2029, 12, 20)


def _body(s, plan):
    """The sheet's PUT body for `plan` ({line no: [(qty, date, 480 | 608 | 752 | 'new' |
    'cancel', remark)]}), as `test_line_splits_round3._save` builds it."""
    body = []
    for no, parts in plan.items():
        splits = []
        for qty, when, on, remark in parts:
            if on == "cancel":
                splits.append(_sp(qty, None, on=_on(s, no), cancel=True, remark=remark))
            else:
                splits.append(_sp(qty, when, on=None if on == "new" else _on(s, on), remark=remark))
        body.append({"line_id": _on(s, no), "splits": splits})
    return body


def _stored_splits(s):
    """Every so_line_splits row of the order: (line no, seq, qty, date, cancel, sits on (line
    no or None), remark, base qty, base date)."""
    from decimal import Decimal

    from app.models.project_so import SOLineSplit

    no_of = {str(line.id): no for no, line in s.line.items()}
    return sorted(
        (
            no_of.get(str(r.so_line_id)), r.seq, Decimal(str(r.qty)).normalize(), r.delivery_date,
            bool(r.is_cancel), no_of.get(str(r.sits_on_line_id)) if r.sits_on_line_id else None,
            r.remark, Decimal(str(r.base_qty)).normalize(), r.base_date,
        )
        for r in s.db.query(SOLineSplit)
        .filter(SOLineSplit.project_sales_order_id == str(s.order.id))
        .all()
    )


def _split_audits(s):
    from app.models.audit import AuditLog
    from app.models.project_so import SOLineSplit

    return (
        s.db.query(AuditLog)
        .filter(
            AuditLog.entity_type == SOLineSplit.__audit_entity_type__,
            AuditLog.entity_id.in_([str(line.id) for line in s.line.values()]),
        )
        .count()
    )


def _assert_refused(s, plan, why):
    """The Save of `plan` answers 422 naming the line and the rule, and stores nothing: the
    order's split rows, its OI rows and the split audit trail are as they were."""
    splits, rows, audits = _stored_splits(s), _snapshot(s), _split_audits(s)
    r = _put(s, _body(s, plan))
    s.db.expire_all()
    assert r.status_code == 422, (why, "the Save is refused", r.status_code, r.text)
    message = str(r.json().get("message") or r.json().get("detail") or r.text)
    assert "Line" in message and PHRASE in message, (why, message)
    assert _stored_splits(s) == splits, (why, "no split row changed", splits, _stored_splits(s))
    assert _snapshot(s) == rows, (why, "no OI row changed")
    assert _split_audits(s) == audits, (why, "no audit row written")


def _assert_saved(s, plan, why):
    r = _put(s, _body(s, plan))
    assert r.status_code == 200, (why, "the Save is accepted", r.status_code, r.text)


def _stamped(s, no):
    """The newest decision's `split_plan` stamp for line `no`, or None."""
    from app.models.project_so import SOSupplyDecision

    decision = (
        s.db.query(SOSupplyDecision)
        .filter(SOSupplyDecision.project_sales_order_id == str(s.order.id))
        .order_by(SOSupplyDecision.revision_no.desc())
        .first()
    )
    return next(
        (snap.get("split_plan") for snap in (decision.line_snapshots or [])
         if str(snap.get("project_line_id")) == str(s.line[no].id)),
        None,
    )


def _new_line_plan_confirmed(api, emails):
    """The owner's New-line plan (480 = 14 own @ 20/09/2026, 236 @ 20/11/2026 and 167 @
    20/11/2029 on New line) saved and confirmed on current code."""
    s = _seed(api)
    _save(s, _new_line_plan())
    _confirm_batch(s, emails)
    return s


def _card_plan_confirmed(api, emails):
    """The card plan (480: 14 own, 236 and 167 on 608; 752: 37 on 608, 467 own) saved and
    confirmed from scratch."""
    s = _seed(api)
    _save(s, _owner_plan())
    _confirm_batch(s, emails)
    return s


# ---------------------------------------------------------------------------
# 1, 2: the card re-plan of an applied plan is refused, stamped or not
# ---------------------------------------------------------------------------


def test_the_card_re_plan_of_a_stamped_applied_plan_is_refused(api, emails):
    """The New-line plan applied (its decision carries the `split_plan` stamp), then the card
    re-plan drops 236 and 167 onto 608 and 752's 37 onto 608: 422 "Line <n>: a confirmed split
    cannot move to another line.", nothing stored. 752 was not split when the plan applied, so
    its part is laid against its current 649 (37 on 608 + 612 own), valid on its own: only
    480's move can refuse the Save."""
    s = _new_line_plan_confirmed(api, emails)
    assert _stamped(s, 480), ("premise: the Confirm stamped 480's plan", _stamped(s, 480))
    _assert_refused(s, {
        480: _owner_plan()[480],
        752: [(37, D_608, 608, ""), (612, D_752_NEW, 752, "")],
        608: [],
    }, "stamped card re-plan")


def test_the_card_re_plan_of_the_unstamped_dev_db_plan_is_refused(api, emails):
    """The dev DB's SO417636 as stored and confirmed (480 = 14 own + 236 and 167 on New line;
    752 = 37 own + 467 on New line), its decisions carrying no `split_plan` stamp: the card
    re-plan is refused the same way, nothing stored."""
    s, _po = _dev_db_case(api, emails)
    _strip_split_plan_stamps(s)
    _assert_refused(s, _card_replan(), "unstamped card re-plan")


# ---------------------------------------------------------------------------
# 3: each single kind of move is refused
# ---------------------------------------------------------------------------


def test_a_new_line_split_dropped_onto_another_line_is_refused(api, emails):
    """(a) The applied New-line plan's 167 is dropped onto 608 (14 own and 236 on New line
    stay): refused."""
    s = _new_line_plan_confirmed(api, emails)
    _assert_refused(s, {
        480: [(14, D_480_NEW, 480, ""), (236, D_608, "new", ""), (167, D_167, 608, "")],
        608: [],
        752: [],
    }, "New line -> 608")


def test_a_split_taken_back_off_another_line_is_refused(api, emails):
    """(b) The card plan confirmed from scratch; 608's 167 is taken back to New line: refused."""
    s = _card_plan_confirmed(api, emails)
    _assert_refused(s, {
        480: [(14, D_480_NEW, 480, ""), (236, D_608, 608, ""), (167, D_167, "new", "")],
        752: [(37, D_608, 608, ""), (467, D_752_NEW, 752, "")],
        608: [],
    }, "608 -> New line")


def test_a_split_moved_between_other_lines_is_refused(api, emails):
    """(c) The card plan confirmed from scratch; the 167 moves from 608 to 752: refused."""
    s = _card_plan_confirmed(api, emails)
    _assert_refused(s, {
        480: [(14, D_480_NEW, 480, ""), (236, D_608, 608, ""), (167, D_167, 752, "")],
        752: [(37, D_608, 608, ""), (467, D_752_NEW, 752, "")],
        608: [],
    }, "608 -> 752")


# ---------------------------------------------------------------------------
# 4: an applied plan's own-line and New-line rows can still be edited
# ---------------------------------------------------------------------------


EDITS = {
    # AC-G15: the owner's mistyped date fixed.
    "167_date": [(14, D_480_NEW, 480, ""), (236, D_608, "new", ""), (167, D_167_EDIT, "new", "")],
    # AC-G14 / AC-G17: own-line and New-line qty against the current 14.
    "own_and_new_line_qty": [(10, D_480_NEW, 480, ""), (4, D_608, "new", "")],
    # A remark only.
    "remark": [(14, D_480_NEW, 480, ""), (236, D_608, "new", TYPED), (167, D_167, "new", "")],
    # AC-G17: the 167's New-line row dropped (its qty joins the 236's; still 417 in all).
    "drop_new_line_row": [(14, D_480_NEW, 480, ""), (403, D_608, "new", "")],
}


@pytest.mark.parametrize("edit", sorted(EDITS))
def test_an_applied_plans_own_and_new_line_rows_can_still_be_edited(api, emails, edit):
    """The applied New-line plan (nothing of 480 on another line) edited without touching
    another line: the Save is accepted."""
    s = _new_line_plan_confirmed(api, emails)
    _assert_saved(s, {480: EDITS[edit], 608: [], 752: []}, edit)


# ---------------------------------------------------------------------------
# 5: a plan never applied can be laid out freely
# ---------------------------------------------------------------------------


def test_a_plan_never_applied_can_drop_splits_onto_other_lines(api, emails):
    """Round 3: with the AutoCount change still pending, the card plan (236 and 167 onto 608,
    752's 37 onto 608) saves, and a saved plan not yet confirmed can be laid out again (the
    New-line plan, then the card plan over it)."""
    s = _seed(api)
    _assert_saved(s, _owner_plan(), "card plan, never applied")
    _assert_saved(s, {**_new_line_plan(), 752: [], 608: []}, "re-laid as the New-line plan")
    _assert_saved(s, _card_replan(), "re-laid as the card plan again")
