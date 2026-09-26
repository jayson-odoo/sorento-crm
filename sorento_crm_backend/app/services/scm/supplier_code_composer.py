"""Compose a supplier code from a BARE model number (S1, `PLAN-stock-list-bare-model-codes.md`
D3-D5).

A supplier who writes a bare 型号 (`8613`, `-7055`, `8066-PP`) is not writing our code; the
supplier's TYPE lives in 品名, the BRAND in 商标, and the trap size in 规格. This module joins
those columns into what our own product code would read (`SRTWC8613-250`), so the existing
matcher (`supplier_code_matcher.py`, untouched by this file - see its module docstring) walks
its ladder against a candidate that has a chance of matching, instead of the bare `8613` four
different rows share.

**No stripping. Every Chinese word is translated, never dropped** (D3). The vocabulary is a
per-supplier `import_field_alias` table (`WORD_DOC_TYPE`), a shared row (`supplier_id` NULL)
answering for everyone unless a supplier's own row overrides it (`WordList.for_supplier`,
AC-W3). A word with no row aborts composition for that row - `compose` and `parse_spec`
return `None` - and the row's key falls back to the raw join of what the supplier wrote
(`raw_key`), which still keeps siblings with different specs apart and waits in the Supplier
codes picker for a human to answer once.

The word list's TOKEN side (what a word resolves TO - `SRT`, `WC`, `P`, `SH`, ...) is an OPEN,
shape-validated vocabulary, not a closed list (review round 1, item 4): `WORD_TOKEN_RE`
accepts any 1-10 character uppercase alphanumeric string. A closed `WORD_TOKENS` tuple would
make the owner's own promised workflow - typing `高压 -> HP` on the admin page the next time a
word shows up unbound - a code change instead of a UI row, which is exactly what D6 says this
mechanism exists to avoid.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy.orm import Session

from app.services.scm.supplier_code_matcher import _size_of, _tokens

#: `import_field_alias.doc_type` for this word list (D6).
WORD_DOC_TYPE = "supplier_inventory_word"

#: The SHAPE a word row's `field` must have (review round 1, item 4) - an open vocabulary,
#: validated by shape rather than membership in a hand-maintained list. Uppercased on write
#: (the admin API and the FE form both uppercase before this ever runs), so this only ever
#: sees what it is meant to accept.
WORD_TOKEN_RE = re.compile(r"^[A-Z0-9]{1,10}$")

#: A trap size the matcher's own rule already defines (`supplier_code_matcher._size_of`):
#: three digits, 100 to 499. Restated here as constants would drift from that rule the moment
#: either side changed it, so the function itself is imported instead (plan's own instruction).
_NON_ASCII_RUN_RE = re.compile(r"[^\x00-\x7f]+")
_MM_RE = re.compile(r"mm", re.IGNORECASE)
_LETTER_RUN_RE = re.compile(r"[A-Za-z]+")
_DIGIT_RUN_RE = re.compile(r"\d+")
#: Two or more digit runs joined by a dimension separator (`600*450*200mm`, `600x450x200mm`)
#: is a size string, never a trap - review round 1, item 2.
_DIMENSION_RE = re.compile(r"\d+\s*[*xX×]\s*\d+")
#: A composed or raw-join key this long is not a code any rung would ever bind - review
#: round 1, item 7's bound, read by the reader rather than restated there.
MAX_KEY_LENGTH = 100


def _normalize_key(word: str) -> str:
    return re.sub(r"\s+", "", (word or "").strip()).upper()


def _is_non_ascii(text: str) -> bool:
    return any(ord(ch) > 127 for ch in text)


class _Abort(Exception):
    """Internal signal: a run inside the text being translated has no word-list entry."""


@dataclass
class SpecParts:
    size: Optional[int] = None
    trap: Optional[str] = None
    extras: list[str] = field(default_factory=list)


class WordList:
    """One supplier's resolved vocabulary: alias (what the supplier wrote) -> our token.

    Lookup is case- and whitespace-insensitive (AC-W3): `SORENTO`, `sorento ` and `SORENTO`
    all resolve to the same row. Built once per upload from `for_supplier`, or handed a plain
    mapping directly for the pure-function tests.
    """

    def __init__(self, mapping: Optional[dict[str, str]] = None):
        self._by_norm: dict[str, str] = {}
        #: Raw (stripped) CJK aliases -> token, kept unnormalised for run segmentation, where
        #: the run's own characters (not upper-cased Latin) must match a supplier's word.
        self._cjk_raw: dict[str, str] = {}
        #: Longest-first, so `segment` never has to re-sort on every call (review round 1,
        #: item 11) - an upload walks hundreds of rows, each calling `segment` at least once.
        self._cjk_sorted_keys: list[str] = []
        if mapping:
            for alias, token in mapping.items():
                self._set(alias, token)

    def _set(self, alias: str, token: str) -> None:
        stripped = (alias or "").strip()
        if not stripped:
            return
        self._by_norm[_normalize_key(stripped)] = token
        if _is_non_ascii(stripped):
            is_new = stripped not in self._cjk_raw
            self._cjk_raw[stripped] = token
            if is_new:
                self._cjk_sorted_keys = sorted(self._cjk_raw, key=len, reverse=True)

    def lookup(self, word: Optional[str]) -> Optional[str]:
        if word is None:
            return None
        return self._by_norm.get(_normalize_key(word))

    def segment(self, run: str) -> Optional[list[str]]:
        """Greedy longest-match split of one non-ASCII run into known word tokens, or `None`
        the moment a position matches no known word (`180横排对冲`: `横排` resolves, `对冲`
        does not, so the whole run aborts rather than resolving to just the first half)."""
        out: list[str] = []
        i = 0
        n = len(run)
        while i < n:
            hit = next((k for k in self._cjk_sorted_keys if run.startswith(k, i)), None)
            if hit is None:
                return None
            out.append(self._cjk_raw[hit])
            i += len(hit)
        return out

    @classmethod
    def for_supplier(cls, db: Session, supplier_id: Optional[str]) -> "WordList":
        """The shared word list, overridden by this supplier's own rows (AC-W3): a supplier
        row for a word wins over the shared row on the same word.

        A `supplier_id` that is not a real id at all (review round 1, item 6) reads as the
        SHARED-only list rather than reaching the uuid column comparison, which raises
        `InvalidTextRepresentation` - not an `AppException` - and leaves the session aborted.
        """
        from sqlalchemy import or_

        from app.models.import_alias import ImportFieldAlias
        from app.services.scm.supplier_scope import is_uuid

        valid_supplier_id = supplier_id if supplier_id and is_uuid(supplier_id) else None
        condition = (
            or_(
                ImportFieldAlias.supplier_id == valid_supplier_id,
                ImportFieldAlias.supplier_id.is_(None),
            )
            if valid_supplier_id
            else ImportFieldAlias.supplier_id.is_(None)
        )
        rows = (
            db.query(ImportFieldAlias)
            .filter(ImportFieldAlias.doc_type == WORD_DOC_TYPE, condition)
            .all()
        )
        words = cls()
        # Shared rows first, then this supplier's own - added second so they overwrite a
        # shared row on the exact same alias text.
        for row in sorted(rows, key=lambda r: r.supplier_id is not None):
            words._set(row.alias, row.field)
        return words


def is_bare(model_no: Optional[str]) -> bool:
    """D1's trigger: the supplier wrote a model that starts with a digit or a sign, once
    Excel's own leading minus is accounted for. A letter-led model never composes."""
    return bool(re.match(r"^[-0-9]", (model_no or "").strip()))


def parse_spec(spec: Optional[str], words: WordList) -> Optional[SpecParts]:
    """规格 -> `SpecParts`, or `None` on an unresolvable CJK word OR a digit run this rule
    does not understand (AC-R6, review round 1 item 2).

    `mm` is noise the supplier sometimes adds and never means anything on its own. Two or
    more digit runs joined by `*`/`x`/`X`/`×` is a DIMENSION string (`600*450*200mm`,
    `600x450x200mm`), never a trap, so no trap parts at all. Otherwise: every CJK run must
    resolve through the word list - replaced by a SEPARATOR, never dropped outright, so
    `180横排250` reads as two digit runs either side of the trap word rather than fusing into
    `180250` - `横排` (anywhere) becomes the `P` trap and anything else becomes a trailing
    extra; the first 3-digit number in the matcher's own trap range is the size; leftover
    ASCII letter groups (`UF`, `A`, `PP`, `NEW`) are extras. A digit run left over once the
    size is taken - `8613`/`500` (500 is out of range), `180横排250` (`250` left after `180`
    is taken) - means this is not a trap spec this rule understands at all: abort to
    `raw_key`, rather than silently dropping stock a person never gets to see.
    """
    if spec is None:
        return SpecParts(None, None, [])
    raw = spec.strip()
    if not raw:
        return SpecParts(None, None, [])
    if _DIMENSION_RE.search(raw):
        return SpecParts(None, None, [])

    working = _MM_RE.sub("", raw)

    trap: Optional[str] = None
    extras: list[str] = []

    def _replace(match: "re.Match[str]") -> str:
        nonlocal trap
        segmented = words.segment(match.group(0))
        if segmented is None:
            raise _Abort()
        for token in segmented:
            if token == "P":
                trap = "P"
            else:
                extras.append(token)
        # A separator, never "" - an empty replacement fuses whatever digits sit either side
        # of the CJK run into one run neither the size step nor the leftover-digit guard
        # below can read correctly.
        return " "

    try:
        working = _NON_ASCII_RUN_RE.sub(_replace, working)
    except _Abort:
        return None

    size: Optional[int] = None
    for m in _DIGIT_RUN_RE.finditer(working):
        candidate = _size_of(m.group(0))
        if candidate is not None:
            size = candidate
            working = working[: m.start()] + working[m.end() :]
            break

    if _DIGIT_RUN_RE.search(working):
        return None

    extras.extend(_LETTER_RUN_RE.findall(working))

    return SpecParts(size=size, trap=trap, extras=extras)


def _translate_token(token: str, words: WordList) -> Optional[str]:
    """One `_tokens(型号)` piece, with every non-ASCII run inside it resolved through the
    word list. `RL高压` with `高压` unseeded aborts; a token with no CJK at all (`8613`, `PP`)
    passes through unchanged."""
    try:
        return _NON_ASCII_RUN_RE.sub(lambda m: _resolve_or_raise(m.group(0), words), token)
    except _Abort:
        return None


def _resolve_or_raise(run: str, words: WordList) -> str:
    segmented = words.segment(run)
    if segmented is None:
        raise _Abort()
    return "".join(segmented)


def compose(
    model_no: Optional[str],
    spec: Optional[str],
    brand: Optional[str],
    product_name: Optional[str],
    words: Optional[WordList],
) -> Optional[str]:
    """The candidate supplier code for a BARE 型号 (D5), or `None` when composition cannot
    finish - a blank/unknown brand or product name, an unresolvable CJK run in the model or
    the spec, or a model that is not bare at all (a letter-led model never composes, D1/D2)."""
    if not is_bare(model_no):
        return None
    if words is None:
        return None
    brand_word = words.lookup(brand) if brand else None
    name_word = words.lookup(product_name) if product_name else None
    if brand_word is None or name_word is None:
        return None

    raw_tokens = _tokens(model_no or "")
    # A single character is not a model number this rule can compose from with any
    # confidence - review round 1, item 2's minimum.
    if not raw_tokens or len(raw_tokens[0]) < 2:
        return None

    model_tokens: list[str] = []
    for token in raw_tokens:
        translated = _translate_token(token, words)
        if translated is None:
            return None
        model_tokens.append(translated)
    if not model_tokens:
        return None

    spec_parts = parse_spec(spec, words)
    if spec_parts is None:
        return None

    parts = [f"{brand_word}{name_word}{model_tokens[0]}", *model_tokens[1:]]
    if spec_parts.trap:
        parts.append(spec_parts.trap)
    if spec_parts.size is not None:
        parts.append(str(spec_parts.size))
    parts.extend(spec_parts.extras)
    return "-".join(parts)


def raw_key(
    model_no: Optional[str],
    spec: Optional[str],
    brand: Optional[str],
    product_name: Optional[str],
) -> str:
    """The fallback key when composition cannot resolve every word (AC-R5): the raw columns,
    present parts only, space-joined in the order the supplier's own sheet reads them - model,
    spec, brand, then product name."""
    parts = [
        (part or "").strip()
        for part in (model_no, spec, brand, product_name)
        if (part or "").strip()
    ]
    return " ".join(parts)
