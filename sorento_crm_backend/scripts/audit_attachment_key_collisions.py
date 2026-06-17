#!/usr/bin/env python3
"""READ-ONLY audit of attachment storage-key collisions and flat-key blast radius.

Background: generic resource attachment keys are `{entity_type}/{stored_filename}` — no
folder/id scope — so two live rows (same type + same name, different folders) can share one
object, silently clobbering each other. Portal (`portal/{contact}/{uuid}{ext}`) and promotion
(`promotion/{entity_id}/{name}`) keys are already scoped. This script quantifies the damage
BEFORE the uuid-segregation migration (see PLAN-attachment-key-uuid-segregation.md).

Run from sorento_crm_backend/:
    python scripts/audit_attachment_key_collisions.py [--limit N]

Makes ZERO writes — DB and storage untouched. Reports:
  * SHARED KEYS  — keys claimed by >1 live attachment (already-corrupted; the migration must
                   NOT auto-relocate these, they need manual disambiguation).
  * FLAT-SCHEME  — count of rows on the `{type}/{name}` shape = migration blast radius.
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import defaultdict

# Allow `from app.*` imports when invoked from the backend directory.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models.resources import Attachment
from app.services.storage_router import extract_key


def _segments(key: str) -> list[str]:
    return [s for s in (key or "").split("/") if s]


def _looks_uuid(s: str) -> bool:
    # 8-4-4-4-12 hex; cheap structural check, no validation lib needed.
    parts = s.split("-")
    return len(parts) == 5 and len("".join(parts)) == 32 and all(
        c in "0123456789abcdefABCDEF" for c in "".join(parts)
    )


def _scheme(key: str) -> str:
    """Classify a key into portal / promotion / uuid-scoped / flat / other."""
    segs = _segments(key)
    if not segs:
        return "empty"
    top = segs[0].lower()
    if top == "portal":
        return "portal"            # portal/{contact}/{uuid}{ext}
    if top == "promotion" and len(segs) >= 3:
        return "promotion"         # promotion/{entity_id}/{name}
    if len(segs) >= 3 and _looks_uuid(segs[1]):
        return "uuid-scoped"       # {type}/{uuid}/{name} — already migrated
    if len(segs) == 2:
        return "flat"              # {type}/{name} — AT RISK, migration target
    return "other"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=None, help="cap rows scanned")
    args = ap.parse_args()

    db = SessionLocal()
    by_key: dict[str, list[Attachment]] = defaultdict(list)
    scheme_counts: dict[str, int] = defaultdict(int)
    no_key = 0
    try:
        q = db.query(Attachment).filter(Attachment.is_deleted == False)  # noqa: E712
        q = q.order_by(Attachment.created_at.asc())
        if args.limit:
            q = q.limit(args.limit)
        rows = q.all()
        for a in rows:
            key = extract_key(a.file_path)
            if not key:
                no_key += 1
                continue
            by_key[key].append(a)
            scheme_counts[_scheme(key)] += 1
    finally:
        db.close()

    shared = {k: v for k, v in by_key.items() if len(v) > 1}

    print(f"scanned {sum(len(v) for v in by_key.values())} keyed row(s); {no_key} with no resolvable key\n")
    print("scheme breakdown:")
    for s in sorted(scheme_counts):
        print(f"  {s:14s} {scheme_counts[s]}")
    print(f"\nflat-scheme rows (migration blast radius): {scheme_counts.get('flat', 0)}")

    print(f"\nSHARED KEYS (>1 live row — already clobbered, needs manual review): {len(shared)}")
    for key, atts in sorted(shared.items()):
        print(f"  {key}")
        for a in atts:
            print(f"      id={a.id} original={a.original_filename!r} dir={a.directory_id} type={a.target_entity_type}")

    if not shared:
        print("  (none — no active clobbers)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
