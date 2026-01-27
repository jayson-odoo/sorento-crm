"""Complaints service for business logic."""
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_, inspect
from typing import Optional
from app.models.complaints import Complaint, ComplaintAttachment, ComplaintManualAttachment
from app.models.resources import Attachment
from app.schemas.complaints import ComplaintCreate, ComplaintUpdate, ComplaintManualAttachmentCreate
from app.services.error_handler import handle_not_found, handle_conflict
from app.services.s3_service import S3Service


class ComplaintService:
    """Service for complaint operations."""
    
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

    def _build_manual_attachments_map(self, complaint_ids: list[str]) -> dict[str, list[ComplaintAttachment]]:
        if not complaint_ids:
            return {}

        manual_links = (
            self.db.query(ComplaintManualAttachment)
            .filter(ComplaintManualAttachment.complaint_id.in_(complaint_ids))
            .all()
        )
        attachment_ids = [link.attachment_id for link in manual_links]
        if not attachment_ids:
            return {complaint_id: [] for complaint_id in complaint_ids}

        attachments = (
            self.db.query(Attachment)
            .filter(Attachment.id.in_(attachment_ids))
            .all()
        )
        attachments_map = {attachment.id: attachment for attachment in attachments}

        result: dict[str, list[ComplaintAttachment]] = {complaint_id: [] for complaint_id in complaint_ids}
        for link in manual_links:
            resource_attachment = attachments_map.get(link.attachment_id)
            if not resource_attachment:
                continue
            result[link.complaint_id].append(
                ComplaintAttachment(
                    id=link.id,
                    complaint_id=link.complaint_id,
                    file_name=resource_attachment.original_filename,
                    file_url=self._resolve_attachment_url(resource_attachment.file_path),
                    file_size_bytes=resource_attachment.file_size_bytes,
                    uploaded_at=link.created_at,
                )
            )
        return result

    def _serialize_complaint(
        self,
        complaint: Complaint,
        manual_attachments: list[ComplaintAttachment],
    ) -> dict:
        data = {attr.key: getattr(complaint, attr.key) for attr in inspect(complaint).mapper.column_attrs}
        data["attachments"] = list(complaint.attachments or []) + manual_attachments
        return data
    
    def list_complaints(
        self,
        page: int = 1,
        limit: int = 50,
        query: Optional[str] = None,
        sort_field: str = "complaint_date",
        sort_dir: str = "asc"
    ):
        """List complaints."""
        q = self.db.query(Complaint).options(joinedload(Complaint.attachments))
        
        if query:
            q = q.filter(
                or_(
                    Complaint.delivery_order_number.ilike(f"%{query}%"),
                    Complaint.customer_name.ilike(f"%{query}%"),
                    Complaint.product_code.ilike(f"%{query}%"),
                    Complaint.defect_description.ilike(f"%{query}%"),
                    Complaint.project_title.ilike(f"%{query}%")
                )
            )
        
        sort_map = {
            "complaint_date": Complaint.complaint_date,
            "delivery_order_number": Complaint.delivery_order_number,
            "customer_name": Complaint.customer_name,
            "product_code": Complaint.product_code,
        }
        sort_column = sort_map.get(sort_field, Complaint.complaint_date)
        if sort_dir == "desc":
            q = q.order_by(sort_column.desc())
        else:
            q = q.order_by(sort_column.asc())
        
        total = q.count()
        offset = (page - 1) * limit
        complaints = q.offset(offset).limit(limit).all()
        manual_attachments_map = self._build_manual_attachments_map([complaint.id for complaint in complaints])
        complaint_data = [
            self._serialize_complaint(
                complaint,
                manual_attachments_map.get(complaint.id, []),
            )
            for complaint in complaints
        ]
        
        return {
            "data": complaint_data,
            "pagination": {"total": total, "page": page, "limit": limit},
            "empty": total == 0
        }
    
    def get_complaint(self, complaint_id: str):
        """Get a complaint by ID."""
        complaint = (
            self.db.query(Complaint)
            .options(joinedload(Complaint.attachments))
            .filter(Complaint.id == complaint_id)
            .first()
        )
        if not complaint:
            raise handle_not_found("Complaint", complaint_id)
        return complaint

    def get_complaint_with_attachments(self, complaint_id: str) -> dict:
        """Get a complaint with manual attachments merged into attachments list."""
        complaint = self.get_complaint(complaint_id)
        manual_attachments_map = self._build_manual_attachments_map([complaint.id])
        return self._serialize_complaint(
            complaint,
            manual_attachments_map.get(complaint.id, []),
        )
    
    def create_complaint(self, complaint_data: ComplaintCreate):
        """Create a new complaint with attachments."""
        complaint_dict = complaint_data.model_dump(exclude={"attachments"})
        complaint = Complaint(**complaint_dict)
        self.db.add(complaint)
        self.db.flush()
        
        # Create attachments if provided
        if complaint_data.attachments:
            for att_data in complaint_data.attachments:
                attachment = ComplaintAttachment(**att_data.model_dump(), complaint_id=complaint.id)
                self.db.add(attachment)
        
        self.db.commit()
        self.db.refresh(complaint)
        return complaint
    
    def update_complaint(self, complaint_id: str, complaint_data: ComplaintUpdate):
        """Update a complaint."""
        complaint = self.get_complaint(complaint_id)
        
        update_data = complaint_data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(complaint, key, value)
        
        self.db.commit()
        self.db.refresh(complaint)
        return complaint

    def delete_complaint(self, complaint_id: str) -> None:
        """Delete a complaint and its related attachments."""
        complaint = self.get_complaint(complaint_id)
        self.db.delete(complaint)
        self.db.commit()

    def create_manual_attachment(self, attachment_data: ComplaintManualAttachmentCreate):
        """Create a manual complaint attachment link."""
        attachment = (
            self.db.query(Attachment)
            .filter(Attachment.id == attachment_data.attachment_id)
            .first()
        )
        if not attachment:
            raise handle_not_found("Attachment", attachment_data.attachment_id)

        existing_link = (
            self.db.query(ComplaintManualAttachment)
            .filter(
                ComplaintManualAttachment.complaint_id == attachment_data.complaint_id,
                ComplaintManualAttachment.attachment_id == attachment_data.attachment_id,
            )
            .first()
        )
        if existing_link:
            raise handle_conflict("Attachment is already linked to this complaint.")

        link = ComplaintManualAttachment(**attachment_data.model_dump())
        self.db.add(link)
        self.db.commit()
        self.db.refresh(link)
        return link, attachment

    def list_manual_attachments(self, complaint_id: str):
        """List manual complaint attachment links with attachment data."""
        links = (
            self.db.query(ComplaintManualAttachment)
            .filter(ComplaintManualAttachment.complaint_id == complaint_id)
            .order_by(ComplaintManualAttachment.created_at.desc())
            .all()
        )
        attachment_ids = [link.attachment_id for link in links]
        attachments = (
            self.db.query(Attachment)
            .filter(Attachment.id.in_(attachment_ids))
            .all()
        ) if attachment_ids else []
        attachments_map = {attachment.id: attachment for attachment in attachments}

        result = []
        for link in links:
            attachment = attachments_map.get(link.attachment_id)
            if not attachment:
                continue
            result.append(
                {
                    "id": link.id,
                    "complaint_id": link.complaint_id,
                    "attachment_id": link.attachment_id,
                    "created_at": link.created_at,
                    "attachment": attachment,
                }
            )
        return result

    def delete_manual_attachment(self, manual_attachment_id: str):
        """Delete a manual attachment link."""
        link = (
            self.db.query(ComplaintManualAttachment)
            .filter(ComplaintManualAttachment.id == manual_attachment_id)
            .first()
        )
        if not link:
            raise handle_not_found("Complaint manual attachment", manual_attachment_id)
        self.db.delete(link)
        self.db.commit()
        return link
