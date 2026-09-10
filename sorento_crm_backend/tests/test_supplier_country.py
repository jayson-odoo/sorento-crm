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

        rows = {
            code: db.execute(
                text("SELECT country_id FROM suppliers WHERE supplier_code = :c"), {"c": code}
            ).scalar()
            for code in (by_name, by_code, unresolved)
        }
        assert rows[by_name] == country.id
        assert rows[by_code] == country.id
        assert rows[unresolved] is None

        unresolved_record = next(r for r in result.records if r.source_ref == f"DK-{unresolved}")
        assert "country" in " ".join(unresolved_record.warnings).lower()
