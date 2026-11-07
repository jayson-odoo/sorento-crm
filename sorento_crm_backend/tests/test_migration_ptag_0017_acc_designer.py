"""PRICETAG-ACCESSORY-DESIGNER S1: migration `ptag_0017_acc_designer`.

Plan: PLAN-pricetag-accessory-designer-07nov.md "Migration". Additive; the data step copies each
`accessories.image_attachment_id` into `accessory_images` (sort 0, no colour) and is idempotent.

Contract assumed here (the plan names no function): the revision module exposes
`copy_images(bind)`, the SAME SQL alembic runs, exactly as ptag_0016 exposes `move_free_text(bind)`.
Written test-FIRST: the revision file does not exist yet.
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
REVISION_FILE = BACKEND / "alembic" / "versions" / "ptag_0017_acc_designer.py"


@pytest.fixture()
def db():
    with blank_session() as session:
        yield session


@pytest.fixture(autouse=True)
def _quiet(monkeypatch):
    r9.block_respond(monkeypatch)


def _revision():
    spec = importlib.util.spec_from_file_location("ptag_0017_acc_designer", REVISION_FILE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _upgrade_source() -> str:
    return REVISION_FILE.read_text().split("def downgrade", 1)[0]


def _attachment(db, stem="pic"):
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


def _accessory(db, *, attachment=None):
    from app.models.accessory import Accessory

    row = Accessory(
        id=str(uuid.uuid4()), company_id=seed.SORENTO, name=unique_code("ZZT ACC").upper(),
        image_attachment_id=attachment.id if attachment else None,
    )
    db.add(row)
    db.flush()
    return row


def _copy(db):
    _revision().copy_images(db.connection())
    db.expire_all()


def _rows(db, accessory):
    from app.models.accessory import AccessoryImage

    return db.query(AccessoryImage).filter(AccessoryImage.accessory_id == accessory.id).all()


def test_revision_is_additive_and_chains_onto_one_head():
    source = _upgrade_source()
    tree = ast.parse(REVISION_FILE.read_text())
    assigns = {
        node.targets[0].id: node.value.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        and isinstance(node.targets[0], ast.Name)
        and isinstance(node.value, ast.Constant)
    }
    assert assigns["revision"] == "ptag_0017_acc_designer"
    assert len(assigns["revision"]) <= 32
    for word in ("drop_table", "drop_column", "DROP TABLE", "DROP COLUMN", "DELETE FROM"):
        assert word not in source, f"upgrade is additive only: found {word}"

    from alembic.config import Config
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(Config(str(BACKEND / "alembic.ini")))
    # One head, with this revision in its ancestry: later revisions chain on top of it.
    heads = script.get_heads()
    assert len(heads) == 1, f"expected one alembic head, found {heads}"
    ancestry = {rev.revision for rev in script.walk_revisions(base="base", head=heads[0])}
    assert "ptag_0017_acc_designer" in ancestry


def test_the_revision_declares_every_new_column_and_the_preset_table():
    source = _upgrade_source()
    for needle in (
        "accessory_images",
        "colour_hex",
        "colour_name",
        "sort_order",
        "image_id",
        "name_override",
        "spec_override",
        "remark_override",
        "remark",
        "accessory_box_preset",
        "lower(name)",
    ):
        assert needle in source, f"the migration never mentions {needle}"


def test_the_data_step_copies_the_old_picture_as_image_one(db):
    pic = _attachment(db, "one")
    acc = _accessory(db, attachment=pic)
    _copy(db)
    (row,) = _rows(db, acc)
    assert row.attachment_id == pic.id
    assert row.sort_order == 0
    assert row.colour_hex is None and row.colour_name is None


def test_an_accessory_without_a_picture_gets_no_row(db):
    acc = _accessory(db)
    _copy(db)
    assert _rows(db, acc) == []


def test_running_twice_adds_nothing_new(db):
    pic = _attachment(db, "twice")
    acc = _accessory(db, attachment=pic)
    _copy(db)
    _copy(db)
    assert len(_rows(db, acc)) == 1


def test_an_accessory_already_holding_that_picture_is_not_duplicated(db):
    from app.models.accessory import AccessoryImage

    pic = _attachment(db, "held")
    acc = _accessory(db, attachment=pic)
    db.add(AccessoryImage(id=str(uuid.uuid4()), accessory_id=acc.id, attachment_id=pic.id, sort_order=0,
                          colour_name="Black", colour_hex="#1f2937"))
    db.flush()
    _copy(db)
    (row,) = _rows(db, acc)
    assert row.colour_hex == "#1f2937", "the existing row is left as it was"


def test_the_old_column_stays_and_is_not_cleared(db):
    pic = _attachment(db, "kept")
    acc = _accessory(db, attachment=pic)
    _copy(db)
    db.refresh(acc)
    assert acc.image_attachment_id == pic.id
