"""The AutoCount `item_classes` ingest master (contract 2.11), a copy of the brands master.

PLAN: documentation/plans/products/PLAN-item-class-master-29oct.md
UAC:  documentation/plans/products/item-class-master-acceptance-criteria.md AC-1 .. AC-10.

Substrate: `tests._pg_fixture.blank_session()`, a real Postgres scratch schema built from the
current ORM models and rolled back per test. Every code is minted under a `ZZTICM` marker.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text

# MUST be the first app import - resolves the circular import in
# app.modules.runtime.guards.
from app.main import app  # noqa: E402

from app.models.company import Company
from app.models.product import ItemClass, Product, ProductCategory, UnitOfMeasure
from app.services.company_scope import DEFAULT_COMPANY_ID
from app.services.integration_reference_service import IntegrationReferenceService

from ._pg_fixture import blank_session, unique_code

MARKER = "ZZTICM"

INGEST = "/api/v1/external/ingest/item_classes"
READ = "/api/v1/external/read/item_classes"
DELETE = "/api/v1/external/ingest/item_classes/deletions"
INGEST_PRODUCTS = "/api/v1/external/ingest/products"
CONTRACT_URL = "/api/v1/external/contract"

_USER_ID = "7d0dad30-1111-4222-8333-4444555588f1"
_ROLE_ID = "7d0dad30-2222-4222-8333-4444555588f2"


def _ref(stem: str) -> str:
    return f"{MARKER}:{stem}:{uuid.uuid4().hex[:8]}"


def _seed_principal(db) -> None:
    from app.models.user import User, UserRole, UserRoleAssignment

    db.add(UserRole(id=_ROLE_ID, slug="superadmin", name=f"{MARKER} Superadmin", description="",
                    is_protected=True, is_default=False))
    db.flush()
    db.add(User(id=_USER_ID, name=f"{MARKER} admin", email=f"{MARKER.lower()}-admin@test.com",
                password="x", status="active"))
    db.flush()
    db.add(UserRoleAssignment(user_id=_USER_ID, role_id=_ROLE_ID))
    db.flush()


class _Env:
    def __init__(self, client: TestClient, db):
        self.client = client
        self.db = db
        self.company_a = DEFAULT_COMPANY_ID
        self.refs = IntegrationReferenceService(db, company_id=self.company_a)

        suffix = uuid.uuid4().hex[:8]
        other = Company(id=str(uuid.uuid4()), name=f"{MARKER} B {suffix}", code=f"ZIC{suffix}")
        db.add(other)
        db.flush()
        self.company_b = str(other.id)
        self.company_a_code = db.execute(
            text("SELECT code FROM companies WHERE id = :id"), {"id": self.company_a}
        ).scalar()
        self.company_b_code = other.code

        self._category = ProductCategory(
            category_code=unique_code(MARKER), category_name=f"{MARKER} category"
        )
        self._uom = UnitOfMeasure(uom_code=unique_code(MARKER), uom_name=f"{MARKER} unit")
        db.add_all([self._category, self._uom])
        db.commit()

    def post(self, url: str, records: list, *, company_code=None, dry_run=False):
        return self.client.post(
            f"{url}?dry_run=true" if dry_run else url,
            json={"companyCode": company_code or self.company_a_code, "records": records},
        )

    def read(self, source_refs: list):
        return self.client.post(
            READ, json={"companyCode": self.company_a_code, "source_refs": source_refs}
        )

    def delete(self, source_refs: list, *, dry_run=False):
        return self.client.post(
            f"{DELETE}?dry_run=true" if dry_run else DELETE,
            json={"companyCode": self.company_a_code, "source_refs": source_refs},
        )

    def item_class(self, *, code: str, name: str, company_id: str, **extra) -> ItemClass:
        row = ItemClass(item_class_code=code, item_class_name=name, company_id=company_id, **extra)
        self.db.add(row)
        self.db.flush()
        return row

    def row(self, item_class_id: str):
        return self.db.execute(
            text("SELECT * FROM item_classes WHERE id = :id"), {"id": str(item_class_id)}
        ).mappings().first()

    def by_code(self, code: str, company_id: str):
        return self.db.execute(
            text("SELECT * FROM item_classes WHERE item_class_code = :c AND company_id = :cid"),
            {"c": code, "cid": company_id},
        ).mappings().first()

    def count(self, company_id: str) -> int:
        return self.db.execute(
            text("SELECT count(*) FROM item_classes WHERE company_id = :cid"), {"cid": company_id}
        ).scalar()

    def product(self, item_class_id: str) -> Product:
        row = Product(
            product_code=unique_code(MARKER),
            product_name=f"{MARKER} product",
            category_id=self._category.id,
            base_uom_id=self._uom.id,
            list_price=10,
            item_class_id=item_class_id,
            company_id=self.company_a,
        )
        self.db.add(row)
        self.db.flush()
        return row


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


def _record(*, code=None, name=None, ref=None, **extra) -> dict:
    return {
        "source_ref": ref or _ref("CLASS"),
        "code": code or unique_code(MARKER)[:20],
        "name": name or f"{MARKER} Class",
        **extra,
    }


# ======================================================================= AC-1, AC-2
class TestCreateAndRepush:
    def test_a_new_class_creates_the_row_and_links_the_reference(self, env):
        record = _record(description="Serene series", is_active=True)

        res = env.post(INGEST, [record])

        assert res.status_code == 200, res.text
        entry = res.json()["records"][0]
        assert entry["outcome"] == "created", entry
        row = env.by_code(record["code"], env.company_a)
        assert row is not None
        assert str(row["id"]) == entry["entity_id"]
        assert row["item_class_name"] == record["name"]
        assert row["description"] == "Serene series"
        assert row["is_active"] is True
        linked = env.refs.resolve(entity_type="item_classes", source_ref=record["source_ref"])
        assert str(linked) == entry["entity_id"]

    def test_repush_updates_the_same_row_absent_untouched_blank_clears(self, env):
        record = _record(description="Keep me")
        first = env.post(INGEST, [record])
        assert first.status_code == 200, first.text
        entity_id = first.json()["records"][0]["entity_id"]

        bare = {"source_ref": record["source_ref"], "code": record["code"], "name": "Renamed"}
        again = env.post(INGEST, [bare])
        assert again.status_code == 200, again.text
        entry = again.json()["records"][0]
        assert entry["outcome"] == "updated", entry
        assert entry["entity_id"] == entity_id
        row = env.row(entity_id)
        assert row["description"] == "Keep me"
        assert row["item_class_name"] == "Renamed", "AutoCount is master for the name"

        cleared = env.post(INGEST, [{**bare, "description": "", "is_active": False}])
        assert cleared.status_code == 200, cleared.text
        row = env.row(entity_id)
        assert row["description"] is None
        assert row["is_active"] is False
        assert env.count(env.company_a) == 1, "still one row, never a duplicate"


# ============================================================================ AC-3
class TestAdoption:
    def test_a_class_a_product_push_created_is_adopted_case_insensitively(self, env):
        # The placeholder #1972's product push back-creates (code = name, auto note), in a
        # different case and padded, to pin the case/whitespace-insensitive match.
        made = env.item_class(
            code=" serene ", name=" serene ", company_id=env.company_a,
            description="Auto-created by product import",
        )
        made_id = str(made.id)
        env.db.commit()

        record = _record(code="SERENE", name="SERENE", description="")
        res = env.post(INGEST, [record])

        assert res.status_code == 200, res.text
        entry = res.json()["records"][0]
        assert entry["outcome"] == "updated", entry
        assert entry["entity_id"] == made_id
        assert env.count(env.company_a) == 1, "no second row"
        row = env.row(made_id)
        assert row["item_class_code"] == "SERENE"
        assert row["item_class_name"] == "SERENE"
        assert row["description"] is None, "AutoCount's blank replaces the placeholder note"
        assert env.refs.resolve(entity_type="item_classes", source_ref=record["source_ref"]) == made_id


# ============================================================================ AC-4
class TestCompanyScope:
    def test_same_code_in_two_companies_creates_independently(self, env):
        theirs = env.item_class(code="DIY", name="DIY A", company_id=env.company_a)
        env.db.commit()

        res = env.post(INGEST, [_record(code="DIY", name="DIY B")], company_code=env.company_b_code)

        assert res.status_code == 200, res.text
        entry = res.json()["records"][0]
        assert entry["outcome"] == "created", entry
        assert entry["entity_id"] != str(theirs.id)
        assert env.row(theirs.id)["item_class_name"] == "DIY A", "company A untouched"
        assert env.by_code("DIY", env.company_b)["item_class_name"] == "DIY B"


# ============================================================================ AC-5
class TestReadBack:
    def test_read_returns_the_canonical_shape(self, env):
        record = _record(description="A description", is_active=True)
        assert env.post(INGEST, [record]).status_code == 200

        res = env.read([record["source_ref"], _ref("NOPE")])
        assert res.status_code == 200, res.text
        body = res.json()
        assert len(body["not_found"]) == 1
        got = body["records"][0]
        assert got["code"] == record["code"]
        assert got["name"] == record["name"]
        assert got["description"] == "A description"
        assert got["is_active"] is True


# ============================================================================ AC-6
class TestDeletionsDeactivate:
    def _linked(self, env):
        row = env.item_class(code=unique_code(MARKER)[:20], name=f"{MARKER} del", company_id=env.company_a)
        source_ref = _ref("DEL")
        env.refs.link(entity_type="item_classes", entity_id=str(row.id), source_ref=source_ref)
        env.db.commit()
        return row, source_ref

    def test_an_unused_class_is_deactivated_never_hard_deleted(self, env):
        # A class can sit in a contact's brand_class_ids JSONB, which the FK referrer probe
        # cannot see, so even an unused class only goes inactive (plan D5).
        row, source_ref = self._linked(env)

        res = env.delete([source_ref])

        assert res.status_code == 200, res.text
        entry = res.json()["records"][0]
        assert entry["outcome"] == "deactivated", entry
        kept = env.row(row.id)
        assert kept is not None
        assert kept["is_active"] is False
        assert env.refs.resolve(entity_type="item_classes", source_ref=source_ref) == str(row.id)

    def test_a_class_products_carry_is_deactivated_and_products_keep_it(self, env):
        row, source_ref = self._linked(env)
        product = env.product(str(row.id))
        env.db.commit()

        res = env.delete([source_ref])

        assert res.status_code == 200, res.text
        assert res.json()["records"][0]["outcome"] == "deactivated"
        assert env.row(row.id)["is_active"] is False
        kept = env.db.execute(
            text("SELECT item_class_id FROM products WHERE id = :id"), {"id": str(product.id)}
        ).scalar()
        assert str(kept) == str(row.id)

    def test_a_repush_reactivates(self, env):
        row, source_ref = self._linked(env)
        assert env.delete([source_ref]).json()["records"][0]["outcome"] == "deactivated"

        res = env.post(INGEST, [_record(code=row.item_class_code, name="Back", ref=source_ref,
                                        is_active=True)])

        assert res.status_code == 200, res.text
        assert res.json()["records"][0]["entity_id"] == str(row.id)
        assert env.row(row.id)["is_active"] is True

    def test_an_unknown_ref_is_not_found(self, env):
        res = env.delete([_ref("GONE")])
        assert res.status_code == 200, res.text
        assert res.json()["records"][0]["outcome"] == "not_found"


# ============================================================================ AC-7
class TestPermissionMaps:
    def test_the_three_doors_take_the_item_class_slugs(self):
        from app.api.v1.external.ingest import (
            DELETE_PERMISSIONS,
            INGEST_PERMISSIONS,
            READ_PERMISSIONS,
        )

        assert INGEST_PERMISSIONS["item_classes"] == "master_data.item_classes.edit"
        assert READ_PERMISSIONS["item_classes"] == "master_data.item_classes.view"
        assert DELETE_PERMISSIONS["item_classes"] == "master_data.item_classes.delete"


class TestPermissionGuard:
    """The real RBAC guard on an empty schema, mirrors `test_ingest_brands.py`."""

    @pytest.fixture()
    def guard_db(self):
        from app.models.integration import Integration, IntegrationApiKey
        from app.models.user import (
            User,
            UserPermission,
            UserRole,
            UserRoleAssignment,
            UserRolePermission,
        )
        from tests._pg_fixture import pg_empty_schema

        with pg_empty_schema(
            [
                User.__table__,
                UserRole.__table__,
                UserRoleAssignment.__table__,
                UserPermission.__table__,
                UserRolePermission.__table__,
                Integration.__table__,
                IntegrationApiKey.__table__,
            ]
        ) as session:
            yield session

    @pytest.fixture()
    def guard_client(self, guard_db):
        from app.dependencies import get_db as app_get_db
        from app.api.v1.external import ingest as ingest_module
        from app.api.v1.external.permissions import require_external_permission_for_path

        api = FastAPI()

        @api.post("/ingest/{entity}")
        def _ingest_stub(
            entity: str,
            _: dict = Depends(
                require_external_permission_for_path(ingest_module.INGEST_PERMISSIONS)
            ),
        ):
            return {"ok": entity}

        def _override_db():
            yield guard_db

        api.dependency_overrides[app_get_db] = _override_db
        return TestClient(api, raise_server_exceptions=False)

    @pytest.fixture()
    def keys(self, guard_db):
        from app.models.integration import Integration
        from app.models.user import (
            User,
            UserPermission,
            UserRole,
            UserRoleAssignment,
            UserRolePermission,
        )
        from app.services.integration_key_service import IntegrationKeyService

        perms = {}
        # The brands edit slug is held by the "brands only" key: it must NOT open item classes.
        for slug in ("master_data.item_classes.edit", "master_data.brands.edit"):
            perm = UserPermission(slug=slug, name=slug)
            guard_db.add(perm)
            guard_db.flush()
            perms[slug] = perm

        issued = {}
        for label, held in (
            ("editor", ["master_data.item_classes.edit"]),
            ("brands", ["master_data.brands.edit"]),
        ):
            user = User(
                email=f"{MARKER.lower()}-{label}@integrations.local",
                name=f"Integration: {label}",
                status="ACTIVE",
                is_integration=True,
            )
            guard_db.add(user)
            guard_db.flush()
            role = UserRole(slug=f"{MARKER.lower()}_{label}", name=f"{MARKER} {label}")
            guard_db.add(role)
            guard_db.flush()
            guard_db.add(UserRoleAssignment(user_id=user.id, role_id=role.id))
            for slug in held:
                guard_db.add(UserRolePermission(role_id=role.id, permission_id=perms[slug].id))
            guard_db.flush()
            integration = Integration(
                name=f"{MARKER}-{label}", type="autocount_esb", act_as_user_id=user.id, is_active=True
            )
            guard_db.add(integration)
            guard_db.flush()
            issued[label] = IntegrationKeyService(guard_db).issue_key(integration)
        return issued

    def test_a_key_without_the_edit_slug_is_403_naming_it(self, guard_client, keys):
        res = guard_client.post("/ingest/item_classes", headers={"X-API-Key": keys["brands"]})
        assert res.status_code == 403, res.text
        assert "master_data.item_classes.edit" in res.text

    def test_the_edit_slug_passes(self, guard_client, keys):
        res = guard_client.post("/ingest/item_classes", headers={"X-API-Key": keys["editor"]})
        assert res.status_code == 200, res.text


# ============================================================================ AC-8
class TestContract:
    def test_version_2_11_lists_item_classes(self, env):
        res = env.client.get(CONTRACT_URL)
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["version"] == "2.11"
        assert "item_classes" in body["entities"]
        assert set(body["fields_added"]["item_classes"]) == {
            "code", "name", "description", "is_active",
        }

    def test_the_reference_allowlist_carries_item_classes(self):
        from app.services.integration_reference_service import SUPPORTED_ENTITY_TYPES

        assert "item_classes" in SUPPORTED_ENTITY_TYPES


# ============================================================================ AC-9
class TestFieldValidation:
    def test_oversize_code_and_name_each_fail_their_own_record(self, env):
        too_long_code = _record(code="C" * 51)
        too_long_name = _record(name="N" * 151)
        good = _record()

        res = env.post(INGEST, [too_long_code, too_long_name, good])

        assert res.status_code == 200, res.text
        by_ref = {r["source_ref"]: r for r in res.json()["records"]}
        assert by_ref[too_long_code["source_ref"]]["outcome"] == "failed"
        assert "code" in by_ref[too_long_code["source_ref"]].get("errors", {})
        assert by_ref[too_long_name["source_ref"]]["outcome"] == "failed"
        assert "name" in by_ref[too_long_name["source_ref"]].get("errors", {})
        assert by_ref[good["source_ref"]]["outcome"] == "created"

    def test_dry_run_writes_nothing(self, env):
        record = _record()
        res = env.post(INGEST, [record], dry_run=True)
        assert res.status_code == 200, res.text
        assert res.json()["records"][0]["outcome"] == "created"
        assert env.by_code(record["code"], env.company_a) is None


# =========================================================================== AC-10
class TestProductPushLinksTheMaster:
    def test_a_product_push_after_a_class_push_links_it_without_a_warning(self, env):
        record = _record(code=unique_code(MARKER)[:20], name="Serene", description="Serene series")
        class_id = env.post(INGEST, [record]).json()["records"][0]["entity_id"]

        product = {
            "source_ref": _ref("ITEM"),
            "code": unique_code(MARKER),
            "name": f"{MARKER} product",
            "category_code": env._category.category_code,
            "uom_code": env._uom.uom_code,
            "item_class_code": record["code"].lower(),
        }
        res = env.post(INGEST_PRODUCTS, [product])

        assert res.status_code == 200, res.text
        entry = res.json()["records"][0]
        assert entry["outcome"] == "created", entry
        assert "item_class_created" not in entry.get("warnings", [])
        linked = env.db.execute(
            text("SELECT item_class_id FROM products WHERE id = :id"), {"id": entry["entity_id"]}
        ).scalar()
        assert str(linked) == class_id
        assert env.count(env.company_a) == 1
        assert env.row(class_id)["description"] == "Serene series"
