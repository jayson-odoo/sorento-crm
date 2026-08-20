"""What did we last pay this supplier for this item, and is that price still usable?

> "i need to know the last PO for this product and this supplier, and the last purchase
>  date, i will know how has the market changed and make decision, of course, the system
>  need to suggest to a certain extent, but i am not sure how smart can we suggest whether
>  to use the same price or need new price cause we are blind to market condition"

The buyer named the limit themselves, and it is the rule this module is built around: we
are blind to the market. Everything here is a fact about OUR OWN purchase history plus the
age of it. The advice codes say "this price is six years old", never "prices have risen".

The live data makes the point. Every real purchase on record was imported from one 2020
listing, so almost every pair resolves to `stale` - which is the honest answer, not a
defect in the rule.
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest

from app.services.scm.price_history_service import (
    MOVEMENT_PCT,
    STALE_AFTER_DAYS,
    Purchase,
    assess_price,
    price_history_for_run,
)

MARKER = "ZZTPRC"
AS_OF = date(2026, 8, 10)


def buy(day: date, cost: float, currency: str = "USD", qty: float = 100.0) -> Purchase:
    return Purchase(
        po_number=f"{MARKER}-{day.isoformat()}",
        issue_date=day,
        unit_cost=cost,
        currency=currency,
        qty=qty,
    )


# --------------------------------------------------------------------------- #
# never bought before
# --------------------------------------------------------------------------- #

def test_no_purchase_on_record_is_its_own_answer_not_a_stale_price():
    """Absence of history is not an old price. A buyer who has never bought this from this
    supplier needs a quote, and telling them it is "stale" would imply a number exists."""
    a = assess_price(None, None, standing_cost=12.0, standing_currency="MYR", as_of=AS_OF)

    assert a.advice == "no_history"
    assert a.age_days is None
    assert a.movement_pct is None


def test_a_standing_cost_is_not_evidence_that_we_ever_bought_it():
    """`product_suppliers.unit_cost` is a number somebody typed. It is what the plan costs
    against, and it is NOT a purchase, so it can never move the advice off no_history."""
    a = assess_price(None, None, standing_cost=999.0, standing_currency="MYR", as_of=AS_OF)

    assert a.advice == "no_history"
    assert a.standing_cost == 999.0


# --------------------------------------------------------------------------- #
# a plan costing at zero
# --------------------------------------------------------------------------- #

def test_a_plan_costing_at_zero_outranks_every_other_price_question():
    """24 buy lines on the live run, 11,675 units, all costed at exactly 0.00. A zero
    price makes any quantity free, so it clears a budget unchallenged and ranks with no
    cash pressure behind it. Nothing else about the price matters until that is settled."""
    a = assess_price(
        buy(date(2026, 7, 1), 9.82), None, standing_cost=0.0, standing_currency="USD", as_of=AS_OF
    )

    assert a.advice == "zero_cost"


def test_a_zero_cost_is_flagged_even_with_no_purchase_to_compare_it_with():
    a = assess_price(None, None, standing_cost=0.0, standing_currency="MYR", as_of=AS_OF)

    assert a.advice == "zero_cost"


def test_the_real_price_we_paid_still_travels_beside_the_zero():
    """The buyer is being asked to correct a zero. The last figure we actually paid is the
    single most useful thing to hand them while they do it."""
    a = assess_price(
        buy(date(2020, 7, 10), 9.82), None, standing_cost=0.0, standing_currency="USD", as_of=AS_OF
    )

    assert a.last.unit_cost == 9.82
    assert a.age_days == 2222


def test_an_unknown_cost_is_not_a_zero_cost():
    """None is "nobody has priced it" and 0.0 is "it is free". Flattening them would put a
    line that simply needs a price into the loudest bucket on the screen."""
    a = assess_price(buy(date(2026, 7, 1), 9.82), None, None, None, as_of=AS_OF)

    assert a.advice == "recent"


# --------------------------------------------------------------------------- #
# age
# --------------------------------------------------------------------------- #

def test_the_live_case_a_2020_price_is_stale():
    last = buy(date(2020, 10, 20), 4.5)
    a = assess_price(last, None, None, None, as_of=AS_OF)

    assert a.advice == "stale"
    assert a.age_days == (AS_OF - date(2020, 10, 20)).days
    assert a.age_days > STALE_AFTER_DAYS


def test_a_price_inside_the_window_is_usable():
    a = assess_price(buy(date(2026, 7, 1), 4.5), None, None, None, as_of=AS_OF)

    assert a.advice == "recent"
    assert a.age_days == 40


def test_the_boundary_day_is_still_usable_and_the_next_one_is_not():
    """An off-by-one here silently re-quotes a price the business considers current."""
    from datetime import timedelta

    on = assess_price(buy(AS_OF - timedelta(days=STALE_AFTER_DAYS), 1.0), None, None, None, as_of=AS_OF)
    past = assess_price(buy(AS_OF - timedelta(days=STALE_AFTER_DAYS + 1), 1.0), None, None, None, as_of=AS_OF)

    assert on.advice == "recent"
    assert past.advice == "stale"


def test_a_purchase_with_no_date_cannot_be_aged_so_it_is_never_called_recent():
    """An undated line is a real price of unknown age. Defaulting it to current would let
    the oldest data in the system pass as fresh."""
    a = assess_price(buy(date(2020, 1, 1), 4.5)._replace(issue_date=None), None, None, None, as_of=AS_OF)

    assert a.age_days is None
    assert a.advice == "unknown_age"


# --------------------------------------------------------------------------- #
# movement between our own purchases
# --------------------------------------------------------------------------- #

def test_a_price_that_moved_between_the_last_two_purchases_is_flagged():
    a = assess_price(
        buy(date(2026, 7, 1), 11.0), buy(date(2026, 3, 1), 10.0), None, None, as_of=AS_OF
    )

    assert a.advice == "moving"
    assert a.movement_pct == pytest.approx(10.0)


def test_a_small_move_is_not_worth_re_quoting_over():
    a = assess_price(
        buy(date(2026, 7, 1), 10.2), buy(date(2026, 3, 1), 10.0), None, None, as_of=AS_OF
    )

    assert a.movement_pct == pytest.approx(2.0)
    assert a.advice == "recent"
    assert abs(a.movement_pct) < MOVEMENT_PCT


def test_age_outranks_movement_because_a_six_year_old_price_needs_a_quote_either_way():
    a = assess_price(
        buy(date(2020, 10, 20), 11.0), buy(date(2020, 3, 1), 10.0), None, None, as_of=AS_OF
    )

    assert a.advice == "stale"
    assert a.movement_pct == pytest.approx(10.0)  # still reported, just not the headline


def test_a_movement_across_two_currencies_is_not_a_movement():
    """USD 10 to MYR 11 is an exchange rate, not a price rise, and reporting it as one
    would invent a market signal out of a bookkeeping change."""
    a = assess_price(
        buy(date(2026, 7, 1), 11.0, "MYR"), buy(date(2026, 3, 1), 10.0, "USD"), None, None, as_of=AS_OF
    )

    assert a.movement_pct is None
    assert a.currency_changed is True
    assert a.advice == "recent"


def test_a_previous_price_of_zero_yields_no_percentage():
    """Percentage change off zero is undefined. Emitting infinity or 100 would both be
    fabrications."""
    a = assess_price(
        buy(date(2026, 7, 1), 5.0), buy(date(2026, 3, 1), 0.0), None, None, as_of=AS_OF
    )

    assert a.movement_pct is None


# --------------------------------------------------------------------------- #
# the standing cost the plan is using vs what we actually paid
# --------------------------------------------------------------------------- #

def test_the_gap_between_the_costed_price_and_the_paid_price_is_reported():
    a = assess_price(
        buy(date(2026, 7, 1), 12.0, "USD"), None, standing_cost=10.0, standing_currency="USD", as_of=AS_OF
    )

    assert a.standing_gap_pct == pytest.approx(20.0)


def test_no_gap_is_claimed_across_currencies():
    a = assess_price(
        buy(date(2026, 7, 1), 12.0, "USD"), None, standing_cost=10.0, standing_currency="MYR", as_of=AS_OF
    )

    assert a.standing_gap_pct is None


def test_no_gap_is_claimed_when_the_plan_has_no_cost_at_all():
    a = assess_price(buy(date(2026, 7, 1), 12.0), None, None, None, as_of=AS_OF)

    assert a.standing_gap_pct is None


# --------------------------------------------------------------------------- #
# read from a real run
# --------------------------------------------------------------------------- #

def test_the_two_most_recent_purchases_are_read_per_product_and_supplier(db_price_world):
    entry = db_price_world["history"][db_price_world["key"]]

    assert entry.last.unit_cost == 12.0
    assert entry.last.po_number.endswith("-NEW")
    assert entry.previous.unit_cost == 10.0
    assert entry.advice == "stale"


def test_a_draft_the_plan_itself_proposed_is_not_something_we_paid(db_price_world):
    """A `draft_recommendation` PO is this run's own proposal. Reading it back as our last
    purchase would let the system quote its own suggestion to itself as evidence."""
    entry = db_price_world["history"][db_price_world["key"]]

    assert entry.last.unit_cost != 99.0
    assert all(p.unit_cost != 99.0 for p in (entry.last, entry.previous) if p)


def test_another_suppliers_price_is_surfaced_labelled_never_as_this_suppliers_own(db_price_world):
    """The buyer asked for the last price from THAT supplier, and this supplier has never
    sold us this product - `no_history` would be correct read alone. But the product DOES
    have a priced purchase, just under a different supplier, so "never bought this" is a
    different, more alarming claim than the truth. Fix-cluster (2026-08-20): surfaced as a
    distinct `other_supplier_price` code, carrying the OTHER supplier's name explicitly -
    never substituted in as if it were this supplier's own quote."""
    entry = db_price_world["history"][db_price_world["other_key"]]
    known = db_price_world["known_supplier"]

    assert entry.advice == "other_supplier_price"
    assert entry.last is not None
    assert entry.last.unit_cost == 12.0
    assert entry.other_supplier_code == known.supplier_code
    assert entry.other_supplier_name == known.supplier_name
    # Fix-cluster (2026-08-20): age_days must be recomputed off the OTHER supplier's own
    # purchase date, not left at the no_history None - else the popup interpolates "null".
    assert entry.age_days == (AS_OF - date(2020, 10, 20)).days


def test_a_free_of_charge_line_is_not_our_last_price(db_price_world):
    """637 lines in the live ledger are recorded at 0.00, and 116 pairs would take one as
    their newest price. "Our last price was 0.00" invites an order at zero, and calling
    26.15 -> 0.00 a 100% fall is nonsense. The real last price stands instead."""
    entry = db_price_world["history"][db_price_world["key"]]

    assert entry.last.unit_cost == 12.0
    assert entry.movement_pct == pytest.approx(20.0)  # 10.00 -> 12.00, not -100%


def test_the_free_of_charge_lines_we_set_aside_are_counted_not_hidden(db_price_world):
    """Dropping them silently would make a supplier we have bought from twice look like
    one we have never priced."""
    assert db_price_world["history"][db_price_world["key"]].free_of_charge_lines == 1


@pytest.fixture()
def db_price_world():
    """One product, two suppliers: a real purchase history with one supplier, a plan line
    against both, and a draft PO this run proposed."""
    from sqlalchemy import text as _t

    from app.models.procurement import Supplier
    from app.models.product import Product, ProductCategory, UnitOfMeasure
    from tests._pg_fixture import pg_session, unique_code

    def _u() -> str:
        return str(uuid.uuid4())

    with pg_session() as db:
        cat = ProductCategory(id=_u(), category_code=unique_code(MARKER),
                              category_name=f"{MARKER} cat")
        uom = UnitOfMeasure(id=_u(), uom_code=unique_code("U")[:20], uom_name=f"{MARKER} u")
        db.add_all([cat, uom])
        db.flush()
        product = Product(id=_u(), product_code=unique_code("P"), product_name=f"{MARKER} p",
                          category_id=cat.id, base_uom_id=uom.id, list_price=0,
                          is_active=True, is_discontinued=False)
        known = Supplier(id=_u(), supplier_code=unique_code("S1"), supplier_name=f"{MARKER} known")
        fresh = Supplier(id=_u(), supplier_code=unique_code("S2"), supplier_name=f"{MARKER} fresh")
        db.add_all([product, known, fresh])
        db.flush()

        wid = _u()
        db.execute(_t(
            "INSERT INTO warehouses (id, warehouse_code, warehouse_name, is_active, "
            "counts_as_available) VALUES (:id, :c, :c, true, true)"),
            {"id": wid, "c": unique_code("W")[:20]})

        def add_po(supplier_id, number, day, cost, status="closed"):
            pid = _u()
            db.execute(_t(
                "INSERT INTO purchase_orders (id, po_number, supplier_id, issue_date, status, "
                "currency, source_system) VALUES (:id, :n, :s, :d, :st, 'USD', :src)"),
                {"id": pid, "n": f"{MARKER}-{number}", "s": supplier_id, "d": day,
                 "st": status, "src": "scm_po_history"})
            db.execute(_t(
                "INSERT INTO purchase_order_lines (id, purchase_order_id, product_id, "
                "warehouse_id, qty_ordered, qty_received, unit_cost, currency, line_status) "
                "VALUES (:id, :po, :p, :w, 100, 0, :c, 'USD', 'open')"),
                {"id": _u(), "po": pid, "p": product.id, "w": wid, "c": cost})

        add_po(known.id, "OLD", date(2020, 3, 1), 8.0)
        add_po(known.id, "MID", date(2020, 6, 1), 10.0)
        add_po(known.id, "NEW", date(2020, 10, 20), 12.0)
        # free of charge, and newer than every real price
        add_po(known.id, "FOC", date(2020, 11, 30), 0.0)
        # this run's own proposal, and the newest row by date
        add_po(known.id, "DRAFT", date(2026, 8, 1), 99.0, status="draft_recommendation")

        run_id = _u()
        db.execute(_t(
            "INSERT INTO scm.reorder_run (id, status, include_market, created_at) "
            "VALUES (:id, 'completed', false, now())"), {"id": run_id})
        for supplier in (known, fresh):
            db.execute(_t(
                "INSERT INTO scm.reorder_recommendation "
                "(id, run_id, product_id, warehouse_id, supplier_id, rec_type, rounded_qty, "
                "status) "
                "VALUES (:id, :r, :p, :w, :s, 'buy', 10, 'proposed')"),
                {"id": _u(), "r": run_id, "p": product.id, "w": wid, "s": supplier.id})
        db.flush()

        history = price_history_for_run(db, run_id, as_of=AS_OF)
        yield {
            "history": history,
            "key": f"{product.id}:{known.supplier_code}",
            "other_key": f"{product.id}:{fresh.supplier_code}",
            "known_supplier": known,
        }


# --------------------------------------------------------------------------- #
# S13e: the thresholds are configuration, not constants
# --------------------------------------------------------------------------- #

def test_a_tighter_staleness_window_from_config_turns_recent_into_stale():
    # 60 days old: fine under the 180-day default, stale under a 30-day policy.
    advice = assess_price(buy(date(2026, 6, 11), 10.0), None, 10.0, "USD",
                          as_of=AS_OF, stale_after_days=30)
    assert advice.advice == "stale"
    assert advice.stale_after_days == 30


def test_a_higher_movement_threshold_from_config_silences_a_small_move():
    last, prev = buy(date(2026, 7, 1), 12.0), buy(date(2026, 5, 1), 10.0)
    default = assess_price(last, prev, 12.0, "USD", as_of=AS_OF)
    relaxed = assess_price(last, prev, 12.0, "USD", as_of=AS_OF, movement_pct=50.0)

    assert default.advice == "moving"  # 20% >= the 5% default
    assert relaxed.advice == "recent"  # 20% < the configured 50%
    assert relaxed.movement_threshold_pct == 50.0


def test_the_run_reads_its_thresholds_off_the_global_policy_row():
    """price_history_for_run applies the policy's thresholds, and the payload names them."""
    from sqlalchemy import text as _t

    from app.models.procurement import Supplier
    from app.models.product import Product, ProductCategory, UnitOfMeasure
    from tests._pg_fixture import pg_session, unique_code

    def _u() -> str:
        return str(uuid.uuid4())

    with pg_session() as db:
        # The configured policy: 30-day staleness, 50% movement. Priority high enough to
        # outrank any global row already on the shared dev DB.
        db.execute(_t(
            "INSERT INTO scm.reorder_policy (id, scope_type, policy_type, is_active, "
            "priority, price_stale_after_days, price_movement_threshold_pct, "
            "source_system, source_ref, created_at, updated_at) "
            "VALUES (:id, 'global', 'forecast', true, 999999, 30, 50, "
            "'manual', :m, now(), now())"), {"id": _u(), "m": MARKER})

        cat = ProductCategory(id=_u(), category_code=unique_code(MARKER),
                              category_name=f"{MARKER} cat")
        uom = UnitOfMeasure(id=_u(), uom_code=unique_code("U")[:20], uom_name=f"{MARKER} u")
        db.add_all([cat, uom])
        db.flush()
        product = Product(id=_u(), product_code=unique_code("P"), product_name=f"{MARKER} p",
                          category_id=cat.id, base_uom_id=uom.id, list_price=0,
                          is_active=True, is_discontinued=False)
        supplier = Supplier(id=_u(), supplier_code=unique_code("S"),
                            supplier_name=f"{MARKER} s")
        db.add_all([product, supplier])
        db.flush()

        wid = _u()
        db.execute(_t(
            "INSERT INTO warehouses (id, warehouse_code, warehouse_name, is_active, "
            "counts_as_available) VALUES (:id, :c, :c, true, true)"),
            {"id": wid, "c": unique_code("W")[:20]})

        # 60 days old, 20% up on the one before: recent+moved under the defaults,
        # stale (and NOT moved) under the configured 30/50.
        for number, day, cost in (("A", date(2026, 5, 1), 10.0), ("B", date(2026, 6, 11), 12.0)):
            pid = _u()
            db.execute(_t(
                "INSERT INTO purchase_orders (id, po_number, supplier_id, issue_date, status, "
                "currency, source_system) VALUES (:id, :n, :s, :d, 'closed', 'USD', "
                "'scm_po_history')"),
                {"id": pid, "n": f"{MARKER}-{number}", "s": supplier.id, "d": day})
            db.execute(_t(
                "INSERT INTO purchase_order_lines (id, purchase_order_id, product_id, "
                "warehouse_id, qty_ordered, qty_received, unit_cost, currency, line_status) "
                "VALUES (:id, :po, :p, :w, 100, 0, :c, 'USD', 'open')"),
                {"id": _u(), "po": pid, "p": product.id, "w": wid, "c": cost})

        run_id = _u()
        db.execute(_t(
            "INSERT INTO scm.reorder_run (id, status, include_market, created_at) "
            "VALUES (:id, 'completed', false, now())"), {"id": run_id})
        db.execute(_t(
            "INSERT INTO scm.reorder_recommendation "
            "(id, run_id, product_id, warehouse_id, supplier_id, rec_type, rounded_qty, "
            "status) "
            "VALUES (:id, :r, :p, :w, :s, 'buy', 10, 'proposed')"),
            {"id": _u(), "r": run_id, "p": product.id, "w": wid, "s": supplier.id})
        db.flush()

        history = price_history_for_run(db, run_id, as_of=AS_OF)
        advice = history[f"{product.id}:{supplier.supplier_code}"]

        assert advice.advice == "stale"
        assert advice.stale_after_days == 30
        assert advice.movement_threshold_pct == 50.0
