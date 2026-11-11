"""Synthetic seed for the TRACE-ENTITY-TOOL browser pass. Sandbox DB (sorento_browse) only.

Run from sorento_crm_backend:
  SORENTO_ENV_FILE=.env.browse BROWSE_ADMIN_PASSWORD=... venv/bin/python <this file>

Writes (all invented): a superadmin and three chatbot turns for one test contact "ZZT-900001":
  1. "hi"         first message (no earlier turn)
  2. "srtwc286"   business_query stock check, trace shaped like turn #8322: the named stock tool
                  event (157 ms), then the fetch step's bare {"domain"} event, a `resolve` event
                  (srtwc286 -> SRTWC286, AND mode), and a span pass with the code span skipped
  3. "thanks"     latest message (no later turn)
Installs every module for the default tenant.
"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, ".")
from app.main import app  # noqa: E402,F401  (import order: circular import)
from app.database import engine  # noqa: E402
from app.models.chatbot_turn import ChatbotTurn  # noqa: E402
from app.models.company import UserCompany  # noqa: E402
from app.models.user import User, UserRoleAssignment  # noqa: E402

COMPANY = "00000000-0000-0000-0000-000000000001"
PASSWORD = os.environ["BROWSE_ADMIN_PASSWORD"]  # throwaway, sandbox DB only
CONTACT = "ZZT-900001"
db = sessionmaker(bind=engine)()

if db.query(User).filter(User.email == "browse.admin@example.com").one_or_none() is None:
    admin = User(id=str(uuid.uuid4()), email="browse.admin@example.com", name="Browse Admin", status="ACTIVE",
                 password=bcrypt.hashpw(PASSWORD.encode(), bcrypt.gensalt()).decode())
    db.add(admin)
    db.flush()
    role = db.execute(text(
        "SELECT id FROM user_roles WHERE slug IN ('superadmin','super_admin') OR name ILIKE 'super admin' LIMIT 1"
    )).scalar()
    db.add(UserRoleAssignment(user_id=admin.id, role_id=role))
    db.add(UserCompany(id=str(uuid.uuid4()), user_id=admin.id, company_id=COMPANY))
    db.flush()

db.query(ChatbotTurn).filter(ChatbotTurn.contact_respond_id == CONTACT).delete()
base = datetime(2026, 11, 11, 11, 30, tzinfo=timezone.utc)


def stage(name, summary, facts=None, ms=5):
    return {"stage": name, "status": "ok", "started_at": base.isoformat(), "ms": ms, "summary": summary,
            "why": summary, "facts": facts or {}, "error": None, "raw": {}}


def envelope(text_value):
    return {"message": {"message": {"message": {"type": "text", "text": text_value}}}}


def turn(n, text_value, branch, trace):
    return ChatbotTurn(
        id=str(uuid.uuid4()), contact_respond_id=CONTACT, message_id=f"wamid.zzt.trace.{n}", ingress="webhook",
        envelope=envelope(text_value), is_test=False, status="done", stage="sent", branch_kind=branch, attempt=1,
        trace=trace, response={"reply": {"text": "ok"}}, created_at=base + timedelta(minutes=n),
        finished_at=base + timedelta(minutes=n, seconds=2),
    )


at = base.isoformat()
stock_trace = [
    stage("received", "Message received"),
    stage("queued", "Queued", {"ticket": 2, "wait_ms": 40}),
    stage("understood", "Understood as a business query about product srtwc286"),
    {"kind": "span_extract", "at": at, "spans": [{"text": "srtwc286", "type": "product_code", "status": "skipped",
                                                  "close": 0}],
     "rows_rendered": 0, "near_exact_rows": 0, "fallback": False, "fallback_reason": None, "provider": "gemini",
     "model": "gemini-flash", "model_source": "global", "ms": 640,
     "tokens": {"prompt_tokens": 410, "completion_tokens": 12, "total_tokens": 422, "cached_tokens": 0},
     "near_exact": [], "final_block": {}},
    {"kind": "resolve", "at": at, "words": [{"word": "srtwc286", "codes": ["SRTWC286"], "more": 0, "tiers": ["and"],
                                              "kinds": ["product"], "ambiguous": False}],
     "unplaced": [], "not_checked": []},
    {"kind": "tool", "at": at, "name": "crm_inventory_stock_balance_list",
     "args": {"product_codes": ["SRTWC286"], "contact_id": "x", "space_id": "y"},
     "envelope": {"has_result": True, "items": [{"title": "SRTWC286"}]}, "ms": 157},
    {"kind": "tool", "at": at, "domain": "inventory"},
    stage("sent", "Reply sent"),
]
db.add_all([
    turn(1, "hi", "greeting", [stage("received", "Message received"), stage("queued", "Queued", {"ticket": 1, "wait_ms": 10})]),
    turn(2, "srtwc286", "business_query", stock_trace),
    turn(3, "thanks", "greeting", [stage("received", "Message received"), stage("queued", "Queued", {"ticket": 3, "wait_ms": 8})]),
])
db.commit()

from app.modules.runtime.installer import DEFAULT_TENANT_ID, install_modules, load_dependency_graph  # noqa: E402

admin_id = db.query(User).filter(User.email == "browse.admin@example.com").one().id
install_modules(db, DEFAULT_TENANT_ID, sorted(load_dependency_graph(db).keys()), actor_user_id=admin_id)
db.commit()
print("seeded", CONTACT)
