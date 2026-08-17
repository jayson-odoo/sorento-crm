"""The floor IN FORCE for one product or one category, and where it comes from.

The listing endpoint returns every rule; it cannot answer "what governs this basin",
because that answer needs the category ancestry walk. Master data (the product Pricing
tab, the category editor) needs exactly that answer: a product with no rule of its own is
still governed by a floor, and showing nothing there is a lie by omission.

So this is one read: the rule set ON the target (if any), plus the resolved floor and the
name of whatever it came from. The product path reuses ``resolve_floor`` unchanged -- the
golden set in tests/test_project_price_floor.py already pins that engine, and a second
resolver for the same question would be free to disagree with it.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.user import User

from ._pg_fixture import blank_session

MARKER = "zzt-floor-eff"
BASE = "/api/v1/project-sales"


def _uid() -> str:
    return str(uuid.uuid4())


def _sorento(db) -> str:
    return db.execute(text("select id from companies where code = 'SRT'")).scalar()


def _user(db, name: str) -> str:
    user_id = _uid()
    db.add(User(id=user_id, email=f"{user_id}@zzt.test", name=name))
    db.flush()
    return user_id


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


def _rule(
    db,
    company_id: str,
    *,
    mode: str,
    value: str,
    product_id=None,
    category_id=None,
    is_active: bool = True,
):
    from app.models.projects import PriceFloorRule

    row = PriceFloorRule(
        id=_uid(),
        company_id=company_id,
        product_id=product_id,
        category_id=category_id,
        mode=mode,
        value=Decimal(value),
        is_active=is_active,
    )
    db.add(row)
    db.flush()
    return row


# ------------------------------------------------------------------- service


def test_a_categorys_own_rule_is_reported_as_its_own():
    from app.services import project_pricing_service as pricing

    with blank_session() as db:
        company_id = _sorento(db)
        category = _category(db, "Basins")
        rule = _rule(db, company_id, mode="percent", value="90", category_id=category.id)

        source = pricing.resolve_category_floor_source(
            db, company_id=company_id, category_id=category.id
        )

        assert source.rule.id == rule.id
        assert source.level == "category"
        assert source.category_id == category.id


def test_a_category_with_no_rule_inherits_its_nearest_ancestor():
    """Nearest first, the same precedence the product resolver uses. A grandparent rule
    must not shadow the parent's, or a broad policy silently overrides the specific one
    beneath it."""
    from app.services import project_pricing_service as pricing

    with blank_session() as db:
        company_id = _sorento(db)
        grandparent = _category(db, "Sanitary Ware")
        parent = _category(db, "Basins", parent_id=grandparent.id)
        leaf = _category(db, "Wall-hung Basins", parent_id=parent.id)
        _rule(db, company_id, mode="percent", value="70", category_id=grandparent.id)
        near = _rule(db, company_id, mode="percent", value="85", category_id=parent.id)

        source = pricing.resolve_category_floor_source(
            db, company_id=company_id, category_id=leaf.id
        )

        assert source.rule.id == near.id
        assert source.level == "category_ancestor"
        assert source.category_id == parent.id


def test_a_category_with_no_ancestor_rule_falls_back_to_the_company_default():
    from app.services import project_pricing_service as pricing

    with blank_session() as db:
        company_id = _sorento(db)
        category = _category(db, "Basins")
        system = _rule(db, company_id, mode="percent", value="80")

        source = pricing.resolve_category_floor_source(
            db, company_id=company_id, category_id=category.id
        )

        assert source.rule.id == system.id
        assert source.level == "system"
        assert source.category_id is None


def test_no_rule_anywhere_means_no_source_rather_than_a_floor_of_zero():
    from app.services import project_pricing_service as pricing

    with blank_session() as db:
        company_id = _sorento(db)
        category = _category(db, "Basins")

        assert (
            pricing.resolve_category_floor_source(
                db, company_id=company_id, category_id=category.id
            )
            is None
        )


def test_an_inactive_rule_is_skipped_and_the_next_level_decides():
    from app.services import project_pricing_service as pricing

    with blank_session() as db:
        company_id = _sorento(db)
        parent = _category(db, "Sanitary Ware")
        leaf = _category(db, "Basins", parent_id=parent.id)
        _rule(
            db,
            company_id,
            mode="percent",
            value="95",
            category_id=leaf.id,
            is_active=False,
        )
        active = _rule(db, company_id, mode="percent", value="70", category_id=parent.id)

        source = pricing.resolve_category_floor_source(
            db, company_id=company_id, category_id=leaf.id
        )

        assert source.rule.id == active.id


def test_another_companys_category_rule_never_applies():
    from app.services import project_pricing_service as pricing

    with blank_session() as db:
        company_id = _sorento(db)
        other_company = _uid()
        db.execute(
            text(
                "insert into companies (id, name, code, is_active) "
                "values (:id, 'Zzt Other Eff', 'ZZE', true)"
            ),
            {"id": other_company},
        )
        category = _category(db, "Basins")
        _rule(db, other_company, mode="percent", value="90", category_id=category.id)

        assert (
            pricing.resolve_category_floor_source(
                db, company_id=company_id, category_id=category.id
            )
            is None
        )


def test_the_rule_set_directly_on_a_target_is_found_without_the_ancestry_walk():
    """Whether the target owns a rule decides whether "Clear" is even offered, so it is
    a separate question from what governs it."""
    from app.services import project_pricing_service as pricing

    with blank_session() as db:
        company_id = _sorento(db)
        uom = _uom(db)
        parent = _category(db, "Sanitary Ware")
        leaf = _category(db, "Basins", parent_id=parent.id)
        product = _product(db, leaf.id, uom, "1000.00")
        _rule(db, company_id, mode="percent", value="70", category_id=parent.id)
        own = _rule(db, company_id, mode="absolute", value="500", product_id=product.id)

        assert (
            pricing.own_floor_rule(db, company_id=company_id, product_id=product.id).id
            == own.id
        )
        # The leaf inherits from its parent, so it owns nothing of its own.
        assert (
            pricing.own_floor_rule(db, company_id=company_id, category_id=leaf.id) is None
        )


# --------------------------------------------------------------------- route


def _client(db, user_id: str):
    from fastapi.testclient import TestClient

    from app.database import get_db
    from app.dependencies import get_current_user, get_current_user_or_api_key
    from app.main import app
    from app.services.company_scope_resolver import apply_company_scope
    from app.services.user_service import UserPermissionService

    actor = {"id": user_id, "email": f"{user_id}@zzt.test", "role": "superadmin"}
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: dict(actor)
    app.dependency_overrides[get_current_user_or_api_key] = lambda: dict(actor)
    app.dependency_overrides[apply_company_scope] = lambda: None

    originals = (
        UserPermissionService.check_user_has_permission,
        UserPermissionService.get_user_permission_slugs,
    )
    UserPermissionService.check_user_has_permission = lambda self, uid, slug: True
    UserPermissionService.get_user_permission_slugs = lambda self, uid: [
        "projects.types.view",
        "projects.types.edit",
    ]
    return TestClient(app), originals


def _restore(originals) -> None:
    from app.main import app
    from app.services.user_service import UserPermissionService

    UserPermissionService.check_user_has_permission = originals[0]
    UserPermissionService.get_user_permission_slugs = originals[1]
    app.dependency_overrides.clear()


@pytest.fixture()
def api():
    from app.models.base import company_scope

    with blank_session() as db:
        company_id = _sorento(db)
        user_id = _user(db, f"{MARKER} Ali")
        db.commit()
        client, originals = _client(db, user_id)
        try:
            with company_scope(db, frozenset({company_id})):
                yield client, db, company_id
        finally:
            _restore(originals)


def test_a_product_with_no_rule_of_its_own_still_reports_the_floor_that_governs_it(api):
    """The whole point of the surface: the salesperson standing on the product must be
    told the inherited floor and where it comes from, not an empty box."""
    client, db, company_id = api
    uom = _uom(db)
    category = _category(db, "Basins")
    product = _product(db, category.id, uom, "1000.00")
    _rule(db, company_id, mode="percent", value="80", category_id=category.id)
    db.commit()

    response = client.get(f"{BASE}/config/price-floors/effective?product_id={product.id}")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["target_level"] == "product"
    assert body["target_label"] == product.product_code
    assert body["list_price"] == "1000.00"
    assert body["own_rule"] is None
    assert body["effective"]["level"] == "category"
    assert body["effective"]["mode"] == "percent"
    assert body["effective"]["amount"] == "800.00"
    # Named, never a UUID: the browser has no way to resolve one.
    assert body["effective"]["source_label"] == category.category_name


def test_a_products_own_rule_is_returned_so_the_editor_can_change_or_clear_it(api):
    client, db, company_id = api
    uom = _uom(db)
    category = _category(db, "Basins")
    product = _product(db, category.id, uom, "1000.00")
    _rule(db, company_id, mode="percent", value="80", category_id=category.id)
    own = _rule(db, company_id, mode="absolute", value="950", product_id=product.id)
    db.commit()

    body = client.get(
        f"{BASE}/config/price-floors/effective?product_id={product.id}"
    ).json()

    assert body["own_rule"]["id"] == own.id
    assert body["own_rule"]["mode"] == "absolute"
    assert body["effective"]["level"] == "product"
    assert body["effective"]["amount"] == "950.00"
    assert body["effective"]["source_label"] == product.product_code


def test_the_company_default_is_named_rather_than_left_blank(api):
    client, db, company_id = api
    uom = _uom(db)
    category = _category(db, "Basins")
    product = _product(db, category.id, uom, "1000.00")
    _rule(db, company_id, mode="percent", value="60")
    db.commit()

    body = client.get(
        f"{BASE}/config/price-floors/effective?product_id={product.id}"
    ).json()

    assert body["effective"]["level"] == "system"
    assert body["effective"]["source_label"] == "Company default"
    assert body["effective"]["amount"] == "600.00"


def test_a_product_governed_by_nothing_reports_no_floor_at_all(api):
    client, db, _company_id = api
    uom = _uom(db)
    category = _category(db, "Basins")
    product = _product(db, category.id, uom, "1000.00")
    db.commit()

    body = client.get(
        f"{BASE}/config/price-floors/effective?product_id={product.id}"
    ).json()

    assert body["effective"] is None
    assert body["own_rule"] is None


def test_a_percentage_floor_on_a_category_has_no_ringgit_amount_to_show(api):
    """A category has no list price, so a percent rule cannot be turned into money.
    Returning a number anyway would be inventing one."""
    client, db, company_id = api
    category = _category(db, "Basins")
    _rule(db, company_id, mode="percent", value="75", category_id=category.id)
    db.commit()

    body = client.get(
        f"{BASE}/config/price-floors/effective?category_id={category.id}"
    ).json()

    assert body["target_level"] == "category"
    assert body["target_label"] == category.category_name
    assert body["list_price"] is None
    assert body["effective"]["mode"] == "percent"
    assert body["effective"]["value"] == "75.00"
    assert body["effective"]["amount"] is None


def test_an_absolute_floor_on_a_category_is_money_already(api):
    client, db, company_id = api
    category = _category(db, "Basins")
    _rule(db, company_id, mode="absolute", value="500", category_id=category.id)
    db.commit()

    body = client.get(
        f"{BASE}/config/price-floors/effective?category_id={category.id}"
    ).json()

    assert body["effective"]["amount"] == "500.00"
    assert body["own_rule"]["id"] == body["effective"]["rule_id"]


def test_naming_neither_target_is_refused(api):
    client, _db, _company_id = api

    response = client.get(f"{BASE}/config/price-floors/effective")

    assert response.status_code == 422, response.text


def test_naming_both_targets_is_refused(api):
    client, db, _company_id = api
    uom = _uom(db)
    category = _category(db, "Basins")
    product = _product(db, category.id, uom, "1000.00")
    db.commit()

    response = client.get(
        f"{BASE}/config/price-floors/effective"
        f"?product_id={product.id}&category_id={category.id}"
    )

    assert response.status_code == 422, response.text


def test_an_unknown_product_is_a_404_rather_than_an_empty_answer(api):
    """"No floor" and "no such product" are different statements, and a blank panel
    would read as the first."""
    client, _db, _company_id = api

    response = client.get(f"{BASE}/config/price-floors/effective?product_id={_uid()}")

    assert response.status_code == 404, response.text


def test_a_user_without_the_pricing_permission_is_refused(api):
    client, db, company_id = api
    uom = _uom(db)
    category = _category(db, "Basins")
    product = _product(db, category.id, uom, "1000.00")
    db.commit()

    from app.services.user_service import UserPermissionService

    saved = UserPermissionService.check_user_has_permission
    UserPermissionService.check_user_has_permission = lambda self, uid, slug: False
    try:
        response = client.get(
            f"{BASE}/config/price-floors/effective?product_id={product.id}"
        )
    finally:
        UserPermissionService.check_user_has_permission = saved

    assert response.status_code == 403, response.text


def test_the_effective_route_is_not_shadowed_by_the_rule_id_path(api):
    """``/config/price-floors/{rule_id}`` sits on the same prefix. If the literal lost
    the race it would be read as a rule id and 404 while looking like empty data."""
    client, db, company_id = api
    category = _category(db, "Basins")
    _rule(db, company_id, mode="percent", value="80", category_id=category.id)
    db.commit()

    response = client.get(
        f"{BASE}/config/price-floors/effective?category_id={category.id}"
    )

    assert response.status_code == 200, response.text
