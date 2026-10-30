"""ENTITY-EXTRACT-MATCH S3 red tests: the semantic bridge (Gemini lookup embedder + span "meaning").

UAC AC-S3-1..5 (AC-S3-6 is the vitest TurnDetailDrawer.spanmeaning.test.tsx). Fakes only, no network; names invented
(ZZ prefix). Assumed beyond the contract (the coder reconciles these with the captain):
- the embedder `lookup_lists.embedder(db)` returns exposes its model as `.model` (a str); a plain callable without
  `.model` keeps today's floors;
- the Gemini embedder reaches Google through `GeminiProvider._request` (the provider's single HTTP seam) with a path
  ending `:batchEmbedContents` and `json_body["requests"]`, a list of one request per text, answered by
  `{"embeddings": [{"values": [...]}, ...]}`, in order;
- `list_resolver.Span` gains `meaning: str | None = None`;
- the trace span entry (`span_extract` event, `spans[i]`) gains `meaning` and `matched_by` ("meaning" | "text");
- the migration module `eem_0003_span_meaning` exposes `publish_meaning_version(session) -> int | None`.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

import app.main  # noqa: F401  isort:skip
from app.models.ai_prompt import AIPromptLabel, AIPromptVersion
from app.services import ai_prompt_registry, llm_provider
from app.services.ai_assistant_service import AIAssistantConfigService
from app.services.chatbot import engine as engine_mod
from app.services.chatbot import llm_call
from app.services.chatbot.head import list_resolver, span_extract
from app.services.chatbot.head import lookup_lists as ll
from app.services.chatbot.head.lookup_lists import LookupRow
from app.services.llm_provider import ChatResult, GeminiProvider
from tests._pg_fixture import blank_session

KEY = "chatbot_lookup_embedder"
GEM_MODEL = "gemini-embedding-001"
OAI_MODEL = "text-embedding-3-small"


def R(list_name, key, label, *texts):
    return LookupRow(list_name, key, label, tuple(texts) if texts else (label,))


# ------------------------------------------------------------------------------------------------ fakes
def _vec(text: str, dims: int) -> list[float]:
    digest = hashlib.sha1(text.encode()).digest()
    return [1.0 + digest[i % len(digest)] / 255.0 for i in range(dims)]


class GeminiFake:
    """Stub of the one embeddings transport (httpx.Client.send, used by embedding_client.embed_texts).

    Records every batchEmbedContents call (the key, the path, the body and the number of texts) and counts
    OpenAI embeddings calls separately. Vectors are 1536 wide, the width the transport now enforces."""

    def __init__(self):
        self.batches: list[int] = []
        self.keys: list[str] = []
        self.paths: list[str] = []
        self.bodies: list[dict] = []
        self.openai_calls = 0

    def send(self, request):
        import json

        import httpx

        body = json.loads(request.content)
        url = str(request.url)
        if url.endswith(":batchEmbedContents"):
            self.paths.append(url.split("/models/", 1)[1] and "/models/" + url.split("/models/", 1)[1])
            self.keys.append(request.headers.get("x-goog-api-key", ""))
            self.bodies.append(body)
            reqs = body.get("requests") or []
            self.batches.append(len(reqs))
            texts = ["".join(p.get("text", "") for p in r["content"]["parts"]) for r in reqs]
            data = {"embeddings": [{"values": _vec(t, 1536)} for t in texts]}
        else:
            self.openai_calls += 1
            data = {"data": [{"index": i, "embedding": _vec(t, 1536)} for i, t in enumerate(body["input"])]}
        return httpx.Response(200, json=data, request=request)


@pytest.fixture()
def gemini(monkeypatch):
    import httpx

    fake = GeminiFake()
    monkeypatch.setattr(httpx.Client, "send", lambda self, request, **kw: fake.send(request))
    return fake


@pytest.fixture()
def fresh_cache(monkeypatch):
    monkeypatch.setattr(ll, "_cache", {})
    monkeypatch.setattr(ll, "_matrices", {})
    monkeypatch.setattr(ll, "_pieces", {})


def _embedder_world(monkeypatch, db, *, provider=None, model=None, gemini_key="ZZ-gemini-key", openai_key="ZZ-openai-key"):
    """The label row (when `provider` is given), a config stub and the key resolver."""
    monkeypatch.setattr(ll, "EMBED", ll.USE_PROVIDER)
    if provider is not None or model is not None:
        version = AIPromptVersion(id=str(uuid.uuid4()), name=KEY, version=1, type="text", template="x", variables=[])
        db.add(version)
        db.flush()
        db.add(AIPromptLabel(name=KEY, label="production", version_id=version.id, provider=provider, model=model))
        db.flush()
    monkeypatch.setattr(AIAssistantConfigService, "get", lambda self: SimpleNamespace(provider="openai", model="gpt-zz"))
    monkeypatch.setattr(
        llm_provider, "resolve_api_key", lambda cfg, name: {"gemini": gemini_key, "openai": openai_key}.get(name, "")
    )


# ------------------------------------------------------------------------------------------------ AC-S3-1
def test_ac_s3_1_the_embedder_key_is_a_registered_prompt_key():
    assert KEY in ai_prompt_registry.PROMPT_KEYS


def test_ac_s3_1_gemini_label_with_a_key_gives_a_gemini_embedder(monkeypatch, gemini, fresh_cache):
    with blank_session() as db:
        _embedder_world(monkeypatch, db, provider="gemini", model=GEM_MODEL)
        emb = ll.embedder(db)
        assert emb is not None
        assert getattr(emb, "model", None) == GEM_MODEL
        got = emb.pieces(["zz gold"])
        assert got.shape == (1, 1536)
        assert gemini.paths and all(p.endswith(":batchEmbedContents") for p in gemini.paths), gemini.paths
        assert set(gemini.keys) == {"ZZ-gemini-key"}


@pytest.mark.parametrize("provider,model", [(None, None), ("gemini", None), ("openai", None)])
def test_ac_s3_1_no_label_or_no_model_keeps_the_openai_embedder(monkeypatch, gemini, fresh_cache, provider, model):
    with blank_session() as db:
        _embedder_world(monkeypatch, db, provider=provider, model=model)
        emb = ll.embedder(db)
        assert emb is not None
        assert getattr(emb, "model", None) == OAI_MODEL
        assert gemini.batches == []


def test_ac_s3_1_gemini_label_without_a_gemini_key_is_spelling_only(monkeypatch, gemini, fresh_cache):
    with blank_session() as db:
        _embedder_world(monkeypatch, db, provider="gemini", model=GEM_MODEL, gemini_key="")
        assert ll.embedder(db) is None  # no exception, and no fallback to the OpenAI key either
        assert gemini.batches == []


# ------------------------------------------------------------------------------------------------ AC-S3-2
def test_ac_s3_2_the_same_text_from_two_models_is_two_cache_entries(monkeypatch, gemini, fresh_cache):
    text = "zz shared text"
    openai_embed = ll.provider_embedder("ZZ-openai-key")
    openai_embed([text])
    assert len(ll._cache) == 1
    with blank_session() as db:
        _embedder_world(monkeypatch, db, provider="gemini", model=GEM_MODEL)
        gem = ll.embedder(db)
        assert gem is not None
        assert gem.is_cached([text]) is False  # an OpenAI vector is not a Gemini vector
        gem.matrix([text])
        assert gem.is_cached([text]) is True
        assert openai_embed.is_cached([text]) is True
    assert len(ll._cache) == 2
    # Both models now answer 1536 wide (the old 3 vs 4 width difference is gone); two entries still prove the key.
    assert sorted(len(v) for v in ll._cache.values()) == [1536, 1536]
    assert gemini.openai_calls == 1


def test_ac_s3_2_gemini_list_texts_are_embedded_in_batches(monkeypatch, gemini, fresh_cache):
    texts = [f"zz list text {i}" for i in range(250)]
    with blank_session() as db:
        _embedder_world(monkeypatch, db, provider="gemini", model=GEM_MODEL)
        gem = ll.embedder(db)
        assert gem is not None
        gem.fill(texts)
        assert gem.is_cached(texts) is True
    assert sum(gemini.batches) == 250
    assert gemini.batches and all(n > 1 for n in gemini.batches), gemini.batches


# ------------------------------------------------------------------------------------------------ AC-S3-3
def fake_embedder(model: str | None, cosines: dict[str, float], span_text: str):
    """span_text -> (1,0,0); a text in `cosines` -> (c, sqrt(1-c^2), 0); anything else -> (0,0,1)."""

    def embed(texts):
        out = []
        for t in texts:
            if t == span_text:
                out.append([1.0, 0.0, 0.0])
            elif t in cosines:
                c = cosines[t]
                out.append([c, (1 - c * c) ** 0.5, 0.0])
            else:
                out.append([0.0, 0.0, 1.0])
        return out

    if model is not None:
        embed.model = model  # type: ignore[attr-defined]
    return embed


def _meaning_resolve(list_name, row_text, other_text, cosine, model):
    span = "zzmelo"
    rows = [R(list_name, "r1", row_text), R(list_name, "r2", other_text)]
    emb = fake_embedder(model, {row_text: cosine}, span)
    return list_resolver.resolve([list_resolver.Span(span, None)], rows, embed=emb)[0]


GEM_FLOORS = {
    "category": 0.70, "spec": 0.75, "file_type": 0.65, "brand": 0.60, "promotion_kind": 0.75,
    "location": 0.65, "salesperson": 0.70, "customer": 0.75, "sales_channel": 0.65, "spec_key": 0.75,
}


def test_ac_s3_3_gemini_customer_floor_is_075():
    below = _meaning_resolve("customer", "Qwenta Haulage", "Blorvak Industries", 0.68, GEM_MODEL)
    above = _meaning_resolve("customer", "Qwenta Haulage", "Blorvak Industries", 0.80, GEM_MODEL)
    assert below.status == "unresolved", below
    assert above.status == "resolved" and above.candidates[0].row.key == "r1"
    assert above.candidates[0].signal == "meaning"


@pytest.mark.parametrize("list_name,floor", sorted(GEM_FLOORS.items()))
def test_ac_s3_3_gemini_floor_table_per_list(list_name, floor):
    below = _meaning_resolve(list_name, "Qwenta Haulage", "Blorvak Industries", round(floor - 0.01, 2), GEM_MODEL)
    above = _meaning_resolve(list_name, "Qwenta Haulage", "Blorvak Industries", round(floor + 0.03, 2), GEM_MODEL)
    assert below.status == "unresolved", (list_name, below)
    assert above.status == "resolved" and above.candidates[0].row.key == "r1", (list_name, above)


def test_ac_s3_3_openai_floors_are_unchanged():
    # customer meaning floor today is 0.6: 0.68 resolves, 0.55 does not
    assert _meaning_resolve("customer", "Qwenta Haulage", "Blorvak Industries", 0.68, OAI_MODEL).status == "resolved"
    assert _meaning_resolve("customer", "Qwenta Haulage", "Blorvak Industries", 0.55, OAI_MODEL).status == "unresolved"


def test_ac_s3_3_an_unknown_model_gives_no_meaning_matches():
    res = _meaning_resolve("customer", "Qwenta Haulage", "Blorvak Industries", 0.99, "zz-embed-unknown")
    assert res.status == "unresolved", res


# ------------------------------------------------------------------------------------------------ AC-S3-4
def test_ac_s3_4_schema_declares_an_optional_nullable_string_meaning():
    props = span_extract.SCHEMA["properties"]["spans"]["items"]["properties"]
    assert "meaning" in props
    kind = props["meaning"].get("type")
    assert set(kind if isinstance(kind, list) else [kind]) == {"string", "null"}


def _cfg():
    return span_extract.SpanConfig("sys", 1, "openai", "gpt-zz", "ZZ-key", "label")


def _extract(content: str):
    with mock.patch.object(llm_call, "chat", return_value=ChatResult(content=content, prompt_tokens=1, completion_tokens=1, total_tokens=2)):
        return span_extract.extract(_cfg(), "zz message")


def test_ac_s3_4_a_span_with_a_meaning_parses():
    answer = _extract(json.dumps({"spans": [{"text": "zzemas", "type": "spec_value", "meaning": "zz gold"}]}))
    assert answer.failure is None
    assert answer.spans[0].text == "zzemas" and answer.spans[0].meaning == "zz gold"


def test_ac_s3_4_null_or_missing_meaning_parses_as_none():
    answer = _extract(json.dumps({"spans": [
        {"text": "zzone", "type": "brand", "meaning": None},
        {"text": "zztwo", "type": "brand"},
    ]}))
    assert answer.failure is None
    assert [(s.text, s.meaning) for s in answer.spans] == [("zzone", None), ("zztwo", None)]


VERSIONS = Path(__file__).resolve().parents[2] / "alembic" / "versions"
SPAN_KEY = "chatbot_span_extractor"
V1_TEXT = "ZZ span extractor v1 text.\nReturn the spans that name a record.\n"


def _migration():
    files = sorted(VERSIONS.glob("eem_0003*.py"))
    assert len(files) == 1, f"expected one eem_0003 migration, found {files}"
    spec = importlib.util.spec_from_file_location("_eem_0003_test", files[0])
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _versions(db):
    return db.query(AIPromptVersion).filter(AIPromptVersion.name == SPAN_KEY).order_by(AIPromptVersion.version).all()


def _span_v1(db):
    row = AIPromptVersion(id=str(uuid.uuid4()), name=SPAN_KEY, version=1, type="text", template=V1_TEXT, variables=[])
    db.add(row)
    db.flush()
    db.add(AIPromptLabel(name=SPAN_KEY, label="production", version_id=row.id))
    db.flush()
    return row


def test_ac_s3_4_migration_revision_single_head_and_chain():
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    m = _migration()
    assert m.revision == "eem_0003_span_meaning" and len(m.revision) <= 32
    script = ScriptDirectory.from_config(Config(str(VERSIONS.parents[1] / "alembic.ini")))
    heads = script.get_heads()
    assert len(heads) == 1, heads
    ancestry = {r.revision for r in script.walk_revisions(base="base", head=heads[0])}
    assert m.revision in ancestry and "eem_0002_span_version_on_diet" in ancestry


def test_ac_s3_4_migration_publishes_v2_with_a_meaning_instruction_unlabelled():
    m = _migration()
    with blank_session() as db:
        v1 = _span_v1(db)
        assert m.publish_meaning_version(db) == 2
        rows = _versions(db)
        assert [r.version for r in rows] == [1, 2]
        v2 = rows[-1]
        assert "meaning" in v2.template.lower() and "meaning" not in V1_TEXT.lower()
        assert V1_TEXT.strip() in v2.template
        labels = db.query(AIPromptLabel).filter(AIPromptLabel.name == SPAN_KEY).all()
        assert [(lbl.label, lbl.version_id) for lbl in labels] == [("production", v1.id)]


def test_ac_s3_4_migration_rerun_publishes_nothing():
    m = _migration()
    with blank_session() as db:
        _span_v1(db)
        assert m.publish_meaning_version(db) is not None
        assert m.publish_meaning_version(db) is None
        assert len(_versions(db)) == 2


def test_ac_s3_4_migration_downgrade_removes_only_its_own_row():
    m = _migration()
    with blank_session() as db:
        v1 = _span_v1(db)
        with mock.patch.object(m.op, "get_bind", return_value=db.connection()):
            m.upgrade()
            db.add(AIPromptVersion(id=str(uuid.uuid4()), name=SPAN_KEY, version=9, type="text", template="someone else's",
                                   variables=[], commit_message="not ours"))
            db.flush()
            m.downgrade()
        db.expire_all()
        assert [r.version for r in _versions(db)] == [1, 9]
        assert _versions(db)[0].id == v1.id
        assert [(lbl.label, lbl.version_id) for lbl in db.query(AIPromptLabel).filter(AIPromptLabel.name == SPAN_KEY)] == [("production", v1.id)]


# ------------------------------------------------------------------------------------------------ AC-S3-5
SPEC_GOLD = "Finish or colour ZZ gold"


def _rows():
    return [
        R("spec", "finish=zz gold", SPEC_GOLD),
        R("spec", "finish=zz silver", "Finish or colour ZZ silver"),
        R("spec", "finish=zz bronze", "Finish or colour ZZ bronze"),
        R("customer", "c1", "ZZKIMLAN"),
        R("customer", "c2", "Blorvak Industries"),
        R("brand", "b1", "Qwenta Haulage"),
    ]


def _run(spans):
    prep = engine_mod._SpanPrep(
        message="zz message", rows=_rows(), spec_key_rows=[], brand_words=frozenset(), numbers=[], held={}, embed=None,
        config=span_extract.SpanConfig("sys", 2, "openai", "gpt-zz", "ZZ-key", "label"),
    )
    answer = span_extract.SpanAnswer(spans, {}, 1)
    with mock.patch.object(span_extract, "extract", return_value=answer):
        return engine_mod._span_lookup(prep, session_factory=None, contact_respond_id="ZZ-contact", dry_run=True, turn_id=None)


def _entry(event, text):
    return next(s for s in event["spans"] if s["text"] == text)


def test_ac_s3_5_a_meaning_resolves_the_span_and_the_trace_records_it():
    lines, _lookup, event = _run([list_resolver.Span("zzemas", "spec_value", meaning="zz gold")])
    assert any(SPEC_GOLD in ln for ln in lines), lines
    entry = _entry(event, "zzemas")
    assert entry["text"] == "zzemas" and entry["meaning"] == "zz gold" and entry["matched_by"] == "meaning"
    assert entry["status"] == "resolved"
    assert entry["candidates"][0]["label"] == SPEC_GOLD


def test_ac_s3_5_a_meaning_that_resolves_nothing_falls_back_to_the_text():
    lines, _lookup, event = _run([list_resolver.Span("zzkimlan", "customer", meaning="zzqq xx vvv")])
    assert any("ZZKIMLAN" in ln for ln in lines), lines
    entry = _entry(event, "zzkimlan")
    assert entry["meaning"] == "zzqq xx vvv" and entry["matched_by"] == "text"
    assert entry["status"] == "resolved"


def test_ac_s3_5_a_span_without_a_meaning_resolves_by_its_text():
    lines, _lookup, event = _run([list_resolver.Span("zzkimlan", "customer")])
    assert any("ZZKIMLAN" in ln for ln in lines), lines
    entry = _entry(event, "zzkimlan")
    assert entry["meaning"] is None and entry["matched_by"] == "text"
