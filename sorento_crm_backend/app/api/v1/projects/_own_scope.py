"""The project-sales "only theirs" guard (PORTAL-P2-ONLY-THEIRS, owner ruling Q1a).

One router-level dependency instead of a scoped loader in each of the ~280 routes. For a
user limited in projects (``projects.projects.view_own`` without ``projects.projects.view``,
see ``app.services.own_scope``) it resolves the FIRST id in the URL to the project it
belongs to and answers 404 when that project is not theirs, before the route body runs. A
holder of ``view`` (and admin, superadmin) is never limited, so the guard does nothing for
them.

It fails closed. For a limited user:

- a route whose first id is not in ``_ANCHORS`` is refused (403), so a child route added
  later is closed to them until someone maps it here;
- an id after the first one must be a name in ``_NESTED`` for that anchor: each of those
  routes already loads it under its parent (``get_task_or_404(db, project_id, task_id)``,
  ``_line_or_404(db, po_id, line_id)``, ...), so a foreign child under their own parent is a
  404 from the route itself;
- a route with no id is refused unless it is in ``_ID_LESS`` (the project list filters in
  the query) or is reference data (``_REFERENCE_PREFIXES`` / ``_REFERENCE_PATHS``);
- the cross-project screens (``_OWN_PERMISSION_PREFIXES``) are left to their own permission
  slug (owner ruling Q2).

``tests/test_portal_p2_own_scope_projects.py`` enumerates ``app.routes`` and pins every route
this lets a limited user reach in ``tests/portal_p2_allowed_routes.txt``.
"""
from __future__ import annotations

import re
from typing import Dict, Optional, Tuple

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user_or_api_key
from app.services import own_scope

PREFIX = "/api/v1/project-sales"

_PARAM = re.compile(r"{(\w+)(?::\w+)?}")


def _one(db: Session, column, key_column, value: str) -> Optional[str]:
    row = db.query(column).filter(key_column == value).first()
    return str(row[0]) if row and row[0] else None


def _project(db: Session, value: str) -> Optional[str]:
    from app.models.projects import Project

    return _one(db, Project.id, Project.id, value)


def _quotation(db: Session, value: str) -> Optional[str]:
    from app.models.projects import ProjectQuotation

    return _one(db, ProjectQuotation.project_id, ProjectQuotation.id, value)


def _quotation_version(db: Session, value: str) -> Optional[str]:
    from app.models.projects import ProjectQuotation, ProjectQuotationVersion

    quotation_id = _one(db, ProjectQuotationVersion.quotation_id, ProjectQuotationVersion.id, value)
    return _one(db, ProjectQuotation.project_id, ProjectQuotation.id, quotation_id) if quotation_id else None


def _sample(db: Session, value: str) -> Optional[str]:
    from app.models.projects import ProjectSample

    return _one(db, ProjectSample.project_id, ProjectSample.id, value)


def _purchase_order(db: Session, value: str) -> Optional[str]:
    from app.models.projects import ProjectPurchaseOrder

    return _one(db, ProjectPurchaseOrder.project_id, ProjectPurchaseOrder.id, value)


def _po_version(db: Session, value: str) -> Optional[str]:
    from app.models.project_so import ProjectPOVersion

    po_id = _one(db, ProjectPOVersion.purchase_order_id, ProjectPOVersion.id, value)
    return _purchase_order(db, po_id) if po_id else None


def _schedule(db: Session, value: str) -> Optional[str]:
    from app.models.project_so import DeliverySchedule

    return _one(db, DeliverySchedule.project_id, DeliverySchedule.id, value)


def _schedule_version(db: Session, value: str) -> Optional[str]:
    from app.models.project_so import DeliveryScheduleVersion

    schedule_id = _one(
        db, DeliveryScheduleVersion.delivery_schedule_id, DeliveryScheduleVersion.id, value
    )
    return _schedule(db, schedule_id) if schedule_id else None


def _phase(db: Session, value: str) -> Optional[str]:
    from app.models.project_so import ProjectDeliveryPhase

    return _one(db, ProjectDeliveryPhase.project_id, ProjectDeliveryPhase.id, value)


def _sales_order(db: Session, value: str) -> Optional[str]:
    from app.models.project_so import ProjectSalesOrder

    return _one(db, ProjectSalesOrder.project_id, ProjectSalesOrder.id, value)


#: The route's own row rule answers instead of the project (owner ruling, behaviour card
#: example 3): a sample request is theirs by who raised it, wherever it sits.
_MODULE_RULE = object()

#: (path segment before the first id, that id's name) -> the project it belongs to.
_ANCHORS: Dict[Tuple[str, str], object] = {
    ("projects", "project_id"): _project,
    ("quotations", "quotation_id"): _quotation,
    ("quotation-versions", "version_id"): _quotation_version,
    ("samples", "sample_id"): _sample,
    ("purchase-orders", "po_id"): _purchase_order,
    ("purchase-order-versions", "po_version_id"): _po_version,
    ("delivery-schedules", "schedule_id"): _schedule,
    ("delivery-schedule-versions", "version_id"): _schedule_version,
    ("delivery-phases", "phase_id"): _phase,
    ("sales-orders", "pso_id"): _sales_order,
    ("sample-requests", "request_id"): _MODULE_RULE,
}

#: Second-and-later ids per anchor, each loaded by its route under the parent the anchor
#: resolved (security review 27 Oct, file:line per name in the PR), plus the plain integer
#: positions some routes take. Keyed per anchor so a name trusted under one parent is not
#: trusted under another.
_NESTED: Dict[str, frozenset] = {
    "projects": frozenset(
        {"task_id", "stakeholder_id", "document_id", "issue_id", "quotation_id", "request_id"}
    ),
    "quotation-versions": frozenset({"line_id"}),
    "purchase-orders": frozenset({"line_id", "finding_id"}),
    "purchase-order-versions": frozenset({"line_id"}),
    "delivery-schedule-versions": frozenset({"column_index", "product_index", "index"}),
    "sales-orders": frozenset({"line_id", "finding_id"}),
}

#: Routes with no id a limited user may call: the list filters to theirs in the query, a
#: registration is theirs by construction, sample requests answer by their own row rule.
_ID_LESS = frozenset(
    {
        ("GET", "/projects/"),
        ("POST", "/projects/"),
        ("GET", "/sample-requests"),
        ("POST", "/sample-requests"),
        ("GET", "/sample-requests/products"),
    }
)

#: Setup and lookups, not anybody's records; their own permission still gates them.
_REFERENCE_PREFIXES = ("/config/", "/status-graph/")

#: The cross-project screens (owner ruling Q2, 27 Oct): "depends on the permission we give to
#: their role". `view_own` on projects neither opens nor closes them; each route answers to its
#: own permission slug exactly as for anyone else, so the guard steps aside.
_OWN_PERMISSION_PREFIXES = (
    "/reports/",
    "/stock-debt",
    "/order-inquiries",
    "/order-inquiry-headers",
    "/order-inquiry-rows",
    "/leads",
    "/allocation-claims",
    "/fulfilment-planning",
    "/plans",
    "/planning-changes",
    "/divergences",
)
_REFERENCE_PATHS = frozenset({"/quotation-approval-graph", "/quotation-line-images", "/quotation-line-stock"})


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")


def _refused() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Not available with access to your own records only.",
    )


def classify(method: str, path_format: str):
    """How a limited user reaches this route: ``"open"`` (no id to check), an anchor resolver
    (or ``_MODULE_RULE``) for its first id, or ``None`` when it is refused."""
    path = path_format[len(PREFIX):] if path_format.startswith(PREFIX) else path_format
    if path.startswith(_REFERENCE_PREFIXES) or path in _REFERENCE_PATHS:
        return "open"
    if path.startswith(_OWN_PERMISSION_PREFIXES):
        return "open"
    names = _PARAM.findall(path)
    if not names:
        return "open" if (method, path) in _ID_LESS else None
    segment = path[: path.index("{")].rstrip("/").rsplit("/", 1)[-1]
    resolver = _ANCHORS.get((segment, names[0]))
    nested = _NESTED.get(segment, frozenset())
    if resolver is None or any(name not in nested for name in names[1:]):
        return None
    return resolver


def check(db: Session, user_id: str, method: str, path_format: str, path_params: dict) -> None:
    """Raise unless a limited user may reach this route with these ids; no-op otherwise."""
    if not own_scope.user_is_limited(
        db, user_id, own_scope.PROJECTS_VIEW, own_scope.PROJECTS_VIEW_OWN
    ):
        return
    resolver = classify(method, path_format)
    if resolver is None:
        raise _refused()
    if resolver == "open" or resolver is _MODULE_RULE:
        return
    path = path_format[len(PREFIX):] if path_format.startswith(PREFIX) else path_format
    first = _PARAM.findall(path)[0]
    value = str(path_params.get(first) or "")
    if not _is_uuid(value):
        raise _not_found()
    project_id = resolver(db, value)  # type: ignore[operator]
    if not own_scope.project_in_scope(db, own_scope.me(db, user_id), project_id):
        raise _not_found()


def _is_uuid(value: str) -> bool:
    import uuid

    try:
        uuid.UUID(value)
    except ValueError:
        return False
    return True


async def project_own_scope_guard(
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_or_api_key),
) -> None:
    route = request.scope.get("route")
    path_format = getattr(route, "path_format", None) or request.url.path
    check(db, str(current_user.get("id") or ""), request.method, path_format, request.path_params)

