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
import re
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
    ProjectSalesOrder,
    ProjectSalesOrderLine,
    SOAmendment,
)
from app.models.product import Product, UnitOfMeasure
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
from app.services.autocount_idempotency import attempt_store, send_with_attempts
from app.services.set_driver_pricing import split_set_driver_price
from app.services.project_so_delta_service import (
    VERB_ADVANCE,
    VERB_CANCEL_BALANCE,
    VERB_DELAY,
    VERB_ORDER,
    VERB_RESERVE_AND_ORDER,
    ProjectSODeltaService,
)
from app.services.project_so_draft_service import ProjectSODraftService

logger = logging.getLogger(__name__)

_MYT = ZoneInfo("Asia/Kuala_Lumpur")
# B11: the Remark fields AutoCount fills from Remark1 by itself.
_MIRRORED_REMARK = re.compile(r"remark[2-4]", re.IGNORECASE)
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
# Only `done` is a success: a `recovered` answer means SS rolled the write back.
_DONE = ("done",)

#: Longest SS message or warning text the CRM relays to a screen.
_MAX_TEXT = 500
WAITING_SYNC = "Waiting for the next AutoCount sync"
SPLIT_ITEM = "This item is on more than one line; change it in AutoCount by hand"
ALREADY_CANCELLED = "Already cancelled in AutoCount."

#: Owner decision pending (fix round 1): does CANCEL BALANCE go to AutoCount as a quantity edit
#: down to `to_value`? Off, it waits like CHANGE SO NO. One switch, both paths are built.
_SEND_CANCEL_BALANCE_AS_QTY_EDIT = False

# SS write API v2 (SS plan 61): its codes in plain words. The code is read, never SS's own text.
DOC_HAS_TRANSFERS_TEXT = (
    "AutoCount will not cancel it: it has already been delivered or copied to another document. "
    "Nothing was changed."
)
DOC_CANCELLED_TEXT = "It is cancelled in AutoCount, so it cannot be changed. Nothing was changed."
CANCEL_IGNORED_TEXT = "AutoCount did not cancel it. Check it in AutoCount."
ROW_TRANSFERRED = "has already been delivered or copied to another document in AutoCount"
LINE_NOT_DELETED_TEXT = "AutoCount did not remove the line. Check it in AutoCount."

_QTY_VERBS = (VERB_ORDER, VERB_RESERVE_AND_ORDER)
_DATE_VERBS = (VERB_ADVANCE, VERB_DELAY)


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
    """The stored last-modified as dd/mm/yyyy in Malaysia time.

    AutoCount stamps carry no zone and are Malaysia local time (ruling V1, as
    `autocount_doc_ingest_service.MALAYSIA`); a stamp with a zone is converted."""
    text = (stored or "").strip()
    try:
        moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return text[:10] or "the last read"
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=_MYT)
    return moment.astimezone(_MYT).strftime("%d/%m/%Y")


def _trim_sentence(message: Optional[str]) -> str:
    return (message or "").strip()[:_MAX_TEXT].rstrip(".").strip()


_CODE_SHAPE = re.compile(r"[A-Z][A-Z0-9_]{0,63}")


def _refused_text(answer: Dict[str, Any]) -> str:
    """A refusal in words. Never a blank reason (AC-E2E-DB3 B14): with no message the code is
    named (only a plain UPPER_SNAKE code, never other text from SS)."""
    reason = _trim_sentence(answer.get("message"))
    if reason:
        return f"AutoCount refused: {reason}. Nothing was changed."
    code = str(answer.get("errorCode") or "")
    if _CODE_SHAPE.fullmatch(code):
        return f"AutoCount refused ({code}). Nothing was changed."
    return "AutoCount refused with no reason given. Nothing was changed."


def _safe_key(key: Any) -> str:
    """A DocKey is digits; anything else never reaches a gateway path."""
    text = str(key or "").strip()
    if not text.isdigit():
        raise AppException(
            status_code=409,
            message="The AutoCount document key is not valid.",
            code="ac_bad_doc_key",
        )
    return text


# ------------------------------------------------------------------ quotation lines (R6)


@dataclass
class QuotationLinesPayload:
    lines: List[dict] = field(default_factory=list)
    skipped: List[dict] = field(default_factory=list)
    exploded: List[dict] = field(default_factory=list)


def _base_uom_codes(db: Session, product_ids: Iterable[Any]) -> Dict[str, str]:
    """Product id -> its base UOM code (the AutoCount UOM), one query for a whole payload."""
    wanted = {pid for pid in product_ids if pid}
    if not wanted:
        return {}
    rows = (
        db.query(Product.id, UnitOfMeasure.uom_code)
        .join(UnitOfMeasure, UnitOfMeasure.id == Product.base_uom_id)
        .filter(Product.id.in_(wanted))
        .all()
    )
    return {pid: (code or "").strip() for pid, code in rows if (code or "").strip()}


def _ac_uom(line_uom: Any, product_id: Any, base_uoms: Optional[Dict[str, str]]) -> Any:
    """The product's AutoCount UOM (its base UOM code); the line's own uom only when it has none."""
    return (base_uoms or {}).get(product_id) or line_uom


def build_quotation_lines(
    lines: Iterable[Any], *, location: str, base_uoms: Optional[Dict[str, str]] = None
) -> QuotationLinesPayload:
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
                per_set = _dec(part.get("quantity") if part.get("quantity") is not None else 1)
                part_qty = per_set * qty
                uom = _ac_uom(part.get("uom") or line.uom, part.get("product_id"), base_uoms)
                if part.get("is_driver"):
                    # One shared rule with the SO draft (R6a): rows of (qty, unit price).
                    for row_qty, row_price in split_set_driver_price(
                        _dec(line.unit_price), qty, per_set
                    ):
                        out.lines.append(
                            {
                                "itemCode": part["product_code"],
                                "description": part.get("description"),
                                "uom": uom,
                                "qty": row_qty,
                                "unitPrice": row_price,
                                "location": location,
                            }
                        )
                else:
                    out.lines.append(
                        {
                            "itemCode": part["product_code"],
                            "description": part.get("description"),
                            "uom": uom,
                            "qty": part_qty,
                            "unitPrice": _ZERO,
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
                "uom": _ac_uom(line.uom, line.product_id, base_uoms),
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

    def _send_attempts(self, base_key: str, call) -> Dict[str, Any]:
        """One write under the intent's current attempt key (#2223's shared helper).

        Attempt 0 is the plain `base_key`; a definite refusal moves the next press of the same
        intent to a new key so it is not answered with the stored refusal. Anything else keeps
        the key, so a retry can only replay."""
        answer = send_with_attempts(
            attempt_store(), base_key, lambda key: self._call(lambda c: call(c, key))
        )
        if answer.get("outcome") not in _DONE:
            # One line per write that did not land, so a refusal on a live stack can be read back.
            logger.warning(
                "autocount write %s: outcome=%s errorCode=%s",
                base_key,
                str(answer.get("outcome"))[:40],
                str(answer.get("errorCode"))[:64],
            )
        return answer

    def company_code(self, company_id: Optional[str]) -> str:
        company = self.db.query(Company).filter(Company.id == company_id).first() if company_id else None
        return company.code if company is not None else ""

    def capabilities(self, company_id: Optional[str]) -> Dict[str, Dict[str, Dict[str, Any]]]:
        """Each op enabled or not, with the plain reason, read from SS now (never hard-coded)."""
        return self.read_capabilities(company_id)[0]

    def read_capabilities(self, company_id: Optional[str]):
        """(ops by group, the book SS names or None). One read per service instance."""
        cache = self.__dict__.setdefault("_caps_cache", {})
        if company_id not in cache:
            cache[company_id] = self._read_capabilities(company_id)
        return cache[company_id]

    def _read_capabilities(self, company_id: Optional[str]):
        try:
            body = self._gateway().write_capabilities(self.company_code(company_id))
        except FoundryxPullError as exc:
            reason = UNREACHABLE if exc.code == "UNREACHABLE" else (exc.message or "")[:_MAX_TEXT]
            return (
                {group: {op: {"enabled": False, "reason": reason} for op in OPS} for group in _KINDS},
                None,
            )
        book = body.get("book")
        book = book.strip() if isinstance(book, str) and book.strip() else None
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
        return out, book

    @staticmethod
    def _require_book(own: Optional[str], named: Optional[str]) -> None:
        """Owner ruling R8: every Update / Cancel waits unless the record's stored (or, for an
        adopted order, derived) book equals the book SS names now. NULL on either side waits."""
        if not own or not named or own.strip().lower() != named.strip().lower():
            raise AppException(status_code=409, message=WAITING, code="ac_waiting")

    def _no_book_answer(self, company_id: Optional[str]) -> Dict[str, Any]:
        """Owner ruling R9: no AutoCount write of any kind, create included, without a book.

        A gateway that cannot be reached is told as such (the screen shows it); one that answers
        without a book makes the action wait (409)."""
        caps = self.read_capabilities(company_id)[0]
        if caps["sales_orders"]["create_doc"]["reason"] == UNREACHABLE:
            return self._blank("unreachable", UNREACHABLE)
        raise AppException(status_code=409, message=WAITING, code="ac_waiting")

    def _order_book(self, order: ProjectSalesOrder) -> Optional[str]:
        """The book an order's key belongs to: stored at create, else the adopted source_ref's."""
        if order.autocount_doc_key:
            return order.autocount_book
        return self._draft.autocount_key_info(order)[1]

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

    @staticmethod
    def _warning(item: Any) -> Any:
        if isinstance(item, dict):
            return {
                k: (v[:_MAX_TEXT] if isinstance(v, str) else v) for k, v in item.items()
            }
        return str(item)[:_MAX_TEXT]

    def _interpret(
        self,
        answer: Dict[str, Any],
        *,
        verb: str,
        stale_since: Optional[str] = None,
        debtor: Optional[str] = None,
    ) -> Dict[str, Any]:
        """One SS answer in the plan's plain words. `done` carries the read-back lines."""
        outcome = answer.get("outcome")
        code = answer.get("errorCode")
        document = answer.get("document") or {}
        doc_no = answer.get("docNo") or document.get("DocNo")
        if outcome in _DONE:
            result = self._blank("done", f"{doc_no} {verb} in AutoCount", doc_no)
            result["lines"] = self._read_back(document)
            result["warnings"] = [self._warning(w) for w in (answer.get("warnings") or [])]
            return result
        if outcome == "pending_verification":
            return self._blank("pending_verification", PENDING)
        if outcome == "gateway_error":
            if code == "UNREACHABLE":
                return self._blank("unreachable", UNREACHABLE)
            return self._blank("refused", _refused_text(answer))
        if code in ("WRITE_DISABLED", "WRITE_NOT_ALLOWED", "WRITE_COMPANY_NOT_TEST"):
            return self._blank("refused", SWITCHED_OFF_HERE)
        if debtor and (
            code == "DEBTOR_TERM_MISSING"
            or (code == "FIELD_REQUIRED" and "displayTerm" in str(answer.get("message") or ""))
        ):
            # Our own debtor code (from the body we sent), never text taken from SS.
            return self._blank(
                "refused",
                f"AutoCount needs a credit term on debtor {debtor}. Set it in AutoCount and try again.",
            )
        if code == "DOC_STALE":
            return self._blank(
                "refused",
                f"Changed in AutoCount since {_since(stale_since)}. Nothing was changed; "
                "check it in AutoCount, then press Update again.",
            )
        if code == "DOC_HAS_TRANSFERS":
            return self._blank("refused", DOC_HAS_TRANSFERS_TEXT)
        if code == "DOC_CANCELLED":
            return self._blank("refused", DOC_CANCELLED_TEXT)
        if code == "ROW_HAS_TRANSFERS":
            return self._blank(
                "refused", f"A line {ROW_TRANSFERRED}, so it cannot be removed. Nothing was changed."
            )
        if code == "CANCEL_IGNORED":
            return self._blank(str(outcome or "mismatch"), CANCEL_IGNORED_TEXT)
        if code == "LINE_NOT_DELETED":
            return self._blank(str(outcome or "mismatch"), LINE_NOT_DELETED_TEXT)
        if outcome == "refused" or outcome is None:
            return self._blank("refused", _refused_text(answer))
        # mismatch and anything else SS may add: shown as AutoCount's answer, never as done.
        return self._blank(
            str(outcome),
            f"AutoCount answered: {_trim_sentence(answer.get('message')) or str(outcome)}.",
        )

    @staticmethod
    def _is_stale(answer: Dict[str, Any]) -> bool:
        return answer.get("outcome") == "refused" and answer.get("errorCode") == "DOC_STALE"

    @staticmethod
    def _held_last_modified(held: Optional[dict]) -> Optional[str]:
        stamp = ((held or {}).get("document") or held or {}).get("LastModified")
        return str(stamp)[:64] if stamp else None

    @staticmethod
    def _done_if_only_mirrored_remarks_ignored(answer: Dict[str, Any]) -> Dict[str, Any]:
        """B11: AutoCount copies Remark1 into Remark2-4 itself, so SS answers `mismatch`
        FIELD_IGNORED "ignored: Remark2, Remark3, Remark4" on an update that landed. Only that
        measured case counts as done: the message must start with "ignored:" and every name must
        be Remark2-4. Any other name (a line field, DocDate, a path form) stays a mismatch."""
        if answer.get("outcome") != "mismatch" or answer.get("errorCode") != "FIELD_IGNORED":
            return answer
        message = str(answer.get("message") or "").strip()
        if not message.lower().startswith("ignored:"):
            return answer
        names = [n.strip().rstrip(".").strip() for n in message[len("ignored:"):].split(",")]
        if not names or not all(_MIRRORED_REMARK.fullmatch(n) for n in names):
            return answer
        return {**answer, "outcome": "done", "errorCode": None}

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
        base_uoms = _base_uom_codes(self.db, (line.product_id for line in lines))
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
                    "uom": _ac_uom(line.uom, line.product_id, base_uoms),
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
        # No displayTerm (owner, round 5): SS fills the term from the debtor's AutoCount record.
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
        if order.autocount_doc_no or self._draft.autocount_doc_key(order):
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
        # The book SS names at write time is the book the document lands in (R8).
        book = self.read_capabilities(order.company_id)[1]
        if not book:
            return self._no_book_answer(order.company_id)
        answer = self._send_attempts(
            f"crm-pso-{order.id}-create",
            lambda c, key: c.write("documents/sales-orders", body, idempotency_key=key),
        )
        result = self._interpret(answer, verb="created", debtor=body["header"]["debtorCode"])
        if self._is_done(answer):
            document = answer.get("document") or {}
            order.autocount_doc_no = result["doc_no"]
            order.autocount_doc_key = self._key_of(answer)
            order.autocount_book = book
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
        doc_key, _own_book, adopted = self._draft.autocount_key_info(order)
        if not doc_key:
            raise AppException(
                status_code=409,
                message=f"{order.provisional_ref} is not in AutoCount yet.",
                code="ac_not_in_autocount",
            )
        doc_key = _safe_key(doc_key)
        accepted, _declined = ProjectSODeltaService(self.db)._decided_rows(
            amendment, amendment.delta_json or {}
        )

        # Classify first (no gateway): what is sent, and what waits.
        _flags, edits, edit_rows, waiting = self._classify(order, accepted)

        result = self._blank("waiting", WAITING, order.autocount_doc_no)
        result["waiting"] = waiting
        if not edits:
            return result
        if amendment.autocount_edit_sent_at is not None:
            # Sent in full already: a second press replays nothing.
            done = self._blank("done", ALREADY, order.autocount_doc_no)
            done["waiting"] = waiting
            return done

        # R8: nothing is written unless SS names the book this order's key belongs to.
        self._require_book(self._order_book(order), self.read_capabilities(order.company_id)[1])
        caps = self.capabilities(order.company_id)["sales_orders"]
        if not caps["edit_doc"]["enabled"]:
            reason = caps["edit_doc"]["reason"] or WAITING
            result["waiting"] = waiting + [self._waiting(row, reason) for row in edit_rows]
            return result

        company = self._order_company_code(order)
        expected = order.autocount_last_modified
        doc_date = None
        if not expected:
            # Adopted order: nothing read back yet, so read the document before the PATCH.
            try:
                held = self._gateway().read_document("sales-orders", doc_key, company)
            except FoundryxPullError as exc:
                failed = self._interpret(
                    {"outcome": "gateway_error", "errorCode": exc.code, "message": exc.message},
                    verb="updated",
                )
                failed["waiting"] = waiting
                return failed
            expected = (held.get("document") or held).get("LastModified")
            doc_date = _iso_date((held.get("document") or held).get("DocDate"))
        body = {
            "companyCode": company,
            "expectedLastModified": expected,
            "lines": list(edits.values()),
        }
        if doc_date:
            # SS finds the document by its own date; with none, it uses the date it staged.
            body["docDate"] = doc_date
        path = f"documents/sales-orders/{doc_key}"
        answer = self._send_attempts(
            f"crm-amd-{amendment.id}-update-edit",
            lambda c, key: c.patch(path, body, idempotency_key=key),
        )
        if not self._is_done(answer):
            refused = self._interpret(answer, verb="updated", stale_since=expected)
            refused["waiting"] = waiting
            if self._is_stale(answer):
                # B10: keep AutoCount's own stamp, so the next press (after a person checked
                # AutoCount) is not refused for good. A failed read keeps the old one.
                try:
                    held = self._gateway().read_document("sales-orders", doc_key, company)
                except FoundryxPullError:
                    held = None
                stamp = self._held_last_modified(held)
                if stamp:
                    order.autocount_last_modified = stamp
                    self.db.flush()
            return refused
        final = self._interpret(answer, verb="updated")
        final["doc_no"] = final["doc_no"] or order.autocount_doc_no
        final["message"] = f"{final['doc_no']} updated in AutoCount"
        final["waiting"] = waiting
        if not order.autocount_doc_key:
            # An adopted order's first done update: keep its key and the book it came from.
            order.autocount_book = _own_book
        order.autocount_doc_key = order.autocount_doc_key or doc_key
        order.autocount_last_modified = (answer.get("document") or {}).get("LastModified") or expected
        amendment.autocount_edit_sent_at = datetime.utcnow()
        self.db.flush()
        return final

    def sendable_flags(self, order: ProjectSalesOrder, accepted: List[dict]) -> List[bool]:
        """Per accepted row: will Update in AutoCount send it? (the change list shows this)"""
        return self._classify(order, accepted)[0]

    def _classify(self, order: ProjectSalesOrder, accepted: List[dict]):
        """Split an amendment's accepted rows into the PATCH edits and the rows that wait.

        Returns (per-row sendable flags, edits by dtlKey, the rows that ride the PATCH, waiting).
        A quantity row for an item that sits on more than one line waits: AutoCount's lines
        cannot be told apart from the row, so a person changes it by hand. Date rows act per
        line and still go.
        """
        lines_of_product: Dict[Any, int] = {}
        for line in self._order_lines(order):
            lines_of_product[line.product_id] = lines_of_product.get(line.product_id, 0) + 1
        flags: List[bool] = []
        edits: Dict[int, Dict[str, Any]] = {}
        edit_rows: List[dict] = []
        waiting: List[dict] = []
        for row in accepted:
            verb = str(row.get("verb") or "")
            as_qty = verb in _QTY_VERBS or (
                verb == VERB_CANCEL_BALANCE and _SEND_CANCEL_BALANCE_AS_QTY_EDIT
            )
            if not (as_qty or verb in _DATE_VERBS):
                waiting.append(self._waiting(row, WAITING))
                flags.append(False)
                continue
            if as_qty and lines_of_product.get(row.get("product_id"), 0) > 1:
                waiting.append(self._waiting(row, SPLIT_ITEM))
                flags.append(False)
                continue
            line = (
                self.db.query(ProjectSalesOrderLine)
                .filter(ProjectSalesOrderLine.id == row.get("so_line_id"))
                .first()
                if row.get("so_line_id")
                else None
            )
            dtl = self._dtl_key(line)
            if dtl is None:
                waiting.append(self._waiting(row, WAITING_SYNC))
                flags.append(False)
                continue
            entry = edits.setdefault(dtl, {"dtlKey": dtl})
            if as_qty:
                entry["qty"] = _num(row.get("to_value"))
            else:
                entry["deliveryDate"] = _iso_date(row.get("to_value"))
            edit_rows.append(row)
            flags.append(True)
        return flags, edits, edit_rows, waiting

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
        doc_key, _own_book, adopted = self._draft.autocount_key_info(order)
        if not doc_key:
            raise AppException(
                status_code=409,
                message=f"{order.provisional_ref} is not in AutoCount.",
                code="ac_not_in_autocount",
            )
        if order.autocount_cancelled_at is not None:
            raise AppException(status_code=409, message=ALREADY_CANCELLED, code="ac_already_cancelled")
        doc_key = _safe_key(doc_key)
        self._require_book(self._order_book(order), self.read_capabilities(order.company_id)[1])
        cap = self.capabilities(order.company_id)["sales_orders"]["cancel_doc"]
        if not cap["enabled"]:
            raise AppException(status_code=409, message=cap["reason"] or WAITING, code="ac_waiting")
        body = {"companyCode": self._order_company_code(order)}
        path = f"documents/sales-orders/{doc_key}/cancel"
        answer = self._send_attempts(
            f"crm-pso-{order.id}-cancel",
            lambda c, key: c.write(path, body, idempotency_key=key),
        )
        return self._finish_cancel(order, answer, actor)

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
        scope_lines = [
            (
                self.db.query(ProjectQuotationLine)
                .filter(ProjectQuotationLine.version_id == scope.version_id)
                .all()
            )
            for scope in scopes
        ]
        product_ids = {
            pid
            for lines in scope_lines
            for l in lines
            for pid in [l.product_id, *[p.get("product_id") for p in (l.set_parts_snapshot or [])]]
        }
        base_uoms = _base_uom_codes(self.db, product_ids)
        for lines in scope_lines:
            part = build_quotation_lines(lines, location=location, base_uoms=base_uoms)
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
        if document.autocount_doc_key:
            _safe_key(document.autocount_doc_key)
            self._require_book(document.autocount_book, self.read_capabilities(document.company_id)[1])

        customer = self._recipient(document)
        if customer is None:
            raise AppException(
                status_code=422,
                message="This quotation has no recipient customer.",
                code="ac_missing_recipient",
            )
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
        if not payload.lines and not document.autocount_doc_key:
            # Create needs a line; an update may remove every line (owner, 10 Nov).
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
        book = self.read_capabilities(document.company_id)[1]
        if not book:
            return self._no_book_answer(document.company_id)
        answer = self._send_attempts(
            f"crm-qt-{document.id}-{issue.id}-create",
            lambda c, key: c.write("documents/quotations", body, idempotency_key=key),
        )
        result = self._interpret(answer, verb="created", debtor=debtor)
        if self._is_done(answer):
            self._store_sent(document, issue, answer)
            document.autocount_book = book
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
        """Match the revision's lines to what AutoCount holds, by item code in order (Q8).

        Three steps, each safe to retry: the PATCH (header + changed rows by DtlKey; rows left
        out are kept), marked done per issue; one add-line POST per new row (`{line}`, the
        gateway's shape; its key names the row's place in the revision); then, when the feed
        offers `delete_line` (SS v2), the removal of each row the revision no longer quotes, the
        last line included (owner, 10 Nov: no extra guards); with it off the row waits. The
        document is read on every press, so a row already added matches by item code and a row
        already removed is not in it: neither is ever sent twice.
        """
        key = _safe_key(document.autocount_doc_key)
        try:
            held_doc = self._gateway().read_document("quotations", key, company)
        except FoundryxPullError as exc:
            return self._interpret(
                {"outcome": "gateway_error", "errorCode": exc.code, "message": exc.message},
                verb="updated",
            )
        held = list((held_doc.get("document") or held_doc).get("Details") or [])
        doc_date = _iso_date((held_doc.get("document") or held_doc).get("DocDate"))
        used: set = set()
        rows: List[dict] = []
        adds: List[tuple] = []
        for place, line in enumerate(payload.lines):
            match = next(
                (
                    i
                    for i, d in enumerate(held)
                    if i not in used and (d.get("ItemCode") or "") == line["itemCode"]
                ),
                None,
            )
            if match is None:
                adds.append((place, _wire_line(line)))
                continue
            used.add(match)
            d = held[match]
            if _dec(d.get("Qty")) != line["qty"] or _dec(d.get("UnitPrice")) != line["unitPrice"]:
                rows.append(
                    {"dtlKey": d.get("DtlKey"), "qty": _num(line["qty"]), "unitPrice": _num(line["unitPrice"])}
                )
        gone = [d for i, d in enumerate(held) if i not in used]
        caps = self.capabilities(document.company_id)["quotations"]
        removing = bool(gone) and caps["delete_line"]["enabled"]
        waiting = (
            []
            if removing
            else [
                {
                    "verb": "REMOVE_LINE",
                    "line_no": d.get("Seq"),
                    "item_code": d.get("ItemCode"),
                    "reason": caps["delete_line"]["reason"] or WAITING,
                }
                for d in gone
            ]
        )
        edit_done = document.autocount_edit_issue_id == issue.id
        if document.autocount_lines_issue_id == issue.id:
            adds = []
        removed: List[dict] = []

        def finish(answer: Optional[Dict[str, Any]]) -> Dict[str, Any]:
            result = self._interpret(answer or {"outcome": "done"}, verb="updated")
            result["doc_no"] = result["doc_no"] or document.autocount_doc_no
            result["message"] = f"{result['doc_no']} updated in AutoCount"
            if removed:
                result["message"] += ". Removed: " + ", ".join(str(d.get("ItemCode") or "") for d in removed) + "."
            result["skipped"] = payload.skipped
            result["exploded"] = payload.exploded
            result["waiting"] = waiting
            if not waiting:
                # Fully matched: this issue is now what AutoCount holds. With rows waiting it
                # stays "needs update", so the screen keeps offering the rest.
                document.autocount_issue_id = issue.id
            self.db.flush()
            return result

        if edit_done and not adds and not removing:
            if waiting:
                result = self._blank("waiting", WAITING, document.autocount_doc_no)
                result["waiting"] = waiting
                result["skipped"] = payload.skipped
                result["exploded"] = payload.exploded
                return result
            return finish(None)
        if not edit_done and not caps["edit_doc"]["enabled"]:
            return self._blank("refused", caps["edit_doc"]["reason"] or WAITING)
        if adds and not caps["add_line"]["enabled"]:
            return self._blank("refused", caps["add_line"]["reason"] or WAITING)

        stale_since = document.autocount_last_modified
        base_key = f"crm-qt-{document.id}-{issue.id}-update"
        last: Optional[Dict[str, Any]] = None
        if not edit_done:
            body = {
                "companyCode": company,
                "header": {"remark1": remark},
                "expectedLastModified": stale_since,
            }
            if doc_date:
                body["docDate"] = doc_date
            if rows:
                body["lines"] = rows
            answer = self._send_attempts(
                f"{base_key}-edit",
                lambda c, idem: c.patch(f"documents/quotations/{key}", body, idempotency_key=idem),
            )
            answer = self._done_if_only_mirrored_remarks_ignored(answer)
            if not self._is_done(answer):
                refused = self._interpret(answer, verb="updated", stale_since=stale_since)
                refused["waiting"] = waiting
                if self._is_stale(answer):
                    self._keep_held_stamp(document, held_doc)
                return refused
            document.autocount_edit_issue_id = issue.id
            document.autocount_last_modified = (
                (answer.get("document") or {}).get("LastModified") or document.autocount_last_modified
            )
            self.db.flush()
            last = answer
        for place, wire in adds:
            add_body = {
                "companyCode": company,
                "expectedLastModified": document.autocount_last_modified,
                "line": wire,
            }
            if doc_date:
                add_body["docDate"] = doc_date
            answer = self._send_attempts(
                f"{base_key}-lines-{place}",
                lambda c, idem: c.write(f"documents/quotations/{key}/lines", add_body, idempotency_key=idem),
            )
            if not self._is_done(answer):
                refused = self._interpret(answer, verb="updated", stale_since=stale_since)
                if self._is_stale(answer) and last is None:
                    # Nothing was written this press, so the read before it is the newest stamp.
                    self._keep_held_stamp(document, held_doc)
                if refused["outcome"] == "refused" and not self._is_stale(answer):
                    refused["message"] = (
                        f"The other changes were made. AutoCount refused the added line "
                        f"{wire.get('itemCode')}: {self._reason_of(answer)}."
                    )
                else:
                    refused["message"] = f"The other changes were made. {refused['message']}"
                refused["waiting"] = waiting
                return refused
            last = answer
            document.autocount_last_modified = (
                (answer.get("document") or {}).get("LastModified") or document.autocount_last_modified
            )
            self.db.flush()
        if adds:
            document.autocount_lines_issue_id = issue.id
            self.db.flush()
        if removing:
            for d in gone:
                answer = self._delete_line(
                    "quotations", key, d.get("DtlKey"), company, doc_date, f"{base_key}-delete"
                )
                if answer.get("errorCode") == "ROW_NOT_FOUND":
                    removed.append(d)  # already gone (an earlier press): nothing left to do
                    continue
                if not self._is_done(answer):
                    refused = self._removal_refused(answer, d.get("ItemCode"), made=True)
                    refused["waiting"] = waiting
                    return refused
                removed.append(d)
                last = answer
                document.autocount_last_modified = (
                    (answer.get("document") or {}).get("LastModified") or document.autocount_last_modified
                )
                self.db.flush()
        return finish(last)

    def _delete_line(
        self, kind: str, doc_key: str, dtl_key: Any, company: str, doc_date: Optional[str], base_key: str
    ) -> Dict[str, Any]:
        """SS v2 delete-line route. The body carries no stamp (an accepted choice: the caller read
        the document this press, and a removed row is gone whatever else changed)."""
        dtl = _safe_key(dtl_key)
        body: Dict[str, Any] = {"companyCode": company}
        if doc_date:
            body["docDate"] = doc_date
        return self._send_attempts(
            f"{base_key}-{dtl}",
            lambda c, idem: c.write(f"documents/{kind}/{doc_key}/lines/{dtl}/delete", body, idempotency_key=idem),
        )

    def _removal_refused(self, answer: Dict[str, Any], item: Any, *, made: bool) -> Dict[str, Any]:
        refused = self._interpret(answer, verb="updated")
        prefix = "The other changes were made. " if made else ""
        if answer.get("errorCode") == "ROW_HAS_TRANSFERS":
            refused["message"] = f"{prefix}Line {item} {ROW_TRANSFERRED}, so it cannot be removed."
        elif made and refused["outcome"] == "refused" and answer.get("errorCode") != "DOC_STALE":
            refused["message"] = f"{prefix}AutoCount refused removing line {item}: {self._reason_of(answer)}."
        elif made:
            refused["message"] = f"{prefix}{refused['message']}"
        return refused

    def _keep_held_stamp(self, document, held_doc: Optional[dict]) -> None:
        """B10: after DOC_STALE keep the stamp read just before the write (one read, no second)."""
        stamp = self._held_last_modified(held_doc)
        if stamp:
            document.autocount_last_modified = stamp
            self.db.flush()

    @staticmethod
    def _reason_of(answer: Dict[str, Any]) -> str:
        if answer.get("outcome") == "gateway_error":
            return _trim_sentence(answer.get("message"))
        return _trim_sentence(answer.get("message")) or "no reason given"

    def cancel_quotation(self, document_id: str, actor: Optional[dict] = None) -> Dict[str, Any]:
        document = self._document(document_id)
        if not document.autocount_doc_key:
            raise AppException(
                status_code=409, message="This quotation is not in AutoCount.", code="ac_not_in_autocount"
            )
        if document.autocount_cancelled_at is not None:
            raise AppException(status_code=409, message=ALREADY_CANCELLED, code="ac_already_cancelled")
        key = _safe_key(document.autocount_doc_key)
        self._require_book(document.autocount_book, self.read_capabilities(document.company_id)[1])
        cap = self.capabilities(document.company_id)["quotations"]["cancel_doc"]
        if not cap["enabled"]:
            raise AppException(status_code=409, message=cap["reason"] or WAITING, code="ac_waiting")
        body = {"companyCode": self.company_code(document.company_id)}
        path = f"documents/quotations/{key}/cancel"
        answer = self._send_attempts(
            f"crm-qt-{document.id}-cancel",
            lambda c, key: c.write(path, body, idempotency_key=key),
        )
        return self._finish_cancel(document, answer, actor)

    def _finish_cancel(self, record, answer: Dict[str, Any], actor: Optional[dict]) -> Dict[str, Any]:
        """Done, or SS saying it is already cancelled (DOC_CANCELLED), records the cancel."""
        result = self._interpret(answer, verb="cancelled")
        if self._is_done(answer):
            result["doc_no"] = result["doc_no"] or record.autocount_doc_no
            result["message"] = f"{result['doc_no']} cancelled in AutoCount"
        elif answer.get("errorCode") == "DOC_CANCELLED":
            result = self._blank("done", ALREADY_CANCELLED, record.autocount_doc_no)
        else:
            return result
        record.autocount_last_modified = (
            (answer.get("document") or {}).get("LastModified") or record.autocount_last_modified
        )
        record.autocount_cancelled_at = datetime.utcnow()
        record.autocount_cancelled_by = (actor or {}).get("id")
        self.db.flush()
        return result
