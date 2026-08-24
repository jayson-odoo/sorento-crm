"""S2c leads (UAC Group O).

A lead is a rumour. That single fact drives every rule tested here: it is NOT
exclusive (several salespeople may record the same sighting), it requires a customer
because somebody told us about it, and ownership only locks when it is QUALIFIED into
a project, which is the moment the registration clash check finally runs.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from app.models.order import Customer
from app.models.projects import ProjectParty, ProjectSalesProfile
from app.models.user import User
from app.services.error_handler import AppException

from ._pg_fixture import blank_session

MARKER = "zzt-lead"


def _uid() -> str:
    return str(uuid.uuid4())


def _sorento(db) -> str:
    return db.execute(text("select id from companies where code = 'SRT'")).scalar()


def _user(db, name: str) -> str:
    user_id = _uid()
    db.add(User(id=user_id, email=f"{user_id}@zzt.test", name=name))
    db.flush()
    return user_id


def _numbering_rule(db, doc_type: str, prefix: str) -> None:
    db.execute(
        text(
            "insert into document_numbering_rules "
            "(id, doc_type, enabled, prefix_template, number_digits, next_value, "
            " start_value, reset_policy) "
            "values (:id, :doc_type, true, :prefix, 6, 1, 1, 'none')"
        ),
        {"id": _uid(), "doc_type": doc_type, "prefix": prefix},
    )
    db.flush()


def _customer(db, company_id: str, name: str) -> Customer:
    customer = Customer(
        id=_uid(),
        company_id=company_id,
        customer_code=f"ZZT-{name[:6]}",
        customer_name=name,
    )
    db.add(customer)
    db.flush()
    return customer


def _developer(db, company_id: str, name: str) -> ProjectParty:
    party = ProjectParty(id=_uid(), company_id=company_id, party_type="developer", name=name)
    db.add(party)
    db.flush()
    return party


def test_creating_a_lead_stamps_a_code_and_its_initial_status():
    from app.services import project_lead_service as leads
    from app.services import project_seed_service

    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        owner = _user(db, f"{MARKER} Ali")
        customer = _customer(db, company_id, f"{MARKER} Khoo Soon Lee")

        lead = leads.create_lead(
            db,
            company_id=company_id,
            actor_user_id=owner,
            payload={
                "customer_id": customer.id,
                "title": "Rumoured tower behind the Setia showroom",
                "source": "site_visit",
                "estimated_value": "750000.00",
            },
        )

        assert lead.lead_code.startswith("LEAD-")
        assert lead.owner_user_id == owner
        assert lead.outcome == leads.OUTCOME_OPEN
        # The status engine assigns the rung; the service must not invent one.
        assert lead.status_id is not None


def test_a_lead_needs_no_buyer_because_nobody_knows_one_yet():
    """AC-A1 replaces AC-O1, which required a customer on every lead.

    That premise conflated two different people: whoever mentioned the job, and
    whoever will eventually place the order. The first is now recorded as the
    informant, which is never a `customers` row because a data source is not a
    debtor. Requiring a buyer here meant inventing a customer to get past the form,
    which is how a pipeline fills up with debtors that never bought anything.
    """
    from app.services import project_lead_service as leads
    from app.services import project_seed_service

    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        owner = _user(db, f"{MARKER} Ali")

        lead = leads.create_lead(
            db,
            company_id=company_id,
            actor_user_id=owner,
            payload={
                "title": "Someone heard something",
                "informant_source": "architect",
                "informant_contact_name": "Ar. Nurul Huda",
            },
        )

        assert lead.customer_id is None
        assert lead.informant_contact_name == "Ar. Nurul Huda"


# ------------------------------------------------------------------ qualify


def test_qualifying_creates_a_project_carrying_the_lead():
    """AC-O4. Qualify is where a rumour becomes a claim and ownership locks."""
    from app.services import project_lead_service as leads
    from app.services import project_seed_service

    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        owner = _user(db, f"{MARKER} Ali")
        customer = _customer(db, company_id, f"{MARKER} Khoo Soon Lee")
        developer = _developer(db, company_id, f"{MARKER} Setia")

        lead = leads.create_lead(
            db,
            company_id=company_id,
            actor_user_id=owner,
            payload={
                "customer_id": customer.id,
                "developer_party_id": developer.id,
                "title": "Setia Alam Phase 9",
                "location": "Setia Alam, Selangor",
                "estimated_value": "900000.00",
            },
        )

        project = leads.qualify_lead(
            db, lead=lead, actor_user_id=owner, company_id=company_id
        )

        assert project.lead_id == lead.id
        assert project.title == "Setia Alam Phase 9"
        assert project.developer_party_id == developer.id
        assert project.owner_user_id == owner
        assert lead.outcome == leads.OUTCOME_QUALIFIED
        assert lead.qualified_at is not None
        # What the lead already knew is carried, not re-asked (the whole point).
        profile = (
            db.query(ProjectSalesProfile)
            .filter(ProjectSalesProfile.project_id == project.id)
            .first()
        )
        assert profile is not None
        assert profile.location == "Setia Alam, Selangor"
        assert str(profile.estimated_sales_value) == "900000.00"


def test_qualifying_onto_somebody_elses_registration_is_blocked_and_the_lead_stays_open():
    """The lock applies at qualify, not at sighting.

    And a block must NOT close the lead: the recourse is join-or-dispute on the
    existing project, and the lead is the user's own record of why they were asking.
    """
    from app.services import project_lead_service as leads
    from app.services import project_seed_service
    from app.services.project_service import register_project

    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        incumbent = _user(db, f"{MARKER} Siti")
        latecomer = _user(db, f"{MARKER} Ali")
        customer = _customer(db, company_id, f"{MARKER} Informant")
        developer = _developer(db, company_id, f"{MARKER} Setia")

        register_project(
            db,
            company_id=company_id,
            actor_user_id=incumbent,
            developer_party_id=developer.id,
            title="Setia Alam Phase 9",
        )

        lead = leads.create_lead(
            db,
            company_id=company_id,
            actor_user_id=latecomer,
            payload={
                "customer_id": customer.id,
                "developer_party_id": developer.id,
                "title": "Setia Alam Ph 9",
            },
        )

        with pytest.raises(AppException) as exc:
            leads.qualify_lead(
                db, lead=lead, actor_user_id=latecomer, company_id=company_id
            )

        assert exc.value.status_code == 409
        assert lead.outcome == leads.OUTCOME_OPEN
        assert lead.qualified_at is None


def test_one_lead_can_yield_several_projects():
    """AC-O5: a masterplan sighting becomes one registration per phase."""
    from app.services import project_lead_service as leads
    from app.services import project_seed_service

    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        owner = _user(db, f"{MARKER} Ali")
        customer = _customer(db, company_id, f"{MARKER} Informant")
        developer = _developer(db, company_id, f"{MARKER} Setia")

        lead = leads.create_lead(
            db,
            company_id=company_id,
            actor_user_id=owner,
            payload={
                "customer_id": customer.id,
                "developer_party_id": developer.id,
                "title": "Setia Alam masterplan",
            },
        )

        first = leads.qualify_lead(
            db,
            lead=lead,
            actor_user_id=owner,
            company_id=company_id,
            project_payload={"title": "Setia Alam Phase 1"},
        )
        first_qualified_at = lead.qualified_at

        second = leads.qualify_lead(
            db,
            lead=lead,
            actor_user_id=owner,
            company_id=company_id,
            project_payload={"title": "Setia Alam Phase 2"},
        )

        assert first.id != second.id
        assert first.lead_id == second.lead_id == lead.id
        # qualified_at marks the FIRST conversion, which is what the rate measures.
        assert lead.qualified_at == first_qualified_at


def test_the_qualify_preview_reports_a_block_before_the_user_commits():
    from app.services import project_lead_service as leads
    from app.services import project_seed_service
    from app.services.project_service import register_project

    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        incumbent = _user(db, f"{MARKER} Siti")
        latecomer = _user(db, f"{MARKER} Ali")
        customer = _customer(db, company_id, f"{MARKER} Informant")
        developer = _developer(db, company_id, f"{MARKER} Setia")

        register_project(
            db,
            company_id=company_id,
            actor_user_id=incumbent,
            developer_party_id=developer.id,
            title="Setia Alam Phase 9",
        )
        lead = leads.create_lead(
            db,
            company_id=company_id,
            actor_user_id=latecomer,
            payload={
                "customer_id": customer.id,
                "developer_party_id": developer.id,
                "title": "Setia Alam Phase 9",
            },
        )

        preview = leads.preview_qualify_clashes(
            db, lead=lead, company_id=company_id
        )

        assert preview["would_block"] is True
        assert preview["candidates"][0].owner_user_id == incumbent


# --------------------------------------------------------------- disqualify


def _open_lead(db, company_id, owner, title="A sighting"):
    from app.services import project_lead_service as leads

    customer = _customer(db, company_id, f"{MARKER} {title[:8]}")
    return leads.create_lead(
        db,
        company_id=company_id,
        actor_user_id=owner,
        payload={"customer_id": customer.id, "title": title},
    )


def test_disqualifying_requires_a_reason_from_the_lookup():
    """AC-O6. Free text cannot be reported on: "not interested" typed nine ways is
    nine buckets in the conversion report."""
    from app.services import project_lead_service as leads
    from app.services import project_seed_service

    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        owner = _user(db, f"{MARKER} Ali")
        lead = _open_lead(db, company_id, owner)

        with pytest.raises(AppException) as missing:
            leads.disqualify_lead(db, lead=lead, reason=None)
        assert missing.value.status_code == 422

        with pytest.raises(AppException) as invented:
            leads.disqualify_lead(db, lead=lead, reason="couldnt be bothered")
        assert invented.value.status_code == 422

        # Untouched by either refusal.
        assert lead.outcome == leads.OUTCOME_OPEN
        assert lead.disqualified_reason is None

        leads.disqualify_lead(db, lead=lead, reason="budget")
        assert lead.outcome == leads.OUTCOME_DISQUALIFIED
        assert lead.disqualified_reason == "budget"


def test_only_a_disqualified_lead_can_be_reopened():
    """A qualified lead has a project behind it; reopening would orphan it."""
    from app.services import project_lead_service as leads
    from app.services import project_seed_service

    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        owner = _user(db, f"{MARKER} Ali")

        disqualified = _open_lead(db, company_id, owner, title="Dead rumour")
        leads.disqualify_lead(db, lead=disqualified, reason="no_project")
        leads.reopen_lead(db, disqualified)
        assert disqualified.outcome == leads.OUTCOME_OPEN
        assert disqualified.disqualified_reason is None

        qualified = _open_lead(db, company_id, owner, title="Live rumour")
        leads.qualify_lead(
            db, lead=qualified, actor_user_id=owner, company_id=company_id
        )
        with pytest.raises(AppException) as exc:
            leads.reopen_lead(db, qualified)
        assert exc.value.status_code == 422


def test_the_two_terminal_rungs_cannot_be_reached_by_a_bare_status_move():
    """Qualified with no project behind it, or disqualified with no reason, is a lie
    the report then repeats."""
    from app.models.status import Status
    from app.services import project_lead_service as leads
    from app.services import project_seed_service

    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        owner = _user(db, f"{MARKER} Ali")
        lead = _open_lead(db, company_id, owner)

        for key in ("qualified", "disqualified"):
            target = (
                db.query(Status)
                .filter(
                    Status.entity_type == "project_lead",
                    Status.scope_id.is_(None),
                    Status.key == key,
                )
                .first()
            )
            with pytest.raises(AppException) as exc:
                leads.change_lead_status(db, lead, target.id)
            assert exc.value.status_code == 422

        # An ordinary rung still moves.
        contacted = (
            db.query(Status)
            .filter(
                Status.entity_type == "project_lead",
                Status.scope_id.is_(None),
                Status.key == "contacted",
            )
            .first()
        )
        leads.change_lead_status(db, lead, contacted.id)
        assert lead.status_id == contacted.id


def test_conversion_rate_is_measured_against_decided_leads_only():
    """Counting this morning's new leads as failures would make the rate fall every
    time somebody records one."""
    from app.services import project_lead_service as leads
    from app.services import project_seed_service

    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        owner = _user(db, f"{MARKER} Ali")

        won = _open_lead(db, company_id, owner, title="Converted one")
        leads.qualify_lead(db, lead=won, actor_user_id=owner, company_id=company_id)
        lost = _open_lead(db, company_id, owner, title="Dead one")
        leads.disqualify_lead(db, lead=lost, reason="budget")
        _open_lead(db, company_id, owner, title="Still open")

        metrics = leads.conversion_metrics(db, company_id=company_id)

        assert metrics["total"] == 3
        assert metrics["open"] == 1
        assert metrics["qualified"] == 1
        assert metrics["disqualified"] == 1
        assert metrics["decided"] == 2
        assert metrics["conversion_rate"] == 0.5
        assert metrics["projects_from_leads"] == 1
        assert metrics["disqualified_reasons"] == [
            {"value": "budget", "label": "Budget too low", "count": 1}
        ]


def test_the_conversion_rate_is_none_rather_than_zero_when_nothing_is_decided():
    """Zero would read as "we convert nothing"; None reads as "no data yet"."""
    from app.services import project_lead_service as leads
    from app.services import project_seed_service

    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        owner = _user(db, f"{MARKER} Ali")
        _open_lead(db, company_id, owner)

        metrics = leads.conversion_metrics(db, company_id=company_id)

        assert metrics["decided"] == 0
        assert metrics["conversion_rate"] is None


# ------------------------------------------------- account view + provenance


def test_a_project_reports_the_lead_it_came_from_and_the_lead_its_projects():
    """AC-O9 / AC-O10. Both directions, because both screens ask.

    The project detail states where the pursuit came from; the customer account view
    lists what that customer's tip-offs turned into.
    """
    from app.services import project_lead_service as leads
    from app.services import project_seed_service
    from app.services import project_service as projects

    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        owner = _user(db, f"{MARKER} Ali")
        customer = _customer(db, company_id, f"{MARKER} Informant")

        lead = leads.create_lead(
            db,
            company_id=company_id,
            actor_user_id=owner,
            payload={
                "customer_id": customer.id,
                "title": "Tower behind the showroom",
                "source": "site_visit",
            },
        )
        project = leads.qualify_lead(
            db, lead=lead, actor_user_id=owner, company_id=company_id
        )

        row = projects.serialize_projects(db, [project])[0]
        assert row["lead_id"] == lead.id
        assert row["lead_code"] == lead.lead_code
        assert row["lead_source"] == "site_visit"

        mine = leads.leads_for_customer(db, customer_id=customer.id)
        assert [item.id for item in mine] == [lead.id]

        serialised = leads.serialize_leads(db, mine)
        assert serialised[0]["project_count"] == 1


def test_a_directly_registered_project_says_so_rather_than_showing_a_blank():
    from app.services import project_seed_service
    from app.services import project_service as projects
    from app.services.project_service import register_project

    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        owner = _user(db, f"{MARKER} Ali")

        project = register_project(
            db,
            company_id=company_id,
            actor_user_id=owner,
            developer_party_id=None,
            title="Walked in off a tender notice",
        )

        row = projects.serialize_projects(db, [project])[0]
        assert row["lead_id"] is None
        assert row["lead_code"] is None


def test_deleting_a_lead_leaves_its_project_standing():
    """`projects.lead_id` is ON DELETE SET NULL: deleting a rumour must never take a
    live registration with it."""
    from app.models.projects import Project
    from app.services import project_lead_service as leads
    from app.services import project_seed_service

    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        owner = _user(db, f"{MARKER} Ali")
        lead = _open_lead(db, company_id, owner, title="Doomed lead")
        project = leads.qualify_lead(
            db, lead=lead, actor_user_id=owner, company_id=company_id
        )
        project_id = project.id

        leads.delete_lead(db, lead)
        db.flush()
        db.expire_all()

        survivor = db.query(Project).filter(Project.id == project_id).first()
        assert survivor is not None
        assert survivor.lead_id is None


def test_near_duplicate_leads_are_surfaced_but_never_blocked():
    """AC-O3: two salespeople reading the same signboard both get to record it."""
    from app.services import project_lead_service as leads
    from app.services import project_seed_service

    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        first = _user(db, f"{MARKER} Ali")
        second = _user(db, f"{MARKER} Siti")
        customer = _customer(db, company_id, f"{MARKER} Informant")

        payload = {"customer_id": customer.id, "title": "Tower on Jalan Ampang"}
        one = leads.create_lead(
            db, company_id=company_id, actor_user_id=first, payload=dict(payload)
        )
        # Same development, different person, different casing. Both are created.
        two = leads.create_lead(
            db,
            company_id=company_id,
            actor_user_id=second,
            payload={**payload, "title": "TOWER ON  JALAN AMPANG"},
        )

        assert one.id != two.id
        assert one.normalised_title == two.normalised_title

        rows = leads.serialize_leads(db, [one, two], with_duplicate_hints=True)
        hints = {row["id"]: row["possible_duplicates"] for row in rows}
        assert [hint["lead_id"] for hint in hints[one.id]] == [two.id]
        assert [hint["lead_id"] for hint in hints[two.id]] == [one.id]


def test_a_disqualified_lead_stops_being_a_duplicate_hint():
    """A dead rumour is not a competing claim, so it must not keep warning people."""
    from app.services import project_lead_service as leads
    from app.services import project_seed_service

    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        owner = _user(db, f"{MARKER} Ali")
        customer = _customer(db, company_id, f"{MARKER} Informant")

        payload = {"customer_id": customer.id, "title": "Tower on Jalan Ampang"}
        alive = leads.create_lead(
            db, company_id=company_id, actor_user_id=owner, payload=dict(payload)
        )
        dead = leads.create_lead(
            db, company_id=company_id, actor_user_id=owner, payload=dict(payload)
        )
        leads.disqualify_lead(db, lead=dead, reason="duplicate")

        rows = leads.serialize_leads(db, [alive], with_duplicate_hints=True)
        assert rows[0]["possible_duplicates"] == []


def test_the_wizard_reuses_an_existing_customer_rather_than_duplicating_it():
    """Without this, "Gamuda Land" and "GAMUDA LAND" become two prospects and the
    account view splits in half."""
    from app.services import project_lead_service as leads
    from app.services import project_seed_service

    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        owner = _user(db, f"{MARKER} Ali")
        existing = _customer(db, company_id, f"{MARKER} Gamuda Land")

        reused = leads.select_or_create_customer(
            db,
            company_id=company_id,
            actor_user_id=owner,
            new_customer={"customer_name": f"{MARKER} GAMUDA LAND  "},
        )
        assert reused.id == existing.id

        created = leads.select_or_create_customer(
            db,
            company_id=company_id,
            actor_user_id=owner,
            new_customer={"customer_name": f"{MARKER} Brand New Developer"},
        )
        assert created.id != existing.id
        # Marked so order and invoice pickers can filter prospects out (plan §5a).
        assert created.source == "project_lead"
        assert created.customer_code


def test_the_customer_portfolio_spans_both_routes_a_project_can_arrive_by():
    """AC-O9. A customer's projects are NOT one join.

    Two independent routes reach the same customer, and a section that shows only one
    of them under-reports the account:
    - a project whose DEVELOPER party is bridged to that customer, and
    - a project qualified out of one of that customer's leads (the informant may be
        an architect who never buys anything).
    """
    from app.services import project_lead_service as leads
    from app.services import project_seed_service
    from app.services.project_service import register_project

    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        owner = _user(db, f"{MARKER} Ali")

        buyer = _customer(db, company_id, f"{MARKER} Buying Developer")
        developer = _developer(db, company_id, f"{MARKER} Buying Developer Sdn")
        developer.customer_id = buyer.id
        db.flush()

        by_developer = register_project(
            db,
            company_id=company_id,
            actor_user_id=owner,
            developer_party_id=developer.id,
            title="Bridged by the developer party",
        )

        informant = _customer(db, company_id, f"{MARKER} Architect Informant")
        lead = leads.create_lead(
            db,
            company_id=company_id,
            actor_user_id=owner,
            payload={"customer_id": informant.id, "title": "Tip-off tower"},
        )
        by_lead = leads.qualify_lead(
            db, lead=lead, actor_user_id=owner, company_id=company_id
        )

        buyer_view = leads.customer_portfolio(db, customer_id=buyer.id)
        assert [row["id"] for row in buyer_view["projects"]] == [by_developer.id]
        assert buyer_view["leads"] == []

        informant_view = leads.customer_portfolio(db, customer_id=informant.id)
        assert [row["id"] for row in informant_view["projects"]] == [by_lead.id]
        assert [row["id"] for row in informant_view["leads"]] == [lead.id]


def test_the_customer_portfolio_never_lists_a_project_twice():
    """When both routes point at the same project, it is still one row."""
    from app.services import project_lead_service as leads
    from app.services import project_seed_service

    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        owner = _user(db, f"{MARKER} Ali")

        customer = _customer(db, company_id, f"{MARKER} Both Routes")
        developer = _developer(db, company_id, f"{MARKER} Both Routes Sdn")
        developer.customer_id = customer.id
        db.flush()

        lead = leads.create_lead(
            db,
            company_id=company_id,
            actor_user_id=owner,
            payload={
                "customer_id": customer.id,
                "developer_party_id": developer.id,
                "title": "Reachable two ways",
            },
        )
        project = leads.qualify_lead(
            db, lead=lead, actor_user_id=owner, company_id=company_id
        )

        view = leads.customer_portfolio(db, customer_id=customer.id)
        assert [row["id"] for row in view["projects"]] == [project.id]
