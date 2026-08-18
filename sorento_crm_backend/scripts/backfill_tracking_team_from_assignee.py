#!/usr/bin/env python3
"""Backfill conversation SLA tracking routing fields from the current assignee.

PLAN-sla-assignee-team-derivation: misrouted-then-reassigned conversations created before
assignee-driven derivation shipped still carry the wrong agent_id / team_set_code, so
escalation would fire into the wrong team's next tier.

Run from sorento_crm_backend/:
    python scripts/backfill_tracking_team_from_assignee.py [--dry-run]

For every OPEN (unresolved) tracking with an assignee, resolve the assignee's unique
tier-1-linked TEAM (team-level invariant) and pick its (agent, team_set) link: prefer the
tracking's stored agent (agent stays put, only the team set flips), else the deterministic
first link (code, then agent_id). Where it differs from the stored routing, update
agent_id + team_set_code ONLY. No tier reset, no clock restart, no event-log rows
(historical correction, not a live reassignment). Assignees without a tier-1 membership
(tier-2/3 managers, unmapped users) are skipped.

Idempotent JOIN-based "set to correct value where mismatch": re-runs safely and corrects
prior errors; a second run reports zero changes.
"""
from __future__ import annotations

import argparse
import os
import sys

# Allow `from app.*` imports when invoked from the backend directory.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import or_

from app.database import SessionLocal
from app.models.access import AccessAgent, AgentTeam, TeamMember
from app.models.sla import ConversationSLATracking
from app.services.form_sla_service import FORM_SLA_TYPES


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Report only; change nothing.")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        # user_id -> their unique tier-1-linked team's links [(code, agent_id)] sorted
        # deterministically; users in multiple tier-1-linked teams are skipped
        # conservatively. Cross-team-set multi-membership is now legal
        # (PLAN-tier1-teamset-invariant.md) - the runtime derivation handles those
        # users; this backfill predates that relaxation and leaves them untouched.
        links = (
            db.query(TeamMember.user_id, AgentTeam.agent_id, AgentTeam.code, AgentTeam.team_id)
            .join(AgentTeam, AgentTeam.team_id == TeamMember.team_id)
            .filter(AgentTeam.tier == 1)
            .all()
        )
        teams_by_user: dict[str, set[str]] = {}
        links_by_user: dict[str, list[tuple[str, str]]] = {}  # (code, agent_id)
        for uid, agent_id, code, team_id in links:
            teams_by_user.setdefault(str(uid), set()).add(str(team_id))
            links_by_user.setdefault(str(uid), []).append((str(code), str(agent_id)))
        tier1_by_user = {
            uid: sorted(links_by_user[uid])
            for uid, teams in teams_by_user.items()
            if len(teams) == 1
        }
        ambiguous = sorted(uid for uid, teams in teams_by_user.items() if len(teams) > 1)
        for uid in ambiguous:
            print(
                f"[SKIP] User {uid} is a member of multiple tier-1-linked teams; "
                "left untouched (cross-team-set membership is legal per "
                "PLAN-tier1-teamset-invariant.md; runtime derivation handles it)."
            )

        agent_codes = {str(a.id): str(a.code) for a in db.query(AccessAgent).all()}

        open_trackings = (
            db.query(ConversationSLATracking)
            .filter(
                ConversationSLATracking.is_resolved.is_(False),
                ConversationSLATracking.assigned_to_id.isnot(None),
                # Conversation trackings only: form SLA stages own their routing
                # via FormSLAConfig and must not be flipped from the assignee.
                or_(
                    ConversationSLATracking.source_entity_type.is_(None),
                    ConversationSLATracking.source_entity_type.notin_(FORM_SLA_TYPES),
                ),
            )
            .all()
        )

        changed = 0
        for tracking in open_trackings:
            uid = str(tracking.assigned_to_id)
            user_links = tier1_by_user.get(uid)
            if not user_links:
                continue  # tier-2/3 manager or unmapped user — no routing signal
            stored_agent_id = str(tracking.agent_id) if tracking.agent_id else None
            stored_code = str(tracking.team_set_code) if tracking.team_set_code else None
            # Prefer the stored agent's link to the user's team; else deterministic first.
            derived_code, derived_agent_id = next(
                ((c, a) for c, a in user_links if a == stored_agent_id),
                user_links[0],
            )
            if stored_agent_id == derived_agent_id and stored_code == derived_code:
                continue
            print(
                f"[FIX] tracking {tracking.id}: "
                f"agent {agent_codes.get(stored_agent_id or '', stored_agent_id)} → "
                f"{agent_codes.get(derived_agent_id, derived_agent_id)}, "
                f"team_set {stored_code or '—'} → {derived_code} "
                f"(assignee {uid}, tier stays {tracking.current_tier})"
            )
            if not args.dry_run:
                tracking.agent_id = derived_agent_id
                tracking.team_set_code = derived_code
            changed += 1

        if args.dry_run:
            print(f"\nDry run: {changed} of {len(open_trackings)} open tracking(s) would be corrected.")
        else:
            db.commit()
            print(f"\nDone: {changed} of {len(open_trackings)} open tracking(s) corrected.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
