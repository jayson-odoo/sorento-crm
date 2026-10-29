"""LEAD-GOVERNS-REGISTER Phase 2 red tests: UAC H (own leads, RBAC) and E6 (submit-only register).

Worlds: the PROJECT-REGISTER-V2 `v2` fixture. `sub_a` / `sub_b` hold `projects.registrations.submit`
+ `projects.projects.view_own` (the salesperson role after PORTAL-P4); `viewer_own` holds view_own
only; `owner` holds view + edit; `nobody` holds nothing relevant. A user with view_own + edit and no
view is added per test. Leads are seeded straight in the database so owner and creator are pinned.
"""
from __future__ import annotations

import uuid

import pytest

from app.main import app  # noqa: F401  MUST be first app import (circular import)

from ._lead_governs_register_support import (
    LEADS,
    LIST,
    STAFF,
    ids_of,
    lead_row,
    new_customer,
    profile_of,
    project_of,
    projects_titled,
    reload_lead,
    title,
)
from ._project_register_v2_support import EDIT, VIEW_OWN, as_user, submit_existing, v2  # noqa: F401
from ._project_registration_support import active_user

# ------------------------------------------------------------------ H1, H2: reads


def _three_leads(w):
    """One owned by A, one created by A but owned by B, one of B only."""
    owned = lead_row(w, customer_id=w.customer.id, owner=w.sub_a, created_by=w.sub_a, name="CONTOH Owned by A")
    made = lead_row(w, customer_id=w.customer.id, owner=w.sub_b, created_by=w.sub_a, name="CONTOH Made by A")
    theirs = lead_row(w, customer_id=w.customer.id, owner=w.sub_b, created_by=w.sub_b, name="CONTOH Only B")
    return owned, made, theirs


def test_h1_a_limited_reader_lists_only_their_own_leads(v2):
    owned, made, theirs = _three_leads(v2)
    res = as_user(v2, v2.sub_a).get(LEADS)
    assert res.status_code == 200, res.text
    # Own = owner_user_id only (security M2): the lead A created but B owns is not A's.
    assert ids_of(res) == {owned.id}
    assert res.json()["pagination"]["total"] == 1


def test_h1_the_total_and_filters_stay_inside_the_own_set(v2):
    owned, made, theirs = _three_leads(v2)
    page = as_user(v2, v2.sub_a).get(LEADS, params={"limit": 1})
    assert page.status_code == 200, page.text
    assert page.json()["pagination"]["total"] == 1
    assert len(page.json()["data"]) == 1

    search = as_user(v2, v2.sub_a).get(LEADS, params={"query": "Only B"})
    assert search.status_code == 200, search.text
    assert ids_of(search) == set()
    assert search.json()["pagination"]["total"] == 0

    by_owner = as_user(v2, v2.sub_a).get(LEADS, params={"owner_user_id": v2.sub_b})
    assert by_owner.status_code == 200, by_owner.text
    assert ids_of(by_owner) == set()


def test_h1_a_view_only_to_own_reader_without_submit_lists_own_leads(v2):
    mine = lead_row(v2, customer_id=v2.customer.id, owner=v2.viewer_own)
    lead_row(v2, customer_id=v2.customer.id, owner=v2.sub_b)
    res = as_user(v2, v2.viewer_own).get(LEADS)
    assert res.status_code == 200, res.text
    assert ids_of(res) == {mine.id}


def test_h1_a_view_holder_still_sees_every_lead(v2):
    owned, made, theirs = _three_leads(v2)
    res = as_user(v2, v2.owner).get(LEADS)
    assert res.status_code == 200, res.text
    assert ids_of(res) == {owned.id, made.id, theirs.id}


def test_h1_holding_neither_slug_is_403(v2):
    assert as_user(v2, v2.nobody).get(LEADS).status_code == 403


def test_h2_a_limited_reader_opens_their_own_lead_but_not_one_they_only_created(v2):
    owned, made, theirs = _three_leads(v2)
    client = as_user(v2, v2.sub_a)
    assert client.get(f"{LEADS}/{owned.id}").status_code == 200
    assert client.get(f"{LEADS}/{made.id}").status_code == 404


def test_h2_anyone_elses_lead_is_a_404_for_a_limited_reader(v2):
    owned, made, theirs = _three_leads(v2)
    res = as_user(v2, v2.sub_a).get(f"{LEADS}/{theirs.id}")
    assert res.status_code == 404, res.text


def test_h2_a_view_holder_opens_any_lead_and_neither_slug_is_403(v2):
    owned, made, theirs = _three_leads(v2)
    assert as_user(v2, v2.owner).get(f"{LEADS}/{theirs.id}").status_code == 200
    assert as_user(v2, v2.nobody).get(f"{LEADS}/{owned.id}").status_code == 403


# ------------------------------------------------------------------ H3: create as submit-only


def test_h3_a_submit_only_user_creates_a_lead_owned_by_themselves(v2):
    res = as_user(v2, v2.sub_a).post(
        LEADS, json={"title": title("Lead"), "customer_id": v2.customer.id}
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["owner_user_id"] == v2.sub_a
    listed = as_user(v2, v2.sub_a).get(LEADS)
    assert body["id"] in ids_of(listed)


def test_h3_the_owner_in_the_body_is_ignored_for_a_submit_only_user(v2):
    res = as_user(v2, v2.sub_a).post(
        LEADS,
        json={"title": title("Lead"), "customer_id": v2.customer.id, "owner_user_id": v2.sub_b},
    )
    assert res.status_code == 201, res.text
    assert res.json()["owner_user_id"] == v2.sub_a
    assert reload_lead(v2, res.json()["id"]).owner_user_id == v2.sub_a


def test_h3_the_customer_rules_apply_to_a_submit_only_creator(v2):
    none = as_user(v2, v2.sub_a).post(LEADS, json={"title": title("Lead")})
    assert none.status_code == 422, none.text
    assert none.json()["code"] == "lead_customer_required"
    inline = as_user(v2, v2.sub_a).post(
        LEADS, json={"title": title("Lead"), "new_customer": {"customer_name": "CONTOH Inline"}}
    )
    assert inline.status_code == 422, inline.text


def test_h3_a_reader_with_view_own_only_or_nothing_cannot_create(v2):
    body = {"title": title("Lead"), "customer_id": v2.customer.id}
    assert as_user(v2, v2.viewer_own).post(LEADS, json=body).status_code == 403
    assert as_user(v2, v2.nobody).post(LEADS, json=body).status_code == 403


# ------------------------------------------------------------------ H4: every other route keeps its slug

_ROUTES = [
    ("put", "{id}", {"notes": "x"}),
    ("post", "{id}/status", {"to_status_id": str(uuid.uuid4())}),
    ("post", "{id}/assign", {"owner_user_id": str(uuid.uuid4())}),
    ("post", "{id}/accept", {}),
    ("post", "{id}/decline", {"reason": "Not my patch"}),
    ("get", "{id}/qualify-preview", None),
    ("post", "{id}/qualify", {"title": "CONTOH Qualify"}),
    ("post", "{id}/disqualify", {"reason": "Not interested"}),
    ("post", "{id}/reopen", {}),
    ("delete", "{id}", None),
    ("get", "metrics", None),
    ("get", "disqualify-reasons", None),
]


@pytest.mark.parametrize("who", ["sub_a", "viewer_own"])
@pytest.mark.parametrize("method,path,body", _ROUTES, ids=[f"{m}-{p}" for m, p, _ in _ROUTES])
def test_h4_other_lead_routes_stay_403_for_submit_only_and_limited_readers(v2, who, method, path, body):
    user = getattr(v2, who)
    lead = lead_row(v2, customer_id=v2.customer.id, owner=user, created_by=user)
    kwargs = {"json": body} if body is not None else {}
    res = getattr(as_user(v2, user), method)(f"{LEADS}/{path.format(id=lead.id)}", **kwargs)
    assert res.status_code == 403, res.text


# ------------------------------------------------------------------ H5: view_own + edit, no view


def test_h5_view_own_plus_edit_is_still_limited_on_reads(v2):
    user = active_user(v2.db, "Edit Own X")
    v2.perms[user] = {VIEW_OWN, EDIT}
    mine = lead_row(v2, customer_id=v2.customer.id, owner=user)
    lead_row(v2, customer_id=v2.customer.id, owner=v2.sub_b)
    res = as_user(v2, user).get(LEADS)
    assert res.status_code == 200, res.text
    assert ids_of(res) == {mine.id}
    assert res.json()["pagination"]["total"] == 1


def test_h5_view_own_plus_edit_creates_as_an_edit_holder(v2):
    user = active_user(v2.db, "Edit Own Y")
    v2.perms[user] = {VIEW_OWN, EDIT}
    res = as_user(v2, user).post(
        LEADS, json={"title": title("Lead"), "customer_id": v2.customer.id}
    )
    assert res.status_code == 201, res.text
    assert res.json()["owner_user_id"] == user


# ------------------------------------------------------------------ E6: submit-only register


def _register(w, user, *, submit: bool, **body):
    payload = {"title": title("Sub"), "submit": submit, **body}
    return as_user(w, user).post(LIST, json=payload)


def _own_lead(w, user=None, customer_id="default", **kw):
    user = user or w.sub_a
    cid = w.customer.id if customer_id == "default" else customer_id
    return lead_row(w, customer_id=cid, owner=user, created_by=user, **kw)


def test_e6_submitting_with_an_own_lead_is_pending_linked_and_takes_the_leads_customer(v2):
    lead = _own_lead(v2)
    res = _register(v2, v2.sub_a, submit=True, lead_id=lead.id)
    assert res.status_code == 201, res.text
    row = project_of(v2, res.json()["id"])
    assert row.approval_state == "pending"
    assert row.lead_id == lead.id
    assert profile_of(v2, row.id).customer_id == v2.customer.id
    assert reload_lead(v2, lead.id).outcome == "qualified"


def test_e6_submitting_without_a_lead_is_refused(v2):
    name = title("NoLeadSub")
    res = _register(v2, v2.sub_a, submit=True, title=name, customer_id=v2.customer.id)
    assert res.status_code == 422, res.text
    assert res.json()["code"] == "project_lead_required"
    assert projects_titled(v2, name) == 0


def test_e6_a_draft_saves_without_a_lead(v2):
    res = _register(v2, v2.sub_a, submit=False, customer_id=v2.customer.id)
    assert res.status_code == 201, res.text
    row = project_of(v2, res.json()["id"])
    assert row.approval_state == "draft"
    assert row.lead_id is None


def test_e6_a_draft_keeps_the_lead_it_was_saved_with(v2):
    lead = _own_lead(v2)
    res = _register(v2, v2.sub_a, submit=False, lead_id=lead.id)
    assert res.status_code == 201, res.text
    assert project_of(v2, res.json()["id"]).lead_id == lead.id


@pytest.mark.parametrize("submit", [False, True])
def test_e6_a_lead_that_is_not_theirs_is_a_404_lead_not_found(v2, submit):
    theirs = _own_lead(v2, user=v2.sub_b)
    name = title("NotMine")
    res = _register(v2, v2.sub_a, submit=submit, title=name, lead_id=theirs.id, customer_id=v2.customer.id)
    assert res.status_code == 404, res.text
    assert res.json()["code"] == "lead_not_found"
    assert projects_titled(v2, name) == 0


@pytest.mark.parametrize("step", ["draft", "submit", "submit_existing"])
def test_e6_a_lead_they_created_but_do_not_own_is_a_404(v2, step):
    made = lead_row(v2, customer_id=v2.customer.id, owner=v2.sub_b, created_by=v2.sub_a)
    name = title("CreatedNotOwned")
    if step == "submit_existing":
        pid = _register(v2, v2.sub_a, submit=False, customer_id=v2.customer.id).json()["id"]
        res = submit_existing(v2, v2.sub_a, pid, {"lead_id": made.id})
    else:
        res = _register(
            v2, v2.sub_a, submit=step == "submit", title=name, lead_id=made.id,
            customer_id=v2.customer.id,
        )
    assert res.status_code == 404, res.text
    assert res.json()["code"] == "lead_not_found"
    assert projects_titled(v2, name) == 0


def test_e6_a_missing_lead_gives_the_same_answer(v2):
    res = _register(v2, v2.sub_a, submit=True, lead_id=str(uuid.uuid4()), customer_id=v2.customer.id)
    assert res.status_code == 404, res.text
    assert res.json()["code"] == "lead_not_found"


def test_e6_a_customer_that_differs_from_the_leads_is_refused(v2):
    other = new_customer(v2)
    lead = _own_lead(v2)
    name = title("Mismatch")
    res = _register(v2, v2.sub_a, submit=True, title=name, lead_id=lead.id, customer_id=other.id)
    assert res.status_code == 422, res.text
    assert res.json()["code"] == "project_customer_not_lead_customer"
    assert projects_titled(v2, name) == 0


def test_e6_a_lead_without_a_customer_takes_the_picked_one(v2):
    lead = _own_lead(v2, customer_id=None)
    res = _register(v2, v2.sub_a, submit=True, lead_id=lead.id, customer_id=v2.customer.id)
    assert res.status_code == 201, res.text
    assert profile_of(v2, res.json()["id"]).customer_id == v2.customer.id
    assert reload_lead(v2, lead.id).customer_id == v2.customer.id


def test_e6_a_lead_already_linked_is_409(v2):
    lead = _own_lead(v2)
    first = _register(v2, v2.sub_a, submit=True, lead_id=lead.id, customer_id=v2.customer.id)
    assert first.status_code == 201, first.text
    second = _register(v2, v2.sub_a, submit=True, lead_id=lead.id, customer_id=v2.customer.id)
    assert second.status_code == 409, second.text
    assert second.json()["code"] == "lead_already_linked"


def test_e6_submitting_a_draft_without_a_lead_is_refused(v2):
    draft = _register(v2, v2.sub_a, submit=False, customer_id=v2.customer.id)
    assert draft.status_code == 201, draft.text
    pid = draft.json()["id"]
    res = submit_existing(v2, v2.sub_a, pid)
    assert res.status_code == 422, res.text
    assert res.json()["code"] == "project_lead_required"
    assert project_of(v2, pid).approval_state == "draft"


def test_e6_submitting_a_draft_that_has_a_lead_goes_pending(v2):
    lead = _own_lead(v2)
    pid = _register(v2, v2.sub_a, submit=False, lead_id=lead.id).json()["id"]
    res = submit_existing(v2, v2.sub_a, pid)
    assert res.status_code == 200, res.text
    row = project_of(v2, pid)
    assert row.approval_state == "pending"
    assert row.lead_id == lead.id
    assert profile_of(v2, pid).customer_id == v2.customer.id


def test_e6_the_submit_body_may_carry_the_lead(v2):
    lead = _own_lead(v2)
    pid = _register(v2, v2.sub_a, submit=False, customer_id=v2.customer.id).json()["id"]
    res = submit_existing(v2, v2.sub_a, pid, {"lead_id": lead.id})
    assert res.status_code == 200, res.text
    assert project_of(v2, pid).lead_id == lead.id
    assert project_of(v2, pid).approval_state == "pending"


def test_e6_the_submit_body_naming_someone_elses_lead_is_a_404(v2):
    theirs = _own_lead(v2, user=v2.sub_b)
    pid = _register(v2, v2.sub_a, submit=False, customer_id=v2.customer.id).json()["id"]
    res = submit_existing(v2, v2.sub_a, pid, {"lead_id": theirs.id})
    assert res.status_code == 404, res.text
    assert res.json()["code"] == "lead_not_found"
    assert project_of(v2, pid).approval_state == "draft"


# ------------------------------------------------------------------ security review round (M1, L3, L4, L5)


def _dups(res, lead_id):
    row = next(r for r in res.json()["data"] if r["id"] == lead_id)
    return row["possible_duplicates"]


def test_m1_a_limited_readers_duplicate_hints_name_only_their_own_leads(v2):
    mine = lead_row(v2, customer_id=v2.customer.id, owner=v2.sub_a, name="Setia Alam Phase 9")
    other = lead_row(v2, customer_id=v2.customer.id, owner=v2.sub_b, name="Setia Alam Phase 9")
    res = as_user(v2, v2.sub_a).get(LEADS)
    assert res.status_code == 200, res.text
    assert ids_of(res) == {mine.id}
    hints = _dups(res, mine.id)
    assert all(h["lead_id"] != other.id for h in hints), hints
    assert other.lead_code not in res.text
    assert other.id not in res.text


def test_m1_a_view_holder_still_gets_the_duplicate_hint(v2):
    mine = lead_row(v2, customer_id=v2.customer.id, owner=v2.sub_a, name="Setia Alam Phase 9")
    other = lead_row(v2, customer_id=v2.customer.id, owner=v2.sub_b, name="Setia Alam Phase 9")
    res = as_user(v2, v2.owner).get(LEADS)
    assert res.status_code == 200, res.text
    assert other.id in {h["lead_id"] for h in _dups(res, mine.id)}


def test_e7_a_lead_the_caller_may_not_link_answers_the_same_whatever_the_customer(v2):
    user = active_user(v2.db, "Edit Own Z")
    v2.perms[user] = {VIEW_OWN, EDIT}
    v2.db.commit()
    other_customer = new_customer(v2)
    theirs = lead_row(v2, customer_id=v2.customer.id, owner=v2.sub_b)
    v2.db.commit()
    answers = []
    for customer in (v2.customer.id, other_customer.id, None):
        res = as_user(v2, user).post(
            LIST, json={k: v for k, v in {
                "title": title("E7"), "lead_id": theirs.id, "customer_id": customer,
            }.items() if v is not None},
        )
        answers.append((res.status_code, res.json().get("code")))
    assert answers[0][0] in (403, 404), answers
    assert len(set(answers)) == 1, answers
    assert answers[0][1] != "project_customer_not_lead_customer"


def test_e8_the_409_on_the_submit_only_path_names_no_other_project(v2):
    lead = _own_lead(v2)
    holder_title = title("HoldsTheLead")
    first = as_user(v2, v2.manager).post(
        LIST, json={"title": holder_title, "lead_id": lead.id, "customer_id": v2.customer.id}
    )
    assert first.status_code == 201, first.text
    code = first.json()["project_code"]
    assert code
    res = _register(v2, v2.sub_a, submit=True, lead_id=lead.id, customer_id=v2.customer.id)
    assert res.status_code == 409, res.text
    assert res.json()["code"] == "lead_already_linked"
    assert code not in res.text
    assert holder_title not in res.text


def _staff_project_with_lead(w):
    lead = lead_row(w, customer_id=w.customer.id, owner=w.owner)
    res = as_user(w, w.owner).post(
        LIST, json={"title": title("E9"), "lead_id": lead.id, "customer_id": w.customer.id}
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


def test_e9_a_put_with_another_customer_than_the_leads_is_refused(v2):
    other = new_customer(v2)
    pid = _staff_project_with_lead(v2)
    res = as_user(v2, v2.owner).put(f"{STAFF}/{pid}", json={"customer_id": other.id})
    assert res.status_code == 422, res.text
    assert res.json()["code"] == "project_customer_not_lead_customer"
    assert profile_of(v2, pid).customer_id == v2.customer.id


def test_e9_a_put_with_the_leads_customer_or_none_is_fine(v2):
    pid = _staff_project_with_lead(v2)
    same = as_user(v2, v2.owner).put(f"{STAFF}/{pid}", json={"customer_id": v2.customer.id})
    assert same.status_code == 200, same.text
    none = as_user(v2, v2.owner).put(f"{STAFF}/{pid}", json={"title": title("E9 renamed")})
    assert none.status_code == 200, none.text
    assert profile_of(v2, pid).customer_id == v2.customer.id


def test_e9_a_submit_payload_with_another_customer_than_the_leads_is_refused(v2):
    other = new_customer(v2)
    lead = _own_lead(v2)
    pid = _register(v2, v2.sub_a, submit=False, lead_id=lead.id, customer_id=v2.customer.id).json()["id"]
    res = submit_existing(v2, v2.sub_a, pid, {"customer_id": other.id})
    assert res.status_code == 422, res.text
    assert res.json()["code"] == "project_customer_not_lead_customer"
    assert project_of(v2, pid).approval_state == "draft"
