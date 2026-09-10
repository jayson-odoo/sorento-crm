"""Supplier country FK (S2, PLAN-local-supplier-oi-routing.md, UAC AC-2.8 - AC-2.10).

RED for Phase 2: `suppliers.country_id` does not exist on the current model (only the
free-text `country` column does), `SupplierCreate`/`SupplierResponse` do not carry
`country_id`/`country_code`/`country_name`, and `_supplier_columns` in
`master_ingest_service.py` still passes `country` straight through as free text. Every
assertion below fails against TODAY's code for that reason - a plain `AttributeError` /
`KeyError` / equality mismatch, never a fixture bug.

Contract this file drives:

* `app.models.procurement.Supplier.country_id` (uuid FK `countries.id`, ON DELETE
  RESTRICT, nullable, indexed) replaces `country`. A `country_code` / `country_name`
  property (or hybrid) on the model, so `SupplierResponse.model_validate(supplier,
  from_attributes=True)` - the exact mechanism `GET .../suppliers/select` already uses -
  picks them up with no route-level rebuild.
* `app.schemas.procurement.SupplierCreate`/`SupplierResponse` carry `country_id` /
  `country_code` / `country_name`. `SupplierService.create_supplier` raises
  `AppException(422, ...)` for an unresolvable `country_id`.
* `alembic/versions/511_supplier_country_id.py` exposes `_update_supplier_country_field
  (bind)` that repoints the `list_query_fields` row (`resource_key='suppliers',
  field_key='country'`) at `country.name` instead of `supplier.country` - named after the
  same `apply(bind)`-on-a-rolled-back-connection pattern as
  `alembic/versions/445_autocount_grant_sweep.py`, since `list_query_fields` is itself
  migration-seeded data a blank scratch schema never sees.
* `app.services.master_ingest_service._supplier_columns` resolves a `country` payload
  value (name or 2-letter code, case-insensitive) to `country_id`; unresolved -> a
  `"country_unresolved"` warning and a null field, row still imports.

Note for the coder: `tests/test_ingest_parity_s0_masters.py::
TestAcP04SupplierAddressBlockAndDeprecatedFields::
test_supplier_contact_and_address_fields_land` asserts `suppliers.country` still holds the
literal text `"Malaysia"` via raw SQL - that assertion is retired by this slice (the column
is dropped) and needs updating alongside the S2 implementation, not left red.
"""
from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy import text

from app.services.error_handler import AppException
from tests._pg_fixture import blank_session, unique_code

MARKER = "ZZTSUPCTY"


def _u() -> str:
    return str(uuid.uuid4())


# --------------------------------------------------------------------------- #
# AC-2.8: country_id column (FK RESTRICT) replaces the free-text country column;
# the list-query metadata field points at the joined name.
# --------------------------------------------------------------------------- #


def test_country_id_column_and_text_column_dropped():
    from app.models.procurement import Supplier

    columns = Supplier.__table__.columns
    assert "country" not in columns, "the free-text column must be dropped"
    assert "country_id" in columns, "suppliers.country_id must exist"

    country_id_col = columns["country_id"]
    assert country_id_col.nullable is True
    fks = list(country_id_col.foreign_keys)
    assert fks, "country_id must carry a foreign key to countries.id"
    fk = fks[0]
    assert fk.column.table.name == "countries"
    assert (fk.ondelete or "").upper() == "RESTRICT"


def test_list_query_metadata_field_points_at_joined_name():
    """`list_query_fields` is migration-seeded, real data on the live database - not
    something `blank_session`'s `create_all` reproduces (same gap AC-2.1/AC-2.6 hit for
    `countries`/permissions). Exercised against the live table inside a rolled-back
    transaction, same as `tests/test_migration_445_grant_sweep.py`.
    """
    import importlib.util
    from pathlib import Path

    from app.database import engine

    migration_path = (
        Path(__file__).resolve().parent.parent / "alembic" / "versions"
        / "511_supplier_country_id.py"
    )
    spec = importlib.util.spec_from_file_location("m511", migration_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    connection = engine.connect()
    transaction = connection.begin()
    try:
        _ensure_suppliers_list_query_metadata(connection)

        before = connection.execute(
            text(
                "SELECT compile_key FROM list_query_fields f "
                "JOIN list_query_resources r ON r.id = f.resource_id "
                "WHERE r.resource_key = 'suppliers' AND f.field_key = 'country'"
            )
        ).scalar()
        assert before is not None, "seed row missing - cannot exercise the update"

        module._update_supplier_country_field(connection)

        after = connection.execute(
            text(
                "SELECT compile_key FROM list_query_fields f "
                "JOIN list_query_resources r ON r.id = f.resource_id "
                "WHERE r.resource_key = 'suppliers' AND f.field_key = 'country'"
            )
        ).scalar()
        assert after == "country.name"
    finally:
        transaction.rollback()
        connection.close()


# --------------------------------------------------------------------------- #
# AC-2.9: supplier create/update accept country_id; list/detail/select carry
# country_id, country_code, country_name; unknown id is 422.
# --------------------------------------------------------------------------- #


def test_supplier_payloads_carry_country_fields():
    from app.models.country import Country
    from app.schemas.procurement import SupplierCreate, SupplierResponse
    from app.services.procurement_service import SupplierService

    with blank_session() as db:
        country = Country(id=_u(), code="MY", name="Malaysia")
        db.add(country)
        db.flush()

        svc = SupplierService(db)
        created = svc.create_supplier(
            SupplierCreate(
                supplier_code=unique_code(MARKER)[:30],
                supplier_name=f"{MARKER} Sdn Bhd",
                country_id=country.id,
            )
        )
        assert created.country_id == country.id

        created_response = SupplierResponse.model_validate(created)
        assert created_response.country_id == country.id
        assert created_response.country_code == "MY"
        assert created_response.country_name == "Malaysia"

        listed = svc.list_suppliers(query=created.supplier_code)
        row = listed["data"][0]
        row_response = SupplierResponse.model_validate(row)
        assert row_response.country_code == "MY"
        assert row_response.country_name == "Malaysia"

        detail = svc.get_supplier(created.id)
        detail_response = SupplierResponse.model_validate(detail)
        assert detail_response.country_code == "MY"
        assert detail_response.country_name == "Malaysia"


def test_unknown_country_id_is_422():
    from app.schemas.procurement import SupplierCreate
    from app.services.procurement_service import SupplierService

    with blank_session() as db:
        with pytest.raises(AppException) as exc:
            SupplierService(db).create_supplier(
                SupplierCreate(
                    supplier_code=unique_code(MARKER)[:30],
                    supplier_name=f"{MARKER} unknown country",
                    country_id=str(uuid.uuid4()),
                )
            )
        assert exc.value.status_code == 422


# --------------------------------------------------------------------------- #
# AC-2.10: master ingest resolves a country name or code, case-insensitively;
# an unresolvable value warns and leaves the field null, and the row still imports.
# --------------------------------------------------------------------------- #


def test_ingest_resolves_name_or_code():
    from app.models.country import Country
    from app.services.company_scope import DEFAULT_COMPANY_ID, register_company_scope_listeners
    from app.services.master_ingest_service import IngestOutcome, MasterIngestService

    register_company_scope_listeners()

    with blank_session() as db:
        country = Country(id=_u(), code="MY", name="Malaysia")
        db.add(country)
        db.flush()

        svc = MasterIngestService(db, integration_id=None, company_id=DEFAULT_COMPANY_ID)
        by_name = unique_code(f"{MARKER}NAME")[:30]
        by_code = unique_code(f"{MARKER}CODE")[:30]
        unresolved = unique_code(f"{MARKER}UNK")[:30]
        result = svc.ingest(
            "suppliers",
            [
                {"source_ref": f"DK-{by_name}", "code": by_name, "name": "Name Match Sdn Bhd", "country": "Malaysia"},
                {"source_ref": f"DK-{by_code}", "code": by_code, "name": "Code Match Sdn Bhd", "country": "my"},
                {"source_ref": f"DK-{unresolved}", "code": unresolved, "name": "Nowhere Sdn Bhd", "country": "Atlantis"},
            ],
        )

        for record in result.records:
            assert record.outcome != IngestOutcome.FAILED, record.errors
        assert result.created == 3

        # ::text, the suite's idiom (test_plan_row_decision.py, test_m4_cash.py): psycopg2
        # returns a raw uuid column as `uuid.UUID`, which never equals the ORM's `str` id.
        rows = {
            code: db.execute(
                text("SELECT country_id::text FROM suppliers WHERE supplier_code = :c"),
                {"c": code},
            ).scalar()
            for code in (by_name, by_code, unresolved)
        }
        assert rows[by_name] == str(country.id)
        assert rows[by_code] == str(country.id)
        assert rows[unresolved] is None

        unresolved_record = next(r for r in result.records if r.source_ref == f"DK-{unresolved}")
        assert "country" in " ".join(unresolved_record.warnings).lower()


# --------------------------------------------------------------------------- #
# Captain's fix-round adjudication (item 3): the supplier list/search/export surfaces
# reading the joined country name, plus a non-UUID-shaped `country_id` at the schema
# boundary. `list_query_resources`/`list_query_fields`/`countries` are migration-seeded
# data a blank scratch schema never sees (same gap AC-2.1/AC-2.6 hit) - a real
# connection/session, rolled back, same substrate `test_list_query_metadata_field_
# points_at_joined_name` above already uses.
# --------------------------------------------------------------------------- #


@pytest.fixture
def api(monkeypatch):
    from fastapi.testclient import TestClient

    from app.database import get_db
    from app.dependencies import get_current_user, get_current_user_or_api_key
    from app.main import app
    from app.services.company_scope_resolver import apply_company_scope
    from app.services.user_service import UserPermissionService
    from tests._pg_fixture import pg_session

    with pg_session() as db:
        actor = {"id": "zzt-supcty-user", "email": "zzt-supcty@zzt.test", "role": "user"}
        monkeypatch.setattr(
            UserPermissionService, "check_user_has_permission", lambda self, uid, slug: True
        )
        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[get_current_user] = lambda: dict(actor)
        app.dependency_overrides[get_current_user_or_api_key] = lambda: dict(actor)
        app.dependency_overrides[apply_company_scope] = lambda: None
        client = TestClient(app)
        try:
            yield client, db
        finally:
            app.dependency_overrides.clear()


def _ensure_country(db, code: str, name: str):
    """Get-or-create the ISO row this test needs, rather than assuming the `510_
    countries` migration seed already ran: CI's database is `scripts/bootstrap_env.py`
    (create_all from the ORM models), never `alembic upgrade head`, so it carries the
    `countries` TABLE but none of the 249 seeded ROWS - the same "seeding migration's
    own data is invisible to a from-zero database" gap `test_countries.py` and
    `test_migration_445_grant_sweep.py` already work around. Locally (a real database,
    migrated by hand) the row already exists and this is a plain lookup."""
    from app.models.country import Country

    existing = db.query(Country).filter(Country.code == code).first()
    if existing is not None:
        return existing
    row = Country(id=_u(), code=code, name=name)
    db.add(row)
    db.flush()
    return row


def _two_countried_suppliers(db):
    from app.models.procurement import Supplier

    my = _ensure_country(db, "MY", "Malaysia")
    cn = _ensure_country(db, "CN", "China")
    my_supplier = Supplier(
        id=_u(), supplier_code=unique_code(MARKER)[:30],
        supplier_name=f"{MARKER} Malaysia Sdn Bhd", country_id=my.id,
    )
    cn_supplier = Supplier(
        id=_u(), supplier_code=unique_code(MARKER)[:30],
        supplier_name=f"{MARKER} China Co", country_id=cn.id,
    )
    db.add_all([my_supplier, cn_supplier])
    db.commit()
    return my_supplier, cn_supplier


#: The six `suppliers` fields migration `101_list_query_metadata` seeds, `country`
#: already carrying `511_supplier_country_id`'s `country.name` compile_key (the
#: CURRENT real shape, not the pre-511 transient one) - `str_ops`/`bool_ops` copied
#: verbatim from `101`'s own module-level lists.
_STR_OPS = json.dumps(["eq", "ne", "contains", "starts_with", "in", "is_null"])
_BOOL_OPS = json.dumps(["eq", "is_null"])
_SUPPLIER_FIELDS = (
    # (field_key, label, data_type, compile_key, allowed_operators_json, sort_order)
    ("supplier_code", "Supplier code", "string", "supplier.supplier_code", _STR_OPS, 10),
    ("supplier_name", "Supplier name", "string", "supplier.supplier_name", _STR_OPS, 20),
    ("is_active", "Active", "boolean", "supplier.is_active", _BOOL_OPS, 30),
    ("city", "City", "string", "supplier.city", _STR_OPS, 40),
    ("country", "Country", "string", "country.name", _STR_OPS, 50),
    ("email", "Email", "string", "supplier.email", _STR_OPS, 60),
)


def _ensure_suppliers_list_query_metadata(conn) -> None:
    """Get-or-create the `suppliers` `list_query_resources`/`list_query_fields` rows
    (migrations `101_list_query_metadata` + `511_supplier_country_id`'s compile_key
    repoint), for the same `bootstrap_env` reason `_ensure_country` above states: CI's
    database carries the two TABLES (`create_all`) but none of the seeded ROWS, so
    `ListQueryMetadataService.fields_by_key("suppliers")` returns nothing there and
    every advanced-search / export call over `country` (or any other supplier field)
    raises before this test's own assertion gets a chance to run. `conn` may be either
    a raw `Connection` (`test_list_query_metadata_field_points_at_joined_name`'s own
    `engine.connect()`) or an ORM `Session` (`pg_session`) - both support `execute
    (text(...))` identically, so one helper serves both call shapes. Idempotent
    (`WHERE NOT EXISTS`), so a real, already-migrated database is a no-op.
    """
    conn.execute(
        text(
            """
            INSERT INTO list_query_resources (id, resource_key, display_name, description, is_active)
            SELECT gen_random_uuid(), 'suppliers', 'Suppliers',
                   'Supplier list filter/export metadata', true
            WHERE NOT EXISTS (
                SELECT 1 FROM list_query_resources WHERE resource_key = 'suppliers'
            )
            """
        )
    )
    for field_key, label, data_type, compile_key, ops_json, sort_order in _SUPPLIER_FIELDS:
        conn.execute(
            text(
                """
                INSERT INTO list_query_fields (
                    id, resource_id, field_key, label, data_type, compile_key,
                    allowed_operators, filterable, exportable, is_line_field, sort_order
                )
                SELECT gen_random_uuid(), r.id, :fk, :label, :dtype, :ckey,
                       CAST(:ops AS jsonb), true, true, false, :so
                FROM list_query_resources r
                WHERE r.resource_key = 'suppliers'
                  AND NOT EXISTS (
                      SELECT 1 FROM list_query_fields f
                      WHERE f.resource_id = r.id AND f.field_key = :fk
                  )
                """
            ),
            {
                "fk": field_key, "label": label, "dtype": data_type, "ckey": compile_key,
                "ops": ops_json, "so": sort_order,
            },
        )


def test_advanced_search_country_contains_matches_by_joined_name(api):
    """(a) `POST /api/v1/list-query/search`, resource `suppliers`, a `contains` filter on
    `field_key: "country"` matches the JOINED `countries.name`, not `suppliers.country_id`
    (`_compile_supplier_country_predicate`). `FilterGroup.op` is required by the schema
    (`Literal["and", "or"]`) even for a single child, so it is stated explicitly here.

    A SECOND child, ANDed, on `supplier_name contains MARKER`: the live database is a prod
    copy carrying hundreds of real Malaysia-based suppliers after the backfill script ran,
    so a bare `country contains Malay` match returns many more rows than the default page
    size and the seeded `my_supplier` is not guaranteed to be on it (the same "never assume
    a real table is small" lesson `test_suppliers_list_sorts_by_joined_country_name`
    already applies via its own `query=MARKER` scoping)."""
    client, db = api
    _ensure_suppliers_list_query_metadata(db)
    my_supplier, cn_supplier = _two_countried_suppliers(db)

    resp = client.post(
        "/api/v1/list-query/search",
        json={
            "resource": "suppliers",
            "filter": {
                "op": "and",
                "children": [
                    {"field_key": "country", "op": "contains", "value": "Malay"},
                    {"field_key": "supplier_name", "op": "contains", "value": MARKER},
                ],
            },
        },
    )
    assert resp.status_code == 200, resp.text
    ids = {row["id"] for row in resp.json()["data"]}
    assert my_supplier.id in ids
    assert cn_supplier.id not in ids


def test_suppliers_list_sorts_by_joined_country_name(api):
    """(b) `GET /api/v1/procurement/suppliers?sort=country_name&dir=asc|desc` orders by
    the joined `countries.name` (`SupplierService._build_list_query`'s `country_name` ->
    `Country.name` sort map entry), never by the FK id or nothing at all."""
    client, db = api
    my_supplier, cn_supplier = _two_countried_suppliers(db)

    # `query=MARKER` scopes the page to these two rows: the live database is a prod
    # copy carrying hundreds of Malaysia-based suppliers already, so an unscoped
    # `limit` could paginate either of ours out before an ORDER BY tie-breaker ever
    # gets a say (`LESSONS-LEARNT.md`: never assume a real table is small).
    asc = client.get(
        "/api/v1/procurement/suppliers",
        params={"sort": "country_name", "dir": "asc", "limit": 200, "query": MARKER},
    )
    assert asc.status_code == 200, asc.text
    asc_ids = [row["id"] for row in asc.json()["data"]]
    assert asc_ids.index(cn_supplier.id) < asc_ids.index(my_supplier.id), (
        "China before Malaysia, ascending by country name"
    )

    desc = client.get(
        "/api/v1/procurement/suppliers",
        params={"sort": "country_name", "dir": "desc", "limit": 200, "query": MARKER},
    )
    assert desc.status_code == 200, desc.text
    desc_ids = [row["id"] for row in desc.json()["data"]]
    assert desc_ids.index(my_supplier.id) < desc_ids.index(cn_supplier.id), (
        "descending reverses the order"
    )


def test_export_suppliers_emits_country_name_under_country_column():
    """(c) `ListQueryExportService._export_suppliers` (`_value_from_supplier`, compile_key
    `country.name`) emits the country NAME - never the id, never the raw FK column - under
    the `country` export column."""
    from app.models.list_query_metadata import ListQueryField
    from app.schemas.list_query import ListExportRequest
    from app.services.list_query_export_service import ListQueryExportService
    from tests._pg_fixture import pg_session

    with pg_session() as db:
        _ensure_suppliers_list_query_metadata(db)
        my_supplier, cn_supplier = _two_countried_suppliers(db)

        field = (
            db.query(ListQueryField)
            .join(ListQueryField.resource)
            .filter_by(resource_key="suppliers")
            .filter(ListQueryField.field_key == "country")
            .one()
        )
        assert field.compile_key == "country.name"

        rows = ListQueryExportService(db)._export_suppliers(
            [field], None,
            ListExportRequest(
                resource="suppliers", fields=[{"field_key": "country"}],
                record_ids=[my_supplier.id, cn_supplier.id],
            ),
        )
        values = {row["country"] for row in rows}
        assert values == {"Malaysia", "China"}


def test_create_supplier_with_non_uuid_country_id_is_422(api):
    """(d) A `country_id` that is not even UUID-shaped ("abc") is a 422 at the schema
    boundary (`_validate_uuid_format`, N2), never a 500 from a query that could not cast
    it to `uuid`."""
    client, _db = api
    resp = client.post(
        "/api/v1/procurement/suppliers",
        json={
            "supplier_code": unique_code(MARKER)[:30],
            "supplier_name": f"{MARKER} bad country",
            "country_id": "abc",
        },
    )
    assert resp.status_code == 422, resp.text
