"""Backfill users.respond_contact_id from a unique phone match.

Idempotent, JOIN-style "set to correct value where a single match exists":
- only fills users that have no link yet
- only links when exactly ONE RespondContact matches the normalised phone
- safe to re-run; a second run reports 0 changes

Usage:
    python scripts/backfill_user_respond_contact.py [--dry-run]
"""
import sys

from app.database import SessionLocal
from app.models.user import User
from app.models.access import RespondContact
from app.services.phone_utils import normalize_msisdn


def run(dry_run: bool = False) -> dict:
    db = SessionLocal()
    linked = 0
    skipped_no_match = 0
    skipped_ambiguous = 0
    already = 0
    try:
        users = db.query(User).filter(User.contact_number.isnot(None)).all()
        for u in users:
            if u.respond_contact_id:
                already += 1
                continue
            n = normalize_msisdn(u.contact_number)
            if not n:
                skipped_no_match += 1
                continue
            matches = db.query(RespondContact).filter(RespondContact.phone_number == n).all()
            if len(matches) == 0:
                skipped_no_match += 1
                continue
            if len(matches) > 1:
                skipped_ambiguous += 1
                continue
            if not dry_run:
                u.respond_contact_id = matches[0].id
            linked += 1
        if not dry_run:
            db.commit()
    finally:
        db.close()
    summary = {
        "linked": linked,
        "already_linked": already,
        "skipped_no_match": skipped_no_match,
        "skipped_ambiguous": skipped_ambiguous,
        "dry_run": dry_run,
    }
    print(summary)
    return summary


if __name__ == "__main__":
    run(dry_run="--dry-run" in sys.argv)
