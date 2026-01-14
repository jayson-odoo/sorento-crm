"""Complaints service for business logic."""
from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import Optional
from app.models.complaints import Complaint, ComplaintAttachment
from app.schemas.complaints import ComplaintCreate, ComplaintUpdate
from app.services.error_handler import handle_not_found, handle_conflict


class ComplaintService:
    """Service for complaint operations."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def list_complaints(
        self,
        page: int = 1,
        limit: int = 50,
        query: Optional[str] = None,
        sort_field: str = "complaint_date",
        sort_dir: str = "asc"
    ):
        """List complaints."""
        q = self.db.query(Complaint)
        
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
        
        return {
            "data": complaints,
            "pagination": {"total": total, "page": page, "limit": limit},
            "empty": total == 0
        }
    
    def get_complaint(self, complaint_id: str):
        """Get a complaint by ID."""
        complaint = self.db.query(Complaint).filter(Complaint.id == complaint_id).first()
        if not complaint:
            raise handle_not_found("Complaint", complaint_id)
        return complaint
    
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
