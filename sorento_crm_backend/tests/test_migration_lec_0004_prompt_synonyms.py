"""Review fix round 6, R6-2: data migration lec_0004_prompt_synonyms moves the former PROMPT_SYNONYMS into data.

Replaces the retired scripts/move_prompt_synonyms.py (its tests are ported here). Raw SQL migration, run on a
rolled-back blank-schema connection.
"""
from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory

from app.models.lookup import LookupOption, LookupOptionKeyword, LookupSet
from app.models.product import ProductCategory
from app.models.resources import AttachmentType
from tests._pg_fixture import blank_session

BACKEND = Path(__file__).resolve().parents[1]
MIGRATION = BACKEND / "alembic" / "versions" / "lec_0004_prompt_synonyms.py"
REVISION = "lec_0004_prompt_synonyms"
ALIAS_SET_KEY = "attachment_type_alias"

CATEGORY_WORDS = {
    "water tap": ("paip air", "kepala paip", "水龙头"),
    "water closet": ("tandas", "mangkuk tandas", "马桶"),
    "kitchen sink": ("sinki dapur", "厨房水槽"),
}
FILE_TYPE_WORDS = {
    "photo": ("gambar", "foto", "image", "picture", "imej"),
    "image": ("imej", "gambar", "foto", "picture"),
    "video": ("videos",),
    "drawing": ("lukisan",),
    "technical drawing": ("lukisan teknikal", "lukisan", "cad", "blueprint"),
    "3d model": ("model 3d",),
    "installation guide": ("installation manual",),
    "certificate": ("sijil", "cert", "ikram"),
}


@pytest.fixture
def db():
    with blank_session() as s:
        yield s


def _load():
    assert MIGRATION.exists(), f"missing {MIGRATION.name}"
    spec = importlib.util.spec_from_file_location("m_lec_0004", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _call(db, fn="upgrade"):
    db.flush()
    ctx = MigrationContext.configure(db.connection())
    with Operations.context(ctx):
        getattr(_load(), fn)()
    db.expire_all()


def _cat(db, name, *, class_label=None, synonyms=(), active=True):
    c = ProductCategory(
        id=str(uuid.uuid4()), category_code=f"ZZT-{uuid.uuid4().hex[:8]}", category_name=name,
        class_label=class_label, search_synonyms=list(synonyms), is_active=active, is_searchable=True,
    )
    db.add(c)
    db.flush()
    return c


def _syn(db, cat):
    return list(db.get(ProductCategory, cat.id).search_synonyms or [])


def _type(db, code, name):
    t = AttachmentType(id=str(uuid.uuid4()), code=code, type_name=name, allowed_extensions="jpg")
    db.add(t)
    db.flush()
    return t


def _keywords(db):
    return [k.keyword for k in db.query(LookupOptionKeyword).all()]


# ------------------------------------------------------------------ the revision


def test_revision_id_chain_and_single_head():
    m = _load()
    assert m.revision == REVISION and len(REVISION) <= 32
    assert m.down_revision == "lec_0003_lookup_words_sync"
    script = ScriptDirectory.from_config(Config(str(BACKEND / "alembic.ini")))
    heads = script.get_heads()
    assert len(heads) == 1
    assert REVISION in {r.revision for r in script.walk_revisions(base="base", head=heads[0])}


def test_the_script_is_gone_one_copy_of_the_word_list():
    assert not (BACKEND / "scripts" / "move_prompt_synonyms.py").exists()


# ------------------------------------------------------------------ category words


def test_category_words_append_in_list_order_skipping_present_ones_case_aside(db):
    a = _cat(db, "ZZT WC A", class_label="Water Closet", synonyms=["Tandas"])
    b = _cat(db, "ZZT WC B", class_label="water closet", synonyms=[])
    _call(db)
    assert _syn(db, a) == ["Tandas", "mangkuk tandas", "马桶"]
    assert _syn(db, b) == list(CATEGORY_WORDS["water closet"])


def test_inactive_and_other_class_categories_are_untouched(db):
    off = _cat(db, "ZZT WC Off", class_label="Water Closet", synonyms=[], active=False)
    sink = _cat(db, "ZZT Basin", class_label="Basin", synonyms=["x"])
    _call(db)
    assert _syn(db, off) == [] and _syn(db, sink) == ["x"]
    assert "mangkuk tandas" not in _syn(db, sink)


def test_water_tap_matches_class_water_tap_and_class_tap(db):
    wt = _cat(db, "ZZT WT", class_label="Water Tap")
    tap = _cat(db, "ZZT Tap", class_label="Tap")
    _call(db)
    assert _syn(db, wt) == list(CATEGORY_WORDS["water tap"])
    assert _syn(db, tap) == list(CATEGORY_WORDS["water tap"])


def test_a_category_is_matched_by_its_own_name_case_aside(db):
    c = _cat(db, "Kitchen Sink", class_label="Other", synonyms=[])
    _call(db)
    assert _syn(db, c) == list(CATEGORY_WORDS["kitchen sink"])


def test_second_upgrade_adds_nothing_to_categories(db):
    a = _cat(db, "ZZT WC A", class_label="Water Closet", synonyms=["tandas"])
    _call(db)
    first = _syn(db, a)
    _call(db)
    assert _syn(db, a) == first and first.count("mangkuk tandas") == 1 and first.count("tandas") == 1


# ------------------------------------------------------------------ file type words


def test_a_type_matched_by_code_gets_an_option_and_its_words_as_keywords(db):
    _type(db, "photo", "Product Photos")
    _call(db)
    (aset,) = db.query(LookupSet).filter_by(set_key=ALIAS_SET_KEY).all()
    (opt,) = db.query(LookupOption).filter_by(set_id=aset.id).all()
    assert opt.value == "Product Photos" and opt.label == "Product Photos"
    assert sorted(k.keyword for k in opt.keywords) == sorted(FILE_TYPE_WORDS["photo"])


def test_a_type_matched_by_name_and_existing_option_and_keyword_are_reused_case_aside(db):
    _type(db, "VID", "Video")
    aset = LookupSet(set_key=ALIAS_SET_KEY, name="Attachment type aliases", is_active=True)
    db.add(aset)
    db.flush()
    opt = LookupOption(set_id=aset.id, value="video", label="Video", is_active=True)
    db.add(opt)
    db.flush()
    db.add(LookupOptionKeyword(option_id=opt.id, keyword="VIDEOS"))
    db.flush()
    _call(db)
    assert db.query(LookupSet).filter_by(set_key=ALIAS_SET_KEY).count() == 1
    assert db.query(LookupOption).count() == 1
    assert _keywords(db) == ["VIDEOS"]


def test_a_label_with_no_attachment_type_is_skipped_and_no_type_is_created(db):
    _type(db, "photo", "Product Photos")
    before = db.query(AttachmentType).count()
    _call(db)
    assert db.query(AttachmentType).count() == before
    assert db.query(LookupOption).count() == 1  # only photo's


def test_with_no_types_at_all_no_option_is_created(db):
    _call(db)
    assert db.query(LookupOption).count() == 0 and db.query(LookupOptionKeyword).count() == 0


def test_second_upgrade_adds_no_keywords_or_rows(db):
    _type(db, "photo", "Product Photos")
    _type(db, "cert", "Certificate")
    _cat(db, "ZZT WC A", class_label="Water Closet")
    _call(db)
    counts = (db.query(LookupSet).count(), db.query(LookupOption).count(), db.query(LookupOptionKeyword).count())
    assert counts[2] == len(FILE_TYPE_WORDS["photo"]) + len(FILE_TYPE_WORDS["certificate"])
    _call(db)
    assert (db.query(LookupSet).count(), db.query(LookupOption).count(), db.query(LookupOptionKeyword).count()) == counts


def test_downgrade_is_a_no_op(db):
    c = _cat(db, "ZZT WC A", class_label="Water Closet")
    _type(db, "photo", "Product Photos")
    _call(db)
    syn, kws = _syn(db, c), sorted(_keywords(db))
    _call(db, "downgrade")
    assert _syn(db, c) == syn and sorted(_keywords(db)) == kws
