"""AC-QTSO-CRM: create, update and cancel a project quotation or sales order in AutoCount.

Plan: `documentation/plans/autocount/PLAN-ac-qtso-crm-04nov.md` ("Phase 2 contract").

The CRM decides the intent; the Shared Service (SS) performs the AutoCount steps and answers one
JSON shape for every status. AutoCount stays the source of truth: only a `done` answer writes to
the CRM (document number, key, last-modified), and what the dialog lists is AutoCount's own
read-back, never the lines we sent. Nothing here ever deletes an AutoCount document or line: what
needs the SS delete / cancel door is listed as `waiting` and sent nowhere.

Identity (U19): the company code and every document / line key come from the CRM record, never
from the request.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.models.company import Company
from app.models.order import Customer, SalesOrderLine
from app.models.project_so import (
    AMENDMENT_PUBLISHED,
    SO_STATUS_AMENDED,
    SO_STATUS_PUBLISHED,
    VERB_ADD_LINE,
    VERB_ADVANCE,
    VERB_DELAY,
    VERB_QTY_CHANGE,
    ProjectSalesOrder,
    ProjectSalesOrderLine,
    SOAmendment,
)
from app.models.projects import (
    Project,
    ProjectParty,
    ProjectPurchaseOrder,
    ProjectQuotationDocument,
    ProjectQuotationIssue,
    ProjectQuotationIssueScope,
    ProjectQuotationLine,
)
from app.services.error_handler import AppException
from app.services.foundryx_autocount_client import FoundryxAutocountClient, FoundryxPullError
from app.services.project_so_delta_service import ProjectSODeltaService
from app.services.project_so_draft_service import ProjectSODraftService

logger = logging.getLogger(__name__)

_MYT = ZoneInfo("Asia/Kuala_Lumpur")
_ZERO = Decimal("0")

WAITING = "Waiting for AutoCount"
SWITCHED_OFF_HERE = "Changes to AutoCount are switched off here"
UNREACHABLE = "Could not reach AutoCount"
PENDING = "Sent; AutoCount has not confirmed yet. It will show after the next sync."
NOT_ACCEPTED = "The customer has not accepted this quotation yet."
ALREADY = "Already in AutoCount."

_REASONS = {
    "VENDOR_UNSUPPORTED": WAITING,
    "WRITE_DISABLED": SWITCHED_OFF_HERE,
    "WRITE_NOT_ALLOWED": SWITCHED_OFF_HERE,
    "WRITE_COMPANY_NOT_TEST": SWITCHED_OFF_HERE,
}
OPS = ("create_doc", "edit_doc", "add_line", "delete_line", "cancel_doc")
_KINDS = {"sales_orders": "sales-orders", "quotations": "quotations"}
_DONE = ("done", "recovered")


# ------------------------------------------------------------------ small helpers


def _dec(value: Any) -> Decimal:
    try:
        return Decimal(str(value if value is not None else 0))
    except Exception:  # noqa: BLE001
        return _ZERO


def _num(value: Any) -> Any:
    """A JSON number: an integer when whole, else a float."""
    d = _dec(value)
    return int(d) if d == d.to_integral() else float(d)


def _plain(value: Any) -> str:
    return format(_dec(value).normalize(), "f")


def _price(value: Any) -> str:
    return str(_dec(value).quantize(Decimal("0.01")))


def _today() -> str:
    return datetime.now(_MYT).date().isoformat()


def _iso_date(value: Any) -> Optional[str]:
    if not value:
        return None
    return str(value)[:10]


def _since(stored: Optional[str]) -> str:
    """The stored last-modified as dd/mm/yyyy (the date part, as AutoCount wrote it)."""
    text = (stored or "")[:10]
    try:
        return datetime.strptime(text, "%Y-%m-%d").strftime("%d/%m/%Y")
    except ValueError:
        return text or "the last read"


def _trim_sentence(message: Optional[str]) -> str:
    return (message or "").strip().rstrip(".").strip()


# ------------------------------------------------------------------ quotation lines (R6)


@dataclass
class QuotationLinesPayload:
    lines: List[dict] = field(default_factory=list)
    skipped: List[dict] = field(default_factory=list)
    exploded: List[dict] = field(default_factory=list)


def build_quotation_lines(lines: Iterable[Any], *, location: str) -> QuotationLinesPayload:
    """The AutoCount lines for a quotation revision's priced lines (owner ruling R6).

    A rate-only line is not sent and is named; a product set goes as its components at part
    qty x set qty, the driver at the set's rate and the others at zero (as the SO draft splits
    a set), so the set's money is counted once. Pure: lines in, payload out.
    """
    out = QuotationLinesPayload()
    for line in sorted(lines, key=lambda l: (l.sort_order or 0)):
        if getattr(line, "is_rate_only", False):
            out.skipped.append(
                {"code": line.product_code_snapshot, "description": line.description_snapshot}
            )
            continue
        qty = _dec(line.quantity)
        if line.set_parts_snapshot:
            components = []
            for part in line.set_parts_snapshot:
                part_qty = _dec(part.get("quantity") if part.get("quantity") is not None else 1) * qty
                out.lines.append(
                    {
                        "itemCode": part["product_code"],
                        "description": part.get("description"),
                        "uom": part.get("uom") or line.uom,
                        "qty": part_qty,
                        "unitPrice": _dec(line.unit_price) if part.get("is_driver") else _ZERO,
                        "location": location,
                    }
                )
                components.append({"code": part["product_code"], "qty": part_qty})
            out.exploded.append({"code": line.product_code_snapshot, "components": components})
            continue
        out.lines.append(
            {
                "itemCode": line.product_code_snapshot,
                "description": line.description_snapshot,
                "uom": line.uom,
                "qty": qty,
                "unitPrice": _dec(line.unit_price),
                "location": location,
            }
        )
    return out


def _wire_line(line: dict) -> dict:
    """A built line as the gateway reads it (numbers, not Decimals)."""
    out = dict(line)
    out["qty"] = _num(line["qty"])
    out["unitPrice"] = _num(line["unitPrice"])
    return out


# ------------------------------------------------------------------ the service


class ProjectAutocountWriteService:
    def __init__(self, db: Session, client: Optional[FoundryxAutocountClient] = None):
        self.db = db
        self._client = client
        self._draft = ProjectSODraftService(db)

    # ------------------------------------------------------------ gateway

    def _gateway(self) -> FoundryxAutocountClient:
        if self._client is None:
            self._client = FoundryxAutocountClient(self.db)
        return self._client

    def _call(self, fn) -> Dict[str, Any]:
        """Run one gateway call; a gateway failure becomes an answer the dialog can show."""
        try:
            return fn(self._gateway())
        except FoundryxPullError as exc:
            return {"outcome": "gateway_error", "errorCode": exc.code, "message": exc.message}

    def company_code(self, company_id: Optional[str]) -> str:
        company = self.db.query(Company).filter(Company.id == company_id).first() if company_id else None
        return company.code if company is not None else ""

    def capabilities(self, company_id: Optional[str]) -> Dict[str, Dict[str, Dict[str, Any]]]:
        """Each op enabled or not, with the plain reason, read from SS now (never hard-coded)."""
        try:
            body = self._gateway().write_capabilities(self.company_code(company_id))
        except FoundryxPullError as exc:
            reason = UNREACHABLE if exc.code == "UNREACHABLE" else exc.message
            return {
                group: {op: {"enabled": False, "reason": reason} for op in OPS} for group in _KINDS
            }
        entries = {
            (e.get("kind"), e.get("op")): e
            for e in (body.get("capabilities") or [])
            if isinstance(e, dict)
        }
        out: Dict[str, Dict[str, Dict[str, Any]]] = {}
        for group, kind in _KINDS.items():
            ops = {}
            for op in OPS:
                entry = entries.get((kind, op))
                if entry is not None and entry.get("enabled") is True:
                    ops[op] = {"enabled": True, "reason": None}
                else:
                    ops[op] = {
                        "enabled": False,
                        "reason": _REASONS.get((entry or {}).get("reasonCode"), WAITING),
                    }
            out[group] = ops
        return out

    # ------------------------------------------------------------ answers

    def _blank(self, outcome: str, message: str, doc_no: Optional[str] = None) -> Dict[str, Any]:
        return {
            "outcome": outcome,
            "message": message,
            "doc_no": doc_no,
            "lines": [],
            "warnings": [],
            "skipped": [],
            "exploded": [],
            "waiting": [],
        }

    @staticmethod
    def _read_back(document: Optional[dict]) -> List[dict]:
        out = []
        for index, d in enumerate((document or {}).get("Details") or [], start=1):
            out.append(
                {
                    "line_no": d.get("Seq") or index,
                    "item_code": d.get("ItemCode"),
                    "description": d.get("Description"),
                    "qty": _plain(d.get("Qty")),
                    "unit_price": _price(d.get("UnitPrice")),
                    "location": d.get("Location"),
                    "delivery_date": _iso_date(d.get("DeliveryDate")),
                }
            )
        return out

    def _interpret(
        self, answer: Dict[str, Any], *, verb: str, stale_since: Optional[str] = None
    ) -> Dict[str, Any]:
        """One SS answer in the plan's plain words. `done` carries the read-back lines."""
        outcome = answer.get("outcome")
        code = answer.get("errorCode")
        document = answer.get("document") or {}
        doc_no = answer.get("docNo") or document.get("DocNo")
        if outcome in _DONE:
            result = self._blank("done", f"{doc_no} {verb} in AutoCount", doc_no)
            result["lines"] = self._read_back(document)
            result["warnings"] = list(answer.get("warnings") or [])
            return result
        if outcome == "pending_verification":
            return self._blank("pending_verification", PENDING)
        if outcome == "gateway_error":
            if code == "UNREACHABLE":
                return self._blank("unreachable", UNREACHABLE)
            return self._blank(
                "refused",
                f"AutoCount refused: {_trim_sentence(answer.get('message'))}. Nothing was changed.",
            )
        if code in ("WRITE_DISABLED", "WRITE_NOT_ALLOWED", "WRITE_COMPANY_NOT_TEST"):
            return self._blank("refused", SWITCHED_OFF_HERE)
        if code == "DOC_STALE":
            return self._blank(
                "refused", f"Changed in AutoCount since {_since(stale_since)}, open Compare first."
            )
        if outcome == "refused" or outcome is None:
            return self._blank(
                "refused",
                f"AutoCount refused: {_trim_sentence(answer.get('message'))}. Nothing was changed.",
            )
        # mismatch and anything else SS may add: shown as AutoCount's answer, never as done.
        return self._blank(
            str(outcome),
            f"AutoCount answered: {_trim_sentence(answer.get('message')) or str(outcome)}.",
        )

    @staticmethod
    def _is_done(answer: Dict[str, Any]) -> bool:
        return answer.get("outcome") in _DONE

    @staticmethod
    def _key_of(answer: Dict[str, Any]) -> Optional[str]:
        document = answer.get("document") or {}
        key = answer.get("docKey") if answer.get("docKey") is not None else document.get("DocKey")
        return str(key) if key is not None else None

    # ------------------------------------------------------------ shared checks

    @staticmethod
    def _debtor_code(customer: Optional[Customer]) -> str:
        code = ((customer.customer_code if customer is not None else None) or "").strip()
        if not code:
            name = (customer.customer_name if customer is not None else None) or "the customer"
            raise AppException(
                status_code=422, message=f"No debtor code on {name}.", code="ac_missing_debtor"
            )
        return code

    @staticmethod
    def _agent_code(customer: Optional[Customer]) -> Optional[str]:
        agent = customer.sales_agent if customer is not None else None
        return agent.sales_agent if agent is not None else None

    def _po(self, order: ProjectSalesOrder) -> Optional[ProjectPurchaseOrder]:
        if not order.purchase_order_id:
            return None
        return (
            self.db.query(ProjectPurchaseOrder)
            .filter(ProjectPurchaseOrder.id == order.purchase_order_id)
            .first()
        )

    def _order_lines(self, order: ProjectSalesOrder) -> List[ProjectSalesOrderLine]:
        return (
            self.db.query(ProjectSalesOrderLine)
            .filter(ProjectSalesOrderLine.project_sales_order_id == order.id)
            .order_by(ProjectSalesOrderLine.line_no.asc())
            .all()
        )

    def _dtl_key(self, line: Optional[ProjectSalesOrderLine]) -> Optional[int]:
        """The AutoCount DtlKey of a project line: the last `:` segment of its core line's ref."""
        if line is None or not line.core_sales_order_line_id:
            return None
        ref = (
            self.db.query(SalesOrderLine.source_ref)
            .filter(SalesOrderLine.id == line.core_sales_order_line_id)
            .scalar()
        )
        try:
            return int((ref or "").strip().split(":")[-1])
        except ValueError:
            return None

    def _order_company_code(self, order: ProjectSalesOrder) -> str:
        return self.company_code(order.company_id)

    # ------------------------------------------------------------ sales order: create

    def build_sales_order_body(self, order: ProjectSalesOrder) -> Dict[str, Any]:
        """`{companyCode, header{...}, lines[...]}` from the order CS is looking at (U6, U7)."""
        project = self.db.query(Project).filter(Project.id == order.project_id).first()
        po = self._po(order)
        customer = self._draft._customer_for(order)
        debtor = self._debtor_code(customer)
        lines = self._order_lines(order)
        codes = self._draft._product_codes(line.product_id for line in lines)
        derived, _why = self._draft.derived_stock_location(order)
        wire = []
        for line in lines:
            location = (line.stock_location or "").strip() or derived
            if not location:
                raise AppException(
                    status_code=422,
                    message=f"No location on line {line.line_no}.",
                    code="ac_missing_location",
                )
            code = codes.get(line.product_id)
            if not code:
                raise AppException(
                    status_code=422,
                    message=f"Line {line.line_no} has no item code.",
                    code="ac_missing_item",
                )
            wire.append(
                {
                    "itemCode": code,
                    "description": line.description,
                    "uom": line.uom,
                    "qty": _num(line.qty),
                    "unitPrice": _num(line.unit_price),
                    "location": location,
                    "deliveryDate": line.delivery_date.isoformat() if line.delivery_date else None,
                }
            )
        header: Dict[str, Any] = {
            "debtorCode": debtor,
            "docDate": _today(),
            "currencyCode": "MYR",
            "currencyRate": 1,
            "ref": project.title if project is not None else None,
            "remark1": order.provisional_ref,
        }
        if po is not None and po.po_number:
            header["yourPONo"] = po.po_number
        if po is not None and po.term_days:
            header["displayTerm"] = f"Net {po.term_days} days"
        agent = self._agent_code(customer)
        if agent:
            header["salesAgent"] = agent
        return {
            "companyCode": self._order_company_code(order),
            "header": header,
            "lines": wire,
        }

    def create_sales_order(self, pso_id: str, actor: Optional[dict] = None) -> Dict[str, Any]:
        order = self._draft.get_order(pso_id)
        if order.autocount_doc_no or order.autocount_doc_key:
            raise AppException(
                status_code=409,
                message=f"{order.provisional_ref} is already in AutoCount.",
                code="ac_already_in_autocount",
            )
        if order.status not in (SO_STATUS_PUBLISHED, SO_STATUS_AMENDED):
            raise AppException(
                status_code=409,
                message=f"{order.provisional_ref} is not published yet.",
                code="ac_not_published",
            )
        if not self._draft.can_export(order):
            raise AppException(
                status_code=409,
                message=(
                    f"{order.provisional_ref} still carries an unacknowledged hard finding. "
                    "Clear it with a reason before it goes to AutoCount."
                ),
                code="so_export_blocked",
            )
        body = self.build_sales_order_body(order)
        answer = self._call(
            lambda c: c.write(
                "documents/sales-orders", body, idempotency_key=f"crm-pso-{order.id}-create"
            )
        )
        result = self._interpret(answer, verb="created")
        if self._is_done(answer):
            document = answer.get("document") or {}
            order.autocount_doc_no = result["doc_no"]
            order.autocount_doc_key = self._key_of(answer)
            order.autocount_last_modified = document.get("LastModified")
            self.db.flush()
        return result

    # ------------------------------------------------------------ sales order: update

    def update_sales_order(self, amendment_id: str, actor: Optional[dict] = None) -> Dict[str, Any]:
        amendment = self.db.query(SOAmendment).filter(SOAmendment.id == amendment_id).first()
        if amendment is None:
            raise AppException(
                status_code=404, message="Amendment not found.", code="amendment_not_found"
            )
        order = self._draft.get_order(amendment.project_sales_order_id)
        if amendment.status != AMENDMENT_PUBLISHED:
            raise AppException(
                status_code=409,
                message="Only a published amendment goes to AutoCount.",
                code="ac_amendment_not_published",
            )
        if not order.autocount_doc_key:
            raise AppException(
                status_code=409,
                message=f"{order.provisional_ref} is not in AutoCount yet.",
                code="ac_not_in_autocount",
            )
        accepted, _declined = ProjectSODeltaService(self.db)._decided_rows(
            amendment, amendment.delta_json or {}
        )
        caps = self.capabilities(order.company_id)["sales_orders"]

        edits: Dict[int, Dict[str, Any]] = {}
        adds: List[dict] = []
        waiting: List[dict] = []
        derived: Optional[str] = None
        for row in accepted:
            verb = str(row.get("verb") or "")
            blocked = self._row_blocked(verb, caps)
            line = (
                self.db.query(ProjectSalesOrderLine)
                .filter(ProjectSalesOrderLine.id == row.get("so_line_id"))
                .first()
                if row.get("so_line_id")
                else None
            )
            if blocked is not None:
                waiting.append(self._waiting(row, blocked))
                continue
            if verb == VERB_ADD_LINE:
                if derived is None:
                    derived = self._draft.derived_stock_location(order)[0] or ""
                location = (row.get("stock_location") or "").strip() or derived
                if not location:
                    raise AppException(
                        status_code=422,
                        message=f"No location on line {row.get('line_no')}.",
                        code="ac_missing_location",
                    )
                adds.append(
                    {
                        "itemCode": row.get("product_code"),
                        "description": row.get("description"),
                        "uom": row.get("uom"),
                        "qty": _num(row.get("to_value")),
                        "unitPrice": _num(row.get("unit_price")),
                        "location": location,
                        "deliveryDate": _iso_date(row.get("delivery_date")),
                    }
                )
                continue
            dtl = self._dtl_key(line)
            if dtl is None:
                waiting.append(self._waiting(row, WAITING))
                continue
            entry = edits.setdefault(dtl, {"dtlKey": dtl})
            if verb == VERB_QTY_CHANGE:
                entry["qty"] = _num(row.get("to_value"))
            else:
                entry["deliveryDate"] = _iso_date(row.get("to_value"))

        result = self._blank("waiting", WAITING)
        result["doc_no"] = order.autocount_doc_no
        result["waiting"] = waiting
        if not edits and not adds:
            return result

        company = self._order_company_code(order)
        base_key = f"crm-amd-{amendment.id}-update"
        last_answer: Optional[Dict[str, Any]] = None
        expected = order.autocount_last_modified
        stale_since = order.autocount_last_modified
        if edits:
            body = {
                "companyCode": company,
                "header": {"docDate": _today()},
                "expectedLastModified": expected,
                "lines": list(edits.values()),
            }
            path = f"documents/sales-orders/{order.autocount_doc_key}"
            answer = self._call(lambda c: c.patch(path, body, idempotency_key=base_key))
            if not self._is_done(answer):
                refused = self._interpret(answer, verb="updated", stale_since=stale_since)
                refused["waiting"] = waiting
                return refused
            last_answer = answer
            expected = (answer.get("document") or {}).get("LastModified") or expected
        if adds:
            body = {"companyCode": company, "expectedLastModified": expected, "lines": adds}
            path = f"documents/sales-orders/{order.autocount_doc_key}/lines"
            answer = self._call(
                lambda c: c.write(path, body, idempotency_key=f"{base_key}-lines")
            )
            if not self._is_done(answer):
                refused = self._interpret(answer, verb="updated", stale_since=stale_since)
                if last_answer is not None:
                    # The edits already reached AutoCount: keep our stale guard in step.
                    order.autocount_last_modified = expected
                    self.db.flush()
                    refused["message"] += " The quantity and date changes were made."
                refused["waiting"] = waiting
                return refused
            last_answer = answer
        final = self._interpret(last_answer or {}, verb="updated")
        final["doc_no"] = final["doc_no"] or order.autocount_doc_no
        final["message"] = f"{final['doc_no']} updated in AutoCount"
        final["waiting"] = waiting
        order.autocount_last_modified = (
            (last_answer.get("document") or {}).get("LastModified") or order.autocount_last_modified
        )
        self.db.flush()
        return final

    @staticmethod
    def _row_blocked(verb: str, caps: Dict[str, Dict[str, Any]]) -> Optional[str]:
        """Why this amendment row cannot go now, else None.

        Quantity and date moves need `edit_doc`, an added line `add_line`. Every other verb
        (remove, balance cancel, repoint, model change) needs the delete / cancel door, which
        is built only when SS ships it: until then it waits, whatever the feed says.
        """
        if verb in (VERB_QTY_CHANGE, VERB_ADVANCE, VERB_DELAY):
            op = caps["edit_doc"]
        elif verb == VERB_ADD_LINE:
            op = caps["add_line"]
        else:
            return WAITING
        return None if op["enabled"] else op["reason"]

    @staticmethod
    def _waiting(row: dict, reason: str) -> dict:
        return {
            "verb": row.get("verb"),
            "line_no": row.get("line_no"),
            "item_code": row.get("product_code"),
            "reason": reason,
        }

    # ------------------------------------------------------------ sales order: cancel

    def cancel_sales_order(self, pso_id: str, actor: Optional[dict] = None) -> Dict[str, Any]:
        order = self._draft.get_order(pso_id)
        if not order.autocount_doc_key:
            raise AppException(
                status_code=409,
                message=f"{order.provisional_ref} is not in AutoCount.",
                code="ac_not_in_autocount",
            )
        cap = self.capabilities(order.company_id)["sales_orders"]["cancel_doc"]
        if not cap["enabled"]:
            raise AppException(status_code=409, message=cap["reason"] or WAITING, code="ac_waiting")
        body = {"companyCode": self._order_company_code(order)}
        path = f"documents/sales-orders/{order.autocount_doc_key}/cancel"
        answer = self._call(
            lambda c: c.write(path, body, idempotency_key=f"crm-pso-{order.id}-cancel")
        )
        result = self._interpret(answer, verb="cancelled")
        if self._is_done(answer):
            result["doc_no"] = result["doc_no"] or order.autocount_doc_no
            result["message"] = f"{result['doc_no']} cancelled in AutoCount"
            order.autocount_last_modified = (
                (answer.get("document") or {}).get("LastModified") or order.autocount_last_modified
            )
            self.db.flush()
        return result

    # ------------------------------------------------------------ quotation

    def _document(self, document_id: str) -> ProjectQuotationDocument:
        document = (
            self.db.query(ProjectQuotationDocument)
            .filter(ProjectQuotationDocument.id == document_id)
            .first()
        )
        if document is None:
            raise AppException(
                status_code=404, message="Quotation not found.", code="quotation_document_not_found"
            )
        return document

    def _latest_issue(self, document: ProjectQuotationDocument) -> Optional[ProjectQuotationIssue]:
        return (
            self.db.query(ProjectQuotationIssue)
            .filter(ProjectQuotationIssue.document_id == document.id)
            .order_by(ProjectQuotationIssue.issue_no.desc())
            .first()
        )

    def _recipient(self, document: ProjectQuotationDocument) -> Optional[Customer]:
        if not document.recipient_party_id:
            return None
        party = (
            self.db.query(ProjectParty).filter(ProjectParty.id == document.recipient_party_id).first()
        )
        if party is None or not party.customer_id:
            return None
        return self.db.query(Customer).filter(Customer.id == party.customer_id).first()

    def _issue_lines(self, issue: ProjectQuotationIssue, *, location: str) -> QuotationLinesPayload:
        scopes = (
            self.db.query(ProjectQuotationIssueScope)
            .filter(ProjectQuotationIssueScope.issue_id == issue.id)
            .order_by(ProjectQuotationIssueScope.sort_order.asc())
            .all()
        )
        merged = QuotationLinesPayload()
        for scope in scopes:
            lines = (
                self.db.query(ProjectQuotationLine)
                .filter(ProjectQuotationLine.version_id == scope.version_id)
                .all()
            )
            part = build_quotation_lines(lines, location=location)
            merged.lines += part.lines
            merged.skipped += part.skipped
            merged.exploded += part.exploded
        return merged

    def send_quotation(self, document_id: str, actor: Optional[dict] = None) -> Dict[str, Any]:
        """Create when the document has no AutoCount key, else update (R5: accepted issues only)."""
        document = self._document(document_id)
        issue = self._latest_issue(document)
        if document.kind != "quotation" or issue is None or issue.accepted_at is None:
            raise AppException(status_code=409, message=NOT_ACCEPTED, code="ac_not_accepted")
        if document.autocount_doc_key and document.autocount_issue_id == issue.id:
            raise AppException(status_code=409, message=ALREADY, code="ac_already_sent")

        customer = self._recipient(document)
        debtor = self._debtor_code(customer)
        location, why = (
            self._draft.derived_location_for_customer(customer)
            if customer is not None
            else (None, "The recipient has no customer.")
        )
        if not location:
            raise AppException(
                status_code=422, message=f"No location for the quotation lines. {why}", code="ac_missing_location"
            )
        payload = self._issue_lines(issue, location=location)
        if not payload.lines:
            raise AppException(
                status_code=422, message="There are no lines to send.", code="ac_no_lines"
            )
        project = self.db.query(Project).filter(Project.id == document.project_id).first()
        company = self.company_code(document.company_id)
        remark = f"{document.document_no} (R{issue.issue_no})"
        if not document.autocount_doc_key:
            return self._create_quotation(document, issue, payload, customer, debtor, project, company, remark)
        return self._update_quotation(document, issue, payload, company, remark)

    def _create_quotation(self, document, issue, payload, customer, debtor, project, company, remark):
        header: Dict[str, Any] = {
            "debtorCode": debtor,
            "docDate": _today(),
            "currencyCode": "MYR",
            "currencyRate": 1,
            "ref": project.title if project is not None else None,
            "remark1": remark,
        }
        if document.your_ref:
            header["yourPONo"] = document.your_ref
        agent = self._agent_code(customer)
        if agent:
            header["salesAgent"] = agent
        body = {
            "companyCode": company,
            "header": header,
            "lines": [_wire_line(l) for l in payload.lines],
        }
        answer = self._call(
            lambda c: c.write(
                "documents/quotations",
                body,
                idempotency_key=f"crm-qt-{document.id}-{issue.id}-create",
            )
        )
        result = self._interpret(answer, verb="created")
        if self._is_done(answer):
            self._store_sent(document, issue, answer)
            result["skipped"] = payload.skipped
            result["exploded"] = payload.exploded
        return result

    def _store_sent(self, document, issue, answer: Dict[str, Any]) -> None:
        document.autocount_doc_no = answer.get("docNo") or (answer.get("document") or {}).get("DocNo") or document.autocount_doc_no
        document.autocount_doc_key = self._key_of(answer) or document.autocount_doc_key
        document.autocount_last_modified = (answer.get("document") or {}).get("LastModified")
        document.autocount_issue_id = issue.id
        self.db.flush()

    def _update_quotation(self, document, issue, payload, company, remark):
        """Match the revision's lines to what AutoCount holds, by item code in order (Q8)."""
        key = document.autocount_doc_key
        try:
            held_doc = self._gateway().read_document("quotations", key, company)
        except FoundryxPullError as exc:
            return self._interpret(
                {"outcome": "gateway_error", "errorCode": exc.code, "message": exc.message}, verb="updated"
            )
        held = list((held_doc.get("document") or held_doc).get("Details") or [])
        caps = self.capabilities(document.company_id)["quotations"]
        used: set = set()
        patched: List[dict] = []
        adds: List[dict] = []
        for line in payload.lines:
            match = next(
                (
                    i
                    for i, d in enumerate(held)
                    if i not in used and (d.get("ItemCode") or "") == line["itemCode"]
                ),
                None,
            )
            if match is None:
                adds.append(_wire_line(line))
                continue
            used.add(match)
            d = held[match]
            if _dec(d.get("Qty")) != line["qty"] or _dec(d.get("UnitPrice")) != line["unitPrice"]:
                patched.append(
                    {"dtlKey": d.get("DtlKey"), "qty": _num(line["qty"]), "unitPrice": _num(line["unitPrice"])}
                )
        waiting = [
            {
                "verb": "REMOVE_LINE",
                "line_no": d.get("Seq"),
                "item_code": d.get("ItemCode"),
                "reason": WAITING,
            }
            for i, d in enumerate(held)
            if i not in used
        ]
        stale_since = document.autocount_last_modified
        expected = stale_since
        base_key = f"crm-qt-{document.id}-{issue.id}-update"
        header = {"docDate": _today(), "remark1": remark}
        if patched and not caps["edit_doc"]["enabled"]:
            return self._blank("refused", caps["edit_doc"]["reason"] or WAITING)
        if adds and not caps["add_line"]["enabled"]:
            return self._blank("refused", caps["add_line"]["reason"] or WAITING)
        body = {"companyCode": company, "header": header, "expectedLastModified": expected}
        if patched:
            body["lines"] = patched
        answer = self._call(
            lambda c: c.patch(f"documents/quotations/{key}", body, idempotency_key=base_key)
        )
        if not self._is_done(answer):
            refused = self._interpret(answer, verb="updated", stale_since=stale_since)
            refused["waiting"] = waiting
            return refused
        last = answer
        if adds:
            expected = (answer.get("document") or {}).get("LastModified") or expected
            add_body = {"companyCode": company, "expectedLastModified": expected, "lines": adds}
            add_answer = self._call(
                lambda c: c.write(
                    f"documents/quotations/{key}/lines", add_body, idempotency_key=f"{base_key}-lines"
                )
            )
            if not self._is_done(add_answer):
                document.autocount_last_modified = expected
                self.db.flush()
                refused = self._interpret(add_answer, verb="updated", stale_since=stale_since)
                refused["waiting"] = waiting
                return refused
            last = add_answer
        result = self._interpret(last, verb="updated")
        result["doc_no"] = result["doc_no"] or document.autocount_doc_no
        result["message"] = f"{result['doc_no']} updated in AutoCount"
        result["skipped"] = payload.skipped
        result["exploded"] = payload.exploded
        result["waiting"] = waiting
        self._store_sent(document, issue, last)
        return result

    def cancel_quotation(self, document_id: str, actor: Optional[dict] = None) -> Dict[str, Any]:
        document = self._document(document_id)
        if not document.autocount_doc_key:
            raise AppException(
                status_code=409, message="This quotation is not in AutoCount.", code="ac_not_in_autocount"
            )
        cap = self.capabilities(document.company_id)["quotations"]["cancel_doc"]
        if not cap["enabled"]:
            raise AppException(status_code=409, message=cap["reason"] or WAITING, code="ac_waiting")
        body = {"companyCode": self.company_code(document.company_id)}
        path = f"documents/quotations/{document.autocount_doc_key}/cancel"
        answer = self._call(
            lambda c: c.write(path, body, idempotency_key=f"crm-qt-{document.id}-cancel")
        )
        result = self._interpret(answer, verb="cancelled")
        if self._is_done(answer):
            result["doc_no"] = result["doc_no"] or document.autocount_doc_no
            result["message"] = f"{result['doc_no']} cancelled in AutoCount"
            document.autocount_last_modified = (
                (answer.get("document") or {}).get("LastModified") or document.autocount_last_modified
            )
            self.db.flush()
        return result
