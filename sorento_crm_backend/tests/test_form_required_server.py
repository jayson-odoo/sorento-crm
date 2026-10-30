"""FORM-REQUIRED-SERVER: the server refuses a portal SUBMIT with a required field empty.

Plan: documentation/plans/forms/PLAN-form-required-server-30oct.md. Found by #1953: for
stock_inquiry, complaint, purchase_request and sponsorship_form a blank draft could be
submitted (200, status submitted, number assigned); only SubmissionForm's required flags
stopped it, in the browser.

Rule: on submit (and on a portal revise, the second way back into the flow) the fields the
portal form marks required must be filled, else 422 with `detail` = the missing field names,
comma separated (the shape `portal-client.ts` `throwSubmissionError` already reads, the same
one project registration answers with). A draft save stays free to be incomplete.

The required list is `app/services/portal_required_fields.py`; the last test here keeps it
equal to the `required: true` flags in SubmissionForm.tsx, so the two cannot drift.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests._forms_chain_support import SUB, contact, world  # noqa: F401  (fixture)

KINDS = ("stock_inquiry", "complaint", "purchase_request", "sponsorship_form")

COMPLAINT_REQUIRED = [
    "delivery_order_number",
    "customer_name",
    "contact_person",
    "contact_number",
    "customer_type",
    "complaint_date",
    "within_warranty",
    "defects_discovered",
    "complaint_type",
    "defect_description",
    "salesperson",
    "product_lines",
]

EXPECTED_REQUIRED = {
    "stock_inquiry": ["salesperson_contact_id"],
    "complaint": COMPLAINT_REQUIRED,
    "purchase_request": ["requested_by_contact_id"],
    "sponsorship_form": ["requested_by_contact_id"],
}


def _complete(kind: str, contact_id: str) -> dict:
    """A body with every required field of `kind` filled, as SubmissionForm sends it."""
    if kind == "stock_inquiry":
        return {"fields": {"salesperson_contact_id": contact_id, "item_description": "ZZT tile"}}
    if kind == "complaint":
        return {
            "fields": {
                "delivery_order_number": ["DO-ZZT-1001"],
                "customer_name": "ZZT Example Hardware",
                "contact_person": "ZZT Ali",
                "contact_number": "0123456789",
                "customer_type": "dealer",
                "complaint_date": "2026-10-30",
                "within_warranty": "yes",
                "defects_discovered": "upon_delivery",
                "complaint_type": "product_defect",
                "defect_description": "Tiles chipped on arrival",
                "salesperson": "ZZT Aminah",
                "product_lines": [{"product_code": "ZZT-TILE-1", "quantity": "12"}],
            },
        }
    return {
        "fields": {"requested_by_contact_id": contact_id, "customer_name": "ZZT Example Trading"},
        "products": [{"item_code": "ZZT-TILE-1", "quantity": 4, "unit_price": 25, "total": 100}],
    }


def _setup(w):
    w.contact = contact(w.db, name="required-fields salesperson")
    w.db.commit()
    return w.as_contact(w.contact)


def _draft(c, kind: str, body: dict) -> str:
    res = c.post(f"{SUB}/{kind}", json=body)
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "draft"
    return res.json()["id"]


def _missing(res) -> list[str]:
    body = res.json()
    detail = body.get("detail")
    if isinstance(detail, dict):  # HTTPException wrapping, depending on the handler
        detail = detail.get("detail")
    return [f for f in (detail or "").split(",") if f]


# ------------------------------------------------------------------ blank draft


@pytest.mark.parametrize("kind", KINDS)
def test_blank_draft_submit_is_refused_with_every_required_field(world, kind):
    c = _setup(world)
    sid = _draft(c, kind, {"fields": {}})

    res = c.post(f"{SUB}/{kind}/{sid}/submit")

    assert res.status_code == 422, res.text
    assert res.json()["message"] == "Fill in the required fields before submitting."
    assert sorted(_missing(res)) == sorted(EXPECTED_REQUIRED[kind])
    detail = c.get(f"{SUB}/{kind}/{sid}").json()
    assert detail["status"] == "draft" and detail["is_draft"] is True
    assert not detail.get("document_number")


# ------------------------------------------------------------------ one field missing


@pytest.mark.parametrize("kind", KINDS)
def test_one_required_field_blank_is_named_alone(world, kind):
    c = _setup(world)
    body = _complete(kind, world.contact)
    dropped = EXPECTED_REQUIRED[kind][0]
    body["fields"][dropped] = "" if dropped != "delivery_order_number" else []
    sid = _draft(c, kind, body)

    res = c.post(f"{SUB}/{kind}/{sid}/submit")

    assert res.status_code == 422, res.text
    assert _missing(res) == [dropped]


def test_complaint_without_a_product_line_is_refused(world):
    c = _setup(world)
    body = _complete("complaint", world.contact)
    body["fields"]["product_lines"] = [{"product_code": "  ", "quantity": "1"}]
    sid = _draft(c, "complaint", body)

    res = c.post(f"{SUB}/complaint/{sid}/submit")

    assert res.status_code == 422, res.text
    assert _missing(res) == ["product_lines"]


def test_whitespace_only_counts_as_empty(world):
    c = _setup(world)
    body = _complete("complaint", world.contact)
    body["fields"]["contact_person"] = "   "
    sid = _draft(c, "complaint", body)

    res = c.post(f"{SUB}/complaint/{sid}/submit")

    assert res.status_code == 422, res.text
    assert _missing(res) == ["contact_person"]


# ------------------------------------------------------------------ happy paths


@pytest.mark.parametrize("kind", KINDS)
def test_complete_draft_submits(world, kind):
    c = _setup(world)
    sid = _draft(c, kind, _complete(kind, world.contact))

    res = c.post(f"{SUB}/{kind}/{sid}/submit")

    assert res.status_code == 200, res.text
    assert res.json()["status"] not in ("draft", None)


@pytest.mark.parametrize("kind", KINDS)
def test_submit_body_fills_the_missing_fields(world, kind):
    """The portal sends the whole form with Submit; the check reads the row AFTER that
    body is applied, so a draft saved blank and submitted complete goes through."""
    c = _setup(world)
    sid = _draft(c, kind, {"fields": {}})

    res = c.post(f"{SUB}/{kind}/{sid}/submit", json=_complete(kind, world.contact))

    assert res.status_code == 200, res.text


@pytest.mark.parametrize("kind", KINDS)
def test_draft_save_may_stay_incomplete(world, kind):
    c = _setup(world)
    sid = _draft(c, kind, {"fields": {}})

    res = c.put(f"{SUB}/{kind}/{sid}", json={"fields": {}})

    assert res.status_code == 200, res.text
    assert res.json()["status"] == "draft"


# ------------------------------------------------------------------ revise


REVISABLE = ("stock_inquiry", "purchase_request", "sponsorship_form")


def _revise_legacy_row(kind, payload, **overrides):
    """Seed a submitted, revisable row and revise it as its contact."""
    from unittest.mock import patch

    from app.services.portal_revision_service import PortalRevisionService
    from tests._pg_fixture import blank_session
    from tests._revision_harness import (
        seed_config,
        seed_contact,
        seed_entity,
        seed_system_settings,
        seed_token,
    )

    with patch("app.services.queue_service.enqueue_job", return_value=None), blank_session() as db:
        seed_system_settings(db, cap=3)
        seed_config(db, kind)
        person = seed_contact(db)
        row = seed_entity(db, kind, person, **overrides)
        return PortalRevisionService(db).revise(
            seed_token(person), kind, str(row.id), payload, "Fixing the form", row.revision_no
        )


@pytest.mark.parametrize("kind", REVISABLE)
def test_revise_does_not_demand_a_frozen_field(kind):
    """The requestor is frozen on revise, so the contact cannot fill it there. A row
    created elsewhere without one (staff / external create leave it optional) must still
    be revisable rather than refused with no way out (security-review finding)."""
    field = EXPECTED_REQUIRED[kind][0]
    out = _revise_legacy_row(kind, {}, **{field: None})
    assert out["revision_no"] == 1


def test_revise_refuses_a_blanked_required_field(monkeypatch):
    """The revise path runs the same check as submit. On main the revisable kinds' only
    required field is frozen, so a non-frozen one is made required here to prove the hook
    is live (complaint revise, coming with #1953, has eleven)."""
    from app.services import portal_required_fields
    from app.services.error_handler import AppException

    monkeypatch.setitem(
        portal_required_fields.REQUIRED_ON_SUBMIT,
        "stock_inquiry",
        ("salesperson_contact_id", "item_description"),
    )
    with pytest.raises(AppException) as err:
        _revise_legacy_row("stock_inquiry", {"item_description": "  "})
    assert err.value.status_code == 422
    assert err.value.detail["detail"] == "item_description"


# ------------------------------------------------------------------ one list


_FE_FORM = (
    Path(__file__).resolve().parents[2]
    / "sorento_crm_frontend/app/(auth)/portal/components/SubmissionForm.tsx"
)


def _fe_required_by_kind() -> dict[str, list[str]]:
    """`required: true` field names per kind, read from SubmissionForm's FIELDS literal.

    Static flags only: a `requiredWhen` (per-contact) field is not read. The one there is,
    sponsorship `project_id`, has its own server check (`assert_project_requirement`).
    """
    src = _FE_FORM.read_text()
    block = src[src.index("const FIELDS: Record<PortalSubmissionKind, FieldDef[]> = {"):]
    block = block[: block.index("\n};\n")]
    out: dict[str, list[str]] = {}
    for kind_match in re.finditer(r"^  (\w+): \[\n(.*?)^  \],", block, re.S | re.M):
        kind, body = kind_match.group(1), kind_match.group(2)
        names = []
        for field in re.finditer(r"\{(.*?)\n?\s*\}", body, re.S):
            text = field.group(1)
            name = re.search(r"name: '(\w+)'", text)
            if name and re.search(r"\brequired: true\b", text):
                names.append(name.group(1))
        out[kind] = names
    return out


def test_server_list_equals_the_portal_form_required_flags():
    if not _FE_FORM.exists():  # backend image built alone: nothing to compare against
        pytest.skip("frontend source not in this checkout")
    from app.services.portal_required_fields import REQUIRED_ON_SUBMIT

    fe = _fe_required_by_kind()
    assert set(fe) >= set(KINDS), fe
    for kind in KINDS:
        server = [f for f in REQUIRED_ON_SUBMIT[kind] if f != "product_lines"]
        assert sorted(server) == sorted(fe[kind]), kind
    # The complaint's "at least one product" is not a FIELDS entry; the form adds it in
    # collectMissingRequired under this exact name.
    assert "name: 'product_lines', label: 'At least one product'" in _FE_FORM.read_text()
    assert "product_lines" in REQUIRED_ON_SUBMIT["complaint"]


def test_parity_parser_reads_the_flags_it_claims_to():
    """Guards the guard: a parser that silently found nothing would pass the test above
    for a kind with no required fields."""
    if not _FE_FORM.exists():
        pytest.skip("frontend source not in this checkout")
    fe = _fe_required_by_kind()
    assert fe["stock_inquiry"] == ["salesperson_contact_id"]
    assert fe["project_registration"] == ["title", "state", "developer_name"]
    assert len(fe["complaint"]) == 11
