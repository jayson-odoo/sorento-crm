"""PS-REGISTRATION-V3 (red-first): customer optional, lead source, more party roles, party contacts,
contacts picked at registration, the project's parties read and the WhatsApp phone fill.

Card: documentation/plans/projects/CARD-ps-registration-v3-02nov.md (rules 1-13). Every name and
number is invented.
"""
from __future__ import annotations

import pytest

from ._project_register_v2_support import (  # noqa: F401  fixture
    LIST,
    as_user,
    developer,
    title,
    uid,
    v2,
)

PARTIES = "/api/v1/project-sales/parties"
PROJECTS = "/api/v1/project-sales/projects"


def _party(w, party_type: str, name: str | None = None, company_id: str | None = None, phone=None):
    row = developer(w.db, company_id or w.company_id, name or f"CONTOH {party_type} {uid()[:6]}", party_type)
    row.phone = phone
    w.db.flush()
    return row


def _contact(w, party, name="Example Person", phone=None, job_title=None, is_active=True):
    from app.models.projects import ProjectPartyContact

    row = ProjectPartyContact(
        id=uid(), company_id=party.company_id, party_id=party.id, name=name,
        phone=phone, job_title=job_title, is_active=is_active,
    )
    w.db.add(row)
    w.db.flush()
    return row


def _register(w, user=None, **body):
    base = {"title": title("V3"), "lead_source": "site_visit"}
    base.update(body)
    return as_user(w, user or w.owner).post(LIST, json={k: v for k, v in base.items() if v is not None})


def _stakeholders(w, project_id):
    from app.models.projects import ProjectStakeholder

    return (
        w.db.query(ProjectStakeholder).filter(ProjectStakeholder.project_id == project_id).all()
    )


# ------------------------------------------------------------------ rule 9: customer optional


def test_r9_staff_register_without_a_customer_is_201(v2):
    res = _register(v2)
    assert res.status_code == 201, res.text
    assert res.json()["customer_id"] is None


def test_r9_submit_only_submit_without_a_customer_goes_pending(v2):
    res = _register(v2, user=v2.sub_a, submit=True)
    assert res.status_code == 201, res.text
    assert res.json()["approval_state"] == "pending"


def test_r9_crm_submit_of_a_draft_without_a_customer_goes_pending(v2):
    from app.services import project_registration_service as svc

    draft = svc.crm_register(
        v2.db, company_id=v2.company_id, user_id=v2.sub_a,
        payload={"title": title("V3d"), "lead_source": "dealer"}, submit=False,
    )
    v2.db.flush()
    svc.crm_submit(v2.db, draft, user_id=v2.sub_a, payload={}, permissions={"projects.registrations.submit"})
    assert draft.approval_state == "pending"


# ------------------------------------------------------------------ rule 8: lead source


def test_r8_register_without_a_lead_source_is_422(v2):
    res = _register(v2, lead_source=None)
    assert res.status_code == 422, res.text
    assert res.json()["code"] == "project_lead_source_required"


def test_r8_submit_only_submit_without_a_lead_source_is_422(v2):
    res = _register(v2, user=v2.sub_a, submit=True, lead_source=None)
    assert res.status_code == 422, res.text
    assert res.json()["code"] == "project_lead_source_required"


def test_r8_a_draft_saves_without_a_lead_source(v2):
    res = _register(v2, user=v2.sub_a, submit=False, lead_source=None)
    assert res.status_code == 201, res.text


def test_r8_crm_submit_of_a_draft_without_a_lead_source_is_422(v2):
    from app.services import project_registration_service as svc
    from app.services.error_handler import AppException

    draft = svc.crm_register(
        v2.db, company_id=v2.company_id, user_id=v2.sub_a, payload={"title": title("V3n")}, submit=False
    )
    v2.db.flush()
    with pytest.raises(AppException) as exc:
        svc.crm_submit(v2.db, draft, user_id=v2.sub_a, payload={}, permissions={"projects.registrations.submit"})
    assert exc.value.code == "project_lead_source_required"
    assert draft.approval_state == "draft"


def test_r8_an_unknown_lead_source_is_422(v2):
    res = _register(v2, lead_source="rumour_mill")
    assert res.status_code == 422, res.text
    assert res.json()["code"] == "project_lead_source_invalid"


def test_r8_lead_source_is_stored_and_returned(v2):
    res = _register(v2, lead_source="architect")
    assert res.status_code == 201, res.text
    assert res.json()["lead_source"] == "architect"
    got = as_user(v2, v2.owner).get(f"{PROJECTS}/{res.json()['id']}")
    assert got.json()["lead_source"] == "architect"


def _lead_source_set(w, values):
    from app.models.lookup import LookupOption, LookupSet

    row = LookupSet(set_key="project_lead_source", name="Project - Lead source", is_active=True)
    w.db.add(row)
    w.db.flush()
    for order, (value, active) in enumerate(values):
        w.db.add(LookupOption(set_id=row.id, value=value, label=value, sort_order=order, is_active=active))
    w.db.flush()


def test_r8_the_lead_source_list_is_the_editable_lookup_set(v2):
    _lead_source_set(v2, [("roadshow", True), ("site_visit", False)])
    ok = _register(v2, lead_source="roadshow")
    assert ok.status_code == 201, ok.text
    off = _register(v2, lead_source="site_visit")  # switched off in Settings
    assert off.status_code == 422, off.text
    assert off.json()["code"] == "project_lead_source_invalid"


def test_r8_leads_validate_against_the_same_list(v2):
    from app.services import project_lead_service as leads
    from app.services.error_handler import AppException

    _lead_source_set(v2, [("roadshow", True)])
    leads._assert_source("roadshow", db=v2.db)
    with pytest.raises(AppException):
        leads._assert_source("site_visit", db=v2.db)


@pytest.mark.parametrize("value", ["bci", "referral", "tender_notice", "existing_customer", "interior_designer"])
def test_r8_the_seed_values_are_valid_without_a_configured_set(v2, value):
    assert _register(v2, lead_source=value).status_code == 201


def test_r8_edit_can_change_the_lead_source(v2):
    pid = _register(v2).json()["id"]
    res = as_user(v2, v2.owner).put(f"{PROJECTS}/{pid}", json={"lead_source": "dealer"})
    assert res.status_code == 200, res.text
    assert res.json()["lead_source"] == "dealer"


# ------------------------------------------------------------------ rule 3: party types and roles


@pytest.mark.parametrize("party_type", ["subcontractor", "interior_designer", "tender_party"])
def test_r3_new_party_types_can_be_created(v2, party_type):
    res = as_user(v2, v2.owner).post(f"{PARTIES}/", json={"party_type": party_type, "name": f"CONTOH {uid()[:6]}"})
    assert res.status_code == 201, res.text
    assert res.json()["party_type"] == party_type


def _links(body):
    return sorted((r["role"], r["party_id"], r["name"]) for r in body["party_links"])


def test_r3_new_roles_are_stored_and_named_several_per_role(v2):
    sub1, sub2 = _party(v2, "subcontractor"), _party(v2, "subcontractor")
    th1, th2 = _party(v2, "trading_house"), _party(v2, "trading_house")
    con, idr, tender = _party(v2, "consultant"), _party(v2, "interior_designer"), _party(v2, "tender_party")
    links = [
        {"role": "subcontractor", "party_id": sub1.id},
        {"role": "subcontractor", "party_id": sub2.id},
        {"role": "trading_house", "party_id": th1.id},
        {"role": "trading_house", "party_id": th2.id},
        {"role": "consultant", "party_id": con.id},
        {"role": "interior_designer", "party_id": idr.id},
        {"role": "tender_party", "party_id": tender.id},
    ]
    res = _register(v2, party_links=links)
    assert res.status_code == 201, res.text
    body = as_user(v2, v2.owner).get(f"{PROJECTS}/{res.json()['id']}").json()
    want = sorted((l["role"], l["party_id"], p.name) for l, p in zip(links, [sub1, sub2, th1, th2, con, idr, tender]))
    assert _links(body) == want


@pytest.mark.parametrize("role", ["consultant", "interior_designer"])
def test_r3_one_consultant_and_one_interior_designer_per_project(v2, role):
    """Owner 2 Nov ~21:40 (Q5 b): several only for trading house, subcontractor, tender party."""
    a, b = _party(v2, role), _party(v2, role)
    res = _register(v2, party_links=[{"role": role, "party_id": a.id}, {"role": role, "party_id": b.id}])
    assert res.status_code == 422, res.text
    assert res.json()["code"] == "project_party_role_single"


def test_r3_a_party_of_another_company_is_refused(v2):
    foreign = _party(v2, "subcontractor", company_id=v2.other_company)
    res = _register(v2, party_links=[{"role": "subcontractor", "party_id": foreign.id}])
    assert res.status_code == 422, res.text


def test_r3_a_party_of_the_wrong_type_for_the_role_is_refused(v2):
    arch = _party(v2, "architect")
    res = _register(v2, party_links=[{"role": "subcontractor", "party_id": arch.id}])
    assert res.status_code == 422, res.text
    assert res.json()["code"] == "project_party_role_mismatch"


def test_r3_an_unknown_role_is_refused(v2):
    sub = _party(v2, "subcontractor")
    res = _register(v2, party_links=[{"role": "developer", "party_id": sub.id}])
    assert res.status_code == 422, res.text


def test_r3_edit_replaces_the_links_and_leaving_them_out_keeps_them(v2):
    sub1, sub2 = _party(v2, "subcontractor"), _party(v2, "subcontractor")
    pid = _register(v2, party_links=[{"role": "subcontractor", "party_id": sub1.id}]).json()["id"]
    c = as_user(v2, v2.owner)
    kept = c.put(f"{PROJECTS}/{pid}", json={"address": "Lot 1"})
    assert kept.status_code == 200, kept.text
    assert [r["party_id"] for r in kept.json()["party_links"]] == [sub1.id]
    swapped = c.put(f"{PROJECTS}/{pid}", json={"party_links": [{"role": "subcontractor", "party_id": sub2.id}]})
    assert swapped.status_code == 200, swapped.text
    assert [r["party_id"] for r in swapped.json()["party_links"]] == [sub2.id]
    cleared = c.put(f"{PROJECTS}/{pid}", json={"party_links": []})
    assert cleared.json()["party_links"] == []


# ------------------------------------------------------------------ rule 4: party contacts master


def test_r4_contacts_crud_on_a_party(v2):
    party = _party(v2, "main_contractor")
    c = as_user(v2, v2.owner)
    made = c.post(f"{PARTIES}/{party.id}/contacts", json={"name": "Example Two", "job_title": "QS"})
    assert made.status_code == 201, made.text  # phone optional (owner 2 Nov)
    assert made.json()["phone"] is None
    cid = made.json()["id"]
    listed = c.get(f"{PARTIES}/{party.id}/contacts")
    assert [r["name"] for r in listed.json()["data"]] == ["Example Two"]
    edited = c.put(f"{PARTIES}/{party.id}/contacts/{cid}", json={"phone": "+60130002222"})
    assert edited.status_code == 200, edited.text
    assert edited.json()["phone"] == "+60130002222"
    gone = c.delete(f"{PARTIES}/{party.id}/contacts/{cid}")
    assert gone.status_code == 200, gone.text
    assert c.get(f"{PARTIES}/{party.id}/contacts").json()["data"] == []


def test_r4_a_contact_needs_a_name(v2):
    party = _party(v2, "architect")
    res = as_user(v2, v2.owner).post(f"{PARTIES}/{party.id}/contacts", json={"name": "  "})
    assert res.status_code == 422, res.text
    assert res.json()["code"] == "project_party_contact_name_required"


def test_r4_creating_a_contact_needs_the_parties_edit_grant(v2):
    party = _party(v2, "architect")
    res = as_user(v2, v2.sales_b).post(f"{PARTIES}/{party.id}/contacts", json={"name": "Example"})
    assert res.status_code == 403, res.text


def test_r4_a_submit_only_salesperson_can_list_contacts_to_pick(v2):
    party = _party(v2, "architect")
    _contact(v2, party, name="Ar. Example One")
    _contact(v2, party, name="Retired Example", is_active=False)
    res = as_user(v2, v2.sub_a).get(f"{PARTIES}/{party.id}/contacts")
    assert res.status_code == 200, res.text
    assert [r["name"] for r in res.json()["data"]] == ["Ar. Example One"]


def test_r4_contacts_of_another_companys_party_are_not_found(v2):
    foreign = _party(v2, "architect", company_id=v2.other_company)
    res = as_user(v2, v2.owner).get(f"{PARTIES}/{foreign.id}/contacts")
    assert res.status_code == 404, res.text


# ------------------------------------------------------------------ rules 5-7: contacts at registration


def test_r6_picked_contacts_become_stakeholders(v2):
    arch = _party(v2, "architect")
    mc = _party(v2, "main_contractor")
    one = _contact(v2, arch, name="Ar. Example One", phone="+60120001111", job_title="Principal")
    two = _contact(v2, mc, name="Example Two", job_title="QS")
    res = _register(
        v2, architect_party_id=arch.id, main_contractor_party_id=mc.id, contact_ids=[one.id, two.id]
    )
    assert res.status_code == 201, res.text
    rows = {s.person_name: s for s in _stakeholders(v2, res.json()["id"])}
    assert set(rows) == {"Ar. Example One", "Example Two"}
    assert rows["Ar. Example One"].party_id == arch.id
    assert rows["Ar. Example One"].party_contact_id == one.id
    assert rows["Ar. Example One"].phone == "+60120001111"
    assert rows["Ar. Example One"].job_title == "Principal"
    assert rows["Example Two"].phone is None


def test_r6_a_contact_picked_twice_is_one_stakeholder(v2):
    mc = _party(v2, "main_contractor")
    one = _contact(v2, mc)
    res = _register(v2, main_contractor_party_id=mc.id, contact_ids=[one.id, one.id])
    assert res.status_code == 201, res.text
    assert len(_stakeholders(v2, res.json()["id"])) == 1


def test_r7_a_contact_of_a_party_not_on_the_project_is_refused(v2):
    arch = _party(v2, "architect")
    stray = _contact(v2, _party(v2, "architect"))
    res = _register(v2, architect_party_id=arch.id, contact_ids=[stray.id])
    assert res.status_code == 422, res.text
    assert res.json()["code"] == "project_contact_not_on_party"


def test_r6_contacts_are_kept_on_a_submit_only_draft(v2):
    arch = _party(v2, "architect")
    one = _contact(v2, arch)
    res = _register(v2, user=v2.sub_a, submit=False, architect_party_id=arch.id, contact_ids=[one.id])
    assert res.status_code == 201, res.text
    assert [s.party_contact_id for s in _stakeholders(v2, res.json()["id"])] == [one.id]


def test_r6_the_developer_contacts_can_be_picked_too(v2):
    dev = _party(v2, "developer")
    one = _contact(v2, dev, name="Developer Example")
    res = _register(v2, developer_party_id=dev.id, contact_ids=[one.id])
    assert res.status_code == 201, res.text
    assert [s.party_id for s in _stakeholders(v2, res.json()["id"])] == [dev.id]


# ------------------------------------------------------------------ rules 10-13: parties read + phone fill


def _project_with_parties(w):
    dev = _party(w, "developer", phone="+60300001000")
    mc = _party(w, "main_contractor")
    two = _contact(w, mc, name="Example Two", phone="+60130002222")
    three = _contact(w, mc, name="Example Three")
    res = _register(w, developer_party_id=dev.id, main_contractor_party_id=mc.id, contact_ids=[two.id, three.id])
    assert res.status_code == 201, res.text
    return res.json()["id"], dev, mc, two, three


def test_r10_the_project_parties_read_lists_roles_and_contacts(v2):
    pid, dev, mc, two, three = _project_with_parties(v2)
    res = as_user(v2, v2.sales_b).get(f"{PROJECTS}/{pid}/parties")
    assert res.status_code == 200, res.text
    rows = {r["party_id"]: r for r in res.json()["data"]}
    assert rows[dev.id]["role"] == "developer" and rows[dev.id]["phone"] == "+60300001000"
    assert rows[mc.id]["role"] == "main_contractor"
    people = {c["name"]: c for c in rows[mc.id]["contacts"]}
    assert people["Example Two"]["phone"] == "+60130002222"
    assert people["Example Three"]["phone"] is None


def test_r11_a_blank_party_phone_is_filled_and_saved(v2):
    pid, dev, mc, two, three = _project_with_parties(v2)
    res = as_user(v2, v2.owner).post(f"{PROJECTS}/{pid}/parties/{mc.id}/phone", json={"phone": "+60135550000"})
    assert res.status_code == 200, res.text
    v2.db.refresh(mc)
    assert mc.phone == "+60135550000"


def test_r11_a_blank_contact_phone_is_saved_to_the_contact_and_its_stakeholder(v2):
    pid, dev, mc, two, three = _project_with_parties(v2)
    stake = next(s for s in _stakeholders(v2, pid) if s.party_contact_id == three.id)
    res = as_user(v2, v2.owner).post(
        f"{PROJECTS}/{pid}/parties/{mc.id}/phone", json={"phone": "+60140003333", "stakeholder_id": stake.id}
    )
    assert res.status_code == 200, res.text
    v2.db.refresh(three)
    v2.db.refresh(stake)
    v2.db.refresh(mc)
    assert three.phone == "+60140003333" and stake.phone == "+60140003333"
    assert mc.phone is None  # the firm's own line is not touched


def test_r11_a_number_on_file_is_never_overwritten(v2):
    pid, dev, mc, two, three = _project_with_parties(v2)
    res = as_user(v2, v2.owner).post(f"{PROJECTS}/{pid}/parties/{dev.id}/phone", json={"phone": "+60399999999"})
    assert res.status_code == 409, res.text
    assert res.json()["code"] == "project_party_phone_on_file"
    v2.db.refresh(dev)
    assert dev.phone == "+60300001000"


def test_r12_a_party_not_on_the_project_is_refused(v2):
    pid, *_ = _project_with_parties(v2)
    stray = _party(v2, "architect")
    res = as_user(v2, v2.owner).post(f"{PROJECTS}/{pid}/parties/{stray.id}/phone", json={"phone": "+60120000000"})
    assert res.status_code == 404, res.text


def test_r12_the_phone_fill_needs_edit_on_the_project_not_parties_edit(v2):
    pid, dev, mc, *_ = _project_with_parties(v2)
    # sales_b holds view + edit but is not the owner: refused like any other write.
    res = as_user(v2, v2.sales_b).post(f"{PROJECTS}/{pid}/parties/{mc.id}/phone", json={"phone": "+60120000000"})
    assert res.status_code == 403, res.text
    # viewer_own holds no edit grant at all (and the project is not theirs: the guard's 404).
    res = as_user(v2, v2.viewer_own).post(f"{PROJECTS}/{pid}/parties/{mc.id}/phone", json={"phone": "+60120000000"})
    assert res.status_code in (403, 404), res.text
    v2.db.refresh(mc)
    assert mc.phone is None


def test_r13_an_empty_phone_is_422(v2):
    pid, dev, mc, *_ = _project_with_parties(v2)
    res = as_user(v2, v2.owner).post(f"{PROJECTS}/{pid}/parties/{mc.id}/phone", json={"phone": "  "})
    assert res.status_code == 422, res.text


# ------------------------------------------------------------------ Parties page: server-side sort (owner rule)


def _parties_listed(w, **params):
    res = as_user(w, w.owner).get(f"{PARTIES}/", params={"party_type": "consultant", "limit": 50, **params})
    assert res.status_code == 200, res.text
    return res.json()["data"]


def test_parties_list_carries_the_contact_count(v2):
    party = _party(v2, "consultant", name=f"CONTOH Count {uid()[:6]}")
    _contact(v2, party)
    _contact(v2, party, name="Second")
    _contact(v2, party, name="Retired", is_active=False)
    row = next(r for r in _parties_listed(v2) if r["id"] == party.id)
    assert row["contact_count"] == 2


@pytest.mark.parametrize("direction", ["asc", "desc"])
def test_parties_list_sorts_by_contact_count_on_the_server(v2, direction):
    none = _party(v2, "consultant", name="CONTOH A none")
    two = _party(v2, "consultant", name="CONTOH B two")
    one = _party(v2, "consultant", name="CONTOH C one")
    _contact(v2, two)
    _contact(v2, two, name="x")
    _contact(v2, one)
    ids = [r["id"] for r in _parties_listed(v2, sort="contact_count", dir=direction)]
    order = [none.id, one.id, two.id]
    assert ids == (order if direction == "asc" else order[::-1])


def test_parties_list_sorts_by_project_count_on_the_server(v2):
    busy = _party(v2, "consultant", name="CONTOH Z busy")
    idle = _party(v2, "consultant", name="CONTOH Y idle")
    _register(v2, party_links=[{"role": "consultant", "party_id": busy.id}])
    ids = [r["id"] for r in _parties_listed(v2, sort="project_count", dir="desc")]
    assert ids.index(busy.id) < ids.index(idle.id)


def test_parties_list_sorts_by_name_desc_and_pages_after_sorting(v2):
    names = [f"CONTOH {c}" for c in "ABC"]
    for n in names:
        _party(v2, "consultant", name=n)
    page = _parties_listed(v2, sort="name", dir="desc", limit=2, page=1)
    assert [r["name"] for r in page] == ["CONTOH C", "CONTOH B"]


def test_parties_project_count_includes_party_links(v2):
    sub = _party(v2, "subcontractor")
    _register(v2, party_links=[{"role": "subcontractor", "party_id": sub.id}])
    res = as_user(v2, v2.owner).get(f"{PARTIES}/{sub.id}")
    assert res.json()["project_count"] == 1


# ------------------------------------------------------------------ rule 4: deferred delete (D7)

PENDING = "/api/v1/pending-actions"


def _park_contact_delete(w, user, contact):
    return as_user(w, user).post(
        PENDING,
        json={
            "action_key": "project_party_contact.delete",
            "entity_type": "project_party_contact",
            "entity_id": contact.id,
            "payload": {},
        },
    )


def test_r4_contact_delete_parks_with_the_parties_edit_grant(v2):
    contact = _contact(v2, _party(v2, "architect"))
    res = _park_contact_delete(v2, v2.owner, contact)
    assert res.status_code == 202, res.text


def test_r4_contact_delete_without_parties_edit_is_refused(v2):
    contact = _contact(v2, _party(v2, "architect"))
    res = _park_contact_delete(v2, v2.sales_b, contact)
    assert res.status_code == 403, res.text


def test_r4_the_parked_delete_removes_the_contact_and_keeps_the_stakeholder_copy(v2):
    from app.models.projects import ProjectPartyContact
    from app.services.form_action_registry import get_action

    arch = _party(v2, "architect")
    contact = _contact(v2, arch, name="Ar. Leaving")
    pid = _register(v2, architect_party_id=arch.id, contact_ids=[contact.id]).json()["id"]
    get_action("project_party_contact.delete").execute(v2.db, {"entity_id": contact.id})
    v2.db.flush()
    assert v2.db.get(ProjectPartyContact, contact.id) is None
    (stake,) = _stakeholders(v2, pid)
    v2.db.refresh(stake)
    assert stake.person_name == "Ar. Leaving" and stake.party_contact_id is None


# ------------------------------------------------------------------ security review gaps (L1, L2 + attack paths)


def test_sec_a_picker_without_parties_view_gets_names_only(v2):
    party = _party(v2, "architect")
    _contact(v2, party, name="Ar. Private", phone="+60120009999")
    row = as_user(v2, v2.sub_a).get(f"{PARTIES}/{party.id}/contacts").json()["data"][0]
    assert row["name"] == "Ar. Private"
    assert "phone" not in row and "email" not in row
    full = as_user(v2, v2.owner).get(f"{PARTIES}/{party.id}/contacts").json()["data"][0]
    assert full["phone"] == "+60120009999"


def test_sec_contact_ids_are_capped(v2):
    res = _register(v2, contact_ids=[uid() for _ in range(201)])
    assert res.status_code == 422, res.text


def test_sec_phone_fill_refuses_a_stakeholder_of_another_project(v2):
    pid, dev, mc, two, three = _project_with_parties(v2)
    other_pid, _d, other_mc, _t, other_three = _project_with_parties(v2)
    foreign = next(s for s in _stakeholders(v2, other_pid) if s.party_contact_id == other_three.id)
    res = as_user(v2, v2.owner).post(
        f"{PROJECTS}/{pid}/parties/{mc.id}/phone", json={"phone": "+60120000001", "stakeholder_id": foreign.id}
    )
    assert res.status_code == 404, res.text
    v2.db.refresh(foreign)
    assert foreign.phone is None


def test_sec_phone_fill_refuses_a_stakeholder_of_another_party_on_the_same_project(v2):
    pid, dev, mc, two, three = _project_with_parties(v2)
    stake = next(s for s in _stakeholders(v2, pid) if s.party_contact_id == three.id)
    res = as_user(v2, v2.owner).post(
        f"{PROJECTS}/{pid}/parties/{dev.id}/phone", json={"phone": "+60120000002", "stakeholder_id": stake.id}
    )
    assert res.status_code == 404, res.text


def test_sec_a_contact_of_another_company_is_refused_at_registration(v2):
    arch = _party(v2, "architect")
    foreign_party = _party(v2, "architect", company_id=v2.other_company)
    foreign = _contact(v2, foreign_party)
    res = _register(v2, architect_party_id=arch.id, contact_ids=[foreign.id])
    assert res.status_code == 422, res.text
    assert res.json()["code"] == "project_contact_not_on_party"


def test_sec_an_own_projects_user_cannot_read_parties_of_a_project_not_theirs(v2):
    pid, *_ = _project_with_parties(v2)
    res = as_user(v2, v2.viewer_own).get(f"{PROJECTS}/{pid}/parties")
    assert res.status_code == 404, res.text


def test_sec_the_phone_fill_is_audited(v2):
    from app.models.audit import AuditLog

    pid, dev, mc, *_ = _project_with_parties(v2)
    res = as_user(v2, v2.owner).post(f"{PROJECTS}/{pid}/parties/{mc.id}/phone", json={"phone": "+60135551111"})
    assert res.status_code == 200, res.text
    rows = v2.db.query(AuditLog).filter(AuditLog.entity_id == mc.id, AuditLog.action == "UPDATE").all()
    assert any((r.new_values or {}).get("phone") == "+60135551111" for r in rows), [
        (r.action, r.new_values) for r in rows
    ]
