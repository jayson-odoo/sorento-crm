"""Send to purchasing: rebuild an order inquiry's open rows into the handover email and send
it again (`documentation/plans/scm/PLAN-oi-resend-purchasing-15oct.md`).

The automatic `order_inquiry_handover` email goes out once, post-commit, for the lines a
write changed, and only through an ENABLED automation (`AutomationService.dispatch_event`).
While that automation was switched off (14-15 Oct) nothing was sent and nothing was
recorded, and there was no way to send it again. This is that way, single or bulk:

* the content is the OI's open rows (`raised` / `partly_linked`), each built by the same
  `ProjectOrderInquiryService.handover_item` the automatic email queues, aggregated by the same
  `_build_handover_context` (same template, same per-line SO files), and marked "(Resent)";
* the recipients and template are the handover automation's own, enabled or not, through
  `park_send` (the reserve flow's preview-then-send pattern);
* each send is one `AutomationService.send_match` run, so it leaves an `automation_runs` row
  and a `notifications` + `notification_deliveries` row, which `last_sent` reads back.
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy.orm import Session

from app.models.automation import Automation
from app.models.notification import Notification
from app.models.project_so import (
    INQUIRY_PARTLY_LINKED,
    INQUIRY_RAISED,
    OrderInquiry,
    OrderInquiryRow,
)
from app.services import park_send
from app.services.error_handler import AppException

logger = logging.getLogger(__name__)

TRIGGER_TYPE = "order_inquiry_handover"
SOURCE_KIND = "order_inquiry_handover_resend"
#: Purchasing has not acted on these yet; a placed or actioned row was already handled.
OPEN_STATES = (INQUIRY_RAISED, INQUIRY_PARTLY_LINKED)
MAX_INQUIRIES = 50


def handover_automations(
    db: Session, sales_order_class: Optional[str] = None, raised_by: Optional[str] = None
) -> List[Automation]:
    """The handover rows an OI of this class, raised by this person, goes through
    (OI-ROUTE-BY-RAISER): every ENABLED row whose conditions pass, oldest first, the same
    rows the automatic email fires (`AutomationService.passing_rows`). When no row is enabled
    at all, the oldest switched-off row that passes (an explicit send a switched-off
    automation must not swallow). Never a row whose conditions fail: an empty list skips
    the OI rather than send it to the wrong people (DEALER-OI-ROUTE)."""
    from app.services.automation_service import AutomationService

    rows = (
        db.query(Automation)
        .filter(Automation.trigger_type == TRIGGER_TYPE)
        .order_by(Automation.created_at.asc())
        .all()
    )
    enabled = [row for row in rows if row.enabled]
    if sales_order_class is None:
        # No OI to read facts off (the preview's "is the automation on" answer).
        return enabled or rows[:1]
    passing = AutomationService(db).passing_rows(
        TRIGGER_TYPE,
        {"sales_order_class": sales_order_class, "raised_by": raised_by},
        enabled if enabled else rows,
    )
    return passing if enabled else passing[:1]


def handover_automation(
    db: Session, sales_order_class: Optional[str] = None, raised_by: Optional[str] = None
) -> Optional[Automation]:
    """The oldest of `handover_automations`, or `None`."""
    rows = handover_automations(db, sales_order_class, raised_by)
    return rows[0] if rows else None


class OrderInquiryHandoverResend:
    def __init__(self, db: Session):
        self.db = db

    def _inquiries(self, inquiry_ids: Sequence[str]) -> List[OrderInquiry]:
        found = {
            str(inquiry.id): inquiry
            for inquiry in self.db.query(OrderInquiry)
            .filter(OrderInquiry.id.in_(list(inquiry_ids)))
            .all()
        }
        if any(str(inquiry_id) not in found for inquiry_id in inquiry_ids):
            raise AppException(
                404, "This order inquiry no longer exists.", code="order_inquiry_not_found"
            )
        seen: set = set()
        ordered = []
        for inquiry_id in inquiry_ids:
            if str(inquiry_id) not in seen:
                seen.add(str(inquiry_id))
                ordered.append(found[str(inquiry_id)])
        return ordered

    def _open_rows(self, inquiry: OrderInquiry) -> List[OrderInquiryRow]:
        return (
            self.db.query(OrderInquiryRow)
            .filter(
                OrderInquiryRow.order_inquiry_id == inquiry.id,
                OrderInquiryRow.state.in_(OPEN_STATES),
            )
            .order_by(OrderInquiryRow.delivery_date.asc().nulls_last(), OrderInquiryRow.id.asc())
            .all()
        )

    def _context(
        self, rows: Sequence[OrderInquiryRow], actor_user_id: str
    ) -> Tuple[Dict[str, Any], int]:
        """`(context, line_count)` for these open rows of one OI, built by the same
        `build_handover_email` the automatic send uses. The OI Excel is only named here;
        `send` stores it for an OI that has someone to send to."""
        from app.services.project_order_inquiry_service import (
            ProjectOrderInquiryService,
            _qty_str,
            build_handover_email,
        )

        service = ProjectOrderInquiryService(self.db)
        # A partly linked row asks only for what no document carries yet: the linked part
        # is already on order, and re-asking for it invites a double order.
        linked = service._linked_qty_by_row([str(row.id) for row in rows])
        # `actor` stays the OI's raiser (`handover_item`'s own fallback), so "Raised by" in
        # the email is true and the raiser is on Cc as on the automatic email; the presser
        # is recorded as `sent_by`.
        items = [
            service.handover_item(
                row,
                kind="raised",
                qty=(
                    Decimal(str(row.qty)) - linked[str(row.id)]
                    if str(row.id) in linked
                    else None
                ),
            )
            for row in rows
        ]
        # OI-LINE-SPLIT (UAC D1): a split line reads one line per split, as on Confirm -
        # while its splits act or after the Confirm that applied them. A stale plan
        # (AutoCount moved on) is not purchasing's instruction: that line prints its row.
        from app.services.project_line_split_service import LineSplitService

        splits = LineSplitService(self.db)
        printable = splits.printable_origin_ids(item.get("so_line_id") for item in items)
        # Qty other lines' splits moved onto a line is told by those origins' split rows. The
        # line's own row then says only the rest: nothing when the row IS what moved in, an
        # "ORDER <rest>" when the line also grew. A row cut below what moved in is a change
        # of its own and prints as it is.
        planned_in = splits.planned_in_by_printable(item.get("so_line_id") for item in items)
        netted: List[Dict[str, Any]] = []
        for item in items:
            line_id = str(item.get("so_line_id") or "")
            moved_in = planned_in.get(line_id, Decimal("0")) if line_id not in printable else 0
            entry = item.get("line") or {}
            row_qty = Decimal(str(entry.get("qty") or "0"))
            if moved_in > 0 and row_qty == moved_in:
                continue
            if moved_in > 0 and row_qty > moved_in:
                rest = _qty_str(row_qty - moved_in)
                entry["qty"] = rest
                entry["remark"] = f"ORDER {rest}"
            netted.append(item)
        items = service.split_handover_items(netted, line_ids=printable)
        context, _source_id = build_handover_email(self.db, items, store_excel=False)
        handover = context["handover"]
        handover["subject_scope"] = f"{handover['subject_scope']} (Resent)"
        handover["headline"] = (
            f"RESENT: {handover['headline']}" if handover.get("headline") else "RESENT"
        )
        handover["resent"] = True
        context["sent_by"] = self._presser_name(actor_user_id)
        return context, len(items)

    def _presser_name(self, user_id: str) -> Optional[str]:
        from app.models.user import User

        user = self.db.get(User, user_id)
        return (user.name or user.email) if user is not None else None

    def _handover_notes(self, inquiry_ids: Sequence[str]) -> List[Tuple[Any, Dict[str, Any]]]:
        """Every handover email on record for these OIs, newest first."""
        return (
            self.db.query(Notification.created_at, Notification.data)
            .filter(
                Notification.type == "automation_email",
                Notification.data["trigger_type"].astext == TRIGGER_TYPE,
                Notification.data["source_id"].astext.in_([str(i) for i in inquiry_ids]),
            )
            .order_by(Notification.created_at.desc())
            .all()
        )

    @staticmethod
    def _last_sent(notes) -> Dict[str, Dict[str, Any]]:
        """The newest handover email on record per OI, automatic or resent."""
        from app.services.order_inquiry_reserve_service import as_utc

        out: Dict[str, Dict[str, Any]] = {}
        for created_at, data in notes:
            data = data or {}
            source_id = str(data.get("source_id"))
            if source_id in out:
                continue
            resent = data.get("source_kind") == SOURCE_KIND
            out[source_id] = {
                "at": as_utc(created_at),
                "kind": "resent" if resent else "automatic",
                "by": data.get("sent_by") if resent else None,
            }
        return out

    @staticmethod
    def _lines(rows, selected_ids, notes, linked) -> List[Dict[str, Any]]:
        """Every open row of a single OI for the preview's ticks. `sent_at`: the newest
        earlier handover email of this OI whose body names the row's item code (owner, 16
        Oct: "the first 2 lines were sent in the previous confirm"). A hint, not a lock."""
        from app.services.order_inquiry_reserve_service import as_utc

        out = []
        for row in rows:
            sent_at = None
            if row.item_code:
                sent_at = next(
                    (
                        as_utc(created_at)
                        for created_at, data in notes
                        if row.item_code in ((data or {}).get("body_html") or "")
                    ),
                    None,
                )
            out.append(
                {
                    "row_id": str(row.id),
                    "item_code": row.item_code,
                    # The open remainder, the same quantity the email asks for (SF3).
                    "qty": str(Decimal(str(row.qty)) - linked.get(str(row.id), Decimal("0"))),
                    "location": row.stock_location,
                    "delivery_date": row.delivery_date,
                    "selected": str(row.id) in selected_ids,
                    "sent_at": sent_at,
                }
            )
        return out

    def _linked(self, rows) -> Dict[str, Decimal]:
        from app.services.project_order_inquiry_service import ProjectOrderInquiryService

        return ProjectOrderInquiryService(self.db)._linked_qty_by_row([str(r.id) for r in rows])

    def _plan(
        self,
        inquiry_ids: Sequence[str],
        actor_user_id: str,
        row_ids: Optional[Sequence[str]] = None,
    ):
        """`(sendable, skipped)`; sendable = `[(inquiry, context, line_count, recipients,
        open_rows, picked_ids, automation)]` in the order asked. `row_ids` (single OI only)
        picks which open rows go; `None` is every open row."""
        if not inquiry_ids:
            raise AppException(422, "Choose at least one order inquiry.")
        # Counted once per OI: the dialog names an OI once per row it goes through.
        if len(set(map(str, inquiry_ids))) > MAX_INQUIRIES:
            raise AppException(422, f"Send at most {MAX_INQUIRIES} order inquiries at once.")
        if row_ids is not None and len(set(map(str, inquiry_ids))) != 1:
            raise AppException(422, "Lines can be chosen for one order inquiry at a time.")
        if row_ids is not None and not row_ids:
            raise AppException(422, "Choose at least one line.")
        inquiries = self._inquiries(inquiry_ids)
        sendable, skipped = [], []
        for inquiry in inquiries:
            open_rows = self._open_rows(inquiry)
            if row_ids is not None:
                wanted = {str(row_id) for row_id in row_ids}
                if not wanted <= {str(row.id) for row in open_rows}:
                    raise AppException(
                        422, "Some of the chosen lines are no longer open on this order inquiry."
                    )
                rows = [row for row in open_rows if str(row.id) in wanted]
            else:
                rows = open_rows
            if not rows:
                skipped.append(_skip(inquiry, "nothing_open"))
                continue
            context, line_count = self._context(rows, actor_user_id)
            if not context.get("raised_by") and inquiry.raised_by:
                # The rows are picked on the header's raiser; the email says the same.
                context["raised_by"] = str(inquiry.raised_by)
            # DEALER-OI-ROUTE + OI-ROUTE-BY-RAISER: every row this OI's class and raiser
            # match, as the automatic email; one email per row.
            picked = None if row_ids is None else [str(row.id) for row in rows]
            any_sent = False
            for automation in handover_automations(
                self.db,
                context.get("sales_order_class"),
                context.get("raised_by"),
            ):
                recipients = park_send.resolve_ordered(self.db, automation, context)
                if not recipients:
                    continue
                any_sent = True
                sendable.append(
                    (inquiry, context, line_count, recipients, open_rows, picked, automation)
                )
            if not any_sent:
                skipped.append(_skip(inquiry, "no_recipient"))
        return sendable, skipped

    def preview(
        self,
        inquiry_ids: Sequence[str],
        *,
        actor_user_id: str,
        row_ids: Optional[Sequence[str]] = None,
    ) -> Dict[str, Any]:
        sendable, skipped = self._plan(inquiry_ids, actor_user_id, row_ids)
        notes = self._handover_notes([str(entry[0].id) for entry in sendable])
        last_sent = self._last_sent(notes)
        # One OI asked for, however many rows it goes through (OI-ROUTE-BY-RAISER): each of
        # its emails carries the same line ticks.
        single = len(set(map(str, inquiry_ids))) == 1
        emails = []
        for inquiry, context, line_count, recipients, open_rows, picked, automation in sendable:
            email = park_send.render_preview(
                self.db, TRIGGER_TYPE, context, recipients, automation=automation
            )
            selected = set(picked) if picked is not None else {str(r.id) for r in open_rows}
            inquiry_notes = [n for n in notes if str((n[1] or {}).get("source_id")) == str(inquiry.id)]
            email.update(
                inquiry_id=str(inquiry.id),
                inquiry_no=inquiry.inquiry_no,
                inquiry_count=1,
                line_count=line_count,
                last_sent=last_sent.get(str(inquiry.id)),
                attachments=list(context["handover"].get("excel_files") or []),
                # The ticks are offered for one OI only; a bulk send takes every open row.
                lines=(
                    self._lines(open_rows, selected, inquiry_notes, self._linked(open_rows))
                    if single
                    else []
                ),
            )
            emails.append(email)
        return {
            "emails": emails,
            # One OI can go through more than one row (one email each); count the OIs.
            "inquiry_total": len({email["inquiry_id"] for email in emails}),
            "unresolved": [],
            "skipped": skipped,
            "automation_enabled": (
                all(entry[6] is not None and entry[6].enabled for entry in sendable)
                if sendable
                else bool((fallback := handover_automation(self.db)) and fallback.enabled)
            ),
        }

    def send(
        self,
        inquiry_ids: Sequence[str],
        *,
        actor_user_id: str,
        row_ids: Optional[Sequence[str]] = None,
    ) -> Dict[str, Any]:
        """One email per (OI, matching row). Each is its own committed automation run, so one
        failure is reported and the rest still go. An OI whose every email failed is
        `failed` (the dialog sends it again); one where some went is `partly_failed`, never
        retried by the dialog, so a row that already has it is not emailed twice."""
        from app.services import automation_triggers
        from app.services.automation_service import AutomationService
        from app.services.project_order_inquiry_service import store_handover_excel

        sendable, skipped = self._plan(inquiry_ids, actor_user_id, row_ids)
        sent = 0
        stored: set = set()
        went: set = set()
        failed: Dict[str, OrderInquiry] = {}
        for inquiry, context, _line_count, _recipients, _open_rows, _picked, automation in sendable:
            try:
                # Stored only now, for an OI that has someone to send to (review S2), and
                # once per OI however many rows it goes through. The workbook is this
                # email's own lines (OI-EMAIL-PURCHASING-FOCUS, 26 Oct 2026), ticked or all,
                # the same rule as the Confirm's.
                if str(inquiry.id) not in stored:
                    store_handover_excel(self.db, context, [str(inquiry.id)])
                    stored.add(str(inquiry.id))
                match = automation_triggers.TriggerMatch(
                    context=context, source_kind=SOURCE_KIND, source_id=str(inquiry.id)
                )
                AutomationService(self.db).send_match(automation, match)
                sent += 1
                went.add(str(inquiry.id))
            except Exception:  # noqa: BLE001 - reported per OI, never a stuck screen
                logger.exception(
                    "handover resend failed for order inquiry %s via automation %s",
                    inquiry.id,
                    automation.id,
                )
                failed[str(inquiry.id)] = inquiry
        for inquiry_id, inquiry in failed.items():
            skipped.append(
                _skip(inquiry, "partly_failed" if inquiry_id in went else "failed")
            )
        return {"emails_sent": sent, "items_sent": sent, "skipped": skipped}


def _skip(inquiry: OrderInquiry, reason: str) -> Dict[str, Any]:
    return {"inquiry_id": str(inquiry.id), "inquiry_no": inquiry.inquiry_no, "reason": reason}
