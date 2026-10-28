"""Synthetic seed for the AUDIT-TRAIL-RESUBMITTED browser pass. Sandbox DB (sorento_browse) only.

Run from sorento_crm_backend:
  SORENTO_ENV_FILE=.env.browse BROWSE_ADMIN_PASSWORD=... venv/bin/python <this file>

Writes (all names invented) a complaint shaped like the one the lane is for: submitted from the
portal, rejected, resubmitted, rejected, resubmitted, then rejected a third time and resubmitted
through today's portal path. The first two resubmits are written the way the portal wrote them
before RESUBMITTED-STATUS (status rejected -> submitted), with the audit listeners on and the
real actor stamped, so their audit rows have the prod shape. Prints the complaint id.
"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timedelta

import bcrypt
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, ".")
from app.main import app  # noqa: E402,F401  (import order: circular import)
from app.audit_context import AuditActor, actor_scope  # noqa: E402
from app.database import engine  # noqa: E402
from app.models.access import RespondContact  # noqa: E402
from app.models.company import UserCompany  # noqa: E402
from app.models.complaints import Complaint  # noqa: E402
from app.models.portal import PortalToken  # noqa: E402
from app.models.user import User, UserRoleAssignment  # noqa: E402
from app.services import portal_service as portal_mod  # noqa: E402
from app.services.audit_service import register_audit_listeners  # noqa: E402
from app.services.portal_service import PortalService  # noqa: E402

COMPANY = "00000000-0000-0000-0000-000000000001"
PASSWORD = os.environ["BROWSE_ADMIN_PASSWORD"]  # throwaway, sandbox DB only

register_audit_listeners()
db = sessionmaker(bind=engine)()


def u() -> str:
    return str(uuid.uuid4())


def user(email: str, name: str) -> User:
    row = db.query(User).filter(User.email == email).one_or_none()
    if row is None:
        row = User(id=u(), email=email, name=name, status="ACTIVE",
                   password=bcrypt.hashpw(PASSWORD.encode(), bcrypt.gensalt()).decode())
        db.add(row)
        db.flush()
        role = db.execute(text("SELECT id FROM user_roles WHERE slug IN ('superadmin','super_admin') "
                               "OR name ILIKE 'super admin' LIMIT 1")).scalar()
        db.add(UserRoleAssignment(user_id=row.id, role_id=role))
        db.add(UserCompany(id=u(), user_id=row.id, company_id=COMPANY))
        db.commit()
    return row


admin = user("browse.admin@example.com", "Browse Admin")
reviewer = user("browse.reviewer@example.com", "Tech Reviewer")

contact = RespondContact(id=u(), phone_number="+60190000219", name="Customer A")
token = PortalToken(id=u(), token="tok_" + uuid.uuid4().hex, contact_id=contact.id, space_id="browse-space",
                    expires_at=datetime.utcnow() + timedelta(days=30))
complaint = Complaint(id=u(), complaint_number="ZZT26-0219", status="draft", contact_id=contact.id,
                      space_id="browse-space", portal_draft_at=datetime.utcnow(), customer_name="Customer A",
                      product_code="CWCX604-P-RL-NEW", defect_description="Panel cracked")
db.add_all([contact, token, complaint])
db.commit()

# Side effects that need a worker / Respond.io: not under test.
PortalService._post_submit_notify = lambda self, *a, **kw: None
import app.services.form_sla_service as sla  # noqa: E402
sla.emit_form_event = lambda *a, **kw: None

as_contact = AuditActor(actor_type="contact", contact_id=contact.id, auth_method="portal_token")
as_staff = AuditActor(actor_type="user", user_id=reviewer.id, real_user_id=reviewer.id, auth_method="password")
svc = PortalService(db)


def staff_respond_and_reject(reason: str) -> None:
    with actor_scope(as_staff, db=db):
        complaint.status = "responded"
        complaint.technical_team_response = "Please send photos of the crack."
        db.commit()
        complaint.status = "rejected"  # what ComplaintService.decide_complaint leaves
        complaint.rejection_reason = reason
        complaint.rejected_at = datetime.utcnow()
        complaint.rejected_by = reviewer.id
        db.commit()


with actor_scope(as_contact, db=db):
    svc.submit_draft(token, "complaint", complaint.id)

# Two resubmits the way the portal wrote them before RESUBMITTED-STATUS.
for code, text_ in (("CWCY604", "Panel cracked, photos attached"),
                    ("CWCY604", "Panel cracked on two corners, photos attached")):
    staff_respond_and_reject("Photos missing")
    with actor_scope(as_contact, db=db):
        complaint.status = "submitted"
        complaint.product_code = code
        complaint.defect_description = text_
        db.commit()

# A third cycle through today's portal path (lands on resubmitted).
staff_respond_and_reject("Wrong product code")
with actor_scope(as_contact, db=db):
    svc.submit_draft(token, "complaint", complaint.id, {"product_code": "CWCY605"})

print("complaint", complaint.id, complaint.complaint_number, db.get(Complaint, complaint.id).status)

# The sandbox tenant has no module rows, so the frontend's module route guard sends every
# page home. Install the complaints module (and what it depends on) for the default tenant.
from app.modules.runtime.installer import install_modules  # noqa: E402
from app.modules.runtime.installer import DEFAULT_TENANT_ID  # noqa: E402

install_modules(db, DEFAULT_TENANT_ID, ["complaints"], actor_user_id=admin.id)
db.commit()
