"""PROJECT-REGISTER-V2 UAC A5, A6 (customer on register) and G1, G2, G4 (brands removed).

Red-first: nothing here relies on code that exists yet. Fixtures are in
`_project_register_v2_support.py`.
"""
from __future__ import annotations

import uuid

from app.main import app  # noqa: F401  MUST be first app import (circular import)

from ._project_register_v2_support import (  # noqa: F401  (v2 is a fixture)
    LIST,
    STAFF,
    as_user,
    developer,
    project,
    register_body,
    seed_lead,
    title,
    uid,
    v2,
)

LEADS = "/api/v1/project-sales/leads"


def _brand(w, name: str = "CONTOH Brand"):
    from app.models.product import Brand

    row = Brand(
        company_id=w.company_id, brand_code=f"ZZT-{uuid.uuid4().hex[:8]}", brand_name=name
    )
    w.db.add(row)
    w.db.flush()
    return row


def _brand_rows(w, project_id: str) -> int:
    from app.models.projects import ProjectBrand

    w.db.expire_all()
    return w.db.query(ProjectBrand).filter(ProjectBrand.project_id == project_id).count()


def _profile(w, project_id: str):
    from app.models.projects import ProjectSalesProfile

    w.db.expire_all()
    return w.db.get(ProjectSalesProfile, project_id)


# ------------------------------------------------------------------ A5 customer on register


def test_a5_register_without_a_customer_is_422_project_customer_required(v2):
    # A lead with no customer: the customer is then the one thing missing (E3).
    lead = seed_lead(v2, v2.owner)
    res = as_user(v2, v2.owner).post(LIST, json={"title": title(), "lead_id": lead.id})
    assert res.status_code == 422, res.text
    assert res.json()["code"] == "project_customer_required"


def test_a5_an_unknown_customer_id_is_422(v2):
    res = as_user(v2, v2.owner).post(LIST, json=register_body(v2, customer_id=uid()))
    assert res.status_code == 422, res.text


def test_a5_a_customer_of_another_company_is_422(v2):
    res = as_user(v2, v2.owner).post(
        LIST, json=register_body(v2, customer_id=v2.foreign_customer.id)
    )
    assert res.status_code == 422, res.text


def test_a5_a_valid_customer_is_stored_in_the_sales_profile_and_returned(v2):
    res = as_user(v2, v2.owner).post(LIST, json=register_body(v2))
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["customer_id"] == v2.customer.id
    assert body["customer_name"] == v2.customer.customer_name
    assert body["customer_code"] == v2.customer.customer_code
    assert str(_profile(v2, body["id"]).customer_id) == v2.customer.id


def test_a5_a_refused_register_writes_no_project(v2):
    from app.models.projects import Project

    before = v2.db.query(Project).count()
    lead = seed_lead(v2, v2.owner)
    as_user(v2, v2.owner).post(LIST, json={"title": title(), "lead_id": lead.id})
    v2.db.expire_all()
    assert v2.db.query(Project).count() == before


def test_a5_put_without_a_customer_keeps_saving(v2):
    old = project(v2.db, v2.company_id, title("Legacy"), owner=v2.owner)
    res = as_user(v2, v2.owner).put(f"{STAFF}/{old.id}", json={"title": title("Renamed")})
    assert res.status_code == 200, res.text


# ------------------------------------------------------------------ A6 lead still links


def test_a6_registering_with_a_lead_still_links_it(v2):
    lead = as_user(v2, v2.owner).post(
        LEADS, json={"title": title("Lead"), "customer_id": v2.customer.id}
    )
    assert lead.status_code in (200, 201), lead.text
    lead_id = lead.json()["id"]
    res = as_user(v2, v2.owner).post(LIST, json=register_body(v2, lead_id=lead_id))
    assert res.status_code == 201, res.text
    assert res.json()["lead_id"] == lead_id


# ------------------------------------------------------------------ G1 brands gone


def test_g1_the_project_response_model_has_no_brand_fields():
    from app.schemas.projects import ProjectResponse

    assert "brands" not in ProjectResponse.model_fields
    assert "brand_ids" not in ProjectResponse.model_fields


def test_g1_register_ignores_brand_ids_and_the_response_has_no_brands(v2):
    brand = _brand(v2)
    res = as_user(v2, v2.owner).post(LIST, json=register_body(v2, brand_ids=[brand.id]))
    assert res.status_code == 201, res.text
    body = res.json()
    assert "brands" not in body and "brand_ids" not in body
    assert _brand_rows(v2, body["id"]) == 0
    got = as_user(v2, v2.owner).get(f"{STAFF}/{body['id']}").json()
    assert "brands" not in got and "brand_ids" not in got


def test_g1_update_ignores_brand_ids(v2):
    brand = _brand(v2)
    pid = as_user(v2, v2.owner).post(LIST, json=register_body(v2)).json()["id"]
    res = as_user(v2, v2.owner).put(f"{STAFF}/{pid}", json={"brand_ids": [brand.id]})
    assert res.status_code == 200, res.text
    assert _brand_rows(v2, pid) == 0


def test_g1_approve_ignores_brand_ids(v2):
    from ._project_registration_support import project as seed

    brand = _brand(v2)
    pending = seed(v2.db, v2.company_id, title("Pending"), approval_state="pending", owner=v2.owner)
    dev = developer(v2.db, v2.company_id, f"CONTOH Dev {uid()[:6]}")
    res = as_user(v2, v2.manager).post(
        f"{STAFF}/{pending.id}/approve",
        json={"developer_party_id": dev.id, "owner_user_id": v2.owner, "brand_ids": [brand.id]},
    )
    assert res.status_code == 200, res.text
    assert "brand_ids" not in res.json()
    assert _brand_rows(v2, pending.id) == 0


def test_g1_lead_qualify_ignores_brand_ids(v2):
    brand = _brand(v2)
    lead = as_user(v2, v2.root).post(LEADS, json={"title": title("Lead")})
    assert lead.status_code in (200, 201), lead.text
    res = as_user(v2, v2.root).post(
        f"{LEADS}/{lead.json()['id']}/qualify", json={"brand_ids": [brand.id]}
    )
    assert res.status_code in (200, 201), res.text
    body = res.json()
    assert "brands" not in body and "brand_ids" not in body
    assert _brand_rows(v2, body["id"]) == 0


# ------------------------------------------------------------------ G2 list and clash


def test_g2_the_list_ignores_brand_id(v2):
    from app.models.projects import ProjectBrand

    brand = _brand(v2)
    tagged = project(v2.db, v2.company_id, title("Tagged"), owner=v2.owner)
    plain = project(v2.db, v2.company_id, title("Plain"), owner=v2.owner)
    v2.db.add(ProjectBrand(project_id=tagged.id, brand_id=brand.id))
    v2.db.flush()
    res = as_user(v2, v2.owner).get(LIST, params={"limit": 100, "brand_id": brand.id})
    assert res.status_code == 200, res.text
    ids = {r["id"] for r in res.json()["data"]}
    assert {tagged.id, plain.id} <= ids


def test_g2_clash_candidates_carry_no_brands(v2):
    ttl = title("Clash")
    dev = developer(v2.db, v2.company_id, f"CONTOH Dev {uid()[:6]}")
    project(v2.db, v2.company_id, ttl, owner=v2.owner, developer_party=dev)
    res = as_user(v2, v2.sales_b).post(
        f"{STAFF}/clash-preview", json={"title": ttl, "developer_party_id": dev.id}
    )
    assert res.status_code == 200, res.text
    candidates = res.json()["candidates"]
    assert candidates
    for c in candidates:
        assert "brands" not in c


# ------------------------------------------------------------------ G4 rows untouched


def test_g4_an_update_leaves_existing_brand_rows_alone_even_when_brand_ids_is_sent_empty(v2):
    from app.models.projects import ProjectBrand

    brand = _brand(v2)
    row = project(v2.db, v2.company_id, title("Branded"), owner=v2.owner)
    v2.db.add(ProjectBrand(project_id=row.id, brand_id=brand.id))
    v2.db.flush()
    res = as_user(v2, v2.owner).put(
        f"{STAFF}/{row.id}", json={"title": title("Renamed"), "brand_ids": []}
    )
    assert res.status_code == 200, res.text
    assert _brand_rows(v2, row.id) == 1


# ------------------------------------------------------------------ customer display fallback (#1618)


def _lead_project(w, *, own_customer=None):
    """A project linked to a lead whose buyer is `w.customer`; the sales profile carries
    `own_customer` (or NULL)."""
    from app.models.projects import ProjectLead, ProjectSalesProfile

    lead = ProjectLead(
        id=uid(), lead_code=f"ZZT-L-{uid()[:8]}", title=title("Lead"),
        normalised_title=title("lead").lower(), company_id=w.company_id,
        customer_id=w.customer.id,
    )
    w.db.add(lead)
    w.db.flush()
    row = project(w.db, w.company_id, title("Linked"), owner=w.owner)
    row.lead_id = lead.id
    w.db.add(
        ProjectSalesProfile(
            project_id=row.id, customer_id=own_customer.id if own_customer else None
        )
    )
    w.db.flush()
    return row


def _list_row(w, project_id: str) -> dict:
    res = as_user(w, w.owner).get(LIST, params={"limit": 100})
    assert res.status_code == 200, res.text
    return next(r for r in res.json()["data"] if r["id"] == project_id)


def test_customer_falls_back_to_the_lead_buyer_on_detail_and_list(v2):
    row = _lead_project(v2)
    detail = as_user(v2, v2.owner).get(f"{STAFF}/{row.id}").json()
    for body in (detail, _list_row(v2, row.id)):
        assert body["customer_id"] == v2.customer.id
        assert body["customer_name"] == v2.customer.customer_name
        assert body["customer_code"] == v2.customer.customer_code


def test_the_sales_profile_customer_wins_over_the_lead_buyer(v2):
    from ._sample_request_seed import make_customer

    own = make_customer(v2.db, v2.company_id)
    row = _lead_project(v2, own_customer=own)
    detail = as_user(v2, v2.owner).get(f"{STAFF}/{row.id}").json()
    assert detail["customer_id"] == own.id
    assert _list_row(v2, row.id)["customer_id"] == own.id


def test_a_put_without_customer_id_pins_nothing_on_the_sales_profile(v2):
    row = _lead_project(v2)
    res = as_user(v2, v2.owner).put(f"{STAFF}/{row.id}", json={"title": title("Renamed")})
    assert res.status_code == 200, res.text
    assert _profile(v2, row.id).customer_id is None
