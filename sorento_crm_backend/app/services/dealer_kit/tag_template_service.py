"""Tag template bulk delete (PLAN-price-tag-feedback-r2.md D26, S11).

One rule, and the whole module is built around it: a foreign or missing id in
the batch refuses the WHOLE batch, before anything is deleted. `TagTemplate`
carries `CompanyScopedMixin`, so the `id.in_(...)` query below is already
filtered to the caller's company by the `do_orm_execute` listener - a row
belonging to another company simply never comes back, and reads exactly like
one that does not exist. That is what makes the 404 below "no existence
oracle": the same message answers a missing id and a foreign one, and nothing
here can tell the two apart to say otherwise.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.dealer_kit import TagTemplate
from app.services.error_handler import AppException

def _not_found() -> AppException:
    """The exact sentence `_get_template_or_404` (tag_templates.py) already answers
    for a single missing id - a batch is refused with the SAME one, never a
    per-id breakdown."""
    return AppException(status_code=404, message="Tag template not found.", code="NOT_FOUND")


def bulk_delete(db: Session, template_ids: list[str]) -> dict:
    """Delete every listed template, or none of them.

    Versions and the published pointer cascade with the row (ON DELETE CASCADE /
    SET NULL, see `TagTemplate.published_version_id` and
    `TagTemplateVersion.template_id`), so nothing extra is deleted here.
    """
    ids = [str(i) for i in template_ids if i]
    rows = db.query(TagTemplate).filter(TagTemplate.id.in_(ids)).all()
    found = {row.id for row in rows}
    if found != set(ids):
        # Refused before anything is touched - a partial batch delete would be
        # a data-loss surprise nobody selected on purpose.
        raise _not_found()
    for row in rows:
        db.delete(row)
    db.commit()
    return {"deleted": len(rows)}
