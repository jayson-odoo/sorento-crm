#!/usr/bin/env python3
"""DEV ONLY: seed the combo shapes the price tag lane is hand tested with.

Under one company (default SRT) it makes sure these combos exist on REAL products (a missing
code is reported and skipped, a product is never created), through the importer's own functions
(`ProductComboService`, `set_combo_templates`), then creates the starter templates and links every
published starter that fits each of these combos and the combos already on the listed hosts.

Matched on host + name, so a re-run changes nothing. Dry run by default; `--apply` writes.

It refuses to run unless the connected database name has a token `dev` or `ci` (the name split
on anything that is not a letter or digit, so `sorento_dev_1028` passes), and refuses outright if
any token is `prod` or `production`.

USAGE
-----
    cd sorento_crm_backend
    venv/bin/python scripts/seed_pricetag_combo_shapes_dev.py            # dry run
    venv/bin/python scripts/seed_pricetag_combo_shapes_dev.py --apply
"""
from __future__ import annotations

import argparse
import os
import sys
from typing import Optional, Sequence, TextIO

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import func  # noqa: E402

from app.audit_context import AuditActor, clear_actor, stamp_actor  # noqa: E402
from app.models.base import company_scope  # noqa: E402
from app.models.company import Company  # noqa: E402
from app.models.product import Product  # noqa: E402
from app.models.product_combo import ProductCombo  # noqa: E402
from app.services.audit_service import register_audit_listeners  # noqa: E402
from app.services.dealer_kit.pricing import _no_selling_price_product_ids  # noqa: E402
from app.services.product_combo_service import ProductComboService  # noqa: E402
from scripts import import_product_combos as importer  # noqa: E402

JOB_ID = "seed_pricetag_combo_shapes_dev"
ALLOWED_TOKENS = {"dev", "ci"}
REFUSED_TOKENS = {"prod", "production"}

#: The combos to ensure, in the importer's seed format. Names and group names are data.
SHAPES = [
    {"id": "basin-tap", "host_code": "SRTWB1419-BL", "combo_name": "Basin + tap",
     "components": [{"code": "SRTWT7449-BL", "role": ""}]},
    {"id": "basin-tap-colour", "host_code": "SRTWB1419-BL", "combo_name": "Basin + tap colour",
     "choice_groups": [{"role": "Tap colour", "options": [{"code": "SRTWT7449-BL"}, {"code": "SRTWT7449-RG"}]}]},
    {"id": "sink-taps-topup", "host_code": "SRTKS7061", "combo_name": "Sink + taps with top-up",
     "choice_groups": [{"role": "Kitchen tap", "options": [
         {"code": "SRTKT1862SS"}, {"code": "SRTKT1863SS"}, {"code": "SRTKT1871SS"}]}],
     "topups": [{"code": "SRTKT71SS", "topup": 150}], "sp": 849},
]
#: Combo 4: the first group again plus one product that is discontinued on the database.
DISCONTINUED_COMBO = {
    "id": "basin-tap-colour-discontinued", "host_code": "SRTWB1419-BL",
    "combo_name": "Basin + tap colour (discontinued option)", "group": "Tap colour",
    "options": ["SRTWT7449-BL", "SRTWT7449-RG"], "discontinued_code": "SRTWT5831-BL",
}
#: Hosts whose existing combos also get the starters linked.
LINK_HOSTS = ["SRTKS7061", "SRTBF11829"]


def database_name(db) -> str:
    return db.get_bind().url.database or ""


def name_tokens(name: str) -> set[str]:
    """The lower-cased letter-and-digit pieces of a database name."""
    return set("".join(c if c.isalnum() else " " for c in name.lower()).split())


def refusal(name: str) -> Optional[str]:
    tokens = name_tokens(name)
    if tokens & REFUSED_TOKENS:
        return f"refusing: database {name!r} looks like production"
    if not tokens & ALLOWED_TOKENS:
        return f"refusing: database {name!r} has no 'dev' or 'ci' token"
    return None


def _extended(db, company_id: str, shape: dict) -> dict:
    """The shape plus the options other combos on the same host already hold in the same group
    (read from the database, by group name)."""
    groups = []
    for group in shape.get("choice_groups") or []:
        codes = [o["code"] for o in group["options"]]
        host = importer.products_by_code(db, company_id, {shape["host_code"]}).get(shape["host_code"].upper())
        if host is not None:
            with company_scope(db, frozenset({company_id})):
                for combo in db.query(ProductCombo).filter(ProductCombo.host_product_id == host.id).all():
                    for part in combo.parts:
                        code = part.part_product.product_code if part.part_product else None
                        if code and not part.part_product.is_discontinued and not part.is_upgrade and (part.choice_group or "").lower() == group["role"].lower() \
                                and code.upper() not in {c.upper() for c in codes}:
                            codes.append(code)
        groups.append({"role": group["role"], "options": [{"code": c} for c in codes]})
    return {**shape, "choice_groups": groups} if groups else shape


def main(argv: Optional[Sequence[str]] = None, db=None, out: Optional[TextIO] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--company", default="SRT", help="company code (default SRT)")
    parser.add_argument("--apply", action="store_true", help="write (default: dry run)")
    args = parser.parse_args(list(argv) if argv is not None else None)
    out = out or sys.stdout

    owns_session = db is None
    if owns_session:
        from app.database import SessionLocal

        db = SessionLocal()
    try:
        name = database_name(db)
        out.write(f"database: {name}\n")
        reason = refusal(name)
        if reason:
            out.write(reason + "\n")
            return 1

        with company_scope(db, None):
            company = db.query(Company).filter(func.upper(Company.code) == args.company.upper()).first()
            company_id = company.id if company else None
        if company_id is None:
            out.write(f"unknown company code: {args.company}\n")
            return 1

        shapes = [_extended(db, company_id, shape) for shape in SHAPES]
        extra = DISCONTINUED_COMBO
        discontinued = importer.products_by_code(db, company_id, {extra["discontinued_code"]}).get(
            extra["discontinued_code"].upper()
        )
        if discontinued is not None and discontinued.is_discontinued:
            shapes.append(
                {"id": extra["id"], "host_code": extra["host_code"], "combo_name": extra["combo_name"],
                 "choice_groups": [{"role": extra["group"], "options": [
                     {"code": c} for c in [*extra["options"], extra["discontinued_code"]]]}]}
            )
        else:
            out.write("no discontinued option seeded\n")

        codes = {s["host_code"] for s in shapes} | set(LINK_HOSTS)
        for shape in shapes:
            codes.update(part["code"] for part in importer.wanted_parts(shape))
        found = importer.products_by_code(db, company_id, codes)
        no_sp_ids = frozenset(
            db.execute(_no_selling_price_product_ids([p.id for p in found.values()])).scalars().all()
        ) if found else frozenset()

        register_audit_listeners()
        stamp_actor(AuditActor(actor_type="system", job_id=JOB_ID), db=db)
        try:
            # Like the importer's own main: it sets the company scope itself.
            importer.create_templates(db, company_id, args.apply, out)
            with company_scope(db, frozenset({company_id})):
                published = [
                    (t, needs) for t, needs in importer.published_templates(db, company_id)
                    if t.name in {s[0] for s in importer.STARTER_SHAPES}
                ]
                combo_ids: list[str] = []
                for shape in shapes:
                    host = found.get(shape["host_code"].upper())
                    row = importer.process_entry(
                        db, shape, host, found, None, args.apply,
                        published=published, no_sp_ids=no_sp_ids,
                    )
                    out.write(f"{shape['id']}: {row['status']} {row['differences']} {row['notes']}".rstrip() + "\n")
                    if row["unsure"]:
                        out.write(f"  not loaded: {row['unsure']}\n")
                    if args.apply and host is not None:
                        combo = (
                            db.query(ProductCombo)
                            .filter(ProductCombo.host_product_id == host.id,
                                    func.lower(ProductCombo.name) == shape["combo_name"].lower())
                            .first()
                        )
                        if combo is not None:
                            combo_ids.append(combo.id)
                            if shape["id"] == extra["id"]:
                                _add_discontinued(db, combo, discontinued, extra["group"], published, out)
                # The combos already on the listed hosts get the starters that fit too.
                for code in LINK_HOSTS:
                    host = found.get(code.upper())
                    if host is None:
                        out.write(f"host {code} not found, nothing linked\n")
                        continue
                    for combo in db.query(ProductCombo).filter(ProductCombo.host_product_id == host.id).all():
                        note = importer.link_fitting_templates(db, combo, published, args.apply)
                        if args.apply:
                            db.commit()
                        out.write(f"{code} / {combo.name}: {note or 'links already in place'}\n")
            if not args.apply:
                db.rollback()
                out.write("DRY RUN: nothing written. Run with --apply.\n")
        finally:
            clear_actor(db)
        return 0
    finally:
        if owns_session:
            db.close()


def _add_discontinued(db, combo, product, group: str, published, out) -> None:
    """The discontinued option goes in directly: the importer never loads a discontinued code."""
    if any(part.part_product_id == product.id for part in combo.parts):
        return
    ProductComboService(db).add_part(combo.id, product.id, group)
    out.write(f"added discontinued option {product.product_code} to {combo.name}\n")


if __name__ == "__main__":
    sys.exit(main())
