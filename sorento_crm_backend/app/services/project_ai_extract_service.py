"""Turn an AI extract answer into proposals for the staff project register form
(PROJECT-REGISTER-V2 C3).

Read only: nothing here creates a project, a party or a customer. A name the company already
holds comes back as ``match`` with its id; a developer, architect or main contractor name it
does not hold comes back as ``new`` (the form creates it on confirm); every other field that
cannot be resolved comes back as ``not_found`` and the form leaves it blank.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.order import Customer
from app.models.projects import ProjectParty, ProjectType
from app.services.error_handler import AppException

#: AI extract field -> the party type it names.
_PARTY_FIELDS = (
    ("developer", "developer_name"),
    ("architect", "architect_name"),
    ("main_contractor", "main_contractor_name"),
)

NOT_FOUND = {"status": "not_found"}


def _text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _key(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip().lower()


def _name_expr(column):
    return func.lower(func.regexp_replace(func.btrim(column), r"\s+", " ", "g"))


def _party(db: Session, company_id: str, party_type: str, name: str) -> Dict[str, Any]:
    if not name:
        return dict(NOT_FOUND)
    row = (
        db.query(ProjectParty)
        .filter(
            ProjectParty.company_id == company_id,
            ProjectParty.party_type == party_type,
            _name_expr(ProjectParty.name) == _key(name),
        )
        .order_by(ProjectParty.created_at, ProjectParty.id)
        .first()
    )
    if row:
        return {"status": "match", "id": str(row.id), "name": row.name}
    return {"status": "new", "name": name}


def _project_type(db: Session, company_id: str, names: list) -> Dict[str, Any]:
    for name in names:
        if not name:
            continue
        row = (
            db.query(ProjectType)
            .filter(
                ProjectType.company_id == company_id,
                ProjectType.is_active.is_(True),
                _name_expr(ProjectType.name) == _key(name),
            )
            .order_by(ProjectType.sort_order, ProjectType.id)
            .first()
        )
        if row:
            return {"status": "match", "id": str(row.id), "name": row.name}
    return dict(NOT_FOUND)


def _building_names(db: Session, raw: str) -> list:
    """The raw text, plus the label of the building type option it names (the extract
    answers with a lookup value, the project type is matched by its name)."""
    names = [raw]
    if not raw:
        return names
    from app.models.lookup import LookupOption, LookupSet

    option = (
        db.query(LookupOption)
        .join(LookupSet, LookupSet.id == LookupOption.set_id)
        .filter(LookupSet.set_key == "project_building_type", LookupOption.value == raw)
        .first()
    )
    if option and option.label:
        names.append(option.label)
    return names


def _state(db: Session, raw: str) -> Dict[str, Any]:
    if not raw:
        return dict(NOT_FOUND)
    from app.services.lookup_resolver import LookupResolverService

    try:
        resolved = LookupResolverService(db).resolve("my_state", raw)
    except AppException:
        return dict(NOT_FOUND)
    return {"status": "match", "value": resolved.value, "name": resolved.label}


def _customer(db: Session, company_id: str, name: str) -> Dict[str, Any]:
    if not name:
        return dict(NOT_FOUND)
    rows = (
        db.query(Customer)
        .filter(Customer.company_id == company_id, _name_expr(Customer.customer_name) == _key(name))
        .limit(2)
        .all()
    )
    if len(rows) == 1:
        return {"status": "match", "id": str(rows[0].id), "name": rows[0].customer_name}
    return dict(NOT_FOUND)


def propose(db: Session, *, company_id: str, values: Dict[str, Any]) -> Dict[str, Any]:
    """One proposal per register-form field from the extract's ``values``."""
    out: Dict[str, Any] = {
        key: _party(db, company_id, key, _text(values.get(field))) for key, field in _PARTY_FIELDS
    }
    out["project_type"] = _project_type(
        db, company_id, _building_names(db, _text(values.get("type_of_building")))
    )
    out["state"] = _state(db, _text(values.get("state")))
    out["mukim"] = _text(values.get("mukim")) or None
    out["customer"] = _customer(db, company_id, _text(values.get("customer_name")))
    out["title"] = str(values.get("title") or "").strip() or None
    return out
