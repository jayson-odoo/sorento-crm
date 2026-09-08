"""The confirm-time recheck judges INCOMING cover by the dated walk too (8 September 2026).

`documentation/plans/scm/PLAN-scm-cs-planning-uat.md` section 9 (rulings), UAC AC-L5b - the
new criterion beside AC-L5, which #743 amended in place rather than splitting into an AC-L5a.
Written BEFORE the fix, as PRINCIPLES step 4 requires.

THE DEFECT, off SO419851 on the live book (8 September 2026). Lines 2, 3 and 4 are one
planning unit - same item, same required date, fulfilment location `BRW-IB`, whose ownership
group is oversold ("IR group is 486 short on its own book, nothing to spare"). The board
proposed `Incoming 3 (BRW-IB)` for lines 3 and 4, and the approved-as-suggested body
(`timely_spo_qty: 3, reserve: [], buy_qty: 0`) came back 422 `"Timely SPO cover is now 0,
not 3."` for both.

The two sides were reading two different figures for the same question:

* the WALK composes `timely_spo` out of `use_candidates_for`'s water candidates - the DATED
  reading, what the one assignment gave this unit BY ITS OWN DATE (`_drawn_at_own_date`,
  R24) - and the board reads that same walk through `compose_lines`
  (`project_fulfilment_board_service.py:2114`, `front_planning_engine._draw_group`);
* the RECHECK bounded the posted quantity at `fact.timely_qty`, which `_apply_group_nets`
  sets to the water share of `_group_take_candidates` - the UNDATED whole-pile reading,
  capped at `group_offer = max(group net + the unit's own quantity, 0)`. On an oversold
  group that is 0, whatever any single early line's own date reads.

The FLOOR half of the very same recheck was repaired this way on 30 August 2026 (SO381895,
ladder v7.1 R24): its capacity is seeded from BOTH readings and the pile is whichever is
larger. The water half was deliberately left on the undated reading then; this is the same
repair applied to it, and nothing wider - a hand-typed quantity above BOTH readings is still
refused.

Postgres via `blank_session`, every chain seeded here (CI's database has no data).
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.schemas.project_supply import ConfirmLine, ConfirmSupplyBody
from app.services.project_supply_service import ProjectSupplyService, SupplyLinesRefused

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
from .test_ladder_v7_borrow import LEAD_DAYS, _policy
from .test_ladder_v7_supply_borrow import ASKER_DAY, _confirm_as_proposed, _spo
from .test_project_supply_service_ladder import (
    _components,
    _group_sites,
    _lead_time,
    _seed_line,
    _world,
)

#: The day the SPO lands, before the asking line needs it (day 20), so it is this line's
#: TIMELY cover rather than step 3's late-but-beats-buying document.
SPO_DAY = ASKER_DAY - 5
#: The oversold sibling's own date, LATER than the asker's, which is the whole case: the
#: group's undated net is negative because of it, and the dated walk still hands the asker
#: the 3 because it is due first.
SIBLING_DAY = ASKER_DAY + 40
#: What the sibling owes at the same group, far beyond anything arriving.
SIBLING_QTY = 486


def _oversold_group_with_timely_water(db, *, asker_qty="3"):
    """Own bin in an oversold ownership group, holding nothing, with an SPO of 3 arriving
    before this line's date and a later sibling order that oversells the group.

    Returns `(order, line, actor, own_bin, spo)`. Nothing is on a floor anywhere: the only
    supply in the world is the SPO, so a proposal naming a Reserve would be a different bug
    and this fixture cannot hide one.

    `asker_qty` is the asking line's own open quantity, 3 by default - exactly the water on
    offer, which is what makes the walk propose Incoming for the whole unit. A caller
    proving the BOUND asks for more than the water covers, so its over-posted quantity
    still balances the line and the timely refusal is the only one it can trip.
    """
    company_id, eling, project, product = _world(db)
    _group, sites = _group_sites(db)
    own, _pool = sites["BRW"]
    _stock(db, product, own, on_hand=0)
    _lead_time(db, product, LEAD_DAYS)
    _policy(db)

    spo = _spo(
        db, product, own, qty=3, arrives=date.today() + timedelta(days=SPO_DAY),
    )
    # THE SIBLING, at the same group's bin and due 40 days after the asker: the group nets
    # 0 + 3 - (3 + 486), so `group_offer` is 0 and the undated water share with it, while
    # the assignment still gives the asker the 3 - it is due first.
    _seed_line(
        db, company_id, project, product, own, qty_ordered=str(SIBLING_QTY),
        required_date=date.today() + timedelta(days=SIBLING_DAY),
        so_number=f"ZZT-SO-SIB{_uid()[:6]}",
    )

    order, line, _cso, _cline = _seed_line(
        db, company_id, project, product, own, qty_ordered=str(asker_qty),
        required_date=date.today() + timedelta(days=ASKER_DAY),
        so_number=f"ZZT-SO-ASK{_uid()[:6]}",
    )
    return order, line, eling, own, spo


# --------------------------------------------------------------------------- AC-L5b


def test_the_board_proposes_incoming_off_the_dated_walk_and_the_confirm_accepts_it():
    """AC-L5b: the composition the walk proposed for an early line of an OVERSOLD group -
    `timely_spo 3`, drawn as the group's water by this line's own date - is accepted by the
    confirmation that judges it.

    Both halves in one test on purpose: the proposal and the recheck are the two readings
    that came apart, and asserting them apart would let either drift alone.
    """
    from app.models.project_so import DECISION_ACTIVE, SOSupplyDecision

    with blank_session() as db:
        order, line, actor, own, spo = _oversold_group_with_timely_water(db)
        service = ProjectSupplyService(db)

        proposal = service.proposal_for(order)
        components = _components(proposal)
        # (a) THE BOARD'S OWN ANSWER. `compose_lines` is the walk the board reads too
        # (`project_fulfilment_board_service.py:2114`), so this is the figure that reached
        # the screen as "Incoming 3 (BRW-IB)".
        assert [
            (c["kind"], c["qty"], c["source_location"], c["rung"]) for c in components
        ] == [("timely_spo", "3", own.warehouse_code, "group_take")], components
        assert spo.spo_number in components[0]["reason"], components[0]["reason"]

        # (b) THE SAME COMPOSITION, POSTED VERBATIM, the way an approved board line posts.
        _confirm_as_proposed(db, order, actor)

        decision = (
            db.query(SOSupplyDecision)
            .filter(
                SOSupplyDecision.project_sales_order_id == order.id,
                SOSupplyDecision.state == DECISION_ACTIVE,
            )
            .one()
        )
        snapshot = next(
            snap for snap in decision.line_snapshots
            if str(snap["project_line_id"]) == str(line.id)
        )
        own_code = own.warehouse_code
        spo_number = spo.spo_number

    assert snapshot["timely_spo_qty"] == "3"
    assert snapshot["buy_qty"] == "0"
    assert snapshot["reserve_qty"] == "0"
    # The frozen row names the bin the goods are coming to and the document behind them.
    #
    # `rung` is ABSENT, and that is `_snapshot`'s water split still reading the UNDATED
    # `_group_take_candidates` alone: on an oversold group it is empty, so the split falls
    # through to its own "no water on offer" row - the retired rung 1's shape, at
    # `fact.own_code`. Here that bin IS where the SPO lands, so the row is right and only
    # its rung is missing; a unit whose dated water sits at a SIBLING bin would be named
    # wrongly. Pinned rather than fixed: the ruling this test carries is about the BOUND,
    # and the split is its own decision to take - recorded as (b) in the 8 Sep 2026 bullet
    # in `PLAN-scm-cs-planning-uat.md` section 9.
    assert [
        (c["kind"], c["qty"], c["source_location"], c.get("rung"))
        for c in snapshot["components"]
    ] == [("timely_spo", "3", own_code, None)], snapshot["components"]
    assert spo_number in snapshot["components"][0]["reason"]


def test_a_timely_quantity_above_both_readings_is_still_refused_with_the_dated_figure():
    """The other side of the repair: the bound moved to the LARGER of the two readings, it
    was not removed. 3 is on offer by this line's date and 5 is not, so a hand-typed 5 is
    refused and the sentence quotes the figure that IS on offer.

    The line is open for 5 here so that a posted 5 BALANCES it: on a line open for 3 the
    payload trips the composition invariant first and the bound is never reached, which
    would prove nothing about the bound.
    """
    with blank_session() as db:
        order, line, actor, _own, _spo_row = _oversold_group_with_timely_water(
            db, asker_qty="5"
        )
        service = ProjectSupplyService(db)

        with pytest.raises(SupplyLinesRefused) as refused:
            service.confirm(
                order,
                ConfirmSupplyBody(
                    lines=[
                        ConfirmLine(
                            project_line_id=line.id,
                            timely_spo_qty=Decimal("5"),
                        )
                    ]
                ),
                actor_user_id=actor,
            )
        detail = refused.value.detail
        said = str(detail.get("failing_lines") or detail)

    assert "Timely SPO cover is now 3, not 5" in said, said
