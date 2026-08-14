"""Shared seeding for the portal-revision suite (not collected by pytest).

Every test seeds its OWN chain - config -> contact -> entity -> policy -> tracker -
with a marker prefix, and asserts only on rows it created. Nothing is borrowed from
an existing table: CI's database is empty, so a ``LIMIT 1`` off ``sla_policies`` or a
lookup of "the live stock_inquiry stage config" resolves to None there and takes the
whole file down with a NOT NULL FK violation.

The ``portal_revision_configs`` seed lives in the MIGRATION BODY, so a schema built
with ``Base.metadata.create_all`` has the table and no rows. A missing config row
means disabled (fail closed), so every test seeds the config it needs.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from app.models.access import AccessAgent, RespondContact
from app.models.portal import PortalRevisionConfig, PortalToken
from app.models.procurement import (
    PurchaseRequestHeader,
    PurchaseRequestLine,
    StockInquiry,
)
from app.models.sla import (
    ConversationSLATracking,
    FormSLAConfig,
    SLAPolicy,
    SLAPolicyTier,
)
from app.models.user import SystemSetting, User
from tests._pg_fixture import TEST_PREFIX

CONTACT_SPACE = f"{TEST_PREFIX}-space"

# The seeded statuses, copied from the migration so a drift shows up as a failure
# here rather than as a silently-disabled type in production.
ALLOWED_STATUSES = {
    "stock_inquiry": ["pending_project_sales", "pending_purchasing", "responded"],
    "purchase_request": ["submitted", "approved"],
    "sponsorship_form": ["submitted", "approved"],
    "complaint": [],
}

REVISABLE_TYPES = ("stock_inquiry", "purchase_request", "sponsorship_form")


def marker(stem: str = "") -> str:
    return f"{TEST_PREFIX}-{stem}-{uuid.uuid4().hex[:8]}" if stem else f"{TEST_PREFIX}-{uuid.uuid4().hex[:8]}"


def seed_config(
    db,
    source_entity_type: str,
    *,
    is_enabled: bool = True,
    max_revisions=None,
    allowed_statuses=None,
    restart_stage_code=None,
) -> PortalRevisionConfig:
    row = PortalRevisionConfig(
        id=str(uuid.uuid4()),
        source_entity_type=source_entity_type,
        is_enabled=is_enabled,
        max_revisions=max_revisions,
        allowed_statuses=(
            ALLOWED_STATUSES.get(source_entity_type, [])
            if allowed_statuses is None
            else allowed_statuses
        ),
        restart_stage_code=restart_stage_code,
    )
    db.add(row)
    db.commit()
    return row


def seed_system_settings(db, *, enabled: bool = True, cap: int = 2) -> SystemSetting:
    row = SystemSetting(
        id=str(uuid.uuid4()),
        portal_revisions_enabled=enabled,
        portal_max_revisions=cap,
    )
    db.add(row)
    db.commit()
    return row


def seed_contact(db, *, name: str = "Test Salesperson") -> RespondContact:
    contact = RespondContact(
        id=str(uuid.uuid4()),
        phone_number=marker("phone"),
        name=name,
        respond_io_id=marker("rio"),
    )
    db.add(contact)
    db.commit()
    return contact


def seed_token(contact: RespondContact) -> PortalToken:
    """A token object, not persisted: the portal code only reads contact_id/space_id."""
    return PortalToken(
        token=marker("tok"),
        contact_id=contact.id,
        space_id=CONTACT_SPACE,
        expires_at=datetime(2099, 1, 1),
        verified_at=datetime(2026, 1, 1),
    )


def seed_entity(
    db,
    source_entity_type: str,
    contact: RespondContact,
    *,
    status=None,
    revision_no: int = 0,
    with_lines: bool = True,
    **overrides,
):
    """One submitted entity of the given type, owned by ``contact``."""
    entity_id = str(uuid.uuid4())
    if source_entity_type == "stock_inquiry":
        row = StockInquiry(
            id=entity_id,
            inquiry_number=marker("SI"),
            status=status or "pending_purchasing",
            contact_id=contact.id,
            space_id=CONTACT_SPACE,
            salesperson=contact.name,
            salesperson_contact_id=contact.id,
            product_code="SRTWT51030",
            item_description="Free Standing Bath Tub Mixer",
            quantity="4",
            revision_no=revision_no,
        )
    else:
        row = PurchaseRequestHeader(
            id=entity_id,
            request_number=marker("PR" if source_entity_type == "purchase_request" else "SP"),
            request_type=source_entity_type,
            status=status or "submitted",
            source="portal",
            contact_id=contact.id,
            space_id=CONTACT_SPACE,
            requested_by=contact.name,
            requested_by_contact_id=contact.id,
            project_title="Marker project",
            purpose="Marker purpose",
            revision_no=revision_no,
        )
    for key, value in overrides.items():
        setattr(row, key, value)
    db.add(row)
    db.flush()
    if source_entity_type != "stock_inquiry" and with_lines:
        db.add(
            PurchaseRequestLine(
                id=str(uuid.uuid4()),
                purchase_request_id=entity_id,
                item_code="ITEM-A",
                quantity=2,
                sort_order=0,
            )
        )
    db.commit()
    return row


def seed_user(db, *, name="Handler") -> User:
    user = User(
        id=str(uuid.uuid4()),
        email=marker("user") + "@example.test",
        name=name,
        status="ACTIVE",
    )
    db.add(user)
    db.commit()
    return user


def seed_policy(db) -> str:
    policy_id = str(uuid.uuid4())
    db.add(SLAPolicy(id=policy_id, code=marker("POL"), name="Marker policy"))
    db.add(
        SLAPolicyTier(
            id=str(uuid.uuid4()),
            policy_id=policy_id,
            tier_level=1,
            tier_name="Tier 1",
            response_hours=4,
            resolution_hours=24,
        )
    )
    db.commit()
    return policy_id


def seed_stage_config(
    db,
    source_entity_type: str,
    policy_id: str,
    *,
    stage_code: str,
    team_set_code: str,
    start_event: str = "submit",
    resolve_event: str = "resolved",
    agent_code=None,
) -> FormSLAConfig:
    config = FormSLAConfig(
        id=str(uuid.uuid4()),
        source_entity_type=source_entity_type,
        stage_code=stage_code,
        policy_id=policy_id,
        agent_code=agent_code or marker("agent"),
        team_set_code=team_set_code,
        start_event=start_event,
        resolve_event=resolve_event,
        is_active=True,
    )
    db.add(config)
    db.commit()
    return config


def seed_agent(db, code: str) -> AccessAgent:
    agent = AccessAgent(id=str(uuid.uuid4()), code=code, name=code)
    db.add(agent)
    db.commit()
    return agent


def seed_tracker(
    db,
    source_entity_type: str,
    source_entity_id: str,
    policy_id: str,
    *,
    team_set_code: str = "purchasing",
    assigned_to_id=None,
    handled_by_id=None,
    is_resolved: bool = False,
    agent_id=None,
    current_tier: int = 1,
) -> ConversationSLATracking:
    now = datetime.utcnow()
    tracker = ConversationSLATracking(
        id=str(uuid.uuid4()),
        policy_id=policy_id,
        current_tier=current_tier,
        initiated_at=now - timedelta(hours=2),
        current_tier_started_at=now - timedelta(hours=1),
        due_at=now + timedelta(hours=4),
        due_at_resolution=now + timedelta(hours=20),
        is_responded=False,
        is_resolved=is_resolved,
        source_entity_type=source_entity_type,
        source_entity_id=str(source_entity_id),
        team_set_code=team_set_code,
        assigned_to_id=assigned_to_id,
        handled_by_id=handled_by_id,
        handled_at=now if handled_by_id else None,
        agent_id=agent_id,
    )
    db.add(tracker)
    db.commit()
    return tracker
