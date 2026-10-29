"""ITEM-CLASS: Item Classes reference API, product list column/filter/sort, product form field.

PLAN: documentation/plans/products/PLAN-item-class-29oct.md D4. Substrate: a blank Postgres
scratch schema rolled back per test (`tests._pg_fixture.blank_session`), a superadmin principal.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

# MUST be the first app import - resolves the circular import in app.modules.runtime.guards.
from app.main import app  # noqa: E402

from app.models.product import Brand, ItemClass, Product
from app.services.company_scope import DEFAULT_COMPANY_ID

from ._mc_lookup_seed import product
from ._pg_fixture import blank_session, unique_code

BASE = "/api/v1/master-data/item-classes"
PRODUCTS = "/api/v1/master-data/products"
MARKER = "ZZTICA"
_USER_ID = "7d0dad32-1111-4222-8333-4444555588f1"
_ROLE_ID = "7d0dad32-2222-4222-8333-4444555588f2"


def _seed_principal(db) -> None:
    from app.models.user import User, UserRole, UserRoleAssignment

    db.add(UserRole(id=_ROLE_ID, slug="superadmin", name=f"{MARKER} Superadmin", description="",
                    is_protected=True, is_default=False))
    db.flush()
    db.add(User(id=_USER_ID, name=f"{MARKER} admin", email=f"{MARKER.lower()}@test.com", password="x",
                status="active"))
    db.flush()
    db.add(UserRoleAssignment(user_id=_USER_ID, role_id=_ROLE_ID))
    db.flush()


@pytest.fixture
def env():
    from app.dependencies import get_current_user, get_current_user_or_api_key, get_db
    from app.models.base import set_company_scope
    from app.services.company_scope_resolver import apply_company_scope

    with blank_session() as db:
        _seed_principal(db)
        db.commit()

        def _db():
            yield db

        def _user():
            return {"id": _USER_ID, "email": f"{MARKER.lower()}@test.com"}

        def _scope():
            set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
            return None

        app.dependency_overrides[get_db] = _db
        app.dependency_overrides[get_current_user] = _user
        app.dependency_overrides[get_current_user_or_api_key] = _user
        app.dependency_overrides[apply_company_scope] = _scope
        try:
            with TestClient(app) as client:
                set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
                yield client, db
        finally:
            app.dependency_overrides.clear()


def _class(db, name: str, active: bool = True) -> ItemClass:
    row = ItemClass(id=str(uuid.uuid4()), item_class_code=unique_code(name)[:50],
                    item_class_name=f"{MARKER} {name}", company_id=DEFAULT_COMPANY_ID, is_active=active)
    db.add(row)
    db.flush()
    return row


def _brand(db, name: str) -> Brand:
    row = Brand(id=str(uuid.uuid4()), brand_code=unique_code(name)[:50], brand_name=f"{MARKER} {name}",
                company_id=DEFAULT_COMPANY_ID)
    db.add(row)
    db.flush()
    return row


def _product(db, *, brand=None, item_class=None) -> Product:
    row = product(db, company_id=DEFAULT_COMPANY_ID, code=unique_code(MARKER, alpha=True))
    row.brand_id = brand.id if brand else None
    row.item_class_id = item_class.id if item_class else None
    db.flush()
    return row


# --------------------------------------------------------------------- reference CRUD


def test_create_read_update_list(env) -> None:
    client, db = env
    code = unique_code("SERENE")[:50]
    res = client.post(BASE + "/", json={"item_class_code": code, "item_class_name": "Serene"})
    assert res.status_code == 201, res.text
    created = res.json()
    assert created["item_class_code"] == code and created["is_active"] is True

    res = client.get(f"{BASE}/{created['id']}")
    assert res.status_code == 200 and res.json()["product_count"] == 0

    res = client.put(f"{BASE}/{created['id']}", json={"item_class_name": "Serene Range"})
    assert res.status_code == 200 and res.json()["item_class_name"] == "Serene Range"

    res = client.get(BASE + "/", params={"query": code})
    assert res.status_code == 200
    assert [r["id"] for r in res.json()["data"]] == [created["id"]]


def test_duplicate_code_any_case_is_a_conflict(env) -> None:
    client, db = env
    row = _class(db, "DUP")
    db.commit()
    res = client.post(BASE + "/", json={"item_class_code": f"  {row.item_class_code.lower()} ",
                                        "item_class_name": "x"})
    assert res.status_code == 409, res.text


def test_list_counts_products_and_sorts_by_name(env) -> None:
    client, db = env
    b = _class(db, "BBB")
    a = _class(db, "AAA")
    _product(db, item_class=a)
    _product(db, item_class=a)
    db.commit()
    res = client.get(BASE + "/", params={"query": MARKER, "sort": "item_class_name", "dir": "desc"})
    rows = [r for r in res.json()["data"] if r["id"] in {a.id, b.id}]
    assert [r["id"] for r in rows] == [b.id, a.id]
    assert {r["id"]: r["product_count"] for r in rows} == {a.id: 2, b.id: 0}


def test_select_by_brand_offers_only_classes_that_brand_carries(env) -> None:
    client, db = env
    sorento, mocha = _brand(db, "SORENTO"), _brand(db, "MOCHA")
    serene, diy, unused = _class(db, "SERENE"), _class(db, "DIY"), _class(db, "UNUSED")
    _class(db, "OFF", active=False)
    _product(db, brand=sorento, item_class=serene)
    _product(db, brand=mocha, item_class=diy)
    db.commit()
    res = client.get(BASE + "/select", params={"brand_id": sorento.id})
    assert res.status_code == 200, res.text
    assert [r["id"] for r in res.json()] == [serene.id]
    everything = {r["id"] for r in client.get(BASE + "/select", params={"query": MARKER}).json()}
    assert {serene.id, diy.id, unused.id} <= everything
    assert all(r["is_active"] for r in client.get(BASE + "/select", params={"query": MARKER}).json())


def test_delete_clears_the_product_link(env) -> None:
    client, db = env
    row = _class(db, "GONE")
    p = _product(db, item_class=row)
    db.commit()
    res = client.delete(f"{BASE}/{row.id}")
    assert res.status_code == 200, res.text
    db.expire_all()
    assert db.get(Product, p.id).item_class_id is None
    assert client.get(f"{BASE}/{row.id}").status_code == 404


def test_delete_is_refused_while_a_contact_is_limited_to_it(env) -> None:
    client, db = env
    from app.models.access import RespondContact

    brand, row = _brand(db, "SORENTO"), _class(db, "HELD")
    contact = RespondContact(id=str(uuid.uuid4()), phone_number=f"+6{unique_code('PH')}",
                             brand_ids=[brand.id], brand_class_ids={brand.id: [row.id]})
    db.add(contact)
    db.commit()
    res = client.delete(f"{BASE}/{row.id}")
    assert res.status_code == 409, res.text
    assert "1 contact" in res.text


def test_delete_runs_through_the_deferred_action_registry() -> None:
    import app.services.record_actions  # noqa: F401  (registers the actions)
    from app.services.form_action_registry import get_action

    action = get_action("item_class.delete")
    assert action is not None
    assert action.permission == "master_data.item_classes.delete"


# --------------------------------------------------------------------- product list + form


def test_product_list_filters_by_several_classes_and_returns_the_class(env) -> None:
    client, db = env
    serene, diy, other = _class(db, "SERENE"), _class(db, "DIY"), _class(db, "OTHER")
    p1, p2 = _product(db, item_class=serene), _product(db, item_class=diy)
    _product(db, item_class=other)
    _product(db)
    db.commit()
    res = client.get(PRODUCTS + "/", params={"item_class_id": f"{serene.id},{diy.id}", "limit": 100})
    assert res.status_code == 200, res.text
    rows = {r["id"]: r for r in res.json()["data"]}
    assert set(rows) == {p1.id, p2.id}
    assert rows[p1.id]["item_class"]["item_class_name"] == serene.item_class_name
    assert rows[p1.id]["item_class_id"] == serene.id


def test_product_list_sorts_by_class_name_server_side_nulls_last(env) -> None:
    client, db = env
    a, z = _class(db, "AAA"), _class(db, "ZZZ")
    pz, pa, pn = _product(db, item_class=z), _product(db, item_class=a), _product(db)
    db.commit()
    wanted = {pz.id, pa.id, pn.id}
    for direction, expected in (("asc", [pa.id, pz.id, pn.id]), ("desc", [pz.id, pa.id, pn.id])):
        res = client.get(PRODUCTS + "/", params={"query": MARKER, "sort": "item_class", "dir": direction,
                                                 "limit": 500})
        assert res.status_code == 200, res.text
        assert [r["id"] for r in res.json()["data"] if r["id"] in wanted] == expected


def test_product_update_sets_and_clears_the_class(env) -> None:
    client, db = env
    row = _class(db, "FORM")
    p = _product(db)
    db.commit()
    res = client.put(f"{PRODUCTS}/{p.id}", json={"item_class_id": row.id})
    assert res.status_code == 200, res.text
    assert res.json()["item_class"]["id"] == row.id
    res = client.put(f"{PRODUCTS}/{p.id}", json={"item_class_id": None})
    assert res.status_code == 200, res.text
    assert res.json()["item_class"] is None


def test_product_update_refuses_an_unknown_class(env) -> None:
    client, db = env
    p = _product(db)
    db.commit()
    res = client.put(f"{PRODUCTS}/{p.id}", json={"item_class_id": str(uuid.uuid4())})
    assert res.status_code == 422, res.text


# --------------------------------------------------------------------- permissions


def test_registry_carries_the_four_slugs() -> None:
    from app.rbac.permission_registry import PERMISSION_REGISTRY

    slugs = {p["slug"] for p in PERMISSION_REGISTRY}
    for action in ("view", "add", "edit", "delete"):
        assert f"master_data.item_classes.{action}" in slugs


def test_migration_grants_follow_the_brand_slugs() -> None:
    """Every role holding `master_data.brands.<action>` gets the matching item-class slug;
    a role without the brand slug gets nothing."""
    from app.models.user import UserPermission, UserRole, UserRolePermission

    import importlib.util
    import pathlib

    path = pathlib.Path(__file__).resolve().parents[1] / "alembic" / "versions" / "item_class_0001.py"
    spec = importlib.util.spec_from_file_location("_item_class_0001", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    with blank_session() as db:
        def _perm(slug):
            row = db.query(UserPermission).filter(UserPermission.slug == slug).first()
            if row is None:
                row = UserPermission(slug=slug, name=slug)
                db.add(row)
                db.flush()
            return row

        holder = UserRole(id=str(uuid.uuid4()), slug=unique_code("brandviewer").lower(), name="h",
                          description="", is_protected=False, is_default=False)
        bystander = UserRole(id=str(uuid.uuid4()), slug=unique_code("nobrand").lower(), name="b",
                             description="", is_protected=False, is_default=False)
        db.add_all([holder, bystander])
        db.flush()
        db.add(UserRolePermission(role_id=holder.id, permission_id=_perm("master_data.brands.view").id))
        db.flush()

        module.apply_grants(db.connection())
        module.apply_grants(db.connection())  # idempotent

        def _slugs(role):
            return {
                s for (s,) in db.execute(
                    text(
                        "SELECT p.slug FROM user_role_permissions rp JOIN user_permissions p "
                        "ON p.id = rp.permission_id WHERE rp.role_id = :r"
                    ),
                    {"r": role.id},
                )
            }

        assert "master_data.item_classes.view" in _slugs(holder)
        assert "master_data.item_classes.edit" not in _slugs(holder)
        assert not any(s.startswith("master_data.item_classes") for s in _slugs(bystander))


# --------------------------------------------------------------------- review round (S2-S4)


def _other_company(db):
    from app.models.company import Company

    row = Company(id=str(uuid.uuid4()), name=f"{MARKER} other", code=f"ZIA{uuid.uuid4().hex[:6]}")
    db.add(row)
    db.flush()
    return row


def _scope_override(db, scope):
    from app.models.base import set_company_scope
    from app.services.company_scope_resolver import apply_company_scope

    def _scope():
        set_company_scope(db, scope)
        return None

    app.dependency_overrides[apply_company_scope] = _scope
    set_company_scope(db, scope)


def test_product_refuses_a_class_of_another_company(env) -> None:
    """S3: classes are per company; a caller seeing two companies cannot cross-link them."""
    client, db = env
    other = _other_company(db)
    foreign = ItemClass(id=str(uuid.uuid4()), item_class_code=unique_code("FRN")[:50],
                        item_class_name=f"{MARKER} FRN", company_id=other.id)
    db.add(foreign)
    p = _product(db)
    db.commit()
    _scope_override(db, frozenset({DEFAULT_COMPANY_ID, str(other.id)}))
    res = client.put(f"{PRODUCTS}/{p.id}", json={"item_class_id": foreign.id})
    assert res.status_code == 422, res.text
    own = _class(db, "OWN")
    db.commit()
    res = client.put(f"{PRODUCTS}/{p.id}", json={"item_class_id": own.id})
    assert res.status_code == 200, res.text


def test_same_code_in_another_company_is_not_a_conflict(env) -> None:
    """S4: an all-companies caller writes into the incumbent company; another company's row
    with the same code does not block it."""
    client, db = env
    other = _other_company(db)
    code = unique_code("SHARED")[:50]
    db.add(ItemClass(id=str(uuid.uuid4()), item_class_code=code, item_class_name=f"{MARKER} S",
                     company_id=other.id))
    db.commit()
    _scope_override(db, None)
    res = client.post(BASE + "/", json={"item_class_code": code, "item_class_name": "Shared"})
    assert res.status_code == 201, res.text
    res = client.post(BASE + "/", json={"item_class_code": code.lower(), "item_class_name": "Again"})
    assert res.status_code == 409, res.text


def test_delete_ignores_a_class_list_of_a_brand_the_contact_no_longer_has(env) -> None:
    """S2: a dormant entry (brand dropped from brand_ids) narrows nothing, so it does not block."""
    client, db = env
    from app.models.access import RespondContact

    sorento, mocha, row = _brand(db, "SORENTO"), _brand(db, "MOCHA"), _class(db, "DORMANT")
    db.add(RespondContact(id=str(uuid.uuid4()), phone_number=f"+6{unique_code('PH')}",
                          brand_ids=[mocha.id], brand_class_ids={sorento.id: [row.id]}))
    db.commit()
    res = client.delete(f"{BASE}/{row.id}")
    assert res.status_code == 200, res.text


def test_tag_brand_write_drops_class_lists_of_dropped_brands(env) -> None:
    """S2: a tag that changes the brands prunes class lists for brands it drops, so re-adding the
    brand later does not silently bring the old narrowing back."""
    _, db = env
    from app.models.access import RespondContact
    from app.services.contact_tag_apply import ALL, _w_columns

    sorento, mocha, row = _brand(db, "SORENTO"), _brand(db, "MOCHA"), _class(db, "TAGGED")
    contact = RespondContact(id=str(uuid.uuid4()), phone_number=f"+6{unique_code('PH')}",
                             brand_ids=[sorento.id, mocha.id],
                             brand_class_ids={sorento.id: [row.id], mocha.id: [row.id]})
    db.add(contact)
    db.flush()

    def _brands(want):
        _w_columns(db, contact, [{"section": "brands", "key": "brands", "_raw": {"expected": want}}], _USER_ID)

    _brands({mocha.id})
    assert contact.brand_class_ids == {mocha.id: [row.id]}
    _brands({sorento.id, mocha.id})
    assert contact.brand_class_ids == {mocha.id: [row.id]}
    _brands(ALL)
    assert contact.brand_ids is None and contact.brand_class_ids is None
