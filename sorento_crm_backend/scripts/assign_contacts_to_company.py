#!/usr/bin/env python3
"""Give every Respond contact a company membership.

Run from sorento_crm_backend/:
    python scripts/assign_contacts_to_company.py                 # dry run, Sorento
    python scripts/assign_contacts_to_company.py --apply
    python scripts/assign_contacts_to_company.py --company MCH --apply

Why this matters more than it looks: a contact with NO membership is not a
partially-scoped contact, it is a fail-closed one. ``_resolve_api_key_scope`` turns
``resolve_contact_company_ids() == []`` into an EMPTY frozenset, and
``build_company_predicate`` turns an empty frozenset into ``false()``. So every
company-owned MCP tool - stock balance, products, promotions, incoming stock -
returns zero rows for that contact, with no error anywhere. It reads as "the bot
knows nothing about our stock", not as a permissions problem.

Assigning contacts BEFORE a second company's catalogue is loaded is therefore the
prerequisite for multi-company MCP working at all.

Idempotent: membership is keyed by (respond_contact_id, company_id) with a unique
index, so re-running adds nothing. Contacts that already belong to the target
company are skipped, and contacts that belong to a DIFFERENT company are reported
rather than silently given a second membership - widening a contact's scope is a
decision, not a backfill.
"""
from __future__ import annotations

import argparse
import os
import sys
import uuid

# Allow `from app.*` imports when invoked from the backend directory.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal  # noqa: E402
from app.models.access import RespondContact  # noqa: E402
from app.models.company import Company, RespondContactCompany  # noqa: E402
from app.models.base import set_company_scope  # noqa: E402


def _resolve_company(db, ref: str) -> Company:
    """Accept a company code (SRT), a name (Sorento) or an id."""
    ref = (ref or "").strip()
    row = (
        db.query(Company)
        .filter((Company.code == ref) | (Company.name == ref) | (Company.id == ref))
        .first()
    )
    if row is None:
        available = ", ".join(f"{c.code} ({c.name})" for c in db.query(Company).all())
        raise SystemExit(f"No company matches {ref!r}. Available: {available}")
    return row


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--company", default="Sorento", help="code, name or id (default: Sorento)")
    ap.add_argument("--apply", action="store_true", help="write; omit for a dry run")
    args = ap.parse_args()

    db = SessionLocal()
    # Contacts are not company-scoped, but Company is - read across all companies.
    set_company_scope(db, None)
    try:
        company = _resolve_company(db, args.company)

        contacts = db.query(RespondContact).all()
        existing = {
            (r.respond_contact_id, r.company_id)
            for r in db.query(RespondContactCompany).all()
        }
        owned_by_other: list[str] = []
        to_add: list[RespondContact] = []
        for c in contacts:
            cid = str(c.id)
            if (cid, company.id) in existing:
                continue
            if any(rc == cid for rc, _ in existing):
                owned_by_other.append(cid)
                continue
            to_add.append(c)

        print(f"company        : {company.name} ({company.code}) {company.id}")
        print(f"contacts       : {len(contacts)}")
        print(f"already in     : {len(contacts) - len(to_add) - len(owned_by_other)}")
        print(f"in another co  : {len(owned_by_other)} (left alone)")
        print(f"to assign      : {len(to_add)}")

        if owned_by_other:
            print("\nContacts already assigned elsewhere - widen these by hand if intended:")
            for cid in owned_by_other[:20]:
                print(f"  {cid}")
            if len(owned_by_other) > 20:
                print(f"  ... and {len(owned_by_other) - 20} more")

        if not args.apply:
            print("\nDRY RUN - nothing written. Re-run with --apply.")
            return 0

        for c in to_add:
            db.add(
                RespondContactCompany(
                    id=str(uuid.uuid4()),
                    respond_contact_id=str(c.id),
                    company_id=company.id,
                )
            )
        db.commit()
        print(f"\nAssigned {len(to_add)} contact(s) to {company.name}.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
