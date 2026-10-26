"""PROMPT-RULES-DIET red tests: migration `diet_0001_parser_prompt_diet` (lkp_0001 pattern) on Postgres."""
from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path
from unittest import mock

import pytest

from app.models.ai_prompt import AIPromptLabel, AIPromptVersion
from app.services import chatbot_lookup_edits as lle
from app.services import chatbot_prompt_diet_edits as diet
from tests._pg_fixture import blank_session

NAME = "chatbot_semantic_parser"
VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"
MARKER = "== LOOKUP LISTS =="
ANCHOR = "A long wordy diet anchor sentence that the edit shortens."
TEXT = f"Rules for {{{{current_date}}}}.\n{ANCHOR}\nTail rule.\n{MARKER}\n"


@pytest.fixture(autouse=True)
def _small_edits(monkeypatch):
    monkeypatch.setattr(diet, "EDITS", (lle.Edit("replace", ANCHOR, "Short."),))


def _migration():
    files = sorted(VERSIONS.glob("diet_0001*.py"))
    assert len(files) == 1, f"expected one diet_0001 migration, found {files}"
    spec = importlib.util.spec_from_file_location("_diet_0001_test", files[0])
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _versions(db):
    return db.query(AIPromptVersion).filter(AIPromptVersion.name == NAME).order_by(AIPromptVersion.version).all()


def _production(db, template: str, version: int = 80) -> AIPromptVersion:
    row = AIPromptVersion(id=str(uuid.uuid4()), name=NAME, version=version, type="text", template=template, variables=["current_date"])
    db.add(row)
    db.flush()
    db.add(AIPromptLabel(name=NAME, label="production", version_id=row.id))
    db.flush()
    return row


def test_revision_ids():
    m = _migration()
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    assert m.revision == "diet_0001_parser_prompt_diet" and len(m.revision) <= 32
    script = ScriptDirectory.from_config(Config(str(VERSIONS.parents[1] / "alembic.ini")))
    assert script.get_revision(m.down_revision) is not None, m.down_revision
    ancestors = {r.revision for r in script.iterate_revisions(m.revision, "base")}
    assert "lkp_0001_parser_lookup_lists" in ancestors


def test_publishes_one_unlabelled_version_with_built_template():
    m = _migration()
    with blank_session() as db:
        prod = _production(db, TEXT)
        assert m.publish_on_production(db) == 81
        rows = _versions(db)
        assert [r.version for r in rows] == [80, 81]
        new = rows[-1]
        assert new.template == diet.build(TEXT) and "Short." in new.template
        assert new.variables == ["current_date"]
        assert new.config_json == {"wording_edit": True}
        assert new.commit_message == m.MESSAGE
        labels = db.query(AIPromptLabel).filter(AIPromptLabel.name == NAME).all()
        assert [(lbl.label, lbl.version_id) for lbl in labels] == [("production", prod.id)]
        assert db.query(AIPromptLabel).filter(AIPromptLabel.version_id == new.id).count() == 0


def test_second_upgrade_publishes_nothing():
    m = _migration()
    with blank_session() as db:
        _production(db, TEXT)
        assert m.publish_on_production(db) is not None
        assert m.publish_on_production(db) is None
        assert len(_versions(db)) == 2


def test_text_that_does_not_take_the_edits_publishes_nothing():
    m = _migration()
    with blank_session() as db:
        _production(db, f"No anchor here.\n{MARKER}\n")
        assert m.publish_on_production(db) is None
        assert len(_versions(db)) == 1


def test_no_production_label_publishes_nothing():
    m = _migration()
    with blank_session() as db:
        assert m.publish_on_production(db) is None
        assert _versions(db) == []


def test_downgrade_removes_only_its_own_unlabelled_version():
    m = _migration()
    with blank_session() as db:
        prod = _production(db, TEXT)
        assert m.publish_on_production(db) == 81
        db.add(AIPromptVersion(id=str(uuid.uuid4()), name=NAME, version=82, type="text", template="other", variables=[],
                               commit_message="someone else's version"))
        labelled = AIPromptVersion(id=str(uuid.uuid4()), name=NAME, version=83, type="text", template="labelled", variables=[],
                                   commit_message=m.MESSAGE)
        db.add(labelled)
        db.flush()
        db.add(AIPromptLabel(name=NAME, label="staging", version_id=labelled.id))
        db.flush()
        with mock.patch.object(m.op, "get_bind", return_value=db.connection()):
            m.downgrade()
        db.expire_all()
        assert [r.version for r in _versions(db)] == [80, 82, 83]
        assert _versions(db)[0].id == prod.id
