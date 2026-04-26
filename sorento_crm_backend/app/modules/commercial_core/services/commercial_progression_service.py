"""Sales order progression: winning quotation path → commercial sales order; tender close-out without SO."""
from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Optional, Tuple

from sqlalchemy.orm import Session

from app.modules.commercial_core.models import (
    CommercialMasterQuotation,
    CommercialMasterQuotationPathRole,
    CommercialQuotationRevision,
    CommercialSalesOrder,
    CommercialSalesOrderStatus,
    CommercialTender,
    CommercialTenderLifecycle,
    CommercialTenderOutcome,
)
from app.models.numbering import DocumentNumberingRule
from app.modules.commercial_core.services.commercial_hierarchy_service import CommercialHierarchyError, validate_new_sales_order


def get_tender_by_ref(db: Session, tender_ref: str) -> Optional[CommercialTender]:
    """Resolve tender by primary key or by unique tender_code."""
    t = db.query(CommercialTender).filter(CommercialTender.id == tender_ref).one_or_none()
    if t:
        return t
    return db.query(CommercialTender).filter(CommercialTender.tender_code == tender_ref).one_or_none()


def allocate_next_commercial_sales_order_number(db: Session, reference_date: Optional[date] = None) -> str:
    """
    Next running number for commercial_sales_order rules; does not commit.
    Falls back to a unique string if no enabled rule exists.
    """
    if reference_date is None:
        reference_date = date.today()

    rule = (
        db.query(DocumentNumberingRule)
        .filter(
            DocumentNumberingRule.doc_type == "commercial_sales_order",
            DocumentNumberingRule.enabled.is_(True),
        )
        .with_for_update()
        .first()
    )
    if not rule:
        return f"CSO-{reference_date.strftime('%Y%m%d')}-{str(uuid.uuid4())[:8].upper()}"

    if rule.reset_policy == "yearly":
        current_key = str(reference_date.year)
    elif rule.reset_policy == "monthly":
        current_key = f"{reference_date.year}-{reference_date.month:02d}"
    else:
        current_key = rule.last_reset_key or ""

    if current_key and current_key != (rule.last_reset_key or ""):
        rule.next_value = rule.start_value
        rule.last_reset_key = current_key

    yy = str(reference_date.year % 100).zfill(2)
    prefix = (rule.prefix_template or "").format(
        year=reference_date.year,
        yy=yy,
        month=reference_date.month,
        day=reference_date.day,
    )
    number_part = str(rule.next_value).zfill(rule.number_digits)
    result = f"{prefix}{number_part}"
    rule.next_value += 1
    db.flush()
    return result


def _assert_tender_open_for_progression(tender: CommercialTender) -> None:
    if tender.tender_lifecycle != CommercialTenderLifecycle.OPEN:
        raise CommercialHierarchyError("Tender is not open for progression.")
    if tender.tender_outcome != CommercialTenderOutcome.PENDING:
        raise CommercialHierarchyError("Tender outcome is already set.")


def _assert_no_blocking_sales_order(db: Session, tender_id: str) -> None:
    existing = (
        db.query(CommercialSalesOrder)
        .filter(
            CommercialSalesOrder.tender_id == tender_id,
            CommercialSalesOrder.status.in_(CommercialSalesOrderStatus.ACTIVE_FOR_TENDER_UNIQUE),
        )
        .first()
    )
    if existing is not None:
        raise CommercialHierarchyError("Tender already has an active commercial sales order.")


def _resolve_master_quotation(
    db: Session, tender_id: str, quotation_code: str
) -> CommercialMasterQuotation:
    mq = (
        db.query(CommercialMasterQuotation)
        .filter(
            CommercialMasterQuotation.tender_id == tender_id,
            CommercialMasterQuotation.quotation_code == quotation_code,
        )
        .one_or_none()
    )
    if mq is None:
        raise CommercialHierarchyError("Master quotation not found for this tender and quotation code.")
    return mq


def _resolve_revision(
    db: Session, master_quotation_id: str, revision_number: int
) -> CommercialQuotationRevision:
    rev = (
        db.query(CommercialQuotationRevision)
        .filter(
            CommercialQuotationRevision.master_quotation_id == master_quotation_id,
            CommercialQuotationRevision.revision_number == revision_number,
        )
        .one_or_none()
    )
    if rev is None:
        raise CommercialHierarchyError("Quotation revision not found for this master quotation.")
    return rev


class CommercialProgressionService:
    def __init__(self, db: Session):
        self.db = db

    def progress_winning_path(
        self,
        *,
        tender_id: str,
        quotation_code: str,
        revision_number: int,
        sales_order_number: Optional[str] = None,
    ) -> Tuple[CommercialTender, CommercialSalesOrder]:
        tender = self.db.query(CommercialTender).filter(CommercialTender.id == tender_id).one_or_none()
        if tender is None:
            raise CommercialHierarchyError("Tender not found.")

        _assert_tender_open_for_progression(tender)

        winner_mq = _resolve_master_quotation(self.db, tender_id, quotation_code)
        rev = _resolve_revision(self.db, winner_mq.id, revision_number)

        existing_winner = (
            self.db.query(CommercialMasterQuotation)
            .filter(
                CommercialMasterQuotation.tender_id == tender_id,
                CommercialMasterQuotation.path_role == CommercialMasterQuotationPathRole.WINNER,
            )
            .first()
        )
        if existing_winner is not None:
            raise CommercialHierarchyError("This tender already has a winning quotation path.")

        winner_mq.final_selected_revision_id = rev.id
        self.db.flush()

        validate_new_sales_order(
            self.db,
            quotation_revision_id=rev.id,
            master_quotation_id=winner_mq.id,
            tender_id=tender_id,
            status=CommercialSalesOrderStatus.DRAFT,
        )

        now = datetime.utcnow()
        son = (sales_order_number or "").strip() or allocate_next_commercial_sales_order_number(self.db)

        for mq in (
            self.db.query(CommercialMasterQuotation)
            .filter(CommercialMasterQuotation.tender_id == tender_id)
            .all()
        ):
            if mq.id == winner_mq.id:
                mq.path_role = CommercialMasterQuotationPathRole.WINNER
            else:
                mq.path_role = CommercialMasterQuotationPathRole.CLOSED_SUPERSEDED

        rev.final_selected_at = now

        so = CommercialSalesOrder(
            id=str(uuid.uuid4()),
            quotation_revision_id=rev.id,
            master_quotation_id=winner_mq.id,
            tender_id=tender_id,
            sales_order_number=son,
            status=CommercialSalesOrderStatus.DRAFT,
        )
        self.db.add(so)

        tender.tender_lifecycle = CommercialTenderLifecycle.CLOSED
        tender.tender_outcome = CommercialTenderOutcome.WON
        tender.closed_at = now
        tender.winning_master_quotation_id = winner_mq.id

        self.db.flush()
        self.db.refresh(so)
        self.db.refresh(tender)
        return tender, so

    def close_tender_without_sales_order(
        self,
        *,
        tender_id: str,
        tender_outcome: str,
        outcome_notes: Optional[str] = None,
    ) -> CommercialTender:
        if tender_outcome not in CommercialTenderOutcome.CLOSE_WITHOUT_ORDER:
            raise CommercialHierarchyError(
                f"Invalid tender outcome {tender_outcome!r}; expected one of {CommercialTenderOutcome.CLOSE_WITHOUT_ORDER}."
            )

        tender = self.db.query(CommercialTender).filter(CommercialTender.id == tender_id).one_or_none()
        if tender is None:
            raise CommercialHierarchyError("Tender not found.")

        _assert_tender_open_for_progression(tender)

        existing_winner = (
            self.db.query(CommercialMasterQuotation)
            .filter(
                CommercialMasterQuotation.tender_id == tender_id,
                CommercialMasterQuotation.path_role == CommercialMasterQuotationPathRole.WINNER,
            )
            .first()
        )
        if existing_winner is not None:
            raise CommercialHierarchyError("Cannot close tender without order: a winning quotation path exists.")

        _assert_no_blocking_sales_order(self.db, tender_id)

        now = datetime.utcnow()
        for mq in (
            self.db.query(CommercialMasterQuotation)
            .filter(CommercialMasterQuotation.tender_id == tender_id)
            .all()
        ):
            mq.path_role = CommercialMasterQuotationPathRole.CLOSED_UNAWARDED

        tender.tender_lifecycle = CommercialTenderLifecycle.CLOSED
        tender.tender_outcome = tender_outcome
        tender.closed_at = now
        tender.winning_master_quotation_id = None
        if outcome_notes is not None:
            tender.outcome_notes = outcome_notes.strip() or None

        self.db.flush()
        self.db.refresh(tender)
        return tender
