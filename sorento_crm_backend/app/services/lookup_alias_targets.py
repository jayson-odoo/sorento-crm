"""What the options of an alias lookup set may name (LOOKUP-EMBED-CENTRAL, AC-LEC-24).

An alias set's option `value` is the thing the keywords are synonyms for, so it must be one of these targets;
an option whose value is not (the type was renamed or deleted) is orphaned and its keywords match nothing.
"""
from __future__ import annotations

from sqlalchemy.orm import Session


def _attachment_types(db: Session) -> list[dict]:
    from app.models.resources import AttachmentType

    rows = db.query(AttachmentType.type_name).filter(AttachmentType.type_name.isnot(None)).order_by(AttachmentType.type_name).all()
    return [{"value": n, "label": n} for (n,) in rows if n and n.strip()]


def _brands(db: Session) -> list[dict]:
    from sqlalchemy import select

    from app.models.product import Brand

    # Core select: an alias set is shared across companies, so its targets are every brand code, not the viewer's.
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


def alias_targets(db: Session, set_key: str) -> list[dict] | None:
    """[{value, label}] for an alias set, None for any other set."""
    loader = ALIAS_SET_TARGETS.get(set_key)
    return loader(db) if loader else None
