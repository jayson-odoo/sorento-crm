"""Hold the exchange rates the plan compares prices with, and say which ones are missing.

The plan cannot rank a 45 USD supplier against a 190 MYR one without a rate, and it must not
pretend to. That leaves the buyer with a plan row that quietly refuses to be funded, so this
service also reports the currencies the purchase-order book actually PRICES in that have no
rate on file. The screen can then say "you have no rate for CNY" rather than leaving the
buyer to reverse-engineer it from a plan.

Saving follows the reconciliation rule the rest of this module uses: same then skip, diff
then update, new then create. Skipping matters here because an unchanged row that gets
rewritten anyway moves `updated_at`, and "updated today" would then be a claim that somebody
checked the rate today.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.scm import CurrencyRate
from app.services.error_handler import AppException
from app.services.scm.money import BASE_CURRENCY, normalize_currency

# Read and write through the MODEL, never `text("... scm.currency_rate ...")`. A schema-
# qualified name bypasses search_path, so raw SQL here would reach past a test's scratch
# schema and touch the real table - the same silent live-data write the blank-schema
# fixture exists to prevent.


def list_rates(db: Session) -> dict:
    """Every rate on file, plus the currencies the book uses that have none."""
    rows = db.query(CurrencyRate).order_by(CurrencyRate.currency).all()
    held = {r.currency for r in rows}

    # What the purchase-order book actually prices in. The line's own currency wins over
    # the order's, matching how the cost cascade reads it.
    used = db.execute(text(
        "SELECT DISTINCT upper(btrim(COALESCE(pol.currency, po.currency))) AS cur "
        "FROM purchase_order_lines pol "
        "JOIN purchase_orders po ON po.id = pol.purchase_order_id "
        "WHERE pol.unit_cost IS NOT NULL "
        "  AND COALESCE(pol.currency, po.currency) IS NOT NULL"
    )).scalars().all()

    missing = sorted(c for c in used
                     if c and c != BASE_CURRENCY and c not in held)
    return {
        "base_currency": BASE_CURRENCY,
        "rates": [_serialize(r) for r in rows],
        "missing": missing,
    }


def upsert_rate(db: Session, currency: str, rate_to_base: float, *,
                as_of: Optional[date] = None, note: Optional[str] = None,
                actor: Optional[str] = None) -> dict:
    """Create, update, or leave alone. Returns `{action, rate}`."""
    code = normalize_currency(currency)
    if code == BASE_CURRENCY:
        raise AppException(
            status_code=422,
            message=(f"{BASE_CURRENCY} is the base currency, so its rate is 1 and is not "
                     "stored. Add a rate for the currency you are converting FROM."),
        )
    try:
        value = float(rate_to_base)
    except (TypeError, ValueError):
        value = 0.0
    if value <= 0:
        raise AppException(
            status_code=422,
            message="A rate must be greater than zero: a zero rate would price every "
                    "item in that currency at nothing.",
        )

    existing = db.get(CurrencyRate, code)

    if existing is not None:
        same = (float(existing.rate_to_base) == value
                and existing.as_of == as_of
                and (existing.note or None) == (note or None))
        if same:
            return {"action": "unchanged", "rate": _serialize(existing)}
        existing.rate_to_base = value
        existing.as_of = as_of
        existing.note = note
        existing.updated_by = actor
        db.commit()
        db.refresh(existing)
        return {"action": "updated", "rate": _serialize(existing)}

    row = CurrencyRate(currency=code, rate_to_base=value, as_of=as_of, note=note,
                       updated_by=actor)
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"action": "created", "rate": _serialize(row)}


def delete_rate(db: Session, currency: str) -> None:
    """Remove a rate. Every price in that currency becomes unrankable again, which is the
    honest consequence and is visible on the plan as "no rate for X"."""
    code = normalize_currency(currency)
    row = db.get(CurrencyRate, code)
    if row is None:
        raise AppException(status_code=404, message=f"No rate on file for {code}.")
    db.delete(row)
    db.commit()


def _serialize(r: CurrencyRate) -> dict:
    return {
        "currency": r.currency,
        "rate_to_base": float(r.rate_to_base),
        "as_of": r.as_of.isoformat() if r.as_of else None,
        "note": r.note,
        "updated_at": r.updated_at.isoformat() if r.updated_at else None,
    }
