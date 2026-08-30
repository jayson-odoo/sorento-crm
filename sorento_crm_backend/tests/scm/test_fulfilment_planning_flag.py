"""The per-bin fulfilment-planning flag (borrow ladder v7.1 S1, migration 443).

AC-S1-1 (the seed), AC-S1-5 (every stock / demand / incoming reader honours it) and
AC-S1-6 (a line at a flagged-off bin is listed with the verdict, proposed nothing, and
refused at confirm).

Postgres via `tests/_pg_fixture.py::blank_session`, every test seeding its own chain: CI's
database is empty and the local one is a prod copy, so nothing here counts existing rows.

Helpers come from the supply suites so this file cannot come to disagree with them about
what a sales order, a warehouse or a board looks like. The shared `_warehouse` helper
defaults `fulfilment_planning=True` (a warehouse a supply test seeds exists to be planned
against); the tests below that need a bin OUTSIDE planning pass `fulfilment_planning=False`
and say why.
"""
from __future__ import annotations

import os
import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.models.inventory import Warehouse
from app.services.project_supply_service import ProjectSupplyService
from app.services.scm.group_netting import netting_for_products
from app.services.scm.planning_predicate import (
    OUTSIDE_FULFILMENT_PLANNING,
    in_fulfilment_planning,
)

from .._pg_fixture import blank_session
from ..test_so_supply_confirmation import (  # noqa: F401  (helpers, not fixtures)
    _core_line,
    _core_so,
    _product,
    _sorento,
    _stock,
    _uid,
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


# --------------------------------------------------------------------------- AC-S1-1


def _seed_443(db) -> int:
    """Run migration 443's own seed function against this session's connection.

    The migration's function, not a restatement of its predicate: the two paths (alembic on
    a real database, `bootstrap_env` on a create_all one) already share it, and a third
    spelling here would be the drift the sharing exists to prevent.
    """
    import importlib.util
    from pathlib import Path

    versions = (
        Path(__file__).resolve().parent.parent.parent / "alembic" / "versions"
    )
    spec = importlib.util.spec_from_file_location(
        "_seed_443_test", versions / "443_fulfilment_planning_flag_tba_date.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.seed_fulfilment_planning_flags(db.connection())


def test_the_seed_flags_exactly_the_active_planned_group_bins():
    """AC-S1-1: true for the ACTIVE bins whose code ends in one of the five planned
    ownership groups, false for every other row - inactive bins, other groups, and the site
    pools, which carry no suffix at all.
    """
    stem = uuid.uuid4().hex[:6].upper()
    with blank_session() as db:
        _sorento(db)
        planned = {
            group: _warehouse(db, f"ZZT{stem}{group}", fulfilment_planning=False)
            for group in ("-BB", "-IB", "-IR", "-NTC", "-AM")
        }
        pool = _warehouse(db, f"ZZT{stem}POOL", fulfilment_planning=False)
        other_group = _warehouse(db, f"ZZT{stem}-HP", fulfilment_planning=False)
        retired = _warehouse(
            db, f"ZZT{stem}R-BB", active=False, fulfilment_planning=False
        )
        db.flush()

        _seed_443(db)
        for row in (*planned.values(), pool, other_group, retired):
            db.refresh(row)

        assert all(row.fulfilment_planning is True for row in planned.values()), (
            "every active bin of the five planned groups is flagged on"
        )
        assert pool.fulfilment_planning is False, "a site pool is not an ownership group"
        assert other_group.fulfilment_planning is False, "-HP is not a planned group"
        assert retired.fulfilment_planning is False, "an inactive bin is not planned"


def test_the_column_defaults_to_false():
    """A warehouse nobody has decided about is outside fulfilment planning, not inside it -
    the safe direction, because a bin wrongly IN the plan quietly promises stock."""
    with blank_session() as db:
        _sorento(db)
        row = Warehouse(
            id=_uid(),
            warehouse_code=f"ZZTDEF-{uuid.uuid4().hex[:6]}",
            warehouse_name="ZZT default",
            is_active=True,
        )
        db.add(row)
        db.flush()
        db.refresh(row)

    assert row.fulfilment_planning is False


def test_the_seed_is_idempotent():
    """It is replayed by `bootstrap_env` on every create_all database and by hand on the
    shared dev copy, so running it twice has to write the same thing."""
    stem = uuid.uuid4().hex[:6].upper()
    with blank_session() as db:
        _sorento(db)
        bin_ = _warehouse(db, f"ZZT{stem}-IB", fulfilment_planning=False)
        db.flush()

        first = _seed_443(db)
        again = _seed_443(db)
        db.refresh(bin_)

    assert bin_.fulfilment_planning is True
    assert first == 1
    assert again == 0, "the second pass finds nothing left to turn on"


# --------------------------------------------------------------------------- AC-S1-5


def test_a_flagged_off_bin_is_absent_from_every_stock_demand_and_incoming_reader():
    """AC-S1-5, all of it in one chain, because it is one rule.

    Two siblings of one ownership group: `own` is in fulfilment planning, `hidden` is
    flagged off while holding 500 on hand, owing 900 on somebody else's order, and expecting
    an SPO of 200. Not one of those three figures may reach the group's net, the group-take
    candidate list, the SPO read or the donor list - the bin is outside fulfilment planning
    entirely (R17), not merely unavailable.
    """
    with blank_session() as db:
        company_id, _eling, project, product = _world(db)
        group, sites = _group_sites(db)
        own, _pool = sites["BRW"]
        hidden = _warehouse(db, f"ZZTHID-{group}", fulfilment_planning=False)
        _stock(db, product, own, on_hand=0)
        _stock(db, product, hidden, on_hand=500)
        # Somebody else's open demand at the hidden bin - the SO leg of the triple.
        core_so = _core_so(db, company_id)
        core_so.so_number = f"SO-HID-{_uid()[:6]}"
        db.flush()
        _core_line(
            db, core_so, product, hidden, qty_ordered="900",
            required_date=REQUIRED_DATE - timedelta(days=10),
        )
        # And its incoming - the SPO leg.
        _spo_line(db, product, hidden, qty=200, arrives=date.today() + timedelta(days=5))
        db.commit()

        order, _line, _cso, _cline = _seed_line(
            db, company_id, project, product, own, qty_ordered="40",
        )
        service = ProjectSupplyService(db)
        proposal = service.proposal_for(order)
        components = _components(proposal)
        facts = service._facts_for(order, service.lines_of(str(order.id)))
        fact = next(iter(facts.values()))

        take = service.group_take_candidates_for(fact)
        donors = service.borrow_candidates_for(fact, need=Decimal("40"))
        # v7.1: another group's FREE stock is step 1's second half, not a borrow rung.
        cross = service.use_candidates_for(fact)[1]
        # The request-scoped SPO read, which is the one every reader shares. `_spo_rows`
        # itself takes its span from its caller, so what is pinned here is that the span the
        # ladder hands it never contains a flagged-off bin.
        spo_rows = service._spo_by_location()
        planning = service._planning_warehouses()
        # `group_net` through the batched door too (no board in sight), asked the PLANNING
        # question - the door itself keeps its full index for the order-inquiry link walk,
        # pinned by `test_the_batched_netting_door_keeps_the_full_group_index_unless_asked_
        # otherwise` below.
        standalone = netting_for_products(
            db, [str(product.id)], planning_only=True
        ).group_net(str(product.id), group)
        hidden_code = hidden.warehouse_code

    assert str(hidden.id) not in planning, "the flag decides the span, not `is_active`"
    # The 500 on hand, the 900 owed and the 200 incoming at the hidden bin are ALL outside
    # the group's net, so it reads only what `own` states: 0 on hand against this line's own
    # 40. Not +500, not -400, not -200.
    assert fact.group_net == Decimal("-40")
    assert standalone.net == Decimal("-40")
    assert hidden_code not in {entry.location for entry in standalone.by_location}
    assert hidden_code not in {c["location"] for c in take}
    assert hidden_code not in {c["warehouse_code"] for c in donors}
    assert hidden_code not in {c["location"] for c in cross}
    assert all(key[1] != str(hidden.id) for key in spo_rows), (
        "the 200 on the water at the hidden bin is not in the request's SPO read"
    )
    assert [c["kind"] for c in components] == ["buy"], (
        "nothing at the hidden bin may cover the line"
    )


def test_the_same_bin_flagged_ON_does_reach_the_readers():
    """The control for the test above: identical chain, flag flipped, and the group's net
    is the sum of the three figures. Without this the assertions above would pass on a
    fixture that simply never wrote the rows."""
    with blank_session() as db:
        company_id, _eling, project, product = _world(db)
        group, sites = _group_sites(db)
        own, _pool = sites["BRW"]
        shown = _warehouse(db, f"ZZTSHN-{group}", fulfilment_planning=True)
        _stock(db, product, own, on_hand=0)
        _stock(db, product, shown, on_hand=500)
        core_so = _core_so(db, company_id)
        core_so.so_number = f"SO-SHN-{_uid()[:6]}"
        db.flush()
        _core_line(
            db, core_so, product, shown, qty_ordered="900",
            required_date=REQUIRED_DATE - timedelta(days=10),
        )
        _spo_line(db, product, shown, qty=200, arrives=date.today() + timedelta(days=5))
        db.commit()

        order, _line, _cso, _cline = _seed_line(
            db, company_id, project, product, own, qty_ordered="40",
        )
        service = ProjectSupplyService(db)
        facts = service._facts_for(order, service.lines_of(str(order.id)))
        fact = next(iter(facts.values()))
        shown_code = shown.warehouse_code
        standalone = netting_for_products(
            db, [str(product.id)], planning_only=True
        ).group_net(str(product.id), group)

    # 500 on hand - 940 owed (900 theirs + this line's 40) + 200 incoming.
    assert fact.group_net == Decimal("-240")
    assert shown_code in {entry.location for entry in standalone.by_location}


def test_the_pool_still_lends_when_every_sibling_bin_in_the_group_is_flagged_off():
    """AC-S1-5's counterpart for the pool rung. `_group_sibling_warehouses` filters
    through `_planning_warehouses()`, so a sibling flagged off drops out of the GROUP
    rung's own candidate list - already proven above. But a site pool is reached through
    `pool_warehouse_id`, never as an ownership group (`planning_predicate`'s own
    docstring), so `_site_pool_warehouses` / `_pile_facts` / `_spo_by_location` /
    `_free_stock` must keep drawing it even when every OTHER bin in the group is off: the
    flag narrows the group's own net, it does not touch the pool rung at all.

    The sibling holds real, sizeable stock on purpose - if the flag failed to exclude it
    from the group rung, THAT stock would cover the line and the pool would never be
    reached, which would hide the bug this test exists to catch.
    """
    with blank_session() as db:
        company_id, _eling, project, product = _world(db)
        _group, sites = _group_sites(db)
        own, pool = sites["BRW"]
        sibling, _sibling_pool = sites["MWH"]
        sibling.fulfilment_planning = False
        db.flush()
        _stock(db, product, sibling, on_hand=500)
        _stock(db, product, pool, on_hand=40)
        db.commit()

        order, _line, _cso, _cline = _seed_line(
            db, company_id, project, product, own, qty_ordered="40",
        )
        proposal = ProjectSupplyService(db).proposal_for(order)
        components = _components(proposal)
        sibling_code = sibling.warehouse_code
        pool_code = pool.warehouse_code

    assert len(components) == 1, components
    assert components[0]["kind"] == "reserve"
    assert components[0]["rung"] == "pool"
    assert components[0]["source_location"] == pool_code
    assert components[0]["source_location"] != sibling_code
    assert components[0]["qty"] == "40"


def test_a_retired_bin_holds_nothing_the_ladder_can_draw_and_keeps_its_old_verdict():
    """R17's rule is `is_active AND fulfilment_planning`, so a RETIRED bin is outside the
    read set whatever its flag says - it already was, because every read this branch
    narrowed was `is_active` filtered before it.

    What it must not acquire is the `Outside fulfilment planning` VERDICT. That sentence
    sends a planner to the Warehouses screen to flip a switch that is already the right way
    up, when the line's actual problem is that its location was retired - so the verdict
    stays exactly what it was before this branch (none), and the line is planned normally
    against a location holding nothing it may draw.
    """
    with blank_session() as db:
        company_id, _eling, project, product = _world(db)
        group, _sites = _group_sites(db)
        retired = _warehouse(
            db, f"ZZTRET-{group}", active=False, fulfilment_planning=True,
        )
        _stock(db, product, retired, on_hand=1000)
        db.commit()

        order, _line, _cso, _cline = _seed_line(
            db, company_id, project, product, retired, qty_ordered="40",
        )
        service = ProjectSupplyService(db)
        facts = service._facts_for(order, service.lines_of(str(order.id)))
        fact = next(iter(facts.values()))
        components = _components(service.proposal_for(order))

    assert fact.unplannable_reason is None, (
        "a retired bin is not told about a flag nobody turned off"
    )
    assert [c["kind"] for c in components] == ["buy"], (
        "the 1000 at the retired bin is not drawable, so the line is bought"
    )


def test_the_public_stock_seams_still_state_what_a_flagged_off_bin_holds():
    """The flag narrows what a PROPOSAL may draw, never what a screen may state (R17).

    `stock_levels_by_location`, `held_stock_by_location` and `free_stock_by_location` are
    one arithmetic in three seams - on hand, less reserved, less held, IS free - and they
    are what the board's stock detail and the location-stock screen print. Narrowing the
    free half alone printed 1,928 on hand beside 0 free at every active unflagged bin,
    which reads as a defect rather than as a policy.

    The DONOR list is the other half of the same rule: what the bin holds is stated, and
    none of it is offered.
    """
    with blank_session() as db:
        company_id, _eling, project, product = _world(db)
        group, sites = _group_sites(db)
        own, _pool = sites["BRW"]
        hidden = _warehouse(db, f"ZZTFRE-{group}", fulfilment_planning=False)
        _stock(db, product, own, on_hand=0)
        _stock(db, product, hidden, on_hand=500, reserved=20)
        db.commit()

        order, _line, _cso, _cline = _seed_line(
            db, company_id, project, product, own, qty_ordered="40",
        )
        service = ProjectSupplyService(db)
        key = (str(product.id), str(hidden.id))
        levels = service.stock_levels_by_location([str(product.id)])
        held = service.held_stock_by_location([str(product.id)])
        free = service.free_stock_by_location([str(product.id)])

        facts = service._facts_for(order, service.lines_of(str(order.id)))
        fact = next(iter(facts.values()))
        donors = service.borrow_candidates_for(fact, need=Decimal("40"))
        # v7.1: another group's FREE stock is step 1's second half, not a borrow rung.
        cross = service.use_candidates_for(fact)[1]
        hidden_code = hidden.warehouse_code

    on_hand, reserved = levels[key]
    assert (on_hand, reserved) == (Decimal("500"), Decimal("20"))
    assert free[key] == on_hand - reserved - held.get(key, Decimal("0"))
    assert free[key] == Decimal("480")
    # ...and not one unit of it is on offer.
    assert hidden_code not in {c["warehouse_code"] for c in donors}
    assert hidden_code not in {c["location"] for c in cross}


def test_the_batched_netting_door_keeps_the_full_group_index_unless_asked_otherwise():
    """`netting_for_products` is the ORDER-INQUIRY link walk's door, not the ladder's.

    That walk reads "this group has no members" as "this group nets zero" and offers its
    open purchase-order lines on the strength of it (`_groups_in_deficit`), so narrowing
    every caller turned a group that is genuinely 800 short into one with purchases to
    spare. The ladder and the board never come through here: they build `GroupNetting`
    themselves with `planning_warehouse_ids` set. So the narrowing is opt-in, and both
    answers are pinned here side by side.
    """
    with blank_session() as db:
        company_id, _eling, _project, product = _world(db)
        group, sites = _group_sites(db)
        own, _pool = sites["BRW"]
        own.fulfilment_planning = False
        db.flush()
        _stock(db, product, own, on_hand=100)
        core_so = _core_so(db, company_id)
        core_so.so_number = f"SO-NET-{_uid()[:6]}"
        db.flush()
        _core_line(
            db, core_so, product, own, qty_ordered="900",
            required_date=REQUIRED_DATE - timedelta(days=10),
        )
        db.commit()

        full = netting_for_products(db, [str(product.id)]).group_net(
            str(product.id), group
        )
        planning = netting_for_products(
            db, [str(product.id)], planning_only=True
        ).group_net(str(product.id), group)

    assert full.net == Decimal("-800"), "the group's real position, members flagged or not"
    assert planning.net == Decimal("0"), "the planning question sees no member at all"


def test_a_group_whose_only_bins_are_flagged_off_still_reports_its_deficit():
    """The consequence of the test above, at the reader that motivated it.

    `_groups_in_deficit` compares the group's net with what its own purchase orders still
    have to come: below zero every unit on order is owed to demand the group already
    carries, and a link would promise the same stock twice. Read through the narrowed
    index the group had no members, netted zero, and 114 open lines at unflagged bins
    became offers no plan stands behind.

    The candidate rows are stand-ins on purpose: `_groups_in_deficit` reads exactly
    `line.id`, `qty_ordered`, `qty_received` and the warehouse's code off them, and the
    figure under test is the NET, which comes from the database.
    """
    from types import SimpleNamespace

    from app.services.project_order_inquiry_service import ProjectOrderInquiryService
    from app.services.scm.sales_agent_service import group_of_warehouse_code

    with blank_session() as db:
        company_id, _eling, _project, product = _world(db)
        group, sites = _group_sites(db)
        own, _pool = sites["BRW"]
        own.fulfilment_planning = False
        db.flush()
        _stock(db, product, own, on_hand=100)
        core_so = _core_so(db, company_id)
        core_so.so_number = f"SO-DEF-{_uid()[:6]}"
        db.flush()
        _core_line(
            db, core_so, product, own, qty_ordered="900",
            required_date=REQUIRED_DATE - timedelta(days=10),
        )
        db.commit()

        po_line = SimpleNamespace(
            id=_uid(), qty_ordered=Decimal("300"), qty_received=Decimal("0")
        )
        deficit = ProjectOrderInquiryService(db)._groups_in_deficit(
            str(product.id), [(po_line, None, None, own)], {}
        )

    # -800 net + 300 still to come is still short, so the group keeps its purchases.
    # Named the way the walk itself names a group: the suffix, upper-cased.
    assert deficit == {group_of_warehouse_code(f"ZZTBRW-{group}")}


# --------------------------------------------------------------------------- AC-S1-6


def test_a_line_at_a_flagged_off_bin_is_unplannable_with_the_verdict():
    """AC-S1-6: the sales order is still LISTED - it is open demand and hiding it would be
    worse than saying why - but no ladder is walked for it and the verdict names the
    reason."""
    with blank_session() as db:
        company_id, _eling, project, product = _world(db)
        group, _sites = _group_sites(db)
        off = _warehouse(db, f"ZZTOFF-{group}", fulfilment_planning=False)
        _stock(db, product, off, on_hand=1000)
        db.commit()

        order, _line, _cso, _cline = _seed_line(
            db, company_id, project, product, off, qty_ordered="40",
        )
        service = ProjectSupplyService(db)
        facts = service._facts_for(order, service.lines_of(str(order.id)))
        fact = next(iter(facts.values()))
        proposal = service.proposal_for(order)

    assert fact.unplannable_reason == OUTSIDE_FULFILMENT_PLANNING
    assert _components(proposal) == [], "no rung is walked for a bin outside the plan"


def test_confirming_a_line_at_a_flagged_off_bin_is_refused():
    """AC-S1-6's second half. The board proposes nothing for it, so an ordinary Confirm
    simply leaves it undecided; a payload that names it anyway is a composition the engine
    never offered, and the refusal states the same verdict the row carries."""
    from app.schemas.project_supply import ConfirmLine, ConfirmSupplyBody
    from app.services.project_supply_service import SupplyLinesRefused

    with blank_session() as db:
        company_id, eling, project, product = _world(db)
        group, _sites = _group_sites(db)
        off = _warehouse(db, f"ZZTOFC-{group}", fulfilment_planning=False)
        _stock(db, product, off, on_hand=1000)
        db.commit()

        order, line, _cso, _cline = _seed_line(
            db, company_id, project, product, off, qty_ordered="40",
        )
        with pytest.raises(SupplyLinesRefused) as excinfo:
            ProjectSupplyService(db).confirm(
                order,
                ConfirmSupplyBody(
                    lines=[
                        ConfirmLine(project_line_id=str(line.id), buy_qty=Decimal("40"))
                    ]
                ),
                actor_user_id=eling,
            )

        reasons = [
            row["reason"] for row in excinfo.value.detail["failing_lines"]
        ]

    assert excinfo.value.status_code == 422
    assert OUTSIDE_FULFILMENT_PLANNING in reasons


def test_the_predicate_reads_a_row_the_same_way_the_query_does():
    """`in_fulfilment_planning` is the ORM-row door onto the same rule the query half
    states, and the two have to answer identically or a reader holding rows and a reader
    writing SQL would disagree about the same bin."""
    with blank_session() as db:
        _sorento(db)
        on = _warehouse(db, f"ZZTP1-{_uid()[:4]}", fulfilment_planning=True)
        off = _warehouse(db, f"ZZTP2-{_uid()[:4]}", fulfilment_planning=False)
        retired = _warehouse(
            db, f"ZZTP3-{_uid()[:4]}", active=False, fulfilment_planning=True
        )
        db.flush()
        matched = {
            str(row[0])
            for row in db.execute(
                text(
                    "SELECT id FROM warehouses WHERE is_active AND fulfilment_planning "
                    "AND warehouse_code LIKE 'ZZTP%'"
                )
            )
        }
        verdicts = {
            str(row.id): in_fulfilment_planning(row) for row in (on, off, retired)
        }

    assert verdicts == {str(on.id): True, str(off.id): False, str(retired.id): False}
    assert matched == {str(on.id)}


# --------------------------------------------------------------------------- bootstrap_env


def test_bootstrap_env_replays_the_seed_on_a_create_all_database(monkeypatch):
    """`scripts.bootstrap_env.seed_fulfilment_planning_flags()` is what a `create_all`
    database (CI's bootstrap, a disaster-recovery restore) runs in place of migration 443's
    own seed, which `create_all` cannot produce - it builds the COLUMN from the ORM and
    nothing else (the create_all-vs-migration-seed gap, #363). Without it every warehouse
    on a fresh database reads `fulfilment_planning = false`, so the ladder proposes Buy for
    every line and the board's verdict is `Outside fulfilment planning` on all of them.

    Run on a THROWAWAY scratch schema built here, never the shared engine `blank_session()`
    reuses for the whole test run: this function opens its OWN connection via
    `app.database.engine` and commits through it (`engine.begin()`), so pointing it at the
    shared blank schema would leak a real, committed row into every other test that uses
    `blank_session()` for the rest of the suite - a rollback at THIS test's teardown would
    not undo it, because it was never this test's own transaction.

    The scratch schema is reached through SEARCH_PATH, not through a
    `schema_translate_map`. The seed under test is raw SQL (`UPDATE warehouses SET ...`)
    and raw SQL is not translated - it resolves through search_path - so a translated
    engine would have run the seed, the inserts and the reads against the REAL
    `public.warehouses` of this prod-copy database while the assertions still passed (the
    migration-396 lesson, in the direction that writes).
    """
    from sqlalchemy import create_engine

    from app.database import Base
    from app.database import engine as real_engine
    from app.models.inventory import Warehouse
    from scripts import bootstrap_env

    from .._pg_fixture import SCRATCH_SCHEMA_PREFIX, _with_dependencies

    name = f"{SCRATCH_SCHEMA_PREFIX}_boot443_{os.getpid()}_{uuid.uuid4().hex[:8]}"
    admin = real_engine.connect().execution_options(isolation_level="AUTOCOMMIT")
    admin.exec_driver_sql(f'CREATE SCHEMA "{name}"')
    admin.close()
    scoped = create_engine(
        real_engine.url.render_as_string(hide_password=False),
        connect_args={"options": f'-csearch_path="{name}"'},
    )
    try:
        with scoped.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            Base.metadata.create_all(
                connection, tables=_with_dependencies([Warehouse.__table__]), checkfirst=True,
            )

        stem = uuid.uuid4().hex[:6].upper()
        codes = {
            "on": f"ZZT{stem}-BB",
            "off_group": f"ZZT{stem}-HP",
            "inactive": f"ZZT{stem}R-BB",
        }
        with scoped.connect() as connection:
            for key, code in codes.items():
                connection.execute(
                    text(
                        "INSERT INTO warehouses (id, warehouse_code, warehouse_name, "
                        "is_active) VALUES (:id, :code, :code, :active)"
                    ),
                    {"id": str(uuid.uuid4()), "code": code, "active": key != "inactive"},
                )
            connection.commit()

        def _flags() -> dict:
            with scoped.connect() as connection:
                return dict(
                    connection.execute(
                        text(
                            "SELECT warehouse_code, fulfilment_planning FROM warehouses "
                            "WHERE warehouse_code = ANY(:codes)"
                        ),
                        {"codes": list(codes.values())},
                    ).all()
                )

        monkeypatch.setattr("app.database.engine", scoped)
        first = bootstrap_env.seed_fulfilment_planning_flags()
        flags = _flags()

        # An admin now turns the seeded bin OFF, and the next deploy bootstraps again -
        # against a database that is stamped, which is what tells a re-run from a first
        # run. The seed is a one-off STARTING POSITION, not a rule, so the second pass must
        # leave that decision alone rather than quietly restoring it.
        with scoped.connect() as connection:
            connection.execute(
                text(
                    "CREATE TABLE alembic_version (version_num varchar(255) NOT NULL)"
                )
            )
            connection.execute(
                text("INSERT INTO alembic_version (version_num) VALUES (:rev)"),
                {"rev": "443_fulfilment_planning_flag"},
            )
            connection.execute(
                text(
                    "UPDATE warehouses SET fulfilment_planning = false "
                    "WHERE warehouse_code = :code"
                ),
                {"code": codes["on"]},
            )
            connection.commit()
        bootstrap_env.seed_fulfilment_planning_flags()
        after_second_pass = _flags()
    finally:
        scoped.dispose()
        cleanup = real_engine.connect().execution_options(isolation_level="AUTOCOMMIT")
        cleanup.exec_driver_sql(f'DROP SCHEMA IF EXISTS "{name}" CASCADE')
        cleanup.close()

    assert flags[codes["on"]] is True, (
        "the seed the migration would have run must fire on a create_all database too"
    )
    assert flags[codes["off_group"]] is False
    assert flags[codes["inactive"]] is False
    assert after_second_pass[codes["on"]] is False, (
        "a bin turned off by hand stays off through the next bootstrap"
    )
    assert first is None  # the function logs a count, it does not return one


def test_a_decided_line_survives_its_bin_being_flagged_off_and_confirms_again():
    """The flag verdict applies to UNDECIDED lines only (review of S2, 30 Aug).

    The live sequence: a line is planned and confirmed while its bin is IN the plan, and an
    admin flags the bin off afterwards. The stock was found, promised and confirmed; the
    switch says what may be PROPOSED next, not that the decision is retracted. Reading the
    verdict off the flag alone made `_facts_for` call the line unplannable, so a verbatim
    re-send of the composition the engine itself had written was refused 422 with a reason
    the board no longer showed.
    """
    from app.schemas.project_supply import ConfirmLine, ConfirmSupplyBody

    with blank_session() as db:
        company_id, eling, project, product = _world(db)
        group, sites = _group_sites(db)
        own, _pool = sites["BRW"]
        _stock(db, product, own, on_hand=1000)
        db.commit()

        order, line, _cso, _cline = _seed_line(
            db, company_id, project, product, own, qty_ordered="40",
        )
        service = ProjectSupplyService(db)
        body = ConfirmSupplyBody(
            lines=[
                ConfirmLine(
                    project_line_id=str(line.id),
                    reserve=[{"warehouse_id": str(own.id), "qty": Decimal("40")}],
                )
            ]
        )
        first = service.confirm(order, body, actor_user_id=eling)
        assert first["lines_decided"] == 1

        # The admin turns the bin off, after the fact.
        own.fulfilment_planning = False
        db.commit()

        after = ProjectSupplyService(db)
        facts = after._facts_for(order, after.lines_of(str(order.id)))
        fact = facts[str(line.id)]
        # Not the verdict: this line has been decided.
        assert fact.unplannable_reason is None

        # And the same body goes through again, rather than 422.
        again = ProjectSupplyService(db).confirm(
            order, body, actor_user_id=eling
        )
        assert again["lines_decided"] == 1
        assert again["revision_no"] == first["revision_no"] + 1
