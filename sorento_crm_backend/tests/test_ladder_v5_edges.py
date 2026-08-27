"""Ladder v5 edges the captain's own walk-through (`PLAN-scm-cs-planning-uat.md` 1e) and the
two proof files (`tests/scm/test_ladder_v5.py`, `tests/test_ladder_v5_proof.py`) do not
already pin: a cap that genuinely binds rather than being trivially exceeded, the whole-line
rule's own sentence on the question that HAD stock, a late SPO's overdue days as the trail and
the drill-down table each treat them, a decided line carrying a frozen incoming component
beside a stale suggestion stamp, a payload-wide scan for leaked rung vocabulary, the other-group
block's zero-holding sibling and its exact arithmetic, and the query-count bound on a big board.

TESTER'S BRIEF: pin current behaviour. Where a fixture in the brief describes something the
ladder's own rules (as ruled in section 1e) make impossible - a PARTIAL cross-group take, for
one - the docstring says so and the test asserts what the code actually does instead, never
what the brief assumed.

Postgres via `blank_session`, every FK target seeded here (CI's database is empty).
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import event

from ._pg_fixture import blank_session
from .test_fulfilment_board import (  # noqa: F401  (helpers, not fixtures)
    MARKER,
    TODAY,
    _adopt,
    _cell,
    _confirm,
    _incoming,
    _line,
    _order,
    _product,
    _service,
    _step,
    _stock,
    _uid,
    _user,
    _warehouse,
)
from .test_ladder_v5_proof import BUCKET, WHEN, _cap, _contribution, _locations


# --------------------------------------------------------------------------- #
# 1. Question 3's cap sentence, genuinely binding (not trivially exceeded)
# --------------------------------------------------------------------------- #


def test_question_three_names_the_cap_when_the_margin_is_close_not_only_when_huge():
    """AC-V4, a second fixture deliberately close to the boundary the sentence is judged
    on, rather than the existing pin's donor of 500 against a cap of 10 (a huge margin).

    Donor net 100, cap (qty) 20, need 24: the donor could very nearly cover the whole line
    on its own, and the cap alone stands between it and a Yes.

    THE RULE IS BINARY, by the plan's own words (section 1e's table: "Yes, N" or "No ...
    the cap (N) is below what is left" - there is no third answer). So there is no
    quantity for "the proposal takes exactly the cap" to describe: nothing is composed at
    all once the cap refuses the residual, and the whole line buys entire. What this test
    pins instead is that the sentence quotes the CONFIGURED cap (20) and the exact
    residual (24) verbatim - not the donor's own 100, not a percentage-derived figure -
    and that the composition is one whole-line Buy, not a Borrow-then-Buy split.
    """
    with blank_session() as db:
        product = _product(db, f"ZZT-{_uid()[:6]}")
        own = _warehouse(db, f"ZZTM{_uid()[:5]}-BB"[:20])
        donor = _warehouse(db, f"ZZTM{_uid()[:5]}-NTC"[:20])
        _stock(db, product, own, on_hand=0)
        _stock(db, product, donor, on_hand=100)
        _cap(db, max_qty=20, max_pct=0.0)
        order = _order(db, so_number=f"ZZT-SO-{_uid()[:8]}", order_date=date(2026, 1, 1))
        _line(db, order, product, qty="24", required_date=WHEN, warehouse=own)

        contribution = _contribution(db, order, product)

        step = _step(contribution, "cross_group_borrow")
        assert step["answer"] == "no"
        assert step["took"] == "0"
        assert "cross-group borrow limit is 20" in step["why"]
        assert "24 is still needed" in step["why"]
        assert donor.warehouse_code in step["why"]

        buy = _step(contribution, "buy")
        assert buy["answer"] == "yes"
        assert buy["took"] == "24"
        assert [s["kind"] for s in contribution["sources"]] == ["buy"]
        assert contribution["sources"][0]["qty"] == "24"


# --------------------------------------------------------------------------- #
# 2. The whole-line rule's own sentence, on the question that HAD stock
# --------------------------------------------------------------------------- #


def test_question_one_names_the_whole_line_rule_when_it_had_stock_but_not_enough():
    """The sentence pinned by name: `_WHOLE_LINE_RULE_DROPPED` - "It had stock to give,
    but the questions together could not cover the whole line, so none of it is taken and
    the line is bought entire." Own group free 10, no pool, no donor anywhere else, need
    24: 10 of 24 is short, so nothing is taken and the whole line buys - and question 1 is
    the one that HAD something and gave it back, so it is the one that must carry this
    sentence rather than a plain "nothing here".
    """
    with blank_session() as db:
        product = _product(db, f"ZZT-{_uid()[:6]}")
        own = _warehouse(db, f"ZZTN{_uid()[:5]}-BB"[:20])
        pool = _warehouse(db, f"ZZTN{_uid()[:5]}"[:20])
        own.pool_warehouse_id = pool.id
        db.flush()
        _stock(db, product, own, on_hand=10)
        _stock(db, product, pool, on_hand=0)
        order = _order(db, so_number=f"ZZT-SO-{_uid()[:8]}", order_date=date(2026, 1, 1))
        _line(db, order, product, qty="24", required_date=WHEN, warehouse=own)

        contribution = _contribution(db, order, product)

        own_step = _step(contribution, "own")
        assert own_step["answer"] == "no"
        assert own_step["took"] == "0"
        assert "could not cover the whole line" in own_step["why"]
        assert "bought entire" in own_step["why"]

        buy = _step(contribution, "buy")
        assert buy["answer"] == "yes"
        assert buy["took"] == "24"
        assert [s["kind"] for s in contribution["sources"]] == ["buy"]
        assert contribution["sources"][0]["qty"] == "24"


# --------------------------------------------------------------------------- #
# 3. A late SPO backing the group's only cover: what the trail says, and does not
# --------------------------------------------------------------------------- #


def test_a_late_spo_backing_the_groups_only_cover_is_silent_in_the_trail_but_named_in_the_table():
    """CAPTAIN'S OPEN QUESTION (not ruled): `app/services/scm/spo_supply.py`'s own module
    docstring says a passed promise is "stated as OVERDUE wherever it is named ... so a
    buyer reading the TRAIL or the popover can see which promise is being leaned on and go
    and chase it." Ladder v5 folds the SPO into the ownership group's net (section 1e's
    first bullet) and question 1 never reads the document's own date at all - a group
    covered ONLY by a promise 40 days overdue answers "Yes, took N" in exactly the same
    words it would for stock already on the shelf.

    Pinned as a SPLIT rather than argued with: the DRILL-DOWN table (`stock_detail`, which
    backs the frontend's `StockDocumentsPanel`) still carries `overdue_days` and the
    frontend still renders "(overdue N days)" from it - that half is right, and this test
    proves it. The trail's own sentence is the half that does not name it. Left for the
    captain: should question 1's own why-sentence also say "overdue N days" when its only
    cover is a late promise, the way the retired rung-1 sentence (`spo_reason`) did?
    """
    with blank_session() as db:
        product = _product(db, f"ZZT-{_uid()[:6]}")
        own = _warehouse(db, f"ZZTP{_uid()[:5]}-BB"[:20])
        # `overdue_days` is measured against the WALL CLOCK (`spo_supply.overdue_days`'s
        # own default), not against the board's `as_of` dial - so the arrival is dated off
        # `date.today()`, never off the fixture's own `TODAY` constant.
        late = _incoming(
            db, product, own, spo_number="ZZT-SPO-LATE", allocated=40, received=0,
            arrives=date.today() - timedelta(days=40),
        )
        order = _order(db, so_number=f"ZZT-SO-{_uid()[:8]}", order_date=date(2026, 1, 1))
        _line(db, order, product, qty="40", required_date=WHEN, warehouse=own)

        contribution = _contribution(db, order, product)

        own_step = _step(contribution, "own")
        assert own_step["answer"] == "yes", "the group net offers it (section 1e/1d)"
        assert own_step["took"] == "40"
        assert "overdue" not in own_step["why"].lower(), (
            "current behaviour: the group's net absorbs the late promise silently"
        )
        assert own_step["note"] is None or "overdue" not in own_step["note"].lower()

        detail = _service(db).stock_detail(str(product.id), str(own.id))
        incoming_row = next(
            row for row in detail["incoming"] if row["spo_number"] == late.spo_number
        )
        assert incoming_row["overdue_days"] == 40, (
            "the table still carries the raw fact, even though the trail's prose does not"
        )


# --------------------------------------------------------------------------- #
# 4. A decided line with a frozen incoming component, and a stale suggestion stamp
# --------------------------------------------------------------------------- #


def test_a_decided_incoming_component_totals_on_the_contribution_and_stales_correctly():
    """AC-V8 + section 3.D's own accounting, wired through the board endpoint.

    `timely_spo_qty` is still an accepted `confirm` field (`ConfirmLine.timely_spo_qty`)
    even though the LIVE ladder never proposes one under v5 - a planner can still record a
    decision that way. `qty_proposed_incoming` on the DECIDED contribution totals it
    (`_apply_frozen` reads it straight off `decision["timely_spo_qty"]`), and it still
    renders.

    The frozen SUGGESTION beside it is downgraded here (direct model write, the same
    technique `test_so_supply_confirmation.py`'s own ladder-stamp test uses) to simulate
    one written before v5 shipped - what `BoardCellBreakdownDialog`'s `suggestionIsStale`
    reads to print "Suggestion (before ladder v5)". A second, undecided line on the same
    order carries no such staleness: every part of its live suggestion is stamped
    `ladder: "v5"` (AC-V8's other half).
    """
    from app.models.project_so import ProjectSalesOrderLine, SOSupplyDecision

    with blank_session() as db:
        product = _product(db, f"ZZT-{_uid()[:6]}")
        own = _warehouse(db, f"ZZTQ{_uid()[:5]}-BB"[:20])
        _incoming(
            db, product, own, spo_number="ZZT-SPO-DEC", allocated=15, received=0,
            arrives=WHEN - timedelta(days=5),
        )
        order = _order(db, so_number=f"ZZT-SO-{_uid()[:8]}", order_date=date(2026, 1, 1))
        decided_core = _line(
            db, order, product, qty="15", required_date=WHEN, warehouse=own,
        )

        other_product = _product(db, f"ZZT-{_uid()[:6]}")
        other_own = _warehouse(db, f"ZZTQ{_uid()[:5]}-BB"[:20])
        _line(
            db, order, other_product, qty="8", required_date=WHEN, warehouse=other_own,
        )

        pso_id = _adopt(db, str(order.id))
        mirror = (
            db.query(ProjectSalesOrderLine)
            .filter(
                ProjectSalesOrderLine.project_sales_order_id == pso_id,
                ProjectSalesOrderLine.core_sales_order_line_id == decided_core.id,
            )
            .first()
        )
        actor = _user(db, f"{MARKER} planner")
        _confirm(
            db, pso_id, actor,
            [{"project_line_id": str(mirror.id), "timely_spo_qty": "15"}],
        )

        decision = (
            db.query(SOSupplyDecision)
            .filter(SOSupplyDecision.project_sales_order_id == pso_id)
            .order_by(SOSupplyDecision.revision_no.desc())
            .first()
        )
        # DEEP copy, not `list(...)`: a shallow copy shares the same nested dicts, so
        # mutating them in place changes the ORIGINAL value too and SQLAlchemy's history
        # comparison (before == after, by content) sees no change and skips the UPDATE.
        import copy

        snapshots = copy.deepcopy(decision.line_snapshots)
        for snapshot in snapshots:
            if snapshot.get("core_line_id") == str(decided_core.id):
                for component in snapshot.get("proposed_components") or []:
                    component["ladder"] = "v4"
        decision.line_snapshots = snapshots
        db.commit()

        board = _service(db).build([order.so_number], granularity="week", as_of=TODAY)

        decided_contribution = _cell(board, product.product_code, BUCKET)["contributions"][0]
        assert decided_contribution["covered"] is True
        assert decided_contribution["qty_proposed_incoming"] == "15"
        proposed_parts = decided_contribution["proposed"]["components"]
        assert proposed_parts, "the frozen suggestion is still recorded beside the decision"
        assert any(part.get("ladder") != "v5" for part in proposed_parts), (
            "the frozen suggestion predates v5, which is the stale signal the FE reads"
        )

        undecided_contribution = _cell(
            board, other_product.product_code, BUCKET
        )["contributions"][0]
        assert undecided_contribution["covered"] is False
        assert {
            part["ladder"] for part in undecided_contribution["proposed"]["components"]
        } == {"v5"}, "an undecided line never carries a stale stamp"


# --------------------------------------------------------------------------- #
# 5. The trail payload's shape, and no leaked rung vocabulary anywhere in its prose
# --------------------------------------------------------------------------- #

#: The engine's INTERNAL rung keys. Legitimate as the VALUE of `kind` / `rung` (addressing),
#: never inside a rendered sentence (`why` / `note` / `reason`) - section 1e's own words:
#: "the rung names are internal keys under ladder v5 and never reach a reader".
_RUNG_TOKENS = ("group_take", "cross_group_borrow", "group_borrow", "timely_spo")


def _prose_strings(contribution) -> list:
    """Every rendered sentence in a contribution payload - never the addressing fields."""
    out = []
    for step in contribution["trail"]:
        if step.get("why"):
            out.append(step["why"])
        if step.get("note"):
            out.append(step["note"])
    for source in contribution["sources"]:
        if source.get("reason"):
            out.append(source["reason"])
    proposed = contribution.get("proposed") or {}
    for component in proposed.get("components") or []:
        if component.get("reason"):
            out.append(component["reason"])
    return out


def test_the_trail_is_five_rows_with_no_leaked_rung_vocabulary_and_a_note_that_agrees():
    """AC-V1 shape (five rows, each with `answer` / `took` / `from` / `why`) plus two
    things the existing proof pins do not: a scan of EVERY rendered sentence in the whole
    payload for the engine's internal rung tokens (not merely the trail's own `kind`
    list), and a POSITIVE case for "the suggestion note equals what the trail rows
    imply" - AC-V4's own pin only checks the negative (a cap-refused donor is never named
    in the Buy). Here a donor is NOT refused by the cap, only too small to finish the
    line alone, so question 3 says "could not cover the whole line" and the Buy's own
    sentence is EXPECTED to say borrowing from it is possible - the two must agree in
    both directions, not only when the answer is silence.
    """
    with blank_session() as db:
        product = _product(db, f"ZZT-{_uid()[:6]}")
        own = _warehouse(db, f"ZZTR{_uid()[:5]}-BB"[:20])
        pool = _warehouse(db, f"ZZTR{_uid()[:5]}"[:20])
        own.pool_warehouse_id = pool.id
        db.flush()
        donor = _warehouse(db, f"ZZTR{_uid()[:5]}-NTC"[:20])
        _stock(db, product, own, on_hand=0)
        _stock(db, product, pool, on_hand=0)
        _stock(db, product, donor, on_hand=10)
        _cap(db, max_qty=50, max_pct=0.0)
        order = _order(db, so_number=f"ZZT-SO-{_uid()[:8]}", order_date=date(2026, 1, 1))
        _line(db, order, product, qty="24", required_date=WHEN, warehouse=own)

        contribution = _contribution(db, order, product)

        # ---- shape ----
        assert [step["question"] for step in contribution["trail"]] == [
            "Can we use our location?",
            "Can we take from the pool?",
            "Can we borrow from another location?",
            "Can we borrow from the same agent's other order in this group?",
            "Buy the rest?",
        ]
        for step in contribution["trail"]:
            assert step["answer"] in ("yes", "no")
            assert isinstance(step["took"], str)
            assert "from" in step
            assert step["why"]

        # ---- no leaked vocabulary anywhere rendered ----
        for text in _prose_strings(contribution):
            for token in _RUNG_TOKENS:
                assert token not in text, (token, text)

        # ---- the donor was offered, not refused by the cap, and the whole line still
        #      buys because 10 alone cannot finish 24 ----
        cross = _step(contribution, "cross_group_borrow")
        assert cross["answer"] == "no"
        assert cross["took"] == "0"
        assert "could not cover the whole line" in cross["why"]
        assert "bought entire" in cross["why"]

        buy = _step(contribution, "buy")
        assert buy["answer"] == "yes"
        buy_reason = next(s["reason"] for s in contribution["sources"] if s["kind"] == "buy")
        assert "Borrowing is possible" in buy_reason
        assert donor.warehouse_code in buy_reason


# --------------------------------------------------------------------------- #
# 6. The other-group block: a zero-holding sibling, and the exact arithmetic
# --------------------------------------------------------------------------- #


def test_a_donor_groups_sibling_holding_nothing_still_lists_with_the_exact_arithmetic():
    """AC-V3, the two edges the existing pin (`test_ladder_v5_proof.py`'s own
    `test_a_cited_other_group_site_brings_its_whole_group_with_its_own_net`, whose
    siblings hold 40 and 7) does not cover: a sibling holding LITERALLY NOTHING - no
    `Stock` row at all, not merely a small one - still appears, at 0/0/0/0; and a
    sibling with real movement is checked against the exact formula the table promises,
    on hand + SPO - SO, rather than merely "whatever the stock row said".
    """
    with blank_session() as db:
        product = _product(db, f"ZZT-{_uid()[:6]}")
        own = _warehouse(db, f"ZZTS{_uid()[:5]}-BB"[:20])
        stem = _uid()[:5]
        drawn = _warehouse(db, f"ZZTT{stem}-NTC"[:20])
        sibling_zero = _warehouse(db, f"ZZTU{stem}-NTC"[:20])
        sibling_moves = _warehouse(db, f"ZZTV{stem}-NTC"[:20])
        _stock(db, product, own, on_hand=0)
        _stock(db, product, drawn, on_hand=40)
        _stock(db, product, sibling_moves, on_hand=50)
        _incoming(
            db, product, sibling_moves, spo_number="ZZT-SPO-SIB", allocated=10, received=0,
            arrives=WHEN + timedelta(days=5),
        )
        other_order = _order(
            db, so_number=f"ZZT-SO-B{_uid()[:6]}", order_date=date(2026, 1, 1)
        )
        _line(
            db, other_order, product, qty="15", required_date=date(2027, 1, 1),
            warehouse=sibling_moves,
        )
        _cap(db, max_qty=100, max_pct=100.0)
        order = _order(db, so_number=f"ZZT-SO-{_uid()[:8]}", order_date=date(2026, 1, 1))
        _line(db, order, product, qty="10", required_date=WHEN, warehouse=own)

        locations = _locations(db, order, product)

        other = {entry["location"]: entry for entry in locations if entry["where"] == "other_group"}
        assert {
            drawn.warehouse_code, sibling_zero.warehouse_code, sibling_moves.warehouse_code,
        } <= set(other), "every active sibling of the donor group is listed"

        zero_row = other[sibling_zero.warehouse_code]
        assert zero_row["qty_on_hand"] == "0"
        assert zero_row["spo_qty"] == "0"
        assert zero_row["so_qty"] == "0"
        assert zero_row["available_qty"] == "0"

        moves_row = other[sibling_moves.warehouse_code]
        assert moves_row["qty_on_hand"] == "50"
        assert moves_row["spo_qty"] == "10"
        assert moves_row["so_qty"] == "15"
        assert moves_row["available_qty"] == "45"
        assert Decimal(moves_row["available_qty"]) == (
            Decimal(moves_row["qty_on_hand"])
            + Decimal(moves_row["spo_qty"])
            - Decimal(moves_row["so_qty"])
        ), "available == on hand + SPO - SO, the formula the table promises"

        # The subtotal is the GROUP's net, over every site including the zero one.
        assert {entry["net"] for entry in other.values()} == {"85"}
        assert {entry["net_of"] for entry in other.values()} == {"NTC"}


# --------------------------------------------------------------------------- #
# 7. A big board's stock reads stay batched, not per line
# --------------------------------------------------------------------------- #


def test_a_board_of_76_lines_does_not_scale_its_query_count_with_the_line_count():
    """Section 1e's own note: "the cell table's batched stock reads now cover every active
    warehouse, because which group is the donor is not known until the engine has
    composed" - widening the SET a board reads must not turn the read itself from one
    round trip per kind of fact into one per LINE. A board of 76 lines, spread over a
    handful of locations and dates, counts its statements with a real
    `before_cursor_execute` listener (the same technique
    `tests/scm/test_project_supply_service_ladder.py`'s own O(1)-queries pin uses) and
    the count must not scale with the number of lines: a fixed, generous bound (40) - not
    a number a colleague's `for line in lines: db.query(...)` could still sneak under a
    smaller board's count.
    """
    with blank_session() as db:
        product = _product(db, f"ZZT-{_uid()[:6]}")
        grp = f"BB{_uid()[:4]}"
        own = _warehouse(db, f"ZZTW{_uid()[:4]}-{grp}"[:20])
        siblings = [
            _warehouse(db, f"ZZTX{_uid()[:3]}{i}-{grp}"[:20]) for i in range(4)
        ]
        for warehouse in [own, *siblings]:
            _stock(db, product, warehouse, on_hand=5)

        order = _order(db, so_number=f"ZZT-SO-{_uid()[:8]}", order_date=date(2026, 1, 1))
        line_count = 76
        for i in range(line_count):
            _line(
                db, order, product, qty="1",
                required_date=WHEN + timedelta(days=(i % 10) * 7),
                warehouse=own, line_status="open",
            )
        db.commit()

        calls = {"n": 0}

        def _count(conn, cursor, statement, parameters, context, executemany):
            calls["n"] += 1

        connection = db.connection()
        event.listen(connection, "before_cursor_execute", _count)
        try:
            board = _service(db).build(
                [order.so_number], granularity="week", as_of=TODAY
            )
        finally:
            event.remove(connection, "before_cursor_execute", _count)

        seen_lines = sum(len(cell["contributions"]) for cell in board["cells"])
        assert seen_lines == line_count, "the seed actually reached the board"
        assert calls["n"] <= 40, calls["n"]
