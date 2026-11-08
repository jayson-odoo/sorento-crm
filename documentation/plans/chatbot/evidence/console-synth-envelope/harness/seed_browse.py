"""Synthetic seed for the CONSOLE-SYNTH-ENVELOPE browser pass. Sandbox DB (sorento_browse) only.

Run from sorento_crm_backend:
  SORENTO_ENV_FILE=.env.browse BROWSE_ADMIN_PASSWORD=... venv/bin/python <this file>

Writes (all names invented) one superadmin and one respond contact with NO chatbot turn on
record, the case the lane is for.
"""
from __future__ import annotations

import os
import sys
import uuid

import bcrypt
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, ".")
from app.main import app  # noqa: E402,F401  (import order: circular import)
from app.database import engine  # noqa: E402
from app.models.company import UserCompany  # noqa: E402
from app.models.user import User, UserRoleAssignment  # noqa: E402

COMPANY = "00000000-0000-0000-0000-000000000001"
PASSWORD = os.environ["BROWSE_ADMIN_PASSWORD"]  # throwaway, sandbox DB only
db = sessionmaker(bind=engine)()

if db.query(User).filter(User.email == "browse.admin@example.com").one_or_none() is None:
    row = User(id=str(uuid.uuid4()), email="browse.admin@example.com", name="Browse Admin", status="ACTIVE",
               password=bcrypt.hashpw(PASSWORD.encode(), bcrypt.gensalt()).decode())
    db.add(row)
    db.flush()
    role = db.execute(text("SELECT id FROM user_roles WHERE slug IN ('superadmin','super_admin') "
                           "OR name ILIKE 'super admin' LIMIT 1")).scalar()
    db.add(UserRoleAssignment(user_id=row.id, role_id=role))
    db.add(UserCompany(id=str(uuid.uuid4()), user_id=row.id, company_id=COMPANY))

db.execute(text(
    "INSERT INTO respond_contacts (id, respond_io_id, phone_number, name, first_name, session_vars) "
    "SELECT gen_random_uuid()::text, '900000777', '+60190000777', 'Simulated Dealer', 'Simulated', '{}'::jsonb "
    "WHERE NOT EXISTS (SELECT 1 FROM respond_contacts WHERE respond_io_id = '900000777')"
))
db.commit()
print("turns for contact:", db.execute(text(
    "SELECT count(*) FROM chatbot.turns WHERE contact_respond_id = '900000777'")).scalar())
