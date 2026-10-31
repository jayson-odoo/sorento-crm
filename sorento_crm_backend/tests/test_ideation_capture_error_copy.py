"""AGENTIC-IDEATE failed-save line round (31 Oct): no sorry, and a migration publishes it.

UAC: documentation/plans/chatbot/agentic-ideate-31oct-acceptance-criteria.md, "Failed-save
line round", AC-NS-1 .. AC-NS-6.

Contract the migration module (revision ``idea_error_copy_0001``) must expose:

- ``STOCK_TEXTS``: dict, registry key -> tuple of old stock texts.
- ``publish(bind)``: for each of the three ``chatbot_reply_ideation_capture_error*`` keys,
  publishes the new text as the next version only where production equals a stock text
  (strip-normalised). ``upgrade()`` calls ``seed_prompt_registry`` then ``publish``.
"""
from __future__ import annotations

import ast
import importlib.util
import logging
import pathlib

import pytest

# MUST be the first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402,F401

from app.models.ai_prompt import AIPromptLabel, AIPromptVersion
from app.services import ai_prompt_registry
from app.services.ideation_capture_replies import render_reply
from tests._pg_fixture import blank_session

# Reuse the capture-turn harness (real Postgres, patched outside seams).
from tests.test_ideation_capture_turn import (  # noqa: F401  (env is a pytest fixture)
    MSG,
    _TRANSIENT,
    _create_scenario,
    _ss_error,
    env,
)

VERSIONS_DIR = pathlib.Path(__file__).resolve().parents[1] / "alembic" / "versions"
REVISION = "idea_error_copy_0001"

OLD = {
    "en": "Sorry, I couldn't save that idea just now. Please try again in a moment.",
    "ms": "Maaf, saya tidak dapat menyimpan idea itu sekarang. Sila cuba lagi sebentar nanti.",
    "zh": "抱歉，我暂时无法保存这个创意，请稍后再试。",
}
NEW = {
    "en": "I couldn't save that idea just now. Please send it again.",
    "ms": "Saya tidak dapat menyimpan idea itu sekarang. Sila hantar sekali lagi.",
    "zh": "我刚才无法保存这个创意，请再发送一次。",
}
KEYS = {
    "en": "chatbot_reply_ideation_capture_error",
    "ms": "chatbot_reply_ideation_capture_error.ms",
    "zh": "chatbot_reply_ideation_capture_error.zh",
}
_CONFIG_ERROR_EN = (
    "Idea capture isn't set up correctly here, so I couldn't save that. "
    "Please let your Sorento contact know."
)


# --------------------------------------------------------------------------- #
# AC-NS-1 - shipped text                                                      #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("lang", ["en", "ms", "zh"])
def test_ns1_error_reply_is_the_new_line_and_has_no_sorry(lang):
    text = render_reply("error", {}, user_message="x", language=lang, db=None)
    assert text == NEW[lang]
    lowered = text.lower()
    for word in ("sorry", "maaf", "抱歉"):
        assert word not in lowered


# --------------------------------------------------------------------------- #
# AC-NS-2 - through the real capture turn                                     #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("status_code", _TRANSIENT)
def test_ns2_transient_similar_lookup_failure_answers_the_new_line(env, status_code):
    env.ready()
    env.idea_message()
    env.similar_result = _ss_error(status_code)
    out = env.turn(MSG)
    assert out["status"] == "error"
    assert out["reply_text"] == NEW["en"]


@pytest.mark.parametrize("where", ["fresh", "held_new"])
@pytest.mark.parametrize("status_code", _TRANSIENT)
def test_ns2_transient_create_failure_answers_the_new_line(env, where, status_code):
    out, _sv = _create_scenario(env, where, status_code)
    assert out["status"] == "error"
    assert out["reply_text"] == NEW["en"]


@pytest.mark.parametrize("step", ["similar_own", "create"])
def test_ns2_permanent_4xx_still_config_error_with_unchanged_text(env, step):
    env.ready()
    env.idea_message()
    if step == "similar_own":
        env.similar_result = _ss_error(403)
    else:
        env.create_result = _ss_error(403)
    out = env.turn(MSG)
    assert out["status"] == "config_error"
    assert out["reply_text"] == _CONFIG_ERROR_EN


# --------------------------------------------------------------------------- #
# AC-NS-6 - migration identity                                                #
# --------------------------------------------------------------------------- #
def _assign(src: str, name: str):
    for node in ast.parse(src).body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == name for t in node.targets):
            return ast.literal_eval(node.value)
    return None


def _migration_path() -> pathlib.Path:
    found = [
        p for p in VERSIONS_DIR.glob("*.py")
        if _assign(p.read_text(encoding="utf-8"), "revision") == REVISION
    ]
    assert len(found) == 1, (
        f"MIGRATION NOT WRITTEN YET: expected exactly one migration with revision {REVISION}, "
        f"found {len(found)}"
    )
    return found[0]


def _load_migration():
    spec = importlib.util.spec_from_file_location("_idea_error_copy_0001_under_test", _migration_path())
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_ns6_revision_id_fits_and_parent_is_a_real_revision():
    path = _migration_path()
    src = path.read_text(encoding="utf-8")
    revision = _assign(src, "revision")
    assert isinstance(revision, str) and 0 < len(revision) <= 32
    assert path.name == f"{REVISION}.py"
    revisions = set()
    for p in VERSIONS_DIR.glob("*.py"):
        rev = _assign(p.read_text(encoding="utf-8"), "revision")
        if isinstance(rev, str):
            revisions.add(rev)
    down_revision = _assign(src, "down_revision")
    assert isinstance(down_revision, str) and down_revision in revisions
    assert down_revision != revision

    upgrade = next(n for n in ast.parse(src).body if isinstance(n, ast.FunctionDef) and n.name == "upgrade")
    called = {
        n.func.id for n in ast.walk(upgrade)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
    }
    assert "seed_prompt_registry" in called
    assert "publish" in called


def test_ns6_stock_texts_hold_the_old_lines_for_the_three_keys():
    stock = _load_migration().STOCK_TEXTS
    assert set(stock) == set(KEYS.values())
    for lang, key in KEYS.items():
        assert OLD[lang] in {t.strip() for t in stock[key]}
        assert NEW[lang] not in {t.strip() for t in stock[key]}


# --------------------------------------------------------------------------- #
# AC-NS-3 / 4 / 5 - publish                                                   #
# --------------------------------------------------------------------------- #
@pytest.fixture
def db():
    with blank_session() as session:
        try:
            ai_prompt_registry.bust_cache()
            yield session
        finally:
            ai_prompt_registry.bust_cache()


def _seed(db, name: str, template: str | None):
    v1 = AIPromptVersion(name=name, version=1, type="text", template=template, variables=[])
    db.add(v1)
    db.flush()
    if template is not None:
        db.add(AIPromptLabel(name=name, label="production", version_id=v1.id))
        db.flush()
    return v1


def _state(db, name: str):
    db.expire_all()
    versions = (
        db.query(AIPromptVersion).filter(AIPromptVersion.name == name).order_by(AIPromptVersion.version).all()
    )
    label = (
        db.query(AIPromptLabel).filter(AIPromptLabel.name == name, AIPromptLabel.label == "production").first()
    )
    current = None
    if label is not None:
        current = db.query(AIPromptVersion).filter(AIPromptVersion.id == label.version_id).one()
    return versions, label, current


def test_ns3_stock_production_is_upgraded_to_the_next_version_for_each_key(db):
    mig = _load_migration()
    for lang, key in KEYS.items():
        _seed(db, key, OLD[lang])
    mig.publish(db.connection())
    ai_prompt_registry.bust_cache()
    for lang, key in KEYS.items():
        versions, _label, current = _state(db, key)
        assert [v.version for v in versions] == [1, 2], key
        assert versions[0].template == OLD[lang], "version 1 stays immutable"
        assert current.version == 2 and current.template == NEW[lang], key
        got = ai_prompt_registry.get_prompt(db, key)
        assert got.text == NEW[lang], key
        assert got.version == 2, key


def test_ns3_stock_text_with_surrounding_whitespace_still_publishes(db):
    mig = _load_migration()
    for lang, key in KEYS.items():
        _seed(db, key, f"\n  {OLD[lang]}  \n\n")
    mig.publish(db.connection())
    for lang, key in KEYS.items():
        versions, _label, current = _state(db, key)
        assert [v.version for v in versions] == [1, 2], key
        assert current.template == NEW[lang], key


def test_ns4_owner_edited_ms_is_left_alone_while_en_and_zh_publish(db, caplog):
    mig = _load_migration()
    edited = "Owner edited Malay failed-save line."
    v1_ms = _seed(db, KEYS["ms"], edited)
    _seed(db, KEYS["en"], OLD["en"])
    _seed(db, KEYS["zh"], OLD["zh"])
    with caplog.at_level(logging.WARNING):
        mig.publish(db.connection())

    versions, label, current = _state(db, KEYS["ms"])
    assert len(versions) == 1
    assert label.version_id == v1_ms.id
    assert current.template == edited
    assert any(r.levelno >= logging.WARNING for r in caplog.records), "expected a warning log"
    assert _state(db, KEYS["en"])[2].template == NEW["en"]
    assert _state(db, KEYS["zh"])[2].template == NEW["zh"]
    assert len(_state(db, KEYS["en"])[0]) == 2 and len(_state(db, KEYS["zh"])[0]) == 2


def test_ns5_rerun_is_a_noop(db, caplog):
    mig = _load_migration()
    for lang, key in KEYS.items():
        _seed(db, key, OLD[lang])
    mig.publish(db.connection())
    with caplog.at_level(logging.WARNING):
        mig.publish(db.connection())
    assert [r for r in caplog.records if r.levelno >= logging.WARNING] == []
    for key in KEYS.values():
        versions, _label, current = _state(db, key)
        assert [v.version for v in versions] == [1, 2], key
        assert current.version == 2, key


def test_ns5_key_without_a_production_label_is_skipped_without_error(db):
    mig = _load_migration()
    mig.publish(db.connection())  # nothing seeded at all
    for key in KEYS.values():
        versions, label, _current = _state(db, key)
        assert versions == [] and label is None
    _seed(db, KEYS["en"], None)  # a version row with no label
    _seed(db, KEYS["ms"], OLD["ms"])
    mig.publish(db.connection())
    versions, label, _current = _state(db, KEYS["en"])
    assert len(versions) == 1 and label is None
    assert _state(db, KEYS["ms"])[2].template == NEW["ms"]
