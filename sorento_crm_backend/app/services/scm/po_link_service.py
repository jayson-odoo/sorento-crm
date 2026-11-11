"""Link a PO line to an SO line through AutoCount, for Stock Debt and Order Inquiries.

One function, two scopes (OI-PO-LINK, `documentation/plans/scm/PLAN-oi-po-link-11nov.md`): a
`PoLinkScope` names the product and the SO lines a write may touch; `scope_for_snapshot_row` and
`scope_for_oi_rows` build it. Stock Debt (AC-LINK-CRM-UI):

Plan: `documentation/plans/autocount/PLAN-ac-link-crm-ui-04nov.md`. Gateway: Shared Service PR
#191 (`57-autocount-write-qtso-contract.md`) plus plan 55's relocate.

The CRM decides the intent (which PO row, which SO row, how much); the Shared Service performs
the AutoCount steps and owns recovery (resume). AutoCount stays the source of truth: after a
`done` answer the CRM applies the document AutoCount read back to its own PO lines (quantities,
links, a new row a split created, and `replacedLines` re-pointing a row whose number changed), so
the drill shows the link before the next sync. Nothing is applied on any other outcome.
"""
from __future__ import annotations

import hashlib
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from sqlalchemy import func, text
from sqlalchemy.orm import Session, defer

from app.models.company import Company
from app.models.inventory import Warehouse
from app.models.order import SalesOrder, SalesOrderLine
from app.models.procurement import PurchaseOrder, PurchaseOrderLine, Supplier
from app.models.stock_debt_snapshot import StockDebtSnapshotRow
from app.services import audit_service
from app.services.autocount_idempotency import attempt_store, is_definite_refusal, send_with_attempts
from app.services.error_handler import AppException, handle_not_found
from app.services.foundryx_autocount_client import FoundryxAutocountClient, FoundryxPullError
from app.services.project_supply_service import ProjectSupplyService
from app.services.scm import po_link_history, po_replace_hint
from app.services.scm.demand import demand_qty

logger = logging.getLogger(__name__)

#: The four actions the drill offers, as `/write-capabilities` names them on purchase orders.
ACTIONS = ("split_link", "link_row", "unlink_row", "relink_row")
_PO_KIND = "purchase-orders"
#: SS operation ids are uuids; anything else never reaches the gateway path.
_OPERATION_ID = re.compile(r"[A-Za-z0-9-]{1,64}")

WAITING = "Waiting for AutoCount"
SWITCHED_OFF = "Changes to AutoCount are switched off here"
UNREACHABLE = "Could not reach AutoCount"
_REASONS = {
    "VENDOR_UNSUPPORTED": WAITING,
    "WRITE_DISABLED": SWITCHED_OFF,
    "WRITE_NOT_ALLOWED": SWITCHED_OFF,
}


#: B12 merge: what the PO ingest writes on a line, so what the duplicate it created knows better.
#: The planner's `moq_snapshot` / `order_multiple_snapshot` are the CRM's own and stay.
_INGEST_OWNED = (
    "product_id", "warehouse_id", "qty_ordered", "qty_received", "qty_cancelled",
    "cancelled_by_cancel_doc", "removed_unreferenced", "unit_cost", "discount", "line_total", "uom",
    "currency", "expected_date", "line_status", "source_system", "from_so_line_ref",
    "from_po_line_ref", "from_po_number", "line_no", "from_so_external",
)


def _keys(ref: Optional[str]) -> Optional[Tuple[str, int, int]]:
    """`{db}:{DocKey}:{DtlKey}` -> (db, DocKey, DtlKey); None for anything else."""
    parts = (ref or "").strip().split(":")
    if len(parts) != 3:
        return None
    try:
        return parts[0], int(parts[1]), int(parts[2])
    except ValueError:
        return None


def _num(value) -> float:
    return float(value or 0)


def _iso(value: Optional[date]) -> Optional[str]:
    return value.isoformat() if value else None


def _line_numbers(db: Session, po_ids: Iterable[str]) -> Dict[str, int]:
    """A PO line's number as staff read it in AutoCount (`line_no`, AutoCount's Seq), else its
    position in the document (a line not synced since the column landed), as `_po_rows`."""
    ids = sorted({str(p) for p in po_ids if p})
    if not ids:
        return {}
    numbered = (
        db.query(
            PurchaseOrderLine.id,
            func.coalesce(
                PurchaseOrderLine.line_no,
                func.row_number().over(
                    partition_by=PurchaseOrderLine.purchase_order_id,
                    order_by=(PurchaseOrderLine.created_at, PurchaseOrderLine.id),
                ),
            ).label("line_no"),
        )
        .filter(PurchaseOrderLine.purchase_order_id.in_(ids))
        .all()
    )
    return {str(line_id): int(no) for line_id, no in numbered}


def po_links_for(db: Session, so_line_ids: Sequence[str]) -> Dict[str, List[Dict[str, Any]]]:
    """The PO lines now linked to each SO line (live, off `from_so_line_ref`), for the drill."""
    ids = [i for i in so_line_ids if i]
    if not ids:
        return {}
    refs = {
        ref.strip(): str(line_id)
        for line_id, ref in db.query(SalesOrderLine.id, SalesOrderLine.source_ref)
        .filter(SalesOrderLine.id.in_(ids), SalesOrderLine.source_ref.isnot(None))
        .all()
        if ref and ref.strip()
    }
    if not refs:
        return {}
    rows = (
        db.query(PurchaseOrderLine, PurchaseOrder.po_number, Warehouse.warehouse_code)
        .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderLine.purchase_order_id)
        .outerjoin(Warehouse, Warehouse.id == PurchaseOrderLine.warehouse_id)
        .filter(
            func.btrim(PurchaseOrderLine.from_so_line_ref).in_(list(refs)),
            PurchaseOrderLine.line_status == "open",
        )
        .all()
    )
    numbers = _line_numbers(db, {line.purchase_order_id for line, _n, _c in rows})
    out: Dict[str, List[Dict[str, Any]]] = {}
    for line, po_number, code in sorted(rows, key=lambda r: (r[1], numbers.get(str(r[0].id), 0))):
        out.setdefault(refs[line.from_so_line_ref.strip()], []).append(
            {
                "po_line_id": str(line.id),
                "po_number": po_number,
                "po_line_no": numbers.get(str(line.id)),
                "qty": _num(line.qty_ordered) - _num(line.qty_cancelled),
                # What is still to arrive on the line (TransferedQty includes cancels):
                # what Change PO can move (crew for the owner, 11 Nov).
                "open_qty": max(_num(line.qty_ordered) - _num(line.qty_received), 0.0),
                "location_code": code,
            }
        )
    return out


def _company_code_of(db: Session, company_id: Optional[str]) -> str:
    company = db.query(Company).filter(Company.id == company_id).first() if company_id else None
    return company.code if company is not None else ""


def actor_of(db: Session, current_user: dict) -> Dict[str, Any]:
    """{id, name} of the pressing user for the SS trace headers (a token may carry no name)."""
    name = current_user.get("name")
    if not name:
        from app.models.user import User

        name = db.query(User.name).filter(User.id == current_user["id"]).scalar()
    return {"id": str(current_user["id"]), "name": name or ""}


@dataclass
class PoLinkScope:
    """What one press may touch: the product, the public SO lines a write may name, the book."""

    product_id: str
    so_line_ids: set
    company_code: str = ""
    #: The refusal text for an SO line outside `so_line_ids` (it names the screen's own unit).
    outside_message: str = "That sales order line is not in this snapshot row."
    #: OI only: ticked rows left out because they have no AutoCount SO line.
    skipped: List[Dict[str, Any]] = field(default_factory=list)


def _scope_company_code(db: Session, so_line_ids: set) -> str:
    ids = sorted(so_line_ids)
    line = db.query(SalesOrderLine).filter(SalesOrderLine.id.in_(ids)).first() if ids else None
    return _company_code_of(db, line.company_id if line is not None else None)


def scope_for_snapshot_row(db: Session, snapshot_id: str, row_id: str) -> PoLinkScope:
    row = (
        db.query(StockDebtSnapshotRow)
        .filter(StockDebtSnapshotRow.id == row_id, StockDebtSnapshotRow.snapshot_id == snapshot_id)
        .first()
    )
    if row is None:
        raise handle_not_found("Snapshot row", row_id)
    ids = {str(l.get("sales_order_line_id")) for l in (row.lines or []) if l.get("sales_order_line_id")}
    return PoLinkScope(
        product_id=row.product_id, so_line_ids=ids, company_code=_scope_company_code(db, ids)
    )


NOT_IN_AUTOCOUNT = "Not in AutoCount yet"


def scope_for_oi_rows(db: Session, row_ids: Sequence[str]) -> PoLinkScope:
    """Ticked Order Inquiry rows -> their AutoCount SO lines (one product), the rest named."""
    from app.models.project_so import OrderInquiry, OrderInquiryRow, ProjectSalesOrderLine

    rows = (
        db.query(OrderInquiryRow, OrderInquiry.inquiry_no, ProjectSalesOrderLine.core_sales_order_line_id)
        .join(OrderInquiry, OrderInquiry.id == OrderInquiryRow.order_inquiry_id)
        .outerjoin(ProjectSalesOrderLine, ProjectSalesOrderLine.id == OrderInquiryRow.so_line_id)
        .filter(OrderInquiryRow.id.in_(list(row_ids)))
        .all()
    )
    core_ids = {str(c) for _r, _n, c in rows if c}
    lines = {
        str(l.id): l
        for l in (db.query(SalesOrderLine).filter(SalesOrderLine.id.in_(sorted(core_ids))).all() if core_ids else [])
    }
    ids: set = set()
    products: set = set()
    skipped: List[Dict[str, Any]] = []
    for row, inquiry_no, core_id in rows:
        line = lines.get(str(core_id)) if core_id else None
        if line is None or _keys(line.source_ref) is None:
            skipped.append({"inquiry_no": inquiry_no, "item_code": row.item_code, "reason": NOT_IN_AUTOCOUNT})
            continue
        ids.add(str(line.id))
        products.add(str(line.product_id))
    if len(products) > 1:
        raise AppException(status_code=422, message="Tick rows of one product.")
    if not ids:
        raise AppException(status_code=422, message="None of the ticked rows is in AutoCount yet.")
    return PoLinkScope(
        product_id=products.pop(),
        so_line_ids=ids,
        company_code=_scope_company_code(db, ids),
        outside_message="That sales order line is not among the ticked rows.",
        skipped=skipped,
    )


class PoLinkService:
    def __init__(self, db: Session, scope: Optional[PoLinkScope] = None, actor: Optional[dict] = None):
        self.db = db
        self.scope = scope
        #: {id, name} of the pressing user: every SS write of this service carries it.
        self.actor = actor
        # One per press (the service is built per request): every SS write of it carries this.
        self.request_id = uuid.uuid4().hex

    # ------------------------------------------------------------------ reads

    def _store(self):
        return attempt_store()

    def _company_code(self, company_id: Optional[str]) -> str:
        return _company_code_of(self.db, company_id)

    def capabilities(self, company_code: str) -> Dict[str, Dict[str, Any]]:
        """Each action enabled or not, with the plain reason, read from SS now."""
        try:
            body = FoundryxAutocountClient(self.db).write_capabilities(company_code)
        except FoundryxPullError:
            return {a: {"enabled": False, "reason": UNREACHABLE} for a in ACTIONS}
        entries = {
            e.get("op"): e
            for e in (body.get("capabilities") or [])
            if isinstance(e, dict) and e.get("kind") == _PO_KIND
        }
        out = {}
        for action in ACTIONS:
            entry = entries.get(action)
            if entry is not None and entry.get("enabled") is True:
                out[action] = {"enabled": True, "reason": None}
            else:
                code = (entry or {}).get("reasonCode")
                out[action] = {"enabled": False, "reason": _REASONS.get(code, WAITING)}
        return out

    def _open_lines(self, product_id: str):
        return (
            self.db.query(PurchaseOrderLine, PurchaseOrder, Warehouse.warehouse_code, Supplier.supplier_name)
            .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderLine.purchase_order_id)
            .outerjoin(Warehouse, Warehouse.id == PurchaseOrderLine.warehouse_id)
            .outerjoin(Supplier, Supplier.id == PurchaseOrder.supplier_id)
            .filter(
                PurchaseOrderLine.product_id == product_id,
                PurchaseOrderLine.source_ref.isnot(None),
                PurchaseOrderLine.from_so_line_ref.is_(None),
                PurchaseOrderLine.from_so_external.is_(None),
                *ProjectSupplyService.open_po_line_clauses(),
            )
            .all()
        )

    def options(self) -> Dict[str, Any]:
        rows = [r for r in self._open_lines(self.scope.product_id) if _keys(r[0].source_ref)]
        numbers = _line_numbers(self.db, {po.id for _l, po, _c, _s in rows})
        po_lines = []
        for line, po, code, supplier in rows:
            free = float(self._free(line))
            if free <= 0:
                continue
            po_lines.append(
                {
                    "po_line_id": str(line.id),
                    "po_number": po.po_number,
                    "po_line_no": numbers.get(str(line.id)),
                    "location_code": code,
                    "delivery_date": _iso(line.expected_date),
                    "po_qty": _num(line.qty_ordered),
                    "free_qty": free,
                    "supplier_name": supplier,
                    # The AutoCount book the line lives in: only a line of the SO line's own
                    # book can be linked to it (never shown; the picker greys the others).
                    "book": _keys(line.source_ref)[0],
                }
            )
        po_lines.sort(key=lambda l: (l["delivery_date"] is None, l["delivery_date"] or "", l["po_number"], l["po_line_no"] or 0))
        so_books = {
            str(line_id): keys[0]
            for line_id, ref in self.db.query(SalesOrderLine.id, SalesOrderLine.source_ref)
            .filter(SalesOrderLine.id.in_(sorted(self.scope.so_line_ids)))
            .all()
            if (keys := _keys(ref)) is not None
        }
        return {
            "capabilities": self.capabilities(self.scope.company_code),
            "po_lines": po_lines,
            "so_books": so_books,
        }

    def lines(self) -> List[Dict[str, Any]]:
        """The scope's SO lines as the dialog draws them (Order Inquiry has no snapshot to read them from)."""
        pairs = (
            self.db.query(SalesOrderLine, SalesOrder)
            .join(SalesOrder, SalesOrder.id == SalesOrderLine.sales_order_id)
            .filter(SalesOrderLine.id.in_(sorted(self.scope.so_line_ids)))
            .all()
        )
        links = po_links_for(self.db, [str(l.id) for l, _o in pairs])
        out = []
        for line, order in sorted(pairs, key=lambda p: (p[1].so_number, p[0].line_no or 0)):
            outstanding, _linked, _numbers = self._coverage(line)
            open_qty = float(outstanding)
            po_links = links.get(str(line.id), [])
            out.append({
                "sales_order_line_id": str(line.id),
                "so_number": order.so_number,
                "line_no": line.line_no,
                "open_qty": open_qty,
                "po_links": po_links,
                "now": {"so_status": "open", "open_qty": open_qty, "po_links": po_links},
            })
        return out

    def _coverage(self, so_line: SalesOrderLine) -> Tuple[Decimal, Decimal, List[str]]:
        """(outstanding, already linked to POs, those PO numbers) for one SO line, now."""
        outstanding = (
            self.db.query(demand_qty())
            .select_from(SalesOrderLine)
            .filter(SalesOrderLine.id == so_line.id)
            .scalar()
        )
        rows = (
            self.db.query(PurchaseOrderLine.qty_ordered, PurchaseOrder.po_number)
            .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderLine.purchase_order_id)
            .filter(
                func.btrim(PurchaseOrderLine.from_so_line_ref) == so_line.source_ref.strip(),
                PurchaseOrderLine.line_status == "open",
            )
            .all()
        )
        linked = sum((Decimal(str(qty or 0)) for qty, _n in rows), Decimal("0"))
        return Decimal(str(outstanding or 0)), linked, sorted({n for _q, n in rows})

    # ------------------------------------------------------------------ writes

    def _so_line(self, so_line_id: str) -> Tuple[SalesOrderLine, SalesOrder]:
        if str(so_line_id) not in self.scope.so_line_ids:
            raise AppException(status_code=422, message=self.scope.outside_message)
        pair = (
            self.db.query(SalesOrderLine, SalesOrder)
            .join(SalesOrder, SalesOrder.id == SalesOrderLine.sales_order_id)
            .filter(SalesOrderLine.id == so_line_id)
            .first()
        )
        if pair is None or _keys(pair[0].source_ref) is None:
            raise AppException(status_code=422, message="That sales order line is not in AutoCount.")
        return pair

    def _po_line(self, po_line_id: str) -> Tuple[PurchaseOrderLine, PurchaseOrder]:
        """An OPEN AutoCount PO line of the row's product (the same open rule the board reads)."""
        pair = (
            self.db.query(PurchaseOrderLine, PurchaseOrder)
            .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderLine.purchase_order_id)
            .filter(PurchaseOrderLine.id == po_line_id, *ProjectSupplyService.open_po_line_clauses())
            .first()
        )
        if pair is None or str(pair[0].product_id) != str(self.scope.product_id) or _keys(pair[0].source_ref) is None:
            raise AppException(status_code=422, message="That PO line is not an open AutoCount line for this product.")
        return pair

    def _row_so_refs(self) -> set:
        ids = sorted(self.scope.so_line_ids)
        if not ids:
            return set()
        return {
            ref.strip()
            for (ref,) in self.db.query(SalesOrderLine.source_ref)
            .filter(SalesOrderLine.id.in_(ids), SalesOrderLine.source_ref.isnot(None))
            .all()
            if ref and ref.strip()
        }

    def _linked_po_line(self, po_line_id: str):
        """A PO line linked to one of THIS row's SO lines, and that SO line (relink / unlink)."""
        po_line, po = self._po_line(po_line_id)
        current = (po_line.from_so_line_ref or "").strip()
        if not current or current not in self._row_so_refs():
            raise AppException(
                status_code=422, message=f"PO {po.po_number} line is not linked to a line of this row."
            )
        return po_line, po, current

    @staticmethod
    def _free(po_line: PurchaseOrderLine) -> Decimal:
        # `qty_received` is AutoCount's TransferedQty, which already includes what Cancel PO
        # documents cancelled (model comment on `qty_cancelled`), so this is the open balance.
        return Decimal(str(po_line.qty_ordered or 0)) - Decimal(str(po_line.qty_received or 0))

    def _result(self, answer: Dict[str, Any], *, so_line=None, so=None, po_line=None, po=None,
                qty=None, company_code: str, linked_line=None) -> Dict[str, Any]:
        doc = answer.get("document") or {}
        target = linked_line if linked_line is not None else po_line
        return {
            "sales_order_line_id": str(so_line.id) if so_line is not None else None,
            "so_number": so.so_number if so is not None else None,
            "so_line_no": so_line.line_no if so_line is not None else None,
            "po_number": answer.get("docNo") or doc.get("DocNo") or (po.po_number if po is not None else None),
            "qty": qty,
            "outcome": answer.get("outcome"),
            "error_code": answer.get("errorCode"),
            "warnings": list(answer.get("warnings") or []),
            "message": answer.get("message") or "",
            "operation_id": answer.get("operationId"),
            "company_code": company_code,
            # The PO line the follow-up (Move location, Resume) acts on: the linked line the
            # read-back produced, else the line the operation was sent for. Never shown.
            "po_line_id": str(target.id) if target is not None else None,
        }

    @staticmethod
    def _intent_key(path: str, body: Dict[str, Any], po_line: PurchaseOrderLine) -> str:
        """The same intent on the same PO row state gives the same key, so a retry after a
        timeout (or a second tab) replays the Shared Service's stored answer instead of
        writing twice. The row's qty is in it: once AutoCount changed the row, a new link is
        a new intent. An unlink also carries the link it removes (STOCKDEBT-LIVE-ACTIONS
        review): its body names no sales order, so unlinking the same row again after it was
        linked elsewhere would otherwise repeat the key and replay the first answer."""
        parts = [path, *(f"{k}={body[k]}" for k in sorted(body)), f"rowQty={format(Decimal(str(po_line.qty_ordered or 0)).normalize(), 'f')}"]
        if path == "po-links/unlink":
            parts.append(f"fromSo={(po_line.from_so_line_ref or '').strip()}")
        raw = "|".join(parts)
        return hashlib.sha256(raw.encode()).hexdigest()[:64]

    def _send_intent(self, path: str, body: Dict[str, Any], po_line: PurchaseOrderLine) -> Dict[str, Any]:
        """`_send` under the intent's key; after a definite AutoCount refusal the next press of the
        same intent goes as a new attempt (STOCKDEBT-LINK-IDEM-KEY), since the Shared Service
        replays a stored refusal for the same key and body forever. Any unconfirmed answer keeps
        the key, so a timeout retry still replays and never splits the PO row twice."""
        answer = send_with_attempts(
            self._store(),
            self._intent_key(path, body, po_line),
            lambda key: self._send(path, body, key=key),
        )
        if is_definite_refusal(answer):  # nothing was replaced: the B12 hint must not pair
            po_replace_hint.forget(po_line.source_ref)
        return answer

    def _send(self, path: str, body: Dict[str, Any], *, key: Optional[str] = None) -> Dict[str, Any]:
        try:
            return FoundryxAutocountClient(self.db).write(
                path, body, idempotency_key=key, request_id=self.request_id, actor=self.actor
            )
        except FoundryxPullError as exc:
            message = UNREACHABLE if exc.code == "UNREACHABLE" else exc.message
            return {"outcome": "vendor_error", "errorCode": exc.code, "message": message}

    def _log_write(self, action: str, answer: Dict[str, Any], po_line, so_line=None, so=None, qty=None) -> None:
        """One audit EVENT per write sent (done or not), on the PO line, naming the pressing user."""
        po_link_history.record_crm_write(
            self.db, po_line, po_line.purchase_order_id, actor=self.actor, request_id=self.request_id,
            action=action, outcome=answer.get("outcome"), operation_id=answer.get("operationId"),
            so_number=so.so_number if so is not None else None,
            so_line_no=so_line.line_no if so_line is not None else None,
            qty=float(qty) if qty is not None else None,
        )

    def _apply_safely(self, answer, po_line, so_ref):
        """`_apply`, never failing the request: AutoCount already changed, so the answer must
        reach the user; the next sync repairs the CRM's copy."""
        try:
            return self._apply(answer, po_line, so_ref)
        except Exception:  # noqa: BLE001
            logger.exception("po link: applying the AutoCount read-back failed")
            # A failed flush leaves the session unusable; what was applied is dropped and the
            # next sync brings AutoCount's state in.
            self.db.rollback()
            return None

    def _rekey(self, by_ref: Dict[str, List[PurchaseOrderLine]], old_ref: str, new_ref: str) -> None:
        """B12: the CRM line of AutoCount row `old_ref` now carries `new_ref`, ONE line per row.

        Ingest already paired them (`po_replace_hint`): nothing left to do. Ingest came first
        without a hint: it retired the old line and created a duplicate for `new_ref`; the old
        line (its id is what the CRM keys on) takes the duplicate's values and the duplicate
        goes. A duplicate something already points at is kept, and the old line is left
        retired under its old ref, so refs stay unique per PO."""
        olds = by_ref.pop(old_ref, [])
        if not olds:
            return
        old = olds[0]
        news = [l for l in by_ref.get(new_ref, []) if l is not old]
        if news and not self._merge_into(old, news[0]):
            by_ref[old_ref] = olds
            return
        old.source_ref = new_ref
        by_ref[new_ref] = [old]

    def _merge_into(self, keep: PurchaseOrderLine, dup: PurchaseOrderLine) -> bool:
        """`keep` takes `dup`'s values and whatever points at `dup` (the claim ingest raised
        from its SO link), then `dup` goes. In a savepoint: on any clash nothing changes and
        False is returned (both lines stay, `keep` under its old ref)."""
        from app.services.dependent_probe import referrers_of

        try:
            with self.db.begin_nested():
                for referrer, column in referrers_of(self.db, PurchaseOrderLine.__tablename__):
                    self.db.execute(
                        text(f'UPDATE {referrer} SET "{column}" = :keep WHERE "{column}" = :dup'),
                        {"keep": str(keep.id), "dup": str(dup.id)},
                    )
                for column in _INGEST_OWNED:
                    setattr(keep, column, getattr(dup, column))
                self.db.delete(dup)
                self.db.flush()
        except Exception:  # noqa: BLE001
            logger.warning("po link: could not merge the ingest duplicate %s into %s", dup.id, keep.id)
            self.db.expire_all()
            return False
        return True

    def _apply(self, answer: Dict[str, Any], po_line: PurchaseOrderLine, so_ref: Optional[str]) -> None:
        """AutoCount's read-back onto the CRM's PO lines (only on `done` / `recovered`)."""
        if answer.get("outcome") not in ("done", "recovered"):
            return None
        # B12: SS pushed the same read-back to the PO ingest DURING the call, in another
        # transaction. Read the lines afresh, or a stale copy is renamed over what ingest wrote.
        self.db.flush()
        self.db.expire_all()
        base = _keys(po_line.source_ref)
        if base is None:
            return None
        db_name, doc_key, _dtl = base
        prefix = f"{db_name}:{doc_key}:"
        by_ref: Dict[str, List[PurchaseOrderLine]] = {}
        for l in (
            self.db.query(PurchaseOrderLine)
            .filter(PurchaseOrderLine.purchase_order_id == po_line.purchase_order_id)
            .order_by(PurchaseOrderLine.created_at)
            .all()
        ):
            by_ref.setdefault((l.source_ref or "").strip(), []).append(l)
        for moved in answer.get("replacedLines") or []:
            self._rekey(by_ref, f"{prefix}{moved.get('oldDtlKey')}", f"{prefix}{moved.get('newDtlKey')}")
        # A retired copy never wins over a live line under the same ref.
        siblings = {
            ref: sorted(lines, key=lambda l: l.line_status == "cancelled")[0]
            for ref, lines in by_ref.items() if lines
        }
        so_keys = _keys(so_ref)
        doc = answer.get("document") or {}
        linked_line = None
        for detail in doc.get("Details") or []:
            ref = f"{prefix}{detail.get('DtlKey')}"
            linked = so_keys is not None and detail.get("FromSODtlKey") == so_keys[2]
            line = siblings.get(ref)
            if line is None:
                if not linked:
                    continue
                line = PurchaseOrderLine(
                    id=str(uuid.uuid4()),
                    purchase_order_id=po_line.purchase_order_id,
                    product_id=po_line.product_id,
                    warehouse_id=po_line.warehouse_id,
                    qty_received=Decimal("0"),
                    line_status="open",
                    company_id=po_line.company_id,
                    source_system=po_line.source_system,
                    source_ref=ref,
                    unit_cost=po_line.unit_cost,
                    uom=po_line.uom,
                    currency=po_line.currency,
                    expected_date=po_line.expected_date,
                )
                self.db.add(line)
                siblings[ref] = line
            if detail.get("Qty") is not None:
                line.qty_ordered = Decimal(str(detail["Qty"]))
            if linked:
                line.from_so_line_ref = so_ref
                linked_line = line
            # B13 (db3, 10 Nov): AutoCount answers 0, not null, for a row with no link.
            elif detail.get("FromSODtlKey") in (None, 0):
                line.from_so_line_ref = None
            location = detail.get("Location")
            if location:
                warehouse = (
                    self.db.query(Warehouse)
                    .filter(Warehouse.warehouse_code == location, Warehouse.company_id == po_line.company_id)
                    .first()
                )
                if warehouse is not None:
                    line.warehouse_id = warehouse.id
        self.db.flush()
        return linked_line

    def link(self, lines: List[Dict[str, Any]]) -> Dict[str, Any]:
        plan = []
        asked: Dict[str, Decimal] = {}
        so_asked: Dict[str, Decimal] = {}
        coverage: Dict[str, Tuple[Decimal, Decimal, List[str]]] = {}
        for item in lines:
            so_line, so = self._so_line(item["sales_order_line_id"])
            po_line, po = self._po_line(item["po_line_id"])
            if po_line.from_so_line_ref or po_line.from_so_external:
                raise AppException(status_code=422, message=f"PO {po.po_number} line is already linked.")
            if _keys(po_line.source_ref)[0] != _keys(so_line.source_ref)[0]:
                raise AppException(
                    status_code=422,
                    message=f"PO {po.po_number} is in a different AutoCount book from {so.so_number}.",
                )
            qty = Decimal(str(item["qty"]))
            # Over-link (crew, round 3): what the SO line still needs once the POs already
            # linked to it, and the earlier lines of this request, are taken off.
            key = str(so_line.id)
            if key not in coverage:
                coverage[key] = self._coverage(so_line)
            outstanding, linked, po_numbers = coverage[key]
            so_label = f"{so.so_number} line {so_line.line_no}" if so_line.line_no is not None else so.so_number
            if linked >= outstanding and linked > 0:
                raise AppException(
                    status_code=422,
                    message=f"{so_label} is already covered by PO {', '.join(po_numbers)}.",
                )
            left = outstanding - linked - so_asked.get(key, Decimal("0"))
            if qty > left:
                raise AppException(
                    status_code=422, message=f"{so_label} needs only {left.normalize():f} more."
                )
            so_asked[key] = so_asked.get(key, Decimal("0")) + qty
            free = self._free(po_line)
            asked[str(po_line.id)] = asked.get(str(po_line.id), Decimal("0")) + qty
            if qty <= 0 or asked[str(po_line.id)] > free:
                raise AppException(
                    status_code=422,
                    message=f"PO {po.po_number}: link between 1 and {free.normalize():f} in total.",
                )
            plan.append((so_line, so, po_line, po, qty))
        # Grouped per PO line, in request order; the SS batch op (`po-links/batch`) is not merged
        # yet, so `_send_group` is the one switch-over point.
        groups: Dict[str, List[Tuple]] = {}
        for step in plan:
            groups.setdefault(str(step[2].id), []).append(step)
        by_step: Dict[int, Dict[str, Any]] = {}
        for members in groups.values():
            for step, result in zip(members, self._send_group(members[0][2], members[0][3], members)):
                by_step[id(step)] = result
        return {"results": [by_step[id(step)] for step in plan]}

    def _send_group(self, po_line, po, members: List[Tuple]) -> List[Dict[str, Any]]:
        return [self._send_link(*member) for member in members]

    def _send_link(self, so_line, so, po_line, po, qty: Decimal) -> Dict[str, Any]:
        """One link write (whole row or split, AutoCount decides by the qty) and its read-back."""
        company_code = self._company_code(po_line.company_id)
        _db, po_doc, po_dtl = _keys(po_line.source_ref)
        _db2, so_doc, so_dtl = _keys(so_line.source_ref)
        body = {
            "companyCode": company_code,
            "poDocKey": po_doc,
            "poDtlKey": po_dtl,
            "soDocKey": so_doc,
            "soDtlKey": so_dtl,
            "qty": float(qty) if qty != qty.to_integral() else int(qty),
        }
        if so.order_date:
            body["soDocDate"] = so.order_date.isoformat()
        if po.issue_date:
            body["docDate"] = po.issue_date.isoformat()
        row_qty = Decimal(str(po_line.qty_ordered or 0))
        if qty >= row_qty:  # whole row: the row itself moves onto the SO line
            po_replace_hint.remember(po_line.source_ref, qty=row_qty, from_so_ref=so_line.source_ref)
        else:  # split: the row keeps the rest and its own link
            po_replace_hint.remember(po_line.source_ref, qty=row_qty - qty,
                                     from_so_ref=po_line.from_so_line_ref)
        answer = self._send_intent("po-links", body, po_line)
        linked = self._apply_safely(answer, po_line, so_line.source_ref.strip())
        self._log_write("link", answer, po_line, so_line, so, qty)
        return self._result(answer, so_line=so_line, so=so, po_line=po_line, po=po,
                            qty=_num(qty), company_code=company_code, linked_line=linked)

    def _send_unlink(self, po_line, po, so_line=None, so=None) -> Dict[str, Any]:
        """One unlink write: the PO row keeps its qty and stays open, with no sales order."""
        keys = _keys(po_line.source_ref)
        company_code = self._company_code(po_line.company_id)
        body = {"companyCode": company_code, "poDocKey": keys[1], "poDtlKey": keys[2]}
        if po.issue_date:
            body["docDate"] = po.issue_date.isoformat()
        po_replace_hint.remember(po_line.source_ref, qty=po_line.qty_ordered, from_so_ref=None)
        answer = self._send_intent("po-links/unlink", body, po_line)
        self._apply_safely(answer, po_line, None)
        self._log_write("unlink", answer, po_line, so_line, so, po_line.qty_ordered)
        return self._result(answer, so_line=so_line, so=so, po_line=po_line, po=po,
                            qty=_num(po_line.qty_ordered), company_code=company_code)

    def _so_line_by_ref(self, ref: str):
        return (
            self.db.query(SalesOrderLine, SalesOrder)
            .join(SalesOrder, SalesOrder.id == SalesOrderLine.sales_order_id)
            .filter(func.btrim(SalesOrderLine.source_ref) == ref)
            .first()
        ) or (None, None)

    def unlink(self, po_line_ids: List[str]) -> Dict[str, Any]:
        """Unlink exactly the PO lines ticked, each linked to a line of this row.

        Unlink is a detach action: the deferred-action countdown (CLAUDE.md CRUD standard)
        is owed before the Shared Service turns `unlink_row` on; until then the menu item is
        greyed "Waiting for AutoCount" and this route answers AutoCount's refusal."""
        plan = [self._linked_po_line(po_line_id) for po_line_id in po_line_ids]
        return {
            "results": [
                self._send_unlink(po_line, po, *self._so_line_by_ref(current))
                for po_line, po, current in plan
            ]
        }

    def change(self, changes: List[Dict[str, Any]]) -> Dict[str, Any]:
        """STOCKDEBT-LIVE-ACTIONS "Change PO..." (owner, 11 Nov, card answers 1a/2a/3a): swap the
        ONE PO line covering an SO line for another PO line, for the open balance still due on it
        (what was already received stays with the old PO).

        Refused, with nothing sent, unless the line is covered by exactly one PO line and the
        new PO line has that qty free. The old PO line is unlinked FIRST: while it covers the
        line, AutoCount refuses any new link as above the SO row's outstanding
        (QTY_ABOVE_OUTSTANDING, AC-E2E-DB3 on db3, 11 Nov). The new link is sent only once the
        unlink is done; if it then fails, the answer names the PO that was unlinked, so the
        user knows the line is uncovered. The old PO line keeps its qty and stays open."""
        named = [str(item["sales_order_line_id"]) for item in changes]
        if len(set(named)) != len(named):
            raise AppException(status_code=422, message="Name each sales order line once.")
        plan = []
        asked: Dict[str, Decimal] = {}
        for item in changes:
            so_line, so = self._so_line(item["sales_order_line_id"])
            so_label = f"{so.so_number} line {so_line.line_no}" if so_line.line_no is not None else so.so_number
            current = [
                pair for pair in (
                    self.db.query(PurchaseOrderLine, PurchaseOrder)
                    .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderLine.purchase_order_id)
                    .filter(
                        func.btrim(PurchaseOrderLine.from_so_line_ref) == so_line.source_ref.strip(),
                        PurchaseOrderLine.line_status == "open",
                    )
                    .all()
                )
            ]
            if len(current) != 1:
                raise AppException(
                    status_code=422, message=f"{so_label} is not covered by exactly one PO line."
                )
            # Crew for the owner, 11 Nov: Change PO moves the OPEN balance still covered by the
            # old PO line; what was already received stays with the old PO. `_free` is that
            # balance (`qty_received` is TransferedQty, which already includes cancels).
            qty = self._free(current[0][0])
            if qty <= 0:
                raise AppException(
                    status_code=422,
                    message=f"Nothing is left open on PO {current[0][1].po_number} to change.",
                )
            # The old row is written to (unlinked) as well: the same open-AutoCount-line checks
            # as the new one, before anything is sent.
            old_line, old_po = self._po_line(str(current[0][0].id))
            new_line, new_po = self._po_line(item["po_line_id"])
            if str(new_line.id) == str(old_line.id):
                raise AppException(status_code=422, message=f"{so_label} is already covered by that PO line.")
            if new_line.from_so_line_ref or new_line.from_so_external:
                raise AppException(status_code=422, message=f"PO {new_po.po_number} line is already linked.")
            if _keys(new_line.source_ref)[0] != _keys(so_line.source_ref)[0]:
                raise AppException(
                    status_code=422,
                    message=f"PO {new_po.po_number} is in a different AutoCount book from {so.so_number}.",
                )
            asked[str(new_line.id)] = asked.get(str(new_line.id), Decimal("0")) + qty
            free = self._free(new_line)
            if asked[str(new_line.id)] > free:
                raise AppException(
                    status_code=422, message=f"PO {new_po.po_number} has only {free.normalize():f} free."
                )
            plan.append((so_line, so, old_line, old_po, new_line, new_po, qty))
        results = []
        for so_line, so, old_line, old_po, new_line, new_po, qty in plan:
            unlinked = self._send_unlink(old_line, old_po, so_line, so)
            results.append({**unlinked, "action": "unlink"})
            if unlinked["outcome"] != "done":
                continue  # nothing changed: the old PO still covers the line
            linked = self._send_link(so_line, so, new_line, new_po, qty)
            results.append({
                **linked,
                "action": "link",
                "unlinked_po": None if linked["outcome"] == "done" else old_po.po_number,
            })
        return {"results": results}

    def relink(self, moves: List[Dict[str, Any]]) -> Dict[str, Any]:
        plan = []
        for move in moves:
            so_line, so = self._so_line(move["to_sales_order_line_id"])
            po_line, po, current = self._linked_po_line(move["po_line_id"])
            if current == so_line.source_ref.strip():
                raise AppException(
                    status_code=422, message=f"PO {po.po_number} line is already on that sales order line."
                )
            plan.append((so_line, so, po_line, po))
        results = []
        for so_line, so, po_line, po in plan:
            company_code = self._company_code(po_line.company_id)
            _d, po_doc, po_dtl = _keys(po_line.source_ref)
            _d2, so_doc, so_dtl = _keys(so_line.source_ref)
            body = {"companyCode": company_code, "poDocKey": po_doc, "poDtlKey": po_dtl,
                    "soDocKey": so_doc, "soDtlKey": so_dtl}
            if po.issue_date:
                body["docDate"] = po.issue_date.isoformat()
            if so.order_date:
                body["soDocDate"] = so.order_date.isoformat()
            po_replace_hint.remember(po_line.source_ref, qty=po_line.qty_ordered,
                                     from_so_ref=so_line.source_ref)
            answer = self._send_intent("po-links/relink", body, po_line)
            linked = self._apply_safely(answer, po_line, so_line.source_ref.strip())
            self._log_write("relink", answer, po_line, so_line, so, po_line.qty_ordered)
            results.append(self._result(answer, so_line=so_line, so=so, po_line=po_line, po=po,
                                        qty=_num(po_line.qty_ordered), company_code=company_code,
                                        linked_line=linked))
        return {"results": results}

    def _any_po_line(self, po_line_id: str) -> Tuple[PurchaseOrderLine, PurchaseOrder]:
        """A PO line by id, through the caller's company scope; its company and keys are the
        server's, never the browser's."""
        pair = (
            self.db.query(PurchaseOrderLine, PurchaseOrder)
            .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderLine.purchase_order_id)
            .filter(PurchaseOrderLine.id == po_line_id)
            .first()
        )
        if pair is None or _keys(pair[0].source_ref) is None:
            raise handle_not_found("PO line", po_line_id)
        return pair

    def relocate(self, po_line_id: str) -> Dict[str, Any]:
        """Move a linked PO line to its SO line's location (after `LOCATION_NOT_MOVED`)."""
        po_line, po = self._any_po_line(po_line_id)
        if not po_line.from_so_line_ref:
            raise AppException(status_code=422, message=f"PO {po.po_number} line is not linked.")
        so_ref = po_line.from_so_line_ref.strip()
        so_line, so = self._so_line_by_ref(so_ref)
        company_code = self._company_code(po_line.company_id)
        keys = _keys(po_line.source_ref)
        answer = self._send(
            "po-links/relocate",
            {"companyCode": company_code, "poDocKey": keys[1], "poDtlKey": keys[2]},
        )
        linked = self._apply_safely(answer, po_line, so_ref)
        self._log_write("relocate", answer, po_line, so_line, so, po_line.qty_ordered)
        return self._result(answer, so_line=so_line, so=so, po_line=po_line, po=po,
                            qty=_num(po_line.qty_ordered), company_code=company_code, linked_line=linked)

    def resume(self, operation_id: str, po_line_id: str, sales_order_line_id: Optional[str]) -> Dict[str, Any]:
        """Ask the Shared Service to finish an operation it stopped; it re-reads AutoCount
        first. The CRM never re-sends a step. The company is the PO line's."""
        if not _OPERATION_ID.fullmatch(operation_id or ""):
            raise AppException(status_code=422, message="Unknown operation.")
        po_line, po = self._any_po_line(po_line_id)
        so_line = so = None
        if sales_order_line_id:
            pair = (
                self.db.query(SalesOrderLine, SalesOrder)
                .join(SalesOrder, SalesOrder.id == SalesOrderLine.sales_order_id)
                .filter(SalesOrderLine.id == sales_order_line_id)
                .first()
            )
            if pair is not None:
                so_line, so = pair
        company_code = self._company_code(po_line.company_id)
        answer = self._send(f"write-operations/{operation_id}/resume", {"companyCode": company_code})
        so_ref = so_line.source_ref.strip() if so_line is not None and so_line.source_ref else None
        linked = self._apply_safely(answer, po_line, so_ref)
        self._log_write("resume", answer, po_line, so_line, so, po_line.qty_ordered)
        return self._result(answer, so_line=so_line, so=so, po_line=po_line, po=po,
                            qty=_num(po_line.qty_ordered), company_code=company_code, linked_line=linked)
