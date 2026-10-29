"""The Embeddings screen's view of the chatbot's lookup words (LOOKUP-EMBED-CENTRAL, AC-LEC-20, 21).

`words_of_list` lists a list's rows with each word's home and whether it has a stored vector; `try_phrase` runs a
phrase through the live span resolver and shows, per candidate row, what each signal saw.
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.services.chatbot.head import candidates, list_resolver, lookup_lists as ll, lookup_word_store

logger = logging.getLogger(__name__)

LIST_NAMES = (
    "category", "spec", "file_type", "brand", "promotion_kind", "location", "salesperson", "customer", "sales_channel",
)
#: The data each list is read from, as the screen names it.
LIST_SOURCES = {
    "category": "Categories", "spec": "Spec registry", "file_type": "Attachment types", "brand": "Brands",
    "promotion_kind": "Promotion types", "location": "Warehouses", "salesperson": "Sales agents",
    "customer": "Customers", "sales_channel": "Sales channels",
}
TRY_LIMIT = 8


def _rows(db: Session) -> list[ll.LookupRow]:
    return ll.load_rows(db, include_salespeople=True, include_customers=True, customer_ids=None)


def _stored_texts(db: Session, model: str) -> set[str]:
    from app.models.embeddings import EmbeddingChunk

    rows = (
        db.query(EmbeddingChunk.chunk_text)
        .filter(
            EmbeddingChunk.source_type == lookup_word_store.LOOKUP_SOURCE,
            EmbeddingChunk.model_name == model,
            EmbeddingChunk.is_current.is_(True),
        )
        .distinct()
        .all()
    )
    return {t for (t,) in rows}


def _home(row: ll.LookupRow, text: str) -> str | None:
    if not row.homes:
        return None
    try:
        return row.homes[row.texts.index(text)]
    except (ValueError, IndexError):
        return None


def words_of_list(db: Session, list_name: str) -> dict[str, Any]:
    from app.services.embedding_settings import resolve_embedder

    model = resolve_embedder(db)[1]
    stored = _stored_texts(db, model)
    rows = []
    for row in _rows(db):
        if row.list_name != list_name:
            continue
        rows.append(
            {
                "key": row.key,
                "label": row.label,
                "source": LIST_SOURCES.get(list_name, list_name),
                "group": row.group,
                "words": [
                    {"text": t, "home": _home(row, t), "has_vector": t in stored} for t in row.texts
                ],
            }
        )
    return {"list": list_name, "rows": rows}


def _best_text(row: ll.LookupRow, scores: dict[str, float]) -> dict[str, Any]:
    if not scores:
        return {"score": 0.0, "text": None, "home": None}
    text, score = max(scores.items(), key=lambda kv: kv[1])
    return {"score": round(float(score), 4), "text": text, "home": _home(row, text)}


def try_phrase(db: Session, phrase: str) -> dict[str, Any]:
    from app.services.embedding_settings import resolve_embedder

    model = resolve_embedder(db)[1]
    rows = _rows(db)
    try:
        lookup_word_store.load_lookup_vectors(db, model)
    except Exception:  # noqa: BLE001 - the embedder below covers what is not stored
        logger.warning("lookup try: stored vectors not loaded", exc_info=True)
    embed = ll.embedder(db)
    span = list_resolver.Span(phrase)
    verdict = list_resolver.resolve([span], rows, embed=embed)[0].status

    folded = ll._fold(phrase)
    grams = candidates.trigrams(folded)
    indexes = list_resolver._prepare(rows)
    meaning = None
    if embed is not None and indexes:
        texts = sorted({t[1] for ix in indexes.values() for t in ix.texts})
        meaning = ll._meaning(embed, [phrase], texts, any_model=True)

    pool: list[tuple[bool, float, dict[str, Any]]] = []
    for name, index in indexes.items():
        floors = {**list_resolver.FLOORS.get(name, list_resolver._FLOORS_OTHER)}
        floors["meaning"] = list_resolver._meaning_floor(embed, name)
        scored = list_resolver._score_list(index, folded, grams)
        per_row_spell: dict[int, dict[str, float]] = {}
        per_row_vec: dict[int, dict[str, float]] = {}
        for i, text, f, g, _w in index.texts:
            spell = 1.0 if f == folded else candidates.similarity(grams, g)
            if spell > 0:
                per_row_spell.setdefault(i, {})[text] = spell
            if meaning is not None:
                pidx, tidx, sim = meaning
                per_row_vec.setdefault(i, {})[text] = float(sim[pidx[phrase], tidx[text]])
        for i, row in enumerate(index.rows):
            s = scored.get(i)
            spell = s.spell if s else 0.0
            partial = s.partial if s else 0.0
            vec = per_row_vec.get(i, {})
            best_vec = max(vec.values()) if vec else 0.0
            if floors["meaning"] > 1.0:
                best_vec = 0.0
            if not (spell > 0 or partial > 0 or best_vec > 0):
                continue
            passed = spell >= floors["spell"] or partial >= floors["partial"] or best_vec >= floors["meaning"]
            signals = (
                ("exact" if s and s.exact else "spell", spell),
                ("partial", partial if partial >= floors["partial"] else 0.0),
                ("meaning", best_vec),
            )
            signal, score = max(signals, key=lambda x: x[1])
            pool.append(
                (
                    passed,
                    score,
                    {
                        "list": name,
                        "key": row.key,
                        "label": row.label,
                        "spelling": _best_text(row, per_row_spell.get(i, {})),
                        "vector": _best_text(row, vec) if meaning is not None else None,
                        "partial": round(float(partial), 4),
                        "floors": {k: round(float(v), 4) for k, v in floors.items()},
                        "passed": bool(passed),
                        "signal": signal,
                    },
                )
            )
    pool.sort(key=lambda k: (not k[0], -k[1]))
    return {"verdict": verdict, "candidates": [c for _p, _s, c in pool[:TRY_LIMIT]]}
