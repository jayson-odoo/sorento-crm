"""Dated exchange rates (AC-ER-01..07).

A rate row is (currency, effective_from, MYR per 1 unit). The rate for a currency on a day is
the row with the latest `effective_from <= day`; no such row is "no rate" and never 1. MYR is 1
by definition and has no row.
"""
from __future__ import annotations

import uuid
from bisect import bisect_right
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.models.costing import ExchangeRate
from app.services.costing.formula import to_decimal
from app.services.error_handler import AppException
from app.services.scm.money import BASE_CURRENCY, normalize_currency

_SIX = Decimal("0.000001")
_FOUR = Decimal("0.0001")
ONE = Decimal(1)


def clean_currency(currency: Optional[str]) -> str:
    """Upper-case, trimmed; a foreign code only (3 letters, never the base currency)."""
    code = normalize_currency(currency)
    if code == BASE_CURRENCY:
        raise AppException(
            status_code=422,
            message=f"{BASE_CURRENCY} is the base currency, so its rate is 1 and is not stored.",
        )
    if len(code) != 3:
        raise AppException(status_code=422, message="A currency code is three letters.")
    return code


#: The currencies the cost-price upload offers, besides the ringgit. The pick-list always has these;
#: any other code on a supplier cost row joins them.
BASE_CURRENCIES = ("CNY", "USD", "EUR")


def known_currencies(db: Session) -> list:
    """The currencies a rate may be set for: those the cost lists and supplier links already use,
    and the upload's own three. Upper-cased, sorted, never the ringgit."""
    from app.models.cost_price import ProductSupplierCost
    from app.models.procurement import ProductSupplier

    codes = set(BASE_CURRENCIES)
    for column in (ProductSupplierCost.currency, ProductSupplier.currency):
        for (value,) in db.query(column).filter(column.isnot(None)).distinct():
            code = normalize_currency(value)
            if code and code != BASE_CURRENCY:
                codes.add(code)
    return sorted(codes)


def check_known_currency(db: Session, code: str) -> None:
    if code not in known_currencies(db):
        raise AppException(status_code=422, message=f"Unknown currency {code}.", code="UNKNOWN_CURRENCY")


def rate_from_units(units_per_base: object) -> Decimal:
    """MYR per unit from "units per MYR 1" (1.6 -> 0.625000)."""
    units = to_decimal(units_per_base)  # type: ignore[arg-type]
    if units <= 0:
        raise AppException(status_code=422, message="A rate must be greater than zero.")
    rate = (ONE / units).quantize(_SIX, rounding=ROUND_HALF_UP)
    if rate <= 0:
        # So large a figure that its inverse is nothing at six places: not a rate.
        raise AppException(status_code=422, message="That rate is too large to store.")
    return rate


def units_per_base(rate_to_base: object) -> Optional[Decimal]:
    """Units per MYR 1, to 4 dp (the workbook's 1.6)."""
    rate = to_decimal(rate_to_base)  # type: ignore[arg-type]
    if rate <= 0:
        return None
    return (ONE / rate).quantize(_FOUR, rounding=ROUND_HALF_UP)


def _positive_rate(value: object) -> Decimal:
    rate = to_decimal(value)  # type: ignore[arg-type]
    if rate <= 0:
        raise AppException(
            status_code=422,
            message="A rate must be greater than zero: a zero rate would price every item "
                    "in that currency at nothing.",
        )
    return rate.quantize(_SIX, rounding=ROUND_HALF_UP)


def rate_on(db: Session, currency: str, day: date) -> Optional[ExchangeRate]:
    """The row in force for `currency` on `day`, else None. One lookup with the page's: `RateBook`."""
    return load_rate_book(db).on(currency, day)


class RateBook:
    """Every rate row held in memory (a handful of rows), so a page of products resolves its
    rates without a query per product."""

    def __init__(self, rows) -> None:
        by_currency: dict[str, list[ExchangeRate]] = {}
        for row in sorted(rows, key=lambda r: (r.currency, r.effective_from)):
            by_currency.setdefault(row.currency, []).append(row)
        self._rows = by_currency
        self._days = {c: [r.effective_from for r in rs] for c, rs in by_currency.items()}

    def on(self, currency: str, day: date) -> Optional[ExchangeRate]:
        code = normalize_currency(currency)
        days = self._days.get(code)
        if not days:
            return None
        i = bisect_right(days, day)
        return self._rows[code][i - 1] if i else None


def load_rate_book(db: Session) -> RateBook:
    return RateBook(db.query(ExchangeRate).all())


def status_of(row: ExchangeRate, rows_of_currency, today: date) -> str:
    """`scheduled` (future), `in_force` (the latest not after today), `past` (superseded)."""
    if row.effective_from > today:
        return "scheduled"
    latest = max((r.effective_from for r in rows_of_currency if r.effective_from <= today), default=None)
    return "in_force" if row.effective_from == latest else "past"


def serialize(row: ExchangeRate, status: str) -> dict:
    units = units_per_base(row.rate_to_base)
    return {
        "id": str(row.id),
        "currency": row.currency,
        "rate_to_base": float(row.rate_to_base),
        "units_per_base": float(units) if units is not None else None,
        "effective_from": row.effective_from.isoformat(),
        "note": row.note,
        "status": status,
    }


def list_rates(db: Session, today: date, currency: Optional[str] = None) -> list[dict]:
    """Newest first per currency."""
    rows = db.query(ExchangeRate).all()
    if currency:
        code = normalize_currency(currency)
        rows = [r for r in rows if r.currency == code]
    by_currency: dict[str, list[ExchangeRate]] = {}
    for r in rows:
        by_currency.setdefault(r.currency, []).append(r)
    out = []
    for code in sorted(by_currency):
        group = by_currency[code]
        for r in sorted(group, key=lambda x: x.effective_from, reverse=True):
            out.append(serialize(r, status_of(r, group, today)))
    return out


def _one(db: Session, row: ExchangeRate, today: date) -> dict:
    group = db.query(ExchangeRate).filter(ExchangeRate.currency == row.currency).all()
    return serialize(row, status_of(row, group, today))


def create_rate(
    db: Session,
    *,
    currency: str,
    effective_from: date,
    rate_to_base: object = None,
    units_per_base_in: object = None,
    note: Optional[str] = None,
    actor: Optional[str] = None,
    today: date,
) -> dict:
    code = clean_currency(currency)
    check_known_currency(db, code)
    if (rate_to_base is None) == (units_per_base_in is None):
        raise AppException(status_code=422, message="Give the rate either as MYR per unit or as units per MYR 1.")
    rate = _positive_rate(rate_to_base) if rate_to_base is not None else rate_from_units(units_per_base_in)
    if rate <= 0:
        raise AppException(status_code=422, message="A rate must be greater than zero.")
    exists = (
        db.query(ExchangeRate)
        .filter(ExchangeRate.currency == code, ExchangeRate.effective_from == effective_from)
        .first()
    )
    if exists is not None:
        raise AppException(
            status_code=409,
            message=f"{code} already has a rate from {effective_from.isoformat()}. Edit that row instead.",
        )
    row = ExchangeRate(
        id=str(uuid.uuid4()), currency=code, rate_to_base=rate, effective_from=effective_from,
        note=note or None, created_by=actor,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _one(db, row, today)


def update_rate(
    db: Session,
    rate_id: str,
    *,
    rate_to_base: object = None,
    units_per_base_in: object = None,
    note_given: bool = False,
    note: Optional[str] = None,
    today: date,
) -> dict:
    row = get_rate(db, rate_id)
    if rate_to_base is not None and units_per_base_in is not None:
        raise AppException(status_code=422, message="Give the rate either as MYR per unit or as units per MYR 1.")
    if rate_to_base is not None:
        row.rate_to_base = _positive_rate(rate_to_base)
    elif units_per_base_in is not None:
        row.rate_to_base = rate_from_units(units_per_base_in)
    if note_given:
        row.note = note or None
    db.commit()
    db.refresh(row)
    return _one(db, row, today)


def get_rate(db: Session, rate_id: str) -> ExchangeRate:
    try:
        uuid.UUID(str(rate_id))
    except ValueError:
        raise AppException(status_code=404, message="Exchange rate not found.", code="NOT_FOUND")
    row = db.query(ExchangeRate).filter(ExchangeRate.id == str(rate_id)).first()
    if row is None:
        raise AppException(status_code=404, message="Exchange rate not found.", code="NOT_FOUND")
    return row


def delete_rate_by_id(db: Session, rate_id: str) -> None:
    """The parked `exchange_rate.delete` action's handler. Already gone is not an error."""
    row = db.query(ExchangeRate).filter(ExchangeRate.id == str(rate_id)).first()
    if row is not None:
        db.delete(row)
        db.flush()
