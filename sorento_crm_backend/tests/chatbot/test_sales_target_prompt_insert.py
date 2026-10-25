"""Phase 2 RED tests - the anchored sales target parser insert and its migration
(lane SALES-TARGET-CHAT, slice 1; UAC T5-2, T5-3; PLAN "Parser candidate").

Written BEFORE `app.services.chatbot.prompt_inserts` and
`alembic/versions/stc_0001_parser_sales_target.py` exist. Imports happen inside each test so
collection succeeds and every test fails on its own (ImportError / missing file).
Postgres only (`blank_session`); every row seeded here.
"""
from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path

import pytest

from app.models.ai_prompt import AIPromptLabel, AIPromptVersion
from tests._pg_fixture import blank_session

PROMPT_NAME = "chatbot_semantic_parser"
VERSIONS = Path(__file__).resolve().parents[2] / "alembic" / "versions"
ANCHOR = '== SALES REPORT: order_status "sales_report", domain_hint "order" =='
SECTION_HEAD = '== SALES TARGET: order_status "sales_target", domain_hint "order" =='
BASE = f"HEAD LINE\nsome rules\n{ANCHOR}\nreport rules\nTAIL\n"


def _inserts():
    from app.services.chatbot import prompt_inserts

    return prompt_inserts


# ------------------------------------------------------------------ T5-2


def test_constants_are_the_anchor_and_a_section_starting_with_the_heading() -> None:
    mod = _inserts()
    assert mod.SALES_TARGET_ANCHOR == ANCHOR
    assert mod.SALES_TARGET_SECTION.startswith(SECTION_HEAD)


def test_insert_sales_target_anchor() -> None:
    mod = _inserts()
    out = mod.insert_sales_target(BASE)
    assert out is not None
    section = mod.SALES_TARGET_SECTION
    assert out == BASE.replace(ANCHOR, section + ANCHOR, 1) or out == BASE.replace(ANCHOR, section + "\n" + ANCHOR, 1), (
        "the section must sit immediately before the anchor line, rest unchanged"
    )
    idx = out.index(section)
    assert out[:idx] == "HEAD LINE\nsome rules\n"
    assert out[out.index(ANCHOR):] == f"{ANCHOR}\nreport rules\nTAIL\n"
    assert out.endswith(f"{ANCHOR}\nreport rules\nTAIL\n")
    assert out.count(ANCHOR) == 1 and out.count(SECTION_HEAD) == 1


def test_insert_sales_target_ends_the_section_on_its_own_line() -> None:
    mod = _inserts()
    out = mod.insert_sales_target(BASE)
    before_anchor = out[: out.index(ANCHOR)]
    assert before_anchor.endswith("\n"), repr(before_anchor[-20:])


def test_insert_returns_none_when_anchor_missing() -> None:
    assert _inserts().insert_sales_target("no anchor here\n") is None


def test_insert_returns_none_when_anchor_occurs_twice() -> None:
    assert _inserts().insert_sales_target(BASE + ANCHOR + "\n") is None


def test_insert_returns_none_when_section_already_present() -> None:
    mod = _inserts()
    once = mod.insert_sales_target(BASE)
    assert once is not None
    assert mod.insert_sales_target(once) is None


# ------------------------------------------------------------------ T5-3


def _load_migration():
    path = VERSIONS / "stc_0001_parser_sales_target.py"
    assert path.exists(), "stc_0001_parser_sales_target.py does not exist"
    spec = importlib.util.spec_from_file_location("mig_stc_0001_parser_sales_target", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _md5(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def _versions(session):
    session.expire_all()
    return (
        session.query(AIPromptVersion)
        .filter(AIPromptVersion.name == PROMPT_NAME)
        .order_by(AIPromptVersion.version)
        .all()
    )


def _labels(session):
    session.expire_all()
    return sorted((l.name, l.label, l.version_id) for l in session.query(AIPromptLabel).all())


def _seed_base(session, template: str, version: int = 7) -> AIPromptVersion:
    from app.services.ai_prompt_registry import PROMPT_KEYS

    row = AIPromptVersion(
        name=PROMPT_NAME, version=version, type="text", template=template,
        variables=list(PROMPT_KEYS[PROMPT_NAME].variables),
    )
    session.add(row)
    session.commit()
    return row


def test_migration_module_shape() -> None:
    module = _load_migration()
    assert module.revision == "stc_0001_parser_sales_target"
    assert len(module.revision) <= 32
    assert isinstance(module.BASE_MD5, str) and module.BASE_MD5
    assert callable(module.publish)


def test_stc_migration_publishes_unlabelled(monkeypatch) -> None:
    module = _load_migration()
    with blank_session() as session:
        base = _seed_base(session, BASE)
        session.add(AIPromptLabel(name=PROMPT_NAME, label="production", version_id=base.id))
        session.commit()
        monkeypatch.setattr(module, "BASE_MD5", _md5(BASE))
        labels_before = _labels(session)

        module.publish(session)

        rows = _versions(session)
        assert [r.version for r in rows] == [7, 8], [r.version for r in rows]
        new = rows[-1]
        assert new.template == _inserts().insert_sales_target(BASE)
        assert new.id not in {vid for _n, _l, vid in _labels(session)}
        assert _labels(session) == labels_before

        module.publish(session)
        assert [r.version for r in _versions(session)] == [7, 8], "second run must insert nothing"


def test_the_new_version_is_max_plus_one_across_all_versions(monkeypatch) -> None:
    module = _load_migration()
    with blank_session() as session:
        _seed_base(session, "older text", version=3)
        _seed_base(session, BASE, version=5)
        _seed_base(session, "newer text", version=9)
        monkeypatch.setattr(module, "BASE_MD5", _md5(BASE))
        module.publish(session)
        assert [r.version for r in _versions(session)] == [3, 5, 9, 10]


def test_no_base_row_with_the_pinned_md5_inserts_nothing(monkeypatch) -> None:
    module = _load_migration()
    with blank_session() as session:
        base = _seed_base(session, BASE)
        session.add(AIPromptLabel(name=PROMPT_NAME, label="production", version_id=base.id))
        session.commit()
        monkeypatch.setattr(module, "BASE_MD5", _md5("some other text"))
        labels_before = _labels(session)
        module.publish(session)
        assert [r.version for r in _versions(session)] == [7]
        assert _labels(session) == labels_before


def test_base_without_the_anchor_inserts_nothing(monkeypatch) -> None:
    module = _load_migration()
    no_anchor = "HEAD LINE\nno report section here\n"
    with blank_session() as session:
        base = _seed_base(session, no_anchor)
        session.add(AIPromptLabel(name=PROMPT_NAME, label="production", version_id=base.id))
        session.commit()
        monkeypatch.setattr(module, "BASE_MD5", _md5(no_anchor))
        labels_before = _labels(session)
        module.publish(session)
        assert [r.version for r in _versions(session)] == [7]
        assert _labels(session) == labels_before
