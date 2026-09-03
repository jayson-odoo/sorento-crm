"""How full a container is, shared by every reader that asks (S5, PLAN-scm-pi-packing-list-
feedback-3sep.md ruling 1).

Capacity is a property of the CONTAINER, not any one document that fed it: the proforma
convert's capacity gate (`proforma_invoice_service._over_capacity`, judging the COMBINED
volume of what a convert is placing against the container size the operator chose) and the
packing list's own fill gauge (the shipment's line volume against
`inbound_shipments.container_size_id`) are the same arithmetic asked by two different
screens. One implementation, so a percentage cannot drift between the refusal a convert shows
and the gauge the packing list renders afterwards.
"""
from __future__ import annotations

from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.scm import ContainerSize


def container_sizes(db: Session) -> tuple[dict[str, ContainerSize], Optional[ContainerSize]]:
    """Every active container size by id, and whichever one is the tenant's default.

    Read once per caller rather than per row: a page of several shipments or invoices asks
    the same three-row question repeatedly otherwise.
    """
    rows = db.query(ContainerSize).filter(ContainerSize.is_active.is_(True)).all()
    return {str(r.id): r for r in rows}, next((r for r in rows if r.is_default), None)


def fit(
    container_size_id: Optional[str],
    total_cbm: Optional[float],
    sizes_by_id: dict[str, ContainerSize],
    default_size: Optional[ContainerSize],
) -> dict[str, Any]:
    """How full a container is, and which one it is.

    The size is RESOLVED at read time from the tenant's default when `container_size_id` is
    unset, rather than copied onto the row: a container nobody has chosen a size for should
    follow the current default, not freeze whatever it happened to be that day.
    """
    size = sizes_by_id.get(str(container_size_id)) if container_size_id else None
    if size is None:
        size = default_size
    capacity = float(size.cbm) if size is not None and size.cbm is not None else None
    fill_pct = (
        (total_cbm / capacity) * 100
        if total_cbm is not None and capacity
        else None
    )
    over = (
        round(total_cbm - capacity, 4)
        if total_cbm is not None and capacity and total_cbm > capacity
        else None
    )
    return {
        "container_size_id": str(size.id) if size is not None else None,
        "container_size_code": size.code if size is not None else None,
        "container_cbm": capacity,
        "total_cbm": total_cbm,
        "fill_pct": round(fill_pct, 2) if fill_pct is not None else None,
        "over_by_cbm": over,
    }
