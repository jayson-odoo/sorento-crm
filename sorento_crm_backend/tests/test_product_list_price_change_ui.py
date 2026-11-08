"""Products list: "List price changed at" column, sort, date-range filter, and the per-product
list-price change history the List Price cell's lightbox reads (LIST-PRICE-CHANGE-UI).

Plan: `documentation/plans/products/PLAN-list-price-change-ui-08nov.md`.

The column mirrors "Discontinued at" (`tests/test_product_discontinued_at_list.py`): it is the
#2228 watermark `products.list_price_notified_at`, exposed as `list_price_changed_at`, sorted
NULLS LAST, filtered by an inclusive Malaysia-day range (`list_price_changed_from` / `_to`).

The history is the product's audit trail: every `product` UPDATE row whose `new_values` carries
`list_price`, newest first, credited by the same rule as the #2228 digest's "by <source>".

Postgres only; every row is seeded fresh with fake values.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.dependencies import (
    get_current_user,
    get_current_user_or_api_key,
    get_db,
    get_external_api_user,
)
from app.main import app
from app.models.audit import AuditLog
from app.models.base import set_company_scope
from app.models.company import Company
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.user import User
from app.schemas.list_query import ListExportRequest, ListSearchRequest
from app.services.company_scope import DEFAULT_COMPANY_ID, register_company_scope_listeners
from app.services.company_scope_resolver import apply_company_scope
from app.services.list_query_export_service import ListQueryExportService
from app.services.list_query_search_service import ListQuerySearchService
from app.services.product_service import ProductService
from tests._pg_fixture import blank_session, pg_session, unique_code
from tests.scm.conftest import requires_pg  # noqa: F401

SORENTO_ID = DEFAULT_COMPANY_ID
STEM = "ZZTLPCUI"


def _refs(db):
    if not hasattr(db, "_zzt_lpc_refs"):
        cat_id = str(uuid.uuid4())
        uom_id = str(uuid.uuid4())
        db.add(ProductCategory(id=cat_id, category_code=unique_code("CAT"), category_name="ZZT Category"))
        db.add(UnitOfMeasure(id=uom_id, uom_code=unique_code("EA")[:16], uom_name="ZZT Each"))
        db.flush()
        db._zzt_lpc_refs = (cat_id, uom_id)
    return db._zzt_lpc_refs


def _mk_product(db, code: str, *, changed_at: datetime | None = None, price="10.00", company_id=None) -> str:
    cat_id, uom_id = _refs(db)
    pid = str(uuid.uuid4())
    kwargs = {"company_id": company_id} if company_id else {}
    db.add(
        Product(
            id=pid,
            product_code=code,
            product_name=code,
            category_id=cat_id,
            base_uom_id=uom_id,
            list_price=Decimal(price),
            list_price_notified=Decimal(price),
            list_price_notified_at=changed_at,
            is_active=True,
            **kwargs,
        )
    )
    db.flush()
    return pid


def _audit(db, pid, *, old, new, actor_type="user", user_id=None, changed_at=None, extra_new=None):
    new_values = {"list_price": new} if new is not None else {}
    new_values.update(extra_new or {})
    old_values = {"list_price": old} if old is not None else {}
    row = AuditLog(
        id=str(uuid.uuid4()),
        entity_type="product",
        entity_id=pid,
        action="UPDATE",
        old_values=old_values,
        new_values=new_values,
        actor_type=actor_type,
        user_id=user_id,
    )
    if changed_at is not None:
        row.changed_at = changed_at
    db.add(row)
    db.flush()
    return row


def _codes(payload: dict) -> set[str]:
    return {row["product_code"] for row in payload["data"]}


def _codes_orm(payload: dict) -> set[str]:
    return {row.product_code for row in payload["data"]}


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

    principal = {"id": str(uuid.uuid4()), "email": "zzt-lpcui@test.com"}

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


# --------------------------------------------------------------------------- column


def test_list_rows_carry_list_price_changed_at(api, db):
    p_changed = _mk_product(db, f"{STEM}-COL-CHANGED", changed_at=datetime(2026, 11, 8, 10, 15, 0))
    p_never = _mk_product(db, f"{STEM}-COL-NEVER")
    db.commit()

    resp = api.get(
        "/api/v1/master-data/products",
        params={"product_ids": [p_changed, p_never], "limit": 50},
    )
    assert resp.status_code == 200, resp.text
    rows = {row["product_code"]: row for row in resp.json()["data"]}
    assert rows[f"{STEM}-COL-CHANGED"]["list_price_changed_at"].startswith("2026-11-08T10:15:00")
    assert "list_price_changed_at" in rows[f"{STEM}-COL-NEVER"]
    assert rows[f"{STEM}-COL-NEVER"]["list_price_changed_at"] is None


# --------------------------------------------------------------------------- sort


@pytest.mark.parametrize("direction", ["asc", "desc"])
def test_sort_list_price_changed_at_nulls_last(db, direction):
    p_a = _mk_product(db, f"{STEM}-SORT-{direction}-A", changed_at=datetime(2026, 11, 1))
    p_b = _mk_product(db, f"{STEM}-SORT-{direction}-B", changed_at=datetime(2026, 11, 5))
    p_c = _mk_product(db, f"{STEM}-SORT-{direction}-C", changed_at=datetime(2026, 11, 5))
    p_d = _mk_product(db, f"{STEM}-SORT-{direction}-D")
    p_e = _mk_product(db, f"{STEM}-SORT-{direction}-E")
    db.commit()

    ties = sorted([p_b, p_c])
    nulls = sorted([p_d, p_e])
    expected = ([p_a] + ties if direction == "asc" else ties + [p_a]) + nulls

    result = ProductService(db).list_products(
        product_ids=[p_a, p_b, p_c, p_d, p_e],
        sort_field="list_price_changed_at",
        sort_dir=direction,
        limit=50,
    )
    assert [row.id for row in result["data"]] == expected


# --------------------------------------------------------------------------- filter


def test_filter_malaysia_day_boundaries(api, db):
    p_in = _mk_product(db, f"{STEM}-FLT1-IN", changed_at=datetime(2026, 11, 7, 16, 30))  # 8 Nov 00:30 MYT
    p_before = _mk_product(db, f"{STEM}-FLT1-BEFORE", changed_at=datetime(2026, 11, 7, 15, 59))  # 7 Nov 23:59
    p_after = _mk_product(db, f"{STEM}-FLT1-AFTER", changed_at=datetime(2026, 11, 8, 16, 0))  # 9 Nov 00:00
    db.commit()

    resp = api.get(
        "/api/v1/master-data/products",
        params={
            "product_ids": [p_in, p_before, p_after],
            "list_price_changed_from": "2026-11-08",
            "list_price_changed_to": "2026-11-08",
            "limit": 50,
        },
    )
    assert resp.status_code == 200, resp.text
    assert _codes(resp.json()) == {f"{STEM}-FLT1-IN"}


def test_filter_open_ended_bounds_exclude_never_changed(api, db):
    p_early = _mk_product(db, f"{STEM}-FLT2-EARLY", changed_at=datetime(2026, 11, 1))
    p_late = _mk_product(db, f"{STEM}-FLT2-LATE", changed_at=datetime(2026, 11, 20))
    p_null = _mk_product(db, f"{STEM}-FLT2-NULL")
    db.commit()
    ids = [p_early, p_late, p_null]

    from_only = api.get(
        "/api/v1/master-data/products",
        params={"product_ids": ids, "list_price_changed_from": "2026-11-10", "limit": 50},
    )
    assert from_only.status_code == 200, from_only.text
    assert _codes(from_only.json()) == {f"{STEM}-FLT2-LATE"}

    to_only = api.get(
        "/api/v1/master-data/products",
        params={"product_ids": ids, "list_price_changed_to": "2026-11-10", "limit": 50},
    )
    assert to_only.status_code == 200, to_only.text
    assert _codes(to_only.json()) == {f"{STEM}-FLT2-EARLY"}


def test_filter_malformed_date_is_422(api, db):
    resp = api.get(
        "/api/v1/master-data/products",
        params={"list_price_changed_from": "08-11-2026", "limit": 10},
    )
    assert resp.status_code == 422, resp.text


def test_filter_is_independent_of_the_discontinued_range(api, db):
    """The two ranges are separate filters on separate columns (a list-price range must not
    read discontinued_notified_at, nor the reverse)."""
    p = _mk_product(db, f"{STEM}-FLT3-ONLYLP", changed_at=datetime(2026, 11, 8, 2, 0))
    db.commit()
    resp = api.get(
        "/api/v1/master-data/products",
        params={"product_ids": [p], "discontinued_from": "2026-11-08", "limit": 10},
    )
    assert resp.status_code == 200
    assert _codes(resp.json()) == set()
    resp = api.get(
        "/api/v1/master-data/products",
        params={"product_ids": [p], "list_price_changed_from": "2026-11-08", "limit": 10},
    )
    assert _codes(resp.json()) == {f"{STEM}-FLT3-ONLYLP"}


@requires_pg
def test_list_query_search_honours_list_price_changed_range():
    with pg_session() as db:
        stem = unique_code(f"{STEM}S")
        _mk_product(db, f"{stem}-IN", changed_at=datetime(2026, 11, 7, 16, 30))
        _mk_product(db, f"{stem}-OUT", changed_at=datetime(2026, 11, 7, 15, 59))
        _mk_product(db, f"{stem}-NULL")
        db.commit()

        req = ListSearchRequest(
            resource="products",
            quick_search=stem,
            list_price_changed_from=date(2026, 11, 8),
            list_price_changed_to=date(2026, 11, 8),
            limit=50,
        )
        result = ListQuerySearchService(db).search(req)
        assert _codes_orm(result) == {f"{stem}-IN"}


def test_export_honours_list_price_changed_range(db):
    from tests.test_product_discontinued_at_list import _ensure_products_discontinued_at_field

    _ensure_products_discontinued_at_field(db)
    p_in = _mk_product(db, f"{STEM}-EXP-IN", changed_at=datetime(2026, 11, 7, 16, 30))
    p_out = _mk_product(db, f"{STEM}-EXP-OUT", changed_at=datetime(2026, 11, 1))
    p_null = _mk_product(db, f"{STEM}-EXP-NULL")
    db.commit()

    req = ListExportRequest(
        resource="products",
        fields=[{"field_key": "discontinued_at"}],
        record_ids=[p_in, p_out, p_null],
        list_price_changed_from=date(2026, 11, 8),
        list_price_changed_to=date(2026, 11, 8),
    )
    rows = ListQueryExportService(db).export_rows(req)
    assert len(rows) == 1, f"expected only the in-range row exported, got {rows}"


# --------------------------------------------------------------------------- history


def _staff(db, name="Fake Pricer", email=None):
    u = User(
        id=str(uuid.uuid4()),
        email=email or f"{unique_code('pricer').lower()}@example.test",
        name=name,
        status="ACTIVE",
    )
    db.add(u)
    db.flush()
    return u


def _history(api, pid, **params):
    return api.get(f"/api/v1/master-data/products/{pid}/list-price-history", params=params)


def test_history_newest_first_with_old_new_pct_and_source(api, db):
    staff = _staff(db, name="Fake Pricer")
    pid = _mk_product(db, f"{STEM}-HIST", price="121.00", changed_at=datetime(2026, 11, 8, 2, 0))
    t0 = datetime(2026, 10, 1, 4, 0)
    _audit(db, pid, old="100.00", new="110.00", actor_type="integration", changed_at=t0)
    _audit(db, pid, old="110.00", new="121.00", actor_type="user", user_id=staff.id,
           changed_at=t0 + timedelta(days=30))
    _audit(db, pid, old="0.00", new="100.00", actor_type="scheduler", changed_at=t0 - timedelta(days=30))
    db.commit()

    resp = _history(api, pid)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    rows = body["data"]
    assert [r["new_price"] for r in rows] == [121.0, 110.0, 100.0], "newest first"
    assert rows[0]["old_price"] == 110.0
    assert rows[0]["change_pct"] == 10.0
    assert rows[0]["changed_by"] == "Fake Pricer"
    assert rows[0]["changed_at"].startswith("2026-10-31T04:00:00")
    assert rows[1]["changed_by"] == "AutoCount sync"
    assert rows[1]["change_pct"] == 10.0
    assert rows[2]["change_pct"] is None, "from 0 there is no percentage"
    assert rows[2]["changed_by"] is None, "a non-user, non-integration actor is not named"
    assert body["total"] == 3
    assert body["truncated"] is False


def test_history_negative_change_pct_rounds_to_one_decimal(api, db):
    pid = _mk_product(db, f"{STEM}-NEG", price="88.88")
    _audit(db, pid, old="99.99", new="88.88")
    db.commit()
    row = _history(api, pid).json()["data"][0]
    assert row["change_pct"] == -11.1
    assert row["old_price"] == 99.99 and row["new_price"] == 88.88


def test_history_skips_rows_without_a_list_price_change(api, db):
    pid = _mk_product(db, f"{STEM}-SKIP")
    other = _mk_product(db, f"{STEM}-OTHER")
    _audit(db, pid, old=None, new=None, extra_new={"product_name": "renamed"})  # not a price change
    _audit(db, pid, old="10.00", new="10.00")  # no-op restatement
    _audit(db, other, old="10.00", new="12.00")  # another product
    db.add(AuditLog(id=str(uuid.uuid4()), entity_type="product", entity_id=pid, action="CREATE",
                    new_values={"list_price": "10.00"}, actor_type="user"))
    _audit(db, pid, old="9.00", new="10.00")
    db.commit()

    rows = _history(api, pid).json()["data"]
    assert [(r["old_price"], r["new_price"]) for r in rows] == [(9.0, 10.0)]


def test_history_empty_for_a_product_with_no_changes(api, db):
    pid = _mk_product(db, f"{STEM}-EMPTY")
    db.commit()
    resp = _history(api, pid)
    assert resp.status_code == 200
    assert resp.json() == {"data": [], "total": 0, "truncated": False}


def test_history_caps_at_limit_and_says_so(api, db):
    pid = _mk_product(db, f"{STEM}-CAP")
    t0 = datetime(2026, 1, 1)
    for i in range(55):
        _audit(db, pid, old=f"{100 + i}.00", new=f"{101 + i}.00", changed_at=t0 + timedelta(hours=i))
    db.commit()
    body = _history(api, pid).json()
    assert len(body["data"]) == 50
    assert body["total"] == 55
    assert body["truncated"] is True
    assert body["data"][0]["new_price"] == 155.0, "the cap keeps the NEWEST rows"


def test_history_unknown_product_is_404(api, db):
    resp = _history(api, str(uuid.uuid4()))
    assert resp.status_code == 404, resp.text


def test_history_of_another_companys_product_is_404(api, db):
    other_company = str(uuid.uuid4())
    db.add(Company(id=other_company, name="ZZT Other Co", code=unique_code("OTH")[:20]))
    db.flush()
    pid = _mk_product(db, f"{STEM}-XCO", company_id=other_company)
    _audit(db, pid, old="10.00", new="12.00")
    db.commit()
    resp = _history(api, pid)
    assert resp.status_code == 404, resp.text


def test_history_through_the_real_audit_listener(api, db):
    """End to end: a real ORM price edit lands in the history, so a rename of the audit entity
    type or of the column key cannot silently empty the lightbox."""
    from app.audit_context import AuditActor, actor_scope
    from app.services.audit_service import register_audit_listeners

    register_audit_listeners()
    staff = _staff(db, name="Fake Real Staff")
    pid = _mk_product(db, f"{STEM}-REAL", price="100.00")
    db.commit()

    with actor_scope(AuditActor(actor_type="user", user_id=staff.id, real_user_id=staff.id), db=db):
        p = db.get(Product, pid)
        p.list_price = Decimal("125.00")
        db.commit()

    rows = _history(api, pid).json()["data"]
    assert len(rows) == 1
    assert (rows[0]["old_price"], rows[0]["new_price"], rows[0]["change_pct"]) == (100.0, 125.0, 25.0)
    assert rows[0]["changed_by"] == "Fake Real Staff"
