"""OCN-ORDER-CHANGE-NOTICE round 15 (crew pass on 27e03cd8), pinned.

- F1: a salesperson (`.view_own` + `.create`) reaches the notices from MY REQUESTS, on the staff
  pages: the list they open reads their own notices only, never another's or another company's.
- Addendum: History reads the notice's user fields as the person's name, old -> new (approver,
  approval requester, sales / C.S. in charge, rejected by, voided by), never an id; an empty side
  stays empty.

Postgres only, every row seeded.
"""
from __future__ import annotations

from ._forms_chain_support import SORENTO, user, world  # noqa: F401
from ._ocn_support import (  # noqa: F401  (fixtures)
    KIND,
    OCN,
    approved,
    create,
    move,
    ocn,
    ok,
    rows_of,
    sla,
)
from .test_ocn_routes import _other_company_ocn


def _name(o, user_id):
    from app.models.user import User

    return o.db.get(User, user_id).name


# ================================================================== F1


def test_r15_a_salespersons_list_holds_their_own_notices_only(ocn):
    mine = create(ocn, user_id=ocn.own, cs_in_charge_user_id=None)
    # Round 20 (UAC I9): "named" is now the user linked to the notice's Requested by contact.
    from .test_ocn_round20 import _eligible, _link

    contact_id = _eligible(ocn.db, "ZZT Requestor Own")
    _link(ocn.db, ocn.own, contact_id)
    named = create(ocn, user_id=ocn.raiser, requested_by_contact_id=contact_id, cs_in_charge_user_id=None)
    theirs = create(ocn, user_id=ocn.raiser, cs_in_charge_user_id=None)
    foreign = _other_company_ocn(ocn)
    res = ocn.as_(ocn.own).get(OCN, params={"limit": 100})
    assert res.status_code == 200, res.text
    ids = {r["id"] for r in rows_of(res.json())}
    assert {mine["id"], named["id"]} <= ids
    assert theirs["id"] not in ids
    assert str(foreign.id) not in ids


def test_r15_a_salesperson_creates_and_submits_their_own_notice(ocn):
    """The list's Create and the form's Submit work for them on the staff routes."""
    d = create(ocn, user_id=ocn.own, cs_in_charge_user_id=None)
    ok(move(ocn, d["id"], "submit", ocn.own))


# ================================================================== addendum: user fields by name


def _history(o, ocn_id, as_user):
    res = o.as_(as_user).get(
        "/api/v1/audit/logs/", params={"entity_type": KIND, "entity_id": ocn_id, "limit": 100}
    )
    assert res.status_code == 200, res.text
    return res.json()["data"]


def test_r15_history_reads_the_approver_and_the_requester_by_name(ocn, sla):
    d = approved(ocn)
    rows = _history(ocn, d["id"], ocn.sales_admin)
    approval = [r for r in rows if "approver_id" in (r["new_values"] or {}) and (r["new_values"] or {}).get("approver_id")]
    assert approval, rows
    assert approval[0]["new_values"]["approver_id"] == _name(ocn, ocn.manager)
    requested = [
        r for r in rows if (r["new_values"] or {}).get("requested_approval_by_user_id")
    ]
    assert requested
    assert requested[0]["new_values"]["requested_approval_by_user_id"] == _name(ocn, ocn.sales_admin)
    assert requested[0]["old_values"].get("requested_approval_by_user_id") in (None, "")
    blob = repr([(r["old_values"], r["new_values"]) for r in rows])
    for user_id in (ocn.manager, ocn.sales_admin):
        assert str(user_id) not in blob


def test_r15_history_reads_cs_in_charge_by_name(ocn):
    """Round 20 retired Sales in charge (its History is test_ocn_round20 I10); C.S. stays."""
    d = create(ocn)
    res = ocn.as_(ocn.raiser).put(f"{OCN}/{d['id']}", json={"cs_in_charge_user_id": ocn.own})
    assert res.status_code == 200, res.text
    rows = _history(ocn, d["id"], ocn.sales_admin)
    moved = [r for r in rows if r["action"] == "UPDATE" and "cs_in_charge_user_id" in (r["new_values"] or {})]
    assert moved, rows
    assert moved[0]["new_values"]["cs_in_charge_user_id"] == _name(ocn, ocn.own)
    assert moved[0]["old_values"]["cs_in_charge_user_id"] == _name(ocn, ocn.cs)
