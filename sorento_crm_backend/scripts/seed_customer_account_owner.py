#!/usr/bin/env python3
"""Seed `customers.account_owner_user_id` from the sales-agent code on each
customer's most recent order (AC-B7, AC-B8, AC-B10, AC-B11, AC-B19, AC-B20).

`account_owner_user_id` is 0 of 3,284 populated, and every after-sales
notification needs it: the Dealer's salesperson is derived from it and never typed
(AC-B9). Orders are the SEED, never the source - this runs once, writes a value a
human can then edit on the Customer form, and no runtime path repeats it.

Run from sorento_crm_backend/ AFTER `alembic upgrade head`:

    python scripts/seed_customer_account_owner.py                  # dry run (default)
    python scripts/seed_customer_account_owner.py --apply
    python scripts/seed_customer_account_owner.py --apply --batch 1

The five things that make this correct, each of which the obvious version gets
wrong:

**It sets its own company scope, explicitly (AC-B20).** A bare `SessionLocal` carries
`UNSET`, which is fail-closed to zero rows, so the naive script exits successfully
having done nothing - and prints "0 scanned" that nobody reads. The scope is set to
None (all companies) because AC-B11 confirms every code suffix appears under BOTH
Sorento and Mocha, so a single-company scope is wrong even when a scope is set.

**Most-recent-order-wins needs a tie-break to be idempotent (AC-B19).** Two orders on
the same day with different agents is not hypothetical across 322 multi-code
customers, and an arbitrary pick flips the account owner on every re-run, which flips
who is notified about every complaint for that dealer. Ordered by
`order_date DESC NULLS LAST`, then `order_number DESC`, then `id DESC`.

**`orders.order_date` is nullable and Postgres sorts NULLs FIRST on DESC.** Without
NULLS LAST the account owner goes to whichever order forgot its date.

**"Set where mismatch", never "update where NULL" (AC-K1).** Update-where-NULL cannot
repair the run that wrote the wrong value, which is the run you most need to repair.
A row already holding the right value is counted and left alone, so a second run
reports zero writes.

**A dry run does not assign (not merely: does not commit).** The seed sets attributes
on ORM rows and the very next query autoflushes them, so `--dry-run` that skips only
the commit has already written the whole table while reporting that it did not.
Verified at `--batch 1`, where the batch boundary is.

Paging is KEYSET (`id > last_id`), never `yield_per`: a server-side cursor dies on
the first mid-loop commit.

The code map is persisted in `salesman_code_users` and is never hardcoded here
(AC-B18). `users` has no code column and one person needs four codes, so a column
could not hold them anyway.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from typing import Optional

# Allow `from app.*` imports when invoked from the backend directory.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models.base import company_scope
from app.models.order import Customer, Order, SalesmanCodeUser

# The seed reads and writes across every company (AC-B11 / AC-B20). `None` is the
# all-companies scope; `UNSET` (the default on a bare session) is fail-closed to
# zero rows, which is the silent no-op this constant exists to avoid.
ALL_COMPANIES = None

_WHITESPACE = re.compile(r"\s+")


def normalize_code(value: Optional[str]) -> str:
    """Upper-cased, whitespace-collapsed. "sean  iii" and "SEAN III" are one code."""
    if not value:
        return ""
    return _WHITESPACE.sub(" ", str(value).strip().upper())


# --------------------------------------------------------------------------- #
# The persisted code map (AC-B18)                                               #
# --------------------------------------------------------------------------- #


def load_salesman_code_map(db) -> dict[str, str]:
    """Every configured code -> users.id, keyed by the normalized code."""
    with company_scope(db, ALL_COMPANIES):
        rows = db.query(SalesmanCodeUser.salesman_code, SalesmanCodeUser.user_id).all()
    return {normalize_code(code): user_id for code, user_id in rows if code and user_id}


def upsert_salesman_code(db, code: str, user_id: str) -> None:
    """Point one code at one user. Many codes may point at the same user.

    Upsert rather than insert so re-running the configuration step, or correcting a
    code that was pointed at the wrong person, is the same operation. Flushed, not
    committed: the caller owns the transaction (a script commits once, a test rolls
    back).
    """
    normalized = normalize_code(code)
    if not normalized:
        raise ValueError("A sales-agent code cannot be blank.")
    if not user_id:
        raise ValueError(f"No user id given for code {normalized!r}.")
    with company_scope(db, ALL_COMPANIES):
        row = (
            db.query(SalesmanCodeUser)
            .filter(SalesmanCodeUser.salesman_code == normalized)
            .first()
        )
        if row is None:
            db.add(SalesmanCodeUser(salesman_code=normalized, user_id=user_id))
        elif row.user_id != user_id:
            row.user_id = user_id
        db.flush()


# --------------------------------------------------------------------------- #
# The seed                                                                      #
# --------------------------------------------------------------------------- #


def _winning_codes(db, customer_ids: list[str]) -> dict[str, str]:
    """The sales-agent code on each customer's most recent order.

    One query per batch, ordered so the FIRST row seen for a customer is the winner:
    dated orders before undated (NULLS LAST), newest first, then the highest order
    number, then the highest id. The last two exist only to make a same-day tie
    deterministic - without them the seed is not idempotent (AC-B19).

    Taking first-per-customer in Python rather than `DISTINCT ON` keeps the ordering
    rule readable and dialect-independent; the row set is bounded by one batch of
    customers.
    """
    if not customer_ids:
        return {}
    rows = (
        db.query(Order.customer_id, Order.salesman)
        .filter(Order.customer_id.in_(customer_ids))
        .order_by(
            Order.customer_id.asc(),
            Order.order_date.desc().nullslast(),
            Order.order_number.desc(),
            Order.id.desc(),
        )
        .all()
    )
    winners: dict[str, str] = {}
    for customer_id, code in rows:
        winners.setdefault(str(customer_id), code)
    return winners


def seed_account_owners(
    db,
    *,
    code_map: Optional[dict[str, str]] = None,
    dry_run: bool = True,
    batch: int = 500,
) -> dict:
    """Set every customer's account owner from their most recent order's agent code.

    `code_map` defaults to the persisted `salesman_code_users` table; it is a
    parameter so a caller can preview a proposed map without writing it first.

    Returns counters: `scanned`, `matched_set` (written, or would be),
    `matched_unchanged` (already correct), `unresolved` (no orders, or an agent code
    that maps to nobody - the ~770 order-less dealers plus the junk codes `0`, `ACT`,
    `CS01`, `WH02`, `MARKETING`, `SAMPLE`, `FUNITURE`, `TERA`). Unresolved is a real
    answer: it stays NULL and is counted so it lands on the dashboard flag (AC-B10)
    rather than on an arbitrary user.
    """
    counters: dict[str, int] = {
        "scanned": 0,
        "matched_set": 0,
        "matched_unchanged": 0,
        "unresolved": 0,
    }
    unresolved_codes: dict[str, int] = {}

    with company_scope(db, ALL_COMPANIES):
        mapping = (
            {normalize_code(k): v for k, v in code_map.items()}
            if code_map is not None
            else load_salesman_code_map(db)
        )

        last_id: Optional[str] = None
        while True:
            query = db.query(Customer)
            if last_id is not None:
                query = query.filter(Customer.id > last_id)
            customers = query.order_by(Customer.id.asc()).limit(batch).all()
            if not customers:
                break
            last_id = str(customers[-1].id)

            winners = _winning_codes(db, [str(c.id) for c in customers])

            for customer in customers:
                counters["scanned"] += 1
                code = normalize_code(winners.get(str(customer.id)))
                user_id = mapping.get(code) if code else None
                if not user_id:
                    counters["unresolved"] += 1
                    if code:
                        unresolved_codes[code] = unresolved_codes.get(code, 0) + 1
                    continue

                if str(customer.account_owner_user_id or "") == str(user_id):
                    counters["matched_unchanged"] += 1
                    continue

                counters["matched_set"] += 1
                if not dry_run:
                    # Assign ONLY when writing. A dry run that dirties the session has
                    # already written: the next query autoflushes it.
                    customer.account_owner_user_id = user_id

            if not dry_run:
                db.commit()

    return {**counters, "unresolved_codes": unresolved_codes}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true", default=True, help="(default) report only, no writes"
    )
    parser.add_argument("--apply", action="store_true", help="perform DB writes (off by default)")
    parser.add_argument("--batch", type=int, default=500, help="Customers per commit batch.")
    args = parser.parse_args()
    if args.apply:
        args.dry_run = False

    db = SessionLocal()
    try:
        code_map = load_salesman_code_map(db)
        print(f"Loaded {len(code_map)} configured code(s) from salesman_code_users.")
        if not code_map:
            print(
                "The map is empty, so every customer will report as unresolved. "
                "Configure it first (upsert_salesman_code) - it is never hardcoded here."
            )

        stats = seed_account_owners(
            db, code_map=code_map, dry_run=args.dry_run, batch=args.batch
        )
        if args.dry_run:
            db.rollback()

        print(
            f"\ncustomers: scanned={stats['scanned']} "
            f"account_owner_set={stats['matched_set']} "
            f"already_correct={stats['matched_unchanged']} "
            f"unresolved={stats['unresolved']}"
        )
        if stats["unresolved_codes"]:
            print("\nCodes that map to nobody (add them to salesman_code_users, or ignore as junk):")
            for code, count in sorted(
                stats["unresolved_codes"].items(), key=lambda kv: (-kv[1], kv[0])
            ):
                print(f"  {code!r}: {count} customer(s)")

        print("\n" + ("[dry-run] no writes performed." if args.dry_run else "Writes committed."))
        return 0
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
