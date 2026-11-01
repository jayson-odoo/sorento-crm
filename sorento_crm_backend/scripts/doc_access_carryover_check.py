"""DOC-ACCESS-SIMPLE carry-over proof: the deploy must change nobody's access.

Run against a THROWAWAY copy of the data (a database whose name contains "prod" is refused):

    python scripts/doc_access_carryover_check.py --database-url postgresql://... \
        [--seed-audiences "Technical Specifications=dealer,Certification=public"]

1. optionally sets `ai_audience` on the named types (the dev copy has every type off, which proves nothing);
2. computes every (contact, readable file) pair under TODAY's rule (`ai_audience` + the file's levels
   + the company rule), and each type's staff readability;
3. adds the two new columns if missing and runs the migration's own `backfill(bind)`;
4. computes the pairs under the NEW rule (`knowledge_service.contact_readable_clause`);
5. prints a per-type table and the number of differences; exits 1 on any difference.

It reads contacts through `respond_contact_*` tables only: no users table is needed.
"""
from __future__ import annotations

import argparse
import importlib.util
import sys
from collections import defaultdict
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
MIGRATION = BACKEND / "alembic" / "versions" / "das_0001_ai_read_ticks.py"


def _migration():
    spec = importlib.util.spec_from_file_location("das_0001_ai_read_ticks", MIGRATION)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _contacts(conn) -> dict:
    """contact id -> (active codes, company ids)."""
    codes = defaultdict(set)
    for cid, code in conn.execute(
        text(
            "SELECT r.contact_id, r.access_type_code FROM respond_contact_access_types r "
            "JOIN contact_access_types c ON c.code = r.access_type_code AND c.is_active IS TRUE"
        )
    ):
        codes[str(cid)].add(str(code))
    companies = defaultdict(set)
    for cid, co in conn.execute(text("SELECT respond_contact_id, company_id FROM respond_contact_companies")):
        companies[str(cid)].add(str(co))
    ids = {str(r[0]) for r in conn.execute(text("SELECT id FROM respond_contacts"))}
    return {i: (codes.get(i, set()), companies.get(i, set())) for i in ids}


def _company_ok(companies: set, file_company) -> bool:
    return bool(companies) and (file_company is None or str(file_company) in companies)


def _old_pairs(conn, contacts: dict) -> set:
    """(contact, file, type) pairs under today's rule (knowledge_service.py:692-703 + company)."""
    out = set()
    for cid, (codes, companies) in contacts.items():
        if not codes or not companies:
            continue
        rows = conn.execute(
            text(
                "SELECT a.id, a.attachment_type_id, a.company_id FROM attachments a "
                "JOIN attachment_types t ON t.id = a.attachment_type_id WHERE a.is_deleted = false AND ("
                "(t.ai_audience = 'public' AND jsonb_exists_any(a.access_levels, CAST(:codes AS text[]))) OR "
                "(t.ai_audience = 'dealer' AND jsonb_exists_any(a.access_levels, CAST(:dealer AS text[]))))"
            ),
            {"codes": sorted(codes), "dealer": sorted(c for c in codes if c != "end_user")},
        ).all()
        out |= {(cid, str(r[0]), str(r[1])) for r in rows if _company_ok(companies, r[2])}
    return out


def _new_pairs(session: Session, contacts: dict) -> set:
    from app.models.base import company_scope
    from app.models.resources import Attachment, AttachmentType
    from app.services import knowledge_service as ks

    out = set()
    with company_scope(session, None):
        for cid, (codes, companies) in contacts.items():
            if not codes or not companies:
                continue
            rows = (
                session.query(Attachment.id, Attachment.attachment_type_id, Attachment.company_id)
                .join(AttachmentType, AttachmentType.id == Attachment.attachment_type_id)
                .filter(Attachment.is_deleted.is_(False), ks.contact_readable_clause(sorted(codes)))
                .all()
            )
            out |= {(cid, str(r[0]), str(r[1])) for r in rows if _company_ok(companies, r[2])}
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--database-url", required=True)
    ap.add_argument("--seed-audiences", default="", help='"Type Name=dealer,Other=public" (throwaway databases only)')
    args = ap.parse_args(argv)

    name = make_url(args.database_url).database or ""
    if "prod" in name.lower():
        print(f"refusing: database name {name!r} contains 'prod'", file=sys.stderr)
        return 2

    engine = create_engine(args.database_url)
    with engine.begin() as conn:
        for pair in filter(None, (p.strip() for p in args.seed_audiences.split(","))):
            type_name, _, audience = pair.rpartition("=")
            if audience not in ("off", "staff", "dealer", "public") or not type_name:
                print(f"bad --seed-audiences entry {pair!r}", file=sys.stderr)
                return 2
            n = conn.execute(
                text("UPDATE attachment_types SET ai_audience = :a WHERE type_name = :n"), {"a": audience, "n": type_name.strip()}
            ).rowcount
            if not n:
                print(f"no type named {type_name!r}", file=sys.stderr)
                return 2

        contacts = _contacts(conn)
        old = _old_pairs(conn, contacts)
        type_names = {str(i): n for i, n in conn.execute(text("SELECT id, type_name FROM attachment_types"))}
        old_staff = {
            str(i): bool(s) for i, s in conn.execute(text("SELECT id, ai_audience <> 'off' FROM attachment_types"))
        }

        conn.execute(text("ALTER TABLE attachment_types ADD COLUMN IF NOT EXISTS ai_read_staff BOOLEAN NOT NULL DEFAULT false"))
        conn.execute(text("ALTER TABLE attachment_types ADD COLUMN IF NOT EXISTS ai_read_codes JSONB NOT NULL DEFAULT '[]'::jsonb"))
        _migration().backfill(conn)
        new_staff = {str(i): bool(s) for i, s in conn.execute(text("SELECT id, ai_read_staff FROM attachment_types"))}

    with Session(engine) as session:
        new = _new_pairs(session, contacts)

    old_by, new_by = defaultdict(int), defaultdict(int)
    for _, _, t in old:
        old_by[t] += 1
    for _, _, t in new:
        new_by[t] += 1
    print(f"{'type':40} {'old pairs':>10} {'new pairs':>10} {'staff old':>10} {'staff new':>10}")
    for tid in sorted(type_names, key=lambda t: type_names[t].lower()):
        print(
            f"{type_names[tid][:40]:40} {old_by[tid]:>10} {new_by[tid]:>10} "
            f"{str(old_staff[tid]):>10} {str(new_staff[tid]):>10}"
        )
    diff = len(old ^ new) + sum(1 for t in type_names if old_staff[t] != new_staff[t])
    print(f"contacts {len(contacts)}, old pairs {len(old)}, new pairs {len(new)}, differences {diff}")
    return 1 if diff else 0


if __name__ == "__main__":
    sys.exit(main())
