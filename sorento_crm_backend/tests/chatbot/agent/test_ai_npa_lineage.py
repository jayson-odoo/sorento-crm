"""NPA-FROM-SI rule 8: the assistant reads stock inquiries, New Product Applications and the code lineage
through the registry (AI tools standard), inside the user's company and own scope.

Card: documentation/plans/procurement/CARD-npa-from-si-07nov.md. Helpers: the AI-QUERY-CORE suite's.
"""
from __future__ import annotations

import uuid
from datetime import datetime

import app.main  # noqa: F401  register every model and the app's listeners
from app.models.new_product_application import (
    NewProductApplication,
    NewProductApplicationLine,
    NewProductApplicationSource,
)
from app.models.procurement import StockInquiry
from tests.chatbot.agent.test_ai_query_core import (  # noqa: F401  (fixtures by import)
    SORENTO,
    _listeners,
    code,
    core,
    db,
    mk_company_b,
    mk_product,
    mk_product_chain,
    mk_user,
    tag,
)
from tests._own_scope_support import contact as mk_contact

NPA_VIEW = "procurement.new_product_applications.view"
NPA_OWN = "procurement.new_product_applications.view_own"
SI_VIEW = "procurement.stock_inquiries.view"


def mk_lineage(db, t, *, company_id=SORENTO, applicant=None, contact=None, why="mirror 600 x 900"):
    """A completed application: built from two current codes, its ONE new code linked."""
    chain = mk_product_chain(db, company_id)
    cur_a = mk_product(db, f"{t}-A", chain)
    cur_b = mk_product(db, f"{t}-B", chain)
    new = mk_product(db, f"{t}-NEW", chain)
    for p in (cur_a, cur_b, new):
        p.company_id = company_id
    app_row = NewProductApplication(
        id=str(uuid.uuid4()), company_id=company_id, application_no=f"NPA-{t}", status="completed",
        applicant_id=applicant, contact_id=str(contact.id) if contact else None,
        customer_name=f"ZZT {t} customer", new_product_id=new.id, new_code_at=datetime.utcnow(),
    )
    app_row.lines.append(NewProductApplicationLine(id=str(uuid.uuid4()), line_no=1, description=why))
    app_row.sources = [
        NewProductApplicationSource(id=str(uuid.uuid4()), product_id=cur_a.id, position=1),
        NewProductApplicationSource(id=str(uuid.uuid4()), product_id=cur_b.id, position=2),
    ]
    db.add(app_row)
    db.flush()
    return app_row, cur_a, cur_b, new


def test_why_does_a_code_exist(db):
    t = tag()
    row, _a, _b, new = mk_lineage(db, t)
    user = mk_user(db, NPA_VIEW)
    out = core(db, user, {
        "entity": "new_product_application_line",
        "fields": ["description", "application.application_no"],
        "filters": [{"field": "application.new_product.product_code", "op": "eq", "value": new.product_code}],
    })
    [r] = out["rows"]
    assert r["description"] == "mirror 600 x 900"
    assert r["application.application_no"] == row.application_no


def test_which_codes_a_new_code_was_made_from_and_what_was_made_from_a_code(db):
    t = tag()
    _row, a, b, new = mk_lineage(db, t)
    user = mk_user(db, NPA_VIEW)
    sources = core(db, user, {
        "entity": "new_product_application_source",
        "fields": ["product.product_code"],
        "filters": [{"field": "application.new_product.product_code", "op": "eq", "value": new.product_code}],
        "sort": [{"field": "position", "dir": "asc"}],
    })
    assert [r["product.product_code"] for r in sources["rows"]] == [a.product_code, b.product_code]
    made = core(db, user, {
        "entity": "new_product_application_source",
        "fields": ["application.new_product.product_code"],
        "filters": [{"field": "product.product_code", "op": "eq", "value": a.product_code}],
    })
    assert [r["application.new_product.product_code"] for r in made["rows"]] == [new.product_code]


def test_another_companys_lineage_never_shows(db):
    t = tag()
    other = mk_company_b(db)
    _row, a, _b, new = mk_lineage(db, t, company_id=other)
    user = mk_user(db, NPA_VIEW)
    lines = core(db, user, {
        "entity": "new_product_application_line", "fields": ["description"],
        "filters": [{"field": "description", "op": "eq", "value": "mirror 600 x 900"},
                    {"field": "application.application_no", "op": "eq", "value": f"NPA-{t}"}],
    })
    assert lines["rows"] == []
    sources = core(db, user, {
        "entity": "new_product_application_source", "fields": ["position"],
        "filters": [{"field": "application.application_no", "op": "eq", "value": f"NPA-{t}"}],
    })
    assert sources["rows"] == []


def test_view_own_sees_only_their_own_applications_lines(db):
    t = tag()
    ca = mk_contact(db, "NPA-A")
    owner = mk_user(db, NPA_OWN, contact=ca)
    mine, *_ = mk_lineage(db, t + "M", applicant=owner)
    by_contact, *_ = mk_lineage(db, t + "C", contact=ca)
    mk_lineage(db, t + "O")
    out = core(db, owner, {
        "entity": "new_product_application", "fields": ["application_no"],
        "filters": [{"field": "application_no", "op": "starts_with", "value": f"NPA-{t}"}],
    })
    assert {code(r) for r in out["rows"]} == {mine.application_no, by_contact.application_no}
    lines = core(db, owner, {
        "entity": "new_product_application_line", "fields": ["application.application_no"],
        "filters": [{"field": "application.application_no", "op": "starts_with", "value": f"NPA-{t}"}],
    })
    assert {r["application.application_no"] for r in lines["rows"]} == {mine.application_no, by_contact.application_no}


def test_stock_inquiry_carries_purchasings_npa_ask(db):
    t = tag()
    db.add(StockInquiry(id=str(uuid.uuid4()), inquiry_number=f"SI-{t}", status="responded", npa_requested=True))
    db.flush()
    user = mk_user(db, SI_VIEW)
    out = core(db, user, {
        "entity": "stock_inquiry", "fields": ["npa_requested"],
        "filters": [{"field": "inquiry_number", "op": "eq", "value": f"SI-{t}"}],
    })
    assert [r["npa_requested"] for r in out["rows"]] == [True]


def test_a_typed_new_code_is_answerable(db):
    t = tag()
    row, *_ = mk_lineage(db, t)
    row.new_product_id, row.new_code_text = None, f"{t}-TYPED"
    db.flush()
    user = mk_user(db, NPA_VIEW)
    out = core(db, user, {
        "entity": "new_product_application", "fields": ["new_code_text"],
        "filters": [{"field": "new_code_text", "op": "eq", "value": f"{t}-TYPED"}],
    })
    assert [r["new_code_text"] for r in out["rows"]] == [f"{t}-TYPED"]
