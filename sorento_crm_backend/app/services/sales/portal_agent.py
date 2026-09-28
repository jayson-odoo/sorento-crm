"""Resolve a portal contact to its sales agent (plan 3.5; slice S2).

Lifted from `PriceTagRequestService.lookup_debtors_for_agent` (section 7, "already solved
once"), which now calls this instead of resolving the link itself, so the portal
opportunity form and the price tag debtor lookup share one copy of the rule.
"""
from __future__ import annotations

import logging
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.sales_agent import SalesAgent

logger = logging.getLogger(__name__)


def agent_for_contact(db: Session, contact_id: str) -> Optional[SalesAgent]:
    """The sales agent linked to this portal contact, or ``None``.

    `sales_agents.contact_id` carries no unique constraint, so an unordered `.first()`
    would let Postgres return either row when a contact is linked twice - the same
    salesperson could open a form twice and be answered differently with nothing on
    screen to explain it. Ordered by the agent code and then the id, so the answer is
    always the same, and a second link is logged rather than guessed at: it is a data
    problem for a human, not something to resolve here.
    """
    agents: List[SalesAgent] = (
        db.query(SalesAgent)
        .filter(SalesAgent.contact_id == contact_id)
        .order_by(SalesAgent.sales_agent, SalesAgent.id)
        .all()
    )
    if not agents:
        return None
    agent = agents[0]
    if len(agents) > 1:
        logger.warning(
            "Portal contact %s is linked to %s sales agents; answering for %s. "
            "Only one link is meant to exist.",
            contact_id,
            len(agents),
            agent.sales_agent,
        )
    return agent
