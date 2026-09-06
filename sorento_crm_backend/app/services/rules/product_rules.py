"""Product-specific ingest rules (S1): discontinued derivation, dimension
parsing, unknown-reference resolve-or-create and the default-supplier link -
moved here from `product_service.py` (`is_discontinued_from_description` /
`is_discontinued_from_row`, `parse_dimensions_from_description`, the
`ensure_reference` / `link_default_supplier` closures inside
`bulk_import_products`) so the xlsx import, the manual create/edit and the
ESB push share one body each (D2, D3, D4, D5).
"""
from __future__ import annotations

import re
import uuid
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.procurement import ProductSupplier, Supplier
from app.services.rules.master_rules import (
    code_name_columns,
    resolve_master_by_code,
    resolve_master_by_name,
)

#: The rollout fallback unit code (moved from `product_service.DEFAULT_UOM_CODE`).
DEFAULT_UOM_CODE = "EA"

#: Description prefix that marks a product discontinued when nothing states
#: the flag explicitly (moved from `product_service.is_discontinued_from_description`).
_DISCONTINUED_PREFIX = "****"

#: Values an explicit Discontinued cell/flag may carry for "yes". AutoCount
#: exports checkbox columns as "Checked"/"Unchecked".
_DISCONTINUED_TRUE = {"CHECKED", "T", "TRUE", "1", "Y", "YES"}


def derivation_text(name: Optional[str], description: Optional[str]) -> str:
    """D2/D4's shared source text for `is_discontinued`/`parse_dimensions`.

    Live finding, 2026-09-06: the ESB maps AutoCount's `Item.Description`
    onto `name` (`products.product_name`) and sends no `description` at
    all, while the xlsx import stores the same AutoCount text in
    `description` (`product_name` is the item code there instead) - two
    channels deriving `is_discontinued`/dimensions from two different
    columns for the identical source text. `description` wins when it is
    non-blank (the xlsx import's shape, and the shape a future ESB mapping
    fix would produce); `name` is the fallback so the ESB's current
    mapping still derives correctly. Every caller of `is_discontinued`/
    `parse_dimensions` - manual create/update, the xlsx import, the ESB
    insert AND update path - feeds this, never the raw `description`
    column directly.
    """
    return description if description else (name or "")


def is_discontinued(flag: Any, description: Optional[str]) -> bool:
    """D2: an explicit flag always wins; otherwise a description starting
    with `****` (after stripping leading whitespace) marks the product
    discontinued.

    `flag` is whatever the caller has - a real bool (manual create/edit, the
    ESB payload), a raw cell value (the xlsx import's Discontinued/checkbox
    column, "Checked"/"T"/"1"/...), or `None` meaning "not sent", the only
    case that falls through to the description rule.
    """
    if isinstance(flag, bool):
        return flag
    if flag is not None:
        text = str(flag).strip()
        if text != "":
            return text.upper() in _DISCONTINUED_TRUE
    if not description:
        return False
    return description.lstrip().startswith(_DISCONTINUED_PREFIX)


#: Same three-number-plus-unit shape AutoCount descriptions carry, extended
#: (over `product_service.parse_dimensions_from_description`) to accept a 2-D
#: form (height NULL) and a unit attached to each number individually
#: (`1.2Mx0.6Mx2M`) rather than only once at the very end.
_NUMBER_TOKEN = r"(\d+(?:\.\d+)?)\s*(mm|cm|m)?"
_DIMENSION_PATTERN = re.compile(
    r"(?<![\d.])\(?"
    + _NUMBER_TOKEN
    + r"\s*[xX×]\s*"
    + _NUMBER_TOKEN
    + r"(?:\s*[xX×]\s*"
    + _NUMBER_TOKEN
    + r")?"
    r"(?:\s*(mm|cm|m)\b)?\)?",
    re.IGNORECASE,
)
_UNIT_TO_MM: dict[str, Decimal] = {
    "": Decimal("1"),
    "mm": Decimal("1"),
    "cm": Decimal("10"),
    "m": Decimal("1000"),
}
_QUANTIZE = Decimal("0.01")


def parse_dimensions(
    description: Optional[str],
) -> tuple[Optional[Decimal], Optional[Decimal], Optional[Decimal]]:
    """Extract length/width/height (in mm) from a product description.

    Returns `(length_mm, width_mm, height_mm)`. A 2-D description
    (`"1000x500"`) returns `height=None`; no match returns all-`None`. The
    unit governing a number with none of its own falls back to the LAST
    number's unit (whether that came from a per-number suffix or a shared
    trailing one) - the only way `"45x38CM"` reads as `(450, 380, None)`
    rather than `(45, 380, None)`.
    """
    if not description:
        return (None, None, None)
    m = _DIMENSION_PATTERN.search(description)
    if not m:
        return (None, None, None)
    n1, u1, n2, u2, n3, u3, trailing = m.groups()
    last_unit = u3 if n3 is not None else u2
    shared_unit = (trailing or last_unit or "").lower()

    def _convert(number: Optional[str], unit: Optional[str]) -> Optional[Decimal]:
        if number is None:
            return None
        factor = _UNIT_TO_MM.get((unit or shared_unit or "").lower(), Decimal("1"))
        try:
            return (Decimal(number) * factor).quantize(_QUANTIZE)
        except Exception:
            return None

    return (_convert(n1, u1), _convert(n2, u2), _convert(n3, u3))


#: Auto-created master data note (moved from `product_service.AUTO_CREATED_NOTE`).
AUTO_CREATED_NOTE = "Auto-created by product import"

#: The code columns are VARCHAR(50) or narrower, so a longer source value is
#: a row error rather than a silent truncation that would collide with a
#: different value later (moved from `product_service.REF_CODE_MAX_LEN`).
REF_CODE_MAX_LEN = 50


class ReferenceTooLong(ValueError):
    """A source value that does not fit the target master's code column."""


def ensure_reference(
    db: Session, model: type, code: Optional[str], company_id: Optional[str]
) -> tuple[str, bool]:
    """Resolve a master-data value, creating the row when it is unknown (D3).

    Matches by normalised CODE, then by normalised NAME (review S2, 2026-09-06):
    `bulk_import_products`'s own `ensure_reference` closure matched a raw
    value against both a code and a name column (lower-cased) - reconciled
    here into the ONE body every caller (bulk import, manual create/edit, the
    ESB push) now shares, rather than the closure's separate copy silently
    drifting from this one's code-only match. `code = name = raw value` on
    CREATE, the same convention the closure already used. Returns
    `(id, created)` so a caller can attach a `<kind>_created` warning only
    when it actually made the row.
    """
    value = (code or "").strip()
    if not value:
        raise ValueError("ensure_reference requires a non-blank code")
    existing_id = resolve_master_by_code(db, model, value, company_id)
    if existing_id is None:
        existing_id = resolve_master_by_name(db, model, value, company_id)
    if existing_id is not None:
        return existing_id, False
    if len(value) > REF_CODE_MAX_LEN:
        raise ReferenceTooLong(
            f"{model.__tablename__} value {value!r} is {len(value)} characters; "
            f"the code column holds {REF_CODE_MAX_LEN}"
        )
    code_column, name_column = code_name_columns(model)
    new_id = str(uuid.uuid4())
    kwargs: dict[str, Any] = {
        "id": new_id,
        code_column: value,
        name_column: value,
        "description": AUTO_CREATED_NOTE,
    }
    if hasattr(model, "company_id"):
        kwargs["company_id"] = company_id
    db.add(model(**kwargs))
    db.flush()
    return new_id, True


def resolve_default_uom(db: Session, company_id: Optional[str], settings: Any = None) -> Optional[str]:
    """The unit a product takes when nobody states one - `system_settings.
    default_uom_id` when set, else `EA` (auto-created via `ensure_reference`
    when missing). Same fallback `product_service._get_default_uom_id` uses
    for the manual/xlsx channels, generalised for a caller (the ESB) that
    passes a blank `uom_code` rather than omitting the column."""
    from app.models.product import UnitOfMeasure
    from app.models.user import SystemSetting

    if settings is None:
        settings = db.query(SystemSetting).first()
    configured = getattr(settings, "default_uom_id", None) if settings else None
    if configured:
        # Security review advisory (c): `system_settings` is a single
        # company-agnostic row (LESSONS-LEARNT "system_settings singleton"),
        # so its `default_uom_id` can name a `UnitOfMeasure` belonging to a
        # DIFFERENT company than this record's own anchor - whichever
        # company an admin was viewing when they set it. Validated before
        # use rather than trusted; an id that does not belong to this
        # company (and is not a shared/global row) is treated as no default
        # at all, falling through to the same `ensure_reference`/`EA` path a
        # blank setting already takes.
        valid = (
            db.query(UnitOfMeasure.id)
            .filter(
                UnitOfMeasure.id == configured,
                or_(UnitOfMeasure.company_id == company_id, UnitOfMeasure.company_id.is_(None)),
            )
            .first()
        )
        if valid:
            return configured
    uom_id, _created = ensure_reference(db, UnitOfMeasure, DEFAULT_UOM_CODE, company_id)
    return uom_id


def resolve_default_supplier_id(db: Session, settings: Any) -> Optional[str]:
    """`system_settings.default_product_supplier_id` when set and valid; else
    the oldest supplier by `created_at` - moved from
    `product_service._resolve_default_supplier_for_new_product` (unchanged
    body, reads the row instead of the ORM service's own query for it)."""
    sid = (getattr(settings, "default_product_supplier_id", None) or "").strip() if settings else ""
    if sid:
        supplier = db.query(Supplier).filter(Supplier.id == sid).first()
        if supplier:
            return supplier.id
    oldest = db.query(Supplier).order_by(Supplier.created_at.asc(), Supplier.id.asc()).first()
    return oldest.id if oldest else None


def resolve_standard_lead_time_days(settings: Any) -> int:
    """`system_settings.default_product_standard_lead_time_days`, falling
    back to 90 - moved from `product_service._default_standard_lead_time_days`
    (unchanged body)."""
    try:
        days = int(getattr(settings, "default_product_standard_lead_time_days", None))
    except (TypeError, ValueError):
        days = 90
    return max(0, days)


def link_default_supplier(db: Session, product_id: str, settings: Any) -> None:
    """Upsert the tenant's default-supplier `product_suppliers` row with the
    configured standard lead time (D5) - create-time link, or the lead time
    refreshed on update, exactly as the Excel import's own
    `link_default_supplier` closure does. `settings` is the (possibly `None`)
    `system_settings` row; a no-op when no default supplier can be resolved.
    """
    default_supplier_id = resolve_default_supplier_id(db, settings)
    if not default_supplier_id:
        return
    lead_time_days = resolve_standard_lead_time_days(settings)
    existing = (
        db.query(ProductSupplier)
        .filter(
            ProductSupplier.product_id == product_id,
            ProductSupplier.supplier_id == default_supplier_id,
        )
        .first()
    )
    if existing is not None:
        if existing.standard_lead_time_days != lead_time_days:
            existing.standard_lead_time_days = lead_time_days
            db.flush()
        return
    db.add(
        ProductSupplier(
            product_id=product_id,
            supplier_id=default_supplier_id,
            standard_lead_time_days=lead_time_days,
        )
    )
    db.flush()
