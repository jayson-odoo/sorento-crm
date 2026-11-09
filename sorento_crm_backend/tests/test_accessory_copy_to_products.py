"""ACC-COPY-TO-PRODUCTS: copy a product's accessories list to hand-picked products in one call.

Plan + behaviour card: `documentation/plans/dealer-kit/PLAN-acc-copy-to-products-09nov.md`.
Written test-FIRST. Contract (invented here, the code must match):

  POST /api/v1/master-data/products/{product_id}/accessories/copy
    body  {"target_product_ids": [...], "dry_run": false}   (1..500 ids)
    200   {"targets": int, "targets_with_a_list": int, "entries_added": int,
           "entries_already_there": int, "box_style_set": int}

  * Add mode: each target keeps its own list and gets the source entries it is missing, at the
    end, in the source's order; an entry the target already lists keeps the TARGET's version.
  * Each copied entry carries the source row's overrides (name / spec / remark / picture pick).
  * The source's box style goes only to targets with none; a target's own style is kept.
  * A product entry naming the target itself is skipped for that target.
  * The source among the targets, and repeated ids, are ignored.
  * All or nothing: an out-of-scope or missing target is 404, a list that would pass 100 entries is
    422 naming the product code, and nothing is written either way.
  * `master_data.products.edit`, signed-in only. `dry_run` answers the same summary and writes nothing.

Synthetic names only.
"""
from __future__ import annotations

import uuid

import pytest

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402,F401

from app.models.accessory import AccessoryImage, ProductAccessory
from app.models.product import Product
from app.services.company_scope import register_company_scope_listeners

from tests import _ptag_combo_seed as seed
from tests._pg_fixture import blank_session, unique_code
from tests.test_accessories import (  # noqa: F401
    EDIT,
    MOCHA,
    VIEW,
    _accessory,
    _caller,
    _clear_overrides,
    _mocha,
    _name,
    _product,
)
from tests.test_accessory_box_style import _preset

COPY = "/api/v1/master-data/products/{product_id}/accessories/copy"


@pytest.fixture()
def db():
    with blank_session() as session:
        yield session


@pytest.fixture(autouse=True)
def _scope_listeners():
    register_company_scope_listeners()


def _link(db, product, *, accessories=(), products=(), start=0, **overrides):
    """Append entries to `product`'s list: accessories first, then product entries."""
    index = start
    rows = []
    for item in accessories:
        row = ProductAccessory(
            id=str(uuid.uuid4()), product_id=product.id, accessory_id=item.id, sort_order=index, **overrides
        )
        rows.append(row)
        index += 1
    for item in products:
        row = ProductAccessory(id=str(uuid.uuid4()), product_id=product.id, item_product_id=item.id, sort_order=index)
        rows.append(row)
        index += 1
    db.add_all(rows)
    db.flush()
    return rows


def _list(db, product_id):
    db.expire_all()
    return (
        db.query(ProductAccessory)
        .filter(ProductAccessory.product_id == product_id)
        .order_by(ProductAccessory.sort_order)
        .all()
    )


def _keys(db, product_id):
    return [row.accessory_id or row.item_product_id for row in _list(db, product_id)]


def _copy(client, source, targets, **extra):
    return client.post(
        COPY.format(product_id=source.id),
        json={"target_product_ids": [t if isinstance(t, str) else t.id for t in targets], **extra},
    )


# --------------------------------------------------------------------------- happy path


def test_copies_the_whole_list_in_order_to_targets_with_none(db, monkeypatch):
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    source = _product(db, "ZZSRC")
    pump, soap, tap = (_accessory(db, _name(s)) for s in ("PUMP", "SOAP", "TAP"))
    _link(db, source, accessories=[pump, soap, tap])
    a, b = _product(db, "ZZTGA"), _product(db, "ZZTGB")

    response = _copy(client, source, [a, b])
    assert response.status_code == 200, response.text
    assert response.json() == {
        "targets": 2,
        "targets_with_a_list": 0,
        "entries_added": 6,
        "entries_already_there": 0,
        "box_style_set": 0,
    }
    for target in (a, b):
        assert _keys(db, target.id) == [pump.id, soap.id, tap.id]
        assert [row.sort_order for row in _list(db, target.id)] == [0, 1, 2]
    assert _keys(db, source.id) == [pump.id, soap.id, tap.id], "the source is untouched"


def test_product_entries_copy_too(db, monkeypatch):
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    source = _product(db, "ZZSRC")
    free = _product(db, "ZZFREE")
    pump = _accessory(db, _name("PUMP"))
    _link(db, source, accessories=[pump], products=[free])
    target = _product(db, "ZZTGT")

    assert _copy(client, source, [target]).status_code == 200
    assert _keys(db, target.id) == [pump.id, free.id]


def test_add_mode_keeps_the_targets_list_and_appends_only_what_is_missing(db, monkeypatch):
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    source = _product(db, "ZZSRC")
    pump, soap, tap, own = (_accessory(db, _name(s)) for s in ("PUMP", "SOAP", "TAP", "OWN"))
    _link(db, source, accessories=[pump, soap, tap])
    target = _product(db, "ZZTGT")
    # The target already lists SOAP with its own remark, plus something of its own.
    _link(db, target, accessories=[own])
    _link(db, target, accessories=[soap], start=1, remark_override="<p>target's own words</p>")

    response = _copy(client, source, [target])
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["targets_with_a_list"] == 1
    assert body["entries_added"] == 2
    assert body["entries_already_there"] == 1
    assert _keys(db, target.id) == [own.id, soap.id, pump.id, tap.id]
    assert [row.sort_order for row in _list(db, target.id)] == [0, 1, 2, 3]
    kept = next(row for row in _list(db, target.id) if row.accessory_id == soap.id)
    assert kept.remark_override == "<p>target's own words</p>", "an entry already there keeps the target's version"


def test_overrides_and_picture_pick_copy_with_each_entry(db, monkeypatch):
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    source = _product(db, "ZZSRC")
    pump = _accessory(db, _name("PUMP"))
    from app.models.resources import Attachment

    stem = unique_code("zztimg")
    attachment = Attachment(
        id=str(uuid.uuid4()), original_filename=f"{stem}.jpg", stored_filename=f"{stem}.jpg",
        file_path=f"https://cdn.test/accessory_image/{stem}.jpg", mime_type="image/jpeg",
        storage_provider="s3", company_id=seed.SORENTO, is_deleted=False,
    )
    db.add(attachment)
    db.flush()
    picture = AccessoryImage(id=str(uuid.uuid4()), accessory_id=pump.id, attachment_id=attachment.id, sort_order=0)
    db.add(picture)
    db.flush()
    _link(
        db,
        source,
        accessories=[pump],
        image_id=picture.id,
        name_override="Pressure pump 30PC",
        spec_override="<p>240V</p>",
        remark_override="<p>Free install</p>",
    )
    target = _product(db, "ZZTGT")

    assert _copy(client, source, [target]).status_code == 200
    (row,) = _list(db, target.id)
    assert (row.image_id, row.name_override, row.spec_override, row.remark_override) == (
        picture.id,
        "Pressure pump 30PC",
        "<p>240V</p>",
        "<p>Free install</p>",
    )


def test_box_style_goes_only_to_targets_without_one(db, monkeypatch):
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    source = _product(db, "ZZSRC")
    _link(db, source, accessories=[_accessory(db, _name("PUMP"))])
    theirs, ours = _preset(db), _preset(db)
    source.accessory_box_preset_id = ours.id
    bare = _product(db, "ZZBARE")
    styled = _product(db, "ZZSTYLED")
    styled.accessory_box_preset_id = theirs.id
    db.flush()

    response = _copy(client, source, [bare, styled])
    assert response.status_code == 200, response.text
    assert response.json()["box_style_set"] == 1
    db.expire_all()
    assert db.get(Product, bare.id).accessory_box_preset_id == ours.id
    assert db.get(Product, styled.id).accessory_box_preset_id == theirs.id, "a target's own style is kept"


def test_source_without_a_box_style_leaves_targets_alone(db, monkeypatch):
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    source = _product(db, "ZZSRC")
    _link(db, source, accessories=[_accessory(db, _name("PUMP"))])
    styled = _product(db, "ZZSTYLED")
    style = _preset(db)
    styled.accessory_box_preset_id = style.id
    db.flush()

    assert _copy(client, source, [styled]).json()["box_style_set"] == 0
    db.expire_all()
    assert db.get(Product, styled.id).accessory_box_preset_id == style.id


# --------------------------------------------------------------------------- edges


def test_a_product_entry_naming_the_target_itself_is_skipped_for_that_target(db, monkeypatch):
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    source = _product(db, "ZZSRC")
    pump = _accessory(db, _name("PUMP"))
    target = _product(db, "ZZTGT")
    _link(db, source, accessories=[pump], products=[target])

    response = _copy(client, source, [target])
    assert response.status_code == 200, response.text
    assert _keys(db, target.id) == [pump.id]


def test_the_source_and_repeated_ids_among_the_targets_are_ignored(db, monkeypatch):
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    source = _product(db, "ZZSRC")
    pump = _accessory(db, _name("PUMP"))
    _link(db, source, accessories=[pump])
    target = _product(db, "ZZTGT")

    response = _copy(client, source, [target, source, target])
    assert response.status_code == 200, response.text
    assert response.json()["targets"] == 1
    assert _keys(db, source.id) == [pump.id]
    assert _keys(db, target.id) == [pump.id]


def test_copying_twice_adds_nothing_the_second_time(db, monkeypatch):
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    source = _product(db, "ZZSRC")
    pump = _accessory(db, _name("PUMP"))
    _link(db, source, accessories=[pump])
    target = _product(db, "ZZTGT")

    assert _copy(client, source, [target]).status_code == 200
    again = _copy(client, source, [target])
    assert again.status_code == 200
    assert again.json()["entries_added"] == 0 and again.json()["entries_already_there"] == 1
    assert _keys(db, target.id) == [pump.id]


def test_an_empty_source_list_is_refused(db, monkeypatch):
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    source = _product(db, "ZZSRC")
    target = _product(db, "ZZTGT")
    response = _copy(client, source, [target])
    assert response.status_code == 422
    assert "no accessories" in response.json()["message"].lower()


@pytest.mark.parametrize("count", [0, 501])
def test_target_count_is_one_to_five_hundred(db, monkeypatch, count):
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    source = _product(db, "ZZSRC")
    _link(db, source, accessories=[_accessory(db, _name("PUMP"))])
    response = _copy(client, source, [str(uuid.uuid4()) for _ in range(count)])
    assert response.status_code == 422


def test_a_malformed_target_id_is_422(db, monkeypatch):
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    source = _product(db, "ZZSRC")
    _link(db, source, accessories=[_accessory(db, _name("PUMP"))])
    assert _copy(client, source, ["not-a-uuid"]).status_code == 422


def test_dry_run_answers_the_summary_and_writes_nothing(db, monkeypatch):
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    source = _product(db, "ZZSRC")
    pump, soap = _accessory(db, _name("PUMP")), _accessory(db, _name("SOAP"))
    _link(db, source, accessories=[pump, soap])
    style = _preset(db)
    source.accessory_box_preset_id = style.id
    fresh, listed = _product(db, "ZZFRESH"), _product(db, "ZZLISTED")
    _link(db, listed, accessories=[soap])
    db.flush()

    response = _copy(client, source, [fresh, listed], dry_run=True)
    assert response.status_code == 200, response.text
    assert response.json() == {
        "targets": 2,
        "targets_with_a_list": 1,
        "entries_added": 3,
        "entries_already_there": 1,
        "box_style_set": 2,
    }
    assert _keys(db, fresh.id) == []
    assert _keys(db, listed.id) == [soap.id]
    db.expire_all()
    assert db.get(Product, fresh.id).accessory_box_preset_id is None


# --------------------------------------------------------------------------- all or nothing


def test_a_target_that_would_pass_100_entries_refuses_the_whole_copy(db, monkeypatch):
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    source = _product(db, "ZZSRC")
    extra = _accessory(db, _name("EXTRA"))
    _link(db, source, accessories=[extra])
    fine = _product(db, "ZZFINE")
    full = _product(db, "ZZFULL")
    _link(db, full, accessories=[_accessory(db, _name(f"F{i}")) for i in range(100)])

    response = _copy(client, source, [fine, full])
    assert response.status_code == 422, response.text
    assert full.product_code in response.json()["message"]
    assert _keys(db, fine.id) == [], "nothing is written when one target is refused"
    assert len(_list(db, full.id)) == 100


def test_another_companys_target_is_404_and_nothing_is_written(db, monkeypatch):
    _mocha(db)
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    source = _product(db, "ZZSRC")
    _link(db, source, accessories=[_accessory(db, _name("PUMP"))])
    ours = _product(db, "ZZOURS")
    theirs = _product(db, "ZZTHEIRS", company_id=MOCHA)

    response = _copy(client, source, [ours, theirs])
    assert response.status_code == 404, response.text
    assert _keys(db, ours.id) == []
    assert _keys(db, theirs.id) == []


def test_a_missing_target_is_404(db, monkeypatch):
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    source = _product(db, "ZZSRC")
    _link(db, source, accessories=[_accessory(db, _name("PUMP"))])
    assert _copy(client, source, [str(uuid.uuid4())]).status_code == 404


def test_another_companys_source_is_404(db, monkeypatch):
    _mocha(db)
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    source = _product(db, "ZZTHEIRS", company_id=MOCHA)
    _link(db, source, accessories=[_accessory(db, _name("PUMP"), company_id=MOCHA)])
    target = _product(db, "ZZOURS")
    assert _copy(client, source, [target]).status_code == 404
    assert _keys(db, target.id) == []


# --------------------------------------------------------------------------- permission


def test_view_only_cannot_copy(db, monkeypatch):
    client = _caller(db, {VIEW}, monkeypatch)
    source = _product(db, "ZZSRC")
    _link(db, source, accessories=[_accessory(db, _name("PUMP"))])
    target = _product(db, "ZZTGT")
    assert _copy(client, source, [target]).status_code == 403
    assert _keys(db, target.id) == []


def test_an_api_key_cannot_copy():
    """Signed-in only, like every accessories write: the route depends on `require_permission`."""
    from app.api.v1.master_data import accessories as routes

    route = next(
        r for r in routes.router.routes if getattr(r, "path", "") == "/products/{product_id}/accessories/copy"
    )
    names = {getattr(dep.call, "__qualname__", "") for dep in route.dependant.dependencies}
    assert not any("api_key" in name for name in names), names


# --------------------------------------------------------------------------- audit


def test_each_target_gets_its_own_audit_trail(db, monkeypatch):
    from app.models.audit import AuditLog
    from app.services.audit_service import register_audit_listeners

    register_audit_listeners()  # the app's startup does this; a bare TestClient never starts up
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    source = _product(db, "ZZSRC")
    _link(db, source, accessories=[_accessory(db, _name("PUMP"))])
    a, b = _product(db, "ZZTGA"), _product(db, "ZZTGB")
    assert _copy(client, source, [a, b]).status_code == 200
    db.expire_all()
    for target in (a, b):
        rows = (
            db.query(AuditLog)
            .filter(
                AuditLog.entity_type == "product_accessories",
                AuditLog.action == "CREATE",
                AuditLog.root_entity_id == target.id,
            )
            .all()
        )
        assert len(rows) == 1, f"one CREATE on {target.product_code}'s trail"
