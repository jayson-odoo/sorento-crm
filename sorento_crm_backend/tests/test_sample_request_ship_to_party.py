"""SAMPLE-REQUEST-V2 slice 1 (red-first): ship to is a party of the project, the contact person is
picked from that party's people, the customer is an AutoCount debtor.

Card: documentation/plans/project-sales/CARD-sample-request-v2-11nov.md (rules 1-4, owner answers
11 Nov: Q2 a ship to the customer = pick it like any party, Q3 a several contacts "A & B", phone from
the first). The proposal "To" is the model (`apply_recipient_pick`), so a party not on the project is
linked in the role given and picked contacts join the project's stakeholders.

Route level through the staff API, on the shared `world` of test_sample_requests_core. Postgres only.
Every name is invented.
"""
from __future__ import annotations

from app.models.projects import (
    ProjectParty,
    ProjectPartyContact,
    ProjectPartyLink,
    ProjectSalesProfile,
    ProjectStakeholder,
)

import pytest

from ._sample_request_seed import MARKER, full_payload, sorento, uid
from .test_sample_requests_core import SR, world  # noqa: F401  (fixture)


@pytest.fixture(autouse=True)
def _sales_owns_the_project(world):
    """The salesperson below edits the project (its owner), as the project page's gate asks
    (security review B1); `sales_b` is the one who cannot."""
    world.project.owner_user_id = world.sales
    world.db.flush()

SITE = "Lot 22, Jalan Seri Murni 5\n43000 Kajang, Selangor"


def _party(db, name, *, party_type="trading_house", address=None, phone=None, company_id=None):
    row = ProjectParty(
        id=uid(),
        company_id=company_id or sorento(db),
        party_type=party_type,
        name=f"{MARKER} {name}",
        address=address,
        phone=phone,
    )
    db.add(row)
    db.flush()
    return row


def _contact(db, party, name, *, phone=None):
    row = ProjectPartyContact(
        id=uid(), company_id=party.company_id, party_id=party.id, name=name, phone=phone
    )
    db.add(row)
    db.flush()
    return row


def _link(db, project, party, role="trading_house"):
    db.add(ProjectPartyLink(project_id=project.id, role=role, party_id=party.id))
    db.flush()


def _site_address(db, project, address=SITE):
    profile = db.get(ProjectSalesProfile, project.id)
    if profile is None:
        profile = ProjectSalesProfile(project_id=project.id)
        db.add(profile)
    profile.address = address
    db.flush()


def _body(w, **over):
    body = full_payload(
        product_id=w.cat.plain.id,
        customer_id=w.customer.id,
        project_id=w.project.id,
    )
    body.pop("customer_name", None)
    body.pop("project_title", None)
    body.pop("ship_to_name", None)
    body.update(over)
    return body


def _create(w, **over):
    return w.api.as_(w.sales).post(SR, json=_body(w, **over))



# ------------------------------------------------------------------ rule 2: ship to = a party


def test_picking_a_party_of_the_project_fills_name_and_address(world):
    w = world
    party = _party(w.db, "Bintang Trading", address="No. 12, Jalan Perindustrian 3, Klang")
    _link(w.db, w.project, party)
    res = _create(w, ship_to_party_id=party.id)
    assert res.status_code == 201, res.text
    d = res.json()
    assert d["ship_to_party_id"] == party.id
    assert d["ship_to_name"] == party.name
    assert d["ship_to_address"] == "No. 12, Jalan Perindustrian 3, Klang"
    assert d["ship_to_role"] == "trading_house"


def test_a_party_without_address_takes_the_project_site_address(world):
    w = world
    _site_address(w.db, w.project)
    party = _party(w.db, "Arkitek Lima", party_type="consultant")
    _link(w.db, w.project, party, role="consultant")
    d = _create(w, ship_to_party_id=party.id).json()
    assert d["ship_to_address"] == SITE


def test_a_typed_address_wins_over_the_party_address(world):
    w = world
    party = _party(w.db, "Bintang Trading", address="Party address")
    _link(w.db, w.project, party)
    d = _create(w, ship_to_party_id=party.id, ship_to_address="Gate B, loading bay").json()
    assert d["ship_to_address"] == "Gate B, loading bay"


def test_a_party_not_on_the_project_needs_a_role(world):
    w = world
    party = _party(w.db, "Delta Interior Works", party_type="subcontractor")
    res = _create(w, ship_to_party_id=party.id)
    assert res.status_code == 422, res.text
    assert res.json()["code"] == "SAMPLE_REQUEST_SHIP_TO_ROLE_REQUIRED"


def test_a_party_not_on_the_project_is_linked_in_the_role_given(world):
    w = world
    party = _party(w.db, "Delta Interior Works", party_type="subcontractor")
    res = _create(w, ship_to_party_id=party.id, ship_to_role="subcontractor")
    assert res.status_code == 201, res.text
    links = (
        w.db.query(ProjectPartyLink)
        .filter(ProjectPartyLink.project_id == w.project.id, ProjectPartyLink.party_id == party.id)
        .all()
    )
    assert [link.role for link in links] == ["subcontractor"]
    assert res.json()["ship_to_role"] == "subcontractor"


def test_another_companys_party_is_refused(world):
    from ._sample_request_seed import second_company

    w = world
    party = _party(w.db, "Foreign Co", company_id=second_company(w.db))
    res = _create(w, ship_to_party_id=party.id, ship_to_role="trading_house")
    assert res.status_code == 422, res.text
    assert res.json()["code"] == "SAMPLE_REQUEST_SHIP_TO_INVALID"


def test_without_a_project_any_party_is_accepted_and_nothing_is_linked(world):
    w = world
    party = _party(w.db, "Bintang Trading", address="Klang")
    res = w.api.as_(w.sales).post(
        SR,
        json=_body(w, project_id=None, project_title=f"{MARKER} unregistered", ship_to_party_id=party.id),
    )
    assert res.status_code == 201, res.text
    assert res.json()["ship_to_name"] == party.name
    assert w.db.query(ProjectPartyLink).filter(ProjectPartyLink.party_id == party.id).count() == 0


# ------------------------------------------------------------------ rule 4: contact person


def test_several_contacts_print_a_and_b_with_the_first_ones_phone(world):
    w = world
    # The phone is party data: it is copied only for a caller who may read it (security S1).
    w.perms[w.sales].add("projects.parties.view")
    party = _party(w.db, "Bintang Trading", address="Klang", phone="0331112222")
    _link(w.db, w.project, party)
    mei = _contact(w.db, party, "Mei Ling Tan", phone="0123456789")
    ravi = _contact(w.db, party, "Ravi Kumar")
    d = _create(w, ship_to_party_id=party.id, ship_to_contact_ids=[mei.id, ravi.id]).json()
    assert d["site_contact_name"] == "Mei Ling Tan & Ravi Kumar"
    assert d["site_contact_phone"] and d["site_contact_phone"].replace(" ", "").replace("-", "").endswith(
        "123456789"
    )


def test_picked_contacts_join_the_projects_stakeholders(world):
    w = world
    party = _party(w.db, "Bintang Trading", address="Klang")
    _link(w.db, w.project, party)
    mei = _contact(w.db, party, "Mei Ling Tan")
    assert _create(w, ship_to_party_id=party.id, ship_to_contact_ids=[mei.id]).status_code == 201
    rows = (
        w.db.query(ProjectStakeholder)
        .filter(ProjectStakeholder.project_id == w.project.id, ProjectStakeholder.party_contact_id == mei.id)
        .count()
    )
    assert rows == 1


def test_a_contact_of_another_party_is_refused(world):
    w = world
    party = _party(w.db, "Bintang Trading", address="Klang")
    _link(w.db, w.project, party)
    other = _party(w.db, "Someone Else")
    stranger = _contact(w.db, other, "Not Theirs")
    res = _create(w, ship_to_party_id=party.id, ship_to_contact_ids=[stranger.id])
    assert res.status_code == 422, res.text
    assert res.json()["code"] == "SAMPLE_REQUEST_CONTACT_NOT_OF_PARTY"


def test_changing_the_party_clears_the_old_contact(world):
    w = world
    first = _party(w.db, "Bintang Trading", address="Klang")
    second = _party(w.db, "Arkitek Lima", party_type="consultant", address="Kajang")
    _link(w.db, w.project, first)
    _link(w.db, w.project, second, role="consultant")
    mei = _contact(w.db, first, "Mei Ling Tan", phone="0123456789")
    d = _create(w, ship_to_party_id=first.id, ship_to_contact_ids=[mei.id]).json()
    res = w.api.as_(w.sales).put(f"{SR}/{d['id']}", json={"ship_to_party_id": second.id})
    assert res.status_code == 200, res.text
    after = res.json()
    assert after["ship_to_name"] == second.name
    assert after["ship_to_address"] == "Kajang"
    assert after["site_contact_name"] is None
    assert after["site_contact_phone"] is None


def test_the_customer_can_be_the_ship_to_party(world):
    """Owner Q2 a: shipping to the customer is picking it like any party."""
    w = world
    party = _party(w.db, "Nusantara Builders", party_type="main_contractor", address="Shah Alam")
    party.customer_id = w.customer.id
    _link(w.db, w.project, party, role="main_contractor")
    res = _create(w, ship_to_party_id=party.id)
    assert res.status_code == 201, res.text
    assert res.json()["ship_to_name"] == party.name


# ------------------------------------------------------------------ rules 1-2 on submit (staff)


def _submit(w, rid):
    return w.api.as_(w.sales).post(f"{SR}/{rid}/submit")


def test_staff_submit_needs_a_ship_to_party(world):
    w = world
    d = _create(w, ship_to_name=f"{MARKER} typed site").json()
    res = _submit(w, d["id"])
    assert res.status_code == 422, res.text
    assert res.json()["details"]["field"] == "ship_to_party_id"


def test_staff_submit_needs_a_debtor_not_a_typed_customer(world):
    w = world
    party = _party(w.db, "Bintang Trading", address="Klang")
    _link(w.db, w.project, party)
    d = _create(w, customer_id=None, customer_name=f"{MARKER} typed buyer", ship_to_party_id=party.id).json()
    res = _submit(w, d["id"])
    assert res.status_code == 422, res.text
    assert res.json()["details"]["field"] == "customer_id"


def test_staff_submit_with_a_party_and_a_debtor_passes(world):
    w = world
    party = _party(w.db, "Bintang Trading", address="Klang")
    _link(w.db, w.project, party)
    d = _create(w, ship_to_party_id=party.id).json()
    res = _submit(w, d["id"])
    assert res.status_code in (200, 201), res.text
    assert res.json()["status"] == "submitted"


def test_staff_submit_needs_a_shipping_address(world):
    """No address on the party and no site address: the address is required on submit."""
    w = world
    party = _party(w.db, "No Address Sdn Bhd")
    _link(w.db, w.project, party)
    d = _create(w, ship_to_party_id=party.id).json()
    assert d["ship_to_address"] is None
    res = _submit(w, d["id"])
    assert res.status_code == 422, res.text
    assert res.json()["details"]["field"] == "ship_to_address"


def test_an_old_free_text_draft_keeps_its_text_until_a_party_is_picked(world):
    """Card example E: nothing is rewritten; the typed Ship To stays on the row."""
    w = world
    d = _create(w, ship_to_name="site office, Lot 22", scope_note="show unit").json()
    got = w.api.as_(w.sales).get(f"{SR}/{d['id']}").json()
    assert got["ship_to_name"] == "site office, Lot 22"
    assert got["scope_note"] == "show unit"
    assert got["ship_to_party_id"] is None


# ------------------------------------------------------------------ security review B1, S1


def test_a_salesperson_who_cannot_edit_the_project_cannot_add_a_party_to_it(world):
    """B1: linking a party is a project edit, behind the project page's own gate."""
    w = world
    party = _party(w.db, "Delta Interior Works", party_type="subcontractor")
    res = w.api.as_(w.sales_b).post(
        SR, json=_body(w, ship_to_party_id=party.id, ship_to_role="subcontractor")
    )
    assert res.status_code == 403, res.text
    assert w.db.query(ProjectPartyLink).filter(ProjectPartyLink.party_id == party.id).count() == 0


def test_a_non_editor_may_still_pick_a_party_already_on_the_project(world):
    w = world
    party = _party(w.db, "Bintang Trading", address="Klang")
    _link(w.db, w.project, party)
    res = w.api.as_(w.sales_b).post(SR, json=_body(w, ship_to_party_id=party.id))
    assert res.status_code == 201, res.text
    assert res.json()["ship_to_name"] == party.name


def test_a_non_editors_contacts_print_but_do_not_join_the_stakeholders(world):
    w = world
    party = _party(w.db, "Bintang Trading", address="Klang")
    _link(w.db, w.project, party)
    mei = _contact(w.db, party, "Mei Ling Tan", phone="0123456789")
    res = w.api.as_(w.sales_b).post(
        SR, json=_body(w, ship_to_party_id=party.id, ship_to_contact_ids=[mei.id])
    )
    assert res.status_code == 201, res.text
    assert res.json()["site_contact_name"] == "Mei Ling Tan"
    assert (
        w.db.query(ProjectStakeholder)
        .filter(ProjectStakeholder.project_id == w.project.id, ProjectStakeholder.party_contact_id == mei.id)
        .count()
        == 0
    )


def test_the_contact_phone_is_not_copied_without_the_parties_view_grant(world):
    """S1: GET /parties/{id}/contacts strips the phone for such a caller; the request must not
    hand it over either."""
    w = world
    assert "projects.parties.view" not in w.perms[w.sales]
    party = _party(w.db, "Bintang Trading", address="Klang")
    _link(w.db, w.project, party)
    mei = _contact(w.db, party, "Mei Ling Tan", phone="0123456789")
    d = _create(w, ship_to_party_id=party.id, ship_to_contact_ids=[mei.id]).json()
    assert d["site_contact_name"] == "Mei Ling Tan"
    assert d["site_contact_phone"] is None


# ------------------------------------------------------------------ review B1 / S1 / S2: edits of a saved draft
# The bodies below are the ones the staff form sends (lib/sample-request-form.ts staffPayloadFromState).


def test_clearing_then_repicking_the_party_leaves_a_submittable_draft(world):
    w = world
    party = _party(w.db, "Bintang Trading", address="Klang")
    _link(w.db, w.project, party)
    d = _create(w, ship_to_party_id=party.id).json()
    cleared = w.api.as_(w.sales).put(
        f"{SR}/{d['id']}", json={"ship_to_party_id": None, "ship_to_address": None}
    )
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["ship_to_party_id"] is None
    again = w.api.as_(w.sales).put(
        f"{SR}/{d['id']}",
        json={
            "ship_to_party_id": party.id,
            "ship_to_name": party.name,
            "ship_to_address": "Klang",
            "ship_to_contact_ids": [],
        },
    )
    assert again.status_code == 200, again.text
    assert again.json()["ship_to_name"] == party.name
    assert _submit(w, d["id"]).status_code in (200, 201)


def test_unticking_every_contact_clears_the_contact_person(world):
    w = world
    party = _party(w.db, "Bintang Trading", address="Klang")
    _link(w.db, w.project, party)
    mei = _contact(w.db, party, "Mei Ling Tan", phone="0123456789")
    d = _create(w, ship_to_party_id=party.id, ship_to_contact_ids=[mei.id]).json()
    assert d["site_contact_name"] == "Mei Ling Tan"
    res = w.api.as_(w.sales).put(
        f"{SR}/{d['id']}",
        json={
            "ship_to_party_id": party.id,
            "ship_to_contact_ids": [],
            "site_contact_name": None,
            "site_contact_phone": None,
        },
    )
    assert res.status_code == 200, res.text
    assert res.json()["site_contact_name"] is None


def test_a_cleared_address_is_cleared_and_then_blocks_submit(world):
    w = world
    party = _party(w.db, "Bintang Trading", address="Klang")
    _link(w.db, w.project, party)
    d = _create(w, ship_to_party_id=party.id).json()
    res = w.api.as_(w.sales).put(
        f"{SR}/{d['id']}", json={"ship_to_party_id": party.id, "ship_to_address": None}
    )
    assert res.status_code == 200, res.text
    assert res.json()["ship_to_address"] is None
    sub = _submit(w, d["id"])
    assert sub.status_code == 422, sub.text
    assert sub.json()["details"]["field"] == "ship_to_address"


def test_an_owner_without_the_project_edit_grant_cannot_add_a_party(world):
    """Security round 2: the project page's own routes also ask `projects.projects.edit`."""
    w = world
    w.perms[w.sales].discard("projects.projects.edit")
    party = _party(w.db, "Delta Interior Works", party_type="subcontractor")
    res = _create(w, ship_to_party_id=party.id, ship_to_role="subcontractor")
    assert res.status_code == 403, res.text
    assert w.db.query(ProjectPartyLink).filter(ProjectPartyLink.party_id == party.id).count() == 0


def test_a_non_editor_cannot_add_a_party_by_updating_a_saved_draft(world):
    """Security round 2 nit: the gate runs on the draft's own project, without a resent project_id."""
    w = world
    on_project = _party(w.db, "Bintang Trading", address="Klang")
    _link(w.db, w.project, on_project)
    d = w.api.as_(w.sales_b).post(SR, json=_body(w, ship_to_party_id=on_project.id))
    assert d.status_code == 201, d.text
    newcomer = _party(w.db, "Delta Interior Works", party_type="subcontractor")
    res = w.api.as_(w.sales_b).put(
        f"{SR}/{d.json()['id']}",
        json={"ship_to_party_id": newcomer.id, "ship_to_role": "subcontractor"},
    )
    assert res.status_code == 403, res.text
    assert w.db.query(ProjectPartyLink).filter(ProjectPartyLink.party_id == newcomer.id).count() == 0
