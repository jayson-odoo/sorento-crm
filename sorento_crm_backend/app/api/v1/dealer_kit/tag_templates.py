"""Tag template CRUD endpoints.

Mounted at ``/api/v1/dealer-kit`` behind
``require_module_enabled_with_api_key("dealer_kit")``.

Permission gates:
  * ``dealer_kit.tag_templates.view``   - list, detail, versions (S5)
  * ``dealer_kit.tag_templates.manage`` - create, update, delete, publish,
    unpublish, restore (S5)
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.dependencies import require_permission, require_permission_with_api_key
from app.models.dealer_kit import TagTemplate, TagTemplateVersion
from app.schemas.price_tag import (
    ProductSetTagData,
    ProductTagData,
    ResolvePreviewIn,
    ResolvePreviewOut,
    TagTemplateCreate,
    TagTemplatePublishIn,
    TagTemplateResponse,
    TagTemplateUpdate,
    TagTemplateVersionDetailResponse,
    TagTemplateVersionResponse,
)
from app.services.dealer_kit import tag_data_service, tag_template_service
from app.services.error_handler import AppException

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tag-templates", tags=["tag-templates"])

_VIEW = require_permission_with_api_key("dealer_kit.tag_templates.view")
_MANAGE = require_permission("dealer_kit.tag_templates.manage")


def _user_id(user: dict) -> str | None:
    if not isinstance(user, dict):
        return None
    return user.get("id") or user.get("user_id")


def _response_for(t: TagTemplate, *, published: bool = False) -> TagTemplateResponse:
    """Build the response row.

    ``published=True`` is the request designer's view (AC-S5-2): the doc and
    print size answered are the PUBLISHED VERSION's, never the draft sitting
    in ``t.doc`` - those two keep drifting apart the moment anyone edits after
    a publish, and the designer must never see the drift.
    """
    resp = TagTemplateResponse.model_validate(t)
    if t.published_version is not None:
        resp.published_version_no = t.published_version.version_no
        if published:
            resp.doc = t.published_version.doc
            resp.print_size = t.published_version.print_size
    return resp


def _get_template_or_404(db: Session, template_id: str) -> TagTemplate:
    t = db.query(TagTemplate).filter(TagTemplate.id == template_id).first()
    if not t:
        raise AppException(
            status_code=404, message="Tag template not found.", code="NOT_FOUND"
        )
    return t


@router.get("", response_model=list[TagTemplateResponse])
def list_tag_templates(
    published: bool = Query(
        False,
        description=(
            "True = the request designer's source: only templates with a live "
            "pointer, and each one's PUBLISHED doc rather than its draft."
        ),
    ),
    db: Session = Depends(get_db),
    _user: dict = Depends(_VIEW),
):
    query = db.query(TagTemplate).options(joinedload(TagTemplate.published_version))
    if published:
        query = query.filter(TagTemplate.published_version_id.isnot(None))
    templates = query.order_by(TagTemplate.family, TagTemplate.name).all()
    return [_response_for(t, published=published) for t in templates]


# DECLARED BEFORE ``/{template_id}``, and that order is load-bearing: FastAPI
# matches in declaration order, so a uuid path param registered first would
# swallow ``/resolve-preview`` whole and answer 404 for a template nobody named.
# This repo has already shipped exactly that bug on the SLA escalate routes.
@router.post("/resolve-preview", response_model=ResolvePreviewOut)
def resolve_preview(
    payload: ResolvePreviewIn,
    db: Session = Depends(get_db),
    _user: dict = Depends(_VIEW),
):
    """Resolve a template's binding so the editor can preview it with real data.

    The same resolver the tag sheet designer uses, so a template that looks
    right in the editor looks right on a tag. Nothing here is stored: the
    template document holds the binding, and the values are answered again on
    every open (ADR 0008).
    """
    if not payload.product_id and not payload.product_set_id:
        raise AppException(
            status_code=422,
            message="Name a product or a product set to preview.",
            code="NOTHING_TO_RESOLVE",
        )

    viewer = tag_data_service.staff_viewer()

    if payload.product_id:
        product = tag_data_service.get_product(db, payload.product_id)
        if product is None:
            raise AppException(
                status_code=404, message="Product not found.", code="NOT_FOUND"
            )
        return ResolvePreviewOut(
            product=ProductTagData.model_validate(
                tag_data_service.product_tag_data(
                    db, product, viewer, payload.promotion_id
                )
            )
        )

    product_set = tag_data_service.get_product_set(db, payload.product_set_id)
    if product_set is None:
        raise AppException(
            status_code=404, message="Product set not found.", code="NOT_FOUND"
        )
    return ResolvePreviewOut(
        product_set=ProductSetTagData.model_validate(
            tag_data_service.product_set_tag_data(
                db, product_set, viewer, payload.promotion_id
            )
        )
    )


@router.get("/{template_id}", response_model=TagTemplateResponse)
def get_tag_template(
    template_id: str,
    db: Session = Depends(get_db),
    _user: dict = Depends(_VIEW),
):
    t = _get_template_or_404(db, template_id)
    return _response_for(t)


@router.post("", response_model=TagTemplateResponse, status_code=status.HTTP_201_CREATED)
def create_tag_template(
    payload: TagTemplateCreate,
    db: Session = Depends(get_db),
    user: dict = Depends(_MANAGE),
):
    t = TagTemplate(
        name=payload.name,
        family=payload.family,
        doc=payload.doc,
        print_size=payload.print_size,
        created_by=_user_id(user),
    )
    db.add(t)
    db.flush()
    db.commit()
    return TagTemplateResponse.model_validate(t)


@router.put("/{template_id}", response_model=TagTemplateResponse)
def update_tag_template(
    template_id: str,
    payload: TagTemplateUpdate,
    db: Session = Depends(get_db),
    _user: dict = Depends(_MANAGE),
):
    t = _get_template_or_404(db, template_id)

    update_data = payload.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(t, key, value)

    db.flush()
    db.commit()
    return _response_for(t)


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_tag_template(
    template_id: str,
    db: Session = Depends(get_db),
    _user: dict = Depends(_MANAGE),
):
    """The immediate delete. The deferred one (`tag_template.delete`, the list's
    countdown) calls the SAME service method, so the two cannot drift."""
    tag_template_service.delete_template(
        db, template_id, requested_by_id=_user_id(_user)
    )


# ---------------------------------------------------------------------------
# Publish / versions (S5, PLAN D7, D15, D16)
# ---------------------------------------------------------------------------


@router.post("/{template_id}/publish", response_model=TagTemplateResponse)
def publish_tag_template(
    template_id: str,
    payload: TagTemplatePublishIn | None = None,
    db: Session = Depends(get_db),
    user: dict = Depends(_MANAGE),
):
    """Snapshot the draft into a new immutable version and move the pointer.

    Never rewrites an existing version - the next number is always
    ``max(version_no) + 1`` for this template, so History is append-only and
    View/Restore have something permanent to point at.
    """
    from sqlalchemy import func

    t = _get_template_or_404(db, template_id)
    next_version_no = (
        db.query(func.coalesce(func.max(TagTemplateVersion.version_no), 0))
        .filter(TagTemplateVersion.template_id == t.id)
        .scalar()
    ) + 1
    version = TagTemplateVersion(
        template_id=t.id,
        version_no=next_version_no,
        doc=t.doc,
        print_size=t.print_size,
        note=payload.note if payload else None,
        created_by=_user_id(user),
    )
    db.add(version)
    try:
        db.flush()
        t.published_version_id = version.id
        db.commit()
    except IntegrityError as exc:
        # Two publishes racing land on the same `next_version_no` - the
        # `uq_dealer_kit_tag_template_version` unique index is the only thing
        # left holding the line, and it fires as a 500 unless translated here.
        db.rollback()
        logger.warning("tag template publish hit a version conflict: %s", getattr(exc, "orig", exc))
        raise AppException(
            status_code=409,
            message="Someone else just published this template. Reload and try again.",
            code="tag_template_publish_conflict",
        ) from exc
    db.refresh(t)
    return _response_for(t)


@router.post("/{template_id}/unpublish", response_model=TagTemplateResponse)
def unpublish_tag_template(
    template_id: str,
    db: Session = Depends(get_db),
    _user: dict = Depends(_MANAGE),
):
    """Move the pointer to NULL. The draft and every version row are untouched -
    a template that leaves the request designer's list can always be published
    again."""
    t = _get_template_or_404(db, template_id)
    t.published_version_id = None
    db.commit()
    db.refresh(t)
    return _response_for(t)


@router.get(
    "/{template_id}/versions", response_model=list[TagTemplateVersionResponse]
)
def list_tag_template_versions(
    template_id: str,
    db: Session = Depends(get_db),
    _user: dict = Depends(_VIEW),
):
    from app.models.user import User

    # Confirms the template is in scope before any version row is touched -
    # TagTemplateVersion is not itself CompanyScopedMixin (it is reachable only
    # through its template, which carries the partition), so this 404 is what
    # stands in for the automatic company filter.
    _get_template_or_404(db, template_id)

    rows = (
        db.query(TagTemplateVersion, User.name)
        .outerjoin(User, User.id == TagTemplateVersion.created_by)
        .filter(TagTemplateVersion.template_id == template_id)
        .order_by(TagTemplateVersion.version_no.desc())
        .all()
    )
    out: list[TagTemplateVersionResponse] = []
    for version, author_name in rows:
        resp = TagTemplateVersionResponse.model_validate(version)
        resp.created_by_name = author_name
        out.append(resp)
    return out


@router.get(
    "/{template_id}/versions/{version_id}",
    response_model=TagTemplateVersionDetailResponse,
)
def get_tag_template_version(
    template_id: str,
    version_id: str,
    db: Session = Depends(get_db),
    _user: dict = Depends(_VIEW),
):
    """The version's full document, for View (D16) - the read-only canvas."""
    from app.models.user import User

    _get_template_or_404(db, template_id)

    row = (
        db.query(TagTemplateVersion, User.name)
        .outerjoin(User, User.id == TagTemplateVersion.created_by)
        .filter(
            TagTemplateVersion.id == version_id,
            TagTemplateVersion.template_id == template_id,
        )
        .first()
    )
    if not row:
        raise AppException(
            status_code=404, message="Version not found.", code="NOT_FOUND"
        )
    version, author_name = row
    resp = TagTemplateVersionDetailResponse.model_validate(version)
    resp.created_by_name = author_name
    return resp


@router.post(
    "/{template_id}/versions/{version_id}/restore",
    response_model=TagTemplateResponse,
)
def restore_tag_template_version(
    template_id: str,
    version_id: str,
    db: Session = Depends(get_db),
    _user: dict = Depends(_MANAGE),
):
    """Copy a version's doc into the DRAFT. The live pointer is untouched -
    restoring an old design is not the same act as publishing it (D15)."""
    t = _get_template_or_404(db, template_id)
    version = (
        db.query(TagTemplateVersion)
        .filter(
            TagTemplateVersion.id == version_id,
            TagTemplateVersion.template_id == template_id,
        )
        .first()
    )
    if not version:
        raise AppException(
            status_code=404, message="Version not found.", code="NOT_FOUND"
        )

    t.doc = version.doc
    t.print_size = version.print_size
    db.commit()
    db.refresh(t)
    return _response_for(t)
