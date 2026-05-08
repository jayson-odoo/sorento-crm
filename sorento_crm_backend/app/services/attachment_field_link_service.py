"""CRUD + template fan-out for ``attachment_field_links`` rows.

Used by:
 * The attachment upload + update endpoints (to validate the per-attachment
   ``target_field_keys`` template against the registry).
 * Every link API (external + manual) — calls :meth:`apply_template_to_row`
   after a per-row link is inserted, so per-field links materialize
   automatically without n8n having to know what field keys exist.
 * The product list/detail endpoints — :meth:`get_field_attachments_for_rows`
   batch-fetches the per-row map for the response payload.
 * The protected per-row "Manage field links" endpoint.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Iterable, Optional

from sqlalchemy.orm import Session

from app.models.attachment_field_link import AttachmentFieldLink
from app.models.resources import Attachment
from app.services.error_handler import handle_validation_error
from app.services.field_linkage import (
    SUPPORTED_ENTITY_TYPES,
    validate_field_keys,
)


def _normalize_entity(entity_type: str, entity_id: str) -> tuple[str, str]:
    et = (entity_type or "").strip()
    eid = (entity_id or "").strip()
    if not et:
        raise handle_validation_error("entity_type is required")
    if not eid:
        raise handle_validation_error("entity_id is required")
    return et, eid


class AttachmentFieldLinkService:
    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def list_for_attachment(self, attachment_id: str) -> list[AttachmentFieldLink]:
        return (
            self.db.query(AttachmentFieldLink)
            .filter(AttachmentFieldLink.attachment_id == attachment_id)
            .all()
        )

    def list_for_row(
        self, entity_type: str, entity_id: str
    ) -> list[AttachmentFieldLink]:
        et, eid = _normalize_entity(entity_type, entity_id)
        return (
            self.db.query(AttachmentFieldLink)
            .filter(
                AttachmentFieldLink.entity_type == et,
                AttachmentFieldLink.entity_id == eid,
            )
            .all()
        )

    def list_for_attachment_and_row(
        self, attachment_id: str, entity_type: str, entity_id: str
    ) -> list[AttachmentFieldLink]:
        et, eid = _normalize_entity(entity_type, entity_id)
        return (
            self.db.query(AttachmentFieldLink)
            .filter(
                AttachmentFieldLink.attachment_id == attachment_id,
                AttachmentFieldLink.entity_type == et,
                AttachmentFieldLink.entity_id == eid,
            )
            .all()
        )

    def get_field_attachments_for_row(
        self, entity_type: str, entity_id: str
    ) -> dict[str, list[Attachment]]:
        """Return ``{field_key: [Attachment, ...]}`` for one row."""
        et, eid = _normalize_entity(entity_type, entity_id)
        rows = (
            self.db.query(AttachmentFieldLink, Attachment)
            .join(Attachment, Attachment.id == AttachmentFieldLink.attachment_id)
            .filter(
                AttachmentFieldLink.entity_type == et,
                AttachmentFieldLink.entity_id == eid,
                Attachment.is_deleted.is_(False),
            )
            .all()
        )
        out: dict[str, list[Attachment]] = defaultdict(list)
        seen: set[tuple[str, str]] = set()
        for link, attachment in rows:
            key = (link.field_key, str(attachment.id))
            if key in seen:
                continue
            seen.add(key)
            out[link.field_key].append(attachment)
        return dict(out)

    def get_field_attachments_for_rows(
        self, entity_type: str, entity_ids: Iterable[str]
    ) -> dict[str, dict[str, list[Attachment]]]:
        """Batch variant: ``{entity_id: {field_key: [Attachment, ...]}}``.

        Used by list endpoints (e.g. products list) to populate
        ``field_attachments`` without an N+1 query.
        """
        et = (entity_type or "").strip()
        ids = [str(i) for i in entity_ids if i]
        if not et or not ids:
            return {}
        rows = (
            self.db.query(AttachmentFieldLink, Attachment)
            .join(Attachment, Attachment.id == AttachmentFieldLink.attachment_id)
            .filter(
                AttachmentFieldLink.entity_type == et,
                AttachmentFieldLink.entity_id.in_(ids),
                Attachment.is_deleted.is_(False),
            )
            .all()
        )
        out: dict[str, dict[str, list[Attachment]]] = defaultdict(lambda: defaultdict(list))
        seen: set[tuple[str, str, str]] = set()
        for link, attachment in rows:
            key = (str(link.entity_id), link.field_key, str(attachment.id))
            if key in seen:
                continue
            seen.add(key)
            out[str(link.entity_id)][link.field_key].append(attachment)
        # Convert defaultdicts to plain dicts for downstream serialization.
        return {eid: dict(per_field) for eid, per_field in out.items()}

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    def set_links(
        self,
        entity_type: str,
        entity_id: str,
        attachment_id: str,
        field_keys: Optional[Iterable[str]],
        *,
        created_by: Optional[str] = None,
    ) -> list[str]:
        """Idempotently sync the field-link rows for (entity, attachment).

        Inserts missing keys, deletes removed keys. Validates against the
        registry — unknown keys raise 400.
        """
        et, eid = _normalize_entity(entity_type, entity_id)
        if not attachment_id:
            raise handle_validation_error("attachment_id is required")

        ok, unknown = validate_field_keys(et, list(field_keys or []))
        if et in SUPPORTED_ENTITY_TYPES and unknown:
            raise handle_validation_error(
                f"Unknown field_keys for {et}: {', '.join(unknown)}"
            )
        # If entity_type is not in the registry, silently skip (so
        # propagation in entity_attachments external API is non-breaking
        # for entity types we haven't onboarded yet).
        if et not in SUPPORTED_ENTITY_TYPES:
            return []

        existing_rows = self.list_for_attachment_and_row(attachment_id, et, eid)
        existing_keys: dict[str, AttachmentFieldLink] = {
            row.field_key: row for row in existing_rows
        }

        desired = set(ok)
        to_add = desired - set(existing_keys)
        to_remove = set(existing_keys) - desired

        for key in to_add:
            self.db.add(
                AttachmentFieldLink(
                    entity_type=et,
                    entity_id=eid,
                    attachment_id=attachment_id,
                    field_key=key,
                    created_by=created_by if created_by else None,
                )
            )

        for key in to_remove:
            self.db.delete(existing_keys[key])

        # Caller commits.
        self.db.flush()
        return sorted(desired)

    def apply_template_to_row(
        self,
        attachment: Attachment | str,
        entity_type: str,
        entity_id: str,
        *,
        override_keys: Optional[Iterable[str]] = None,
        created_by: Optional[str] = None,
    ) -> list[str]:
        """Fan an attachment's upload-time template out to a freshly linked row.

        ``override_keys`` (if not None) **replaces** the template — does not
        union. A caller that wants the union must pass it explicitly.
        Passing an empty list as override is a way to skip per-field link
        creation for this row.
        """
        et, eid = _normalize_entity(entity_type, entity_id)

        if isinstance(attachment, str):
            attachment_id = attachment
            row = (
                self.db.query(Attachment)
                .filter(Attachment.id == attachment_id)
                .first()
            )
        else:
            attachment_id = str(attachment.id)
            row = attachment

        if override_keys is not None:
            keys: list[str] = list(override_keys)
        else:
            tmpl = getattr(row, "target_field_keys", None) if row is not None else None
            keys = list(tmpl or [])
            target_type = (
                getattr(row, "target_entity_type", None) if row is not None else None
            )
            # Honour template only when the link's entity_type matches the
            # template's target_entity_type. This keeps a "Product" template
            # from accidentally writing field keys when the same attachment is
            # linked to a promotion later.
            if target_type and target_type != et:
                keys = []

        return self.set_links(
            et, eid, attachment_id, keys, created_by=created_by
        )

    def delete_for_row(self, entity_type: str, entity_id: str) -> int:
        """Drop every field link for a row (used when the row itself is deleted)."""
        et, eid = _normalize_entity(entity_type, entity_id)
        deleted = (
            self.db.query(AttachmentFieldLink)
            .filter(
                AttachmentFieldLink.entity_type == et,
                AttachmentFieldLink.entity_id == eid,
            )
            .delete(synchronize_session=False)
        )
        return int(deleted or 0)

    def delete_for_attachment_and_row(
        self, attachment_id: str, entity_type: str, entity_id: str
    ) -> int:
        et, eid = _normalize_entity(entity_type, entity_id)
        deleted = (
            self.db.query(AttachmentFieldLink)
            .filter(
                AttachmentFieldLink.attachment_id == attachment_id,
                AttachmentFieldLink.entity_type == et,
                AttachmentFieldLink.entity_id == eid,
            )
            .delete(synchronize_session=False)
        )
        return int(deleted or 0)
