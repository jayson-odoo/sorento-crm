"""Sandbox only: a second complaint for the seeded portal contact, left rejected, plus its token."""
import sys, uuid
from datetime import datetime
sys.path.insert(0, ".")
from app.main import app  # noqa: F401
from sqlalchemy.orm import sessionmaker
from app.database import engine
from app.models.complaints import Complaint
from app.models.portal import PortalToken

db = sessionmaker(bind=engine)()
tok = db.query(PortalToken).filter(PortalToken.space_id == "browse-space").first()
c = Complaint(id=str(uuid.uuid4()), complaint_number="ZZT26-0220", status="rejected", contact_id=tok.contact_id,
              space_id="browse-space", customer_name="Customer A", product_code="CWCY604",
              defect_description="Hinge loose", rejection_reason="Photos missing", rejected_at=datetime.utcnow())
db.add(c); db.commit()
print("rejected", c.id, "token", tok.token)
