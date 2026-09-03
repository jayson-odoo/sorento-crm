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

#: Catalogue dimensions are millimetres; volume is cubic metres.
_MM3_PER_M3 = 1_000_000_000.0
#: Carton dimensions on a shipment line are centimetres (the sheet's `SIZE (CM)` block).
_CM3_PER_M3 = 1_000_000.0


def _as_float(value: Any) -> Optional[float]:
    return None if value is None else float(value)


def _catalogue_cbm(product: Any, qty: float) -> Optional[float]:
    """Volume from the catalogue when nothing on the line itself measured it.

    MOVED here from `consolidated_packing_list.py` (S12): `line_cbm` below is the one place
    that falls back to it now, so a second copy of the same fallback for the fill gauge is
    exactly the drift this slice closes. Catalogue dimensions are millimetres; the mm^3 basis
    matches `loading_plan_service._catalogue_cbm`, which keeps its OWN copy for the reason
    given at its definition - a per-unit figure, not one lane's dims-only line total.
    """
    l, w, h = product.dimensions_length, product.dimensions_width, product.dimensions_height
    if l is None or w is None or h is None:
        return None
    return round(float(l) * float(w) * float(h) / _MM3_PER_M3 * float(qty), 6)


def line_cbm(line: Any, product: Any = None) -> Optional[float]:
    """The one figure every reader of a shipment line's volume asks for (S12).

    Three sources, in order:

    1. The line's own STORED `cbm` - what the supplier stated, or what a convert wrote.
    2. The line's own CARTON measurements - `ctn * L * W * H / 1e6` in cubic metres, where
       `ctn` is `quantity_shipped / pcs_per_carton` when a pack size was stated (a factory
       routinely gives pieces-per-carton and no carton count) and the line's own
       `cartons_count` otherwise. This was the hole S12 closes: `build()` used to skip
       straight from (1) to (3), so a line typed with only its own carton dimensions
       measured as zero on the Split card and the fill gauge while `to_xlsx` derived the
       SAME figure live from those dimensions - the workbook was right and the screen it
       came from was not.
    3. The CATALOGUE's own dimensions, times the line's quantity - only when neither the
       line nor its cartons were measured at all.

    `product` is optional: `build()` already has it from its own join and passes it in, so
    it costs no extra query there; a caller with only the ORM line (`_attach_capacity`) falls
    back to `line.product`, a lazy load that only fires for a line reaching step 3 - the
    common case of a fully measured line never pays for it.
    """
    stored = _as_float(getattr(line, "cbm", None))
    if stored is not None:
        return stored
    length = _as_float(getattr(line, "carton_length_cm", None))
    width = _as_float(getattr(line, "carton_width_cm", None))
    height = _as_float(getattr(line, "carton_height_cm", None))
    if length is not None and width is not None and height is not None:
        qty = _as_float(getattr(line, "quantity_shipped", None)) or 0.0
        pcs = _as_float(getattr(line, "pcs_per_carton", None))
        ctn = (qty / pcs) if pcs and pcs > 0 else (_as_float(getattr(line, "cartons_count", None)) or 0.0)
        return round(ctn * length * width * height / _CM3_PER_M3, 6)
    resolved_product = product if product is not None else getattr(line, "product", None)
    if resolved_product is None:
        return None
    qty = _as_float(getattr(line, "quantity_shipped", None)) or 0.0
    return _catalogue_cbm(resolved_product, qty)


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
