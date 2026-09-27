"""Grounding: every descriptor the parser emitted, mapped onto the specification registry.

Fix round 8 on PR #833 (owner retest of round 7, 27 Sep 2026): "is it the parser is not
bounded by what the system has as a spec? like it doesn't know colour is colour one meh,
why it become document type one". The parser had entity kinds for a product, a category,
a brand and a document type, and none for a specification value, so every descriptor it
could not place went into `attachment_type`: "pink colour" came back a photo, "thickness
1.2 mm" a technical drawing, and "gunmetal basin" stayed one category token no set could
be scoped by.

The prompt now teaches a `specification` kind rendered from the registry
(`chatbot_parser_prompt.render_prompt_blocks`), and this module is the deterministic half
that runs after every parse, whatever kind the parser picked:

  * a `category` / `product_type` token keeps only what the thing IS (class and type
    words, "basin"); every other registry word in it becomes a `specification` entity
    ("gunmetal" -> Finish or colour: Gunmetal);
  * an `attachment_type` token stays one only when its words are on the attachment-type
    list (a type name, an alias the owner entered, a certificate word or scheme); anything
    else is grounded like any other descriptor, never read as a document;
  * a `specification` token the parser emitted is checked against the registry: its key
    must exist and its value must be one of that key's choices (or a number, for a
    numeric key);
  * a word next to a key's own word that is none of its choices ("pink colour", "f trap")
    is an UNKNOWN value of that key, said back with the ones the registry knows.

No word list lives here. The registry's keys, labels, choices, synonyms and units, the
class vocabulary and the attachment-type table decide; staff editing any of them on
Product Specifications changes what grounds, with no prompt or code change.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover
    from sqlalchemy.orm import Session

#: The entity kind a grounded descriptor carries (parser prompt, `chatbot_entity_kinds`).
SPECIFICATION_HINT = "specification"
#: Older replays and fixtures spell it short.
_SPEC_HINTS = frozenset({SPECIFICATION_HINT, "spec"})
#: The kinds whose raw can hold a descriptor glued to what the thing is.
_CLASS_HINTS = frozenset({"category", "product_type"})
_ATTACHMENT_HINT = "attachment_type"

#: Registry keys that are not descriptors: the class and the type are what the thing IS
#: (they stay in the category token), and the brand is its own entity kind.
_NOT_DESCRIPTOR_KEYS = frozenset({"class", "brand", "product_type"})

#: Words a key's LABEL carries that do not name the key ("Finish or colour", "Number of
#: bowls", "Has a drainer board"). Grammar, not vocabulary.
_LABEL_GRAMMAR = frozenset(
    {"or", "of", "and", "a", "an", "the", "in", "with", "has", "is", "number", "comes", "set", "per", "type"}
)

_TOKEN_RE = re.compile(r"\d+(?:\.\d+)?|[a-z]+", re.IGNORECASE)
_NUMBER_RE = re.compile(r"^\d+(?:\.\d+)?$")


def _near(a: str, b: str) -> bool:
    """One typo apart: one insert, delete, substitution or swap of two neighbours, on
    words of five letters or more ("thicnkess" is "thickness", "kitchne" is "kitchen",
    "color" is "colour"). Shorter words must match exactly: "tap" and "cap" are two
    different things."""
    if a == b:
        return True
    if min(len(a), len(b)) < 5 or abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        diff = [i for i, (x, y) in enumerate(zip(a, b)) if x != y]
        if len(diff) == 1:
            return True
        return len(diff) == 2 and diff[1] == diff[0] + 1 and a[diff[0]] == b[diff[1]] and a[diff[1]] == b[diff[0]]
    short, long_ = (a, b) if len(a) < len(b) else (b, a)
    return any(long_[:i] + long_[i + 1 :] == short for i in range(len(long_)))


@dataclass
class _Key:
    key: str
    label: str
    data_type: str
    unit: str | None
    #: phrase (words joined by one space) -> stored value, for enum, boolean and the
    #: worded numbers of a numeric key ("double bowl" -> 2).
    phrases: dict[str, Any] = field(default_factory=dict)
    #: words that name the key itself ("colour", "finish", "thickness", "thick", "trap")
    names: set[str] = field(default_factory=set)
    #: words that end two or more of its phrases ("trap" in "p trap" / "s trap"): a word
    #: in front of one is in a value position
    heads: set[str] = field(default_factory=set)
    #: the words that stand in front of each head word in a known phrase
    modifiers: dict[str, set[str]] = field(default_factory=dict)
    known: list[str] = field(default_factory=list)


@dataclass
class Vocabulary:
    keys: list[_Key]
    type_phrases: set[str]
    class_phrases: set[str]
    class_words: set[str]
    #: every word any key's choices or names use: never an unknown value of another key
    known_words: set[str]
    attachment_words: set[str]
    brand_words: set[str]


def _words(text: Any) -> list[str]:
    return [w.lower() for w in _TOKEN_RE.findall(str(text or ""))]


def load_vocabulary(db: "Session") -> Vocabulary:
    """The registry, the class vocabulary and the attachment-type list, read once per
    turn through the readers every other consumer uses (`active_registry`,
    `merged_synonyms`, `merged_allowed_values`, `display_spec_value`)."""
    from app.models.product import ProductCategory
    from app.models.resources import AttachmentType
    from app.services.product_class_signal import CLASS_SYNONYMS, stored_class_labels
    from app.services.product_spec_registry import (
        active_registry,
        display_spec_value,
        merged_allowed_values,
        merged_synonyms,
    )
    from app.services.product_spec_search import SELF_SYNONYM_KEY, brand_names

    keys: list[_Key] = []
    type_phrases: set[str] = set()
    class_words: set[str] = set()
    class_phrases: set[str] = set()
    for label, synonyms in CLASS_SYNONYMS.items():
        class_phrases.update(" ".join(_words(p)) for p in [label, *synonyms])
    class_phrases.update(" ".join(_words(label)) for label in stored_class_labels(db))
    for label, synonyms in db.query(ProductCategory.class_label, ProductCategory.search_synonyms).filter(
        ProductCategory.class_label.isnot(None)
    ):
        class_phrases.update(" ".join(_words(p)) for p in [label, *(synonyms or [])])

    for row in active_registry(db):
        synonyms = merged_synonyms(row)
        if row.spec_key == "class":
            for value, phrases in synonyms.items():
                class_phrases.update(" ".join(_words(p)) for p in [value, *phrases])
            continue
        if row.spec_key == "product_type":
            for value, phrases in synonyms.items():
                for phrase in [str(value).replace("_", " "), *phrases]:
                    if _words(phrase):
                        type_phrases.add(" ".join(_words(phrase)))
            continue
        if row.spec_key in _NOT_DESCRIPTOR_KEYS:
            continue
        data_type = (row.data_type or "").lower()
        entry = _Key(key=row.spec_key, label=row.label or row.spec_key, data_type=data_type, unit=row.unit)
        for value, phrases in synonyms.items():
            if value == SELF_SYNONYM_KEY:
                for phrase in phrases:
                    entry.names.update(_words(phrase))
                continue
            stored: Any = value
            if data_type == "boolean":
                stored = str(value).strip().lower() in {"true", "yes", "1"}
            elif data_type == "numeric":
                try:
                    number = float(value)
                except (TypeError, ValueError):
                    continue
                stored = int(number) if number.is_integer() else number
            spoken = [*phrases] if data_type != "enum" else [str(value).replace("_", " "), *phrases]
            for phrase in spoken:
                words = _words(phrase)
                if words:
                    entry.phrases.setdefault(" ".join(words), stored)
        entry.names.update(w for w in _words(entry.label) if w not in _LABEL_GRAMMAR and not w.isdigit())
        entry.names.update(w for w in row.spec_key.split("_") if len(w) >= 4 and w not in _LABEL_GRAMMAR)
        enders: dict[str, set[Any]] = {}
        for phrase, value in entry.phrases.items():
            words = phrase.split()
            if len(words) >= 2:
                enders.setdefault(words[-1], set()).add(str(value))
        entry.heads = {w for w, values in enders.items() if len(values) >= 2}
        for phrase in entry.phrases:
            words = phrase.split()
            if len(words) >= 2 and words[-1] in entry.heads:
                entry.modifiers.setdefault(words[-1], set()).add(words[-2])
        if data_type == "enum":
            labels = dict(getattr(row, "value_labels", None) or {})
            entry.known = sorted({display_spec_value(v, labels) for v in merged_allowed_values(row)})
        keys.append(entry)

    class_phrases.discard("")
    class_words = {w for phrase in class_phrases for w in phrase.split()}
    # A word that names a class or a type is never a key's own name ("basin" in "High
    # basin", "shower" in "Shower union"): it says what the thing is.
    type_words = {w for phrase in type_phrases for w in phrase.split()}
    for entry in keys:
        entry.names -= class_words | type_words

    attachment_words: set[str] = set()
    for (name,) in db.query(AttachmentType.type_name).all():
        attachment_words.update(_singular(w) for w in _words(name))
    from app.services.chatbot.lanes.business.predicate import _BARE_CERT_WORDS

    attachment_words.update(_BARE_CERT_WORDS)
    brand_words = {w for name in brand_names(db) for w in _words(name)}
    known_words = set(class_words) | type_words
    for entry in keys:
        known_words |= entry.names
        for phrase in entry.phrases:
            known_words.update(phrase.split())
    return Vocabulary(
        keys=keys,
        type_phrases=type_phrases,
        class_phrases=class_phrases,
        class_words=class_words,
        known_words=known_words,
        attachment_words=attachment_words,
        brand_words=brand_words,
    )


def _singular(word: str) -> str:
    return word[:-1] if len(word) > 3 and word.endswith("s") and not word.endswith("ss") else word


def _display(key: _Key, value: Any) -> str:
    from app.services.product_spec_registry import display_spec_value

    shown = display_spec_value(value)
    return f"{shown} {key.unit}" if key.unit and key.data_type == "numeric" else shown


@dataclass
class Grounded:
    """One descriptor the registry placed (`value` set) or could not (`value` None)."""

    key: str
    label: str
    said: str
    value: Any = None
    unit: str | None = None
    known: list[str] = field(default_factory=list)
    #: the registry's own words for the value ("gunmetal" for a typed "gunmetl")
    words: str | None = None

    def entity(self, template: dict[str, Any]) -> dict[str, Any]:
        return {
            **{k: template.get(k) for k in ("current_message", "confident", "hint_confident", "quantity")},
            "raw": self.said,
            "hint": SPECIFICATION_HINT,
            "canonical_code": None if self.value is None else str(self.value),
            "spec_key": self.key,
            "spec_value": self.value,
            "spec_unit": self.unit,
            "spec_label": self.label,
            "spec_words": self.words,
            "spec_known": list(self.known) if self.value is None else [],
        }


def _covered_by_class(tokens: list[str], vocab: Vocabulary) -> set[int]:
    """Token positions that belong to what the thing IS: every class word, and every type
    phrase ("kitchen tap", "close coupled"), where the whole phrase is said. A word of a
    class phrase on its own ("bowl" of "toilet bowl") is not covered: "double bowl" is a
    bowl count."""
    covered: set[int] = set()
    for phrase in vocab.class_phrases | vocab.type_phrases:
        words = phrase.split()
        for start in range(len(tokens) - len(words) + 1):
            if tokens[start : start + len(words)] == words:
                covered.update(range(start, start + len(words)))
    return covered


def ground_words(text: str, vocab: Vocabulary, *, keep: set[int] | None = None) -> tuple[list[Grounded], set[int]]:
    """Every descriptor `text` names, and the token positions they used.

    Longest registry phrase first, over all keys at once, so "rose gold" is never read as
    "gold" and "under counter" never as "counter". Then numbers with a key's own word
    ("thickness 1.2 mm", "600mm long"), then a word beside a key's own word that is none
    of its choices ("pink colour", "f trap"). Positions in `keep` (the class and type
    words) are never taken."""
    tokens = _words(text)
    keep = set(keep or ())
    used: set[int] = set()
    out: list[Grounded] = []

    def free(i: int) -> bool:
        return i not in used and i not in keep

    # 1. Registry phrases, longest first; a one-typo single word of five letters or more.
    candidates: list[tuple[int, str, _Key, Any]] = []
    for entry in vocab.keys:
        for phrase, value in entry.phrases.items():
            candidates.append((len(phrase.split()), phrase, entry, value))
    candidates.sort(key=lambda c: -c[0])
    for size, phrase, entry, value in candidates:
        words = phrase.split()
        for start in range(len(tokens) - size + 1):
            span = range(start, start + size)
            if not all(free(i) for i in span):
                continue
            window = tokens[start : start + size]
            exact = window == words
            if not exact and not (size == 1 and _near(window[0], words[0]) and window[0] not in vocab.class_words):
                continue
            taken = set(span)
            # A key word right beside its value is part of what was said ("gunmetal colour").
            for j in (start - 1, start + size):
                if 0 <= j < len(tokens) and free(j) and any(_near(tokens[j], name) for name in entry.names):
                    taken.add(j)
            used.update(taken)
            if not any(g.key == entry.key and g.value == value for g in out):
                said = " ".join(tokens[i] for i in sorted(taken))
                unit = entry.unit if entry.data_type == "numeric" else None
                out.append(Grounded(entry.key, entry.label, said, value, unit, words=phrase))

    # 2. A number beside a numeric key's own word, with its unit when one is said.
    for entry in vocab.keys:
        if entry.data_type != "numeric":
            continue
        for i, token in enumerate(tokens):
            if not free(i) or not any(_near(token, name) for name in entry.names):
                continue
            number_at = next(
                (j for j in (i + 1, i + 2, i - 1, i - 2) if 0 <= j < len(tokens) and free(j) and _NUMBER_RE.match(tokens[j])),
                None,
            )
            if number_at is None:
                continue
            span = {i, number_at}
            unit_at = number_at + 1
            if entry.unit and unit_at < len(tokens) and free(unit_at) and tokens[unit_at] == entry.unit.lower():
                span.add(unit_at)
            number = float(tokens[number_at])
            value = int(number) if number.is_integer() else number
            used.update(span)
            said = " ".join(tokens[min(span) : max(span) + 1])
            out.append(Grounded(entry.key, entry.label, said, value, entry.unit))

    # 3. An unknown value: a word beside a key's own word that is none of its choices.
    #    Beside a word the key's phrases END with ("t trap"), only in a value position
    #    (the shape of the words that stand there, `_in_value_position`); beside the
    #    key's NAME ("pink colour", "colour pink"), whatever the word is.
    from app.services.product_spec_search import _in_value_position

    for entry in vocab.keys:
        if entry.data_type != "enum":
            continue
        for i, token in enumerate(tokens):
            if not free(i):
                continue
            is_head = token in entry.heads
            is_name = any(_near(token, name) for name in entry.names)
            if not (is_head or is_name):
                continue
            sides = (i - 1,) if is_head and not is_name else (i - 1, i + 1)
            for j in sides:
                if not (0 <= j < len(tokens)) or not free(j):
                    continue
                word = tokens[j]
                if _NUMBER_RE.match(word) or word in vocab.brand_words or word in _STOPWORDS or word in vocab.known_words:
                    continue
                if is_head and not is_name and not _in_value_position(word, entry.modifiers.get(token, set())):
                    continue
                said = f"{word} {token}" if is_head and j == i - 1 else word
                used.update({i, j})
                out.append(Grounded(entry.key, entry.label, said, None, None, list(entry.known)))
                break
    return out, used


#: Words that sit around a descriptor without being one ("any", "with", "in").
_STOPWORDS = frozenset(
    {
        "any", "with", "in", "the", "a", "an", "of", "for", "and", "or", "which", "what", "got", "has",
        "have", "is", "are", "ada", "yang", "dalam", "type", "only", "some", "all", "one", "item", "items",
    }
)


def _on_attachment_list(db: "Session", raw: str, vocab: Vocabulary) -> bool:
    """Is `raw` a document type the system has? A type name's words (singular or plural,
    "photo" for Product Photos), a certificate word or scheme, or an alias the owner
    entered on System > Lookup Sets."""
    from app.services.chatbot.lanes.business.predicate import _CERT_RE
    from app.services.product_predicate_service import _lookup_resolve

    words = [_singular(w) for w in _words(raw) if w not in _STOPWORDS]
    if not words:
        return False
    if all(w in vocab.attachment_words for w in words) or _CERT_RE.search(raw):
        return True
    return bool(_lookup_resolve(db, "attachment_type_alias", raw))


def _corrected_class(db: "Session", text: str, vocab: Vocabulary) -> str:
    """A class phrase with one typo per word put right against the class vocabulary
    ("kitchne sink" -> "kitchen sink"), only when the corrected phrase names a class and
    the typed one does not. Otherwise the text as typed."""
    from app.services.product_class_signal import resolve_classes_for_term

    if not text or resolve_classes_for_term(db, text):
        return text
    fixed = []
    for word in text.split():
        low = word.lower()
        near = next((w for w in sorted(vocab.class_words) if low not in vocab.class_words and _near(low, w)), None)
        fixed.append(near or word)
    candidate = " ".join(fixed)
    return candidate if candidate != text and resolve_classes_for_term(db, candidate) else text


def _remainder(raw: str, used: set[int]) -> str:
    """`raw` without the tokens at `used`, trimmed of stopwords at either end."""
    tokens = _TOKEN_RE.findall(str(raw or ""))
    kept = [t for i, t in enumerate(tokens) if i not in used]
    while kept and kept[0].lower() in _STOPWORDS:
        kept.pop(0)
    while kept and kept[-1].lower() in _STOPWORDS:
        kept.pop()
    return " ".join(kept)


def _validate(entity: dict[str, Any], vocab: Vocabulary) -> list[Grounded]:
    """A `specification` entity the parser emitted, checked against the registry: a key
    it knows and a value among that key's choices, else grounded from its raw words."""
    key_name = str(entity.get("spec_key") or "").strip()
    value = entity.get("spec_value")
    raw = str(entity.get("raw") or "").strip()
    entry = next((k for k in vocab.keys if k.key == key_name), None)
    if entry is not None and value not in (None, ""):
        said = raw or str(value)
        if entry.data_type == "numeric":
            try:
                number = float(str(value).split()[0])
            except (TypeError, ValueError, IndexError):
                number = None
            if number is not None:
                return [Grounded(entry.key, entry.label, said, int(number) if number.is_integer() else number, entry.unit)]
        else:
            spoken = " ".join(_words(value))
            if entry.data_type == "boolean" and isinstance(value, bool):
                return [Grounded(entry.key, entry.label, said, value)]
            if spoken in entry.phrases:
                return [Grounded(entry.key, entry.label, said, entry.phrases[spoken], words=spoken)]
            for phrase, stored in entry.phrases.items():
                if str(stored).lower() == str(value).strip().lower() or str(stored).replace("_", " ").lower() == spoken:
                    return [Grounded(entry.key, entry.label, said, stored, words=phrase)]
    found, _ = ground_words(raw or str(value or ""), vocab)
    if found:
        return found
    if entry is not None and entry.data_type == "enum":
        return [Grounded(entry.key, entry.label, raw or str(value or ""), None, None, list(entry.known))]
    return []


def ground(db: "Session", verdict: dict[str, Any], *, vocab: Vocabulary | None = None) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """The verdict with every descriptor grounded, and a note per change for the trace.

    Entities the registry says nothing about are returned untouched, in place: a turn
    with no descriptor is byte-identical to the parse."""
    entities = verdict.get("entities")
    if not isinstance(entities, list) or not entities:
        return verdict, []
    touched = [
        e
        for e in entities
        if isinstance(e, dict)
        and str(e.get("hint") or "").strip().lower() in (_CLASS_HINTS | _SPEC_HINTS | {_ATTACHMENT_HINT})
    ]
    if not touched:
        return verdict, []
    vocab = vocab or load_vocabulary(db)
    out: list[Any] = []
    notes: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    def add(grounded: list[Grounded], template: dict[str, Any]) -> None:
        for g in grounded:
            mark = (g.key, str(g.value) if g.value is not None else f"?{g.said}")
            if mark in seen:
                continue
            seen.add(mark)
            out.append(g.entity(template))

    for entity in entities:
        if not isinstance(entity, dict):
            out.append(entity)
            continue
        hint = str(entity.get("hint") or "").strip().lower()
        raw = str(entity.get("raw") or "").strip()
        if hint in _SPEC_HINTS:
            grounded = _validate(entity, vocab)
            add(grounded, entity)
            notes.append({"from": hint, "raw": raw, "to": [g.__dict__ for g in grounded]})
            continue
        if hint in _CLASS_HINTS and raw:
            tokens = _words(raw)
            keep = _covered_by_class(tokens, vocab)
            grounded, used = ground_words(raw, vocab, keep=keep)
            if not grounded:
                fixed = _corrected_class(db, raw, vocab)
                if fixed != raw:
                    out.append({**entity, "raw": fixed})
                    notes.append({"from": hint, "raw": raw, "to": fixed})
                else:
                    out.append(entity)
                continue
            rest = _corrected_class(db, _remainder(raw, used), vocab)
            if rest:
                out.append({**entity, "raw": rest, "canonical_code": None})
            add(grounded, entity)
            notes.append({"from": hint, "raw": raw, "to": [rest, *[g.__dict__ for g in grounded]]})
            continue
        if hint == _ATTACHMENT_HINT and raw and not _on_attachment_list(db, raw, vocab):
            tokens = _words(raw)
            grounded, used = ground_words(raw, vocab, keep=_covered_by_class(tokens, vocab))
            rest = _remainder(raw, used)
            if rest and _covered_by_class(_words(rest), vocab):
                out.append({**entity, "raw": _corrected_class(db, rest, vocab), "hint": "category", "canonical_code": None})
                rest = ""
            if not grounded and rest:
                # Named by nothing the system holds: not a document type, not a value of
                # any key. Said back as a descriptor it does not know, never a document.
                grounded = [Grounded("", "", rest)]
            add(grounded, entity)
            notes.append({"from": hint, "raw": raw, "to": [g.__dict__ for g in grounded]})
            continue
        out.append(entity)
    if not notes:
        return verdict, []
    return {**verdict, "entities": out}, notes


def specification_entities(entities: Any) -> list[dict[str, Any]]:
    """The grounded `specification` entities of a verdict, in order."""
    return [
        e
        for e in (entities or [])
        if isinstance(e, dict) and str(e.get("hint") or "").strip().lower() in _SPEC_HINTS
    ]


def scope_word(entity: dict[str, Any]) -> str | None:
    """The registry's own words for a grounded enum or boolean value, the way a scope
    term is written ("gunmetal", "under counter", "p trap"). None for a number (it
    travels as a spec, `spec_bound`) and for an unknown value."""
    value = entity.get("spec_value")
    if value is None or isinstance(value, (int, float)) and not isinstance(value, bool):
        return None
    return str(entity.get("spec_words") or "").strip() or str(value).replace("_", " ")
