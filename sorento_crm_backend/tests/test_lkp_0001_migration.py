"""CHAT-SLIM-INDEX S5 red tests: migration `lkp_0001` (maskp_0001 pattern) on Postgres.

Assumed: `alembic/versions/lkp_0001*.py` exposes `revision` (<= 32 chars), `down_revision`, `publish_on_production(session)`
returning the new version number or None, and `downgrade()`. The production-labelled text is the input.
"""
from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path

from app.models.ai_prompt import AIPromptLabel, AIPromptVersion
from app.services.chatbot import prompt_lookup_edits as ple
from tests._pg_fixture import blank_session
from tests.chatbot.test_prompt_lookup_edits import fixture

NAME = "chatbot_semantic_parser"
VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"


def _migration():
    files = sorted(VERSIONS.glob("lkp_0001*.py"))
    assert len(files) == 1, f"expected one lkp_0001 migration, found {files}"
    spec = importlib.util.spec_from_file_location("_lkp_0001_test", files[0])
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _versions(db):
    return db.query(AIPromptVersion).filter(AIPromptVersion.name == NAME).order_by(AIPromptVersion.version).all()


def _production(db, template: str, version: int = 63) -> AIPromptVersion:
    row = AIPromptVersion(id=str(uuid.uuid4()), name=NAME, version=version, type="text", template=template, variables=["current_date"])
    db.add(row)
    db.flush()
    db.add(AIPromptLabel(name=NAME, label="production", version_id=row.id))
    db.flush()
    return row


def test_revision_id_fits_and_chains():
    m = _migration()
    assert m.revision.startswith("lkp_0001") and len(m.revision) <= 32
    assert m.down_revision


def test_it_publishes_one_unlabelled_version_of_the_edited_production_text():
    m = _migration()
    text = fixture()
    with blank_session() as db:
        prod = _production(db, text)
        assert m.publish_on_production(db) == 64
        rows = _versions(db)
        assert [r.version for r in rows] == [63, 64]
        new = rows[-1]
        assert new.template == ple.apply(text)
        assert new.variables == ["current_date"] and new.commit_message
        labels = db.query(AIPromptLabel).filter(AIPromptLabel.name == NAME).all()
        assert [(lbl.label, lbl.version_id) for lbl in labels] == [("production", prod.id)]
        assert db.query(AIPromptLabel).filter(AIPromptLabel.version_id == new.id).count() == 0


def test_a_second_run_publishes_nothing():
    m = _migration()
    with blank_session() as db:
        _production(db, fixture())
        assert m.publish_on_production(db) is not None
        assert m.publish_on_production(db) is None
        assert len(_versions(db)) == 2


def test_a_production_text_missing_an_anchor_publishes_nothing_and_does_not_raise():
    m = _migration()
    with blank_session() as db:
        _production(db, fixture(skip=0))
        assert m.publish_on_production(db) is None
        assert len(_versions(db)) == 1


def test_a_doubled_anchor_publishes_nothing():
    m = _migration()
    with blank_session() as db:
        _production(db, fixture(double=0))
        assert m.publish_on_production(db) is None
        assert len(_versions(db)) == 1


def test_no_production_label_publishes_nothing():
    m = _migration()
    with blank_session() as db:
        assert m.publish_on_production(db) is None
        assert _versions(db) == []


def test_the_downgrade_drops_only_its_own_unlabelled_marked_version():
    m = _migration()
    with blank_session() as db:
        prod = _production(db, fixture())
        assert m.publish_on_production(db) == 64
        other = AIPromptVersion(id=str(uuid.uuid4()), name=NAME, version=65, type="text", template="plain unlabelled", variables=[])
        db.add(other)
        db.flush()
        from unittest import mock

        with mock.patch.object(m.op, "get_bind", return_value=db.connection()):
            m.downgrade()
        db.expire_all()
        assert [r.version for r in _versions(db)] == [63, 65]
        assert _versions(db)[0].id == prod.id
