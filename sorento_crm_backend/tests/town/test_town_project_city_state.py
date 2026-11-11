"""TOWN-PROJECT-CITY Phase 2 (red): the Malaysian postcode table and `shops[].state`.

Contract: PLAN-town-project-city-11nov.md "Phase 2 contract" (`shops[].state`) and card rule 9.
Postgres only; every row seeded here.
"""
from __future__ import annotations

import json
import re
from datetime import timedelta

import pytest

from app.main import app  # noqa: F401
from app.models.base import set_company_scope
from app.services.company_scope import DEFAULT_COMPANY_ID
from tests._mc_lookup_seed import seed_mocha
from tests._pg_fixture import blank_session
from tests._sales_unified_seed import cust
from tests.town._town_project_seed import addr, delivery_order, shop_for
from tests.town._town_seed import DAY, NOW, dealer_doc


@pytest.mark.parametrize("postcode,state", [
    ("40150", "Selangor"), ("50450", "Kuala Lumpur"), ("62000", "Putrajaya"), ("81300", "Johor"),
    ("10200", "Pulau Pinang"), ("88000", "Sabah"), ("93350", "Sarawak"), ("87000", "Labuan"),
    ("25200", "Pahang"), ("01000", "Perlis"), ("05000", "Kedah"), ("15000", "Kelantan"),
    ("20000", "Terengganu"), ("30000", "Perak"), ("70000", "Negeri Sembilan"), ("75000", "Melaka"),
])
def test_state_for_postcode_known_ranges(postcode, state):
    from app.services.town.my_postcodes import state_for_postcode

    assert state_for_postcode(postcode) == state


@pytest.mark.parametrize("postcode", ["99999", "00000", "4015", "", "ABCDE", "401500"])
def test_state_for_postcode_outside_every_range_is_none(postcode):
    from app.services.town.my_postcodes import state_for_postcode

    assert state_for_postcode(postcode) is None


def test_state_for_postcode_returns_only_my_state_values():
    from app.services.town.my_postcodes import state_for_postcode
    from tests.town._town_project_seed import MY_STATES

    seen = {state_for_postcode(f"{n:05d}") for n in range(0, 100000, 250)}
    assert (seen - {None}) <= set(MY_STATES)
    assert len(seen - {None}) >= 14  # the table reaches every state and territory


@pytest.fixture
def db():
    with blank_session() as s:
        set_company_scope(s, None)
        seed_mocha(s)
        yield s


def _state_of(db, customer):
    """Make `customer` a top-30 shop (a dealer document today) and read its resolved state."""
    from app.services.town.snapshot import build_snapshot

    dealer_doc(db, customer, "100.00", DAY)
    snap = build_snapshot(db, DEFAULT_COMPANY_ID, DAY, now=NOW)
    return shop_for(snap, customer)["state"], snap


def _orders(db, customer, postcodes, *, start=1):
    """One delivery order per postcode, the first listed the OLDEST."""
    for i, pc in enumerate(postcodes):
        delivery_order(db, customer, addr(pc), DAY - timedelta(days=start + len(postcodes) - i))


def test_no_orders_means_null(db):
    assert _state_of(db, cust(db))[0] is None


def test_orders_without_a_postcode_mean_null(db):
    c = cust(db)
    delivery_order(db, c, "Jalan Tiada Poskod, Shah Alam", DAY - timedelta(days=1))
    delivery_order(db, c, None, DAY - timedelta(days=2))
    assert _state_of(db, c)[0] is None


def test_last_five_digit_group_in_the_address_wins(db):
    c = cust(db)
    delivery_order(db, c, "No. 12345, Jalan X, 81300 Skudai, Johor", DAY - timedelta(days=1))
    assert _state_of(db, c)[0] == "Johor"


def test_most_frequent_postcode_wins(db):
    c = cust(db)
    _orders(db, c, ["81300", "40150", "40150", "81300", "40150"])
    assert _state_of(db, c)[0] == "Selangor"


def test_tie_goes_to_the_most_recent_order(db):
    c = cust(db)
    _orders(db, c, ["40150", "81300"])  # Johor is newest
    assert _state_of(db, c)[0] == "Johor"
    d = cust(db)
    _orders(db, d, ["81300", "40150"])  # Selangor is newest
    assert _state_of(db, d)[0] == "Selangor"


def test_only_the_last_twenty_orders_count(db):
    c = cust(db)
    # 5 oldest Selangor, then 12 Johor + 8 Selangor newest: window of 20 is 12 Johor vs 8 Selangor,
    # whole history would be 13 Selangor vs 12 Johor.
    _orders(db, c, ["40150"] * 5 + ["81300"] * 12 + ["40150"] * 8)
    assert _state_of(db, c)[0] == "Johor"


def test_cancelled_and_deleted_orders_are_ignored(db):
    c = cust(db)
    for k in range(3):
        delivery_order(db, c, addr("81300"), DAY - timedelta(days=1 + k), cancelled=True)
        delivery_order(db, c, addr("81300"), DAY - timedelta(days=5 + k), deleted=True)
    delivery_order(db, c, addr("40150"), DAY - timedelta(days=30))
    assert _state_of(db, c)[0] == "Selangor"


def test_cancelled_orders_alone_mean_null(db):
    c = cust(db)
    delivery_order(db, c, addr("81300"), DAY - timedelta(days=1), cancelled=True)
    assert _state_of(db, c)[0] is None


def test_unmapped_postcode_is_ignored_and_the_next_valid_one_counts(db):
    c = cust(db)
    _orders(db, c, ["99999", "99999", "99999", "40150"])
    assert _state_of(db, c)[0] == "Selangor"


def test_other_customers_orders_are_not_used(db):
    c, other = cust(db), cust(db)
    delivery_order(db, other, addr("81300"), DAY - timedelta(days=1))
    assert _state_of(db, c)[0] is None


@pytest.mark.parametrize("region,expected", [("Selangor", "Selangor"), ("  selangor ", "Selangor"),
                                             ("KUALA LUMPUR", "Kuala Lumpur")])
def test_region_equal_to_a_my_state_value_overrides_the_postcode(db, region, expected):
    c = cust(db)
    c.region = region
    db.flush()
    _orders(db, c, ["81300", "81300"])
    assert _state_of(db, c)[0] == expected


def test_region_that_is_not_a_my_state_value_falls_back_to_the_postcode(db):
    c = cust(db)
    c.region = "ZZT-AREA-07"
    db.flush()
    _orders(db, c, ["81300"])
    assert _state_of(db, c)[0] == "Johor"


def test_every_shop_carries_the_state_key(db):
    c = cust(db)
    _, snap = _state_of(db, c)
    assert all("state" in shop for shop in snap["shops"])


def test_a_stall_also_carries_its_state(db):
    from app.services.town.snapshot import build_snapshot

    c = cust(db)
    c.region = "Perak"
    db.flush()
    dealer_doc(db, c, "10.00", DAY)
    # 30 better-ranked dealers push `c` out of the top 30 and into a stall
    for _ in range(30):
        dealer_doc(db, cust(db), "9999.00", DAY - timedelta(days=2))
    stall = shop_for(build_snapshot(db, DEFAULT_COMPANY_ID, DAY, now=NOW), c)
    assert stall["kind"] == "stall"
    assert stall["state"] == "Perak"


def test_postcode_and_address_never_appear_in_the_snapshot(db):
    from app.services.town.snapshot import redact, strip_names

    c = cust(db)
    delivery_order(db, c, "No. 54321, Jalan Zzt Unik, 81300 Skudai, Johor", DAY - timedelta(days=1))
    state, snap = _state_of(db, c)
    assert state == "Johor"
    for variant in (snap, redact(snap), strip_names(snap), strip_names(redact(snap))):
        text = json.dumps(variant)
        assert not re.search(r"\b(81300|54321)\b", text)
        assert "Jalan Zzt Unik" not in text and "Skudai" not in text
