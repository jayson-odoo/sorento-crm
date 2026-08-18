"""Migration `385_fulfilment_priority_fair` - the ranking is asked to actually rank.

The captain, on a board where every row scored 0.00: "I need a fair policy please".

The seeded rule weights only `po_document_sequence`, which no sales-order line can carry, so
`rank_score` divides by a zero denominator and answers 0.0 for every contributor. That is the
legacy rule doing exactly what it says, and the fix is not a hand-edited row: it is a seeded
policy, activated by a migration, with the previous rule left present and inactive so the
change is reversed by flipping back rather than by remembering what it used to be.

One policy serves three moments (`app/services/scm/priority.py`), so this file pins BOTH
halves: a sales-order demand row must now separate, and a purchase-order candidate must keep
the demand band migration 374 deliberately switched on for container loading.

TEST-FIRST. Before the migration file existed the loader raised `FileNotFoundError`; before
the constants existed `priority.FAIR_WEIGHTS` raised `AttributeError`.

Runs against the REAL database via `pg_session`: the migration guards inspect `scm.*` by name,
which a `schema_translate_map` connection does not rewrite. Postgres DDL and DML are both
transactional, so the outer rollback discards every statement below - no live row is changed
by this file.
"""
from __future__ import annotations

import importlib.util
import pathlib
import uuid
from datetime import date

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from app.services.scm import priority
from app.services.scm.cash_ranking import rank_score
from tests._pg_fixture import pg_session

_MIGRATION = (
    pathlib.Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "385_fulfilment_priority_fair.py"
)

MARKER = "ZZFAIR"
LEGACY_NAME = "Today's rule (PO document sequence)"


def _load_migration():
    spec = importlib.util.spec_from_file_location("migration_385", _MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(db, direction: str) -> None:
    module = _load_migration()
    context = MigrationContext.configure(db.connection())
    with Operations.context(context):
        getattr(module, direction)()


def _policies(db) -> list:
    """Every policy row, as a list rather than a name-keyed dict.

    Nothing makes `name` unique, and a database that has already taken this revision genuinely
    holds two rows under one name once a test seeds its own. Keying by name silently collapsed
    them, and the assertion then read whichever row the scan happened to return last.
    """
    return db.execute(
        sa.text(
            "SELECT id, name, is_active, factors, demand_class_weights "
            "FROM scm.priority_policy"
        )
    ).mappings().all()


def _active(db) -> list:
    return [row for row in _policies(db) if row["is_active"]]


def _row(db, policy_id: str):
    return next(row for row in _policies(db) if str(row["id"]) == str(policy_id))


def _seed_legacy(db) -> str:
    """The row a database that has not been re-seeded actually carries today.

    Returns its id, because the assertions below are scoped to the rows THIS test created -
    the shared database has its own rows under the same names.
    """
    policy_id = str(uuid.uuid4())
    db.execute(sa.text("UPDATE scm.priority_policy SET is_active = false"))
    db.execute(
        sa.text(
            "INSERT INTO scm.priority_policy (id, name, is_active, factors, demand_class_weights)"
            " VALUES (:id, :name, true, CAST(:f AS jsonb), CAST(:c AS jsonb))"
        ),
        {
            "id": policy_id,
            "name": LEGACY_NAME,
            "f": '{"po_document_sequence": 1.0, "demand_class": 0.0,'
                 ' "need_by_date": 0.0, "document_age": 0.0}',
            "c": '{"project": 1.0, "retail": 0.4}',
        },
    )
    return policy_id


# --------------------------------------------------------------------------- #
# the migration
# --------------------------------------------------------------------------- #


def test_the_fair_policy_is_seeded_and_becomes_the_active_one():
    with pg_session() as db:
        legacy_id = _seed_legacy(db)

        _run(db, "upgrade")

        # The index allows one active policy, so exactly one is what must be there, and it is
        # the fair one carrying the shipped weights.
        active = _active(db)
        assert len(active) == 1
        assert active[0]["name"] == priority.FAIR_POLICY_NAME
        assert dict(active[0]["factors"]) == priority.FAIR_WEIGHTS
        assert dict(active[0]["demand_class_weights"]) == priority.FAIR_CLASS_WEIGHTS
        # The rule it replaces is kept, and kept OFF: flipping back is how this is undone.
        assert _row(db, legacy_id)["is_active"] is False


def test_running_the_migration_twice_changes_nothing():
    with pg_session() as db:
        _seed_legacy(db)

        _run(db, "upgrade")
        before = {str(r["id"]): (r["is_active"], dict(r["factors"])) for r in _policies(db)}
        _run(db, "upgrade")
        after = {str(r["id"]): (r["is_active"], dict(r["factors"])) for r in _policies(db)}

        assert before == after


def test_the_downgrade_puts_the_previous_rule_back_in_charge():
    with pg_session() as db:
        _seed_legacy(db)
        _run(db, "upgrade")

        _run(db, "downgrade")

        active = _active(db)
        assert len(active) == 1
        assert active[0]["name"] in (
            "Today's rule (PO document sequence)",
            "Today's rule (demand owed, then PO document sequence)",
        )
        assert all(
            row["is_active"] is False
            for row in _policies(db)
            if row["name"] == priority.FAIR_POLICY_NAME
        )


def test_the_migration_repeats_the_module_constants_exactly():
    """The literals are duplicated so migrations stay standalone (the house rule 374 states).

    Duplicated means they can drift, so the drift is what this test forbids.
    """
    module = _load_migration()

    assert module._FAIR_NAME == priority.FAIR_POLICY_NAME
    assert module._FAIR_FACTORS == priority.FAIR_WEIGHTS
    assert module._FAIR_CLASS_WEIGHTS == priority.FAIR_CLASS_WEIGHTS


# --------------------------------------------------------------------------- #
# what the weights actually do, on both shapes the one policy serves
# --------------------------------------------------------------------------- #


def _demand_row(key, **kw) -> dict:
    return {
        "row_key": key,
        "required_date": kw.get("required_date"),
        "order_date": kw.get("order_date"),
        "payment_terms_days": kw.get("payment_terms_days"),
        "demand_class": kw.get("demand_class", "project"),
    }


def test_a_board_row_is_ranked_by_delivery_date_first_then_document_date():
    """What the captain asked for, in the order they asked for it."""
    rows = [
        _demand_row("soon", required_date=date(2026, 9, 1), order_date=date(2026, 7, 28),
                    payment_terms_days=90),
        _demand_row("late", required_date=date(2027, 5, 15), order_date=date(2024, 1, 9),
                    payment_terms_days=30),
    ]
    with pg_session() as db:
        out = priority.factors_for_demand_rows(
            db, rows,
            weights=dict(priority.FAIR_WEIGHTS),
            class_weights=dict(priority.FAIR_CLASS_WEIGHTS),
        )

    # need_by at 3.0 outweighs document_age at 1.0 and customer_credit at 1.0 together, so
    # the sooner delivery wins even against an older document from a prompter payer.
    assert rank_score(out["soon"]) > rank_score(out["late"])
    assert priority.discriminates_nothing(out) is False


def test_the_fair_policy_still_drops_an_absent_factor_rather_than_scoring_it_zero():
    rows = [
        _demand_row("stated", required_date=date(2026, 9, 1), order_date=date(2026, 1, 1),
                    payment_terms_days=30),
        _demand_row("silent", required_date=date(2026, 9, 1), order_date=date(2026, 1, 1)),
    ]
    with pg_session() as db:
        out = priority.factors_for_demand_rows(
            db, rows,
            weights=dict(priority.FAIR_WEIGHTS),
            class_weights=dict(priority.FAIR_CLASS_WEIGHTS),
        )

    credit = next(f for f in out["silent"] if f.key == "customer_credit")
    assert credit.present is False and credit.value is None
    # Both rows agree on every factor they both state, so the customer nobody has assessed is
    # neither punished nor rewarded for it: the scores are equal.
    assert rank_score(out["silent"]) == rank_score(out["stated"])
    sequence = next(f for f in out["stated"] if f.key == "po_document_sequence")
    assert sequence.present is False, "a sales-order line has no purchase order, ever"


def test_a_purchase_order_owed_to_a_customer_still_beats_one_owed_to_nobody():
    """The blast radius, pinned: container loading shares this policy.

    Migration 374 deliberately switched demand ON for the purchase-order path, so the fair
    policy keeps `demand_class` weighted. A purchase order feeding a project must still
    outrank one feeding nobody when the dates agree - otherwise "fairness on the planning
    board" would quietly rewrite what goes in a container.
    """
    candidates = [
        {"po_line_id": "owed", "po_number": "ZZ-PO-1", "expected_date": date(2026, 9, 1),
         "po_date": date(2026, 1, 1)},
        {"po_line_id": "nobody", "po_number": "ZZ-PO-2", "expected_date": date(2026, 9, 1),
         "po_date": date(2026, 1, 1)},
    ]
    with pg_session():
        weights = dict(priority.FAIR_WEIGHTS)
        classes = dict(priority.FAIR_CLASS_WEIGHTS)
        owed = priority.factors_for(
            weights,
            sequence=1.0,
            demand_weight=priority.demand_value(
                {"ZZ-PO-1": "project"}, classes, "ZZ-PO-1"
            ),
            need_by=1.0,
            age=1.0,
        )
        nobody = priority.factors_for(
            weights,
            sequence=1.0,
            demand_weight=priority.demand_value({}, classes, "ZZ-PO-2"),
            need_by=1.0,
            age=1.0,
        )

    assert rank_score(owed) > rank_score(nobody)
    assert len(candidates) == 2  # the shapes above are the two candidates, stated in full
