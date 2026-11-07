"""PRICETAG-ACCESSORY-DESIGNER S6: a product or combo may name its own box style (a saved accessories
template) for its "Accessories included" list.

Plan: PLAN-pricetag-accessory-designer-07nov.md "S6 Layout flexibility / Box style override".
Written test-FIRST. Invented names (the coder must match them):
  * columns `products.accessory_box_preset_id`, `product_combos.accessory_box_preset_id`
    (FK dealer_kit.accessory_box_preset ON DELETE SET NULL), model attribute `accessory_box_preset_id`
  * list endpoints answer `{"data": [...], "box_style_id": str | None}`; PUT takes `box_style_id`
    beside `items` (omitted = unchanged, null = cleared, unknown or other-company id = 404)
  * `accessory_service.box_style_for(db, *, product_id=None, combo_id=None) -> {id, name, design} | None`
  * payload key `accessory_box_style` ({id, name, design} or None, key always present) next to every
    accessories list: product tag data, the combo object (`row["combo"]`), the line row (its combo's when
    the line has a combo, else its product's) and every slot part (that part's own product's)
  * a pinned row freezes it; a row pinned before reads None
  * migration revision `ptag_0018_acc_box_style` (down_revision `ptag_0017_acc_designer`), additive.
Note for the coder: `tests/test_migration_ptag_0017_acc_designer.py` asserts the single head is 0017 and
must be updated when 0018 lands.
"""
from __future__ import annotations

import ast
import uuid
from pathlib import Path

import pytest

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402,F401

from app.services.company_scope import register_company_scope_listeners

from tests import _ptag_combo_seed as seed
from tests._pg_fixture import blank_session, unique_code
from tests.test_accessories import (  # noqa: F401
    COMBO_LIST,
    EDIT,
    MOCHA,
    PRODUCT_LIST,
    VIEW,
    _accessory,
    _caller,
    _clear_overrides,
    _combo,
    _mocha,
    _name,
    _product,
    signed,
)

BACKEND = Path(__file__).resolve().parent.parent
REVISION_FILE = BACKEND / "alembic" / "versions" / "ptag_0018_acc_box_style.py"

DESIGN = {"direction": "horizontal", "headerText": "FREE", "columns": 2, "card": {"width_mm": 30, "height_mm": 20, "elements": []}}


@pytest.fixture()
def db():
    with blank_session() as session:
        yield session


@pytest.fixture(autouse=True)
def _scope_listeners():
    register_company_scope_listeners()


def _preset(db, name=None, *, company_id=seed.SORENTO, design=None):
    from app.models.dealer_kit import AccessoryBoxPreset

    row = AccessoryBoxPreset(
        id=str(uuid.uuid4()), company_id=company_id, name=name or unique_code("ZZT style"), design=design or dict(DESIGN)
    )
    db.add(row)
    db.flush()
    return row


def _put(client, url, **body):
    return client.put(url, json={"items": [], **body})


# --------------------------------------------------------------------------- endpoints


@pytest.mark.parametrize("kind", ["product", "combo"])
def test_a_new_list_has_no_box_style(db, monkeypatch, kind):
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    host = _product(db, "ZZSTY")
    url = _url(db, kind, host)
    body = client.get(url).json()
    assert body["data"] == [] and body["box_style_id"] is None


def _url(db, kind, host):
    if kind == "product":
        return PRODUCT_LIST.format(product_id=host.id)
    return COMBO_LIST.format(combo_id=_combo(db, host, "ZZT 1 tap").id)


@pytest.mark.parametrize("kind", ["product", "combo"])
def test_put_sets_reads_keeps_and_clears_the_box_style(db, monkeypatch, kind):
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    host = _product(db, "ZZSTY")
    url = _url(db, kind, host)
    preset = _preset(db)
    item = _accessory(db, _name("BOARD"))

    set_ = _put(client, url, items=[{"accessory_id": item.id}], box_style_id=preset.id)
    assert set_.status_code == 200, set_.text
    assert set_.json()["box_style_id"] == preset.id
    assert client.get(url).json()["box_style_id"] == preset.id

    omitted = client.put(url, json={"items": [{"accessory_id": item.id}]})
    assert omitted.status_code == 200
    assert omitted.json()["box_style_id"] == preset.id, "omitted = unchanged"

    cleared = _put(client, url, items=[{"accessory_id": item.id}], box_style_id=None)
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["box_style_id"] is None, "null = cleared"
    assert client.get(url).json()["box_style_id"] is None


@pytest.mark.parametrize("kind", ["product", "combo"])
def test_an_unknown_or_other_companys_style_is_404_and_changes_nothing(db, monkeypatch, kind):
    _mocha(db)
    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    host = _product(db, "ZZSTY")
    url = _url(db, kind, host)
    mine = _preset(db)
    theirs = _preset(db, company_id=MOCHA)
    assert _put(client, url, box_style_id=mine.id).status_code == 200
    assert _put(client, url, box_style_id=str(uuid.uuid4())).status_code == 404
    assert _put(client, url, box_style_id=theirs.id).status_code == 404
    assert client.get(url).json()["box_style_id"] == mine.id


def test_view_only_cannot_set_a_box_style(db, monkeypatch):
    client = _caller(db, {VIEW}, monkeypatch)
    host = _product(db, "ZZSTY")
    preset = _preset(db)
    assert _put(client, PRODUCT_LIST.format(product_id=host.id), box_style_id=preset.id).status_code == 403


# --------------------------------------------------------------------------- box_style_for


def test_box_style_for_returns_id_name_design_or_none(db):
    from app.services.accessory_service import box_style_for

    host = seed.product(db, "ZZSTY")
    cb = seed.combo(db, host, "ZZT 1 tap")
    assert box_style_for(db, product_id=host.id) is None
    assert box_style_for(db, combo_id=cb.id) is None
    assert box_style_for(db) is None

    preset = _preset(db, "FREE vertical")
    host.accessory_box_preset_id = preset.id
    db.flush()
    assert box_style_for(db, product_id=host.id) == {"id": preset.id, "name": "FREE vertical", "design": DESIGN}
    assert box_style_for(db, combo_id=cb.id) is None, "a combo never inherits its host's style"

    other = _preset(db, "Row of three")
    cb.accessory_box_preset_id = other.id
    db.flush()
    assert box_style_for(db, combo_id=cb.id)["id"] == other.id
    assert box_style_for(db, product_id=host.id)["id"] == preset.id


def test_deleting_the_preset_clears_the_overrides(db):
    from app.models.dealer_kit import AccessoryBoxPreset

    host = seed.product(db, "ZZSTY")
    cb = seed.combo(db, host, "ZZT 1 tap")
    preset = _preset(db)
    host.accessory_box_preset_id = preset.id
    cb.accessory_box_preset_id = preset.id
    db.flush()
    db.query(AccessoryBoxPreset).filter(AccessoryBoxPreset.id == preset.id).delete(synchronize_session=False)
    db.flush()
    db.expire_all()
    db.refresh(host)
    db.refresh(cb)
    assert host.accessory_box_preset_id is None and cb.accessory_box_preset_id is None


# --------------------------------------------------------------------------- tag payload


def _style(preset):
    return {"id": preset.id, "name": preset.name, "design": preset.design}


def test_product_tag_data_carries_its_box_style(db, signed):
    from app.services.dealer_kit.tag_data_service import product_tag_data, staff_viewer

    host = seed.product(db, "ZZSTY")
    assert product_tag_data(db, host, staff_viewer())["accessory_box_style"] is None
    preset = _preset(db)
    host.accessory_box_preset_id = preset.id
    db.flush()
    assert product_tag_data(db, host, staff_viewer())["accessory_box_style"] == _style(preset)


def test_a_combo_line_row_carries_the_combos_style_on_the_row_and_the_combo_object(db, signed):
    host = seed.product(db, "ZZSTY")
    cb = seed.combo(db, host, "ZZT 1 tap")
    combo_style, product_style = _preset(db, "Combo style"), _preset(db, "Product style")
    cb.accessory_box_preset_id = combo_style.id
    host.accessory_box_preset_id = product_style.id
    db.flush()
    request = seed.submit_one(db, host, cb, [])
    db.flush()
    (row,) = seed.rows(db, request)
    assert row["combo"]["accessory_box_style"] == _style(combo_style)
    assert row["accessory_box_style"] == _style(combo_style), "a combo line: the combo's, not the product's"


def test_a_combo_line_without_a_combo_style_never_borrows_the_products(db, signed):
    host = seed.product(db, "ZZSTY")
    cb = seed.combo(db, host, "ZZT 1 tap")
    host.accessory_box_preset_id = _preset(db).id
    db.flush()
    request = seed.submit_one(db, host, cb, [])
    db.flush()
    (row,) = seed.rows(db, request)
    assert row["combo"]["accessory_box_style"] is None
    assert row["accessory_box_style"] is None


def test_an_ala_carte_line_row_carries_the_products_style(db, signed):
    host = seed.product(db, "ZZSTY")
    preset = _preset(db)
    host.accessory_box_preset_id = preset.id
    db.flush()
    request = seed.submit_one(db, host, None, [])
    db.flush()
    (row,) = seed.rows(db, request)
    assert row["accessory_box_style"] == _style(preset)


def test_a_row_with_no_style_carries_the_key_as_none(db, signed):
    host = seed.product(db, "ZZSTY")
    request = seed.submit_one(db, host, None, [])
    db.flush()
    (row,) = seed.rows(db, request)
    assert "accessory_box_style" in row and row["accessory_box_style"] is None


def test_slot_parts_carry_their_own_products_style(db, signed):
    host = seed.product(db, "ZZSTY")
    tap = seed.product(db, "ZZTAP")
    cb = seed.combo(db, host, "ZZT 1 tap", parts=[{"product": tap}])
    host_style, tap_style = _preset(db, "Host style"), _preset(db, "Tap style")
    host.accessory_box_preset_id = host_style.id
    tap.accessory_box_preset_id = tap_style.id
    db.flush()
    request = seed.submit_one(db, host, cb, [{"product_id": tap.id}])
    db.flush()
    (row,) = seed.rows(db, request)
    slots = row["slots"]
    assert slots["main"]["accessory_box_style"] == _style(host_style)
    fixed = [part for part in slots["fixed"] if part.get("code") == tap.product_code]
    assert fixed and fixed[0]["accessory_box_style"] == _style(tap_style)


# --------------------------------------------------------------------------- pins


def test_a_pinned_row_freezes_the_style_and_an_old_pin_reads_none(db, signed):
    from app.services.dealer_kit import tag_data_service

    host = seed.product(db, "ZZSTY")
    preset = _preset(db, "Frozen")
    host.accessory_box_preset_id = preset.id
    db.flush()
    request = seed.submit_one(db, host, None, [])
    db.flush()
    live = tag_data_service.resolve_tags_live(db, request)[0]
    pinned = tag_data_service.pin_payload(live)
    line = request.lines[0]

    preset.name = "Renamed"
    preset.design = {**DESIGN, "headerText": "CHANGED"}
    host.accessory_box_preset_id = None
    db.flush()
    row = tag_data_service._row_from_pin(db, line, line.tags[0], pinned, "1a")
    assert row["accessory_box_style"] == {"id": preset.id, "name": "Frozen", "design": DESIGN}

    old = {k: v for k, v in pinned.items() if k != "accessory_box_style"}
    old_row = tag_data_service._row_from_pin(db, line, line.tags[0], old, "1a")
    assert old_row["accessory_box_style"] is None


# --------------------------------------------------------------------------- migration


def test_revision_0018_is_additive_and_chains_onto_one_head():
    source = REVISION_FILE.read_text().split("def downgrade", 1)[0]
    tree = ast.parse(REVISION_FILE.read_text())
    assigns = {
        node.targets[0].id: node.value.value
        for node in tree.body
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) and isinstance(node.value, ast.Constant)
    }
    assert assigns["revision"] == "ptag_0018_acc_box_style"
    assert len(assigns["revision"]) <= 32
    assert assigns["down_revision"] == "ptag_0017_acc_designer"
    for word in ("drop_table", "drop_column", "DROP TABLE", "DROP COLUMN", "DELETE FROM"):
        assert word not in source, f"upgrade is additive only: found {word}"
    for needle in ("accessory_box_preset_id", "products", "product_combos", "SET NULL", "accessory_box_preset"):
        assert needle in source, f"the migration never mentions {needle}"

    from alembic.config import Config
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(Config(str(BACKEND / "alembic.ini")))
    assert script.get_heads() == ["ptag_0018_acc_box_style"]
