"""ENTITY-EXTRACT-MATCH S2 fix: `eem_0002_span_version_on_diet` publishes the span version from a production text
that ALREADY carries the diet (eem_0001 only handled a pre-diet text), and the trace detail exposes the span pass."""
from __future__ import annotations

import importlib.util
import uuid
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import app.main  # noqa: F401  isort:skip
from app.models.ai_prompt import AIPromptLabel, AIPromptVersion
from app.services.chatbot.trace_detail import compose_trace_detail
from app.services.chatbot_lookup_edits import MARKER, SPAN_MARKER
from tests._pg_fixture import blank_session

VERSIONS = Path(__file__).resolve().parents[2] / "alembic" / "versions"
PARSER = "chatbot_semantic_parser"
DIET_TEXT = f"Rules for {{{{current_date}}}}.\nAlready dieted rule.\n{MARKER}\nTail.\n"


def _migration():
    files = sorted(VERSIONS.glob("eem_0002*.py"))
    assert len(files) == 1, f"expected one eem_0002 migration, found {files}"
    spec = importlib.util.spec_from_file_location("_eem_0002_test", files[0])
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _versions(db):
    return db.query(AIPromptVersion).filter(AIPromptVersion.name == PARSER).order_by(AIPromptVersion.version).all()


def _production(db, template=DIET_TEXT, version=67):
    row = AIPromptVersion(id=str(uuid.uuid4()), name=PARSER, version=version, type="text", template=template,
                          variables=["current_date"])
    db.add(row)
    db.flush()
    db.add(AIPromptLabel(name=PARSER, label="production", version_id=row.id))
    db.flush()
    return row


def test_single_head_and_chain():
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    m = _migration()
    assert m.revision == "eem_0002_span_version_on_diet" and len(m.revision) <= 32
    script = ScriptDirectory.from_config(Config(str(VERSIONS.parents[1] / "alembic.ini")))
    assert script.get_revision(m.down_revision) is not None
    assert script.get_heads() == [m.revision], script.get_heads()


def test_dieted_production_text_publishes_one_unlabelled_span_version():
    m = _migration()
    with blank_session() as db:
        prod = _production(db)
        assert m.publish_on_production(db) == 68
        rows = _versions(db)
        assert [r.version for r in rows] == [67, 68]
        new = rows[-1]
        assert SPAN_MARKER in new.template.splitlines() and MARKER not in new.template.splitlines()
        assert "Already dieted rule." in new.template
        assert new.variables == ["current_date"] and new.config_json == {"wording_edit": True}
        labels = db.query(AIPromptLabel).filter(AIPromptLabel.name == PARSER).all()
        assert [(lbl.label, lbl.version_id) for lbl in labels] == [("production", prod.id)]


def test_rerun_publishes_nothing():
    m = _migration()
    with blank_session() as db:
        _production(db)
        assert m.publish_on_production(db) is not None
        assert m.publish_on_production(db) is None
        assert len(_versions(db)) == 2


def test_text_without_the_lists_line_publishes_nothing():
    m = _migration()
    with blank_session() as db:
        _production(db, template="Rules.\nNo lookup line here.\n")
        assert m.publish_on_production(db) is None
        assert len(_versions(db)) == 1


def test_text_already_carrying_spans_publishes_nothing():
    m = _migration()
    with blank_session() as db:
        _production(db, template=f"Rules.\n{SPAN_MARKER}\n")
        assert m.publish_on_production(db) is None
        assert len(_versions(db)) == 1


def test_downgrade_removes_only_its_own_row():
    m = _migration()
    with blank_session() as db:
        prod = _production(db)
        with mock.patch.object(m.op, "get_bind", return_value=db.connection()):
            m.upgrade()
            db.add(AIPromptVersion(id=str(uuid.uuid4()), name=PARSER, version=90, type="text", template="other",
                                   variables=[], commit_message="not ours"))
            db.flush()
            m.downgrade()
        db.expire_all()
        assert [r.version for r in _versions(db)] == [67, 90]
        assert _versions(db)[0].id == prod.id


# ------------------------------------------------------------------------------------------ trace detail
NOW = datetime(2026, 10, 27, tzinfo=timezone.utc)


def _row(trace):
    return SimpleNamespace(id="zzt-turn", created_at=NOW, trace=trace, contact_respond_id="ZZT-c", is_test=True, envelope={})


SPAN_EVENT = {
    "kind": "span_extract", "at": NOW.isoformat(),
    "spans": [{"text": "frg", "type": "spec", "status": "close", "close": 2, "residual": True}],
    "rows_rendered": 3, "near_exact_rows": 1, "fallback": False, "fallback_reason": None,
    "provider": "openai", "model": "gpt-x", "model_source": "label", "ms": 120,
}
LOOKUP_EVENT = {
    "kind": "lookup_lists", "at": NOW.isoformat(), "spans": ["frg"],
    "hits": [
        {"label": "Finish: French Gold", "piece": "frg", "spelling": 0.9, "meaning": 0.0},
        {"label": "Finish: French Gold", "piece": "frg", "spelling": 0.8, "meaning": 0.0},
        {"label": "Brand: ZZT", "piece": "zzt", "spelling": 1.0, "meaning": 0.0},
    ],
}


def test_trace_detail_exposes_the_span_pass_with_the_rows_shown():
    d = compose_trace_detail(_row([SPAN_EVENT, LOOKUP_EVENT]))
    se = d["span_extract"]
    assert se["spans"] == SPAN_EVENT["spans"]
    assert se["rows_rendered"] == 3 and se["near_exact_rows"] == 1 and se["fallback"] is False
    assert (se["provider"], se["model"], se["model_source"], se["ms"]) == ("openai", "gpt-x", "label", 120)
    assert se["matched_rows"] == ["Finish: French Gold", "Brand: ZZT"]


def test_trace_detail_span_fallback_shape_and_absent_event():
    fb = {**SPAN_EVENT, "spans": [], "fallback": True, "fallback_reason": "unreadable"}
    lookup = {"kind": "lookup_lists", "at": NOW.isoformat(), "pieces": ["x"], "fallback": True, "hits": []}
    se = compose_trace_detail(_row([fb, lookup]))["span_extract"]
    assert se["fallback"] is True and se["fallback_reason"] == "unreadable" and se["matched_rows"] == []
    assert compose_trace_detail(_row([LOOKUP_EVENT]))["span_extract"] is None
