"""The lookup lists' words in the embedding store (LOOKUP-EMBED-CENTRAL, AC-LEC-15..17).

One `embedding_documents` row per lookup row (`source_type = 'lookup_word'`, `source_id = '<list>:<row key>'`) and one
chunk per text of that row. The in-process cache of the chatbot's lookup lists is loaded from here, so a process start
needs no provider call; record readers never read this source (it is not in `RECORD_KEEP_SET`).
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.models.embeddings import EmbeddingChunk, EmbeddingDocument

logger = logging.getLogger(__name__)

LOOKUP_SOURCE = "lookup_word"
EMBED_BATCH = 100
_IN_CHUNK = 1000


@dataclass
class SyncResult:
    created: int = 0
    updated: int = 0
    retired: int = 0
    embedded: int = 0


def _source_id(list_name: str, key) -> str:
    sid = f"{list_name}:{key}"
    if len(sid) > 128:  # the column is 128 wide; a long spec key keeps a stable id through its hash
        sid = f"{list_name}:{hashlib.sha1(str(key).encode()).hexdigest()}"
    return sid


def _hash(texts) -> str:
    return hashlib.sha256("\n".join(texts).encode("utf-8")).hexdigest()


def _provider(model: str) -> str:
    from app.services.embedding_settings import provider_for_model

    return provider_for_model(model)


def _chunk(doc_id: str, source_id: str, source_hash: str, model: str, index: int, text: str, vector) -> EmbeddingChunk:
    return EmbeddingChunk(
        document_id=doc_id,
        source_type=LOOKUP_SOURCE,
        source_id=source_id,
        chunk_index=index,
        chunk_text=text,
        chunk_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        embedding=list(vector),
        model_name=model,
        model_version=settings.embedding_model_version,
        embedding_provider=_provider(model),
        source_hash=source_hash,
        company_id=None,
        is_current=True,
    )


def _current_state(db: Session, model: str):
    """doc id -> {chunk text -> chunk index} and doc id -> next free chunk index, for current chunks of `model`."""
    texts: dict[str, dict[str, int]] = {}
    rows = (
        db.query(EmbeddingChunk.document_id, EmbeddingChunk.chunk_text, EmbeddingChunk.chunk_index)
        .filter(
            EmbeddingChunk.source_type == LOOKUP_SOURCE,
            EmbeddingChunk.model_name == model,
            EmbeddingChunk.model_version == settings.embedding_model_version,
            EmbeddingChunk.is_current.is_(True),
        )
        .all()
    )
    for doc_id, text, index in rows:
        texts.setdefault(str(doc_id), {})[text] = index
    return texts


def _add_chunks(db: Session, model: str, vectors: dict, docs: list) -> int:
    """For every doc in `docs`, a current chunk of `model` for each of its texts that has a vector in `vectors`
    and no current chunk yet. Returns the chunks written."""
    state = _current_state(db, model)
    written = 0
    for doc in docs:
        have = state.get(str(doc.id), {})
        nxt = (max(have.values()) + 1) if have else 0
        for text in dict.fromkeys(t for t in (doc.body_text or "").split("\n") if t):
            if text in have or text not in vectors:
                continue
            db.add(_chunk(doc.id, doc.source_id, doc.source_hash, model, nxt, text, vectors[text]))
            nxt += 1
            written += 1
    if written:
        db.flush()
    return written


def _stored_vectors(db: Session, model: str, texts: set[str]) -> dict:
    """text -> vector for `texts` already embedded for `model` in any current lookup_word chunk."""
    found: dict = {}
    pending = sorted(texts)
    for i in range(0, len(pending), _IN_CHUNK):
        part = pending[i : i + _IN_CHUNK]
        rows = (
            db.query(EmbeddingChunk.chunk_text, EmbeddingChunk.embedding)
            .filter(
                EmbeddingChunk.source_type == LOOKUP_SOURCE,
                EmbeddingChunk.model_name == model,
                EmbeddingChunk.is_current.is_(True),
                EmbeddingChunk.chunk_text.in_(part),
            )
            .distinct(EmbeddingChunk.chunk_text)
            .all()
        )
        for text, vector in rows:
            found[text] = vector
    return found


def sync_lookup_words(db: Session, *, model: str | None = None, embed: bool = True) -> SyncResult:
    """Bring the `lookup_word` documents in line with the lookup rows (widest visibility: all companies, salespeople,
    customers, spec rows), then give every active document a chunk for each text that has a vector for `model`.
    A text already embedded for `model` is copied; only new texts call the provider. The caller commits."""
    from app.models.base import get_company_scope, set_company_scope
    from app.services.chatbot.head import lookup_lists as ll
    from app.services.embedding_settings import embed_for_model, resolve_embedder

    model = model or resolve_embedder(db)[1]
    result = SyncResult()
    scope = get_company_scope(db)
    set_company_scope(db, None)
    try:
        rows = ll.load_rows(db, include_salespeople=True, include_customers=True, customer_ids=None)
    finally:
        set_company_scope(db, scope)

    existing = {d.source_id: d for d in db.query(EmbeddingDocument).filter(EmbeddingDocument.source_type == LOOKUP_SOURCE)}
    seen: set[str] = set()
    changed_docs: list = []
    for row in rows:
        texts = [t for t in row.texts if t]
        sid = _source_id(row.list_name, row.key)
        if sid in seen:
            continue
        seen.add(sid)
        digest = _hash(texts)
        body = "\n".join(texts)
        doc = existing.get(sid)
        if doc is None:
            db.add(
                EmbeddingDocument(
                    source_type=LOOKUP_SOURCE, source_id=sid, source_key=str(row.key)[:255], title=row.label,
                    body_text=body, metadata_json={}, visibility_scope="internal", source_hash=digest,
                    company_id=None, is_active=True,
                )
            )
            result.created += 1
        elif doc.source_hash != digest or doc.title != row.label or not doc.is_active:
            doc.title, doc.body_text, doc.source_hash, doc.is_active = row.label, body, digest, True
            changed_docs.append(doc)
            result.updated += 1
    db.flush()
    existing = {d.source_id: d for d in db.query(EmbeddingDocument).filter(EmbeddingDocument.source_type == LOOKUP_SOURCE)}

    # Documents of rows that no longer exist go dark; their chunks stop being current.
    retired_ids = [d.id for sid, d in existing.items() if sid not in seen and d.is_active]
    if retired_ids:
        for d in existing.values():
            if d.id in retired_ids:
                d.is_active = False
        (
            db.query(EmbeddingChunk)
            .filter(EmbeddingChunk.document_id.in_(retired_ids), EmbeddingChunk.is_current.is_(True))
            .update({EmbeddingChunk.is_current: False, EmbeddingChunk.superseded_at: func.now()}, synchronize_session=False)
        )
        result.retired = len(retired_ids)

    # A changed document drops the chunks of texts it no longer has.
    for doc in changed_docs:
        keep = set((doc.body_text or "").split("\n"))
        stale = (
            db.query(EmbeddingChunk)
            .filter(
                EmbeddingChunk.document_id == doc.id,
                EmbeddingChunk.model_name == model,
                EmbeddingChunk.is_current.is_(True),
            )
            .all()
        )
        for chunk in stale:
            if chunk.chunk_text not in keep:
                chunk.is_current = False
                chunk.superseded_at = func.now()
    db.flush()

    active = [d for d in existing.values() if d.is_active]
    if embed:
        state = _current_state(db, model)
        needed: set[str] = set()
        for doc in active:
            have = state.get(str(doc.id), {})
            needed.update(t for t in (doc.body_text or "").split("\n") if t and t not in have)
        vectors = _stored_vectors(db, model, needed)
        todo = sorted(needed - set(vectors))
        for i in range(0, len(todo), EMBED_BATCH):
            part = todo[i : i + EMBED_BATCH]
            try:
                fresh = embed_for_model(db, part, model)
            except Exception:  # noqa: BLE001 - the next sync picks the rest up
                logger.warning("lookup word sync: embed of %d texts failed", len(part), exc_info=True)
                break
            vectors.update(zip(part, fresh))
            result.embedded += len(part)
        if vectors:
            _add_chunks(db, model, vectors, active)
    db.flush()
    return result


def load_lookup_vectors(db: Session, model: str) -> int:
    """Load the current `lookup_word` chunks of `model` into the lookup lists' process cache (one SELECT, no
    provider call). Returns the vectors loaded."""
    import numpy as np

    from app.services.chatbot.head import lookup_lists as ll

    rows = (
        db.query(EmbeddingChunk.chunk_text, EmbeddingChunk.embedding)
        .filter(
            EmbeddingChunk.source_type == LOOKUP_SOURCE,
            EmbeddingChunk.model_name == model,
            EmbeddingChunk.is_current.is_(True),
        )
        .all()
    )
    if not rows:
        return 0
    unit = ll._unit_rows(np.stack([np.asarray(v, dtype=np.float32) for _t, v in rows]))
    with ll._store_lock:
        if len(ll._cache) + len(rows) > ll._CACHE_CAP:
            ll._cache.clear()
            ll._matrices.clear()
        loaded = 0
        for (text, _v), vec in zip(rows, unit):
            key = ll._key(text, model)
            if key not in ll._cache:
                ll._cache[key] = vec
                loaded += 1
    return loaded


def write_back(db: Session, model: str, vectors: dict) -> int:
    """A turn's freshly embedded row texts become chunks of every active `lookup_word` document whose texts contain
    them (and that has no current chunk of the text for `model`). Returns the chunks written; the caller commits."""
    if not vectors:
        return 0
    docs = (
        db.query(EmbeddingDocument)
        .filter(EmbeddingDocument.source_type == LOOKUP_SOURCE, EmbeddingDocument.is_active.is_(True))
        .all()
    )
    return _add_chunks(db, model, vectors, docs)
