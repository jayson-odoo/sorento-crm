"""PROJECT-REG-PORTAL portal surface, red-first (UAC A1-A13, F1).

The kind joins the generic `/submissions/{kind}` routes (PLAN D1), so everything goes
through the TestClient: mounting and the kind gate are part of the contract.
Nothing exists yet: expected red reasons are a missing model/module, `Unsupported
submission type` (400), or a kind absent from a constant.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.main import app  # noqa: F401  MUST be first app import (circular import)

from ._project_registration_support import (
    FIELD_KEYS,
    KIND,
    SUB,
    PORTAL,
    agent,
    as_contact,
    contact,
    create_draft,
    field_values,
    fields,
    pending,
    project,
    registration,
    submit,
    uid,
    world,  # noqa: F401  (fixture)
)

# ------------------------------------------------------------------ A1, A2 access


def test_a1_no_grant_is_403_form_type_not_visible_and_not_in_visible_kinds(world):
    from app.services.portal_form_visibility_service import resolve_visible_form_types

    res = as_contact(world, world.ungranted).get(f"{PORTAL}/submissions", params={"type": KIND})
    assert res.status_code == 403, res.text
    assert res.json().get("code") == "FORM_TYPE_NOT_VISIBLE"
    assert KIND not in resolve_visible_form_types(world.db, world.ungranted)
    assert KIND in resolve_visible_form_types(world.db, world.a)


def test_a1_a_segment_grant_makes_it_visible(world):
    from app.services.portal_form_visibility_service import resolve_visible_form_types

    from ._portal_grant import link_contact_segment, seed_segment

    assert KIND not in resolve_visible_form_types(world.db, world.ungranted)
    segment = seed_segment(world.db, kinds=[KIND])
    link_contact_segment(world.db, world.ungranted, segment.code)
    assert KIND in resolve_visible_form_types(world.db, world.ungranted)
    res = as_contact(world, world.ungranted).get(f"{PORTAL}/submissions", params={"type": KIND})
    assert res.status_code == 200, res.text


def test_a1_every_route_is_gated_for_an_ungranted_contact(world):
    c = as_contact(world, world.ungranted)
    some = uid()
    calls = [
        c.get(f"{SUB}/{some}"),
        c.post(SUB, json={"fields": {}}),
        c.put(f"{SUB}/{some}", json={"fields": {}}),
        c.post(f"{SUB}/{some}/submit"),
        c.delete(f"{SUB}/{some}"),
    ]
    for res in calls:
        assert res.status_code == 403, (res.request.url, res.status_code, res.text)
        assert res.json().get("code") == "FORM_TYPE_NOT_VISIBLE"


def test_a2_grantable_not_default_and_labelled():
    from app.services import portal_form_visibility_service as vis
    from app.services.portal_service import GRANTABLE_PORTAL_FORM_TYPES, SUPPORTED_TYPES

    assert KIND in GRANTABLE_PORTAL_FORM_TYPES
    assert KIND not in SUPPORTED_TYPES
    assert vis._KIND_LABELS[KIND] == "Project Registration"


def test_a2_generic_tuple_adds_the_kind_to_the_base():
    from app.services.portal_service import GENERIC_SUBMISSION_TYPES, SUPPORTED_TYPES

    assert GENERIC_SUBMISSION_TYPES == SUPPORTED_TYPES + (KIND,)


def test_a2_the_kind_has_no_revision_settings_row():
    from app.api.v1.forms.revision_configs import REVISABLE_PORTAL_FORM_TYPES

    assert KIND not in REVISABLE_PORTAL_FORM_TYPES


# ------------------------------------------------------------------ A3 sales agent


def test_a3_granted_contact_without_an_active_agent_cannot_create(world):
    res = as_contact(world, world.noagent).post(SUB, json={"fields": fields()})
    assert res.status_code == 403, res.text
    assert res.json().get("code") == "NOT_A_SALES_AGENT"


def test_a3_an_inactive_agent_does_not_count(world):
    inactive = contact(world.db, world.company_id)
    agent(world.db, inactive, active=False)
    res = as_contact(world, inactive).post(SUB, json={"fields": fields()})
    assert res.status_code == 403, res.text
    assert res.json().get("code") == "NOT_A_SALES_AGENT"


def test_a3_a_contact_without_an_agent_cannot_submit_either(world):
    """An agent link removed after the draft was made: submit fails with the same code."""
    d = create_draft(world)
    world.agent_a.is_active = False
    world.db.flush()
    res = submit(world, d["id"])
    assert res.status_code == 403, res.text
    assert res.json().get("code") == "NOT_A_SALES_AGENT"


# ------------------------------------------------------------------ A4 create


def test_a4_create_a_draft_shows_the_agents_name_not_the_code(world):
    d = create_draft(world)
    assert d["status"] == "draft"
    assert d["is_draft"] is True
    assert d["reference"] is None
    assert d["sales_agent_name"] == "Aminah Example"
    assert world.agent_a.sales_agent not in d["sales_agent_name"]
    got = as_contact(world, world.a).get(f"{SUB}/{d['id']}").json()
    assert field_values(got)["title"].startswith("CADANGAN BLOK PEJABAT")


def test_a4_sales_agent_name_falls_back_to_description_then_the_code(world):
    only_description = contact(world.db, world.company_id)
    agent(world.db, only_description, person_label=None, description="Cahaya desk")
    bare = contact(world.db, world.company_id)
    bare_agent = agent(world.db, bare, person_label=None, description=None, code="ZZP-BARE1")
    assert create_draft(world, only_description)["sales_agent_name"] == "Cahaya desk"
    assert create_draft(world, bare)["sales_agent_name"] == bare_agent.sales_agent


def test_a4_with_two_agents_the_first_by_code_is_used(world):
    both = contact(world.db, world.company_id)
    agent(world.db, both, code="ZZP-B2", person_label="Second Example")
    agent(world.db, both, code="ZZP-A1", person_label="First Example")
    assert create_draft(world, both)["sales_agent_name"] == "First Example"


# ------------------------------------------------------------------ A5 stored fields


def test_a5_unknown_keys_are_ignored_and_the_stored_fields_are_exactly_the_eleven(world):
    body = fields(
        world.debtor_a.id,
        bogus="x",
        status="approved",
        company_id=world.other_company,
        project_id=uid(),
        reject_reason="nope",
    )
    res = as_contact(world, world.a).post(SUB, json={"fields": body})
    assert res.status_code == 200, res.text
    d = res.json()
    assert d["status"] == "draft"
    got = as_contact(world, world.a).get(f"{SUB}/{d['id']}").json()
    values = field_values(got)
    assert FIELD_KEYS <= set(values)
    if "fields" in got:
        assert set(got["fields"]) == FIELD_KEYS
    assert "bogus" not in values and "bogus" not in got
    assert values["developer_name"] == "Example Developer Sdn Bhd"
    assert values["customer_id"] == world.debtor_a.id
    row = registration(world, d["id"])
    assert row.status == "draft"
    assert str(row.company_id) == str(world.company_id)
    assert row.project_id is None
    assert row.reject_reason is None


def test_a5_the_pick_and_the_typed_values_round_trip(world):
    d = create_draft(
        world, distributor_name="Typed Distributor", your_ref="REF-9", customer_name="Typed Customer"
    )
    got = field_values(as_contact(world, world.a).get(f"{SUB}/{d['id']}").json())
    assert got["distributor_name"] == "Typed Distributor"
    assert got["your_ref"] == "REF-9"
    assert got["customer_name"] == "Typed Customer"


def test_a5_update_a_draft(world):
    d = create_draft(world)
    res = as_contact(world, world.a).put(
        f"{SUB}/{d['id']}", json={"fields": fields(world.debtor_a.id, mukim="Senai")}
    )
    assert res.status_code == 200, res.text
    got = as_contact(world, world.a).get(f"{SUB}/{d['id']}").json()
    assert field_values(got)["mukim"] == "Senai"


# ------------------------------------------------------------------ A6 debtor pick


def test_a6_customer_must_be_one_of_the_agents_own_debtors(world):
    c = as_contact(world, world.a)
    for bad in (world.debtor_b.id, uid()):
        res = c.post(SUB, json={"fields": fields(bad)})
        assert res.status_code == 422, (bad, res.status_code, res.text)
    ok = c.post(SUB, json={"fields": fields(world.debtor_a.id)})
    assert ok.status_code == 200, ok.text


def test_a6_the_check_also_applies_on_update(world):
    d = create_draft(world)
    res = as_contact(world, world.a).put(
        f"{SUB}/{d['id']}", json={"fields": fields(world.debtor_b.id)}
    )
    assert res.status_code == 422, res.text


# ------------------------------------------------------------------ A7 ownership


def test_a7_another_contacts_registration_is_404_everywhere(world):
    d = create_draft(world)
    c = as_contact(world, world.b)
    assert c.get(f"{SUB}/{d['id']}").status_code == 404
    assert c.put(f"{SUB}/{d['id']}", json={"fields": fields()}).status_code == 404
    assert c.post(f"{SUB}/{d['id']}/submit").status_code == 404
    assert c.delete(f"{SUB}/{d['id']}").status_code == 404
    assert registration(world, d["id"]).status == "draft"


# ------------------------------------------------------------------ A8 / A9 submit


def test_a8_submit_lists_the_missing_fields_and_changes_nothing(world):
    d = create_draft(world)
    res = as_contact(world, world.a).put(
        f"{SUB}/{d['id']}", json={"fields": fields(world.debtor_a.id, title="", state=" ", developer_name="")}
    )
    assert res.status_code == 200, res.text
    res = submit(world, d["id"])
    assert res.status_code == 422, res.text
    missing = {x.strip() for x in str(res.json()["detail"]).split(",")}
    assert missing == {"title", "state", "developer_name"}
    row = registration(world, d["id"])
    assert row.status == "draft"
    assert row.submitted_at is None


def test_a8_only_the_blank_one_is_named(world):
    d = create_draft(world, state="")
    res = submit(world, d["id"])
    assert res.status_code == 422, res.text
    assert {x.strip() for x in str(res.json()["detail"]).split(",")} == {"state"}


def test_a8_submit_can_carry_the_fields(world):
    d = create_draft(world, developer_name="")
    res = submit(world, d["id"], body=fields(world.debtor_a.id, developer_name="Late Developer Sdn Bhd"))
    assert res.status_code == 200, res.text
    assert registration(world, d["id"]).developer_name == "Late Developer Sdn Bhd"


def test_a9_submit_a_complete_draft_locks_it(world):
    d = create_draft(world)
    res = submit(world, d["id"])
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "pending"
    assert body["is_draft"] is False
    row = registration(world, d["id"])
    assert row.status == "pending"
    assert row.submitted_at is not None
    assert row.applicant_user_id == world.applicant_user
    locked = as_contact(world, world.a).put(f"{SUB}/{d['id']}", json={"fields": fields(world.debtor_a.id)})
    assert locked.status_code == 422, locked.text


# ------------------------------------------------------------------ A10 delete


def test_a10_delete_a_draft_but_not_a_pending_one(world):
    from app.models.project_registration import ProjectRegistration

    draft = create_draft(world)
    res = as_contact(world, world.a).delete(f"{SUB}/{draft['id']}")
    assert res.status_code == 204, res.text
    world.db.expire_all()
    assert world.db.get(ProjectRegistration, draft["id"]) is None

    rid = pending(world)
    res = as_contact(world, world.a).delete(f"{SUB}/{rid}")
    assert res.status_code == 422, res.text
    assert registration(world, rid).status == "pending"


# ------------------------------------------------------------------ A11 list


def test_a11_list_is_mine_only_newest_first_with_status_and_ppf_no(world):
    first = create_draft(world, title="ALPHA SENTINEL TOWER", developer_name="Zeta Holdings")
    second = create_draft(world, title="BETA SENTINEL TOWER", developer_name="Eta Holdings")
    theirs = create_draft(world, world.b, title="GAMMA SENTINEL TOWER")
    for rid, age in ((first["id"], 3), (second["id"], 1)):
        registration(world, rid).created_at = datetime.utcnow() - timedelta(days=age)
        world.db.flush()

    res = as_contact(world, world.a).get(f"{PORTAL}/submissions", params={"type": KIND})
    assert res.status_code == 200, res.text
    items = res.json()["items"]
    ids = [r["id"] for r in items]
    assert theirs["id"] not in ids
    assert ids == [second["id"], first["id"]]
    assert {r["status"] for r in items} == {"draft"}
    assert all(r["title"] and "developer_name" in r for r in items)
    assert all(r.get("ppf_no") in (None, "") for r in items)


def test_a11_q_matches_title_and_developer_name(world):
    by_title = create_draft(world, title="UNIQUE ORCHID PLAZA", developer_name="Plain One")
    by_dev = create_draft(world, title="PLAIN TWO", developer_name="Lotus Corp")
    c = as_contact(world, world.a)

    def ids(q):
        return {r["id"] for r in c.get(f"{PORTAL}/submissions", params={"type": KIND, "q": q}).json()["items"]}

    assert ids("orchid") == {by_title["id"]}
    assert ids("lotus") == {by_dev["id"]}


def test_a11_an_approved_row_carries_its_ppf_no(world):
    rid = pending(world)
    row = registration(world, rid)
    made = project(world.db, world.company_id, "APPROVED SENTINEL", code="PPF2601001")
    row.status = "approved"
    row.project_id = made.id
    world.db.flush()
    items = as_contact(world, world.a).get(f"{PORTAL}/submissions", params={"type": KIND}).json()["items"]
    mine = next(r for r in items if r["id"] == rid)
    assert mine["status"] == "approved"
    assert mine["ppf_no"] == "PPF2601001"
    detail = as_contact(world, world.a).get(f"{SUB}/{rid}").json()
    assert detail["reference"] == "PPF2601001"
    assert detail["is_draft"] is False


# ------------------------------------------------------------------ A12 duplicates


def test_a12_detail_names_a_project_on_the_same_lot_and_mukim_without_ids(world):
    existing = project(
        world.db, world.company_id, "KILANG ALPHA LOT 9001 MUKIM TEBRAU", code="PRJ-ZZT-9001"
    )
    rid = pending(
        world,
        title="CADANGAN PEMBINAAN GUDANG DI ATAS LOT 9001, MUKIM TEBRAU, JOHOR",
        mukim="Tebrau",
    )
    got = as_contact(world, world.a).get(f"{SUB}/{rid}").json()
    assert got["possible_duplicates"] == [{"project_code": existing.project_code, "title": existing.title}]
    assert existing.id not in str(got)


def test_a12_nothing_similar_means_an_empty_list(world):
    rid = pending(world)
    got = as_contact(world, world.a).get(f"{SUB}/{rid}").json()
    assert got["possible_duplicates"] == []


# ------------------------------------------------------------------ A13 AI extract


def test_a13_form_schema_lists_the_fields_minus_customer_id():
    from app.services.ai_extract.form_schema_registry import FORM_SCHEMAS

    schema = FORM_SCHEMAS["portal.project_registration"]
    assert {spec.name for spec in schema} == FIELD_KEYS - {"customer_id"}


def test_a13_ai_extract_is_refused_without_the_grant(world):
    png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0"
        b"\x00\x00\x03\x01\x01\x00\xc9\xfe\x92\xef\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    c = as_contact(world, world.ungranted)
    res = c.post(
        f"{PORTAL}/ai-extract",
        data={"form_key": "portal.project_registration"},
        files=[("files", ("zzt.png", png, "image/png"))],
    )
    assert res.status_code == 403, res.text
    assert res.json().get("code") == "FORM_TYPE_NOT_VISIBLE"
    schema = c.get(f"{PORTAL}/ai-extract/schema", params={"form_key": "portal.project_registration"})
    assert schema.status_code == 403, schema.text
    # Pair: the same key is served to a contact WITH the grant, so the 403 above is the gate
    # and not merely an unknown key.
    granted = as_contact(world, world.a).get(
        f"{PORTAL}/ai-extract/schema", params={"form_key": "portal.project_registration"}
    )
    assert granted.status_code == 200, granted.text


def test_a13_the_schema_is_served_to_a_granted_contact(world):
    res = as_contact(world, world.a).get(
        f"{PORTAL}/ai-extract/schema", params={"form_key": "portal.project_registration"}
    )
    assert res.status_code == 200, res.text


# ------------------------------------------------------------------ F1 notification


def test_f1_submit_notifies_every_approve_holder_except_the_applicant(world):
    pending(world)
    recipients = {user for user, _type in world.sent}
    assert recipients == {world.approver}
    assert world.applicant_user not in recipients


def test_f1_creating_or_saving_a_draft_notifies_nobody(world):
    d = create_draft(world)
    as_contact(world, world.a).put(f"{SUB}/{d['id']}", json={"fields": fields(world.debtor_a.id)})
    assert world.sent == []


# ------------------------------------------------------------------ the form's two lookup sets


@pytest.mark.parametrize("set_key", ["project_building_type", "my_state"])
def test_the_portal_may_read_the_two_lookup_sets_the_form_uses(world, set_key):
    """The form's State and Type of building are `lookup-select` widgets that read
    `/lookups/sets/{key}`, which is whitelisted per key. The migration seeds the sets; the
    whitelist must name them or the dropdowns are empty with a 403 behind them."""
    from app.models.lookup import LookupOption, LookupSet

    row = LookupSet(id=uid(), set_key=set_key, name=f"zzt {set_key}")
    world.db.add(row)
    world.db.flush()
    world.db.add(LookupOption(id=uid(), set_id=row.id, value="Johor", label="Johor", sort_order=1))
    world.db.flush()

    res = as_contact(world, world.a).get(f"{PORTAL}/lookups/sets/{set_key}")
    assert res.status_code == 200, res.text
    assert [o["value"] for o in res.json()["options"]] == ["Johor"]
