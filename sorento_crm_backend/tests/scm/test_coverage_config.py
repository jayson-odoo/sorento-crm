"""The three configurable figures behind the Coverage Timeline, and the horizon arithmetic.

``test_coverage_routes`` pins the WIRE and ``test_coverage_service`` pins the maths. Neither
covers what this slice added underneath them:

* the resolution of ``planning_horizon_months`` / ``transfer_lead_time_days`` /
  ``transfer_cost_per_unit`` off ``scm.reorder_policy``, through the resolver the reorder
  engine already uses, so a per-SKU override beats the global row;
* the NULL behaviour of the transfer pair, which is load-bearing rather than cosmetic: 0
  would read as a free instant move and make a proposal look better than the truth;
* ``build_timeline``'s exclusion COUNT, including the boundary, because an omission a
  screen does not mention is indistinguishable from data that is not there.

**Nothing is asserted about a row the environment happened to hold.** Every policy this
file resolves is a SKU-scoped row it seeded itself, which outranks any global row a database
may or may not carry - a test that asserted "the default applies" would pass on an empty
database and fail on one that has been configured, which is the wrong way round. The
"nothing resolves" case is reached by making the resolver return nothing rather than by
hoping the table is empty.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta

import pytest

from app.models.inventory import Warehouse
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.scm import ReorderPolicy
from app.services.scm import coverage_service as coverage_module
from app.services.scm.coverage_service import (
    DEFAULT_PLANNING_HORIZON_MONTHS,
    CoverageService,
    _add_months,
)
from app.services.scm.coverage_timeline import (
    DEMAND,
    SUPPLY,
    TimelineEvent,
    build_timeline,
)
from app.services.sla_service import MALAYSIA_TZ, to_naive_datetime
from tests._pg_fixture import pg_session, unique_code
from tests.scm.test_coverage_service import _so_line, _stock


def _u() -> str:
    return str(uuid.uuid4())


def _today() -> date:
    """The service's own notion of today: Malaysia wall-clock, not the server's zone."""
    return to_naive_datetime(datetime.now(MALAYSIA_TZ)).date()


@pytest.fixture()
def db():
    with pg_session() as s:
        yield s


@pytest.fixture()
def chain(db):
    """product + pool + one member bin + one location at ANOTHER site holding stock.

    The other site is what makes a transfer proposal exist at all, so it is part of the
    fixture rather than being seeded per test.
    """
    cat = ProductCategory(
        id=_u(), category_code=unique_code("CAT")[:40], category_name=unique_code("cat")
    )
    uom = UnitOfMeasure(id=_u(), uom_name=unique_code("uom"), uom_code=unique_code("U")[:20])
    db.add_all([cat, uom])
    db.flush()

    product = Product(
        id=_u(), product_code=unique_code("SKU"), product_name="Wall hung WC",
        category_id=cat.id, base_uom_id=uom.id, list_price=0,
    )
    pool = Warehouse(
        id=_u(), warehouse_code=unique_code("POOL"), warehouse_name="pool", is_active=True
    )
    db.add_all([product, pool])
    db.flush()

    bin_a = Warehouse(
        id=_u(), warehouse_code=unique_code("BINA"), warehouse_name="bin a",
        is_active=True, pool_warehouse_id=pool.id,
    )
    other_site = Warehouse(
        id=_u(), warehouse_code=unique_code("OTHR"), warehouse_name="other site",
        is_active=True,
    )
    pool.pool_warehouse_id = pool.id
    db.add_all([bin_a, other_site])
    db.flush()
    other_site.pool_warehouse_id = other_site.id
    db.flush()
    return {"product": product, "pool": pool, "bin_a": bin_a, "other": other_site}


def _sku_policy(db, product_id, **values) -> ReorderPolicy:
    """A SKU-scoped active policy for this product.

    SKU scope, not global: it outranks whatever the database already holds, so the
    assertion is about the code's resolution rather than about the environment.
    """
    policy = ReorderPolicy(
        id=_u(), scope_type="sku", scope_ref=str(product_id),
        policy_type="reorder_point", is_active=True, priority=0, **values,
    )
    db.add(policy)
    db.flush()
    return policy


# =========================================================================== #
# 1. policy resolution of the three new columns
# =========================================================================== #

def test_a_sku_scoped_policy_supplies_all_three_figures(db, chain):
    """The whole point of putting these on ``reorder_policy``: scope resolution came free.

    A per-SKU override beating the global row is what makes "this one item ships from a
    different port" configuration rather than code, and it is resolved by the SAME resolver
    the reorder engine uses, so the plan and the timeline cannot disagree about which row
    won.
    """
    _sku_policy(
        db, chain["product"].id,
        planning_horizon_months=3,
        transfer_lead_time_days=7,
        transfer_cost_per_unit=3.5,
    )

    config = CoverageService(db).config_for(chain["product"].id, pool_id=chain["pool"].id)

    assert config.horizon_months == 3
    assert config.transfer_lead_time_days == 7
    assert config.transfer_cost_per_unit == 3.5


def test_a_null_horizon_on_the_resolved_policy_falls_back_to_the_code_default(db, chain):
    """A configured policy that says nothing about the horizon is not a zero-month horizon.

    Treating NULL as 0 would bound the axis at today and report every future commitment as
    excluded, which is the same lie as dropping them silently.
    """
    _sku_policy(db, chain["product"].id, planning_horizon_months=None)

    config = CoverageService(db).config_for(chain["product"].id, pool_id=chain["pool"].id)

    assert config.horizon_months == DEFAULT_PLANNING_HORIZON_MONTHS == 6


def test_no_policy_at_all_still_yields_a_horizon(db, chain, monkeypatch):
    """A tenant that has configured nothing must still get a timeline.

    The resolver is made to return nothing rather than the table being assumed empty: on a
    configured database a global row always matches, so "empty table" is not a state a test
    can rely on.
    """
    monkeypatch.setattr(coverage_module, "resolve_policy_for_sku", lambda *a, **k: None)

    config = CoverageService(db).config_for(chain["product"].id, pool_id=chain["pool"].id)

    assert config.horizon_months == DEFAULT_PLANNING_HORIZON_MONTHS
    assert config.transfer_lead_time_days is None
    assert config.transfer_cost_per_unit is None


def test_a_failing_policy_lookup_degrades_to_defaults_rather_than_a_500(db, chain, monkeypatch):
    """Config is an input to the advice, not the advice itself.

    An install whose scm policy tables are not there yet would otherwise lose the whole
    screen to a 500 over a figure that has a perfectly good default.
    """
    def _boom(*_a, **_k):
        raise RuntimeError("scm.reorder_policy does not exist")

    monkeypatch.setattr(coverage_module, "resolve_policy_for_sku", _boom)

    config = CoverageService(db).config_for(chain["product"].id, pool_id=chain["pool"].id)

    assert config.horizon_months == DEFAULT_PLANNING_HORIZON_MONTHS


def test_the_resolved_horizon_bounds_the_timeline_and_the_count_reports_the_drop(db, chain):
    """The configured months reach the axis, not just the payload's own field.

    Asserted end to end because a horizon that is reported but not applied is worse than
    no horizon at all: the screen would state a bound the numbers do not respect.
    """
    _sku_policy(db, chain["product"].id, planning_horizon_months=1)
    today = _today()
    _so_line(db, chain["product"], chain["bin_a"], 10, today)
    _so_line(db, chain["product"], chain["bin_a"], 900, _add_months(today, 9))

    cov = CoverageService(db).coverage_for(chain["product"].id, pool_id=chain["pool"].id)

    assert cov.horizon_months == 1
    assert cov.horizon_end == _add_months(today, 1)
    assert cov.timeline.closing_balance == -10
    assert cov.excluded_event_count == 1


# =========================================================================== #
# 2. the transfer pair: NULL is a real answer, 0 is a lie
# =========================================================================== #

def test_an_unconfigured_transfer_carries_no_cost_no_lead_time_and_no_arrival(db, chain):
    """Zero cost reads as a free move and zero lead time as an instant one.

    Either would make the proposal look better than the truth, which is the one thing a
    proposal a person is asked to ACCEPT must never do. ``arrives_at`` is null for the same
    reason: with no lead time, "today" is a guess dressed as a date.
    """
    _sku_policy(
        db, chain["product"].id,
        transfer_lead_time_days=None, transfer_cost_per_unit=None,
    )
    _stock(db, chain["product"], chain["other"], 500)
    _so_line(db, chain["product"], chain["bin_a"], 50, _today())

    cov = CoverageService(db).coverage_for(chain["product"].id, pool_id=chain["pool"].id)

    assert len(cov.transfer_proposals) == 1
    proposal = cov.transfer_proposals[0]
    assert proposal.transfer_cost is None
    assert proposal.lead_time_days is None
    assert proposal.arrives_at is None
    # Still offered, and still not netted: the balance is short the full 50.
    assert proposal.available_qty == 500
    assert proposal.qty == 50
    assert cov.timeline.closing_balance == -50


def test_a_configured_transfer_prices_the_moved_quantity_and_dates_its_arrival(db, chain):
    """Cost and lead time are what turn "there is stock elsewhere" into a decision.

    The cost is for the quantity actually moved rather than per unit, because that is the
    figure being compared against buying, and the arrival is derived from the lead time so
    the proposal can be read against the need-by date it is meant to cover.
    """
    _sku_policy(
        db, chain["product"].id,
        transfer_lead_time_days=7, transfer_cost_per_unit=3.5,
    )
    _stock(db, chain["product"], chain["other"], 500)
    _so_line(db, chain["product"], chain["bin_a"], 40, _today())

    cov = CoverageService(db).coverage_for(chain["product"].id, pool_id=chain["pool"].id)

    proposal = cov.transfer_proposals[0]
    assert proposal.qty == 40
    assert proposal.transfer_cost == pytest.approx(140.0)  # 40 x 3.50
    assert proposal.lead_time_days == 7
    assert proposal.arrives_at == _today() + timedelta(days=7)


def test_the_proposal_reference_is_a_human_key_and_is_stable_across_computations(db, chain):
    """A key the UI holds to accept the proposal, and a planner may read aloud.

    A UUID would be unusable on both counts (AC-B2), and a reference that changed between
    two computations of the same position would make the accept action point at nothing.
    """
    _stock(db, chain["product"], chain["other"], 500)
    _so_line(db, chain["product"], chain["bin_a"], 50, _today())

    svc = CoverageService(db)
    first = svc.coverage_for(chain["product"].id, pool_id=chain["pool"].id)
    second = svc.coverage_for(chain["product"].id, pool_id=chain["pool"].id)

    ref = first.transfer_proposals[0].proposal_ref
    assert ref == f"TP-{chain['pool'].warehouse_code}-0001"
    assert second.transfer_proposals[0].proposal_ref == ref
    with pytest.raises(ValueError):
        uuid.UUID(ref)


def test_a_pool_that_needs_no_purchase_is_offered_no_transfer(db, chain):
    """A proposal against a covered pool competes with the answer "use the pool".

    That answer is the entire point of the module, so cross-site stock is offered only when
    something would otherwise have to be bought.
    """
    _stock(db, chain["product"], chain["pool"], 4397)
    _stock(db, chain["product"], chain["other"], 500)
    _so_line(db, chain["product"], chain["bin_a"], 67, _today())

    cov = CoverageService(db).coverage_for(chain["product"].id, pool_id=chain["pool"].id)

    assert cov.use_stock is True
    assert cov.buy_qty == 0
    assert cov.transfer_proposals == ()


# =========================================================================== #
# 3. the exclusion count, as arithmetic
# =========================================================================== #

def _event(when, qty=-10.0, kind=DEMAND, ref="X"):
    return TimelineEvent(at=when, qty=qty, kind=kind, ref=ref)


def test_every_event_beyond_the_horizon_is_counted_not_merely_dropped():
    """The count IS the honesty of the bound.

    A planner who cannot see that two of four events were excluded reads the visible
    shortfall as the whole picture, so the count has to equal what was removed rather than
    being a boolean "some were".
    """
    result = build_timeline(
        0.0,
        [
            _event(date(2026, 9, 1), ref="A"),
            _event(date(2026, 10, 1), ref="B"),
            _event(date(2030, 1, 1), ref="C"),
            _event(date(2035, 1, 1), ref="D"),
        ],
        horizon_end=date(2026, 12, 31),
    )

    assert result.excluded_event_count == 2
    # Opening row plus the two kept events, and the balance reflects only those two.
    assert [row.event.ref for row in result.rows] == ["", "A", "B"]
    assert result.closing_balance == -20


def test_an_event_landing_exactly_on_the_horizon_is_kept():
    """The bound is inclusive, and the boundary is where an off-by-one hides.

    A container due on the last day of the window is inside the plan; excluding it would
    report a shortfall the very supply that covers it was dropped from.
    """
    result = build_timeline(
        0.0,
        [_event(date(2026, 12, 31), qty=100.0, kind=SUPPLY, ref="ON-THE-LINE")],
        horizon_end=date(2026, 12, 31),
    )

    assert result.excluded_event_count == 0
    assert result.closing_balance == 100


def test_nothing_is_excluded_when_no_horizon_is_stated():
    result = build_timeline(
        0.0, [_event(date(2035, 1, 1)), _event(date(2040, 1, 1))], horizon_end=None
    )
    assert result.excluded_event_count == 0
    assert len(result.rows) == 3


def test_an_undated_event_is_never_excluded_by_the_horizon():
    """An event with no date cannot be beyond a date, and counting it as excluded would
    report an omission that never happened."""
    result = build_timeline(
        0.0, [_event(None, qty=5.0, kind=SUPPLY)], horizon_end=date(2026, 1, 1)
    )
    assert result.excluded_event_count == 0


# =========================================================================== #
# 4. month arithmetic
# =========================================================================== #

def test_the_horizon_is_added_in_calendar_months_and_clamps_to_a_short_month():
    """Months, not 30-day blocks: the horizon is stated in months by the people who use it.

    The clamp is what stops 31 August plus six months becoming an invalid 31 February.
    """
    assert _add_months(date(2026, 8, 4), 6) == date(2027, 2, 4)
    assert _add_months(date(2026, 8, 31), 6) == date(2027, 2, 28)
    assert _add_months(date(2026, 12, 15), 1) == date(2027, 1, 15)
    assert _add_months(date(2026, 8, 4), 0) == date(2026, 8, 4)
