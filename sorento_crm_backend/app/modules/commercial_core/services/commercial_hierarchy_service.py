"""Shared validations for the commercial entity hierarchy (used by future APIs)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.modules.commercial_core.models import (
    CommercialMasterQuotation,
    CommercialQuotationRevision,
    CommercialSalesOrder,
    CommercialSalesOrderStatus,
)


class CommercialHierarchyError(Exception):
    """Raised when an operation violates commercial hierarchy or winner rules."""


class ToleranceAdvanceConfirmationRequired(CommercialHierarchyError):
    """Advancing would exceed tolerance; client must confirm before rerouting for approval."""

    def __init__(self, breaches: List[Dict[str, Any]]):
        self.breaches = breaches
        super().__init__(
            "Tolerance confirmation required: line items exceed product price tolerance for this advance."
        )


def revision_hierarchy_ids(db: Session, revision_id: str) -> Tuple[str, str, str]:
    """
    Returns (tender_id, master_quotation_id, revision_id) for a quotation revision.
    """
    rev = (
        db.query(CommercialQuotationRevision)
        .filter(CommercialQuotationRevision.id == revision_id)
        .one_or_none()
    )
    if rev is None:
        raise CommercialHierarchyError("Quotation revision not found.")
    mq = (
        db.query(CommercialMasterQuotation)
        .filter(CommercialMasterQuotation.id == rev.master_quotation_id)
        .one_or_none()
    )
    if mq is None:
        raise CommercialHierarchyError("Master quotation not found for revision.")
    return mq.tender_id, mq.id, rev.id


def assert_revision_matches_master(db: Session, revision_id: str, master_quotation_id: str) -> None:
    rev = (
        db.query(CommercialQuotationRevision)
        .filter(
            CommercialQuotationRevision.id == revision_id,
            CommercialQuotationRevision.master_quotation_id == master_quotation_id,
        )
        .one_or_none()
    )
    if rev is None:
        raise CommercialHierarchyError("Quotation revision does not belong to the given master quotation.")


def assert_master_matches_tender(db: Session, master_quotation_id: str, tender_id: str) -> None:
    mq = (
        db.query(CommercialMasterQuotation)
        .filter(
            CommercialMasterQuotation.id == master_quotation_id,
            CommercialMasterQuotation.tender_id == tender_id,
        )
        .one_or_none()
    )
    if mq is None:
        raise CommercialHierarchyError("Master quotation does not belong to the given tender.")


def assert_sales_order_status_allowed(status: str) -> None:
    if status not in CommercialSalesOrderStatus.ALL:
        raise CommercialHierarchyError(
            f"Invalid sales order status {status!r}; expected one of {CommercialSalesOrderStatus.ALL}."
        )


def assert_no_active_sales_order_for_tender(db: Session, tender_id: str, *, ignore_sales_order_id: Optional[str] = None) -> None:
    q = db.query(CommercialSalesOrder).filter(
        CommercialSalesOrder.tender_id == tender_id,
        CommercialSalesOrder.status.in_(CommercialSalesOrderStatus.ACTIVE_FOR_TENDER_UNIQUE),
    )
    if ignore_sales_order_id:
        q = q.filter(CommercialSalesOrder.id != ignore_sales_order_id)
    if q.first() is not None:
        raise CommercialHierarchyError("This tender already has an active commercial sales order (draft or confirmed).")


def assert_no_sales_order_for_master_quotation(
    db: Session, master_quotation_id: str, *, ignore_sales_order_id: Optional[str] = None
) -> None:
    q = db.query(CommercialSalesOrder).filter(CommercialSalesOrder.master_quotation_id == master_quotation_id)
    if ignore_sales_order_id:
        q = q.filter(CommercialSalesOrder.id != ignore_sales_order_id)
    if q.first() is not None:
        raise CommercialHierarchyError("This master quotation already has a commercial sales order.")


def denormalized_ids_for_revision(db: Session, quotation_revision_id: str) -> Tuple[str, str]:
    """Returns (tender_id, master_quotation_id) consistent with the revision."""
    tender_id, master_id, _ = revision_hierarchy_ids(db, quotation_revision_id)
    return tender_id, master_id


def validate_new_sales_order(
    db: Session,
    *,
    quotation_revision_id: str,
    master_quotation_id: str,
    tender_id: str,
    status: str,
) -> None:
    """
    Validates denormalized FKs and exclusivity rules before inserting a commercial sales order.
    """
    assert_sales_order_status_allowed(status)
    assert_revision_matches_master(db, quotation_revision_id, master_quotation_id)
    assert_master_matches_tender(db, master_quotation_id, tender_id)
    t_id, m_id, _ = revision_hierarchy_ids(db, quotation_revision_id)
    if t_id != tender_id or m_id != master_quotation_id:
        raise CommercialHierarchyError("Denormalized tender_id or master_quotation_id does not match the revision chain.")
    assert_no_sales_order_for_master_quotation(db, master_quotation_id)
    if status in CommercialSalesOrderStatus.ACTIVE_FOR_TENDER_UNIQUE:
        assert_no_active_sales_order_for_tender(db, tender_id)

    mq = (
        db.query(CommercialMasterQuotation)
        .filter(CommercialMasterQuotation.id == master_quotation_id)
        .one_or_none()
    )
    if mq is None:
        raise CommercialHierarchyError("Master quotation not found.")
    if not mq.final_selected_revision_id:
        raise CommercialHierarchyError(
            "Set a final selected quotation revision on the master quotation before creating a sales order."
        )
    if str(mq.final_selected_revision_id) != str(quotation_revision_id):
        raise CommercialHierarchyError(
            "Sales order must use the master quotation's final selected revision."
        )
