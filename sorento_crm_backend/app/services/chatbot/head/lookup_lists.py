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
import threading
import time
from dataclasses import dataclass
from functools import lru_cache
from typing import TYPE_CHECKING, Any, Callable

from app.services.chatbot.head import candidates

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

MARKER = "== LOOKUP LISTS =="
HEADER_NOUN = {
    "category": "Category", "spec": "Spec", "file_type": "File type", "brand": "Brand",
    "promotion_kind": "Promotion kind", "salesperson": "Salesperson", "location": "Location",
    "sales_channel": "Sales channel", "customer": "Customer",
}
FLOOR_SPELLING = 0.5
#: The base meaning floor (the measured 3-large config); `shortlist` reads `FLOOR_MEANING_BY_LIST`.
FLOOR_MEANING = 0.5
#: Per list for text-embedding-3-small (free re-score of 26 Oct); any other list uses `_FLOOR_MEANING_OTHER`.
FLOOR_MEANING_BY_LIST = {
    "category": 0.55, "sales_channel": 0.55, "brand": 0.58, "spec": 0.55, "file_type": 0.59, "customer": 0.53,
}
_FLOOR_MEANING_OTHER = 0.55
TOP_K = {
    "category": 10, "spec": 10, "file_type": 5, "brand": 3, "promotion_kind": 3, "salesperson": 5, "location": 5,
    "sales_channel": 2, "customer": 5,
}
DEFAULT_ORDER = (
    "category", "spec", "file_type", "brand", "promotion_kind", "salesperson", "location", "sales_channel", "customer",
)

#: The word lists the v63 prompt carried (category translations, file type words), as row texts:
#: list -> row label (case aside) -> extra texts matched beside the row's own.
PROMPT_SYNONYMS: dict[str, dict[str, tuple[str, ...]]] = {
    "category": {
        "water tap": ("paip air", "kepala paip", "水龙头"),
        "water closet": ("tandas", "mangkuk tandas", "马桶"),
        "kitchen sink": ("sinki dapur", "厨房水槽"),
    },
    "file_type": {
        "photo": ("gambar", "foto", "image", "picture", "imej"),
        "image": ("imej", "gambar", "foto", "picture"),
        "video": ("videos",),
        "drawing": ("lukisan",),
        "technical drawing": ("lukisan teknikal", "lukisan", "cad", "blueprint"),
        "3d model": ("model 3d",),
        "installation guide": ("installation manual",),
        "certificate": ("sijil", "cert", "ikram"),
    },
}

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
_CUSTOMER_BLOCKERS = frozenset({"category", "brand", "sales_channel", "location"})
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
    # A piece that is exactly another list's word (category, brand, channel, location) feeds no customer row.
    other_words = {_fold(t) for r in rows if r.list_name in _CUSTOMER_BLOCKERS for t in r.texts} | set(brand_words)
    if "customer" in by_list:
        by_list["customer"] = [p for p in by_list["customer"] if p not in other_words]
    row_texts = sorted({t for r in rows for t in r.texts if _fold(t)})
    vec = _vectors(embed, [*usable, *row_texts])

    best: dict[str, dict[str, Hit]] = {}
    for row in rows:
        row_pieces = by_list.get(row.list_name) or []
        floor_meaning = FLOOR_MEANING_BY_LIST.get(row.list_name, _FLOOR_MEANING_OTHER)
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
                score = max(s if s >= FLOOR_SPELLING else 0.0, m if m >= floor_meaning else 0.0)
                if score > score_best:
                    piece_best, score_best = piece, score
        if spell_best >= FLOOR_SPELLING or mean_best >= floor_meaning:
            best.setdefault(row.list_name, {})[row.key] = Hit(row, piece_best, spell_best, mean_best)
    out: dict[str, list[Hit]] = {}
    for name, hits in best.items():
        ordered = sorted(hits.values(), key=lambda h: (-max(h.spelling, h.meaning), h.row.label))
        out[name] = ordered[: TOP_K.get(name, 10)]
    return out


def render(hits: dict[str, list[Hit]], order: tuple[str, ...] = DEFAULT_ORDER) -> list[str]:
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


def _with_synonyms(list_name: str, label: str, texts: tuple[str, ...]) -> tuple[str, ...]:
    extra = {k.casefold(): v for k, v in PROMPT_SYNONYMS.get(list_name, {}).items()}.get(label.casefold(), ())
    return tuple(dict.fromkeys([*texts, *extra]))


def _spec_rows(db: "Session", hidden: frozenset[str] = frozenset()) -> list[LookupRow]:
    """One row per registry value of an enum key that says something other than the product's type
    or brand (those are category rows and the brand list): label `<spec label> <value>`."""
    from app.services.product_spec_registry import (
        active_registry,
        display_spec_value,
        merged_allowed_values,
        merged_synonyms,
    )

    out: list[LookupRow] = []
    for row in active_registry(db):
        if (row.data_type or "").lower() != "enum" or row.spec_key in candidates.TYPE_KEYS | candidates.SKIP_KEYS or row.spec_key in hidden:
            continue
        synonyms = merged_synonyms(row)
        labels = dict(getattr(row, "value_labels", None) or {})
        for value in merged_allowed_values(row):
            display = display_spec_value(value, labels)
            texts = [str(value), display, *(synonyms.get(value) or [])]
            out.append(
                LookupRow(
                    "spec", f"{row.spec_key}={value}", f"{row.label} {display} ({row.spec_key}: {value})",
                    tuple(dict.fromkeys(str(t) for t in texts if t and _fold(str(t)))),
                )
            )
    return out


def _file_type_rows(db: "Session") -> list[LookupRow]:
    """Attachment types and certificate kinds (the sources `closed_lists_index._file_matches` reads)."""
    from app.services import chatbot_prompt_vars as pv

    aliases = pv._alias_words(db)
    out: list[LookupRow] = []
    for row in [*pv._file_type_rows(db), *pv._cert_kind_rows(db)]:
        name = str(row.get("type_name") or pv._item(row))
        texts = (name, pv._item(row), *pv._type_words(row, aliases))
        out.append(
            LookupRow(
                "file_type", pv._item(row) or name, name,
                _with_synonyms("file_type", name, tuple(dict.fromkeys(t for t in texts if t and _fold(t)))),
            )
        )
    return out


def _brand_rows(db: "Session") -> list[LookupRow]:
    """Active brands of the session's companies, labelled exactly as the `Known brands:` line spells them."""
    from app.services.chatbot import turn_runtime
    from app.services.chatbot.turn.context import known_brands_line

    out: list[LookupRow] = []
    seen: set[str] = set()
    for b in turn_runtime.active_brands(db):
        name = str(b.get("brand_name") or "").strip()
        line = known_brands_line([b])
        if not name or name in seen or not line:
            continue
        seen.add(name)
        texts = [name, b.get("brand_code"), *(b.get("aliases") or [])]
        out.append(
            LookupRow("brand", str(b.get("id") or name), line.removeprefix("Known brands: "),
                      tuple(dict.fromkeys(str(t) for t in texts if t and _fold(str(t)))))
        )
    return out


def _promotion_kind_rows(db: "Session") -> list[LookupRow]:
    from app.services.chatbot import turn_runtime

    return [
        LookupRow("promotion_kind", r["type_code"], f"{r['type_name']} ({r['type_code']})", (r["type_name"], r["type_code"]))
        for r in turn_runtime.promotion_kind_rows(db)
        if r.get("type_code") and r.get("type_name")
    ]


def _location_rows(db: "Session") -> list[LookupRow]:
    """Active warehouses of the session's companies: label `<name> (<code>)`."""
    from app.models.inventory import Warehouse

    out: list[LookupRow] = []
    for w in db.query(Warehouse).filter(Warehouse.is_active.is_(True)).order_by(Warehouse.warehouse_code).all():
        code = str(w.warehouse_code or "").strip()
        name = str(w.warehouse_name or "").strip()
        if code:
            out.append(LookupRow("location", str(w.id), f"{name} ({code})" if name else code, tuple(t for t in (name, code) if t)))
    return out


def _salesperson_rows(db: "Session") -> list[LookupRow]:
    """Active sales agents (the sales report's agent names, `reports/ask.py`): shared rows (no company)
    and the session's companies'. Label is the agent code."""
    from sqlalchemy import or_

    from app.models.base import get_company_scope
    from app.models.sales_agent import SalesAgent

    query = db.query(SalesAgent).filter(SalesAgent.is_active.is_(True))
    scope = get_company_scope(db)
    if isinstance(scope, frozenset):
        query = query.filter(or_(SalesAgent.company_id.is_(None), SalesAgent.company_id.in_(list(scope))))
    elif scope is not None:
        query = query.filter(SalesAgent.company_id.is_(None))
    out: list[LookupRow] = []
    for a in query.order_by(SalesAgent.sales_agent).all():
        code = str(a.sales_agent or "").strip()
        aliases = [x.strip() for x in str(a.aliases or "").split(",")]
        texts = [code, a.person_label, *aliases]
        if code:
            out.append(LookupRow("salesperson", str(a.id), code, tuple(dict.fromkeys(str(t) for t in texts if t and _fold(str(t))))))
    return out


def _customer_rows(db: "Session", only_ids: frozenset[str] | None) -> list[LookupRow]:
    """Active customers of the session's companies, labelled as the customer picker shows them
    (`customer_name`); `only_ids` narrows to a dealer contact's own linked customers."""
    from app.models.order import Customer

    query = db.query(Customer.id, Customer.customer_name).filter(Customer.is_active.is_(True))
    if only_ids is not None:
        query = query.filter(Customer.id.in_(list(only_ids)))
    return [
        LookupRow("customer", str(cid), name.strip(), (name.strip(),))
        for cid, name in query.order_by(Customer.customer_code).all()
        if name and name.strip() and _fold(name)
    ]


def load_rows(
    db: "Session", *, hidden_spec_keys: frozenset[str] = frozenset(), include_salespeople: bool = False,
    include_customers: bool = False, customer_ids: frozenset[str] | None = None,
) -> list[LookupRow]:
    """Categories (searchable and active, company-scoped by the session), class labels, product types,
    spec word values, file types and the sales channels."""
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
        texts = tuple(dict.fromkeys(str(t) for t in [c.category_name, c.category_code, c.class_label, *(c.search_synonyms or [])] if t and str(t).strip()))
        out.append(LookupRow("category", str(c.id), c.category_name, _with_synonyms("category", c.category_name, texts)))
        seen_labels.add(_fold(c.category_name))
    # Class labels and product types, as the parser's old `Product types:` line named them.
    for name in turn_runtime.product_type_names(db):
        key = _fold(name)
        if key and key not in seen_labels:
            seen_labels.add(key)
            out.append(LookupRow("category", "type:" + key, name, _with_synonyms("category", name, (name,))))
    out.extend(_spec_rows(db, hidden_spec_keys))
    out.extend(_file_type_rows(db))
    out.extend(_brand_rows(db))
    out.extend(_promotion_kind_rows(db))
    out.extend(_location_rows(db))
    if include_salespeople:
        out.extend(_salesperson_rows(db))
    if include_customers:
        out.extend(_customer_rows(db, customer_ids))
    out.extend(LookupRow("sales_channel", ch, ch, (ch,)) for ch in SALES_CHANNELS)
    return out


# ---------------------------------------------------------------------------- spec numbers

#: A length in the message: not glued to a letter or digit before it (a code), a unit after it.
_LENGTH_RE = re.compile(r"(?<![a-z0-9.])(\d+(?:\.\d+)?)\s*(mm|cm|m)(?![a-z0-9])")
_SIZE_RE = re.compile(r"(?<![a-z0-9.])(\d+(?:\.\d+)?)\s*x\s*(\d+(?:\.\d+)?)\s*(mm|cm|m)(?![a-z0-9])")
_TO_MM = {"mm": 1.0, "cm": 10.0, "m": 1000.0}


def _mm(number: str, unit: str) -> str:
    return f"{round(float(number) * _TO_MM[unit], 3):g}"


def normalise_number(text: str) -> str | None:
    """A length as exact millimetres: "200 mm" = "200mm" = "20 cm" = "0.2 m" -> "200mm"; a size
    "60 x 40 cm" -> "600x400mm"; None when the text holds no length."""
    folded = str(text or "").casefold().strip()
    size = _SIZE_RE.search(folded)
    if size:
        return f"{_mm(size.group(1), size.group(3))}x{_mm(size.group(2), size.group(3))}mm"
    one = _LENGTH_RE.search(folded)
    return f"{_mm(one.group(1), one.group(2))}mm" if one else None


def number_hits(message: str, db: "Session", *, hidden_spec_keys: frozenset[str] = frozenset()) -> list[Hit]:
    """Every numeric spec key whose stored values hold a length the message says, as exact
    millimetres in the key's own unit ("trap length 200mm"). No meaning score; nothing is offered
    for a number no key holds. A code that merely contains digits is never a length."""
    folded = str(message or "").casefold()
    found: list[tuple[str, str]] = []  # (piece, millimetres)
    for m in _LENGTH_RE.finditer(folded):
        found.append((m.group(0), _mm(m.group(1), m.group(2))))
    if not found:
        return []
    from sqlalchemy import case, func

    from app.models.product import Product, chat_searchable_products
    from app.models.product_spec import ProductSpecifications
    from app.services.product_spec_registry import active_registry
    from app.services.product_spec_search import membership_clause

    keys = [r for r in active_registry(db) if (r.data_type or "").lower() == "numeric" and (r.unit or "").lower() in _TO_MM and r.spec_key not in hidden_spec_keys]
    if not keys:
        return []
    asks: list[tuple[Any, str, str, float]] = []  # (registry row, piece, shown, value in the key's unit)
    for row in keys:
        unit = row.unit.lower()
        for piece, mm in dict.fromkeys(found):
            value = round(float(mm) / _TO_MM[unit], 6)
            asks.append((row, piece, f"{value:g}{unit}", value))
    columns = [
        func.coalesce(func.sum(case((membership_clause({row.spec_key: [value]}), 1), else_=0)), 0)
        for row, _p, _s, value in asks
    ]
    counts = (
        db.query(*columns)
        .select_from(ProductSpecifications)
        .join(Product, Product.id == ProductSpecifications.product_id)
        .filter(chat_searchable_products())
        .one()
    )
    out: list[Hit] = []
    for (row, piece, shown, value), held in zip(asks, counts):
        if int(held) > 0:
            label = f"{row.label} {shown} ({row.spec_key}: {value:g})"
            out.append(Hit(LookupRow("spec", f"{row.spec_key}={shown}", label, (label,)), _fold(piece), 1.0, 0.0))
    return sorted(out, key=lambda h: h.row.label)


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

    def fill(texts: list[str]) -> None:
        """The background warm-up: every uncached text in chunks, each chunk under its own timeout, no
        total deadline; chunks are kept as they complete."""
        todo = [t for t in dict.fromkeys(texts) if _key(t) not in _cache]
        client = OpenAIProvider(api_key)._client(timeout=EMBED_TIMEOUT, max_retries=0)
        for i in range(0, len(todo), EMBED_CHUNK):
            chunk = todo[i : i + EMBED_CHUNK]
            resp = client.embeddings.create(model=EMBED_MODEL, input=chunk)
            for t, item in zip(chunk, resp.data):
                _cache[_key(t)] = list(item.embedding)

    embed.fill = fill  # type: ignore[attr-defined]
    embed.needs_warm = True  # type: ignore[attr-defined]
    embed.is_cached = lambda texts: all(_key(t) in _cache for t in texts)  # type: ignore[attr-defined]
    return embed


_warm_lock = threading.Lock()


def row_texts(rows: list[LookupRow]) -> list[str]:
    return sorted({t for r in rows for t in r.texts if _fold(t)})


def warm(rows: list[LookupRow], embed: Embedder | None) -> None:
    """Embed every row text on a background thread so a cold cache never blocks a turn. One warm-up
    at a time; a failure is swallowed (the next turn tries again, the turn itself is spelling only)."""
    if embed is None or not rows or not _warm_lock.acquire(blocking=False):
        return
    texts = row_texts(rows)

    def run() -> None:
        try:
            getattr(embed, "fill", embed)(texts)
        except Exception:  # noqa: BLE001 - advisory
            pass
        finally:
            _warm_lock.release()

    threading.Thread(target=run, name="lookup-lists-warm", daemon=True).start()


def usable_embedder(rows: list[LookupRow], embed: Embedder | None) -> Embedder | None:
    """`embed` for the turn: the provider embedder only once every row text is cached (else None, spelling
    only, while `warm` fills the cache); any other embedder as given."""
    if embed is not None and getattr(embed, "needs_warm", False) and not embed.is_cached(row_texts(rows)):  # type: ignore[attr-defined]
        return None
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
