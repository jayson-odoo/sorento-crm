"""What a page of a customer PO MEANS, with no database in sight (P4, P5).

Split out of ``project_po_extraction_service`` on the 2026-08-12 audit: these are the
pure functions - number discipline, note classification, code spelling, re-scan
identity - and keeping them import-clean of the ORM is what keeps them testable in
microseconds and reusable by whichever service needs to read the same paper.

The doctrine they carry is the module's one sentence: **the AI proposes, arithmetic
decides.** Nothing a vision model says about a number is believed until
``qty * unit_price == amount`` is recomputed here, in Decimal, from the values it gave.
"""
from __future__ import annotations

import hashlib
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

# Three string constants, not the ORM: the outcome rank below has to speak the same
# vocabulary the quotation model does, and retyping the strings here is how the two
# would silently diverge.
from app.models.projects import (
    QUOTATION_OUTCOME_LOST,
    QUOTATION_OUTCOME_OPEN,
    QUOTATION_OUTCOME_WON,
)
from app.models.project_so import ProjectPOLine
from app.services.error_handler import AppException

STATE_QUEUED = "queued"
STATE_RUNNING = "running"
STATE_DONE = "done"
STATE_FAILED = "failed"

INTERP_CANCEL = "cancel_line"
INTERP_AMEND_CODE = "amend_code"
INTERP_AMEND_DESCRIPTION = "amend_description"
INTERP_SUCCESSOR_PO = "successor_po"
INTERP_SIGNATURE = "signature"
INTERP_OTHER = "other"

INTERPRETATIONS = frozenset(
    {
        INTERP_CANCEL,
        INTERP_AMEND_CODE,
        INTERP_AMEND_DESCRIPTION,
        INTERP_SUCCESSOR_PO,
        INTERP_SIGNATURE,
        INTERP_OTHER,
    }
)

# Keys inside ``interpretation_json``. Named as constants because the review screen reads
# and writes the same four, and a mismatch here is invisible until a person clicks Accept
# and nothing happens.
KEY_LINE_NOS = "line_nos"  # which printed lines the note is about
KEY_CODE = "code"  # the stock code an amend-code note means
KEY_DESCRIPTION = "description"  # the description an amend-description note means
KEY_PO_NUMBER = "po_number"  # the purchase order a note points at
# Older spellings, read but never written. An edit posted with the previous key must not
# silently apply nothing.
_LEGACY_KEYS = {
    KEY_LINE_NOS: ("lines",),
    KEY_CODE: ("stock_code",),
    KEY_PO_NUMBER: ("successor_po_number",),
}

# A scan is the normal case; a PO photographed on a phone is the other one.
ALLOWED_MIMES = {
    "application/pdf": "pdf",
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/png": "png",
}
_EXTENSION_MIMES = {
    "pdf": "application/pdf",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
}

# One attachment type for every project document, so the Files screens group them
# instead of growing a type per document kind.
ATTACHMENT_TYPE_CODE = "project_document"
ATTACHMENT_TYPE_NAME = "Project Document"
ATTACHMENT_ENTITY_TYPE = "project_po_version"

# Only ever visible for the moment between phase 1's "a PO needs its number" guard and
# the blanking below. The contract says an un-numbered upload creates the PO with an
# empty number and lets the confirm screen agree to the extracted one.
_PENDING_NUMBER = "(pending extraction)"

_CENTS = Decimal("0.01")

# A code-shaped token. Used to recover the real stock code from the description,
# because the customer's own code COLUMN is truncated by their printing (`SRTWC86`,
# `2155-BLUE`) and trusting that column alone yields a PO that resolves to nothing
# (AC-M1b, measured).
_CODE_TOKEN = re.compile(r"[A-Z0-9]{2,}(?:-[A-Z0-9]+)*")

# A PO number in the client's house style: three or more slash-separated segments, e.g.
# HQ/26/05/087. Deliberately not two, so the literal "P/O" in a pencil note is not read
# as a document number.
_PO_NUMBER_IN_TEXT = re.compile(
    r"\b[A-Z0-9]{1,10}(?:/[A-Z0-9]{1,10}){2,}\b", re.IGNORECASE
)

# How the note announces the number it is pointing at. Needed because these notes open
# with the date they were written -- "15/5/26 - Cancel item (7) ... Refer to New P/O
# HQ/26/05/087" -- and `15/5/26` is itself three slash-separated segments. Taking the
# first match would file the DATE as the successor purchase order.
_PO_NUMBER_TRIGGER = re.compile(
    r"(?:p\s*/\s*o|purchase\s+order|order\s+no|\bpo\b)", re.IGNORECASE
)

# Words a reader would use for each act, matched against the model's own "meaning"
# together with the verbatim text. The meaning is paraphrased differently page to page;
# the text is the thing that does not move.
_CANCEL_WORDS = ("cancel", "void", "delete", "struck", "strike", "cross out")
_SIGNATURE_WORDS = ("signature", "signed", "chop", "initial")
_AMEND_WORDS = ("amend", "change", "revise", "correct", "replace", "update")

_HEADER_TOTAL_KEYS = ("total", "grand_total", "total_amount", "po_total", "amount_total")

# How good a quotation scope is as the thing a confirmed PO should be checked against. A
# won scope is what a PO follows from; a lost one is still a document the customer was
# given, so it is a last resort rather than no candidate at all.
_OUTCOME_RANK = {
    QUOTATION_OUTCOME_WON: 0,
    QUOTATION_OUTCOME_OPEN: 1,
    QUOTATION_OUTCOME_LOST: 2,
}
_OUTCOME_RANK_DEFAULT = 1

# Where the extractor's header keys land on our own header block.
_HEADER_ALIASES = {
    "po_number": ("po_number", "purchase_order_no", "po_no"),
    "po_date": ("po_date", "date"),
    "term": ("term", "terms", "term_days", "payment_term"),
    "sales_person": ("sales_person", "salesperson", "sales"),
    "customer_order_ref": ("cust_order_no", "customer_order_ref", "customer_order_no"),
    "remark": ("remark", "remarks", "note", "notes"),
}



# --------------------------------------------------------------- number handling


def _to_decimal(value: Any) -> Optional[Decimal]:
    """A model number to Decimal, via ``str``, never via ``float``.

    ``Decimal(392.85)`` is 392.85000000000000852651282912120223045349121093750 and a
    total built from 52 of those disagrees with the paper by cents. ``Decimal("392.85")``
    does not, and the cent is the whole proof.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        return value
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return None


def _money(value: Optional[Decimal]) -> Decimal:
    return (value or Decimal("0")).quantize(_CENTS)


def _payload_value(payload: Dict[str, Any], key: str) -> Any:
    """Read one ``interpretation_json`` key, tolerating its older spelling."""
    if payload.get(key) not in (None, "", []):
        return payload[key]
    for legacy in _LEGACY_KEYS.get(key, ()):
        if payload.get(legacy) not in (None, "", []):
            return payload[legacy]
    return None


def _reason(exc: AppException) -> str:
    """``AppException`` stuffs its sentence into ``HTTPException.detail`` as a dict, so
    there is no ``.message`` attribute to read."""
    detail = exc.detail
    if isinstance(detail, dict):
        return str(detail.get("message") or "")
    return str(detail or "")


def _int_or_none(value: Any) -> Optional[int]:
    """First integer in the value. ``"60 DAYS"`` is a term of 60."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    match = re.search(r"-?\d+", str(value))
    return int(match.group(0)) if match else None


def _is_description_fragment(item: Dict[str, Any]) -> bool:
    """Is this payload the tail of the row above rather than a row?

    A real line always carries the customer's printed item number or money, and in
    practice both. A fragment carries description text and no number of any kind, which
    is what the tail of a wrapped description looks like once the page it lands on is
    read on its own.

    The stock code cell is deliberately NOT part of the test. On the client's own scan,
    item 49 finishes on the next page as "GRATING" and the model put "??2-6" in the code
    column, misreading the ink bleeding through from the row above. Requiring an empty
    code cell let that through as a 52nd line. A code with no money and no item number
    beside it is spill from the same wrap, so it is dropped: the line above already
    carries the code the customer actually printed.
    """
    if not str(item.get("description") or "").strip():
        return False
    if _int_or_none(item.get("no")) is not None:
        return False
    return not any(
        _to_decimal(item.get(key)) is not None
        for key in ("qty", "unit_price", "amount")
    )


def arithmetic_ok(
    qty: Optional[Decimal], unit_price: Optional[Decimal], amount: Optional[Decimal]
) -> Optional[bool]:
    """``qty * unit_price == amount`` to two decimals, computed here.

    ``None`` when the page did not yield all three numbers. That is a different problem
    from a wrong one and must never count as a pass: a missing number is something a
    person types, a mismatch is something they reconcile.
    """
    if qty is None or unit_price is None or amount is None:
        return None
    return (qty * unit_price).quantize(_CENTS) == amount.quantize(_CENTS)


def _computed_amount(line: ProjectPOLine) -> Decimal:
    """Our own figure for a line: ``qty * unit_price``, falling back to the printed
    amount when the page did not yield both factors, so a short page understates
    nothing."""
    qty = _to_decimal(line.qty)
    unit_price = _to_decimal(line.unit_price)
    if qty is not None and unit_price is not None:
        return (qty * unit_price).quantize(_CENTS)
    return _money(_to_decimal(line.amount))


def _parse_date(value: Any) -> Optional[date]:
    """ISO first, then day-first, which is how every document here is written."""
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    if not text:
        return None
    for pattern in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y", "%d-%m-%y", "%d.%m.%Y"):
        try:
            return datetime.strptime(text, pattern).date()
        except ValueError:
            continue
    return None


# ----------------------------------------------------------------- text handling


def normalise_annotation_text(text: Optional[str]) -> str:
    """Alphanumerics only, lowercased.

    Punctuation is dropped rather than kept because one pencil note reads as
    "cancel - refer to New P/O HQ/26/05/087" on the first scan and
    "cancel , refer to new P/O HQ/26/05/087." on the second. Keeping punctuation would
    make those two different notes and re-propose a decision somebody already made.
    """
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())


def _int_list(values: Optional[Iterable[Any]]) -> List[int]:
    out: List[int] = []
    for value in values or []:
        try:
            out.append(int(str(value).strip()))
        except (TypeError, ValueError):
            continue
    return out


def dedup_key(
    written_date: Optional[str],
    refers_to_lines: Optional[Sequence[Any]],
    raw_text: Optional[str],
) -> str:
    """Identity of a handwritten note across re-scans (D11, AC-D5)."""
    digest = hashlib.sha1(normalise_annotation_text(raw_text).encode()).hexdigest()
    lines = ",".join(str(n) for n in sorted(_int_list(refers_to_lines)))
    return f"{(written_date or '').strip()}|{lines}|{digest}"[:180]


def successor_po_number(text: Optional[str]) -> Optional[str]:
    """The PO a pencil note points forward to: `refer to New P/O HQ/26/05/087`.

    Read from the phrase that announces it rather than from the first slash-separated
    token, because these notes open with the date they were written and a date looks
    exactly like a PO number to a regex. Failing that, a candidate carrying a letter is
    taken, since a bare `26/1/26` is a date and nothing else.
    """
    body = text or ""
    candidates = [(match.start(), match.group(0).upper()) for match in _PO_NUMBER_IN_TEXT.finditer(body)]
    if not candidates:
        return None
    for trigger in _PO_NUMBER_TRIGGER.finditer(body):
        for start, candidate in candidates:
            if start >= trigger.end():
                return candidate
    for _start, candidate in candidates:
        if any(character.isalpha() for character in candidate):
            return candidate
    return None


def _looks_like_code(token: str) -> bool:
    """Long enough, and mixing letters with digits. Filters the English out: `CANCEL`
    and `NEW` are code-shaped to a regex and are not codes."""
    return (
        len(token) >= 4
        and any(character.isdigit() for character in token)
        and any(character.isalpha() for character in token)
    )


def _squash(text: Optional[str]) -> str:
    """A code with its punctuation dropped, for comparing spellings of one product.

    `SRTFH15CR` and `SRTFH15-CR` are the same thing written by two people. Nothing here
    reorders or truncates, so two codes that squash alike really are the same code.
    """
    return re.sub(r"[^A-Z0-9]", "", (text or "").upper())


def _code_tokens(text: Optional[str]) -> List[str]:
    """The parts of a code, so a reordering can be recognised.

    The client writes `B2155-BLUE-NL` for what we stock as `B2155-NL-BLUE`. Same
    product, same parts, different order, and comparing the SET of parts sees that
    while comparing the strings never will.
    """
    return [part for part in re.split(r"[^A-Z0-9]+", (text or "").upper()) if part]


def _proposed_code(text: Optional[str]) -> Optional[str]:
    """The code an amend-code note seems to be naming.

    The LAST code-shaped token, because these notes are written as "change SRTWC8613-RL
    to SRTWC8608-RL" and the replacement comes second. A guess is acceptable here and
    only here: the card is a proposal, and a person either accepts it or edits it.
    """
    tokens = [
        token
        for token in _CODE_TOKEN.findall((text or "").upper())
        if _looks_like_code(token)
    ]
    return tokens[-1] if tokens else None


def classify_annotation(
    text: Optional[str],
    meaning: Optional[str],
    refers_to_lines: Optional[Sequence[Any]],
    model_kind: Optional[str] = None,
    model_payload: Optional[Dict[str, Any]] = None,
) -> Tuple[str, Dict[str, Any]]:
    """Read a note into one of the six interpretations, plus what applying it needs.

    **The MODEL's classification wins when it gave one.** The vision model has already
    read the page - it saw the strike-through, the arrow, the position of the note
    against the line - and asking it for a ``kind`` from the fixed vocabulary is one
    more field on an answer it is already writing. The keyword pass below re-derives
    the same decision from the note's TEXT alone, which loses everything the model saw
    and breaks the day the client writes "batal" instead of "cancel". It survives only
    as the FALLBACK: for prompt versions that predate the ``kind`` field, and for the
    odd answer where the model returns something outside the vocabulary.

    Even under a model kind, the structured extras are cross-checked here: a successor
    PO number or a proposed code the model names is taken, but where it names none the
    regexes still try, so an older prompt loses nothing.

    Cancellation is tested first in the fallback because it is the only reading that
    removes money, and a note that both cancels and names a successor ("cancel - refer
    to New P/O HQ/26/05/087") is ONE act by one hand: two cards for it would ask the
    reader the same question twice, so the successor rides along in
    ``interpretation_json`` and is applied by the same accept.
    """
    blob = f"{meaning or ''} {text or ''}".lower()
    lines = _int_list(refers_to_lines)
    extras = model_payload or {}
    # Structured extras: the model's answer first, the regex second, so a prompt version
    # that predates the fields loses nothing and a model that read the arrow wins.
    successor = (
        str(extras.get("successor_po_number") or "").strip().upper() or None
    ) or successor_po_number(text)
    payload: Dict[str, Any] = {KEY_LINE_NOS: lines}
    if successor:
        # One key for "the PO this note points at", whether the note cancels and
        # redirects or only redirects. Two keys meaning the same thing is how the screen
        # and the service end up disagreeing about which one to read.
        payload[KEY_PO_NUMBER] = successor

    kind = str(model_kind or "").strip().lower() or None
    if kind in INTERPRETATIONS:
        if kind == INTERP_AMEND_CODE:
            proposed = (
                str(extras.get("proposed_code") or "").strip().upper() or None
            ) or _proposed_code(text)
            if proposed:
                payload[KEY_CODE] = proposed
        return kind, payload

    # ------------- fallback: the note's text alone, by keyword. See the docstring.
    if any(word in blob for word in _CANCEL_WORDS):
        return INTERP_CANCEL, payload
    if any(word in blob for word in _SIGNATURE_WORDS):
        return INTERP_SIGNATURE, payload
    if successor:
        return INTERP_SUCCESSOR_PO, payload

    amending = any(word in blob for word in _AMEND_WORDS)
    if amending and "code" in blob:
        proposed = _proposed_code(text)
        if proposed:
            payload[KEY_CODE] = proposed
        return INTERP_AMEND_CODE, payload
    if amending and "desc" in blob:
        return INTERP_AMEND_DESCRIPTION, payload
    return INTERP_OTHER, payload


