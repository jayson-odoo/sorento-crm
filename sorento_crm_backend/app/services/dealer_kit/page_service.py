"""Dealer Kit page lifecycle: immutable versions, movable labels.

The whole publishing model is two rules:

  1. A version is NEVER updated in place. Saving writes ``max(version) + 1`` for
     that page.
  2. Going live MOVES a label. It does not touch a version.

Everything good about this falls out of those two. Rollback is just the label
aimed at an older version, so it costs nothing and loses nothing. "Which edition
did the customer see in March" is answerable. A bad publish is one click from
undone.

Mirrors ``ai_prompt_versions`` / ``ai_prompt_labels``, deliberately - that
pattern is already proven in this codebase and a second shape would be a second
thing to reason about.
"""
from __future__ import annotations

import logging
from typing import Iterable, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.models.dealer_kit import Page, PageLabel, PageVersion

logger = logging.getLogger(__name__)
from app.services.dealer_kit import asset_service
from app.services.error_handler import AppException

DEFAULT_PRINT_PROFILE = {
    "pageSize": "A4",
    "orientation": "portrait",
    "margins": {"top": 15, "right": 15, "bottom": 15, "left": 15},
    "cover": True,
    "headerFooter": {"left": "", "right": "", "pageNumbers": True},
}

PUBLISHED = "published"
STAGING = "staging"
VALID_LABELS = (PUBLISHED, STAGING)


def _require_page(db: Session, page_id: str) -> Page:
    page = db.query(Page).filter(Page.id == page_id).first()
    if page is None:
        # The company scope filter runs before this, so "another company's page"
        # and "no such page" are the same answer on purpose.
        raise AppException(status_code=404, message="Page not found")
    return page


def _require_promotion(db: Session, promotion_id: str) -> None:
    """404 unless the promotion exists in the caller's company scope.

    Scope is enforced by the ORM filter, so another company's promotion reads as
    absent - the same answer a page of theirs gives, and for the same reason.
    """
    from app.models.marketing import Promotion

    exists = db.query(Promotion.id).filter(Promotion.id == promotion_id).first()
    if exists is None:
        raise AppException(status_code=404, message="Promotion not found")


def promotion_labels(db: Session, promotion_ids: Iterable[Optional[str]]) -> dict[str, Optional[str]]:
    """promotion_id -> its description, for a screen.

    Resolved here for the same reason ``author_names`` is: an id must never
    reach the UI, and "which offer prices this brochure" is only useful as the
    flyer's name. A promotion with no description resolves to None rather than
    to its id - the UI supplies the words for that, and a uuid is never an
    acceptable fallback label.
    """
    ids = {pid for pid in promotion_ids if pid}
    if not ids:
        return {}

    from app.models.marketing import Promotion

    rows = db.query(Promotion.id, Promotion.description).filter(Promotion.id.in_(ids)).all()
    return {pid: (description or None) for pid, description in rows}


def public_path(db: Session, page) -> Optional[str]:
    """The shareable address for a page: ``/c/{company_code}/{slug}``.

    Built here rather than in the UI because the company segment is what keeps
    two companies' identical slugs apart, and a screen has no business deriving
    that rule (nor holding a company id to derive it from).
    """
    from app.models.company import Company

    if not getattr(page, "company_id", None):
        return None
    code = db.query(Company.code).filter(Company.id == page.company_id).scalar()
    return f"/c/{code}/{page.slug}" if code else None


def list_pages(db: Session) -> list[dict]:
    """Pages with their published and latest version numbers.

    Both numbers matter to a Designer: "live" is what readers see, "latest" is
    what they have been working on, and the gap between them is the unpublished
    work.
    """
    pages = db.query(Page).order_by(Page.updated_at.desc()).all()
    if not pages:
        return []

    page_ids = [p.id for p in pages]

    # One lookup for every company represented, rather than one per page.
    from app.models.company import Company

    company_ids = {p.company_id for p in pages if getattr(p, "company_id", None)}
    codes = (
        dict(db.query(Company.id, Company.code).filter(Company.id.in_(company_ids)).all())
        if company_ids
        else {}
    )

    latest = dict(
        db.query(PageVersion.page_id, func.max(PageVersion.version))
        .filter(PageVersion.page_id.in_(page_ids))
        .group_by(PageVersion.page_id)
        .all()
    )

    published = dict(
        db.query(PageLabel.page_id, PageVersion.version)
        .join(PageVersion, PageVersion.id == PageLabel.version_id)
        .filter(PageLabel.page_id.in_(page_ids), PageLabel.label == PUBLISHED)
        .all()
    )

    # One lookup for the whole list, like the company codes above: a per-row
    # resolve turns a page list into a query per page.
    labels = promotion_labels(db, (p.promotion_id for p in pages))

    return [
        {
            "id": p.id,
            "name": p.name,
            "slug": p.slug,
            "updated_at": p.updated_at,
            "promotion_id": p.promotion_id,
            "promotion_label": labels.get(p.promotion_id) if p.promotion_id else None,
            "published_version": published.get(p.id),
            "latest_version": latest.get(p.id, 0),
            "public_path": (
                f"/c/{codes[p.company_id]}/{p.slug}"
                if getattr(p, "company_id", None) in codes
                else None
            ),
        }
        for p in pages
    ]


def get_page(db: Session, page_id: str) -> Page:
    return _require_page(db, page_id)


def create_page(
    db: Session,
    *,
    name: str,
    slug: str,
    user_id: Optional[str],
    promotion_id: Optional[str] = None,
) -> Page:
    existing = db.query(Page).filter(Page.slug == slug).first()
    if existing is not None:
        raise AppException(status_code=409, message=f"A page already uses the address '{slug}'")

    if promotion_id:
        # Validated before the insert, so a bad link cannot leave a half-made
        # page behind. Optional: no promotion is list prices only, not an error.
        _require_promotion(db, promotion_id)

    # A new page ships with real paper geometry. Leaving it null pushes the
    # decision onto every reader of the document, and paper mode has nothing to
    # paginate against.
    page = Page(
        name=name,
        slug=slug,
        created_by=user_id,
        print_profile=DEFAULT_PRINT_PROFILE,
        promotion_id=promotion_id or None,
    )
    db.add(page)
    db.commit()
    db.refresh(page)
    return page


def set_promotion(db: Session, page_id: str, promotion_id: Optional[str]) -> Page:
    """Link a brochure to the promotion that prices it, or clear the link.

    One promotion, never a list: which offer a brochure quotes is an editorial
    decision somebody makes once (PLAN D5). Whether it applies to the reader in
    front of us is a separate question, answered per viewer at read time.

    ``None`` clears it, and clearing is a normal end state - the page falls back
    to list prices (D6) rather than to a stale offer.
    """
    page = _require_page(db, page_id)

    if promotion_id:
        _require_promotion(db, promotion_id)

    page.promotion_id = promotion_id or None
    db.commit()
    db.refresh(page)
    return page


def delete_page(db: Session, page_id: str) -> None:
    """Hard delete. Versions and labels cascade with it.

    And so does the artwork this was the last brochure to show. Backgrounds are
    bound as asset ids in the versions about to be cascaded away, so without
    this the assets survive with nothing naming them - unfindable, unsignable
    and unremovable, since ``asset.attachment_id`` is ON DELETE RESTRICT.

    Only what nothing else names, which is why the ids are collected BEFORE the
    delete and swept AFTER it: another brochure may show the same banner, and
    the flyer reading that produced it usually still claims it, in which case
    the artwork stays and goes later with the reading. Either order leaves
    nothing behind, and neither order can strip a page somebody is reading.
    """
    page = _require_page(db, page_id)
    backgrounds = {
        value
        for version in db.query(PageVersion.doc).filter(PageVersion.page_id == page_id).all()
        for value in asset_service.background_asset_ids(version[0])
    }

    db.delete(page)
    db.flush()

    doomed = asset_service.delete_unreferenced(db, backgrounds)
    db.commit()

    # After the commit, never before: bytes are the one part of this no
    # rollback can undo.
    asset_service.purge_objects(doomed)


def list_versions(db: Session, page_id: str) -> list[PageVersion]:
    _require_page(db, page_id)
    return (
        db.query(PageVersion)
        .filter(PageVersion.page_id == page_id)
        .order_by(PageVersion.version.desc())
        .all()
    )


def author_names(db: Session, user_ids: Iterable[Optional[str]]) -> dict[str, str]:
    """user_id -> display name, for version history.

    Resolved here rather than in the UI because a raw user id must never reach a
    screen, and "who saved version 4" is only useful as a person's name.
    """
    ids = {uid for uid in user_ids if uid}
    if not ids:
        return {}

    from app.models.user import User

    rows = db.query(User.id, User.name, User.email).filter(User.id.in_(ids)).all()
    return {uid: (name or email or "Unknown") for uid, name, email in rows}


def labels_for(db: Session, page_id: str) -> dict[str, list[str]]:
    """version_id -> label, for decorating a version list."""
    rows = db.query(PageLabel).filter(PageLabel.page_id == page_id).all()
    out: dict[str, list[str]] = {}
    for row in rows:
        out.setdefault(row.version_id, []).append(row.label)
    return out


def save_version(
    db: Session,
    page_id: str,
    *,
    doc: dict,
    commit_message: Optional[str],
    user_id: Optional[str],
) -> PageVersion:
    """Write a new immutable version.

    The next number is ``max(version) + 1`` PER PAGE, not a global sequence:
    "version 3" has to mean the third edit of THIS page, or the history is
    unreadable.
    """
    _require_page(db, page_id)

    current_max = (
        db.query(func.max(PageVersion.version))
        .filter(PageVersion.page_id == page_id)
        .scalar()
    ) or 0

    version = PageVersion(
        page_id=page_id,
        version=current_max + 1,
        doc=doc,
        commit_message=commit_message or None,
        created_by=user_id,
    )
    db.add(version)
    db.commit()
    db.refresh(version)

    # An edit invalidates an approval, so an approved Edition goes back to the
    # Approver. Imported here rather than at module scope because
    # edition_service imports this module.
    #
    # Best-effort: the save has already committed, and raising here would hand
    # back a 500 for a save that succeeded (the retry then writes a SECOND
    # version). The hard guarantee is publish's own check that the version it is
    # about to publish is the one that was approved - this is what puts the
    # Edition back in front of a human, not what enforces the rule.
    try:
        from app.services.dealer_kit import edition_service

        edition_service.send_back_on_edit(db, page_id)
    except Exception:  # pragma: no cover - defensive
        logger.warning(
            "Could not send the approved Edition on page %s back after a save",
            page_id,
            exc_info=True,
        )

    return version


def move_label(
    db: Session,
    page_id: str,
    label: str,
    *,
    version_id: str,
    user_id: Optional[str],
) -> PageLabel:
    """Point a label at a version. This is publish AND rollback.

    Idempotent: pointing a label where it already points is a no-op that still
    returns 200, so a double-click cannot produce a confusing error.
    """
    if label not in VALID_LABELS:
        raise AppException(status_code=422, message=f"Unknown label '{label}'. Expected one of: {', '.join(VALID_LABELS)}")

    _require_page(db, page_id)

    version = (
        db.query(PageVersion)
        .filter(PageVersion.id == version_id, PageVersion.page_id == page_id)
        .first()
    )
    if version is None:
        # Guarding page_id too: a label must never be able to point at another
        # page's version.
        raise AppException(status_code=404, message="Version not found on this page")

    row = (
        db.query(PageLabel)
        .filter(PageLabel.page_id == page_id, PageLabel.label == label)
        .first()
    )
    if row is None:
        row = PageLabel(page_id=page_id, label=label, version_id=version_id, updated_by=user_id)
        db.add(row)
    else:
        row.version_id = version_id
        row.updated_by = user_id

    db.commit()
    db.refresh(row)
    return row


def published_doc(db: Session, slug: str) -> dict:
    """The live document for a public reader.

    404s when no ``published`` label exists. It deliberately does NOT fall back
    to the latest version: an unpublished draft reaching a reader is worse than
    a missing page, because nobody would know it happened (AC-B10).
    """
    page = db.query(Page).filter(Page.slug == slug).first()
    if page is None:
        raise AppException(status_code=404, message="Page not found")

    row = (
        db.query(PageLabel)
        .options(joinedload(PageLabel.version))
        .filter(PageLabel.page_id == page.id, PageLabel.label == PUBLISHED)
        .first()
    )
    if row is None or row.version is None:
        raise AppException(status_code=404, message="Page not found")

    return {
        "page_id": page.id,
        "name": page.name,
        "slug": page.slug,
        "version": row.version.version,
        "doc": row.version.doc,
        # Which offer prices this reader's tiles (ADR 0008). It comes from the
        # PAGE and not the version: the document holds bindings and never a
        # price, so an offer that ends does not require republishing - and one
        # that starts reaches the already-published page immediately. Null is
        # list prices only, which is a normal state (PLAN D6).
        "promotion_id": page.promotion_id,
    }
