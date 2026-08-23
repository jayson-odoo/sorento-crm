"""An /external match-by-code resolves inside ONE company, not by row order.

The defect this pins: an ``X-API-Key`` call that carries no ``contact_id`` /
``space_id`` resolves to scope ``None`` = ALL companies
(``company_scope_resolver._resolve_api_key_scope``). ``product_code`` is unique
PER COMPANY only (``uq_products_company_product_code``, migration 305), and on
the live database 11k+ codes exist in both companies - so ``get_products_by_code``
built its ``{code: product}`` dict from an unordered ``.all()`` and kept whichever
row the scan returned last. GRN and SPO-allocation posts therefore bound goods to
an arbitrary company's product.

The fix is not "return all of them": the two candidates ARE the same product in
different companies and only one is right. The payload has to name its company
through something globally unique - a warehouse code, a container number, an SPO -
and ``pin_scope_to_companies`` pins the request to it before any code is matched.

Substrate: Postgres only, on the shared blank schema whose writes are discarded
(group T). Every test seeds its own chain under a ZZTANCH marker; nothing is
borrowed and nothing asserts about a production row.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

# MUST be the first app import - resolves the circular import in
# app.modules.runtime.guards.
from app.main import app  # noqa: E402

from app.api.v1.external.utils import get_products_by_code, pin_scope_to_companies
from app.models.company import Company
from app.models.inventory import Warehouse
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.services.company_scope import DEFAULT_COMPANY_ID

from ._pg_fixture import blank_session, unique_code

MARKER = "ZZTANCH"
GRN = "/api/v1/external/grn/"

_USER_ID = "5b8b9c10-1111-4222-8333-444455556661"
_ROLE_ID = "5b8b9c10-2222-4222-8333-444455556662"


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
        suffix = uuid.uuid4().hex[:8]
        # The incumbent is auto-seeded by conftest; the second company is ours.
        self.company_a = DEFAULT_COMPANY_ID
        other = Company(
            id=str(uuid.uuid4()), name=f"{MARKER} B {suffix}", code=f"ZB{suffix}"
        )
        db.add(other)
        db.flush()
        self.company_b = str(other.id)
        self._category = ProductCategory(
            category_code=unique_code(MARKER), category_name=f"{MARKER} category"
        )
        self._uom = UnitOfMeasure(uom_code=unique_code(MARKER), uom_name=f"{MARKER} unit")
        db.add_all([self._category, self._uom])
        db.flush()

    def product(self, code: str, company_id: str) -> Product:
        row = Product(
            product_code=code,
            product_name=f"{MARKER} {code}",
            category_id=self._category.id,
            base_uom_id=self._uom.id,
            list_price=10,
            company_id=company_id,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def warehouse(self, code: str, company_id: str) -> Warehouse:
        row = Warehouse(
            warehouse_code=code,
            warehouse_name=f"{MARKER} {code}",
            company_id=company_id,
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

        # THE POINT OF THIS SUITE: reproduce the real n8n principal, which sends
        # X-API-Key with no contact identity and therefore arrives scoped to ALL
        # companies. Pinning a company here would hide the very defect under test.
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


# ------------------------------------------------------ the helper's own rules
def test_one_anchor_company_pins_the_request(env):
    resolved = pin_scope_to_companies(env.db, [env.company_b], anchor="test")
    assert resolved == env.company_b

    code = f"{MARKER}-PIN-{uuid.uuid4().hex[:6]}"
    env.product(code, env.company_a)
    wanted = env.product(code, env.company_b)

    # Same code in both companies; the pinned scope decides which one resolves.
    found = get_products_by_code(env.db, [code])
    assert {str(p.id) for p in found.values()} == {str(wanted.id)}


def test_no_anchor_falls_back_to_the_incumbent_company(env):
    """Deterministic beats arbitrary. Every pre-multi-company row carries the
    incumbent id, so that is what these integrations were effectively resolving
    to already - the same rule `_portal_token_scope` uses."""
    assert pin_scope_to_companies(env.db, [], anchor="test") == DEFAULT_COMPANY_ID

    code = f"{MARKER}-FALL-{uuid.uuid4().hex[:6]}"
    incumbent = env.product(code, env.company_a)
    env.product(code, env.company_b)

    found = get_products_by_code(env.db, [code])
    assert {str(p.id) for p in found.values()} == {str(incumbent.id)}


def test_anchors_spanning_two_companies_are_a_400_not_a_guess(env):
    with pytest.raises(HTTPException) as excinfo:
        pin_scope_to_companies(
            env.db, [env.company_a, env.company_b], anchor="This GRN's warehouses"
        )
    assert excinfo.value.status_code == 400
    assert "more than one company" in excinfo.value.detail["message"]


# --------------------------------------------------------------- the GRN route
def test_grn_binds_the_product_of_the_company_its_warehouse_belongs_to(env):
    """The regression. Two companies hold the same product code; the GRN names a
    warehouse in the second. Before the fix the line could bind either one."""
    code = f"{MARKER}-GRN-{uuid.uuid4().hex[:6]}"
    # The WRONG company's row is inserted LAST on purpose. Unscoped,
    # `get_products_by_code` builds `{code: product}` from an unordered `.all()`,
    # so the last row scanned wins the key - on a freshly written table that is
    # this one. Seeded the other way round the old code passes by luck and the
    # test guards nothing.
    wanted = env.product(code, env.company_b)
    env.product(code, env.company_a)
    warehouse = env.warehouse(f"{MARKER}WH{uuid.uuid4().hex[:6]}", env.company_b)
    env.db.commit()

    from app.models.procurement import PickingHeader, PickingLine

    picking_number = f"{MARKER}-{uuid.uuid4().hex[:6]}"
    response = env.client.post(
        GRN,
        json={
            "goods_receive_notes": {
                "picking_number": picking_number,
                "picking_date": "2026-03-10",
            },
            "grn_lines": [
                {"product_code": code, "quantity": 2, "location": warehouse.warehouse_code}
            ],
        },
    )
    assert response.status_code == 201, response.text

    header = (
        env.db.query(PickingHeader)
        .filter(PickingHeader.picking_number == picking_number)
        .one()
    )
    line = env.db.query(PickingLine).filter(PickingLine.picking_header_id == header.id).one()
    assert str(line.product_id) == str(wanted.id)
