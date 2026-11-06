#!/usr/bin/env python3
"""Crew hand-test setup for PR #2220 (FP-EMAIL-ONE-TRIGGER). DEV COPIES ONLY.

Builds two hand-test sales orders cloned from a real undecided project SO, so the owner can see
that only the board Confirm emails purchasing:

  HT-EMAIL-REMOVE   adopted, one live ORDER row (raised, acknowledged) on line Seq 10. The script
                    then replays an AutoCount push that REALLY removes Seq 10. Expected and
                    checked here: no automation run, no Outgoing Mails row, the order inquiry row
                    still live, and the removal waiting on the board as a pending change. The
                    owner then presses Confirm on the board: one run, one Outgoing Mails row
                    (CANCEL).
  HT-EMAIL-UNDO     adopted, undecided, no order inquiry row. The owner decides a line, presses
                    Confirm (one handover run), then "Undo ... confirm" (one undone run): the
                    Undo email is kept (owner, Q5).

The real SO is only READ (`PICK_SQL`), never written. Pushes run the SO ingest the way
`/external/ingest/sales_orders` does (`DocumentIngestService.ingest`, the commit, then the
route's `_run_document_hooks`), in this process: no HTTP, no API key.

AUTOMATIONS. The handover rows route by class AND raiser (`order_inquiry.raisedBy` "is any of"
[users]), so both hand-test inquiries are raised by a user the rows name: `--raiser-email` if
listed, else the E2E staff user (`E2E_EMAIL`, env or the frontend's `.env.local`) if listed, else
the first ACTIVE listed user. With that raiser, `--apply` switches ON exactly one
`order_inquiry_handover` automation (the oldest whose conditions pass for a project order) and
one `order_inquiry_undone` automation, pointing their recipients at `HANDTEST_ADDRESS` only
(`.invalid`, so it can never be delivered), and switches OFF any other enabled row of the two
triggers that would also fire for the hand-test orders (it would mail real people). Every row it
touches is saved to `STATE_DIR` first; `--cleanup` restores each exactly.

NO EMAIL IS SENT. The only recipient is an `.invalid` address and the copies' SMTP host is
`smtp.invalid`. Mails this process queues are never handed to the send job (`_hold_back_mail`),
and `--hold` / `--cleanup` mark every pending delivery to `HANDTEST_ADDRESS` cancelled
("Hand-test setup: held back, never sent"); Outgoing Mails keeps the row as the evidence.

`--apply` is idempotent: an order already built is not built again, the removal push already made
is not made again, an automation already switched on keeps its saved original. `--cleanup`
deletes both hand-test orders and what hung off them, restores the automations and cancels the
held mails; audit and Outgoing Mails rows stay as the record.

Refuses on anything but a dev database on this machine, with exactly the checks of
`handtest_1679_setup.py` (imported, not copied).

Run from sorento_crm_backend/ with the copy's env (its DATABASE_URL):
    venv/bin/python scripts/handtest_fp_email_setup.py --apply
    venv/bin/python scripts/handtest_fp_email_setup.py --hold
    venv/bin/python scripts/handtest_fp_email_setup.py --cleanup
Optional: --so <SO number> to clone that real SO.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path
from typing import Any, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

from sqlalchemy import text  # noqa: E402

from handtest_1679_setup import Refused, guard, guard_connected  # noqa: E402

BOOK = "HANDTEST-FPEMAIL"
SEQ_SUBJECT = 10
SEQ_KEEPER = 20
#: (scenario, SO number, DocKey). DtlKeys: DocKey*10 + 1 (Seq 10), + 2 (Seq 20).
ORDERS = (
    ("remove", "HT-EMAIL-REMOVE", 260611101),
    ("undo", "HT-EMAIL-UNDO", 260611102),
)
HANDTEST_ADDRESS = "handtest-fp-email@example.invalid"
HELD_BACK = "Hand-test setup: held back, never sent"
TRIGGERS = ("order_inquiry_handover", "order_inquiry_undone")
STATE_DIR = Path(os.environ.get("HANDTEST_STATE_DIR", Path.home() / ".sorento-handtest"))

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
      AND so.so_number NOT LIKE 'HT-%'
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


# --------------------------------------------------------------------------- the pushes
def _ref(doc_key: int, dtl_key: Optional[int] = None) -> str:
    return f"{BOOK}:{doc_key}" if dtl_key is None else f"{BOOK}:{doc_key}:{dtl_key}"


def _line(pick: dict, i: int, *, seq: int, doc_key: int) -> dict:
    required = pick["dates"][i]
    line = {
        "source_ref": _ref(doc_key, doc_key * 10 + (1 if seq == SEQ_SUBJECT else 2)),
        "line_number": seq,
        "product_code": pick["item_codes"][i],
        "warehouse_code": pick["locations"][i],
        "qty_ordered": str(pick["qtys"][i]),
        "qty_delivered": "0",
        "unit_price": None if pick["prices"][i] is None else str(pick["prices"][i]),
        "required_date": required.isoformat() if isinstance(required, date) else None,
    }
    if pick.get("uoms") and pick["uoms"][i]:
        line["uom"] = pick["uoms"][i]
    return line


def _record(pick: dict, so_number: str, doc_key: int, *, with_subject: bool) -> dict:
    lines = [_line(pick, 1, seq=SEQ_KEEPER, doc_key=doc_key)]
    if with_subject:
        lines.insert(0, _line(pick, 0, seq=SEQ_SUBJECT, doc_key=doc_key))
    record = {
        "source_ref": _ref(doc_key),
        "so_number": so_number,
        "status": "open",
        "doc_date": date.today().isoformat(),
        "lines": lines,
    }
    if pick.get("customer_code"):
        record["customer_code"] = pick["customer_code"]
    return record


def _actor(db) -> Optional[str]:
    """The FoundryX ESB integration's principal, who the real sync acts as."""
    from app.models.user import User

    row = db.query(User.id).filter(User.email == "foundryx-esb@integrations.local").first()
    return str(row[0]) if row else None


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


def _header(db, doc_key: int):
    from app.models.order import SalesOrder
    from app.models.integration_reference import IntegrationReference

    entity_id = (
        db.query(IntegrationReference.entity_id)
        .filter(
            IntegrationReference.entity_type == "sales_orders",
            IntegrationReference.source_ref == _ref(doc_key),
        )
        .scalar()
    )
    return db.get(SalesOrder, str(entity_id)) if entity_id else None


def _core_line(db, header_id: str, seq: int):
    from app.models.order import SalesOrderLine

    return (
        db.query(SalesOrderLine)
        .filter(SalesOrderLine.sales_order_id == header_id, SalesOrderLine.line_no == seq)
        .order_by(SalesOrderLine.created_at)
        .first()
    )


def _adopt(db, header_id: str, *, raiser: Optional[str], with_row: bool) -> None:
    """Adopt into Fulfilment Planning (as CS's classification does) and open the order's one
    order inquiry, raised by `raiser` (the purchasing automations route by
    `order_inquiry.raisedBy`; the owner's later Confirm reuses this inquiry, so its email
    routes the same way). For the removal case, one raised, acknowledged ORDER row on line
    Seq 10."""
    from app.models.order import SalesOrder
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

    db.get(SalesOrder, header_id).demand_class = "project"
    db.flush()
    ProjectSOAdoptionService(db).adopt(header_id, actor_user_id=_actor(db))
    order = db.query(ProjectSalesOrder).filter(ProjectSalesOrder.so_id == header_id).one()
    inquiry = ProjectOrderInquiryService(db).ensure_inquiry(order, actor_user_id=raiser)
    if with_row:
        core = _core_line(db, header_id, SEQ_SUBJECT)
        mirror = (
            db.query(ProjectSalesOrderLine)
            .filter(ProjectSalesOrderLine.core_sales_order_line_id == str(core.id))
            .one()
        )
        db.add(OrderInquiryRow(
            company_id=order.company_id,
            order_inquiry_id=inquiry.id,
            so_line_id=mirror.id,
            item_code=_product_code(db, core.product_id),
            qty=core.qty_ordered,
            delivery_date=core.required_date,
            verb=IV_ORDER,
            state=INQUIRY_RAISED,
            ack_state=ACK_ACKNOWLEDGED,
        ))
    db.commit()


def _product_code(db, product_id) -> Optional[str]:
    from app.models.product import Product

    return db.query(Product.product_code).filter(Product.id == str(product_id)).scalar()


# --------------------------------------------------------------------------- the evidence
def _counts(db) -> dict:
    """Automation runs of the purchasing triggers, and Outgoing Mails rows to the hand-test
    address: what the owner reads on the pages."""
    from app.models.automation import Automation, AutomationRun
    from app.models.notification import Notification, NotificationDelivery

    runs = (
        db.query(AutomationRun)
        .join(Automation, Automation.id == AutomationRun.automation_id)
        .filter(Automation.trigger_type.in_(TRIGGERS))
        .count()
    )
    mails = (
        db.query(NotificationDelivery)
        .join(Notification, Notification.id == NotificationDelivery.notification_id)
        .filter(
            NotificationDelivery.channel == "email",
            Notification.data["recipient_emails"].astext.contains(HANDTEST_ADDRESS),
        )
        .count()
    )
    return {"automation_runs": runs, "outgoing_mails": mails}


def _removal_state(db, header) -> dict:
    from app.models.planning_change import PlanningChangeRow
    from app.models.project_so import OrderInquiryRow, ProjectSalesOrderLine

    core = _core_line(db, str(header.id), SEQ_SUBJECT)
    rows = (
        db.query(OrderInquiryRow.state)
        .join(ProjectSalesOrderLine, ProjectSalesOrderLine.id == OrderInquiryRow.so_line_id)
        .filter(ProjectSalesOrderLine.core_sales_order_line_id == str(core.id))
        .all()
    )
    pending = (
        db.query(PlanningChangeRow)
        .filter(
            PlanningChangeRow.core_line_id == str(core.id),
            PlanningChangeRow.kind == "cancelled",
        )
        .count()
    )
    return {
        "line_status": core.line_status,
        "oi_row_states": sorted(state for (state,) in rows),
        "pending_cancelled_changes": pending,
    }


# --------------------------------------------------------------------------- automations
def _state_file(db) -> Path:
    name = db.execute(text("SELECT current_database()")).scalar()
    return STATE_DIR / f"fp-email-{name}.json"


RAISED_BY_FACT = "order_inquiry.raisedBy"


def _listed_raisers(tree: Any) -> list[str]:
    """The user ids an automation's rule tree lets through on `order_inquiry.raisedBy` ("is
    any of"), in order."""
    found: list[str] = []

    def walk(node: Any) -> None:
        if not isinstance(node, dict):
            return
        for rule in node.get("rules") or []:
            if rule.get("kind") == "group":
                walk(rule)
            elif (
                rule.get("fact") == RAISED_BY_FACT
                and rule.get("operator") == "in"
                and rule.get("valueKind") != "fact"
            ):
                value = rule.get("value")
                for item in value if isinstance(value, list) else [value]:
                    if item and str(item) not in found:
                        found.append(str(item))

    walk(tree)
    return found


def _e2e_email() -> Optional[str]:
    """The E2E staff login (`E2E_EMAIL`), from the environment or the frontend's
    `.env.local`, as browser verification reads it."""
    if os.environ.get("E2E_EMAIL"):
        return os.environ["E2E_EMAIL"].strip()
    env_local = Path(HERE).parents[1] / "sorento_crm_frontend" / ".env.local"
    if env_local.exists():
        for line in env_local.read_text().splitlines():
            if line.startswith("E2E_EMAIL="):
                return line.split("=", 1)[1].strip().strip("'\"") or None
    return None


def _choose_raiser(db, rows: list, raiser_email: Optional[str]) -> Optional[str]:
    """Who the hand-test inquiries are raised by: a user an enabled-for-test handover
    automation's condition names (`order_inquiry.raisedBy`), preferring `--raiser-email`, then
    the E2E staff user, then the first ACTIVE listed user. None when no automation routes by
    raiser (every row then passes on class alone)."""
    from app.models.user import User

    listed: list[str] = []
    for row in rows:
        for user_id in _listed_raisers(row.conditions_json):
            if user_id not in listed:
                listed.append(user_id)
    if not listed:
        return None
    active = {
        str(user_id): (email or "").lower()
        for user_id, email in db.query(User.id, User.email).filter(
            User.id.in_(listed), User.status == "ACTIVE", User.is_trashed.is_(False)
        )
    }
    for wanted in (raiser_email, _e2e_email()):
        if wanted:
            for user_id in listed:
                if active.get(user_id) == wanted.lower():
                    return user_id
    for user_id in listed:
        if user_id in active:
            return user_id
    raise SystemExit(
        "the handover automations route by order_inquiry.raisedBy, but none of the users "
        "they name is an active user"
    )


def _switch_on(db, raiser: Optional[str]) -> list[str]:
    """One handover and one undone automation, on, mailing only the hand-test address. The
    originals are saved before the first change and never overwritten by a re-run."""
    from app.models.automation import Automation
    from app.services.automation_service import AutomationService

    path = _state_file(db)
    saved = json.loads(path.read_text()) if path.exists() else {}
    chosen = []
    service = AutomationService(db)
    context = {"sales_order_class": "project", "raised_by": raiser}
    for trigger in TRIGGERS:
        rows = (
            db.query(Automation)
            .filter(Automation.trigger_type == trigger)
            .order_by(Automation.created_at.asc())
            .all()
        )
        passing = service.passing_rows(trigger, context, rows) if rows else []
        if not passing:
            raise SystemExit(
                f"no {trigger} automation whose conditions pass for a project order raised by "
                f"{raiser or 'nobody in particular'}"
            )
        row = next(
            (r for r in passing if saved.get(str(r.id), {}).get("role") == "chosen"),
            passing[0],
        )
        if str(row.id) not in saved:
            saved[str(row.id)] = {
                "role": "chosen",
                "enabled": row.enabled,
                "recipient_config": row.recipient_config,
            }
        row.enabled = True
        row.recipient_config = {
            "user_ids": [],
            "role_ids": [],
            "extra_emails": [HANDTEST_ADDRESS],
            "include_actor": False,
            "one_email": True,
        }
        chosen.append(f"{row.name} ({trigger})")
        # Any OTHER row that would also fire for the hand-test orders mails real people:
        # off for the test (saved and restored like the chosen one).
        for other in passing:
            if other is row or not other.enabled:
                continue
            saved.setdefault(str(other.id), {
                "role": "off",
                "enabled": other.enabled,
                "recipient_config": other.recipient_config,
            })
            other.enabled = False
            chosen.append(f"switched off for the test: {other.name}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(saved, indent=2))
    db.commit()
    return chosen


def _restore(db) -> int:
    from app.models.automation import Automation

    path = _state_file(db)
    if not path.exists():
        return 0
    saved = json.loads(path.read_text())
    for automation_id, original in saved.items():
        row = db.get(Automation, automation_id)
        if row is not None:
            row.enabled = original["enabled"]
            row.recipient_config = original["recipient_config"]
    db.commit()
    path.unlink()
    return len(saved)


def _hold_back_mail() -> None:
    """Mails this process queues are never handed to the send job (the only reader of a
    pending delivery, `notification_tasks.send_notification_deliveries`); every other job
    passes through. `_cancel_held_mail` then marks them cancelled."""
    from app.services import queue_service
    from app.tasks import notification_tasks

    real = queue_service.enqueue_job

    def enqueue_job(func, *args, **kwargs):
        if func is notification_tasks.send_notification_deliveries:
            return None
        return real(func, *args, **kwargs)

    queue_service.enqueue_job = enqueue_job


def _cancel_held_mail(db) -> int:
    """Every pending delivery to the hand-test address: cancelled, never sent."""
    from app.models.notification import Notification, NotificationDelivery

    ids = [
        notification_id
        for (notification_id,) in db.query(Notification.id).filter(
            Notification.data["recipient_emails"].astext.contains(HANDTEST_ADDRESS)
        )
    ]
    if not ids:
        return 0
    count = (
        db.query(NotificationDelivery)
        .filter(
            NotificationDelivery.notification_id.in_([str(i) for i in ids]),
            NotificationDelivery.status == "pending",
        )
        .update(
            {NotificationDelivery.status: "cancelled", NotificationDelivery.error_message: HELD_BACK},
            synchronize_session=False,
        )
    )
    db.commit()
    return count


# --------------------------------------------------------------------------- apply / cleanup
def _pick(db, so_number: Optional[str]) -> dict:
    pick = db.execute(text(PICK_SQL), {"so": so_number}).mappings().first()
    if pick is None:
        raise SystemExit("no open project SO with two undelivered lines of two items "
                         "(with codes and an active location) to clone")
    pick = dict(pick)
    print(f"cloning real SO {pick['so_number']} (read only)")
    return pick


def apply(
    db,
    so_number: Optional[str] = None,
    *,
    pick: Optional[dict] = None,
    raiser_email: Optional[str] = None,
) -> dict:
    """Returns what it checked, per order (the test reads it)."""
    from app.models.automation import Automation
    from app.models.base import company_scope
    from app.models.user import User

    handover_rows = (
        db.query(Automation).filter(Automation.trigger_type == TRIGGERS[0]).all()
    )
    raiser = _choose_raiser(db, handover_rows, raiser_email)
    raiser_shown = (
        db.query(User.email).filter(User.id == raiser).scalar() if raiser else "no one in particular"
    )
    print(f"hand-test inquiries raised by: {raiser_shown}")
    names = _switch_on(db, raiser)
    print(f"automations on for the test, mailing {HANDTEST_ADDRESS} only: {', '.join(names)}")
    report: dict[str, Any] = {"raiser": raiser}
    for scenario, number, doc_key in ORDERS:
        header = _header(db, doc_key)
        if header is None:
            pick = pick or _pick(db, so_number)
            with company_scope(db, frozenset({str(pick["company_id"])})):
                _push(db, str(pick["company_id"]),
                      _record(pick, number, doc_key, with_subject=True))
                header = _header(db, doc_key)
                _adopt(db, str(header.id), raiser=raiser, with_row=scenario == "remove")
            print(f"  built {number}")
        if scenario != "remove":
            report[scenario] = {"so_number": header.so_number}
            continue
        state = _removal_state(db, header)
        if state["line_status"] == "cancelled":
            print(f"  {number}: removal push already made")
            report[scenario] = {**state, **_counts(db), "pushed_now": False}
        else:
            pick = pick or _pick_back(db, header)
            before = _counts(db)
            with company_scope(db, frozenset({str(header.company_id)})):
                _push(db, str(header.company_id),
                      _record(pick, number, doc_key, with_subject=False))
            after = _counts(db)
            db.expire_all()
            state = _removal_state(db, header)
            report[scenario] = {
                **state,
                "new_automation_runs": after["automation_runs"] - before["automation_runs"],
                "new_outgoing_mails": after["outgoing_mails"] - before["outgoing_mails"],
                "pushed_now": True,
            }
            print(f"  {number} after the AutoCount removal of Seq {SEQ_SUBJECT}: "
                  f"core line {state['line_status']}, OI rows {state['oi_row_states']}, "
                  f"pending cancelled change rows {state['pending_cancelled_changes']}, "
                  f"new automation runs {report[scenario]['new_automation_runs']}, "
                  f"new Outgoing Mails rows {report[scenario]['new_outgoing_mails']}")
    held = _cancel_held_mail(db)
    print(f"held back (cancelled) pending hand-test mails: {held}")
    print("\nApply done. After the owner's steps: --hold. At the end: --cleanup")
    return report


def _pick_back(db, header) -> dict:
    """The hand-test order's own first-push values, read back, so a re-run replays exactly
    what the first push sent."""
    from app.models.order import Customer
    from app.models.inventory import Warehouse

    lines = [_core_line(db, str(header.id), seq) for seq in (SEQ_SUBJECT, SEQ_KEEPER)]
    customer = db.get(Customer, str(header.customer_id)) if header.customer_id else None
    return {
        "company_id": header.company_id,
        "customer_code": getattr(customer, "customer_code", None),
        "item_codes": [_product_code(db, line.product_id) for line in lines],
        "locations": [
            db.query(Warehouse.warehouse_code).filter(Warehouse.id == line.warehouse_id).scalar()
            for line in lines
        ],
        "qtys": [line.qty_ordered for line in lines],
        "prices": [line.unit_price for line in lines],
        "dates": [line.required_date for line in lines],
        "uoms": [line.uom for line in lines],
    }


def _delete_orders(db, headers) -> None:
    """Both hand-test orders and what hung off them, through the ORM (so the schema map the
    app uses applies): order inquiries (their rows and children cascade), planning records
    (their planning changes cascade), mirror lines, core lines, references, headers."""
    from app.models.integration_reference import IntegrationReference
    from app.models.order import SalesOrder, SalesOrderLine
    from app.models.project_so import OrderInquiry, ProjectSalesOrder, ProjectSalesOrderLine

    ids = [str(h.id) for h in headers]
    pso_ids = [
        str(pid) for (pid,) in db.query(ProjectSalesOrder.id).filter(ProjectSalesOrder.so_id.in_(ids))
    ]
    core_line_ids = [
        str(lid)
        for (lid,) in db.query(SalesOrderLine.id).filter(SalesOrderLine.sales_order_id.in_(ids))
    ]
    if pso_ids:
        db.query(OrderInquiry).filter(OrderInquiry.project_sales_order_id.in_(pso_ids)).delete(
            synchronize_session=False
        )
    if core_line_ids:
        db.query(ProjectSalesOrderLine).filter(
            ProjectSalesOrderLine.core_sales_order_line_id.in_(core_line_ids)
        ).delete(synchronize_session=False)
    if pso_ids:
        db.query(ProjectSalesOrder).filter(ProjectSalesOrder.id.in_(pso_ids)).delete(
            synchronize_session=False
        )
    db.query(SalesOrderLine).filter(SalesOrderLine.sales_order_id.in_(ids)).delete(
        synchronize_session=False
    )
    db.query(IntegrationReference).filter(IntegrationReference.source_ref.like(f"{BOOK}:%")).delete(
        synchronize_session=False
    )
    db.query(SalesOrder).filter(SalesOrder.id.in_(ids)).delete(synchronize_session=False)
    db.commit()


def cleanup(db) -> None:
    held = _cancel_held_mail(db)
    restored = _restore(db)
    headers = [h for h in (_header(db, doc_key) for _, _, doc_key in ORDERS) if h]
    if headers:
        numbers = [h.so_number for h in headers]
        _delete_orders(db, headers)
        print(f"removed {', '.join(numbers)} and what hung off them")
    print(f"Cleanup done: {restored} automation(s) restored, {held} pending mail(s) cancelled "
          "(audit and Outgoing Mails rows stay).")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--apply", action="store_true", help="build the orders, push the removal")
    action.add_argument("--hold", action="store_true", help="cancel pending hand-test mails")
    action.add_argument("--cleanup", action="store_true", help="delete the orders, restore")
    parser.add_argument("--so", help="clone this real SO number")
    parser.add_argument("--raiser-email",
                        help="raise the hand-test inquiries as this user, when a handover "
                             "automation's raisedBy condition names them")
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
            apply(db, args.so, raiser_email=args.raiser_email)
        elif args.hold:
            print(f"held back (cancelled) pending hand-test mails: {_cancel_held_mail(db)}")
        else:
            cleanup(db)
    finally:
        db.rollback()
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
