"""After-sales P2: the products on a service job and the warranty answer for them.

A line is a catalogue product plus the facts the policy needs (kind, purchase date, defect). The kind is
suggested from the kind rules when CS does not pick one, and stored; the verdicts are never stored, they
are computed from the policy in force whenever they are read.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.lookup import LookupOption
from app.models.product import Product, ProductCategory
from app.models.service_jobs import ServiceJobProduct
from app.models.warranty import WarrantyProductKind
from app.schemas.service_job_products import ServiceJobProductCreate, ServiceJobProductUpdate
from app.services import warranty_service
from app.services.error_handler import handle_not_found, handle_unprocessable
from app.services.service_job_service import _valid_uuid, get_row
from app.services.warranty_config_service import defect_ids_are_valid

SUMMARY_ORDER = ("covered", "partly_covered", "not_covered", "unknown")

_BAD = {
    warranty_service.VERDICT_EXPIRED,
    warranty_service.VERDICT_DEFECT_NOT_COVERED,
    warranty_service.VERDICT_NO_TERM,
}


def summarize(verdict_lines: Sequence[Sequence[warranty_service.WarrantyVerdict]]) -> Optional[str]:
    """One word for a job over all its lines; None when it has none."""
    verdicts = [v.verdict for line in verdict_lines for v in line]
    if not verdicts:
        return None
    covered = sum(1 for v in verdicts if v == warranty_service.VERDICT_COVERED)
    if covered == len(verdicts):
        return "covered"
    if covered:
        return "partly_covered"
    return "not_covered" if any(v in _BAD for v in verdicts) else "unknown"


def _lines_query(db: Session):
    return (
        db.query(ServiceJobProduct, Product, WarrantyProductKind, LookupOption)
        .outerjoin(Product, Product.id == ServiceJobProduct.product_id)
        .outerjoin(WarrantyProductKind, WarrantyProductKind.id == ServiceJobProduct.kind_id)
        .outerjoin(LookupOption, LookupOption.id == ServiceJobProduct.defect_type_id)
    )


def _order():
    return (ServiceJobProduct.sort_order, ServiceJobProduct.created_at, ServiceJobProduct.id)


def _serialize(row: Tuple) -> Dict[str, Any]:
    line, product, kind, option = row
    return {
        "id": line.id,
        "service_job_id": line.service_job_id,
        "product_id": line.product_id,
        "product_code": product.product_code if product is not None else None,
        "product_name": product.product_name if product is not None else None,
        "kind_id": line.kind_id,
        "kind_name": kind.name if kind is not None else None,
        "purchase_date": line.purchase_date,
        "defect_type_id": line.defect_type_id,
        "defect_label": option.label if option is not None else None,
        "sort_order": line.sort_order,
    }


def list_lines(db: Session, job_id: str) -> List[Dict[str, Any]]:
    job = get_row(db, job_id)[0]
    rows = _lines_query(db).filter(ServiceJobProduct.service_job_id == job.id).order_by(*_order()).all()
    return [_serialize(r) for r in rows]


def _one(db: Session, job_id: str, line_id: str) -> Tuple:
    job = get_row(db, job_id)[0]
    row = (
        _lines_query(db)
        .filter(ServiceJobProduct.id == str(line_id), ServiceJobProduct.service_job_id == job.id)
        .first()
        if _valid_uuid(line_id)
        else None
    )
    if row is None:
        raise handle_not_found("Service job product", str(line_id))
    return row


def _check_purchase_date(value: Optional[date]) -> None:
    if value is not None and value > warranty_service.warranty_today():
        raise handle_unprocessable("Purchase date cannot be in the future.")


def _check_defect(db: Session, defect_type_id: Optional[str]) -> None:
    if defect_type_id and not defect_ids_are_valid(db, [defect_type_id]):
        raise handle_unprocessable("defect_type_id: not a defect type.")


def _check_kind(db: Session, kind_id: Optional[str]) -> None:
    kind = (
        db.query(WarrantyProductKind).filter(WarrantyProductKind.id == str(kind_id)).first()
        if kind_id and _valid_uuid(kind_id)
        else None
    )
    if kind is None:
        raise handle_unprocessable("kind_id: kind not found.")
    if not kind.is_active:
        raise handle_unprocessable("kind_id: that kind is archived.")


def add_line(db: Session, job_id: str, payload: ServiceJobProductCreate) -> Dict[str, Any]:
    job = get_row(db, job_id)[0]
    values = payload.model_dump(exclude_unset=True)
    product_id = values.get("product_id")
    found = (
        db.query(Product, ProductCategory.category_code)
        .outerjoin(ProductCategory, ProductCategory.id == Product.category_id)
        .filter(Product.id == str(product_id), Product.company_id == job.company_id)
        .first()
        if product_id and _valid_uuid(product_id)
        else None
    )
    if found is None:
        raise handle_unprocessable("product_id: product not found.")
    product, category_code = found
    _check_purchase_date(values.get("purchase_date"))
    _check_defect(db, values.get("defect_type_id"))
    kind_id = values.get("kind_id") or None
    if kind_id:
        _check_kind(db, kind_id)
    else:
        suggested = warranty_service.resolve_kind(
            db, product_code=product.product_code, category_code=category_code, product_name=product.product_name
        )
        kind_id = suggested.id if suggested is not None else None
    position = db.query(func.count(ServiceJobProduct.id)).filter(ServiceJobProduct.service_job_id == job.id).scalar() or 0
    line = ServiceJobProduct(
        id=str(uuid.uuid4()),
        service_job_id=job.id,
        product_id=product.id,
        kind_id=kind_id,
        purchase_date=values.get("purchase_date"),
        defect_type_id=values.get("defect_type_id") or None,
        sort_order=position,
        company_id=job.company_id,
    )
    db.add(line)
    db.commit()
    return _serialize(_one(db, job.id, line.id))


def update_line(db: Session, job_id: str, line_id: str, payload: ServiceJobProductUpdate) -> Dict[str, Any]:
    line = _one(db, job_id, line_id)[0]
    values = payload.model_dump(exclude_unset=True)
    if "purchase_date" in values:
        _check_purchase_date(values["purchase_date"])
    if "defect_type_id" in values:
        _check_defect(db, values["defect_type_id"])
    if "kind_id" in values:
        # Keeping the kind it already has is always fine, even if archived since.
        if values["kind_id"] and values["kind_id"] != line.kind_id:
            _check_kind(db, values["kind_id"])
        values["kind_id"] = values["kind_id"] or None
    if "defect_type_id" in values:
        values["defect_type_id"] = values["defect_type_id"] or None
    for key, value in values.items():
        setattr(line, key, value)
    line.updated_at = datetime.utcnow()
    db.commit()
    return _serialize(_one(db, job_id, line_id))


def delete_line(db: Session, job_id: str, line_id: str) -> Dict[str, str]:
    line = _one(db, job_id, line_id)[0]
    db.delete(line)
    db.commit()
    return {"message": "Service job product deleted successfully"}


# ------------------------------------------------------------------ the warranty answer


def _verdict_dict(v: warranty_service.WarrantyVerdict) -> Dict[str, Any]:
    return {
        "part_name": v.part_name,
        "verdict": v.verdict,
        "expiry": v.expiry,
        "reason": v.reason,
        "is_lifetime": v.is_lifetime,
        "installation_included": v.installation_included,
        "policy_version": v.policy_version,
    }


def _verdicts_for(db: Session, lines: Sequence[ServiceJobProduct]) -> Dict[str, List[warranty_service.WarrantyVerdict]]:
    """line id -> verdicts, one batched resolution per company."""
    by_company: Dict[str, List[ServiceJobProduct]] = {}
    for line in lines:
        by_company.setdefault(line.company_id, []).append(line)
    out: Dict[str, List[warranty_service.WarrantyVerdict]] = {}
    for company_id, group in by_company.items():
        results = warranty_service.resolve_lines(
            db, [(l.kind_id, l.purchase_date, l.defect_type_id) for l in group], company_id=company_id
        )
        out.update({l.id: r for l, r in zip(group, results)})
    return out


def warranty_for_job(db: Session, job_id: str) -> List[Dict[str, Any]]:
    rows = _lines_query(db).filter(ServiceJobProduct.service_job_id == job_id).order_by(*_order()).all()
    verdicts = _verdicts_for(db, [r[0] for r in rows])
    out = []
    for row in rows:
        data = _serialize(row)
        out.append(
            {
                "id": data["id"],
                "product_code": data["product_code"],
                "product_name": data["product_name"],
                "kind_name": data["kind_name"],
                "purchase_date": data["purchase_date"],
                "defect_label": data["defect_label"],
                "verdicts": [_verdict_dict(v) for v in verdicts[row[0].id]],
            }
        )
    return out


def summaries_for_jobs(db: Session, job_ids: Sequence[str]) -> Dict[str, Optional[str]]:
    """job id -> warranty summary (jobs without lines are absent)."""
    if not job_ids:
        return {}
    lines = db.query(ServiceJobProduct).filter(ServiceJobProduct.service_job_id.in_(list(job_ids))).all()
    verdicts = _verdicts_for(db, lines)
    per_job: Dict[str, List[List[warranty_service.WarrantyVerdict]]] = {}
    for line in lines:
        per_job.setdefault(line.service_job_id, []).append(verdicts[line.id])
    return {job_id: summarize(v) for job_id, v in per_job.items()}
