"""`EmbeddingReadService.search_tool_chunks` filters a domain's pool on
`mcp_tools.chatbot_domain` (DATA), not on the tool NAME (owner ruling, 8 Sep 2026: "I
don't accept the leak" - the PO placed tool's OLD name contained the word "order" and
leaked into every `order` pool under the old `source_id LIKE '%<domain>%'` filter; the
tool was also renamed to `crm_procurement_po_placed_list` so no domain's substring can
match it, but this column is the systemic fix for every OTHER tool, which is what these
fixture names below stand in for).

Real Postgres, via `tests/_pg_fixture.py::pg_session` - pgvector cosine distance needs the
real extension, and the rollback keeps every row scoped to this test. A throwaway
`source_type` per test isolates the query from the real `mcp_tool` pool entirely (the
domain subquery over `mcp_tools` has no `source_type` of its own, so isolation has to come
from the chunk side).
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime

from app.models.access import McpTool
from app.models.embeddings import EmbeddingChunk, EmbeddingDocument
from app.services.chatbot.contracts import DOMAIN_SPEC
from app.services.embedding_service import EmbeddingReadService
from tests._pg_fixture import pg_session

QUERY_VECTOR = [0.5] * 1536
FAR_VECTOR = [0.1] * 1536


def _seed_tool_and_chunk(db, *, source_type: str, tool_name: str, chatbot_domain, embedding):
    db.add(
        McpTool(
            id=str(uuid.uuid4()),
            tool_name=tool_name,
            description="test tool",
            http_path="/api/v1/test",
            http_method="GET",
            is_active=True,
            last_seen_at=datetime.utcnow(),
            chatbot_domain=chatbot_domain,
        )
    )
    source_id = f"implemented::{tool_name}"
    doc = EmbeddingDocument(
        id=str(uuid.uuid4()),
        source_type=source_type,
        source_id=source_id,
        source_key=source_id,
        title=tool_name,
        body_text=tool_name,
        source_hash=hashlib.sha256(source_id.encode()).hexdigest(),
        is_active=True,
    )
    db.add(doc)
    db.flush()
    db.add(
        EmbeddingChunk(
            id=str(uuid.uuid4()),
            document_id=doc.id,
            source_type=source_type,
            source_id=source_id,
            chunk_index=0,
            chunk_text=tool_name,
            chunk_hash=hashlib.sha256(f"chunk-{tool_name}".encode()).hexdigest(),
            embedding=embedding,
            model_name="test-model",
            model_version="v1",
            embedding_provider="test",
            source_hash=doc.source_hash,
            is_current=True,
        )
    )


def test_order_and_purchase_order_are_real_domain_spec_keys():
    """The premise both fixture domains below rely on."""
    assert "order" in DOMAIN_SPEC
    assert "purchase_order" in DOMAIN_SPEC


def test_order_pool_never_yields_the_po_tool_even_when_nearest():
    suffix = uuid.uuid4().hex[:8]
    source_type = f"zzt_tool_search_{suffix}"
    order_tool = f"zzt_order_list_{suffix}"
    # Deliberately contains "order" (the leak's premise): the old name-LIKE filter would
    # have matched this on `domain="order"`.
    po_tool = f"zzt_order_leak_po_{suffix}"

    with pg_session() as db:
        _seed_tool_and_chunk(
            db,
            source_type=source_type,
            tool_name=order_tool,
            chatbot_domain="order",
            embedding=FAR_VECTOR,
        )
        # The PO tool's chunk is an EXACT match to the query vector - the nearest
        # possible neighbour - so a name-based leak would surface it first.
        _seed_tool_and_chunk(
            db,
            source_type=source_type,
            tool_name=po_tool,
            chatbot_domain="purchase_order",
            embedding=QUERY_VECTOR,
        )
        db.flush()

        rows = EmbeddingReadService(db).search_tool_chunks(
            QUERY_VECTOR, source_type=source_type, limit=5, domain="order"
        )
        source_ids = {row["source_id"] for row in rows}

    assert f"implemented::{order_tool}" in source_ids
    assert f"implemented::{po_tool}" not in source_ids


def test_purchase_order_pool_yields_the_po_tool():
    suffix = uuid.uuid4().hex[:8]
    source_type = f"zzt_tool_search_{suffix}"
    order_tool = f"zzt_order_list_{suffix}"
    po_tool = f"zzt_order_leak_po_{suffix}"

    with pg_session() as db:
        _seed_tool_and_chunk(
            db,
            source_type=source_type,
            tool_name=order_tool,
            chatbot_domain="order",
            embedding=FAR_VECTOR,
        )
        _seed_tool_and_chunk(
            db,
            source_type=source_type,
            tool_name=po_tool,
            chatbot_domain="purchase_order",
            embedding=QUERY_VECTOR,
        )
        db.flush()

        rows = EmbeddingReadService(db).search_tool_chunks(
            QUERY_VECTOR, source_type=source_type, limit=5, domain="purchase_order"
        )
        source_ids = {row["source_id"] for row in rows}

    assert f"implemented::{po_tool}" in source_ids
    assert f"implemented::{order_tool}" not in source_ids


def test_an_unknown_domain_falls_back_to_the_name_like():
    """A `domain` outside `DOMAIN_SPEC` still hits the old substring filter - this is the
    degrade-not-throw path `search_tool_chunks`'s docstring names."""
    suffix = uuid.uuid4().hex[:8]
    source_type = f"zzt_tool_search_{suffix}"
    po_tool = f"zzt_order_leak_po_{suffix}"
    fallback_domain = f"leak_po_{suffix}"
    assert fallback_domain not in DOMAIN_SPEC

    with pg_session() as db:
        _seed_tool_and_chunk(
            db,
            source_type=source_type,
            tool_name=po_tool,
            chatbot_domain="purchase_order",
            embedding=QUERY_VECTOR,
        )
        db.flush()

        rows = EmbeddingReadService(db).search_tool_chunks(
            QUERY_VECTOR, source_type=source_type, limit=5, domain=fallback_domain
        )
        source_ids = {row["source_id"] for row in rows}

    assert f"implemented::{po_tool}" in source_ids
