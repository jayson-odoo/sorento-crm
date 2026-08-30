"""Ladder v7.1 - tester's gap suite, written beside the coder's own
`tests/scm/test_ladder_v7_borrow.py`.

Five cases the UAC calls for that the coder's suite either did not reach or reached only at
the schema level:

  (a) AC-S3-9 on `walk()`: the donor ledger across TWO units of one board, where the second
      unit is offered only the PARTIAL remainder (not zero, not the whole donor again).
  (b) AC-S3-5's other half: a superseded donor's line is RE-PROPOSED on its next board build,
      and the supersede reason is the exact sentence, not merely a prefix match.
  (c) AC-S3-10: a frozen v4/v5 snapshot naming `cross_group_borrow` still renders through the
      real board build, and the LIVE ladder is shown never to write that rung again.
  (d) AC-S3-14 through the response_model trap: `options[]` survives the actual BOARD ROUTE
      (`GET /fulfilment-planning/board`), not only a hand-built schema round-trip.
  (e) is already covered end-to-end by the coder's own
      `test_the_step_two_refusal_names_the_window_date` (goes through
      `FulfilmentBoardService.build` and asserts the day and year of the window date appear
      in the refusal sentence) - not repeated here.

Postgres via `blank_session`, every chain seeded here (CI's database has no data).
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from app.models.project_so import DECISION_ACTIVE, DECISION_SUPERSEDED, SOSupplyDecision
from app.schemas.project_supply import ConfirmLine, ConfirmSupplyBody
from app.services.project_supply_service import ProjectSupplyService

from .._pg_fixture import blank_session
from ..test_so_supply_confirmation import (  # noqa: F401  (helpers, not fixtures)
    _core_line,
    _core_so,
    _product,
    _project_line,
    _project_so,
    _sorento,
    _stock,
    _uid,
    _user,
    _warehouse,
)
from .test_ladder_v7_borrow import LEAD_DAYS, WINDOW_DAY, _borrow_world, _decide, _policy
from .test_project_supply_service_ladder import (
    REQUIRED_DATE,
    _components,
    _group_sites,
    _lead_time,
    _seed_line,
    _world,
)


def _seed_adopted_line(db, company_id, project, product, warehouse, *, qty_ordered, so_number):
    """`_seed_line`, but with the Project SO actually ADOPTING the core order
    (`projects.sales_orders.so_id`), which `_mirror_addressing` requires before the board
    will read a frozen decision back for it at all. `_seed_line` itself leaves `so_id` unset
    - fine for every other scenario here, which never reads `row.decision` - but this test
    needs the addressing so the board can find the frozen snapshot to render.
    """
    from app.models.project_so import SO_STATUS_PUBLISHED

    core_so = _core_so(db, company_id)
    core_so.so_number = so_number
    db.flush()
    core_line = _core_line(
        db, core_so, product, warehouse, qty_ordered=qty_ordered, required_date=REQUIRED_DATE,
    )
    order = _project_so(db, project, status=SO_STATUS_PUBLISHED, so_id=core_so.id)
    line = _project_line(db, order, line_no=10, product=product, core_line=core_line)
    db.commit()
    return order, line, core_so, core_line


# --------------------------------------------------------------------------- AC-S3-9


def test_a_donor_line_offers_only_what_is_left_to_the_second_unit_of_one_board():
    """AC-S3-9, the arithmetic the coder's own
    `test_one_donor_line_is_offered_once_across_the_walk_and_the_later_unit_buys` does not
    reach: that test drains the donor to EXACTLY zero, so "offered nothing" and "offered
    only what is left" read the same. Here the donor holds 15, the first unit of one board
    takes 10 (whole, borrow), and the second unit needs 8 with only 5 left - not the whole
    of it (buys) and not the zero a drained ledger would offer. `_whole_line_buy_reason`
    states the residual the ladder actually found, which is the only place this number
    reaches the wire, so it is the assertion.
    """
    with blank_session() as db:
        company_id, eling, project, product = _world(db)
        _group, sites = _group_sites(db)
        own, _pool = sites["BRW"]
        donor_bin = _warehouse(db, f"ZZTMWH-IB{_uid()[:3]}")
        _stock(db, product, donor_bin, on_hand=15)
        _lead_time(db, product, LEAD_DAYS)
        _policy(db)

        donor_order, donor_line, _a, _b = _seed_line(
            db, company_id, project, product, donor_bin, qty_ordered="15",
            required_date=date.today() + timedelta(days=WINDOW_DAY + 60), line_no=9,
            so_number=f"ZZTSO-DONOR{_uid()[:4]}",
        )
        _decide(db, donor_order, donor_line, donor_bin, "15", eling)

        core_so = _core_so(db, company_id)
        core_so.so_number = f"ZZTSO-TWOUNITS{_uid()[:4]}"
        db.flush()
        first_core = _core_line(
            db, core_so, product, own, qty_ordered="10", required_date=REQUIRED_DATE,
        )
        second_core = _core_line(
            db, core_so, product, own, qty_ordered="8",
            required_date=REQUIRED_DATE + timedelta(days=1),
        )
        asker = _project_so(db, project)
        _project_line(db, asker, line_no=1, product=product, core_line=first_core)
        _project_line(db, asker, line_no=2, product=product, core_line=second_core)
        db.commit()

        lines = ProjectSupplyService(db).proposal_for(asker)["lines"]
        first = [(c["kind"], c["qty"]) for c in lines[0]["components"]]
        second = [(c["kind"], c["qty"], c["reason"]) for c in lines[1]["components"]]

    assert first == [("borrow", "10")], first
    assert len(second) == 1
    kind, qty, reason = second[0]
    assert kind == "buy" and qty == "8", second
    assert "5" in reason and "8" in reason, (
        f"the second unit's Buy must state the 5 the donor had left, not 0 or 15: {reason!r}"
    )


# --------------------------------------------------------------------------- AC-S3-5


def test_a_superseded_donor_is_re_proposed_on_its_next_board_build():
    """AC-S3-5's other half, which the coder's
    `test_borrowing_from_a_decided_donor_supersedes_its_decision_and_raises_its_order_back`
    does not reach: it asserts the decision falls and an ORDER_BACK is raised, but never
    re-walks the donor's own order to see whether it is actually proposed again. It also
    only checks `reason.startswith("Borrowed by SO")`; here the sentence is matched exactly,
    line number included, as AC-S3-5 states it word for word.
    """
    with blank_session() as db:
        world = _borrow_world(db)
        service = ProjectSupplyService(db)
        proposal = service.proposal_for(world["asker"])
        component = _components(proposal)[0]

        ProjectSupplyService(db).confirm(
            world["asker"],
            ConfirmSupplyBody(
                lines=[
                    ConfirmLine(
                        project_line_id=world["asker_line"].id,
                        borrow=[
                            {
                                "source": "other_location",
                                "warehouse_id": str(world["donor_bin"].id),
                                "qty": component["qty"],
                                "reason": "Ladder v7.1 step 2.",
                                "donor_core_line_id": component["donor_core_line_id"],
                                "donor_so_number": component["donor_so_number"],
                                "donor_line_no": component["donor_line_no"],
                                "donor_required_date": component["donor_required_date"],
                            }
                        ],
                    )
                ]
            ),
            actor_user_id=world["eling"],
        )
        db.commit()

        decision = (
            db.query(SOSupplyDecision)
            .filter(SOSupplyDecision.project_sales_order_id == world["donor_order"].id)
            .filter(SOSupplyDecision.state == DECISION_SUPERSEDED)
            .one()
        )
        expected_reason = (
            f"Borrowed by SO{world['asker'].provisional_ref} line "
            f"{world['asker_line'].line_no}"
        )
        reason = decision.superseded_reason

        # The next board build for the DONOR's own order re-walks its line rather than
        # trusting a decision that no longer holds. Its own required date sits outside its
        # own reserve window (`_borrow_world`'s default), so a fresh walk buys whole with
        # the window's own sentence - a deterministic, unambiguous sign the line was walked
        # again and not silently left "covered" by a decision that has just been superseded.
        donor_components = _components(
            ProjectSupplyService(db).proposal_for(world["donor_order"])
        )

    assert reason == expected_reason, reason
    assert donor_components, "the donor line must be re-proposed, not silently skipped"
    assert donor_components[0]["kind"] == "buy", donor_components
    assert "beyond the lead time window" in donor_components[0]["reason"], donor_components


# --------------------------------------------------------------------------- AC-S3-10


def test_a_frozen_v5_snapshot_naming_cross_group_borrow_still_renders_on_the_board():
    """AC-S3-10: a decision confirmed before v7.1 could freeze a `cross_group_borrow`
    component (kind `borrow`, rung `cross_group_borrow`). The board must still render it -
    a snapshot is evidence of what was promised - which the coder's own
    `test_a_frozen_snapshot_carrying_the_retired_rung_still_renders` never actually proves:
    it constructs a bare `BoardTrailStep` by hand and round-trips it through Pydantic, never
    exercising the real frozen-decision read path (`_frozen_decisions` /
    `_line_decision` in `project_fulfilment_board_service.py`) at all.
    """
    from app.services.project_fulfilment_board_service import FulfilmentBoardService

    with blank_session() as db:
        company_id, eling, project, product = _world(db)
        _group, sites = _group_sites(db)
        own, _pool = sites["BRW"]
        _stock(db, product, own, on_hand=10)
        _lead_time(db, product, LEAD_DAYS)
        _policy(db)

        order, line, core_so, _cline = _seed_adopted_line(
            db, company_id, project, product, own, qty_ordered="10",
            so_number=f"ZZTSO-FROZEN{_uid()[:4]}",
        )
        _decide(db, order, line, own, "10", eling)

        # Rewrite the frozen snapshot exactly as a v4/v5 build would have written it: the
        # engine no longer WRITES this rung (`test_the_retired_cross_group_settings_are_
        # read_by_no_code_path` pins that), but a decision confirmed under the old ladder
        # still carries it in `so_supply_decisions.line_snapshots`, and the board reads that
        # column back verbatim.
        decision = (
            db.query(SOSupplyDecision)
            .filter(SOSupplyDecision.project_sales_order_id == order.id)
            .filter(SOSupplyDecision.state == DECISION_ACTIVE)
            .one()
        )
        snapshots = [dict(snapshot) for snapshot in decision.line_snapshots]
        components = [dict(component) for component in snapshots[0]["components"]]
        components[0] = {
            **components[0],
            "kind": "borrow",
            "rung": "cross_group_borrow",
            "source": "other_location",
        }
        snapshots[0]["components"] = components
        decision.line_snapshots = snapshots
        db.add(decision)
        db.commit()

        board = FulfilmentBoardService(db).build(
            [core_so.so_number], granularity="week", as_of=date.today()
        )
        contribution = next(
            contribution
            for cell in board["cells"]
            for contribution in cell["contributions"]
        )
        rungs = [row["rung"] for row in contribution["decision"]["borrow"]]

    assert rungs == ["cross_group_borrow"], contribution["decision"]


def test_the_live_borrow_candidate_list_does_not_write_the_retired_rung():
    """AC-S3-10's read-only half, from the OTHER direction: `RUNG_CROSS_GROUP_BORROW`
    must survive only for READING a frozen snapshot, never for labelling a LIVE candidate.

    `use_candidates_for` (step 1) already proves this for the ENGINE's own proposal - a
    free pile outside the asker's own group is composed as a plain Reserve with no rung of
    that name (`test_another_project_groups_free_pile_covers_the_unit_before_any_borrow_is_
    tried`). This checks the SECOND place the rung's vocabulary could leak back in: the
    manual donor list `BorrowAddDialog` reads (`ProjectSupplyService.borrow_candidates_for`,
    which is `_borrow_candidates` under a public name). The same free-stock-outside-the-
    group case is a live candidate there too, and if that list still tags it
    `cross_group_borrow`, the retired rung is not read-only - it is still being written for
    a fresh planning decision, which is exactly what AC-S3-10 says stops.
    """
    with blank_session() as db:
        company_id, _eling, project, product = _world(db)
        _group, sites = _group_sites(db)
        own, pool = sites["BRW"]
        donor = _warehouse(db, f"ZZTDC1-IR{_uid()[:3]}")
        _stock(db, product, donor, on_hand=100)
        _stock(db, product, pool, on_hand=100)
        _lead_time(db, product, LEAD_DAYS)
        _policy(db)

        order, _line, _cso, _cline = _seed_line(
            db, company_id, project, product, own, qty_ordered="40",
        )
        service = ProjectSupplyService(db)
        facts = service._facts_for(order, service.lines_of(str(order.id)))
        fact = next(iter(facts.values()))
        candidates = service.borrow_candidates_for(fact, need=Decimal("40"))
        rungs = [c.get("rung") for c in candidates]

    assert "cross_group_borrow" not in rungs, (
        "the manual donor list still tags a live free-stock row `cross_group_borrow` "
        f"(project_supply_service.py, `_borrow_candidates`): {candidates}"
    )


# --------------------------------------------------------------------------- AC-S3-14


def test_options_arrive_through_the_board_route_payload():
    """AC-S3-14 through the response_model TRAP the coder's own
    `test_the_board_payload_declares_the_options_so_the_response_model_keeps_them` does not
    reach: that test constructs a `BoardContribution` directly from a hand-built dict, which
    proves the SCHEMA carries `options` but not that the ROUTE actually populates and
    serializes it off a real walk. This hits the real
    `GET /fulfilment-planning/board` endpoint over a live `TestClient` and reads the wire.
    """
    from app.models.base import company_scope

    from tests.test_fulfilment_board import BASE, VIEW, _client, _restore

    with blank_session() as db:
        company_id, eling, project, product = _world(db)
        _group, sites = _group_sites(db)
        own, _pool = sites["BRW"]
        donor_bin = _warehouse(db, f"ZZTMWH-IB{_uid()[:3]}")
        _stock(db, product, donor_bin, on_hand=30)
        _lead_time(db, product, LEAD_DAYS)
        _policy(db)

        donor_order, donor_line, donor_core_so, _b = _seed_line(
            db, company_id, project, product, donor_bin, qty_ordered="30",
            required_date=date.today() + timedelta(days=WINDOW_DAY + 20), line_no=2,
            so_number=f"ZZTSO-DONOR{_uid()[:4]}",
        )
        _decide(db, donor_order, donor_line, donor_bin, "30", eling)

        _asker_order, _asker_line, asker_core_so, _acline = _seed_line(
            db, company_id, project, product, own, qty_ordered="30", line_no=1,
            so_number=f"ZZTSO-ASK{_uid()[:5]}",
        )
        db.commit()

        client, originals = _client(db, eling, [VIEW])
        try:
            with company_scope(db, frozenset({company_id})):
                response = client.get(
                    f"{BASE}/fulfilment-planning/board",
                    params={
                        "orders": asker_core_so.so_number,
                        "granularity": "week",
                        "as_of": date.today().isoformat(),
                    },
                )
        finally:
            _restore(originals)

        assert response.status_code == 200, response.text
        body = response.json()
        contribution = body["cells"][0]["contributions"][0]
        options = contribution.get("options")
        donor_so_number = donor_core_so.so_number

    assert options is not None, "`options` was dropped by the response_model"
    assert [option["step"] for option in options] == [
        "use", "order_borrow", "supply_borrow", "pool", "buy",
    ]
    assert sum(1 for option in options if option["chosen"]) == 1
    chosen = next(option for option in options if option["chosen"])
    assert chosen["step"] == "order_borrow"
    assert chosen["whole"] is True
    assert chosen["debt_so_number"] == donor_so_number
    assert chosen["debt_month"] and len(chosen["debt_month"]) == 7
    for option in options:
        assert (option["fulfil_date"] is None) == (option["days_late"] is None), option
        if option["step"] in ("use", "buy"):
            assert option["debt_so_number"] is None, option
            assert option["debt_month"] is None, option
