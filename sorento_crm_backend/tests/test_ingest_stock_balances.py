"""RED tests for the `stock_balances` push ingest entity (contract 2.5, SR5a).

PLAN: documentation/plans/autocount/PLAN-ingest-stock-balances-2-5.md D1-D12.
UAC:  documentation/plans/autocount/ingest-stock-balances-2-5-acceptance-criteria.md
      AC-SB-1 .. AC-SB-20. AC-SB-21 (SR5b) is pending a separate ruling and has
      no test here.

None of this exists yet (D1): `stock_balances` is not in `SUPPORTED_ENTITIES`,
`INGEST_PERMISSIONS`, `READ_PERMISSIONS` or `DELETE_PERMISSIONS`. The router
mount in `app/api/v1/external/__init__.py` wraps BOTH the ingest and read
routers in `Depends(require_external_permission_for_path(...))`, which 404s
("unknown_entity") an unmapped entity BEFORE the handler's own body parsing
or DB work ever runs - even for a superadmin principal, since the permission
map lookup happens before any permission CHECK. So every test below that
calls the real `/external/ingest|read/stock_balances*` routes is expected to
fail on that 404 today, not on an ImportError or a fixture bug. AC-SB-1 (the
contract endpoint) fails differently: it returns 200 today, just with the
WRONG version/entities/warnings - a value mismatch, not an exception.

Substrate: `tests._pg_fixture.blank_session()`, a real Postgres scratch
schema built from the current ORM models and rolled back per test - same
substrate as `tests/test_ingest_brands.py`. `stock_balances` resolution
(D4) never goes through `integration_references` (D3: `source_ref` is an
echo key only, never stored), so unlike the brands/masters fixtures this one
seeds no `IntegrationReferenceService` at all - identity is always the
(product, warehouse) pair, resolved fresh on every push.

Every code minted here carries a `ZZTSB` marker.
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text

# MUST be the first app import - resolves the circular import in
# app.modules.runtime.guards.
from app.main import app  # noqa: E402

from app.api.v1.external.ingest import MAX_BATCH
from app.database import engine
from app.models.company import Company
from app.models.inventory import Stock, Warehouse
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.services.company_scope import DEFAULT_COMPANY_ID

from ._pg_fixture import blank_session, unique_code

MARKER = "ZZTSB"

INGEST_SB = "/api/v1/external/ingest/stock_balances"
READ_SB = "/api/v1/external/read/stock_balances"
DELETE_SB = "/api/v1/external/ingest/stock_balances/deletions"
CONTRACT_URL = "/api/v1/external/contract"

_USER_ID = "7d0dad30-5555-4222-8333-4444555577f5"
_ROLE_ID = "7d0dad30-6666-4222-8333-4444555577f6"


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
        other = Company(id=str(uuid.uuid4()), name=f"{MARKER} B {suffix}", code=f"ZSB{suffix}")
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
        db.flush()

        # D4 step 2: location resolution is trimmed + case-insensitive,
        # company-scoped. One active, one inactive, one belonging to the
        # OTHER company - none share a code, so a resolution result can only
        # be explained by one of the three.
        self.wh_active = self._warehouse("MBS", is_active=True, company_id=self.company_a)
        self.wh_inactive = self._warehouse("CON", is_active=False, company_id=self.company_a)
        self.wh_other_company = self._warehouse(
            "OTH", is_active=True, company_id=self.company_b
        )

        # D4 step 3: item_code resolution, trimmed + case-insensitive,
        # company-scoped. One plain code, one with spaces AND quotes in it
        # (AC-SB-8), one belonging to the other company.
        self.product = self._product(unique_code(MARKER), company_id=self.company_a)
        self.special_code = f'1/2" ULTRA CIRCULAR {uuid.uuid4().hex[:6]}'
        self.special_product = self._product(self.special_code, company_id=self.company_a)
        self.product_other_company = self._product(
            unique_code(MARKER), company_id=self.company_b
        )
        db.commit()

    # --------------------------------------------------------------- seeds
    def _warehouse(self, code: str, *, is_active: bool, company_id: str) -> Warehouse:
        row = Warehouse(
            warehouse_code=f"{code}-{uuid.uuid4().hex[:6]}",
            warehouse_name=f"{MARKER} {code}",
            is_active=is_active,
            company_id=company_id,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def _product(self, code: str, *, company_id: str) -> Product:
        row = Product(
            product_code=code,
            product_name=f"{MARKER} product {code}",
            category_id=self._category.id,
            base_uom_id=self._uom.id,
            list_price=10,
            company_id=company_id,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def make_stock(self, *, product_id: str, warehouse_id: str, company_id: str = None, **kw) -> Stock:
        row = Stock(
            product_id=product_id,
            warehouse_id=warehouse_id,
            company_id=company_id or self.company_a,
            **kw,
        )
        self.db.add(row)
        self.db.flush()
        return row

    # --------------------------------------------------------------- calls
    def post(self, url: str, records: list, *, company_code=None, dry_run=False):
        return self.client.post(
            f"{url}?dry_run=true" if dry_run else url,
            json={"companyCode": company_code or self.company_a_code, "records": records},
        )

    def delete(self, source_refs: list, pairs: dict, *, company_code=None, dry_run=False, raw_pairs=False):
        body = {
            "companyCode": company_code or self.company_a_code,
            "source_refs": source_refs,
            "pairs": pairs,
        }
        return self.client.post(
            f"{DELETE_SB}?dry_run=true" if dry_run else DELETE_SB,
            json=body,
        )

    def read(self, source_refs: list, pairs: dict, *, company_code=None):
        return self.client.post(
            READ_SB,
            json={
                "companyCode": company_code or self.company_a_code,
                "source_refs": source_refs,
                "pairs": pairs,
            },
        )

    # --------------------------------------------------------------- reads
    def stock_row(self, product_id, warehouse_id):
        return (
            self.db.execute(
                text(
                    "SELECT * FROM stock WHERE product_id = :p AND warehouse_id = :w"
                ),
                {"p": str(product_id), "w": str(warehouse_id)},
            )
            .mappings()
            .first()
        )

    def stock_by_id(self, stock_id):
        return (
            self.db.execute(text("SELECT * FROM stock WHERE id = :id"), {"id": str(stock_id)})
            .mappings()
            .first()
        )


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


def _sb_record(*, item_code=None, location_code=None, qty=0, ref=None, **extra) -> dict:
    record = {"source_ref": ref or _ref("SB")}
    if item_code is not None:
        record["item_code"] = item_code
    if location_code is not None:
        record["location_code"] = location_code
    record["qty"] = qty
    record.update(extra)
    return record


# ==================================================================== AC-SB-1
class TestContractAC1:
    def test_contract_lists_2_5_stock_balances_and_warehouse_inactive(self, env):
        res = env.client.get(CONTRACT_URL)
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["version"] == "2.5", body["version"]
        assert "stock_balances" in body["entities"]
        assert "warehouse_inactive" in body["warnings"]
        assert "stock_balances" in body["fields_added"]


# ==================================================================== AC-SB-2
class TestCreateAC2:
    def test_a_new_pair_is_created_with_reserved_and_damaged_zero(self, env):
        record = _sb_record(
            item_code=env.product.product_code,
            location_code=env.wh_active.warehouse_code,
            qty=25,
        )

        res = env.post(INGEST_SB, [record])

        assert res.status_code == 200, res.text
        entry = res.json()["records"][0]
        assert entry["outcome"] == "created", entry
        row = env.stock_row(env.product.id, env.wh_active.id)
        assert row is not None
        assert str(row["id"]) == entry["entity_id"]
        assert row["quantity_on_hand"] == 25
        assert row["quantity_reserved"] == 0
        assert row["quantity_damaged"] == 0


# ==================================================================== AC-SB-3
class TestUpdatePreservesOtherColumnsAC3:
    def test_existing_pair_updates_only_quantity_on_hand(self, env):
        zone = str(uuid.uuid4())
        existing = env.make_stock(
            product_id=env.product.id,
            warehouse_id=env.wh_active.id,
            quantity_on_hand=100,
            quantity_reserved=5,
            quantity_damaged=2,
            reorder_point=10,
            zone_id=zone,
        )

        record = _sb_record(
            item_code=env.product.product_code,
            location_code=env.wh_active.warehouse_code,
            qty=150,
        )
        res = env.post(INGEST_SB, [record])

        assert res.status_code == 200, res.text
        entry = res.json()["records"][0]
        assert entry["outcome"] == "updated", entry
        assert entry["entity_id"] == str(existing.id)
        row = env.stock_by_id(existing.id)
        assert row["quantity_on_hand"] == 150
        assert row["quantity_reserved"] == 5
        assert row["quantity_damaged"] == 2
        assert row["reorder_point"] == 10
        assert str(row["zone_id"]) == zone


# ==================================================================== AC-SB-4
class TestRepushSameValueAC4:
    def test_same_record_twice_second_is_updated_with_empty_diff_on_dry_run(self, env):
        record = _sb_record(
            item_code=env.product.product_code,
            location_code=env.wh_active.warehouse_code,
            qty=10,
        )
        first = env.post(INGEST_SB, [record])
        assert first.status_code == 200, first.text
        assert first.json()["records"][0]["outcome"] == "created"

        again = env.post(INGEST_SB, [record], dry_run=True)
        assert again.status_code == 200, again.text
        entry = again.json()["records"][0]
        assert entry["outcome"] == "updated", entry
        assert entry.get("diff") == {}, entry


# ==================================================================== AC-SB-5
class TestLocationCaseAndTrimAC5:
    def test_location_matches_trimmed_and_case_insensitive(self, env):
        record = _sb_record(
            item_code=env.product.product_code,
            location_code=f"  {env.wh_active.warehouse_code.lower()}  ",
            qty=5,
        )
        res = env.post(INGEST_SB, [record])
        assert res.status_code == 200, res.text
        entry = res.json()["records"][0]
        assert entry["outcome"] == "created", entry
        row = env.stock_row(env.product.id, env.wh_active.id)
        assert row is not None
        assert row["quantity_on_hand"] == 5


# ==================================================================== AC-SB-6
class TestUnknownLocationAC6:
    def test_unknown_location_is_updated_with_warehouse_unresolved_nothing_written(self, env):
        record = _sb_record(
            item_code=env.product.product_code,
            location_code=f"{MARKER}-NOWHERE-{uuid.uuid4().hex[:6]}",
            qty=5,
        )
        res = env.post(INGEST_SB, [record])
        assert res.status_code == 200, res.text
        entry = res.json()["records"][0]
        assert entry["outcome"] == "updated", entry
        assert "warehouse_unresolved" in entry.get("warnings", []), entry
        assert entry["entity_id"] is None, entry
        # nothing written anywhere for this product
        row = env.stock_row(env.product.id, env.wh_active.id)
        assert row is None


# ==================================================================== AC-SB-7
class TestInactiveLocationAC7:
    def test_inactive_warehouse_is_updated_with_warehouse_inactive_nothing_changed(self, env):
        existing = env.make_stock(
            product_id=env.product.id,
            warehouse_id=env.wh_inactive.id,
            quantity_on_hand=42,
        )
        record = _sb_record(
            item_code=env.product.product_code,
            location_code=env.wh_inactive.warehouse_code,
            qty=999,
        )
        res = env.post(INGEST_SB, [record])
        assert res.status_code == 200, res.text
        entry = res.json()["records"][0]
        assert entry["outcome"] == "updated", entry
        assert "warehouse_inactive" in entry.get("warnings", []), entry
        row = env.stock_by_id(existing.id)
        assert row["quantity_on_hand"] == 42, "must not have been touched"


# ==================================================================== AC-SB-8
class TestUnknownAndSpecialItemCodeAC8:
    def test_unknown_item_code_is_retryable_nothing_written(self, env):
        record = _sb_record(
            item_code=f"{MARKER}-GONE-{uuid.uuid4().hex[:6]}",
            location_code=env.wh_active.warehouse_code,
            qty=5,
        )
        res = env.post(INGEST_SB, [record])
        assert res.status_code == 200, res.text
        entry = res.json()["records"][0]
        assert entry["outcome"] == "retryable", entry

    def test_item_code_with_spaces_and_quotes_resolves(self, env):
        record = _sb_record(
            item_code=env.special_code,
            location_code=env.wh_active.warehouse_code,
            qty=7,
        )
        res = env.post(INGEST_SB, [record])
        assert res.status_code == 200, res.text
        entry = res.json()["records"][0]
        assert entry["outcome"] == "created", entry
        row = env.stock_row(env.special_product.id, env.wh_active.id)
        assert row is not None
        assert row["quantity_on_hand"] == 7


# ==================================================================== AC-SB-9
class TestFieldValidationAC9:
    def test_missing_item_code_fails(self, env):
        record = {"source_ref": _ref("MISS1"), "location_code": env.wh_active.warehouse_code, "qty": 1}
        res = env.post(INGEST_SB, [record])
        assert res.status_code == 200, res.text
        entry = res.json()["records"][0]
        assert entry["outcome"] == "failed", entry
        assert "item_code" in entry.get("errors", {}), entry

    def test_blank_item_code_fails(self, env):
        record = _sb_record(item_code="   ", location_code=env.wh_active.warehouse_code, qty=1)
        res = env.post(INGEST_SB, [record])
        assert res.status_code == 200, res.text
        entry = res.json()["records"][0]
        assert entry["outcome"] == "failed", entry

    def test_missing_location_code_fails(self, env):
        record = {"source_ref": _ref("MISS2"), "item_code": env.product.product_code, "qty": 1}
        res = env.post(INGEST_SB, [record])
        assert res.status_code == 200, res.text
        entry = res.json()["records"][0]
        assert entry["outcome"] == "failed", entry
        assert "location_code" in entry.get("errors", {}), entry

    def test_qty_string_fails(self, env):
        record = _sb_record(
            item_code=env.product.product_code, location_code=env.wh_active.warehouse_code, qty="10"
        )
        res = env.post(INGEST_SB, [record])
        assert res.status_code == 200, res.text
        entry = res.json()["records"][0]
        assert entry["outcome"] == "failed", entry
        assert "qty" in entry.get("errors", {}), entry

    def test_qty_float_fails(self, env):
        record = _sb_record(
            item_code=env.product.product_code, location_code=env.wh_active.warehouse_code, qty=10.5
        )
        res = env.post(INGEST_SB, [record])
        assert res.status_code == 200, res.text
        entry = res.json()["records"][0]
        assert entry["outcome"] == "failed", entry

    def test_qty_bool_fails(self, env):
        record = _sb_record(
            item_code=env.product.product_code, location_code=env.wh_active.warehouse_code, qty=True
        )
        res = env.post(INGEST_SB, [record])
        assert res.status_code == 200, res.text
        entry = res.json()["records"][0]
        assert entry["outcome"] == "failed", entry

    def test_qty_negative_fails(self, env):
        record = _sb_record(
            item_code=env.product.product_code, location_code=env.wh_active.warehouse_code, qty=-1
        )
        res = env.post(INGEST_SB, [record])
        assert res.status_code == 200, res.text
        entry = res.json()["records"][0]
        assert entry["outcome"] == "failed", entry

    def test_qty_zero_is_accepted_and_written(self, env):
        record = _sb_record(
            item_code=env.product.product_code, location_code=env.wh_active.warehouse_code, qty=0
        )
        res = env.post(INGEST_SB, [record])
        assert res.status_code == 200, res.text
        entry = res.json()["records"][0]
        assert entry["outcome"] == "created", entry
        row = env.stock_row(env.product.id, env.wh_active.id)
        assert row is not None
        assert row["quantity_on_hand"] == 0


# =================================================================== AC-SB-10
class TestExtraKeyAC10:
    def test_unknown_extra_key_fails(self, env):
        record = _sb_record(
            item_code=env.product.product_code,
            location_code=env.wh_active.warehouse_code,
            qty=1,
            not_a_real_field="whatever",
        )
        res = env.post(INGEST_SB, [record])
        assert res.status_code == 200, res.text
        entry = res.json()["records"][0]
        assert entry["outcome"] == "failed", entry

    def test_item_description_and_uom_code_are_accepted_and_ignored(self, env):
        record = _sb_record(
            item_code=env.product.product_code,
            location_code=env.wh_active.warehouse_code,
            qty=1,
            item_description="Some description",
            uom_code=env._uom.uom_code if hasattr(env, "_uom") else "PCS",
        )
        res = env.post(INGEST_SB, [record])
        assert res.status_code == 200, res.text
        entry = res.json()["records"][0]
        assert entry["outcome"] == "created", entry

    def test_item_description_and_uom_code_absent_is_fine(self, env):
        record = _sb_record(
            item_code=env.product.product_code,
            location_code=env.wh_active.warehouse_code,
            qty=1,
        )
        res = env.post(INGEST_SB, [record])
        assert res.status_code == 200, res.text
        assert res.json()["records"][0]["outcome"] == "created"


# =================================================================== AC-SB-11
class TestCompanyScopeAC11:
    def test_other_companys_warehouse_never_resolves(self, env):
        record = _sb_record(
            item_code=env.product.product_code,
            location_code=env.wh_other_company.warehouse_code,
            qty=5,
        )
        res = env.post(INGEST_SB, [record])
        assert res.status_code == 200, res.text
        entry = res.json()["records"][0]
        assert entry["outcome"] == "updated", entry
        assert "warehouse_unresolved" in entry.get("warnings", []), entry

    def test_other_companys_product_never_resolves(self, env):
        record = _sb_record(
            item_code=env.product_other_company.product_code,
            location_code=env.wh_active.warehouse_code,
            qty=5,
        )
        res = env.post(INGEST_SB, [record])
        assert res.status_code == 200, res.text
        entry = res.json()["records"][0]
        assert entry["outcome"] == "retryable", entry

    def test_created_row_carries_the_anchored_company(self, env):
        record = _sb_record(
            item_code=env.product.product_code,
            location_code=env.wh_active.warehouse_code,
            qty=5,
        )
        res = env.post(INGEST_SB, [record])
        assert res.status_code == 200, res.text
        row = env.stock_row(env.product.id, env.wh_active.id)
        assert row is not None
        assert str(row["company_id"]) == env.company_a


# =================================================================== AC-SB-12
class TestDryRunAC12:
    def test_dry_run_writes_nothing_created_has_no_diff(self, env):
        record = _sb_record(
            item_code=env.product.product_code,
            location_code=env.wh_active.warehouse_code,
            qty=5,
        )
        res = env.post(INGEST_SB, [record], dry_run=True)
        assert res.status_code == 200, res.text
        entry = res.json()["records"][0]
        assert entry["outcome"] == "created", entry
        assert "diff" not in entry, entry
        assert env.stock_row(env.product.id, env.wh_active.id) is None

    def test_dry_run_of_a_change_carries_current_vs_incoming_diff(self, env):
        existing = env.make_stock(
            product_id=env.product.id, warehouse_id=env.wh_active.id, quantity_on_hand=10
        )
        record = _sb_record(
            item_code=env.product.product_code,
            location_code=env.wh_active.warehouse_code,
            qty=99,
        )
        res = env.post(INGEST_SB, [record], dry_run=True)
        assert res.status_code == 200, res.text
        entry = res.json()["records"][0]
        assert entry["outcome"] == "updated", entry
        assert entry.get("diff") == {"qty": {"current": 10, "incoming": 99}}, entry
        row = env.stock_by_id(existing.id)
        assert row["quantity_on_hand"] == 10, "dry run must not write"

    def test_real_run_of_a_change_carries_no_diff_key(self, env):
        env.make_stock(product_id=env.product.id, warehouse_id=env.wh_active.id, quantity_on_hand=10)
        record = _sb_record(
            item_code=env.product.product_code,
            location_code=env.wh_active.warehouse_code,
            qty=99,
        )
        res = env.post(INGEST_SB, [record])
        assert res.status_code == 200, res.text
        entry = res.json()["records"][0]
        assert entry["outcome"] == "updated", entry
        assert "diff" not in entry, entry


# =================================================================== AC-SB-13
class TestDuplicatePairInBatchAC13:
    def test_duplicate_pair_last_value_wins(self, env):
        ref1 = _ref("DUP1")
        ref2 = _ref("DUP2")
        rec1 = _sb_record(
            item_code=env.product.product_code,
            location_code=env.wh_active.warehouse_code,
            qty=10,
            ref=ref1,
        )
        rec2 = _sb_record(
            item_code=env.product.product_code,
            location_code=env.wh_active.warehouse_code,
            qty=20,
            ref=ref2,
        )
        res = env.post(INGEST_SB, [rec1, rec2])
        assert res.status_code == 200, res.text
        by_ref = {r["source_ref"]: r for r in res.json()["records"]}
        assert by_ref[ref1]["outcome"] == "created", by_ref[ref1]
        assert by_ref[ref2]["outcome"] == "updated", by_ref[ref2]
        row = env.stock_row(env.product.id, env.wh_active.id)
        assert row is not None
        assert row["quantity_on_hand"] == 20


# =================================================================== AC-SB-14
class TestSummaryShapeAC14:
    def test_summary_shape_and_every_record_echoes_its_source_ref(self, env):
        created = _sb_record(
            item_code=env.product.product_code, location_code=env.wh_active.warehouse_code, qty=1
        )
        existing = env.make_stock(
            product_id=env.special_product.id, warehouse_id=env.wh_active.id, quantity_on_hand=1
        )
        updated = _sb_record(
            item_code=env.special_code, location_code=env.wh_active.warehouse_code, qty=2
        )
        failed = {"source_ref": _ref("FAIL"), "location_code": env.wh_active.warehouse_code, "qty": 1}
        retryable = _sb_record(
            item_code=f"{MARKER}-MISSING-{uuid.uuid4().hex[:6]}",
            location_code=env.wh_active.warehouse_code,
            qty=1,
        )

        records = [created, updated, failed, retryable]
        res = env.post(INGEST_SB, records)
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["summary"] == {
            "total": 4,
            "created": 1,
            "updated": 1,
            "failed": 1,
            "retryable": 1,
        }, body["summary"]
        sent_refs = {r["source_ref"] for r in records}
        got_refs = {r["source_ref"] for r in body["records"]}
        assert sent_refs == got_refs


# =================================================================== AC-SB-15
class TestDeletionsHappyPathAC15:
    def test_resolvable_pair_zeroes_qty_keeps_row(self, env):
        existing = env.make_stock(
            product_id=env.product.id,
            warehouse_id=env.wh_active.id,
            quantity_on_hand=50,
            quantity_reserved=5,
            quantity_damaged=2,
        )
        ref = _ref("DEL1")
        pairs = {
            ref: {
                "item_code": env.product.product_code,
                "location_code": env.wh_active.warehouse_code,
            }
        }
        res = env.delete([ref], pairs)
        assert res.status_code == 200, res.text
        entry = res.json()["records"][0]
        assert entry["outcome"] == "deleted", entry
        row = env.stock_by_id(existing.id)
        assert row is not None, "row must be kept, never hard-deleted"
        assert row["quantity_on_hand"] == 0
        assert row["quantity_reserved"] == 5
        assert row["quantity_damaged"] == 2

    def test_already_zero_is_deleted_again(self, env):
        existing = env.make_stock(
            product_id=env.product.id, warehouse_id=env.wh_active.id, quantity_on_hand=0
        )
        ref = _ref("DEL2")
        pairs = {
            ref: {
                "item_code": env.product.product_code,
                "location_code": env.wh_active.warehouse_code,
            }
        }
        res = env.delete([ref], pairs)
        assert res.status_code == 200, res.text
        assert res.json()["records"][0]["outcome"] == "deleted"
        row = env.stock_by_id(existing.id)
        assert row["quantity_on_hand"] == 0


# =================================================================== AC-SB-16
class TestDeletionsNotFoundAC16:
    def test_missing_pairs_entry_is_not_found(self, env):
        ref = _ref("NOPAIR")
        res = env.delete([ref], {})
        assert res.status_code == 200, res.text
        assert res.json()["records"][0]["outcome"] == "not_found"

    def test_unknown_product_is_not_found(self, env):
        ref = _ref("NOPROD")
        pairs = {
            ref: {
                "item_code": f"{MARKER}-GONE-{uuid.uuid4().hex[:6]}",
                "location_code": env.wh_active.warehouse_code,
            }
        }
        res = env.delete([ref], pairs)
        assert res.status_code == 200, res.text
        assert res.json()["records"][0]["outcome"] == "not_found"

    def test_unknown_warehouse_is_not_found(self, env):
        ref = _ref("NOWH")
        pairs = {
            ref: {
                "item_code": env.product.product_code,
                "location_code": f"{MARKER}-NOWHERE-{uuid.uuid4().hex[:6]}",
            }
        }
        res = env.delete([ref], pairs)
        assert res.status_code == 200, res.text
        assert res.json()["records"][0]["outcome"] == "not_found"

    def test_resolvable_pair_with_no_stock_row_is_not_found(self, env):
        ref = _ref("NOROW")
        pairs = {
            ref: {
                "item_code": env.product.product_code,
                "location_code": env.wh_active.warehouse_code,
            }
        }
        res = env.delete([ref], pairs)
        assert res.status_code == 200, res.text
        assert res.json()["records"][0]["outcome"] == "not_found"

    def test_inactive_warehouse_is_not_found_with_warning_row_untouched(self, env):
        existing = env.make_stock(
            product_id=env.product.id, warehouse_id=env.wh_inactive.id, quantity_on_hand=42
        )
        ref = _ref("INACTDEL")
        pairs = {
            ref: {
                "item_code": env.product.product_code,
                "location_code": env.wh_inactive.warehouse_code,
            }
        }
        res = env.delete([ref], pairs)
        assert res.status_code == 200, res.text
        entry = res.json()["records"][0]
        assert entry["outcome"] == "not_found", entry
        assert "warehouse_inactive" in entry.get("warnings", []), entry
        row = env.stock_by_id(existing.id)
        assert row["quantity_on_hand"] == 42


# =================================================================== AC-SB-17
class TestDeletionsValidationAC17:
    def test_malformed_entry_is_failed(self, env):
        ref = _ref("MALFORMED")
        pairs = {ref: "not-a-dict"}
        res = env.delete([ref], pairs)
        assert res.status_code == 200, res.text
        assert res.json()["records"][0]["outcome"] == "failed"

    def test_pairs_not_an_object_is_422_invalid_body(self, env):
        res = env.client.post(
            DELETE_SB,
            json={
                "companyCode": env.company_a_code,
                "source_refs": [],
                "pairs": ["a", "b"],
            },
        )
        assert res.status_code == 422, res.text
        assert res.json()["code"] == "INVALID_BODY"

    def test_pairs_over_max_batch_is_413(self, env):
        pairs = {
            f"{MARKER}-{i}": {"item_code": "X", "location_code": "Y"}
            for i in range(MAX_BATCH + 1)
        }
        res = env.client.post(
            DELETE_SB,
            json={
                "companyCode": env.company_a_code,
                "source_refs": list(pairs.keys())[:5],
                "pairs": pairs,
            },
        )
        assert res.status_code == 413, res.text
        assert res.json()["code"] == "BATCH_TOO_LARGE"

    def test_dry_run_deletion_writes_nothing(self, env):
        existing = env.make_stock(
            product_id=env.product.id, warehouse_id=env.wh_active.id, quantity_on_hand=77
        )
        ref = _ref("DRYDEL")
        pairs = {
            ref: {
                "item_code": env.product.product_code,
                "location_code": env.wh_active.warehouse_code,
            }
        }
        res = env.delete([ref], pairs, dry_run=True)
        assert res.status_code == 200, res.text
        assert res.json()["records"][0]["outcome"] == "deleted"
        row = env.stock_by_id(existing.id)
        assert row["quantity_on_hand"] == 77, "dry run must not actually zero it"


# =================================================================== AC-SB-18
class TestPermissionGuardAC18:
    """The real RBAC guard, on an empty schema of its own - mirrors
    `test_ingest_brands.py::TestPermissionGuardAC9`. `stock_balances` is not
    yet in `INGEST_PERMISSIONS`/`DELETE_PERMISSIONS` (D1/D9), so every case
    here 404s ("unknown_entity") today, on BOTH keys, rather than 403/200 -
    that 404 is what this file pins as red-for-the-right-reason. It turns
    into a real 403/200 test the moment the coder adds
    `"stock_balances": "inventory.stock.edit"` etc to the live maps (imported
    by reference below, never copied)."""

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

        @api.post("/ingest/{entity}/deletions")
        def _delete_stub(
            entity: str,
            _: dict = Depends(
                require_external_permission_for_path(ingest_module.DELETE_PERMISSIONS)
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

        edit_slug = "inventory.stock.edit"
        view_slug = "inventory.stock.view"
        delete_slug = "inventory.stock.delete"
        perms = {}
        for slug in (edit_slug, view_slug, delete_slug):
            perm = UserPermission(slug=slug, name=slug)
            guard_db.add(perm)
            guard_db.flush()
            perms[slug] = perm

        issued = {}
        for label, held in (
            ("editor", [edit_slug]),
            ("viewer", [view_slug]),
            ("deleter", [delete_slug]),
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
                name=f"{MARKER}-{label}",
                type="autocount_esb",
                act_as_user_id=user.id,
                is_active=True,
            )
            guard_db.add(integration)
            guard_db.flush()
            issued[label] = IntegrationKeyService(guard_db).issue_key(integration)
        return issued

    def test_a_key_without_edit_is_403_on_ingest_naming_it(self, guard_client, keys):
        res = guard_client.post(
            "/ingest/stock_balances", headers={"X-API-Key": keys["viewer"]}
        )
        assert res.status_code == 403, res.text
        assert "inventory.stock.edit" in res.text

    def test_the_edit_slug_passes_ingest(self, guard_client, keys):
        res = guard_client.post(
            "/ingest/stock_balances", headers={"X-API-Key": keys["editor"]}
        )
        assert res.status_code == 200, res.text

    def test_a_key_without_delete_is_403_on_deletions_naming_it(self, guard_client, keys):
        res = guard_client.post(
            "/ingest/stock_balances/deletions", headers={"X-API-Key": keys["editor"]}
        )
        assert res.status_code == 403, res.text
        assert "inventory.stock.delete" in res.text

    def test_the_delete_slug_passes_deletions(self, guard_client, keys):
        res = guard_client.post(
            "/ingest/stock_balances/deletions", headers={"X-API-Key": keys["deleter"]}
        )
        assert res.status_code == 200, res.text


class TestMigrationGrantAC18:
    """D9: the migration grants `inventory.stock.{view,edit,delete}` to
    `integration_foundryx_esb`.

    Run for real via the CLI (`alembic upgrade head`) against THIS
    worktree's OWN private database (`sorento_sbp_ci`) rather than the
    guessed-migration-filename `apply()`/`revert()` convention used
    elsewhere in this suite (`test_migration_brands_grant.py`,
    `test_migration_445_grant_sweep.py`) - that convention exists because
    those tests run against the shared local dev database, whose
    `alembic_version` tracks a DIFFERENT branch, so stepping it there would
    move a stamp every other worktree relies on. This database belongs to
    this worktree alone and was stamped to the pre-SR5a head by
    `scripts/bootstrap_env.py` (see the tester's setup notes) - a real
    `alembic upgrade head` here applies ONLY the coder's own new
    migration(s), exactly as CI's `check-migration-heads`/deploy path would,
    and is safe to run from a test because it is idempotent both ways (D9,
    mirroring `511_brands_esb_grant.py`): a second run is a no-op.

    `integration_foundryx_esb` does not exist on a freshly bootstrapped
    database (checked directly: 0 rows), so it is seeded here first, inside
    the SAME connection `alembic upgrade head`'s migration will read -
    committed (not rolled back) so the subprocess's own connection can see
    it, and cleaned up in a `finally` so re-running this test is safe.
    """

    _ESB_ROLE_SLUG = "integration_foundryx_esb"
    _TARGET_SLUGS = (
        "inventory.stock.view",
        "inventory.stock.edit",
        "inventory.stock.delete",
    )

    def test_alembic_upgrade_head_grants_the_esb_role(self):
        import subprocess

        backend_dir = Path(__file__).resolve().parent.parent

        with engine.connect() as conn:
            existing = conn.execute(
                text("SELECT id FROM user_roles WHERE slug = :s"),
                {"s": self._ESB_ROLE_SLUG},
            ).first()
            seeded_role = existing is None
            if seeded_role:
                role_id = str(uuid.uuid4())
                conn.execute(
                    text(
                        "INSERT INTO user_roles (id, slug, name, description, "
                        "is_protected, is_default, is_trashed) VALUES "
                        "(:i, :s, :n, :d, false, false, false)"
                    ),
                    {
                        "i": role_id,
                        "s": self._ESB_ROLE_SLUG,
                        "n": f"{MARKER} ESB role",
                        "d": f"{MARKER} scratch",
                    },
                )
                conn.commit()
            else:
                role_id = str(existing[0])

        try:
            result = subprocess.run(
                [sys.executable, "-m", "alembic", "upgrade", "head"],
                cwd=backend_dir,
                capture_output=True,
                text=True,
            )
            assert result.returncode == 0, result.stdout + "\n" + result.stderr

            with engine.connect() as conn:
                for slug in self._TARGET_SLUGS:
                    count = conn.execute(
                        text(
                            "SELECT count(*) FROM user_role_permissions rp "
                            "JOIN user_permissions p ON p.id = rp.permission_id "
                            "WHERE rp.role_id = :r AND p.slug = :s"
                        ),
                        {"r": role_id, "s": slug},
                    ).scalar()
                    assert count == 1, (
                        f"{slug} not granted to {self._ESB_ROLE_SLUG} after "
                        "alembic upgrade head"
                    )
        finally:
            if seeded_role:
                with engine.begin() as conn:
                    conn.execute(
                        text("DELETE FROM user_role_permissions WHERE role_id = :r"),
                        {"r": role_id},
                    )
                    conn.execute(text("DELETE FROM user_roles WHERE id = :r"), {"r": role_id})


# =================================================================== AC-SB-19
class TestReadBackAC19:
    def test_read_returns_records_and_not_found(self, env):
        env.make_stock(product_id=env.product.id, warehouse_id=env.wh_active.id, quantity_on_hand=33)
        ref = _ref("READ1")
        missing_ref = _ref("READMISS")
        pairs = {
            ref: {
                "item_code": env.product.product_code,
                "location_code": env.wh_active.warehouse_code,
            }
        }
        res = env.read([ref, missing_ref], pairs)
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["not_found"] == [missing_ref], body
        got = {r["source_ref"]: r["qty"] for r in body["records"]}
        assert got == {ref: 33}, body


# =================================================================== AC-SB-20
class TestFixturesAC20:
    @pytest.mark.skip(reason="awaiting corrected Foundryx A7 fixtures")
    def test_corrected_a7_fixtures_replay_against_seeded_chain(self, env):
        # Fixtures land at tests/fixtures/stock_balances/*.json (source_ref,
        # entity_id, diff, summary, deletions shape corrected per the
        # tester brief: no fake entity_id, no diff on a created row, no
        # warningCounts, no deletions `retryable` key). Loaded here once
        # they exist; this test intentionally does no fixture loading yet.
        pass
