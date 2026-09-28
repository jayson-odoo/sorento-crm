"""The quotation FORM page's save (issue #1341, UAC quotation-form-28sep).

The owner's ask: "I should be able to add product straight away and save when I am satisfied".
So the create is ONE request carrying the letterhead, the scopes and their lines, and the edit
is ONE request too. What these tests pin, against the UAC rather than the handlers:

- AC-QF014 / AC-QF015: create with scopes and lines lands every row, and a refused line rolls
  the WHOLE create back, so Cancel-by-failure never leaves a half quotation behind.
- AC-QF017: no placeholder line. A scope saved empty has zero lines.
- AC-QF021 / AC-QF023 / AC-QF024: edit applies header, rename, series, new scope and full line
  set in one PATCH; an issued scope refuses lines with the existing 422 and nothing in that
  save lands; a scope left out of the PATCH is untouched.

Postgres only, through the same fixture the document route suite uses.
"""
from __future__ import annotations

from decimal import Decimal

from app.models.projects import (
    ProjectQuotation,
    ProjectQuotationDocument,
    ProjectQuotationLine,
    ProjectQuotationVersion,
)

from .test_project_quotation_document_routes import (  # noqa: F401  (fixture import)
    BASE,
    MARKER,
    _category,
    _product,
    _sign,
    _uom,
    _without_permission,
    api,
)


def _documents(db, project_id: str):
    return (
        db.query(ProjectQuotationDocument)
        .filter(ProjectQuotationDocument.project_id == project_id)
        .all()
    )


def _lines_of_scope(db, scope_id: str):
    version = (
        db.query(ProjectQuotationVersion)
        .filter(ProjectQuotationVersion.quotation_id == scope_id)
        .order_by(ProjectQuotationVersion.version_no.desc())
        .first()
    )
    return (
        db.query(ProjectQuotationLine)
        .filter(ProjectQuotationLine.version_id == version.id)
        .order_by(ProjectQuotationLine.sort_order)
        .all()
    )


def _create(client, project_id: str, body: dict):
    return client.post(f"{BASE}/projects/{project_id}/quotation-documents", json=body)


def _patch(client, project_id: str, document_id: str, body: dict):
    return client.patch(
        f"{BASE}/projects/{project_id}/quotation-documents/{document_id}", json=body
    )


def _seed_product(db, list_price: str = "300.00"):
    uom = _uom(db)
    category = _category(db, "Sanitary Ware")
    product = _product(db, category.id, uom, list_price)
    db.commit()
    return product


# ------------------------------------------------------------------ create


def test_create_writes_the_document_its_scopes_and_every_line_in_one_request(api):
    """AC-QF014: two scopes, three lines, one POST, one quotation that reads back whole."""
    client, db, _company_id, _user_id, project, _party = api
    product = _seed_product(db)

    response = _create(
        client,
        project.id,
        {
            "your_ref": f"{MARKER}/NC/1",
            "attn_name": "Kelly",
            "subject_title": f"{MARKER} Pangsapuri",
            "doc_date": "2026-09-28",
            "scopes": [
                {
                    "scope_label": f"{MARKER} Townhouse",
                    "lines": [
                        {"product_id": product.id, "unit_price": "250.00", "quantity": "4"},
                        {
                            "description_snapshot": "Off-catalog basin mixer",
                            "unit_price": "80.00",
                            "quantity": "2",
                            "band_label": "BILL NO 3",
                        },
                    ],
                },
                {
                    "scope_label": f"{MARKER} Guard House",
                    "lines": [
                        {"product_id": product.id, "unit_price": "400.00", "quantity": "1"},
                    ],
                },
            ],
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()

    assert body["your_ref"] == f"{MARKER}/NC/1"
    assert body["attn_name"] == "Kelly"
    assert [scope["scope_label"] for scope in body["scopes"]] == [
        f"{MARKER} Townhouse",
        f"{MARKER} Guard House",
    ]
    assert [scope["line_count"] for scope in body["scopes"]] == [2, 1]
    assert Decimal(str(body["scopes"][0]["scope_total"])) == Decimal("1160.00")
    assert Decimal(str(body["grand_total"])) == Decimal("1560.00")

    townhouse_lines = _lines_of_scope(db, body["scopes"][0]["id"])
    # Array order is the line order, and the section heading rides on the line that opens it.
    assert [line.product_id for line in townhouse_lines] == [product.id, None]
    assert townhouse_lines[1].description_snapshot == "Off-catalog basin mixer"
    assert townhouse_lines[1].band_label == "BILL NO 3"
    # The product fill is the server's, exactly as the bulk line route does it.
    assert townhouse_lines[0].description_snapshot
    # And the unit: a product line sent with no UOM takes the product's base unit.
    assert townhouse_lines[0].uom


def test_a_refused_line_rolls_the_whole_create_back(api):
    """AC-QF015: an off-catalog line with no description is refused, and NOTHING is left."""
    client, db, _company_id, _user_id, project, _party = api
    product = _seed_product(db)
    before = len(_documents(db, project.id))

    response = _create(
        client,
        project.id,
        {
            "scopes": [
                {
                    "scope_label": f"{MARKER} Townhouse",
                    "lines": [
                        {"product_id": product.id, "unit_price": "250.00", "quantity": "1"},
                        {"unit_price": "10.00", "quantity": "1"},
                    ],
                }
            ]
        },
    )
    assert response.status_code == 422, response.text
    assert response.json().get("code") == "quotation_line_description_required" or (
        "description" in response.text
    )
    db.expire_all()
    assert len(_documents(db, project.id)) == before
    assert (
        db.query(ProjectQuotation)
        .filter(ProjectQuotation.scope_label == f"{MARKER} Townhouse")
        .filter(ProjectQuotation.project_id == project.id)
        .count()
        == 0
    )


def test_create_with_an_empty_scope_writes_no_placeholder_line(api):
    """AC-QF017: a scope saved with no lines holds zero lines, never an "Item 1" stand-in."""
    client, db, _company_id, _user_id, project, _party = api

    response = _create(client, project.id, {"scopes": [{"scope_label": f"{MARKER} Empty"}]})
    assert response.status_code == 201, response.text
    scope = response.json()["scopes"][0]
    assert scope["line_count"] == 0
    assert _lines_of_scope(db, scope["id"]) == []


def test_create_without_scopes_still_answers_the_old_one_press_body(api):
    """The existing body shape keeps working: no scopes means no scope and no line."""
    client, _db, _company_id, _user_id, project, _party = api

    response = _create(client, project.id, {})
    assert response.status_code == 201, response.text
    assert response.json()["scopes"] == []


def test_a_recipient_typed_on_create_is_stored_and_a_blank_one_keeps_the_snapshot(api):
    """AC-QF019: typed wins, blank keeps what the developer party gives."""
    client, _db, _company_id, _user_id, project, party = api

    response = _create(
        client,
        project.id,
        {
            "recipient_name_snapshot": f"{MARKER} Finance Dept",
            "recipient_address_snapshot": "",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["recipient_name_snapshot"] == f"{MARKER} Finance Dept"
    assert body["recipient_address_snapshot"] == party.address
    assert body["recipient_phone_snapshot"] == party.phone


def test_a_scope_with_no_name_is_refused_and_nothing_is_created(api):
    client, db, _company_id, _user_id, project, _party = api
    before = len(_documents(db, project.id))

    response = _create(client, project.id, {"scopes": [{"scope_label": "   "}]})
    assert response.status_code == 422, response.text
    db.expire_all()
    assert len(_documents(db, project.id)) == before


# -------------------------------------------------------------------- edit


def _created(client, db, project_id: str, product) -> dict:
    response = _create(
        client,
        project_id,
        {
            "scopes": [
                {
                    "scope_label": f"{MARKER} Townhouse",
                    "lines": [
                        {"product_id": product.id, "unit_price": "250.00", "quantity": "4"},
                        {
                            "description_snapshot": "Old line",
                            "unit_price": "5.00",
                            "quantity": "1",
                        },
                    ],
                },
                {"scope_label": f"{MARKER} Guard House"},
            ]
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_edit_applies_header_rename_new_scope_and_full_line_set_in_one_patch(api):
    """AC-QF021: everything the form holds, in one request."""
    client, db, _company_id, _user_id, project, _party = api
    product = _seed_product(db)
    document = _created(client, db, project.id, product)
    townhouse, guard = document["scopes"]
    kept = _lines_of_scope(db, townhouse["id"])[0]

    response = _patch(
        client,
        project.id,
        document["id"],
        {
            "your_ref": f"{MARKER}/NC/2",
            "scopes": [
                {
                    "id": townhouse["id"],
                    "scope_label": f"{MARKER} Townhouse Block A",
                    "lines": [
                        {
                            "id": kept.id,
                            "product_id": product.id,
                            "unit_price": "260.00",
                            "quantity": "4",
                        },
                        {
                            "description_snapshot": "New line",
                            "unit_price": "10.00",
                            "quantity": "3",
                        },
                    ],
                },
                {
                    "scope_label": f"{MARKER} Reception",
                    "lines": [
                        {"product_id": product.id, "unit_price": "100.00", "quantity": "1"}
                    ],
                },
            ],
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["your_ref"] == f"{MARKER}/NC/2"
    labels = [scope["scope_label"] for scope in body["scopes"]]
    # AC-QF024: the Guard House was left out of the PATCH and is still there, untouched.
    assert labels == [
        f"{MARKER} Townhouse Block A",
        f"{MARKER} Guard House",
        f"{MARKER} Reception",
    ]
    db.expire_all()
    lines = _lines_of_scope(db, townhouse["id"])
    assert [line.id for line in lines][0] == kept.id
    assert [line.description_snapshot for line in lines][1] == "New line"
    assert len(lines) == 2  # "Old line" was left out of the set, so it is gone
    assert Decimal(lines[0].unit_price) == Decimal("260.00")
    assert body["scopes"][1]["id"] == guard["id"]
    assert body["scopes"][1]["line_count"] == 0


def test_edit_can_set_and_clear_a_scope_series(api):
    client, db, company_id, _user_id, project, _party = api
    from app.models.projects import ProjectSeries

    product = _seed_product(db)
    document = _created(client, db, project.id, product)
    series = ProjectSeries(company_id=company_id, name=f"{MARKER} Series", is_active=True)
    db.add(series)
    db.commit()
    scope_id = document["scopes"][0]["id"]

    response = _patch(
        client,
        project.id,
        document["id"],
        {"scopes": [{"id": scope_id, "series_id": str(series.id)}]},
    )
    assert response.status_code == 200, response.text
    db.expire_all()
    assert str(db.get(ProjectQuotation, scope_id).series_id) == str(series.id)

    response = _patch(
        client, project.id, document["id"], {"scopes": [{"id": scope_id, "series_id": None}]}
    )
    assert response.status_code == 200, response.text
    db.expire_all()
    assert db.get(ProjectQuotation, scope_id).series_id is None


def test_edit_sending_lines_to_an_issued_scope_is_refused_and_writes_nothing(api):
    """AC-QF023: the existing 422, and the header change in the same save does not land."""
    client, db, _company_id, _user_id, project, _party = api
    product = _seed_product(db)
    document = _created(client, db, project.id, product)
    root = f"{BASE}/projects/{project.id}/quotation-documents"
    _sign(client, root, document["id"])
    issued = client.post(f"{root}/{document['id']}/issue")
    assert issued.status_code == 201, issued.text
    townhouse = document["scopes"][0]

    response = _patch(
        client,
        project.id,
        document["id"],
        {
            "your_ref": f"{MARKER}/SHOULD-NOT-LAND",
            "scopes": [
                {
                    "id": townhouse["id"],
                    "lines": [
                        {"description_snapshot": "Sneaked in", "unit_price": "1", "quantity": "1"}
                    ],
                }
            ],
        },
    )
    assert response.status_code == 422, response.text
    assert response.json().get("code") == "quotation_version_issued"
    db.expire_all()
    assert db.get(ProjectQuotationDocument, document["id"]).your_ref != (
        f"{MARKER}/SHOULD-NOT-LAND"
    )
    assert len(_lines_of_scope(db, townhouse["id"])) == 2


def test_edit_of_a_scope_on_another_document_is_refused(api):
    client, db, _company_id, _user_id, project, _party = api
    product = _seed_product(db)
    first = _created(client, db, project.id, product)
    second = _created(client, db, project.id, product)

    response = _patch(
        client,
        project.id,
        first["id"],
        {"scopes": [{"id": second["scopes"][0]["id"], "scope_label": "Stolen"}]},
    )
    assert response.status_code == 404, response.text


def test_a_scope_id_that_is_not_an_id_is_a_404_not_a_500(api):
    client, db, _company_id, _user_id, project, _party = api
    product = _seed_product(db)
    document = _created(client, db, project.id, product)

    response = _patch(
        client, project.id, document["id"], {"scopes": [{"id": "not-a-uuid", "scope_label": "X"}]}
    )
    assert response.status_code in (404, 422), response.text


def test_lines_written_by_the_form_raise_the_below_floor_alert(api, monkeypatch):
    """The form's create and edit tell management about below-floor lines exactly as the bulk
    line route does: every line written is handed to the same notifier."""
    from app.api.v1.projects import quotation_documents as route

    seen = []
    monkeypatch.setattr(route, "_notify_breaches", lambda db, line, actor: seen.append(line.id))
    client, db, _company_id, _user_id, project, _party = api
    product = _seed_product(db)

    document = _created(client, db, project.id, product)
    assert len(seen) == 2

    townhouse = document["scopes"][0]
    response = _patch(
        client,
        project.id,
        document["id"],
        {
            "scopes": [
                {
                    "id": townhouse["id"],
                    "lines": [{"product_id": product.id, "unit_price": "1.00", "quantity": "1"}],
                }
            ]
        },
    )
    assert response.status_code == 200, response.text
    assert len(seen) == 3


# ------------------------------------------------ fix round 2: the owner's rulings (11:33Z)


def test_edit_removes_a_saved_scope_nothing_in_which_was_issued(api):
    """AC-QF058, owner on Q2: "yes can". Edit quotation may delete a saved scope while nothing in
    it has been issued; the scope, its versions and its lines go in the same PATCH."""
    client, db, _company_id, _user_id, project, _party = api
    product = _seed_product(db)
    document = _created(client, db, project.id, product)
    townhouse, guard = document["scopes"]

    response = _patch(
        client,
        project.id,
        document["id"],
        {"your_ref": f"{MARKER}/R2", "remove_scope_ids": [townhouse["id"]]},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert [scope["id"] for scope in body["scopes"]] == [guard["id"]]
    assert body["your_ref"] == f"{MARKER}/R2"
    db.expire_all()
    assert db.get(ProjectQuotation, townhouse["id"]) is None
    assert (
        db.query(ProjectQuotationVersion)
        .filter(ProjectQuotationVersion.quotation_id == townhouse["id"])
        .count()
        == 0
    )


def test_removing_a_scope_that_was_issued_is_refused_and_writes_nothing(api):
    """AC-QF059: the server refuses with a clear message naming the scope, and nothing else in
    the same save lands."""
    client, db, _company_id, _user_id, project, _party = api
    product = _seed_product(db)
    document = _created(client, db, project.id, product)
    root = f"{BASE}/projects/{project.id}/quotation-documents"
    _sign(client, root, document["id"])
    issued = client.post(f"{root}/{document['id']}/issue")
    assert issued.status_code == 201, issued.text
    townhouse = document["scopes"][0]

    response = _patch(
        client,
        project.id,
        document["id"],
        {"your_ref": f"{MARKER}/SHOULD-NOT-LAND", "remove_scope_ids": [townhouse["id"]]},
    )
    assert response.status_code == 422, response.text
    payload = response.json()
    assert payload.get("code") == "quotation_scope_issued"
    assert f"{MARKER} Townhouse" in (payload.get("message") or payload.get("detail") or "")
    db.expire_all()
    assert db.get(ProjectQuotation, townhouse["id"]) is not None
    assert db.get(ProjectQuotationDocument, document["id"]).your_ref != (
        f"{MARKER}/SHOULD-NOT-LAND"
    )


def test_removing_a_scope_that_was_issued_then_revised_is_still_refused(api):
    """AC-QF059: "nothing in that scope has been issued" means ANY version, not only the open
    one. A revision opened after the issue does not make the scope deletable."""
    client, db, _company_id, _user_id, project, _party = api
    product = _seed_product(db)
    document = _created(client, db, project.id, product)
    root = f"{BASE}/projects/{project.id}/quotation-documents"
    _sign(client, root, document["id"])
    assert client.post(f"{root}/{document['id']}/issue").status_code == 201
    townhouse = document["scopes"][0]
    revised = client.post(f"{BASE}/quotations/{townhouse['id']}/revise", json={})
    assert revised.status_code in (200, 201), revised.text

    response = _patch(
        client, project.id, document["id"], {"remove_scope_ids": [townhouse["id"]]}
    )
    assert response.status_code == 422, response.text
    assert response.json().get("code") == "quotation_scope_issued"


def test_removing_a_scope_of_another_document_is_a_404(api):
    client, db, _company_id, _user_id, project, _party = api
    product = _seed_product(db)
    first = _created(client, db, project.id, product)
    second = _created(client, db, project.id, product)

    response = _patch(
        client, project.id, first["id"], {"remove_scope_ids": [second["scopes"][0]["id"]]}
    )
    assert response.status_code == 404, response.text
    db.expire_all()
    assert db.get(ProjectQuotation, second["scopes"][0]["id"]) is not None


def test_a_header_only_create_writes_the_letterhead_and_no_scope(api):
    """AC-QF060, owner on Q3: "yes can, header only is fine"."""
    client, _db, _company_id, _user_id, project, _party = api

    response = _create(
        client,
        project.id,
        {"your_ref": f"{MARKER}/HDR", "attn_name": "Kelly", "scopes": []},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["scopes"] == []
    assert body["your_ref"] == f"{MARKER}/HDR"
    assert body["attn_name"] == "Kelly"


def test_a_header_only_edit_leaves_every_scope_as_it_was(api):
    """AC-QF060 on edit: a PATCH with no scopes key changes the letterhead only."""
    client, db, _company_id, _user_id, project, _party = api
    product = _seed_product(db)
    document = _created(client, db, project.id, product)

    response = _patch(client, project.id, document["id"], {"attn_name": "Mr Tan"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["attn_name"] == "Mr Tan"
    assert [scope["id"] for scope in body["scopes"]] == [s["id"] for s in document["scopes"]]
    assert [scope["line_count"] for scope in body["scopes"]] == [2, 0]


class _FakeTemplate:
    def __init__(self, body_html: str):
        self.body_html = body_html


def _fake_templates(monkeypatch):
    from app.services import project_quotation_template_service as templates

    bodies = {
        templates.TEMPLATE_KIND_COVER_LETTER: "<p>Dear {{attn_name}}, our ref {{our_ref}}.</p>",
        templates.TEMPLATE_KIND_TERMS: "<p>Valid 30 days.</p>",
    }
    monkeypatch.setattr(
        templates,
        "active_template",
        lambda db, *, company_id, kind: _FakeTemplate(bodies[kind]) if kind in bodies else None,
    )
    return bodies


def test_the_create_form_reads_the_company_letter_templates(api, monkeypatch):
    """AC-QF056: the create form's Cover letter and Terms tabs are prefilled from the company's
    active templates before anything is saved. The merge fields stay as written; they are
    filled in against the real reference when the quotation is saved."""
    client, _db, _company_id, _user_id, project, _party = api
    bodies = _fake_templates(monkeypatch)

    response = client.get(f"{BASE}/projects/{project.id}/quotation-documents/letter-templates")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["cover_letter_html"] == bodies["cover_letter"]
    assert body["terms_html"] == bodies["terms"]


_ONE_PRICED_SCOPE = [
    {
        "scope_label": f"{MARKER} Townhouse",
        "lines": [{"description_snapshot": "Vanity top", "unit_price": "250.00", "quantity": "4"}],
    }
]


def test_a_letter_edited_on_create_is_stored_with_its_merge_fields_filled(api, monkeypatch):
    """AC-QF056: what the salesperson typed in the create form's tabs is what the quotation
    holds, with the merge fields rendered against the saved document: its number, its Attn and
    the total of the lines saved in the same request (rendered AFTER the scopes exist)."""
    client, _db, _company_id, _user_id, project, _party = api
    _fake_templates(monkeypatch)

    response = _create(
        client,
        project.id,
        {
            "attn_name": "Kelly",
            "cover_letter_html": "<p>Hi {{attn_name}}, see {{our_ref}}, RM {{grand_total}}.</p>",
            "terms_html": "<p>Edited terms.</p>",
            "scopes": _ONE_PRICED_SCOPE,
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["cover_letter_html"] == (
        f"<p>Hi Kelly, see {body['document_no']}, RM 1,000.00.</p>"
    )
    assert body["terms_html"] == "<p>Edited terms.</p>"


def test_a_blank_letter_on_create_takes_the_template_with_the_real_total(api, monkeypatch):
    """AC-QF056: a create form whose letter tab is blank (cleared, or saved before the templates
    answered) gets the company template, rendered after the scopes, so its total is not 0.00."""
    from app.services import project_quotation_template_service as templates

    client, _db, _company_id, _user_id, project, _party = api
    monkeypatch.setattr(
        templates,
        "active_template",
        lambda db, *, company_id, kind: _FakeTemplate("<p>RM {{grand_total}}</p>"),
    )

    response = _create(
        client, project.id, {"cover_letter_html": "  ", "scopes": _ONE_PRICED_SCOPE}
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["cover_letter_html"] == "<p>RM 1,000.00</p>"
    assert body["terms_html"] == "<p>RM 1,000.00</p>"


def test_removing_a_scope_needs_the_delete_permission(api):
    """AC-QF058: removing a saved scope is a hard delete, so it asks for the same grant as the
    scope DELETE route (projects.projects.delete). Edit alone gets a 403 and the scope stays."""
    client, db, _company_id, _user_id, project, _party = api
    product = _seed_product(db)
    document = _created(client, db, project.id, product)
    townhouse = document["scopes"][0]

    with _without_permission("projects.projects.delete"):
        response = _patch(
            client,
            project.id,
            document["id"],
            {"your_ref": f"{MARKER}/NO", "remove_scope_ids": [townhouse["id"]]},
        )
    assert response.status_code == 403, response.text
    db.expire_all()
    assert db.get(ProjectQuotation, townhouse["id"]) is not None
    assert db.get(ProjectQuotationDocument, document["id"]).your_ref != f"{MARKER}/NO"


def test_a_scope_both_removed_and_edited_in_one_save_is_refused_up_front(api):
    """A scope named in remove_scope_ids and in scopes is a contradiction; refused with a 422
    that says so, not a misleading 404 after the delete."""
    client, db, _company_id, _user_id, project, _party = api
    product = _seed_product(db)
    document = _created(client, db, project.id, product)
    townhouse = document["scopes"][0]

    response = _patch(
        client,
        project.id,
        document["id"],
        {
            "remove_scope_ids": [townhouse["id"]],
            "scopes": [{"id": townhouse["id"], "scope_label": "Renamed"}],
        },
    )
    assert response.status_code == 422, response.text
    assert response.json().get("code") == "quotation_scope_removed_and_edited"
    db.expire_all()
    assert db.get(ProjectQuotation, townhouse["id"]) is not None
