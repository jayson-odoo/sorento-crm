"""CERT-LINK-CLEANUP: is a certificate-product link backed by the certificate's own text?

Pure rules over `certificate_pdf_service.printed_runs` output (card
`documentation/plans/certificates/CARD-cert-link-cleanup-08nov.md` R2 + R8, owner answer Q1 8 Nov):

- **found**: the printed code is a whole token on the PDF AND is contained in the product code as a
  contiguous run of 3+ characters with a digit (`14A` inside `CSK14A-BL`, `WB 1515` inside `SRTWB1515`).
  A code a person typed (`model_code_source = manual`) skips the containment rule.
- **check**: as found, but the code is digits only (`120` is usually a quantity or a size).
- **not_found**: the PDF has text and the rule above fails.
- **scanned**: the PDF has no text layer, cannot be checked. **no_file**: no readable current PDF.

The same normalisation as the #2245 matcher (`certificate_pdf_service.normalise`).
"""
from __future__ import annotations

from typing import Any, Optional

from app.services.certificate_pdf_service import normalise

VERDICT_FOUND = "found"
VERDICT_CHECK = "check"
VERDICT_NOT_FOUND = "not_found"
VERDICT_SCANNED = "scanned"
VERDICT_NO_FILE = "no_file"
VERDICTS = (VERDICT_FOUND, VERDICT_CHECK, VERDICT_NOT_FOUND, VERDICT_SCANNED, VERDICT_NO_FILE)

MIN_CODE_LEN = 3

#: Resolver tiers a printed certificate string may link through (Q2 (a), certificates only):
#: substring stays, gated by `_containable`; the family-prefix tier is off.
_ALWAYS_TIERS = ("exact", "product_set", "plus_split")


def _containable(norm: str) -> bool:
    return len(norm) >= MIN_CODE_LEN and any(ch.isdigit() for ch in norm)


def printed_on(text: Optional[dict], code: Optional[str]) -> bool:
    """The string is printed as a whole token. A scan or a missing file cannot say no."""
    if not text or not text.get("has_text"):
        return True
    norm = normalise(code or "")
    return bool(norm) and norm in (text.get("runs") or {})


def ingest_match_allowed(code: Optional[str], via: str) -> bool:
    """R8: may this resolver match link a product to a certificate?"""
    if via in _ALWAYS_TIERS:
        return True
    if via != "substring":
        return False
    norm = normalise(code or "")
    return _containable(norm) and not norm.isdigit()


def verdict(
    text: Optional[dict],
    *,
    model_code: Optional[str],
    model_code_source: Optional[str],
    product_code: Optional[str],
) -> tuple[str, Optional[str]]:
    """`(verdict, code used)` of one link. `text` is `printed_runs(...)`, or None when no file."""
    if text is None:
        return VERDICT_NO_FILE, model_code
    if not text.get("has_text"):
        return VERDICT_SCANNED, model_code
    runs: dict = text.get("runs") or {}
    product_norm = normalise(product_code or "")

    if model_code and model_code.strip():
        norm = normalise(model_code)
        if not norm or norm not in runs:
            return VERDICT_NOT_FOUND, model_code
        if model_code_source != "manual" and not (_containable(norm) and norm in product_norm):
            return VERDICT_NOT_FOUND, model_code
        return (VERDICT_CHECK if norm.isdigit() else VERDICT_FOUND), model_code

    # No code on the link: the longest printed run that sits inside the product code. A lettered
    # run beats a digits-only one of any length, so `check` is only the answer when nothing else is.
    best: Optional[str] = None
    best_digits: Optional[str] = None
    for start in range(len(product_norm)):
        for end in range(len(product_norm), start + MIN_CODE_LEN - 1, -1):
            piece = product_norm[start:end]
            if piece in runs and _containable(piece):
                if piece.isdigit():
                    if best_digits is None or len(piece) > len(best_digits):
                        best_digits = piece
                elif best is None or len(piece) > len(best):
                    best = piece
                break
    if best is not None:
        return VERDICT_FOUND, runs[best]
    if best_digits is not None:
        return VERDICT_CHECK, runs[best_digits]
    return VERDICT_NOT_FOUND, None


def read_text(data: Optional[bytes]) -> Optional[dict[str, Any]]:
    """`printed_runs` of the file, or None when there is no file."""
    if not data:
        return None
    from app.services.certificate_pdf_service import printed_runs

    return printed_runs(data)
