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

`WORD_TOKENS` is the closed vocabulary of tokens the word list may resolve TO - our own prefix
letters (`SRT`, `C`, `M`), our own product-family letters (`WC`, `WCX`, `WCY`, `WB`, `SC`) and
the trap-size token (`P`, "横排" - a P-trap laid flat, our own code's `-P-` segment) plus room
for a suffix word the owner has already named (`SH`, for 对冲 on the DAFUYUAN word list). A
brand-new KIND of word (say `UR` for urinals) is a one-line change here; a new SPELLING of an
existing one is a UI row (D6).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy.orm import Session

from app.services.scm.supplier_code_matcher import _size_of, _tokens

#: `import_field_alias.doc_type` for this word list (D6).
WORD_DOC_TYPE = "supplier_inventory_word"

#: The closed vocabulary a word row may resolve TO. `canonical_fields(WORD_DOC_TYPE)` reads
#: this list directly, so the admin API and page accept exactly these fields and nothing else.
WORD_TOKENS = ("SRT", "C", "M", "WC", "WCX", "WCY", "WB", "SC", "P", "SH")

#: A trap size the matcher's own rule already defines (`supplier_code_matcher._size_of`):
#: three digits, 100 to 499. Restated here as constants would drift from that rule the moment
#: either side changed it, so the function itself is imported instead (plan's own instruction).
_NON_ASCII_RUN_RE = re.compile(r"[^\x00-\x7f]+")
_MM_RE = re.compile(r"mm", re.IGNORECASE)
_LETTER_RUN_RE = re.compile(r"[A-Za-z]+")


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
        if mapping:
            for alias, token in mapping.items():
                self._set(alias, token)

    def _set(self, alias: str, token: str) -> None:
        stripped = (alias or "").strip()
        if not stripped:
            return
        self._by_norm[_normalize_key(stripped)] = token
        if _is_non_ascii(stripped):
            self._cjk_raw[stripped] = token

    def lookup(self, word: Optional[str]) -> Optional[str]:
        if word is None:
            return None
        return self._by_norm.get(_normalize_key(word))

    def segment(self, run: str) -> Optional[list[str]]:
        """Greedy longest-match split of one non-ASCII run into known word tokens, or `None`
        the moment a position matches no known word (`180横排对冲`: `横排` resolves, `对冲`
        does not, so the whole run aborts rather than resolving to just the first half)."""
        keys = sorted(self._cjk_raw, key=len, reverse=True)
        out: list[str] = []
        i = 0
        n = len(run)
        while i < n:
            hit = next((k for k in keys if run.startswith(k, i)), None)
            if hit is None:
                return None
            out.append(self._cjk_raw[hit])
            i += len(hit)
        return out

    @classmethod
    def for_supplier(cls, db: Session, supplier_id: Optional[str]) -> "WordList":
        """The shared word list, overridden by this supplier's own rows (AC-W3): a supplier
        row for a word wins over the shared row on the same word."""
        from sqlalchemy import or_

        from app.models.import_alias import ImportFieldAlias

        condition = (
            or_(
                ImportFieldAlias.supplier_id == str(supplier_id),
                ImportFieldAlias.supplier_id.is_(None),
            )
            if supplier_id
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
    """规格 -> `SpecParts`, or `None` on an unresolvable CJK word (AC-R6).

    `mm` is noise the supplier sometimes adds and never means anything on its own; `*` means
    a dimension string (`600*450*200mm`), never a trap, so no trap parts at all; the first
    3-digit number in the matcher's own trap range is the size; every CJK run must resolve
    through the word list, `横排` (anywhere) becoming the `P` trap and anything else becoming
    a trailing extra; leftover ASCII letter groups (`UF`, `A`, `PP`, `NEW`) are extras too.
    """
    if spec is None:
        return SpecParts(None, None, [])
    raw = spec.strip()
    if not raw:
        return SpecParts(None, None, [])
    if "*" in raw:
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
        return ""

    try:
        working = _NON_ASCII_RUN_RE.sub(_replace, working)
    except _Abort:
        return None

    size: Optional[int] = None
    for m in re.finditer(r"\d+", working):
        candidate = _size_of(m.group(0))
        if candidate is not None:
            size = candidate
            working = working[: m.start()] + working[m.end() :]
            break

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

    model_tokens: list[str] = []
    for token in _tokens(model_no or ""):
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
