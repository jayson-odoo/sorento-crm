#!/usr/bin/env python3
"""Crew hand-test setup for PR #2219 (AC-REKEY-SAME-LINE). DEV COPIES ONLY.

Builds three hand-test sales orders and replays the AutoCount push that decides each one, so the
owner can look at all three cases side by side in the UI:

  HT-REKEY-SAME     line Seq 10 comes back with a NEW DtlKey, everything else equal (the fix:
                    the same line, its order inquiry row stays live, nothing cancelled, no email)
  HT-REKEY-REMOVED  line Seq 10 is gone from the push (a real removal: today's behaviour)
  HT-REKEY-CHANGED  line Seq 10 comes back with a NEW DtlKey AND a different qty (not the same
                    line: today's removal + a new line)

Each order is cloned from a real project SO on this database (`PICK_SQL`: its customer, the
item, location, price and delivery date of two of its undelivered lines), so the hand-test
orders look like real ones; the real SO itself is only READ, never written. Each gets two
lines (Seq 10, the one the second push changes, and Seq 20, which stays), is set to project
demand (as CS's classification does), adopted into Fulfilment Planning
(`ProjectSOAdoptionService.adopt`) and given one order inquiry with an ORDER row on line Seq 10,
`raised` and acknowledged: what a confirmed plan leaves for purchasing. Both pushes go through
the SO ingest the way `/external/ingest/sales_orders` runs it (`DocumentIngestService.ingest`,
the commit, then the route's `_run_document_hooks`), in this process, on the one database the
guard checked: nothing goes over HTTP and no API key is needed.

NO EMAIL IS SENT. A removal (REMOVED, CHANGED) queues today's purchasing handover email; this
script never lets it leave: the send job is not queued and the delivery is marked cancelled
("Hand-test setup: held back, never sent"), so Outgoing Mails shows that today's code WOULD have
emailed, and nobody receives it (`_hold_back_mail`, `_cancel_held_mail`).

`--apply` is idempotent: an order already built is not built again, a second push already made
is not made again; it prints the state either way. `--cleanup` deletes the three hand-test
orders and everything this script or the pushes hung off them (planning record, order inquiry
and its rows, planning changes, references). Audit rows and the held-back Outgoing Mails rows
stay, as the record of what happened.

Refuses on anything but a dev database on this machine, with exactly the checks of
`handtest_1679_setup.py` (imported, not copied): a local host, no redirecting query string or PG*
variable, a dev / ci / test / copy database name (or `--allow-db <name>`), and the address
Postgres itself reports being loopback or a unix socket.

The held-back count needs the "Order inquiry to purchasing" automation enabled and a user with a
purchasing role; on the shared dev DB the automation is off, so every push reports 0 and nothing
is queued at all. The owner's hand test: `documentation/plans/scm/ac-rekey-same-line-handtest.md`.

Run from sorento_crm_backend/ with the copy's env (its DATABASE_URL):
    venv/bin/python scripts/handtest_ac_rekey_setup.py --apply
    venv/bin/python scripts/handtest_ac_rekey_setup.py --cleanup
Optional: --so <SO number> to clone that real SO.
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date
from decimal import Decimal
from typing import Any, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

from sqlalchemy import text  # noqa: E402

from handtest_1679_setup import Refused, guard, guard_connected  # noqa: E402

BOOK = "HANDTEST-REKEY"
SEQ_SUBJECT = 10
SEQ_KEEPER = 20
#: (scenario, SO number, DocKey). DtlKeys: DocKey*10 + 1 (Seq 10), + 2 (Seq 20), + 3 (the new
#: key Seq 10 comes back with).
ORDERS = (
    ("same", "HT-REKEY-SAME", 260611001),
    ("removed", "HT-REKEY-REMOVED", 260611002),
    ("changed", "HT-REKEY-CHANGED", 260611003),
)

PICK_SQL = """
WITH eligible AS (
    SELECT DISTINCT ON (so.id, p.product_code)
           so.id AS so_id, so.so_number, so.company_id, so.order_date, c.customer_code,
           p.product_code, w.warehouse_code, core.qty_ordered, core.unit_price,
           core.required_date, core.uom, core.line_no, core.id AS line_id
    FROM public.sales_orders so
    JOIN public.customers c ON c.id = so.customer_id
    JOIN public.sales_order_lines core ON core.sales_order_id = so.id
    JOIN public.products p ON p.id = core.product_id
    JOIN public.warehouses w ON w.id = core.warehouse_id
    WHERE so.status = 'open'
      AND so.demand_class = 'project'
      AND so.doc_type = 'sales_order'
      AND (CAST(:so AS text) IS NULL OR so.so_number = CAST(:so AS text))
      AND so.so_number NOT LIKE 'HT-REKEY-%'
      AND c.customer_code IS NOT NULL
      AND core.line_status = 'open'
      AND core.cancelled_at IS NULL
      AND core.qty_ordered > 1
      AND COALESCE(core.qty_delivered, 0) = 0
      AND p.product_code IS NOT NULL
      AND w.warehouse_code IS NOT NULL
      AND w.is_active
    ORDER BY so.id, p.product_code, core.line_no NULLS LAST, core.id
), two AS (
    SELECT *, row_number() OVER (PARTITION BY so_id ORDER BY line_no NULLS LAST, line_id) AS n
    FROM eligible
)
SELECT so_number, company_id, customer_code,
       array_agg(product_code ORDER BY n) AS item_codes,
       array_agg(warehouse_code ORDER BY n) AS locations,
       array_agg(qty_ordered ORDER BY n) AS qtys,
       array_agg(unit_price ORDER BY n) AS prices,
       array_agg(required_date ORDER BY n) AS dates,
       array_agg(uom ORDER BY n) AS uoms
FROM two
WHERE n <= 2
GROUP BY so_id, so_number, company_id, customer_code, order_date
HAVING count(*) = 2
ORDER BY order_date DESC NULLS LAST, so_number
LIMIT 1
"""


def _ref(doc_key: int, dtl_key: Optional[int] = None) -> str:
    return f"{BOOK}:{doc_key}" if dtl_key is None else f"{BOOK}:{doc_key}:{dtl_key}"


def _line(pick: dict, i: int, *, seq: int, dtl_key: int, doc_key: int,
          qty: Optional[Decimal] = None) -> dict:
    required = pick["dates"][i]
    line = {
        "source_ref": _ref(doc_key, dtl_key),
        "line_number": seq,
        "product_code": pick["item_codes"][i],
        "warehouse_code": pick["locations"][i],
        "qty_ordered": str(qty if qty is not None else pick["qtys"][i]),
        "qty_delivered": "0",
        "unit_price": None if pick["prices"][i] is None else str(pick["prices"][i]),
        "required_date": required.isoformat() if isinstance(required, date) else None,
    }
    if pick["uoms"][i]:
        line["uom"] = pick["uoms"][i]
    return line


def _record(pick: dict, so_number: str, doc_key: int, lines: list[dict]) -> dict:
    return {
        "source_ref": _ref(doc_key),
        "so_number": so_number,
        "status": "open",
        "customer_code": pick["customer_code"],
        "doc_date": date.today().isoformat(),
        "lines": lines,
    }


def _first_push(pick: dict, so_number: str, doc_key: int) -> dict:
    return _record(pick, so_number, doc_key, [
        _line(pick, 0, seq=SEQ_SUBJECT, dtl_key=doc_key * 10 + 1, doc_key=doc_key),
        _line(pick, 1, seq=SEQ_KEEPER, dtl_key=doc_key * 10 + 2, doc_key=doc_key),
    ])


def _second_push(pick: dict, scenario: str, so_number: str, doc_key: int) -> dict:
    keeper = _line(pick, 1, seq=SEQ_KEEPER, dtl_key=doc_key * 10 + 2, doc_key=doc_key)
    if scenario == "removed":
        return _record(pick, so_number, doc_key, [keeper])
    qty = None
    if scenario == "changed":
        qty = Decimal(pick["qtys"][0]) - 1
    subject = _line(pick, 0, seq=SEQ_SUBJECT, dtl_key=doc_key * 10 + 3, doc_key=doc_key, qty=qty)
    return _record(pick, so_number, doc_key, [subject, keeper])


def _actor(db) -> Optional[str]:
    """The FoundryX ESB integration's principal, who the real sync acts as."""
    return db.execute(text(
        "SELECT id FROM users WHERE email = 'foundryx-esb@integrations.local'"
    )).scalar()


def _push(db, company_id: str, record: dict) -> None:
    """The route's own sequence: ingest, commit, then the post-write document hooks."""
    from app.api.v1.external.ingest import _run_document_hooks
    from app.services.document_ingest_service import DocumentIngestService

    service = DocumentIngestService(db, None, company_id=company_id)
    result = service.ingest("sales_orders", [record])
    outcome = result.records[0]
    if str(getattr(outcome.outcome, "value", outcome.outcome)) in ("failed", "retryable"):
        db.rollback()
        raise SystemExit(f"{record['so_number']}: ingest {outcome.outcome}: {outcome.errors}")
    db.commit()
    _run_document_hooks(db, "sales_orders", service, actor=_actor(db))
    print(f"  pushed {record['so_number']}: lines {outcome.lines}")


HELD_BACK = "Hand-test setup: held back, never sent"


def _hold_back_mail() -> None:
    """No hand-test email ever reaches anybody. The purchasing handover a removal queues today
    is written as a Notification + a pending email delivery, then a `notifications` RQ job
    sends it (`automation_service._enqueue_email`). That job is never queued from this process
    (the only reader of a pending delivery is that job, `notification_tasks.py`), and
    `_cancel_held_mail` marks the delivery cancelled, so Outgoing Mails shows it and nothing
    sends it. Every other job passes through."""
    from app.services import queue_service
    from app.tasks import notification_tasks

    real = queue_service.enqueue_job

    def enqueue_job(func, *args, **kwargs):
        if func is notification_tasks.send_notification_deliveries:
            return None
        return real(func, *args, **kwargs)

    queue_service.enqueue_job = enqueue_job


def _cancel_held_mail(db, header_id: str) -> int:
    """The handover deliveries the pushes queued for this order: cancelled, never sent."""
    count = db.execute(text(
        "UPDATE public.notification_deliveries d SET status = 'cancelled', error_message = :why "
        "FROM public.notifications n WHERE n.id = d.notification_id AND d.status = 'pending' "
        "AND n.data ->> 'source_kind' = 'order_inquiry_handover' "
        "AND n.data ->> 'source_id' IN (SELECT i.id::text FROM projects.order_inquiries i "
        "  JOIN projects.sales_orders p ON p.id = i.project_sales_order_id WHERE p.so_id = :h)"
    ), {"why": HELD_BACK, "h": header_id}).rowcount
    db.commit()
    return count


def _header(db, doc_key: int) -> Optional[dict]:
    row = db.execute(text(
        "SELECT so.id, so.so_number, so.company_id FROM public.sales_orders so "
        "JOIN public.integration_references r ON r.entity_id = so.id::text "
        "WHERE r.entity_type = 'sales_orders' AND r.source_ref = :ref"
    ), {"ref": _ref(doc_key)}).mappings().first()
    return dict(row) if row else None


def _second_push_made(db, scenario: str, header_id: str, doc_key: int) -> bool:
    refs = {ref for (ref,) in db.execute(text(
        "SELECT source_ref FROM public.sales_order_lines WHERE sales_order_id = :h"
    ), {"h": header_id})}
    if scenario == "removed":
        old = db.execute(text(
            "SELECT line_status FROM public.sales_order_lines WHERE source_ref = :r"
        ), {"r": _ref(doc_key, doc_key * 10 + 1)}).scalar()
        return old == "cancelled"
    return _ref(doc_key, doc_key * 10 + 3) in refs


def _seed_order_inquiry(db, header_id: str) -> None:
    """Adopt into Fulfilment Planning, then one inquiry with an ORDER row on line Seq 10."""
    from app.models.project_so import (
        ACK_ACKNOWLEDGED,
        INQUIRY_RAISED,
        IV_ORDER,
        OrderInquiryRow,
        ProjectSalesOrder,
        ProjectSalesOrderLine,
    )
    from app.services.project_order_inquiry_service import ProjectOrderInquiryService
    from app.services.project_so_adoption_service import ProjectSOAdoptionService

    db.execute(text("UPDATE public.sales_orders SET demand_class = 'project' WHERE id = :h"),
               {"h": header_id})
    ProjectSOAdoptionService(db).adopt(header_id, actor_user_id=_actor(db))
    order = db.query(ProjectSalesOrder).filter(ProjectSalesOrder.so_id == header_id).one()
    core = db.execute(text(
        "SELECT l.id, l.qty_ordered, l.required_date, p.product_code, w.warehouse_code "
        "FROM public.sales_order_lines l JOIN public.products p ON p.id = l.product_id "
        "LEFT JOIN public.warehouses w ON w.id = l.warehouse_id "
        "WHERE l.sales_order_id = :h AND l.line_no = :seq"
    ), {"h": header_id, "seq": SEQ_SUBJECT}).mappings().one()
    mirror = (
        db.query(ProjectSalesOrderLine)
        .filter(ProjectSalesOrderLine.core_sales_order_line_id == str(core["id"]))
        .one()
    )
    inquiry = ProjectOrderInquiryService(db).ensure_inquiry(order, actor_user_id=_actor(db))
    db.add(OrderInquiryRow(
        company_id=order.company_id,
        order_inquiry_id=inquiry.id,
        so_line_id=mirror.id,
        item_code=core["product_code"],
        qty=core["qty_ordered"],
        delivery_date=core["required_date"],
        stock_location=core["warehouse_code"],
        verb=IV_ORDER,
        state=INQUIRY_RAISED,
        ack_state=ACK_ACKNOWLEDGED,
    ))
    db.commit()


STATE_SQL = """
SELECT l.line_no AS seq, split_part(l.source_ref, ':', 3) AS dtl_key, l.line_status,
       l.qty_ordered, p.product_code, l.id AS core_id,
       (SELECT count(*) FROM projects.sales_order_lines m
         WHERE m.core_sales_order_line_id = l.id) AS mirror_lines,
       (SELECT string_agg(i.inquiry_no || ' ' || r.state
                          || COALESCE(' (' || r.note || ')', ''), '; ')
          FROM projects.sales_order_lines m
          JOIN projects.order_inquiry_rows r ON r.so_line_id = m.id
          JOIN projects.order_inquiries i ON i.id = r.order_inquiry_id
         WHERE m.core_sales_order_line_id = l.id) AS oi_rows
FROM public.sales_order_lines l JOIN public.products p ON p.id = l.product_id
WHERE l.sales_order_id = :h
ORDER BY l.line_no, l.created_at
"""


def _print_state(db, header: dict) -> None:
    db.expire_all()
    print(f"  {header['so_number']}:")
    for row in db.execute(text(STATE_SQL), {"h": header["id"]}).mappings():
        print(f"    Seq {row['seq']} DtlKey {row['dtl_key']} {row['product_code']} "
              f"qty {row['qty_ordered']} {row['line_status']}, mirror lines "
              f"{row['mirror_lines']}, OI rows: {row['oi_rows'] or 'none'}")


def apply(db, so_number: Optional[str]) -> None:
    from app.models.base import company_scope

    pick = None
    for scenario, number, doc_key in ORDERS:
        header = _header(db, doc_key)
        if header is None:
            if pick is None:
                pick = db.execute(text(PICK_SQL), {"so": so_number}).mappings().first()
                if pick is None:
                    raise SystemExit("no open project SO with two undelivered lines of two items "
                                     "(with codes and an active location) to clone")
                pick = dict(pick)
                print(f"cloning real SO {pick['so_number']} (read only)")
            with company_scope(db, frozenset({str(pick["company_id"])})):
                _push(db, str(pick["company_id"]), _first_push(pick, number, doc_key))
                header = _header(db, doc_key)
                _seed_order_inquiry(db, str(header["id"]))
            print(f"  built {number}; before the second push:")
            _print_state(db, header)
        if _second_push_made(db, scenario, str(header["id"]), doc_key):
            print(f"  {number}: second push already made")
        else:
            if pick is None:
                pick = _pick_back(db, header)
            with company_scope(db, frozenset({str(header["company_id"])})):
                _push(db, str(header["company_id"]),
                      _second_push(pick, scenario, number, doc_key))
            held = _cancel_held_mail(db, str(header["id"]))
            print(f"  {number}: purchasing email(s) queued by this push and held back: {held}")
        _print_state(db, header)
    print("\nApply done. Cleanup: --cleanup")


def _pick_back(db, header: dict) -> dict:
    """The hand-test order's own first-push values, read back (a re-run after the clone source
    changed must replay exactly what the first push sent)."""
    rows = db.execute(text(
        "SELECT p.product_code, w.warehouse_code, l.qty_ordered, l.unit_price, l.required_date, "
        "l.uom FROM public.sales_order_lines l JOIN public.products p ON p.id = l.product_id "
        "LEFT JOIN public.warehouses w ON w.id = l.warehouse_id "
        "WHERE l.sales_order_id = :h AND l.source_ref LIKE :pat ORDER BY l.line_no"
    ), {"h": header["id"], "pat": f"{BOOK}:%"}).mappings().all()
    first = {}
    for row in rows:
        first.setdefault(row["product_code"], row)
    rows = list(first.values())[:2]
    customer = db.execute(text(
        "SELECT c.customer_code FROM public.sales_orders so "
        "JOIN public.customers c ON c.id = so.customer_id WHERE so.id = :h"
    ), {"h": header["id"]}).scalar()
    return {
        "customer_code": customer,
        "item_codes": [r["product_code"] for r in rows],
        "locations": [r["warehouse_code"] for r in rows],
        "qtys": [r["qty_ordered"] for r in rows],
        "prices": [r["unit_price"] for r in rows],
        "dates": [r["required_date"] for r in rows],
        "uoms": [r["uom"] for r in rows],
    }


CLEANUP_SQL = (
    # Order inquiry rows and their children go with the inquiry, planning changes with the
    # planning record (ON DELETE CASCADE).
    "DELETE FROM projects.order_inquiries WHERE project_sales_order_id IN "
    "(SELECT id FROM projects.sales_orders WHERE so_id = ANY(CAST(:ids AS uuid[])))",
    "DELETE FROM projects.sales_order_lines WHERE core_sales_order_line_id IN "
    "(SELECT id FROM public.sales_order_lines WHERE sales_order_id = ANY(CAST(:ids AS uuid[])))",
    "DELETE FROM projects.sales_orders WHERE so_id = ANY(CAST(:ids AS uuid[]))",
    "DELETE FROM public.sales_order_lines WHERE sales_order_id = ANY(CAST(:ids AS uuid[]))",
    "DELETE FROM public.integration_references WHERE source_ref LIKE :pat",
    "DELETE FROM public.sales_orders WHERE id = ANY(CAST(:ids AS uuid[]))",
)


def cleanup(db) -> None:
    headers = [h for h in (_header(db, doc_key) for _, _, doc_key in ORDERS) if h]
    ids = [str(h["id"]) for h in headers]
    if not ids:
        print("no hand-test order on this database: nothing to clean up")
        return
    for statement in CLEANUP_SQL:
        db.execute(text(statement), {"ids": ids, "pat": f"{BOOK}:%"})
    db.commit()
    print(f"Cleanup done: removed {', '.join(h['so_number'] for h in headers)} and what hung "
          "off them (audit and held-back Outgoing Mails rows stay).")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--apply", action="store_true", help="build and push the three orders")
    action.add_argument("--cleanup", action="store_true", help="delete the three orders")
    parser.add_argument("--so", help="clone this real SO number")
    parser.add_argument("--allow-db", metavar="NAME",
                        help="accept this exact database name as a dev database")
    args = parser.parse_args()

    from app.config import settings

    try:
        guard(settings.database_url, args.allow_db)
    except Refused as refusal:
        print(f"Refused: {refusal}.", file=sys.stderr)
        return 2

    from app.database import SessionLocal
    from app.services.audit_service import register_audit_listeners
    from app.services.company_scope import register_company_scope_listeners
    from app.services.project_order_inquiry_service import (
        register_order_inquiry_post_commit_dispatch,
    )

    db = SessionLocal()
    try:
        name, addr = db.execute(
            text("SELECT current_database(), host(inet_server_addr())")).one()
        try:
            guard_connected(name, addr, args.allow_db)
        except Refused as refusal:
            print(f"Refused: {refusal}.", file=sys.stderr)
            return 2
        db.rollback()
        # What the API registers at startup (as `handtest_1679_setup.py` does).
        register_audit_listeners()
        register_company_scope_listeners()
        register_order_inquiry_post_commit_dispatch()
        _hold_back_mail()
        print(f"database {name} ({addr or 'unix socket'})")
        if args.apply:
            apply(db, args.so)
        else:
            cleanup(db)
    finally:
        db.rollback()
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
