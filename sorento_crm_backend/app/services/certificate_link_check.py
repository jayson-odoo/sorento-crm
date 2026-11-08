"""CERT-LINK-CLEANUP: is a certificate-product link backed by the certificate's own text?

Pure rules over `certificate_pdf_service.printed_runs` output (card
`documentation/plans/certificates/CARD-cert-link-cleanup-08nov.md` R2 + R8, owner answer Q1 8 Nov):

- **found**: the printed code is a whole token on the PDF AND sits in the product code as a contiguous
  run of 4+ characters with a digit, on a boundary (`WB 1515` inside `SRTWB1515`, `CSK14A` inside
  `CSK14A-BL`). Boundary (crew ruling 8 Nov, on the real SPAN BPAI/1327-2024 file): a printed code that
  starts with a digit must not be preceded by a digit in the product code, and must not be followed by
  another letter or digit unless that is the end of a dash/space segment (`11C` is not in `BRD7711CP`,
  `MGB5011C`; `14A` is not in `SV-14AB`). Any code that ends in a digit must not run on into another
  digit (`CSK14` is not in `CSK140-BL`). A code a person typed (`model_code_source = manual`) or a link a
  person confirmed (`source = manual`) skips every product-side rule; the code must still be printed. The exact tiers the ingest keeps count too: the product's own code, a printed
  product-set code the product is a member of, and each part of an `A + B` code (reviewer round 1).
- **check**: as found, but the code starts with a digit, is not the full product code, and more than one
  product family across the whole active catalogue contains it (rule B-cat, crew 8 Nov: `75-RG` is in
  M459A, M460A, M461A; `32SS` in M and SRTKT; `906SS` in SRTWT and ORIWT; `162-QT` only in SRTWT, so it
  stays Found; `CatalogueFamilies`), or the code is SHORT (3 or fewer letters and digits: `14A`, `11C`; or printed only
  as a run of such short tokens: `AB 12C`, crew offline check 8 Nov) or digits only (`120`). A row number
  printed next to a model (`3 | 13A`) is never joined into it (`certificate_pdf_service._index_cells`). Never auto-Found: a person confirms it once (it becomes manual) or removes it.
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
#: A printed code this long or shorter is never auto-Found (crew ruling 8 Nov): `14A`, `11C`, `13C`.
SHORT_CODE_LEN = 3

#: Resolver tiers a printed certificate string may link through (Q2 (a), certificates only):
#: substring stays, gated by `_containable`; the family-prefix tier is off.
_ALWAYS_TIERS = ("exact", "product_set", "plus_split")


def _containable(norm: str) -> bool:
    return len(norm) >= MIN_CODE_LEN and any(ch.isdigit() for ch in norm)


def plus_parts(code: Optional[str]) -> list[str]:
    """`A + B` names two products: the normalised parts, or [] for a single code."""
    parts = [normalise(p) for p in (code or "").split("+")]
    parts = [p for p in parts if p]
    return parts if len(parts) > 1 else []


def _segments(product_code: Optional[str]) -> tuple[str, set[int]]:
    """The normalised product code, and the indexes in it where a dash/space segment ends."""
    chars: list[str] = []
    ends: set[int] = set()
    for ch in normalise_raw(product_code):
        if ch.isspace() or ch in _SEPARATORS:
            if chars:
                ends.add(len(chars))
            continue
        chars.append(ch)
    ends.add(len(chars))
    return "".join(chars), ends


def normalise_raw(value: Optional[str]) -> str:
    """Case-folded and symbol-font decoded, separators KEPT (they mark segment ends)."""
    from app.services.certificate_pdf_service import unshift

    return unshift(value or "").lower()


_SEPARATORS = set(" -.,;:()[]/")


def boundary_starts(norm: str, product_code: Optional[str]) -> list[int]:
    """Every start index of `norm` in the normalised product code that the boundary rule allows."""
    out: list[int] = []
    if not norm:
        return out
    product_norm, ends = _segments(product_code)
    start = product_norm.find(norm)
    while start != -1:
        end = start + len(norm)
        nxt = product_norm[end] if end < len(product_norm) and end not in ends else ""
        if norm[0].isdigit():
            # Only a digit in the SAME dash/space segment counts: `75-RG` in `M459-75-RG` starts a
            # segment of its own (crew re-check: it read Not found only by accident before).
            preceded = start > 0 and start not in ends and product_norm[start - 1].isdigit()
            followed = bool(nxt)
        else:
            # A code ending in a digit must not run on into another digit (`CSK14` is not in
            # `CSK140-BL`); a letter after it (`WB1515` in `SRTWB1515W`) is unchanged.
            preceded = False
            followed = norm[-1].isdigit() and nxt.isdigit()
        if not preceded and not followed:
            out.append(start)
        start = product_norm.find(norm, start + 1)
    return out


def on_boundary(norm: str, product_code: Optional[str]) -> bool:
    """Is `norm` inside the product code at a place the crew boundary rule allows (see module doc)?"""
    return bool(boundary_starts(norm, product_code))


class CatalogueFamilies:
    """Crew rule B-cat (8 Nov): which product FAMILIES a printed run appears in, across the whole
    active catalogue. Family = the normalised product code up to the start of the printed run
    (`M459A-75-RG` -> `m459a`, `SRTKT32SS` -> `srtkt`, `CB61SS-BL` -> `cb`). Built once per check job
    and memoised per run, so the catalogue is scanned once per distinct run, not once per link."""

    def __init__(self, product_codes):
        self._codes = sorted({str(c) for c in product_codes if c})
        self._normalised = [(code, normalise(code)) for code in self._codes]
        self._memo: dict[str, frozenset[str]] = {}

    def families(self, norm: str) -> frozenset[str]:
        if norm not in self._memo:
            found: set[str] = set()
            for code, code_norm in self._normalised:
                if norm not in code_norm:
                    continue
                starts = boundary_starts(norm, code)
                if starts:
                    found.add(code_norm[: starts[0]])
            self._memo[norm] = frozenset(found)
        return self._memo[norm]

    def only_family_of(self, norm: str, product_code: Optional[str]) -> bool:
        """True when the run sits in exactly ONE catalogue family and it is this product's own family
        (reviewer round 5: an inactive product is not in the catalogue, so "one family" alone could be
        somebody else's)."""
        starts = boundary_starts(norm, product_code)
        if not starts:
            return False
        own = normalise(product_code or "")[: starts[0]]
        return self.families(norm) == frozenset({own})


def _ambiguous(norm: str, product_norm: str, solid, sets, families=None, product_code=None) -> bool:
    """A backed code that a person must decide (Check, never auto-Found): short, digits only, printed
    only as short tokens, or (crew re-check 8 Nov) digit-led and not the full product code: `75-RG`
    backs `M459A-75-RG` and `M460A-75-RG` alike because the family prefix is not printed. A printed
    set code the product belongs to is explicit, so it is not digit-led ambiguous."""
    return (
        is_short(norm)
        or norm.isdigit()
        or norm not in solid
        or (
            norm[0].isdigit()
            and norm != product_norm
            and norm not in sets
            # Rule B-cat: a digit-led run that only one catalogue family contains is not ambiguous.
            and not (families is not None and families.only_family_of(norm, product_code))
        )
    )


def is_short(norm: str) -> bool:
    return len(norm) <= SHORT_CODE_LEN


def _backs(norm: str, product_code: Optional[str], *, typed: bool, set_codes) -> bool:
    """Does a printed `norm` back a link to this product? A code a person typed, the exact code, a
    set it belongs to, or a contained run of 3+ characters with a digit on a boundary."""
    product_norm = normalise(product_code or "")
    return (
        typed
        or norm == product_norm
        or norm in set_codes
        or (_containable(norm) and on_boundary(norm, product_code))
    )


def printed_on(text: Optional[dict], code: Optional[str]) -> bool:
    """The string is printed as a whole token. A scan or a missing file cannot say no."""
    if not text or not text.get("has_text"):
        return True
    norm = normalise(code or "")
    return bool(norm) and norm in (text.get("runs") or {})


def ingest_printed(text: Optional[dict], code: Optional[str], via: str, product_code: Optional[str]) -> bool:
    """R8 printed check for one resolver match. A `+` code is checked per part (parts may sit in
    separate table cells): the part that names this product must be printed."""
    if via == "plus_split":
        return printed_on(text, code) or printed_on(text, product_code)
    return printed_on(text, code)


def ingest_match_allowed(code: Optional[str], via: str, product_code: Optional[str]) -> bool:
    """R8: may this resolver match link a product to a certificate? A substring match must also
    sit on a boundary of the product code (crew ruling 8 Nov), so the ingest stops creating the
    `11C` -> `BRD7711CP` links the report would only flag."""
    if via in _ALWAYS_TIERS:
        return True
    if via != "substring":
        return False
    norm = normalise(code or "")
    return _containable(norm) and not norm.isdigit() and on_boundary(norm, product_code)


def verdict(
    text: Optional[dict],
    *,
    model_code: Optional[str],
    model_code_source: Optional[str],
    product_code: Optional[str],
    set_codes=(),
    source: Optional[str] = None,
    families: Optional[CatalogueFamilies] = None,
) -> tuple[str, Optional[str]]:
    """`(verdict, code used)` of one link. `text` is `printed_runs(...)`, or None when no file.
    `set_codes`: normalised codes of the product sets this product belongs to (a printed set code
    names its members; reviewer round 1)."""
    if text is None:
        return VERDICT_NO_FILE, model_code
    if not text.get("has_text"):
        return VERDICT_SCANNED, model_code
    runs: dict = text.get("runs") or {}
    product_norm = normalise(product_code or "")

    if model_code and model_code.strip():
        # A typed code, or a link a person confirmed (Q3: Confirm flips `source` to manual).
        typed = model_code_source == "manual" or source == "manual"
        sets = set(set_codes or ())
        parts = plus_parts(model_code) or [normalise(model_code)]
        backing = [p for p in parts if p and p in runs and _backs(p, product_code, typed=typed, set_codes=sets)]
        if not backing:
            return VERDICT_NOT_FOUND, model_code
        if typed:
            return VERDICT_FOUND, model_code
        solid = text.get("solid") or ()
        # Crew rule: "Check unless the FULL product code is printed", wherever it is on the PDF.
        full_printed = product_norm in runs and product_norm in solid
        if not full_printed and all(
            _ambiguous(p, product_norm, solid, sets, families, product_code) for p in backing
        ):
            return VERDICT_CHECK, model_code
        return VERDICT_FOUND, model_code

    # No code on the link. A link a person confirmed counts like a typed code (crew re-check: Confirm
    # must read Found on every branch): any printed run of the product code backs it.
    if source == "manual":
        confirmed: Optional[str] = None
        for start in range(len(product_norm)):
            for end in range(start + MIN_CODE_LEN, len(product_norm) + 1):
                piece = product_norm[start:end]
                if piece in runs and _containable(piece) and (confirmed is None or len(piece) > len(confirmed)):
                    confirmed = piece
        if confirmed is not None:
            return VERDICT_FOUND, runs[confirmed]
        return VERDICT_NOT_FOUND, None

    # Otherwise the longest printed run inside the product code that passes the boundary rule. Only
    # an unambiguous run is Found; a short, digits-only or digit-led one is Check at best.
    found: Optional[str] = None
    checked: Optional[str] = None
    solid = text.get("solid") or ()
    for start in range(len(product_norm)):
        for end in range(len(product_norm), start + MIN_CODE_LEN - 1, -1):
            piece = product_norm[start:end]
            if piece not in runs or not _containable(piece) or not on_boundary(piece, product_code):
                continue
            if _ambiguous(piece, product_norm, solid, (), families, product_code):
                if checked is None or len(piece) > len(checked):
                    checked = piece
            elif found is None or len(piece) > len(found):
                found = piece
    if found is not None:
        return VERDICT_FOUND, runs[found]
    if checked is not None:
        return VERDICT_CHECK, runs[checked]
    return VERDICT_NOT_FOUND, None


def wanted_for_codes(codes, product_codes=()) -> set[str]:
    """The normalised strings an ingest looks up: the requested codes, their `+` parts, and the
    product codes a `+` split matched."""
    out: set[str] = set()
    for code in list(codes) + list(product_codes):
        out.add(normalise(code or ""))
        out.update(plus_parts(code))
    out.discard("")
    return out


def wanted_for_links(links) -> set[str]:
    """What `verdict` can look up for `(model_code, product_code)` pairs: each code, and every
    3+ character run of each product code (the no-code search)."""
    out: set[str] = set()
    for model_code, product_code in links:
        if model_code:
            out.add(normalise(model_code))
            out.update(plus_parts(model_code))
        product_norm = normalise(product_code or "")
        for start in range(len(product_norm)):
            for end in range(start + MIN_CODE_LEN, len(product_norm) + 1):
                out.add(product_norm[start:end])
    out.discard("")
    return out


def read_text(data: Optional[bytes], wanted: set[str]) -> Optional[dict[str, Any]]:
    """`printed_runs` of the file, restricted to `wanted`, or None when there is no file."""
    if not data:
        return None
    from app.services.certificate_pdf_service import printed_runs

    return printed_runs(data, wanted)
