"""Phase 3 fix S2: portal company resolution never widens past the request's own scope.

`_resolve_company` used to trust `agent.company_id` unconditionally, and fell back to an
unordered `Company.first()` when the agent had none - either can hand a NEW prospect a company
that has nothing to do with the contact this request is for. "The contact's companies" is
modelled here the way `_require_agent` now establishes it: a `company_scope(...)` already active
on the session by the time `_resolve_company` runs. An agent whose OWN `company_id` disagrees
with that active scope must not widen it - the created record still lands in, and is found
through, the scope the request is actually confined to (this also covers reviewer should-fix 10,
the same "visible in the contact's own list" property).
"""
from __future__ import annotations

import uuid

from app.models.base import company_scope

from ._pg_fixture import blank_session


def _uid() -> str:
    return str(uuid.uuid4())


def _company(db, *, name: str) -> str:
    from app.models.company import Company

    company = Company(id=_uid(), name=name, code=f"ZZT{_uid()[:6].upper()}")
    db.add(company)
    db.flush()
    return company.id


def test_fix_s2_agent_company_outside_the_active_scope_does_not_widen_it():
    from app.api.v1.public.portal_sales_opportunity import _resolve_company
    from app.models.sales_agent import SalesAgent

    with blank_session() as db:
        contacts_company = _company(db, name="ZZT S2 Contact's Company")
        agents_other_company = _company(db, name="ZZT S2 Agent's Other Company")
        agent = SalesAgent(
            id=_uid(),
            sales_agent="ZZO-S2",
            description="ZZT S2 Agent",
            is_active=True,
            company_id=agents_other_company,
        )
        db.add(agent)
        db.flush()

        # The request is already confined to the contact's own company - established by
        # `_require_agent` in the real request path - BEFORE `_resolve_company` runs.
        with company_scope(db, frozenset({contacts_company})):
            resolved = _resolve_company(db, customer_id=None, agent=agent)

        assert resolved == contacts_company, (
            f"resolved {resolved!r} - the agent's own out-of-scope company "
            f"{agents_other_company!r} must never win over the request's active scope"
        )


def test_fix_s2_prospect_created_this_way_is_visible_in_the_contacts_own_scoped_list():
    """The other half of the same property: the record this resolves for is not just
    stamped correctly, it is actually FOUND again through the same scope."""
    from app.api.v1.public.portal_sales_opportunity import _resolve_company
    from app.models.sales import SalesOpportunity
    from app.models.sales_agent import SalesAgent
    from app.services.sales import sales_seed_service

    with blank_session() as db:
        sales_seed_service.run(db)
        contacts_company = _company(db, name="ZZT S2b Contact's Company")
        agents_other_company = _company(db, name="ZZT S2b Agent's Other Company")
        agent = SalesAgent(
            id=_uid(),
            sales_agent="ZZO-S2B",
            description="ZZT S2 Agent B",
            is_active=True,
            company_id=agents_other_company,
        )
        db.add(agent)
        db.flush()

        with company_scope(db, frozenset({contacts_company})):
            company_id = _resolve_company(db, customer_id=None, agent=agent)
            from app.models.status import Status

            initial_status = (
                db.query(Status)
                .filter(Status.entity_type == "sales_opportunity", Status.is_initial.is_(True))
                .one()
            )
            opp = SalesOpportunity(
                id=_uid(),
                company_id=company_id,
                opportunity_no="ZZT-S2-000001",
                title="ZZT S2 Prospect Opp",
                prospect_name="ZZT S2 Prospect",
                sales_agent_id=agent.id,
                status_id=initial_status.id,
                expected_amount="100.00",
                expected_close_date="2026-11-01",
                source="portal",
            )
            db.add(opp)
            db.flush()

            found = (
                db.query(SalesOpportunity)
                .filter(SalesOpportunity.id == opp.id)
                .first()
            )
            assert found is not None, "the opportunity must be visible in the contact's own scope"
