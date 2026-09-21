"""AC-S3-10 (`board-received-stock-own-arrival-acceptance-criteria.md`, added 21 Sep after the
S3 coder flagged the gap): the live CONFIRM round trip must honour the own-arrival credit, not
only the board proposal `FulfilmentBoardService.build` composes (AC-S3-1, already green).

`_check_line`'s confirm-time recheck (`app/services/project_supply_service.py` ~:4730) reads
`own_use, other_use, _own_offer, _short = self.use_candidates_for(unit.fact)` for capacity -
assignment-based candidates only. It has no call to `_own_arrival_credit_for` (~:2604), the
helper S3 added so the LADDER (the compose side) draws the credit first. So on the AC-S3-1
shape - L2 needs 20, 40 received on its own PO line, group net negative because of a competing
order at the same location - a live Confirm asking for that 20 as a Reserve at L2's own location
is expected to be REFUSED as exceeding capacity: the composer offers the Reserve, the recheck
that has to agree with it does not know why it is safe.

CONTRACT CHOICE this file pins: `ProjectSupplyService.confirm()` is called DIRECTLY rather than
through `planning_change_service.build_batch()` + `.apply()`. `_apply_one_order`
(`planning_change_service.py` ~:4546) builds a `ConfirmSupplyBody` from the row's own composition
and calls `supply.confirm(...)` - the exact same method, with the exact same `_check_line` recheck
inside it - so a batch-and-apply round trip would exercise no code this call does not already
exercise, at the cost of a synthetic `Diff`/`Change` this AC's own fixture shape (a first
confirmation, not an edit to an existing held line) has no natural one to build from. The
"real round trip" the brief asks for is the recheck itself, which both paths call identically.

Fixture: the AC-S3-1 shape, at the PROJECT layer `ProjectSupplyService.confirm()` needs (unlike
AC-S3-1's own CORE-only board read) - `own_wh`/`_core_so`/`_core_line`/`_project_so`/
`_project_line` from `tests.test_so_supply_confirmation` (the same convention
`tests.scm.test_project_supply_service_ladder` already imports these from), the own-arrival PO
helpers from `tests.scm._own_arrival_fixture` (imported, not modified), and `_world` from
`tests.scm.test_project_supply_service_ladder` for the company/project/product minimum.

Postgres only (`tests/_pg_fixture.py`), every FK seeded here, never a borrowed row.
"""
from __future__ import annotations

from datetime import date, timedelta

from app.schemas.project_supply import ConfirmLine, ConfirmSupplyBody
from app.services.project_supply_service import ProjectSupplyService

from tests._pg_fixture import blank_session
from tests.scm._own_arrival_fixture import po_line_bought_for, supplier_and_po
from tests.scm.test_project_supply_service_ladder import _world
from tests.test_so_supply_confirmation import (  # noqa: F401  (helpers, not fixtures)
    _core_line,
    _core_so,
    _project_line,
    _project_so,
    _stock,
    _uid,
    _warehouse,
)


def test_ac_s3_10_confirm_round_trip_with_own_arrival_reserve():
    """AC-S3-10: "Full round trip: a batch built for the fixture order carries an
    own-arrival Reserve for L2; Confirm (`apply` -> confirm-time recheck `_check_line`)
    succeeds and the Reserve is applied, even when the group net is negative because of
    the other order. The recheck must know the credit the same way the ladder does."

    L2 (needs 20) carries its own PO line, 40 received; on hand at its location is 40
    (>= the received total, the UAC's own fixture-shape paragraph); a competing order at
    the SAME location, dated EARLIER, asks for 5000 - the same "group net deeply negative
    because of the other order" shape AC-S3-1 already measured the ladder's own answer
    against. `confirm()` is asked for exactly the Reserve AC-S3-1 says the ladder should
    compose for L2: 20 at its own location.

    Simplest observable this file's own convention (`test_project_supply_service_ladder.
    py::test_a_pool_with_negative_available_offers_nothing_not_a_floor_of_zero_read_as_
    some`'s sibling `test_confirm_reads_the_same_claim_netting_as_the_proposal_did`)
    already asserts confirm() success on: no `AppException` raised, and
    `result["lines_decided"] == 1`, `result["exceptions"] == []` - the Reserve applied,
    nothing bounced to purchasing for exception handling.
    """
    within_window = date.today() + timedelta(days=10)
    dominant = date.today() + timedelta(days=5)
    with blank_session() as db:
        company_id, actor, project, product = _world(db)
        own = _warehouse(db, f"ZZT-OWN-{_uid()[:4]}")
        _stock(db, product, own, on_hand=40)

        core_so = _core_so(db, company_id)
        core_line = _core_line(
            db, core_so, product, own, qty_ordered="20", required_date=within_window,
        )
        core_line.source_ref = f"ZZT-L2-{_uid()[:8]}"
        db.flush()
        po = supplier_and_po(db, po_number=f"ZZT-PO-OWNARR10-{_uid()[:8]}")
        po_line_bought_for(
            db, po, product, own, from_so_line_ref=core_line.source_ref,
            qty_received=40, qty_ordered=40,
        )

        # The other order that drives the group net negative - same location, earlier
        # date so it dominates the DATE-AWARE reading too (AC-S3-1's own shape).
        other_so = _core_so(db, company_id)
        _core_line(db, other_so, product, own, qty_ordered="5000", required_date=dominant)

        order = _project_so(db, project, so_id=core_so.id)
        line = _project_line(db, order, line_no=1, product=product, core_line=core_line)
        db.commit()

        result = ProjectSupplyService(db).confirm(
            order,
            ConfirmSupplyBody(
                lines=[
                    ConfirmLine(
                        project_line_id=str(line.id),
                        reserve=[{"warehouse_id": str(own.id), "qty": "20"}],
                    ),
                ]
            ),
            actor_user_id=actor,
        )
        db.commit()

    assert result["exceptions"] == [], result["exceptions"]
    assert result["lines_decided"] == 1, result
