#!/usr/bin/env python3
"""
Backfill respond_inbox_url for portal-created submissions.

Targets complaints, stock_inquiries, purchase_requests rows that have
contact_id and space_id. Resolves the stored contact_id (internal RespondContact.id)
to respond_contacts.respond_io_id and rewrites the URL as
{base}/space/{space_id}/inbox/{respond_io_id}.

Re-runs are safe: only rows whose URL differs from the freshly-computed correct
URL are updated. This also corrects rows previously written with the internal
UUID instead of the Respond.io contact id.

Run from sorento_crm_backend/ with: python scripts/backfill_portal_respond_inbox_url.py
Add --dry-run to preview counts without writing.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text

from app.config import settings
from app.database import engine


TABLES = ("complaints", "stock_inquiries", "purchase_requests")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Report counts only; no writes.")
    args = parser.parse_args()

    base = (settings.respond_app_base_url or "").rstrip("/")
    if not base:
        print("ERROR: respond_app_base_url not configured.", file=sys.stderr)
        sys.exit(1)
    print(f"Base URL: {base}")
    print(f"Mode: {'DRY-RUN' if args.dry_run else 'WRITE'}")

    with engine.connect() as conn:
        for table in TABLES:
            candidate_sql = f"""
                SELECT t.id,
                       :base || '/space/' || TRIM(t.space_id) || '/inbox/' || TRIM(rc.respond_io_id) AS new_url
                FROM {table} t
                JOIN respond_contacts rc
                  ON rc.id = TRIM(t.contact_id) OR rc.respond_io_id = TRIM(t.contact_id)
                WHERE t.contact_id IS NOT NULL AND TRIM(t.contact_id) <> ''
                  AND t.space_id IS NOT NULL AND TRIM(t.space_id) <> ''
                  AND rc.respond_io_id IS NOT NULL AND TRIM(rc.respond_io_id) <> ''
                  AND (t.respond_inbox_url IS DISTINCT FROM
                       :base || '/space/' || TRIM(t.space_id) || '/inbox/' || TRIM(rc.respond_io_id))
            """
            count_row = conn.execute(
                text(f"SELECT count(*) FROM ({candidate_sql}) AS sub"),
                {"base": base},
            ).scalar_one()
            print(f"{table}: {count_row} row(s) need update")

            if args.dry_run or count_row == 0:
                continue

            result = conn.execute(
                text(
                    f"""
                    UPDATE {table} AS t
                    SET respond_inbox_url = sub.new_url
                    FROM ({candidate_sql}) AS sub
                    WHERE t.id = sub.id
                    """
                ),
                {"base": base},
            )
            conn.commit()
            print(f"  updated {result.rowcount} row(s)")

        skipped_sql = """
            SELECT count(*)
            FROM {table} t
            LEFT JOIN respond_contacts rc
              ON rc.id = TRIM(t.contact_id) OR rc.respond_io_id = TRIM(t.contact_id)
            WHERE t.contact_id IS NOT NULL AND TRIM(t.contact_id) <> ''
              AND t.space_id IS NOT NULL AND TRIM(t.space_id) <> ''
              AND (rc.id IS NULL OR rc.respond_io_id IS NULL OR TRIM(rc.respond_io_id) = '')
        """
        for table in TABLES:
            n = conn.execute(text(skipped_sql.format(table=table))).scalar_one()
            if n:
                print(f"WARN: {table}: {n} row(s) skipped (contact unresolved or missing respond_io_id)")


if __name__ == "__main__":
    main()
