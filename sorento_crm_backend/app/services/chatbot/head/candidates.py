"""The per-turn candidate shortlist the parser picks from (CHAT-CLOSED-LISTS S2, design D2).

Code only SHORTLISTS. For the words of the current message it lists what is on file under
them: product codes (the whole code, or a code holding a word that has a digit), product
types and spec values (a registry value, its label or one of its synonyms, as whole words),
and near spellings of either (crew Q1 (a), 17 Oct: similarity only ADDS a line). Every line
says what the candidate is, so the parser chooses the kind as well as the value, or chooses
none and the bot asks. Nothing here decides what a word means, and nothing downstream binds
on a candidate: the parser's pick is validated against the lists, never against this
module's scores.

Bounded: at most `CAP_PER_WORD` code rows per word and `CAP_LINES` lines per message (a spec
line is never cut: every key that holds a value has its line, ranked by data, F3-a); one
scoped count query for the message's spec and size pairs; one whole-code query for the message plus one query per word with a digit (at most
`CODE_WORDS_PER_MESSAGE`); the registry read once per call. Runs in the
session-held phase before the parse; a product read goes through the ORM so the contact's
company and brand scope and `chat_searchable_products` apply as on every other chat read.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

HEADER = "Candidates for words of this message (each says what it is; pick one or none):"

CAP_PER_WORD = 5
CAP_LINES = 12
#: Words with a digit read for codes holding them / spelt near them, per message (one
#: query each); every other word costs nothing beyond the one whole-code query.
CODE_WORDS_PER_MESSAGE = 6
#: The longest run of words read as one phrase ("toilet bowl soft close" is two phrases).
MAX_PHRASE_WORDS = 3
#: Near spellings, as pg_trgm scores them: a spec phrase from 4 characters, a code from 3.
NEAR_PHRASE = 0.55
NEAR_CODE = 0.5
MIN_NEAR_CHARS = 4
MIN_CODE_CHARS = 3

#: Registry keys whose values say what the product IS (the category entity keeps them).
TYPE_KEYS = frozenset({"class", "product_type"})
#: The brand is its own entity kind, with its own `Known brands:` line.
SKIP_KEYS = frozenset({"brand"})

_TOKEN_RE = re.compile(r"[0-9a-z][0-9a-z\-/.]*")
_WORD_RE = re.compile(r"[0-9a-z]+")


@dataclass
class WordCandidates:
    """The candidates listed under one word or phrase of the message, best first."""

    gram: str
    position: int
    items: list[str] = field(default_factory=list)
    #: F3-a: item -> (key, value, "num" | "text") for the spec lines the value index counts.
    pairs: dict[str, tuple[str, str, str]] = field(default_factory=dict)
    #: F3-a: a number + unit word, resolved against the counts: (number, unit, keys, bare keys).
    size: tuple[str, str, list[str], set[str]] | None = None


@dataclass(frozen=True)
class _Value:
    kind: str  # "product type" | "spec" | "flag" (a boolean key, printed as a spec)
    spec_key: str
    value: str
    display: str

    def text(self) -> str:
        from app.services.chatbot_prompt_vars import candidate_text

        key, value, display = candidate_text(self.spec_key), candidate_text(self.value), candidate_text(self.display)
        if self.kind == "product type":
            return f"product type {display} ({key} = {value})"
        return f"spec {key} = {value} ({display})"


def trigrams(text: str) -> frozenset[str]:
    """pg_trgm's trigrams of `text`: lower case, each alphanumeric run padded with two
    spaces in front and one behind."""
    out: set[str] = set()
    for word in _WORD_RE.findall(text.casefold()):
        padded = f"  {word} "
        out.update(padded[i : i + 3] for i in range(len(padded) - 2))
    return frozenset(out)


def similarity(a: frozenset[str], b: frozenset[str]) -> float:
    """pg_trgm's `similarity`: shared trigrams over all trigrams."""
    union = len(a | b)
    return len(a & b) / union if union else 0.0


def _tokens(message: str) -> list[str]:
    return [w for w in (t.rstrip("-/.") for t in _TOKEN_RE.findall((message or "").casefold())) if w]


def _phrase(text: str) -> str:
    return " ".join(_WORD_RE.findall(str(text).casefold().replace("_", " ")))


def _registry(db: "Session", hidden: frozenset[str]) -> list:
    """The active registry rows minus the contact's hidden spec keys: the ONE place a hidden
    key leaves the candidate LINES (value, size and boolean lines all read through it). The
    other things the parser sees (the {{specs}} vocabulary, the Product details line) list
    registry names only."""
    from app.services.product_spec_registry import active_registry

    return [row for row in active_registry(db) if row.spec_key not in hidden]


def _vocabulary(db: "Session", hidden: frozenset[str] = frozenset()) -> tuple[dict[str, list[_Value]], dict[str, list[str]]]:
    """Every enum registry value under each of its phrases (value, label, synonyms), and
    every numeric key under the words that name it ("in 1" for `piece_count`). The class
    key is an open vocabulary: its values are its worded labels plus every class label a
    category carries."""
    from app.models.product import ProductCategory
    from app.services.product_spec_registry import (
        display_spec_value,
        merged_allowed_values,
        merged_synonyms,
    )

    phrases: dict[str, list[_Value]] = {}
    numeric: dict[str, list[str]] = {}
    for row in _registry(db, hidden):
        data_type = (row.data_type or "").lower()
        if row.spec_key in SKIP_KEYS:
            continue
        synonyms = merged_synonyms(row)
        if data_type == "numeric":
            for said in synonyms.get("_self") or []:
                key = _phrase(said)
                if key and row.spec_key not in numeric.setdefault(key, []):
                    numeric[key].append(row.spec_key)
            continue
        if data_type == "boolean":
            # R6-2: a boolean key's registry phrases per value (`{"true": [phrases]}`); only a value
            # the registry holds phrases for is offered, so no false line is ever invented.
            for value, said in synonyms.items():
                if value == "_self":
                    continue
                entry = _Value("flag", row.spec_key, str(value), str(row.label or row.spec_key))
                for word in said or []:
                    key = _phrase(word)
                    if key and entry not in phrases.setdefault(key, []):
                        phrases[key].append(entry)
            continue
        if data_type != "enum":
            continue
        labels = dict(getattr(row, "value_labels", None) or {})
        kind = "product type" if row.spec_key in TYPE_KEYS else "spec"
        values = [*merged_allowed_values(row), *(v for v in synonyms if v != "_self")]
        if row.spec_key == "class":
            values += [label for (label,) in db.query(ProductCategory.class_label).distinct() if label]
        for value in dict.fromkeys(values):
            display = display_spec_value(value, labels)
            entry = _Value(kind, row.spec_key, str(value), display)
            for said in (value, display, *(synonyms.get(value) or [])):
                key = _phrase(said)
                if key and entry not in phrases.setdefault(key, []):
                    phrases[key].append(entry)
    return phrases, numeric


def type_values(db: "Session") -> dict[str, str]:
    """The product types a candidate line can name (`product type T (K = V)`), as
    `{casefolded V: T}`: what grounding checks a class pick against under the gate."""
    phrases, _numeric = _vocabulary(db)
    return {
        value.value.casefold(): value.display
        for values in phrases.values()
        for value in values
        if value.kind == "product type"
    }


def _is_number(word: str) -> bool:
    return bool(re.fullmatch(r"\d+(\.\d+)?", word))


def _numeric_candidates(numeric: dict[str, list[str]], grams: list[tuple[int, str]], words: list[str]) -> list[WordCandidates]:
    """A numeric key's own words in the message, with the number beside them when there is
    one ("4 in 1" -> piece_count 4); the reading of the number is still the parser's."""
    out: list[WordCandidates] = []
    for position, gram in grams:
        keys = numeric.get(gram)
        if not keys:
            continue
        end = position + len(gram.split())
        if position > 0 and _is_number(words[position - 1]):
            number, shown, at = words[position - 1], f"{words[position - 1]} {gram}", position - 1
        elif end < len(words) and _is_number(words[end]) and not _is_number(gram.split()[-1]):
            number, shown, at = words[end], f"{gram} {words[end]}", position
        else:
            number, shown, at = None, gram, position
        items = [f"spec {key} = {number}" if number else f"spec {key} (a number)" for key in keys]
        out.append(WordCandidates(gram=shown, position=at, items=items))
    return out


def _value_candidates(db: "Session", tokens: list[str], hidden: frozenset[str] = frozenset()) -> list[WordCandidates]:
    vocab, numeric = _vocabulary(db, hidden)
    if not vocab and not numeric:
        return []
    words = [_phrase(t) for t in tokens]
    grams: list[tuple[int, str]] = []
    for size in range(MAX_PHRASE_WORDS, 0, -1):
        for start in range(len(words) - size + 1):
            gram = " ".join(w for w in words[start : start + size] if w)
            if gram:
                grams.append((start, gram))
    numbered = _numeric_candidates(numeric, grams, words)

    best: dict[_Value, tuple[int, float, int, str]] = {}  # value -> (exact, score, position, gram)
    for position, gram in grams:
        for value in vocab.get(gram, []):
            if best.get(value, (0,))[0] == 0 or len(gram) > len(best[value][3]):
                best[value] = (1, 1.0, position, gram)
    # A word inside a longer phrase that is on file exactly is that phrase's word ("flexible"
    # in "double flexible", "basin" in "basin mixer"): the longer phrase is what was said, so
    # neither the shorter exact reading nor a near spelling of it is listed.
    # A boolean flag's phrase never hides a product type's word ("toilet" in "smart toilet").
    exact_spans = [(p, p + len(g.split())) for v, (e, _s, p, g) in best.items() if e and v.kind != "flag"]

    def inside_longer(position: int, gram: str) -> bool:
        end = position + len(gram.split())
        return any(lo <= position and end <= hi and hi - lo > end - position for lo, hi in exact_spans)

    best = {v: held for v, held in best.items() if not inside_longer(held[2], held[3])}
    phrase_trigrams = {phrase: trigrams(phrase) for phrase in vocab}
    for position, gram in grams:
        if len(gram.replace(" ", "")) < MIN_NEAR_CHARS or gram in vocab:
            continue
        end = position + len(gram.split())
        if any(lo <= position and end <= hi for lo, hi in exact_spans):
            continue
        gram_trigrams = trigrams(gram)
        size = len(gram.split())
        for phrase, values in vocab.items():
            # A near spelling is the same number of words spelt differently; one word is
            # never "near" a longer phrase that merely contains it ("seat", "toilet seat").
            if len(phrase.split()) != size:
                continue
            score = similarity(gram_trigrams, phrase_trigrams[phrase])
            if score < NEAR_PHRASE:
                continue
            for value in values:
                held = best.get(value)
                if held is None or (held[0] == 0 and score > held[1]):
                    best[value] = (0, score, position, gram)

    by_gram: dict[str, WordCandidates] = {}
    for value, (exact, score, position, gram) in sorted(
        best.items(), key=lambda item: (-item[1][0], -item[1][1], item[0].kind != "product type")
    ):
        entry = by_gram.setdefault(gram, WordCandidates(gram=gram, position=position))
        entry.items.append(value.text() if exact else f"near {value.text()}")
        if exact and value.kind != "product type":
            entry.pairs[value.text()] = (value.spec_key, value.value, "flag" if value.kind == "flag" else "text")
    return list(by_gram.values()) + numbered


def _code_label(code: str, name: str | None, holds: bool, holding: str | None = None) -> str:
    from app.services.chatbot_prompt_vars import candidate_text

    # Product rows are staff / import text: one line each and free of the line's own
    # delimiters, so a stored newline can never start a line of its own in the user turn
    # (security review, 17 Oct 2026) and a name or code can never add an item to the line.
    code, name = candidate_text(code), candidate_text(name or "")
    label = f"code {code} ({name})" if name else f"code {code}"
    if holding:
        # R5-2: a code that only CONTAINS the word is not the word's own code; it says so.
        label += f', holding "{candidate_text(holding)}"'
    return label if holds else f"near {label}"


def _code_candidates(db: "Session", tokens: list[str]) -> list[WordCandidates]:
    """Codes on file under each word: the whole code for any word, in ONE query for the
    whole message; for a word with a digit (the first `CODE_WORDS_PER_MESSAGE` of them) also
    every code holding it and the codes spelt near it, one query each."""
    from sqlalchemy import case, func, or_

    from app.models.product import Product, chat_searchable_products

    norm = func.lower(func.regexp_replace(Product.product_code, r"[-\s]+", "", "g"))
    words = {position: re.sub(r"[-\s]+", "", token) for position, token in enumerate(tokens)}
    words = {p: w for p, w in words.items() if len(w) >= 2}
    coded = [p for p, w in words.items() if any(ch.isdigit() for ch in w) and len(w) >= MIN_CODE_CHARS]
    coded = coded[:CODE_WORDS_PER_MESSAGE]
    whole_only = sorted({w for p, w in words.items() if p not in coded})
    by_word: dict[str, list[tuple[str, str | None]]] = {}
    if whole_only:
        rows = (
            db.query(norm.label("word"), Product.product_code, Product.product_name)
            .filter(chat_searchable_products(), norm.in_(whole_only))
            .order_by(Product.product_code)
            .limit(CAP_PER_WORD * len(whole_only))
            .all()
        )
        for word, code, name in rows:
            held = by_word.setdefault(word, [])
            if len(held) < CAP_PER_WORD:
                held.append((code, name))
    out: list[WordCandidates] = []
    for position, word in words.items():
        token = tokens[position]
        if position in coded:
            sim = func.similarity(norm, word)
            rows = (
                db.query(
                    Product.product_code,
                    Product.product_name,
                    norm.contains(word, autoescape=True).label("holds"),
                    (norm == word).label("whole"),
                )
                .filter(chat_searchable_products(), or_(norm.contains(word, autoescape=True), sim >= NEAR_CODE))
                .order_by(
                    case((norm == word, 0), (norm.startswith(word, autoescape=True), 1),
                         (norm.contains(word, autoescape=True), 2), else_=3),
                    sim.desc(),
                    Product.product_code,
                )
                .limit(CAP_PER_WORD)
                .all()
            )
            items = [_code_label(code, name, holds, token if holds and not whole else None) for code, name, holds, whole in rows]
        else:
            items = [_code_label(code, name, True) for code, name in by_word.get(word, [])]
        if items:
            out.append(WordCandidates(gram=token, position=position, items=items))
    return out


_SIZE_RE = re.compile(r"(\d+(?:\.\d+)?)([a-z]+)")


def _unit_index(db: "Session", hidden: frozenset[str] = frozenset()) -> dict[str, tuple[list[str], set[str]]]:
    """Every numeric registry key under its own unit, in name order, with the keys a size given
    alone can mean (the registry's `matches_bare_size` flag, or a key a class scopes):
    `{"mm": (["dim_length", ...], {"dim_width", ...})}`. Data only."""
    units: dict[str, tuple[list[str], set[str]]] = {}
    for row in _registry(db, hidden):
        unit = str(getattr(row, "unit", None) or "").strip().casefold()
        if (row.data_type or "").lower() != "numeric" or not unit or row.spec_key in SKIP_KEYS:
            continue
        keys, bare = units.setdefault(unit, ([], set()))
        keys.append(row.spec_key)
        if getattr(row, "matches_bare_size", False) or (getattr(row, "applies_when", None) or {}).get("class"):
            bare.add(row.spec_key)
    return {unit: (sorted(set(keys)), bare) for unit, (keys, bare) in units.items()}


def _support(
    db: "Session", pairs: set[tuple[str, str, str]], held_ids: list[str] | None
) -> dict[tuple[str, str, str], tuple[int, int]]:
    """F3-a: for each (key, value, kind) pair, the chat-searchable products in the contact's
    scope that hold it and how many of the held family do. ONE query for every pair, through
    the scoped Product join; each pair holds the way the set search matches it
    (`membership_clause`: a number as a number, a list-valued spec by containment, a yes as true)."""
    if not pairs:
        return {}
    from sqlalchemy import case, func

    from app.models.product import Product, chat_searchable_products
    from app.models.product_spec import ProductSpecifications
    from app.services.chatbot.head.held_family import _family_ids
    from app.services.product_spec_search import membership_clause

    family = _family_ids(db, held_ids) if held_ids else set()
    in_family = ProductSpecifications.product_id.in_(list(family) or ["00000000-0000-0000-0000-000000000000"])
    ordered = sorted(pairs)
    columns = []
    for key, value, kind in ordered:
        typed = float(value) if kind == "num" else (value.lower() == "true") if kind == "flag" else value
        holds = membership_clause({key: [typed]})
        columns.append(func.coalesce(func.sum(case((holds, 1), else_=0)), 0))
        columns.append(func.coalesce(func.sum(case((holds & in_family, 1), else_=0)), 0))
    row = (
        db.query(*columns)
        .select_from(ProductSpecifications)
        .join(Product, Product.id == ProductSpecifications.product_id)
        .filter(chat_searchable_products())
        .one()
    )
    return {pair: (int(row[2 * i]), int(row[2 * i + 1])) for i, pair in enumerate(ordered)}


def _by_data(counts: dict, pair: tuple[str, str, str]) -> tuple[int, int, str]:
    """The rank of a spec line among the keys of one word: the held family's key first, then
    the most products holding it, then the key name as a stable tiebreak."""
    total, in_family = counts.get(pair, (0, 0))
    return (-(in_family > 0), -total, pair[0])


def _size_candidates(
    db: "Session", tokens: list[str], hidden: frozenset[str] = frozenset()
) -> tuple[list[WordCandidates], set[int]]:
    """SIZE-AS-CODE (crew, 18 Oct 2026): a number with a unit a numeric key carries ("600mm",
    "600 mm") is that key's value, offered as `spec K = N` for each such key, and the words
    it spans are never code words (a code merely holding "600mm" is not what was said). The
    units are the registry's own (`product_spec_registry.unit`). The entries come back
    unresolved (`size` set): which keys hold the number is the value index's count."""
    units = _unit_index(db, hidden)
    if not units:
        return [], set()
    out: list[WordCandidates] = []
    spanned: set[int] = set()
    for position, token in enumerate(tokens):
        joined = _SIZE_RE.fullmatch(token)
        if joined and joined.group(2) in units:
            number, unit_name, shown, span = joined.group(1), joined.group(2), token, {position}
        elif _is_number(token) and position + 1 < len(tokens) and tokens[position + 1] in units:
            unit_name = tokens[position + 1]
            number, shown, span = token, f"{token} {unit_name}", {position, position + 1}
        else:
            continue
        keys, bare = units[unit_name]
        out.append(WordCandidates(gram=shown, position=position, size=(number, unit_name, keys, bare)))
        spanned |= span
    return out, spanned


def _resolve(entries: list[WordCandidates], counts: dict) -> None:
    """F3-a: a size's lines are the keys that hold the number, ranked by data (every key of the
    unit, in name order, when none does), the bare-size line first when a flagged key holds it
    (R6-1); a shared phrase's exact spec lines are ranked by data in the slots they hold."""
    for entry in entries:
        if entry.size:
            number, unit_name, keys, bare = entry.size
            holders = [k for k in keys if counts.get((k, number, "num"), (0, 0))[0] > 0]
            ranked = sorted(holders, key=lambda k: _by_data(counts, (k, number, "num"))) or keys
            entry.items = [f"spec {key} = {number}" for key in ranked]
            if bare & set(holders):
                entry.items.insert(0, f"size {number} {unit_name} (no dimension named)")
            continue
        slots = [n for n, item in enumerate(entry.items) if item in entry.pairs]
        for slot, item in zip(slots, sorted((entry.items[n] for n in slots), key=lambda i: _by_data(counts, entry.pairs[i]))):
            entry.items[slot] = item


def shortlist(
    db: "Session", message: str, held_ids: list[str] | None = None, hidden: frozenset[str] = frozenset()
) -> list[WordCandidates]:
    """The candidates for every word of `message` that has any, in message order. A key in
    `hidden` (the contact's hidden spec keys) is named by no line."""
    tokens = _tokens(message)
    if not tokens:
        return []
    sizes, spanned = _size_candidates(db, tokens, hidden)
    values = _value_candidates(db, tokens, hidden)
    # The pairs that need data: every size's keys, and the exact spec lines of a word two keys share.
    wanted = {(k, n, "num") for e in sizes for n in [e.size[0]] for k in e.size[2]}
    for entry in values:
        if len({pair[0] for pair in entry.pairs.values()}) > 1:
            wanted.update(entry.pairs.values())
    _resolve(sizes + values, _support(db, wanted, held_ids))
    code_words = list(dict.fromkeys(t for position, t in enumerate(tokens) if position not in spanned))
    merged: dict[str, WordCandidates] = {}
    for entry in sizes + values + _code_candidates(db, code_words):
        held = merged.setdefault(entry.gram, WordCandidates(gram=entry.gram, position=entry.position))
        held.items.extend(item for item in entry.items if item not in held.items)
    ordered = sorted(merged.values(), key=lambda e: (e.position, -len(e.gram)))
    for entry in ordered:
        exact = [i for i in entry.items if not i.startswith("near ")]
        rows = exact + [i for i in entry.items if i.startswith("near ")]
        # Only an exact spec line is never cut (every holding key keeps its line); every code
        # and near row shares the cap.
        capped = [i for i in rows if i.startswith(("code ", "near "))][:CAP_PER_WORD]
        entry.items = [i for i in rows if not i.startswith(("code ", "near ")) or i in capped]
    return ordered


def candidate_lines(entries: list[WordCandidates]) -> list[str]:
    """The block for the parser's user turn: a header and one line per word, capped; empty
    when nothing in the message is on file (the user turn is then unchanged)."""
    lines = [f'- "{entry.gram}": ' + "; ".join(entry.items) for entry in entries if entry.items]
    if not lines:
        return []
    return [HEADER, *lines[:CAP_LINES]]
