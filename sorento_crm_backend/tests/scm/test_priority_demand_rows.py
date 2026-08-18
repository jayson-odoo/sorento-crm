"""Fulfilment Priority for SALES-ORDER demand rows (PLAN section 13.5).

TEST-FIRST, and written from the intended semantics rather than from the code: the Phase 1
prototype had `document_age` inverted at one point, with the NEWEST document winning, and a
test written after the fact would have enshrined that. So the ordering assertions below name
concrete dates and say which one has to win before anything is implemented.

What is under test is `factors_for_demand_rows`, the SIBLING of `factors_for_candidates`:
same policy row, same `rank_score`, same central rule that an ABSENT factor is dropped from
both sums and never scored zero. The purchase-order assembly is not touched; a board row is
a sales-order line and has no purchase order behind it, so forcing one through the other's
signature would mean inventing a `po_line_id`.

Postgres only (PRINCIPLES). The pure-value tests pass weights in directly so they say what
they mean; the two policy tests seed their own `scm.priority_policy` row.
"""
from __future__ import annotations

import uuid
from datetime import date

from app.services.scm import priority
from app.services.scm.cash_ranking import rank_score
from tests._pg_fixture import pg_session

MARKER = "ZZPDR"


def _row(key: str, **kw) -> dict:
    """One demand row. Everything absent unless the test states it."""
    return {
        "row_key": key,
        "required_date": kw.get("required_date"),
        "order_date": kw.get("order_date"),
        "payment_terms_days": kw.get("payment_terms_days"),
        "demand_class": kw.get("demand_class", "project"),
    }


def _score(factors) -> float:
    return rank_score(factors)


def _value(factors, key: str):
    return next(f for f in factors if f.key == key).value


def _factor(factors, key: str):
    return next(f for f in factors if f.key == key)


# --------------------------------------------------------------------------- #
# the three factors a board row can carry
# --------------------------------------------------------------------------- #


def test_sooner_required_date_ranks_higher():
    rows = [
        _row("soon", required_date=date(2026, 9, 4)),
        _row("late", required_date=date(2027, 5, 15)),
    ]
    with pg_session() as db:
        out = priority.factors_for_demand_rows(
            db, rows, weights={"need_by_date": 1.0}, class_weights={}
        )
    assert _value(out["soon"], "need_by_date") == 1.0
    assert _value(out["late"], "need_by_date") == 0.0
    assert _score(out["soon"]) > _score(out["late"])


def test_older_document_ranks_higher():
    """The one the prototype got backwards: 2023 must beat 2026, not the other way round."""
    rows = [
        _row("old", order_date=date(2023, 12, 8)),
        _row("new", order_date=date(2026, 7, 28)),
    ]
    with pg_session() as db:
        out = priority.factors_for_demand_rows(
            db, rows, weights={"document_age": 1.0}, class_weights={}
        )
    assert _value(out["old"], "document_age") == 1.0, "the OLDER document must score 1.0"
    assert _value(out["new"], "document_age") == 0.0
    assert _score(out["old"]) > _score(out["new"])


def test_shorter_payment_terms_rank_higher():
    """`customer_credit` is payment TERMS, and 30 days beats 90 (13.5).

    Not `credit_limit`: it reaches 8 of 11,166 open project lines, so a factor keyed on it
    would rank essentially nothing.
    """
    rows = [
        _row("cash", payment_terms_days=30),
        _row("slow", payment_terms_days=90),
    ]
    with pg_session() as db:
        out = priority.factors_for_demand_rows(
            db, rows, weights={"customer_credit": 1.0}, class_weights={}
        )
    assert _value(out["cash"], "customer_credit") == 1.0
    assert _value(out["slow"], "customer_credit") == 0.0
    assert _score(out["cash"]) > _score(out["slow"])


# --------------------------------------------------------------------------- #
# absence, in all four of its shapes
# --------------------------------------------------------------------------- #


def test_a_customer_with_no_terms_is_absent_never_best_and_never_worst():
    rows = [
        _row("cash", payment_terms_days=30),
        _row("unknown"),
        _row("slow", payment_terms_days=90),
    ]
    with pg_session() as db:
        out = priority.factors_for_demand_rows(
            db, rows, weights={"customer_credit": 1.0}, class_weights={}
        )
    unknown = _factor(out["unknown"], "customer_credit")
    assert unknown.present is False and unknown.value is None
    # Dropped from both sums, so it is neither the best nor the worst - it simply does not
    # take part. A customer nobody has assessed is not thereby the safest or the riskiest.
    assert _score(out["unknown"]) == 0.0
    assert _score(out["cash"]) == 1.0
    assert _score(out["slow"]) == 0.0


def test_an_absent_factor_is_dropped_from_both_sums_not_scored_zero():
    """The rule the whole module rests on, stated as arithmetic.

    One row states a required date and no order date; the other states both. Under equal
    weights the first must score its need-by value alone (1.0), NOT the average of 1.0 and
    a fabricated zero.
    """
    rows = [
        _row("dateless", required_date=date(2026, 9, 4)),
        _row("complete", required_date=date(2027, 5, 15), order_date=date(2026, 1, 1)),
    ]
    with pg_session() as db:
        out = priority.factors_for_demand_rows(
            db,
            rows,
            weights={"need_by_date": 1.0, "document_age": 1.0},
            class_weights={},
        )
    assert _factor(out["dateless"], "document_age").present is False
    assert _score(out["dateless"]) == 1.0
    assert _score(out["complete"]) == 0.5


def test_po_document_sequence_is_structurally_absent_on_every_demand_row():
    """A sales-order line has no purchase order behind it, so this can never have a value."""
    rows = [_row("a", required_date=date(2026, 9, 4))]
    with pg_session() as db:
        out = priority.factors_for_demand_rows(
            db, rows, weights=dict(priority.SEEDED_WEIGHTS), class_weights={}
        )
    sequence = _factor(out["a"], "po_document_sequence")
    assert sequence.present is False and sequence.value is None


def test_a_demand_class_the_policy_does_not_weight_is_absent():
    rows = [_row("unweighted", demand_class="wholesale")]
    with pg_session() as db:
        out = priority.factors_for_demand_rows(
            db, rows, weights={"demand_class": 1.0}, class_weights={"project": 1.0}
        )
    assert _factor(out["unweighted"], "demand_class").present is False


def test_demand_class_is_present_but_constant_on_a_project_board():
    rows = [_row("a"), _row("b")]
    with pg_session() as db:
        out = priority.factors_for_demand_rows(
            db, rows, weights={"demand_class": 1.0}, class_weights={"project": 1.0}
        )
    assert _factor(out["a"], "demand_class").present is True
    assert _value(out["a"], "demand_class") == _value(out["b"], "demand_class")
    # Present, weighted, and it still separates nobody: every row on this board is
    # project-class by construction.
    assert priority.discriminates_nothing(out) is True


# --------------------------------------------------------------------------- #
# the flat ranking, reported honestly
# --------------------------------------------------------------------------- #


def test_a_policy_weighting_only_absent_factors_scores_every_row_flat_and_says_so():
    """The live seeded rule, on the board: `po_document_sequence` 1.0, everything else 0.0.

    Every row scores 0.0. That is not a bug in the scorer - it is the legacy rule doing
    what it says - so the board has to report it rather than show a plausible-looking order.
    """
    rows = [
        _row("a", required_date=date(2026, 9, 4), order_date=date(2023, 12, 8)),
        _row("b", required_date=date(2027, 5, 15), order_date=date(2026, 7, 28)),
    ]
    with pg_session() as db:
        out = priority.factors_for_demand_rows(
            db,
            rows,
            weights={
                "po_document_sequence": 1.0,
                "demand_class": 0.0,
                "need_by_date": 0.0,
                "document_age": 0.0,
            },
            class_weights={"project": 1.0},
        )
    assert _score(out["a"]) == 0.0 and _score(out["b"]) == 0.0
    assert priority.discriminates_nothing(out) is True


def test_a_policy_that_does_separate_the_rows_is_not_reported_as_flat():
    rows = [
        _row("a", required_date=date(2026, 9, 4)),
        _row("b", required_date=date(2027, 5, 15)),
    ]
    with pg_session() as db:
        out = priority.factors_for_demand_rows(
            db, rows, weights=dict(priority.BOARD_PREVIEW_WEIGHTS), class_weights={}
        )
    assert priority.discriminates_nothing(out) is False


# --------------------------------------------------------------------------- #
# the policy row itself
# --------------------------------------------------------------------------- #


def _policy(db, factors: dict, class_weights: dict | None = None, *, name: str | None = None,
            active: bool = True) -> str:
    """A policy owned by this test. Deactivates the incumbent rather than deleting it."""
    from app.models.scm import PriorityPolicy

    if active:
        db.query(PriorityPolicy).filter(PriorityPolicy.is_active.is_(True)).update(
            {"is_active": False}, synchronize_session=False
        )
    row = PriorityPolicy(
        id=str(uuid.uuid4()),
        name=name or f"{MARKER}-policy-{uuid.uuid4().hex[:6]}",
        is_active=active,
        factors=factors,
        demand_class_weights=class_weights or {},
    )
    db.add(row)
    db.flush()
    return str(row.id)


def test_the_active_policy_row_is_what_weights_a_demand_row():
    rows = [
        _row("soon", required_date=date(2026, 9, 4), order_date=date(2026, 7, 28)),
        _row("old", required_date=date(2027, 5, 15), order_date=date(2023, 12, 8)),
    ]
    with pg_session() as db:
        _policy(db, {"need_by_date": 0.0, "document_age": 1.0}, {"project": 1.0})
        out = priority.factors_for_demand_rows(db, rows)
        # Weighted on document age alone, so the older document wins despite the later date.
        assert _score(out["old"]) > _score(out["soon"])
        assert _factor(out["old"], "document_age").weight == 1.0
        assert _factor(out["old"], "need_by_date").weight == 0.0


def test_a_named_policy_can_be_read_without_being_activated():
    """The preview (13.5, recommendation 3): a what-if, never a second active policy."""
    with pg_session() as db:
        live = _policy(db, {"po_document_sequence": 1.0}, {"project": 1.0})
        _policy(db, {"need_by_date": 1.0}, {"project": 1.0},
                name=f"{MARKER}-what-if", active=False)

        found = priority.policy_by_name(db, f"{MARKER}-what-if")

        assert found is not None
        assert found.is_active is False
        assert dict(found.factors) == {"need_by_date": 1.0}
        # The live row is untouched: a preview activates nothing.
        assert str(priority.active_policy(db).id) == live


def test_payment_terms_are_read_off_the_customer_when_the_column_is_there():
    """`customers.payment_terms_days` exists in the database but not on the ORM model.

    Same situation as `customers.credit_limit`, and read the same guarded way
    (`project_so_draft_service._credit_limit`): a scratch schema built from the models alone
    does not have the column, and an unguarded statement would poison the transaction rather
    than answering "nobody has assessed this customer".
    """
    from sqlalchemy import text

    from app.models.order import Customer
    from tests._pg_fixture import blank_session

    with blank_session() as db:
        db.execute(
            text("ALTER TABLE customers ADD COLUMN IF NOT EXISTS payment_terms_days integer")
        )
        customer = Customer(
            id=str(uuid.uuid4()),
            customer_code=f"{MARKER}-{uuid.uuid4().hex[:6]}",
            customer_name=f"{MARKER} customer",
        )
        db.add(customer)
        db.flush()
        db.execute(
            text("UPDATE customers SET payment_terms_days = 45 WHERE id = :id"),
            {"id": str(customer.id)},
        )

        terms = priority.payment_terms_by_customer(db, [str(customer.id)])

        assert terms == {str(customer.id): 45}


def test_a_database_without_the_terms_column_answers_absent_rather_than_erroring():
    """The guard on the unmapped column, proved rather than assumed.

    A scratch schema built from the ORM models alone has no `payment_terms_days`, and an
    unguarded statement there would poison the surrounding transaction instead of answering
    "nobody has assessed this customer". Read against the blank schema, which is exactly that
    database.
    """
    from sqlalchemy import text as sql

    from app.models.order import Customer
    from tests._pg_fixture import blank_session

    with blank_session() as db:
        db.execute(sql("ALTER TABLE customers DROP COLUMN IF EXISTS payment_terms_days"))
        customer = Customer(
            id=str(uuid.uuid4()),
            customer_code=f"{MARKER}-{uuid.uuid4().hex[:6]}",
            customer_name=f"{MARKER} customer",
        )
        db.add(customer)
        db.flush()

        assert priority.payment_terms_by_customer(db, [str(customer.id)]) == {}
        # And the session is still usable, which is the half a swallowed error would lose.
        assert db.query(Customer).filter(Customer.id == customer.id).first() is not None
