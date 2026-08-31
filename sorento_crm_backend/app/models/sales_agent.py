"""The salesperson master. One row per agent CODE as it appears on documents.

`SEAN I`, `SEAN III` and `LCL` are three agents here, not one person with three codes. The
code is what a document states and therefore the only thing an import can resolve; who is
behind it is `person_label`, which groups them for reporting and decides nothing.

NOT `access_agents` (those are Respond.io routing agents) and NOT `users`: the captain's
ruling of 2026-08-14 is that salespeople "shouldn't have user account in our system, or
optional at least", so there is no link to `users` in this slice. A nullable `user_id` FK is
future work for the day one of them needs a login.

**This table is also the AutoCount mirror target** (`app/models/sales_agent.py` on the
autocount branch, migration `303_autocount_slice2_masters`), which is why it already exists
on the shared dev database with no definition in main. The five original columns are kept
byte-identical to that definition so the two branches describe ONE table; the four added here
are annotations, which that branch's re-sync contract already promises to leave alone.
"""
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func, text

from app.database import Base
from app.services.scm.demand_class import check_constraint_sql
import uuid

#: Coalesce target for the company-scoped unique index. `company_id` is NULL on every shared
#: master row and Postgres treats NULLs as distinct, so a plain two-column unique would let
#: the same shared code be inserted twice. Same constant and same reason as `scm.models`.
_NIL_COMPANY = "00000000-0000-0000-0000-000000000000"


class SalesAgent(Base):
    __tablename__ = "sales_agents"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    # AutoCount SalesAgent (code == name). Adoption/idempotency key, stored upper-cased and
    # trimmed by `sales_agent_service` so a file spelling it `sean i` resolves to the row the
    # captain classified rather than creating a second one. Unique PER COMPANY rather than
    # globally - see the index below.
    sales_agent = Column(String(100), nullable=False)
    description = Column(String(255), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, server_default=text("true"))

    internal_note = Column(Text, nullable=True)
    follow_up = Column(Boolean, nullable=False, default=False, server_default=text("false"))

    # Who the codes belong to. Metadata, never identity: the captain's 38 codes decompose to
    # 16 people via a `(name, I|III|IV)` split, and grouping them is a reporting convenience.
    # Making it the key would merge three agents whose demand can differ.
    person_label = Column(String(100), nullable=True)
    # What this agent's orders are for, when nothing else on the document says. NULL means
    # nobody has decided yet, which is the state all 38 codes ship in: the suffix's meaning
    # maps to neither company nor market segment in this database, so it is the captain's to
    # fill and never ours to guess (UAC AC-3.3).
    demand_class = Column(String(32), nullable=True)
    # NULL = a shared master row, visible to every company. The captain's own files show the
    # same agents selling for both companies, so partitioning them would duplicate the master
    # and split one person's demand class in two. Deliberately NOT `CompanyScopedMixin`: the
    # mixin's auto-filter drops NULL-company rows, which would hide the entire master. Same
    # shape and same reason as `container_size`; recorded in `_COMPANY_ID_ALLOWLIST`. The
    # uniqueness below is scoped to it, so a tenant CAN one day hold its own `SEAN III`
    # alongside the shared one without the schema having to change first.
    company_id = Column(UUID(as_uuid=False), ForeignKey("companies.id"), nullable=True)
    # How the row got here: `manual` (an admin or the AutoCount mirror), `import` (an
    # outstanding-SO upload met a code nobody held). It is what lets the Test result say
    # "new agent, unclassified" instead of quietly inventing master data.
    source = Column(String(20), nullable=False, default="manual",
                    server_default=text("'manual'"))
    # Which warehouse-suffix ownership group this agent's stock lives in - `BB` for
    # BRW-BB/MWH-BB/DC1-BB, per the captain's ruling that those three locations are one
    # ownership group belonging to the BB salespeople (PLAN-demo-followups-19aug-ladder-v2.md
    # section 8). NULL means nobody has decided yet, the same "not our guess to make" shape
    # as `demand_class`. Stored upper/trim-normalised by `sales_agent_service.annotate` so a
    # typed `bb` still matches the group the warehouse suffix carries.
    location_group = Column(String(16), nullable=True)
    # Portal contact linked to this agent. Allows the portal to scope the debtor
    # dropdown and show price_tag_request to contacts whose linked agent exists.
    # Text, not UUID, because respond_contacts.id is Text.
    contact_id = Column(
        Text,
        ForeignKey("respond_contacts.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # The person behind `contact_id`, so no screen ever has to print the id. Eager,
    # because the master list draws every row and a lazy load would be one query per
    # agent for a single name.
    contact = relationship("RespondContact", lazy="joined")

    @property
    def contact_name(self):
        """Who the linked portal contact is, in the words a human would use.

        A contact can exist with no name (a phone number Respond.io has never had a
        profile for), and a picker showing a blank row is a picker nobody can use, so
        the number stands in. Read by `SalesAgentResponse`.
        """
        contact = self.contact
        if contact is None:
            return None
        return contact.name or contact.phone_number

    __table_args__ = (
        CheckConstraint(check_constraint_sql(), name="ck_sales_agents_demand_class"),
        # One code per company, with NULL coalesced to the nil uuid so the SHARED rows - which
        # today are all of them - still collide with each other. A plain unique on
        # `sales_agent` alone was the shape this replaced, and it made `company_id`
        # unexpressible: the column existed but a tenant could never hold its own `SEAN III`
        # while the shared one was there, so the documented future ("company_id IS NULL OR
        # company_id = <scope>" in `sales_agent_service`) could not have been implemented
        # without a migration first. Same shape as `scm.container_size` and
        # `scm.reorder_level`. Kept in lockstep with migration 356.
        Index(
            "uq_sales_agents_company_sales_agent",
            text("coalesce(company_id, '%s'::uuid)" % _NIL_COMPANY),
            "sales_agent",
            unique=True,
        ),
    )
