"""Partial HNSW indexes on `embedding_chunks`, one set per embedding model (LOOKUP-EMBED-CENTRAL, AC-LEC-10/11).

A vector index serves a query only when the query repeats the index's WHERE clause literally, so the
predicate text lives here and `EmbeddingReadService.search_current` reuses it.
"""
from __future__ import annotations

import re

from app.services.embedding_settings import HOT_FILTERED_SOURCES, RECORD_KEEP_SET


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
