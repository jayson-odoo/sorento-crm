"""Hold the exchange rates the plan compares prices with, and say which ones are missing.

The plan cannot rank a 45 USD supplier against a 190 MYR one without a rate, and it must not
pretend to. That leaves the buyer with a plan row that quietly refuses to be funded, so this
service also reports the currencies the purchase-order book actually PRICES in that have no
rate on file. The screen can then say "you have no rate for CNY" rather than leaving the
buyer to reverse-engineer it from a plan.

Rates live in the dated `exchange_rates` table (PRODUCT-COSTING, contract 4.8). The SCM screen
keeps its one-row-per-currency shape: it lists and edits the row in force TODAY, and saving
writes the row dated `as_of` (today when none is given), updating it when that date already has
one.

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

from app.models.costing import ExchangeRate
from app.services.error_handler import AppException
from app.services.scm.money import BASE_CURRENCY, normalize_currency

# Read and write through the MODEL, never `text("... exchange_rates ...")` for the rates. A
# schema-qualified name bypasses search_path, so raw SQL here would reach past a test's
# scratch schema and touch the real table - the same silent live-data write the blank-schema
# fixture exists to prevent.


def _today() -> date:
    from app.services.reports.registry import today_malaysia

    return today_malaysia()


def _in_force_rows(db: Session, currency: Optional[str] = None) -> list[ExchangeRate]:
    """The row in force today for each currency (or for one)."""
    query = db.query(ExchangeRate).filter(ExchangeRate.effective_from <= _today())
    if currency is not None:
        query = query.filter(ExchangeRate.currency == currency)
    latest: dict[str, ExchangeRate] = {}
    for r in query.order_by(ExchangeRate.currency, ExchangeRate.effective_from):
        latest[r.currency] = r
    return [latest[c] for c in sorted(latest)]


def list_rates(db: Session) -> dict:
    """Every rate in force today, plus the currencies the book uses that have none."""
    rows = _in_force_rows(db)
    held = {r.currency for r in rows}

    # What the purchase-order book actually prices in. The line's own currency wins over
    # the order's, matching how the cost cascade reads it.
    used = db.execute(text(
        "SELECT DISTINCT upper(btrim(COALESCE(pol.currency, po.currency))) AS cur "
        "FROM purchase_order_lines pol "
        "JOIN purchase_orders po ON po.id = pol.purchase_order_id "
        "WHERE pol.unit_cost IS NOT NULL "
        "  AND COALESCE(pol.currency, po.currency) IS NOT NULL"
        # AC-REMOVED-KEEP-CANCELLED: a removed line the ingest used to delete counts in no total.
        "  AND NOT pol.removed_unreferenced"
    )).scalars().all()

    missing = sorted(c for c in used
                     if c and c != BASE_CURRENCY and c not in held)
    # The next dated row of each currency that has not started yet ("Scheduled from ...").
    scheduled: dict[str, ExchangeRate] = {}
    for r in (
        db.query(ExchangeRate)
        .filter(ExchangeRate.effective_from > _today())
        .order_by(ExchangeRate.effective_from.desc())
    ):
        scheduled[r.currency] = r  # descending, so the earliest future row wins
    out = []
    for r in rows:
        item = _serialize(r)
        nxt = scheduled.get(r.currency)
        item["scheduled_from"] = nxt.effective_from.isoformat() if nxt else None
        item["scheduled_rate_to_base"] = float(nxt.rate_to_base) if nxt else None
        out.append(item)
    return {
        "base_currency": BASE_CURRENCY,
        "rates": out,
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

    effective_from = as_of or _today()
    in_force = _in_force_rows(db, code)
    if in_force and effective_from < in_force[0].effective_from:
        # This screen keeps ONE live rate per currency: it can change today's, or schedule a
        # later one. Back-dating a rate rewrites history, which Costing > Settings owns.
        raise AppException(
            status_code=422,
            message="A past rate is added in Costing > Settings.",
            code="PAST_RATE",
        )
    existing = (
        db.query(ExchangeRate)
        .filter(ExchangeRate.currency == code, ExchangeRate.effective_from == effective_from)
        .first()
    )

    if existing is not None:
        same = (round(float(existing.rate_to_base), 6) == round(value, 6)
                and (existing.note or None) == (note or None))
        if same:
            return {"action": "unchanged", "rate": _serialize(existing)}
        existing.rate_to_base = value
        existing.note = note
        db.commit()
        db.refresh(existing)
        return {"action": "updated", "rate": _serialize(existing)}

    # The screen's words stay per currency: a currency with a rate already is being UPDATED to
    # a new one (a new dated row), and only its first row is a creation.
    had_rate = db.query(ExchangeRate).filter(ExchangeRate.currency == code).first() is not None
    row = ExchangeRate(currency=code, rate_to_base=value, effective_from=effective_from,
                       note=note, created_by=actor)
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"action": "updated" if had_rate else "created", "rate": _serialize(row)}


def delete_rate(db: Session, currency: str) -> None:
    """Remove the rate in force today. Every price in that currency falls back to the
    previous dated row, or becomes unrankable again when there is none, which is the honest
    consequence and is visible on the plan as "no rate for X"."""
    code = normalize_currency(currency)
    rows = _in_force_rows(db, code)
    if not rows:
        raise AppException(status_code=404, message=f"No rate on file for {code}.")
    db.delete(rows[0])
    db.commit()


def _serialize(r: ExchangeRate) -> dict:
    return {
        "currency": r.currency,
        "rate_to_base": float(r.rate_to_base),
        "as_of": r.effective_from.isoformat() if r.effective_from else None,
        "note": r.note,
        "updated_at": r.updated_at.isoformat() if r.updated_at else None,
    }
