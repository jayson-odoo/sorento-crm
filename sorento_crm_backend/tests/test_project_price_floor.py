"""S3 price-floor resolution (AC-E6, AC-E7) as a golden set.

This is the deterministic engine of the slice, so it is specified as a table of cases
written before the implementation.

Two rules do all the work:

1. **Specificity wins.** product > its category > that category's ancestors (nearest
   first) > system. A rule on "Basins" must beat one on "Sanitary Ware" for a basin.
2. **A level may be a PERCENTAGE of list price or an ABSOLUTE amount**, and the two are
   never mixed within a level -- the resolved rule is used as it stands.

The resolved value is stored ON the line (AC-E7), so re-pricing policy later never
retro-flags a quotation somebody already sent.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.models.product import Product, ProductCategory, UnitOfMeasure

from ._pg_fixture import blank_session

MARKER = "zzt-floor"


def _uid() -> str:
    return str(uuid.uuid4())


def _sorento(db) -> str:
    return db.execute(text("select id from companies where code = 'SRT'")).scalar()


def _uom(db) -> str:
    row = UnitOfMeasure(id=_uid(), uom_code=f"ZZT{_uid()[:4]}", uom_name="Piece")
    db.add(row)
    db.flush()
    return row.id


def _category(db, name: str, parent_id: str | None = None) -> ProductCategory:
    row = ProductCategory(
        id=_uid(),
        category_code=f"ZZT-{_uid()[:8]}",
        category_name=f"{MARKER} {name}",
        parent_category_id=parent_id,
    )
    db.add(row)
    db.flush()
    return row


def _product(db, category_id: str, uom_id: str, list_price: str) -> Product:
    row = Product(
        id=_uid(),
        product_code=f"ZZT-{_uid()[:8]}",
        product_name=f"{MARKER} Product",
        category_id=category_id,
        base_uom_id=uom_id,
        list_price=Decimal(list_price),
    )
    db.add(row)
    db.flush()
    return row


def _rule(db, company_id: str, *, mode: str, value: str, product_id=None, category_id=None):
    from app.models.projects import PriceFloorRule

    row = PriceFloorRule(
        id=_uid(),
        company_id=company_id,
        product_id=product_id,
        category_id=category_id,
        mode=mode,
        value=Decimal(value),
    )
    db.add(row)
    db.flush()
    return row


# ------------------------------------------------------------------ the set


def test_a_system_rule_applies_when_nothing_more_specific_exists():
    from app.services import project_pricing_service as pricing

    with blank_session() as db:
        company_id = _sorento(db)
        uom = _uom(db)
        category = _category(db, "Sanitary Ware")
        product = _product(db, category.id, uom, "1000.00")
        _rule(db, company_id, mode="percent", value="80")

        floor = pricing.resolve_floor(db, company_id=company_id, product=product)

        assert floor.value == Decimal("800.00")
        assert floor.level == "system"
        assert floor.mode == "percent"


def test_a_category_rule_beats_the_system_rule():
    from app.services import project_pricing_service as pricing

    with blank_session() as db:
        company_id = _sorento(db)
        uom = _uom(db)
        category = _category(db, "Basins")
        product = _product(db, category.id, uom, "1000.00")
        _rule(db, company_id, mode="percent", value="80")
        _rule(db, company_id, mode="percent", value="90", category_id=category.id)

        floor = pricing.resolve_floor(db, company_id=company_id, product=product)

        assert floor.value == Decimal("900.00")
        assert floor.level == "category"


def test_a_product_rule_beats_its_category_and_the_system():
    from app.services import project_pricing_service as pricing

    with blank_session() as db:
        company_id = _sorento(db)
        uom = _uom(db)
        category = _category(db, "Basins")
        product = _product(db, category.id, uom, "1000.00")
        _rule(db, company_id, mode="percent", value="80")
        _rule(db, company_id, mode="percent", value="90", category_id=category.id)
        _rule(db, company_id, mode="absolute", value="950.00", product_id=product.id)

        floor = pricing.resolve_floor(db, company_id=company_id, product=product)

        assert floor.value == Decimal("950.00")
        assert floor.level == "product"
        assert floor.mode == "absolute"


def test_the_nearest_ancestor_wins_over_a_more_distant_one():
    """AC-E6: the category's ANCESTORS, nearest first.

    Sanitary Ware > Basins > Wall-hung Basins, a rule on each of the two upper levels,
    the product on the leaf. "Basins" is one hop away and must win, or a broad
    group-level policy silently overrides the specific one beneath it.
    """
    from app.services import project_pricing_service as pricing

    with blank_session() as db:
        company_id = _sorento(db)
        uom = _uom(db)
        grandparent = _category(db, "Sanitary Ware")
        parent = _category(db, "Basins", parent_id=grandparent.id)
        leaf = _category(db, "Wall-hung Basins", parent_id=parent.id)
        product = _product(db, leaf.id, uom, "1000.00")

        _rule(db, company_id, mode="percent", value="70", category_id=grandparent.id)
        _rule(db, company_id, mode="percent", value="85", category_id=parent.id)

        floor = pricing.resolve_floor(db, company_id=company_id, product=product)

        assert floor.value == Decimal("850.00")
        assert floor.level == "category_ancestor"
        assert floor.category_id == parent.id


def test_a_percentage_resolves_against_the_products_list_price():
    from app.services import project_pricing_service as pricing

    with blank_session() as db:
        company_id = _sorento(db)
        uom = _uom(db)
        category = _category(db, "Basins")
        cheap = _product(db, category.id, uom, "100.00")
        dear = _product(db, category.id, uom, "2500.00")
        _rule(db, company_id, mode="percent", value="75", category_id=category.id)

        assert pricing.resolve_floor(
            db, company_id=company_id, product=cheap
        ).value == Decimal("75.00")
        assert pricing.resolve_floor(
            db, company_id=company_id, product=dear
        ).value == Decimal("1875.00")


def test_an_absolute_rule_ignores_the_list_price_entirely():
    from app.services import project_pricing_service as pricing

    with blank_session() as db:
        company_id = _sorento(db)
        uom = _uom(db)
        category = _category(db, "Basins")
        product = _product(db, category.id, uom, "100.00")
        # Deliberately ABOVE list: an absolute floor is a hard number, and a policy
        # that says "never below RM 500" means it even on a cheap line.
        _rule(db, company_id, mode="absolute", value="500.00", category_id=category.id)

        floor = pricing.resolve_floor(db, company_id=company_id, product=product)

        assert floor.value == Decimal("500.00")


def test_no_rule_anywhere_means_no_floor_rather_than_a_floor_of_zero():
    """A floor of zero would mark every line compliant and read as "checked and fine".
    Absent is a different statement and the caller must be able to tell."""
    from app.services import project_pricing_service as pricing

    with blank_session() as db:
        company_id = _sorento(db)
        uom = _uom(db)
        category = _category(db, "Basins")
        product = _product(db, category.id, uom, "1000.00")

        floor = pricing.resolve_floor(db, company_id=company_id, product=product)

        assert floor is None


def test_an_off_catalog_line_has_no_floor_to_resolve():
    """A line with no product has no list price and no category, so there is nothing to
    resolve against. It is flagged as non-standard instead (AC-E5)."""
    from app.services import project_pricing_service as pricing

    with blank_session() as db:
        company_id = _sorento(db)
        _rule(db, company_id, mode="percent", value="80")

        assert pricing.resolve_floor(db, company_id=company_id, product=None) is None


def test_a_percentage_of_a_missing_list_price_yields_no_floor():
    """Guard rather than a crash: percent needs a base, and 0 would be a false pass."""
    from app.services import project_pricing_service as pricing

    with blank_session() as db:
        company_id = _sorento(db)
        uom = _uom(db)
        category = _category(db, "Basins")
        product = _product(db, category.id, uom, "0.00")
        _rule(db, company_id, mode="percent", value="80", category_id=category.id)

        assert pricing.resolve_floor(db, company_id=company_id, product=product) is None


def test_another_companys_rule_never_applies():
    """Floors are company-scoped policy: Mocha's discount ceiling is not Sorento's."""
    from app.services import project_pricing_service as pricing

    with blank_session() as db:
        company_id = _sorento(db)
        other_company = _uid()
        db.execute(
            text(
                "insert into companies (id, name, code, is_active) "
                "values (:id, 'Zzt Other', 'ZZO', true)"
            ),
            {"id": other_company},
        )
        uom = _uom(db)
        category = _category(db, "Basins")
        product = _product(db, category.id, uom, "1000.00")
        _rule(db, other_company, mode="percent", value="90", category_id=category.id)

        assert pricing.resolve_floor(db, company_id=company_id, product=product) is None


def test_a_percentage_over_a_hundred_is_refused_at_configuration_time():
    """A floor above list price is a policy nobody means: every line would breach it.

    Refused when the rule is saved rather than silently clamped, because clamping hides
    the typo and the admin never learns their 950 should have been 95.
    """
    from app.services import project_pricing_service as pricing
    from app.services.error_handler import AppException

    with blank_session() as db:
        company_id = _sorento(db)

        with pytest.raises(AppException) as exc:
            pricing.upsert_floor_rule(
                db, company_id=company_id, payload={"mode": "percent", "value": "950"}
            )

        assert exc.value.status_code == 422


def test_a_rule_naming_both_a_product_and_a_category_is_refused():
    """The level is implied by which key is set, so both set is ambiguous: it would be
    stored at one specificity and read at another."""
    from app.services import project_pricing_service as pricing
    from app.services.error_handler import AppException

    with blank_session() as db:
        company_id = _sorento(db)
        uom = _uom(db)
        category = _category(db, "Basins")
        product = _product(db, category.id, uom, "1000.00")

        with pytest.raises(AppException) as exc:
            pricing.upsert_floor_rule(
                db,
                company_id=company_id,
                payload={
                    "mode": "percent",
                    "value": "80",
                    "product_id": product.id,
                    "category_id": category.id,
                },
            )

        assert exc.value.status_code == 422


# ------------------------------------------------- series membership (AC-E5)


def _series(db, company_id: str, name: str, category_ids=()):
    from app.models.projects import ProjectSeries
    from app.services import project_pricing_service as pricing

    series = ProjectSeries(id=_uid(), company_id=company_id, name=f"{MARKER} {name}")
    db.add(series)
    db.flush()
    if category_ids:
        pricing.set_series_categories(db, series=series, category_ids=list(category_ids))
    return series


def test_nominating_a_parent_category_covers_every_descendant():
    """AC-E5. Otherwise a series is a hand-maintained SKU list that goes stale the week
    after it is written."""
    from app.services import project_pricing_service as pricing

    with blank_session() as db:
        company_id = _sorento(db)
        uom = _uom(db)
        top = _category(db, "Sanitary Ware")
        middle = _category(db, "Basins", parent_id=top.id)
        leaf = _category(db, "Wall-hung Basins", parent_id=middle.id)
        unrelated = _category(db, "Kitchen Sinks")

        deep_product = _product(db, leaf.id, uom, "1000.00")
        outside_product = _product(db, unrelated.id, uom, "1000.00")

        series = _series(db, company_id, "Premium", [top.id])

        assert pricing.is_in_series(db, series_id=series.id, product=deep_product) is True
        assert pricing.is_in_series(db, series_id=series.id, product=outside_product) is False


def test_a_line_with_no_product_is_never_in_the_series():
    from app.services import project_pricing_service as pricing

    with blank_session() as db:
        company_id = _sorento(db)
        category = _category(db, "Basins")
        series = _series(db, company_id, "Premium", [category.id])

        assert pricing.is_in_series(db, series_id=series.id, product=None) is False


def test_with_no_series_nominated_everything_counts_as_standard():
    """A project that never picked a series has no allowlist to breach, and flagging
    every line on it would make the alert meaningless."""
    from app.services import project_pricing_service as pricing

    with blank_session() as db:
        uom = _uom(db)
        category = _category(db, "Basins")
        product = _product(db, category.id, uom, "1000.00")

        assert pricing.is_in_series(db, series_id=None, product=product) is True
        assert pricing.is_in_series(db, series_id=None, product=None) is True


def test_replacing_the_nominated_set_reconciles_rather_than_rebuilding():
    from app.models.projects import ProjectSeriesCategory
    from app.services import project_pricing_service as pricing

    with blank_session() as db:
        company_id = _sorento(db)
        keep = _category(db, "Basins")
        drop = _category(db, "Kitchen Sinks")
        add = _category(db, "Showers")
        series = _series(db, company_id, "Premium", [keep.id, drop.id])

        pricing.set_series_categories(db, series=series, category_ids=[keep.id, add.id])

        rows = {
            row.category_id
            for row in db.query(ProjectSeriesCategory)
            .filter(ProjectSeriesCategory.series_id == series.id)
            .all()
        }
        assert rows == {keep.id, add.id}


def test_the_category_walk_survives_a_cycle_rather_than_spinning():
    """A cycle in parent_category_id is bad data, not a reason to hang the request."""
    from app.services import project_pricing_service as pricing

    with blank_session() as db:
        first = _category(db, "Loop A")
        second = _category(db, "Loop B", parent_id=first.id)
        first.parent_category_id = second.id
        db.flush()

        chain = pricing.category_ancestry(db, first.id)

        assert chain[:2] == [first.id, second.id]
        assert len(chain) == 2
