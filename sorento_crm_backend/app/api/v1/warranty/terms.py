"""Warranty terms - one promise, about one part of one Kind, under one Policy.

NESTED under the policy on purpose (AC-P9). `WarrantyTerm` is deliberately not
company-scoped, because it is only ever reachable through `policy_id` - which makes
an unguarded flat route hand another company's warranty terms to anyone who guesses
an id. The service loads the Policy FIRST, under the caller's scope, so one outside
it 404s before a term is touched.

Terms ride the POLICIES permission slug (AC-P11): there is no `warranty.terms.*`,
because a slug nobody will ever grant separately is a slug that rots.
"""
from typing import List, Optional, Union

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission, require_permission_with_api_key
from app.schemas.warranty_config import (
    TermCreate,
    TermResponse,
    TermsGroupedResponse,
    TermUpdate,
)
from app.services.uuid_path_param import validate_uuid_path
from app.services.warranty_config_service import WarrantyConfigService

router = APIRouter()


@router.get(
    "/{policy_id}/terms",
    response_model=Union[TermsGroupedResponse, List[TermResponse]],
)
async def list_warranty_terms(
    policy_id: str,
    group_by: Optional[str] = Query(None),
    current_user: dict = Depends(require_permission_with_api_key("warranty.policies.view")),
    db: Session = Depends(get_db),
):
    """AC-P4: `?group_by=kind` returns every Term of a Kind together.

    A Water Closet carries three simultaneously that disagree on lifetime,
    duration, defect scope AND installation, so a screen that shows one at a time
    cannot be checked against the policy document. A policy with no Terms answers an
    empty group list, never a 404.
    """
    validate_uuid_path(policy_id, resource="Warranty Policy")
    service = WarrantyConfigService(db)
    if (group_by or "").strip().lower() == "kind":
        return service.list_terms_grouped_by_kind(policy_id)
    return service.list_terms(policy_id)


@router.post("/{policy_id}/terms", response_model=TermResponse, status_code=status.HTTP_201_CREATED)
async def create_warranty_term(
    policy_id: str,
    payload: TermCreate,
    current_user: dict = Depends(require_permission("warranty.policies.add")),
    db: Session = Depends(get_db),
):
    validate_uuid_path(policy_id, resource="Warranty Policy")
    return WarrantyConfigService(db).create_term(policy_id, payload)


@router.patch("/{policy_id}/terms/{term_id}", response_model=TermResponse)
async def update_warranty_term(
    policy_id: str,
    term_id: str,
    payload: TermUpdate,
    current_user: dict = Depends(require_permission("warranty.policies.edit")),
    db: Session = Depends(get_db),
):
    validate_uuid_path(policy_id, resource="Warranty Policy")
    validate_uuid_path(term_id, resource="Warranty Term")
    return WarrantyConfigService(db).update_term(policy_id, term_id, payload)


@router.delete("/{policy_id}/terms/{term_id}")
async def delete_warranty_term(
    policy_id: str,
    term_id: str,
    current_user: dict = Depends(require_permission("warranty.policies.delete")),
    db: Session = Depends(get_db),
):
    """Hard delete. Stored assessments SURVIVE it (AC-P8a): `term_id` is ON DELETE
    SET NULL and the snapshot columns keep the verdict readable without it."""
    validate_uuid_path(policy_id, resource="Warranty Policy")
    validate_uuid_path(term_id, resource="Warranty Term")
    return WarrantyConfigService(db).delete_term(policy_id, term_id)
