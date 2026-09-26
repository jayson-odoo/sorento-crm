"""S0 - the Brand specification is removed (#1286, D1-D4).

Contract: documentation/plans/products/CONTRACT-product-specs-rule-engine.md,
UAC: documentation/plans/products/product-specs-non-technical-acceptance-criteria.md
(AC-S0.1, AC-S0.3, AC-S0.4, AC-S0.5, AC-S0.6).

The migration test (AC-S0.1) runs raw SQL against `product_spec_registry`,
`product_specifications`, `product_spec_exceptions` and `product_spec_verifications`
inside a rolled-back `pg_session`, mirroring `tests/test_migration_450_spec_rules_backfill.py`
(LESSONS: migration tests via upgrade() in a rolled-back pg_session). Every other test
here seeds its own chain in `blank_session` with a ZZT marker, per LESSONS (CI's DB has
no data; never borrow existing rows).
"""
from __future__ import annotations

import importlib.util
import json
import uuid
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import text

from app.models.product import Brand, Product, ProductCategory, UnitOfMeasure
from app.services.product_spec_derivation import derive_for_code
from app.services.product_spec_registry import seed_spec_registry
from app.services.product_spec_rendering import render_spec_sentence
from app.services.product_spec_search import (
    filter_specs,
    resolve_terms_to_specs,
    search_specs,
)
from tests._pg_fixture import pg_session, blank_session, unique_code

_MIGRATION_PATH = (
    Path(__file__).resolve().parent.parent
    / "alembic"
    / "versions"
    / "spec_0001_drop_brand_spec.py"
)


# --------------------------------------------------------------------------- #
# AC-S0.1 - the migration
# --------------------------------------------------------------------------- #
def _migration_module():
    spec = importlib.util.spec_from_file_location("zzt_migration_spec_0001", _MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(db, direction: str = "upgrade") -> None:
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    module = _migration_module()
    context = MigrationContext.configure(connection=db.connection())
    with Operations.context(context):
        getattr(module, direction)()


def _ensure_brand_registry_row(db) -> None:
    """The `brand` row, however the live DB already seeded it."""
    existing = db.execute(
        text("SELECT id FROM product_spec_registry WHERE spec_key = 'brand'")
    ).first()
    if existing is None:
        db.execute(
            text(
                "INSERT INTO product_spec_registry"
                " (id, spec_key, label, data_type, excluded_values, user_values,"
                "  value_labels, suppressed_values, user_synonyms)"
                " VALUES (:id, 'brand', 'Brand', 'enum', CAST(:excluded AS jsonb),"
                "  CAST(:user_values AS jsonb), CAST(:value_labels AS jsonb),"
                "  CAST(:suppressed AS jsonb), CAST(:user_synonyms AS jsonb))"
            ),
            {
                "id": str(uuid.uuid4()),
                "excluded": json.dumps(["OTHERS", "NO LOGO"]),
                "user_values": json.dumps(["SHADOW BRAND"]),
                "value_labels": json.dumps({}),
                "suppressed": json.dumps([]),
                "user_synonyms": json.dumps({}),
            },
        )


_SORENTO_COMPANY_ID = "00000000-0000-0000-0000-000000000001"


def _seed_zzt_product_with_brand_spec(db, code: str) -> None:
    category_id = str(uuid.uuid4())
    uom_id = str(uuid.uuid4())
    db.execute(
        text(
            "INSERT INTO product_categories (id, company_id, category_code, category_name)"
            " VALUES (:id, :cid, :code, :code)"
        ),
        {"id": category_id, "cid": _SORENTO_COMPANY_ID, "code": unique_code("CAT")},
    )
    db.execute(
        text(
            "INSERT INTO units_of_measure (id, company_id, uom_code, uom_name)"
            " VALUES (:id, :cid, :code, :code)"
        ),
        {"id": uom_id, "cid": _SORENTO_COMPANY_ID, "code": unique_code("UOM")},
    )
    db.execute(
        text(
            "INSERT INTO products"
            " (id, company_id, product_code, product_name, description, category_id,"
            "  base_uom_id, list_price, is_active, is_discontinued)"
            " VALUES (:id, :cid, :code, :code, :code, :category_id, :uom_id, 1.0, true, false)"
        ),
        {
            "id": str(uuid.uuid4()),
            "cid": _SORENTO_COMPANY_ID,
            "code": code,
            "category_id": category_id,
            "uom_id": uom_id,
        },
    )
    product_id = db.execute(
        text("SELECT id FROM products WHERE product_code = :code"), {"code": code}
    ).scalar()
    db.execute(
        text(
            "INSERT INTO product_specifications (id, product_id, values, provenance)"
            " VALUES (:id, :pid, CAST(:values AS jsonb), CAST(:provenance AS jsonb))"
        ),
        {
            "id": str(uuid.uuid4()),
            "pid": product_id,
            "values": json.dumps({"brand": {"value": "OTHERS"}, "material": {"value": "brass"}}),
            "provenance": json.dumps(
                {
                    "brand": {"source": "human", "confidence": 1.0, "evidence": "brand=OTHERS"},
                    "material": {"source": "derived", "confidence": 1.0, "evidence": "BRASS"},
                }
            ),
        },
    )
    db.execute(
        text(
            "INSERT INTO product_spec_exceptions (id, product_code, spec_key, reason)"
            " VALUES (:id, :code, 'brand', 'company_copies_disagree')"
        ),
        {"id": str(uuid.uuid4()), "code": code},
    )
    db.execute(
        text(
            "INSERT INTO product_spec_verifications"
            " (id, product_code, party, values_hash, invalidated_diff)"
            " VALUES (:id, :code, 'internal', 'deadbeef', CAST(:diff AS jsonb))"
        ),
        {
            "id": str(uuid.uuid4()),
            "code": code,
            "diff": json.dumps(
                {
                    "changed": [
                        {"spec_key": "brand", "was": "OTHERS", "now": "SORENTO"},
                        {"spec_key": "material", "was": "brass", "now": "steel"},
                    ]
                }
            ),
        },
    )
    return product_id


def test_ac_s0_1_migration_removes_the_brand_row_and_every_mention(pg_session=pg_session):
    with pg_session() as db:
        _ensure_brand_registry_row(db)
        code = unique_code("BRANDMIG")
        _seed_zzt_product_with_brand_spec(db, code)
        db.flush()

        _run(db)

        assert (
            db.execute(
                text("SELECT 1 FROM product_spec_registry WHERE spec_key = 'brand'")
            ).first()
            is None
        ), "the brand registry row must be gone"

        spec_row = db.execute(
            text(
                "SELECT values, provenance FROM product_specifications ps"
                " JOIN products p ON p.id = ps.product_id WHERE p.product_code = :code"
            ),
            {"code": code},
        ).first()
        values, provenance = spec_row
        assert "brand" not in values, "no product's stored values may mention brand"
        assert "brand" not in provenance, "no product's provenance may mention brand"
        assert values.get("material") == {"value": "brass"}, "an unrelated key must survive untouched"

        open_exception = db.execute(
            text(
                "SELECT 1 FROM product_spec_exceptions WHERE product_code = :code"
                " AND spec_key = 'brand' AND resolved_at IS NULL"
            ),
            {"code": code},
        ).first()
        assert open_exception is None, "an open brand exception must be deleted"

        diff = db.execute(
            text(
                "SELECT invalidated_diff FROM product_spec_verifications WHERE product_code = :code"
            ),
            {"code": code},
        ).scalar()
        changed_keys = {entry["spec_key"] for entry in (diff or {}).get("changed", [])}
        assert "brand" not in changed_keys, "a verification stamp's diff must not mention brand"
        assert "material" in changed_keys, "an unrelated diff entry must survive"

        columns = {
            row[0]
            for row in db.execute(
                text(
                    "SELECT column_name FROM information_schema.columns"
                    " WHERE table_name = 'brands'"
                )
            ).all()
        }
        assert "is_searchable" in columns, "brands.is_searchable must exist after the migration"

        searchable = dict(
            db.execute(
                text("SELECT brand_name, is_searchable FROM brands WHERE UPPER(brand_name) IN ('OTHERS', 'NO LOGO')")
            ).all()
        )
        for name, flag in searchable.items():
            assert flag is False, f"{name} must be seeded not-searchable"

        # Idempotent: running upgrade again on an already-migrated database is a no-op,
        # not an error.
        _run(db)
        assert (
            db.execute(
                text("SELECT 1 FROM product_spec_registry WHERE spec_key = 'brand'")
            ).first()
            is None
        )


# --------------------------------------------------------------------------- #
# AC-S0.3 - search binds and ranks on the product's own brand field
# --------------------------------------------------------------------------- #
@pytest.fixture
def search_db():
    with blank_session() as s:
        cat = ProductCategory(id=str(uuid.uuid4()), category_code="ZZT-KS", category_name="ZZT-KS")
        uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code="ZZT-PCS", uom_name="Piece")
        house = Brand(id=str(uuid.uuid4()), brand_code="ZZT-SRT", brand_name="SORENTO")
        rival = Brand(id=str(uuid.uuid4()), brand_code="ZZT-BRV", brand_name="BRAVAT")
        others = Brand(
            id=str(uuid.uuid4()),
            brand_code="ZZT-OTH",
            brand_name="OTHERS",
            is_searchable=False,
        )
        no_logo = Brand(
            id=str(uuid.uuid4()),
            brand_code="ZZT-NLG",
            brand_name="NO LOGO",
            is_searchable=False,
        )
        s.add_all([cat, uom, house, rival, others, no_logo])
        s.flush()
        seed_spec_registry(s)
        s.info["refs"] = {
            "cat": cat.id,
            "uom": uom.id,
            "house": house.id,
            "rival": rival.id,
            "others": others.id,
            "no_logo": no_logo.id,
        }
        yield s


def _product(db, code, description, *, brand=None):
    refs = db.info["refs"]
    row = Product(
        id=str(uuid.uuid4()),
        product_code=code,
        product_name=code,
        description=description,
        category_id=refs["cat"],
        base_uom_id=refs["uom"],
        list_price=Decimal("1.00"),
        brand_id=refs[brand] if brand else None,
    )
    db.add(row)
    db.flush()
    derive_for_code(db, code)
    return row


def test_ac_s0_3_resolve_terms_binds_the_named_brand(search_db):
    resolved = resolve_terms_to_specs(search_db, ["sorento", "kitchen", "sink"])
    assert {"key": "brand", "value": "SORENTO"} in resolved


def test_ac_s0_3_search_ranks_the_matching_brand_id_above_another(search_db):
    code_a = unique_code("BRANDA")
    code_b = unique_code("BRANDB")
    _product(search_db, code_a, "STAINLESS STEEL KITCHEN SINK", brand="house")
    _product(search_db, code_b, "STAINLESS STEEL KITCHEN SINK", brand="rival")
    search_db.flush()

    result = search_specs(search_db, free_terms=["sorento", "kitchen", "sink"])
    ranked_codes = [row["product_code"] for row in result["candidates"]]
    assert code_a in ranked_codes and code_b in ranked_codes
    assert ranked_codes.index(code_a) < ranked_codes.index(code_b), (
        "the product whose brand_id names the asked-for brand must rank above an "
        "otherwise identical product with another brand"
    )
    winner = next(row for row in result["candidates"] if row["product_code"] == code_a)
    assert "brand" in winner.get("matched_specs", []), "brand must appear in matched_specs"


def test_ac_s0_3_filter_specs_clause_selects_by_brand_id(search_db):
    code_a = unique_code("FILTA")
    code_b = unique_code("FILTB")
    _product(search_db, code_a, "STAINLESS STEEL KITCHEN SINK", brand="house")
    _product(search_db, code_b, "STAINLESS STEEL KITCHEN SINK", brand="rival")
    search_db.flush()

    from app.models.product import Product as ProductModel
    from app.models.product_spec import ProductSpecifications

    result = filter_specs(search_db, specs=[{"key": "brand", "value": "SORENTO"}])
    clause = result["clause"]
    assert clause is not None

    rows = (
        search_db.query(ProductSpecifications)
        .join(ProductModel, ProductModel.id == ProductSpecifications.product_id)
        .filter(clause)
        .all()
    )
    matched_codes = {
        search_db.query(ProductModel.product_code)
        .filter(ProductModel.id == row.product_id)
        .scalar()
        for row in rows
    }
    assert code_a in matched_codes
    assert code_b not in matched_codes


# --------------------------------------------------------------------------- #
# AC-S0.4 - is_searchable gates a brand word; "no logo" still binds in full
# --------------------------------------------------------------------------- #
def test_ac_s0_4_a_single_generic_word_never_binds_a_non_searchable_brand(search_db):
    resolved = resolve_terms_to_specs(search_db, ["others", "kitchen", "sink"])
    assert not any(entry["key"] == "brand" and entry["value"] == "OTHERS" for entry in resolved)


def test_ac_s0_4_no_logo_still_binds_on_the_full_phrase(search_db):
    resolved = resolve_terms_to_specs(search_db, ["no", "logo", "kitchen", "sink"])
    assert {"key": "brand", "value": "NO LOGO"} in resolved


def test_ac_s0_4_vocabulary_offers_only_searchable_brand_names(search_db):
    from app.services.product_spec_understanding import _vocabulary

    described, _index, _open_values = _vocabulary(search_db)
    brand_entry = next((entry for entry in described if entry["spec_key"] == "brand"), None)
    assert brand_entry is not None, "a synthetic brand entry must be offered to the model"
    offered = set(brand_entry.get("allowed_values", []))
    assert "SORENTO" in offered
    assert "BRAVAT" in offered
    assert "OTHERS" not in offered
    assert "NO LOGO" not in offered


# --------------------------------------------------------------------------- #
# AC-S0.5 - the customer sentence leads with the product's brand field
# --------------------------------------------------------------------------- #
def test_ac_s0_5_render_spec_sentence_leads_with_the_brand_argument():
    sentence = render_spec_sentence({"class": {"value": "kitchen_sink"}}, brand="SORENTO")
    assert sentence is not None
    assert sentence.startswith("Sorento kitchen sink")


def test_ac_s0_5_derive_for_code_still_renders_the_brand_lead(search_db):
    code = unique_code("BRANDLEAD")
    _product(search_db, code, "STAINLESS STEEL KITCHEN SINK", brand="house")
    search_db.flush()

    from app.models.product_spec import ProductSpecifications

    spec = (
        search_db.query(ProductSpecifications)
        .join(Product, Product.id == ProductSpecifications.product_id)
        .filter(Product.product_code == code)
        .first()
    )
    assert spec is not None
    assert "brand" not in (spec.values or {}), "S0 removes brand from stored values entirely"
    assert (spec.rendered_text or "").startswith("Sorento"), (
        "the rendered sentence must still lead with the product's own brand field "
        "even though nothing in `values` carries brand any more"
    )


# --------------------------------------------------------------------------- #
# AC-S0.6 - brand is refused everywhere a rule or a spec write could still reach it
# --------------------------------------------------------------------------- #
def test_ac_s0_6_from_field_choices_no_longer_offers_brand():
    from app.services.product_spec_registry import from_field_choices

    assert "brand" not in from_field_choices()
    assert "category" in from_field_choices()


def test_ac_s0_6_get_spec_registry_has_no_brand_row(search_db, monkeypatch):
    from app.main import app
    from app.database import get_db
    from app.dependencies import get_current_user, get_current_user_or_api_key
    from app.services.company_scope_resolver import apply_company_scope
    from app.services.user_service import UserPermissionService
    from fastapi.testclient import TestClient

    app.dependency_overrides[get_db] = lambda: search_db
    user = {"id": str(uuid.uuid4()), "email": "brandtest@example.com"}
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_current_user_or_api_key] = lambda: user
    app.dependency_overrides[apply_company_scope] = lambda: None
    monkeypatch.setattr(
        UserPermissionService, "check_user_has_permission", lambda self, uid, slug: True
    )
    monkeypatch.setattr(
        UserPermissionService,
        "get_user_permission_slugs",
        lambda self, uid: {
            "master_data.products.view",
            "master_data.spec_registry.view",
            "master_data.spec_registry.edit",
        },
    )
    try:
        client = TestClient(app)
        body = client.get("/api/v1/master-data/spec-registry").json()
        keys = {row["spec_key"] for row in body.get("items", body if isinstance(body, list) else [])}
        assert "brand" not in keys
    finally:
        app.dependency_overrides.clear()


def test_ac_s0_6_a_rule_naming_brand_only_when_is_refused(search_db):
    from app.services.error_handler import AppException
    from app.services.product_spec_rules import validate_rules

    rules = [
        {
            "builder": {
                "kind": "words",
                "look_in": "any",
                "words": ["MATT BLACK"],
                "value": "black",
                "only_when": {"spec": "brand", "is": True, "values": ["SORENTO"]},
            }
        }
    ]
    with pytest.raises(AppException) as excinfo:
        validate_rules(rules, spec_key="finish", data_type="enum", allowed_values=["black"])
    assert excinfo.value.status_code == 400
    assert "brand" not in excinfo.value.message.lower() or "not a specification" in excinfo.value.message.lower()
