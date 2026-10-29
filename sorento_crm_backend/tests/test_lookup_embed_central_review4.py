"""LOOKUP-EMBED-CENTRAL review fix round 4 (J-1, J-2), backend. Red before the fixes.
Run: SORENTO_ENV_FILE=.env.ci-tests PGGSSENCMODE=disable no_proxy='*' venv/bin/pytest tests/test_lookup_embed_central_review4.py -q -n 2
"""
from __future__ import annotations

from unittest.mock import MagicMock

from tests.test_lookup_embed_central_review3 import (  # noqa: F401  (fixtures and helpers)
    EDIT_SETTINGS, GEM, M3S, SETTINGS, _always_bad_for_one_document, _doc, _failures, _setting, allow, client, db,
    inline_jobs, pad, scope,
)


# ================================================================== J-1: new product_spec documents survive a failing first batch
def test_j1_a_per_document_400_in_the_first_batch_keeps_the_new_product_spec_documents(db, monkeypatch):
    from app.models.embeddings import EmbeddingChunk, EmbeddingDocument
    from app.services.company_scope import set_company_scope
    from app.services.embedding_backfill_service import backfill_records
    from tests.test_lookup_embed_central_slice2 import _product, _spec

    set_company_scope(db, None)
    _setting(db)
    for n in range(3):
        _doc(db, "promotion", n)
    bad = _doc(db, "promotion", 999, body="zzt ALWAYS-BAD input")
    products = [_product(db, f"ZZT-J1-{i}") for i in range(2)]
    for p in products:
        _spec(db, p, f"zzt j1 spec text {p.product_code}")
    db.commit()
    assert db.query(EmbeddingDocument).filter_by(source_type="product_spec").count() == 0
    _always_bad_for_one_document(monkeypatch)

    backfill_records(db, GEM, sleep=lambda s: None)  # must not raise

    db.rollback()  # anything only flushed is gone; committed rows stay
    db.expire_all()
    docs = {d.source_id for d in db.query(EmbeddingDocument).filter_by(source_type="product_spec")}
    assert docs == {str(p.id) for p in products}, sorted(docs)
    assert db.query(EmbeddingChunk).filter_by(source_type="product_spec", model_name=GEM, is_current=True).count() == 2
    assert db.query(EmbeddingChunk).filter_by(source_type="promotion", model_name=GEM, is_current=True).count() >= 3
    assert _failures(db, bad, GEM) == 1


# ================================================================== J-2: a settings model change clears the Stop flag
def test_j2_a_settings_model_change_clears_the_records_backfill_stop_flag_before_it_enqueues(
    client, db, allow, inline_jobs, monkeypatch
):
    from app.services import queue_service
    from app.tasks import embedding_backfill as task

    seen: list = []

    def record(func, *args, **kw):
        seen.append((func, task.RECORDS_BACKFILL_STOP_KEY in inline_jobs.store))
        return MagicMock(id="j")

    monkeypatch.setattr(queue_service, "enqueue_job", record)
    allow.add(EDIT_SETTINGS)
    _setting(db, embedding_provider="openai", embedding_model=M3S)
    db.commit()
    inline_jobs.store[task.RECORDS_BACKFILL_STOP_KEY] = "1"  # Stop pressed earlier

    resp = client.put(f"{SETTINGS}/general", json={"embedding_provider": "gemini", "embedding_model": GEM})

    assert resp.status_code == 200, resp.text
    assert [f for f, _ in seen] == [task.run_records_backfill]
    assert seen[0][1] is False, "the stop flag was still set when the backfill was enqueued"
    assert task.RECORDS_BACKFILL_STOP_KEY not in inline_jobs.store
