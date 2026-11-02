"""QUOTE-COVER-PAGE red test: the project detail names the main contact's email, beside
customer_attn, so the quotation form can prefill Email (UAC B2)."""
from __future__ import annotations

import uuid

from app.models.order import CustomerContact

from .test_project_customer_from_lead import (  # noqa: F401  (api is a fixture)
    CUSTOMERS_VIEW,
    FULL_PERMS,
    PROJECTS_BASE,
    _as,
    _lead_with_customer,
    _register,
    api,
)


def test_project_detail_carries_customer_email_from_the_main_contact(api):
    client, db, company_id, user_id = api
    lead = _lead_with_customer(client, db, company_id, f"zzt Cover Builders {uuid.uuid4().hex[:8]}")
    db.add(
        CustomerContact(
            company_id=company_id,
            customer_id=lead["customer_id"],
            full_name="Lim Wei Ming",
            contact_role="main",
            email="lim.weiming@zzt.test",
        )
    )
    db.flush()
    project = _register(client, lead_id=lead["id"], customer_id=lead["customer_id"]).json()
    reader = _as(db, user_id, FULL_PERMS + [CUSTOMERS_VIEW])

    body = reader.get(f"{PROJECTS_BASE}/{project['id']}").json()

    assert body["customer_attn"] == "Lim Wei Ming"
    assert body["customer_email"] == "lim.weiming@zzt.test"
