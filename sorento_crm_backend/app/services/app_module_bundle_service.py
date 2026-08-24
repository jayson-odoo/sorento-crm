"""CRUD for app_module_bundles + resolution for install."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.app_modules import AppModuleBundle, AppModuleCatalog
from app.modules.runtime.module_manifest import MODULE_BUNDLES
from app.services.error_handler import handle_conflict, handle_validation_error

_BUNDLE_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{1,62}$")


def _module_keys_as_list(raw: Any) -> List[str]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(x) for x in raw]
    if isinstance(raw, tuple):
        return [str(x) for x in raw]
    return []


def _catalog_keys(db: Session) -> set[str]:
    return {r[0] for r in db.query(AppModuleCatalog.module_key).all()}


def _validate_module_keys(db: Session, keys: List[str]) -> List[str]:
    """Dedupe preserving order; ensure every key exists in catalog."""
    seen: set[str] = set()
    out: List[str] = []
    for k in keys:
        s = (k or "").strip()
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
    if not out:
        raise handle_validation_error("At least one module_key is required.")
    catalog = _catalog_keys(db)
    unknown = [k for k in out if k not in catalog]
    if unknown:
        raise handle_validation_error(f"Unknown module keys: {', '.join(unknown)}")
    return out


def list_bundles_from_db(db: Session) -> List[Dict[str, Any]]:
    """Bundles for API / UI. Falls back to code defaults if table is empty."""
    rows = (
        db.query(AppModuleBundle)
        .order_by(AppModuleBundle.sort_order.asc().nullslast(), AppModuleBundle.bundle_key)
        .all()
    )
    if not rows:
        return [
            {
                "bundle_key": k,
                "display_name": k.replace("_", " ").title(),
                "module_keys": list(v),
                "sort_order": str(i).zfill(3),
            }
            for i, (k, v) in enumerate(MODULE_BUNDLES.items())
        ]
    out: List[Dict[str, Any]] = []
    for r in rows:
        keys = _module_keys_as_list(getattr(r, "module_keys", None))
        out.append(
            {
                "bundle_key": str(getattr(r, "bundle_key", "")),
                "display_name": str(getattr(r, "display_name", "")),
                "module_keys": keys,
                "sort_order": getattr(r, "sort_order", None),
            }
        )
    return out


def resolve_bundle_module_keys(db: Session, bundle_key: str) -> List[str]:
    """Module keys to pass into install resolver (ordered seed list)."""
    row = (
        db.query(AppModuleBundle)
        .filter(AppModuleBundle.bundle_key == bundle_key)
        .first()
    )
    if row is not None:
        keys = _module_keys_as_list(getattr(row, "module_keys", None))
        if not keys:
            raise handle_validation_error(
                f"Bundle «{bundle_key}» has no modules configured. Edit the bundle or pick another."
            )
        _validate_module_keys(db, keys)
        return keys
    if bundle_key in MODULE_BUNDLES:
        return list(MODULE_BUNDLES[bundle_key])
    raise handle_validation_error(f"Unknown bundle: {bundle_key}")


def create_bundle(
    db: Session,
    *,
    bundle_key: str,
    display_name: str,
    module_keys: List[str],
    sort_order: Optional[str],
) -> AppModuleBundle:
    bk = bundle_key.strip()
    if not _BUNDLE_KEY_RE.match(bk):
        raise handle_validation_error(
            "bundle_key must be 2 - 63 chars: start with a letter, then lowercase letters, digits, or underscores."
        )
    if db.query(AppModuleBundle).filter(AppModuleBundle.bundle_key == bk).first():
        raise handle_conflict(f"Bundle «{bk}» already exists.")
    keys = _validate_module_keys(db, module_keys)
    row = AppModuleBundle(
        bundle_key=bk,
        display_name=display_name.strip()[:255],
        module_keys=keys,
        sort_order=(sort_order.strip()[:16] if sort_order else None),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def update_bundle(
    db: Session,
    bundle_key: str,
    *,
    display_name: Optional[str] = None,
    module_keys: Optional[List[str]] = None,
    sort_order: Optional[str] = None,
) -> AppModuleBundle:
    row = (
        db.query(AppModuleBundle)
        .filter(AppModuleBundle.bundle_key == bundle_key)
        .first()
    )
    if not row:
        raise handle_validation_error(f"Unknown bundle: {bundle_key}")
    if display_name is None and module_keys is None and sort_order is None:
        raise handle_validation_error("Provide at least one field to update.")
    if display_name is not None:
        dn = display_name.strip()
        if not dn:
            raise handle_validation_error("display_name cannot be empty.")
        setattr(row, "display_name", dn[:255])
    if module_keys is not None:
        setattr(row, "module_keys", _validate_module_keys(db, module_keys))
    if sort_order is not None:
        so = sort_order.strip()
        setattr(row, "sort_order", so[:16] if so else None)
    db.commit()
    db.refresh(row)
    return row


def delete_bundle(db: Session, bundle_key: str) -> None:
    row = (
        db.query(AppModuleBundle)
        .filter(AppModuleBundle.bundle_key == bundle_key)
        .first()
    )
    if not row:
        raise handle_validation_error(f"Unknown bundle: {bundle_key}")
    db.delete(row)
    db.commit()
