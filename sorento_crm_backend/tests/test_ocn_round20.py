"""OCN-ORDER-CHANGE-NOTICE round 20 (owner hand-test, 13 Nov), red-first. UAC section I.

- I1-I3: `order_change_notice` is ONE opt-in portal form kind (registry, resolver, the contact's
  Portal forms card, the tag catalog, the market segment editor).
- I7-I10: one "Requested by" field (contact) replaces Sales Person / Sales Incharge on the API:
  eligibility, defaults, own-records, history, sort key.

The portal routes live in tests/test_ocn_round20_portal.py. Postgres only, every row seeded,
fake values only.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from ._forms_chain_support import SORENTO, contact, user, world  # noqa: F401
from ._ocn_support import (  # noqa: F401  (fixtures)
    KIND,
    OCN,
    create,
    ocn,
    payload,
    rows_of,
)

REQUESTOR = "ZZT Requestor"


# ------------------------------------------------------------------ helpers


def _body(o, **over) -> dict:
    """A draft payload with the retired salesperson field gone."""
    body = payload(o)
    body.pop("sales_in_charge_user_id", None)
    body.update(over)
    return body


def _segment(db, code="zzt-ocn-req"):
    from app.models.access import MarketSegment

    row = db.query(MarketSegment).filter(MarketSegment.code == code).first()
    if row is None:
        db.add(MarketSegment(code=code, name=f"ZZT {code}", is_active=True, is_requestor_selectable=True))
        db.flush()
    return code


def _eligible(db, name: str) -> str:
    """A contact inside an active, requestor-selectable market segment."""
    from ._portal_grant import link_contact_segment

    cid = contact(db, name=name)
    link_contact_segment(db, cid, _segment(db))
    db.commit()
    return cid


def _ineligible(db, name: str) -> str:
    cid = contact(db, name=name)
    db.commit()
    return cid


def _contact_name(db, contact_id: str) -> str:
    from app.models.access import RespondContact

    db.expire_all()
    return db.get(RespondContact, contact_id).name


def _link(db, user_id: str, contact_id: str) -> None:
    from app.models.user import User

    db.get(User, user_id).respond_contact_id = contact_id
    db.commit()


def _post(o, body, user_id=None):
    return o.as_(user_id or o.raiser).post(OCN, json=body)


# ================================================================== I1 / I2 registry and resolver


def test_i1_order_change_notice_is_grantable_not_default():
    """I1/I2: in GRANTABLE_PORTAL_FORM_TYPES, NOT in SUPPORTED_TYPES."""
    from app.services.portal_service import GRANTABLE_PORTAL_FORM_TYPES, SUPPORTED_TYPES

    assert "order_change_notice" in GRANTABLE_PORTAL_FORM_TYPES
    assert "order_change_notice" not in SUPPORTED_TYPES


def test_i1_kind_label_is_order_change_notice():
    """I1/I3: the visibility service labels the kind."""
    from app.services import portal_form_visibility_service as visibility

    assert visibility._KIND_LABELS["order_change_notice"] == "Order Change Notice"


def test_i2_a_plain_contact_does_not_see_it():
    """I2: no tag, segment or switch -> not offered (opt-in, unlike the base four)."""
    from app.services.portal_form_visibility_service import resolve_visible_form_types

    from ._pg_fixture import blank_session

    with blank_session() as db:
        cid = contact(db)
        db.commit()
        visible = resolve_visible_form_types(db, cid)
        assert "complaint" in visible  # the base still shows, so an empty list is not the reason
        assert "order_change_notice" not in visible


def test_i2_the_contacts_own_switch_turns_it_on():
    from app.services.portal_form_visibility_service import resolve_visible_form_types

    from ._pg_fixture import blank_session
    from ._portal_grant import grant_portal_forms

    with blank_session() as db:
        cid = contact(db)
        grant_portal_forms(db, cid, ["order_change_notice"])
        db.commit()
        assert "order_change_notice" in resolve_visible_form_types(db, cid)


def test_i2_an_active_segment_grants_it_and_a_contact_switch_off_hides_it():
    from app.models.price_tag import ContactPortalFormOverride
    from app.services.portal_form_visibility_service import resolve_visible_form_types

    from ._pg_fixture import blank_session
    from ._portal_grant import link_contact_segment, seed_segment

    with blank_session() as db:
        cid = contact(db)
        seg = seed_segment(db, kinds=["order_change_notice"])
        link_contact_segment(db, cid, seg.code)
        db.commit()
        assert "order_change_notice" in resolve_visible_form_types(db, cid)

        db.add(
            ContactPortalFormOverride(
                id=str(uuid.uuid4()), contact_id=cid, form_type="order_change_notice", is_enabled=False
            )
        )
        db.commit()
        assert "order_change_notice" not in resolve_visible_form_types(db, cid)


# ================================================================== I3 the three cards


def _staff_client(db, monkeypatch) -> TestClient:
    from app.database import get_db
    from app.dependencies import get_current_user
    from app.main import app
    from app.services.user_service import UserPermissionService

    def _db_override():
        yield db

    app.dependency_overrides[get_db] = _db_override
    app.dependency_overrides[get_current_user] = lambda: {"id": str(uuid.uuid4())}
    monkeypatch.setattr(UserPermissionService, "check_user_has_permission", lambda *a, **k: True)
    return TestClient(app)


@pytest.fixture
def _clear_overrides():
    yield
    from app.main import app

    app.dependency_overrides.clear()


def test_i3_contact_portal_forms_card_lists_the_row_and_put_accepts_it(monkeypatch, _clear_overrides):
    """I3: GET .../portal-forms has an inherited/override/effective row labelled by kind;
    PUT accepts it (no 422 unknown form type)."""
    from ._pg_fixture import blank_session

    with blank_session() as db:
        cid = contact(db)
        db.commit()
        client = _staff_client(db, monkeypatch)
        url = f"/api/v1/user-management/contacts/{cid}/portal-forms"

        got = client.get(url)
        assert got.status_code == 200, got.text
        rows = {r["form_type"]: r for r in got.json()["forms"]}
        assert "order_change_notice" in rows, sorted(rows)
        assert rows["order_change_notice"]["inherited"] is False
        assert rows["order_change_notice"]["override"] is None
        assert rows["order_change_notice"]["effective"] is False

        put = client.put(url, json={"overrides": [{"form_type": "order_change_notice", "is_enabled": True}]})
        assert put.status_code == 200, put.text
        rows = {r["form_type"]: r for r in put.json()["forms"]}
        assert rows["order_change_notice"]["override"] is True
        assert rows["order_change_notice"]["effective"] is True


def test_i3_market_segment_editor_accepts_the_kind(monkeypatch, _clear_overrides):
    """I3: market segment create/update validation accepts it and echoes it."""
    from ._pg_fixture import blank_session

    with blank_session() as db:
        client = _staff_client(db, monkeypatch)
        code = f"zzt-ocn-{uuid.uuid4().hex[:8]}"
        res = client.post(
            "/api/v1/user-management/market-segments/",
            json={"code": code, "name": "ZZT segment", "portal_form_types": ["order_change_notice"]},
        )
        assert res.status_code == 201, res.text
        assert res.json()["portal_form_types"] == ["order_change_notice"]

        upd = client.put(
            f"/api/v1/user-management/market-segments/{code}",
            json={"portal_form_types": ["order_change_notice", "sample_request"]},
        )
        assert upd.status_code == 200, upd.text
        assert upd.json()["portal_form_types"] == ["order_change_notice", "sample_request"]


def test_i3_tag_catalog_offers_it_with_the_label(client, db, all_perms):
    """I3: the contact tag card's `portal_forms` catalog lists it, labelled."""
    resp = client.get("/api/v1/user-management/contact-tags/settings-catalog")
    assert resp.status_code == 200, resp.text
    forms = {f["value"]: f["label"] for f in resp.json()["portal_forms"]}
    assert forms.get("order_change_notice") == "Order Change Notice", forms


def test_i3_a_tag_switching_it_on_grants_it_to_the_holder_at_apply(client, db, all_perms):
    """I3: a tag's `portal_forms.order_change_notice` is accepted and, applied, grants the kind."""
    from app.models.price_tag import ContactPortalFormOverride
    from app.services.portal_form_visibility_service import resolve_visible_form_types
    from tests.test_contact_tags_s2 import _holder, _stag
    from tests.test_contact_tags_s3 import _apply, _rows

    tag = _stag(client, db, {"portal_forms": {"order_change_notice": True}})
    holder = _holder(client, db, [tag])
    assert "order_change_notice" not in resolve_visible_form_types(db, str(holder.id))
    _rows(_apply(client, [holder.id], dry_run=False))
    db.expire_all()
    rows = db.query(ContactPortalFormOverride).filter_by(
        contact_id=str(holder.id), form_type="order_change_notice"
    ).all()
    assert [r.is_enabled for r in rows] == [True]
    assert "order_change_notice" in resolve_visible_form_types(db, str(holder.id))


# The catalog tests use the contact-tags fixtures the existing suites use.
from tests.test_contact_tags_s1 import client, db, perms  # noqa: E402,F401
from tests.test_contact_tags_s2 import all_perms  # noqa: E402,F401


# ================================================================== I7 one Requested-by field


def test_i7_create_stamps_the_eligible_requestor_and_returns_id_and_name(ocn):
    cid = _eligible(ocn.db, f"{REQUESTOR} A")
    d = create_with(ocn, requested_by_contact_id=cid)
    assert d.get("requested_by_contact_id") == cid, d
    assert d.get("requested_by") == _contact_name(ocn.db, cid)
    got = ocn.as_(ocn.viewer).get(f"{OCN}/{d['id']}").json()
    assert got.get("requested_by_contact_id") == cid
    assert got.get("requested_by") == _contact_name(ocn.db, cid)


def create_with(o, user_id=None, **over) -> dict:
    res = _post(o, _body(o, **over), user_id)
    assert res.status_code in (200, 201), res.text
    return res.json()


def test_i7_the_api_no_longer_carries_the_salesperson_fields(ocn):
    d = create_with(ocn)
    detail = ocn.as_(ocn.viewer).get(f"{OCN}/{d['id']}").json()
    listed = rows_of(ocn.as_(ocn.viewer).get(OCN, params={"limit": 100}).json())
    assert listed
    for body in (d, detail, *listed):
        assert "sales_in_charge_user_id" not in body, sorted(body)
        assert "sales_in_charge_name" not in body, sorted(body)
    # ...and the replacement is on the list row too.
    assert "requested_by" in listed[0] and "requested_by_contact_id" in listed[0], sorted(listed[0])


def test_i7_an_ineligible_requestor_is_422_on_create(ocn):
    cid = _ineligible(ocn.db, f"{REQUESTOR} Outsider")
    res = _post(ocn, _body(ocn, requested_by_contact_id=cid))
    assert res.status_code == 422, res.text
    assert res.json().get("code") == "REQUESTOR_NOT_ELIGIBLE", res.text


def test_i7_an_ineligible_requestor_is_422_on_update_and_the_row_is_untouched(ocn):
    good = _eligible(ocn.db, f"{REQUESTOR} Good")
    bad = _ineligible(ocn.db, f"{REQUESTOR} Bad")
    d = create_with(ocn, requested_by_contact_id=good)
    res = ocn.as_(ocn.sales_admin).put(f"{OCN}/{d['id']}", json={"requested_by_contact_id": bad})
    assert res.status_code == 422, res.text
    assert res.json().get("code") == "REQUESTOR_NOT_ELIGIBLE"
    kept = ocn.as_(ocn.viewer).get(f"{OCN}/{d['id']}").json()
    assert kept.get("requested_by_contact_id") == good


def test_i7_update_changes_the_requestor_and_the_label_follows_the_contacts_name(ocn):
    a = _eligible(ocn.db, f"{REQUESTOR} A")
    b = _eligible(ocn.db, f"{REQUESTOR} B")
    d = create_with(ocn, requested_by_contact_id=a)
    res = ocn.as_(ocn.sales_admin).put(f"{OCN}/{d['id']}", json={"requested_by_contact_id": b})
    assert res.status_code == 200, res.text
    assert res.json().get("requested_by_contact_id") == b
    assert res.json().get("requested_by") == _contact_name(ocn.db, b)


def test_i7_the_requestor_can_be_cleared(ocn):
    a = _eligible(ocn.db, f"{REQUESTOR} A")
    d = create_with(ocn, requested_by_contact_id=a)
    res = ocn.as_(ocn.sales_admin).put(f"{OCN}/{d['id']}", json={"requested_by_contact_id": None})
    assert res.status_code == 200, res.text
    assert res.json().get("requested_by_contact_id") is None
    assert "requested_by_contact_id" in res.json()


def test_i7_the_list_sorts_on_requested_by(ocn):
    """Rows i = 0, 1, 2 carry contacts named C, B, A (descending in i), created in order."""
    ids = []
    for letter in "CBA":
        cid = _eligible(ocn.db, f"{REQUESTOR} {letter}")
        ids.append(create_with(ocn, requested_by_contact_id=cid, customer_po_no=f"XT04/38{letter} (R1)")["id"])

    def order(direction):
        res = ocn.as_(ocn.viewer).get(OCN, params={"sort": "requested_by", "dir": direction, "limit": 100})
        assert res.status_code == 200, res.text
        return [r["id"] for r in rows_of(res.json()) if r["id"] in ids]

    assert order("asc") == list(reversed(ids))
    assert order("desc") == ids


# ================================================================== I8 default


def test_i8_crm_create_defaults_to_the_creating_users_linked_contact(ocn):
    """The linked contact is the default even when it sits in no requestor segment."""
    mine = _ineligible(ocn.db, f"{REQUESTOR} Mine")
    _link(ocn.db, ocn.raiser, mine)
    d = create_with(ocn)  # payload omits requested_by_contact_id
    assert d.get("requested_by_contact_id") == mine, d
    assert d.get("requested_by") == _contact_name(ocn.db, mine)


def test_i8_crm_create_is_empty_when_the_user_has_no_linked_contact(ocn):
    d = create_with(ocn)
    assert "requested_by_contact_id" in d, sorted(d)
    assert d["requested_by_contact_id"] is None
    assert not d.get("requested_by")


def test_i8_an_explicit_requestor_beats_the_default(ocn):
    mine = _ineligible(ocn.db, f"{REQUESTOR} Mine")
    _link(ocn.db, ocn.raiser, mine)
    other = _eligible(ocn.db, f"{REQUESTOR} Other")
    d = create_with(ocn, requested_by_contact_id=other)
    assert d.get("requested_by_contact_id") == other


# ================================================================== I9 own-records


def test_i9_a_view_own_user_linked_to_the_requestor_contact_sees_the_notice(ocn):
    cid = _eligible(ocn.db, f"{REQUESTOR} Own")
    _link(ocn.db, ocn.own, cid)
    d = create_with(ocn, requested_by_contact_id=cid)  # raised by someone else
    listed = {r["id"] for r in rows_of(ocn.as_(ocn.own).get(OCN, params={"limit": 100}).json())}
    assert d["id"] in listed
    assert ocn.as_(ocn.own).get(f"{OCN}/{d['id']}").status_code == 200


def test_i9_a_view_own_user_not_linked_to_it_does_not(ocn):
    cid = _eligible(ocn.db, f"{REQUESTOR} Someone")
    d = create_with(ocn, requested_by_contact_id=cid)
    listed = {r["id"] for r in rows_of(ocn.as_(ocn.own).get(OCN, params={"limit": 100}).json())}
    assert d["id"] not in listed
    assert ocn.as_(ocn.own).get(f"{OCN}/{d['id']}").status_code == 404


def test_i9_the_creator_and_the_cs_in_charge_still_see_theirs(ocn):
    mine = create_with(ocn, user_id=ocn.own)
    cs_named = create_with(ocn, cs_in_charge_user_id=ocn.own)
    listed = {r["id"] for r in rows_of(ocn.as_(ocn.own).get(OCN, params={"limit": 100}).json())}
    assert {mine["id"], cs_named["id"]} <= listed


def test_i9_naming_the_old_sales_in_charge_no_longer_makes_it_theirs(ocn):
    """The retired field is ignored: a payload still naming it does not put the notice in the list."""
    d = create_with(ocn, sales_in_charge_user_id=ocn.own)
    listed = {r["id"] for r in rows_of(ocn.as_(ocn.own).get(OCN, params={"limit": 100}).json())}
    assert d["id"] not in listed


# ================================================================== I10 history


def _history(o, ocn_id):
    res = o.as_(o.sales_admin).get(
        "/api/v1/audit/logs/", params={"entity_type": KIND, "entity_id": ocn_id, "limit": 100}
    )
    assert res.status_code == 200, res.text
    return res.json()["data"]


@pytest.fixture(autouse=False)
def _audit_listeners():
    from app.services.audit_service import register_audit_listeners

    register_audit_listeners()


def test_i10_history_reads_requested_by_old_to_new_with_names_never_ids(ocn, _audit_listeners):
    a = _eligible(ocn.db, f"{REQUESTOR} A")
    b = _eligible(ocn.db, f"{REQUESTOR} B")
    d = create_with(ocn, requested_by_contact_id=a)
    res = ocn.as_(ocn.sales_admin).put(f"{OCN}/{d['id']}", json={"requested_by_contact_id": b})
    assert res.status_code == 200, res.text
    rows = _history(ocn, d["id"])
    moved = [r for r in rows if r["action"] == "UPDATE" and "requested_by" in (r["new_values"] or {})]
    assert moved, rows
    assert moved[0]["old_values"]["requested_by"] == _contact_name(ocn.db, a)
    assert moved[0]["new_values"]["requested_by"] == _contact_name(ocn.db, b)
    blob = repr([(r["old_values"], r["new_values"]) for r in rows])
    for contact_id in (a, b):
        assert contact_id not in blob
    assert "sales_in_charge" not in blob


# ================================================================== round 20b (reviewer's report)

from .test_ocn_amendment_link import _create as _amend, build  # noqa: E402,F401


def _contact_row(db, name: str) -> str:
    from app.models.access import RespondContact

    row = RespondContact(id=str(uuid.uuid4()), phone_number=f"+6011{uuid.uuid4().hex[:8]}", name=name)
    db.add(row)
    db.flush()
    return row.id


def test_r20b_an_amendment_drafted_notice_defaults_requested_by_to_the_amending_users_contact(build):
    """I8: the notice a sales order amendment drafts gets the amending user's linked contact."""
    from app.models.project_so import OrderChangeNotice

    b = build
    mine = _contact_row(b.db, f"{REQUESTOR} Amender")
    _link(b.db, b.owner, mine)
    created = _amend(b)
    row = b.db.query(OrderChangeNotice).filter(OrderChangeNotice.id == created["ocn_id"]).one()
    assert row.requested_by_contact_id == mine
    assert row.requested_by == _contact_name(b.db, mine)


def test_r20b_an_amendment_drafted_notice_has_no_requestor_when_the_user_has_no_linked_contact(build):
    """I8 guard: empty when the amending user has no linked contact."""
    from app.models.project_so import OrderChangeNotice

    created = _amend(build)
    row = build.db.query(OrderChangeNotice).filter(OrderChangeNotice.id == created["ocn_id"]).one()
    assert row.requested_by_contact_id is None


@pytest.fixture
def rs_client():
    from app.database import get_db
    from app.dependencies import get_current_user_or_api_key
    from app.main import app

    from ._pg_fixture import blank_session
    from ._sample_request_seed import make_user

    with blank_session() as db:
        caller = make_user(db, "zzt-ocn caller")
        state = {"user": caller}
        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[get_current_user_or_api_key] = lambda: {
            "id": state["user"], "email": "staff@zzt.test",
        }
        try:
            with TestClient(app) as c:
                yield c, db, caller
        finally:
            app.dependency_overrides.clear()


SELECT = "/api/v1/master-data/respond-contacts/requestor-select"


def test_r20b_requestor_select_returns_the_callers_own_linked_contact_outside_any_segment(rs_client):
    """I8: include_ids holding the caller's own linked contact returns it (it is the default)."""
    c, db, caller = rs_client
    mine = _contact_row(db, f"{REQUESTOR} Mine")  # in no requestor segment, on no form
    _link(db, caller, mine)
    res = c.get(SELECT, params={"include_ids": mine})
    assert res.status_code == 200, res.text
    assert [i["id"] for i in res.json()["items"]] == [mine]


def test_r20b_requestor_select_still_refuses_another_contact_on_no_form(rs_client):
    """Fail-closed guard: someone else's contact, on no form and no segment, is not resolved."""
    c, db, caller = rs_client
    mine = _contact_row(db, f"{REQUESTOR} Mine")
    _link(db, caller, mine)
    other = _contact_row(db, f"{REQUESTOR} Other")
    db.commit()
    res = c.get(SELECT, params={"include_ids": other})
    assert res.status_code == 200, res.text
    assert [i["id"] for i in res.json()["items"]] == []


def test_r20b_filter_form_referenced_ids_keeps_an_id_referenced_only_by_a_notice(ocn):
    """Guard (green on HEAD): a requestor saved on an order change notice stays selectable."""
    from app.services.requestor_options_service import filter_form_referenced_ids

    cid = _eligible(ocn.db, f"{REQUESTOR} OnNotice")
    create_with(ocn, requested_by_contact_id=cid)
    stranger = _ineligible(ocn.db, f"{REQUESTOR} OnNothing")
    assert filter_form_referenced_ids(ocn.db, [cid, stranger]) == [cid]
