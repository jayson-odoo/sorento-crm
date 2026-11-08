"""PRICETAG-ACCESSORY-DESIGNER S7: migration `ptag_0019_acc_colours` (pictures and colours independent).

Plan: "S7 Pictures and colours are independent". Additive; the data step `copy_picture_colours(bind)` copies
each accessory's picture colours (distinct hex, in picture order, name kept) into `accessory_colours`, skipping
any already there, so it is idempotent. Written test-FIRST: the revision file does not exist yet.
Invented: model `app.models.accessory.AccessoryColour` (id, accessory_id, name, hex, sort_order).
"""
from __future__ import annotations

import ast
import hashlib
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
REVISION_FILE = BACKEND / "alembic" / "versions" / "ptag_0019_acc_colours.py"


@pytest.fixture()
def db():
    with blank_session() as session:
        yield session


@pytest.fixture(autouse=True)
def _quiet(monkeypatch):
    r9.block_respond(monkeypatch)


def _revision():
    spec = importlib.util.spec_from_file_location("ptag_0019_acc_colours", REVISION_FILE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _attachment(db, stem):
    from app.models.resources import Attachment, AttachmentType

    kind = db.query(AttachmentType).filter(AttachmentType.code == "accessory_image").first()
    if kind is None:
        kind = AttachmentType(
            id=str(uuid.uuid4()), code="accessory_image", type_name="Accessory Image",
            allowed_extensions="jpg,jpeg,png,webp", max_file_size_mb=10,
        )
        db.add(kind)
        db.flush()
    row = Attachment(
        id=str(uuid.uuid4()), attachment_type_id=kind.id, original_filename=f"{stem}.jpg",
        stored_filename=f"{stem}.jpg", file_path=f"https://cdn.test/accessory_image/{stem}.jpg",
        file_size_bytes=10, mime_type="image/jpeg", file_hash=hashlib.sha256(stem.encode()).hexdigest(),
        entity_type="general", uploader_kind="system", storage_provider="s3", company_id=seed.SORENTO,
    )
    db.add(row)
    db.flush()
    return row


def _accessory(db, pictures):
    """`pictures` = [(name, hex)] in picture order (None = no colour)."""
    from app.models.accessory import Accessory, AccessoryImage

    acc = Accessory(id=str(uuid.uuid4()), company_id=seed.SORENTO, name=unique_code("ZZT ACC").upper())
    db.add(acc)
    db.flush()
    for index, (name, hex_value) in enumerate(pictures):
        att = _attachment(db, unique_code("pic"))
        db.add(
            AccessoryImage(
                id=str(uuid.uuid4()), accessory_id=acc.id, attachment_id=att.id, sort_order=index,
                colour_name=name, colour_hex=hex_value,
            )
        )
    db.flush()
    return acc


def _copy(db):
    _revision().copy_picture_colours(db.connection())
    db.expire_all()


def _colours(db, accessory):
    from app.models.accessory import AccessoryColour

    rows = (
        db.query(AccessoryColour)
        .filter(AccessoryColour.accessory_id == accessory.id)
        .order_by(AccessoryColour.sort_order)
        .all()
    )
    return [(row.name, row.hex.lower()) for row in rows]


def test_revision_is_additive_and_chains_onto_one_head():
    tree = ast.parse(REVISION_FILE.read_text())
    assigns = {
        node.targets[0].id: node.value.value
        for node in tree.body
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) and isinstance(node.value, ast.Constant)
    }
    assert assigns["revision"] == "ptag_0019_acc_colours"
    assert len(assigns["revision"]) <= 32
    assert assigns["down_revision"] == "ptag_0018_acc_box_style"

    source = REVISION_FILE.read_text().split("def downgrade", 1)[0]
    for word in ("drop_table", "drop_column", "DROP TABLE", "DROP COLUMN", "DELETE FROM"):
        assert word not in source, f"upgrade is additive only: found {word}"
    for needle in ("accessory_colours", "lower(hex)", "sort_order", "CASCADE", "copy_picture_colours"):
        assert needle in REVISION_FILE.read_text(), f"the migration never mentions {needle}"

    from alembic.config import Config
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(Config(str(BACKEND / "alembic.ini")))
    heads = script.get_heads()
    assert len(heads) == 1
    ancestry = {rev.revision for rev in script.walk_revisions(base="base", head=heads[0])}
    assert "ptag_0019_acc_colours" in ancestry


def test_picture_colours_become_the_colours_list_in_picture_order(db):
    acc = _accessory(db, [("Black", "#1f2937"), ("Grey", "#9ca3af"), ("Black again", "#1F2937")])
    _copy(db)
    assert _colours(db, acc) == [("Black", "#1f2937"), ("Grey", "#9ca3af")]


def test_a_picture_with_no_colour_adds_nothing(db):
    acc = _accessory(db, [(None, None), ("Gold", "#d4af37"), (None, None)])
    _copy(db)
    assert _colours(db, acc) == [("Gold", "#d4af37")]
    bare = _accessory(db, [(None, None)])
    _copy(db)
    assert _colours(db, bare) == []


def test_a_colour_with_a_hex_but_no_name_keeps_a_null_name(db):
    acc = _accessory(db, [(None, "#c0c0c0")])
    _copy(db)
    assert _colours(db, acc) == [(None, "#c0c0c0")]


def test_running_twice_inserts_nothing_new(db):
    acc = _accessory(db, [("Black", "#1f2937"), ("Grey", "#9ca3af")])
    _copy(db)
    _copy(db)
    assert _colours(db, acc) == [("Black", "#1f2937"), ("Grey", "#9ca3af")]


def test_a_colour_already_in_the_list_is_skipped_and_the_rest_appended(db):
    from app.models.accessory import AccessoryColour

    acc = _accessory(db, [("Black", "#1f2937"), ("Grey", "#9ca3af")])
    db.add(AccessoryColour(id=str(uuid.uuid4()), accessory_id=acc.id, name="Own black", hex="#1F2937", sort_order=0))
    db.flush()
    _copy(db)
    got = _colours(db, acc)
    assert got[0] == ("Own black", "#1f2937"), "the existing entry is left as it was"
    assert got[1:] == [("Grey", "#9ca3af")]


def test_each_accessory_is_handled_on_its_own(db):
    one = _accessory(db, [("Black", "#1f2937")])
    two = _accessory(db, [("Black", "#1f2937"), ("Gold", "#d4af37")])
    _copy(db)
    assert _colours(db, one) == [("Black", "#1f2937")]
    assert _colours(db, two) == [("Black", "#1f2937"), ("Gold", "#d4af37")]


def test_the_picture_colour_columns_stay_untouched(db):
    from app.models.accessory import AccessoryImage

    acc = _accessory(db, [("Black", "#1f2937")])
    _copy(db)
    (image,) = db.query(AccessoryImage).filter(AccessoryImage.accessory_id == acc.id).all()
    assert (image.colour_name, image.colour_hex) == ("Black", "#1f2937")


def test_the_first_non_empty_name_for_a_hex_wins_across_pictures(db):
    acc = _accessory(db, [(None, "#1f2937"), ("Black", "#1f2937"), ("Other", "#1F2937")])
    _copy(db)
    assert _colours(db, acc) == [("Black", "#1f2937")]
