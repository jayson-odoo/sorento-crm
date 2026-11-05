"""SO-DRAFT-SET-PRICE: a set split on the SO draft must add up to the accepted quotation.

Bug (proved on main by lane AC-QTSO-CRM, PR #2173): the driver part was priced at the FULL
set rate while its qty was also multiplied by its qty per set, so set RM100 x 2 sets with a
2-per-set driver drafted 4 x 100.00 = 400.00 against an accepted 200.00.

Rule (owner, 5 Nov 2026, "ok a"): driver at set rate / its qty per set; remainder cents on a
one-unit row of the same item. Shared function: `app.services.set_driver_pricing`.
"""
from __future__ import annotations

from decimal import Decimal

from app.services.set_driver_pricing import split_set_driver_price

from ._pg_fixture import blank_session
from .test_set_quote_line import MARKER, _env, _product, _save, _set, _set_line, _uid
from .test_set_quote_line_wire import _drafted_lines, _so_chain

D = Decimal


# ------------------------------------------------------------------ the shared function


def _total(rows):
    return sum((qty * price for qty, price in rows), D("0"))


def test_one_per_set_is_unchanged():
    assert split_set_driver_price(D("100.00"), D("2"), D("1")) == [(D("2"), D("100.00"))]


def test_two_per_set_halves_the_rate_and_keeps_the_money():
    rows = split_set_driver_price(D("100.00"), D("2"), D("2"))
    assert rows == [(D("4"), D("50.00"))]
    assert _total(rows) == D("200.00")


def test_three_per_set_puts_the_remainder_cents_on_one_unit():
    rows = split_set_driver_price(D("100.00"), D("1"), D("3"))
    assert rows == [(D("2"), D("33.33")), (D("1"), D("33.34"))]
    assert _total(rows) == D("100.00")


def test_the_recorded_r6a_example_200_over_six_units():
    rows = split_set_driver_price(D("100.00"), D("2"), D("3"))
    assert rows == [(D("5"), D("33.33")), (D("1"), D("33.35"))]
    assert _total(rows) == D("200.00")


def test_every_small_case_adds_up_to_the_cent():
    for rate in ("100.00", "99.99", "0.01", "1234.57", "200.00"):
        for sets in ("1", "2", "3", "7", "10"):
            for per_set in ("1", "2", "3", "4", "6", "7"):
                rows = split_set_driver_price(D(rate), D(sets), D(per_set))
                assert _total(rows) == (D(rate) * D(sets)).quantize(D("0.01")), (
                    rate,
                    sets,
                    per_set,
                    rows,
                )
                assert sum(q for q, _ in rows) == D(sets) * D(per_set)
                assert all(p == p.quantize(D("0.01")) and p >= 0 for _, p in rows)


# ------------------------------------------------------------------ the real SO draft build


def _driver_set(db, env, per_set: str):
    driver = _product(db, env["category"], env["uom"], f"ZZPF{_uid()[:5].upper()}-DRV")
    other = _product(db, env["category"], env["uom"], f"ZZPF{_uid()[:5].upper()}-OTH")
    product_set = _set(
        db,
        env["company_id"],
        env["category"],
        env["uom"],
        parts=[(driver, per_set, True), (other, "1", False)],
    )
    return product_set, driver, other


def _build(db, env, product_set, *, rate: str, sets: str):
    from app.services.project_so_draft_service import ProjectSODraftService

    _set_line(db, env, product_set, unit_price=rate, quantity=sets)
    po, schedule_version = _so_chain(db, env, product_set, po_qty=sets)
    result = ProjectSODraftService(db).build(po.id, schedule_version.id)
    return po, _drafted_lines(db, result)


def _money(lines):
    return sum((line.amount for line in lines), D("0"))


def test_build_one_per_set_is_unchanged():
    with blank_session() as db:
        env = _env(db)
        product_set, driver, other = _driver_set(db, env, "1")
        _po, lines = _build(db, env, product_set, rate="100.00", sets="2")

        by_product = {line.product_id: line for line in lines}
        assert len(lines) == 2
        assert (by_product[driver.id].qty, by_product[driver.id].unit_price) == (D("2"), D("100"))
        assert by_product[other.id].unit_price == D("0")
        assert _money(lines) == D("200.00")


def test_build_two_per_set_drafts_the_accepted_money_not_double():
    with blank_session() as db:
        env = _env(db)
        product_set, driver, other = _driver_set(db, env, "2")
        _po, lines = _build(db, env, product_set, rate="100.00", sets="2")

        by_product = {line.product_id: line for line in lines}
        assert len(lines) == 2
        assert by_product[driver.id].qty == D("4")
        assert by_product[driver.id].unit_price == D("50")
        assert by_product[driver.id].amount == D("200.00")
        assert by_product[other.id].qty == D("2")
        assert by_product[other.id].amount == D("0")
        assert _money(lines) == D("200.00")


def test_build_three_per_set_rounds_with_the_remainder_on_one_unit():
    with blank_session() as db:
        env = _env(db)
        product_set, driver, other = _driver_set(db, env, "3")
        _po, lines = _build(db, env, product_set, rate="100.00", sets="1")

        driver_lines = [line for line in lines if line.product_id == driver.id]
        assert [(line.qty, line.unit_price, line.amount) for line in driver_lines] == [
            (D("2"), D("33.33"), D("66.66")),
            (D("1"), D("33.34"), D("33.34")),
        ]
        assert all(line.explosion_source == "set" for line in driver_lines)
        assert [line.product_id for line in lines].count(other.id) == 1
        assert _money(lines) == D("100.00")
        # the order's own total agrees with its lines
        from app.models.project_so import ProjectSalesOrder

        order = (
            db.query(ProjectSalesOrder)
            .filter(ProjectSalesOrder.id == lines[0].project_sales_order_id)
            .one()
        )
        assert D(order.total_amount) == D("100.00")


def test_build_mixed_quotation_prices_the_set_by_the_rule_and_the_normal_line_as_quoted():
    from app.models.project_so import ProjectPOLine, ProjectPOVersion
    from app.services.project_so_draft_service import ProjectSODraftService

    with blank_session() as db:
        env = _env(db)
        product_set, driver, other = _driver_set(db, env, "2")
        _set_line(db, env, product_set, unit_price="100.00", quantity="2")
        plain = _product(db, env["category"], env["uom"], f"ZZPF{_uid()[:5].upper()}-PLN")
        _save(db, env, {"product_id": plain.id, "unit_price": "12.50", "quantity": "3"})
        po, schedule_version = _so_chain(db, env, product_set, po_qty="2")
        po_version = (
            db.query(ProjectPOVersion).filter(ProjectPOVersion.purchase_order_id == po.id).one()
        )
        db.add(
            ProjectPOLine(
                id=_uid(),
                company_id=env["company_id"],
                po_version_id=po_version.id,
                line_no=2,
                stock_code_raw=plain.product_code,
                description_raw=f"{MARKER} plain",
                qty=D("3"),
                uom_raw="PCS",
                unit_price=D("12.50"),
                amount=D("37.50"),
                is_cancelled=False,
                resolved_product_id=plain.id,
                arithmetic_ok=None,
            )
        )
        db.flush()

        result = ProjectSODraftService(db).build(po.id, schedule_version.id)
        lines = _drafted_lines(db, result)

        by_product = {line.product_id: line for line in lines}
        assert (by_product[driver.id].qty, by_product[driver.id].unit_price) == (D("4"), D("50"))
        assert by_product[other.id].amount == D("0")
        assert (by_product[plain.id].qty, by_product[plain.id].unit_price) == (D("3"), D("12.5"))
        assert _money(lines) == D("237.50")


def test_build_rate_only_set_line_splits_by_the_same_rule():
    """A rate-only set line has no committed quantity: the PO's qty x the rate is the money."""
    with blank_session() as db:
        env = _env(db)
        product_set, driver, other = _driver_set(db, env, "2")
        quoted = _set_line(db, env, product_set, unit_price="100.00", quantity="1", is_rate_only=True)
        assert quoted.is_rate_only is True
        po, schedule_version = _so_chain(db, env, product_set, po_qty="3")
        from app.services.project_so_draft_service import ProjectSODraftService

        lines = _drafted_lines(db, ProjectSODraftService(db).build(po.id, schedule_version.id))

        by_product = {line.product_id: line for line in lines}
        assert (by_product[driver.id].qty, by_product[driver.id].unit_price) == (D("6"), D("50"))
        assert by_product[other.id].amount == D("0")
        assert _money(lines) == D("300.00")


def test_build_prices_from_the_pos_quotation_version_even_when_it_was_never_issued():
    """The draft reads `po.quotation_version_id` (project_so_draft_service.py `_quotation_version`),
    which need not be an accepted issue: the fixture's version is a plain, never-issued one."""
    from app.models.projects import ProjectQuotationIssueScope

    with blank_session() as db:
        env = _env(db)
        assert (
            db.query(ProjectQuotationIssueScope)
            .filter(ProjectQuotationIssueScope.version_id == env["version"].id)
            .count()
            == 0
        )
        product_set, driver, _other = _driver_set(db, env, "4")
        _po, lines = _build(db, env, product_set, rate="10.00", sets="3")

        driver_lines = [line for line in lines if line.product_id == driver.id]
        assert [(line.qty, line.unit_price) for line in driver_lines] == [(D("12"), D("2.5"))]
        assert _money(lines) == D("30.00")
