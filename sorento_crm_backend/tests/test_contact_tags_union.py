"""Lane TAG-UNION: contact tags add up (union merge, live recompute, own changes, inactive tags ignored).

UAC `documentation/plans/contacts/tag-union-08nov-acceptance-criteria.md` (U1-U14), plan
`PLAN-tag-union-08nov.md`. Red tests written before the implementation. Tag settings are seeded with
raw SQL (bypassing validation and gates); membership goes through the HTTP routes, so the live
recompute under test runs. Postgres only, every row seeded here.
"""
from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy import text

from app.models.access import RespondContact, StockVisibilityPolicy
from app.models.company import Company, RespondContactCompany
from app.services.company_scope import DEFAULT_COMPANY_ID

from tests.test_contact_tags_s1 import (  # noqa: F401
    CONTACTS,
    EDIT,
    TAGS,
    VIEW,
    _contact,
    _tag,
    client,
    db,
    perms,
)
from tests._pg_fixture import unique_code

AGENTS_EDIT = "user_management.access_agents.edit"
STOCK_EDIT = "inventory.stock.edit"
OUTBOUND_EDIT = "system.respond_workspaces.edit"
BULK = f"{CONTACTS}/bulk-tags"


@pytest.fixture
def su(perms, monkeypatch):
    """Every right, superadmin included (companies are a superadmin section)."""
    perms["granted"] = {VIEW, EDIT, AGENTS_EDIT, STOCK_EDIT, OUTBOUND_EDIT, "system.ai_assistant_settings.edit"}
    monkeypatch.setattr("app.api.v1.system.companies._is_superadmin", lambda db_, uid: True)
    return perms


@pytest.fixture
def editor(perms, monkeypatch):
    """contacts.edit only: no superadmin, no stock / agents / messaging rights."""
    perms["granted"] = {VIEW, EDIT}
    monkeypatch.setattr("app.api.v1.system.companies._is_superadmin", lambda db_, uid: False)
    return perms


# ---------------------------------------------------------------- seeding


def _stag(client, db, settings: dict, name: str | None = None, active: bool = True) -> dict:
    tag = _tag(client, name)
    db.execute(
        text("UPDATE contact_tags SET settings = CAST(:s AS jsonb), is_active = :a WHERE id = :i"),
        {"s": json.dumps(settings), "a": active, "i": tag["id"]},
    )
    return tag


def _company(db, name="co") -> Company:
    row = Company(name=f"ZZT {name}", code=unique_code("zco")[:50])
    db.add(row)
    db.flush()
    return row


def _put(client, contact, tags):
    return client.put(f"{CONTACTS}/{contact.id}/tags", json={"tag_ids": [t["id"] for t in tags]})


def _tags(client, contact, tags) -> None:
    resp = _put(client, contact, tags)
    assert resp.status_code == 200, resp.text


def _companies(db, contact) -> set[str]:
    db.expire_all()
    return {
        str(c)
        for (c,) in db.query(RespondContactCompany.company_id).filter(
            RespondContactCompany.respond_contact_id == str(contact.id)
        )
    }


def _fresh(db, contact) -> RespondContact:
    db.expire_all()
    return db.query(RespondContact).filter(RespondContact.id == str(contact.id)).one()


def _link_raw(db, contact, tags) -> None:
    """Membership as it exists on prod today: linked, no recompute, snapshot never seeded."""
    for t in tags:
        db.execute(
            text("INSERT INTO respond_contact_tags (contact_id, tag_id) VALUES (:c, :t)"),
            {"c": str(contact.id), "t": t["id"]},
        )
    db.flush()


def _wh(db):
    from app.models.inventory import Warehouse

    code = unique_code("zwh")
    row = Warehouse(warehouse_code=code, warehouse_name=f"ZZT {code}", company_id=DEFAULT_COMPANY_ID)
    db.add(row)
    db.flush()
    return row


# ---------------------------------------------------------------- U1-U6 merge


def test_u1_disjoint_company_tags_add_up_instead_of_wiping(client, db, su):
    sorento, mocha = _company(db, "sorento"), _company(db, "mocha")
    a = _stag(client, db, {"companies": [sorento.id]})
    b = _stag(client, db, {"companies": [mocha.id]})
    c = _contact(db)
    _tags(client, c, [a, b])
    assert _companies(db, c) == {sorento.id, mocha.id}


def test_u1_access_types_and_regions_add_up(client, db, su):
    from tests.test_contact_tags_s2 import _atype

    t1, t2 = _atype(db, "a"), _atype(db, "b")
    a = _stag(client, db, {"access_types": [t1.code], "regions": ["west"]})
    b = _stag(client, db, {"access_types": [t2.code], "regions": ["east"]})
    c = _contact(db)
    _tags(client, c, [a, b])
    codes = {r for (r,) in db.execute(
        text("SELECT access_type_code FROM respond_contact_access_types WHERE contact_id = :c"), {"c": str(c.id)}
    )}
    assert codes == {t1.code, t2.code}
    assert set(_fresh(db, c).regions) == {"west", "east"}


def test_u2_brands_union_and_any_all_gives_all(client, db, su):
    from tests.test_contact_tags_s2 import _brand

    b1, b2 = _brand(db), _brand(db)
    a = _stag(client, db, {"brands": [b1.id]})
    b = _stag(client, db, {"brands": [b2.id]})
    every = _stag(client, db, {"brands": "all"})
    c1, c2 = _contact(db), _contact(db)
    _tags(client, c1, [a, b])
    assert set(_fresh(db, c1).brand_ids) == {b1.id, b2.id}
    _tags(client, c2, [a, every])
    assert not _fresh(db, c2).brand_ids  # NULL = every brand


def test_u3_ai_replies_and_every_switch_add_up(client, db, su):
    a = _stag(client, db, {"chatbot": {"chatbot_allowed": False, "escalation_allowed": False,
                                      "chatbot_files_as_links": False}, "outbound_enabled": False})
    b = _stag(client, db, {"chatbot": {"chatbot_allowed": True, "escalation_allowed": True,
                                      "chatbot_files_as_links": True}, "outbound_enabled": True})
    c = _contact(db)
    _tags(client, c, [a, b])
    row = _fresh(db, c)
    assert row.chatbot_allowed is True
    assert row.escalation_allowed is True
    assert row.chatbot_files_as_links is True
    assert row.outbound_enabled is True


def test_u4_restrictions_need_every_tag(client, db, su):
    w1, w2 = _wh(db), _wh(db)
    a = _stag(client, db, {"requires_registered_project": True,
                           "stock_visibility": {"excluded_warehouse_ids": [w1.id, w2.id], "hide_zero_locations": True}})
    b = _stag(client, db, {"requires_registered_project": False,
                           "stock_visibility": {"excluded_warehouse_ids": [w2.id], "hide_zero_locations": False}})
    c = _contact(db)
    _tags(client, c, [a, b])
    assert _fresh(db, c).requires_registered_project is False
    pol = db.query(StockVisibilityPolicy).filter(StockVisibilityPolicy.contact_id == str(c.id)).one()
    assert set(pol.excluded_warehouse_ids) == {w2.id}
    assert pol.hide_zero_locations is False


def test_u5_include_on_one_tag_and_exclude_on_another_resolves_to_exclude_minus_include(client, db, su):
    w1, w2, w3 = _wh(db), _wh(db), _wh(db)
    a = _stag(client, db, {"stock_visibility": {"warehouse_ids": [w1.id]}})
    b = _stag(client, db, {"stock_visibility": {"excluded_warehouse_ids": [w1.id, w2.id]}})
    c = _contact(db)
    _tags(client, c, [a, b])
    pol = db.query(StockVisibilityPolicy).filter(StockVisibilityPolicy.contact_id == str(c.id)).one()
    assert pol.warehouse_ids is None
    assert set(pol.excluded_warehouse_ids) == {w2.id}
    del w3


def test_u6_memory_highest_and_stock_mode_loosest(client, db, su):
    a = _stag(client, db, {"chatbot": {"memory_level": "conversation"}, "stock_visibility": {"mode": "availability"}})
    b = _stag(client, db, {"chatbot": {"memory_level": "full"}, "stock_visibility": {"mode": "compact"}})
    c = _contact(db)
    _tags(client, c, [a, b])
    assert _fresh(db, c).chatbot_memory_level == "full"
    pol = db.query(StockVisibilityPolicy).filter(StockVisibilityPolicy.contact_id == str(c.id)).one()
    assert pol.mode == "compact"


# ---------------------------------------------------------------- U7 inactive


def test_u7_inactive_tag_counts_for_nothing(client, db, su):
    from app.services.contact_llm_choice import contact_llm_choice

    sorento, mocha = _company(db, "s"), _company(db, "m")
    a = _stag(client, db, {"companies": [sorento.id]})
    off = _stag(client, db, {"companies": [mocha.id], "chatbot": {"llm": {"provider": "openai", "model": "gpt-x"}}},
                active=False)
    c = _contact(db)
    _tags(client, c, [a, off])
    assert _companies(db, c) == {sorento.id}
    assert contact_llm_choice(db, _fresh(db, c)).source == "none"


# ---------------------------------------------------------------- U8 live recompute


def test_u8_removing_a_tag_removes_what_only_it_granted(client, db, su):
    sorento, mocha = _company(db, "s"), _company(db, "m")
    a = _stag(client, db, {"companies": [sorento.id]})
    b = _stag(client, db, {"companies": [mocha.id, sorento.id]})
    c = _contact(db)
    _tags(client, c, [a, b])
    _tags(client, c, [a])
    assert _companies(db, c) == {sorento.id}
    _tags(client, c, [])
    assert _companies(db, c) == set()


def test_u8_editing_a_tag_updates_every_holder(client, db, su):
    sorento, mocha = _company(db, "s"), _company(db, "m")
    a = _stag(client, db, {"companies": [sorento.id]})
    c1, c2 = _contact(db), _contact(db)
    _tags(client, c1, [a])
    _tags(client, c2, [a])
    resp = client.patch(f"{TAGS}/{a['id']}", json={"settings": {"companies": [sorento.id, mocha.id]}})
    assert resp.status_code == 200, resp.text
    assert _companies(db, c1) == {sorento.id, mocha.id}
    assert _companies(db, c2) == {sorento.id, mocha.id}


def test_u8_switching_a_tag_off_and_deleting_it_take_its_grants_away(client, db, su):
    sorento, mocha = _company(db, "s"), _company(db, "m")
    a = _stag(client, db, {"companies": [sorento.id]})
    b = _stag(client, db, {"companies": [mocha.id]})
    c = _contact(db)
    _tags(client, c, [a, b])
    assert client.patch(f"{TAGS}/{b['id']}", json={"is_active": False}).status_code == 200
    assert _companies(db, c) == {sorento.id}
    assert client.patch(f"{TAGS}/{b['id']}", json={"is_active": True}).status_code == 200
    assert _companies(db, c) == {sorento.id, mocha.id}
    assert client.delete(f"{TAGS}/{b['id']}").status_code == 204
    assert _companies(db, c) == {sorento.id}


def test_u8_bulk_remove_recomputes(client, db, su):
    sorento, mocha = _company(db, "s"), _company(db, "m")
    a = _stag(client, db, {"companies": [sorento.id]})
    b = _stag(client, db, {"companies": [mocha.id]})
    c = _contact(db)
    _tags(client, c, [a, b])
    resp = client.post(BULK, json={"contact_ids": [str(c.id)], "add_tag_ids": [], "remove_tag_ids": [b["id"]],
                                   "dry_run": False})
    assert resp.status_code == 200, resp.text
    assert _companies(db, c) == {sorento.id}


def test_u8_bulk_preview_writes_nothing(client, db, su):
    sorento = _company(db, "s")
    a = _stag(client, db, {"companies": [sorento.id]})
    c = _contact(db)
    resp = client.post(BULK, json={"contact_ids": [str(c.id)], "add_tag_ids": [a["id"]], "remove_tag_ids": [],
                                   "dry_run": True})
    assert resp.status_code == 200, resp.text
    assert _companies(db, c) == set()


# ---------------------------------------------------------------- U9-U10 own changes


def test_u9_company_added_by_hand_survives_tag_removal(client, db, su):
    sorento, mocha = _company(db, "s"), _company(db, "m")
    a = _stag(client, db, {"companies": [sorento.id]})
    c = _contact(db)
    _tags(client, c, [a])
    assert _companies(db, c) == {sorento.id}
    db.add(RespondContactCompany(respond_contact_id=str(c.id), company_id=mocha.id))
    db.flush()
    _tags(client, c, [])
    assert _companies(db, c) == {mocha.id}


def test_u9_company_held_before_the_tag_stays_under_it(client, db, su):
    sorento, mocha = _company(db, "s"), _company(db, "m")
    c = _contact(db)
    db.add(RespondContactCompany(respond_contact_id=str(c.id), company_id=mocha.id))
    db.flush()
    a = _stag(client, db, {"companies": [sorento.id]})
    _tags(client, c, [a])
    assert _companies(db, c) == {sorento.id, mocha.id}
    _tags(client, c, [])
    assert _companies(db, c) == {mocha.id}


def test_u9_company_removed_by_hand_stays_removed_when_the_tag_changes(client, db, su):
    s, m, x = _company(db, "s"), _company(db, "m"), _company(db, "x")
    a = _stag(client, db, {"companies": [s.id, m.id]})
    c = _contact(db)
    _tags(client, c, [a])
    db.query(RespondContactCompany).filter(
        RespondContactCompany.respond_contact_id == str(c.id), RespondContactCompany.company_id == m.id
    ).delete()
    db.flush()
    assert client.patch(f"{TAGS}/{a['id']}", json={"settings": {"companies": [s.id, m.id, x.id]}}).status_code == 200
    assert _companies(db, c) == {s.id, x.id}


def test_u9_switch_changed_by_hand_keeps_its_value(client, db, su):
    a = _stag(client, db, {"chatbot": {"chatbot_stock_allowed": True}})
    c = _contact(db)
    c.chatbot_stock_allowed = False
    c.escalation_allowed = False
    db.flush()
    _tags(client, c, [a])
    assert _fresh(db, c).chatbot_stock_allowed is True
    row = _fresh(db, c)
    row.chatbot_stock_allowed = False
    db.flush()
    resp = client.patch(f"{TAGS}/{a['id']}", json={"settings": {"chatbot": {"chatbot_stock_allowed": True,
                                                                             "escalation_allowed": True}}})
    assert resp.status_code == 200, resp.text
    assert _fresh(db, c).chatbot_stock_allowed is False
    assert _fresh(db, c).escalation_allowed is True


def test_u10_untouched_switch_goes_back_to_its_value_before_the_tag(client, db, su):
    c = _contact(db)
    c.chatbot_stock_allowed = False
    db.flush()
    a = _stag(client, db, {"chatbot": {"chatbot_stock_allowed": True}})
    _tags(client, c, [a])
    assert _fresh(db, c).chatbot_stock_allowed is True
    _tags(client, c, [])
    assert _fresh(db, c).chatbot_stock_allowed is False


# ---------------------------------------------------------------- U11 existing contacts (seeding)


def test_u11_value_differing_from_todays_tag_result_is_kept_as_own(client, db, su):
    from app.services import contact_tag_union

    s, m = _company(db, "s"), _company(db, "m")
    a = _stag(client, db, {"companies": [s.id]})
    c = _contact(db)
    _link_raw(db, c, [a])
    db.add(RespondContactCompany(respond_contact_id=str(c.id), company_id=m.id))  # set by hand, never applied
    db.flush()
    dry = contact_tag_union.run(db, apply=False, expect=None, contact_ids=[str(c.id)])
    report = contact_tag_union.run(db, apply=True, expect=dry["changed"], contact_ids=[str(c.id)])
    assert _companies(db, c) == {m.id}
    assert report["own_changes"] == 1
    with pytest.raises(ValueError):
        contact_tag_union.run(db, apply=True, expect=None, contact_ids=[str(c.id)])


def test_u11_empty_companies_bug_is_repaired_by_the_recompute(client, db, su):
    from app.services import contact_tag_union

    s, m = _company(db, "s"), _company(db, "m")
    a = _stag(client, db, {"companies": [s.id]})
    b = _stag(client, db, {"companies": [m.id]})
    c = _contact(db)
    _link_raw(db, c, [a, b])  # old apply wrote the empty intersection: no company rows
    dry = contact_tag_union.run(db, apply=False, expect=None, contact_ids=[str(c.id)])
    assert dry["empty_companies_today"] == 1
    assert dry["changed"] == 1
    assert _companies(db, c) == set()  # dry run writes nothing
    contact_tag_union.run(db, apply=True, expect=1, contact_ids=[str(c.id)])
    assert _companies(db, c) == {s.id, m.id}


def test_u14_apply_refuses_when_expect_does_not_match(client, db, su):
    from app.services import contact_tag_union

    s, m = _company(db, "s"), _company(db, "m")
    a = _stag(client, db, {"companies": [s.id]})
    b = _stag(client, db, {"companies": [m.id]})
    c = _contact(db)
    _link_raw(db, c, [a, b])
    with pytest.raises(ValueError):
        contact_tag_union.run(db, apply=True, expect=5, contact_ids=[str(c.id)])
    assert _companies(db, c) == set()


def test_u14_apply_writes_one_audit_row_per_changed_contact(client, db, su):
    from app.services import contact_tag_union

    s, m = _company(db, "s"), _company(db, "m")
    a = _stag(client, db, {"companies": [s.id]})
    b = _stag(client, db, {"companies": [m.id]})
    c = _contact(db)
    _link_raw(db, c, [a, b])
    contact_tag_union.run(db, apply=True, expect=1, contact_ids=[str(c.id)])
    n = db.execute(
        text("SELECT count(*) FROM audit_logs WHERE entity_id = :c AND description ILIKE '%tag union recompute%'"),
        {"c": str(c.id)},
    ).scalar()
    assert n == 1


# ---------------------------------------------------------------- U12 Apply settings = reset to tags


def test_u12_apply_settings_resets_own_changes(client, db, su):
    s, m = _company(db, "s"), _company(db, "m")
    a = _stag(client, db, {"companies": [s.id]})
    c = _contact(db)
    _tags(client, c, [a])
    db.add(RespondContactCompany(respond_contact_id=str(c.id), company_id=m.id))
    db.flush()
    body = client.get(f"{CONTACTS}/{c.id}/tag-settings").json()
    assert body["status"] == "differs"
    resp = client.post(f"{CONTACTS}/bulk-apply-tag-settings", json={"contact_ids": [str(c.id)], "dry_run": False})
    assert resp.status_code == 200, resp.text
    assert _companies(db, c) == {s.id}
    _tags(client, c, [])  # the reset value is the tags' value now: removing the tag takes it away
    assert _companies(db, c) == set()


# ---------------------------------------------------------------- U13 gates


def test_u13_adding_or_removing_a_companies_tag_needs_superadmin(client, db, su, editor):
    s = _company(db, "s")
    a = _stag(client, db, {"companies": [s.id]})
    c = _contact(db)
    resp = _put(client, c, [a])
    assert resp.status_code == 403, resp.text
    assert _companies(db, c) == set()
    resp = client.post(BULK, json={"contact_ids": [str(c.id)], "add_tag_ids": [a["id"]], "remove_tag_ids": [],
                                   "dry_run": False})
    assert resp.status_code == 403, resp.text
    _link_raw(db, c, [a])
    assert _put(client, c, []).status_code == 403


def test_u13_switching_a_gated_tag_off_needs_the_gate(client, db, su, editor):
    s = _company(db, "s")
    a = _stag(client, db, {"companies": [s.id]})
    assert client.patch(f"{TAGS}/{a['id']}", json={"is_active": False}).status_code == 403


def test_u13_ungated_tag_is_fine_for_a_contacts_editor(client, db, editor):
    a = _stag(client, db, {"chatbot": {"chatbot_stock_allowed": True}})
    c = _contact(db)
    c.chatbot_stock_allowed = False
    db.flush()
    _tags(client, c, [a])
    assert _fresh(db, c).chatbot_stock_allowed is True


def test_u13_stock_tag_needs_stock_edit(client, db, perms, monkeypatch):
    perms["granted"] = {VIEW, EDIT}
    monkeypatch.setattr("app.api.v1.system.companies._is_superadmin", lambda db_, uid: False)
    a = _stag(client, db, {"stock_visibility": {"mode": "compact"}})
    c = _contact(db)
    assert _put(client, c, [a]).status_code == 403
    perms["granted"] = {VIEW, EDIT, STOCK_EDIT}
    assert _put(client, c, [a]).status_code == 200


# ---------------------------------------------------------------- the owner's hand test, end to end


def test_handtest_sequence(client, db, su):
    """The steps of `tag-union-08nov-handtest.md`, so the values it promises are the values the code gives."""
    s, m = _company(db, "sorento"), _company(db, "mocha")
    ts = _stag(client, db, {"companies": [s.id], "chatbot": {"chatbot_allowed": False}}, "ZZT TU Sorento")
    tm = _stag(client, db, {"companies": [m.id], "chatbot": {"chatbot_allowed": True}}, "ZZT TU Mocha")
    c = _contact(db)
    _tags(client, c, [ts])
    assert _companies(db, c) == {s.id}
    _tags(client, c, [ts, tm])
    assert _companies(db, c) == {s.id, m.id} and _fresh(db, c).chatbot_allowed is True
    _tags(client, c, [ts])
    assert _companies(db, c) == {s.id} and _fresh(db, c).chatbot_allowed is False
    db.add(RespondContactCompany(respond_contact_id=str(c.id), company_id=m.id))
    db.flush()
    _tags(client, c, [])
    assert _companies(db, c) == {m.id}
    _tags(client, c, [ts])
    assert client.patch(f"{TAGS}/{ts['id']}", json={"is_active": False}).status_code == 200
    assert _companies(db, c) == {m.id}
    assert client.patch(f"{TAGS}/{ts['id']}", json={"is_active": True}).status_code == 200
    assert _companies(db, c) == {s.id, m.id}
    db.query(RespondContactCompany).filter(
        RespondContactCompany.respond_contact_id == str(c.id), RespondContactCompany.company_id == s.id
    ).delete()
    db.flush()
    body = client.get(f"{CONTACTS}/{c.id}/tag-settings").json()
    assert [i["section"] for i in body["items"] if i["differs"]] == ["companies"]
    resp = client.post(f"{CONTACTS}/bulk-apply-tag-settings", json={"contact_ids": [str(c.id)], "dry_run": False})
    assert resp.status_code == 200, resp.text
    assert _companies(db, c) == {s.id, m.id}
    assert client.get(f"{CONTACTS}/{c.id}/tag-settings").json()["status"] == "matches"


# ---------------------------------------------------------------- security review fixes


def test_sec_b1_own_removal_never_writes_an_empty_brand_list(client, db, su):
    """An empty brand list means EVERY brand: the recompute must never write one (fail closed)."""
    from tests.test_contact_tags_s2 import _brand

    b1, b2 = _brand(db), _brand(db)
    t1 = _stag(client, db, {"brands": [b1.id]})
    t2 = _stag(client, db, {"brands": [b2.id]})
    c = _contact(db)
    _tags(client, c, [t1, t2])
    row = _fresh(db, c)
    row.brand_ids = [b2.id]  # a person takes brand 1 away by hand
    db.flush()
    _tags(client, c, [t1])  # tags {b1} + own removal of b1 would be empty
    assert _fresh(db, c).brand_ids == [b2.id]


def test_sec_b1_an_empty_brand_list_on_a_tag_is_refused(client, db, su):
    tag = _tag(client)
    resp = client.patch(f"{TAGS}/{tag['id']}", json={"settings": {"brands": []}})
    assert resp.status_code == 422, resp.text


def test_sec_s1_inactive_tag_added_by_an_editor_writes_no_companies(client, db, su, editor):
    s, m = _company(db, "s"), _company(db, "m")
    a = _stag(client, db, {"companies": [s.id]})
    b = _stag(client, db, {"companies": [m.id]})
    off = _stag(client, db, {"companies": [s.id], "chatbot": {"chatbot_stock_allowed": True}}, active=False)
    c = _contact(db)
    _link_raw(db, c, [a, b])  # a prod contact the old rule left with no company
    assert _put(client, c, [a, b, off]).status_code == 200
    assert _companies(db, c) == set()


def test_sec_s1_editing_an_ungated_section_does_not_recompute_gated_ones(client, db, su, editor):
    s, m = _company(db, "s"), _company(db, "m")
    a = _stag(client, db, {"companies": [s.id], "chatbot": {"chatbot_stock_allowed": True}})
    b = _stag(client, db, {"companies": [m.id]})
    c = _contact(db)
    _link_raw(db, c, [a, b])
    resp = client.patch(f"{TAGS}/{a['id']}", json={"settings": {"companies": [s.id],
                                                                "chatbot": {"chatbot_stock_allowed": False}}})
    assert resp.status_code == 200, resp.text
    assert _companies(db, c) == set()  # companies untouched until a superadmin change or the script


def test_sec_s2_tag_delete_audit_names_the_actor(client, db, su):
    s = _company(db, "s")
    a = _stag(client, db, {"companies": [s.id]})
    c = _contact(db)
    _tags(client, c, [a])
    assert client.delete(f"{TAGS}/{a['id']}").status_code == 204
    actor = db.execute(
        text("SELECT user_id FROM audit_logs WHERE entity_id = :c AND description LIKE 'Tag deleted:%'"),
        {"c": str(c.id)},
    ).scalar()
    assert actor is not None


def test_sec_n1_adding_a_tag_that_sets_the_ai_model_needs_the_ai_settings_right(client, db, editor):
    a = _stag(client, db, {"chatbot": {"llm": {"provider": "openai", "model": "gpt-x"}}})
    c = _contact(db)
    assert _put(client, c, [a]).status_code == 403
