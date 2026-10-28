#!/usr/bin/env python3
"""Give every brand back to the Mocha contacts the 27 Oct access-sheet import narrowed.

Owner ruling 27 Oct (ACCESS-SHEET-FIXES): a contact that holds company MCH keeps every brand.
Before the fix, the import (`contact.access_sheet`) moved some of them from every brand to the
Sorento dealer brands. This finds them by that audit (brands "every brand" -> a list) AND the
MCH membership they hold now AND a brand list they still carry, and resets the list to NULL
(every brand). Nothing else is touched.

Run from sorento_crm_backend/:

    python scripts/fix_access_sheet_mocha_brands.py            # dry run: lists, writes nothing
    python scripts/fix_access_sheet_mocha_brands.py --apply    # one transaction, one audit row each

Each applied contact gets an audit row (`contact.access_sheet_brand_fix`) holding the brand ids
before and NULL after, so the change can be read back and reversed by hand.
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session

from app.models.access import RespondContact
from app.models.audit import AuditLog
from app.models.base import company_scope
from app.models.company import Company, RespondContactCompany
from app.services import audit_service
from app.services.contact_access_sheet_service import EVERY_BRAND_COMPANIES

SHEET_EVENT = "contact.access_sheet"
EVENT = "contact.access_sheet_brand_fix"
EVERY_BRAND = "every brand"


def repair(db: Session, *, apply: bool) -> list[dict]:
    """The contacts to reset (``contact_id``, ``name``, ``phone``, ``brand_ids``); writes only with ``apply``."""
    with company_scope(db, None):
        narrowed = {
            entity_id
            for entity_id, old, new in db.query(AuditLog.entity_id, AuditLog.old_values, AuditLog.new_values).filter(
                AuditLog.event == SHEET_EVENT, AuditLog.entity_type == "respond_contacts"
            )
            if (old or {}).get("brands") == EVERY_BRAND and isinstance((new or {}).get("brands"), list)
        }
        if not narrowed:
            return []
        mocha = (
            db.query(RespondContactCompany.respond_contact_id)
            .join(Company, Company.id == RespondContactCompany.company_id)
            .filter(Company.code.in_(EVERY_BRAND_COMPANIES), RespondContactCompany.respond_contact_id.in_(narrowed))
        )
        rows = (
            db.query(RespondContact.id, RespondContact.name, RespondContact.phone_number, RespondContact.brand_ids)
            .filter(RespondContact.id.in_(mocha), RespondContact.brand_ids.isnot(None))
            .order_by(RespondContact.name, RespondContact.id)
            .all()
        )
        found = [
            {"contact_id": r.id, "name": r.name, "phone": r.phone_number, "brand_ids": sorted(r.brand_ids)}
            for r in rows
            if r.brand_ids  # an empty list already means every brand
        ]
        if apply and found:
            try:
                for f in found:
                    db.query(RespondContact).filter(RespondContact.id == f["contact_id"]).update(
                        {"brand_ids": None}, synchronize_session=False
                    )
                    audit_service.record(
                        db, event=EVENT, entity_type="respond_contacts", entity_id=f["contact_id"],
                        old_values={"brand_ids": f["brand_ids"]}, new_values={"brand_ids": None},
                        description="Every brand restored for a Mocha contact the access sheet narrowed",
                    )
                db.commit()
            except Exception:
                db.rollback()
                raise
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="write the reset (default: dry run)")
    args = parser.parse_args(argv)

    from app.database import SessionLocal

    db = SessionLocal()
    try:
        found = repair(db, apply=args.apply)
    finally:
        db.close()
    mode = "APPLIED" if args.apply else "DRY RUN (nothing written; pass --apply)"
    print(f"{mode}: {len(found)} contact(s) back to every brand")
    for f in found:
        print(f"  {f['name'] or '-'} ({f['phone']}): {len(f['brand_ids'])} brand(s) -> every brand")
    return 0


if __name__ == "__main__":
    sys.exit(main())
