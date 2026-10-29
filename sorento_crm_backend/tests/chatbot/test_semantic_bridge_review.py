"""ENTITY-EXTRACT-MATCH S3 review round (#1898): dimensions, meaning-first, label seed, spelling-only gates, floor off,
schema by prompt, cold-turn embedding model."""
from __future__ import annotations

import uuid
from unittest import mock

import pytest

import app.main  # noqa: F401  isort:skip
from app.models.ai_prompt import AIPromptLabel, AIPromptVersion
from app.services.chatbot import engine as engine_mod
from app.services.chatbot import llm_call
from app.services.chatbot.head import list_resolver, span_extract
from app.services.chatbot.head import lookup_lists as ll
from app.services.llm_provider import ChatResult
from tests._pg_fixture import blank_session
from tests.chatbot.test_semantic_bridge import (  # noqa: F401
    GEM_MODEL, KEY, R, _embedder_world, _migration, _rows, _run, fake_embedder, fresh_cache, gemini,
)


# 1. the request asks for the dimension the floors were calibrated on
def test_gemini_requests_ask_for_1536_dimensions(monkeypatch, gemini, fresh_cache):
    with blank_session() as db:
        _embedder_world(monkeypatch, db, provider="gemini", model=GEM_MODEL)
        ll.embedder(db).pieces(["zz gold"])
    bodies = gemini.bodies
    assert bodies and all(r.get("outputDimensionality") == 1536 for b in bodies for r in b["requests"]), bodies


# 2. meaning-first: text and meaning resolve to different rows, the meaning wins
def test_meaning_wins_over_a_text_that_also_resolves():
    rows = [R("brand", "b1", "ZZALPHA"), R("brand", "b2", "ZZBETA")]
    res = list_resolver.resolve([list_resolver.Span("zzalpha", "brand", meaning="zzbeta")], rows)[0]
    assert res.matched_by == "meaning" and res.candidates[0].row.key == "b2", res


# 3. eem_0003 also seeds the embedder prompt key
def test_migration_seeds_the_embedder_prompt_with_an_unset_production_label():
    m = _migration()
    with blank_session() as db:
        m.seed_embedder_prompt(db)
        label = db.query(AIPromptLabel).filter_by(name=KEY, label="production").one()
        assert label.provider is None and label.model is None
        v = db.query(AIPromptVersion).filter_by(id=label.version_id).one()
        assert v.name == KEY and v.version == 1 and v.template.strip()
        m.seed_embedder_prompt(db)
        assert db.query(AIPromptVersion).filter_by(name=KEY).count() == 1


def test_migration_leaves_an_existing_embedder_label_alone():
    m = _migration()
    with blank_session() as db:
        v = AIPromptVersion(id=str(uuid.uuid4()), name=KEY, version=1, type="text", template="x", variables=[])
        db.add(v)
        db.flush()
        db.add(AIPromptLabel(name=KEY, label="production", version_id=v.id, provider="gemini", model=GEM_MODEL))
        db.flush()
        m.seed_embedder_prompt(db)
        assert db.query(AIPromptVersion).filter_by(name=KEY).count() == 1
        assert db.query(AIPromptLabel).filter_by(name=KEY).one().provider == "gemini"


def test_migration_downgrade_removes_the_seeded_embedder_rows_only():
    m = _migration()
    with blank_session() as db:
        with mock.patch.object(m.op, "get_bind", return_value=db.connection()):
            m.upgrade()
            assert db.query(AIPromptLabel).filter_by(name=KEY).count() == 1
            m.downgrade()
        db.expire_all()
        assert db.query(AIPromptLabel).filter_by(name=KEY).count() == 0
        assert db.query(AIPromptVersion).filter_by(name=KEY).count() == 0


# 4. the n-gram path and prefetch make no meaning call on another model
class _Spy:
    def __init__(self, model):
        self.model, self.calls = model, 0
        self.needs_warm = False

    def __call__(self, texts):
        self.calls += 1
        return [[1.0, 0.0] for _ in texts]

    def pieces(self, texts):
        self.calls += 1
        import numpy as np

        return np.ones((len(texts), 2), dtype="float32")

    def matrix(self, texts):
        self.calls += 1
        import numpy as np

        return np.ones((len(texts), 2), dtype="float32")


@pytest.mark.parametrize("model,expected_calls", [("zz-other-model", 0), (ll.EMBED_MODEL, 1)])
def test_the_ngram_path_reads_meaning_only_on_the_openai_model(model, expected_calls):
    spy = _Spy(model)
    ll.shortlist("zz gold", [R("spec", "k1", "Finish ZZ gold")], spy)
    assert (spy.calls > 0) == bool(expected_calls), spy.calls


@pytest.mark.parametrize("model,expected", [("zz-other-model", False), (ll.EMBED_MODEL, True)])
def test_prefetch_embeds_pieces_only_on_the_openai_model(model, expected):
    spy = _Spy(model)
    ll.prefetch("zz gold", spy)()
    assert (spy.calls > 0) is expected


# 5. a list whose meaning floor is off never yields a meaning signal
def test_a_floor_that_is_off_gives_no_meaning_signal():
    rows = [R("customer", "c1", "ZZMELOX"), R("customer", "c2", "Blorvak Industries")]
    emb = fake_embedder("zz-embed-unknown", {"ZZMELOX": 0.99}, "zzmelo")
    res = list_resolver.resolve([list_resolver.Span("zzmelo", None)], rows, embed=emb)[0]
    assert all(c.signal != "meaning" for c in res.candidates), res


# 6. the meaning schema only when the prompt asks for meanings
def _schema_used(prompt: str):
    cfg = span_extract.SpanConfig(prompt, 1, "openai", "gpt-zz", "ZZ-key", "label")
    with mock.patch.object(llm_call, "chat", return_value=ChatResult(content='{"spans": []}', prompt_tokens=1, completion_tokens=1, total_tokens=2)) as chat:
        span_extract.extract(cfg, "zz message")
    return chat.call_args.kwargs["json_schema"]


def test_a_v1_prompt_keeps_the_old_schema_and_a_meaning_prompt_gets_the_meaning_schema():
    old = _schema_used("ZZ v1 prompt.")["properties"]["spans"]["items"]
    assert "meaning" not in old["properties"] and old["required"] == ["text", "type"]
    new = _schema_used("ZZ v1 prompt." + span_extract.MEANING_PARAGRAPH)["properties"]["spans"]["items"]
    assert "meaning" in new["properties"] and "meaning" in new["required"]


def test_the_migration_paragraph_is_the_shared_constant():
    assert _migration().MEANING_PARAGRAPH is span_extract.MEANING_PARAGRAPH


# nit: a cold (spelling-only) turn does not name an embedding model
def _prep_with(embed):
    return engine_mod._SpanPrep(
        message="zz message", rows=_rows(), spec_key_rows=[], brand_words=frozenset(), numbers=[], held={}, embed=embed,
        config=span_extract.SpanConfig("sys", 2, "openai", "gpt-zz", "ZZ-key", "label"),
    )


@pytest.mark.parametrize("cached,expected", [(False, None), (True, "zz-model")])
def test_event_names_the_embedding_model_only_when_the_embedder_is_usable(cached, expected):
    emb = fake_embedder("zz-model", {}, "zzkimlan")
    emb.needs_warm, emb.is_cached = True, lambda texts: cached
    answer = span_extract.SpanAnswer([list_resolver.Span("zzkimlan", "customer")], {}, 1)
    with mock.patch.object(span_extract, "extract", return_value=answer):
        _l, _e, event = engine_mod._span_lookup(_prep_with(emb), session_factory=None, contact_respond_id="ZZ", dry_run=True, turn_id=None)
    assert event["embedding_model"] == expected
