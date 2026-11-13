"""Link an adopted sales order to a project and its PO (AC-PI-29).

The ONE function that puts a project sales order (`projects.sales_orders`) on a project,
and on one of its POs when given. The project import calls it after
`ProjectSOAdoptionService.adopt_for_migration`; nothing else had a shared way to do this.

An order already on ANOTHER project is refused with 409 and is never moved: which project
an order belongs to is a person's decision, not an import's.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.models.project_so import ProjectSalesOrder
from app.models.projects import Project, ProjectPurchaseOrder
from app.services.error_handler import AppException


def link_sales_order_to_project(
    db: Session,
    *,
    project_sales_order: ProjectSalesOrder,
    project: Project,
    purchase_order: Optional[ProjectPurchaseOrder],
) -> None:
    """Set the order's project (and its PO when one is given and none is set yet)."""
    current = project_sales_order.project_id
    if current is not None and str(current) != str(project.id):
        raise AppException(
            409,
            f"Sales order {project_sales_order.provisional_ref} is already on another project.",
            code="sales_order_on_other_project",
        )
    project_sales_order.project_id = project.id
    if purchase_order is not None and project_sales_order.purchase_order_id is None:
        project_sales_order.purchase_order_id = purchase_order.id
    db.flush()
