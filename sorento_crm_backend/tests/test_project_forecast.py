"""S5a forecast maths (UAC Group I). Golden set, written before the engine.

The rule that shapes everything: **three numbers, never blended** (AC-I1).

- **Pipeline** -- what is on the table: open quotations at their current version total,
  falling back to the registration estimate where nothing is quoted yet.
- **Weighted** -- pipeline times the per-status probability (AC-I2), which management tunes
  on the status record with no deploy.
- **Committed** -- what has actually been ordered.

Blending them is the failure mode this whole group exists to prevent: one "forecast" number
that mixes a banked PO with a 10%-probability rumour is a number nobody can act on, and it
is the number every spreadsheet ends up producing.

Year bucketing applies to Committed by default (AC-I2a). Pipeline and Weighted may be
bucketed too, but the engine returns them separately so the UI can label them speculative
rather than standing them next to banked revenue in the same column.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.status import Status
from app.models.user import User
from app.services import project_seed_service

from ._pg_fixture import blank_session

MARKER = "zzt-fcast"


def _uid() -> str:
    return str(uuid.uuid4())


def _sorento(db) -> str:
    return db.execute(text("select id from companies where code = 'SRT'")).scalar()


def _user(db, name: str) -> str:
    user_id = _uid()
    db.add(User(id=user_id, email=f"{user_id}@zzt.test", name=name))
    db.flush()
    return user_id


def _status_id(db, key: str) -> str:
    return str(
        db.execute(
            text(
                "select id from statuses where entity_type = 'project' and key = :k "
                "and scope_id is null"
            ),
            {"k": key},
        ).scalar()
    )


def _set_probability(db, key: str, percent) -> None:
    db.execute(
        text("update statuses set win_probability = :p where id = :i"),
        {"p": percent, "i": _status_id(db, key)},
    )
    db.flush()


def _project(db, company_id: str, owner: str, *, title=None, status_key=None, details=None):
    from app.services.project_service import register_project

    project = register_project(
        db,
        company_id=company_id,
        actor_user_id=owner,
        developer_party_id=None,
        title=title or f"{MARKER} Tower {_uid()[:6]}",
        details=details,
    )
    if status_key:
        project.status_id = _status_id(db, status_key)
        db.flush()
    return project


def _quote(db, project, owner: str, *, unit_price: str, quantity=1, scope="House Units"):
    """A quotation with one priced line, so the version total is real."""
    from app.services import project_quotation_service as quotes

    uom = UnitOfMeasure(id=_uid(), uom_code=f"ZZT{_uid()[:4]}", uom_name="Piece")
    category = ProductCategory(
        id=_uid(), category_code=f"ZZT-{_uid()[:8]}", category_name=f"{MARKER} cat"
    )
    db.add_all([uom, category])
    db.flush()
    product = Product(
        id=_uid(),
        product_code=f"ZZT-{_uid()[:8]}",
        product_name=f"{MARKER} item",
        category_id=category.id,
        base_uom_id=uom.id,
        list_price=Decimal(unit_price),
    )
    db.add(product)
    db.flush()

    quotation = quotes.create_quotation(
        db, project=project, actor_user_id=owner, payload={"scope_label": scope}
    )
    version = quotes.current_version(db, quotation.id)
    quotes.upsert_line(
        db,
        version=version,
        actor_user_id=owner,
        payload={
            "product_id": product.id,
            "unit_price": Decimal(unit_price),
            "quantity": quantity,
        },
    )
    return quotation, version


def _po(db, project, owner: str, *, amount: str, number=None, version_id=None):
    from app.services import project_po_service as pos

    return pos.create_po(
        db,
        project=project,
        actor_user_id=owner,
        payload={
            "po_source": "contractor_direct",
            "po_number": number or f"PO-{_uid()[:6]}",
            "po_amount": Decimal(amount),
            "quotation_version_id": version_id,
        },
    )


@pytest.fixture()
def seeded():
    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        owner = _user(db, f"{MARKER} Ali")
        yield db, company_id, owner


# ------------------------------------------------------------------- pipeline


def test_pipeline_sums_the_current_version_of_open_quotations(seeded):
    """AC-I1. The CURRENT version, not v1 and not the sum of all versions: a revised
    quotation would otherwise be counted twice at two different prices."""
    from app.services import project_forecast_service as fc
    from app.services import project_quotation_service as quotes

    db, company_id, owner = seeded
    project = _project(db, company_id, owner)
    quotation, _v1 = _quote(db, project, owner, unit_price="1000.00", quantity=10)
    v2 = quotes.revise(db, quotation=quotation, actor_user_id=owner)
    v2_line = quotes.list_lines(db, version_id=v2.id)[0]
    quotes.upsert_line(
        db, version=v2, actor_user_id=owner, line=v2_line, payload={"unit_price": Decimal("900")}
    )

    numbers = fc.forecast(db, company_id=company_id)

    assert numbers["pipeline"] == Decimal("9000.00")


def test_pipeline_falls_back_to_the_registration_estimate_when_nothing_is_quoted(seeded):
    """AC-I1. A registered project with no quotation is still pipeline: the estimate is what
    the salesperson believes, and dropping it would make the number go DOWN as the pipeline
    fills up with early-stage projects."""
    from app.services import project_forecast_service as fc

    db, company_id, owner = seeded
    _project(
        db, company_id, owner, details={"estimated_sales_value": Decimal("250000.00")}
    )

    assert fc.forecast(db, company_id=company_id)["pipeline"] == Decimal("250000.00")


def test_a_quoted_project_uses_the_quotation_not_the_estimate(seeded):
    """Otherwise the same project is counted twice, once as a guess and once as a price."""
    from app.services import project_forecast_service as fc

    db, company_id, owner = seeded
    project = _project(
        db, company_id, owner, details={"estimated_sales_value": Decimal("250000.00")}
    )
    _quote(db, project, owner, unit_price="1000.00", quantity=10)

    assert fc.forecast(db, company_id=company_id)["pipeline"] == Decimal("10000.00")


def test_a_lost_quotation_leaves_the_pipeline(seeded):
    from app.services import project_forecast_service as fc
    from app.services import project_quotation_service as quotes

    db, company_id, owner = seeded
    project = _project(db, company_id, owner)
    quotation, _v = _quote(db, project, owner, unit_price="1000.00", quantity=10)
    quotes.set_outcome(db, quotation=quotation, outcome="lost", loss_reason="price")

    assert fc.forecast(db, company_id=company_id)["pipeline"] == Decimal("0.00")


def test_a_won_quotation_leaves_the_pipeline_too(seeded):
    """Won work is COMMITTED, not pipeline. Counting it in both is the double-count that
    makes a forecast add up to more than the business."""
    from app.services import project_forecast_service as fc
    from app.services import project_quotation_service as quotes

    db, company_id, owner = seeded
    project = _project(db, company_id, owner)
    quotation, _v = _quote(db, project, owner, unit_price="1000.00", quantity=10)
    quotes.set_outcome(db, quotation=quotation, outcome="won", loss_reason=None)

    assert fc.forecast(db, company_id=company_id)["pipeline"] == Decimal("0.00")


def test_a_partly_decided_project_keeps_only_its_open_scope_in_pipeline(seeded):
    """AC-I5's sibling: house units won and common area still open is ONE open scope of
    pipeline, not a whole project either way."""
    from app.services import project_forecast_service as fc
    from app.services import project_quotation_service as quotes

    db, company_id, owner = seeded
    project = _project(db, company_id, owner)
    won, _v1 = _quote(db, project, owner, unit_price="1000.00", quantity=10, scope="House Units")
    _open_q, _v2 = _quote(db, project, owner, unit_price="500.00", quantity=4, scope="Common Area")
    quotes.set_outcome(db, quotation=won, outcome="won", loss_reason=None)

    assert fc.forecast(db, company_id=company_id)["pipeline"] == Decimal("2000.00")


# ------------------------------------------------------------------- weighted


def test_weighted_applies_the_probability_on_the_projects_status(seeded):
    """AC-I2. Project-level: three scopes on one project share one percentage, because the
    percentage describes how likely the PROJECT is to land, not each line item."""
    from app.services import project_forecast_service as fc

    db, company_id, owner = seeded
    _set_probability(db, "quoted", 40)
    project = _project(db, company_id, owner, status_key="quoted")
    _quote(db, project, owner, unit_price="1000.00", quantity=10)

    numbers = fc.forecast(db, company_id=company_id)
    assert numbers["pipeline"] == Decimal("10000.00")
    assert numbers["weighted"] == Decimal("4000.00")


def test_a_status_with_no_probability_set_contributes_nothing_to_weighted(seeded):
    """Deliberately NOT a default of 100%, and not of 50%: an unconfigured status has no
    opinion, and inventing one puts a number in front of management that nobody chose."""
    from app.services import project_forecast_service as fc

    db, company_id, owner = seeded
    project = _project(db, company_id, owner, status_key="identified")
    _quote(db, project, owner, unit_price="1000.00", quantity=10)

    # The seeder fills a starting probability on every rung, so an unconfigured rung has to
    # be arranged: clearing it back to NULL is what a team looks like after deleting a
    # default they disagreed with, or after adding a rung of their own.
    db.query(Status).filter(
        Status.entity_type == "project",
        Status.scope_id.is_(None),
        Status.key == "identified",
    ).update({Status.win_probability: None}, synchronize_session=False)
    db.flush()

    numbers = fc.forecast(db, company_id=company_id)
    assert numbers["pipeline"] == Decimal("10000.00")
    assert numbers["weighted"] == Decimal("0.00")


def test_weighted_never_exceeds_pipeline(seeded):
    """A probability over 100 is a data-entry error, and letting it through would print a
    weighted figure larger than the pipeline it derives from."""
    from app.services import project_forecast_service as fc

    db, company_id, owner = seeded
    _set_probability(db, "tendering", 150)
    project = _project(db, company_id, owner, status_key="tendering")
    _quote(db, project, owner, unit_price="1000.00", quantity=10)

    numbers = fc.forecast(db, company_id=company_id)
    assert numbers["weighted"] == numbers["pipeline"]


# ------------------------------------------------------------------ committed


def test_committed_sums_recorded_po_amounts(seeded):
    from app.services import project_forecast_service as fc

    db, company_id, owner = seeded
    project = _project(db, company_id, owner)
    _quote(db, project, owner, unit_price="1000.00", quantity=10)
    _po(db, project, owner, amount="8000.00")

    numbers = fc.forecast(db, company_id=company_id)
    assert numbers["committed"] == Decimal("8000.00")


def test_committed_and_pipeline_are_never_the_same_money(seeded):
    """The whole point of AC-I1. A project with a won scope AND an open one contributes to
    both numbers, but never the same amount to both."""
    from app.services import project_forecast_service as fc
    from app.services import project_quotation_service as quotes

    db, company_id, owner = seeded
    project = _project(db, company_id, owner)
    won, won_v = _quote(db, project, owner, unit_price="1000.00", quantity=10, scope="House Units")
    _quote(db, project, owner, unit_price="500.00", quantity=4, scope="Common Area")
    quotes.set_outcome(db, quotation=won, outcome="won", loss_reason=None)
    _po(db, project, owner, amount="9500.00", version_id=won_v.id)

    numbers = fc.forecast(db, company_id=company_id)
    assert numbers["pipeline"] == Decimal("2000.00")
    assert numbers["committed"] == Decimal("9500.00")


# --------------------------------------------------------------- delivery year


def test_delivery_year_comes_from_launch_plus_the_configured_lag(seeded):
    """AC-I3. 30 months seeded, so a March 2026 launch delivers in 2028."""
    from app.services import project_forecast_service as fc

    db, company_id, owner = seeded
    project = _project(
        db, company_id, owner, details={"launch_date": date(2026, 3, 1)}
    )

    assert fc.delivery_year(db, project=project) == 2028


def test_an_explicit_delivery_window_overrides_the_lag(seeded):
    """AC-I3: "the override wins wherever set". The salesperson who typed a window knows
    something the arithmetic does not."""
    from app.services import project_forecast_service as fc

    db, company_id, owner = seeded
    project = _project(
        db,
        company_id,
        owner,
        details={
            "launch_date": date(2026, 3, 1),
            "expected_delivery_from": date(2027, 6, 1),
        },
    )

    assert fc.delivery_year(db, project=project) == 2027


def test_a_project_with_neither_a_launch_nor_a_window_has_no_delivery_year(seeded):
    """None, not "this year". Bucketing an unknown into the current year is how a forecast
    quietly claims revenue it has no basis for."""
    from app.services import project_forecast_service as fc

    db, company_id, owner = seeded
    project = _project(db, company_id, owner)

    assert fc.delivery_year(db, project=project) is None


def test_the_lag_is_a_setting_not_a_constant(seeded):
    """AC-I3: changing it is a settings edit, never a deploy."""
    from app.services import project_forecast_service as fc

    db, company_id, owner = seeded
    # A blank schema carries no settings row, so this INSERTS one through the ORM: the
    # table has a dozen NOT NULL columns whose defaults live on the model, and hand-writing
    # the INSERT means discovering them one failure at a time.
    from app.models.user import SystemSetting

    db.add(SystemSetting(id=_uid(), name="zzt", project_delivery_lag_months=12))
    db.flush()
    project = _project(db, company_id, owner, details={"launch_date": date(2026, 3, 1)})

    assert fc.delivery_year(db, project=project) == 2027


# ---------------------------------------------------------------- year buckets


def test_committed_is_bucketed_by_delivery_year(seeded):
    """AC-I2a: Committed is the number that gets year-bucketed by default, because it is the
    only one of the three that is actually banked."""
    from app.services import project_forecast_service as fc

    db, company_id, owner = seeded
    early = _project(
        db, company_id, owner, title=f"{MARKER} Bukit Jalil", details={"launch_date": date(2026, 1, 1)}
    )
    later = _project(
        db, company_id, owner, title=f"{MARKER} Kota Damansara", details={"launch_date": date(2027, 1, 1)}
    )
    _po(db, early, owner, amount="1000.00")
    _po(db, later, owner, amount="2000.00")

    buckets = {row["year"]: row for row in fc.forecast(db, company_id=company_id)["by_year"]}
    assert buckets[2028]["committed"] == Decimal("1000.00")
    assert buckets[2029]["committed"] == Decimal("2000.00")


def test_speculative_money_is_kept_out_of_the_banked_column(seeded):
    """AC-I2a. Pipeline and Weighted ARE bucketed, but under their own keys, so a UI cannot
    accidentally stack a 3-year-out guess on top of banked revenue in one column."""
    from app.services import project_forecast_service as fc

    db, company_id, owner = seeded
    _set_probability(db, "quoted", 50)
    project = _project(
        db, company_id, owner, status_key="quoted", details={"launch_date": date(2026, 1, 1)}
    )
    _quote(db, project, owner, unit_price="1000.00", quantity=10)

    row = next(r for r in fc.forecast(db, company_id=company_id)["by_year"] if r["year"] == 2028)
    assert row["committed"] == Decimal("0.00")
    assert row["pipeline"] == Decimal("10000.00")
    assert row["weighted"] == Decimal("5000.00")


def test_projects_with_no_delivery_year_are_reported_separately_not_dropped(seeded):
    """Dropping them makes the buckets disagree with the totals, and the first person to
    add up the columns loses trust in the whole report."""
    from app.services import project_forecast_service as fc

    db, company_id, owner = seeded
    project = _project(db, company_id, owner)
    _quote(db, project, owner, unit_price="1000.00", quantity=10)

    numbers = fc.forecast(db, company_id=company_id)
    assert numbers["pipeline"] == Decimal("10000.00")
    assert sum(row["pipeline"] for row in numbers["by_year"]) == Decimal("0.00")
    assert numbers["undated"]["pipeline"] == Decimal("10000.00")


# ----------------------------------------------------------------- conversion


def test_conversion_reads_quotation_outcomes_rolled_to_projects(seeded):
    """AC-I5. A partial win is not a full win: the project is decided only when every scope
    is, and counting house-units-won as a win while common-area is live would report a
    conversion that has not happened yet."""
    from app.services import project_forecast_service as fc
    from app.services import project_quotation_service as quotes

    db, company_id, owner = seeded
    won = _project(db, company_id, owner, title=f"{MARKER} Bukit Jalil")
    lost = _project(db, company_id, owner, title=f"{MARKER} Kota Damansara")
    partial = _project(db, company_id, owner, title=f"{MARKER} Setia Alam")

    q_won, _ = _quote(db, won, owner, unit_price="100.00")
    quotes.set_outcome(db, quotation=q_won, outcome="won", loss_reason=None)
    q_lost, _ = _quote(db, lost, owner, unit_price="100.00")
    quotes.set_outcome(db, quotation=q_lost, outcome="lost", loss_reason="price")
    q_part, _ = _quote(db, partial, owner, unit_price="100.00", scope="House Units")
    _quote(db, partial, owner, unit_price="100.00", scope="Common Area")
    quotes.set_outcome(db, quotation=q_part, outcome="won", loss_reason=None)

    metrics = fc.conversion(db, company_id=company_id)
    # The partly-decided project counts as WON (any scope won -> the project is won, per
    # AC-E10) but the project that is still fully open is not in the denominator at all.
    assert metrics["won"] == 2
    assert metrics["lost"] == 1
    assert metrics["decided"] == 3
    assert metrics["rate"] == Decimal("66.67")


def test_conversion_is_none_rather_than_zero_with_nothing_decided(seeded):
    """0% says we lose everything. None says we have not finished anything yet."""
    from app.services import project_forecast_service as fc

    db, company_id, owner = seeded
    _project(db, company_id, owner)

    metrics = fc.conversion(db, company_id=company_id)
    assert metrics["decided"] == 0
    assert metrics["rate"] is None


def test_loss_reasons_are_counted_for_the_report(seeded):
    """AC-I4. Counted from the QUOTATION, which is where the reason is recorded, so a
    project that lost two scopes for two different reasons reports both."""
    from app.services import project_forecast_service as fc
    from app.services import project_quotation_service as quotes

    db, company_id, owner = seeded
    project = _project(db, company_id, owner)
    first, _ = _quote(db, project, owner, unit_price="100.00", scope="House Units")
    second, _ = _quote(db, project, owner, unit_price="100.00", scope="Common Area")
    quotes.set_outcome(db, quotation=first, outcome="lost", loss_reason="price")
    quotes.set_outcome(db, quotation=second, outcome="lost", loss_reason="lead_time")

    reasons = {row["reason"]: row for row in fc.loss_reason_counts(db, company_id=company_id)}
    assert reasons["price"]["count"] == 1
    assert reasons["lead_time"]["count"] == 1
    assert reasons["price"]["label"] == "Price"


def test_salesperson_performance_reports_per_owner(seeded):
    """AC-I4. Per owner, and it has to carry the same three numbers as the headline or the
    rows will not add up to it."""
    from app.services import project_forecast_service as fc

    db, company_id, owner = seeded
    other = _user(db, f"{MARKER} Siti")
    mine = _project(db, company_id, owner, title=f"{MARKER} Bukit Jalil")
    _quote(db, mine, owner, unit_price="1000.00", quantity=10)
    theirs = _project(db, company_id, other, title=f"{MARKER} Kota Damansara")
    _quote(db, theirs, other, unit_price="500.00", quantity=2)

    rows = {row["owner_user_id"]: row for row in fc.by_salesperson(db, company_id=company_id)}
    assert rows[owner]["pipeline"] == Decimal("10000.00")
    assert rows[other]["pipeline"] == Decimal("1000.00")
    assert rows[owner]["owner_name"] == f"{MARKER} Ali"
