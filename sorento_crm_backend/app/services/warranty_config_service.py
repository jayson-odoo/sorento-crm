"""After-sales P2: configuration of the warranty policy, its terms, the product kinds and kind rules.

Rules live here; the routers only gate permissions and shape HTTP. Every write commits and is audited by
the model listeners (a term's history rolls up to its policy). Policies are company-scoped by the scope
layer; kinds and rules are shared.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy import asc, desc, func, or_, text
from sqlalchemy.orm import Session

from app.models.base import get_company_scope
from app.models.lookup import LookupOption, LookupSet
from app.models.product import Product, ProductCategory
from app.models.warranty import WarrantyKindRule, WarrantyPolicy, WarrantyProductKind, WarrantyTerm
from app.schemas.warranty_config import (
    KindCreate,
    KindRuleCreate,
    KindRuleUpdate,
    KindUpdate,
    PolicyCreate,
    PolicyUpdate,
    SupersedeRequest,
    TermCreate,
    TermUpdate,
)
from app.services.error_handler import AppException, handle_conflict, handle_not_found, handle_unprocessable
from app.services.warranty_service import KIND_RULE_MATCH_TYPES, dmy, rank_kind_matches
from app.services.warranty_seed import DEFECT_TYPE_SET_KEY


def _valid_uuid(value: Any) -> bool:
    try:
        uuid.UUID(str(value))
        return True
    except (TypeError, ValueError):
        return False


def _now() -> datetime:
    return datetime.utcnow()


def _required(value: Optional[str], label: str) -> str:
    cleaned = (value or "").strip()
    if not cleaned:
        raise handle_unprocessable(f"{label} is required.")
    return cleaned


def _page(q, order, page: int, limit: int, serialize) -> Dict[str, Any]:
    total = q.count()
    rows = q.order_by(*order).offset((page - 1) * limit).limit(limit).all()
    return {
        "data": [serialize(r) for r in rows],
        "pagination": {"total": total, "page": page, "limit": limit},
        "empty": total == 0,
    }


def _direction(column, direction: Optional[str]):
    return desc(column) if (direction or "asc").lower() == "desc" else asc(column)


def _company_id(db: Session) -> Optional[str]:
    from app.services.company_scope import resolve_write_company_id

    return resolve_write_company_id(get_company_scope(db), ambiguous=None)


# ------------------------------------------------------------------ policies


def _policy_row(db: Session, policy_id: str) -> WarrantyPolicy:
    row = (
        db.query(WarrantyPolicy).filter(WarrantyPolicy.id == str(policy_id)).first()
        if _valid_uuid(policy_id)
        else None
    )
    if row is None:
        raise handle_not_found("Warranty policy", str(policy_id))
    return row


def _term_count(db: Session, policy_id: str) -> int:
    return db.query(func.count(WarrantyTerm.id)).filter(WarrantyTerm.policy_id == policy_id).scalar() or 0


def _policy_dict(row: WarrantyPolicy, term_count: int) -> Dict[str, Any]:
    return {
        "id": row.id,
        "version": row.version,
        "effective_from": row.effective_from,
        "effective_to": row.effective_to,
        "policy_text": row.policy_text,
        "term_count": term_count,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def get_policy(db: Session, policy_id: str) -> Dict[str, Any]:
    row = _policy_row(db, policy_id)
    return _policy_dict(row, _term_count(db, row.id))


def list_policies(db: Session, *, page: int, limit: int, query: Optional[str], sort: Optional[str], direction: str):
    counts = (
        db.query(WarrantyTerm.policy_id.label("pid"), func.count(WarrantyTerm.id).label("n"))
        .group_by(WarrantyTerm.policy_id)
        .subquery()
    )
    q = db.query(WarrantyPolicy, func.coalesce(counts.c.n, 0)).outerjoin(counts, counts.c.pid == WarrantyPolicy.id)
    if query and query.strip():
        q = q.filter(WarrantyPolicy.version.ilike(f"%{query.strip()}%"))
    sorts = {
        "version": WarrantyPolicy.version,
        "effective_from": WarrantyPolicy.effective_from,
        "effective_to": WarrantyPolicy.effective_to,
    }
    column = sorts.get(sort or "", WarrantyPolicy.effective_from)
    order = _direction(column, direction if sort else "desc")
    return _page(q, [order.nulls_last(), WarrantyPolicy.id], page, limit, lambda r: _policy_dict(r[0], r[1]))


def _check_window(start: date, end: Optional[date]) -> None:
    if end is not None and end < start:
        raise handle_unprocessable("effective_to must not be before effective_from.")


def _check_overlap(
    db: Session, start: date, end: Optional[date], *, company_id: Optional[str], skip: Sequence[str] = ()
) -> None:
    q = db.query(WarrantyPolicy)
    if company_id:
        q = q.filter(WarrantyPolicy.company_id == company_id)
    for other in q.all():
        if other.id in skip:
            continue
        if other.effective_from <= (end or date.max) and start <= (other.effective_to or date.max):
            until = dmy(other.effective_to) if other.effective_to else "no end date"
            raise handle_conflict(
                f"These dates overlap policy {other.version} ({dmy(other.effective_from)} to {until})."
            )


def _check_version_free(db: Session, version: str, *, company_id: Optional[str], skip: Optional[str] = None) -> None:
    q = db.query(WarrantyPolicy.id).filter(WarrantyPolicy.version == version)
    if company_id:
        q = q.filter(WarrantyPolicy.company_id == company_id)
    if skip:
        q = q.filter(WarrantyPolicy.id != skip)
    if q.first() is not None:
        raise handle_conflict(f"A policy with version {version} already exists.")


def create_policy(db: Session, payload: PolicyCreate) -> Dict[str, Any]:
    version = _required(payload.version, "version")[:32]
    _check_window(payload.effective_from, payload.effective_to)
    company_id = _company_id(db)
    _check_version_free(db, version, company_id=company_id)
    _check_overlap(db, payload.effective_from, payload.effective_to, company_id=company_id)
    row = WarrantyPolicy(
        id=str(uuid.uuid4()),
        version=version,
        effective_from=payload.effective_from,
        effective_to=payload.effective_to,
        policy_text=payload.policy_text,
        **({"company_id": company_id} if company_id else {}),
    )
    db.add(row)
    db.commit()
    return get_policy(db, row.id)


def update_policy(db: Session, policy_id: str, payload: PolicyUpdate) -> Dict[str, Any]:
    row = _policy_row(db, policy_id)
    values = payload.model_dump(exclude_unset=True)
    if "version" in values:
        values["version"] = _required(values["version"], "version")[:32]
    if values.get("effective_from") is None:
        values.pop("effective_from", None)
    start = values.get("effective_from", row.effective_from)
    end = values["effective_to"] if "effective_to" in values else row.effective_to
    _check_window(start, end)
    company_id = row.company_id
    if "version" in values and values["version"] != row.version:
        _check_version_free(db, values["version"], company_id=company_id, skip=row.id)
    if start != row.effective_from or end != row.effective_to:
        _check_overlap(db, start, end, company_id=company_id, skip=(row.id,))
    for key, value in values.items():
        setattr(row, key, value)
    row.updated_at = _now()
    db.commit()
    return get_policy(db, row.id)


def delete_policy(db: Session, policy_id: str) -> Dict[str, str]:
    row = _policy_row(db, policy_id)
    db.delete(row)  # its terms go with it (ON DELETE CASCADE)
    db.commit()
    return {"message": "Warranty policy deleted successfully"}


def supersede_policy(db: Session, policy_id: str, payload: SupersedeRequest) -> Dict[str, Any]:
    """Close an open-ended policy the day before a new one starts and create the new one, in one commit."""
    old = _policy_row(db, policy_id)
    version = _required(payload.version, "version")[:32]
    if old.effective_to is not None:
        raise handle_conflict(f"Policy {old.version} is already closed.")
    if payload.effective_from <= old.effective_from:
        raise handle_unprocessable(f"The new policy must start after {dmy(old.effective_from)}.")
    _check_version_free(db, version, company_id=old.company_id)
    _check_overlap(db, payload.effective_from, None, company_id=old.company_id, skip=(old.id,))
    new = WarrantyPolicy(
        id=str(uuid.uuid4()),
        version=version,
        effective_from=payload.effective_from,
        effective_to=None,
        policy_text=payload.policy_text,
        company_id=old.company_id,
    )
    old.effective_to = payload.effective_from - timedelta(days=1)
    old.updated_at = _now()
    db.add(new)
    db.commit()
    return {"closed": get_policy(db, old.id), "created": get_policy(db, new.id)}


# ------------------------------------------------------------------ terms


def _term_dict(row: WarrantyTerm) -> Dict[str, Any]:
    return {
        "id": row.id,
        "policy_id": row.policy_id,
        "kind_id": row.kind_id,
        "part_name": row.part_name,
        "duration_months": row.duration_months,
        "is_lifetime": bool(row.is_lifetime),
        "covered_defect_type_ids": list(row.covered_defect_type_ids) if row.covered_defect_type_ids else None,
        "installation_included": bool(row.installation_included),
        "qualifications": row.qualifications,
        "exclusions": row.exclusions,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _term_row(db: Session, term_id: str) -> WarrantyTerm:
    row = None
    if _valid_uuid(term_id):
        # Reached through its policy, which is the company-scoped table.
        row = (
            db.query(WarrantyTerm)
            .join(WarrantyPolicy, WarrantyPolicy.id == WarrantyTerm.policy_id)
            .filter(WarrantyTerm.id == str(term_id))
            .first()
        )
    if row is None:
        raise handle_not_found("Warranty term", str(term_id))
    return row


def list_terms(db: Session, policy_id: str) -> List[Dict[str, Any]]:
    _policy_row(db, policy_id)
    rows = db.query(WarrantyTerm).filter(WarrantyTerm.policy_id == str(policy_id)).order_by(WarrantyTerm.part_name, WarrantyTerm.id).all()
    return [_term_dict(r) for r in rows]


def defect_ids_are_valid(db: Session, ids: Sequence[str]) -> bool:
    wanted = {str(i) for i in ids}
    if not all(_valid_uuid(i) for i in wanted):
        return False
    found = (
        db.query(LookupOption.id)
        .join(LookupSet, LookupSet.id == LookupOption.set_id)
        .filter(LookupSet.set_key == DEFECT_TYPE_SET_KEY, LookupOption.id.in_(wanted))
        .all()
    )
    return len(found) == len(wanted)


def _check_term(db: Session, values: Dict[str, Any]) -> None:
    months, lifetime = values.get("duration_months"), bool(values.get("is_lifetime"))
    if lifetime and months is not None:
        raise handle_unprocessable("A lifetime term has no duration.")
    if not lifetime and (months is None or months <= 0):
        raise handle_unprocessable("A term needs a duration in months, or lifetime cover.")
    defects = values.get("covered_defect_type_ids")
    if defects and not defect_ids_are_valid(db, defects):
        raise handle_unprocessable("covered_defect_type_ids: each must be a defect type.")


def _check_term_free(db: Session, policy_id: str, kind_id: str, part: str, skip: Optional[str] = None) -> None:
    q = db.query(WarrantyTerm.id).filter(
        WarrantyTerm.policy_id == policy_id, WarrantyTerm.kind_id == kind_id, WarrantyTerm.part_name == part
    )
    if skip:
        q = q.filter(WarrantyTerm.id != skip)
    if q.first() is not None:
        raise handle_conflict(f"This policy already has a term for {part} on that kind.")


def create_term(db: Session, payload: TermCreate) -> Dict[str, Any]:
    policy = _policy_row(db, payload.policy_id)
    if not _valid_uuid(payload.kind_id) or db.query(WarrantyProductKind.id).filter(WarrantyProductKind.id == payload.kind_id).first() is None:
        raise handle_unprocessable("kind_id: kind not found.")
    part = _required(payload.part_name, "part_name")[:120]
    values = payload.model_dump()
    _check_term(db, values)
    _check_term_free(db, policy.id, payload.kind_id, part)
    row = WarrantyTerm(
        id=str(uuid.uuid4()),
        policy_id=policy.id,
        kind_id=payload.kind_id,
        part_name=part,
        duration_months=payload.duration_months,
        is_lifetime=payload.is_lifetime,
        covered_defect_type_ids=payload.covered_defect_type_ids or None,
        installation_included=payload.installation_included,
        qualifications=payload.qualifications,
        exclusions=payload.exclusions,
    )
    db.add(row)
    db.commit()
    return _term_dict(row)


def update_term(db: Session, term_id: str, payload: TermUpdate) -> Dict[str, Any]:
    row = _term_row(db, term_id)
    values = payload.model_dump(exclude_unset=True)
    for key in ("part_name", "is_lifetime", "installation_included"):
        if key in values and values[key] is None:
            values.pop(key)
    if "part_name" in values:
        values["part_name"] = _required(values["part_name"], "part_name")[:120]
        if values["part_name"] != row.part_name:
            _check_term_free(db, row.policy_id, row.kind_id, values["part_name"], skip=row.id)
    merged = {
        "duration_months": values["duration_months"] if "duration_months" in values else row.duration_months,
        "is_lifetime": values.get("is_lifetime", row.is_lifetime),
        "covered_defect_type_ids": values.get("covered_defect_type_ids") if "covered_defect_type_ids" in values else None,
    }
    _check_term(db, merged)
    if "covered_defect_type_ids" in values:
        values["covered_defect_type_ids"] = values["covered_defect_type_ids"] or None
    for key, value in values.items():
        setattr(row, key, value)
    row.updated_at = _now()
    db.commit()
    return _term_dict(row)


def delete_term(db: Session, term_id: str) -> Dict[str, str]:
    row = _term_row(db, term_id)
    db.delete(row)
    db.commit()
    return {"message": "Warranty term deleted successfully"}


# ------------------------------------------------------------------ kinds


def _kind_row(db: Session, kind_id: str) -> WarrantyProductKind:
    row = (
        db.query(WarrantyProductKind).filter(WarrantyProductKind.id == str(kind_id)).first()
        if _valid_uuid(kind_id)
        else None
    )
    if row is None:
        raise handle_not_found("Warranty kind", str(kind_id))
    return row


def _kind_counts(db: Session, kind_ids: Sequence[str]) -> Dict[str, Dict[str, int]]:
    out = {k: {"rule_count": 0, "term_count": 0} for k in kind_ids}
    if not kind_ids:
        return out
    for key, table in (("rule_count", "warranty_kind_rules"), ("term_count", "warranty_terms")):
        for kind_id, n in db.execute(
            text(f"select kind_id::text, count(*) from {table} where kind_id::text = any(:ids) group by kind_id"),
            {"ids": list(kind_ids)},
        ):
            out[kind_id][key] = n
    return out


def _kind_dict(row: WarrantyProductKind, counts: Dict[str, int]) -> Dict[str, Any]:
    return {
        "id": row.id,
        "code": row.code,
        "name": row.name,
        "sort_order": row.sort_order,
        "is_active": bool(row.is_active),
        "rule_count": counts["rule_count"],
        "term_count": counts["term_count"],
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def get_kind(db: Session, kind_id: str) -> Dict[str, Any]:
    row = _kind_row(db, kind_id)
    return _kind_dict(row, _kind_counts(db, [row.id])[row.id])


def list_kinds(
    db: Session,
    *,
    page: int,
    limit: int,
    query: Optional[str],
    sort: Optional[str],
    direction: str,
    active_values: Optional[Sequence[str]] = None,
    has_no_rule: bool = False,
) -> Dict[str, Any]:
    rule_n = (
        db.query(func.count(WarrantyKindRule.id))
        .filter(WarrantyKindRule.kind_id == WarrantyProductKind.id)
        .correlate(WarrantyProductKind)
        .scalar_subquery()
    )
    term_n = (
        db.query(func.count(WarrantyTerm.id))
        .filter(WarrantyTerm.kind_id == WarrantyProductKind.id)
        .correlate(WarrantyProductKind)
        .scalar_subquery()
    )
    q = db.query(WarrantyProductKind, rule_n, term_n)
    if query and query.strip():
        like = f"%{query.strip()}%"
        q = q.filter(or_(WarrantyProductKind.code.ilike(like), WarrantyProductKind.name.ilike(like)))
    flags = {v.strip().lower() == "true" for v in (active_values or []) if v.strip().lower() in ("true", "false")}
    if flags:
        q = q.filter(WarrantyProductKind.is_active.in_(flags))
    if has_no_rule:
        q = q.filter(rule_n == 0)
    sorts = {
        "code": WarrantyProductKind.code,
        "name": WarrantyProductKind.name,
        "is_active": WarrantyProductKind.is_active,
        "rule_count": rule_n,
        "term_count": term_n,
        "sort_order": WarrantyProductKind.sort_order,
    }
    column = sorts.get(sort or "", WarrantyProductKind.sort_order)
    order = _direction(column, direction)
    return _page(
        q,
        [order, WarrantyProductKind.code],
        page,
        limit,
        lambda r: _kind_dict(r[0], {"rule_count": r[1], "term_count": r[2]}),
    )


def create_kind(db: Session, payload: KindCreate) -> Dict[str, Any]:
    code = _required(payload.code, "code")[:64]
    name = _required(payload.name, "name")[:255]
    if db.query(WarrantyProductKind.id).filter(WarrantyProductKind.code == code).first() is not None:
        raise handle_conflict(f"A kind with code {code} already exists.")
    row = WarrantyProductKind(
        id=str(uuid.uuid4()), code=code, name=name, sort_order=payload.sort_order, is_active=payload.is_active
    )
    db.add(row)
    db.commit()
    return get_kind(db, row.id)


def update_kind(db: Session, kind_id: str, payload: KindUpdate) -> Dict[str, Any]:
    row = _kind_row(db, kind_id)
    values = payload.model_dump(exclude_unset=True)
    for key in ("code", "name", "sort_order", "is_active"):
        if key in values and values[key] is None:
            values.pop(key)
    if "code" in values:
        values["code"] = _required(values["code"], "code")[:64]
        taken = db.query(WarrantyProductKind.id).filter(
            WarrantyProductKind.code == values["code"], WarrantyProductKind.id != row.id
        )
        if taken.first() is not None:
            raise handle_conflict(f"A kind with code {values['code']} already exists.")
    if "name" in values:
        values["name"] = _required(values["name"], "name")[:255]
    for key, value in values.items():
        setattr(row, key, value)
    row.updated_at = _now()
    db.commit()
    return get_kind(db, row.id)


def delete_kind(db: Session, kind_id: str) -> Dict[str, str]:
    row = _kind_row(db, kind_id)
    counts = _kind_counts(db, [row.id])[row.id]
    # Raw SQL: a kind is shared, and a job line of another company is invisible to the scoped ORM.
    jobs = db.execute(
        text("select count(*) from service_job_products where kind_id::text = :k"), {"k": row.id}
    ).scalar() or 0
    used = [
        f"{n} {label}{'s' if n != 1 else ''}"
        for n, label in ((counts["term_count"], "term"), (counts["rule_count"], "rule"), (jobs, "job line"))
        if n
    ]
    if used:
        raise handle_conflict(f"This kind is in use by {', '.join(used)}. Archive it instead.")
    db.delete(row)
    db.commit()
    return {"message": "Warranty kind deleted successfully"}


# ------------------------------------------------------------------ kind rules


def _rule_dict(rule: WarrantyKindRule, kind: WarrantyProductKind) -> Dict[str, Any]:
    return {
        "id": rule.id,
        "kind_id": rule.kind_id,
        "kind_code": kind.code,
        "kind_name": kind.name,
        "match_type": rule.match_type,
        "match_value": rule.match_value,
        "priority": rule.priority,
        "created_at": rule.created_at,
        "updated_at": rule.updated_at,
    }


def _rule_row(db: Session, rule_id: str) -> WarrantyKindRule:
    row = (
        db.query(WarrantyKindRule).filter(WarrantyKindRule.id == str(rule_id)).first()
        if _valid_uuid(rule_id)
        else None
    )
    if row is None:
        raise handle_not_found("Warranty kind rule", str(rule_id))
    return row


def _rule_with_kind(db: Session, rule: WarrantyKindRule) -> Dict[str, Any]:
    return _rule_dict(rule, _kind_row(db, rule.kind_id))


def list_rules(
    db: Session,
    *,
    page: int,
    limit: int,
    query: Optional[str],
    sort: Optional[str],
    direction: str,
    kind_ids: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    q = db.query(WarrantyKindRule, WarrantyProductKind).join(
        WarrantyProductKind, WarrantyProductKind.id == WarrantyKindRule.kind_id
    )
    if kind_ids:
        q = q.filter(WarrantyKindRule.kind_id.in_(list(kind_ids)))
    if query and query.strip():
        like = f"%{query.strip()}%"
        q = q.filter(or_(WarrantyKindRule.match_value.ilike(like), WarrantyProductKind.name.ilike(like)))
    sorts = {
        "kind": WarrantyProductKind.name,
        "match_type": WarrantyKindRule.match_type,
        "match_value": WarrantyKindRule.match_value,
        "priority": WarrantyKindRule.priority,
    }
    column = sorts.get(sort or "", WarrantyProductKind.name)
    order = _direction(column, direction)
    return _page(q, [order, WarrantyKindRule.id], page, limit, lambda r: _rule_dict(r[0], r[1]))


def _check_rule(match_type: Optional[str], match_value: Optional[str]) -> tuple:
    kind = (match_type or "").strip().lower()
    if kind not in KIND_RULE_MATCH_TYPES:
        raise handle_unprocessable(f"match_type must be one of {', '.join(KIND_RULE_MATCH_TYPES)}.")
    return kind, _required(match_value, "match_value")


def _check_kind_exists(db: Session, kind_id: str) -> None:
    if not _valid_uuid(kind_id) or db.query(WarrantyProductKind.id).filter(WarrantyProductKind.id == str(kind_id)).first() is None:
        raise handle_unprocessable("kind_id: kind not found.")


def create_rule(db: Session, payload: KindRuleCreate) -> Dict[str, Any]:
    match_type, match_value = _check_rule(payload.match_type, payload.match_value)
    _check_kind_exists(db, payload.kind_id)
    row = WarrantyKindRule(
        id=str(uuid.uuid4()),
        kind_id=payload.kind_id,
        match_type=match_type,
        match_value=match_value,
        priority=payload.priority,
    )
    db.add(row)
    db.commit()
    return _rule_with_kind(db, row)


def update_rule(db: Session, rule_id: str, payload: KindRuleUpdate) -> Dict[str, Any]:
    row = _rule_row(db, rule_id)
    values = payload.model_dump(exclude_unset=True)
    for key in ("kind_id", "match_type", "match_value", "priority"):
        if key in values and values[key] is None:
            values.pop(key)
    if "match_type" in values or "match_value" in values:
        values["match_type"], values["match_value"] = _check_rule(
            values.get("match_type", row.match_type), values.get("match_value", row.match_value)
        )
    if "kind_id" in values:
        _check_kind_exists(db, values["kind_id"])
    for key, value in values.items():
        setattr(row, key, value)
    row.updated_at = _now()
    db.commit()
    return _rule_with_kind(db, row)


def delete_rule(db: Session, rule_id: str) -> Dict[str, str]:
    row = _rule_row(db, rule_id)
    db.delete(row)
    db.commit()
    return {"message": "Warranty kind rule deleted successfully"}


def try_rules(db: Session, product_id: str) -> Dict[str, Any]:
    """Which kind a catalogue product reaches today, and the rule that decided it."""
    row = (
        db.query(Product, ProductCategory.category_code)
        .outerjoin(ProductCategory, ProductCategory.id == Product.category_id)
        .filter(Product.id == str(product_id))
        .first()
        if _valid_uuid(product_id)
        else None
    )
    if row is None:
        raise handle_not_found("Product", str(product_id))
    product, category_code = row
    matches = rank_kind_matches(
        db, product_code=product.product_code, category_code=category_code, product_name=product.product_name
    )
    if not matches:
        return {"resolved_kind": None, "deciding_rule": None}
    best = matches[0]
    return {
        "resolved_kind": {"id": best.kind.id, "code": best.kind.code, "name": best.kind.name},
        "deciding_rule": {"id": best.rule.id, "match_type": best.rule.match_type, "match_value": best.rule.match_value},
    }
