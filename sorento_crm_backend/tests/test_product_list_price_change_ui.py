"""Products list: "List price changed at" column, sort, date-range filter, and the per-product
list-price change history the List Price cell's lightbox reads (LIST-PRICE-CHANGE-UI).

Plan: `documentation/plans/products/PLAN-list-price-change-ui-08nov.md`.

The column mirrors "Discontinued at" (`tests/test_product_discontinued_at_list.py`): it is the
#2228 watermark `products.list_price_notified_at`, exposed as `list_price_changed_at`, sorted
NULLS LAST, filtered by an inclusive Malaysia-day range (`list_price_changed_from` / `_to`).

The history is the product's audit trail: every `product` UPDATE row whose `new_values` carries
`list_price`, plus (owner, Q5) the price the product was created with as an "Initial price" row,
credited by the #2228 digest's "by <source>" rule, paged and sorted on the server (owner, Q3: the
lightbox is the standard DataGrid with pagination). Owner Q1: a one-time backfill stamps
`list_price_notified_at` from the latest audited change. Owner Q4: an export column.

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


def _mk_product(
    db, code: str, *, changed_at: datetime | None = None, price="10.00", company_id=None, keep_trail=False
) -> str:
    """A product with NO audit trail unless ``keep_trail``: once the app has started, the real
    audit listener writes a CREATE row for every insert, and the history tests seed their own."""
    cat_id, uom_id = _refs(db)
    pid = str(uuid.uuid4())
    kwargs = {"company_id": company_id} if company_id else {}
    if not keep_trail:
        # The audit service's own per-session switch (audit_service._session_before_flush).
        db.info["skip_audit_entity_types"] = ["product"]
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
    db.info.pop("skip_audit_entity_types", None)
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
def granted(monkeypatch):
    """The slugs the test principal holds; the history route checks the products view grant
    (security review on #2260: the same grant `/audit/logs` asks for a product's trail)."""
    from app.services.user_service import UserPermissionService

    slugs = {"master_data.products.view"}
    asked: list[str] = []

    def _check(self, uid, slug):
        asked.append(slug)
        return slug in slugs

    monkeypatch.setattr(UserPermissionService, "check_user_has_permission", _check)
    return slugs, asked


@pytest.fixture
def api(db, granted):
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


def _create_row(db, pid, *, price, actor_type="user", user_id=None, changed_at=None):
    row = AuditLog(
        id=str(uuid.uuid4()), entity_type="product", entity_id=pid, action="CREATE",
        new_values={"list_price": price, "product_code": "x"}, actor_type=actor_type, user_id=user_id,
    )
    if changed_at is not None:
        row.changed_at = changed_at
    db.add(row)
    db.flush()
    return row


def _history(api, pid, **params):
    return api.get(f"/api/v1/master-data/products/{pid}/list-price-history", params=params)


def _seed_three(db):
    staff = _staff(db, name="Fake Pricer")
    pid = _mk_product(db, f"{STEM}-HIST-{uuid.uuid4().hex[:6]}", price="121.00")
    t0 = datetime(2026, 10, 1, 4, 0)
    _create_row(db, pid, price="100.00", actor_type="user", user_id=staff.id, changed_at=t0 - timedelta(days=60))
    _audit(db, pid, old="100.00", new="110.00", actor_type="integration", changed_at=t0)
    _audit(db, pid, old="110.00", new="121.00", actor_type="user", user_id=staff.id,
           changed_at=t0 + timedelta(days=30))
    _audit(db, pid, old="121.00", new="0.00", actor_type="scheduler", changed_at=t0 + timedelta(days=31))
    _audit(db, pid, old="0.00", new="121.00", actor_type="legacy", changed_at=t0 + timedelta(days=32))
    db.commit()
    return pid


def test_history_default_newest_first_with_initial_price_row(api, db):
    pid = _seed_three(db)
    resp = _history(api, pid)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    rows = body["data"]
    assert body["pagination"] == {"total": 5, "page": 1, "limit": 10}
    assert [r["kind"] for r in rows] == ["change", "change", "change", "change", "initial"]
    assert [(r["old_price"], r["new_price"]) for r in rows] == [
        (0.0, 121.0), (121.0, 0.0), (110.0, 121.0), (100.0, 110.0), (None, 100.0),
    ]
    assert rows[2]["change_pct"] == 10.0
    assert rows[2]["changed_by"] == "Fake Pricer"
    assert rows[2]["changed_at"].startswith("2026-10-31T04:00:00")
    assert rows[3]["changed_by"] == "AutoCount sync"
    assert rows[1]["change_pct"] == -100.0
    assert rows[0]["change_pct"] is None, "from 0 there is no percentage"
    assert rows[0]["changed_by"] is None and rows[1]["changed_by"] is None, (
        "a non-user, non-integration actor is not named"
    )
    assert rows[4]["change_pct"] is None
    assert rows[4]["changed_by"] == "Fake Pricer"
    assert all(r["id"] for r in rows)


def test_history_initial_price_row_is_a_switch(api, db, monkeypatch):
    from app.services import product_list_price_history_service as svc

    pid = _seed_three(db)
    monkeypatch.setattr(svc, "INCLUDE_INITIAL_PRICE", False)
    body = _history(api, pid).json()
    assert body["pagination"]["total"] == 4
    assert all(r["kind"] == "change" for r in body["data"])


def test_history_pages_on_the_server(api, db):
    pid = _mk_product(db, f"{STEM}-PAGE")
    t0 = datetime(2026, 1, 1)
    for i in range(12):
        _audit(db, pid, old=f"{100 + i}.00", new=f"{101 + i}.00", changed_at=t0 + timedelta(hours=i))
    db.commit()
    page1 = _history(api, pid, page=1, limit=5).json()
    page3 = _history(api, pid, page=3, limit=5).json()
    assert page1["pagination"] == {"total": 12, "page": 1, "limit": 5}
    assert [r["new_price"] for r in page1["data"]] == [112.0, 111.0, 110.0, 109.0, 108.0]
    assert [r["new_price"] for r in page3["data"]] == [102.0, 101.0]

    # Past the last page the window count is gone; the total must still be the real one,
    # or the pagination bar collapses with no way back (review S1).
    past = _history(api, pid, page=99, limit=5).json()
    assert past == {"data": [], "pagination": {"total": 12, "page": 99, "limit": 5}}


@pytest.mark.parametrize(
    "sort,direction,expected_new",
    [
        ("changed_at", "asc", [100.0, 110.0, 121.0, 0.0, 121.0]),
        ("new_price", "desc", [121.0, 121.0, 110.0, 100.0, 0.0]),
        ("old_price", "asc", [None, 110.0, 121.0, 0.0, 121.0]),
        ("change_pct", "desc", [121.0, 110.0, 0.0, 121.0, 100.0]),
        ("changed_by", "asc", [110.0, 121.0, 100.0, 121.0, 0.0]),
    ],
)
def test_history_sorts_every_column_on_the_server(api, db, sort, direction, expected_new):
    """Nulls last in both directions; ties fall back to newest first."""
    pid = _seed_three(db)
    rows = _history(api, pid, sort=sort, dir=direction).json()["data"]
    got = [r["new_price"] for r in rows]
    if sort == "old_price":
        # old_price asc: 0.00, 100, 110, 121, then the initial row's null last.
        assert [r["old_price"] for r in rows] == [0.0, 100.0, 110.0, 121.0, None]
    elif sort == "change_pct":
        # +10.0 (110 -> 121), +10.0 (100 -> 110), -100.0, then the two nulls (newest first).
        assert [r["change_pct"] for r in rows] == [10.0, 10.0, -100.0, None, None]
        assert got == [121.0, 110.0, 0.0, 121.0, 100.0]
    elif sort == "changed_by":
        # "AutoCount sync" < "Fake Pricer" (x2, newest first), then the unnamed (newest first).
        assert [r["changed_by"] for r in rows] == [
            "AutoCount sync", "Fake Pricer", "Fake Pricer", None, None,
        ]
        assert got == [110.0, 121.0, 100.0, 121.0, 0.0]
    else:
        assert got == expected_new


def test_history_unknown_sort_falls_back_to_newest_first(api, db):
    pid = _seed_three(db)
    rows = _history(api, pid, sort="id; DROP TABLE x", dir="sideways").json()["data"]
    assert [r["new_price"] for r in rows][:2] == [121.0, 0.0]


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
    _audit(db, pid, old="10.0", new="10.00")  # same number, different text
    _audit(db, other, old="10.00", new="12.00")  # another product
    _audit(db, pid, old="9.00", new="10.00")
    db.commit()

    rows = _history(api, pid).json()["data"]
    assert [(r["old_price"], r["new_price"]) for r in rows] == [(9.0, 10.0)]


def test_history_empty_for_a_product_with_no_history(api, db):
    pid = _mk_product(db, f"{STEM}-EMPTY")
    db.commit()
    resp = _history(api, pid)
    assert resp.status_code == 200
    assert resp.json() == {"data": [], "pagination": {"total": 0, "page": 1, "limit": 10}}


def test_history_limit_is_bounded(api, db):
    pid = _mk_product(db, f"{STEM}-LIM")
    db.commit()
    from app.schemas.common import MAX_PAGE_LIMIT

    assert _history(api, pid, limit=MAX_PAGE_LIMIT).status_code == 200
    assert _history(api, pid, limit=MAX_PAGE_LIMIT + 1).status_code == 422
    assert _history(api, pid, page=0).status_code == 422


def test_history_requires_the_products_view_grant(api, db, granted):
    slugs, asked = granted
    pid = _mk_product(db, f"{STEM}-PERM")
    _audit(db, pid, old="10.00", new="12.00")
    db.commit()

    assert _history(api, pid).status_code == 200
    assert "master_data.products.view" in asked

    slugs.clear()
    resp = _history(api, pid)
    assert resp.status_code == 403, resp.text


def test_history_by_product_code_reads_that_products_trail(api, db):
    """The gate resolves a code as well as an id (`resolve_identifier`); the trail must be
    read for the RESOLVED product, not the raw path value (security review nit on #2260)."""
    code = f"{STEM}-SKU-{uuid.uuid4().hex[:6]}"
    pid = _mk_product(db, code)
    _audit(db, pid, old="10.00", new="12.00")
    db.commit()
    rows = _history(api, code).json()["data"]
    assert [(r["old_price"], r["new_price"]) for r in rows] == [(10.0, 12.0)]


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
    """End to end: a real ORM create and price edit land in the history, so a rename of the
    audit entity type, action or column key cannot silently empty the lightbox."""
    from app.audit_context import AuditActor, actor_scope
    from app.services.audit_service import register_audit_listeners

    register_audit_listeners()
    staff = _staff(db, name="Fake Real Staff")
    db.commit()
    with actor_scope(AuditActor(actor_type="user", user_id=staff.id, real_user_id=staff.id), db=db):
        pid = _mk_product(db, f"{STEM}-REAL", price="100.00", keep_trail=True)
        db.commit()
        p = db.get(Product, pid)
        p.list_price = Decimal("125.00")
        db.commit()

    rows = _history(api, pid).json()["data"]
    assert [(r["kind"], r["old_price"], r["new_price"]) for r in rows] == [
        ("change", 100.0, 125.0), ("initial", None, 100.0),
    ]
    assert rows[0]["change_pct"] == 25.0
    assert rows[0]["changed_by"] == "Fake Real Staff"


# --------------------------------------------------------------------------- migration (Q1 + Q4)


def _migration():
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parent.parent / "alembic" / "versions" / "lpcui_0001_list_price_changed.py"
    spec = importlib.util.spec_from_file_location("_lpcui_0001", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_backfill_stamps_latest_audited_change_only_where_unset_and_not_pending(db):
    t0 = datetime(2026, 6, 1, 3, 0)
    changed = _mk_product(db, f"{STEM}-BF-CHANGED", price="12.00")
    _audit(db, changed, old="10.00", new="11.00", changed_at=t0)
    _audit(db, changed, old="11.00", new="12.00", changed_at=t0 + timedelta(days=5))
    _audit(db, changed, old=None, new=None, extra_new={"product_name": "later rename"},
           changed_at=t0 + timedelta(days=9))

    already = _mk_product(db, f"{STEM}-BF-ALREADY", price="12.00", changed_at=datetime(2026, 11, 8, 1, 0))
    _audit(db, already, old="10.00", new="12.00", changed_at=t0)

    pending = _mk_product(db, f"{STEM}-BF-PENDING", price="15.00")
    db.get(Product, pending).list_price_notified = Decimal("12.00")  # changed, not yet reported
    _audit(db, pending, old="12.00", new="15.00", changed_at=t0)

    noop = _mk_product(db, f"{STEM}-BF-NOOP", price="10.00")
    _audit(db, noop, old="10.00", new="10.00", changed_at=t0)

    created_only = _mk_product(db, f"{STEM}-BF-CREATED")
    _create_row(db, created_only, price="10.00", changed_at=t0)
    db.commit()

    _migration().backfill_changed_at(db.connection())
    db.expire_all()

    assert db.get(Product, changed).list_price_notified_at == t0 + timedelta(days=5)
    assert db.get(Product, already).list_price_notified_at == datetime(2026, 11, 8, 1, 0)
    assert db.get(Product, pending).list_price_notified_at is None
    assert db.get(Product, noop).list_price_notified_at is None
    assert db.get(Product, created_only).list_price_notified_at is None


def test_export_catalog_row_seeds_once_and_exports_the_malaysia_date(db):
    from tests.test_product_discontinued_at_list import _ensure_products_discontinued_at_field

    _ensure_products_discontinued_at_field(db)  # the products resource row
    m = _migration()
    assert m.seed(db.connection()) is True
    assert m.seed(db.connection()) is False, "idempotent"

    from app.models.list_query_metadata import ListQueryField

    field = (
        db.query(ListQueryField)
        .join(ListQueryField.resource)
        .filter_by(resource_key="products")
        .filter(ListQueryField.field_key == "list_price_changed_at")
        .one()
    )
    assert field.label == "List price changed at"
    assert field.export_column_name == "List price changed at"
    assert field.data_type == "date"
    assert field.compile_key == "product.list_price_notified_at"
    assert field.filterable is False and field.exportable is True

    p_in = _mk_product(db, f"{STEM}-EXPV-IN", changed_at=datetime(2026, 11, 7, 16, 30))  # 8 Nov MYT
    p_null = _mk_product(db, f"{STEM}-EXPV-NULL")
    db.commit()
    rows = ListQueryExportService(db).export_rows(
        ListExportRequest(
            resource="products",
            fields=[{"field_key": "list_price_changed_at"}],
            record_ids=[p_in, p_null],
        )
    )
    assert sorted(r["List price changed at"] or "" for r in rows) == ["", "2026-11-08"]


def test_bootstrap_replays_the_catalog_seed():
    import inspect

    import scripts.bootstrap_env as boot

    src = inspect.getsource(boot.seed_products_list_query_fields)
    assert "lpcui_0001_list_price_changed.py" in src
