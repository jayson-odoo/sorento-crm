"""Complaint <-> Delivery Order auto-fulfilment.

A replacement / fulfilment Delivery Order (DO) names the complaint number(s) it
fulfils in its ``remarks_cs`` field. This service is the single place that:

1. **Reconciles links** (delta-only) from a DO's Remarks CS to the named
   complaints — gated so only ``processed_by_cs`` / ``fulfilled`` complaints link.
2. **Recomputes status** — a ``processed_by_cs`` complaint becomes ``fulfilled``
   once every non-cancelled linked DO is delivered; a ``fulfilled`` complaint
   reopens to ``processed_by_cs`` if a non-delivered DO links (or a delivered one
   un-delivers). ``closed`` / ``rejected`` are sticky and never touched.
3. **Emits per-DO delivery notifications** (customer Respond/WhatsApp + Complaint
   team in-app/email), once per ``(complaint, DO)`` via the
   ``delivery_notified_at`` stamp — best-effort, post-commit, never "fulfilled".

Triggered from order import, ``PUT /orders/{id}``, and ``is_cancelled`` flips.
Batched + delta-only so a no-change import issues no per-row complaint queries.

See docs/plans/PLAN-complaint-do-auto-fulfilment.md.
"""
from __future__ import annotations

import logging
import re
import uuid
from collections import defaultdict
from datetime import datetime
from typing import Iterable, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.models.complaints import Complaint, ComplaintFulfilmentOrder
from app.models.order import Order, OrderLine
from app.models.product import Product

logger = logging.getLogger(__name__)

# Complaint statuses a DO may link to. Linking is gated on the complaint already
# being processed by CS (the single open state in the fulfilment loop).
LINKABLE_STATUSES = {"processed_by_cs", "fulfilled"}

# Remarks CS tokens split on '&', ',', and any whitespace.
_TOKEN_SPLIT = re.compile(r"[\s,&]+")


class ComplaintFulfilmentService:
    """Reconcile complaint<->DO links, recompute fulfilment, dispatch notifications."""

    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------ #
    # Parsing helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _parse_tokens(remarks: Optional[str]) -> set[str]:
        """Lowercased complaint-number tokens from a Remarks CS string."""
        if not remarks:
            return set()
        return {
            t.strip().lower()
            for t in _TOKEN_SPLIT.split(str(remarks))
            if t and t.strip()
        }

    @staticmethod
    def _norm_remarks(value: Optional[str]) -> str:
        return (value or "").strip()

    def _items_for_orders(self, order_ids: list[str]) -> dict[str, list[dict]]:
        """``{order_id: [{product_code, product_type, qty}]}`` in one query."""
        out: dict[str, list[dict]] = defaultdict(list)
        if not order_ids:
            return out
        rows = (
            self.db.query(OrderLine, Product)
            .outerjoin(Product, Product.id == OrderLine.product_id)
            .filter(OrderLine.order_id.in_(order_ids))
            .order_by(OrderLine.line_sequence)
            .all()
        )
        for line, product in rows:
            qty = line.quantity
            try:
                qty_val: object = float(qty) if qty is not None else None
                if qty_val is not None and float(qty_val).is_integer():
                    qty_val = int(qty_val)
            except (TypeError, ValueError):
                qty_val = qty
            out[str(line.order_id)].append(
                {
                    "product_code": getattr(product, "product_code", None)
                    if product
                    else None,
                    "product_type": getattr(product, "item_type", None)
                    if product
                    else None,
                    "qty": qty_val,
                }
            )
        return out

    # ------------------------------------------------------------------ #
    # Core recompute
    # ------------------------------------------------------------------ #
    def reconcile_links_and_status(
        self, changes: list[dict], *, dry_run: bool
    ) -> tuple[list[str], list[dict]]:
        """Reconcile links + recompute fulfilment for a batch of changed orders.

        ``changes`` = ``[{"order": Order, "old_remarks": str|None}]`` — only orders
        whose Remarks CS / delivery / cancel actually changed should be passed
        (delta-only; an unchanged import passes an empty list).

        Mutates the session (link inserts/deletes, complaint.status, link
        ``delivery_notified_at`` stamps) but does NOT commit — the caller owns the
        commit. On ``dry_run=True`` (validate-only import) it computes warnings only
        and writes nothing.

        Returns ``(warnings, notify_payloads)``. ``notify_payloads`` is a list of
        serializable dicts to hand to :meth:`dispatch_delivery_notifications` AFTER
        the commit.
        """
        warnings: list[str] = []
        notify_payloads: list[dict] = []
        if not changes:
            return warnings, notify_payloads

        db = self.db

        # 1. Parse new tokens per order; gather them for ONE batched complaint lookup.
        parsed: list[tuple[Order, set[str]]] = []
        all_new_tokens: set[str] = set()
        for ch in changes:
            order = ch["order"]
            new_tokens = self._parse_tokens(getattr(order, "remarks_cs", None))
            parsed.append((order, new_tokens))
            all_new_tokens |= new_tokens

        complaints_by_token: dict[str, Complaint] = {}
        if all_new_tokens:
            rows = (
                db.query(Complaint)
                .filter(func.lower(Complaint.complaint_number).in_(list(all_new_tokens)))
                .all()
            )
            for c in rows:
                if c.complaint_number:
                    complaints_by_token[c.complaint_number.strip().lower()] = c

        # 2. Existing links for the changed orders (one query).
        order_ids = [str(o.id) for o, _ in parsed if getattr(o, "id", None)]
        existing_links: list[ComplaintFulfilmentOrder] = []
        if order_ids:
            existing_links = (
                db.query(ComplaintFulfilmentOrder)
                .filter(ComplaintFulfilmentOrder.order_id.in_(order_ids))
                .all()
            )
        links_by_order: dict[str, list[ComplaintFulfilmentOrder]] = defaultdict(list)
        for link in existing_links:
            links_by_order[str(link.order_id)].append(link)

        affected_complaint_ids: set[str] = set()

        # 3. Reconcile link delta per order.
        for order, new_tokens in parsed:
            oid = str(order.id)
            existing = links_by_order.get(oid, [])
            existing_cids = {str(link.complaint_id) for link in existing}
            desired_cids: set[str] = set()
            for tok in new_tokens:
                complaint = complaints_by_token.get(tok)
                if complaint is None:
                    # Token matches no complaint -> ignore (no warn spam).
                    continue
                status = (getattr(complaint, "status", None) or "").strip().lower()
                if status not in LINKABLE_STATUSES:
                    warnings.append(
                        f"Order {order.order_number}: complaint "
                        f"{complaint.complaint_number} not yet processed by CS / is "
                        f"{status or 'unknown'} — not linked"
                    )
                    continue
                desired_cids.add(str(complaint.id))

            to_add = desired_cids - existing_cids
            to_remove = existing_cids - desired_cids
            affected_complaint_ids |= desired_cids
            affected_complaint_ids |= to_remove
            if dry_run:
                continue
            for cid in to_add:
                db.add(
                    ComplaintFulfilmentOrder(
                        id=str(uuid.uuid4()), complaint_id=cid, order_id=oid
                    )
                )
            if to_remove:
                for link in existing:
                    if str(link.complaint_id) in to_remove:
                        db.delete(link)

        if dry_run:
            return warnings, notify_payloads

        db.flush()

        # 4. Recompute every complaint linked to ANY changed order — a delivery-date
        #    or cancel change flips fulfilment even when remarks are unchanged.
        if order_ids:
            for link in (
                db.query(ComplaintFulfilmentOrder)
                .filter(ComplaintFulfilmentOrder.order_id.in_(order_ids))
                .all()
            ):
                affected_complaint_ids.add(str(link.complaint_id))

        if not affected_complaint_ids:
            return warnings, notify_payloads

        complaint_by_id = {
            str(c.id): c
            for c in db.query(Complaint)
            .filter(Complaint.id.in_(affected_complaint_ids))
            .all()
        }
        all_links = (
            db.query(ComplaintFulfilmentOrder)
            .filter(ComplaintFulfilmentOrder.complaint_id.in_(affected_complaint_ids))
            .all()
        )
        links_by_complaint: dict[str, list[ComplaintFulfilmentOrder]] = defaultdict(list)
        linked_order_ids: set[str] = set()
        for link in all_links:
            links_by_complaint[str(link.complaint_id)].append(link)
            linked_order_ids.add(str(link.order_id))

        orders_by_id: dict[str, Order] = {}
        if linked_order_ids:
            orders_by_id = {
                str(o.id): o
                for o in db.query(Order).filter(Order.id.in_(linked_order_ids)).all()
            }

        now = datetime.utcnow()
        notify_links: list[tuple[Complaint, Order]] = []
        for cid, complaint in complaint_by_id.items():
            links = links_by_complaint.get(cid, [])
            linked_orders = [orders_by_id.get(str(link.order_id)) for link in links]
            non_cancelled = [
                o for o in linked_orders if o is not None and not bool(o.is_cancelled)
            ]
            all_delivered = bool(non_cancelled) and all(
                o.actual_delivery_date is not None for o in non_cancelled
            )
            status = (getattr(complaint, "status", None) or "").strip().lower()
            if status == "processed_by_cs" and all_delivered:
                complaint.status = "fulfilled"
                complaint.resolved_at = now
                self._emit_complaint_resolved(complaint)
            elif status == "fulfilled" and not all_delivered:
                # Auto-reopen to the single pre-fulfilment state. No SLA to resurrect.
                # Clear resolved_at so a reopened complaint never shows a stale
                # resolution timestamp (status is the source of truth).
                complaint.status = "processed_by_cs"
                complaint.resolved_at = None

            # Per-DO delivery notify: newly-delivered, non-cancelled, not yet notified.
            for link in links:
                order = orders_by_id.get(str(link.order_id))
                if order is None or bool(order.is_cancelled):
                    continue
                if order.actual_delivery_date is None:
                    continue
                if link.delivery_notified_at is not None:
                    continue
                link.delivery_notified_at = now
                notify_links.append((complaint, order))

        if notify_links:
            items_by_order = self._items_for_orders(
                list({str(o.id) for _, o in notify_links})
            )
            for complaint, order in notify_links:
                notify_payloads.append(
                    {
                        "complaint_id": str(complaint.id),
                        "complaint_number": getattr(complaint, "complaint_number", None),
                        "order_number": getattr(order, "order_number", None),
                        "items": items_by_order.get(str(order.id), []),
                    }
                )

        return warnings, notify_payloads

    def _emit_complaint_resolved(self, complaint: Complaint) -> None:
        """Mirror ``_finalize_complaint``'s SLA close (best-effort)."""
        try:
            from app.services.form_sla_service import emit_form_event

            emit_form_event(
                self.db,
                "complaint",
                str(complaint.id),
                "resolved",
                contact_id=getattr(complaint, "contact_id", None),
            )
        except Exception as exc:  # best-effort — status is the source of truth
            logger.warning(
                "Fulfilment: SLA 'resolved' emit failed for complaint %s: %s",
                complaint.id,
                exc,
            )

    # ------------------------------------------------------------------ #
    # Notification dispatch (post-commit, best-effort)
    # ------------------------------------------------------------------ #
    def dispatch_delivery_notifications(self, notify_payloads: list[dict]) -> None:
        """Send per-DO delivery notices (customer + Complaint team). Best-effort —
        each send is isolated so one failure never aborts the rest, and never
        propagates (the import/PUT already committed)."""
        if not notify_payloads:
            return
        from app.services.complaints_service import ComplaintService

        complaint_svc = ComplaintService(self.db)
        for payload in notify_payloads:
            complaint_id = payload.get("complaint_id")
            complaint_number = payload.get("complaint_number") or ""
            order_number = payload.get("order_number") or ""
            items = payload.get("items") or []
            try:
                complaint_svc.notify_customer_do_delivered(
                    complaint_id,
                    complaint_number=complaint_number,
                    order_number=order_number,
                    items=items,
                )
            except Exception:
                logger.exception(
                    "Fulfilment: customer delivery notify failed (complaint=%s, DO=%s)",
                    complaint_id,
                    order_number,
                )
            try:
                complaint_svc.notify_team_do_delivered(
                    complaint_id,
                    complaint_number=complaint_number,
                    order_number=order_number,
                    items=items,
                )
            except Exception:
                logger.exception(
                    "Fulfilment: team delivery notify failed (complaint=%s, DO=%s)",
                    complaint_id,
                    order_number,
                )

    # ------------------------------------------------------------------ #
    # Convenience trigger for single-order paths (PUT / cancel)
    # ------------------------------------------------------------------ #
    def apply_for_orders(self, changes: list[dict]) -> list[str]:
        """Reconcile + recompute for already-committed order changes, commit the
        link/status writes, then dispatch notifications. Returns warnings."""
        warnings, notify_payloads = self.reconcile_links_and_status(
            changes, dry_run=False
        )
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            logger.exception("Fulfilment: commit of reconcile writes failed")
            return warnings
        try:
            self.dispatch_delivery_notifications(notify_payloads)
        except Exception:
            logger.exception("Fulfilment: notification dispatch failed")
        return warnings

    # ------------------------------------------------------------------ #
    # Freeze signal
    # ------------------------------------------------------------------ #
    def is_remarks_cs_locked(self, order: Order) -> bool:
        """A DO's Remarks CS is frozen once it is delivered AND linked to >=1 complaint."""
        if order is None or getattr(order, "actual_delivery_date", None) is None:
            return False
        if getattr(order, "id", None) is None:
            return False
        return (
            self.db.query(ComplaintFulfilmentOrder.id)
            .filter(ComplaintFulfilmentOrder.order_id == str(order.id))
            .first()
            is not None
        )

    # ------------------------------------------------------------------ #
    # Read endpoints
    # ------------------------------------------------------------------ #
    def list_fulfilment_orders(self, complaint_id: str) -> list[dict]:
        """Linked replacement DOs for a complaint (newest-linked first), each with
        its line items for the detail popup."""
        links = (
            self.db.query(ComplaintFulfilmentOrder)
            .filter(ComplaintFulfilmentOrder.complaint_id == str(complaint_id))
            .order_by(ComplaintFulfilmentOrder.linked_at.desc())
            .all()
        )
        order_ids = [str(link.order_id) for link in links]
        if not order_ids:
            return []
        orders = {
            str(o.id): o
            for o in self.db.query(Order)
            .options(joinedload(Order.order_status))
            .filter(Order.id.in_(order_ids))
            .all()
        }
        items_by_order = self._items_for_orders(order_ids)
        result: list[dict] = []
        for link in links:
            order = orders.get(str(link.order_id))
            if order is None:
                continue
            order_status = getattr(order, "order_status", None)
            status_code = (getattr(order_status, "status_code", None) or "").lower()
            status_label = (
                getattr(order_status, "status_name", None) or status_code or ""
            )
            result.append(
                {
                    "order_id": str(order.id),
                    "order_number": order.order_number,
                    "status": status_code,
                    "status_label": status_label,
                    "actual_delivery_date": order.actual_delivery_date,
                    "is_cancelled": bool(order.is_cancelled),
                    "items": items_by_order.get(str(order.id), []),
                }
            )
        return result

    def list_fulfilled_complaints(self, order_id: str) -> list[dict]:
        """Complaints a DO fulfils (reverse view on the DO detail page)."""
        rows = (
            self.db.query(
                ComplaintFulfilmentOrder.complaint_id, Complaint.complaint_number
            )
            .join(Complaint, Complaint.id == ComplaintFulfilmentOrder.complaint_id)
            .filter(ComplaintFulfilmentOrder.order_id == str(order_id))
            .order_by(ComplaintFulfilmentOrder.linked_at.desc())
            .all()
        )
        return [
            {"complaint_id": str(cid), "complaint_number": number}
            for cid, number in rows
        ]
