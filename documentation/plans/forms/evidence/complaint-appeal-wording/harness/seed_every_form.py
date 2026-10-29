"""Sandbox only: one appealed (`resubmitted`) record per form, all names invented.

Run from sorento_crm_backend after seed_browse.py:
  SORENTO_ENV_FILE=.env.browse venv/bin/python <this file>
"""
import sys
import uuid
from datetime import datetime

sys.path.insert(0, ".")
from app.main import app  # noqa: F401,E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.database import engine  # noqa: E402
from app.models.new_product_application import NewProductApplication  # noqa: E402
from app.models.portal import PortalToken  # noqa: E402
from app.models.procurement import PurchaseRequestHeader, StockInquiry  # noqa: E402
from app.models.projects import Project, ProjectQuotationDocument  # noqa: E402

COMPANY = "00000000-0000-0000-0000-000000000001"
from app.services.company_scope import company_scope  # noqa: E402

db = sessionmaker(bind=engine)()
_scope = company_scope(db, frozenset({COMPANY}))
_scope.__enter__()
tok = db.query(PortalToken).filter(PortalToken.space_id == "browse-space").first()
u = lambda: str(uuid.uuid4())  # noqa: E731
now = datetime.utcnow()

db.add(StockInquiry(id=u(), status="resubmitted", inquiry_number="ZZT-SI-0001", contact_id=tok.contact_id,
                    space_id="browse-space", product_code="CWCY604"))
db.add(StockInquiry(id=u(), status="rejected", inquiry_number="ZZT-SI-0002", contact_id=tok.contact_id,
                    space_id="browse-space", product_code="CWCY605", portal_draft_at=now))
for kind, number in (("purchase_request", "ZZT-PR-0001"), ("sponsorship_form", "ZZT-SF-0001")):
    db.add(PurchaseRequestHeader(id=u(), request_type=kind, request_number=number, status="resubmitted",
                                 source="portal", contact_id=tok.contact_id, space_id="browse-space",
                                 project_title="Appeal Tower"))
db.add(NewProductApplication(id=u(), company_id=COMPANY, application_no="ZZT-NPA-0001", status="resubmitted",
                             contact_id=tok.contact_id))
project = Project(id=u(), title="APPEAL TOWER", normalised_title="appeal tower", approval_state="resubmitted",
                  company_id=COMPANY)
db.add(project)
db.flush()
resub = db.execute(text("SELECT id FROM statuses WHERE entity_type='quotation' AND key='resubmitted'")).scalar()
db.add(ProjectQuotationDocument(id=u(), project_id=project.id, document_no="ZZT-Q-0001", approval_status_id=resub))
db.commit()
print("seeded")
