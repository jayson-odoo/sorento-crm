"""The quotation's side of the product picture: live while it is a draft, frozen at issue.

`product_image_service` owns the DECISION (which photograph is the product). This module owns
WHEN a quotation stops asking. Those are different questions and they resolve at different
moments:

- **A draft asks every time it is read.** Only 30 of the 535 products with candidate photos carry
  a choice, so almost every line is priced before anybody has answered for its product. Stamping
  the answer onto the line at save time would mean the choice made ten minutes later never
  reaches the quotation, and nobody is going to re-save 52 lines to collect it.
- **Issuing writes it down.** `project_quotation_lines.image_attachment_id` is the record of the
  photograph the customer was sent. Once stamped it is never overwritten - not by a later
  revision, not by the product's photo being re-chosen - because a re-download of R1 next year has
  to be R1.

The freeze is therefore a FILL, never an update: `image_attachment_id IS NULL` is the only row it
touches. That is what makes it safe to run again on the same version when an unchanged scope is
carried into R2, and it is why R1 and R2 of that scope cannot disagree about a picture.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy.orm import Session

from app.models.projects import ProjectQuotationLine
from app.services import product_image_service as images


def resolved_attachment_ids(
    db: Session, lines: Sequence[Any]
) -> Dict[str, Optional[str]]:
    """Per line id, the attachment its picture cell should show.

    The stamped id wins wherever there is one - that line has been issued, and what the customer
    holds does not move. Everything else asks the product, live.
    """
    live_needed = [
        line.product_id
        for line in lines
        if not line.image_attachment_id and line.product_id
    ]
    live = images.images_for(db, live_needed) if live_needed else {}
    resolved: Dict[str, Optional[str]] = {}
    for line in lines:
        if line.image_attachment_id:
            resolved[str(line.id)] = str(line.image_attachment_id)
            continue
        found = live.get(str(line.product_id)) if line.product_id else None
        resolved[str(line.id)] = found.attachment_id if found is not None else None
    return resolved


def line_images(db: Session, lines: Sequence[Any]) -> Dict[str, Dict[str, Any]]:
    """Per line id, the picture cell as the frontend reads it.

    One pass for the whole table: a scope runs to 52 lines and this is computed on every read of
    it, so a query per row would be 52 round trips to draw one column.

    A FROZEN line reports `chosen` off its own stamped id rather than off the product's state -
    the product may have no chosen photo at all today, and the issued line still carries the
    photograph that went out.
    """
    if not lines:
        return {}

    frozen = {
        str(line.id): str(line.image_attachment_id)
        for line in lines
        if line.image_attachment_id
    }
    live = images.images_for(
        db,
        [line.product_id for line in lines if line.product_id and not line.image_attachment_id],
    )

    to_sign: List[str] = list(frozen.values())
    to_sign += [
        row.attachment_id
        for row in live.values()
        if row.state == images.CHOSEN and row.attachment_id
    ]
    urls = images.preview_urls(db, to_sign)
    # The originals, for the viewer that opens on click. A second pass rather than a second
    # decision: same ids, same cache, and the thumbnail stays what the table cell renders.
    full_urls = images.preview_urls(db, to_sign, full=True)
    names = _filenames(db, frozen.values())

    cells: Dict[str, Dict[str, Any]] = {}
    for line in lines:
        key = str(line.id)
        stamped = frozen.get(key)
        if stamped:
            cells[key] = {
                "state": images.CHOSEN,
                "url": urls.get(stamped),
                "preview_url": full_urls.get(stamped) or urls.get(stamped),
                "attachment_id": stamped,
                "filename": names.get(stamped),
                # A frozen line is not a to-do: there is nothing left to choose on it, so the
                # count that drives "N photos to choose from" is deliberately zero.
                "candidate_count": 0,
            }
            continue
        if not line.product_id:
            cells[key] = images.serialize(images.OFF_CATALOG_IMAGE)
            continue
        found = live.get(str(line.product_id))
        if found is None:
            cells[key] = images.serialize(
                images.ProductImage(product_id=str(line.product_id), state=images.NO_PHOTOS)
            )
            continue
        cells[key] = images.serialize(
            found,
            urls.get(found.attachment_id) if found.attachment_id else None,
            full_urls.get(found.attachment_id) if found.attachment_id else None,
        )
    return cells


def _filenames(db: Session, attachment_ids) -> Dict[str, Optional[str]]:
    """Names for the STAMPED ids only. The live ones already came back with theirs."""
    from app.models.resources import Attachment

    wanted = list(dict.fromkeys(str(a) for a in attachment_ids if a))
    if not wanted:
        return {}
    return {
        str(row.id): (row.original_filename or row.stored_filename)
        for row in db.query(Attachment).filter(Attachment.id.in_(wanted)).all()
    }


def freeze_version_images(db: Session, version_id: str) -> int:
    """Stamp the chosen photograph onto every line of a version that has none. Returns the count.

    Called at ISSUE, which is the moment "what was sent" is decided. A FILL, never an update: a
    line that already carries an id is what a customer already holds, and re-issuing an unchanged
    scope in R2 must show what R1 showed.
    """
    lines = (
        db.query(ProjectQuotationLine)
        .filter(
            ProjectQuotationLine.version_id == str(version_id),
            ProjectQuotationLine.image_attachment_id.is_(None),
            ProjectQuotationLine.product_id.isnot(None),
        )
        .all()
    )
    if not lines:
        return 0

    chosen = images.images_for(db, [line.product_id for line in lines])
    filled = 0
    for line in lines:
        found = chosen.get(str(line.product_id))
        if found is None or found.state != images.CHOSEN or not found.attachment_id:
            continue
        line.image_attachment_id = found.attachment_id
        filled += 1
    if filled:
        db.flush()
    return filled


__all__ = ["freeze_version_images", "line_images", "resolved_attachment_ids"]
