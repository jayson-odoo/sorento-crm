"""P1: the lead informant and the acceptance handshake (UAC Group A, D6 + D7).

Two facts drive everything here.

**A lead anchors on the DEVELOPMENT, not on a counterparty (D6).** Marketing works BCI
and panel channels, where on day one nobody knows who the buyer is, because the trading
house only exists once a contractor is awarded. So the buyer is nullable and means the
debtor who will issue the PO, and the informant who told us is recorded separately --
BCI is a data source, never a debtor, and is never written to `customers`.

**Assignment is not ownership (D7).** A lead sits `assigned` until the salesperson
accepts it, and a decline puts it back in marketing's pool with a reason on it. Their own
note is what asked for this: the handover has to be explicit or the lead dies between the
two of them.

Postgres only, on a throwaway schema, rolled back at teardown. Every assertion is scoped
to rows this file created -- the database it runs against holds real records.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy import text

from app.models.notification import Notification
from app.models.order import Customer
from app.models.projects import ProjectParty
from app.models.user import User
from app.services.error_handler import AppException

from ._pg_fixture import blank_schema_engine, blank_session

MARKER = "zzt-lead-accept"


def _uid() -> str:
    return str(uuid.uuid4())


def _sorento(db) -> str:
    return db.execute(text("select id from companies where code = 'SRT'")).scalar()


def _allow_no_buyer(db) -> None:
    """Match the migrated database, where `project_leads.customer_id` is NULLABLE.

    Migration 319 dropped the NOT NULL (D6), but `ProjectLead.customer_id` still
    declares ``nullable=False`` -- so the scratch schema this fixture builds FROM THE
    MODELS is stricter than production. Dropping it here keeps the no-buyer tests
    honest about the real column. Idempotent, so it stays a no-op once the model catches
    up with the migration.

    Qualified with the fixture's scratch stand-in for the `projects` schema (ADR-0011).
    A literal ``projects.leads`` here would reach past the scratch schema and alter the
    REAL table.
    """
    schema = blank_schema_engine().get_execution_options()["schema_translate_map"]["projects"]
    db.execute(text(f'alter table "{schema}".leads alter column customer_id drop not null'))
    db.flush()


def _user(db, name: str, **kwargs) -> str:
    user_id = _uid()
    db.add(User(id=user_id, email=f"{user_id}@zzt.test", name=name, **kwargs))
    db.flush()
    return user_id


def _customer(db, company_id: str, name: str) -> Customer:
    customer = Customer(
        id=_uid(),
        company_id=company_id,
        customer_code=f"ZZT-{uuid.uuid4().hex[:6]}",
        customer_name=name,
    )
    db.add(customer)
    db.flush()
    return customer


def _party(db, company_id: str, name: str, party_type: str = "consultant") -> ProjectParty:
    party = ProjectParty(
        id=_uid(), company_id=company_id, party_type=party_type, name=name
    )
    db.add(party)
    db.flush()
    return party


def _seeded(db) -> str:
    """A company with the lead numbering rule and status graph in place."""
    from app.services import project_seed_service

    company_id = _sorento(db)
    project_seed_service.run(db, company_id=company_id)
    return company_id


def _lead(db, company_id: str, actor: str, **payload):
    from app.services import project_lead_service as leads

    body = {"title": f"{MARKER} sighting {uuid.uuid4().hex[:6]}"}
    body.update(payload)
    return leads.create_lead(
        db, company_id=company_id, actor_user_id=actor, payload=body
    )


# ---------------------------------------------------- D6: the buyer is optional


def test_a_lead_can_be_registered_with_no_buyer_at_all():
    """AC-A1 + AC-A3. Development, location, developer, value -- nothing else required.

    This is the accepted deviation from ecohub, whose `Lead.clientId` is non-nullable
    because its lead IS a consumer enquiry. A BCI sighting has no counterparty.
    """
    from app.services import project_lead_service as leads

    with blank_session() as db:
        company_id = _seeded(db)
        _allow_no_buyer(db)
        marketing = _user(db, f"{MARKER} Marketing")

        lead = _lead(
            db,
            company_id,
            marketing,
            title="Maryam Tuju Residence",
            location="Cyberjaya, Selangor",
            estimated_value="1810640.62",
        )

        assert lead.customer_id is None
        assert lead.lead_code.startswith("LEAD-")
        assert lead.outcome == leads.OUTCOME_OPEN
        # No handshake has happened yet, so the lead is not waiting on anybody.
        assert lead.acceptance_state is None


def test_the_informant_is_recorded_and_resolved_to_a_name_for_the_screen():
    """AC-A2. An informant is a data source, never a debtor.

    ``informant_party_label`` exists so no UUID reaches the UI, per the cursor rule.
    """
    from app.services import project_lead_service as leads

    with blank_session() as db:
        company_id = _seeded(db)
        _allow_no_buyer(db)
        marketing = _user(db, f"{MARKER} Marketing")
        firm = _party(db, company_id, f"{MARKER} BCI Asia")

        lead = _lead(
            db,
            company_id,
            marketing,
            informant_source="bci",
            informant_ref="BCI-2026-114523",
            informant_party_id=firm.id,
            informant_contact_name="Wong Mei Ling",
        )

        row = leads.serialize_leads(db, [lead])[0]
        assert row["informant_source"] == "bci"
        assert row["informant_ref"] == "BCI-2026-114523"
        assert row["informant_party_label"] == f"{MARKER} BCI Asia"
        assert row["informant_contact_name"] == "Wong Mei Ling"
        assert row["customer_id"] is None
        # The informant is NOT a customer. Nothing was created in the buying ledger.
        assert (
            db.query(Customer)
            .filter(Customer.customer_name == f"{MARKER} BCI Asia")
            .first()
            is None
        )


def test_an_informant_source_outside_the_bucket_list_is_refused():
    """The bucket has to be reportable: free text here is nine names for one channel."""
    from app.services import project_lead_service as leads

    with blank_session() as db:
        company_id = _seeded(db)
        _allow_no_buyer(db)
        marketing = _user(db, f"{MARKER} Marketing")

        with pytest.raises(AppException) as exc:
            _lead(db, company_id, marketing, informant_source="a bloke at the site")
        assert exc.value.status_code == 422
        assert exc.value.detail["code"] == "lead_informant_source_invalid"

        with pytest.raises(AppException) as missing:
            _lead(db, company_id, marketing, informant_party_id=_uid())
        assert missing.value.status_code == 404


def test_a_named_buyer_is_still_validated_and_can_be_cleared_again():
    """Optional does not mean unchecked, and a buyer named in error is CLEARED rather
    than swapped for some other debtor."""
    from app.services import project_lead_service as leads

    with blank_session() as db:
        company_id = _seeded(db)
        _allow_no_buyer(db)
        marketing = _user(db, f"{MARKER} Marketing")
        buyer = _customer(db, company_id, f"{MARKER} Buimaco")

        lead = _lead(db, company_id, marketing, customer_id=buyer.id)
        assert lead.customer_id == buyer.id

        with pytest.raises(AppException) as exc:
            leads.update_lead(db, lead, {"customer_id": _uid()})
        assert exc.value.status_code == 404

        leads.update_lead(db, lead, {"customer_id": None})
        assert lead.customer_id is None


def test_a_lead_with_no_buyer_still_qualifies_into_a_project():
    """The whole point of D6: the pursuit proceeds while the buyer is unknown."""
    from app.services import project_lead_service as leads

    with blank_session() as db:
        company_id = _seeded(db)
        _allow_no_buyer(db)
        owner = _user(db, f"{MARKER} Ali")
        developer = _party(db, company_id, f"{MARKER} Tuju Setia", party_type="developer")

        lead = _lead(
            db,
            company_id,
            owner,
            title="Maryam Tuju Residence",
            developer_party_id=developer.id,
            location="Cyberjaya, Selangor",
        )

        project = leads.qualify_lead(
            db, lead=lead, actor_user_id=owner, company_id=company_id
        )

        assert project.lead_id == lead.id
        assert lead.outcome == leads.OUTCOME_QUALIFIED


# --------------------------------------------------- D7: the acceptance handshake


def test_assigning_a_lead_starts_the_clock_without_giving_it_away():
    """AC-A4. The lead reads "awaiting acceptance by Ali", and is NOT his yet."""
    from app.services import project_lead_service as leads

    with blank_session() as db:
        company_id = _seeded(db)
        _allow_no_buyer(db)
        marketing = _user(db, f"{MARKER} Marketing")
        ali = _user(db, f"{MARKER} Ali")

        lead = _lead(db, company_id, marketing)
        before = datetime.utcnow()
        leads.assign_lead(db, lead=lead, owner_user_id=ali)

        assert lead.owner_user_id == ali
        assert lead.acceptance_state == leads.ACCEPTANCE_ASSIGNED
        assert lead.assigned_at is not None and lead.assigned_at >= before
        assert lead.accepted_at is None


def test_the_assignee_accepting_is_what_confers_ownership():
    """AC-A5. Accepted, with the date recorded."""
    from app.services import project_lead_service as leads

    with blank_session() as db:
        company_id = _seeded(db)
        _allow_no_buyer(db)
        marketing = _user(db, f"{MARKER} Marketing")
        ali = _user(db, f"{MARKER} Ali")

        lead = _lead(db, company_id, marketing)
        leads.assign_lead(db, lead=lead, owner_user_id=ali)
        leads.accept_lead(db, lead=lead, actor_user_id=ali)

        assert lead.acceptance_state == leads.ACCEPTANCE_ACCEPTED
        assert lead.accepted_at is not None
        assert lead.owner_user_id == ali
        assert lead.declined_reason is None


def test_declining_puts_the_lead_back_in_the_pool_with_the_reason_on_it():
    """AC-A5. It goes back to marketing rather than dying in his tray.

    ``owner_user_id`` MUST be cleared: a declined lead that kept its owner would sit in
    the refuser's list forever and never appear in the unassigned view.
    """
    from app.services import project_lead_service as leads

    with blank_session() as db:
        company_id = _seeded(db)
        _allow_no_buyer(db)
        marketing = _user(db, f"{MARKER} Marketing")
        ali = _user(db, f"{MARKER} Ali")

        lead = _lead(db, company_id, marketing)
        leads.assign_lead(db, lead=lead, owner_user_id=ali)
        leads.decline_lead(
            db, lead=lead, reason="  Johor, not my patch  ", actor_user_id=ali
        )

        assert lead.acceptance_state == leads.ACCEPTANCE_DECLINED
        assert lead.owner_user_id is None
        assert lead.declined_reason == "Johor, not my patch"
        assert lead.declined_at is not None
        # A decline is a handover failing, NOT the development going away.
        assert lead.outcome == leads.OUTCOME_OPEN


def test_the_marketing_user_who_raised_it_can_hand_a_declined_lead_on():
    """The decline path only works if the lead is re-assignable once it lands.

    A decline clears the owner, and the ordinary edit rule is owner-or-manager -- so
    without the creator exception the person the lead came BACK to could not pass it on.
    """
    from app.services import project_lead_service as leads

    with blank_session() as db:
        company_id = _seeded(db)
        _allow_no_buyer(db)
        marketing = _user(db, f"{MARKER} Marketing")
        ali = _user(db, f"{MARKER} Ali")
        siti = _user(db, f"{MARKER} Siti")

        lead = _lead(db, company_id, marketing)
        leads.assign_lead(db, lead=lead, owner_user_id=ali)
        leads.decline_lead(db, lead=lead, reason="Not my patch", actor_user_id=ali)

        leads.assert_can_assign_lead(lead, marketing, set())
        leads.assign_lead(db, lead=lead, owner_user_id=siti)
        assert lead.owner_user_id == siti


def test_reassigning_resets_the_clock_and_clears_the_earlier_refusal():
    """Siti cannot inherit Ali's silence, and Ali's "wrong patch" must not read as hers."""
    from app.services import project_lead_service as leads

    with blank_session() as db:
        company_id = _seeded(db)
        _allow_no_buyer(db)
        marketing = _user(db, f"{MARKER} Marketing")
        ali = _user(db, f"{MARKER} Ali")
        siti = _user(db, f"{MARKER} Siti")

        lead = _lead(db, company_id, marketing)
        leads.assign_lead(db, lead=lead, owner_user_id=ali)
        leads.decline_lead(db, lead=lead, reason="Not my patch", actor_user_id=ali)

        stale_clock = datetime.utcnow() - timedelta(hours=40)
        lead.assigned_at = stale_clock
        db.flush()

        leads.assign_lead(db, lead=lead, owner_user_id=siti)

        assert lead.owner_user_id == siti
        assert lead.acceptance_state == leads.ACCEPTANCE_ASSIGNED
        assert lead.assigned_at > stale_clock
        assert lead.declined_reason is None
        assert lead.declined_at is None


def test_somebody_who_was_not_handed_the_lead_cannot_accept_it():
    """Ownership by clicking somebody else's Accept is exactly what D7 forbids."""
    from app.services import project_lead_service as leads

    with blank_session() as db:
        company_id = _seeded(db)
        _allow_no_buyer(db)
        marketing = _user(db, f"{MARKER} Marketing")
        ali = _user(db, f"{MARKER} Ali")
        opportunist = _user(db, f"{MARKER} Opportunist")

        lead = _lead(db, company_id, marketing)
        leads.assign_lead(db, lead=lead, owner_user_id=ali)

        with pytest.raises(AppException) as exc:
            leads.accept_lead(db, lead=lead, actor_user_id=opportunist)
        assert exc.value.status_code == 403
        assert exc.value.detail["code"] == "lead_acceptance_not_yours"

        with pytest.raises(AppException) as declining:
            leads.decline_lead(
                db, lead=lead, reason="not mine either", actor_user_id=opportunist
            )
        assert declining.value.status_code == 403

        # Untouched by either refusal: still waiting on Ali.
        assert lead.acceptance_state == leads.ACCEPTANCE_ASSIGNED
        assert lead.owner_user_id == ali


def test_a_manager_can_answer_for_an_assignee_who_has_gone_quiet():
    """Otherwise a lead assigned to somebody on leave is frozen `assigned` forever."""
    from app.services import project_lead_service as leads

    with blank_session() as db:
        company_id = _seeded(db)
        _allow_no_buyer(db)
        marketing = _user(db, f"{MARKER} Marketing")
        ali = _user(db, f"{MARKER} Ali")
        manager = _user(db, f"{MARKER} Manager")

        lead = _lead(db, company_id, marketing)
        leads.assign_lead(db, lead=lead, owner_user_id=ali)

        leads.decline_lead(
            db,
            lead=lead,
            reason="Ali is on leave for three weeks",
            actor_user_id=manager,
            permissions={leads.MANAGE_PERMISSION},
        )
        assert lead.acceptance_state == leads.ACCEPTANCE_DECLINED


def test_accepting_a_lead_nobody_handed_over_is_refused():
    """409, and it says what to do: assign it first."""
    from app.services import project_lead_service as leads

    with blank_session() as db:
        company_id = _seeded(db)
        _allow_no_buyer(db)
        marketing = _user(db, f"{MARKER} Marketing")

        lead = _lead(db, company_id, marketing)

        with pytest.raises(AppException) as exc:
            leads.accept_lead(db, lead=lead, actor_user_id=marketing)
        assert exc.value.status_code == 409
        assert exc.value.detail["code"] == "lead_not_awaiting_acceptance"

        # And accepting twice is the same refusal: the second click is not an event.
        ali = _user(db, f"{MARKER} Ali")
        leads.assign_lead(db, lead=lead, owner_user_id=ali)
        leads.accept_lead(db, lead=lead, actor_user_id=ali)
        with pytest.raises(AppException) as again:
            leads.accept_lead(db, lead=lead, actor_user_id=ali)
        assert again.value.status_code == 409


def test_declining_without_saying_why_is_refused():
    """The reason is routing information for the next assignment, not a formality."""
    from app.services import project_lead_service as leads

    with blank_session() as db:
        company_id = _seeded(db)
        _allow_no_buyer(db)
        marketing = _user(db, f"{MARKER} Marketing")
        ali = _user(db, f"{MARKER} Ali")

        lead = _lead(db, company_id, marketing)
        leads.assign_lead(db, lead=lead, owner_user_id=ali)

        for blank in (None, "", "   "):
            with pytest.raises(AppException) as exc:
                leads.decline_lead(db, lead=lead, reason=blank, actor_user_id=ali)
            assert exc.value.status_code == 422
            assert exc.value.detail["code"] == "lead_decline_reason_required"

        assert lead.acceptance_state == leads.ACCEPTANCE_ASSIGNED
        assert lead.owner_user_id == ali


def test_a_lead_cannot_be_handed_to_nobody_or_to_somebody_who_has_left():
    """A lead assigned to a removed user is a lead the list says is being worked."""
    from app.services import project_lead_service as leads

    with blank_session() as db:
        company_id = _seeded(db)
        _allow_no_buyer(db)
        marketing = _user(db, f"{MARKER} Marketing")
        departed = _user(db, f"{MARKER} Departed", is_trashed=True)

        lead = _lead(db, company_id, marketing)

        with pytest.raises(AppException) as nobody:
            leads.assign_lead(db, lead=lead, owner_user_id="")
        assert nobody.value.status_code == 422

        with pytest.raises(AppException) as unknown:
            leads.assign_lead(db, lead=lead, owner_user_id=_uid())
        assert unknown.value.status_code == 404

        with pytest.raises(AppException) as gone:
            leads.assign_lead(db, lead=lead, owner_user_id=departed)
        assert gone.value.status_code == 422
        assert gone.value.detail["code"] == "lead_assignee_inactive"

        assert lead.acceptance_state is None


# ------------------------------------------------------- AC-A7: the worklist


def test_the_worklist_is_only_unanswered_handovers_newest_first_with_the_wait():
    """AC-A7. "Which of my leads has nobody taken" is one screen, not a question.

    Newest assignment first, because this is the queue marketing works: the oldest rows
    are the ones already chased. Every row carries the wait so the screen does no date
    maths.
    """
    from app.services import project_lead_service as leads

    with blank_session() as db:
        company_id = _seeded(db)
        _allow_no_buyer(db)
        marketing = _user(db, f"{MARKER} Marketing")
        ali = _user(db, f"{MARKER} Ali")
        siti = _user(db, f"{MARKER} Siti")

        just_now = _lead(db, company_id, marketing, title=f"{MARKER} assigned just now")
        leads.assign_lead(db, lead=just_now, owner_user_id=ali)

        since_tuesday = _lead(db, company_id, marketing, title=f"{MARKER} waiting days")
        leads.assign_lead(db, lead=since_tuesday, owner_user_id=siti)
        since_tuesday.assigned_at = datetime.utcnow() - timedelta(hours=30)

        accepted = _lead(db, company_id, marketing, title=f"{MARKER} taken")
        leads.assign_lead(db, lead=accepted, owner_user_id=ali)
        leads.accept_lead(db, lead=accepted, actor_user_id=ali)

        declined = _lead(db, company_id, marketing, title=f"{MARKER} refused")
        leads.assign_lead(db, lead=declined, owner_user_id=ali)
        leads.decline_lead(db, lead=declined, reason="Wrong patch", actor_user_id=ali)

        never_assigned = _lead(db, company_id, marketing, title=f"{MARKER} untouched")
        db.flush()

        result = leads.awaiting_acceptance(db, company_id=company_id)

        assert result["total"] == 2
        ids = [row["id"] for row in result["data"]]
        assert ids == [just_now.id, since_tuesday.id]
        assert accepted.id not in ids
        assert declined.id not in ids
        assert never_assigned.id not in ids

        waits = {row["id"]: row["hours_since_assigned"] for row in result["data"]}
        assert waits[just_now.id] < 1
        assert 29.5 < waits[since_tuesday.id] < 30.5
        # The owner is named, not identified by id (no UUID reaches the UI).
        assert result["data"][0]["owner_name"] == f"{MARKER} Ali"


def test_the_worklist_narrows_to_one_salesperson_and_to_a_minimum_wait():
    """The two questions marketing actually asks of it (contract: owner_user_id, min_hours)."""
    from app.services import project_lead_service as leads

    with blank_session() as db:
        company_id = _seeded(db)
        _allow_no_buyer(db)
        marketing = _user(db, f"{MARKER} Marketing")
        ali = _user(db, f"{MARKER} Ali")
        siti = _user(db, f"{MARKER} Siti")

        fresh = _lead(db, company_id, marketing, title=f"{MARKER} fresh")
        leads.assign_lead(db, lead=fresh, owner_user_id=ali)

        stale = _lead(db, company_id, marketing, title=f"{MARKER} stale")
        leads.assign_lead(db, lead=stale, owner_user_id=siti)
        stale.assigned_at = datetime.utcnow() - timedelta(hours=26)
        db.flush()

        mine = leads.awaiting_acceptance(db, company_id=company_id, owner_user_id=[ali])
        assert [row["id"] for row in mine["data"]] == [fresh.id]

        overdue = leads.awaiting_acceptance(db, company_id=company_id, min_hours=24)
        assert [row["id"] for row in overdue["data"]] == [stale.id]

        # min_hours 0 is the default and must not filter anything out.
        assert leads.awaiting_acceptance(db, company_id=company_id, min_hours=0)["total"] == 2


def test_the_ordinary_list_can_be_filtered_by_handshake_state():
    """AC-A7's other half: "what became of the ones that were taken"."""
    from app.services import project_lead_service as leads

    with blank_session() as db:
        company_id = _seeded(db)
        _allow_no_buyer(db)
        marketing = _user(db, f"{MARKER} Marketing")
        ali = _user(db, f"{MARKER} Ali")

        taken = _lead(db, company_id, marketing, title=f"{MARKER} taken")
        leads.assign_lead(db, lead=taken, owner_user_id=ali)
        leads.accept_lead(db, lead=taken, actor_user_id=ali)

        refused = _lead(db, company_id, marketing, title=f"{MARKER} refused")
        leads.assign_lead(db, lead=refused, owner_user_id=ali)
        leads.decline_lead(db, lead=refused, reason="Wrong patch", actor_user_id=ali)
        db.flush()

        accepted = leads.list_leads(
            db, company_id=company_id, acceptance_state=[leads.ACCEPTANCE_ACCEPTED]
        )
        assert [row["id"] for row in accepted["data"]] == [taken.id]

        declined = leads.list_leads(
            db, company_id=company_id, acceptance_state=[leads.ACCEPTANCE_DECLINED]
        )
        assert [row["id"] for row in declined["data"]] == [refused.id]


# ------------------------------------------------------------ notifications


@pytest.fixture()
def _no_queue(monkeypatch):
    """No Redis, no worker. The delivery rows are what this file asserts on."""
    from app.services import queue_service

    monkeypatch.setattr(queue_service, "enqueue_job", lambda *a, **k: None)


def test_the_assignee_gets_one_notification_with_enough_on_it_to_decide(_no_queue):
    """Journey step 2: the development, the developer and the value, in one message.

    Anything less and Ali opens the record just to decide whether to care.
    """
    from app.services import project_lead_service as leads

    with blank_session() as db:
        company_id = _seeded(db)
        _allow_no_buyer(db)
        marketing = _user(db, f"{MARKER} Marketing")
        ali = _user(db, f"{MARKER} Ali")
        developer = _party(db, company_id, f"{MARKER} Tuju Setia", party_type="developer")

        lead = _lead(
            db,
            company_id,
            marketing,
            title="Maryam Tuju Residence",
            developer_party_id=developer.id,
            estimated_value="1810640.62",
        )
        leads.assign_lead(db, lead=lead, owner_user_id=ali)
        db.flush()

        sent = leads.notify_lead_assigned(
            db, lead=lead, actor_user_id=marketing, note="BCI says tender closes Friday"
        )
        assert sent == 1

        notification = (
            db.query(Notification)
            .filter(
                Notification.source_entity_type == leads.LEAD_ENTITY_TYPE,
                Notification.source_entity_id == lead.id,
            )
            .one()
        )
        assert notification.user_id == ali
        assert lead.lead_code in notification.title
        assert "Maryam Tuju Residence" in (notification.body or "")
        assert f"{MARKER} Tuju Setia" in (notification.body or "")
        assert "1810640.62" in (notification.body or "")
        assert "tender closes Friday" in (notification.body or "")
        assert notification.data.get("lead_code") == lead.lead_code


def test_a_decline_is_reported_back_to_whoever_raised_the_lead(_no_queue):
    """A decline nobody hears about is the tray D7 exists to escape."""
    from app.services import project_lead_service as leads

    with blank_session() as db:
        company_id = _seeded(db)
        _allow_no_buyer(db)
        marketing = _user(db, f"{MARKER} Marketing")
        ali = _user(db, f"{MARKER} Ali")

        lead = _lead(db, company_id, marketing)
        leads.assign_lead(db, lead=lead, owner_user_id=ali)
        leads.decline_lead(db, lead=lead, reason="Johor, not my patch", actor_user_id=ali)
        db.flush()

        sent = leads.notify_lead_declined(db, lead=lead, actor_user_id=ali)
        assert sent == 1

        notification = (
            db.query(Notification)
            .filter(
                Notification.source_entity_type == leads.LEAD_ENTITY_TYPE,
                Notification.source_entity_id == lead.id,
                Notification.event_type == "project_lead_declined",
            )
            .one()
        )
        assert notification.user_id == marketing
        assert "Johor, not my patch" in (notification.body or "")
        assert f"{MARKER} Ali" in (notification.body or "")


def test_a_notification_failure_never_undoes_the_handover(monkeypatch):
    """Post-commit side effects are best-effort, always.

    The assign has already committed by the time this runs. A 500 here would report a
    failure for something that happened, and the retry would assign it twice.
    """
    from app.services import notification_service
    from app.services import project_lead_service as leads

    def _boom(*args, **kwargs):
        raise RuntimeError("notification backend down")

    monkeypatch.setattr(
        notification_service.NotificationService,
        "create_with_channel_preferences",
        _boom,
    )

    with blank_session() as db:
        company_id = _seeded(db)
        _allow_no_buyer(db)
        marketing = _user(db, f"{MARKER} Marketing")
        ali = _user(db, f"{MARKER} Ali")

        lead = _lead(db, company_id, marketing)
        leads.assign_lead(db, lead=lead, owner_user_id=ali)
        db.flush()

        assert leads.notify_lead_assigned(db, lead=lead, actor_user_id=marketing) == 0
        assert lead.acceptance_state == leads.ACCEPTANCE_ASSIGNED
        assert lead.owner_user_id == ali


# --------------------------------------------------------------- over HTTP
#
# The wiring between HTTP and the service is code too. Two things here can only fail at
# this seam: /leads/awaiting-acceptance being swallowed by /leads/{lead_id}, and the
# response model dropping a field the service returns.


BASE = "/api/v1/project-sales/leads"

# No `projects.projects.manage`, deliberately: with it every acceptance check passes and
# the "not yours" refusal could never be observed through the API.
_SLUGS = [
    "projects.projects.view",
    "projects.projects.create",
    "projects.projects.edit",
    "projects.projects.delete",
]


@pytest.fixture()
def api(monkeypatch):
    """One session shared by the test and the routes, with the company scope pinned.

    The scope normally comes from the request middleware, which the dependency override
    bypasses, and ``acting_company_id`` fails closed on an unresolved scope exactly as it
    should. Pinning it is what the middleware would have done.
    """
    from fastapi.testclient import TestClient

    from app.database import get_db
    from app.dependencies import get_current_user, get_current_user_or_api_key
    from app.main import app
    from app.models.base import company_scope
    from app.services import queue_service
    from app.services.company_scope_resolver import apply_company_scope
    from app.services.user_service import UserPermissionService

    monkeypatch.setattr(queue_service, "enqueue_job", lambda *a, **k: None)

    with blank_session() as db:
        company_id = _seeded(db)
        _allow_no_buyer(db)
        marketing = _user(db, f"{MARKER} Marketing")

        actor = {"id": marketing}

        def _act_as(user_id: str) -> None:
            actor["id"] = user_id

        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[get_current_user] = lambda: {
            "id": actor["id"],
            "email": f"{actor['id']}@zzt.test",
            "role": "user",
        }
        app.dependency_overrides[get_current_user_or_api_key] = (
            app.dependency_overrides[get_current_user]
        )
        app.dependency_overrides[apply_company_scope] = lambda: None

        original_check = UserPermissionService.check_user_has_permission
        original_slugs = UserPermissionService.get_user_permission_slugs
        UserPermissionService.check_user_has_permission = lambda self, uid, slug: True
        UserPermissionService.get_user_permission_slugs = lambda self, uid: list(_SLUGS)

        try:
            with company_scope(db, frozenset({company_id})):
                yield TestClient(app), db, company_id, marketing, _act_as
        finally:
            UserPermissionService.check_user_has_permission = original_check
            UserPermissionService.get_user_permission_slugs = original_slugs
            app.dependency_overrides.clear()


def test_the_handshake_round_trips_over_http(api):
    """Create with no buyer, assign, refuse somebody else's Accept, accept, all through
    FastAPI. The acceptance columns and the informant have to survive the response model."""
    client, db, company_id, marketing, act_as = api
    ali = _user(db, f"{MARKER} Ali")
    firm = _party(db, company_id, f"{MARKER} BCI Asia")

    created = client.post(
        BASE,
        json={
            "title": "Maryam Tuju Residence",
            "location": "Cyberjaya, Selangor",
            "informant_source": "bci",
            "informant_ref": "BCI-2026-114523",
            "informant_party_id": firm.id,
        },
    )
    assert created.status_code == 201, created.text
    lead = created.json()
    assert lead["customer_id"] is None
    assert lead["customer_name"] is None
    assert lead["informant_party_label"] == f"{MARKER} BCI Asia"
    assert lead["acceptance_state"] is None

    assigned = client.post(f"{BASE}/{lead['id']}/assign", json={"owner_user_id": ali})
    assert assigned.status_code == 200, assigned.text
    assert assigned.json()["acceptance_state"] == "assigned"
    assert assigned.json()["assigned_at"] is not None
    assert assigned.json()["owner_name"] == f"{MARKER} Ali"

    # The person who handed it over is not the person who answers for it.
    refused = client.post(f"{BASE}/{lead['id']}/accept")
    assert refused.status_code == 403, refused.text

    act_as(ali)
    accepted = client.post(f"{BASE}/{lead['id']}/accept")
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["acceptance_state"] == "accepted"
    assert accepted.json()["accepted_at"] is not None


def test_declining_over_http_returns_the_lead_to_the_pool(api):
    client, db, _company_id, marketing, act_as = api
    ali = _user(db, f"{MARKER} Ali")

    lead = client.post(BASE, json={"title": f"{MARKER} Johor tower"}).json()
    client.post(f"{BASE}/{lead['id']}/assign", json={"owner_user_id": ali})

    act_as(ali)
    empty = client.post(f"{BASE}/{lead['id']}/decline", json={"reason": ""})
    assert empty.status_code == 422, empty.text

    declined = client.post(
        f"{BASE}/{lead['id']}/decline", json={"reason": "Johor, not my patch"}
    )
    assert declined.status_code == 200, declined.text
    body = declined.json()
    assert body["acceptance_state"] == "declined"
    assert body["owner_user_id"] is None
    assert body["declined_reason"] == "Johor, not my patch"

    # The route fires the notification AFTER its commit, so the refusal reaches the
    # person who handed it over rather than dying in Ali's tray.
    told = (
        db.query(Notification)
        .filter(
            Notification.source_entity_id == lead["id"],
            Notification.event_type == "project_lead_declined",
        )
        .all()
    )
    assert [row.user_id for row in told] == [marketing]

    # And accepting it now is a 409, not a silent re-grab.
    assert client.post(f"{BASE}/{lead['id']}/accept").status_code == 409


def test_the_worklist_endpoint_is_not_swallowed_by_the_lead_id_route(api):
    """`/leads/awaiting-acceptance` must be declared BEFORE `/leads/{lead_id}`.

    Reading it as a lead id is the classic failure here, and it surfaces as a 404 or a
    422 on a path that looks correct.
    """
    client, db, _company_id, _marketing, _act_as = api
    ali = _user(db, f"{MARKER} Ali")

    lead = client.post(BASE, json={"title": f"{MARKER} awaiting"}).json()
    client.post(f"{BASE}/{lead['id']}/assign", json={"owner_user_id": ali})

    response = client.get(f"{BASE}/awaiting-acceptance")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["pagination"]["total"] == 1
    row = body["data"][0]
    assert row["id"] == lead["id"]
    assert row["hours_since_assigned"] is not None
    assert row["hours_since_assigned"] < 1
    assert row["owner_name"] == f"{MARKER} Ali"

    # Filtered to somebody else, the worklist is empty rather than wrong.
    other = client.get(f"{BASE}/awaiting-acceptance", params={"owner_user_id": [_uid()]})
    assert other.status_code == 200
    assert other.json()["pagination"]["total"] == 0
    assert other.json()["empty"] is True
