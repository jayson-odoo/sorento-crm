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

from app.services.error_handler import AppException
from app.services.scm.money import BASE_CURRENCY, normalize_currency


def list_rates(db: Session) -> dict:
    """Every rate on file, plus the currencies the book uses that have none."""
    rows = db.execute(text(
        "SELECT currency, rate_to_base, as_of, note, updated_at "
        "FROM scm.currency_rate ORDER BY currency"
    )).mappings().all()
    held = {r["currency"] for r in rows}

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

    existing = db.execute(text(
        "SELECT currency, rate_to_base, as_of, note, updated_at "
        "FROM scm.currency_rate WHERE currency = :c"
    ), {"c": code}).mappings().first()

    if existing is not None:
        same = (float(existing["rate_to_base"]) == value
                and existing["as_of"] == as_of
                and (existing["note"] or None) == (note or None))
        if same:
            return {"action": "unchanged", "rate": _serialize(existing)}
        db.execute(text(
            "UPDATE scm.currency_rate "
            "SET rate_to_base = :v, as_of = :a, note = :n, updated_by = :u, "
            "    updated_at = CURRENT_TIMESTAMP "
            "WHERE currency = :c"
        ), {"v": value, "a": as_of, "n": note, "u": actor, "c": code})
        db.commit()
        return {"action": "updated", "rate": _read_one(db, code)}

    db.execute(text(
        "INSERT INTO scm.currency_rate (currency, rate_to_base, as_of, note, updated_by) "
        "VALUES (:c, :v, :a, :n, :u)"
    ), {"c": code, "v": value, "a": as_of, "n": note, "u": actor})
    db.commit()
    return {"action": "created", "rate": _read_one(db, code)}


def delete_rate(db: Session, currency: str) -> None:
    """Remove a rate. Every price in that currency becomes unrankable again, which is the
    honest consequence and is visible on the plan as "no rate for X"."""
    code = normalize_currency(currency)
    deleted = db.execute(text(
        "DELETE FROM scm.currency_rate WHERE currency = :c"
    ), {"c": code}).rowcount
    if not deleted:
        raise AppException(status_code=404, message=f"No rate on file for {code}.")
    db.commit()


def _read_one(db: Session, code: str) -> dict:
    row = db.execute(text(
        "SELECT currency, rate_to_base, as_of, note, updated_at "
        "FROM scm.currency_rate WHERE currency = :c"
    ), {"c": code}).mappings().first()
    return _serialize(row) if row else {}


def _serialize(r) -> dict:
    return {
        "currency": r["currency"],
        "rate_to_base": float(r["rate_to_base"]),
        "as_of": r["as_of"].isoformat() if r["as_of"] else None,
        "note": r["note"],
        "updated_at": r["updated_at"].isoformat() if r["updated_at"] else None,
    }
