"""PROJECT-PARTY-ROLES PR 1 (red-first): configurable party roles, one parties table, any party any
role, contacts added on edit too.

Card: documentation/plans/project-sales/CARD-project-party-roles-10nov.md (owner answers 10 Nov
~15:10: Q1 a, Q2 a, Q3 a, Q4 b, Q5 a, Q6 b, Q7 a). UAC:
documentation/plans/project-sales/project-party-roles-10nov-acceptance-criteria.md (AC-1..AC-11).
Every name and number is invented.
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
SET_KEY = "project_party_role"


def _party(w, party_type: str, name: str | None = None):
    return developer(w.db, w.company_id, name or f"CONTOH {party_type} {uid()[:6]}", party_type)


def _contact(w, party, name="Example Person", phone=None):
    from app.models.projects import ProjectPartyContact

    row = ProjectPartyContact(id=uid(), company_id=party.company_id, party_id=party.id, name=name, phone=phone)
    w.db.add(row)
    w.db.flush()
    return row


def _register(w, **body):
    base = {"title": title("PPR"), "lead_source": "site_visit"}
    base.update(body)
    return as_user(w, w.owner).post(LIST, json={k: v for k, v in base.items() if v is not None})


def _role_set(w):
    from app.models.lookup import LookupSet

    return w.db.query(LookupSet).filter(LookupSet.set_key == SET_KEY, LookupSet.tenant_id.is_(None)).one()


def _option(w, value):
    from app.models.lookup import LookupOption

    return w.db.query(LookupOption).filter(LookupOption.set_id == _role_set(w).id, LookupOption.value == value).one()


def _add_role(w, value, label, *, allows_many=False, active=True):
    from app.models.lookup import LookupOption

    row = LookupOption(
        set_id=_role_set(w).id, value=value, label=label, sort_order=900, is_active=active, allows_many=allows_many
    )
    w.db.add(row)
    w.db.flush()
    return row


def _links(body):
    return sorted((r["role"], r["party_id"]) for r in body["party_links"])


# ------------------------------------------------------------------ AC-1: the seeded role list


def test_ac1_the_role_set_is_seeded_with_todays_eight_and_their_many_flags():
    from app.services.project_party_roles import SEED_ROLES

    assert [r[0] for r in SEED_ROLES] == [
        "developer", "architect", "main_contractor", "trading_house",
        "subcontractor", "tender_party", "consultant", "interior_designer",
    ]
    many = {r[0] for r in SEED_ROLES if r[2]}
    assert many == {"trading_house", "subcontractor", "tender_party"}
    assert "dealer" not in {r[0] for r in SEED_ROLES}


def test_ac1_the_public_options_read_carries_allows_many(v2):
    res = as_user(v2, v2.owner).get(f"/api/v1/lookup/{SET_KEY}/options?include_inactive=true")
    assert res.status_code == 200, res.text
    rows = {r["value"]: r for r in res.json()}
    assert rows["trading_house"]["allows_many"] is True
    assert rows["architect"]["allows_many"] is False


def test_ac1_option_create_and_update_carry_allows_many(v2):
    from app.schemas.lookup import LookupOptionCreate, LookupOptionUpdate
    from app.services.lookup_option_service import LookupOptionService

    svc = LookupOptionService(v2.db)
    row = svc.create(_role_set(v2).id, LookupOptionCreate(value=f"qs_{uid()[:6]}", label="Quantity surveyor", allows_many=True))
    assert row.allows_many is True
    row = svc.update(row.id, LookupOptionUpdate(allows_many=False))
    assert row.allows_many is False


# ------------------------------------------------------------------ AC-2: a role an admin adds


def test_ac2_a_new_role_links_parties_without_a_code_change(v2):
    role = f"qs_{uid()[:6]}"
    _add_role(v2, role, "Quantity surveyor")
    qs = _party(v2, "consultant")
    res = _register(v2, party_links=[{"role": role, "party_id": qs.id}])
    assert res.status_code == 201, res.text
    assert _links(res.json()) == [(role, qs.id)]


def test_ac2_a_new_role_is_a_valid_party_type(v2):
    role = f"qs_{uid()[:6]}"
    _add_role(v2, role, "Quantity surveyor")
    res = as_user(v2, v2.owner).post(f"{PARTIES}/", json={"party_type": role, "name": f"CONTOH QS {uid()[:6]}"})
    assert res.status_code == 201, res.text
    assert res.json()["party_type"] == role


def test_ac2_a_party_type_outside_the_set_is_422(v2):
    res = as_user(v2, v2.owner).post(f"{PARTIES}/", json={"party_type": "dealer", "name": f"CONTOH {uid()[:6]}"})
    assert res.status_code == 422, res.text
    assert res.json()["code"] == "project_party_type_invalid"


def test_ac2_many_flag_comes_from_the_set(v2):
    role = f"qs_{uid()[:6]}"
    _add_role(v2, role, "Quantity surveyor", allows_many=True)
    a, b = _party(v2, "consultant"), _party(v2, "consultant")
    res = _register(v2, party_links=[{"role": role, "party_id": a.id}, {"role": role, "party_id": b.id}])
    assert res.status_code == 201, res.text


def test_ac2_a_one_party_role_refuses_a_second_party(v2):
    a, b = _party(v2, "consultant"), _party(v2, "consultant")
    res = _register(v2, party_links=[{"role": "consultant", "party_id": a.id}, {"role": "consultant", "party_id": b.id}])
    assert res.status_code == 422, res.text
    assert res.json()["code"] == "project_party_role_single"


def test_ac2_switching_trading_house_to_one_keeps_two_already_linked_but_refuses_a_third(v2):
    a, b, c = (_party(v2, "trading_house") for _ in range(3))
    pid = _register(
        v2, party_links=[{"role": "trading_house", "party_id": a.id}, {"role": "trading_house", "party_id": b.id}]
    ).json()["id"]
    _option(v2, "trading_house").allows_many = False
    v2.db.flush()
    client = as_user(v2, v2.owner)
    kept = client.put(f"{PROJECTS}/{pid}", json={"party_links": [
        {"role": "trading_house", "party_id": a.id}, {"role": "trading_house", "party_id": b.id}]})
    assert kept.status_code == 200, kept.text
    third = client.put(f"{PROJECTS}/{pid}", json={"party_links": [
        {"role": "trading_house", "party_id": a.id}, {"role": "trading_house", "party_id": b.id},
        {"role": "trading_house", "party_id": c.id}]})
    assert third.status_code == 422, third.text
    assert third.json()["code"] == "project_party_role_single"


def test_ac2_developer_is_not_a_link_role(v2):
    dev = _party(v2, "developer")
    res = _register(v2, party_links=[{"role": "developer", "party_id": dev.id}])
    assert res.status_code == 422, res.text
    assert res.json()["code"] == "project_party_role_invalid"


def test_ac2_an_unknown_role_is_422(v2):
    p = _party(v2, "consultant")
    res = _register(v2, party_links=[{"role": "dealer", "party_id": p.id}])
    assert res.status_code == 422, res.text
    assert res.json()["code"] == "project_party_role_invalid"


# ------------------------------------------------------------------ AC-3: rename touches no project


def test_ac3_renaming_a_role_keeps_every_link(v2):
    a = _party(v2, "main_contractor")
    pid = _register(v2, party_links=[{"role": "main_contractor", "party_id": a.id}]).json()["id"]
    _option(v2, "main_contractor").label = "Main con"
    v2.db.flush()
    body = as_user(v2, v2.owner).get(f"{PROJECTS}/{pid}").json()
    assert _links(body) == [("main_contractor", a.id)]


# ------------------------------------------------------------------ AC-4: a deactivated role


def test_ac4_an_inactive_role_already_on_a_project_is_kept_on_save(v2):
    idr = _party(v2, "interior_designer")
    pid = _register(v2, party_links=[{"role": "interior_designer", "party_id": idr.id}]).json()["id"]
    _option(v2, "interior_designer").is_active = False
    v2.db.flush()
    res = as_user(v2, v2.owner).put(f"{PROJECTS}/{pid}", json={"party_links": [{"role": "interior_designer", "party_id": idr.id}]})
    assert res.status_code == 200, res.text
    assert _links(res.json()) == [("interior_designer", idr.id)]


def test_ac4_a_new_link_in_an_inactive_role_is_422(v2):
    _option(v2, "interior_designer").is_active = False
    v2.db.flush()
    idr = _party(v2, "interior_designer")
    res = _register(v2, party_links=[{"role": "interior_designer", "party_id": idr.id}])
    assert res.status_code == 422, res.text
    assert res.json()["code"] == "project_party_role_inactive"


def test_ac4_an_inactive_role_is_not_a_type_for_a_new_party(v2):
    _option(v2, "interior_designer").is_active = False
    v2.db.flush()
    res = as_user(v2, v2.owner).post(f"{PARTIES}/", json={"party_type": "interior_designer", "name": f"CONTOH {uid()[:6]}"})
    assert res.status_code == 422, res.text


# ------------------------------------------------------------------ AC-5: the option guard


def test_ac5_developer_cannot_be_deactivated(v2):
    from app.schemas.lookup import LookupOptionUpdate
    from app.services.error_handler import AppException
    from app.services.lookup_option_service import LookupOptionService

    with pytest.raises(AppException) as exc:
        LookupOptionService(v2.db).update(_option(v2, "developer").id, LookupOptionUpdate(is_active=False))
    assert exc.value.code == "project_party_role_locked"


def test_ac5_developer_can_be_renamed(v2):
    from app.schemas.lookup import LookupOptionUpdate
    from app.services.lookup_option_service import LookupOptionService

    row = LookupOptionService(v2.db).update(_option(v2, "developer").id, LookupOptionUpdate(label="Owner developer"))
    assert row.label == "Owner developer"


def test_ac5_developer_cannot_be_deleted(v2):
    from app.services.error_handler import AppException
    from app.services.lookup_option_service import LookupOptionService

    with pytest.raises(AppException) as exc:
        LookupOptionService(v2.db).delete(_option(v2, "developer").id)
    assert exc.value.code == "project_party_role_locked"


def test_ac5_a_role_used_by_a_party_cannot_be_deleted(v2):
    from app.services.error_handler import AppException
    from app.services.lookup_option_service import LookupOptionService

    role = f"qs_{uid()[:6]}"
    opt = _add_role(v2, role, "Quantity surveyor")
    _party(v2, role)
    with pytest.raises(AppException) as exc:
        LookupOptionService(v2.db).delete(opt.id)
    assert exc.value.status_code == 409
    assert exc.value.code == "project_party_role_in_use"


def test_ac5_a_role_used_by_a_project_link_cannot_be_deleted(v2):
    from app.services.error_handler import AppException
    from app.services.lookup_option_service import LookupOptionService

    role = f"qs_{uid()[:6]}"
    opt = _add_role(v2, role, "Quantity surveyor")
    p = _party(v2, "consultant")
    assert _register(v2, party_links=[{"role": role, "party_id": p.id}]).status_code == 201
    with pytest.raises(AppException) as exc:
        LookupOptionService(v2.db).delete(opt.id)
    assert exc.value.code == "project_party_role_in_use"


def test_ac5_a_role_key_in_use_cannot_be_rewritten(v2):
    from app.schemas.lookup import LookupOptionUpdate
    from app.services.error_handler import AppException
    from app.services.lookup_option_service import LookupOptionService

    _party(v2, "consultant")
    with pytest.raises(AppException) as exc:
        LookupOptionService(v2.db).update(_option(v2, "consultant").id, LookupOptionUpdate(value="consultancy"))
    assert exc.value.code == "project_party_role_in_use"


def test_ac5_an_unused_role_deletes(v2):
    from app.models.lookup import LookupOption
    from app.services.lookup_option_service import LookupOptionService

    opt = _add_role(v2, f"qs_{uid()[:6]}", "Quantity surveyor")
    LookupOptionService(v2.db).delete(opt.id)
    assert v2.db.get(LookupOption, opt.id) is None


def test_ac5_the_guard_leaves_other_sets_alone(v2):
    from app.models.lookup import LookupOption, LookupSet
    from app.services.lookup_option_service import LookupOptionService

    other = LookupSet(set_key=f"zzt_other_{uid()[:6]}", name="Other", is_active=True)
    v2.db.add(other)
    v2.db.flush()
    opt = LookupOption(set_id=other.id, value="developer", label="Developer", sort_order=1, is_active=True)
    v2.db.add(opt)
    v2.db.flush()
    LookupOptionService(v2.db).delete(opt.id)
    assert v2.db.get(LookupOption, opt.id) is None


# ------------------------------------------------------------------ AC-6: architect / main contractor are links


def test_ac6_architect_and_main_contractor_are_ordinary_links(v2):
    arch, mc = _party(v2, "architect"), _party(v2, "main_contractor")
    res = _register(v2, party_links=[
        {"role": "architect", "party_id": arch.id}, {"role": "main_contractor", "party_id": mc.id}])
    assert res.status_code == 201, res.text
    assert _links(res.json()) == sorted([("architect", arch.id), ("main_contractor", mc.id)])


def test_ac6_the_old_columns_are_not_written(v2):
    from app.models.projects import ProjectSalesProfile

    arch = _party(v2, "architect")
    pid = _register(v2, party_links=[{"role": "architect", "party_id": arch.id}]).json()["id"]
    profile = v2.db.get(ProjectSalesProfile, pid)
    assert profile.architect_party_id is None


def test_ac6_the_project_response_no_longer_carries_the_two_columns(v2):
    body = _register(v2).json()
    for key in ("architect_party_id", "architect_name", "main_contractor_party_id", "main_contractor_name"):
        assert key not in body


def test_ac6_the_project_parties_read_lists_architect_from_the_link(v2):
    arch = _party(v2, "architect")
    pid = _register(v2, party_links=[{"role": "architect", "party_id": arch.id}]).json()["id"]
    rows = as_user(v2, v2.owner).get(f"{PROJECTS}/{pid}/parties").json()["data"]
    assert ("architect", arch.id) in {(r["role"], r["party_id"]) for r in rows}


def test_ac6_the_backfill_sql_copies_both_columns_once(v2):
    """The migration's backfill statement, run twice: one link per column, no duplicates."""
    from sqlalchemy import text

    from app.models.projects import ProjectPartyLink, ProjectSalesProfile
    from app.services.project_party_roles import BACKFILL_SQL

    arch, mc = _party(v2, "architect"), _party(v2, "main_contractor")
    pid = _register(v2).json()["id"]
    profile = v2.db.get(ProjectSalesProfile, pid)
    profile.architect_party_id = arch.id
    profile.main_contractor_party_id = mc.id
    v2.db.flush()
    # The scratch schema stands in for `projects`; the statements name the real one.
    mapped = (v2.db.connection().get_execution_options().get("schema_translate_map") or {}).get("projects", "projects")
    for _ in range(2):
        for stmt in BACKFILL_SQL:
            v2.db.execute(text(stmt.replace("projects.", f"{mapped}.")))
    links = v2.db.query(ProjectPartyLink).filter(ProjectPartyLink.project_id == pid).all()
    assert sorted((l.role, l.party_id) for l in links) == sorted([("architect", arch.id), ("main_contractor", mc.id)])


# ------------------------------------------------------------------ AC-7 / AC-8: any party any role, one row per firm


def test_ac7_a_main_contractor_can_be_a_subcontractor_elsewhere(v2):
    mc = _party(v2, "main_contractor")
    res = _register(v2, party_links=[{"role": "subcontractor", "party_id": mc.id}])
    assert res.status_code == 201, res.text
    assert _links(res.json()) == [("subcontractor", mc.id)]


def test_ac7_the_same_party_can_hold_two_roles_on_one_project(v2):
    p = _party(v2, "main_contractor")
    res = _register(v2, party_links=[{"role": "main_contractor", "party_id": p.id}, {"role": "tender_party", "party_id": p.id}])
    assert res.status_code == 201, res.text


def test_ac7_party_search_without_a_type_returns_every_type(v2):
    tag = uid()[:6]
    a = _party(v2, "architect", f"CONTOH SEARCH {tag} A")
    m = _party(v2, "main_contractor", f"CONTOH SEARCH {tag} M")
    res = as_user(v2, v2.owner).get(f"{PARTIES}/?query=CONTOH SEARCH {tag}")
    assert res.status_code == 200, res.text
    got = {r["id"]: r["party_type"] for r in res.json()["data"]}
    assert got == {a.id: "architect", m.id: "main_contractor"}


def test_ac8_create_on_the_spot_reuses_a_same_name_party_of_another_type(v2):
    name = f"CONTOH FIRM {uid()[:6]}"
    mc = _party(v2, "main_contractor", name)
    res = as_user(v2, v2.owner).post(f"{PARTIES}/", json={"party_type": "subcontractor", "name": f"  {name.lower()} "})
    assert res.status_code in (200, 201), res.text
    assert res.json()["id"] == mc.id
    assert res.json()["party_type"] == "main_contractor"


def test_ac8_a_party_type_can_be_edited_to_any_active_role(v2):
    p = _party(v2, "architect")
    res = as_user(v2, v2.owner).put(f"{PARTIES}/{p.id}", json={"party_type": "interior_designer"})
    assert res.status_code == 200, res.text
    assert res.json()["party_type"] == "interior_designer"


# ------------------------------------------------------------------ AC-9 / AC-10: contacts on edit, add only


def test_ac9_contacts_picked_on_edit_become_stakeholders(v2):
    from app.models.projects import ProjectStakeholder

    arch = _party(v2, "architect")
    person = _contact(v2, arch, "AR. CONTOH")
    pid = _register(v2, party_links=[{"role": "architect", "party_id": arch.id}]).json()["id"]
    res = as_user(v2, v2.owner).put(f"{PROJECTS}/{pid}", json={"contact_ids": [person.id]})
    assert res.status_code == 200, res.text
    rows = v2.db.query(ProjectStakeholder).filter(ProjectStakeholder.project_id == pid).all()
    assert [r.party_contact_id for r in rows] == [person.id]


def test_ac9_a_contact_of_a_party_linked_in_the_same_edit_is_accepted(v2):
    arch = _party(v2, "architect")
    person = _contact(v2, arch)
    pid = _register(v2).json()["id"]
    res = as_user(v2, v2.owner).put(f"{PROJECTS}/{pid}", json={
        "party_links": [{"role": "architect", "party_id": arch.id}], "contact_ids": [person.id]})
    assert res.status_code == 200, res.text


def test_ac10_contact_ids_on_edit_only_add(v2):
    from app.models.projects import ProjectStakeholder

    arch = _party(v2, "architect")
    a, b = _contact(v2, arch, "AR. A"), _contact(v2, arch, "AR. B")
    pid = _register(v2, party_links=[{"role": "architect", "party_id": arch.id}], contact_ids=[a.id]).json()["id"]
    res = as_user(v2, v2.owner).put(f"{PROJECTS}/{pid}", json={"contact_ids": [b.id]})
    assert res.status_code == 200, res.text
    got = {r.party_contact_id for r in v2.db.query(ProjectStakeholder).filter(ProjectStakeholder.project_id == pid)}
    assert got == {a.id, b.id}


def test_ac10_a_contact_of_a_party_not_on_the_project_is_refused_on_edit(v2):
    stranger = _party(v2, "architect")
    person = _contact(v2, stranger)
    pid = _register(v2).json()["id"]
    res = as_user(v2, v2.owner).put(f"{PROJECTS}/{pid}", json={"contact_ids": [person.id]})
    assert res.status_code == 422, res.text
    assert res.json()["code"] == "project_contact_not_on_party"
