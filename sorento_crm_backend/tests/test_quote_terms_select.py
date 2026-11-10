"""QUOTE-TERMS-SELECT: Payment Terms picked from the AutoCount-synced terms master, Validity as a
number + day/week/month/year. Plan: documentation/plans/projects/PLAN-quote-terms-select-10nov.md.

The print text stays in the existing ``payment_terms`` / ``validity`` text columns (issue freeze,
cover, PDF and sign link read those unchanged); the structured fields decide that text on save.
A legacy free-text value no structured field touched is kept as it is (no silent loss).

Postgres only, through the shared quotation document ``api`` fixture.
"""
from __future__ import annotations

import pytest

from app.services import quote_terms_service as qts

from .test_project_quotation_document_routes import (  # noqa: F401  (api is a fixture)
    BASE,
    _create_document,
    api,
)

TEMPLATES = f"{BASE}/config/quotation-templates"
MARKER = "zzt-qterms"


# ------------------------------------------------------------------------------ pure rules


@pytest.mark.parametrize(
    "value,unit,expected",
    [(2, "week", "2 WEEKS"), (1, "month", "1 MONTH"), (30, "day", "30 DAYS"), (1, "year", "1 YEAR")],
)
def test_validity_prints_number_and_unit_upper_case_plural_when_not_one(value, unit, expected):
    assert qts.format_validity(value, unit) == expected


@pytest.mark.parametrize(
    "text,expected",
    [
        ("30 days", (30, "day")),
        (" 2 Weeks ", (2, "week")),
        ("1 month", (1, "month")),
        ("2 WEEKS", (2, "week")),
        ("1 year", (1, "year")),
        ("30 days from quotation date", None),
        ("two weeks", None),
        ("", None),
        (None, None),
        ("0 days", None),
    ],
)
def test_legacy_validity_text_maps_only_on_an_exact_number_and_unit(text, expected):
    assert qts.parse_validity(text) == expected


def test_a_term_prints_its_description_else_its_code():
    from types import SimpleNamespace

    assert qts.term_label(SimpleNamespace(term_code="C.B.D.", description="CASH BEFORE DELIVERY")) == (
        "CASH BEFORE DELIVERY"
    )
    assert qts.term_label(SimpleNamespace(term_code="30 DAYS", description=None)) == "30 DAYS"
    assert qts.term_label(SimpleNamespace(term_code="30 DAYS", description="  ")) == "30 DAYS"


# ------------------------------------------------------------------------------ helpers


def _term(db, company_id: str, code: str, description=None, *, is_active=True):
    from app.models.payment_term import PaymentTerm

    row = PaymentTerm(
        company_id=company_id,
        term_code=f"{MARKER}-{code}",
        description=description,
        is_active=is_active,
    )
    db.add(row)
    db.flush()
    return row


def _other_company(db) -> str:
    import uuid

    from app.models.company import Company

    suffix = uuid.uuid4().hex[:6]
    other = Company(id=str(uuid.uuid4()), name=f"{MARKER} other {suffix}", code=f"ZQT{suffix}")
    db.add(other)
    db.flush()
    return str(other.id)


def _terms_template(client, **extra) -> dict:
    body = {"kind": "terms", "name": f"{MARKER} Standard terms", "body_html": "<p>clause</p>", **extra}
    response = client.post(TEMPLATES, json=body)
    assert response.status_code == 201, response.text
    return response.json()


# ------------------------------------------------------------------------------ the select


def test_the_template_select_lists_this_companys_active_terms_only(api):
    client, db, company_id, *_ = api
    cbd = _term(db, company_id, "CBD", "CASH BEFORE DELIVERY")
    _term(db, company_id, "OLD", "RETIRED TERM", is_active=False)
    _term(db, _other_company(db), "ELSE", "SOMEONE ELSES TERM")
    db.commit()

    response = client.get(f"{TEMPLATES}/payment-terms")
    assert response.status_code == 200, response.text
    rows = [row for row in response.json()["data"] if row["code"].startswith(MARKER)]
    assert [row["id"] for row in rows] == [str(cbd.id)]
    assert rows[0] == {
        "id": str(cbd.id),
        "code": f"{MARKER}-CBD",
        "description": "CASH BEFORE DELIVERY",
        "label": "CASH BEFORE DELIVERY",
    }


def test_the_quotation_form_has_its_own_select_on_the_project(api):
    client, db, company_id, _user, project, _party = api
    cbd = _term(db, company_id, "CBD", "CASH BEFORE DELIVERY")
    db.commit()
    response = client.get(f"{BASE}/projects/{project.id}/quotation-documents/payment-terms")
    assert response.status_code == 200, response.text
    assert str(cbd.id) in {row["id"] for row in response.json()["data"]}


# ------------------------------------------------------------------------------ template


def test_template_picks_a_term_and_a_validity_and_prints_both(api):
    client, db, company_id, *_ = api
    cbd = _term(db, company_id, "CBD", "CASH BEFORE DELIVERY")
    db.commit()

    created = _terms_template(
        client, payment_term_id=str(cbd.id), validity_value=2, validity_unit="week"
    )
    assert created["payment_term_id"] == str(cbd.id)
    assert created["payment_terms"] == "CASH BEFORE DELIVERY"
    assert created["validity_value"] == 2
    assert created["validity_unit"] == "week"
    assert created["validity"] == "2 WEEKS"

    updated = client.put(
        f"{TEMPLATES}/{created['id']}", json={"validity_value": 1, "validity_unit": "month"}
    )
    assert updated.status_code == 200, updated.text
    body = updated.json()
    assert body["validity"] == "1 MONTH"
    # Untouched by this save, so unchanged.
    assert body["payment_terms"] == "CASH BEFORE DELIVERY"
    assert body["payment_term_id"] == str(cbd.id)


def test_clearing_the_select_clears_the_printed_text_too(api):
    client, db, company_id, *_ = api
    cbd = _term(db, company_id, "CBD", "CASH BEFORE DELIVERY")
    db.commit()
    created = _terms_template(
        client, payment_term_id=str(cbd.id), validity_value=2, validity_unit="week"
    )

    cleared = client.put(
        f"{TEMPLATES}/{created['id']}",
        json={"payment_term_id": None, "validity_value": None, "validity_unit": None},
    )
    assert cleared.status_code == 200, cleared.text
    body = cleared.json()
    assert body["payment_term_id"] is None and body["payment_terms"] is None
    assert body["validity_value"] is None and body["validity_unit"] is None
    assert body["validity"] is None


def test_a_legacy_free_text_value_survives_a_save_that_does_not_touch_it(api):
    """No silent loss: the old text keeps printing until someone picks."""
    client, *_ = api
    created = _terms_template(
        client,
        payment_terms=f"{MARKER} 50% deposit, balance before delivery",
        validity=f"{MARKER} 30 days from quotation date",
    )
    assert created["payment_term_id"] is None and created["validity_value"] is None

    renamed = client.put(f"{TEMPLATES}/{created['id']}", json={"name": f"{MARKER} renamed"})
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["payment_terms"] == f"{MARKER} 50% deposit, balance before delivery"
    assert renamed.json()["validity"] == f"{MARKER} 30 days from quotation date"


@pytest.mark.parametrize(
    "body",
    [
        {"validity_value": 2, "validity_unit": "fortnight"},
        {"validity_value": 0, "validity_unit": "day"},
        {"validity_value": 1000, "validity_unit": "day"},
        {"validity_value": 2},
        {"validity_unit": "week"},
        {"validity_value": 2, "validity_unit": None},
    ],
)
def test_a_validity_needs_a_number_from_1_to_999_and_a_known_unit(api, body):
    client, *_ = api
    created = _terms_template(client)
    response = client.put(f"{TEMPLATES}/{created['id']}", json=body)
    assert response.status_code == 422, response.text


def test_a_term_of_another_company_or_unknown_is_refused(api):
    import uuid

    client, db, _company_id, *_ = api
    foreign = _term(db, _other_company(db), "ELSE", "SOMEONE ELSES TERM")
    db.commit()
    created = _terms_template(client)
    for term_id in (str(foreign.id), str(uuid.uuid4())):
        response = client.put(f"{TEMPLATES}/{created['id']}", json={"payment_term_id": term_id})
        assert response.status_code == 422, response.text
        assert response.json().get("code") == "payment_term_unknown", response.text


def test_an_inactive_term_cannot_be_newly_picked(api):
    client, db, company_id, *_ = api
    old = _term(db, company_id, "OLD", "RETIRED TERM", is_active=False)
    db.commit()
    created = _terms_template(client)
    response = client.put(f"{TEMPLATES}/{created['id']}", json={"payment_term_id": str(old.id)})
    assert response.status_code == 422, response.text


# ------------------------------------------------------------------------------ quotation copy


def test_letter_templates_carry_the_structured_defaults(api):
    client, db, company_id, _user, project, _party = api
    cbd = _term(db, company_id, "CBD", "CASH BEFORE DELIVERY")
    db.commit()
    made = _terms_template(
        client, payment_term_id=str(cbd.id), validity_value=2, validity_unit="week"
    )
    assert made["is_active"] is True

    got = client.get(f"{BASE}/projects/{project.id}/quotation-documents/letter-templates").json()
    assert got["payment_term_id"] == str(cbd.id)
    assert got["payment_terms"] == "CASH BEFORE DELIVERY"
    assert got["validity_value"] == 2
    assert got["validity_unit"] == "week"
    assert got["validity"] == "2 WEEKS"


def test_a_quotation_picks_and_patches_its_own_terms(api):
    client, db, company_id, _user, project, _party = api
    cbd = _term(db, company_id, "CBD", "CASH BEFORE DELIVERY")
    net = _term(db, company_id, "N30", None)
    db.commit()
    root = f"{BASE}/projects/{project.id}/quotation-documents"

    created = _create_document(
        client, project.id, payment_term_id=str(cbd.id), validity_value=2, validity_unit="week"
    )
    assert created["payment_term_id"] == str(cbd.id)
    assert created["payment_terms"] == "CASH BEFORE DELIVERY"
    assert created["validity"] == "2 WEEKS"
    assert created["validity_value"] == 2 and created["validity_unit"] == "week"

    patched = client.patch(f"{root}/{created['id']}", json={"payment_term_id": str(net.id)})
    assert patched.status_code == 200, patched.text
    # No description: the code prints.
    assert patched.json()["payment_terms"] == f"{MARKER}-N30"
    assert patched.json()["validity"] == "2 WEEKS"

    reread = client.get(f"{root}/{created['id']}").json()
    assert reread["payment_term_id"] == str(net.id)


def test_a_quotation_keeps_legacy_text_on_a_header_save(api):
    client, _db, _company_id, _user, project, _party = api
    root = f"{BASE}/projects/{project.id}/quotation-documents"
    created = _create_document(client, project.id, payment_terms=f"{MARKER} 50% deposit")
    patched = client.patch(f"{root}/{created['id']}", json={"attn_name": "Mr Tan"})
    assert patched.status_code == 200, patched.text
    assert patched.json()["payment_terms"] == f"{MARKER} 50% deposit"


def test_the_cover_preview_prints_the_picked_values_before_save(api):
    client, db, company_id, _user, project, _party = api
    cbd = _term(db, company_id, "CBD", "CASH BEFORE DELIVERY")
    db.commit()
    response = client.post(
        f"{BASE}/projects/{project.id}/quotation-documents/cover-preview",
        json={"payment_term_id": str(cbd.id), "validity_value": 2, "validity_unit": "week"},
    )
    assert response.status_code == 200, response.text
    rows = {row["key"]: row for row in response.json()["cover_rows"]}
    assert rows["payment_terms"]["text"] == "CASH BEFORE DELIVERY"
    assert rows["validity"]["text"] == "2 WEEKS"


# ------------------------------------------------------------------------------ customer default
# Owner Q3 (10 Nov 2026): a new quotation defaults to the customer's AutoCount debtor terms
# (Debtor.DisplayTerm, `customers.payment_terms_code`) when they name a synced term; the terms
# template's default otherwise.


def _customer_on(db, project, company_id: str, terms_code):
    import uuid

    from app.models.order import Customer

    customer = Customer(
        company_id=company_id,
        customer_code=f"ZQT{uuid.uuid4().hex[:8]}".upper(),
        customer_name=f"{MARKER} customer",
        payment_terms_code=terms_code,
    )
    db.add(customer)
    db.flush()
    from app.models.projects import ProjectSalesProfile

    profile = db.query(ProjectSalesProfile).filter(ProjectSalesProfile.project_id == project.id).first()
    if profile is None:
        profile = ProjectSalesProfile(project_id=project.id)
        db.add(profile)
    profile.customer_id = str(customer.id)
    db.commit()
    return customer


def test_a_new_quotation_defaults_to_the_customers_debtor_terms(api):
    client, db, company_id, _user, project, _party = api
    template_term = _term(db, company_id, "CBD", "CASH BEFORE DELIVERY")
    debtor_term = _term(db, company_id, "N30", "30 DAYS FROM INVOICE")
    db.commit()
    _terms_template(
        client, payment_term_id=str(template_term.id), validity_value=2, validity_unit="week"
    )
    # Spelled the way AutoCount may send it: other case, stray spaces.
    _customer_on(db, project, company_id, f"  {MARKER}-n30 ")

    got = client.get(f"{BASE}/projects/{project.id}/quotation-documents/letter-templates").json()
    assert got["payment_term_id"] == str(debtor_term.id)
    assert got["payment_terms"] == "30 DAYS FROM INVOICE"
    # Validity is still the template's.
    assert got["validity"] == "2 WEEKS" and got["validity_value"] == 2


@pytest.mark.parametrize("terms_code", [None, "", "NO-SUCH-TERM"])
def test_without_a_synced_debtor_term_the_template_default_stands(api, terms_code):
    client, db, company_id, _user, project, _party = api
    template_term = _term(db, company_id, "CBD", "CASH BEFORE DELIVERY")
    db.commit()
    _terms_template(client, payment_term_id=str(template_term.id))
    _customer_on(db, project, company_id, terms_code)

    got = client.get(f"{BASE}/projects/{project.id}/quotation-documents/letter-templates").json()
    assert got["payment_term_id"] == str(template_term.id)
    assert got["payment_terms"] == "CASH BEFORE DELIVERY"


def test_an_inactive_debtor_term_does_not_become_the_default(api):
    client, db, company_id, _user, project, _party = api
    _term(db, company_id, "OLD", "RETIRED", is_active=False)
    db.commit()
    _customer_on(db, project, company_id, f"{MARKER}-OLD")
    got = client.get(f"{BASE}/projects/{project.id}/quotation-documents/letter-templates").json()
    assert got["payment_term_id"] is None


# ------------------------------------------------------------------------------ review round 1


def test_a_deactivated_template_term_does_not_block_new_quotations(api):
    """Reviewer blocker: the template's term deactivated in AutoCount must not seed a create that
    `resolve` then refuses. The text still prints and shows as the legacy value."""
    client, db, company_id, _user, project, _party = api
    cbd = _term(db, company_id, "CBD", "CASH BEFORE DELIVERY")
    db.commit()
    _terms_template(client, payment_term_id=str(cbd.id))
    cbd.is_active = False
    db.commit()

    got = client.get(f"{BASE}/projects/{project.id}/quotation-documents/letter-templates").json()
    assert got["payment_term_id"] is None
    assert got["payment_terms"] == "CASH BEFORE DELIVERY"

    # As the form sends it: a null default id is not sent at all (QuotationFormClient).
    created = _create_document(client, project.id, payment_terms=got["payment_terms"])
    assert created["payment_terms"] == "CASH BEFORE DELIVERY"


def test_a_quotation_on_a_term_later_deactivated_still_prints_and_saves(api):
    """AC-B4: picked, then deactivated: still printed, and an unrelated save still works."""
    client, db, company_id, _user, project, _party = api
    cbd = _term(db, company_id, "CBD", "CASH BEFORE DELIVERY")
    db.commit()
    root = f"{BASE}/projects/{project.id}/quotation-documents"
    created = _create_document(client, project.id, payment_term_id=str(cbd.id))
    cbd.is_active = False
    db.commit()

    patched = client.patch(f"{root}/{created['id']}", json={"attn_name": "Mr Tan"})
    assert patched.status_code == 200, patched.text
    assert patched.json()["payment_term_id"] == str(cbd.id)
    assert patched.json()["payment_terms"] == "CASH BEFORE DELIVERY"


@pytest.mark.parametrize("bad", ["not-a-uuid", "123"])
def test_a_malformed_term_id_is_a_422_not_a_500(api, bad):
    client, *_ = api
    created = _terms_template(client)
    response = client.put(f"{TEMPLATES}/{created['id']}", json={"payment_term_id": bad})
    assert response.status_code == 422, response.text
    assert response.json().get("code") == "payment_term_unknown"


def test_the_migration_backfill_maps_only_an_exact_number_and_unit(api):
    """AC-D3: the migration's own SQL rule, run against literals, agrees with parse_validity."""
    import importlib.util
    import pathlib

    from sqlalchemy import text

    _client, db, *_ = api
    path = pathlib.Path(__file__).resolve().parents[1] / "alembic/versions/qts_0001_quote_terms_select.py"
    spec = importlib.util.spec_from_file_location("qts_0001", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    samples = ["30 days", " 2 Weeks ", "1 month", "30 days from quotation date", "0 days", "two weeks"]
    for sample in samples:
        row = db.execute(
            text(
                "SELECT (regexp_match(:v, :re, 'i'))[1]::int AS n, "
                "lower((regexp_match(:v, :re, 'i'))[2]) AS u"
            ),
            {"v": sample, "re": module._VALIDITY_RE},
        ).first()
        sql = (row.n, row.u) if row.n is not None and 1 <= row.n <= 999 else None
        assert sql == qts.parse_validity(sample), sample


def test_the_legacy_link_skips_a_quotation_that_is_with_a_manager_or_approved(api, monkeypatch):
    """Security review 4: a sync never writes a locked quotation, not even the link. The
    approval state is stubbed; the lock rule itself has its own suite."""
    from app.models.projects import ProjectQuotationDocument
    from app.services import project_quotation_approval_service as approvals

    client, db, company_id, _user, project, _party = api
    open_doc = _create_document(client, project.id, payment_terms="cash before delivery")
    locked_doc = _create_document(client, project.id, payment_terms="CASH BEFORE DELIVERY")
    term = _term(db, company_id, "CBD", "CASH BEFORE DELIVERY")
    db.commit()

    monkeypatch.setattr(
        approvals,
        "current_key",
        lambda _db, document: approvals.STATUS_APPROVED if str(document.id) == locked_doc["id"] else None,
    )
    qts.link_legacy_terms(db, company_id=company_id)

    rows = {
        str(row.id): row
        for row in db.query(ProjectQuotationDocument)
        .filter(ProjectQuotationDocument.id.in_([open_doc["id"], locked_doc["id"]]))
        .all()
    }
    assert str(rows[open_doc["id"]].payment_term_id) == str(term.id)
    assert rows[locked_doc["id"]].payment_term_id is None
