"""Synthetic seed for the PROJECT-REG-PORTAL browser pass. Sandbox DB (sorento_browse) only.

Run from sorento_crm_backend:
  SORENTO_ENV_FILE=.env.browse BROWSE_ADMIN_PASSWORD=... venv/bin/python <this file>

Rework storage (owner ruling 25 Oct 17:50): a portal registration is a projects.projects row in
approval_state pending, so there is no registration table to seed and none is touched here.

Writes (all names invented): an admin login, the lookup sets / permission / numbering rule the
prreg_0001 migration seeds (its upgrade() is run, it is idempotent), a Coordinator approver (the
role from APPROVER_ROLE_NAMES only, plus projects view/edit and parties.view), a viewer user with
projects view only (no approve), a portal contact linked to an active sales agent (person_label
'Salesperson A', code 'SA-007') and to a CRM user, a verified portal token, the project_registration
grant, two debtors of that agent, developer parties, and three APPROVED projects. Embeddings are
seeded afterwards with: venv/bin/python -m scripts.seed_project_embeddings, then the queue is
processed (see the README). Prints the portal slug and token.
"""
from __future__ import annotations

import importlib.util
import os
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import bcrypt
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, ".")
from app.main import app  # noqa: E402,F401  (import order: circular import)
from app.database import engine  # noqa: E402

COMPANY = "00000000-0000-0000-0000-000000000001"
ADMIN_EMAIL = "browse.admin@example.com"
ADMIN_PASSWORD = os.environ["BROWSE_ADMIN_PASSWORD"]  # throwaway, sandbox DB only
TOKEN = "browse-token-sa007"
SLUG = "sa007slug"
SPACE = "browse-space"


def u() -> str:
    return str(uuid.uuid4())


# --- the migration's data (lookup sets, permission grant, numbering rule) -----------------
from alembic.migration import MigrationContext  # noqa: E402
from alembic.operations import Operations  # noqa: E402

path = Path("alembic/versions/prreg_0001_project_registrations.py")
spec = importlib.util.spec_from_file_location("prreg", path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
APPROVER_ROLES = tuple(mod.APPROVER_ROLE_NAMES)  # the non-admin roles the migration grants the approve slug
with engine.begin() as conn:
    # The roles exist BEFORE the migration runs, so their grant is the migration's own doing.
    for n in APPROVER_ROLES:
        conn.execute(text(
            "INSERT INTO user_roles (id, slug, name, is_trashed, is_protected, is_default) "
            "SELECT :i, :s, :n, false, false, false "
            "WHERE NOT EXISTS (SELECT 1 FROM user_roles WHERE name = :n)"
        ), {"i": str(uuid.uuid4()), "s": n.lower().replace(" ", "_"), "n": n})
    with Operations.context(MigrationContext.configure(conn)):
        mod.upgrade()
    # What a manager or coordinator also holds in real life (the approve slug itself came from the migration).
    conn.execute(text(
        "INSERT INTO user_role_permissions (id, role_id, permission_id) "
        "SELECT gen_random_uuid()::text, r.id, p.id FROM user_roles r, user_permissions p "
        "WHERE r.name = ANY(:n) AND p.slug IN ('projects.projects.view','projects.projects.edit',"
        "'projects.parties.view') AND NOT EXISTS (SELECT 1 FROM user_role_permissions x "
        "WHERE x.role_id = r.id AND x.permission_id = p.id)"
    ), {"n": list(APPROVER_ROLES)})

db = sessionmaker(bind=engine)()

from app.models.access import RespondContact  # noqa: E402
from app.models.company import RespondContactCompany, UserCompany  # noqa: E402
from app.models.order import Customer  # noqa: E402
from app.models.portal import PortalToken  # noqa: E402
from app.models.price_tag import ContactPortalFormOverride  # noqa: E402
from app.models.projects import Project, ProjectParty  # noqa: E402
from app.models.sales_agent import SalesAgent  # noqa: E402
from app.models.user import User, UserRoleAssignment  # noqa: E402
from app.services import project_seed_service  # noqa: E402
from app.services.project_service import register_project  # noqa: E402

project_seed_service.run(db, company_id=COMPANY)

# --- users ----------------------------------------------------------------------------------
admin = db.query(User).filter(User.email == ADMIN_EMAIL).one_or_none()
if admin is None:
    admin = User(id=u(), email=ADMIN_EMAIL, name="Browse Admin", status="ACTIVE",
                 password=bcrypt.hashpw(ADMIN_PASSWORD.encode(), bcrypt.gensalt()).decode())
    db.add(admin)
    db.flush()
    role = db.execute(text("SELECT id FROM user_roles WHERE slug IN ('superadmin','super_admin') "
                           "OR name ILIKE 'super admin' LIMIT 1")).scalar()
    db.add(UserRoleAssignment(user_id=admin.id, role_id=role))
    db.flush()
    db.add(UserCompany(id=u(), user_id=admin.id, company_id=COMPANY))

approver = db.query(User).filter(User.email == "browse.approver@example.com").one_or_none()
if approver is None:
    approver = User(id=u(), email="browse.approver@example.com", name="Approver Manager", status="ACTIVE",
                    password=bcrypt.hashpw(ADMIN_PASSWORD.encode(), bcrypt.gensalt()).decode())
    db.add(approver)
    db.flush()
    db.add(UserCompany(id=u(), user_id=approver.id, company_id=COMPANY))
    db.flush()
# the approver is a Coordinator, not a manager and not an admin: proves the second named role
role_id = db.execute(text("SELECT id FROM user_roles WHERE name = :n"), {"n": APPROVER_ROLES[-1]}).scalar()
if not db.execute(text("SELECT 1 FROM user_role_assignments WHERE user_id = :u AND role_id = :r"),
                  {"u": approver.id, "r": role_id}).scalar():
    db.add(UserRoleAssignment(user_id=approver.id, role_id=role_id))
    db.flush()

# a user WITHOUT the approve slug: project view + parties view only (check 5)
viewer = db.query(User).filter(User.email == "browse.viewer@example.com").one_or_none()
if viewer is None:
    viewer = User(id=u(), email="browse.viewer@example.com", name="Viewer Only", status="ACTIVE",
                  password=bcrypt.hashpw(ADMIN_PASSWORD.encode(), bcrypt.gensalt()).decode())
    db.add(viewer)
    db.flush()
    db.add(UserCompany(id=u(), user_id=viewer.id, company_id=COMPANY))
    vrole = u()
    db.execute(text("INSERT INTO user_roles (id, slug, name, is_trashed, is_protected, is_default) "
                    "VALUES (:i, 'browse_project_viewer', 'Browse Project Viewer', false, false, false)"),
               {"i": vrole})
    db.execute(text(
        "INSERT INTO user_role_permissions (id, role_id, permission_id) "
        "SELECT gen_random_uuid()::text, :r, p.id FROM user_permissions p "
        "WHERE p.slug IN ('projects.projects.view','projects.parties.view')"), {"r": vrole})
    db.flush()
    db.add(UserRoleAssignment(user_id=viewer.id, role_id=vrole))
    db.flush()

linked = db.query(User).filter(User.email == "salesperson.a@example.com").one_or_none()
if linked is None:
    linked = User(id=u(), email="salesperson.a@example.com", name="Salesperson A", status="ACTIVE")
    db.add(linked)
    db.flush()
    db.add(UserCompany(id=u(), user_id=linked.id, company_id=COMPANY))
    # a staff user (the people picker lists only users holding a role)
    sp_role = db.execute(text("SELECT id FROM user_roles WHERE slug = 'salesperson'")).scalar()
    db.add(UserRoleAssignment(user_id=linked.id, role_id=sp_role))
db.flush()

# --- the portal contact, its agent, token and grant ----------------------------------------
contact = db.query(RespondContact).filter(RespondContact.portal_slug == SLUG).one_or_none()
if contact is None:
    contact = RespondContact(id=u(), phone_number="+60100000007", name="Salesperson A",
                             portal_slug=SLUG)
    db.add(contact)
    db.flush()
    db.add(RespondContactCompany(respond_contact_id=contact.id, company_id=COMPANY))
    db.add(ContactPortalFormOverride(id=u(), contact_id=contact.id, form_type="project_registration",
                                     is_enabled=True))
    agent = SalesAgent(id=u(), sales_agent="SA-007", description="SA-007 desk",
                       person_label="Salesperson A", is_active=True, contact_id=contact.id)
    db.add(agent)
    db.flush()
    linked.respond_contact_id = contact.id
    for code, name in (("DEB-A1", "Debtor One Sdn Bhd"), ("DEB-A2", "Debtor Two Sdn Bhd")):
        db.add(Customer(id=u(), company_id=COMPANY, customer_code=code, customer_name=name,
                        sales_agent_id=agent.id))
    db.add(PortalToken(id=u(), token=TOKEN, contact_id=contact.id, space_id=SPACE,
                       expires_at=datetime.utcnow() + timedelta(days=30),
                       verified_at=datetime.utcnow() - timedelta(minutes=5)))
    # developers and existing projects
    alpha = ProjectParty(id=u(), company_id=COMPANY, party_type="developer", name="Alpha Packaging Sdn Bhd")
    beta = ProjectParty(id=u(), company_id=COMPANY, party_type="developer", name="Beta Holdings Sdn Bhd")
    db.add_all([alpha, beta])
    db.flush()
    register_project(db, company_id=COMPANY, actor_user_id=admin.id, developer_party_id=beta.id,
                     title="KILANG ALPHA LOT 9001 MUKIM TEBRAU")
    register_project(db, company_id=COMPANY, actor_user_id=admin.id, developer_party_id=alpha.id,
                     title="TAMAN DELTA FASA 4")
    # an approved project whose meaning is near the registration pasted in the pass (live embeddings)
    register_project(db, company_id=COMPANY, actor_user_id=admin.id, developer_party_id=alpha.id,
                     title="CADANGAN KILANG 2 TINGKAT DI ATAS LOT 9001 MUKIM TEBRAU JOHOR BAHRU")

# --- every module installed for the default tenant, so the sidebar renders its groups ------
from app.modules.runtime.installer import (  # noqa: E402
    DEFAULT_TENANT_ID,
    install_modules,
    load_dependency_graph,
)

install_modules(db, DEFAULT_TENANT_ID, sorted(load_dependency_graph(db)), None, action="install")

db.commit()
print(f"admin={ADMIN_EMAIL} slug={SLUG} token={TOKEN}")
