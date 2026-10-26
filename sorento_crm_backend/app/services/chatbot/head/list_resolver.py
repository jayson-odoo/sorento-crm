"""Resolve extracted spans to rows of the lookup lists (ENTITY-EXTRACT-MATCH S1).

The extractor hands over spans of the message ("kimlan", "srt", "马桶"); this module places each on the
rows the caller loaded (`lookup_lists.load_rows`, visibility already applied). Code only SCORES; the span
type is a tie-break, never a filter, and nothing here knows what a word means: an alias is a text on the
row, not a word in this file. Per (span, row) the best over the row's texts of

- exact: the span equals a text after case/space folding (1.0);
- spelling: trigram similarity (`candidates.similarity`, as the lookup lists);
- partial: the IDF-weighted share of the span's words that a row word matches (equal, trigram >= 0.6, or one
  edit for words of 4+ letters; a fuzzy match counts for its similarity, an exact one for 1.0). IDF comes from
  the list's own texts and a span word weighs what the row word it matches weighs, so "SDN", "TRADING" and
  their typos weigh little and "Kimlan" resolves "KIMLAN TRADING SDN BHD";
- meaning: cosine of the embeddings, when an embedder is given and answers (advisory, as `lookup_lists`).

A row passes when any signal reaches its list's floor. The best passing row over ALL lists wins; rows within
`AMBIGUITY_MARGIN` of it on SCORE (different rows) make the span `ambiguous` and are all returned; word coverage
only orders them. A typed span prefers its own list when that list's best row is within `TYPE_MARGIN` of the
overall best, and never loses a row for want of one. Among close rows, those the span equals outright (signal
`exact`) are the only ones kept. Nothing on the turn path imports this module yet.
"""
from __future__ import annotations

import hashlib
import math
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

from app.services.chatbot.head import candidates
from app.services.chatbot.head.lookup_lists import Embedder, LookupRow, _fold, _meaning

SPAN_TYPES = (
    "brand", "customer", "salesperson", "location", "category", "spec_key", "spec_value",
    "file_type", "promotion_kind", "sales_channel", "product_code",
)
#: The list a span type prefers on a tie; every type but `spec_value` is its own list's name.
TYPE_LIST = {t: t for t in SPAN_TYPES} | {"spec_value": "spec"}

#: Per list: the floor each signal must reach. From the phase-1 calibration on the calibration half
#: (reported on the test half); 1.01 turns a signal off for that list.
FLOORS: dict[str, dict[str, float]] = {
    "category": {"spell": 0.45, "partial": 0.8, "meaning": 0.6},
    "spec": {"spell": 0.55, "partial": 0.8, "meaning": 0.55},
    "file_type": {"spell": 0.5, "partial": 0.5, "meaning": 0.59},
    "brand": {"spell": 0.5, "partial": 0.8, "meaning": 0.58},
    "promotion_kind": {"spell": 0.5, "partial": 1.01, "meaning": 0.6},
    "location": {"spell": 0.5, "partial": 0.8, "meaning": 0.55},
    "salesperson": {"spell": 0.4, "partial": 0.8, "meaning": 0.6},
    "customer": {"spell": 0.5, "partial": 0.6, "meaning": 0.6},
    "sales_channel": {"spell": 0.5, "partial": 0.8, "meaning": 0.55},
    "spec_key": {"spell": 0.5, "partial": 0.8, "meaning": 0.6},
}
_FLOORS_OTHER = {"spell": 0.5, "partial": 0.8, "meaning": 0.6}
#: Rows whose scores differ by no more than this are the same answer to the span.
AMBIGUITY_MARGIN = 0.03
#: A word is common in a list when it is in two or more of its texts and its IDF is below this share of the IDF
#: of a word the list never saw; a span of only common words ("trading sdn bhd") names no single row of it.
DISTINCTIVE_IDF = 0.5
#: A typed span prefers its own list when that list's best row is within this of the overall best.
TYPE_MARGIN = 0.15
#: Words matching a span word by trigram similarity.
TOKEN_SIMILARITY = 0.6
#: One edit is allowed only in words at least this long.
EDIT_MIN_LETTERS = 4
#: Row sets whose text structures are kept (the last few), so a turn prepares only its own spans.
_PREPARED_SETS = 2


@dataclass(frozen=True)
class Span:
    text: str
    type: str | None = None


@dataclass(frozen=True)
class Candidate:
    row: LookupRow
    #: 0..1, the best signal for this row.
    score: float
    #: "exact" | "spell" | "partial" | "meaning"
    signal: str


@dataclass(frozen=True)
class Resolution:
    span: Span
    #: "resolved" | "ambiguous" | "unresolved" | "skipped"
    status: str
    #: Best first; resolved -> the row; ambiguous -> every close row.
    candidates: tuple[Candidate, ...] = field(default_factory=tuple)


def spec_key_rows(registry: Iterable[Any]) -> list[LookupRow]:
    """One row per active product spec key (`product_spec_registry.active_registry` entries): the label, the
    key spelled with spaces, and the words of its values (`merged_synonyms`: synonyms and user synonyms, minus
    the suppressed ones)."""
    from app.services.product_spec_registry import merged_synonyms

    out: list[LookupRow] = []
    for entry in registry:
        if not getattr(entry, "is_active", True):
            continue
        words = [w for ws in merged_synonyms(entry).values() for w in ws or []]
        key = str(entry.spec_key)
        label = str(getattr(entry, "label", "") or key)
        texts = tuple(dict.fromkeys(t for t in (label, key.replace("_", " "), *words) if t and _fold(t)))
        out.append(LookupRow("spec_key", key, label, texts))
    return out


class _ListIndex:
    """The texts of one list, folded and tokenised once: trigrams, word IDF, and an inverted word index."""

    def __init__(self, rows: Sequence[LookupRow]):
        self.rows = list(rows)
        #: (row index, original text, folded, trigrams, words)
        self.texts: list[tuple[int, str, str, frozenset[str], tuple[str, ...]]] = []
        for i, row in enumerate(self.rows):
            for text in dict.fromkeys(row.texts):
                folded = _fold(text)
                if folded:
                    self.texts.append((i, text, folded, candidates.trigrams(folded), tuple(folded.split())))
        distinct = {t[2] for t in self.texts}
        df: dict[str, int] = defaultdict(int)
        for folded in distinct:
            for w in set(folded.split()):
                df[w] += 1
        n = len(distinct)
        self.unknown_idf = math.log(n + 1) + 0.1
        self.df = dict(df)
        self.idf = {w: math.log((n + 1) / (c + 0.5)) + 0.1 for w, c in df.items()}
        self.inverted: dict[str, list[int]] = defaultdict(list)
        for ti, t in enumerate(self.texts):
            for w in set(t[4]):
                self.inverted[w].append(ti)
        self.text_idf = [sum(self.idf[w] for w in set(t[4])) for t in self.texts]
        self.vocab = sorted(self.idf)
        self.vocab_grams = {w: candidates.trigrams(w) for w in self.vocab}
        #: word (or the word with one letter dropped) -> the words of 4+ letters it can be one edit from
        self.deletions: dict[str, set[str]] = defaultdict(set)
        for w in self.vocab:
            self.deletions[w].add(w)
            if len(w) >= EDIT_MIN_LETTERS:
                for k in range(len(w)):
                    self.deletions[w[:k] + w[k + 1 :]].add(w)
        self._matches: dict[str, dict[str, float]] = {}

    def matching_words(self, word: str) -> dict[str, float]:
        """The vocabulary words a span word stands for, with how well: 1.0 equal, the trigram similarity when it
        is at least `TOKEN_SIMILARITY`, `1 - 1/letters` for one edit."""
        hit = self._matches.get(word)
        if hit is None:
            hit = {}
            if word in self.idf:
                hit[word] = 1.0
            grams = candidates.trigrams(word)
            for w in self.vocab:
                sim = candidates.similarity(grams, self.vocab_grams[w])
                if sim >= TOKEN_SIMILARITY:
                    hit[w] = max(hit.get(w, 0.0), sim)
            if len(word) >= EDIT_MIN_LETTERS:
                near = set(self.deletions.get(word, ()))
                for k in range(len(word)):
                    near |= self.deletions.get(word[:k] + word[k + 1 :], set())
                for w in near:
                    if len(w) >= EDIT_MIN_LETTERS and abs(len(w) - len(word)) <= 1 and w != word:
                        hit[w] = max(hit.get(w, 0.0), 1.0 - 1.0 / max(len(w), len(word)))
            self._matches[word] = hit
        return hit

    def weight(self, word: str) -> tuple[float, bool]:
        """(IDF, common) of a span word: those of the row word it matches best, the unseen-word IDF when it
        matches none."""
        hit = self.matching_words(word)
        if not hit:
            return self.unknown_idf, False
        best = max(hit, key=lambda w: (hit[w], self.idf[w]))
        return self.idf[best], self.df[best] >= 2 and self.idf[best] < DISTINCTIVE_IDF * self.unknown_idf


_prepared: dict[str, dict[str, _ListIndex]] = {}
_prepared_lock = threading.RLock()


def _prepare(rows: Sequence[LookupRow]) -> dict[str, _ListIndex]:
    key = hashlib.sha1("\x01".join(f"{r.list_name}\x00{r.key}\x00" + "\x00".join(r.texts) for r in rows).encode()).hexdigest()
    with _prepared_lock:
        built = _prepared.get(key)
        if built is None:
            by_list: dict[str, list[LookupRow]] = defaultdict(list)
            for row in rows:
                by_list[row.list_name].append(row)
            built = {name: _ListIndex(rs) for name, rs in by_list.items()}
            while len(_prepared) >= _PREPARED_SETS:
                _prepared.pop(next(iter(_prepared)))
            _prepared[key] = built
        return built


@dataclass
class _RowScore:
    row: LookupRow
    spell: float = 0.0
    exact: bool = False
    partial: float = 0.0
    #: IDF-weighted share of the row's own words the span matched, in the text that gave `partial`
    coverage: float = 0.0
    #: characters of that text: of two rows equally covered the shorter one is nearer
    length: int = 0
    meaning: float = 0.0


def _score_list(index: _ListIndex, folded: str, grams: frozenset[str]) -> dict[int, _RowScore]:
    """Spelling and partial scores of one span against every row of the list that either touches."""
    scores: dict[int, _RowScore] = {}

    def of(i: int) -> _RowScore:
        if i not in scores:
            scores[i] = _RowScore(index.rows[i])
        return scores[i]

    words = list(dict.fromkeys(folded.split()))
    weights = {w: index.weight(w) for w in words}
    if all(common for _idf, common in weights.values()):
        # only common words of this list: nothing short of the whole text names a row
        for i, _text, f, _g, _w in index.texts:
            if f == folded:
                row = of(i)
                row.spell, row.exact, row.partial, row.coverage, row.length = 1.0, True, 1.0, 1.0, len(_text)
        return scores
    for i, _text, f, g, _words in index.texts:
        s = 1.0 if f == folded else candidates.similarity(grams, g)
        if s > 0:
            row = of(i)
            row.spell = max(row.spell, s)
            row.exact = row.exact or f == folded
    total = sum(idf for idf, _c in weights.values())
    if total <= 0:
        return scores
    #: text index -> span word -> best similarity of a text word to it
    reach: dict[int, dict[str, float]] = defaultdict(dict)
    matched_words: set[str] = set()
    for w in words:
        for sw, sim in index.matching_words(w).items():
            matched_words.add(sw)
            for ti in index.inverted.get(sw, ()):
                cell = reach[ti]
                cell[w] = max(cell.get(w, 0.0), sim)
    for ti, hit in reach.items():
        i, _text, _f, _g, tokens = index.texts[ti]
        partial = sum(weights[w][0] * sim for w, sim in hit.items()) / total
        coverage = sum(index.idf[w] for w in set(tokens) if w in matched_words) / max(index.text_idf[ti], 1e-9)
        row = of(i)
        if (partial, coverage) > (row.partial, row.coverage):
            row.partial, row.coverage, row.length = partial, coverage, len(index.texts[ti][1])
    return scores


def _meaning_scores(spans: list[str], indexes: dict[str, _ListIndex], embed: Embedder | None) -> dict[tuple[str, int], dict[str, float]]:
    """span text -> {(list, row index): best cosine over the row's texts}; empty when no embedder answers."""
    if embed is None or not spans:
        return {}
    texts = sorted({t[1] for ix in indexes.values() for t in ix.texts})
    got = _meaning(embed, spans, texts)
    if got is None:
        return {}
    pidx, tidx, sim = got
    out: dict[tuple[str, int], dict[str, float]] = {}
    for name, ix in indexes.items():
        for ti, (i, text, _f, _g, _w) in enumerate(ix.texts):
            col = sim[:, tidx[text]]
            for span, p in pidx.items():
                cell = out.setdefault((name, i), {})
                cell[span] = max(cell.get(span, 0.0), float(col[p]))
    return out


def resolve(spans: Sequence[Span], rows: Sequence[LookupRow], *, embed: Embedder | None = None) -> list[Resolution]:
    """One `Resolution` per span, in input order. Never raises on an embedder failure (spelling and partial
    names still resolve); a `product_code` span is `skipped` and a span naming nothing is `unresolved`."""
    indexes = _prepare(rows) if rows else {}
    live = [s.text for s in spans if s.type != "product_code" and _fold(s.text) and s.text]
    meaning = _meaning_scores(list(dict.fromkeys(live)), indexes, embed)
    out: list[Resolution] = []
    for span in spans:
        folded = _fold(span.text)
        if span.type == "product_code":
            out.append(Resolution(span, "skipped"))
            continue
        if not folded or not indexes:
            out.append(Resolution(span, "unresolved"))
            continue
        grams = candidates.trigrams(folded)
        pool: list[tuple[float, float, int, Candidate]] = []
        for name, index in indexes.items():
            floors = FLOORS.get(name, _FLOORS_OTHER)
            scored = _score_list(index, folded, grams)
            for i in set(scored) | {i for (n, i) in meaning if n == name and span.text in meaning[(n, i)]}:
                row = scored.get(i) or _RowScore(index.rows[i])
                row.meaning = max(0.0, meaning.get((name, i), {}).get(span.text, 0.0))
                if not (row.spell >= floors["spell"] or row.partial >= floors["partial"] or row.meaning >= floors["meaning"]):
                    continue
                signals = (
                    ("exact" if row.exact else "spell", row.spell),
                    ("partial", row.partial if row.partial >= floors["partial"] else 0.0),
                    ("meaning", row.meaning),
                )
                signal, score = max(signals, key=lambda s: s[1])
                pool.append((-round(score, 2), -round(row.coverage, 2), row.length, Candidate(row.row, score, signal)))
        if not pool:
            out.append(Resolution(span, "unresolved"))
            continue
        pool.sort(key=lambda k: k[:3])
        preferred = TYPE_LIST.get(span.type or "")
        typed = [k for k in pool if k[3].row.list_name == preferred]
        if typed and pool[0][3].score - typed[0][3].score <= TYPE_MARGIN:
            pool = typed
        best = pool[0][3].score
        near = [k[3] for k in pool if best - k[3].score <= AMBIGUITY_MARGIN]
        # a row whose whole text the span equals is not tied with rows that merely contain its words
        near = [c for c in near if c.signal == "exact"] or near
        distinct = list(dict.fromkeys((c.row.list_name, c.row.key) for c in near))
        out.append(Resolution(span, "resolved" if len(distinct) == 1 else "ambiguous", tuple(near[:1] if len(distinct) == 1 else near)))
    return out
