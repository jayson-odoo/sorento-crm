"""Who is ahead of a line, and why: the two review findings on it (19 August 2026).

F7: `_facts_for` (the sheet read, and every confirm) asked `_attribution` for the ahead
    DETAIL of every line of every pile - `_leading_factor` per pair, quadratic on a crowded
    pile - and nothing on the sheet reads it. The board asks for it by line id; the sheet asks
    for none.

F10: `_leading_factor` named the wrong thing twice. Equal scores were always `tie_break`
    ("the same rank and a lower sales order number") although `_pile_book` breaks a tie on
    the required date FIRST; and a line ahead only through a factor absent on MY side (they
    have payment terms, I have none) fell through to the same tie-break because every shared
    difference was <= 0.

Pure-function tests for F10; the sheet fixture from the Stage 1C suite for F7. Postgres via
`tests/_pg_fixture.py::blank_session` through that fixture, per PRINCIPLES.
"""
from __future__ import annotations

from datetime import date
from unittest.mock import patch

from app.services.scm.cash_ranking import Factor

from .test_so_supply_confirmation import (  # noqa: F401  (api is a fixture)
    _core_line,
    _core_so,
    _project_line,
    _project_so,
    _stock,
    api,
)


def _factors(**values: float | None) -> list:
    """`need_by_date` weighs 3, `document_age` and `customer_credit` weigh 1; None is absent."""
    weights = {"need_by_date": 3.0, "document_age": 1.0, "customer_credit": 1.0}
    return [
        Factor(key=key, weight=weight, value=values.get(key), present=values.get(key) is not None)
        for key, weight in weights.items()
    ]


def _row(so_number: str, score: float, required_date=None, **values) -> dict:
    return {
        "so_number": so_number,
        "rank_score": score,
        "required_date": required_date,
        "factors": _factors(**values),
    }


# --------------------------------------------------------------------------- F10


def test_the_largest_shared_weighted_difference_names_the_factor():
    from app.services.project_supply_service import _leading_factor

    mine = _row("SO2", 0.5, need_by_date=0.5, document_age=0.5, customer_credit=0.5)
    theirs = _row("SO1", 0.8, need_by_date=1.0, document_age=0.5, customer_credit=0.5)
    assert _leading_factor(mine, theirs) == "need_by_date"


def test_a_factor_they_carry_and_i_do_not_is_what_put_them_ahead():
    """They have payment terms and I have none: every SHARED difference is 0, and the old
    rule fell through to "a lower sales order number", which is not why they are ahead."""
    from app.services.project_supply_service import _leading_factor

    mine = _row("SO2", 0.5, need_by_date=0.5, document_age=0.5, customer_credit=None)
    theirs = _row("SO1", 0.6, need_by_date=0.5, document_age=0.5, customer_credit=1.0)
    assert _leading_factor(mine, theirs) == "customer_credit"


def test_a_shared_difference_still_beats_a_smaller_absent_one():
    from app.services.project_supply_service import _leading_factor

    mine = _row("SO2", 0.4, need_by_date=0.0, document_age=0.5, customer_credit=None)
    # 3 * (1.0 - 0.0) on the date beats 1 * 0.2 on the terms I do not carry.
    theirs = _row("SO1", 0.9, need_by_date=1.0, document_age=0.5, customer_credit=0.2)
    assert _leading_factor(mine, theirs) == "need_by_date"


def test_equal_scores_with_an_earlier_required_date_name_the_date_tie():
    """`_pile_book` breaks a tie on the required date first, so that is what put them ahead."""
    from app.services.project_supply_service import _leading_factor

    mine = _row("SO1", 0.0, required_date=date(2026, 9, 3))
    theirs = _row("SO2", 0.0, required_date=date(2026, 9, 1))
    assert _leading_factor(mine, theirs) == "earlier_date"


def test_equal_scores_where_only_they_have_a_date_name_the_date_tie():
    from app.services.project_supply_service import _leading_factor

    mine = _row("SO1", 0.0, required_date=None)
    theirs = _row("SO2", 0.0, required_date=date(2026, 9, 1))
    assert _leading_factor(mine, theirs) == "earlier_date"


def test_equal_scores_and_dates_in_the_same_order_are_line_order():
    from app.services.project_supply_service import _leading_factor

    mine = _row("SO1", 0.0, required_date=date(2026, 9, 3))
    theirs = _row("SO1", 0.0, required_date=date(2026, 9, 3))
    assert _leading_factor(mine, theirs) == "line_order"


def test_equal_scores_and_dates_across_orders_are_the_sales_order_tie_break():
    from app.services.project_supply_service import _leading_factor

    mine = _row("SO2", 0.0, required_date=date(2026, 9, 3))
    theirs = _row("SO1", 0.0, required_date=date(2026, 9, 3))
    assert _leading_factor(mine, theirs) == "tie_break"


def test_the_ahead_phrase_has_words_for_the_date_tie():
    from app.services.project_fulfilment_board_service import _ahead_phrase

    assert _ahead_phrase({"earlier_date": 4}) == "the same rank and an earlier delivery date"
    assert "earlier_date" not in _ahead_phrase({"earlier_date": 4, "tie_break": 1})


# --------------------------------------------------------------------------- F7


def test_the_sheet_read_does_not_describe_the_queue_of_every_line_of_every_pile(api):
    """`_facts_for` never reads the ahead detail, so it must not pay for it."""
    from app.services import project_supply_service as module
    from app.services.project_supply_service import ProjectSupplyService

    _client, world = api
    db = world.db
    _stock(db, world.product, world.own_wh, on_hand=100)
    # A crowded pile: five other lines competing for the same stock.
    for _index in range(5):
        other_so = _core_so(db, world.company_id)
        _core_line(db, other_so, world.product, world.own_wh, qty_ordered="10")
    order = _project_so(db, world.project)
    core_so = _core_so(db, world.company_id)
    core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="50")
    line = _project_line(db, order, line_no=10, product=world.product, core_line=core_line)
    db.commit()

    service = ProjectSupplyService(db)
    with patch.object(module, "_ahead_detail", wraps=module._ahead_detail) as spy:
        facts = service._facts_for(order, [line])

    assert str(line.id) in facts
    assert facts[str(line.id)].own_free > 0, "the share itself is still computed"
    assert spy.call_count == 0, "the sheet asked for nobody's queue"
