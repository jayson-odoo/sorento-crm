#!/usr/bin/env python3
"""Remove the flyer-named duplicates the first prod apply of the combo seed made.

WHY
---
The importer matched a flyer combo on host + name. Where the owner already had the combo under
another name (the seed's `aka`), the first apply made a second, flyer-named combo beside it. This
deletes only that duplicate, and only when nothing shows a person ever touched it.

RULES (per seed entry that has `aka`; owner = a combo on the host named one of the aka, dup = the
combo named the flyer name):
* NO OWNER COMBO / NO DUPLICATE: nothing to do.
* DELETE only when ALL hold: `created_by` is NULL; an audit row created it under the importer's
  job id; every audit row on it (as entity or as root) carries that job id; no tag template link
  and no price tag request line points at it.
* otherwise KEEP, with every failed condition named.

Dry run by default (a read-only transaction, rolled back). `--apply` runs in ONE transaction; any
error rolls everything back and exits 2.

    venv/bin/python scripts/oneoff/remove_flyer_seed_duplicates.py [--file seed.json] [--company SRT] [--apply]
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Optional, Sequence, TextIO

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy import func, or_, text  # noqa: E402

from app.audit_context import AuditActor, clear_actor, stamp_actor  # noqa: E402
from app.models.audit import AuditLog  # noqa: E402
from app.models.base import company_scope  # noqa: E402
from app.models.company import Company  # noqa: E402
from app.models.dealer_kit import ComboTagTemplate  # noqa: E402
from app.models.price_tag import PriceTagRequestLine  # noqa: E402
from app.models.product_combo import ProductCombo  # noqa: E402
from app.services.audit_service import register_audit_listeners  # noqa: E402
from app.services.product_combo_service import ProductComboService  # noqa: E402
from scripts.import_product_combos import JOB_ID as IMPORT_JOB_ID  # noqa: E402
from scripts.import_product_combos import products_by_code, read_seed  # noqa: E402

JOB_ID = "remove_flyer_seed_duplicates"
DEFAULT_SEED = str(Path(__file__).resolve().parents[1] / "data" / "combo_seed_flyer_2026.json")
VERDICT_ORDER = ("DELETE", "KEEP", "NO DUPLICATE", "NO OWNER COMBO")
_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f]")


def clean(value) -> str:
    return _CONTROL.sub(" ", str(value or "")).replace(" | ", " / ").strip()


def _person_made(db, owner: ProductCombo) -> bool:
    if owner.created_by is not None:
        return True
    return (
        db.query(AuditLog)
        .filter(or_(AuditLog.entity_id == owner.id, AuditLog.root_entity_id == owner.id))
        .filter(or_(AuditLog.job_id.is_(None), AuditLog.job_id != IMPORT_JOB_ID))
        .count()
        > 0
    )


def judge(db, dup: ProductCombo, owners: list) -> tuple[bool, str]:
    """(deletable, details) for one duplicate."""
    failed: list[str] = []
    if dup.created_by is not None:
        failed.append("created by a user (created_by is set)")
    rows = (
        db.query(AuditLog)
        .filter(or_(AuditLog.entity_id == dup.id, AuditLog.root_entity_id == dup.id))
        .all()
    )
    if not any(r.job_id == IMPORT_JOB_ID and r.entity_id == dup.id and r.action in ("CREATE", "INSERT") for r in rows):
        failed.append("no audit row shows the importer created it")
    foreign = [r for r in rows if r.job_id != IMPORT_JOB_ID]
    if dup.image_attachment_id is not None:
        failed.append("has a picture")
    if foreign:
        failed.append(f"touched since: {len(foreign)} audit row(s) not from the importer (user or other job)")
    if db.query(ComboTagTemplate).filter(ComboTagTemplate.combo_id == dup.id).count():
        failed.append("template link: a tag template is linked")
    if db.query(PriceTagRequestLine).filter(PriceTagRequestLine.combo_id == dup.id).count():
        failed.append("price tag request: a request line points at it")
    if not any(_person_made(db, o) for o in owners):
        names = ", ".join(f'"{clean(o.name)}"' for o in owners)
        failed.append(f"owner combo {names} not made or edited by a person")
    if failed:
        return False, "; ".join(failed)
    made = next(
        (r.changed_at for r in rows if r.job_id == IMPORT_JOB_ID and r.entity_id == dup.id
         and r.action in ("CREATE", "INSERT")),
        None,
    )
    when = made.strftime("%d/%m/%Y %H:%M") if made else "unknown"
    return True, f"made by the importer on {when}, untouched, unused"


def run(db, entries: list, company_id: str, apply: bool) -> list[tuple[str, str, str, str, str]]:
    codes = {(e.get("host_code") or "").strip() for e in entries if isinstance(e, dict) and e.get("aka")}
    found = products_by_code(db, company_id, codes)
    rows = []
    for entry in entries:
        if not isinstance(entry, dict) or not entry.get("aka"):
            continue
        host_code = (entry.get("host_code") or "").strip()
        name = (entry.get("combo_name") or entry.get("title") or "").strip()
        akas = {str(a).strip().lower() for a in entry["aka"] if str(a).strip()}
        host = found.get(host_code.upper())
        lead = (clean(host_code), clean(name))
        if host is None:
            rows.append(("NO OWNER COMBO", *lead, "-", "host not found"))
            continue
        query = db.query(ProductCombo).filter(ProductCombo.host_product_id == host.id)
        combos = query.with_for_update(of=ProductCombo).all() if apply else query.all()
        owners = [c for c in combos if (c.name or "").strip().lower() in akas]
        dup = next((c for c in combos if (c.name or "").strip().lower() == name.lower()), None)
        owner_text = clean(", ".join(c.name for c in owners)) or "-"
        if not owners:
            rows.append(("NO OWNER COMBO", *lead, owner_text, ""))
        elif dup is None:
            rows.append(("NO DUPLICATE", *lead, owner_text, ""))
        else:
            ok, details = judge(db, dup, owners)
            if ok and apply:
                ProductComboService(db).delete(dup.id)
            rows.append(("DELETE" if ok else "KEEP", *lead, owner_text, details))
    return rows


def main(argv: Optional[Sequence[str]] = None, db=None, out: Optional[TextIO] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--file", default=DEFAULT_SEED, help="the combos seed (JSON list)")
    parser.add_argument("--company", default="SRT", help="company code (default SRT)")
    parser.add_argument("--apply", action="store_true", help="delete (default: dry run)")
    args = parser.parse_args(list(argv) if argv is not None else None)
    out = out or sys.stdout
    try:
        entries = read_seed(args.file)
    except Exception as exc:
        out.write(f"cannot read {args.file}: {exc}\n")
        return 1

    owns_session = db is None
    if owns_session:
        from app.database import SessionLocal

        db = SessionLocal()
    try:
        if not args.apply:
            db.rollback()
            db.execute(text("SET TRANSACTION READ ONLY"))
        with company_scope(db, None):
            company = db.query(Company).filter(func.upper(Company.code) == args.company.upper()).first()
            company_id = company.id if company else None
        if company_id is None:
            db.rollback()
            out.write(f"unknown company code: {args.company}\n")
            return 1

        register_audit_listeners()
        stamp_actor(AuditActor(actor_type="system", job_id=JOB_ID), db=db)
        real_commit = db.commit
        if args.apply:
            db.commit = db.flush
        try:
            with company_scope(db, frozenset({company_id})):
                rows = run(db, entries, company_id, args.apply)
            if args.apply:
                real_commit()
            else:
                db.rollback()
        except Exception as exc:
            db.rollback()
            out.write(f"FAILED, nothing changed: {clean(str(exc)[:300])}\n")
            return 2
        finally:
            if args.apply:
                del db.commit
            clear_actor(db)

        for row in rows:
            verdict, host, name, owner, details = row
            out.write(f"{verdict} | {host} | {name} | owner: {owner} | {details}\n")
        for verdict in VERDICT_ORDER:
            count = sum(1 for row in rows if row[0] == verdict)
            if count:
                out.write(f"{verdict}: {count}\n")
        if not args.apply:
            out.write("DRY RUN: nothing written. Run with --apply to delete.\n")
        return 0
    finally:
        if owns_session:
            db.close()


if __name__ == "__main__":
    sys.exit(main())
