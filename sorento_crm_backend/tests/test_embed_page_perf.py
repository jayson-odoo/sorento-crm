"""EMBED-PAGE-PERF: the Embeddings overview never reads the embedding_chunks heap.

`GET /api/v1/system/embeddings/overview` (System > Configuration > Embeddings, Records tab, refetched every 30 s)
counts chunks per source and model and the documents still missing the target model. Prod keeps every superseded
and old-model chunk (each row carries a 1536-dim vector and its chunk text), so a heap scan of embedding_chunks
grows with every re-embed and left the Records tab empty while it loaded. Every statement the overview runs must
answer its embedding_chunks part from an index alone.

The shape is pinned with sequential and bitmap scans disabled: the test data is tiny, so the planner would
otherwise seq-scan anything; the question is whether an index-only path EXISTS for each statement.

Postgres only (blank_session); all rows seeded here; Redis patched; no network.
Run: SORENTO_ENV_FILE=.env.ci-tests PGGSSENCMODE=disable no_proxy='*' venv/bin/pytest tests/test_embed_page_perf.py -q
"""
from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy import event, text

from tests._pg_fixture import TEST_PREFIX, blank_session

M3S = "text-embedding-3-small"
GEM = "gemini-embedding-001"


def pad(*head):
    return [float(x) for x in head] + [0.0] * (1536 - len(head))


@pytest.fixture
def db():
    with blank_session() as s:
        yield s


def _seed(db):
    from app.models.embeddings import EmbeddingChunk, EmbeddingDocument
    from app.models.user import SystemSetting

    db.add(SystemSetting(
        id=str(uuid.uuid4()), name=f"{TEST_PREFIX} EPP Co", embedding_provider="gemini", embedding_model=GEM,
        embedding_records_search_model=M3S, embedding_backfill_rpm=20,
    ))
    for st, n in (("attachment", 3), ("promotion", 2), ("lookup_word", 1), ("order", 1)):
        for i in range(n):
            d = EmbeddingDocument(
                id=str(uuid.uuid4()), source_type=st, source_id=f"zzt-epp-{st}-{i}", body_text="a\nb",
                metadata_json={"embed_failures": {GEM: 3}} if (st, i) == ("promotion", 1) else {},
                source_hash="h", is_active=True,
            )
            db.add(d)
            db.flush()
            for model, current in ((M3S, True), (GEM, i != 1), (M3S, False)):
                db.add(EmbeddingChunk(
                    id=str(uuid.uuid4()), document_id=d.id, source_type=st, source_id=d.source_id,
                    chunk_index=0 if current else 1, chunk_text="zzt", chunk_hash="h", embedding=pad(1.0),
                    model_name=model, model_version="1", embedding_provider="x", source_hash="h", is_current=current,
                ))
    db.flush()


def _chunk_nodes(plan):
    if plan.get("Relation Name") == "embedding_chunks":
        yield plan["Node Type"]
    for child in plan.get("Plans", []):
        yield from _chunk_nodes(child)


def test_overview_reads_embedding_chunks_through_indexes_only(db, monkeypatch):
    from app.api.v1.system import embeddings as api

    monkeypatch.setattr(api, "_backfill_running", lambda: False)
    _seed(db)

    statements: list[tuple[str, object]] = []
    conn = db.connection()

    def _capture(_conn, _cursor, statement, parameters, _context, _executemany):
        if "embedding_chunks" in statement:
            statements.append((statement, parameters))

    event.listen(conn, "before_cursor_execute", _capture)
    try:
        out = api.embeddings_overview(db)
    finally:
        event.remove(conn, "before_cursor_execute", _capture)

    # The counts the screen shows are unchanged by the query shape.
    records = {r["source_type"]: r for r in out["records"]}
    assert records["attachment"]["documents"] == 3
    assert records["attachment"]["chunks_by_model"] == {M3S: 3, GEM: 2}
    assert records["promotion"]["chunks_by_model"] == {M3S: 2, GEM: 1}
    assert out["guard"]["remaining"] == 1  # attachment-1 lacks GEM; promotion-1 is given up on
    assert out["guard"]["failed"] == 1
    assert out["lookup"]["texts_with_vector"] == 1

    assert len(statements) >= 4, statements
    db.execute(text("SET LOCAL enable_seqscan = off"))
    db.execute(text("SET LOCAL enable_bitmapscan = off"))
    raw = db.connection().connection.cursor()
    for statement, parameters in statements:
        raw.execute("EXPLAIN (FORMAT JSON) " + statement, parameters)
        plan = raw.fetchone()[0]
        plan = plan if isinstance(plan, list) else json.loads(plan)
        nodes = list(_chunk_nodes(plan[0]["Plan"]))
        assert nodes, statement
        assert all(n == "Index Only Scan" for n in nodes), f"{nodes} for: {statement}"
