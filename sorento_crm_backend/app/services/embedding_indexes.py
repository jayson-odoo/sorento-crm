"""Partial HNSW indexes on `embedding_chunks`, one set per embedding model (LOOKUP-EMBED-CENTRAL, AC-LEC-10/11).

A vector index serves a query only when the query repeats the index's WHERE clause literally, so the
predicate text lives here and `EmbeddingReadService.search_current` reuses it.
"""
from __future__ import annotations

import logging
import re

from sqlalchemy import text

from app.services.embedding_settings import HOT_FILTERED_SOURCES, RECORD_KEEP_SET

logger = logging.getLogger(__name__)

# `hnsw.iterative_scan` exists only from pgvector 0.8; read the extension version once per process.
_ITERATIVE_SCAN_SUPPORTED: bool | None = None


def _version_supports_iterative_scan(version) -> bool:
    try:
        major, minor = (int(part) for part in str(version).split(".")[:2])
    except ValueError:
        return False
    return (major, minor) >= (0, 8)


def set_iterative_scan(db) -> None:
    """Let a post-filtered HNSW read keep scanning until enough rows survive, on servers that support it.

    On pgvector < 0.8 the SET would raise and abort the transaction, so it is skipped and the read runs
    without the iterative scan (as it did before LOOKUP-EMBED-CENTRAL)."""
    global _ITERATIVE_SCAN_SUPPORTED
    if _ITERATIVE_SCAN_SUPPORTED is None:
        version = db.execute(text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")).scalar()
        _ITERATIVE_SCAN_SUPPORTED = _version_supports_iterative_scan(version)
        if not _ITERATIVE_SCAN_SUPPORTED:
            logger.warning(
                "pgvector %s does not support hnsw.iterative_scan (needs >= 0.8); filtered vector reads run without it",
                version,
            )
    if _ITERATIVE_SCAN_SUPPORTED:
        db.execute(text("SET LOCAL hnsw.iterative_scan = relaxed_order"))


def _quote(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _slug(model: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", model.lower()).strip("_")


def keep_set_sql() -> str:
    return ", ".join(_quote(s) for s in sorted(RECORD_KEEP_SET))


def base_predicate(model: str) -> str:
    return f"model_name = {_quote(model)} AND is_current"


def index_names(model: str) -> dict[str, str]:
    slug = _slug(model)
    names = {"keep": f"ix_embchunk_hnsw_{slug}_keep"}
    for source in HOT_FILTERED_SOURCES:
        names[source] = f"ix_embchunk_hnsw_{slug}_{source}"
    return names


def online_indexes(model: str) -> tuple[tuple[str, str, str], ...]:
    """(table, name, columns) per index, the shape `app/utils/online_index.py` builds; `index_ddl` renders the same."""
    names = index_names(model)
    base = base_predicate(model)
    out = [
        (
            "embedding_chunks",
            names["keep"],
            f"USING hnsw (embedding vector_cosine_ops) WHERE {base} AND source_type IN ({keep_set_sql()})",
        )
    ]
    for source in HOT_FILTERED_SOURCES:
        out.append(
            (
                "embedding_chunks",
                names[source],
                f"USING hnsw (embedding vector_cosine_ops) WHERE {base} AND source_type = {_quote(source)}",
            )
        )
    return tuple(out)


def index_ddl(model: str) -> list[str]:
    return [
        f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {name} ON {table} {columns}"
        for table, name, columns in online_indexes(model)
    ]


# The set `lec_0002_embedding_indexes` and `scripts/ensure_goods_chain_indexes.py` build.
MIGRATION_INDEXES = online_indexes("text-embedding-3-small")
