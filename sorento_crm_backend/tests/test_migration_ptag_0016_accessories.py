"""PRICETAG-ACCESSORIES A12: the one-off move of the old free text into the library + lists.

Owner ruling Q5 (6 Nov ~10:00): combo "Free items" and the request-line included text become the
one accessories system; existing values migrate into library items + lists, de-duplicated by name.
Splitting follows card Q-M1 (a): line breaks, commas and " + ".

The data step lives in the migration as `move_free_text(bind)` so the SAME SQL runs in alembic and
here; this file loads the revision module by path and runs it against the blank test schema.

Written test-FIRST: the revision file does not exist yet.
"""
from __future__ import annotations

import ast
import importlib.util
import uuid
from pathlib import Path

import pytest

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402,F401

from tests import _ptag_combo_seed as seed
from tests import _ptag_r9_seed as r9
from tests._pg_fixture import blank_session, unique_code

BACKEND = Path(__file__).resolve().parent.parent
REVISION_FILE = BACKEND / "alembic" / "versions" / "ptag_0016_accessories.py"


@pytest.fixture()
def db():
    with blank_session() as session:
        yield session


@pytest.fixture(autouse=True)
def _quiet(monkeypatch):
    r9.block_respond(monkeypatch)


def _revision():
    spec = importlib.util.spec_from_file_location("ptag_0016_accessories", REVISION_FILE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _move(db):
    _revision().move_free_text(db.connection())
    db.expire_all()


def _combo_names(db, combo):
    from app.models.accessory import Accessory, ProductComboAccessory

    rows = (
        db.query(Accessory.name)
        .join(ProductComboAccessory, ProductComboAccessory.accessory_id == Accessory.id)
        .filter(ProductComboAccessory.combo_id == combo.id)
        .order_by(ProductComboAccessory.sort_order)
        .all()
    )
    return [name for (name,) in rows]


def _product_names(db, product):
    from app.models.accessory import Accessory, ProductAccessory

    rows = (
        db.query(Accessory.name)
        .join(ProductAccessory, ProductAccessory.accessory_id == Accessory.id)
        .filter(ProductAccessory.product_id == product.id)
        .order_by(ProductAccessory.sort_order)
        .all()
    )
    return [name for (name,) in rows]


def _library(db, names):
    from sqlalchemy import func

    from app.models.accessory import Accessory

    wanted = [name.lower() for name in names]
    return db.query(Accessory).filter(func.lower(Accessory.name).in_(wanted)).all()


def _tag(stem: str) -> str:
    """A unique item name so runs never collide with a library row from another test."""
    return unique_code(stem).upper()


# --------------------------------------------------------------------------- the file


def test_revision_is_additive_and_chains_onto_one_head():
    source = REVISION_FILE.read_text()
    tree = ast.parse(source)
    assigns = {
        node.targets[0].id: node.value.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        and isinstance(node.targets[0], ast.Name)
        and isinstance(node.value, ast.Constant)
    }
    assert assigns["revision"] == "ptag_0016_accessories"
    assert len(assigns["revision"]) <= 32
    for word in ("drop_column", "alter_column", "DROP CONSTRAINT", "DELETE FROM", "UPDATE "):
        upgrade_src = source.split("def downgrade", 1)[0]
        assert word not in upgrade_src, f"upgrade is additive only: found {word}"

    from alembic.config import Config
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(Config(str(BACKEND / "alembic.ini")))
    # One head, with this revision in its ancestry: later revisions chain on top of it.
    heads = script.get_heads()
    assert len(heads) == 1, f"expected one alembic head, found {heads}"
    ancestry = {rev.revision for rev in script.walk_revisions(base="base", head=heads[0])}
    assert "ptag_0016_accessories" in ancestry


def test_split_rule():
    split = _revision().SPLIT_PATTERN
    import re

    def parts(text):
        return [p.strip() for p in re.split(split, text) if p.strip()]

    assert parts("ZZTBK800 DRAINER, CHOPPING BOARD") == ["ZZTBK800 DRAINER", "CHOPPING BOARD"]
    assert parts("Drainer\nPull out drainer") == ["Drainer", "Pull out drainer"]
    assert parts("Drainer + Colander") == ["Drainer", "Colander"]
    assert parts("A+B") == ["A+B"], "a plus without spaces is part of a name"


# --------------------------------------------------------------------------- combos


def test_combo_free_items_become_its_ordered_list(db):
    drainer, pullout = _tag("DRAINER"), _tag("PULL OUT DRAINER")
    host = seed.product(db, "ZZMIG")
    cb = seed.combo(db, host, "ZZT 1 tap", free_items=f"{drainer}, {pullout}")
    _move(db)
    assert _combo_names(db, cb) == [drainer, pullout]
    assert _product_names(db, host) == [], "the product keeps its own (empty) list"


def test_names_deduplicate_ignoring_case_and_the_first_spelling_wins(db):
    drainer = _tag("DRAINER")
    host = seed.product(db, "ZZMIG")
    first = seed.combo(db, host, "ZZT a", free_items=drainer)
    second = seed.combo(db, host, "ZZT b", free_items=f"  {drainer.lower()} ")
    _move(db)
    library = _library(db, [drainer])
    assert len(library) == 1
    assert _combo_names(db, first) == _combo_names(db, second) == [library[0].name]


def test_the_same_name_twice_in_one_text_is_listed_once(db):
    drainer = _tag("DRAINER")
    cb = seed.combo(db, seed.product(db, "ZZMIG"), "ZZT a", free_items=f"{drainer}, {drainer}")
    _move(db)
    assert _combo_names(db, cb) == [drainer]


def test_a_combo_that_already_has_a_list_is_left_alone(db):
    from app.models.accessory import Accessory, ProductComboAccessory

    kept = Accessory(id=str(uuid.uuid4()), company_id=seed.SORENTO, name=_tag("KEPT"))
    db.add(kept)
    db.flush()
    cb = seed.combo(db, seed.product(db, "ZZMIG"), "ZZT a", free_items=_tag("IGNORED"))
    db.add(ProductComboAccessory(id=str(uuid.uuid4()), combo_id=cb.id, accessory_id=kept.id, sort_order=0))
    db.flush()
    _move(db)
    assert _combo_names(db, cb) == [kept.name]


def test_a_blank_text_adds_nothing(db):
    cb = seed.combo(db, seed.product(db, "ZZMIG"), "ZZT a", free_items="  ,  \n ")
    _move(db)
    assert _combo_names(db, cb) == []


def test_library_rows_belong_to_the_host_products_company(db):
    from app.models.accessory import Accessory

    name = _tag("SCOPED")
    seed.combo(db, seed.product(db, "ZZMIG"), "ZZT a", free_items=name)
    _move(db)
    row = db.query(Accessory).filter(Accessory.name == name).one()
    assert row.company_id == seed.SORENTO


def test_running_twice_adds_nothing_new(db):
    from app.models.accessory import Accessory, ProductComboAccessory

    name = _tag("TWICE")
    cb = seed.combo(db, seed.product(db, "ZZMIG"), "ZZT a", free_items=name)
    _move(db)
    _move(db)
    assert db.query(Accessory).filter(Accessory.name == name).count() == 1
    assert db.query(ProductComboAccessory).filter(ProductComboAccessory.combo_id == cb.id).count() == 1


# --------------------------------------------------------------------------- request lines


def test_a_line_text_fills_its_combo_when_that_combo_has_none(db):
    name = _tag("LINE")
    host = seed.product(db, "ZZMIG")
    cb = seed.combo(db, host, "ZZT a")
    seed.submit_one(db, host, cb, [], included_accessories=name)
    db.flush()
    _move(db)
    assert _combo_names(db, cb) == [name]
    assert _product_names(db, host) == []


def test_a_line_text_never_overwrites_a_combo_list(db):
    combo_item, line_item = _tag("COMBO"), _tag("LINE")
    host = seed.product(db, "ZZMIG")
    cb = seed.combo(db, host, "ZZT a", free_items=combo_item)
    seed.submit_one(db, host, cb, [], included_accessories=line_item)
    db.flush()
    _move(db)
    assert _combo_names(db, cb) == [combo_item]
    assert _product_names(db, host) == [], "a combo line's text does not spill onto the product"


def test_an_ala_carte_line_text_fills_its_product_when_empty(db):
    name = _tag("ALACARTE")
    host = seed.product(db, "ZZMIG")
    seed.submit_one(db, host, None, [], included_accessories=name)
    db.flush()
    _move(db)
    assert _product_names(db, host) == [name]


# --------------------------------------------------------------------------- product entries
# Owner, 6 Nov ~10:45: a free item can be a real product. The importer wrote "CODE label"; a piece
# whose FIRST word is a product code of the same company becomes a product entry.


def _combo_entries(db, combo):
    from app.models.accessory import ProductComboAccessory

    rows = (
        db.query(ProductComboAccessory)
        .filter(ProductComboAccessory.combo_id == combo.id)
        .order_by(ProductComboAccessory.sort_order)
        .all()
    )
    return [("product", r.item_product_id) if r.item_product_id else ("accessory", r.accessory_id) for r in rows]


def test_a_piece_led_by_a_product_code_becomes_a_product_entry(db):
    waste = seed.product(db, "ZZWASTE")
    host = seed.product(db, "ZZMIG")
    other = _tag("CHOPPING BOARD")
    cb = seed.combo(db, host, "ZZT a", free_items=f"{waste.product_code} Popup waste, {other}")
    _move(db)
    entries = _combo_entries(db, cb)
    assert entries[0] == ("product", waste.id)
    assert entries[1][0] == "accessory"
    assert _library(db, [f"{waste.product_code} Popup waste"]) == [], "no library row for a product"


def test_a_code_from_another_company_is_not_a_product_entry(db):
    from tests.test_product_combos import MOCHA, _mocha

    _mocha(db)
    theirs = seed.product(db, "ZZTHEIRS", company_id=MOCHA)
    cb = seed.combo(db, seed.product(db, "ZZMIG"), "ZZT a", free_items=f"{theirs.product_code} thing")
    _move(db)
    assert _combo_entries(db, cb)[0][0] == "accessory"


def test_a_piece_naming_the_host_itself_stays_a_library_accessory(db):
    host = seed.product(db, "ZZMIG")
    cb = seed.combo(db, host, "ZZT a", free_items=f"{host.product_code} spare")
    _move(db)
    assert _combo_entries(db, cb)[0][0] == "accessory"


def test_a_piece_naming_a_combo_part_stays_a_library_accessory(db):
    host = seed.product(db, "ZZMIG")
    tap = seed.product(db, "ZZTAP")
    cb = seed.combo(db, host, "ZZT a", parts=[{"product": tap}], free_items=f"{tap.product_code} spare")
    _move(db)
    assert _combo_entries(db, cb)[0][0] == "accessory"


def test_a_line_piece_naming_its_own_product_stays_a_library_accessory(db):
    host = seed.product(db, "ZZMIG")
    seed.submit_one(db, host, None, [], included_accessories=f"{host.product_code} spare")
    db.flush()
    _move(db)
    from app.models.accessory import ProductAccessory

    (row,) = db.query(ProductAccessory).filter(ProductAccessory.product_id == host.id).all()
    assert row.item_product_id is None and row.accessory_id is not None
