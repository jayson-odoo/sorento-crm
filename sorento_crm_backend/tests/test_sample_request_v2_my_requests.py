"""SAMPLE-REQUEST-V2 slice 2 (red-first): the salesperson who sees only their own sample requests
writes them through /api/v1/my-requests with the same ship-to rules as the staff form (owner Q1 a,
11 Nov), while an external contact on the public portal keeps today's form (the party is ignored
there and never shown).

Plan: documentation/plans/project-sales/PLAN-sample-request-v2-slice2-11nov.md. Harness: the
PORTAL-P4 world (a salesperson `rep` with a linked portal contact, `me` = /api/v1/my-requests).
"""
from __future__ import annotations

from app.models.projects import ProjectParty, ProjectPartyContact, ProjectPartyLink

from tests import _portal_p4_support as s
from tests._portal_p4_sr_so_support import SR_PORTAL, scene, sr_row, world  # noqa: F401


def _party(w, name, *, address="No. 12, Jalan Perindustrian 3, Klang"):
    row = ProjectParty(
        id=s.uid(), company_id=w.company_id, party_type="trading_house", name=f"ZZT {name}", address=address
    )
    w.sc.db.add(row)
    w.sc.db.flush()
    return row


def _contact(w, party, name):
    row = ProjectPartyContact(id=s.uid(), company_id=party.company_id, party_id=party.id, name=name)
    w.sc.db.add(row)
    w.sc.db.flush()
    return row


def _body(w, **over):
    body = w.sr_body(customer_id=w.rep.mine.id, customer_name=None, **over)
    body.pop("ship_to_name", None)
    return body


def test_my_requests_takes_the_ship_to_party_and_shows_it(world):
    w = world
    party = _party(w, "Bintang Trading")
    w.sc.db.commit()
    res = w.rep.me.call("POST", SR_PORTAL, json=_body(w, ship_to_party_id=party.id))
    assert res.status_code == 201, res.text
    d = res.json()
    assert d["ship_to_party_id"] == party.id
    assert d["ship_to_name"] == party.name
    assert d["ship_to_address"] == "No. 12, Jalan Perindustrian 3, Klang"
    assert sr_row(w, d["id"]).ship_to_party_id == party.id


def test_my_requests_contacts_print_a_and_b(world):
    w = world
    party = _party(w, "Bintang Trading")
    a = _contact(w, party, "Mei Ling Tan")
    b = _contact(w, party, "Ravi Kumar")
    w.sc.db.commit()
    d = w.rep.me.call(
        "POST", SR_PORTAL, json=_body(w, ship_to_party_id=party.id, ship_to_contact_ids=[a.id, b.id])
    ).json()
    assert d["site_contact_name"] == "Mei Ling Tan & Ravi Kumar"


def test_my_requests_submit_needs_the_party_like_staff(world):
    w = world
    d = w.rep.me.call("POST", SR_PORTAL, json=w.sr_body(customer_id=w.rep.mine.id, customer_name=None)).json()
    res = w.rep.me.call("POST", f"{SR_PORTAL}/{d['id']}/submit")
    assert res.status_code == 422, res.text
    assert res.json()["details"]["field"] == "ship_to_party_id"


def test_my_requests_submit_with_party_and_debtor_passes(world):
    w = world
    party = _party(w, "Bintang Trading")
    w.sc.db.commit()
    d = w.rep.me.call("POST", SR_PORTAL, json=_body(w, ship_to_party_id=party.id)).json()
    res = w.rep.me.call("POST", f"{SR_PORTAL}/{d['id']}/submit")
    assert res.status_code in (200, 201), res.text
    assert res.json()["status"] == "submitted"


def test_my_requests_cannot_link_a_party_to_a_project_it_cannot_edit(world):
    """The salesperson holds no projects.projects.edit: a party not on the project is refused."""
    from tests._sample_request_seed import make_project

    w = world
    project = make_project(w.sc.db, w.company_id, w.rep.actor.id)
    party = _party(w, "Delta Interior Works")
    w.sc.db.commit()
    res = w.rep.me.call(
        "POST",
        SR_PORTAL,
        json=_body(w, project_id=project.id, project_title=None, ship_to_party_id=party.id, ship_to_role="subcontractor"),
    )
    assert res.status_code in (403, 422), res.text
    assert w.sc.db.query(ProjectPartyLink).filter(ProjectPartyLink.party_id == party.id).count() == 0


def test_the_public_portal_still_ignores_and_hides_the_party(world):
    w = world
    party = _party(w, "Bintang Trading")
    w.sc.db.commit()
    res = w.rep.portal.call("POST", SR_PORTAL, json=w.sr_body(ship_to_party_id=party.id))
    assert res.status_code == 201, res.text
    d = res.json()
    assert "ship_to_party_id" not in d
    assert sr_row(w, d["id"]).ship_to_party_id is None
    # ... and the portal's own submit keeps the typed Ship To (external contacts keep today's form).
    assert w.rep.portal.call("POST", f"{SR_PORTAL}/{d['id']}/submit").status_code in (200, 201)
