"""Write-route permission gates on the products router.

Context: `documentation/plans/security/PLAN-product-edit-perm-30oct.md` +
`documentation/plans/security/product-edit-perm-acceptance-criteria.md`.

Ten writes in `app/api/v1/master_data/products.py` were
`Depends(get_current_user)` only, so a signed-in user with module access but no
`master_data.products.*` grant could create, edit, delete or import products.
They now require the matching registered slug (create = `.add`, delete =
`.delete`, bulk delete = `.bulk_delete`, bulk import = `.import`, every other
write = `.edit`), through the same `require_permission` dependency the
family-code routes in that file already use.

Structure:

* UAC1 - per route, a caller holding every products slug EXCEPT the one the
  route needs gets 403 and nothing changes.
* UAC2 - per route, a caller holding only that slug succeeds. Every route runs
  for real against a scratch schema except the attachment field-links POST,
  whose `set_links` is recorded (it needs a stored attachment).
* UAC3 - structural: every non-GET route on the products router is gated by
  plain `require_permission` on a `master_data.products.*` slug, so a new
  ungated write fails here.

Dependency-override + `allow`-set monkeypatch pattern copied from
tests/test_contact_write_gates.py.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient

from app.api.v1.master_data import products as products_module
from app.database import get_db
from app.dependencies import get_current_user, get_current_user_or_api_key
from app.main import app
from app.models.base import set_company_scope
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.services import attachment_field_link_service
from app.services.company_scope import DEFAULT_COMPANY_ID
from app.services.company_scope_resolver import apply_company_scope
from tests._pg_fixture import blank_session, unique_code

BASE = "/api/v1/master-data/products"
ADD = "master_data.products.add"
EDIT = "master_data.products.edit"
DELETE = "master_data.products.delete"
BULK_DELETE = "master_data.products.bulk_delete"
IMPORT = "master_data.products.import"
ALL_PRODUCT_SLUGS = {
    "master_data.products.view",
    ADD,
    EDIT,
    DELETE,
    BULK_DELETE,
    IMPORT,
    "master_data.products.export",
}


@pytest.fixture
def db():
    with blank_session() as s:
        set_company_scope(s, None)
        yield s


@pytest.fixture
def api(db, monkeypatch):
    """A caller whose permission set is the returned `allow` set, plus a record
    of every field-link write the routes attempted."""
    from app.services.user_service import UserPermissionService

    allow: set[str] = set()
    calls: list[tuple[str, object]] = []
    caller = {"id": str(uuid.uuid4()), "email": "product-gates-caller@zzt.test"}

    def _override_db():
        yield db

    def _override_scope(_db=Depends(get_db)):
        set_company_scope(_db, None)
        return None

    def _fake_set_links(self, entity_type, row_id, attachment_id, field_keys, created_by=None):
        calls.append(("field_links", row_id))
        return list(field_keys)

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: caller
    # The router-level module guard resolves its caller through this one.
    app.dependency_overrides[get_current_user_or_api_key] = lambda: caller
    app.dependency_overrides[apply_company_scope] = _override_scope
    monkeypatch.setattr(
        UserPermissionService,
        "check_user_has_permission",
        lambda self, uid, slug: slug in allow,
    )
    monkeypatch.setattr(
        attachment_field_link_service.AttachmentFieldLinkService, "set_links", _fake_set_links
    )
    try:
        yield TestClient(app), allow, calls
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_current_user_or_api_key, None)
        app.dependency_overrides.pop(apply_company_scope, None)


# --------------------------------------------------------------------- seeds


class _World:
    def __init__(self, db):
        self.db = db
        self.uom = str(uuid.uuid4())
        self.cat = str(uuid.uuid4())
        db.add(UnitOfMeasure(id=self.uom, uom_code=unique_code("U")[:20], uom_name="Each"))
        db.add(ProductCategory(id=self.cat, category_code=unique_code("C")[:50], category_name="C"))
        db.flush()

    def product(self, name: str = "ZZT Product") -> str:
        pid = str(uuid.uuid4())
        self.db.add(
            Product(
                id=pid,
                product_code=unique_code("ZZTPW")[:50],
                product_name=name,
                category_id=self.cat,
                base_uom_id=self.uom,
                list_price=Decimal("10.00"),
                is_active=True,
                company_id=DEFAULT_COMPANY_ID,
            )
        )
        self.db.flush()
        return pid


def _row(db, pid: str) -> Product | None:
    db.expire_all()
    return db.query(Product).filter(Product.id == pid).first()


# ---------------------------------------------------------------- route table
#
# Each spec: (label, slug, method, build(world) -> (url, json, ctx),
#             succeeded(resp, db, ctx, calls), unchanged(db, ctx, calls)).


def _create(w):
    code = unique_code("ZZTPWNEW")[:50]
    body = {
        "product_code": code,
        "product_name": "ZZT Created",
        "category_id": w.cat,
        "base_uom_id": w.uom,
        "list_price": "12.50",
    }
    return f"{BASE}/", body, {"code": code}


def _created(db, ctx) -> bool:
    db.expire_all()
    return db.query(Product).filter(Product.product_code == ctx["code"]).first() is not None


def _update(w):
    pid = w.product("ZZT Before")
    return f"{BASE}/{pid}", {"product_name": "ZZT After"}, {"pid": pid}


def _bulk_update(w):
    pid = w.product()
    return f"{BASE}/bulk", {"ids": [pid], "updates": {"is_searchable": False}}, {"pid": pid}


def _bulk_import(w):
    body = {"products": [{"product_code": unique_code("ZZTPWI")[:50]}], "validate_only": True}
    return f"{BASE}/bulk-import", body, {}


def _delete(w):
    pid = w.product()
    return f"{BASE}/{pid}", None, {"pid": pid}


def _bulk_delete(w):
    pid = w.product()
    return f"{BASE}/bulk", {"ids": [pid]}, {"pid": pid}


def _variant_parent(w):
    parent = w.product("ZZT Parent")
    child = w.product("ZZT Child")
    return f"{BASE}/{child}/variant-parent", {"parent_id": parent}, {"pid": child, "parent": parent}


def _seed_linked_child(w):
    parent = w.product("ZZT Parent")
    child = w.product("ZZT Child")
    row = w.db.query(Product).filter(Product.id == child).one()
    row.variant_of_id = parent
    row.variant_link_manual = True
    w.db.flush()
    return child, parent


def _unlink(w):
    child, parent = _seed_linked_child(w)
    return f"{BASE}/{child}/variant-parent", None, {"pid": child, "parent": parent}


def _variant_reset(w):
    child, parent = _seed_linked_child(w)
    return f"{BASE}/{child}/variant-reset", None, {"pid": child, "parent": parent}


def _field_links(w):
    pid = w.product()
    aid = str(uuid.uuid4())
    return f"{BASE}/{pid}/attachments/{aid}/field-links", {"field_keys": ["list_price"]}, {"pid": pid}


SPECS = [
    (
        "create", ADD, "POST", _create,
        lambda r, db, c, k: r.status_code == 201 and _created(db, c),
        lambda db, c, k: not _created(db, c),
    ),
    (
        "update", EDIT, "PUT", _update,
        lambda r, db, c, k: r.status_code == 200 and _row(db, c["pid"]).product_name == "ZZT After",
        lambda db, c, k: _row(db, c["pid"]).product_name == "ZZT Before",
    ),
    (
        "bulk_update", EDIT, "PUT", _bulk_update,
        lambda r, db, c, k: r.status_code == 200 and _row(db, c["pid"]).is_searchable is False,
        lambda db, c, k: _row(db, c["pid"]).is_searchable is not False,
    ),
    (
        "bulk_import", IMPORT, "POST", _bulk_import,
        lambda r, db, c, k: r.status_code == 200 and "valid" in r.json(),
        lambda db, c, k: True,
    ),
    (
        "delete", DELETE, "DELETE", _delete,
        lambda r, db, c, k: r.status_code == 200 and _row(db, c["pid"]) is None,
        lambda db, c, k: _row(db, c["pid"]) is not None,
    ),
    (
        "bulk_delete", BULK_DELETE, "DELETE", _bulk_delete,
        lambda r, db, c, k: r.status_code == 200 and _row(db, c["pid"]) is None,
        lambda db, c, k: _row(db, c["pid"]) is not None,
    ),
    (
        "set_variant_parent", EDIT, "PUT", _variant_parent,
        lambda r, db, c, k: r.status_code == 200 and str(_row(db, c["pid"]).variant_of_id) == c["parent"],
        lambda db, c, k: _row(db, c["pid"]).variant_of_id is None,
    ),
    (
        "unlink_variant", EDIT, "DELETE", _unlink,
        lambda r, db, c, k: r.status_code == 200 and _row(db, c["pid"]).variant_of_id is None,
        lambda db, c, k: str(_row(db, c["pid"]).variant_of_id) == c["parent"],
    ),
    (
        "variant_reset", EDIT, "POST", _variant_reset,
        lambda r, db, c, k: r.status_code == 200 and _row(db, c["pid"]).variant_link_manual is False,
        lambda db, c, k: _row(db, c["pid"]).variant_link_manual is True,
    ),
    (
        "field_links", EDIT, "POST", _field_links,
        lambda r, db, c, k: r.status_code == 200 and ("field_links", c["pid"]) in k,
        lambda db, c, k: not k,
    ),
]


def _send(client, method, url, body):
    return client.request(method, url, json=body)


@pytest.mark.parametrize("spec", SPECS, ids=[s[0] for s in SPECS])
def test_write_without_its_permission_is_403_and_changes_nothing(db, api, spec):
    label, slug, method, build, _succeeded, unchanged = spec
    client, allow, calls = api
    world = _World(db)
    db.commit()
    url, body, ctx = build(world)
    db.commit()
    allow.update(ALL_PRODUCT_SLUGS - {slug})

    resp = _send(client, method, url, body)

    assert resp.status_code == 403, (label, resp.status_code, resp.text)
    assert slug in resp.text
    assert unchanged(db, ctx, calls), label


@pytest.mark.parametrize("spec", SPECS, ids=[s[0] for s in SPECS])
def test_write_with_its_permission_succeeds(db, api, spec):
    label, slug, method, build, succeeded, _unchanged = spec
    client, allow, calls = api
    world = _World(db)
    db.commit()
    url, body, ctx = build(world)
    db.commit()
    allow.add(slug)

    resp = _send(client, method, url, body)

    assert succeeded(resp, db, ctx, calls), (label, resp.status_code, resp.text)


def test_every_product_write_route_requires_a_products_permission():
    """A new non-GET route on the products router must carry the gate."""
    ungated = []
    for route in products_module.router.routes:
        methods = set(getattr(route, "methods", set())) - {"GET", "HEAD", "OPTIONS"}
        if not methods:
            continue
        slugs = []
        for dep in route.dependant.dependencies:
            call = dep.call
            if getattr(call, "__name__", "") != "_require" or not call.__closure__:
                continue
            if "require_permission." not in call.__qualname__:
                continue
            for cell in call.__closure__:
                val = cell.cell_contents
                if isinstance(val, str) and val.startswith("master_data.products."):
                    slugs.append(val)
        if not slugs:
            ungated.append((sorted(methods), route.path))
    assert not ungated, f"ungated product write routes: {ungated}"
