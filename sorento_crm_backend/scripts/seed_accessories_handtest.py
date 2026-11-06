#!/usr/bin/env python3
"""Dev-only: create the combos the PRICETAG-ACCESSORIES hand test uses.

WHY
---
The owner's examples name combos the dev copy does not have (crew pass, 6 Nov): SRTKS7061-BL as
"Kitchen sink with 1 tap" and "with 2 taps", and SRTWB7065 with tap SRTWT7202 plus a FREE SRTW5000
popup waste. This creates them through the same services the product page uses, so the hand test
runs on the owner's own products.

WHAT IT CREATES (company SRT by default; every name ends in "(hand test)" so it is easy to spot)
-------------------------------------------------------------------------------------------------
* SRTKS7061-BL "Kitchen sink with 1 tap (hand test)": fixed part = first tap; Free items =
  DRAINER, PULL OUT DRAINER (library accessories, created when missing; DRAINER gets the spec
  "390x300x140, Depth: 160mm" when it has none).
* SRTKS7061-BL "Kitchen sink with 2 taps (hand test)": fixed parts = both taps; same Free items.
* SRTWB7065 "Basin with tap (hand test)": fixed part = SRTWT7202; Free items = product SRTW5000.

Idempotent: a combo that exists by host + name is reused, a missing part is added, and the Free
items list is set to exactly the above. Nothing else is touched.

USAGE
-----
  python scripts/seed_accessories_handtest.py                 # dry run: says what it would do
  python scripts/seed_accessories_handtest.py --apply         # write (dev ENVIRONMENT only)
  python scripts/seed_accessories_handtest.py --cleanup --apply
      # after the hand test: deletes every combo named "... (hand test)" on SRTKS7061-BL and
      # SRTWB7065, and every UNUSED library accessory named "crew-pass-..." (a used one is
      # listed, never deleted). Library accessories the migration made are never touched.
  --taps SRTWT7202,SRTKT1632SS   the sink's two taps (default shown); --company SRT
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
from app.models.product_combo import ProductCombo, ProductComboPart  # noqa: E402
from app.services.accessory_service import AccessoryService  # noqa: E402
from app.services.audit_service import register_audit_listeners  # noqa: E402
from app.services.product_combo_service import ProductComboService  # noqa: E402

JOB_ID = "seed_accessories_handtest"
SINK = "SRTKS7061-BL"
BASIN, BASIN_TAP, WASTE = "SRTWB7065", "SRTWT7202", "SRTW5000"
DRAINER_SPEC = "390x300x140, Depth: 160mm"
DEV_ENVIRONMENTS = {"development", "dev", "local", "test", "testing", "staging"}


def _environment() -> str:
    from app.config import settings

    return (getattr(settings, "environment", "") or "").strip().lower()


def plan(taps: list[str]) -> list[dict]:
    """The combos to make: host code, name, fixed part codes, free items (("accessory", name, spec)
    or ("product", code, None))."""
    sink_free = [("accessory", "DRAINER", DRAINER_SPEC), ("accessory", "PULL OUT DRAINER", None)]
    return [
        {"host": SINK, "name": "Kitchen sink with 1 tap (hand test)", "parts": taps[:1], "free": sink_free},
        {"host": SINK, "name": "Kitchen sink with 2 taps (hand test)", "parts": taps[:2], "free": sink_free},
        {
            "host": BASIN,
            "name": "Basin with tap (hand test)",
            "parts": [BASIN_TAP],
            "free": [("product", WASTE, None)],
        },
    ]


def _product(db, code: str, company_id: str) -> Optional[Product]:
    return (
        db.query(Product)
        .filter(func.upper(Product.product_code) == code.upper(), Product.company_id == company_id)
        .first()
    )


def seed(db, company_id: str, taps: list[str], apply: bool, out: TextIO) -> int:
    """Returns 0 when every product exists (and, with `apply`, everything was written), else 1."""
    wanted = plan(taps)
    codes = {code for combo in wanted for code in [combo["host"], *combo["parts"]]}
    codes |= {name for combo in wanted for kind, name, _ in combo["free"] if kind == "product"}
    found = {code: _product(db, code, company_id) for code in sorted(codes)}
    missing = [code for code, row in found.items() if row is None]
    if missing:
        out.write(f"missing products (nothing written): {', '.join(missing)}\n")
        out.write("pick other taps with --taps, or create these products first\n")
        return 1

    combos = ProductComboService(db)
    accessories = AccessoryService(db)
    for combo in wanted:
        host = found[combo["host"]]
        existing = (
            db.query(ProductCombo)
            .filter(ProductCombo.host_product_id == host.id, ProductCombo.name == combo["name"])
            .first()
        )
        verb = "reuse" if existing else "create"
        out.write(
            f"{verb} {combo['host']} \"{combo['name']}\": parts {', '.join(combo['parts'])}; free "
            f"{', '.join(name for _, name, _ in combo['free'])}\n"
        )
        if not apply:
            continue
        combo_id = existing.id if existing else combos.create(host.id, combo["name"], created_by=None)["id"]
        have = {
            part_id
            for (part_id,) in db.query(ProductComboPart.part_product_id).filter(
                ProductComboPart.combo_id == combo_id
            )
        }
        for code in combo["parts"]:
            if found[code].id not in have:
                combos.add_part(combo_id, found[code].id, None)
        items = []
        for kind, name, spec in combo["free"]:
            if kind == "product":
                items.append({"product_id": found[name].id})
                continue
            row = accessories.find_or_create(name, company_id)
            if spec and not row.spec:
                row.spec = spec
            items.append({"accessory_id": row.id})
        db.flush()
        accessories.set_combo_list(combo_id, items)
    if not apply:
        out.write("dry run: nothing written (add --apply)\n")
    return 0


def cleanup(db, company_id: str, apply: bool, out: TextIO) -> int:
    """Remove what the hand test leaves behind (crew pass 2, 6 Nov)."""
    from app.models.accessory import Accessory

    combos = ProductComboService(db)
    accessories = AccessoryService(db)
    hosts = [row for row in (_product(db, code, company_id) for code in (SINK, BASIN)) if row is not None]
    rows = (
        db.query(ProductCombo)
        .filter(
            ProductCombo.host_product_id.in_([host.id for host in hosts]),
            ProductCombo.name.like("%(hand test)"),
        )
        .all()
        if hosts
        else []
    )
    for combo in rows:
        out.write(f'delete combo "{combo.name}" on {combo.host_product.product_code}\n')
        if apply:
            combos.delete(combo.id)
    leftovers = (
        db.query(Accessory)
        .filter(Accessory.company_id == company_id, func.lower(Accessory.name).like("crew-pass-%"))
        .all()
    )
    for item in leftovers:
        counts = accessories._counts([item.id]).get(item.id, (0, 0))
        if counts != (0, 0):
            out.write(f'keep accessory "{item.name}": still used on {counts[0]} products, {counts[1]} combos\n')
            continue
        out.write(f'delete accessory "{item.name}"\n')
        if apply:
            accessories.delete(item.id)
    if not apply:
        out.write("dry run: nothing deleted (add --apply)\n")
    return 0


def main(argv: Optional[Sequence[str]] = None, db=None, out: Optional[TextIO] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="write (default: dry run)")
    parser.add_argument("--cleanup", action="store_true", help="remove the hand-test combos and crew-pass accessories")
    parser.add_argument("--company", default="SRT", help="company code (default SRT)")
    parser.add_argument("--taps", default="SRTWT7202,SRTKT1632SS", help="the sink's taps, comma separated")
    args = parser.parse_args(list(argv) if argv is not None else None)
    out = out or sys.stdout

    taps = [code.strip() for code in args.taps.split(",") if code.strip()]
    if len(taps) < 2:
        out.write("--taps needs two product codes\n")
        return 1
    if args.apply and _environment() not in DEV_ENVIRONMENTS:
        out.write(f"refused: ENVIRONMENT is {_environment()!r}; this seed runs on a dev copy only\n")
        return 1

    owns_session = db is None
    if owns_session:
        from app.database import SessionLocal

        db = SessionLocal()
    try:
        with company_scope(db, None):
            company = db.query(Company).filter(func.upper(Company.code) == args.company.upper()).first()
        if company is None:
            out.write(f"unknown company code: {args.company}\n")
            return 1
        register_audit_listeners()
        stamp_actor(AuditActor(actor_type="system", job_id=JOB_ID), db=db)
        try:
            with company_scope(db, frozenset({company.id})):
                if args.cleanup:
                    code = cleanup(db, company.id, args.apply, out)
                else:
                    code = seed(db, company.id, taps, args.apply, out)
            if code == 0 and args.apply:
                db.commit()
            else:
                db.rollback()
            return code
        finally:
            clear_actor(db)
    finally:
        if owns_session:
            db.close()


if __name__ == "__main__":
    raise SystemExit(main())
