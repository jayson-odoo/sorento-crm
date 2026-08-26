"""Ladder v4 through the SERVICE: availability is the ownership group's (section 1d).

`tests/scm/test_group_netting.py` pins the arithmetic and
`tests/scm/test_front_planning_golden.py` pins the composition the engine builds from a
capped candidate list. This file is the join between them - what
`ProjectSupplyService` actually hands the engine when it reads a real book - and it is
where AC-L7 to AC-L13 live, each with the captain's own measured numbers.

Helpers come from the v3 ladder suite so the two files cannot come to disagree about what a
Project SO looks like. Postgres via `blank_session`, every test seeding its own chain.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from app.services.project_supply_service import ProjectSupplyService
from app.services.scm import priority

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
from .test_project_supply_service_ladder import (
    REQUIRED_DATE,
    _components,
    _group_sites,
    _seed_line,
    _spo_line,
    _world,
)


def _demand(db, company_id, product, warehouse, qty, *, so_number=None):
    """Somebody else's open line at a location - what makes a group's net negative.

    Core only: it is demand on the book, not a planning record, which is exactly the shape
    of the 27,804 units `BRW-IB` owes on `B2155-NL-BLUE`.

    Dated EARLIER than the line under test, deliberately: the group's pile is served in the
    active policy's own order, so "this quantity is spoken for before my line is reached" is
    a statement about the queue and has to be made in the fixture rather than left to a
    tie-break on the sales-order number.
    """
    core_so = _core_so(db, company_id)
    if so_number is not None:
        core_so.so_number = so_number
    db.flush()
    _core_line(
        db,
        core_so,
        product,
        warehouse,
        qty_ordered=str(qty),
        required_date=REQUIRED_DATE - timedelta(days=10),
    )
    db.flush()


# --------------------------------------------------------------------------- AC-L7


def test_a_sibling_holding_stock_offers_nothing_while_the_group_nets_negative():
    """AC-L7, the case the ruling came from.

    `B2155-NL-BLUE`: BRW-IB 5290 on hand against 27,804 owed, MWH-IB 7000 against nothing.
    Read warehouse by warehouse MWH-IB looks like 7000 free to promise; read as the group
    those 7000 are already owed at BRW-IB, the group nets -15514, and the line buys.
    """
    with blank_session() as db:
        company_id, _eling, project, product = _world(db)
        _group, sites = _group_sites(db)
        own, _pool = sites["BRW"]
        sibling, _sibling_pool = sites["MWH"]
        _stock(db, product, own, on_hand=5290)
        _stock(db, product, sibling, on_hand=7000)
        # 27,804 owed at the line's own location, on somebody else's orders.
        _demand(db, company_id, product, own, 27744, so_number="SO770001")
        db.commit()

        order, _line, _cso, _cline = _seed_line(
            db, company_id, project, product, own, qty_ordered="60",
        )
        service = ProjectSupplyService(db)
        proposal = service.proposal_for(order)
        components = _components(proposal)
        facts = service._facts_for(order, service.lines_of(str(order.id)))
        fact = next(iter(facts.values()))
        candidates = service.group_take_candidates_for(fact)

    assert fact.group_net == Decimal("-15514")
    assert candidates == [], "a group in deficit offers no location at all"
    assert [c["kind"] for c in components] == ["buy"]
    assert components[0]["qty"] == "60"


def test_the_front_of_the_group_queue_is_still_served_while_the_group_is_short():
    """The other half of the rule, and the half a naive `max(group_net, 0)` would break.

    1015 sit at the group and 9,080 are owed against them, so the group is 8,065 short. The
    line at the FRONT of that queue still reserves its 80 - fair share is a queue, not a
    ban - and the 9,000 behind it, facing the 935 the queue leaves, falls to the whole-line
    rule and buys. Refusing both would buy 9,080 with 1,015 sitting in the warehouse.

    What ladder v4 changed is WHOSE pile and WHOSE queue: one group-wide pile and one
    group-wide queue, instead of v3's own-location queue beside each sibling's own signed
    availability.
    """
    with blank_session() as db:
        company_id, _eling, project, product = _world(db)
        _group, sites = _group_sites(db)
        own, _pool = sites["BRW"]
        sibling, _sibling_pool = sites["MWH"]
        _stock(db, product, sibling, on_hand=1015)
        db.commit()

        first, _l1, _c1, _cl1 = _seed_line(
            db, company_id, project, product, own, qty_ordered="80",
            required_date=REQUIRED_DATE - timedelta(days=20), so_number="SO820001",
        )
        behind, _l2, _c2, _cl2 = _seed_line(
            db, company_id, project, product, own, qty_ordered="9000",
            required_date=REQUIRED_DATE, so_number="SO820002",
        )
        service = ProjectSupplyService(db)
        front = _components(service.proposal_for(first))
        back = _components(ProjectSupplyService(db).proposal_for(behind))

    assert [(c["kind"], c["qty"]) for c in front] == [("reserve", "80")]
    assert [(c["kind"], c["qty"]) for c in back] == [("buy", "9000")]


def test_the_group_still_covers_a_line_its_own_book_leaves_room_for():
    """The other side of AC-L7, and the one that keeps the rule honest.

    `sum(SO)` counts every open line at the group INCLUDING this one, so a group that
    exactly covers its book nets zero - and reading that as "nothing available" would buy
    stock sitting in the warehouse waiting for this very line. This line's own demand is
    un-netted; every other line's stays netted.
    """
    with blank_session() as db:
        company_id, _eling, project, product = _world(db)
        _group, sites = _group_sites(db)
        own, _pool = sites["BRW"]
        _stock(db, product, own, on_hand=40)
        db.commit()

        order, _line, _cso, _cline = _seed_line(
            db, company_id, project, product, own, qty_ordered="40",
        )
        components = _components(ProjectSupplyService(db).proposal_for(order))

    assert [c["kind"] for c in components] == ["reserve"]
    assert components[0]["rung"] == "group_take"
    assert components[0]["qty"] == "40"
    assert components[0]["source_location"] == own.warehouse_code


def test_the_offer_names_the_group_and_not_the_warehouse():
    """The reason travels with the quantity, and under v4 the quantity is the GROUP's."""
    with blank_session() as db:
        company_id, _eling, project, product = _world(db)
        _group, sites = _group_sites(db)
        own, _pool = sites["BRW"]
        sibling, _sibling_pool = sites["MWH"]
        _stock(db, product, sibling, on_hand=50)
        db.commit()

        order, _line, _cso, _cline = _seed_line(
            db, company_id, project, product, own, qty_ordered="50",
        )
        components = _components(ProjectSupplyService(db).proposal_for(order))

    assert components[0]["reason"] == (
        f"{sibling.warehouse_code} gives 50 of the 50 the {_group.upper()} group can "
        "cover this line with"
    )


# --------------------------------------------------------------------------- AC-L8


def test_the_site_pools_net_as_one_pile_so_a_lone_positive_pool_gives_nothing():
    """AC-L8, `SRTWCY8605-PJ` measured: BRW -103, DC1 +1, pools net -102.

    Per-pool arithmetic offered the single unit at DC1. It is stock the shared book already
    owes at BRW, and promising it is how one pool comes to be sold twice.
    """
    with blank_session() as db:
        company_id, _eling, project, product = _world(db)
        _group, sites = _group_sites(db)
        own, own_pool = sites["BRW"]
        _other_own, other_pool = sites["DC1"]
        _stock(db, product, other_pool, on_hand=1)
        _demand(db, company_id, product, own_pool, 103, so_number="SO780001")
        db.commit()

        order, _line, _cso, _cline = _seed_line(
            db, company_id, project, product, own, qty_ordered="10",
        )
        service = ProjectSupplyService(db)
        components = _components(service.proposal_for(order))
        facts = service._facts_for(order, service.lines_of(str(order.id)))
        fact = next(iter(facts.values()))

    assert fact.pools_net == Decimal("-102")
    assert [c["kind"] for c in components] == ["buy"]
    assert components[0]["qty"] == "10"


def test_a_pool_pile_that_nets_positive_is_still_drawn():
    """The control for AC-L8: the rule is the PILE's sign, not a blanket refusal."""
    with blank_session() as db:
        company_id, _eling, project, product = _world(db)
        _group, sites = _group_sites(db)
        own, own_pool = sites["BRW"]
        _stock(db, product, own_pool, on_hand=200)
        db.commit()

        order, _line, _cso, _cline = _seed_line(
            db, company_id, project, product, own, qty_ordered="10",
        )
        components = _components(ProjectSupplyService(db).proposal_for(order))

    assert [c["rung"] for c in components] == ["pool"]
    assert components[0]["source_location"] == own_pool.warehouse_code


# --------------------------------------------------------------------------- AC-L9


def test_a_cross_group_donor_is_offered_only_while_its_own_group_nets_positive():
    """AC-L9: `MWH-IR` holding 100 lends nothing if the whole `-IR` group is oversold.

    Two runs of one shape: the donor group flush, then the same donor warehouse with a
    sibling of its own carrying the demand that sinks it. The warehouse the borrow would
    come from holds exactly the same 100 in both.
    """
    def _run(sink: bool):
        with blank_session() as db:
            company_id, _eling, project, product = _world(db)
            _group, sites = _group_sites(db)
            own, _pool = sites["BRW"]
            donor_group = f"IR{_uid()[:4]}"
            donor = _warehouse(db, f"ZZTMWH-{donor_group}")
            donor_sibling = _warehouse(db, f"ZZTDC1-{donor_group}")
            _stock(db, product, donor, on_hand=100)
            if sink:
                _demand(db, company_id, product, donor_sibling, 500, so_number=f"SO79{_uid()[:4]}")
            priority.create_revision(
                db, name=f"zzt-v4-{_uid()[:4]}", factors={}, demand_class_weights={},
                reorder_coverage_until=None,
                cross_group_borrow_max_qty=50, cross_group_borrow_max_pct=0.0,
            )
            db.commit()

            order, _line, _cso, _cline = _seed_line(
                db, company_id, project, product, own, qty_ordered="40",
            )
            return _components(ProjectSupplyService(db).proposal_for(order)), donor

    flush, donor = _run(sink=False)
    assert [c["rung"] for c in flush] == ["cross_group_borrow"]
    assert flush[0]["qty"] == "40"

    sunk, _donor = _run(sink=True)
    assert [c["kind"] for c in sunk] == ["buy"], (
        "a warehouse whose group nets negative has nothing to lend"
    )


def test_confirming_a_cross_group_borrow_raises_an_order_back_at_the_donor():
    """AC-L9's second half, ruled 26 August: the `-IR` group lent 40 and is owed 40 back.

    For the WHOLE quantity, unconditionally. The v3 rule raised one only where the donor's
    own pile went negative, and under v4 the borrow is already capped at the donor group's
    net, so that test can never fire again.
    """
    from app.models.project_so import IV_BORROW_SHORTFALL, OrderInquiryRow
    from app.schemas.project_supply import ConfirmLine, ConfirmSupplyBody

    with blank_session() as db:
        company_id, eling, project, product = _world(db)
        _group, sites = _group_sites(db)
        own, _pool = sites["BRW"]
        donor = _warehouse(db, f"ZZTMWH-IR{_uid()[:4]}")
        _stock(db, product, donor, on_hand=100)
        priority.create_revision(
            db, name=f"zzt-v4-ob-{_uid()[:4]}", factors={}, demand_class_weights={},
            reorder_coverage_until=None,
            cross_group_borrow_max_qty=50, cross_group_borrow_max_pct=0.0,
        )
        db.commit()

        order, line, _cso, _cline = _seed_line(
            db, company_id, project, product, own, qty_ordered="40",
        )
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
        rows = (
            db.query(OrderInquiryRow)
            .filter(OrderInquiryRow.verb == IV_BORROW_SHORTFALL)
            .all()
        )
        raised = [(r.qty, r.stock_location, r.note) for r in rows]

    assert len(raised) == 1
    assert raised[0][0] == Decimal("40")
    assert raised[0][1] == donor.warehouse_code
    assert "lent 40" in raised[0][2]


# -------------------------------------------------------------------------- AC-L13


def test_a_pool_draw_raises_no_order_back():
    """AC-L13, ruled 26 August. The pool is shared and nobody is owed it back.

    It used to raise one whenever the draw pushed the pool's own availability below zero -
    which under v4 cannot happen, because rung 3 draws only while the five pools net
    positive between them.
    """
    from app.models.project_so import IV_BORROW_SHORTFALL, OrderInquiryRow
    from app.schemas.project_supply import ConfirmLine, ConfirmSupplyBody

    with blank_session() as db:
        company_id, eling, project, product = _world(db)
        _group, sites = _group_sites(db)
        own, pool = sites["BRW"]
        _stock(db, product, pool, on_hand=60)
        db.commit()

        order, line, _cso, _cline = _seed_line(
            db, company_id, project, product, own, qty_ordered="60",
        )
        proposal = ProjectSupplyService(db).proposal_for(order)
        assert [c["rung"] for c in _components(proposal)] == ["pool"]

        ProjectSupplyService(db).confirm(
            order,
            ConfirmSupplyBody(
                lines=[
                    ConfirmLine(
                        project_line_id=line.id,
                        reserve=[{"warehouse_id": str(pool.id), "qty": "60"}],
                    )
                ]
            ),
            actor_user_id=eling,
        )
        rows = (
            db.query(OrderInquiryRow)
            .filter(OrderInquiryRow.verb == IV_BORROW_SHORTFALL)
            .count()
        )

    assert rows == 0


# -------------------------------------------------------------------------- AC-L10


def test_an_spo_inside_a_negative_group_net_covers_nothing():
    """AC-L10, `SRTWC7405-SC` measured: 110 arrives at BRW-IB and the IB group still nets
    -1893 with it counted, so it is owed to that backlog and this line buys.

    The document is not hidden: `timely_qty_before_group_net` still carries it, and the
    trail names it, so a buyer can go and chase the promise rather than wondering where it
    went.
    """
    with blank_session() as db:
        company_id, _eling, project, product = _world(db)
        _group, sites = _group_sites(db)
        own, _pool = sites["BRW"]
        sibling, _sibling_pool = sites["MWH"]
        _stock(db, product, own, on_hand=2)
        _stock(db, product, sibling, on_hand=330)
        _spo_line(
            db, product, own, qty=110, arrives=REQUIRED_DATE - timedelta(days=5),
        )
        # The backlog sits at the SIBLING, so nothing at this line's own location is
        # ranked ahead of it: rung 1 hands this line the whole 10 it asks for, and the
        # ONLY thing that takes it away is the group's own net. Put the backlog at the own
        # location instead and the rank queue would zero it first, which proves a different
        # rule than the one AC-L10 is about.
        _demand(db, company_id, product, sibling, 2325, so_number="SO810001")
        db.commit()

        order, _line, _cso, _cline = _seed_line(
            db, company_id, project, product, own, qty_ordered="10",
        )
        service = ProjectSupplyService(db)
        components = _components(service.proposal_for(order))
        facts = service._facts_for(order, service.lines_of(str(order.id)))
        fact = next(iter(facts.values()))

    assert fact.group_net == Decimal("-1893")
    # 8, not 10: the 2 sitting on hand is drawn before the SPO is, which is PLAN 3.5's own
    # order. What matters is that it was POSITIVE before the group net was applied.
    assert fact.timely_qty_before_group_net == Decimal("8")
    assert fact.timely_qty == Decimal("0")
    assert [ref.qty for ref in fact.timely_refs] == [Decimal("110")], (
        "the document is still named - it exists, and a buyer has a promise to chase"
    )
    assert [c["kind"] for c in components] == ["buy"]
    assert components[0]["qty"] == "10"
