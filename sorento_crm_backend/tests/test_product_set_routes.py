"""S1 phase 2: the product-set CRUD the authoring screen calls.

The frontend was built against a mock first, with the contract written at the top
of `productSetService.ts`. These tests hold the backend to that contract, so the
two halves meet rather than drift.

A set is NOT orderable, so there is deliberately no stock write, no costing and
no order route here - only the master a person authors and the read the detail
page renders.

UAC groups A and B (the FE behaviour they back), C and D (the model and price).
Plan: `documentation/plans/master-data/PLAN-product-sets.md`.
"""
from __future__ import annotations

import os
import uuid
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.database import SessionLocal, engine
from app.models.company import Company
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.product_set import ProductSet, ProductSetMember
from app.services.company_scope import (
    DEFAULT_COMPANY_ID,
    company_scope,
    register_company_scope_listeners,
)
from app.services.error_handler import AppException
from app.services.product_set_service import ProductSetService

register_company_scope_listeners()

pytestmark = pytest.mark.skipif(
    os.environ.get("SKIP_LIVE_DB_TESTS") == "1",
    reason="SKIP_LIVE_DB_TESTS=1",
)


def _uid(stem: str) -> str:
    return f"ZZT-{stem}-{uuid.uuid4().hex[:8]}"


@pytest.fixture()
def db() -> Session:
    """A session whose writes are DISCARDED, even when the code under test commits.

    `SessionLocal()` + `begin_nested()` is not enough and it silently leaks: the
    service calls `db.commit()`, which commits the OUTER transaction rather than
    releasing a savepoint, so the fixture's rollback has nothing left to undo and
    every ZZT row lands in the shared database for good. That is what happened
    here - 99 sets, 407 products and 204 companies had to be swept back out.

    Binding to a connection that already holds a transaction, with
    `join_transaction_mode="create_savepoint"`, is what makes a committing test
    safe: its commits land on a savepoint inside the outer transaction, visible
    to the test and to the code under it, and the outer rollback still discards
    everything. Same approach as `tests/_pg_fixture.blank_session`.
    """
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        with company_scope(session, None):
            yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture()
def world(db: Session):
    company = Company(id=str(uuid.uuid4()), name=_uid("co"), code=_uid("C")[:20])
    other = Company(id=str(uuid.uuid4()), name=_uid("co2"), code=_uid("C2")[:20])
    category = ProductCategory(
        id=str(uuid.uuid4()), category_code=_uid("cat")[:50], category_name=_uid("cat")
    )
    uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code=_uid("u")[:20], uom_name=_uid("uom"))
    db.add_all([company, other, category, uom])
    db.flush()

    def product(stem: str, price: str, company_id: str) -> Product:
        row = Product(
            id=str(uuid.uuid4()),
            product_code=_uid(stem),
            product_name=_uid(stem),
            category_id=category.id,
            base_uom_id=uom.id,
            list_price=Decimal(price),
            company_id=company_id,
        )
        db.add(row)
        db.flush()
        return row

    return {
        "company": company,
        "other": other,
        "pedestal": product("pedestal", "1180.00", company.id),
        "cistern": product("cistern", "0.00", company.id),
        "seat": product("seat", "85.00", company.id),
        "foreign": product("foreign", "9.00", other.id),
    }


def _service(db: Session, company) -> ProductSetService:
    return ProductSetService(db)


def _create(db: Session, world, **overrides):
    payload = {
        "set_code": _uid("set"),
        "name": "S-trap assembly",
        "members": [
            {"product_code": world["pedestal"].product_code, "quantity": 1,
             "contributes_to_price": True, "sort_order": 0},
            {"product_code": world["cistern"].product_code, "quantity": 1,
             "contributes_to_price": False, "sort_order": 1},
        ],
    }
    payload.update(overrides)
    with company_scope(db, frozenset({str(world["company"].id)})):
        return _service(db, world["company"]).create(payload, created_by=None)


# ------------------------------------------------------------------- creating


def test_a_set_is_created_with_its_members_by_product_code(db: Session, world):
    """The screen sends codes, never UUIDs. Resolution happens server-side."""
    created = _create(db, world)

    assert created.set_code
    assert [m.product_id for m in created.members] == [
        world["pedestal"].id,
        world["cistern"].id,
    ]


def test_the_computed_price_comes_back_on_create(db: Session, world):
    """AC-B.1 - the header shows a price the moment the set exists."""
    created = _create(db, world)
    with company_scope(db, frozenset({str(world["company"].id)})):
        detail = _service(db, world["company"]).get(created.id)
    assert detail.price.computed == Decimal("1180.00")


def test_a_duplicate_set_code_in_one_company_is_refused(db: Session, world):
    """The FE surfaces this as "already exists", so it must be a clean 409."""
    first = _create(db, world)
    with pytest.raises(AppException) as excinfo:
        _create(db, world, set_code=first.set_code)
    assert excinfo.value.status_code == 409


def test_the_same_code_is_free_in_another_company(db: Session, world):
    """AC-C.2 - Sorento and Mocha both legitimately carry the same codes."""
    first = _create(db, world)
    with company_scope(db, frozenset({str(world["other"].id)})):
        twin = _service(db, world["other"]).create(
            {"set_code": first.set_code, "name": "same code, other company", "members": []},
            created_by=None,
        )
    assert twin.id != first.id


def test_a_member_code_that_names_no_product_is_refused_by_name(db: Session, world):
    """Naming the code is the difference between a fix and a guess."""
    with pytest.raises(AppException) as excinfo:
        _create(db, world, members=[
            {"product_code": "ZZT-NO-SUCH-PRODUCT", "quantity": 1,
             "contributes_to_price": True, "sort_order": 0},
        ])
    assert "ZZT-NO-SUCH-PRODUCT" in str(excinfo.value.detail)


def test_another_companys_product_cannot_be_made_a_member(db: Session, world):
    """Membership crossing companies would leak one catalogue into the other."""
    with pytest.raises(AppException):
        _create(db, world, members=[
            {"product_code": world["foreign"].product_code, "quantity": 1,
             "contributes_to_price": True, "sort_order": 0},
        ])


# -------------------------------------------------------------------- reading


def test_the_detail_read_orders_members_and_carries_stock_fields(db: Session, world):
    created = _create(db, world)
    with company_scope(db, frozenset({str(world["company"].id)})):
        detail = _service(db, world["company"]).get(created.id)

    assert [m.sort_order for m in detail.members] == [0, 1]
    # Stock is answered per member; None is legal (no stock rows), 0 is not the
    # same thing and must not be substituted for it.
    assert all(hasattr(m, "available") for m in detail.members)


def test_a_set_from_another_company_is_a_404_not_a_403(db: Session, world):
    """A scoped reader must not learn that another company's set exists."""
    created = _create(db, world)
    with company_scope(db, frozenset({str(world["other"].id)})):
        with pytest.raises(AppException) as excinfo:
            _service(db, world["other"]).get(created.id)
    assert excinfo.value.status_code == 404


def test_the_listing_finds_a_set_by_code_and_by_name(db: Session, world):
    created = _create(db, world, name="Washdown rimless")
    with company_scope(db, frozenset({str(world["company"].id)})):
        service = _service(db, world["company"])
        by_code = service.list(page=1, limit=50, query=created.set_code)
        by_name = service.list(page=1, limit=50, query="Washdown rimless")

    assert created.id in {row.id for row in by_code.data}
    assert created.id in {row.id for row in by_name.data}


# -------------------------------------------------------------------- editing


def test_replacing_members_replaces_them_wholesale(db: Session, world):
    """`members: []` empties it; omitting the key leaves membership alone."""
    created = _create(db, world)
    with company_scope(db, frozenset({str(world["company"].id)})):
        service = _service(db, world["company"])
        service.update(created.id, {"members": [
            {"product_code": world["seat"].product_code, "quantity": 2,
             "contributes_to_price": True, "sort_order": 0},
        ]}, updated_by=None)
        after = service.get(created.id)

    assert [m.product_id for m in after.members] == [world["seat"].id]
    assert after.price.computed == Decimal("170.00")  # 85 x 2


def test_omitting_members_leaves_membership_untouched(db: Session, world):
    created = _create(db, world)
    with company_scope(db, frozenset({str(world["company"].id)})):
        service = _service(db, world["company"])
        service.update(created.id, {"name": "renamed only"}, updated_by=None)
        after = service.get(created.id)

    assert after.name == "renamed only"
    assert len(after.members) == 2


def test_an_override_is_stamped_with_who_and_when(db: Session, world):
    """AC-B.2 - the badge names the person, so it needs the person recorded."""
    created = _create(db, world)
    actor = str(uuid.uuid4())
    with company_scope(db, frozenset({str(world["company"].id)})):
        service = _service(db, world["company"])
        service.update(created.id, {"list_price_override": Decimal("1150.00")}, updated_by=actor)
        after = service.get(created.id)

    assert after.price.override == Decimal("1150.00")
    assert after.price.resolved == Decimal("1150.00")
    assert after.price.computed == Decimal("1180.00")
    assert after.override_set_by == actor


def test_clearing_the_override_returns_the_set_to_its_computed_price(db: Session, world):
    """AC-B.3 - null means computed, and the stamp goes with it."""
    created = _create(db, world)
    with company_scope(db, frozenset({str(world["company"].id)})):
        service = _service(db, world["company"])
        actor = str(uuid.uuid4())
        service.update(created.id, {"list_price_override": Decimal("1150.00")}, updated_by=actor)
        service.update(created.id, {"list_price_override": None}, updated_by=actor)
        after = service.get(created.id)

    assert after.price.override is None
    assert after.price.resolved == Decimal("1180.00")
    assert after.override_set_by is None


# ------------------------------------------------------------------- deleting


def test_deleting_a_set_is_a_hard_delete_that_spares_the_products(db: Session, world):
    """AC-A.6 - hard delete. Members go; the products they name do not."""
    created = _create(db, world)
    member_ids = [m.id for m in created.members]

    with company_scope(db, frozenset({str(world["company"].id)})):
        _service(db, world["company"]).delete(created.id)

    assert db.query(ProductSet).filter(ProductSet.id == created.id).first() is None
    assert db.query(ProductSetMember).filter(ProductSetMember.id.in_(member_ids)).count() == 0
    assert db.query(Product).filter(Product.id == world["pedestal"].id).first() is not None


def test_deleting_another_companys_set_is_a_404(db: Session, world):
    created = _create(db, world)
    with company_scope(db, frozenset({str(world["other"].id)})):
        with pytest.raises(AppException) as excinfo:
            _service(db, world["other"]).delete(created.id)
    assert excinfo.value.status_code == 404


# ---------------------------------------------------- the write path under `None`
#
# An `X-API-Key` caller with no `contact_id`/`space_id` resolves to `None` (all
# companies) - the scope migration 414 grants `master_data.product_sets.add`/
# `.edit`/`.delete` to `integration_n8n` and `integration_sorento_mcp` for.
# `set_code` and `product_code` are both unique PER COMPANY only, so an
# unscoped code lookup here would pick a company by physical row order rather
# than refusing or resolving deterministically - 11k+ codes exist in both
# companies. `pin_scope_to_companies` / `resolve_write_company_id` are what the
# service now pins to before any such lookup runs.


@pytest.fixture()
def cross_company_world(db: Session, world):
    """A product carrying the SAME code as one of `world`'s, but in `world["other"]`.

    The shape that breaks an unscoped lookup: two rows, two companies, one code.
    """
    shared_code = _uid("shared")
    incumbent = Product(
        id=str(uuid.uuid4()),
        product_code=shared_code,
        product_name=_uid("shared"),
        category_id=world["pedestal"].category_id,
        base_uom_id=world["pedestal"].base_uom_id,
        list_price=Decimal("42.00"),
        company_id=DEFAULT_COMPANY_ID,
    )
    other = Product(
        id=str(uuid.uuid4()),
        product_code=shared_code,
        product_name=_uid("shared"),
        category_id=world["pedestal"].category_id,
        base_uom_id=world["pedestal"].base_uom_id,
        list_price=Decimal("9.00"),
        company_id=world["other"].id,
    )
    db.add_all([incumbent, other])
    db.flush()
    return {"shared_code": shared_code, "incumbent_product": incumbent, "other_product": other}


def test_create_under_none_scope_pins_to_the_incumbent_company(db: Session, cross_company_world):
    """Regression: before the pin, `_replace_members`'s code lookup ran under the
    RAW `None` scope and could resolve `shared_code` to either company's row by
    row order. Pinned first, it resolves to the SAME company the new set's own
    `company_id` is about to be auto-stamped into (the incumbent, DEFAULT_COMPANY_ID)."""
    with company_scope(db, None):
        created = ProductSetService(db).create(
            {
                "set_code": _uid("set"),
                "name": "created under an all-companies caller",
                "members": [
                    {"product_code": cross_company_world["shared_code"], "quantity": 1,
                     "contributes_to_price": True, "sort_order": 0},
                ],
            },
            created_by=None,
        )

    assert created.company_id == DEFAULT_COMPANY_ID
    assert [m.product_id for m in created.members] == [
        cross_company_world["incumbent_product"].id
    ]


def test_update_under_none_scope_resolves_a_new_member_to_the_sets_own_company(
    db: Session, world, cross_company_world
):
    """Regression: `_require` loads by id (unambiguous even under `None`), but the
    OLD code let the follow-up member lookup run unscoped anyway, so a member
    added on edit could land on the wrong company's product. Pinned to the SET's
    own company (`world["other"]`), it must resolve to THAT company's row."""
    with company_scope(db, frozenset({str(world["other"].id)})):
        created = ProductSetService(db).create(
            {"set_code": _uid("set"), "name": "other company's set", "members": []},
            created_by=None,
        )

    with company_scope(db, None):
        updated = ProductSetService(db).update(
            created.id,
            {"members": [
                {"product_code": cross_company_world["shared_code"], "quantity": 1,
                 "contributes_to_price": True, "sort_order": 0},
            ]},
            updated_by=None,
        )

    assert [m.product_id for m in updated.members] == [cross_company_world["other_product"].id]


def test_a_per_company_duplicate_code_is_still_accepted_under_none_scope(
    db: Session, world
):
    """Regression, the OTHER failure mode: the OLD `_reject_duplicate_code` ran
    under the RAW `None` scope (no company predicate at all), so it saw EVERY
    company's sets and would 409 a code that is only taken in a DIFFERENT
    company than the one this write is about to land in. AC-C.2's guarantee -
    a code is free per company - must hold for a `None`-scope caller too."""
    with company_scope(db, frozenset({str(world["other"].id)})):
        first = ProductSetService(db).create(
            {"set_code": _uid("dup"), "name": "other company's set", "members": []},
            created_by=None,
        )

    with company_scope(db, None):
        # `None` pins to the incumbent (DEFAULT_COMPANY_ID) - a DIFFERENT
        # company from `world["other"]` - so the same code must be free here.
        twin = ProductSetService(db).create(
            {"set_code": first.set_code, "name": "incumbent set, same code", "members": []},
            created_by=None,
        )

    assert twin.company_id == DEFAULT_COMPANY_ID
    assert twin.id != first.id


# ------------------------------------------------------- the routes themselves
#
# Everything above exercises the SERVICE. That is not enough on its own: the
# detail route shipped a 500 because `validate_uuid_path(value, "Product Set")`
# passed a keyword-only argument positionally, and no service test could see it.
# These call the app, so a wiring mistake between the router and the service
# fails here rather than in a browser.


@pytest.fixture()
def client(db: Session, monkeypatch):
    """A client whose actor is allowed through the permission gate.

    The gate itself is NOT what these tests are for - RBAC has its own suite, and
    seeding a user, a role and four grants here would test that instead of the
    thing that actually broke. `check_user_has_permission` is patched so the
    request reaches the handler, which is where the wiring bug lived.
    """
    from fastapi.testclient import TestClient

    from app.database import get_db
    from app.dependencies import get_current_user, get_current_user_or_api_key
    from app.main import app
    from app.services.company_scope_resolver import apply_company_scope
    from app.services.user_service import UserPermissionService

    monkeypatch.setattr(
        UserPermissionService, "check_user_has_permission", lambda self, *a, **k: True
    )

    actor = {"id": str(uuid.uuid4()), "email": "zzt@example.com", "role": "superadmin"}
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: dict(actor)
    app.dependency_overrides[get_current_user_or_api_key] = lambda: dict(actor)
    # The request-scope resolver reads the caller's ACTIVE company and fail-closes
    # when there is none, so a synthetic actor sees nothing and every detail read
    # is a 404. Neutralised here so the session keeps the scope the fixture set;
    # the resolver has its own tests, and isolation is asserted above at the
    # service level where the scope can be stated explicitly.
    app.dependency_overrides[apply_company_scope] = lambda: None
    try:
        yield TestClient(app, raise_server_exceptions=False)
    finally:
        app.dependency_overrides.clear()


BASE = "/api/v1/master-data/product-sets"


def test_the_list_route_answers(client, world):
    response = client.get(f"{BASE}/")
    assert response.status_code == 200, response.text
    assert "data" in response.json()


def test_the_detail_route_answers_and_carries_every_declared_field(client, db, world):
    """The regression that shipped: this route 500d on a keyword-only argument.

    Also asserts the declared fields are actually present - `response_model`
    drops what it was not told about, so a field can be computed correctly and
    still never reach the screen.
    """
    created = _create(db, world)
    response = client.get(f"{BASE}/{created.id}")
    assert response.status_code == 200, response.text

    body = response.json()
    for field in (
        "set_code", "name", "price", "member_count",
        "complete_sets", "limiting_member_code", "members",
    ):
        assert field in body, f"{field} was dropped on the way out"
    assert {"computed", "override", "resolved", "is_overridden", "reason"} <= set(body["price"])


def test_a_malformed_id_is_a_404_not_a_500(client):
    """A bad-format id is a guaranteed-missing row, so one code for clients."""
    assert client.get(f"{BASE}/not-a-uuid").status_code == 404


def test_the_delete_route_answers_204(client, db, world):
    created = _create(db, world)
    assert client.delete(f"{BASE}/{created.id}").status_code == 204


def test_an_override_stamp_survives_the_audit_listener(db: Session, world):
    """`product_sets` is audit-tracked, and the listener snapshots the row into
    `audit_logs.new_values` as JSON at flush. The stamp used to be assigned as the SQL
    expression `func.now()`, which is not a value until the database evaluates it, so
    the snapshot failed with "Object of type now is not JSON serializable" whenever the
    listeners were registered in the same process - true in the app, and in CI when a
    sibling test registered them first. The stamp has to be a real datetime.
    """
    from app.services.audit_service import register_audit_listeners

    register_audit_listeners()
    created = _create(db, world)
    actor = str(uuid.uuid4())
    with company_scope(db, frozenset({str(world["company"].id)})):
        service = _service(db, world["company"])
        service.update(created.id, {"list_price_override": Decimal("1150.00")}, updated_by=actor)
        after = service.get(created.id)

    assert after.override_set_by == actor
    db.expire_all()
    row = db.get(ProductSet, created.id)
    assert row is not None and row.override_set_at is not None
