"""Form submissions on the form-SLA machinery: the event names, the emit, the stage seed.

F1 put a submission's status in the status engine and F1a made a deriving definition's
header follow its lines. Neither told the SLA machinery that ``workflow_submission``
exists, so a submission had no clock, no assignee, no escalation and no handling lock.
This module is the wiring, and it owns three things that must not be spread out:

**One place names an event.** The seeded stage's ``start_event`` / ``resolve_event`` and
the code that emits those events have to agree on one string. Two hand-written copies of
the convention is the same defect as the duplicated type tuple, one layer down, so
``submission_status_event`` is the only thing allowed to spell one.

**A creation event, because a deriving form has no other reachable start.**
``assert_manual_header_move_allowed`` refuses every manual move INTO the derived pair,
and a submission is *created* on the open rung with no transition at all. So the only
header events a deriving form can fire are the pair's two keys, and the resolved one
fires when the work FINISHES: a stage could only ever start at the wrong end of its own
clock. ``submission_created`` is therefore emitted on creation, and a deriving
definition's first stage starts there. Non-deriving forms keep starting on the
status-move event, exactly as ``complaint`` starts on ``submit``. Two event sources,
chosen per definition, rather than overloading a status with a meaning it does not have.

**The emit is post-commit and best-effort, at the service callers.** NOT inside
``recompute_submission_status``, which documents "flushes, never commits", while
``_start_for_config`` commits unconditionally: an emit in there would commit a caller's
half-built transaction, and ``create_submission`` recomputes BEFORE its own commit. The
move has already been accepted by the time anything here runs, so a mis-configured stage
can only produce a warning in the log. A submission that cannot be approved because its
SLA stage is wrong is the worst outcome available.

**The stage seed creates no teams.** A migration cannot invent team members, and a stage
whose tier has no team raises a 422 that ``emit_event`` swallows - which looks exactly
like a form with no SLA. Team configuration is deliberately left to whoever configures
after-sales; until then the seeded stage is inert in the same way an unconfigured
``form_sla_configs`` row has always been.

See documentation/plans/forms-platform/forms-platform-acceptance-criteria.md, group F2a.
"""
from __future__ import annotations

import logging
import uuid
from decimal import Decimal
from typing import Dict, Optional

from sqlalchemy.orm import Session

from app.models.access import AccessAgent
from app.models.sla import FormSLAConfig, SLAPolicy, SLAPolicyTier
from app.services.workflow_submission_status_graph import (
    WORKFLOW_SUBMISSION_ENTITY_TYPE,
)

logger = logging.getLogger(__name__)


# The event a submission fires when it is CREATED, which is the only event a deriving
# definition can start a clock on. Distinct from every status key by construction, or it
# would collide with a status move's event and one rung's move would fire it.
SUBMISSION_CREATED_EVENT = "submission_created"

# What the seed writes. Codes rather than ids so the seed is re-runnable by lookup, and
# so a human reading form_sla_configs can tell which agent and policy belong to it.
SEED_AGENT_CODE = "workflow_submission"
SEED_POLICY_CODE = "WORKFLOW_SUBMISSION"
SEED_STAGE_CODE = "main"
SEED_TEAM_SET_CODE = "main"

# (tier_level, response_hours, resolution_hours). Three tiers so the overdue scan has
# somewhere to escalate to twice; each tier is tighter than the last, since a breach is
# the reason the next tier is looking at it.
#
# Decimal, because the columns are NUMERIC(6,2): comparing a stored Decimal('24.00')
# against a literal 24 is never equal, so an int here would make every re-run report a
# change it did not make.
SEED_POLICY_TIERS = (
    (1, Decimal("24"), Decimal("72")),
    (2, Decimal("12"), Decimal("48")),
    (3, Decimal("8"), Decimal("24")),
)


def submission_status_event(status_key: Optional[str]) -> str:
    """The SLA event name a submission's move to ``status_key`` emits: the key itself.

    Total over every key (including ones an admin adds to a forked graph) and INJECTIVE,
    which is the property that matters: two keys mapping to one event name would make one
    rung's move fire another rung's stage, and the symptom would be a stage that starts
    or resolves for no visible reason.

    It is a function rather than an f-string at each call site so the seeded config and
    the emitter cannot drift apart, which is the same defect as the duplicated
    FORM_SLA_TYPES tuple one layer down.

    ``Optional``, because ``WorkflowSubmission.status_key`` reads through the status
    relationship and is None when that row is missing. It degrades to an empty event
    name, which ``emit_submission_event`` then declines to fire, rather than raising a
    TypeError inside a post-commit side effect.
    """
    return str(status_key or "").strip()


def emit_submission_event(
    db: Session,
    submission,
    event_name: str,
    *,
    actor_user_id: Optional[str] = None,
) -> None:
    """Fire one ``workflow_submission`` SLA event. Never raises.

    Call this AFTER committing the status write. Best-effort in both directions: the
    caller's move has already been accepted, so an SLA failure must not surface as a 500
    (or a rollback) for an operation that worked. ``emit_event`` already swallows
    per-config failures; this catches the rest, including a session left unusable by one.

    ``actor_user_id`` is the mover, and it is None for a DERIVED move on purpose: a
    person really did decide a LINE a moment earlier, and crediting them with the
    header's move - which is what ``resolved_by`` would then record - is a lie plausible
    enough to be believed (AC-F1a-29).

    The respondent contact is read off the submission HERE rather than taken as a kwarg,
    so no caller can forget it. It is what populates
    ``conversation_sla_tracking.respond_contact_id`` - the field the WhatsApp channel and
    the CS pin lookup both key on - and without it a portal submission spawns a tracker
    with a deadline and no way to reply to whoever filed it. NULL for an internal
    submission, which legitimately has no contact.

    The import is local, mirroring every other form service's call site: the SLA module
    pulls in the notification stack, and it is also what makes the emit patchable in a
    test that has to prove a failing emit does not break the move.
    """
    submission_id = str(getattr(submission, "id", "") or "")
    event = str(event_name or "").strip()
    if not submission_id or not event:
        return
    try:
        from app.services.form_sla_service import emit_form_event

        emit_form_event(
            db,
            WORKFLOW_SUBMISSION_ENTITY_TYPE,
            submission_id,
            event,
            contact_id=str(getattr(submission, "respondent_contact_id", "") or "")
            or None,
            actor_user_id=actor_user_id,
            # Scopes the config set to this form. One type covers every definition, so
            # without it a stage seeded for an RMA form would also clock a survey.
            definition_id=str(getattr(submission, "definition_id", "") or "") or None,
        )
    except Exception as exc:  # noqa: BLE001 - post-commit side effect, never fatal
        logger.warning(
            "Form SLA emit '%s' failed for submission %s: %s",
            event,
            submission_id,
            exc,
        )


# ------------------------------------------------------------------------- seeding


def _apply(row: object, values: Dict[str, object]) -> bool:
    """Set only the attributes that differ. True when something changed.

    Mirrors the status-graph seeds: "set where mismatch", not "insert where absent". A
    re-run repairs a drifted event name or flag IN PLACE, keeping the row's id, so every
    live tracker that belongs to the stage follows the repair. Insert-if-absent could
    never fix a prior bad run, and replace-the-row would orphan every running clock.
    """
    changed = False
    for field, value in values.items():
        if getattr(row, field, None) != value:
            setattr(row, field, value)
            changed = True
    return changed


def _seed_agent(db: Session, summary: Dict[str, int]) -> AccessAgent:
    """The routing agent the stage names.

    ``_start_for_config`` raises when ``agent_code`` names no row, and ``emit_event``
    swallows that - so a missing agent is indistinguishable from a form with no SLA at
    all. The seed owns it rather than assuming an admin created one first.
    """
    agent = db.query(AccessAgent).filter(AccessAgent.code == SEED_AGENT_CODE).first()
    values = {
        "name": "Form submissions",
        "description": (
            "Routes form-submission SLA stages. Its tier teams decide who handles a "
            "submission; add them per team set before the stage can assign anyone."
        ),
        "is_active": True,
    }
    if agent is None:
        agent = AccessAgent(id=str(uuid.uuid4()), code=SEED_AGENT_CODE, **values)
        db.add(agent)
        summary["agents_created"] += 1
    elif _apply(agent, values):
        summary["agents_updated"] += 1
    db.flush()
    return agent


def _seed_policy(db: Session, summary: Dict[str, int]) -> SLAPolicy:
    """The stage's own deadlines.

    Its own row, never a shared one: stages that share a policy re-time each other, and
    editing one stage's response hours would silently move every other stage of the same
    form. Tiers 1..3 so the overdue scan has somewhere to escalate to.
    """
    policy = db.query(SLAPolicy).filter(SLAPolicy.code == SEED_POLICY_CODE).first()
    values = {"name": "Form submission", "is_active": True}
    if policy is None:
        policy = SLAPolicy(id=str(uuid.uuid4()), code=SEED_POLICY_CODE, **values)
        db.add(policy)
        summary["policies_created"] += 1
    elif _apply(policy, values):
        summary["policies_updated"] += 1
    db.flush()

    for level, response_hours, resolution_hours in SEED_POLICY_TIERS:
        tier_values = {
            "tier_name": f"Tier {level}",
            "response_hours": response_hours,
            "resolution_hours": resolution_hours,
        }
        tier = (
            db.query(SLAPolicyTier)
            .filter(
                SLAPolicyTier.policy_id == policy.id,
                SLAPolicyTier.tier_level == level,
            )
            .first()
        )
        if tier is None:
            db.add(
                SLAPolicyTier(
                    id=str(uuid.uuid4()),
                    policy_id=policy.id,
                    tier_level=level,
                    **tier_values,
                )
            )
            summary["policy_tiers_created"] += 1
        elif _apply(tier, tier_values):
            summary["policy_tiers_updated"] += 1
    db.flush()
    return policy


def seed_workflow_submission_sla_configs(db: Session) -> Dict[str, int]:
    """Create or CORRECT the default submission SLA stage. Returns a change summary.

    ONE stage, on the default vocabulary. The default header graph's post-decision rungs
    (``approved``, ``rejected``) are both terminal and nothing leaves a terminal rung, so
    there is no rung left for a second stage to resolve on - and widening the default
    graph to invent one is exactly what F1 refuses, since every unforked definition would
    inherit it. Forked definitions add their own chained stages against their own
    ``definition_id``.

    ``definition_id`` is NULL: this stage applies to every definition, which is what
    makes a brand new form get a clock with no configuration at all.

    Self-sufficient on a blank schema (it creates the agent, the policy and its tiers),
    with one deliberate exception: it creates NO ``teams`` / ``agent_teams`` /
    ``team_members``. A seed cannot invent members, and a stage whose tier has no team
    raises a 422 that ``emit_event`` swallows, so an invented empty team would look
    identical to a working one. Configuring the tier teams is an admin act.

    Flushes but never commits, so a migration or a caller owns the transaction boundary.
    """
    summary = {
        "agents_created": 0,
        "agents_updated": 0,
        "policies_created": 0,
        "policies_updated": 0,
        "policy_tiers_created": 0,
        "policy_tiers_updated": 0,
        "configs_created": 0,
        "configs_updated": 0,
    }

    agent = _seed_agent(db, summary)
    policy = _seed_policy(db, summary)

    values = {
        "policy_id": str(policy.id),
        "agent_code": str(agent.code),
        "team_set_code": SEED_TEAM_SET_CODE,
        # Two event sources, one stage. A DERIVING definition can only start here on
        # creation (every manual move into its derived pair is refused), while a
        # non-deriving one starts on the submit move like every other form. Starting is
        # idempotent per stage, so a non-deriving submission that fires both gets one
        # clock, not two.
        "start_event": f"{SUBMISSION_CREATED_EVENT},{submission_status_event('submitted')}",
        # No respond_event: nothing in the default graph sits between submitted and the
        # decision, so there is no distinct "responded" act to record. An event no
        # transition can fire would be false documentation.
        "respond_event": None,
        "resolve_event": (
            f"{submission_status_event('approved')},"
            f"{submission_status_event('rejected')}"
        ),
        # Single stage, so nothing to advance to. When a chain is added, set
        # advance_on_event to the APPROVING event: NULL means "any resolve advances",
        # which hands a REJECTED submission to the next team as though it had passed.
        "next_config_id": None,
        "advance_on_event": None,
        "definition_id": None,
        "is_active": True,
        "notify_assignee": True,
        "notify_on_escalation": True,
    }

    # Keyed on (source_entity_type, stage_code, definition_id IS NULL), which is the
    # scope the partial unique index enforces. Not on the id: a re-run must find the row
    # it wrote last time.
    config = (
        db.query(FormSLAConfig)
        .filter(
            FormSLAConfig.source_entity_type == WORKFLOW_SUBMISSION_ENTITY_TYPE,
            FormSLAConfig.stage_code == SEED_STAGE_CODE,
            FormSLAConfig.definition_id.is_(None),
        )
        .first()
    )
    if config is None:
        db.add(
            FormSLAConfig(
                id=str(uuid.uuid4()),
                source_entity_type=WORKFLOW_SUBMISSION_ENTITY_TYPE,
                stage_code=SEED_STAGE_CODE,
                **values,
            )
        )
        summary["configs_created"] += 1
    elif _apply(config, values):
        summary["configs_updated"] += 1
    db.flush()

    return summary
