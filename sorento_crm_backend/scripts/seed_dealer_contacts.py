#!/usr/bin/env python3
"""Bind representative `respond_contacts.customer_id` dealer contacts for local and
staging (AC-B12).

Without a few bound contacts there is no way to exercise the dealer journey at all:
every phone number resolves to Consumer by elimination, so the dealer track, the
salesperson derivation and the Sanimart case are all unreachable in a dev database.

**Production bindings are configured manually by Sorento. No bulk import ships.**
Which phone number belongs to which dealer is a commercial fact this codebase does
not hold, and a bulk guess would mis-route real people's complaints, their
notifications and their salesperson - the single error the whole parties slice
exists to avoid.

Run from sorento_crm_backend/:

    python scripts/seed_dealer_contacts.py            # dry run (default)
    python scripts/seed_dealer_contacts.py --apply

Matching rule, chosen rather than inherited (AC-B12 says only "representative"):
**exact phone equality after reducing both sides to digits**, mirroring
`backfill_requested_by_contact`'s exact-match-or-leave rule. Anything fuzzier binds a
Consumer to a Dealer. Two customers on one number is ambiguous and is left unbound,
because a guess here puts a person on the wrong journey and nothing downstream can
tell that it happened.

**Fill-only, never re-point.** Unlike `seed_customer_account_owner` (which corrects a
prior bad run by design), a contact that already carries a binding was bound
deliberately by Sorento, and a phone coincidence must not overwrite that. The
correction path for a wrong binding is the admin UI, not this script.

A dry run does not assign, only reports. Setting an attribute is enough to write:
the next query autoflushes it regardless of the commit.
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
from app.models.access import RespondContact
from app.models.base import company_scope
from app.models.order import Customer

# Contacts are global; customers are company-partitioned. `None` is the
# all-companies scope. A bare session carries `UNSET`, which is fail-closed to zero
# rows, so the script would report "nothing to do" and exit 0 having seen no
# customers at all.
ALL_COMPANIES = None

_NON_DIGITS = re.compile(r"\D+")


def normalize_phone(value: Optional[str]) -> str:
    """Digits only. Enough to make "+60 12-345 6789" and "+60123456789" one number,
    and deliberately not enough to make two different numbers equal."""
    if not value:
        return ""
    return _NON_DIGITS.sub("", str(value))


def _customers_by_phone(db) -> dict[str, set[str]]:
    """Normalized phone -> the set of customer ids carrying it.

    A set, not a single id: the ambiguity is the point. Two customers sharing a
    number (a group with several debtor accounts, a shared shop line) must not
    resolve to whichever one the query happened to return first.
    """
    index: dict[str, set[str]] = {}
    rows = db.query(Customer.id, Customer.phone_number, Customer.mobile_number).all()
    for customer_id, phone_number, mobile_number in rows:
        for raw in (phone_number, mobile_number):
            key = normalize_phone(raw)
            if len(key) >= 7:  # shorter than a real number: an extension or junk
                index.setdefault(key, set()).add(str(customer_id))
    return index


def seed_dealer_contacts(db, *, dry_run: bool = True) -> dict:
    """Bind unbound contacts whose phone matches exactly one customer.

    Returns counters: `scanned`, `bound` (written, or would be), `already_bound`,
    `ambiguous` (more than one customer on that number), `unmatched`.
    """
    counters: dict[str, int] = {
        "scanned": 0,
        "bound": 0,
        "already_bound": 0,
        "ambiguous": 0,
        "unmatched": 0,
    }
    ambiguous_report: list[tuple[str, str]] = []

    with company_scope(db, ALL_COMPANIES):
        index = _customers_by_phone(db)

        for contact in db.query(RespondContact).all():
            counters["scanned"] += 1
            if contact.customer_id:
                # Configured deliberately, or bound by a prior run. Never re-pointed.
                counters["already_bound"] += 1
                continue

            matches = index.get(normalize_phone(contact.phone_number), set())
            if not matches:
                counters["unmatched"] += 1
                continue
            if len(matches) > 1:
                counters["ambiguous"] += 1
                ambiguous_report.append((contact.id, ", ".join(sorted(matches))))
                continue

            counters["bound"] += 1
            if not dry_run:
                # Assign ONLY when writing - autoflush turns a dirty row into an
                # UPDATE whether or not the commit runs.
                contact.customer_id = next(iter(matches))

        if not dry_run:
            db.commit()

    return {**counters, "ambiguous_contacts": ambiguous_report}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true", default=True, help="(default) report only, no writes"
    )
    parser.add_argument("--apply", action="store_true", help="perform DB writes (off by default)")
    args = parser.parse_args()
    if args.apply:
        args.dry_run = False

    db = SessionLocal()
    try:
        stats = seed_dealer_contacts(db, dry_run=args.dry_run)
        if args.dry_run:
            db.rollback()

        print(
            f"respond_contacts: scanned={stats['scanned']} bound={stats['bound']} "
            f"already_bound={stats['already_bound']} ambiguous={stats['ambiguous']} "
            f"unmatched={stats['unmatched']}"
        )
        if stats["ambiguous_contacts"]:
            print("\nLeft unbound because the number matched more than one customer:")
            for contact_id, customer_ids in stats["ambiguous_contacts"]:
                print(f"  contact={contact_id} customers={customer_ids}")

        print("\n" + ("[dry-run] no writes performed." if args.dry_run else "Writes committed."))
        return 0
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
