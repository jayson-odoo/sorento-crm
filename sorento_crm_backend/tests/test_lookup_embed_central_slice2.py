"""LOOKUP-EMBED-CENTRAL slice 2 red tests: keep set, product_spec, readers, indexes (AC-LEC-5..7, 9..12).

Postgres only (blank_session); every row is seeded here. No network: the one embeddings transport
(httpx.Client.send) is stubbed, so any reader that embeds through embedding_client is intercepted and the
request body shows which model it asked for. Vectors are tiny and padded to 1536.
Run: SORENTO_ENV_FILE=.env.ci-tests PGGSSENCMODE=disable no_proxy='*' venv/bin/pytest tests/test_lookup_embed_central_slice2.py -q -n 2
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import date, datetime

import httpx
import pytest
from sqlalchemy import event, text

from app.models.embeddings import EmbeddingChunk, EmbeddingDocument, EmbeddingQueue
from app.models.product import Brand, Product, ProductCategory, UnitOfMeasure
from app.models.product_spec import ProductSpecifications
from app.services import entity_resolver as er
from app.services.company_scope import set_company_scope
from app.services.embedding_change_listener import register_embedding_change_listeners
from app.services.embedding_service import EmbeddingReadService
from app.services.product_spec_change_listener import register_product_spec_listeners
from tests._pg_fixture import TEST_PREFIX, blank_session

register_embedding_change_listeners()
register_product_spec_listeners()

KEEP = {"attachment", "promotion", "certificate", "form", "product_spec", "project"}
M3S = "text-embedding-3-small"
GEM = "gemini-embedding-001"


def pad(*head: float) -> list[float]:
    return [float(x) for x in head] + [0.0] * (1536 - len(head))


@pytest.fixture
def db():
    with blank_session() as s:
        set_company_scope(s, None)
        yield s


class Transport:
    """Stub of httpx.Client.send: answers every input text from `vectors`, else `default`."""

    def __init__(self, default, vectors=None):
        self.default = default
        self.vectors = vectors or {}
        self.models: list[str] = []
        self.inputs: list[str] = []

    def send(self, request):
        body = json.loads(request.content)
        self.models.append(body.get("model", ""))
        inputs = body.get("input") or [
            "".join(p.get("text", "") for p in r["content"]["parts"]) for r in body.get("requests", [])
        ]
        self.inputs.extend(inputs)
        vecs = [self.vectors.get(t, self.default) for t in inputs]
        if "batchEmbedContents" in str(request.url):
            data = {"embeddings": [{"values": v} for v in vecs]}
        else:
            data = {"data": [{"index": i, "embedding": v} for i, v in enumerate(vecs)]}
        return httpx.Response(200, json=data, request=request)


@pytest.fixture
def transport(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "openai_api_key", "zzt-key", raising=False)
    for name in ("_VECTOR_CACHE",):
        getattr(er, name, {}).clear() if hasattr(getattr(er, name, None), "clear") else None

    def make(default, vectors=None):
        t = Transport(default, vectors)
        monkeypatch.setattr(httpx.Client, "send", lambda self, request, **kw: t.send(request))
        return t

    return make


# ------------------------------------------------------------------ seed helpers
def _setting(db, **cols):
    from app.models.user import SystemSetting

    row = SystemSetting(id=str(uuid.uuid4()), name=f"{TEST_PREFIX} LEC2 Co", **cols)
    db.add(row)
    db.flush()
    return row


def _product(db, code: str) -> Product:
    cat = db.query(ProductCategory).first()
    if cat is None:
        cat = ProductCategory(id=str(uuid.uuid4()), category_code="ZZT-LEC2", category_name="ZZT LEC2")
        uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code="ZZT-L2", uom_name="Piece")
        brand = Brand(id=str(uuid.uuid4()), brand_code="ZZT-L2B", brand_name="ZZT L2")
        db.add_all([cat, uom, brand])
        db.flush()
    uom = db.query(UnitOfMeasure).first()
    brand = db.query(Brand).first()
    p = Product(
        id=str(uuid.uuid4()), product_code=code, product_name=code, description="zzt",
        category_id=cat.id, base_uom_id=uom.id, brand_id=brand.id, list_price=1,
    )
    db.add(p)
    db.flush()
    return p


def _doc(db, source_type, source_id, source_key=None) -> EmbeddingDocument:
    d = (
        db.query(EmbeddingDocument)
        .filter_by(source_type=source_type, source_id=str(source_id))
        .first()
    )
    if d is None:
        d = EmbeddingDocument(
            id=str(uuid.uuid4()), source_type=source_type, source_id=str(source_id),
            source_key=source_key, title=source_key, body_text="zzt body", source_hash="h", is_active=True,
        )
        db.add(d)
        db.flush()
    return d


def _chunk(db, source_type, source_id, vec, *, model=M3S, source_key=None, is_current=True, doc=None):
    doc = doc or _doc(db, source_type, source_id, source_key)
    c = EmbeddingChunk(
        id=str(uuid.uuid4()), document_id=doc.id, source_type=source_type, source_id=str(source_id),
        chunk_index=0, chunk_text="zzt", chunk_hash="h", embedding=vec, model_name=model,
        model_version="1", embedding_provider="openai" if model == M3S else "gemini",
        source_hash="h", is_current=is_current,
    )
    db.add(c)
    db.flush()
    return c


def _pending(db, source_type, source_id=None):
    q = db.query(EmbeddingQueue).filter(EmbeddingQueue.source_type == source_type)
    if source_id is not None:
        q = q.filter(EmbeddingQueue.source_id == str(source_id))
    return q.all()


def _clear_queue(db):
    db.query(EmbeddingQueue).update({"status": "completed"}, synchronize_session=False)
    db.flush()


# ================================================================== AC-LEC-5
def test_ac_lec_5_record_keep_set_is_exactly_the_six_sources():
    from app.services.embedding_settings import HOT_FILTERED_SOURCES, RECORD_KEEP_SET

    assert RECORD_KEEP_SET == frozenset(KEEP)
    assert tuple(HOT_FILTERED_SOURCES) == ("attachment", "product_spec")


def test_ac_lec_5_changed_dropped_sources_enqueue_nothing(db):
    from app.models.marketing import Promotion, PromotionGroup, PromotionProduct
    from app.models.order import Customer, Order

    order = Order(order_number="ZZT-LEC2-1", order_date=date(2026, 10, 1), debtor_name="D", remarks="r")
    customer = Customer(customer_code="ZZT-LEC2-C", customer_name="ZZT LEC2 Customer")
    promo = Promotion(description="ZZT LEC2 promo", start_date=date(2026, 10, 1), end_date=date(2026, 12, 1), is_active=True)
    product = _product(db, "ZZT-LEC2-P")
    db.add_all([order, customer, promo])
    db.flush()
    group = PromotionGroup(promotion_id=promo.id, group_name="ZZT LEC2 group")
    db.add(group)
    db.flush()
    pp = PromotionProduct(promotion_id=promo.id, promotion_group_id=group.id, product_id=product.id)
    db.add(pp)
    db.flush()
    _clear_queue(db)
    order.remarks = "changed"
    customer.customer_name = "ZZT LEC2 Customer changed"
    pp.discount_percent = 5
    product.product_name = "ZZT-LEC2-P changed"
    db.flush()
    pending = [r for r in db.query(EmbeddingQueue).filter(EmbeddingQueue.status == "pending").all()]
    dropped = {r.source_type for r in pending} - KEEP
    assert not dropped, f"queued sources outside the keep set: {sorted(dropped)}"


def test_ac_lec_5_inserted_dropped_sources_enqueue_nothing(db):
    from app.models.order import Customer, Order

    db.add_all([
        Order(order_number="ZZT-LEC2-2", order_date=date(2026, 10, 1), debtor_name="D", remarks="r"),
        Customer(customer_code="ZZT-LEC2-C2", customer_name="ZZT LEC2 Customer 2"),
    ])
    db.flush()
    queued = {r.source_type for r in db.query(EmbeddingQueue).all()}
    assert not (queued - KEEP), sorted(queued - KEEP)


def test_ac_lec_5_bulk_enqueue_of_a_dropped_source_queues_nothing(db):
    from app.services.embedding_change_listener import bulk_enqueue_embedding_events

    bulk_enqueue_embedding_events(db, "customer", [str(uuid.uuid4())])
    assert _pending(db, "customer") == []


def test_ac_lec_5_keep_set_sources_still_enqueue(db):
    from app.models.marketing import Promotion

    promo = Promotion(description="ZZT LEC2 keep", start_date=date(2026, 10, 1), end_date=date(2026, 12, 1), is_active=True)
    db.add(promo)
    db.flush()
    assert len(_pending(db, "promotion", promo.id)) == 1


@pytest.fixture
def worker(db, monkeypatch):
    from app.services import embedding_client, embedding_worker

    monkeypatch.setattr(embedding_worker, "SessionLocal", lambda: db)
    monkeypatch.setattr(db, "close", lambda: None)
    calls: list[tuple] = []

    def spy(texts, provider, model, **kw):
        calls.append((list(texts), provider, model))
        return [pad(1.0) for _ in texts]

    monkeypatch.setattr(embedding_client, "embed_texts", spy)
    monkeypatch.setattr(embedding_worker, "_embed_text_chunks", lambda chunks, timeout=None: (calls.append((list(chunks), "x", "x")), [pad(1.0) for _ in chunks])[1])
    return embedding_worker, calls


def test_ac_lec_5_worker_skips_a_dropped_source_without_embedding(db, worker):
    embedding_worker, calls = worker
    sid = str(uuid.uuid4())
    chunk = _chunk(db, "order", sid, pad(1.0), source_key="ZZT-LEC2-ORD")
    now = datetime.utcnow()
    item = EmbeddingQueue(
        id=str(uuid.uuid4()), source_type="order", source_id=sid, event_type="order.updated", event_version=1,
        payload={}, status="pending", retry_count=0, available_at=now, created_at=now,
    )
    db.add(item)
    db.flush()

    result = embedding_worker.process_embedding_queue_item(item.id)

    db.expire_all()
    assert result["status"] == "skipped", result
    assert db.get(EmbeddingQueue, item.id).status == "skipped"
    assert calls == [], f"the worker embedded a dropped source: {calls}"
    assert db.get(EmbeddingChunk, chunk.id) is not None, "an existing chunk of a dropped source was deleted"
    assert db.get(EmbeddingChunk, chunk.id).is_current is True


# ================================================================== AC-LEC-6
def _spec(db, product, rendered_text):
    s = ProductSpecifications(id=str(uuid.uuid4()), product_id=product.id, rendered_text=rendered_text)
    db.add(s)
    db.flush()
    return s


def test_ac_lec_6_spec_insert_with_text_enqueues_product_spec(db):
    p = _product(db, "ZZT-LEC2-S1")
    _spec(db, p, "ceramic wall hung closet 400 mm")
    rows = _pending(db, "product_spec", p.id)
    assert len(rows) == 1 and rows[0].status == "pending"


def test_ac_lec_6_changed_rendered_text_enqueues_again(db):
    p = _product(db, "ZZT-LEC2-S2")
    s = _spec(db, p, "ceramic wall hung closet 400 mm")
    _clear_queue(db)
    s.rendered_text = "ceramic floor standing closet 500 mm"
    db.flush()
    assert len([r for r in _pending(db, "product_spec", p.id) if r.status == "pending"]) == 1


def test_ac_lec_6_empty_rendered_text_enqueues_nothing(db):
    p = _product(db, "ZZT-LEC2-S3")
    s = _spec(db, p, "")
    s2_product = _product(db, "ZZT-LEC2-S4")
    _spec(db, s2_product, None)
    s.rendered_text = "   "
    db.flush()
    assert _pending(db, "product_spec") == []


def test_ac_lec_6_worker_text_is_rendered_text_only(db):
    from app.services.embedding_worker import _canonical_for_source, _chunks_for_source

    p = _product(db, "ZZT-LEC2-S5")
    _spec(db, p, "ceramic wall hung closet 400 mm")
    canonical = _canonical_for_source(db, "product_spec", p.id)
    assert canonical["body_text"] == "ceramic wall hung closet 400 mm"
    assert _chunks_for_source("product_spec", canonical) == ["ceramic wall hung closet 400 mm"]


# ================================================================== AC-LEC-7
def _spec_product_with_chunk(db, code, vec, *, model=M3S):
    p = _product(db, code)
    _spec(db, p, f"zzt spec of {code}")
    _chunk(db, "product_spec", p.id, vec, model=model, source_key=code)
    return p


def test_ac_lec_7_reader_source_map_stays_inside_the_keep_set_and_uses_product_spec():
    from app.services.embedding_settings import RECORD_KEEP_SET

    assert er._EMBEDDING_SOURCE_TYPES.get("product_spec") == "product"
    assert "product" not in er._EMBEDDING_SOURCE_TYPES
    outside = set(er._EMBEDDING_SOURCE_TYPES) - set(RECORD_KEEP_SET)
    assert not outside, f"readers ask for sources outside the keep set: {sorted(outside)}"


def test_ac_lec_7_tier3_maps_a_product_spec_hit_to_the_product(db, transport):
    p = _spec_product_with_chunk(db, "ZZT-LEC2-T1", pad(1.0, 0.1))
    transport(pad(1.0, 0.1))
    hits = er._tier3_embedding_lookup(db, f"zzt toilet bowl {uuid.uuid4().hex}", frozenset({"product"}))
    assert [(h.entity_type, h.canonical_code, h.uuid) for h in hits] == [("product", "ZZT-LEC2-T1", str(p.id))]


def test_ac_lec_7_rag_phrase_maps_a_product_spec_hit_to_the_product(db, transport):
    _spec_product_with_chunk(db, "ZZT-LEC2-R1", pad(1.0, 0.1))
    transport(pad(1.0, 0.1))
    hits = er._rag_resolve_phrase(db, f"zzt toilet bowl {uuid.uuid4().hex}", frozenset({"product"}))
    assert [(h.entity_type, h.canonical_code) for h in hits] == [("product", "ZZT-LEC2-R1")]


# ================================================================== AC-LEC-9
def _two_model_world(db):
    p = _product(db, "ZZT-LEC2-M1")
    _spec(db, p, "zzt two model spec")
    doc = _doc(db, "product_spec", p.id, "ZZT-LEC2-M1")
    q = pad(1.0)
    _chunk(db, "product_spec", p.id, pad(0.9, 0.43589), model=M3S, doc=doc, source_key="ZZT-LEC2-M1")  # cos 0.90
    _chunk(db, "product_spec", p.id, pad(1.0), model=GEM, doc=doc, source_key="ZZT-LEC2-M1")  # cos 1.00, nearer
    _setting(db, embedding_records_search_model=M3S)
    return p, q


def test_ac_lec_9_search_current_compares_only_the_records_search_model(db):
    _p, q = _two_model_world(db)
    hits = EmbeddingReadService(db).search_current(q, top_k=5)
    assert [c.model_name for c, _d, _s in hits] == [M3S], [(c.model_name, round(s, 3)) for c, _d, s in hits]


def test_ac_lec_9_resolver_tier_embeds_and_filters_by_the_records_search_model(db, transport):
    _p, q = _two_model_world(db)
    t = transport(q)
    hits = er._tier3_embedding_lookup(db, f"zzt closet {uuid.uuid4().hex}", frozenset({"product"}))
    assert t.models and set(t.models) == {M3S}, t.models
    assert len(hits) == 1 and hits[0].similarity == pytest.approx(0.90, abs=0.01), hits


def test_ac_lec_9_rag_phrase_embeds_and_filters_by_the_records_search_model(db, transport):
    _p, q = _two_model_world(db)
    t = transport(q)
    hits = er._rag_resolve_phrase(db, f"zzt closet {uuid.uuid4().hex}", frozenset({"product"}))
    assert t.models and set(t.models) == {M3S}, t.models
    assert [round(h.similarity, 2) for h in hits] == [0.90], hits


# ================================================================== AC-LEC-10 / 11 (indexes)
def _create_indexes(db, model=M3S):
    from app.services import embedding_indexes

    for ddl in embedding_indexes.index_ddl(model):
        db.execute(text(ddl.replace(" CONCURRENTLY", "")))  # CONCURRENTLY cannot run inside the test transaction
    # Competing btree indexes on source_type / is_current / model_name let the planner answer a 60-row
    # table with btree + sort at a fraction of the HNSW cost, so enable_seqscan=off alone cannot make it
    # pick the HNSW index. They are dropped here, inside this test's rolled-back transaction, so the plan
    # can only prove one thing: the reader's predicate matches the partial index. Which plan wins at real
    # table size is verified separately on a dev copy.
    for (name,) in db.execute(
        text(
            "SELECT indexname FROM pg_indexes WHERE schemaname = current_schema() "
            "AND tablename = 'embedding_chunks' AND indexname LIKE 'ix\\_embedding\\_chunks%'"
        )
    ).all():
        db.execute(text(f'DROP INDEX "{name}"'))
    db.flush()


def _captured_search_sql(db, fn):
    captured: list[tuple] = []
    bind = db.get_bind()

    def grab(conn, cursor, statement, parameters, context, executemany):
        if "embedding_chunks" in statement and "<=>" in statement:
            captured.append((statement, parameters))

    event.listen(bind, "before_cursor_execute", grab)
    try:
        result = fn()
    finally:
        event.remove(bind, "before_cursor_execute", grab)
    assert captured, "no vector search statement was issued"
    return captured[-1], result


def _explain(db, statement, parameters):
    rows = db.connection().exec_driver_sql("EXPLAIN " + statement, parameters).fetchall()
    return "\n".join(r[0] for r in rows)


def _seed_many(db, plan):
    """plan: list of (source_type, count, vector_factory(i))."""
    docs, chunks = [], []
    n = 0
    for source_type, count, factory in plan:
        for i in range(count):
            sid = f"zzt-lec2-{source_type}-{i}"
            d = EmbeddingDocument(
                id=str(uuid.uuid4()), source_type=source_type, source_id=sid, source_key=sid,
                title=sid, body_text="zzt", source_hash="h", is_active=True,
            )
            docs.append(d)
            chunks.append(
                EmbeddingChunk(
                    id=str(uuid.uuid4()), document_id=d.id, source_type=source_type, source_id=sid,
                    chunk_index=0, chunk_text="zzt", chunk_hash="h", embedding=factory(n), model_name=M3S,
                    model_version="1", embedding_provider="openai", source_hash="h", is_current=True,
                )
            )
            n += 1
    db.add_all(docs)
    db.flush()
    db.add_all(chunks)
    db.flush()


def _near(i):  # cosine to e0 about 0.99
    v = pad(1.0)
    v[2 + (i % 400)] = 0.1
    return v


def _far(i):  # cosine to e0 about 0.1
    v = pad(0.1, 1.0)
    v[2 + (i % 400)] = 0.1
    return v


def _sweep(i):
    """Vectors fanned out from the query direction (0 to 85 degrees by insertion order), so the HNSW graph is
    one connected chain: iterative scan can walk from the nearest rows out to the farthest ones. Two separate
    clusters would be unreachable from each other, which no real catalogue is."""
    import math

    theta = math.radians(85.0 * i / 200)
    v = pad(math.cos(theta), math.sin(theta))
    v[2 + i] = 0.01
    return v


def test_ac_lec_11_index_names_and_ddl_shape():
    from app.services import embedding_indexes
    from app.services.embedding_settings import HOT_FILTERED_SOURCES, RECORD_KEEP_SET

    for model in (M3S, GEM):
        names = embedding_indexes.index_names(model)
        ddl = embedding_indexes.index_ddl(model)
        assert len(ddl) == 1 + len(HOT_FILTERED_SOURCES) == len(set(names.values()))
        for n in names.values():
            assert re.fullmatch(r"[a-z0-9_]{1,63}", n), n
            assert sum(n in d for d in ddl) == 1, n
        for d in ddl:
            assert d.startswith("CREATE INDEX CONCURRENTLY IF NOT EXISTS ")
            assert "USING hnsw (embedding vector_cosine_ops)" in d
            assert f"model_name = '{model}'" in d and "is_current" in d
        keep = [d for d in ddl if "source_type IN" in d]
        assert len(keep) == 1 and all(f"'{s}'" in keep[0] for s in RECORD_KEEP_SET)
        for s in HOT_FILTERED_SOURCES:
            assert sum(f"source_type = '{s}'" in d for d in ddl) == 1


@pytest.mark.serial_ddl
def test_ac_lec_10_search_current_orders_by_distance_and_uses_the_keep_set_index(db):
    from app.services import embedding_indexes

    _create_indexes(db)
    _seed_many(db, [("certificate", 40, _near), ("promotion", 20, _far)])
    db.execute(text("ANALYZE embedding_chunks"))
    # A 60-row table is cheaper to scan sequentially, so the planner is told not to: the question is
    # whether the query is SHAPED to match the partial index, not what a tiny table costs.
    db.execute(text("SET LOCAL enable_seqscan = off"))
    (statement, params), _hits = _captured_search_sql(
        db, lambda: EmbeddingReadService(db).search_current(pad(1.0), top_k=5)
    )
    assert re.search(r"ORDER BY\s+embedding_chunks\.embedding\s*<=>", statement), statement
    plan = _explain(db, statement, params)
    names = set(embedding_indexes.index_names(M3S).values())
    assert "Index Scan" in plan and any(n in plan for n in names), plan


@pytest.mark.serial_ddl
def test_ac_lec_11_attachment_filtered_read_uses_its_index_and_returns_five_of_five(db):
    from app.services import embedding_indexes

    _create_indexes(db)
    # 30% attachment, all far from the query; the 140 nearest chunks are other sources.
    _seed_many(db, [("certificate", 140, _near), ("attachment", 60, _far)])
    db.execute(text("ANALYZE embedding_chunks"))
    db.execute(text("SET LOCAL enable_seqscan = off"))  # tiny table; see the AC-LEC-10 test
    (statement, params), hits = _captured_search_sql(
        db, lambda: EmbeddingReadService(db).search_current(pad(1.0), top_k=5, source_type="attachment")
    )
    assert len(hits) == 5, f"filtered read returned {len(hits)} of 5 (HNSW post-filter starvation)"
    plan = _explain(db, statement, params)
    attach = [n for n in embedding_indexes.index_names(M3S).values() if "attachment" in n]
    assert attach and any(n in plan for n in attach), plan


@pytest.mark.serial_ddl
def test_ac_lec_11_non_hot_filtered_read_returns_five_of_five_by_iterative_scan(db):
    _create_indexes(db)
    # promotion is 30% of the rows and far from the query; the keep-set index alone would return none.
    _seed_many(db, [("certificate", 140, _sweep), ("promotion", 60, _sweep)])
    db.execute(text("ANALYZE embedding_chunks"))
    db.execute(text("SET LOCAL enable_seqscan = off"))  # tiny table; see the AC-LEC-10 test
    hits = EmbeddingReadService(db).search_current(pad(1.0), top_k=5, source_type="promotion")
    assert len(hits) == 5, f"filtered read returned {len(hits)} of 5"


# ================================================================== AC-LEC-12
def test_ac_lec_12_fuzzy_resolver_adds_a_vector_hit_only_above_the_floor(db, transport):
    from app.models.product import Product as P
    from app.services import fuzzy_resolver

    assert fuzzy_resolver.VECTOR_FLOOR_BY_MODEL == {M3S: 0.55, GEM: 0.70}
    near = _spec_product_with_chunk(db, "ZZT-LEC2-F-NEAR", pad(1.0, 0.2))  # cosine 0.98
    far = _spec_product_with_chunk(db, "ZZT-LEC2-F-FAR", pad(0.3, 1.0))  # cosine 0.29, under the floor
    _setting(db, embedding_records_search_model=M3S)
    transport(pad(1.0))
    clause, values = fuzzy_resolver.resolve_via_embedding_then_ilike(
        db, "zzt toilet", source_type="product_spec", ilike_columns=[P.product_name],
        canonical_model=P, canonical_fields=("product_code",),
    )
    assert clause is not None
    assert values == [near.product_code], f"far vector (below the floor) was added: {values}"
    assert far.product_code not in values
