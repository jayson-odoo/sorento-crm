"""Reusable service for linking attachments to any entity."""
from __future__ import annotations

from typing import Optional, Any
from sqlalchemy.orm import Session

from app.models.entity_attachment import EntityAttachmentLink
from app.models.resources import Attachment, AttachmentType
from app.services.error_handler import handle_not_found, handle_conflict, handle_validation_error
from app.services.s3_service import S3Service


class EntityAttachmentService:
    """Generic attachment link operations (create/link/list/unlink) across entity types."""

    def __init__(self, db: Session):
        self.db = db

    def _resolve_attachment_url(self, file_path: Optional[str]) -> Optional[str]:
        if not file_path:
            return None
        if file_path.startswith(("http://", "https://")):
            return file_path
        try:
            return S3Service().get_file_url(file_path)
        except Exception:
            return file_path

    def _normalize(self, entity_type: str, entity_id: str) -> tuple[str, str]:
        et = (entity_type or "").strip()
        eid = (entity_id or "").strip()
        if not et:
            raise handle_validation_error("entity_type is required")
        if not eid:
            raise handle_validation_error("entity_id is required")
        return et, eid

    def _attachment_type_id_by_code(self, code: str) -> str:
        row = self.db.query(AttachmentType.id).filter(AttachmentType.code == code).first()
        if not row:
            raise handle_not_found("Attachment type", code)
        return row[0]

    def list_links(self, entity_type: str, entity_id: str) -> list[EntityAttachmentLink]:
        et, eid = self._normalize(entity_type, entity_id)
        return (
            self.db.query(EntityAttachmentLink)
            .filter(EntityAttachmentLink.entity_type == et, EntityAttachmentLink.entity_id == eid)
            .order_by(
                EntityAttachmentLink.sort_order.asc().nulls_last(),
                EntityAttachmentLink.created_at.asc(),
            )
            .all()
        )

    def list_links_for_entities(
        self, entity_type: str, entity_ids: list[str]
    ) -> dict[str, list[EntityAttachmentLink]]:
        if not entity_ids:
            return {}
        et = (entity_type or "").strip()
        rows = (
            self.db.query(EntityAttachmentLink)
            .filter(
                EntityAttachmentLink.entity_type == et,
                EntityAttachmentLink.entity_id.in_([str(i) for i in entity_ids if i is not None]),
            )
            .order_by(
                EntityAttachmentLink.entity_id.asc(),
                EntityAttachmentLink.sort_order.asc().nulls_last(),
                EntityAttachmentLink.created_at.asc(),
            )
            .all()
        )
        out: dict[str, list[EntityAttachmentLink]] = {}
        for row in rows:
            out.setdefault(str(row.entity_id), []).append(row)
        return out

    def link_existing_attachment(
        self,
        entity_type: str,
        entity_id: str,
        attachment_id: str,
        created_by: Optional[str] = None,
    ) -> EntityAttachmentLink:
        et, eid = self._normalize(entity_type, entity_id)
        att_id = (attachment_id or "").strip()
        if not att_id:
            raise handle_validation_error("attachment_id is required")

        attachment = self.db.query(Attachment).filter(Attachment.id == att_id).first()
        if not attachment:
            raise handle_not_found("Attachment", att_id)

        existing = (
            self.db.query(EntityAttachmentLink)
            .filter(
                EntityAttachmentLink.entity_type == et,
                EntityAttachmentLink.entity_id == eid,
                EntityAttachmentLink.attachment_id == att_id,
            )
            .first()
        )
        if existing:
            raise handle_conflict("Attachment is already linked to this record.")

        count = (
            self.db.query(EntityAttachmentLink)
            .filter(EntityAttachmentLink.entity_type == et, EntityAttachmentLink.entity_id == eid)
            .count()
        )
        link = EntityAttachmentLink(
            entity_type=et,
            entity_id=eid,
            attachment_id=att_id,
            is_primary=(count == 0),
            sort_order=count,
            created_by=created_by,
        )
        self.db.add(link)
        self.db.flush()
        self.db.refresh(link)
        return link

    def create_attachment_and_link(
        self,
        entity_type: str,
        entity_id: str,
        file_url: str,
        file_name: Optional[str] = None,
        file_size_bytes: Optional[int] = None,
        attachment_type_code: str = "complaint_document",
        created_by: Optional[str] = None,
    ) -> EntityAttachmentLink:
        et, eid = self._normalize(entity_type, entity_id)
        url = (file_url or "").strip()
        if not url:
            raise handle_validation_error("file_url is required")

        type_id = self._attachment_type_id_by_code((attachment_type_code or "").strip())
        name = (file_name or url.split("/")[-1].split("?")[0] or "document").strip()[:255]
        stored = name[:255]
        path = url[:500]

        attachment = Attachment(
            attachment_type_id=type_id,
            original_filename=name,
            stored_filename=stored,
            file_path=path,
            file_size_bytes=file_size_bytes,
        )
        self.db.add(attachment)
        self.db.flush()
        return self.link_existing_attachment(
            entity_type=et,
            entity_id=eid,
            attachment_id=str(attachment.id),
            created_by=created_by,
        )

    def delete_link(self, link_id: str, entity_type: Optional[str] = None) -> EntityAttachmentLink:
        q = self.db.query(EntityAttachmentLink).filter(EntityAttachmentLink.id == link_id)
        if entity_type:
            q = q.filter(EntityAttachmentLink.entity_type == entity_type.strip())
        link = q.first()
        if not link:
            raise handle_not_found("Entity attachment link", link_id)
        self.db.delete(link)
        self.db.flush()
        return link

    def delete_links_for_entity(self, entity_type: str, entity_id: str) -> int:
        et, eid = self._normalize(entity_type, entity_id)
        deleted = (
            self.db.query(EntityAttachmentLink)
            .filter(EntityAttachmentLink.entity_type == et, EntityAttachmentLink.entity_id == eid)
            .delete(synchronize_session=False)
        )
        self.db.flush()
        return int(deleted or 0)

    def serialize_link(
        self,
        link: EntityAttachmentLink,
        entity_key: str,
        link_type: Optional[str] = None,
    ) -> dict[str, Any]:
        """Serialize one generic link into API response shape with a custom entity id key."""
        att = link.attachment
        return {
            "id": link.id,
            entity_key: link.entity_id,
            "attachment_id": link.attachment_id,
            "file_name": getattr(att, "original_filename", None),
            "original_filename": getattr(att, "original_filename", None),
            "file_url": self._resolve_attachment_url(getattr(att, "file_path", None)),
            "file_size_bytes": getattr(att, "file_size_bytes", None),
            "uploaded_at": getattr(att, "uploaded_at", None) or link.created_at,
            "link_type": link_type or link.entity_type,
        }

