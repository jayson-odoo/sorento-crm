"""COMBO-COPY-TO-PRODUCTS: copy one product combo to hand-picked products in one call.

Plan: `documentation/plans/products/PLAN-combo-copy-to-products-09nov.md` (owner answers 9 Nov).
Written test-FIRST. Contract (the code must match):

  POST /api/v1/master-data/product-combos/{combo_id}/copy
    body  {"target_product_ids": [...] (1..500), "overwrite_product_ids": [...], "dry_run": false}
    200   {"targets": int, "created": int, "overwritten": int,
           "skipped": [{"product_id", "code", "name", "reason": "exists" | "part"}],
           "conflicts": [{"product_id", "code", "name"}],
           "template_links_copied": bool}

  * Each target gets a combo with the source's name, description, list / sell price, legacy free
    items text, box style, picture, parts (group, option price, top-up, upgrade, order) and free
    items (with overrides and picture pick). The target becomes the host.
  * Template links (with LP / SP defaults) copy only when the caller holds
    `dealer_kit.tag_templates.manage`.
  * A target with a combo of that name (case ignored) is a conflict: skipped unless its id is in
    `overwrite_product_ids`, which replaces that combo's contents and keeps its row.
  * A target that is a part of the combo is skipped (`part`); a free item naming the target is left
    out for that target. The source host and repeated ids are ignored.
  * All or nothing: a missing / other-company target is 404 and nothing is written.
  * `master_data.products.edit`, signed-in only. `dry_run` answers the same and writes nothing.

Synthetic names only.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402,F401

from app.models.accessory import AccessoryImage, ProductComboAccessory
from app.models.dealer_kit import ComboTagTemplate
from app.models.product import ProductAttachment
from app.models.product_combo import ProductCombo, ProductComboPart
from app.models.resources import Attachment, AttachmentType
from app.services.company_scope import register_company_scope_listeners

from tests._pg_fixture import blank_session, unique_code
from tests.test_accessories import _accessory, _name
from tests.test_accessory_box_style import _preset
from tests.test_product_combos import (  # noqa: F401  (_clear_overrides autouse, storage fixture)
    EDIT,
    MOCHA,
    VIEW,
    _caller,
    _clear_overrides,
    _mocha,
    _product,
    storage,
)
from tests.test_product_tag_templates import _template

COPY = "/api/v1/master-data/product-combos/{combo_id}/copy"
MANAGE = "dealer_kit.tag_templates.manage"


@pytest.fixture()
def db():
    with blank_session() as session:
        yield session


@pytest.fixture(autouse=True)
def _scope_listeners():
    register_company_scope_listeners()


def _attachment(db, host):
    """A combo picture linked into `host`'s gallery, as an upload leaves it."""
    kind = db.query(AttachmentType).filter(AttachmentType.code == "combo_image").first()
    if kind is None:
        kind = AttachmentType(
            id=str(uuid.uuid4()), code="combo_image", type_name="Combo Image",
            allowed_extensions="jpg,jpeg,png,webp", max_file_size_mb=10,
        )
        db.add(kind)
        db.flush()
    row = Attachment(
        id=str(uuid.uuid4()),
        attachment_type_id=kind.id,
        original_filename="tub.jpg",
        stored_filename="tub.jpg",
        file_path=f"https://cdn.test/product_combo_image/{uuid.uuid4()}/tub.jpg",
        file_size_bytes=10,
        mime_type="image/jpeg",
        file_hash=uuid.uuid4().hex,
        entity_type="product_combo_image",
        storage_provider="s3",
        company_id=host.company_id,
    )
    db.add(row)
    db.flush()
    db.add(ProductAttachment(
        id=str(uuid.uuid4()), product_id=host.id, attachment_id=row.id, is_primary=False,
        access_levels=["dealer", "end_user"], company_id=host.company_id,
    ))
    db.flush()
    return row


def _bathtub_combo(db, *, with_picture=True, with_templates=()):
    """SRTBT1860-16's flyer combo, synthetic codes: 4 tap upgrades, 1 fixed drainer, 2 free items."""
    host = _product(db, "ZZBT1860")
    drainer = _product(db, "ZZDRAIN")
    taps = [_product(db, f"ZZTAP{colour}") for colour in ("BL", "GM")]
    pump, soap = _accessory(db, _name("PUMP")), _accessory(db, _name("SOAP"))
    free_product = _product(db, "ZZFREE")
    preset = _preset(db)
    combo = ProductCombo(
        id=str(uuid.uuid4()),
        host_product_id=host.id,
        name="Bathtub Combo",
        sort_order=0,
        description="<p><strong>Free Standing Bathtub</strong></p><p>L1600xW780xH800mm</p>",
        free_items="Pump, soap",
        list_price=Decimal("7588.00"),
        sell_price=Decimal("6599.00"),
        accessory_box_preset_id=preset.id,
        image_attachment_id=_attachment(db, host).id if with_picture else None,
    )
    db.add(combo)
    db.flush()
    db.add(ProductComboPart(
        id=str(uuid.uuid4()), combo_id=combo.id, part_product_id=drainer.id, sort_order=0,
    ))
    for index, tap in enumerate(taps, start=1):
        db.add(ProductComboPart(
            id=str(uuid.uuid4()), combo_id=combo.id, part_product_id=tap.id, choice_group="Mixer tap",
            sort_order=index, sell_price=Decimal("10.00"), topup_amount=Decimal("150.00"), is_upgrade=True,
        ))
    image = AccessoryImage(id=str(uuid.uuid4()), accessory_id=pump.id, attachment_id=_attachment(db, host).id)
    db.add(image)
    db.flush()
    db.add(ProductComboAccessory(
        id=str(uuid.uuid4()), combo_id=combo.id, accessory_id=pump.id, sort_order=0,
        image_id=image.id, name_override="Booster pump", spec_override="SUS304", remark_override="Free",
    ))
    db.add(ProductComboAccessory(id=str(uuid.uuid4()), combo_id=combo.id, accessory_id=soap.id, sort_order=1))
    db.add(ProductComboAccessory(
        id=str(uuid.uuid4()), combo_id=combo.id, item_product_id=free_product.id, sort_order=2,
    ))
    for index, template_id in enumerate(with_templates):
        db.add(ComboTagTemplate(
            combo_id=combo.id, template_id=template_id, default_list=index == 0, default_selling=index == 0,
        ))
    db.flush()
    return combo, {"host": host, "drainer": drainer, "taps": taps, "pump": pump, "soap": soap,
                   "free_product": free_product, "preset": preset, "image": image}


def _copy(client, combo, targets, **extra):
    return client.post(
        COPY.format(combo_id=combo.id),
        json={"target_product_ids": [t if isinstance(t, str) else t.id for t in targets], **extra},
    )


def _combos_on(db, product):
    db.expire_all()
    return db.query(ProductCombo).filter(ProductCombo.host_product_id == product.id).all()


def _parts(db, combo_id):
    return [
        (p.part_product_id, p.choice_group, p.sort_order, p.sell_price, p.topup_amount, p.is_upgrade)
        for p in db.query(ProductComboPart).filter(ProductComboPart.combo_id == combo_id)
        .order_by(ProductComboPart.sort_order).all()
    ]


def _free(db, combo_id):
    return [
        (r.accessory_id, r.item_product_id, r.sort_order, r.image_id, r.name_override, r.spec_override,
         r.remark_override)
        for r in db.query(ProductComboAccessory).filter(ProductComboAccessory.combo_id == combo_id)
        .order_by(ProductComboAccessory.sort_order).all()
    ]


def _links(db, combo_id):
    return sorted(
        (r.template_id, r.default_list, r.default_selling)
        for r in db.query(ComboTagTemplate).filter(ComboTagTemplate.combo_id == combo_id).all()
    )


# --------------------------------------------------------------------------- happy path


def test_copies_every_field_part_and_free_item_to_each_target(db, monkeypatch):
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    source, seed = _bathtub_combo(db)
    a, b = _product(db, "ZZBT1835"), _product(db, "ZZBT1846")

    response = _copy(client, source, [a, b])
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["targets"] == 2 and body["created"] == 2 and body["overwritten"] == 0
    assert body["skipped"] == [] and body["conflicts"] == []

    for target in (a, b):
        [copy] = _combos_on(db, target)
        assert copy.id != source.id
        assert copy.name == "Bathtub Combo"
        assert copy.description == source.description, "formatting kept"
        assert copy.free_items == "Pump, soap"
        assert copy.list_price == Decimal("7588.00") and copy.sell_price == Decimal("6599.00")
        assert copy.accessory_box_preset_id == seed["preset"].id
        assert _parts(db, copy.id) == _parts(db, source.id)
        assert _free(db, copy.id) == _free(db, source.id)
    assert len(_combos_on(db, seed["host"])) == 1, "the source host is untouched"


def test_the_picture_is_shared_and_linked_into_each_target_gallery(db, monkeypatch):
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    source, seed = _bathtub_combo(db)
    target = _product(db, "ZZBT1835")

    assert _copy(client, source, [target]).status_code == 200
    [copy] = _combos_on(db, target)
    assert copy.image_attachment_id == source.image_attachment_id
    gallery = {
        row.product_id
        for row in db.query(ProductAttachment).filter(ProductAttachment.attachment_id == source.image_attachment_id)
    }
    assert gallery == {seed["host"].id, target.id}


def test_a_target_already_showing_the_picture_gets_no_second_gallery_link(db, monkeypatch):
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    source, _ = _bathtub_combo(db)
    target = _product(db, "ZZBT1835")
    db.add(ProductAttachment(
        id=str(uuid.uuid4()), product_id=target.id, attachment_id=source.image_attachment_id,
        is_primary=False, access_levels=["dealer"], company_id=target.company_id,
    ))
    db.flush()

    assert _copy(client, source, [target]).status_code == 200, "no unique-constraint error"
    assert db.query(ProductAttachment).filter(
        ProductAttachment.product_id == target.id,
        ProductAttachment.attachment_id == source.image_attachment_id,
    ).count() == 1


def test_a_combo_without_picture_copies_without_one(db, monkeypatch):
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    source, _ = _bathtub_combo(db, with_picture=False)
    target = _product(db, "ZZBT1835")
    assert _copy(client, source, [target]).status_code == 200
    [copy] = _combos_on(db, target)
    assert copy.image_attachment_id is None


def test_the_copy_is_placed_after_the_targets_own_combos(db, monkeypatch):
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    source, _ = _bathtub_combo(db)
    target = _product(db, "ZZBT1835")
    for index, name in enumerate(("One", "Two")):
        db.add(ProductCombo(id=str(uuid.uuid4()), host_product_id=target.id, name=name, sort_order=index))
    db.flush()
    assert _copy(client, source, [target]).status_code == 200
    copy = next(c for c in _combos_on(db, target) if c.name == "Bathtub Combo")
    assert copy.sort_order == 2


# --------------------------------------------------------------------------- template links


def test_template_links_and_defaults_copy_for_a_template_manager(db, monkeypatch):
    client = _caller(db, {VIEW, EDIT, MANAGE}, monkeypatch)
    first, second = _template(db, "ZZT combo tag A"), _template(db, "ZZT combo tag B")
    source, _ = _bathtub_combo(db, with_templates=(first, second))
    target = _product(db, "ZZBT1835")

    response = _copy(client, source, [target])
    assert response.status_code == 200, response.text
    assert response.json()["template_links_copied"] is True
    [copy] = _combos_on(db, target)
    assert _links(db, copy.id) == _links(db, source.id)
    assert (first, True, True) in _links(db, copy.id)


def test_without_the_template_permission_the_combo_copies_without_links(db, monkeypatch):
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    source, _ = _bathtub_combo(db, with_templates=(_template(db, "ZZT combo tag A"),))
    target = _product(db, "ZZBT1835")

    response = _copy(client, source, [target])
    assert response.status_code == 200, response.text
    assert response.json()["template_links_copied"] is False
    [copy] = _combos_on(db, target)
    assert _links(db, copy.id) == []
    assert copy.name == "Bathtub Combo", "everything else still copies"


def test_a_combo_with_no_links_reports_none_copied_even_for_a_manager(db, monkeypatch):
    client = _caller(db, {VIEW, EDIT, MANAGE}, monkeypatch)
    source, _ = _bathtub_combo(db)
    response = _copy(client, source, [_product(db, "ZZBT1835")])
    assert response.json()["template_links_copied"] is True, "allowed; nothing to copy is not a refusal"


# --------------------------------------------------------------------------- same name on a target


def _existing(db, target, name="bathtub combo"):
    """A combo the target already has under the same name (other case), with its own contents."""
    other = _product(db, "ZZOLDPART")
    row = ProductCombo(
        id=str(uuid.uuid4()), host_product_id=target.id, name=name, sort_order=0,
        description="<p>old</p>", list_price=Decimal("1.00"), sell_price=Decimal("1.00"),
    )
    db.add(row)
    db.flush()
    db.add(ProductComboPart(id=str(uuid.uuid4()), combo_id=row.id, part_product_id=other.id, sort_order=0))
    db.add(ProductComboAccessory(
        id=str(uuid.uuid4()), combo_id=row.id, accessory_id=_accessory(db, _name("OLD")).id, sort_order=0,
    ))
    db.flush()
    return row


def test_dry_run_lists_targets_that_already_have_the_name_and_writes_nothing(db, monkeypatch):
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    source, _ = _bathtub_combo(db)
    clash, fresh = _product(db, "ZZBT1835"), _product(db, "ZZBT1846")
    _existing(db, clash)

    response = _copy(client, source, [clash, fresh], dry_run=True)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["conflicts"] == [
        {"product_id": clash.id, "code": clash.product_code, "name": clash.product_name}
    ]
    assert body["created"] == 1 and body["overwritten"] == 0
    assert [s["reason"] for s in body["skipped"]] == ["exists"]
    assert _combos_on(db, fresh) == [], "a dry run writes nothing"


def test_a_conflict_is_skipped_by_default_and_left_as_it_was(db, monkeypatch):
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    source, _ = _bathtub_combo(db)
    clash, fresh = _product(db, "ZZBT1835"), _product(db, "ZZBT1846")
    old = _existing(db, clash)
    before = (_parts(db, old.id), _free(db, old.id))

    body = _copy(client, source, [clash, fresh]).json()
    assert body["created"] == 1 and body["overwritten"] == 0
    assert body["skipped"] == [
        {"product_id": clash.id, "code": clash.product_code, "name": clash.product_name, "reason": "exists"}
    ]
    [kept] = _combos_on(db, clash)
    assert kept.id == old.id and kept.description == "<p>old</p>"
    assert (_parts(db, old.id), _free(db, old.id)) == before
    assert len(_combos_on(db, fresh)) == 1


def test_overwrite_replaces_the_contents_and_keeps_the_combo_row(db, monkeypatch):
    client = _caller(db, {VIEW, EDIT, MANAGE}, monkeypatch)
    tag = _template(db, "ZZT combo tag A")
    source, seed = _bathtub_combo(db, with_templates=(tag,))
    clash = _product(db, "ZZBT1835")
    old = _existing(db, clash)
    db.add(ComboTagTemplate(combo_id=old.id, template_id=_template(db, "ZZT old tag")))
    db.flush()

    body = _copy(client, source, [clash], overwrite_product_ids=[clash.id]).json()
    assert body["overwritten"] == 1 and body["created"] == 0 and body["skipped"] == []
    [row] = _combos_on(db, clash)
    assert row.id == old.id, "request lines naming the combo stay linked"
    assert row.name == "Bathtub Combo"
    assert row.description == source.description
    assert row.list_price == Decimal("7588.00") and row.sell_price == Decimal("6599.00")
    assert row.free_items == "Pump, soap"
    assert row.accessory_box_preset_id == seed["preset"].id
    assert row.image_attachment_id == source.image_attachment_id
    assert _parts(db, old.id) == _parts(db, source.id)
    assert _free(db, old.id) == _free(db, source.id)
    assert _links(db, old.id) == _links(db, source.id)


def test_overwrite_without_the_template_permission_keeps_the_targets_links(db, monkeypatch):
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    source, _ = _bathtub_combo(db, with_templates=(_template(db, "ZZT combo tag A"),))
    clash = _product(db, "ZZBT1835")
    old = _existing(db, clash)
    own = _template(db, "ZZT own tag")
    db.add(ComboTagTemplate(combo_id=old.id, template_id=own, default_list=True))
    db.flush()

    body = _copy(client, source, [clash], overwrite_product_ids=[clash.id]).json()
    assert body["overwritten"] == 1 and body["template_links_copied"] is False
    assert _links(db, old.id) == [(own, True, False)]


def test_overwrite_moves_the_target_off_its_old_picture(db, monkeypatch, storage):
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    source, _ = _bathtub_combo(db)
    clash = _product(db, "ZZBT1835")
    old = _existing(db, clash)
    old_picture = _attachment(db, clash)
    old.image_attachment_id = old_picture.id
    db.flush()

    assert _copy(client, source, [clash], overwrite_product_ids=[clash.id]).status_code == 200
    db.expire_all()
    assert db.query(ProductAttachment).filter(
        ProductAttachment.product_id == clash.id, ProductAttachment.attachment_id == old_picture.id
    ).count() == 0, "the old picture leaves the target's gallery like a replace does"
    assert db.query(Attachment).filter(Attachment.id == old_picture.id).first() is None


def test_overwrite_ids_must_be_among_the_targets(db, monkeypatch):
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    source, _ = _bathtub_combo(db)
    target, stray = _product(db, "ZZBT1835"), _product(db, "ZZBT1846")
    response = _copy(client, source, [target], overwrite_product_ids=[stray.id])
    assert response.status_code == 422, response.text
    assert _combos_on(db, target) == []


# --------------------------------------------------------------------------- what is skipped / left out


def test_a_target_that_is_a_part_of_the_combo_is_skipped(db, monkeypatch):
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    source, seed = _bathtub_combo(db)
    tap = seed["taps"][0]

    body = _copy(client, source, [tap]).json()
    assert body["created"] == 0
    assert body["skipped"] == [
        {"product_id": tap.id, "code": tap.product_code, "name": tap.product_name, "reason": "part"}
    ]
    assert _combos_on(db, tap) == []


def test_a_free_item_naming_the_target_is_left_out_for_that_target(db, monkeypatch):
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    source, seed = _bathtub_combo(db)
    free = seed["free_product"]

    assert _copy(client, source, [free]).status_code == 200
    [copy] = _combos_on(db, free)
    assert [row[1] for row in _free(db, copy.id)] == [None, None], "only the two accessories"
    assert [row[2] for row in _free(db, copy.id)] == [0, 1]


def test_the_source_host_and_repeats_are_ignored(db, monkeypatch):
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    source, seed = _bathtub_combo(db)
    target = _product(db, "ZZBT1835")

    body = _copy(client, source, [seed["host"], target, target]).json()
    assert body["targets"] == 1 and body["created"] == 1
    assert len(_combos_on(db, seed["host"])) == 1
    assert len(_combos_on(db, target)) == 1


# --------------------------------------------------------------------------- all or nothing, scope, gate


def test_an_other_company_target_is_404_and_nothing_is_written(db, monkeypatch):
    _mocha(db)
    client = _caller(db, {VIEW, EDIT}, monkeypatch, company_id=None)
    source, _ = _bathtub_combo(db)
    ours, theirs = _product(db, "ZZBT1835"), _product(db, "ZZMCH", company_id=MOCHA)

    response = _copy(client, source, [ours, theirs])
    assert response.status_code == 404, response.text
    assert _combos_on(db, ours) == []


def test_a_missing_target_is_404_and_nothing_is_written(db, monkeypatch):
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    source, _ = _bathtub_combo(db)
    ours = _product(db, "ZZBT1835")
    response = _copy(client, source, [ours, str(uuid.uuid4())])
    assert response.status_code == 404, response.text
    assert _combos_on(db, ours) == []


def test_a_combo_in_another_company_is_404(db, monkeypatch):
    _mocha(db)
    source, _ = _bathtub_combo(db)
    client = _caller(db, {VIEW, EDIT}, monkeypatch, company_id=MOCHA)
    response = _copy(client, source, [_product(db, "ZZMCH", company_id=MOCHA)])
    assert response.status_code == 404, response.text


def test_view_only_is_403(db, monkeypatch):
    client = _caller(db, {VIEW}, monkeypatch)
    source, _ = _bathtub_combo(db)
    target = _product(db, "ZZBT1835")
    assert _copy(client, source, [target]).status_code == 403
    assert _combos_on(db, target) == []


@pytest.mark.parametrize("ids", [[], ["not-a-uuid"]])
def test_bad_target_lists_are_422(db, monkeypatch, ids):
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    source, _ = _bathtub_combo(db)
    assert _copy(client, source, ids).status_code == 422


def test_more_than_500_targets_is_422(db, monkeypatch):
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    source, _ = _bathtub_combo(db)
    ids = [str(uuid.uuid4()) for _ in range(501)]
    assert _copy(client, source, ids).status_code == 422


# --------------------------------------------------------------------------- shared picture stays safe


def test_clearing_one_copys_picture_keeps_it_for_the_source(db, monkeypatch, storage):
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    source, seed = _bathtub_combo(db)
    target = _product(db, "ZZBT1835")
    assert _copy(client, source, [target]).status_code == 200
    [copy] = _combos_on(db, target)
    picture = source.image_attachment_id

    assert client.delete(f"/api/v1/master-data/product-combos/{copy.id}/image").status_code == 204
    db.expire_all()
    assert db.query(Attachment).filter(Attachment.id == picture).first() is not None
    assert db.get(ProductCombo, source.id).image_attachment_id == picture


def test_clearing_a_picture_keeps_the_gallery_link_while_a_sibling_combo_shows_it(db, monkeypatch, storage):
    """Two combos on one host can point at one shared picture (a copy, renamed, copied again)."""
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    source, _ = _bathtub_combo(db)
    target = _product(db, "ZZBT1835")
    assert _copy(client, source, [target]).status_code == 200
    [first] = _combos_on(db, target)
    first.name = unique_code("Renamed")
    db.flush()
    assert _copy(client, source, [target]).status_code == 200
    second = next(c for c in _combos_on(db, target) if c.id != first.id)
    assert second.image_attachment_id == first.image_attachment_id

    assert client.delete(f"/api/v1/master-data/product-combos/{first.id}/image").status_code == 204
    db.expire_all()
    assert db.query(ProductAttachment).filter(
        ProductAttachment.product_id == target.id,
        ProductAttachment.attachment_id == second.image_attachment_id,
    ).count() == 1, "the sibling combo still shows it in this product's gallery"


def test_a_picture_shared_by_copies_survives_while_any_combo_still_shows_it(db, monkeypatch, storage):
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    source, _ = _bathtub_combo(db)
    target = _product(db, "ZZBT1835")
    assert _copy(client, source, [target]).status_code == 200
    [copy] = _combos_on(db, target)
    picture = source.image_attachment_id
    # The target's gallery link goes away by hand; only the copied combo still shows the picture.
    db.query(ProductAttachment).filter(
        ProductAttachment.product_id == target.id, ProductAttachment.attachment_id == picture
    ).delete(synchronize_session=False)
    db.flush()

    assert client.delete(f"/api/v1/master-data/product-combos/{source.id}/image").status_code == 204
    db.expire_all()
    assert db.query(Attachment).filter(Attachment.id == picture).first() is not None
    assert db.get(ProductCombo, copy.id).image_attachment_id == picture


def test_overwrite_keeps_an_old_picture_something_else_still_points_at(db, monkeypatch, storage):
    from app.models.accessory import Accessory

    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    source, _ = _bathtub_combo(db)
    clash = _product(db, "ZZBT1835")
    old = _existing(db, clash)
    uploaded = client.post(
        f"/api/v1/master-data/product-combos/{old.id}/image",
        files={"file": ("old.jpg", bytes.fromhex("ffd8ffe000104a4649460001") + b"\x00" * 32 + bytes.fromhex("ffd9"), "image/jpeg")},
    )
    assert uploaded.status_code in (200, 201), uploaded.text
    db.expire_all()
    p_old = db.get(ProductCombo, old.id).image_attachment_id
    assert p_old is not None
    accessory = _accessory(db, _name("KEEPPIC"))
    accessory.image_attachment_id = p_old
    db.flush()
    deleted: list[str] = []
    real_delete = storage.delete_file

    def spy(key):
        deleted.append(key)
        return real_delete(key)

    monkeypatch.setattr(storage, "delete_file", spy)

    assert _copy(client, source, [clash], overwrite_product_ids=[clash.id]).status_code == 200
    db.expire_all()
    assert db.query(Attachment).filter(Attachment.id == p_old).first() is not None
    assert db.get(Accessory, accessory.id).image_attachment_id == p_old
    assert deleted == [], f"storage delete issued for a picture still in use: {deleted}"


@pytest.mark.parametrize("dry_run", [True, False])
def test_no_template_permission_but_nothing_to_withhold_reports_links_copied(db, monkeypatch, dry_run):
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    source, _ = _bathtub_combo(db)
    response = _copy(client, source, [_product(db, "ZZBT1835")], dry_run=dry_run)
    assert response.status_code == 200, response.text
    assert response.json()["template_links_copied"] is True


# --------------------------------------------------------------------------- deleting a combo with a picture


def _spy_deletes(storage, monkeypatch) -> list:
    deleted: list = []
    real_delete = storage.delete_file

    def spy(key):
        deleted.append(key)
        return real_delete(key)

    monkeypatch.setattr(storage, "delete_file", spy)
    return deleted


def _gallery(db, product, attachment_id) -> int:
    db.expire_all()
    return db.query(ProductAttachment).filter(
        ProductAttachment.product_id == product.id, ProductAttachment.attachment_id == attachment_id
    ).count()


def test_deleting_a_combo_drops_a_picture_nobody_else_uses(db, monkeypatch, storage):
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    source, seed = _bathtub_combo(db)
    host, picture = seed["host"], source.image_attachment_id
    deleted = _spy_deletes(storage, monkeypatch)

    assert client.delete(f"/api/v1/master-data/product-combos/{source.id}").status_code == 204
    assert _gallery(db, host, picture) == 0, "the host's gallery link goes with the combo"
    assert db.query(Attachment).filter(Attachment.id == picture).first() is None
    assert deleted, "the stored file is swept"


def test_deleting_a_copy_leaves_the_shared_picture_for_the_source(db, monkeypatch, storage):
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    source, seed = _bathtub_combo(db)
    host, target = seed["host"], _product(db, "ZZBT1835")
    assert _copy(client, source, [target]).status_code == 200
    [copy] = _combos_on(db, target)
    picture = source.image_attachment_id
    deleted = _spy_deletes(storage, monkeypatch)

    assert client.delete(f"/api/v1/master-data/product-combos/{copy.id}").status_code == 204
    assert _gallery(db, target, picture) == 0, "the target's own gallery link goes"
    assert db.query(Attachment).filter(Attachment.id == picture).first() is not None
    assert db.get(ProductCombo, source.id).image_attachment_id == picture
    assert _gallery(db, host, picture) == 1
    assert deleted == []


def test_deleting_one_of_two_combos_on_a_host_sharing_a_picture_keeps_the_link(db, monkeypatch, storage):
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    first, seed = _bathtub_combo(db)
    host, picture = seed["host"], first.image_attachment_id
    second = ProductCombo(
        id=str(uuid.uuid4()), host_product_id=host.id, name="Second Combo", sort_order=1,
        image_attachment_id=picture,
    )
    db.add(second)
    db.flush()
    deleted = _spy_deletes(storage, monkeypatch)

    assert client.delete(f"/api/v1/master-data/product-combos/{first.id}").status_code == 204
    assert _gallery(db, host, picture) == 1
    assert db.query(Attachment).filter(Attachment.id == picture).first() is not None
    assert deleted == []
