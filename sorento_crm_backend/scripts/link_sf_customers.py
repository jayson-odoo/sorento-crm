#!/usr/bin/env python3
"""Link old Sponsorship Forms to their customer, from a list the owner reviews first (one-off).

SF-CUSTOMER-LINK (documentation/plans/procurement/PLAN-sf-customer-link-19oct.md). An SF saved
before the customer picker has no `customer_id`, only the typed `customer_name`, so
`backfill_sf_sales_type.py` cannot fill its sales type. This proposes a link per SF and writes the
proposal to a CSV; nothing is linked until the owner has reviewed that CSV and passes it back.

A proposal is LINK only when exactly ONE active customer of the company has the typed name,
compared after trimming, collapsing whitespace and ignoring case. Nothing looser: no fuzzy match,
no prefix/suffix stripping. Other statuses: AMBIGUOUS (two or more), NO MATCH (none, or blank),
ALREADY LINKED (the SF has a customer link; never touched).

Run from sorento_crm_backend/ (the owner runs it on prod; the PR changes no data):
    python scripts/link_sf_customers.py --csv proposal.csv                 # dry-run, writes nothing
    python scripts/link_sf_customers.py --apply --from-csv proposal.csv    # links the LINK rows
    python scripts/backfill_sf_sales_type.py                               # then the sales type

`--apply` links only rows still marked LINK in the file (delete a row to skip it). Each is re-run
against the database first and linked only when the whole row is still what the owner reviewed
(an edited row, or an SF or match that changed since the dry run, is skipped and counted). It never
overwrites a customer link and commits all links in one transaction. Idempotent: a second
`--apply` links nothing. The CSV holds real customer names: by default it goes to the temp
directory, never the working directory.
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
import tempfile
from collections import Counter

# Allow `from app.*` imports when invoked from the backend directory.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models.base import set_company_scope
from app.models.order import Customer
from app.models.procurement import PurchaseRequestHeader
from app.services.audit_service import register_audit_listeners
from app.services.company_scope import DEFAULT_COMPANY_ID, register_company_scope_listeners
from app.services.debtor_type import SALES_TYPE_FOR_DEBTOR_TYPE, link_customer

LINK = "LINK"
NO_MATCH = "NO MATCH"
AMBIGUOUS = "AMBIGUOUS"
ALREADY_LINKED = "ALREADY LINKED"
STATUSES = (LINK, NO_MATCH, AMBIGUOUS, ALREADY_LINKED)

CSV_FIELDS = (
    "status",
    "form_number",
    "typed_customer",
    "customer_code",
    "customer_name",
    "debtor_type",
    "sales_type",
    "sf_id",
    "customer_id",
)
DEFAULT_CSV = os.path.join(tempfile.gettempdir(), "sf_customer_link_proposal.csv")
# A cell starting with one of these runs as a formula when the CSV is opened in a spreadsheet, and
# typed_customer is free text (portal SFs): such a cell is written with a leading apostrophe.
_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


def _key(name) -> str:
    """Trim, collapse whitespace, ignore case. The only normalisation a match gets."""
    return " ".join((name or "").split()).lower()


def _sales_type(debtor_type) -> str:
    return SALES_TYPE_FOR_DEBTOR_TYPE.get(debtor_type, "") if debtor_type else ""


def _row(header, status, customers=()) -> dict:
    row = {
        "status": status,
        "form_number": header.request_number or "",
        "typed_customer": header.customer_name or "",
        "customer_code": "; ".join(sorted(c.customer_code for c in customers)),
        "customer_name": "",
        "debtor_type": "",
        "sales_type": "",
        "sf_id": str(header.id),
        "customer_id": "",
    }
    if len(customers) == 1:
        (c,) = customers
        row.update(
            customer_name=c.customer_name,
            debtor_type=c.debtor_type or "",
            sales_type=_sales_type(c.debtor_type),
            customer_id=str(c.id),
        )
    return row


def _active_by_name(db, company_id) -> dict:
    by_name: dict = {}
    for c in (
        db.query(Customer)
        .filter(Customer.company_id == company_id, Customer.is_active.is_(True))
        .all()
    ):
        by_name.setdefault(_key(c.customer_name), []).append(c)
    return by_name


def _propose_one(db, header, by_name) -> dict:
    if header.customer_id:
        linked = db.query(Customer).filter(Customer.id == header.customer_id).first()
        return _row(header, ALREADY_LINKED, [linked] if linked else ())
    key = _key(header.customer_name)
    matches = by_name.get(key, []) if key else []
    if not matches:
        return _row(header, NO_MATCH)
    return _row(header, LINK if len(matches) == 1 else AMBIGUOUS, matches)


def _sponsorship_forms(db):
    return db.query(PurchaseRequestHeader).filter(PurchaseRequestHeader.request_type == "sponsorship_form")


def propose(db, company_id) -> list[dict]:
    """One row per Sponsorship Form (CSV_FIELDS), matched against `company_id`'s active customers.

    Reads only: a dry run is this plus `write_csv`.
    """
    by_name = _active_by_name(db, company_id)
    headers = _sponsorship_forms(db).order_by(
        PurchaseRequestHeader.request_number, PurchaseRequestHeader.id
    ).all()
    return [_propose_one(db, h, by_name) for h in headers]


def _cell(value) -> str:
    value = value or ""
    return "'" + value if value.startswith(_FORMULA_START) else value


def _uncell(value) -> str:
    """A CSV cell back to its value, whether the spreadsheet kept the guard apostrophe or not."""
    value = value or ""
    if value.startswith("'") and value[1:].startswith(_FORMULA_START):
        value = value[1:]
    return value.strip()


def write_csv(rows, path) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows({k: _cell(v) for k, v in r.items()} for r in rows)


def _reviewed_links(path) -> dict:
    """sf_id -> row for every row the reviewed CSV still marks LINK. A form listed twice is refused."""
    with open(path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        missing = set(CSV_FIELDS) - set(reader.fieldnames or ())
        if missing:
            raise ValueError(f"{path} is not a proposal CSV from this script: no {', '.join(sorted(missing))} column")
        seen, links = set(), {}
        for r in reader:
            sf_id = _uncell(r["sf_id"])
            if not sf_id:
                continue
            if sf_id in seen:
                raise ValueError(f"{path} lists sponsorship form {_uncell(r['form_number']) or sf_id} twice")
            seen.add(sf_id)
            if _uncell(r["status"]) == LINK:
                links[sf_id] = r
        return links


def apply_csv(db, path, company_id) -> dict:
    """Link the reviewed CSV's LINK rows, each re-checked now. One transaction.

    A row is linked only when the SF is still unlinked and the proposal, run again now, is still
    LINK with every column equal to the reviewed row (so a row edited to another customer, or a
    match that changed, is skipped). Returns `{"reviewed", "linked", "skipped_already_linked",
    "skipped_changed"}`.
    """
    reviewed = _reviewed_links(path)
    by_name = _active_by_name(db, company_id)
    counts = Counter()
    try:
        # Locked: a staff link saved meanwhile waits for this commit instead of being overwritten.
        headers = (
            _sponsorship_forms(db)
            .filter(PurchaseRequestHeader.id.in_(list(reviewed)))
            .with_for_update(of=PurchaseRequestHeader)
            .all()
            if reviewed
            else []
        )
        found = {str(h.id): h for h in headers}
        for sf_id, row in reviewed.items():
            header = found.get(sf_id)
            now = _propose_one(db, header, by_name) if header is not None else None
            if now is not None and now["status"] == ALREADY_LINKED:
                counts["skipped_already_linked"] += 1
                continue
            if now is None or now["status"] != LINK or any(
                _uncell(row[f]) != (now[f] or "").strip() for f in CSV_FIELDS if f != "status"
            ):
                counts["skipped_changed"] += 1
                continue
            # The staff form's link path: active + company-visible, and the customer's own name
            # becomes customer_name (procurement_service._apply_customer_link).
            header.customer_id, header.customer_name = link_customer(db, now["customer_id"])
            counts["linked"] += 1
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {
        "reviewed": len(reviewed),
        "linked": counts["linked"],
        "skipped_already_linked": counts["skipped_already_linked"],
        "skipped_changed": counts["skipped_changed"],
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--csv", default=DEFAULT_CSV, help="Dry run: where to write the proposal (default: temp dir).")
    parser.add_argument("--apply", action="store_true", help="Link the LINK rows of --from-csv. Default is dry-run.")
    parser.add_argument("--from-csv", help="The reviewed proposal CSV (required with --apply).")
    parser.add_argument("--company-id", default=DEFAULT_COMPANY_ID, help="Match this company's customers only.")
    args = parser.parse_args(argv)
    if args.apply and not args.from_csv:
        parser.error("--apply needs --from-csv <the reviewed proposal CSV>")

    # A script process has no app startup: without these the company scope below is a no-op and
    # the links write no audit rows (PurchaseRequestHeader is __audit_track__).
    register_company_scope_listeners()
    register_audit_listeners()
    db = SessionLocal()
    # Scoped to the one company whose customers it matches: purchase_requests has no company of its
    # own, and link_customer then refuses any other company's customer.
    set_company_scope(db, frozenset({args.company_id}))
    try:
        if args.apply:
            result = apply_csv(db, args.from_csv, args.company_id)
            print(
                f"Done. Reviewed LINK rows: {result['reviewed']}. Linked: {result['linked']}. "
                f"Skipped, already linked: {result['skipped_already_linked']}. "
                f"Skipped, changed since the dry run: {result['skipped_changed']}."
            )
            print("Next: python scripts/backfill_sf_sales_type.py (dry run), then --apply, to fill Sales Type.")
            return 0
        rows = propose(db, args.company_id)
        for r in rows:
            print(f"  {r['status']:<14} {r['form_number'] or r['sf_id']}  ->  {r['customer_code'] or '-'}")
        write_csv(rows, args.csv)
        tally = Counter(r["status"] for r in rows)
        print(
            f"[dry-run] {len(rows)} sponsorship form(s). "
            + ", ".join(f"{s}: {tally.get(s, 0)}" for s in STATUSES)
            + f". Proposal written to {args.csv}."
        )
        print("No writes. Review the CSV (delete any row to skip it), then re-run with --apply --from-csv <file>.")
        return 0
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
