"""SO-LINE-NUMBERS (`documentation/plans/scm/so-line-numbers-22oct-acceptance-criteria.md`).

Fulfilment planning names the number the customer's sales order carries (the core
`SalesOrderLine.line_no`), never the planning order's own `ProjectSalesOrderLine.line_no`.
Every fixture here gives the core line a number that DIFFERS from its mirror's, so a text
built from the wrong one cannot pass by coincidence. A core line with no number keeps the
mirror's (AC-10), which the existing suites already pin on data where the two agree.
"""
from __future__ import annotations

import pytest

from app.models.order import SalesOrderLine
from app.models.project_so import (
    DECISION_SUPERSEDED,
    IV_BORROW_SHORTFALL,
    IV_ORDER_BACK,
    OrderInquiryRow,
    SOSupplyDecision,
)
from app.services.project_supply_service import ProjectSupplyService

from ._borrow_mode import borrow_from_order_on
from ._pg_fixture import blank_session
from .scm.test_borrow_location_only import (
    _component_to_payload,
    _confirm_borrow,
    _order_backs,
    _reference,
    _step_two_borrow,
)
from .scm.test_ladder_v7_borrow import _borrow_world
from .test_planning_change_apply_on_board import api, world  # noqa: F401 - fixtures
from .test_planning_why_history import (  # noqa: F401 - fixtures
    _as_role as _history_as_role,
    _by_kind,
    _get,
    _seed,
)
from .test_planning_why_refusal import (  # noqa: F401 - fixtures
    ERROR,
    _as_role,
    _cleanup_refusal_audit_rows,
    _order_with_change,
    _press,
    _result,
)

ASKER_SO_LINE = 304
DONOR_SO_LINE = 224


def _renumber(db, line, core_no) -> None:
    """Give a mirror line's core line the AutoCount number the customer's order carries."""
    db.query(SalesOrderLine).filter(SalesOrderLine.id == line.core_sales_order_line_id).update(
        {SalesOrderLine.line_no: core_no}
    )
    db.commit()


# --------------------------------------------------------------------------- AC-3 / AC-4 / AC-5


def test_a_location_order_back_note_names_the_borrowing_lines_so_number():
    with blank_session() as db:
        world_ = _borrow_world(db)
        _renumber(db, world_["asker_line"], ASKER_SO_LINE)
        assert world_["asker_line"].line_no != ASKER_SO_LINE
        component = _step_two_borrow(db, world_)
        _confirm_borrow(
            db, world_, _component_to_payload(component, warehouse=world_["donor_bin"])
        )
        rows = _order_backs(db)
        note = rows[0].note
        expected = (
            f"Order-back: {world_['donor_bin'].warehouse_code} lent 30 to "
            f"{_reference(world_['asker'])} line {ASKER_SO_LINE}"
        )

    assert len(rows) == 1
    assert note == expected, note


@pytest.mark.usefixtures("ladder_steps_on")
def test_a_donor_order_borrow_names_so_numbers_in_the_donor_note_and_the_superseded_reason():
    with blank_session() as db:
        borrow_from_order_on(db)
        world_ = _borrow_world(db)
        _renumber(db, world_["asker_line"], ASKER_SO_LINE)
        _renumber(db, world_["donor_line"], DONOR_SO_LINE)
        component = _step_two_borrow(db, world_)
        donor_so = component["donor_so_number"]
        _confirm_borrow(
            db, world_, _component_to_payload(component, warehouse=world_["donor_bin"])
        )
        notes = [r.note for r in _order_backs(db)]
        superseded = [
            r.superseded_reason
            for r in db.query(SOSupplyDecision)
            .filter(
                SOSupplyDecision.project_sales_order_id == world_["donor_order"].id,
                SOSupplyDecision.state == DECISION_SUPERSEDED,
            )
            .all()
        ]
        reason = f"Borrowed by SO{_reference(world_['asker'])} line {ASKER_SO_LINE}"
        asker_ref = _reference(world_["asker"])

    # AC-4: the candidate the dialog lists names the donor's SO line.
    assert component["donor_line_no"] == DONOR_SO_LINE, component
    # AC-3: both ends of the order-back sentence.
    assert any(
        n == f"Order-back: {donor_so} line {DONOR_SO_LINE} lent 30 to {asker_ref} line {ASKER_SO_LINE}"
        or n.startswith(
            f"Order-back: {donor_so} line {DONOR_SO_LINE} lent 30 to {asker_ref} line {ASKER_SO_LINE} "
        )
        for n in notes
    ), notes
    # AC-5
    assert reason in superseded, superseded


def test_a_cross_group_borrow_order_back_names_the_so_number():
    from tests.scm.test_ladder_v4_group_netting import (
        _group_sites,
        _seed_line,
        _stock,
        _uid,
        _warehouse,
        _world,
        priority,
    )
    from app.schemas.project_supply import ConfirmLine, ConfirmSupplyBody

    with blank_session() as db:
        company_id, eling, project, product = _world(db)
        _group, sites = _group_sites(db)
        own, _pool = sites["BRW"]
        donor = _warehouse(db, f"ZZTMWH-IR{_uid()[:4]}")
        _stock(db, product, donor, on_hand=100)
        priority.create_revision(
            db, name=f"zzt-sln-{_uid()[:4]}", factors={}, demand_class_weights={},
            reorder_coverage_until=None,
        )
        db.commit()
        order, line, _cso, _cline = _seed_line(
            db, company_id, project, product, own, qty_ordered="40",
        )
        _renumber(db, line, ASKER_SO_LINE)
        ProjectSupplyService(db).confirm(
            order,
            ConfirmSupplyBody(
                lines=[
                    ConfirmLine(
                        project_line_id=line.id,
                        borrow=[
                            {
                                "source": "other_location",
                                "warehouse_id": str(donor.id),
                                "qty": "40",
                                "reason": "Urgent site delivery.",
                            }
                        ],
                    )
                ]
            ),
            actor_user_id=eling,
        )
        notes = [
            r.note
            for r in db.query(OrderInquiryRow)
            .filter(OrderInquiryRow.verb == IV_BORROW_SHORTFALL)
            .all()
        ]

    assert len(notes) == 1
    assert notes[0].endswith(f"line {ASKER_SO_LINE}"), notes


# --------------------------------------------------------------------------- AC-6


def test_the_change_refusal_and_row_out_carry_the_so_line_number(
    api, monkeypatch, _cleanup_refusal_audit_rows  # noqa: F811
):
    from app.services import planning_change_service

    _as_role(monkeypatch, "admin")
    fx = _order_with_change(api, line_no=592, seen=_cleanup_refusal_audit_rows)
    db = fx["world"].db
    _renumber(db, fx["line"], 604)

    result = _result(_press(fx, preview=False))
    out = planning_change_service.row_out(db, fx["row"])

    assert result["error"] == ERROR
    assert result["failing_lines"][0]["so_line_no"] == 604, result["failing_lines"]
    assert out["so_line_no"] == 604, out
    assert out["line_no"] == 592, "the sheet's own address keeps its meaning (AC-9)"


def test_the_history_sheet_names_so_line_numbers(api, monkeypatch):
    _history_as_role(monkeypatch, "admin")
    fx = _seed(api)
    db = fx["world"].db
    from app.models.project_so import ProjectSalesOrderLine

    mirror = {
        l.line_no: l
        for l in db.query(ProjectSalesOrderLine)
        .filter(ProjectSalesOrderLine.project_sales_order_id == fx["order"].id)
        .all()
    }
    _renumber(db, mirror[592], 1592)
    _renumber(db, mirror[700], 1700)

    events = _get(fx).json()["events"]
    rev1 = [e for e in _by_kind(events, "revision_confirmed") if e["revision_no"] == 1][0]
    rev2 = [e for e in _by_kind(events, "revision_confirmed") if e["revision_no"] == 2][0]
    update = _by_kind(events, "autocount_update")[0]

    assert 1592 in {l["so_line_no"] for l in rev1["lines"]}, rev1["lines"]
    assert 592 not in {l["so_line_no"] for l in rev1["lines"]}
    assert 1700 in {l["so_line_no"] for l in rev2["lines"]}, rev2["lines"]
    assert [l["so_line_no"] for l in update["lines"]] == [1592], update["lines"]
