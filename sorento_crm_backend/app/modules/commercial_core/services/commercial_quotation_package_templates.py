"""Quotation package templates from process settings (assignment.quotation_package_templates)."""
from __future__ import annotations

import copy
import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.modules.commercial_core.models_process_config import CommercialProcessSettings

PROCESS_SETTINGS_ID = "default"
QUOTATION_PACKAGE_TEMPLATES_KEY = "quotation_package_templates"


def _new_key() -> str:
    return str(uuid.uuid4())


def _parse_lines(raw_items: Any) -> List[Dict[str, Any]]:
    if not isinstance(raw_items, list):
        return []
    out: List[Dict[str, Any]] = []
    for line in raw_items:
        if not line or not isinstance(line, dict):
            continue
        L = line
        lid = str(L.get("id") or "").strip() or _new_key()
        lname = str(L.get("name") or L.get("item") or "").strip()
        if not lname:
            continue
        qty = L.get("quantity")
        if isinstance(qty, (int, float)):
            qn = float(qty)
        else:
            try:
                qn = float(str(qty or 0))
            except (TypeError, ValueError):
                qn = 0.0
        out.append(
            {
                "id": lid,
                "product_id": str(L.get("product_id") or "").strip() or None,
                "product_code": str(L.get("product_code") or "").strip() or None,
                "name": lname,
                "description": str(L.get("description") or "").strip(),
                "quantity": qn,
                "uom": str(L.get("uom") or "Unit").strip() or "Unit",
            }
        )
    return out


def _parse_templates(raw: Any) -> List[Dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    out: List[Dict[str, Any]] = []
    for item in raw:
        if not item or not isinstance(item, dict):
            continue
        o = item
        tid = str(o.get("id") or "").strip() or _new_key()
        name = str(o.get("name") or "").strip()
        if not name:
            continue
        vd = o.get("validity_days")
        if isinstance(vd, (int, float)):
            validity_days = int(vd)
        else:
            try:
                validity_days = int(str(vd or 30), 10)
            except (TypeError, ValueError):
                validity_days = 30
        terms = str(o.get("terms") or "").strip()
        items = _parse_lines(o.get("items"))
        out.append(
            {
                "id": tid,
                "name": name,
                "validity_days": validity_days,
                "terms": terms,
                "items": items,
            }
        )
    return out


def list_quotation_package_templates(db: Session) -> List[Dict[str, Any]]:
    row = db.query(CommercialProcessSettings).filter(CommercialProcessSettings.id == PROCESS_SETTINGS_ID).first()
    if not row or not isinstance(row.assignment, dict):
        return []
    raw = row.assignment.get(QUOTATION_PACKAGE_TEMPLATES_KEY)
    return _parse_templates(raw)


def get_quotation_package_template_by_id(db: Session, template_id: str) -> Optional[Dict[str, Any]]:
    tid = (template_id or "").strip()
    if not tid:
        return None
    for t in list_quotation_package_templates(db):
        if str(t.get("id")) == tid:
            return copy.deepcopy(t)
    return None


def build_pricing_snapshot_from_package_template(pkg: Dict[str, Any]) -> Dict[str, Any]:
    meta: Dict[str, Any] = {
        "customer_label": "",
        "issued_on": "",
        "salesperson_user_id": "",
        "payment_term_code": "",
        "notes": "",
        "terms_html": str(pkg.get("terms") or ""),
        "quotation_validity_days": str(int(pkg.get("validity_days") or 30)),
        "quotation_package_template_id": str(pkg.get("id") or ""),
        "quotation_package_template_name": str(pkg.get("name") or ""),
    }
    order_items: List[Dict[str, Any]] = []
    for line in pkg.get("items") or []:
        if not isinstance(line, dict):
            continue
        order_items.append(
            {
                "_key": _new_key(),
                "product_id": str(line.get("product_id") or ""),
                "product_code": str(line.get("product_code") or ""),
                "description": str(line.get("description") or line.get("name") or "").strip(),
                "qty": str(line.get("quantity") if line.get("quantity") is not None else "1"),
                "uom_code": str(line.get("uom") or "Unit"),
                "unit_price": "0",
                "discount_pct": "",
                "discount_amt": "",
                "discount_mode": "percent",
                "tax_rate_code": "",
            }
        )
    return {"quotation_meta": meta, "order_items": order_items}
