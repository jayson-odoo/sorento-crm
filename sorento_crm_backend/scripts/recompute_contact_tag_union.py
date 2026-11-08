#!/usr/bin/env python3
"""TAG-UNION one-off: move every tagged contact from the old most-restrictive tag rule to the new
"tags add up" rule (plan documentation/plans/contacts/PLAN-tag-union-08nov.md).

Per tagged contact it seeds the snapshot from TODAY's rule (a value that differs from what the tags
say today is kept as the contact's own change, owner Q3), then recomputes with the new rule and writes
what changes, one audit row per changed contact ("Tag union recompute: ...").

Run from sorento_crm_backend/ AFTER `alembic upgrade head`:

    python scripts/recompute_contact_tag_union.py                 # dry run (default): report only
    python scripts/recompute_contact_tag_union.py --apply --expect N

The dry run writes nothing (everything runs inside a transaction that is rolled back). `--apply`
refuses, writing nothing, unless N equals the dry run's "contacts changed" count, so the numbers the
owner reviewed are the numbers that get written.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal  # noqa: E402
from app.services import contact_tag_union  # noqa: E402

RULE = "=" * 72


def _print(report: dict) -> None:
    print(RULE)
    print("TAG-UNION recompute " + ("(APPLIED)" if report["applied"] else "(dry run, nothing written)"))
    print(RULE)
    rows = [
        ("Tagged contacts checked", report["contacts"]),
        ("Contacts changed", report["changed"]),
        ("  of which gain access (widened)", report["widened"]),
        ("  of which lose access (narrowed)", report["narrowed"]),
        ("Contacts with no company today despite a companies tag", report["empty_companies_today"]),
        ("Contacts keeping own changes (differ from their tags after)", report["own_changes"]),
        ("Contacts holding only inactive tags", report["inactive_only"]),
        ("Contacts that failed (nothing written for them)", report["failed"]),
    ]
    width = max(len(r[0]) for r in rows)
    for label, n in rows:
        print(f"{label.ljust(width)}  {n}")
    if report["by_setting"]:
        print("\nChanged contacts per setting:")
        for label, n in sorted(report["by_setting"].items(), key=lambda kv: (-kv[1], kv[0])):
            print(f"  {label}: {n}")
    print(RULE)
    if not report["applied"]:
        print(f"To write it: python scripts/recompute_contact_tag_union.py --apply --expect {report['changed']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="write the changes (needs --expect)")
    parser.add_argument("--expect", type=int, default=None, help="the dry run's 'Contacts changed' count")
    parser.add_argument("--json", action="store_true", help="print the report as JSON")
    args = parser.parse_args(argv)
    if args.apply and args.expect is None:
        parser.error("--apply needs --expect N (the dry run's 'Contacts changed' count)")

    db = SessionLocal()
    try:
        report = contact_tag_union.run(db, apply=args.apply, expect=args.expect)
        if args.apply:
            db.commit()
        else:
            db.rollback()
    except ValueError as exc:
        db.rollback()
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    finally:
        db.close()
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        _print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
