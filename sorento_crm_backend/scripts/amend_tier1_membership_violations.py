#!/usr/bin/env python3
"""Amend tier-1 membership invariant violations (PLAN-sla-assignee-team-derivation).

STALE - DO NOT RUN until updated. The invariant this script enforces was relaxed to
per TEAM SET (`AgentTeam.code`) by PLAN-tier1-teamset-invariant.md: a user may now
legally hold tier-1 membership in one team PER team set (cross-team-set membership is
valid). This script still groups violations per user globally, so a run would DELETE
now-legal cross-team-set memberships. It needs its violation detection rescoped to
(user, team set code) before any future use.

Old invariant (TEAM-level, superseded): a user may belong to at most ONE team that is
linked at tier 1 (under any agent), otherwise assignee-driven routing derivation is
ambiguous. The same team being linked at tier 1 under many agents is fine (shared
executive pools).

Run from sorento_crm_backend/:
    python scripts/amend_tier1_membership_violations.py [--dry-run]

For each violating user the script KEEPS the most recent tier-1 team membership
(TeamMember.created_at latest = latest config intent) and DELETES the user's older
memberships in other tier-1-linked teams. Every removal is logged. Idempotent:
a second run finds no violations.
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import defaultdict

# Allow `from app.*` imports when invoked from the backend directory.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models.access import AccessAgent, AgentTeam, Team, TeamMember
from app.models.user import User


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Report only; change nothing.")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        # All tier-1 links: team_id -> set of (agent_id, code) (multi-agent links are legal)
        tier1_links = db.query(AgentTeam).filter(AgentTeam.tier == 1).all()
        sets_by_team: dict[str, set[tuple[str, str]]] = defaultdict(set)
        for link in tier1_links:
            sets_by_team[str(link.team_id)].add((str(link.agent_id), str(link.code)))

        if not sets_by_team:
            print("No tier-1 team links configured; nothing to do.")
            return 0

        # Memberships in tier-1-linked teams, grouped per user.
        memberships = (
            db.query(TeamMember)
            .filter(TeamMember.team_id.in_(list(sets_by_team.keys())))
            .all()
        )
        by_user: dict[str, list[TeamMember]] = defaultdict(list)
        for m in memberships:
            by_user[str(m.user_id)].append(m)

        agent_codes = {str(a.id): str(a.code) for a in db.query(AccessAgent).all()}
        team_names = {str(t.id): str(t.name) for t in db.query(Team).all()}

        removed = 0
        violating_users = 0
        for user_id, rows in sorted(by_user.items()):
            distinct_teams = {str(m.team_id) for m in rows}
            if len(distinct_teams) <= 1:
                continue
            violating_users += 1
            user = db.query(User).filter(User.id == user_id).first()
            user_label = (user.name or user.email) if user else user_id

            # Keep the most recent membership; among ties, deterministic by team_id.
            rows_sorted = sorted(
                rows, key=lambda m: (m.created_at or 0, str(m.team_id)), reverse=True
            )
            keep = rows_sorted[0]
            keep_team = str(keep.team_id)
            print(
                f"[FIX] User '{user_label}' is in {len(distinct_teams)} tier-1-linked teams "
                f"{sorted(team_names.get(t, t) for t in distinct_teams)}; keeping latest "
                f"membership in '{team_names.get(keep_team, keep_team)}'."
            )
            for m in rows_sorted[1:]:
                tid = str(m.team_id)
                if tid == keep_team:
                    continue
                agent_label = ", ".join(
                    f"{agent_codes.get(aid, aid)}/{code}" for aid, code in sorted(sets_by_team[tid])
                )
                print(
                    f"       - remove from team '{team_names.get(tid, tid)}' ({agent_label}), "
                    f"member since {m.created_at}"
                )
                if not args.dry_run:
                    db.delete(m)
                removed += 1

        if args.dry_run:
            print(f"\nDry run: {violating_users} violating user(s), {removed} membership(s) would be removed.")
        else:
            db.commit()
            print(f"\nDone: {violating_users} violating user(s), {removed} membership(s) removed.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
