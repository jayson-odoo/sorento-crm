"""Prev/next neighbour sequences for the project-sales detail screens.

Each detail page (a sales order, a customer PO, a delivery schedule version) carries the
shared `RecordNavigation` pager, and the pager has to walk the SAME set, in the SAME order,
as the list the user came from - otherwise "next" lands somewhere the list never showed
them, which reads as a wrong record rather than as a different sort.

So each function below mirrors ONE list, named in its docstring, and the position/wrap maths
is deferred to the shared, resource-agnostic ``compute_neighbours`` helper the rest of the
system already uses. Circular by that helper's rule: Next on the last record reaches the
first, Prev on the first reaches the last.

No filter or sort arguments: these three lists are project TABS rather than filtered grids,
so each has exactly one order, and the pager takes it as it stands. If a filtered
list-to-detail flow ever arrives, this is where the list query would be threaded through -
the way the customer and complaint neighbours already do it.

The ordering is deterministic to the last term. Sales orders built in one pass share a
``created_at`` to the microsecond, so a query ordered on that alone can return them in any
order, and the pager would then disagree with the tab it is standing on; the tie is broken
on the provisional reference, which is unique and monotonic. The two lists this mirrors
carry the same tie-breakers, deliberately.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.models.project_so import DeliveryScheduleVersion, ProjectSalesOrder
from app.models.projects import ProjectPurchaseOrder
from app.services.error_handler import AppException
from app.services.record_navigation import compute_neighbours


def sales_order_neighbours(db: Session, *, project_id: str, pso_id: str) -> dict:
    """Neighbours of one sales order within its project's orders, newest first.

    Mirrors ``ProjectSODraftService.list_for_project`` with no filter and its default sort,
    which is what the project's sales-orders tab asks for.
    """
    order = (
        db.query(ProjectSalesOrder).filter(ProjectSalesOrder.id == pso_id).first()
    )
    _assert_in_project(
        found=order is not None,
        owner_project_id=order.project_id if order else None,
        project_id=project_id,
        message="Sales order not found.",
        code="sales_order_not_found",
    )

    ordered_ids = [
        str(row[0])
        for row in db.query(ProjectSalesOrder.id)
        .filter(ProjectSalesOrder.project_id == project_id)
        .order_by(
            ProjectSalesOrder.created_at.desc(),
            ProjectSalesOrder.provisional_ref.asc(),
        )
        .all()
    ]
    return compute_neighbours(ordered_ids, pso_id)


def purchase_order_neighbours(db: Session, *, project_id: str, po_id: str) -> dict:
    """Neighbours of one customer PO within its project's POs, newest PO date first.

    Mirrors ``project_po_service.list_pos``, which is what the project's POs tab shows.
    """
    po = (
        db.query(ProjectPurchaseOrder).filter(ProjectPurchaseOrder.id == po_id).first()
    )
    _assert_in_project(
        found=po is not None,
        owner_project_id=po.project_id if po else None,
        project_id=project_id,
        message="Purchase order not found.",
        code="po_not_found",
    )

    ordered_ids = [
        str(row[0])
        for row in db.query(ProjectPurchaseOrder.id)
        .filter(ProjectPurchaseOrder.project_id == project_id)
        .order_by(
            ProjectPurchaseOrder.po_date.desc().nullslast(),
            ProjectPurchaseOrder.created_at.desc(),
            ProjectPurchaseOrder.po_number.asc(),
        )
        .all()
    ]
    return compute_neighbours(ordered_ids, po_id)


def schedule_version_neighbours(db: Session, *, version_id: str) -> dict:
    """Neighbours of one schedule version within ITS OWN schedule's revision history.

    Mirrors ``ProjectScheduleService.list_versions`` (newest version first), which is the
    grid the reviewer opens a version from. Scoped to the one schedule rather than to the
    project: R1 and R2 are two documents of one commitment, and stepping between them is
    what the reviewer is doing; a different schedule is a different commitment.
    """
    version = (
        db.query(DeliveryScheduleVersion)
        .filter(DeliveryScheduleVersion.id == version_id)
        .first()
    )
    if version is None:
        raise AppException(
            status_code=404,
            message="Delivery schedule version not found.",
            code="schedule_version_not_found",
        )

    ordered_ids = [
        str(row[0])
        for row in db.query(DeliveryScheduleVersion.id)
        .filter(
            DeliveryScheduleVersion.delivery_schedule_id == version.delivery_schedule_id
        )
        .order_by(
            DeliveryScheduleVersion.version_no.desc(),
            DeliveryScheduleVersion.id.asc(),
        )
        .all()
    ]
    return compute_neighbours(ordered_ids, version_id)


def _assert_in_project(
    *,
    found: bool,
    owner_project_id: Optional[str],
    project_id: str,
    message: str,
    code: str,
) -> None:
    """A record that does not exist, and one that belongs to another project, are the same
    404 here: both would put a record the list never held into this sequence."""
    if not found or str(owner_project_id) != str(project_id):
        raise AppException(status_code=404, message=message, code=code)
