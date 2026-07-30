"""`/master-data/products/select` must search and page on the SERVER.

This endpoint feeds every product dropdown in the app, including all three
dealer-kit pickers. It used to return the first 100 active products with no way
to ask for more, so any caller that filtered client-side could only ever see
those 100 rows: on the real catalogue (22,000+ active products) a search for a
code shared by 998 products answered "no products match".

The tests below pin the three properties that bug needed:

1. the search term is applied in SQL, not by the caller,
2. `offset` reaches rows the first page never contained,
3. the order is stable, so paging cannot repeat or skip a row.

Auth/scope override pattern from test_dealer_kit_selection_routes.py.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402

from tests._pg_fixture import blank_session

_USER_ID = "5b2e7c94-1f38-5a06-8d47-3c9b6e2f4a18"
_ROLE_ID = "3a7f1d26-8c45-5b93-9e02-7d4c1a8f6b35"
_SORENTO = "00000000-0000-0000-0000-000000000001"

# Distinctive so a stray real product cannot satisfy a "search finds it" test.
_STEM = f"ZZTPS{uuid.uuid4().hex[:5]}".upper()


def _seed(db: Session) -> None:
    from app.models.user import (
        User,
        UserPermission,
        UserRole,
        UserRoleAssignment,
        UserRolePermission,
    )

    db.add(
        UserRole(
            id=_ROLE_ID,
            slug="superadmin",
            name="Superadmin",
            description="",
            is_protected=True,
            is_default=False,
        )
    )
    db.add(User(id=_USER_ID, email="zzt-select@test.com", name="Select", status="ACTIVE"))
    db.flush()
    db.add(UserRoleAssignment(user_id=_USER_ID, role_id=_ROLE_ID))
    perm_id = str(uuid.uuid4())
    db.add(
        UserPermission(
            id=perm_id,
            slug="master_data.products.view",
            name="products.view",
            description="",
        )
    )
    db.flush()
    db.add(UserRolePermission(id=str(uuid.uuid4()), role_id=_ROLE_ID, permission_id=perm_id))
    db.commit()


def _products(db: Session, count: int) -> list[str]:
    """`count` active products sharing one code prefix. Returns their codes."""
    from app.models.product import Product, ProductCategory, UnitOfMeasure

    category = ProductCategory(
        category_code=f"{_STEM}CAT", category_name=f"ZZT cat {_STEM}"
    )
    uom = UnitOfMeasure(uom_code=f"{_STEM}U"[:20], uom_name=f"ZZT uom {_STEM}")
    db.add_all([category, uom])
    db.flush()

    codes = []
    for index in range(count):
        # Zero-padded so lexical order (what the endpoint sorts by) matches the
        # order they were created in - otherwise "page 2" is untestable.
        code = f"{_STEM}-{index:03d}"
        codes.append(code)
        db.add(
            Product(
                product_code=code,
                product_name=f"ZZT product {index}",
                category_id=category.id,
                base_uom_id=uom.id,
                list_price=Decimal("10.00"),
                currency="MYR",
                is_active=True,
                is_discontinued=False,
                company_id=_SORENTO,
            )
        )
    db.flush()
    return codes


@pytest.fixture
def api():
    from app.dependencies import get_current_user, get_current_user_or_api_key, get_db
    from app.models.base import set_company_scope
    from app.services.company_scope_resolver import apply_company_scope

    with blank_session() as db:
        _seed(db)

        def _override_get_db():
            yield db

        app.dependency_overrides[get_db] = _override_get_db

        async def _override_scope():
            scope = frozenset({_SORENTO})
            set_company_scope(db, scope)
            return scope

        app.dependency_overrides[apply_company_scope] = _override_scope

        principal = {"id": _USER_ID, "email": "zzt-select@test.com"}
        app.dependency_overrides[get_current_user] = lambda: principal
        app.dependency_overrides[get_current_user_or_api_key] = lambda: principal

        yield db

        app.dependency_overrides.clear()


def _codes(response) -> list[str]:
    assert response.status_code == 200, response.text
    return [row["product_code"] for row in response.json()["data"]]


def test_a_search_term_is_applied_on_the_server(api):
    db = api
    _products(db, 3)
    client = TestClient(app)

    found = _codes(client.get("/api/v1/master-data/products/select", params={"query": _STEM}))
    assert len(found) == 3
    assert all(code.startswith(_STEM) for code in found)


def test_a_search_term_that_matches_nothing_returns_nothing(api):
    db = api
    _products(db, 3)
    client = TestClient(app)

    found = _codes(
        client.get(
            "/api/v1/master-data/products/select",
            params={"query": f"{_STEM}-NO-SUCH-CODE"},
        )
    )
    assert found == []


def test_offset_reaches_rows_the_first_page_did_not_contain(api):
    """The bug in one assertion: without a working offset, page 2 is page 1."""
    db = api
    _products(db, 12)
    client = TestClient(app)

    first = _codes(
        client.get(
            "/api/v1/master-data/products/select",
            params={"query": _STEM, "limit": 5, "offset": 0},
        )
    )
    second = _codes(
        client.get(
            "/api/v1/master-data/products/select",
            params={"query": _STEM, "limit": 5, "offset": 5},
        )
    )
    third = _codes(
        client.get(
            "/api/v1/master-data/products/select",
            params={"query": _STEM, "limit": 5, "offset": 10},
        )
    )

    assert len(first) == 5 and len(second) == 5
    assert len(third) == 2, "the last page must be short, not padded or wrapped"
    assert not set(first) & set(second)
    assert len(set(first) | set(second) | set(third)) == 12


def test_paging_is_ordered_by_code_so_pages_neither_repeat_nor_skip(api):
    db = api
    codes = _products(db, 7)
    client = TestClient(app)

    walked: list[str] = []
    for offset in (0, 3, 6):
        walked.extend(
            _codes(
                client.get(
                    "/api/v1/master-data/products/select",
                    params={"query": _STEM, "limit": 3, "offset": offset},
                )
            )
        )

    assert walked == sorted(codes)


def test_the_limit_is_bounded_and_validated(api):
    """`limit` is capped, so one caller cannot ask for the whole catalogue, and
    a nonsense value is a 422 rather than a silently different page size."""
    db = api
    _products(db, 3)
    client = TestClient(app)

    assert client.get("/api/v1/master-data/products/select", params={"limit": 500}).status_code == 422
    assert client.get("/api/v1/master-data/products/select", params={"limit": 0}).status_code == 422
    assert client.get("/api/v1/master-data/products/select", params={"offset": -1}).status_code == 422


def test_discontinued_and_price_reach_the_dropdown(api):
    """A picker that cannot see `is_discontinued` offers a product nobody can
    buy with nothing to say so."""
    db = api
    from app.models.product import Product

    _products(db, 2)
    db.query(Product).filter(Product.product_code == f"{_STEM}-001").update(
        {"is_discontinued": True}
    )
    db.flush()
    client = TestClient(app)

    rows = client.get(
        "/api/v1/master-data/products/select", params={"query": _STEM}
    ).json()["data"]
    by_code = {row["product_code"]: row for row in rows}
    assert by_code[f"{_STEM}-000"]["is_discontinued"] is False
    assert by_code[f"{_STEM}-001"]["is_discontinued"] is True
    assert by_code[f"{_STEM}-000"]["list_price"] == "10.00"
    assert by_code[f"{_STEM}-000"]["category_name"] == f"ZZT cat {_STEM}"


def test_inactive_products_never_appear(api):
    db = api
    from app.models.product import Product

    _products(db, 2)
    db.query(Product).filter(Product.product_code == f"{_STEM}-001").update(
        {"is_active": False}
    )
    db.flush()
    client = TestClient(app)

    found = _codes(client.get("/api/v1/master-data/products/select", params={"query": _STEM}))
    assert found == [f"{_STEM}-000"]


def test_a_category_narrows_the_list_and_composes_with_the_search(api):
    """Category is what turns a 22,000-product dropdown into a browsable one.

    It has to NARROW rather than replace: picking a category and then typing
    must search inside that category, not across the catalogue again.
    """
    db = api
    from app.models.product import Product, ProductCategory

    _products(db, 3)
    mine = db.query(Product).filter(Product.product_code.like(f"{_STEM}%")).all()
    category_id = mine[0].category_id

    other_category = ProductCategory(
        category_code=f"{_STEM}OTH", category_name=f"ZZT other {_STEM}"
    )
    db.add(other_category)
    db.flush()
    db.query(Product).filter(Product.product_code == f"{_STEM}-002").update(
        {"category_id": other_category.id}
    )
    db.flush()

    client = TestClient(app)

    narrowed = _codes(
        client.get(
            "/api/v1/master-data/products/select",
            params={"query": _STEM, "category_id": category_id},
        )
    )
    assert narrowed == [f"{_STEM}-000", f"{_STEM}-001"]

    # Composed with a search term, not replaced by it.
    both = _codes(
        client.get(
            "/api/v1/master-data/products/select",
            params={"query": f"{_STEM}-001", "category_id": category_id},
        )
    )
    assert both == [f"{_STEM}-001"]

    # A category with nothing in it is an empty list, not everything.
    empty = _codes(
        client.get(
            "/api/v1/master-data/products/select",
            params={"query": _STEM, "category_id": str(uuid.uuid4())},
        )
    )
    assert empty == []
