"""Products list: "Discontinued at" column, sort and date-range filter (issue #1287).

UAC: `documentation/plans/products/products-discontinued-at-26sep-acceptance-criteria.md`.
Plan: `documentation/plans/products/PLAN-products-discontinued-at-26sep.md`.

RED for Phase 2: `ProductResponse` does not carry `discontinued_at`, `sort_map` has no
`discontinued_at` entry, `GET /api/v1/master-data/products` has no `discontinued_from` /
`discontinued_to` query params, `ListSearchRequest` / `ListExportRequest` have no such
fields either, and no `list_query_fields` catalog row exists for `discontinued_at` on the
`products` resource. Every assertion below fails against TODAY's code for one of those
reasons - a missing field / silently-ignored query param / empty catalog lookup - never an
import typo or fixture bug.

Harness copied from `tests/test_product_exclude_from_planning.py` (blank_session + TestClient
`api` fixture) and `tests/test_product_brand_id_comma_filter.py` (blank_session + ProductService
direct). Postgres only, every row marker-prefixed (`ZZTDISCAT`) and seeded fresh - nothing
borrowed off the shared prod-copy database.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.dependencies import (
    get_current_user,
    get_current_user_or_api_key,
    get_db,
    get_external_api_user,
)
from app.main import app
from app.models.base import set_company_scope
from app.models.list_query_metadata import ListQueryField
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.schemas.list_query import ListExportRequest, ListSearchRequest
from app.services.company_scope import DEFAULT_COMPANY_ID, register_company_scope_listeners
from app.services.company_scope_resolver import apply_company_scope
from app.services.list_query_export_service import ListQueryExportService
from app.services.list_query_search_service import ListQuerySearchService
from app.services.product_service import ProductService
from tests._pg_fixture import blank_session, pg_session, unique_code
from tests.scm.conftest import requires_pg, scm_app  # noqa: F401 - pytest fixture import

SORENTO_ID = DEFAULT_COMPANY_ID
STEM = "ZZTDISCAT"


# --------------------------------------------------------------------------------------- #
# Shared seeding helpers
# --------------------------------------------------------------------------------------- #


def _refs(db):
    """Get-or-create a category + uom on this session, cached on the session object."""
    if not hasattr(db, "_zzt_discat_refs"):
        cat_id = str(uuid.uuid4())
        uom_id = str(uuid.uuid4())
        db.add(ProductCategory(id=cat_id, category_code=unique_code("CAT"), category_name="ZZT Category"))
        db.add(UnitOfMeasure(id=uom_id, uom_code=unique_code("EA")[:16], uom_name="ZZT Each"))
        db.flush()
        db._zzt_discat_refs = (cat_id, uom_id)
    return db._zzt_discat_refs


def _mk_product(db, code: str, *, discontinued_notified_at: datetime | None = None) -> str:
    cat_id, uom_id = _refs(db)
    pid = str(uuid.uuid4())
    db.add(
        Product(
            id=pid,
            product_code=code,
            product_name=code,
            category_id=cat_id,
            base_uom_id=uom_id,
            list_price=Decimal("10.00"),
            is_active=True,
            discontinued_notified_at=discontinued_notified_at,
        )
    )
    db.flush()
    return pid


def _codes(payload: dict) -> set[str]:
    return {row["product_code"] for row in payload["data"]}


def _codes_orm(payload: dict) -> set[str]:
    """Same as `_codes`, but for a raw `ProductService.list_products` result whose
    `data` rows are ORM `Product` instances (attribute access), not JSON dicts."""
    return {row.product_code for row in payload["data"]}


def _ensure_products_discontinued_at_field(conn) -> None:
    """Get-or-create the `products` resource row and its `discontinued_at` field row.

    Same reasoning as `test_supplier_country.py`'s `_ensure_suppliers_list_query_metadata`:
    `list_query_resources` / `list_query_fields` are migration-seeded DATA, invisible to a
    from-scratch `blank_session` schema (`create_all` builds the TABLES only). Idempotent
    (`WHERE NOT EXISTS`), so it is also a safe no-op against an already-migrated database
    that already carries the row this lane's own migration will add.
    """
    conn.execute(
        text(
            """
            INSERT INTO list_query_resources (id, resource_key, display_name, description, is_active)
            SELECT gen_random_uuid(), 'products', 'Products', 'Product master list', true
            WHERE NOT EXISTS (
                SELECT 1 FROM list_query_resources WHERE resource_key = 'products'
            )
            """
        )
    )
    conn.execute(
        text(
            """
            INSERT INTO list_query_fields (
                id, resource_id, field_key, label, data_type, compile_key,
                allowed_operators, filterable, exportable, export_column_name,
                is_line_field, sort_order
            )
            SELECT gen_random_uuid(), r.id, 'discontinued_at', 'Discontinued at', 'date',
                   'product.discontinued_notified_at', CAST('["eq","gt","gte","lt","lte","is_null"]' AS jsonb),
                   false, true, 'Discontinued at', false, 98
            FROM list_query_resources r
            WHERE r.resource_key = 'products'
              AND NOT EXISTS (
                  SELECT 1 FROM list_query_fields f
                  WHERE f.resource_id = r.id AND f.field_key = 'discontinued_at'
              )
            """
        )
    )


# --------------------------------------------------------------------------------------- #
# Fixtures (TestClient path - AC-COL-3, AC-FLT-1/2/3)
# --------------------------------------------------------------------------------------- #


@pytest.fixture(autouse=True)
def _scope_listeners():
    register_company_scope_listeners()


@pytest.fixture
def db():
    with blank_session() as session:
        set_company_scope(session, None)
        yield session


@pytest.fixture
def api(db):
    def _override_get_db():
        yield db

    principal = {"id": str(uuid.uuid4()), "email": "zzt-discat@test.com"}

    async def _override_scope():
        scope = frozenset({SORENTO_ID})
        set_company_scope(db, scope)
        return scope

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_user] = lambda: principal
    app.dependency_overrides[get_current_user_or_api_key] = lambda: principal
    app.dependency_overrides[get_external_api_user] = lambda: principal
    app.dependency_overrides[apply_company_scope] = _override_scope
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()


# --------------------------------------------------------------------------------------- #
# AC-COL-3: every GET row carries discontinued_at
# --------------------------------------------------------------------------------------- #


def test_list_rows_carry_discontinued_at(api, db):
    stamp = datetime(2026, 9, 20, 10, 15, 0)
    p_stamped = _mk_product(db, f"{STEM}-COL-STAMPED", discontinued_notified_at=stamp)
    p_available = _mk_product(db, f"{STEM}-COL-AVAILABLE", discontinued_notified_at=None)
    db.commit()

    resp = api.get(
        "/api/v1/master-data/products",
        params={"product_ids": [p_stamped, p_available], "limit": 50},
    )
    assert resp.status_code == 200, resp.text
    rows = {row["product_code"]: row for row in resp.json()["data"]}

    assert "discontinued_at" in rows[f"{STEM}-COL-STAMPED"], (
        "ProductResponse must carry discontinued_at"
    )
    assert rows[f"{STEM}-COL-STAMPED"]["discontinued_at"].startswith("2026-09-20T10:15:00")
    assert rows[f"{STEM}-COL-AVAILABLE"].get("discontinued_at") is None


# --------------------------------------------------------------------------------------- #
# AC-SORT-1: sort=discontinued_at, both directions, nulls last, id tiebreak
# --------------------------------------------------------------------------------------- #


def test_sort_discontinued_at_asc_nulls_last(db):
    p_a = _mk_product(db, f"{STEM}-SORT-A", discontinued_notified_at=datetime(2026, 9, 1))
    p_b = _mk_product(db, f"{STEM}-SORT-B", discontinued_notified_at=datetime(2026, 9, 15))
    p_c = _mk_product(db, f"{STEM}-SORT-C", discontinued_notified_at=datetime(2026, 9, 15))
    p_d = _mk_product(db, f"{STEM}-SORT-D", discontinued_notified_at=None)
    p_e = _mk_product(db, f"{STEM}-SORT-E", discontinued_notified_at=None)
    db.commit()

    tie_order = sorted([p_b, p_c])
    null_order = sorted([p_d, p_e])
    expected = [p_a] + tie_order + null_order

    result = ProductService(db).list_products(
        product_ids=[p_a, p_b, p_c, p_d, p_e],
        sort_field="discontinued_at",
        sort_dir="asc",
        limit=50,
    )
    got = [row.id for row in result["data"]]
    assert got == expected, f"expected id order {expected}, got {got}"


def test_sort_discontinued_at_desc_nulls_last(db):
    p_a = _mk_product(db, f"{STEM}-SORT2-A", discontinued_notified_at=datetime(2026, 9, 1))
    p_b = _mk_product(db, f"{STEM}-SORT2-B", discontinued_notified_at=datetime(2026, 9, 15))
    p_c = _mk_product(db, f"{STEM}-SORT2-C", discontinued_notified_at=datetime(2026, 9, 15))
    p_d = _mk_product(db, f"{STEM}-SORT2-D", discontinued_notified_at=None)
    p_e = _mk_product(db, f"{STEM}-SORT2-E", discontinued_notified_at=None)
    db.commit()

    tie_order = sorted([p_b, p_c])
    null_order = sorted([p_d, p_e])
    expected = tie_order + [p_a] + null_order

    result = ProductService(db).list_products(
        product_ids=[p_a, p_b, p_c, p_d, p_e],
        sort_field="discontinued_at",
        sort_dir="desc",
        limit=50,
    )
    got = [row.id for row in result["data"]]
    assert got == expected, f"expected id order {expected}, got {got}"


# --------------------------------------------------------------------------------------- #
# AC-FLT-1: inclusive Malaysia-day boundaries
# --------------------------------------------------------------------------------------- #


def test_filter_malaysia_day_boundaries(api, db):
    p_in = _mk_product(
        db, f"{STEM}-FLT1-IN", discontinued_notified_at=datetime(2026, 9, 25, 16, 30, 0)
    )  # 26 Sep 00:30 MYT -> inside [26 Sep, 26 Sep]
    p_before = _mk_product(
        db, f"{STEM}-FLT1-BEFORE", discontinued_notified_at=datetime(2026, 9, 25, 15, 59, 0)
    )  # 25 Sep 23:59 MYT -> outside
    p_after = _mk_product(
        db, f"{STEM}-FLT1-AFTER", discontinued_notified_at=datetime(2026, 9, 26, 16, 0, 0)
    )  # 27 Sep 00:00 MYT -> outside
    db.commit()

    resp = api.get(
        "/api/v1/master-data/products",
        params={
            "product_ids": [p_in, p_before, p_after],
            "discontinued_from": "2026-09-26",
            "discontinued_to": "2026-09-26",
            "limit": 50,
        },
    )
    assert resp.status_code == 200, resp.text
    assert _codes(resp.json()) == {f"{STEM}-FLT1-IN"}


# --------------------------------------------------------------------------------------- #
# AC-FLT-2: open-ended bound; any bound set excludes nulls
# --------------------------------------------------------------------------------------- #


def test_filter_from_only_and_to_only_exclude_nulls(api, db):
    p_before = _mk_product(
        db, f"{STEM}-FLT2-BEFORE", discontinued_notified_at=datetime(2026, 9, 5, 0, 0, 0)
    )
    p_after = _mk_product(
        db, f"{STEM}-FLT2-AFTER", discontinued_notified_at=datetime(2026, 9, 15, 0, 0, 0)
    )
    p_null = _mk_product(db, f"{STEM}-FLT2-NULL", discontinued_notified_at=None)
    db.commit()
    ids = [p_before, p_after, p_null]

    from_only = api.get(
        "/api/v1/master-data/products",
        params={"product_ids": ids, "discontinued_from": "2026-09-10", "limit": 50},
    )
    assert from_only.status_code == 200, from_only.text
    assert _codes(from_only.json()) == {f"{STEM}-FLT2-AFTER"}, (
        "from-only must include everything on/after the day and exclude nulls"
    )

    to_only = api.get(
        "/api/v1/master-data/products",
        params={"product_ids": ids, "discontinued_to": "2026-09-10", "limit": 50},
    )
    assert to_only.status_code == 200, to_only.text
    assert _codes(to_only.json()) == {f"{STEM}-FLT2-BEFORE"}, (
        "to-only must include everything on/before the day and exclude nulls"
    )


# --------------------------------------------------------------------------------------- #
# AC-FLT-3: malformed date -> 422
# --------------------------------------------------------------------------------------- #


def test_filter_malformed_date_is_422(api, db):
    resp = api.get(
        "/api/v1/master-data/products",
        params={"discontinued_from": "26-09-2026", "limit": 10},
    )
    assert resp.status_code == 422, resp.text


# --------------------------------------------------------------------------------------- #
# AC-FLT-4: POST /api/v1/list-query/search honours the range (service level, real DB -
# the `products` list_query_resources row is migration-seeded, invisible to blank_session)
# --------------------------------------------------------------------------------------- #

@requires_pg
def test_list_query_search_honours_discontinued_range():
    with pg_session() as db:
        stem = unique_code(f"{STEM}FLT4")
        _mk_product(db, f"{stem}-IN", discontinued_notified_at=datetime(2026, 9, 25, 16, 30, 0))
        _mk_product(db, f"{stem}-BEFORE", discontinued_notified_at=datetime(2026, 9, 25, 15, 59, 0))
        _mk_product(db, f"{stem}-AFTER", discontinued_notified_at=datetime(2026, 9, 26, 16, 0, 0))
        db.commit()

        req = ListSearchRequest(
            resource="products",
            quick_search=stem,
            discontinued_from=date(2026, 9, 26),
            discontinued_to=date(2026, 9, 26),
            limit=50,
        )
        result = ListQuerySearchService(db).search(req)
        assert _codes_orm(result) == {f"{stem}-IN"}, (
            f"expected only the in-range row, got {_codes_orm(result)}"
        )


# --------------------------------------------------------------------------------------- #
# AC-EXP-1 (part 1): the products export field catalog lists discontinued_at
# (real migrated database - a from-scratch blank_session schema never carries the
# migration-SEEDED list_query_fields row this pins).
# --------------------------------------------------------------------------------------- #


def test_export_catalog_has_discontinued_at_field(scm_app):
    from app.services.list_query_metadata_service import ListQueryMetadataService

    _, real_db, _, _ = scm_app
    fields = ListQueryMetadataService(real_db).fields_by_key("products")
    field = fields.get("discontinued_at")
    assert field is not None, "discontinued_at must be in the products field catalog"
    assert field.label == "Discontinued at"
    assert field.data_type == "date"
    assert field.export_column_name == "Discontinued at"
    # Export only: the Filters popover range is the one filter for this date. A
    # filterable row would offer a second "Discontinued at" in Actions > Advanced
    # filters, whose compiler has no Malaysia-day conversion (reviewer S1).
    assert field.filterable is False, (
        "discontinued_at must not be offered in advanced filters"
    )


def test_seed_flips_an_already_seeded_filterable_row(db):
    """A database that ran the first cut of `prod_discontinued_at_flt` carries the row
    with `filterable = true`; replaying `seed()` (bootstrap, downgrade/upgrade) must leave
    it export-only, without inserting a duplicate."""
    import importlib.util
    from pathlib import Path

    _ensure_products_discontinued_at_field(db)
    db.execute(
        text(
            "UPDATE list_query_fields SET filterable = true "
            "WHERE field_key = 'discontinued_at' AND resource_id = "
            "(SELECT id FROM list_query_resources WHERE resource_key = 'products')"
        )
    )
    db.flush()

    path = Path(__file__).resolve().parent.parent / "alembic" / "versions" / "prod_discontinued_at_flt.py"
    spec = importlib.util.spec_from_file_location("_seed_prod_discontinued_at_flt", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.seed(db.connection()) is False
    rows = db.execute(
        text(
            "SELECT f.filterable, f.exportable FROM list_query_fields f "
            "JOIN list_query_resources r ON r.id = f.resource_id "
            "WHERE r.resource_key = 'products' AND f.field_key = 'discontinued_at'"
        )
    ).fetchall()
    assert [(r.filterable, r.exportable) for r in rows] == [(False, True)]


# --------------------------------------------------------------------------------------- #
# AC-EXP-1 (part 2) + AC-EXP-2: exported value is the Malaysia calendar date, and the
# export honours discontinued_from / discontinued_to.
# --------------------------------------------------------------------------------------- #


def test_export_value_is_malaysia_date_and_honours_range(db):
    _ensure_products_discontinued_at_field(db)

    p_in = _mk_product(
        db, f"{STEM}-EXP-IN", discontinued_notified_at=datetime(2026, 9, 25, 16, 30, 0)
    )  # 26 Sep 00:30 MYT
    p_out = _mk_product(
        db, f"{STEM}-EXP-OUT", discontinued_notified_at=datetime(2026, 9, 20, 0, 0, 0)
    )
    p_null = _mk_product(db, f"{STEM}-EXP-NULL", discontinued_notified_at=None)
    db.commit()

    field = (
        db.query(ListQueryField)
        .join(ListQueryField.resource)
        .filter_by(resource_key="products")
        .filter(ListQueryField.field_key == "discontinued_at")
        .one()
    )
    assert field.compile_key == "product.discontinued_notified_at"

    req = ListExportRequest(
        resource="products",
        fields=[{"field_key": "discontinued_at"}],
        record_ids=[p_in, p_out, p_null],
        discontinued_from=date(2026, 9, 26),
        discontinued_to=date(2026, 9, 26),
    )
    rows = ListQueryExportService(db).export_rows(req)

    assert len(rows) == 1, f"expected only the in-range row exported, got {rows}"
    assert rows[0]["Discontinued at"] == "2026-09-26"
