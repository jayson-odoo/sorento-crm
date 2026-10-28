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

import fcntl
import hashlib
import logging
import os
import random
import re
import tempfile
import threading
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable

from app.services.chatbot.head import candidates
from app.services.chatbot_lookup_edits import MARKER, SPAN_MARKER

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

HEADER_NOUN = {
    "category": "Category", "spec": "Spec", "file_type": "File type", "brand": "Brand",
    "promotion_kind": "Promotion kind", "salesperson": "Salesperson", "location": "Location",
    "sales_channel": "Sales channel", "customer": "Customer",
}
FLOOR_SPELLING = 0.5
#: ENTITY-EXTRACT-MATCH S2 V2: on the span path a row the message spells at least this well is offered even when no
#: span named it (a misspelling the span model passed over); looser spellings and meaning-only hits are not.
NEAR_EXACT_SPELLING = 0.95
#: The base meaning floor (the measured 3-large config); `shortlist` reads `FLOOR_MEANING_BY_LIST`.
FLOOR_MEANING = 0.5
#: Per list for text-embedding-3-small (free re-score of 26 Oct); any other list uses `_FLOOR_MEANING_OTHER`.
FLOOR_MEANING_BY_LIST = {
    "category": 0.55, "sales_channel": 0.55, "brand": 0.58, "spec": 0.55, "file_type": 0.59, "customer": 0.53,
}
_FLOOR_MEANING_OTHER = 0.55
#: A message is read for its first words only (CPU bound).
MAX_MESSAGE_WORDS = 40
#: Distinct quantities one message may look up in the spec values.
MAX_NUMBER_ASKS = 3
#: A printed label is one line of at most this many characters.
MAX_LABEL_CHARS = 120
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
#: The prompt-registry key whose production label (provider, model) picks the lookup embedder.
EMBEDDER_PROMPT_KEY = "chatbot_lookup_embedder"
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

#: CHAT-V66-REGRESSIONS: the State subject keys whose values a list holds (`chat_state._subject`), so a value the
#: conversation already settled stays nameable on a turn whose own words do not repeat it (v63 listed every brand,
#: location, salesperson and channel on every turn).
HELD_SUBJECT_LISTS = {
    "brand": "brand", "warehouse": "location", "customer": "customer", "channel": "sales_channel",
    "category": "category", "salesperson": "salesperson", "attachment_type": "file_type",
}

_LINE_RE = re.compile(r"^[ \t]*" + re.escape(MARKER) + r"[ \t]*$", re.MULTILINE)
_SPAN_LINE_RE = re.compile(r"^[ \t]*" + re.escape(SPAN_MARKER) + r"[ \t]*$", re.MULTILINE)
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
    #: EEM-CATEGORY-PICK: a category row's class (`product_class_signal.category_class`); a "type:" row is its own.
    group: str | None = None
    #: DIMENSION-ANY: a number line offered for a dimension no product holds at that value is kept only beside a
    #: Category row whose products carry the key (these are those rows' keys); None is always kept.
    scope: frozenset[str] | None = None


@dataclass(frozen=True)
class Hit:
    row: LookupRow
    piece: str
    spelling: float
    meaning: float


def gate_on(template: str | None) -> bool:
    """True when the RAW template carries the marker as its own line."""
    return bool(template) and _LINE_RE.search(template) is not None


def spans_gate_on(template: str | None) -> bool:
    """True when the RAW template carries the span marker as its own line (ENTITY-EXTRACT-MATCH S2)."""
    return bool(template) and _SPAN_LINE_RE.search(template) is not None


def header(list_name: str) -> str:
    return f"{HEADER_NOUN[list_name]} candidates (pick one only if the message means it):"


def _fold(text: str) -> str:
    """`candidates._phrase`, but any script: a Chinese word survives the fold (spelling still
    reads ASCII trigrams only, so such a word is placed by meaning or exact equality)."""
    return " ".join(_WORD_RE.findall(str(text).casefold()))


def pieces(message: str, max_words: int = 4) -> list[str]:
    """Every 1..`max_words` consecutive-word piece of the folded message, in message order, once each."""
    words = _fold(message).split()[:MAX_MESSAGE_WORDS]
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


def _spelling(piece: str, piece_grams: frozenset[str], folded: str, grams: frozenset[str], same_words: bool = False) -> float:
    if not folded:
        return 0.0
    if piece == folded:
        return 1.0
    # Spec words: a near spelling is the same number of words spelt differently, so "bowl" is never "near"
    # the number word "3 bowl" (as the candidate lines read near spellings).
    if same_words and piece.count(" ") != folded.count(" "):
        return 0.0
    return candidates.similarity(piece_grams, grams)


#: Folded text and trigrams of each row text, built once per row set (the last few sets), so a turn folds
#: and trigrams only its own pieces.
_prepared: dict[str, dict[str, tuple[str, frozenset[str]]]] = {}
_PREPARED_SETS = 2
#: Guards `_prepared`, `_cache`, `_matrices` and `_pieces`: turns run on several threads.
_store_lock = threading.RLock()


def _prepare(texts: list[str]) -> dict[str, tuple[str, frozenset[str]]]:
    key = hashlib.sha1("\0".join(texts).encode()).hexdigest()
    with _store_lock:
        built = _prepared.get(key)
        if built is None:
            built = {}
            for t in texts:
                folded = _fold(t)
                built[t] = (folded, candidates.trigrams(folded) if folded else frozenset())
            while len(_prepared) >= _PREPARED_SETS:
                _prepared.pop(next(iter(_prepared)))
            _prepared[key] = built
        return built


#: CHAT-V66-REGRESSIONS: only the rows a floor can be reached for go through the exact per-piece loop
#: (`_rows_that_can_hit`); False sends every row (the reference the tests compare against).
FILTER_ROWS = True
#: Per row set: the trigram postings of its texts (text columns in `row_texts` order), kept like `_prepared`.
_indexes: dict[str, tuple[dict[str, Any], Any, Any, dict[str, list[int]]]] = {}


def _text_index(texts: list[str], prepared: dict[str, tuple[str, frozenset[str]]]):
    """(trigram -> columns holding it, trigrams per text, words per text, folded text -> its columns) for `texts`
    (folded, non-empty)."""
    import numpy as np

    key = hashlib.sha1("\0".join(texts).encode()).hexdigest()
    with _store_lock:
        built = _indexes.get(key)
        if built is None:
            postings: dict[str, list[int]] = {}
            for col, t in enumerate(texts):
                for g in prepared[t][1]:
                    postings.setdefault(g, []).append(col)
            same: dict[str, list[int]] = {}
            for col, t in enumerate(texts):
                same.setdefault(prepared[t][0], []).append(col)
            built = (
                {g: np.asarray(cols, dtype=np.int64) for g, cols in postings.items()},
                np.asarray([len(prepared[t][1]) for t in texts], dtype=np.int64),
                np.asarray([prepared[t][0].count(" ") + 1 for t in texts], dtype=np.int64),
                same,
            )
            while len(_indexes) >= _PREPARED_SETS:
                _indexes.pop(next(iter(_indexes)))
            _indexes[key] = built
        return built


def _rows_that_can_hit(rows, by_list, prepared, texts, piece_grams, meaning) -> list[LookupRow]:
    """The rows (in order) whose best spelling (`_spelling`: the same trigram Jaccard, from integer counts) or best
    meaning (the same cosines) over their list's pieces reaches a floor. Every other row would score below both floors
    in the exact loop, so leaving it out changes no hit."""
    import numpy as np

    pieces_all = list(piece_grams)
    postings, sizes, nwords, same = _text_index(texts, prepared)
    n = len(texts)
    col = {t: i for i, t in enumerate(texts)}
    jac = np.zeros((len(pieces_all), n), dtype=np.float64)
    for i, p in enumerate(pieces_all):
        parts = [postings[g] for g in piece_grams[p] if g in postings]
        if parts:
            inter = np.bincount(np.concatenate(parts), minlength=n)
            jac[i] = inter / (len(piece_grams[p]) + sizes - inter)
        jac[i, same.get(p, [])] = 1.0  # `_spelling`: the same folded text is 1.0 (a Chinese word has no ASCII trigrams)
    pwords = np.asarray([p.count(" ") + 1 for p in pieces_all], dtype=np.int64)
    sim = meaning[2].astype(np.float64) if meaning is not None else None
    pos = {p: i for i, p in enumerate(pieces_all)}
    keep: set[int] = set()
    by_name: dict[str, list[tuple[int, LookupRow]]] = {}
    for at, r in enumerate(rows):
        by_name.setdefault(r.list_name, []).append((at, r))
    for name, members in by_name.items():
        allowed = [pos[p] for p in by_list.get(name) or [] if p in pos]
        if not allowed:
            continue
        spell = jac[allowed]
        if name == "spec":  # `_spelling(same_words=True)`: a near spelling has as many words as the text
            spell = spell * (pwords[allowed][:, None] == nwords[None, :])
        best = (spell.max(axis=0) >= FLOOR_SPELLING)
        if sim is not None:
            floor = FLOOR_MEANING_BY_LIST.get(name, _FLOOR_MEANING_OTHER)
            best = best | (sim[allowed].max(axis=0) >= floor)
        for at, r in members:
            if any(best[col[t]] for t in r.texts if t in col):
                keep.add(at)
    return [r for at, r in enumerate(rows) if at in keep]


def _unit_rows(mat):
    import numpy as np

    mat = np.asarray(mat, dtype=np.float32)
    norms = np.linalg.norm(mat, axis=-1, keepdims=True)
    norms[norms == 0] = 1.0
    return (mat / norms).astype(np.float32)


def _meaning(embed: Embedder | None, usable: list[str], texts: list[str], *, any_model: bool = False):
    """(piece index, text index, S) with S[p, t] the cosine of piece p and row text t, or None when there
    is no embedder or it fails (spelling only). The provider embedder hands over its cached row matrix
    (built once per row set) and embeds only the message pieces; any other embedder is called once."""
    if embed is None or not texts:
        return None
    if not any_model and getattr(embed, "model", EMBED_MODEL) != EMBED_MODEL:
        return None  # the n-gram floors are calibrated on OpenAI vectors: any other model reads spelling only
    try:
        if hasattr(embed, "matrix"):
            m = embed.matrix(texts)  # type: ignore[attr-defined]
            pm = embed.pieces(usable)  # type: ignore[attr-defined]
        else:
            raw = _unit_rows(embed([*usable, *texts]))
            if raw.ndim != 2 or raw.shape[0] != len(usable) + len(texts):
                return None
            pm, m = raw[: len(usable)], raw[len(usable) :]
        return {p: i for i, p in enumerate(usable)}, {t: i for i, t in enumerate(texts)}, pm @ m.T
    except Exception:  # noqa: BLE001 - advisory: spelling only
        return None


def held_values(subject: dict[str, Any]) -> dict[str, tuple[str, ...]]:
    """List name -> the values the State subject holds for it (`HELD_SUBJECT_LISTS`); other subject keys are dropped."""
    out: dict[str, tuple[str, ...]] = {}
    for key, name in HELD_SUBJECT_LISTS.items():
        value = subject.get(key)
        values = tuple(str(v) for v in (value if isinstance(value, list) else [value]) if v and _fold(str(v)))
        if values:
            out[name] = values
    return out


def _held_hits(rows: list[LookupRow], held: dict[str, tuple[str, ...]]) -> dict[str, dict[str, Hit]]:
    """Per list, the rows whose own text is a held value, case and punctuation aside (no near spelling, no meaning)."""
    wanted = {name: {_fold(v) for v in values} for name, values in held.items()}
    out: dict[str, dict[str, Hit]] = {}
    for row in rows:
        folded = wanted.get(row.list_name)
        match = next((_fold(t) for t in row.texts if _fold(t) in folded), None) if folded else None
        if match:
            out.setdefault(row.list_name, {})[row.key] = Hit(row, match, 1.0, 0.0)
    return out


def shortlist(
    message: str,
    rows: list[LookupRow],
    embed: Embedder | None,
    *,
    brand_words: frozenset[str] = frozenset(),
    held: dict[str, tuple[str, ...]] | None = None,
) -> dict[str, list[Hit]]:
    """Per list, the rows the message spells or means near, and the rows `held` names (`held_values`), best first,
    cut to `TOP_K`."""
    best: dict[str, dict[str, Hit]] = _held_hits(rows, held) if held else {}
    usable = [p for p in pieces(message) if not _code_like(p)]
    if not usable or not rows:
        return _ordered(best)
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
    prepared = _prepare(sorted({t for r in rows for t in r.texts}))
    row_texts = [t for t, (folded, _g) in prepared.items() if folded]
    meaning = _meaning(embed, usable, row_texts)
    piece_grams = {p: candidates.trigrams(p) for p in usable}
    scan = _rows_that_can_hit(rows, by_list, prepared, row_texts, piece_grams, meaning) if FILTER_ROWS else rows

    for row in scan:
        row_pieces = by_list.get(row.list_name) or []
        floor_meaning = FLOOR_MEANING_BY_LIST.get(row.list_name, _FLOOR_MEANING_OTHER)
        spell_best, mean_best, piece_best, score_best = 0.0, 0.0, "", -1.0
        for piece in row_pieces:
            for text in row.texts:
                folded, grams = prepared[text]
                s = _spelling(piece, piece_grams[piece], folded, grams, row.list_name == "spec")
                m = 0.0
                if meaning is not None and text in meaning[1]:
                    m = max(0.0, float(meaning[2][meaning[0][piece], meaning[1][text]]))
                spell_best, mean_best = max(spell_best, s), max(mean_best, m)
                score = max(s if s >= FLOOR_SPELLING else 0.0, m if m >= floor_meaning else 0.0)
                if score > score_best:
                    piece_best, score_best = piece, score
        if (spell_best >= FLOOR_SPELLING or mean_best >= floor_meaning) and row.key not in best.get(row.list_name, {}):
            best.setdefault(row.list_name, {})[row.key] = Hit(row, piece_best, spell_best, mean_best)
    return _ordered(best)


def _ordered(best: dict[str, dict[str, Hit]]) -> dict[str, list[Hit]]:
    out: dict[str, list[Hit]] = {}
    for name, hits in best.items():
        ordered = sorted(hits.values(), key=lambda h: (-max(h.spelling, h.meaning), h.row.label))
        out[name] = ordered[: TOP_K.get(name, 10)]
    return out


def _one_line(label: str) -> str:
    """One line of at most `MAX_LABEL_CHARS`; a closing `(key: value)` bracket is kept whole, the text before it shrinks."""
    text = " ".join(str(label).split())
    if len(text) <= MAX_LABEL_CHARS:
        return text
    at = text.rfind(" (")
    if at > 0 and text.endswith(")") and len(text) - at <= MAX_LABEL_CHARS // 2:
        tail = text[at:]
        return text[: MAX_LABEL_CHARS - len(tail)].rstrip() + tail
    return text[:MAX_LABEL_CHARS]


def _grouped_category_lines(hits: list[Hit]) -> list[str]:
    """EEM-CATEGORY-PICK: one line per class, "- <class>: <label>, <label>" (the class row's own label is the line's
    head, not an item; a class matched only by its own row prints bare); a row with no class prints "- <label>"."""
    groups: dict[str, list[Any]] = {}  # folded class -> [printed spelling, items, spelling came from a member row]
    for h in hits:
        label = _one_line(h.row.label)
        if not label:
            continue
        head = _one_line(h.row.group or "") or label
        entry = groups.setdefault(head.casefold(), [head, [], False])
        if label.casefold() != head.casefold():
            if label not in entry[1]:
                entry[1].append(label)
            if not entry[2]:  # the class's own spelling is the one its member rows carry
                entry[0], entry[2] = head, True
    return [f"- {head}: {', '.join(items)}" if items else f"- {head}" for head, items, _m in groups.values()]


def render(hits: dict[str, list[Hit]], order: tuple[str, ...] = DEFAULT_ORDER, *, group_categories: bool = False) -> list[str]:
    """One block per list with hits: the header, then `- <label>` once per label (a category block one line per
    class when `group_categories`)."""
    lines: list[str] = []
    for name in order:
        if group_categories and name == "category":
            grouped = _grouped_category_lines(hits.get(name) or [])
            if grouped:
                lines.append(header(name))
                lines.extend(grouped)
            continue
        labels: list[str] = []
        for h in hits.get(name) or []:
            label = _one_line(h.row.label)
            if label and label not in labels:
                labels.append(label)
        if labels:
            lines.append(header(name))
            lines.extend(f"- {label}" for label in labels)
    return lines


def _with_synonyms(list_name: str, label: str, texts: tuple[str, ...]) -> tuple[str, ...]:
    extra = {k.casefold(): v for k, v in PROMPT_SYNONYMS.get(list_name, {}).items()}.get(label.casefold(), ())
    return tuple(dict.fromkeys([*texts, *extra]))


def _spec_rows(db: "Session", hidden: frozenset[str] = frozenset()) -> list[LookupRow]:
    """One row per value the registry knows, each line ending in the registry's own `(key: value)` so the
    parser fills `spec_key` / `spec_value` from it: an enum value (`<label> <value>`), a yes/no key
    (`<label> yes`, true) and a numeric key said in words (`<label> <n>`, "double bowl" = 2). Enum keys
    that say what the product IS (class, product type) or its brand are category / brand rows."""
    from app.services.product_spec_registry import (
        active_registry,
        display_spec_value,
        merged_allowed_values,
        merged_synonyms,
    )

    def texts_of(*parts) -> tuple[str, ...]:
        return tuple(dict.fromkeys(str(t) for p in parts for t in p if t and _fold(str(t))))

    out: list[LookupRow] = []
    for row in active_registry(db):
        key, kind = row.spec_key, (row.data_type or "").lower()
        if key in hidden or key in candidates.TYPE_KEYS | candidates.SKIP_KEYS:
            continue
        synonyms = merged_synonyms(row)
        if kind == "enum":
            labels = dict(getattr(row, "value_labels", None) or {})
            for value in merged_allowed_values(row):
                display = display_spec_value(value, labels)
                out.append(
                    LookupRow("spec", f"{key}={value}", f"{row.label} {display} ({key}: {value})",
                              texts_of([str(value), display], synonyms.get(value) or []))
                )
        elif kind == "boolean":
            out.append(
                LookupRow("spec", f"{key}=true", f"{row.label} yes ({key}: true)",
                          texts_of(synonyms.get("true") or []))
            )
        elif kind == "numeric":
            for value in (v for v in synonyms if v != "_self"):
                out.append(
                    LookupRow("spec", f"{key}={value}", f"{row.label} {value} ({key}: {value})",
                              texts_of(synonyms.get(value) or []))
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


def _brand_rows(db: "Session", brands: list[dict] | None = None) -> list[LookupRow]:
    """Active brands of the session's companies, labelled exactly as the `Known brands:` line spells them."""
    from app.services.chatbot import turn_runtime
    from app.services.chatbot.turn.context import known_brands_line

    out: list[LookupRow] = []
    seen: set[str] = set()
    for b in turn_runtime.active_brands(db) if brands is None else brands:
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
        LookupRow("promotion_kind", r["type_code"], f"{r['type_code']} ({r['type_name']})", (r["type_name"], r["type_code"]))
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
    include_customers: bool = False, customer_ids: frozenset[str] | None = None, brands: list[dict] | None = None,
    group_categories: bool = False,
) -> list[LookupRow]:
    """Categories (searchable and active, company-scoped by the session), class labels, product types,
    spec word values, file types and the sales channels. `group_categories` (EEM-CATEGORY-PICK) reads the class
    vocabulary to set each category row's `group`; off, it is never read."""
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
    from app.services.product_class_signal import ClassVocabulary, category_class

    vocab = ClassVocabulary(db) if group_categories and any(not (c.class_label or "").strip() for c in cats) else None
    for c in cats:
        texts = tuple(dict.fromkeys(str(t) for t in [c.category_name, c.category_code, c.class_label, *(c.search_synonyms or [])] if t and str(t).strip()))
        group = (
            category_class(db, code=c.category_code, name=c.category_name, class_label=c.class_label, vocab=vocab)
            if group_categories else None
        )
        out.append(LookupRow("category", str(c.id), c.category_name, _with_synonyms("category", c.category_name, texts), group))
        seen_labels.add(_fold(c.category_name))
    # Class labels and product types, as the parser's old `Product types:` line named them.
    for name in turn_runtime.product_type_names(db):
        key = _fold(name)
        if key and key not in seen_labels:
            seen_labels.add(key)
            out.append(LookupRow("category", "type:" + key, name, _with_synonyms("category", name, (name,)), name if group_categories else None))
    out.extend(_spec_rows(db, hidden_spec_keys))
    out.extend(_file_type_rows(db))
    out.extend(_brand_rows(db, brands))
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
#: A unit word (as said or as the registry stores it) -> (unit class, factor to the class's base unit).
_UNITS = {
    "mm": ("len", 1.0), "cm": ("len", 10.0), "m": ("len", 1000.0),
    "l": ("l", 1.0), "litre": ("l", 1.0), "litres": ("l", 1.0), "liter": ("l", 1.0), "liters": ("l", 1.0),
    "hp": ("hp", 1.0), "oz": ("oz", 1.0), "ounce": ("oz", 1.0), "ounces": ("oz", 1.0),
}


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


def _unit_words(rows: list[Any]) -> dict[str, tuple[str, float]]:
    """`_UNITS` plus every alias the registry lists for a numeric key (`unit_aliases`, DIMENSION-ANY): "inch" ->
    ("len", 25.4) off a mm key's `{"inch": 25.4}`. Unit words beyond the shipped ones are data, never code."""
    units = dict(_UNITS)
    for row in rows:
        base = _UNITS.get((row.unit or "").strip().lower())
        if base is None:
            continue
        for alias, factor in (getattr(row, "unit_aliases", None) or {}).items():
            word = str(alias).strip().casefold()
            if word and isinstance(factor, (int, float)) and not isinstance(factor, bool) and factor > 0:
                units.setdefault(word, (base[0], base[1] * float(factor)))
    return units


def _quantity_re(words: Any) -> re.Pattern[str]:
    """A quantity in the message: a number not glued to a letter or digit before it (a code), one of these unit
    words after it, the longest first."""
    alternatives = "|".join(re.escape(w) for w in sorted(words, key=len, reverse=True))
    return re.compile(rf"(?<![a-z0-9.])(\d+(?:\.\d+)?)\s*({alternatives})(?![a-z0-9])")


def _plain(value: float) -> str:
    """A number as a person writes it: no exponent, no trailing zeros ("1000000", "152.4")."""
    return f"{value:.6f}".rstrip("0").rstrip(".")


#: DIMENSION-ANY: the bracket key of the line that offers a length with no dimension named; the parser emits it as
#: spec_key and grounding reads it as every dimension (`head/bare_size.py`).
SIZE_KEY = "size"


def number_hits(message: str, db: "Session", *, hidden_spec_keys: frozenset[str] = frozenset()) -> list[Hit]:
    """Every numeric spec key whose stored values hold a quantity the message says (mm / cm / m, litres, hp, oz,
    and the registry's own unit aliases), in the key's own unit, the line ending in the bare number the parser
    reads ("trap length 200mm (trap_length: 200)"). At most `MAX_NUMBER_ASKS` distinct quantities per message. No
    meaning score. A code that merely contains digits is never a quantity.

    DIMENSION-ANY (owner, 28 Oct 2026): a length leads with "Size 150mm, any dimension (size: 150)", the line a
    size said with no dimension named is emitted from, then the keys that hold it, then every other dimension's own
    line, so a NAMED dimension is always nameable (a miss is said back as named, and a named dimension nothing holds
    falls back to any dimension). Any other quantity no key holds offers nothing."""
    from sqlalchemy import case, func

    from app.models.product import Product, chat_searchable_products
    from app.models.product_spec import ProductSpecifications
    from app.services.product_spec_registry import active_registry
    from app.services.product_spec_search import dimension_keys, membership_clause

    rows = [
        row for row in active_registry(db)
        if (row.data_type or "").lower() == "numeric" and row.spec_key not in hidden_spec_keys
    ]
    units = _unit_words(rows)
    folded = str(message or "").casefold()
    asks: list[tuple[str, float, str]] = []  # (unit class, value in its base unit, piece)
    for m in _quantity_re(units).finditer(folded):
        cls, factor = units[m.group(2)]
        ask = (cls, round(float(m.group(1)) * factor, 6), m.group(0))
        if not any(a[:2] == ask[:2] for a in asks):
            asks.append(ask)
        if len(asks) >= MAX_NUMBER_ASKS:
            break
    if not asks:
        return []
    dims = set(dimension_keys(rows))
    wanted: list[tuple[Any, str, float, str]] = []  # (registry row, shown, value in the key's unit, piece)
    for row in rows:
        unit = (row.unit or "").strip()
        if unit.lower() not in _UNITS:
            continue
        cls, factor = _UNITS[unit.lower()]
        for ask_cls, base, piece in asks:
            if ask_cls == cls:
                value = round(base / factor, 6)
                wanted.append((row, f"{_plain(value)}{unit}", value, piece))
    if not wanted:
        return []
    columns = [
        func.coalesce(func.sum(case((membership_clause({row.spec_key: [value]}), 1), else_=0)), 0)
        for row, _s, value, _p in wanted
    ]
    counts = (
        db.query(*columns)
        .select_from(ProductSpecifications)
        .join(Product, Product.id == ProductSpecifications.product_id)
        .filter(chat_searchable_products())
        .one()
    )
    held = {(row.spec_key, shown) for (row, shown, _v, _p), n in zip(wanted, counts) if int(n) > 0}
    scopes = _carried_by(db, sorted({row.spec_key for row, shown, _v, _p in wanted if row.spec_key in dims and (row.spec_key, shown) not in held}))
    sizes: dict[str, Hit] = {}
    holding: list[Hit] = []
    named: list[Hit] = []
    for row, shown, value, piece in wanted:
        is_dim = row.spec_key in dims
        if is_dim and shown not in sizes:
            label = f"Size {shown}, any dimension ({SIZE_KEY}: {_plain(value)})"
            sizes[shown] = Hit(LookupRow("spec", f"{SIZE_KEY}={shown}", label, (label,)), _fold(piece), 1.0, 0.0)
        if (row.spec_key, shown) in held or is_dim:
            label = f"{row.label} {shown} ({row.spec_key}: {_plain(value)})"
            holds = (row.spec_key, shown) in held
            scope = None if holds else scopes.get(row.spec_key, frozenset())
            hit = Hit(LookupRow("spec", f"{row.spec_key}={shown}", label, (label,), scope=scope), _fold(piece), 1.0, 0.0)
            (holding if holds else named).append(hit)
    by_label = lambda h: h.row.label  # noqa: E731
    return [*sizes.values(), *sorted(holding, key=by_label), *sorted(named, key=by_label)]


def _carried_by(db: "Session", keys: list[str]) -> dict[str, frozenset[str]]:
    """Per spec key, the Category row keys (`load_rows`: a category's id, "type:<class or product type>") whose
    chat-searchable products carry the key at all. One grouped query."""
    if not keys:
        return {}
    from sqlalchemy import func

    from app.models.product import Product, chat_searchable_products
    from app.models.product_spec import ProductSpecifications

    values = ProductSpecifications.values
    kinds = (values["class"]["value"].astext, values["product_type"]["value"].astext)
    rows = (
        db.query(Product.category_id, *kinds, *[func.bool_or(values.has_key(k)) for k in keys])
        .join(ProductSpecifications, ProductSpecifications.product_id == Product.id)
        .filter(chat_searchable_products())
        .group_by(Product.category_id, *kinds)
        .all()
    )
    from app.services.product_spec_registry import active_registry, display_spec_value

    # A "type:" row is named by the product type's display label (`turn_runtime.product_type_names`), which can
    # differ in words from the stored value: both are folded.
    type_row = next((r for r in active_registry(db) if r.spec_key == "product_type"), None)
    type_labels = dict(getattr(type_row, "value_labels", None) or {})
    out: dict[str, set[str]] = {k: set() for k in keys}
    for category_id, klass, product_type, *carries in rows:
        shown = display_spec_value(product_type, type_labels) if product_type else None
        names = {str(category_id)} | {"type:" + _fold(n) for n in (klass, product_type, shown) if n}
        for key, carried in zip(keys, carries):
            if carried:
                out[key] |= names
    return {k: frozenset(v) for k, v in out.items()}


def with_numbers(numbers: list[Hit], spec: list[Hit], categories: list[Hit] | None = None) -> list[Hit]:
    """The Spec block: the number lines first, then the word lines at their own cap (a length's dimension lines
    never push a word the message also said out of the block).

    DIMENSION-ANY (crew gate round 2, dealer "hose 2m" shown 10 dimension lines): a dimension no product holds at
    the asked value is offered only when a Category row of this block carries it (hoses carry a hose length, not a
    trap outlet length); with no Category row, every dimension stays nameable."""
    named = {h.row.key for h in categories or []}
    kept = [h for h in numbers if h.row.scope is None or not named or h.row.scope & named]
    return [*kept, *spec[: TOP_K["spec"]]]


def brand_words(db: "Session", brands: list[dict] | None = None) -> frozenset[str]:
    """Folded brand names, codes and aliases: the words that are a brand and never a category."""
    from app.services.chatbot import turn_runtime

    words: set[str] = set()
    for b in turn_runtime.active_brands(db) if brands is None else brands:
        for w in (b.get("brand_name"), b.get("brand_code"), *(b.get("aliases") or [])):
            folded = _fold(w) if w else ""
            if folded:
                words.add(folded)
    return frozenset(words)


# ---------------------------------------------------------------------------- production embedder

#: Row-text vectors, unit float32, per process; message pieces are never stored here.
_cache: dict[tuple[str, str], Any] = {}
#: The row matrix of a row set (rows aligned to its sorted texts), built once and kept for the last few sets.
_matrices: dict[str, Any] = {}
_MATRIX_SETS = 2
#: A tiny LRU of message-piece vectors.
_pieces: dict[str, Any] = {}
_PIECES_CAP = 512


def _key(text: str, model: str = EMBED_MODEL) -> tuple[str, str]:
    return (model, hashlib.sha1(text.encode()).hexdigest())


#: Gemini's batchEmbedContents takes at most 100 texts per request.
GEMINI_EMBED_CHUNK = 100
#: The vector size the meaning floors were calibrated on (native is 3072; `GeminiProvider.embed` also sizes down).
GEMINI_EMBED_DIMENSIONS = 1536


#: Waits (seconds) before each retry of a warm chunk the provider rate-limited; a per-minute burst limit clears in
#: one. Each wait is stretched by up to 50% jitter so the workers of a container do not retry in lockstep.
WARM_RETRY_WAITS = (15, 30, 60)
_sleep = time.sleep
_jitter = random.random


def _shared_path(model: str) -> str | None:
    """The shared vector file of `model`, or None when sharing is off (`CHATBOT_LOOKUP_VECTOR_DIR` = off/0/false/no).
    The directory defaults to the system temp dir, which every worker of a container sees."""
    base = os.environ.get("CHATBOT_LOOKUP_VECTOR_DIR") or tempfile.gettempdir()
    if base.strip().lower() in ("off", "0", "false", "no"):
        return None
    return os.path.join(base, "lookup-vectors-" + re.sub(r"[^A-Za-z0-9._-]", "_", model) + ".npz")


def _lock_shared(path: str) -> int | None:
    """Take the exclusive lock beside the shared file (blocking); None, with a warning, when it cannot be had."""
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        fd = os.open(path[: -len(".npz")] + ".lock", os.O_CREAT | os.O_RDWR, 0o600)
    except OSError:
        logger.warning("lookup shared vectors: no lock file, warming without the shared file", exc_info=True)
        return None
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
    except OSError:
        os.close(fd)
        logger.warning("lookup shared vectors: lock failed, warming without the shared file", exc_info=True)
        return None
    return fd


def _read_shared(path: str) -> dict[str, Any]:
    """sha1 -> unit float32 vector from the shared file; empty when it is absent or unusable (warned)."""
    import numpy as np

    if not os.path.exists(path):
        return {}
    try:
        with np.load(path, allow_pickle=False) as f:
            keys, vectors = f["keys"], f["vectors"]
        if vectors.ndim != 2 or vectors.dtype != np.float32 or len(keys) != len(vectors):
            raise ValueError("unexpected shape")
        return {str(k): vectors[i] for i, k in enumerate(keys)}
    except Exception:  # noqa: BLE001 - a bad file is rebuilt by this warm
        logger.warning("lookup shared vectors: %s unreadable, re-embedding", path, exc_info=True)
        return {}


def _write_shared(path: str, vectors: dict[str, Any]) -> None:
    """Write the shared file atomically (temp file in the same directory, then rename); never raises."""
    import numpy as np

    if not vectors:
        return
    tmp = None
    try:
        fd, tmp = tempfile.mkstemp(prefix=".part-", suffix=".npz", dir=os.path.dirname(path))
        with os.fdopen(fd, "wb") as out:
            np.savez(out, keys=np.array(list(vectors)), vectors=np.stack(list(vectors.values())).astype(np.float32))
        os.replace(tmp, path)
        tmp = None
    except Exception:  # noqa: BLE001 - the warm stands without the file
        logger.warning("lookup shared vectors: could not write %s", path, exc_info=True)
    finally:
        if tmp is not None:
            try:
                os.unlink(tmp)
            except OSError:
                pass


def _vector_embedder(model: str, request: Callable[[list[str]], list[Any]], chunk_size: int) -> Embedder:
    """A row-vector embedder over `request` (texts -> raw vectors): vectors cached per process by (model, sha1 of
    text) as unit float32, the uncached texts of a call sent in chunks inside one `EMBED_TIMEOUT` budget. `matrix`
    is the row matrix of a row set (built once); `pieces` embeds a message's pieces without storing them as rows.
    The model is part of the cache key, so a model switch never mixes vector spaces."""

    def store(chunk: list[str], raw: list[Any]) -> None:
        vectors = _unit_rows(raw)
        with _store_lock:
            for t, vec in zip(chunk, vectors):
                _cache[_key(t, model)] = vec

    def embed(texts: list[str]) -> list[Any]:
        deadline = time.monotonic() + EMBED_TIMEOUT
        with _store_lock:
            todo = [t for t in dict.fromkeys(texts) if _key(t, model) not in _cache]
            if len(_cache) + len(todo) > _CACHE_CAP:
                _cache.clear()
                _matrices.clear()
                todo = list(dict.fromkeys(texts))
        for i in range(0, len(todo), chunk_size):
            if time.monotonic() > deadline:
                raise TimeoutError("lookup list embedding budget spent")
            chunk = todo[i : i + chunk_size]
            store(chunk, request(chunk))
        with _store_lock:
            return [_cache[_key(t, model)] for t in texts]

    def fill(texts: list[str]) -> int:
        """The background warm-up: every uncached text in chunks, each chunk under its own timeout, no
        total deadline; chunks are kept as they complete. A rate-limited chunk is waited out (`WARM_RETRY_WAITS`),
        then the error is re-raised; a large warm is back-to-back requests and trips the per-minute limit.
        The workers of a container share their vectors through a per-model file (`_shared_path`) under an
        exclusive file lock held for the whole warm, so one worker embeds and the rest load. Returns how many
        texts came from that file."""
        lock_fd = None
        path = _shared_path(model)
        if path is not None:
            lock_fd = _lock_shared(path)
        loaded = 0
        file_vectors: dict[str, Any] = {}
        try:
            with _store_lock:
                missing = [t for t in dict.fromkeys(texts) if _key(t, model) not in _cache]
                if len(_cache) + len(missing) > _CACHE_CAP:  # the cap `embed` keeps, so the store stays bounded
                    _cache.clear()
                    _matrices.clear()
            if lock_fd is not None:
                file_vectors = _read_shared(path)
                with _store_lock:
                    for t in dict.fromkeys(texts):
                        sha = _key(t, model)[1]
                        if _key(t, model) not in _cache and sha in file_vectors:
                            _cache[_key(t, model)] = file_vectors[sha]
                            loaded += 1
            with _store_lock:
                todo = [t for t in dict.fromkeys(texts) if _key(t, model) not in _cache]
            for i in range(0, len(todo), chunk_size):
                chunk = todo[i : i + chunk_size]
                for wait in (*WARM_RETRY_WAITS, None):
                    try:
                        raw = request(chunk)
                        break
                    except Exception as exc:  # noqa: BLE001
                        from app.services.chatbot import llm_call

                        if wait is None or not llm_call.is_rate_limited(exc) or llm_call._quota_exhausted(exc):
                            raise
                        _sleep(wait * (1 + 0.5 * _jitter()))
                store(chunk, raw)
        finally:
            if lock_fd is not None:
                try:
                    with _store_lock:
                        asked = {_key(t, model)[1]: _cache[_key(t, model)] for t in texts if _key(t, model) in _cache}
                    merged = {**file_vectors, **asked}
                    _write_shared(path, merged if len(merged) <= _CACHE_CAP else asked)
                finally:
                    os.close(lock_fd)  # closing the descriptor releases the flock
        return loaded

    def matrix(texts: list[str]):
        import numpy as np

        embed(texts)
        key = hashlib.sha1((model + "\0" + "\0".join(texts)).encode()).hexdigest()
        with _store_lock:
            built = _matrices.get(key)
            if built is None:
                built = np.stack([_cache[_key(t, model)] for t in texts])
                while len(_matrices) >= _MATRIX_SETS:
                    _matrices.pop(next(iter(_matrices)))
                _matrices[key] = built
            return built

    def pieces_matrix(texts: list[str]):
        import numpy as np

        # The message's own vectors are read before the cache evicts: a cached piece at the front of the cache is
        # still this message's piece (CHAT-V66-REGRESSIONS: it raised KeyError and the turn lost its meaning scores).
        with _store_lock:
            got = {t: _pieces[(model, t)] for t in texts if (model, t) in _pieces}
        todo = [t for t in dict.fromkeys(texts) if t not in got]
        if todo:
            vectors = _unit_rows(request(todo))
            got.update(zip(todo, vectors))
            with _store_lock:
                for t, vec in zip(todo, vectors):
                    _pieces[(model, t)] = vec
                while len(_pieces) > _PIECES_CAP:
                    _pieces.pop(next(iter(_pieces)))
        return np.stack([got[t] for t in texts])

    embed.fill = fill  # type: ignore[attr-defined]
    embed.matrix = matrix  # type: ignore[attr-defined]
    embed.pieces = pieces_matrix  # type: ignore[attr-defined]
    embed.needs_warm = True  # type: ignore[attr-defined]
    embed.model = model  # type: ignore[attr-defined]
    embed.is_cached = lambda texts: all(_key(t, model) in _cache for t in list(texts))  # type: ignore[attr-defined]
    return embed


def provider_embedder(api_key: str) -> Embedder:
    """OpenAI `text-embedding-3-small` (see `_vector_embedder`)."""
    from app.services.llm_provider import OpenAIProvider

    def request(chunk: list[str]) -> list[Any]:
        client = OpenAIProvider(api_key)._client(timeout=EMBED_TIMEOUT, max_retries=0)
        return [item.embedding for item in client.embeddings.create(model=EMBED_MODEL, input=chunk).data]

    return _vector_embedder(EMBED_MODEL, request, EMBED_CHUNK)


def gemini_embedder(api_key: str, model: str) -> Embedder:
    """Gemini `batchEmbedContents` on `model` (see `_vector_embedder`), one request per batch of texts."""
    from app.services.llm_provider import GeminiProvider

    def request(chunk: list[str]) -> list[Any]:
        body = GeminiProvider(api_key)._request(
            "POST",
            f"models/{model}:batchEmbedContents",
            json_body={
                "requests": [
                    {
                        "model": f"models/{model}",
                        "content": {"parts": [{"text": t}]},
                        "outputDimensionality": GEMINI_EMBED_DIMENSIONS,
                    }
                    for t in chunk
                ]
            },
            timeout=EMBED_TIMEOUT,
        )
        vectors = [e.get("values") or [] for e in body.get("embeddings") or []]
        if len(vectors) != len(chunk) or not all(vectors):
            raise RuntimeError("Gemini batchEmbedContents returned the wrong number of vectors.")
        return vectors

    return _vector_embedder(model, request, GEMINI_EMBED_CHUNK)


_warm_lock = threading.Lock()


def _import_sdk() -> None:
    """Import the provider SDK modules a lookup thread will use, in the CALLING thread: two threads importing the
    SDK lazily at once (the warm-up or prefetch thread and the span call) raced to `KeyError: 'openai.resources'`
    on a fresh process. Not done at app import: the SDK stays lazy."""
    try:
        import openai  # noqa: F401
        import openai.resources.embeddings  # noqa: F401
    except Exception:  # noqa: BLE001 - no SDK, no provider embedder: nothing to race
        pass


def prefetch(message: str, embed: Embedder | None) -> Callable[[], bool]:
    """CHAT-V66-REGRESSIONS: start the message pieces' embedding (the lookup's one network call per turn) on a thread,
    so the round trip overlaps the turn's database work. The returned call waits for it, at most `EMBED_TIMEOUT`, and
    says whether the pieces arrived; when they did not (late or failed) the turn reads spelling only rather than send
    the request a second time. Only the provider embedder (`pieces`) is prefetched; anything else is ready at once."""
    usable = [p for p in pieces(message) if not _code_like(p)]
    if embed is None or not hasattr(embed, "pieces") or not usable or getattr(embed, "model", EMBED_MODEL) != EMBED_MODEL:
        return lambda: True
    arrived: list[bool] = []

    def run() -> None:
        try:
            embed.pieces(usable)  # type: ignore[attr-defined]
            arrived.append(True)
        except Exception:  # noqa: BLE001 - advisory: spelling only
            pass

    thread = threading.Thread(target=run, name="lookup-lists-prefetch", daemon=True)
    _import_sdk()
    thread.start()

    def ready() -> bool:
        thread.join(EMBED_TIMEOUT)
        return bool(arrived)

    return ready


def row_texts(rows: list[LookupRow]) -> list[str]:
    return sorted({t for r in rows for t in r.texts if _fold(t)})


def warm(rows: list[LookupRow], embed: Embedder | None) -> None:
    """Embed every row text on a background thread so a cold cache never blocks a turn. One warm-up
    at a time; a failure is swallowed (the next turn tries again, the turn itself is spelling only)."""
    if embed is None or not rows:
        return
    texts = row_texts(rows)
    # A full cache has nothing to fetch: no thread, no lock, no log line per turn.
    is_cached = getattr(embed, "is_cached", None)
    if is_cached is not None and is_cached(texts):
        return
    if not _warm_lock.acquire(blocking=False):
        return

    def run() -> None:
        started = time.monotonic()
        try:
            from_file = getattr(embed, "fill", embed)(texts)
            logger.info(
                "lookup lists warm: %d texts cached on %s in %.1f s (%d from the shared file)",
                len(texts), getattr(embed, "model", "?"), time.monotonic() - started,
                from_file if isinstance(from_file, int) else 0,
            )
        except Exception:  # noqa: BLE001 - advisory
            logger.warning("lookup lists warm failed", exc_info=True)
        finally:
            _warm_lock.release()

    _import_sdk()
    threading.Thread(target=run, name="lookup-lists-warm", daemon=True).start()


def usable_embedder(rows: list[LookupRow], embed: Embedder | None) -> Embedder | None:
    """`embed` for the turn: the provider embedder only once every row text is cached (else None, spelling
    only, while `warm` fills the cache); any other embedder as given."""
    if embed is not None and getattr(embed, "needs_warm", False) and not embed.is_cached(row_texts(rows)):  # type: ignore[attr-defined]
        return None
    return embed


def embedder(db: "Session") -> Embedder | None:
    """`EMBED` as the engine uses it: a set value (a callable or None) wins; the default follows the production
    label of prompt key `chatbot_lookup_embedder`: provider gemini plus a model -> a Gemini embedder with the AI
    config's Gemini key; otherwise the OpenAI embedder with its key. No key for the chosen provider -> None
    (spelling only)."""
    if EMBED is not USE_PROVIDER:
        return EMBED
    from app.services import ai_prompt_registry, llm_provider
    from app.services.ai_assistant_service import AIAssistantConfigService

    config = AIAssistantConfigService(db).get()
    provider, model = ai_prompt_registry.agent_model(db, EMBEDDER_PROMPT_KEY)
    if provider == "gemini" and model:
        key = llm_provider.resolve_api_key(config, "gemini")
        return gemini_embedder(key, model) if key else None
    key = llm_provider.resolve_api_key(config, "openai")
    return provider_embedder(key) if key else None
