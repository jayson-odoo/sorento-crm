"""`resolve_via_embedding_then_ilike` really takes the embedding pre-resolve path
rather than silently degrading to raw ilike.

This pins the regression the OpenAI-key-resolution fix introduced: `_embed_query`
picked up a `db` parameter and `fuzzy_resolver.py` kept calling it with only the
query term. The broad `except Exception` a few lines down swallowed the resulting
`TypeError` and fell back to matching the raw term only - every caller of
`resolve_via_embedding_then_ilike` (order_service, incoming_stock_service,
procurement_service) kept "working" with worse search quality and no error
anywhere. A stubbed embedder + a real canonical row is the only way to prove the
embed path ran rather than merely that no exception escaped.
"""
from __future__ import annotations

import uuid

from app.models.order import Customer
from app.services.fuzzy_resolver import resolve_via_embedding_then_ilike
from tests._pg_fixture import blank_session


def _uid() -> str:
    return str(uuid.uuid4())


class _EmbedRecorder:
    def __init__(self):
        self.calls: list[tuple] = []

    def __call__(self, db, query):
        self.calls.append((db, query))
        return [0.1, 0.2, 0.3]


class _StubChunk:
    def __init__(self, source_id: str):
        self.source_id = source_id


class _StubEmbeddingReadService:
    """Stands in for `EmbeddingReadService(db)` - returns one hit pointing at the
    canonical row the test seeded, so `canonical_values` only comes out non-empty
    if the embed-then-search path actually ran."""

    last_kwargs: dict | None = None

    def __init__(self, db):
        self.db = db

    def search_current(self, *_a, **kwargs):
        _StubEmbeddingReadService.last_kwargs = kwargs
        return [(_StubChunk(_StubEmbeddingReadService.hit_id), None, 0.9)]


def test_resolve_via_embedding_then_ilike_takes_the_embed_path(monkeypatch):
    import app.api.v1.external.rag as rag_module
    import app.services.embedding_service as embedding_service_module

    recorder = _EmbedRecorder()
    monkeypatch.setattr(rag_module, "_embed_query", recorder)
    monkeypatch.setattr(
        embedding_service_module, "EmbeddingReadService", _StubEmbeddingReadService
    )

    with blank_session() as db:
        customer = Customer(
            id=_uid(), customer_code="ZZT-CODE-1", customer_name="ZZT Customer One"
        )
        db.add(customer)
        db.flush()
        _StubEmbeddingReadService.hit_id = customer.id

        clause, canonical_values = resolve_via_embedding_then_ilike(
            db,
            "yotu",
            source_type="customer",
            ilike_columns=[Customer.customer_name, Customer.customer_code],
            canonical_model=Customer,
            canonical_fields=("customer_name", "customer_code"),
        )

    assert recorder.calls, "the embed path was never taken - a signature drift is falling back silently"
    assert recorder.calls[0] == (db, "yotu")
    assert "ZZT Customer One" in canonical_values
    assert "ZZT-CODE-1" in canonical_values
    assert clause is not None


def test_resolve_via_embedding_then_ilike_degrades_to_raw_ilike_when_embed_raises(monkeypatch):
    """The documented fallback still works - an embed failure loses the canonical
    expansion, never the whole search."""
    import app.api.v1.external.rag as rag_module

    def _boom(db, query):
        raise RuntimeError("no OpenAI key configured")

    monkeypatch.setattr(rag_module, "_embed_query", _boom)

    with blank_session() as db:
        clause, canonical_values = resolve_via_embedding_then_ilike(
            db,
            "yotu",
            source_type="customer",
            ilike_columns=[Customer.customer_name],
            canonical_model=Customer,
            canonical_fields=("customer_name", "customer_code"),
        )

    assert canonical_values == []
    assert clause is not None
