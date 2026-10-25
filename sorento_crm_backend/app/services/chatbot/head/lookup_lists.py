"""The per-turn lookup lists the parser picks from (CHAT-SLIM-INDEX S1).

Code only SHORTLISTS. For every 1-4 word piece of the current message, each list keeps the rows
it spells near (trigram similarity, as `head/candidates.py`) or means near (cosine of the
embedding vectors), and prints one self-describing block per list. The parser picks one row or
none; nothing here decides what a word means. A version carries the `== LOOKUP LISTS ==` line
(`gate_on`) to receive the blocks, and then loses the per-turn list lines they replace.

Embedding is advisory: no embedder, a failure or the timeout leaves meaning at 0.0 for every
row (spelling only) and the turn goes on. Product codes and document numbers are never
offered (their exact path runs after the parser).
"""
from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass
from functools import lru_cache
from typing import TYPE_CHECKING, Any, Callable

from app.services.chatbot.head import candidates

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

MARKER = "== LOOKUP LISTS =="
HEADER_NOUN = {"category": "Category", "sales_channel": "Sales channel"}
FLOOR_SPELLING = 0.5
FLOOR_MEANING = 0.5
TOP_K = {"category": 10, "sales_channel": 2}

EMBED_MODEL = "text-embedding-3-small"
#: One request's timeout, and the whole embed step's budget, in seconds.
EMBED_TIMEOUT = 3.0
EMBED_CHUNK = 500
#: Row-text vectors kept per process; cleared whole when it grows past this.
_CACHE_CAP = 20000

Embedder = Callable[[list[str]], list[list[float]]]


class _UseProvider:
    """Sentinel: the production default, an OpenAI embedder built per turn (`embedder`)."""

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "USE_PROVIDER"


USE_PROVIDER = _UseProvider()
#: `None` means spelling only; tests set a callable or None.
EMBED: Any = USE_PROVIDER

_LINE_RE = re.compile(r"^[ \t]*" + re.escape(MARKER) + r"[ \t]*$", re.MULTILINE)
_WORD_RE = re.compile(r"[^\W_]+")
_CODE_WORD_RE = re.compile(r"\d{3,}|(?=[a-z0-9]*\d)(?=[a-z0-9]*[a-z])[a-z0-9]{5,}")


@dataclass(frozen=True)
class LookupRow:
    list_name: str
    key: str
    #: What the block prints.
    label: str
    #: The strings matched (name, code, synonyms, class label).
    texts: tuple[str, ...]


@dataclass(frozen=True)
class Hit:
    row: LookupRow
    piece: str
    spelling: float
    meaning: float


def gate_on(template: str | None) -> bool:
    """True when the RAW template carries the marker as its own line."""
    return bool(template) and _LINE_RE.search(template) is not None


def header(list_name: str) -> str:
    return f"{HEADER_NOUN[list_name]} candidates (pick one only if the message means it):"


def _fold(text: str) -> str:
    """`candidates._phrase`, but any script: a Chinese word survives the fold (spelling still
    reads ASCII trigrams only, so such a word is placed by meaning or exact equality)."""
    return " ".join(_WORD_RE.findall(str(text).casefold()))


def pieces(message: str, max_words: int = 4) -> list[str]:
    """Every 1..`max_words` consecutive-word piece of the folded message, in message order, once each."""
    words = _fold(message).split()
    out: list[str] = []
    seen: set[str] = set()
    for size in range(1, max_words + 1):
        for i in range(len(words) - size + 1):
            piece = " ".join(words[i : i + size])
            if piece not in seen:
                seen.add(piece)
                out.append(piece)
    return out


def _code_like(piece: str) -> bool:
    return any(_CODE_WORD_RE.fullmatch(w) for w in piece.split())


@lru_cache(maxsize=8192)
def _grams(text: str) -> frozenset[str]:
    return candidates.trigrams(text)


def _spelling(piece: str, text: str) -> float:
    folded = _fold(text)
    if not folded:
        return 0.0
    if piece == folded:
        return 1.0
    return candidates.similarity(_grams(piece), _grams(folded))


def _vectors(embed: Embedder | None, texts: list[str]):
    """{text: unit vector} for `texts` in ONE embedder call, or {} when there is no embedder / it fails."""
    if embed is None or not texts:
        return {}
    try:
        import numpy as np

        raw = embed(texts)
        mat = np.asarray(raw, dtype=float)
        if mat.ndim != 2 or mat.shape[0] != len(texts):
            return {}
        norms = np.linalg.norm(mat, axis=1)
        norms[norms == 0] = 1.0
        mat = mat / norms[:, None]
        return {t: mat[i] for i, t in enumerate(texts)}
    except Exception:  # noqa: BLE001 - advisory: spelling only
        return {}


def shortlist(
    message: str,
    rows: list[LookupRow],
    embed: Embedder | None,
    *,
    brand_words: frozenset[str] = frozenset(),
) -> dict[str, list[Hit]]:
    """Per list, the rows the message spells or means near, best first, cut to `TOP_K`."""
    usable = [p for p in pieces(message) if not _code_like(p)]
    if not usable or not rows:
        return {}
    # One-span-one-list: a piece that holds a brand word feeds no category row.
    by_list: dict[str, list[str]] = {}
    for name in {r.list_name for r in rows}:
        by_list[name] = [
            p for p in usable if not (name == "category" and any(f" {b} " in f" {p} " for b in brand_words))
        ]
    row_texts = sorted({t for r in rows for t in r.texts if _fold(t)})
    vec = _vectors(embed, [*usable, *row_texts])

    best: dict[str, dict[str, Hit]] = {}
    for row in rows:
        row_pieces = by_list.get(row.list_name) or []
        spell_best, mean_best, piece_best, score_best = 0.0, 0.0, "", -1.0
        for piece in row_pieces:
            pv = vec.get(piece)
            for text in row.texts:
                s = _spelling(piece, text)
                m = 0.0
                tv = vec.get(text)
                if pv is not None and tv is not None:
                    m = max(0.0, float(pv @ tv))
                spell_best, mean_best = max(spell_best, s), max(mean_best, m)
                score = max(s if s >= FLOOR_SPELLING else 0.0, m if m >= FLOOR_MEANING else 0.0)
                if score > score_best:
                    piece_best, score_best = piece, score
        if spell_best >= FLOOR_SPELLING or mean_best >= FLOOR_MEANING:
            best.setdefault(row.list_name, {})[row.key] = Hit(row, piece_best, spell_best, mean_best)
    out: dict[str, list[Hit]] = {}
    for name, hits in best.items():
        ordered = sorted(hits.values(), key=lambda h: (-max(h.spelling, h.meaning), h.row.label))
        out[name] = ordered[: TOP_K.get(name, 10)]
    return out


def render(hits: dict[str, list[Hit]], order: tuple[str, ...] = ("category", "sales_channel")) -> list[str]:
    """One block per list with hits: the header, then `- <label>` once per label."""
    lines: list[str] = []
    for name in order:
        labels: list[str] = []
        for h in hits.get(name) or []:
            if h.row.label not in labels:
                labels.append(h.row.label)
        if labels:
            lines.append(header(name))
            lines.extend(f"- {label}" for label in labels)
    return lines


def load_rows(db: "Session") -> list[LookupRow]:
    """Categories (searchable and active, company-scoped by the session), class labels, product types,
    and the sales channels."""
    from app.models.product import ProductCategory
    from app.services.chatbot import turn_runtime
    from app.services.reports.ask import SALES_CHANNELS

    out: list[LookupRow] = []
    seen_labels: set[str] = set()
    cats = (
        db.query(ProductCategory)
        .filter(ProductCategory.is_searchable.isnot(False), ProductCategory.is_active.is_(True))
        .order_by(ProductCategory.category_name)
        .all()
    )
    for c in cats:
        texts = [c.category_name, c.category_code, c.class_label, *(c.search_synonyms or [])]
        out.append(
            LookupRow("category", str(c.id), c.category_name, tuple(dict.fromkeys(str(t) for t in texts if t and str(t).strip())))
        )
        seen_labels.add(_fold(c.category_name))
    # Class labels and product types, as the parser's old `Product types:` line named them.
    for name in turn_runtime.product_type_names(db):
        key = _fold(name)
        if key and key not in seen_labels:
            seen_labels.add(key)
            out.append(LookupRow("category", "type:" + key, name, (name,)))
    out.extend(LookupRow("sales_channel", ch, ch, (ch,)) for ch in SALES_CHANNELS)
    return out


def brand_words(db: "Session") -> frozenset[str]:
    """Folded brand names, codes and aliases: the words that are a brand and never a category."""
    from app.services.chatbot import turn_runtime

    words: set[str] = set()
    for b in turn_runtime.active_brands(db):
        for w in (b.get("brand_name"), b.get("brand_code"), *(b.get("aliases") or [])):
            folded = _fold(w) if w else ""
            if folded:
                words.add(folded)
    return frozenset(words)


# ---------------------------------------------------------------------------- production embedder

_cache: dict[tuple[str, str], list[float]] = {}


def _key(text: str) -> tuple[str, str]:
    return (EMBED_MODEL, hashlib.sha1(text.encode()).hexdigest())


def provider_embedder(api_key: str) -> Embedder:
    """OpenAI `text-embedding-3-small`: vectors cached per process by (model, sha1 of text), the
    uncached texts of a call sent in chunks inside one `EMBED_TIMEOUT` budget."""
    from app.services.llm_provider import OpenAIProvider

    def embed(texts: list[str]) -> list[list[float]]:
        deadline = time.monotonic() + EMBED_TIMEOUT
        todo = [t for t in dict.fromkeys(texts) if _key(t) not in _cache]
        if len(_cache) + len(todo) > _CACHE_CAP:
            _cache.clear()
            todo = list(dict.fromkeys(texts))
        client = OpenAIProvider(api_key)._client(timeout=EMBED_TIMEOUT, max_retries=0)
        for i in range(0, len(todo), EMBED_CHUNK):
            if time.monotonic() > deadline:
                raise TimeoutError("lookup list embedding budget spent")
            chunk = todo[i : i + EMBED_CHUNK]
            resp = client.embeddings.create(model=EMBED_MODEL, input=chunk)
            for t, item in zip(chunk, resp.data):
                _cache[_key(t)] = list(item.embedding)
        return [_cache[_key(t)] for t in texts]

    return embed


def embedder(db: "Session") -> Embedder | None:
    """`EMBED` as the engine uses it: a set value (a callable or None) wins; the default builds the
    provider embedder from the assistant config's OpenAI key, or None (spelling only) with no key."""
    if EMBED is not USE_PROVIDER:
        return EMBED
    from app.services import llm_provider
    from app.services.ai_assistant_service import AIAssistantConfigService

    key = llm_provider.resolve_api_key(AIAssistantConfigService(db).get(), "openai")
    return provider_embedder(key) if key else None
