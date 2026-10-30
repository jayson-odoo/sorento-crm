"""Tests for AutoCount ItemClass on products (ITEM-CLASS).

PLAN: documentation/plans/products/PLAN-item-class-29oct.md
UAC:  documentation/plans/products/item-class-acceptance-criteria.md AC-1 .. AC-5.

Item classes follow the brand rule exactly: a product push's `item_class_code`
resolves through `product_rules.ensure_reference`, back-creating an unknown code
(code = name = raw value) with an `item_class_created` warning. Rows are read
through raw SQL so the file does not import the model it is testing.

Substrate: `tests._pg_fixture.blank_session()`, a real Postgres scratch schema
rolled back per test. Every code is minted under a `ZZTICL` marker.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

# MUST be the first app import - resolves the circular import in
# app.modules.runtime.guards.
from app.main import app  # noqa: E402

from app.models.company import Company
from app.models.product import ProductCategory, UnitOfMeasure
from app.services.company_scope import DEFAULT_COMPANY_ID

from ._pg_fixture import blank_session, unique_code

MARKER = "ZZTICL"

INGEST_PRODUCTS = "/api/v1/external/ingest/products"
CONTRACT_URL = "/api/v1/external/contract"

_USER_ID = "7d0dad31-1111-4222-8333-4444555588f1"
_ROLE_ID = "7d0dad31-2222-4222-8333-4444555588f2"


def _ref(stem: str) -> str:
    return f"{MARKER}:{stem}:{uuid.uuid4().hex[:8]}"


def _seed_principal(db) -> None:
    from app.models.user import User, UserRole, UserRoleAssignment

    db.add(
        UserRole(
            id=_ROLE_ID,
            slug="superadmin",
            name=f"{MARKER} Superadmin",
            description="",
            is_protected=True,
            is_default=False,
        )
    )
    db.flush()
    db.add(
        User(
            id=_USER_ID,
            name=f"{MARKER} admin",
            email=f"{MARKER.lower()}-admin@test.com",
            password="x",
            status="active",
        )
    )
    db.flush()
    db.add(UserRoleAssignment(user_id=_USER_ID, role_id=_ROLE_ID))
    db.flush()


class _Env:
    def __init__(self, client: TestClient, db):
        self.client = client
        self.db = db
        self.company_a = DEFAULT_COMPANY_ID
        suffix = uuid.uuid4().hex[:8]
        other = Company(id=str(uuid.uuid4()), name=f"{MARKER} B {suffix}", code=f"ZIC{suffix}")
        db.add(other)
        db.flush()
        self.company_b = str(other.id)
        self.company_a_code = db.execute(
            text("SELECT code FROM companies WHERE id = :id"), {"id": self.company_a}
        ).scalar()
        self.company_b_code = other.code
        db.commit()

    def post_product(self, *, code: str, company_code=None, **extra):
        company_code = company_code or self.company_a_code
        # A category and unit per company: products.category_id / base_uom_id
        # are NOT NULL, and ensure_reference back-creates them on first use.
        record = {
            "source_ref": extra.pop("source_ref", None) or _ref("ITEM"),
            "code": code,
            "name": f"{MARKER} product",
            "category_code": f"{MARKER}CAT",
            "uom_code": f"{MARKER}UOM",
            **extra,
        }
        res = self.client.post(
            INGEST_PRODUCTS, json={"companyCode": company_code, "records": [record]}
        )
        assert res.status_code == 200, res.text
        return record, res.json()["records"][0]

    def item_classes(self, company_id: str) -> list[dict]:
        return [
            dict(r)
            for r in self.db.execute(
                text(
                    "SELECT * FROM item_classes WHERE company_id = :cid "
                    "AND item_class_code ILIKE :p ORDER BY created_at"
                ),
                {"cid": company_id, "p": f"%{MARKER}%"},
            ).mappings()
        ]

    def product_item_class_id(self, code: str, company_id: str):
        return self.db.execute(
            text(
                "SELECT item_class_id FROM products WHERE product_code = :c AND company_id = :cid"
            ),
            {"c": code, "cid": company_id},
        ).scalar()


@pytest.fixture
def env():
    from app.dependencies import (  # safe: app.main is already loaded
        get_current_user,
        get_current_user_or_api_key,
        get_db,
        get_external_api_user,
    )
    from app.models.base import set_company_scope
    from app.services.company_scope_resolver import apply_company_scope

    with blank_session() as db:
        _seed_principal(db)

        def _override_get_db():
            yield db

        def _override_user():
            return {"id": _USER_ID, "email": f"{MARKER.lower()}-admin@test.com"}

        def _override_company_scope():
            set_company_scope(db, None)
            return None

        app.dependency_overrides[get_db] = _override_get_db
        app.dependency_overrides[get_current_user] = _override_user
        app.dependency_overrides[get_current_user_or_api_key] = _override_user
        app.dependency_overrides[get_external_api_user] = _override_user
        app.dependency_overrides[apply_company_scope] = _override_company_scope
        try:
            with TestClient(app) as client:
                yield _Env(client, db)
        finally:
            app.dependency_overrides.clear()


# ===================================================================== AC-1
class TestBackCreate:
    def test_unknown_item_class_is_created_and_linked_with_a_warning(self, env):
        item_class = f"{MARKER} SERENE"
        record, entry = env.post_product(code=unique_code(MARKER), item_class_code=item_class)

        assert entry["outcome"] == "created", entry
        assert "item_class_created" in entry.get("warnings", [])
        rows = env.item_classes(env.company_a)
        assert len(rows) == 1
        assert rows[0]["item_class_code"] == item_class
        assert rows[0]["item_class_name"] == item_class
        assert str(env.product_item_class_id(record["code"], env.company_a)) == str(rows[0]["id"])


# ===================================================================== AC-2
class TestReuse:
    def test_same_code_any_case_and_spacing_links_the_existing_row(self, env):
        first, _ = env.post_product(code=unique_code(MARKER), item_class_code=f"{MARKER}SERENE2")
        second, entry = env.post_product(
            code=unique_code(MARKER), item_class_code=f"  {MARKER.lower()}serene2 "
        )

        assert "item_class_created" not in entry.get("warnings", [])
        rows = env.item_classes(env.company_a)
        assert len(rows) == 1
        for pushed in (first, second):
            linked = env.product_item_class_id(pushed["code"], env.company_a)
            assert linked is not None
            assert str(linked) == str(rows[0]["id"])


# ===================================================================== AC-3
class TestAbsentOrBlankLeavesLink:
    def test_absent_item_class_leaves_the_stored_link(self, env):
        code = unique_code(MARKER)
        ref = _ref("KEEP")
        env.post_product(code=code, source_ref=ref, item_class_code=f"{MARKER}DIY")
        linked = env.product_item_class_id(code, env.company_a)
        assert linked is not None

        _, entry = env.post_product(code=code, source_ref=ref)

        assert entry["outcome"] in ("updated", "unchanged"), entry
        assert env.product_item_class_id(code, env.company_a) == linked

    @pytest.mark.parametrize("blank", ["", "   ", None])
    def test_blank_item_class_clears_the_stored_link(self, env, blank):
        """Crew ruling 29 Oct (security M1): AutoCount cleared the class, so the CRM does."""
        code = unique_code(MARKER)
        ref = _ref("CLEAR")
        env.post_product(code=code, source_ref=ref, item_class_code=f"{MARKER}DIY")
        assert env.product_item_class_id(code, env.company_a) is not None

        _, entry = env.post_product(code=code, source_ref=ref, item_class_code=blank)

        assert entry["outcome"] == "updated", entry
        assert env.product_item_class_id(code, env.company_a) is None
        assert "item_class_created" not in entry.get("warnings", [])

    def test_a_product_pushed_without_item_class_has_none(self, env):
        code = unique_code(MARKER)
        env.post_product(code=code)
        assert env.product_item_class_id(code, env.company_a) is None


# ===================================================================== AC-4
class TestCompanyIsolation:
    def test_same_code_in_another_company_is_a_separate_row(self, env):
        item_class = f"{MARKER}SERENE3"
        env.post_product(code=unique_code(MARKER), item_class_code=item_class)
        _, entry_b = env.post_product(
            code=unique_code(MARKER), item_class_code=item_class, company_code=env.company_b_code
        )

        assert "item_class_created" in entry_b.get("warnings", [])
        a_rows = env.item_classes(env.company_a)
        b_rows = env.item_classes(env.company_b)
        assert len(a_rows) == 1 and len(b_rows) == 1
        assert a_rows[0]["id"] != b_rows[0]["id"]


# ===================================================================== AC-5
class TestContract:
    def test_contract_lists_the_field_and_the_warning(self, env):
        res = env.client.get(CONTRACT_URL)
        assert res.status_code == 200, res.text
        body = res.json()
        assert "item_class_code" in body["fields_added"]["products"]
        assert "item_class_created" in body["warnings"]
