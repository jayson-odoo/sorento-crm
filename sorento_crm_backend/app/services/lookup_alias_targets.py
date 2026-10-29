"""What the options of an alias lookup set may name (LOOKUP-EMBED-CENTRAL, AC-LEC-24).

An alias set's option `value` is the thing the keywords are synonyms for, so it must be one of these targets;
an option whose value is not (the type was renamed or deleted) is orphaned and its keywords match nothing.
"""
from __future__ import annotations

from sqlalchemy.orm import Session


def _attachment_types(db: Session) -> list[dict]:
    """Both ways an option may key a type: its name and its code."""
    from app.models.resources import AttachmentType

    rows = db.query(AttachmentType.code, AttachmentType.type_name).order_by(AttachmentType.type_name).all()
    out: dict[str, dict] = {}
    for code, name in rows:
        if name and name.strip():
            out.setdefault(name.casefold(), {"value": name, "label": name})
        if code and code.strip():
            out.setdefault(code.casefold(), {"value": code, "label": f"{code} ({name})" if name else code})
    return list(out.values())


def _brands(db: Session, scoped: bool = True) -> list[dict]:
    """Brand codes for the picker: the caller's companies through the standard ORM filter. `scoped=False` (the orphan
    check) lists every brand code, so an option for a brand of another company is not called orphaned."""
    from sqlalchemy import select

    from app.models.product import Brand

    if scoped:
        rows = db.query(Brand.brand_code, Brand.brand_name).filter(Brand.brand_code.isnot(None)).order_by(Brand.brand_code).all()
    else:
        t = Brand.__table__
        rows = db.execute(select(t.c.brand_code, t.c.brand_name).where(t.c.brand_code.isnot(None)).order_by(t.c.brand_code)).all()
    return [{"value": code, "label": f"{name} ({code})" if name else code} for code, name in rows if code and code.strip()]


def _sales_channels(db: Session) -> list[dict]:
    from app.services.reports.ask import SALES_CHANNELS

    return [{"value": c, "label": c} for c in SALES_CHANNELS]


#: set_key -> the loader of its targets. A set key not here is not an alias set.
ALIAS_SET_TARGETS = {
    "attachment_type_alias": _attachment_types,
    "brand_alias": _brands,
    "sales_channel_alias": _sales_channels,
}


def is_alias_set(set_key: str) -> bool:
    return set_key in ALIAS_SET_TARGETS


def alias_targets(db: Session, set_key: str, *, scoped: bool = True) -> list[dict] | None:
    """[{value, label}] for an alias set, None for any other set. `scoped=False` ignores the caller's company scope
    (for the orphan check; only brands are company-scoped)."""
    loader = ALIAS_SET_TARGETS.get(set_key)
    if loader is None:
        return None
    return loader(db, scoped) if loader is _brands else loader(db)
