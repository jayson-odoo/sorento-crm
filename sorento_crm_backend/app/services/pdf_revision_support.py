"""Snapshot-fed revision rendering, shared by the entity PDF exports.

Round 6 (6.3 / 6.4) of PLAN-portal-submission-revisions adds two things to the
stock-inquiry and purchase-request PDFs: a printable copy of ONE superseded
version, and a "with revisions" export that appends the EARLIER versions behind
the current form. Both services need the same facts - the lineage, one entry
looked up by id, which entries an include-revisions export appends, the filename
marker, the heading wording and a version's own attachments - so they live here
instead of being written twice and drifting apart.

An include-revisions export never gives the NEWEST entry a page: that entry is
the version the current form already shows, so printing both put the same form on
two consecutive pages. See :func:`appended_revision_entries`.

The rule every caller follows: a value printed for a revision comes from that
revision's STORED SNAPSHOT, never from the live row. The document exists to show
the form as it was at that version, so reading the current row would defeat it.

``status`` is deliberately never rendered for a revision: the snapshot is written
BEFORE the post-revision status restart is applied, so it holds the superseded
version's status and would read as wrong information under an "as it was"
heading (same reasoning as ``PortalRevisionService._snapshot_fields``).
"""
from __future__ import annotations

import logging
from collections import Counter
from datetime import date, datetime
from types import SimpleNamespace
from typing import Any, Optional

from fastapi import status
from sqlalchemy.orm import Session

from app.services.document_number import suffix_revision
from app.services.error_handler import AppException
from app.services.pdf_render import in_malaysia

logger = logging.getLogger(__name__)

__all__ = [
    "validate_export_request",
    "revision_entries",
    "find_revision_entry",
    "has_revision_history",
    "appended_revision_entries",
    "latest_revision_entry",
    "is_superseded",
    "export_filename",
    "filename_with_revision",
    "revision_document_number",
    "revision_heading",
    "revision_reason",
    "revision_attachment_names",
    "revision_attachment_sections",
    "snapshot_date",
    "snapshot_datetime",
    "snapshot_decimal",
]

# Mirrors PortalRevisionService's kinds. Kept as literals rather than imported so
# this module stays free of the service that imports it back.
KIND_ORIGINAL = "original"
KIND_RESUBMISSION = "resubmission"


def validate_export_request(
    db: Session,
    source_entity_type: str,
    source_entity_id: str,
    *,
    revision_id: Optional[str],
    include_revisions: bool,
    label: str,
    stem: str,
    number: Any,
    number_field: str,
) -> str:
    """Check an export request up front and return the filename it produces.

    The export is asynchronous, so a bad request has to fail at the route: a 404
    discovered inside the RQ task would surface as a failed download in the
    drawer with no explanation of what the caller got wrong.

    The filename is composed here rather than passed in, so the row the caller
    creates in My Downloads is named exactly as the rendered artifact will be
    (the services call the same two helpers).

    Raises 400 when both options are given (they are mutually exclusive) and 404
    when the revision is not this record's.
    """
    if revision_id and include_revisions:
        from app.services.error_handler import handle_validation_error

        raise handle_validation_error(
            "Ask for one revision or for the full history, not both."
        )
    if not revision_id:
        return export_filename(stem, number)
    entries = revision_entries(db, source_entity_type, source_entity_id)
    entry = find_revision_entry(entries, revision_id, label=label)
    return filename_with_revision(stem, entry, number_field, fallback=number)


def revision_entries(
    db: Session, source_entity_type: str, source_entity_id: str
) -> list[dict]:
    """The full lineage, oldest first - exactly what both revision timelines read.

    One reader for history, so a PDF can never show a version the screen does not.
    """
    from app.services.portal_revision_service import PortalRevisionService

    return PortalRevisionService(db).list_revisions(
        source_entity_type, str(source_entity_id)
    )


def find_revision_entry(entries: list[dict], revision_id: str, *, label: str) -> dict:
    """The entry with this id, or 404.

    Searched inside the entries of ONE submission, so a revision id that exists
    but belongs to another record 404s exactly as an unknown id does - the
    caller never learns that the id is real elsewhere.
    """
    wanted = str(revision_id or "").strip()
    for entry in entries or []:
        if str(entry.get("id") or "") == wanted:
            return entry
    raise AppException(
        status_code=status.HTTP_404_NOT_FOUND,
        message=f"That revision was not found on this {label}.",
        code="NOT_FOUND",
    )


def has_revision_history(entries: list[dict]) -> bool:
    """Whether this record has anything to append beyond its current form.

    A lone ``original`` entry is the record itself, not a revision, so an
    include-revisions export of a never-revised form is silently just the form.
    """
    if not entries:
        return False
    if len(entries) > 1:
        return True
    return int(entries[0].get("revision_no") or 0) > 0


def latest_revision_entry(entries: list[dict]) -> Optional[dict]:
    """The version the record is at right now, or None when it has no lineage.

    The current form IS this entry, so an include-revisions export reads its
    label, submitter and reason onto the current form page instead of giving it a
    page of its own.
    """
    if not has_revision_history(entries):
        return None
    return entries[-1] or None


def appended_revision_entries(entries: list[dict]) -> list[dict]:
    """The pages an include-revisions export appends, newest first.

    Every entry EXCEPT the newest. The newest is the version the current form
    already prints, so a page for it repeats page 1 verbatim - the reader gets the
    same form twice and has to compare them to discover they are identical. What
    that page uniquely carried (which revision it is, who sent it, why) is not
    lost: it moves onto the current form page, which is the version it produced.

    A lineage of only the original therefore appends nothing, and the document is
    exactly the current form - which is correct, because the original IS the
    current form on a record that was never revised.
    """
    if not has_revision_history(entries):
        return []
    return list(reversed(entries[:-1]))


def is_superseded(entries: list[dict], entry: dict) -> bool:
    """Whether a later version was submitted after this one.

    The newest entry in a lineage is the version in play, so the heading must not
    call it superseded - the reader would go looking for a newer copy that does
    not exist.
    """
    if not entries:
        return False
    return str((entries[-1] or {}).get("id") or "") != str(entry.get("id") or "")


def export_filename(stem: str, number: Any) -> str:
    """``("product-inquiry", "SI-26-0184-R2")`` -> ``product-inquiry-SI-26-0184-R2.pdf``.

    One composer for both the route (which names the pending download row) and
    the service (which names the rendered artifact), so the drawer cannot show
    one name and hand over a file with another.
    """
    safe = "".join(c for c in str(number or "").strip() if c.isalnum() or c in ("-", "_"))
    return f"{stem}-{safe}.pdf" if safe else f"{stem}.pdf"


def _entry_filename_marker(entry: dict) -> str:
    """The ONE word that says this file is a stored version, not the live record.

    Always present, exactly one of three:

    * ``original`` - the version-0 entry, whose own number is the bare one;
    * ``resubmitted-v<N>`` - a RESUBMISSION, which carries the record's CURRENT
      ``revision_no`` (an office reject never burns a revision, UAC C4), so it
      shares its number with the revision it followed, and a second resubmit
      would share it again - hence the version number;
    * ``as-submitted`` - any other revision.

    The last one is not decoration. A revision export and the current-form export
    of a record sitting at that same revision are two DIFFERENT documents: the
    live one carries office fields the snapshot cannot (the purchasing reply, the
    status, the approval block). Landing them side by side in My Downloads under
    one name is precisely the filing failure UAC N5/P2 exists to prevent.
    """
    kind = str(entry.get("kind") or "")
    if kind == KIND_ORIGINAL:
        return "original"
    if kind == KIND_RESUBMISSION:
        return f"resubmitted-v{int(entry.get('version_no') or 0)}"
    return "as-submitted"


def filename_with_revision(
    stem: str, entry: dict, number_field: str, *, fallback: Any = None
) -> str:
    """The filename of a ONE-version export:
    ``product-inquiry-SI-26-0184-R1-as-submitted.pdf``.

    Named after THAT version's own document number, not the record's current one
    plus a second revision marker: the record's number already carries its own
    suffix, so the old form read ``...-SI-26-0184-R2-rev1.pdf`` - two revision
    markers meaning different things in one filename, leaving the reader to work
    out which version the document actually is.

    Exactly one marker, always. The number says WHICH version; the marker says
    this is that stored version rather than the live record, and the two never
    stack (an ``original`` is not also ``as-submitted``). The plain current-form
    export and the include-revisions export keep the unmarked name.
    """
    number = revision_document_number(entry, number_field) or fallback
    name = export_filename(stem, number)
    return f"{name[:-4]}-{_entry_filename_marker(entry)}.pdf"


def revision_document_number(entry: dict, number_field: str) -> Optional[str]:
    """The document number AS AT this version: ``SI-26-0184-R2``.

    Rendered through the shared suffix helper off the snapshotted bare number, so
    the printed revision reads the same as every other surface (UAC N1/N4).
    """
    snapshot = entry.get("snapshot") or {}
    return suffix_revision(snapshot.get(number_field), entry.get("revision_no")) or None


def revision_heading(entry: dict, *, superseded: bool = True) -> str:
    """``Revision 2 (superseded) - submitted 12/08/2026 by Alice Tan``.

    The reader has to know which version they are holding without cross-checking
    anything. "(superseded)" is only added when the entry really is behind the
    current one - the newest entry in a lineage is the version in play.
    """
    label = str(entry.get("label") or "Revision")
    if superseded:
        # "Original (reconstructed)" already carries a parenthetical, and
        # "Original (reconstructed) (superseded)" reads like a stutter - fold the
        # second note into the first bracket instead.
        label = (
            f"{label[:-1]}, superseded)" if label.endswith(")") else f"{label} (superseded)"
        )
    parts = [label]
    when = _format_date(entry.get("submitted_at"))
    if when:
        parts.append(f"- submitted {when}")
    who = str(entry.get("submitted_by") or "").strip()
    if who:
        parts.append(f"by {who}" if when else f"- submitted by {who}")
    return " ".join(parts)


def revision_reason(entry: dict) -> Optional[str]:
    reason = str(entry.get("reason") or "").strip()
    return reason or None


def revision_attachment_names(entry: dict) -> list[str]:
    """Filenames the version carried, in the order the snapshot stored them.

    The fallback when the attachment rows cannot be read at all
    (:func:`revision_attachment_sections` degrades to this): the snapshot is the
    record of WHICH files the version had, so a name is always available even
    when the bytes are not.
    """
    names: list[str] = []
    for item in entry.get("attachments") or []:
        name = str((item or {}).get("filename") or "").strip()
        names.append(name or "attachment")
    return names


def _revision_attachment_links(db: Session, entry: dict) -> tuple[list, list[str]]:
    """``(link-shaped objects, names with no row left)`` for ONE version's files.

    The PDF image helpers read ``link.attachment``, so the rows are wrapped in
    that shape rather than forking them: a revision page then embeds its photos
    through exactly the same code the current form does.

    Fetched BY ATTACHMENT ID, never by link: a file a later revision removed is
    unlinked, not destroyed (UAC G6), and it is precisely the file a historical
    page exists to show - the on-screen history already resolves the same rows
    this way (``_attachment_urls``).
    """
    from app.models.resources import Attachment

    items = [item or {} for item in (entry.get("attachments") or [])]
    ids = {str(item.get("attachment_id")) for item in items if item.get("attachment_id")}
    rows: dict[str, Any] = {}
    if ids:
        for att in db.query(Attachment).filter(Attachment.id.in_(ids)).all():
            rows[str(att.id)] = att

    links: list = []
    missing: list[str] = []
    for item in items:
        att = rows.get(str(item.get("attachment_id") or ""))
        if att is None:
            missing.append(str(item.get("filename") or "").strip() or "attachment")
            continue
        links.append(SimpleNamespace(attachment=att))
    return links, missing


def revision_attachment_sections(
    db: Session, entry: dict, *, context: str = "revision PDF"
) -> tuple[list[dict], list[str]]:
    """``(embedded images, filenames to list)`` for ONE version's own files.

    A revision page prints its photos exactly as the current form prints its own,
    from THAT version's attachment set - the user's expectation, in his words,
    that "we using same printing function for all revisions". Non-image files are
    listed by name, as everywhere else.

    Best-effort in three places, because a printed history must never fail over a
    file: an attachment row that no longer exists falls back to its snapshotted
    name, an image whose bytes cannot be fetched falls back to its name (
    ``embedded_images`` drops it silently, so the difference is reconciled here),
    and a failure to read the rows at all falls back to the whole name list.

    Cost: one query per revision page plus one storage download per image on it.
    An include-revisions export of a long, photo-heavy lineage therefore does real
    work - it runs on the RQ worker, off the request path, exactly as the current
    form's own images already do.
    """
    from app.services.pdf_render import embedded_images, image_mime, non_image_names

    try:
        links, missing = _revision_attachment_links(db, entry)
    except Exception:  # pragma: no cover - never fail a render on a lookup
        logger.warning("%s: failed to read revision attachments", context, exc_info=True)
        return [], revision_attachment_names(entry)

    images = embedded_images(links, context=context)
    names = list(non_image_names(links))

    # An image counted here but absent from `images` never downloaded. Counted,
    # not set-differenced, so two files sharing a name are not confused.
    embedded = Counter(str(img.get("name") or "") for img in images)
    for link in links:
        att = link.attachment
        if image_mime(att) is None:
            continue
        name = getattr(att, "original_filename", None) or "image"
        if embedded.get(name, 0) > 0:
            embedded[name] -= 1
        else:
            names.append(name)

    return images, names + missing


def snapshot_date(value: Any) -> Any:
    """An ISO date/datetime string from a snapshot back to a date object.

    Snapshots store dates as ISO text (``_jsonable``), and the PDF date
    formatters take date objects. Anything that is not an ISO date passes
    through untouched: several of these columns are free text (a stock inquiry's
    delivery date accepts "ASAP") and must print as the contact typed it.
    """
    if isinstance(value, (date, datetime)):
        return value
    text = str(value or "").strip()
    if not text:
        return value
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return value


def snapshot_datetime(value: Any) -> Any:
    """A stored TIMESTAMP from a lineage entry, as Malaysia wall clock.

    ``list_revisions`` emits ``submitted_at`` as naive UTC, and every other
    surface renders it through the frontend's ``formatDateInMalaysia``. Printing
    the raw components would date a version submitted at 17:00 UTC one day
    earlier on paper than on screen - and UAC P2 makes that date load-bearing
    ("submitted 12/08/2026 by ..."), so the two documents of ONE revision would
    contradict each other.

    Use this for ``submitted_at``; :func:`snapshot_date` stays the reader for
    the snapshot's own date FIELDS, which are calendar days with no instant to
    shift.
    """
    return in_malaysia(snapshot_date(value))


def snapshot_decimal(value: Any) -> Any:
    """A numeric snapshot string back to a Decimal, so a snapshotted quantity or
    price prints in the same format the live row does. Non-numeric text passes
    through."""
    from decimal import Decimal, InvalidOperation

    if isinstance(value, Decimal) or value is None:
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return value


def _format_date(value: Any) -> Optional[str]:
    parsed = snapshot_datetime(value)
    if isinstance(parsed, (date, datetime)):
        return parsed.strftime("%d/%m/%Y")
    return None
