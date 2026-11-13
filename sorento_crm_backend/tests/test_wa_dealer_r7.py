"""WA-COMPLAINT-INTAKE round 7 red tests: the one non-staff rule everywhere a linked user is read.

UAC: documentation/plans/chatbot/wa-complaint-intake-acceptance-criteria.md (section D, dealers file as
their own CRM user). "Staff" is ONE rule: `user_service.holds_staff_role` / `only_non_staff_roles`
(a linked user holding a live role outside {portal_user, guest}); `contact_grant._is_staff` is the
contact-level reading of it (staff by phone, by a linked staff user, or by a sales agent's contact).

Contract these tests pin:

* R7 sec: `ideation_capture_service._dealer_eligible(db, contact)` is False for a contact the one rule
  treats as staff (linked staff user, a staff user's phone, a sales agent's contact): no portal_user is
  created and the turn takes the existing non-dealer reply (`no_access`).
* R7 S1: the portal helpers `_linked_user_id(db, contact_id)` in
  `app/api/v1/public/portal_new_product_application.py`, `app/api/v1/public/portal_sample_request.py`
  and `app/services/project_registration_service.py` ignore a linked user holding no staff role (a
  dealer's own portal_user) and answer as for an unlinked contact (None). A linked staff user is
  still returned.
* R7 S3: the own-message check takes the contact's latest inbound turn that HAS text: a photo sent
  seconds after the text does not hide it.
* R7 sec nit: an EXISTING dealer-own user (portal_user only) files only from the contact's own latest
  live inbound message, the same refusal as a new dealer's forged call.
* R7 sec nit: `chatbot.analytics.facts._who` does not count a portal_user-only linked user as staff.

Postgres only (blank schema via tests/_pg_fixture.py); every test seeds its own chain.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

# MUST be the first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402,F401

from app.models.access import RespondContact
from app.models.chatbot_turn import ChatbotTurn
from app.models.sales_agent import SalesAgent
from app.models.user import User
from app.services import reference_seed
from tests._pg_fixture import blank_session, unique_code
from tests.test_ideation_capture_turn import MSG, Env, env  # noqa: F401  (fixture)
from tests.test_wa_dealer_submitter import (
    NO_ACCESS_EN,
    SUBMIT,
    _assign,
    _dealer,
    _dealer_unseeded,
    _linked_users,
    _role,
    _role_slugs,
    seed_inbound,
)


def _user(db, *, contact_id: str | None, phone: str | None = None, roles: tuple[str, ...] = ()) -> User:
    user = User(
        id=str(uuid.uuid4()),
        email=f"{unique_code('r7').lower()}@zzt.test",
        name="ZZT R7 User",
        status="ACTIVE",
        contact_number=phone,
        respond_contact_id=contact_id,
    )
    db.add(user)
    db.flush()
    _assign(db, user, *roles)
    return user


# --------------------------------------------------------------------------- #
# R7 sec: a contact the one rule treats as staff is never a dealer            #
# --------------------------------------------------------------------------- #
def _staff_linked(e: Env, contact: RespondContact) -> None:
    reference_seed.seed_roles(e.db)
    _user(e.db, contact_id=contact.id, roles=("salesperson",))


def _staff_phone(e: Env, contact: RespondContact) -> None:
    """A salesperson's own CRM user carries this contact's number, unlinked (contact_grant._is_staff by phone)."""
    reference_seed.seed_roles(e.db)
    _user(e.db, contact_id=None, phone=contact.phone_number.lstrip("+"), roles=("salesperson",))


def _sales_agent_contact(e: Env, contact: RespondContact) -> None:
    """The contact is a sales agent's own contact (contact_grant._is_staff, sales agent branch)."""
    e.db.add(SalesAgent(id=str(uuid.uuid4()), sales_agent=unique_code("ZZTR7").upper(), contact_id=contact.id))
    e.db.flush()


STAFF_CASES = {
    "linked_staff_user": _staff_linked,
    "staff_users_phone": _staff_phone,
    "sales_agent_contact": _sales_agent_contact,
}


@pytest.mark.parametrize("case", sorted(STAFF_CASES))
def test_R7_sec_dealer_eligible_refuses_a_staff_contact(env, case):
    contact = _dealer(env)
    STAFF_CASES[case](env, contact)
    assert env.svc._dealer_eligible(env.db, contact) is False, f"{case}: a staff contact is not a dealer"


@pytest.mark.parametrize("case", sorted(STAFF_CASES))
def test_R7_sec_a_staff_contact_gets_no_portal_user_and_the_no_access_reply(env, case):
    contact = _dealer(env)  # its turns are genuine own messages: staff-ness is the only refusal
    STAFF_CASES[case](env, contact)
    before = {u.id for u in _linked_users(env.db, contact.id)}
    env.created()
    out = env.turn(env.idea_message(language="en"))
    assert out["status"] == "no_access", out["status"]
    assert out["reply_text"] == NO_ACCESS_EN
    assert env.create_calls == []
    after = _linked_users(env.db, contact.id)
    assert {u.id for u in after} == before
    assert not any(_role_slugs(env.db, u.id) == {"portal_user"} for u in after)


def test_R7_sec_control_a_dealer_with_its_own_portal_user_stays_eligible(env):
    contact = _dealer(env)
    _user(env.db, contact_id=contact.id, roles=("portal_user",))
    assert env.svc._dealer_eligible(env.db, contact) is True


# --------------------------------------------------------------------------- #
# R7 S1: the portal helpers ignore a dealer's own (non-staff) linked user     #
# --------------------------------------------------------------------------- #
def _npa_lookup():
    from app.api.v1.public.portal_new_product_application import _linked_user_id

    return _linked_user_id


def _project_lookup():
    from app.services.project_registration_service import _linked_user_id

    return _linked_user_id


def _sample_lookup():
    from app.api.v1.public.portal_sample_request import _linked_user_id

    return _linked_user_id


SITES = {
    "new_product_application_applicant": _npa_lookup,
    "project_registration_owner": _project_lookup,
    "sample_request_salesperson": _sample_lookup,
}


def _portal_contact(db) -> RespondContact:
    reference_seed.seed_roles(db)
    contact = RespondContact(
        id=str(uuid.uuid4()),
        phone_number="+601" + str(uuid.uuid4().int % 10**8).zfill(8),
        name="ZZT R7 Portal Contact",
        respond_io_id=f"rio-{uuid.uuid4().hex[:10]}",
        session_vars={},
    )
    db.add(contact)
    db.flush()
    return contact


@pytest.mark.parametrize("site", sorted(SITES))
def test_R7_S1_a_dealers_own_portal_user_is_ignored(site):
    lookup = SITES[site]()
    with blank_session() as db:
        contact = _portal_contact(db)
        unlinked = lookup(db, contact.id)
        _user(db, contact_id=contact.id, roles=("portal_user",))
        assert unlinked is None
        assert lookup(db, contact.id) is None, f"{site}: a portal_user-only linked user is not staff"


@pytest.mark.parametrize("site", sorted(SITES))
def test_R7_S1_control_a_linked_staff_user_is_still_used(site):
    lookup = SITES[site]()
    with blank_session() as db:
        contact = _portal_contact(db)
        user = _user(db, contact_id=contact.id, roles=("salesperson", "portal_user"))
        assert lookup(db, contact.id) == user.id


# --------------------------------------------------------------------------- #
# R7 S3: a photo right after the text does not hide the text                  #
# --------------------------------------------------------------------------- #
def _seed_photo(db, respond_id: str, *, with_null_text: bool) -> None:
    """An inbound image turn, as the chatbot stores it: an attachment on the inner message, no words."""
    inner = {"type": "attachment", "attachment": {"type": "image", "url": "https://cdn.test/p.jpg"}}
    if with_null_text:
        inner["text"] = None
    db.add(
        ChatbotTurn(
            id=str(uuid.uuid4()),
            contact_respond_id=respond_id,
            message_id=f"zzt-msg-{uuid.uuid4().hex[:10]}",
            ingress="webhook",
            envelope={"message": {"message": {"message": inner}}},
            is_test=False,
            status="processing",
            created_at=datetime.now(timezone.utc) - timedelta(seconds=2),
        )
    )
    db.flush()


@pytest.mark.parametrize("with_null_text", [False, True], ids=["no_text_key", "text_null"])
def test_R7_S3_a_photo_after_the_text_still_files_the_text(env, with_null_text):
    contact = _dealer_unseeded(env)
    seed_inbound(env.db, env.rio, MSG, minutes_ago=5 / 60)  # the text, 5 seconds ago
    _seed_photo(env.db, env.rio, with_null_text=with_null_text)  # the photo, 2 seconds ago
    env.created()
    out = env.turn(env.idea_message())
    assert out["status"] == "complete", out["status"]
    assert len(_linked_users(env.db, contact.id)) == 1
    assert len(env.create_calls) == 1


# --------------------------------------------------------------------------- #
# R7 sec nit: an existing dealer-own user files only its own latest message   #
# --------------------------------------------------------------------------- #
def _existing_dealer(e: Env) -> tuple[RespondContact, User]:
    """An eligible contact already linked to its own portal_user-only user (made on an earlier filing)."""
    contact = _dealer_unseeded(e)
    _role(e.db, "portal_user", SUBMIT)
    user = _user(e.db, contact_id=contact.id, roles=("portal_user",))
    assert e.svc._access_user(e.db, e.rio) is not None, "fixture: the dealer-own user may file"
    return contact, user


def test_R7_sec_an_existing_dealer_user_does_not_file_a_text_it_never_sent(env):
    contact, user = _existing_dealer(env)
    env.created()
    out = env.turn(env.idea_message(language="en"))
    assert out["status"] == "no_access", out["status"]
    assert out["reply_text"] == NO_ACCESS_EN
    assert env.create_calls == [] and env.similar_calls == []
    assert [u.id for u in _linked_users(env.db, contact.id)] == [user.id]


def test_R7_sec_an_existing_dealer_user_does_not_file_an_older_message(env):
    _existing_dealer(env)
    seed_inbound(env.db, env.rio, MSG, minutes_ago=3)
    seed_inbound(env.db, env.rio, "thanks", minutes_ago=1)
    env.created()
    out = env.turn(env.idea_message(language="en"))
    assert out["status"] == "no_access", out["status"]
    assert env.create_calls == []


def test_R7_sec_control_an_existing_dealer_user_files_its_genuine_latest_message(env):
    contact, user = _existing_dealer(env)
    seed_inbound(env.db, env.rio, MSG, minutes_ago=1)
    env.created()
    out = env.turn(env.idea_message(language="en"))
    assert out["status"] == "complete", out["status"]
    (payload,) = env.create_calls
    assert payload["submitter_crm_user_id"] == user.id
    assert [u.id for u in _linked_users(env.db, contact.id)] == [user.id]


# --------------------------------------------------------------------------- #
# R7 sec nit: analytics facts do not count a dealer's own user as staff       #
# --------------------------------------------------------------------------- #
def test_R7_facts_who_does_not_count_a_portal_user_as_staff():
    from app.services.chatbot.analytics.facts import _who

    with blank_session() as db:
        contact = _portal_contact(db)
        contact.chatbot_allowed = True
        db.flush()
        unlinked = _who(db, contact.respond_io_id)
        _user(db, contact_id=contact.id, roles=("portal_user",))
        got = _who(db, contact.respond_io_id)
        assert got["audience"] != "staff"
        assert got == unlinked


def test_R7_facts_who_control_a_linked_staff_user_is_staff():
    from app.services.chatbot.analytics.facts import _who

    with blank_session() as db:
        contact = _portal_contact(db)
        _user(db, contact_id=contact.id, roles=("salesperson",))
        got = _who(db, contact.respond_io_id)
        assert got["audience"] == "staff" and got["contact_type"] == "office"
