"""Translation memory (AC-G1, R15/R16, purchasing consolidation batch, lane C).

Postgres only, on a blank schema (`tests._pg_fixture.blank_session`): CI's database is
empty, so nothing here borrows an existing row. The AI provider is ALWAYS stubbed
(`_stub_provider`) - `.env` carries a real `OPENAI_API_KEY` for the app itself, and a
test that forgot to stub `get_provider` would make a genuine network call the moment
its scenario reached a miss, which is exactly the failure mode `test_supplier_document_
service.py`'s own `_no_ai_translation` fixture guards against for that file.
"""
from __future__ import annotations

import json
import uuid
from types import SimpleNamespace

import pytest

from app.config import settings
from app.models.ai_assistant import AIAssistantConfig
from app.models.translation_memory import TranslationMemory
from app.services import translation_service as svc
from tests._pg_fixture import blank_session

MARKER = "ZZTR"


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


def _configure_ai(db, api_key: str | None = "fake-key") -> AIAssistantConfig:
    cfg = AIAssistantConfig(
        id=str(uuid.uuid4()),
        provider="openai",
        model="gpt-4o-mini",
        temperature=0,
        system_prompt="",
        api_key_ciphertext=api_key,
        enabled_tools=[],
        rag_enabled=True,
        is_enabled=True,
    )
    db.add(cfg)
    db.flush()
    return cfg


class _FakeProvider:
    """Returns one `{"source": ..., "target": ...}` pair per input line, in order,
    from whatever the test hands it - `chat()` never leaves this process."""

    def __init__(self, answers: dict[str, str]):
        self.answers = answers
        self.calls: list[list[dict]] = []

    def chat(self, messages, **_kwargs):
        self.calls.append(messages)
        user_content = messages[-1]["content"]
        lines = [
            ln.split(". ", 1)[1] if ". " in ln else ln
            for ln in user_content.rsplit("\n\n", 1)[-1].splitlines()
            if ln.strip()
        ]
        translations = [
            {"source": ln, "target": self.answers.get(ln, f"[{ln}]")} for ln in lines
        ]
        return SimpleNamespace(content=json.dumps({"translations": translations}))


def _stub_provider(monkeypatch, answers: dict[str, str]) -> _FakeProvider:
    fake = _FakeProvider(answers)
    monkeypatch.setattr(svc, "get_provider", lambda *a, **kw: fake)
    return fake


def test_manual_hit_returns_the_stored_english_without_touching_the_ai(db, monkeypatch):
    db.add(
        TranslationMemory(
            id=str(uuid.uuid4()),
            source_text="座厕",
            source_lang="zh",
            target_lang="en",
            target_text="Toilet bowl",
            source="manual",
        )
    )
    db.flush()
    _configure_ai(db)
    fake = _stub_provider(monkeypatch, {})

    out = svc.translate(db, ["座厕"])

    assert out["座厕"] == svc.TranslationHit(text="Toilet bowl", source="manual")
    assert fake.calls == []  # the memory answered; the model was never asked


def test_ai_hit_returns_the_stored_english_and_never_calls_the_model_again(db, monkeypatch):
    db.add(
        TranslationMemory(
            id=str(uuid.uuid4()),
            source_text="空瓷",
            source_lang="zh",
            target_lang="en",
            target_text="Blank ceramic",
            source="ai",
        )
    )
    db.flush()
    _configure_ai(db)
    fake = _stub_provider(monkeypatch, {})

    out = svc.translate(db, ["空瓷"])

    assert out["空瓷"] == svc.TranslationHit(text="Blank ceramic", source="ai")
    assert fake.calls == []


def test_a_miss_with_ai_configured_writes_an_ai_row_and_returns_it(db, monkeypatch):
    _configure_ai(db)
    fake = _stub_provider(monkeypatch, {"座厕 S-250出水 对冲": "Toilet bowl S-250, back outlet"})

    out = svc.translate(db, ["座厕 S-250出水 对冲"])
    db.commit()

    assert out["座厕 S-250出水 对冲"] == svc.TranslationHit(
        text="Toilet bowl S-250, back outlet", source="ai"
    )
    assert len(fake.calls) == 1

    row = (
        db.query(TranslationMemory)
        .filter(TranslationMemory.source_text == "座厕 S-250出水 对冲")
        .one()
    )
    assert row.source == "ai"
    assert row.target_text == "Toilet bowl S-250, back outlet"

    # The same phrase asked again hits the memory - the model is never asked twice.
    out2 = svc.translate(db, ["座厕 S-250出水 对冲"])
    assert out2["座厕 S-250出水 对冲"].source == "ai"
    assert len(fake.calls) == 1


def test_no_key_configured_flags_a_miss_untranslated_never_raises(db, monkeypatch):
    _configure_ai(db, api_key=None)
    monkeypatch.setattr(settings, "openai_api_key", None, raising=False)
    fake = _stub_provider(monkeypatch, {})

    out = svc.translate(db, ["纸箱：2个"])

    assert out["纸箱：2个"] == svc.TranslationHit(text=None, source=None)
    assert fake.calls == []


def test_english_only_text_is_never_sent_to_the_model(db, monkeypatch):
    """A supplier's own English remark ("loaded first") is not Chinese and has
    nothing to translate - asking anyway would be a network round trip on every
    apply, memory or not (protects every packing-list test whose fixtures use a
    plain-English remark column)."""
    _configure_ai(db)
    fake = _stub_provider(monkeypatch, {})

    out = svc.translate(db, ["loaded first"])

    assert out["loaded first"] == svc.TranslationHit(text=None, source=None)
    assert fake.calls == []


def test_manual_beats_an_existing_ai_row(db):
    row = TranslationMemory(
        id=str(uuid.uuid4()),
        source_text="空瓷",
        source_lang="zh",
        target_lang="en",
        target_text="Blank ceramic",
        source="ai",
    )
    db.add(row)
    db.flush()

    svc.remember(db, [{"source_text": "空瓷", "target_text": "Blank porcelain"}])
    db.commit()

    refreshed = db.query(TranslationMemory).filter(TranslationMemory.id == row.id).one()
    assert refreshed.target_text == "Blank porcelain"
    assert refreshed.source == "manual"


def test_ai_never_overwrites_a_manual_row(db, monkeypatch):
    db.add(
        TranslationMemory(
            id=str(uuid.uuid4()),
            source_text="空瓷",
            source_lang="zh",
            target_lang="en",
            target_text="Blank porcelain (corrected)",
            source="manual",
        )
    )
    db.flush()
    _configure_ai(db)
    fake = _stub_provider(monkeypatch, {"空瓷": "Something the model would have said instead"})

    out = svc.translate(db, ["空瓷"])

    assert out["空瓷"] == svc.TranslationHit(text="Blank porcelain (corrected)", source="manual")
    assert fake.calls == []  # already in memory as manual - never asked


def test_compose_bilingual_prints_english_and_chinese_only_when_they_differ():
    hit = svc.TranslationHit(text="Toilet bowl", source="manual")
    assert svc.compose_bilingual(hit, "座厕") == "Toilet bowl (座厕)"
    # Same text both ways (an English remark the AI would echo back unchanged) -
    # printed once, not doubled.
    same = svc.TranslationHit(text="loaded first", source="ai")
    assert svc.compose_bilingual(same, "loaded first") == "loaded first"
    # Untranslated - the source alone, never a blank line.
    assert svc.compose_bilingual(None, "座厕") == "座厕"
    assert svc.compose_bilingual(svc.TranslationHit(text=None, source=None), "座厕") == "座厕"
    # Nothing was said at all.
    assert svc.compose_bilingual(hit, None) is None
    assert svc.compose_bilingual(hit, "") is None
