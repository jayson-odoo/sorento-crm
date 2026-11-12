"""RED tests B13: a customer merge carries the costing profile and its products. PRODUCT-COSTING.
AC-PC-10.

`app.services.customer_merge._merge_group` repoints every FK onto `customers.id` generically, but
`customer_costing_profiles.customer_id` is also the PRIMARY KEY, so a survivor and a retired row
that both have a profile would collide. Contract 4.8: when the survivor has a profile the retired
profile is dropped via `_drop_where` (kept in the merge map, so a revert restores it); retired
`customer_costing_products` whose `product_id` the survivor already has are dropped the same way;
the rest are repointed.

Substrate and seeding follow tests/test_customer_merge.py: `blank_session()`, cash-style `301-`
codes so differently named rows merge without a hold, the oldest row is the survivor.
"""
from __future__ import annotations

import uuid
from datetime import datetime

import pytest
from sqlalchemy import text

from app.models.order import Customer
from app.services import customer_merge
from app.services.company_scope import DEFAULT_COMPANY_ID, register_company_scope_listeners
from tests._pg_fixture import blank_session, unique_code
from tests.support.costing_env import CostingEnv

OLD = datetime(2025, 1, 1, 9, 0, 0)
NEW = datetime(2026, 9, 1, 9, 0, 0)


@pytest.fixture(autouse=True)
def _listeners():
    register_company_scope_listeners()


@pytest.fixture()
def env():
    with blank_session() as db:
        yield CostingEnv(db)


def _code() -> str:
    return "301-" + unique_code("ZZPCM")[:26]


def _customer(db, code, name, created_at) -> str:
    row = Customer(id=str(uuid.uuid4()), customer_code=code, customer_name=name,
                   created_at=created_at, company_id=DEFAULT_COMPANY_ID)
    db.add(row)
    db.flush()
    return str(row.id)


def _scalar(db, sql, **params):
    return db.execute(text(sql), params).scalar()


def _products(db, customer_id) -> dict[str, float | None]:
    rows = db.execute(
        text("SELECT product_id::text, markup_pct FROM customer_costing_products WHERE customer_id = :c"),
        {"c": customer_id},
    ).all()
    return {r[0]: (None if r[1] is None else float(r[1])) for r in rows}


def _profile(db, customer_id):
    return db.execute(
        text("SELECT markup_pct, cost_method, is_active FROM customer_costing_profiles WHERE customer_id = :c"),
        {"c": customer_id},
    ).first()


class _P:
    """Light stand-in for a Customer when the helpers only need `.id`."""

    def __init__(self, id):
        self.id = id


def _world(env):
    cat = env.category("MergeCat")
    p1 = env.item("ZZ-M-1", category=cat, list_price="10")
    p2 = env.item("ZZ-M-2", category=cat, list_price="10")
    p3 = env.item("ZZ-M-3", category=cat, list_price="10")
    code = _code()
    survivor = _customer(env.db, code, "CASH SALES", OLD)
    retired = _customer(env.db, code, "BUYER-1", NEW)
    return code, survivor, retired, (p1, p2, p3)


# ------------------------------------------------------------------ profile only on the retired row


def test_ac_pc_10_a_profile_on_the_retired_row_only_moves_to_the_survivor(env):
    code, survivor, retired, (p1, p2, p3) = _world(env)
    env.profile(_P(retired), markup_pct=8, cost_method="average")
    env.party_product(_P(retired), p1)
    env.party_product(_P(retired), p2, markup_pct=11)
    env.db.flush()

    result = customer_merge.apply(env.db, run_id="run-pc-1", codes=[code])
    assert [g.survivor_id for g in result.merged] == [survivor]

    profile = _profile(env.db, survivor)
    assert profile is not None, "the retired customer's profile must follow the merge"
    assert float(profile[0]) == 8.0 and profile[1] == "average" and profile[2] is True
    assert _scalar(env.db, "SELECT count(*) FROM customer_costing_profiles WHERE customer_id = :c", c=retired) == 0
    assert _products(env.db, survivor) == {p1.id: None, p2.id: 11.0}
    assert _scalar(env.db, "SELECT count(*) FROM customers WHERE id = :c", c=retired) == 0


def test_ac_pc_10_a_profile_on_the_survivor_only_is_left_alone(env):
    code, survivor, retired, (p1, p2, p3) = _world(env)
    env.profile(_P(survivor), markup_pct=6)
    env.party_product(_P(survivor), p1, markup_pct=7)
    env.db.flush()
    customer_merge.apply(env.db, run_id="run-pc-2", codes=[code])
    assert float(_profile(env.db, survivor)[0]) == 6.0
    assert _products(env.db, survivor) == {p1.id: 7.0}


def test_ac_pc_10_a_merge_with_no_costing_rows_anywhere_is_unaffected(env):
    code, survivor, retired, (p1, p2, p3) = _world(env)
    result = customer_merge.apply(env.db, run_id="run-pc-3", codes=[code])
    assert [g.survivor_id for g in result.merged] == [survivor]
    assert _profile(env.db, survivor) is None
    assert _products(env.db, survivor) == {}


# ------------------------------------------------------------------ both rows have a profile


def test_ac_pc_10_both_have_a_profile_the_survivors_wins_and_product_sets_are_unioned(env):
    code, survivor, retired, (p1, p2, p3) = _world(env)
    env.profile(_P(survivor), markup_pct=8, cost_method="primary")
    env.party_product(_P(survivor), p1, markup_pct=10)   # overlap: survivor's 10 wins
    env.party_product(_P(survivor), p2)                  # survivor only
    env.profile(_P(retired), markup_pct=15, cost_method="last_po")
    env.party_product(_P(retired), p1, markup_pct=20)    # overlap: dropped
    env.party_product(_P(retired), p3, markup_pct=12)    # retired only: repointed, keeps its 12
    env.db.flush()

    result = customer_merge.apply(env.db, run_id="run-pc-4", codes=[code])
    assert [g.survivor_id for g in result.merged] == [survivor]

    profile = _profile(env.db, survivor)
    assert float(profile[0]) == 8.0 and profile[1] == "primary"  # the survivor's profile, untouched
    assert _scalar(env.db, "SELECT count(*) FROM customer_costing_profiles WHERE customer_id = :c", c=retired) == 0

    assert _products(env.db, survivor) == {p1.id: 10.0, p2.id: None, p3.id: 12.0}
    # the pair constraint still holds: exactly one row per product on the survivor
    assert _scalar(env.db, "SELECT count(*) FROM customer_costing_products WHERE customer_id = :c", c=survivor) == 3
    assert _scalar(env.db, "SELECT count(*) FROM customer_costing_products WHERE customer_id = :c", c=retired) == 0


def test_ac_pc_10_what_was_dropped_is_logged_in_the_merge_map(env):
    from app.models.order import CustomerMergeMap

    code, survivor, retired, (p1, p2, p3) = _world(env)
    env.profile(_P(survivor), markup_pct=8)
    env.party_product(_P(survivor), p1, markup_pct=10)
    env.profile(_P(retired), markup_pct=15, cost_method="average")
    env.party_product(_P(retired), p1, markup_pct=20)
    env.party_product(_P(retired), p3, markup_pct=12)
    env.db.flush()
    customer_merge.apply(env.db, run_id="run-pc-5", codes=[code])

    entry = env.db.query(CustomerMergeMap).filter(CustomerMergeMap.run_id == "run-pc-5").one()
    dropped = {}
    for d in entry.dropped:
        dropped.setdefault(d["table"].split(".")[-1], []).append(d["row"])
    profiles = dropped.get("customer_costing_profiles")
    assert profiles and len(profiles) == 1
    assert float(profiles[0]["markup_pct"]) == 15.0 and profiles[0]["cost_method"] == "average"
    products = dropped.get("customer_costing_products")
    assert products and len(products) == 1
    assert str(products[0]["product_id"]) == p1.id and float(products[0]["markup_pct"]) == 20.0
    # the repointed product row is in the map too, so a revert can send it back
    assert any(k.endswith("customer_costing_products.customer_id") for k in entry.repointed)


def test_ac_pc_10_a_revert_brings_the_retired_profile_and_products_back(env):
    code, survivor, retired, (p1, p2, p3) = _world(env)
    env.profile(_P(survivor), markup_pct=8)
    env.party_product(_P(survivor), p1, markup_pct=10)
    env.profile(_P(retired), markup_pct=15, cost_method="average")
    env.party_product(_P(retired), p1, markup_pct=20)
    env.party_product(_P(retired), p3, markup_pct=12)
    env.db.flush()
    customer_merge.apply(env.db, run_id="run-pc-6", codes=[code])
    assert customer_merge.revert(env.db, "run-pc-6") == 1

    assert float(_profile(env.db, retired)[0]) == 15.0
    assert _profile(env.db, retired)[1] == "average"
    assert _products(env.db, retired) == {p1.id: 20.0, p3.id: 12.0}
    assert _products(env.db, survivor) == {p1.id: 10.0}
    assert float(_profile(env.db, survivor)[0]) == 8.0


def test_ac_pc_10_a_retired_product_with_no_survivor_profile_conflict_is_the_only_move(env):
    """Both profiled, retired has a product the survivor lacks and none in common: it is repointed,
    nothing is dropped from the product table."""
    from app.models.order import CustomerMergeMap

    code, survivor, retired, (p1, p2, p3) = _world(env)
    env.profile(_P(survivor), markup_pct=8)
    env.profile(_P(retired), markup_pct=15)
    env.party_product(_P(retired), p1)
    env.db.flush()
    customer_merge.apply(env.db, run_id="run-pc-7", codes=[code])
    assert _products(env.db, survivor) == {p1.id: None}
    entry = env.db.query(CustomerMergeMap).filter(CustomerMergeMap.run_id == "run-pc-7").one()
    assert [d for d in entry.dropped if d["table"].split(".")[-1] == "customer_costing_products"] == []
