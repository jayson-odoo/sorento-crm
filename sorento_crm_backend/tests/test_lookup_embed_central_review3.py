"""LOOKUP-EMBED-CENTRAL review fix round 3 (H-1, H-2, H-3, H-6), backend. Red before the fixes.
Run: SORENTO_ENV_FILE=.env.ci-tests PGGSSENCMODE=disable no_proxy='*' venv/bin/pytest tests/test_lookup_embed_central_review3.py -q -n 2
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest

from tests.test_lookup_embed_central_review2 import (  # noqa: F401  (fixtures and helpers)
    EDIT_SETTINGS, GEM, M3S, SETTINGS, SETTINGS_UPDATE, _FakeRedis, _assistant, _doc, _failures, _setting, allow, client,
    db, pad, scope,
)

START = "/api/v1/system/embeddings/records-backfill"


# ================================================================== H-1: the real call shape carries the hint
@pytest.mark.parametrize("query", ["stock for SRT-123", "how many units of SRT-123 do we have"])
def test_h1_the_stock_balance_tool_wins_with_the_resolved_references_hint_present(db, monkeypatch, query):
    from app.services import embedding_client, embedding_settings
    from app.services.mcp_tool_capability_service import build_capability_documents

    _svc, cls, inst = _assistant(db)
    names = sorted({d.source_key for d in build_capability_documents(include_planned=False)})

    def boom(*a, **k):
        raise AssertionError("an embed call was made")

    monkeypatch.setattr(embedding_client, "embed_texts", boom)
    monkeypatch.setattr(embedding_settings, "embed_search_texts", boom)
    rag_query = f'{query}\nResolved references: "SRT-123" is product.'  # standalone_query + to_query_hint()
    selected, _sources = inst._rag_select_tools(standalone_query=rag_query, enabled_tools=names, top_k=1)
    assert [c["tool_name"] for c in selected] == ["crm_inventory_stock_balance_list"], selected


# ================================================================== H-2: failures accumulate across Starts
@pytest.fixture
def inline_jobs(db, monkeypatch):
    """Redis faked, the job queue runs a job inline on the test session, the guard builds no real index."""
    from app.services import embedding_indexes, queue_service
    from app.tasks import embedding_backfill as task

    fake = _FakeRedis()
    monkeypatch.setattr(queue_service, "redis_conn", fake)
    monkeypatch.setattr(task, "SessionLocal", lambda: db)
    monkeypatch.setattr(db, "close", lambda: None)
    monkeypatch.setattr(embedding_indexes, "index_ddl", lambda model: [])

    def run(func, *args, **kw):
        func(*args)
        return MagicMock(id="inline")

    monkeypatch.setattr(queue_service, "enqueue_job", run)
    return fake


def _always_bad_for_one_document(monkeypatch):
    from app.services import embedding_client, embedding_settings

    def picky(session, texts, model, **kw):
        if any("ALWAYS-BAD" in t for t in texts):
            raise embedding_client.EmbeddingHTTPError("Embedding call failed (400): input rejected", 400)
        return [pad(1.0) for _ in texts]

    monkeypatch.setattr(embedding_settings, "embed_for_model", picky)


def test_h2_a_document_that_always_fails_reaches_three_across_starts_and_stops_blocking_the_guard(
    client, db, allow, inline_jobs, monkeypatch
):
    from app.models.user import SystemSetting
    from app.services.embedding_backfill_service import failed_documents

    allow.add(SETTINGS_UPDATE)
    _setting(db, embedding_backfill_rpm=6000)  # a 0.01 s pause between requests: the single-document retries are many
    for n in range(150):
        _doc(db, "promotion", n)
    bad = _doc(db, "promotion", 999, body="zzt ALWAYS-BAD input")
    db.commit()
    _always_bad_for_one_document(monkeypatch)
    for expected in (1, 2, 3):
        assert client.post(START, json={"action": "start"}).status_code == 202
        assert _failures(db, bad, GEM) == expected, f"after Start {expected}"
    assert [i for _t, i, _n in failed_documents(db, GEM)] == [bad.source_id]
    db.expire_all()
    assert db.query(SystemSetting).first().embedding_records_search_model == GEM


def test_h2_a_settings_model_change_still_resets_the_new_models_counts(client, db, allow, monkeypatch):
    from app.services import queue_service

    monkeypatch.setattr(queue_service, "enqueue_job", lambda *a, **k: MagicMock(id="j"))
    allow.add(EDIT_SETTINGS)
    _setting(db, embedding_provider="openai", embedding_model=M3S)
    stuck = _doc(db, "promotion", 1, failures={GEM: 3})
    db.commit()
    assert client.put(f"{SETTINGS}/general", json={"embedding_provider": "gemini", "embedding_model": GEM}).status_code == 200
    assert _failures(db, stuck, GEM) == 0


# ================================================================== H-3
def test_h3_a_failing_count_reset_never_turns_a_saved_setting_into_a_500(client, db, allow, monkeypatch):
    from app.models.user import SystemSetting
    from app.services import embedding_backfill_service, queue_service

    monkeypatch.setattr(queue_service, "enqueue_job", lambda *a, **k: MagicMock(id="j"))

    def boom(*a, **k):
        raise RuntimeError("zzt reset failed")

    monkeypatch.setattr(embedding_backfill_service, "clear_failures", boom)
    allow.add(EDIT_SETTINGS)
    _setting(db, embedding_provider="openai", embedding_model=M3S)
    db.commit()
    resp = client.put(f"{SETTINGS}/general", json={"embedding_provider": "gemini", "embedding_model": GEM})
    assert resp.status_code == 200, resp.text
    db.expire_all()
    assert db.query(SystemSetting).first().embedding_model == GEM


def test_h3_a_job_that_cannot_claim_the_running_flag_exits_without_embedding(db, monkeypatch):
    from app.services import embedding_backfill_service as svc, queue_service
    from app.tasks import embedding_backfill as task

    fake = _FakeRedis()
    fake.store[task.RECORDS_BACKFILL_RUNNING_KEY] = "another-job-token"
    monkeypatch.setattr(queue_service, "redis_conn", fake)
    monkeypatch.setattr(task, "SessionLocal", lambda: db)
    monkeypatch.setattr(db, "close", lambda: None)
    _setting(db)
    calls: list = []
    monkeypatch.setattr(svc, "backfill_records", lambda *a, **k: calls.append(a) or svc.BackfillResult(0, 0, 0, True))
    monkeypatch.setattr(svc, "apply_search_model_guard", lambda *a, **k: calls.append(a) or False)
    task.run_records_backfill(GEM)
    assert calls == [], "a second job ran while another held the running flag"
    assert fake.store.get(task.RECORDS_BACKFILL_RUNNING_KEY) == "another-job-token", "the other job's flag was taken or cleared"


# ================================================================== H-6: product_spec documents for existing products
def test_h6_the_records_backfill_creates_and_embeds_product_spec_documents_for_products_with_spec_text(db, monkeypatch):
    from app.models.embeddings import EmbeddingChunk, EmbeddingDocument
    from app.services import embedding_settings
    from app.services.embedding_backfill_service import backfill_records
    from app.services.company_scope import set_company_scope
    from tests.test_lookup_embed_central_slice2 import _product, _spec

    set_company_scope(db, None)
    _setting(db)
    p1, p2, p3 = _product(db, "ZZT-H6-1"), _product(db, "ZZT-H6-2"), _product(db, "ZZT-H6-3")
    _spec(db, p1, "ceramic wall hung closet 400 mm")
    _spec(db, p2, "chrome basin mixer")
    _spec(db, p3, "")  # nothing to embed
    db.commit()
    assert db.query(EmbeddingDocument).filter_by(source_type="product_spec").count() == 0
    monkeypatch.setattr(embedding_settings, "embed_for_model", lambda session, texts, model, **kw: [pad(1.0) for _ in texts])

    backfill_records(db, GEM, sleep=lambda s: None)

    db.expire_all()
    docs = {d.source_id: d for d in db.query(EmbeddingDocument).filter_by(source_type="product_spec")}
    assert set(docs) == {str(p1.id), str(p2.id)}, sorted(docs)
    chunks = db.query(EmbeddingChunk).filter_by(source_type="product_spec", model_name=GEM, is_current=True).all()
    assert {c.chunk_text for c in chunks} == {"ceramic wall hung closet 400 mm", "chrome basin mixer"}
