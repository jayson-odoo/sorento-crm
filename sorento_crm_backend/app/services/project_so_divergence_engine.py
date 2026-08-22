"""Comparing our sales order against AutoCount's copy of it (P8a, AC-N1..N3).

No database, no session, no clock. Our document and theirs go in, a per-row verdict comes
out. The match back, the persistence and the resolution live in
``project_so_ingest_service.py`` and ``project_so_divergence_service.py``; this file is the
part worth pinning as a table of cases.

Three rules carry it.

**Pairing is on `(product code, delivery date)`, then on product code alone.** AutoCount
renumbers on import, so pairing by line number would report a reordered but identical
document as every line changed. Pairing on the product alone as a second pass is what makes
a moved delivery date read as ONE line whose date changed rather than a deletion plus an
insertion.

**A different product code is a removal plus an addition, never a field edit.** There is no
honest way to say which of our lines `CB6634` corresponds to when we sold `CB6633`. The
reviewer is shown both rows and decides.

**Comparison happens at the scale the column stores.** Quantities are 4dp, unit prices 5dp,
money 2dp. A difference in a decimal place the database cannot hold is not a difference
anybody can act on, and reporting one would send a CS looking for a change that is not there.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence, Tuple

SCOPE_HEADER = "header"
SCOPE_LINE = "line"

PRESENCE_BOTH = "both"
PRESENCE_OURS_ONLY = "ours_only"
PRESENCE_THEIRS_ONLY = "theirs_only"

# The scales the columns actually store (`project_sales_order_lines`).
_QTY = Decimal("0.0001")
_PRICE = Decimal("0.00001")
_MONEY = Decimal("0.01")

# AC-N1, in the order a reviewer reads them.
_LINE_FIELDS = ("qty", "unit_price", "delivery_date")
_HEADER_FIELDS = ("customer_code", "customer_po_no", "terms", "total_amount")


def _q(value: Optional[Decimal], scale: Decimal) -> Optional[str]:
    if value is None:
        return None
    return str(Decimal(value).quantize(scale))


def _d(value: Optional[date]) -> Optional[str]:
    return value.isoformat() if value else None


def _s(value: Optional[str]) -> Optional[str]:
    """Blank and absent are the same absence on a document."""
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


@dataclass(frozen=True)
class OurLine:
    so_line_id: str
    line_no: int
    product_code: Optional[str]
    qty: Decimal
    unit_price: Decimal
    delivery_date: Optional[date] = None
    description: Optional[str] = None
    uom: Optional[str] = None


@dataclass(frozen=True)
class TheirLine:
    line_no: Optional[int]
    product_code: Optional[str]
    qty: Decimal
    unit_price: Decimal
    delivery_date: Optional[date] = None
    description: Optional[str] = None
    uom: Optional[str] = None


@dataclass(frozen=True)
class OurHeader:
    customer_code: Optional[str] = None
    customer_po_no: Optional[str] = None
    terms: Optional[str] = None
    total_amount: Optional[Decimal] = None


@dataclass(frozen=True)
class TheirHeader:
    doc_no: Optional[str] = None
    customer_code: Optional[str] = None
    customer_po_no: Optional[str] = None
    terms: Optional[str] = None
    total_amount: Optional[Decimal] = None


@dataclass
class ComparedRow:
    scope: str
    presence: str
    ours: Dict[str, Any]
    theirs: Dict[str, Any]
    differing_fields: List[str] = field(default_factory=list)
    so_line_id: Optional[str] = None
    line_no: Optional[int] = None
    product_code: Optional[str] = None

    @property
    def is_difference(self) -> bool:
        """A row present on one side only IS the difference, with no field to name."""
        return self.presence != PRESENCE_BOTH or bool(self.differing_fields)


@dataclass
class DivergenceReport:
    rows: List[ComparedRow]

    @property
    def compared_count(self) -> int:
        return len(self.rows)

    @property
    def differing_count(self) -> int:
        return sum(1 for row in self.rows if row.is_difference)

    @property
    def agreeing_count(self) -> int:
        return self.compared_count - self.differing_count

    @property
    def has_differences(self) -> bool:
        return self.differing_count > 0


def _our_payload(line: OurLine) -> Dict[str, Any]:
    return {
        "product_code": _s(line.product_code),
        "description": line.description,
        "qty": _q(line.qty, _QTY),
        "unit_price": _q(line.unit_price, _PRICE),
        "uom": _s(line.uom),
        "delivery_date": _d(line.delivery_date),
        "line_no": line.line_no,
    }


def _their_payload(line: TheirLine) -> Dict[str, Any]:
    return {
        "product_code": _s(line.product_code),
        "description": line.description,
        "qty": _q(line.qty, _QTY),
        "unit_price": _q(line.unit_price, _PRICE),
        "uom": _s(line.uom),
        "delivery_date": _d(line.delivery_date),
        "line_no": line.line_no,
    }


def _pair(
    ours: Sequence[OurLine], theirs: Sequence[TheirLine]
) -> Tuple[List[Tuple[OurLine, TheirLine]], List[OurLine], List[TheirLine]]:
    """Two passes: exact `(code, date)`, then code alone, in order of appearance."""
    remaining_ours = list(ours)
    remaining_theirs = list(theirs)
    pairs: List[Tuple[OurLine, TheirLine]] = []

    for key in (
        lambda line: (_s(line.product_code), _d(line.delivery_date)),
        lambda line: (_s(line.product_code),),
    ):
        buckets: Dict[Any, List[TheirLine]] = {}
        for line in remaining_theirs:
            buckets.setdefault(key(line), []).append(line)

        still_ours: List[OurLine] = []
        for line in remaining_ours:
            bucket = buckets.get(key(line))
            if bucket:
                pairs.append((line, bucket.pop(0)))
            else:
                still_ours.append(line)

        remaining_ours = still_ours
        remaining_theirs = [line for bucket in buckets.values() for line in bucket]
        # Order of appearance survives the bucketing, which matters for the second pass.
        remaining_theirs.sort(key=lambda line: theirs.index(line))

    return pairs, remaining_ours, remaining_theirs


def _compare_fields(
    ours: Dict[str, Any], theirs: Dict[str, Any], fields: Sequence[str]
) -> List[str]:
    return [name for name in fields if ours.get(name) != theirs.get(name)]


def compare(
    our_header: OurHeader,
    our_lines: Sequence[OurLine],
    their_header: TheirHeader,
    their_lines: Sequence[TheirLine],
) -> DivergenceReport:
    """Our document against theirs: one row per compared line, plus one header row."""
    rows: List[ComparedRow] = []

    ours_payload = {
        "customer_code": _s(our_header.customer_code),
        "customer_po_no": _s(our_header.customer_po_no),
        "terms": _s(our_header.terms),
        "total_amount": _q(our_header.total_amount, _MONEY),
    }
    theirs_payload = {
        "doc_no": _s(their_header.doc_no),
        "customer_code": _s(their_header.customer_code),
        "customer_po_no": _s(their_header.customer_po_no),
        "terms": _s(their_header.terms),
        "total_amount": _q(their_header.total_amount, _MONEY),
    }
    rows.append(
        ComparedRow(
            scope=SCOPE_HEADER,
            presence=PRESENCE_BOTH,
            ours=ours_payload,
            theirs=theirs_payload,
            differing_fields=_compare_fields(ours_payload, theirs_payload, _HEADER_FIELDS),
        )
    )

    pairs, only_ours, only_theirs = _pair(our_lines, their_lines)

    for our_line, their_line in pairs:
        ours_line_payload = _our_payload(our_line)
        theirs_line_payload = _their_payload(their_line)
        rows.append(
            ComparedRow(
                scope=SCOPE_LINE,
                presence=PRESENCE_BOTH,
                ours=ours_line_payload,
                theirs=theirs_line_payload,
                differing_fields=_compare_fields(
                    ours_line_payload, theirs_line_payload, _LINE_FIELDS
                ),
                so_line_id=our_line.so_line_id,
                line_no=our_line.line_no,
                product_code=_s(our_line.product_code),
            )
        )

    for our_line in only_ours:
        rows.append(
            ComparedRow(
                scope=SCOPE_LINE,
                presence=PRESENCE_OURS_ONLY,
                ours=_our_payload(our_line),
                theirs={},
                so_line_id=our_line.so_line_id,
                line_no=our_line.line_no,
                product_code=_s(our_line.product_code),
            )
        )

    for their_line in only_theirs:
        rows.append(
            ComparedRow(
                scope=SCOPE_LINE,
                presence=PRESENCE_THEIRS_ONLY,
                ours={},
                theirs=_their_payload(their_line),
                so_line_id=None,
                line_no=their_line.line_no,
                product_code=_s(their_line.product_code),
            )
        )

    return DivergenceReport(rows=rows)


def line_fingerprint(items: Sequence[Tuple[Optional[str], Decimal, Optional[date]]]) -> str:
    """AC-F11a's tie breaker: codes, quantities and dates, hashed.

    Sorted before hashing, so the same commitment printed in a different order is the same
    fingerprint. Quantized for the same reason the comparison is: `600` and `600.0000` are
    one quantity.
    """
    parts = sorted(
        f"{_s(code) or ''}|{_q(qty, _QTY) or ''}|{_d(delivery) or ''}"
        for code, qty, delivery in items
    )
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()
