"""QUOTE-TERMS-SELECT: the AutoCount `payment_terms` ingest master (contract 2.14).

The contract as posted on PR #2305 for the shared-service lane (SS-PAYMENT-TERMS): push, read
door, deactivate-only deletions, and the legacy-text link a non-dry push makes.
Substrate: the item-class ingest suite's ``env`` fixture (blank scratch schema, superadmin
principal).
"""
from __future__ import annotations

import uuid

from sqlalchemy import text

from .test_ingest_item_classes import CONTRACT_URL, env  # noqa: F401  (env is a fixture)

MARKER = "ZZTPTM"
INGEST = "/api/v1/external/ingest/payment_terms"
READ = "/api/v1/external/read/payment_terms"
DELETE = "/api/v1/external/ingest/payment_terms/deletions"


def _ref() -> str:
    return f"{MARKER}:{uuid.uuid4().hex[:10]}"


def _code() -> str:
    return f"{MARKER}{uuid.uuid4().hex[:6]}".upper()


def _row(env, code: str, company_id: str):
    return env.db.execute(
        text("SELECT * FROM payment_terms WHERE term_code = :c AND company_id = :cid"),
        {"c": code, "cid": company_id},
    ).mappings().first()


def test_contract_names_the_entity_and_its_fields(env):
    body = env.client.get(CONTRACT_URL).json()
    assert body["version"] == "2.14"
    assert "payment_terms" in body["entities"]
    assert body["fields_added"]["payment_terms"] == ["code", "description", "term_days", "is_active"]


def test_a_push_creates_then_updates_one_row_per_company(env):
    ref, code = _ref(), _code()
    first = env.post(INGEST, [{"source_ref": ref, "code": code, "description": "CASH BEFORE DELIVERY",
                               "term_days": 0}])
    assert first.status_code == 200, first.text
    row = _row(env, code, env.company_a)
    assert row is not None
    assert row["description"] == "CASH BEFORE DELIVERY"
    assert row["term_days"] == 0
    assert row["is_active"] is True
    assert _row(env, code, env.company_b) is None

    again = env.post(INGEST, [{"source_ref": ref, "code": code, "description": "CASH ON DELIVERY"}])
    assert again.status_code == 200, again.text
    assert _row(env, code, env.company_a)["description"] == "CASH ON DELIVERY"
    count = env.db.execute(
        text("SELECT count(*) FROM payment_terms WHERE term_code = :c"), {"c": code}
    ).scalar()
    assert count == 1


def test_the_read_door_returns_the_stored_fields(env):
    ref, code = _ref(), _code()
    pushed = env.post(INGEST, [{"source_ref": ref, "code": code, "description": "NET 30", "term_days": 30}])
    assert pushed.json()["records"][0]["outcome"] == "created", pushed.text
    # Not env.read(): that helper is bound to the item classes door.
    response = env.client.post(READ, json={"companyCode": env.company_a_code, "source_refs": [ref]})
    assert response.status_code == 200, response.text
    assert ref in response.text and "NET 30" in response.text


def test_deletions_only_deactivate(env):
    ref, code = _ref(), _code()
    env.post(INGEST, [{"source_ref": ref, "code": code, "description": "NET 30"}])
    response = env.client.post(DELETE, json={"companyCode": env.company_a_code, "source_refs": [ref]})
    assert response.status_code == 200, response.text
    row = _row(env, code, env.company_a)
    assert row is not None and row["is_active"] is False


def test_a_push_links_legacy_text_that_matches_exactly_and_leaves_the_rest(env):
    from app.models.projects import QuotationTemplate

    code = _code()
    matching = QuotationTemplate(
        company_id=env.company_a, kind="terms", name=f"{MARKER} a", body_html="<p>x</p>",
        payment_terms="  cash   before delivery ",
    )
    by_code = QuotationTemplate(
        company_id=env.company_a, kind="terms", name=f"{MARKER} b", body_html="<p>x</p>",
        payment_terms=code.lower(),
    )
    unmatched = QuotationTemplate(
        company_id=env.company_a, kind="terms", name=f"{MARKER} c", body_html="<p>x</p>",
        payment_terms="50% deposit, balance before delivery",
    )
    other_company = QuotationTemplate(
        company_id=env.company_b, kind="terms", name=f"{MARKER} d", body_html="<p>x</p>",
        payment_terms="CASH BEFORE DELIVERY",
    )
    env.db.add_all([matching, by_code, unmatched, other_company])
    env.db.commit()

    pushed = env.post(INGEST, [{"source_ref": _ref(), "code": code, "description": "CASH BEFORE DELIVERY"}])
    assert pushed.status_code == 200, pushed.text
    term_id = str(_row(env, code, env.company_a)["id"])

    for template in (matching, by_code, unmatched, other_company):
        env.db.refresh(template)
    assert str(matching.payment_term_id) == term_id
    assert str(by_code.payment_term_id) == term_id
    # Printed text is never rewritten by a sync.
    assert matching.payment_terms == "  cash   before delivery "
    assert unmatched.payment_term_id is None
    assert other_company.payment_term_id is None


def test_a_dry_run_links_nothing(env):
    from app.models.projects import QuotationTemplate

    code = _code()
    template = QuotationTemplate(
        company_id=env.company_a, kind="terms", name=f"{MARKER} e", body_html="<p>x</p>",
        payment_terms=code,
    )
    env.db.add(template)
    env.db.commit()
    env.post(INGEST, [{"source_ref": _ref(), "code": code}], dry_run=True)
    env.db.refresh(template)
    assert template.payment_term_id is None


# Owner Q3: the customer feed carries AutoCount Debtor.DisplayTerm again (contract 2.14).

def _customer_terms(env, code: str):
    return env.db.execute(
        text("SELECT payment_terms_code FROM customers WHERE customer_code = :c AND company_id = :cid"),
        {"c": code, "cid": env.company_a},
    ).scalar()


def test_the_customer_feed_stores_the_debtor_terms_code(env):
    code = _code()
    customers = "/api/v1/external/ingest/customers"
    record = {"source_ref": _ref(), "code": code, "name": f"{MARKER} debtor", "payment_terms_code": "C.B.D."}
    assert env.post(customers, [record]).status_code == 200
    assert _customer_terms(env, code) == "C.B.D."

    # Absent = untouched.
    untouched = {k: v for k, v in record.items() if k != "payment_terms_code"}
    assert env.post(customers, [untouched]).status_code == 200
    assert _customer_terms(env, code) == "C.B.D."

    # Blank = cleared (D14).
    assert env.post(customers, [{**record, "payment_terms_code": ""}]).status_code == 200
    assert _customer_terms(env, code) is None


def test_contract_lists_the_customer_field_as_added_not_removed(env):
    body = env.client.get(CONTRACT_URL).json()
    assert "payment_terms_code" in body["fields_added"]["customers"]
    assert "payment_terms_code" not in body["fields_removed"].get("customers", [])


def test_a_push_never_links_legacy_text_to_an_inactive_term(env):
    from app.models.projects import QuotationTemplate

    code = _code()
    template = QuotationTemplate(
        company_id=env.company_a, kind="terms", name=f"{MARKER} f", body_html="<p>x</p>",
        payment_terms=code,
    )
    env.db.add(template)
    env.db.commit()
    env.post(INGEST, [{"source_ref": _ref(), "code": code, "is_active": False}])
    env.db.refresh(template)
    assert template.payment_term_id is None
