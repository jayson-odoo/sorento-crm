"""Tag template delete, single and in bulk (PLAN-price-tag-feedback-r2.md D26, S11).

One rule, and the whole module is built around it: a foreign or missing id in
the batch refuses the WHOLE batch, before anything is deleted. `TagTemplate`
carries `CompanyScopedMixin`, so a row belonging to another company simply
never comes back, and reads exactly like one that does not exist. That is what
makes the 404 below "no existence oracle": the same message answers a missing
id and a foreign one, and nothing here can tell the two apart to say otherwise.

The company predicate is spliced on EXPLICITLY (`_scoped`) rather than left to
the `do_orm_execute` listener alone. Both apply the same four-state rule from
`build_company_predicate`, so the two can never disagree - but this module's
promise is a delete, and a delete that is only safe while a globally-registered
listener happens to be installed is a promise made by somebody else's import
order. The listener is registered in the API process AND the worker; a plain
`python -c` script, a management command, or `COMPANY_SCOPE_ENFORCE=0` is
neither.
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Query, Session

from app.models.dealer_kit import TagTemplate, TagTemplateVersion
from app.services.company_scope import build_company_predicate, get_company_scope
from app.services.error_handler import AppException

logger = logging.getLogger(__name__)


def _not_found() -> AppException:
    """The exact sentence `_get_template_or_404` (tag_templates.py) already answers
    for a single missing id - a batch is refused with the SAME one, never a
    per-id breakdown."""
    return AppException(status_code=404, message="Tag template not found.", code="NOT_FOUND")


def _scoped(db: Session) -> Query:
    """Templates this session may touch, under its own company scope.

    Four-state, straight from `build_company_predicate`: UNSET or an empty scope
    is fail-closed (no rows), `None` is the system principal (every company), a
    frozenset is `company_id IN (...)`. A deferred commit puts the REQUESTER's
    scope back on the session first (`form_action_service._execute`), so this is
    the clicking user's company even when the sweep is what ran the handler.
    """
    query = db.query(TagTemplate)
    predicate = build_company_predicate(TagTemplate, get_company_scope(db))
    return query if predicate is None else query.filter(predicate)


def _audit_deletion(
    db: Session, rows: list[TagTemplate], *, requested_by_id: Optional[str], batch_size: int
) -> None:
    """One audit row per template, on the template itself.

    `TagTemplate` is not `__audit_track__`ed, so nothing records this otherwise -
    and a deferred batch delete is exactly the case where "which templates, and
    who asked for it" is asked days later, with the templates themselves gone.
    The action row in `sla_form_actions` names the CLICK (its entity id is a
    client-generated batch token), never the templates, so it cannot answer it.
    """
    from app.services.audit_service import log_audit

    detail = ", ".join(f"{row.name} ({row.id})" for row in rows)
    logger.info(
        "Deleting %s tag template(s) [%s] requested by %s",
        len(rows),
        detail,
        requested_by_id or "unknown",
    )
    for row in rows:
        log_audit(
            db,
            "tag_template",
            str(row.id),
            "DELETE",
            old_values={"name": row.name, "family": row.family},
            user_id=requested_by_id,
            company_id=str(row.company_id) if row.company_id else None,
            description=(
                f'Deleted tag template "{row.name}"'
                + (f" (one of {batch_size} selected)" if batch_size > 1 else "")
            ),
        )


def delete_template(
    db: Session, template_id: str, *, requested_by_id: Optional[str] = None
) -> dict:
    """Delete one template, or 404 if this company cannot see it."""
    row = _scoped(db).filter(TagTemplate.id == str(template_id)).first()
    if row is None:
        raise _not_found()
    _audit_deletion(db, [row], requested_by_id=requested_by_id, batch_size=1)
    db.delete(row)
    db.commit()
    return {"deleted": 1}


def bulk_delete(
    db: Session, template_ids: list[str], *, requested_by_id: Optional[str] = None
) -> dict:
    """Delete every listed template, or none of them.

    Versions and the published pointer cascade with the row (ON DELETE CASCADE /
    SET NULL, see `TagTemplate.published_version_id` and
    `TagTemplateVersion.template_id`), so nothing extra is deleted here.
    """
    ids = [str(i) for i in template_ids if i]
    rows = _scoped(db).filter(TagTemplate.id.in_(ids)).all()
    found = {row.id for row in rows}
    if found != set(ids):
        # Refused before anything is touched - a partial batch delete would be
        # a data-loss surprise nobody selected on purpose.
        raise _not_found()
    _audit_deletion(db, rows, requested_by_id=requested_by_id, batch_size=len(rows))
    for row in rows:
        db.delete(row)
    db.commit()
    return {"deleted": len(rows)}


# ---------------------------------------------------------------------------
# Publish (S5, PLAN D7, D15, D16; reused by S4's "Save as template", D1)
# ---------------------------------------------------------------------------


def publish(
    db: Session,
    template: TagTemplate,
    *,
    note: Optional[str] = None,
    created_by: Optional[str] = None,
) -> TagTemplate:
    """Snapshot the draft into a new immutable version and move the pointer.

    Shared by the publish route (`tag_templates.py`) and `create_and_publish`
    below (S4's "Save as template") - the same act either way, so the two
    cannot drift. Never rewrites an existing version - the next number is
    always `max(version_no) + 1` for this template, so History is append-only
    and View/Restore always have something permanent to point at.
    """
    next_version_no = (
        db.query(func.coalesce(func.max(TagTemplateVersion.version_no), 0))
        .filter(TagTemplateVersion.template_id == template.id)
        .scalar()
    ) + 1
    version = TagTemplateVersion(
        template_id=template.id,
        version_no=next_version_no,
        doc=template.doc,
        print_size=template.print_size,
        note=note,
        created_by=created_by,
    )
    db.add(version)
    try:
        db.flush()
        template.published_version_id = version.id
        db.commit()
    except IntegrityError as exc:
        # Two publishes racing land on the same `next_version_no` - the
        # `uq_dealer_kit_tag_template_version` unique index is the only thing
        # left holding the line, and it fires as a 500 unless translated here.
        db.rollback()
        logger.warning(
            "tag template publish hit a version conflict: %s", getattr(exc, "orig", exc)
        )
        raise AppException(
            status_code=409,
            message="Someone else just published this template. Reload and try again.",
            code="tag_template_publish_conflict",
        ) from exc
    db.refresh(template)
    return template


def create_and_publish(
    db: Session,
    *,
    name: str,
    family: str,
    doc: dict,
    print_size: dict,
    created_by: Optional[str] = None,
) -> TagTemplate:
    """"Save as template" (S4, D1, AC-S4-7): create AND publish v1 in ONE
    transaction. The request designer's design becomes a template ready in
    the "Use template..." picker right away - nothing here leaves a draft
    nobody sees, because nothing reads a draft template's doc but its own
    editor.
    """
    template = TagTemplate(
        name=name, family=family, doc=doc, print_size=print_size, created_by=created_by
    )
    db.add(template)
    db.flush()  # `template.id` has to exist before the version can reference it
    return publish(db, template, created_by=created_by)
