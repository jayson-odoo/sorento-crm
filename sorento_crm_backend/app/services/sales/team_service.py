"""Sales teams and their dated membership (plan 3.8; UAC S6-1 to S6-3, S6-14, S6-15).

The only writer of `sales.team_members`, which is why "no two memberships of one agent in one
company overlap" is checked here rather than by an exclusion constraint (plan 3.8).

The dated rule, stated once: an order of agent A dated X counts for team T when A has a row for
T with `coalesce(valid_from, -infinity) <= X <= coalesce(valid_to, infinity)`.

- An agent's FIRST team: `valid_from` empty, so their earlier orders count too (V1).
- A move on D (the agent is open in another team): the old row closes at D - 1, a new row
  opens at D. D is never later than today (a future move is a calendar note, not a membership).
- Removing an agent: the open row closes at today and stays, so past periods keep its orders.

The leader (owner ruling 26 Sep ~13:25Z, W1) is one of the team's current agents, a current
attribute rather than dated history. Picking a leader who is not yet a member places them the
same way Add agents does (a Moves on when they come from another team); when the leader leaves
or moves, the leader clears. `trg_sales_teams_leader_is_member` holds the same rule at commit.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Dict, Iterable, List, Optional, Tuple, cast
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.sales import SalesTeam, SalesTeamMember
from app.models.sales_agent import SalesAgent
from app.services.error_handler import AppException

_MALAYSIA = ZoneInfo("Asia/Kuala_Lumpur")


def _today() -> date:
    """The business day, in Malaysia. A seam, so tests can pin it."""
    return datetime.now(_MALAYSIA).date()


@dataclass
class Move:
    sales_agent_id: str
    label: str
    from_team_id: str
    from_team_name: str


# --------------------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------------------


def acting_company_id(db: Session) -> str:
    """The company a write belongs to; the same answer the insert auto-stamp gives."""
    from app.services.company_scope import get_company_scope, resolve_write_company_id

    # None only under the test-only leave-NULL seam; a real ambiguous scope raises there.
    return cast(str, resolve_write_company_id(get_company_scope(db)))


def agent_label(agent: SalesAgent) -> str:
    """`ALI - Ali Hassan`, or the code alone when the agent has no name."""
    name = (agent.description or "").strip()
    return f"{agent.sales_agent} - {name}" if name else agent.sales_agent


def _visible_agents(db: Session, company_id: str):
    # `sales_agents` is not company-scoped: NULL company is a shared master row (sales_agent.py).
    return db.query(SalesAgent).filter(
        or_(SalesAgent.company_id.is_(None), SalesAgent.company_id == company_id)
    )


def get_team_or_404(db: Session, team_id: str) -> SalesTeam:
    team = db.query(SalesTeam).filter(SalesTeam.id == team_id).first()
    if team is None:
        raise AppException(status_code=404, message="Sales team not found.", code="NOT_FOUND")
    return team


def _flush_name(db: Session, name: str) -> None:
    """Flush, turning `uq_sales_teams_company_lower_name` (case-insensitive, per company) into a 409."""
    try:
        with db.begin_nested():
            db.flush()
    except IntegrityError as exc:
        if "uq_sales_teams_company_lower_name" not in str(exc.orig):
            raise
        raise AppException(
            status_code=409,
            message=f'A sales team called "{name}" already exists.',
            code="SALES_TEAM_NAME_TAKEN",
        ) from exc


def _unprocessable(message: str, code: str) -> AppException:
    return AppException(status_code=422, message=message, code=code)


# --------------------------------------------------------------------------------------
# writes
# --------------------------------------------------------------------------------------


def create_team_with_members(
    db: Session,
    *,
    company_id: str,
    name: str,
    sales_agent_ids: Iterable[str],
    is_active: bool = True,
    moves_on: Optional[date] = None,
    leader_sales_agent_id: Optional[str] = None,
) -> Tuple[SalesTeam, List[Move]]:
    name = name.strip()
    team = SalesTeam(company_id=company_id, name=name, is_active=is_active)
    db.add(team)
    _flush_name(db, name)
    moved = save_members_and_leader(
        db,
        team,
        sales_agent_ids,
        moves_on=moves_on,
        leader_sales_agent_id=leader_sales_agent_id,
        set_leader=True,
    )
    return team, moved


def create_team(db: Session, **kwargs) -> SalesTeam:
    team, _ = create_team_with_members(db, **kwargs)
    return team


def update_team(
    db: Session, team: SalesTeam, *, name: Optional[str] = None, is_active: Optional[bool] = None
) -> SalesTeam:
    if name is not None:
        name = name.strip()
        team.name = name
    if is_active is not None:
        team.is_active = is_active
    _flush_name(db, name or team.name)
    return team


def delete_team(db: Session, team: SalesTeam) -> None:
    """Hard delete (S6-3). Memberships go with it (ON DELETE CASCADE); agents are untouched."""
    db.query(SalesTeamMember).filter(SalesTeamMember.sales_team_id == team.id).delete(
        synchronize_session=False
    )
    db.delete(team)
    db.flush()


def delete_team_by_id(db: Session, team_id: str) -> None:
    """The parked `sales_team.delete` action's handler. Already gone is not an error."""
    team = db.query(SalesTeam).filter(SalesTeam.id == team_id).first()
    if team is not None:
        delete_team(db, team)


def save_members_and_leader(
    db: Session,
    team: SalesTeam,
    sales_agent_ids: Optional[Iterable[str]],
    *,
    moves_on: Optional[date] = None,
    leader_sales_agent_id: Optional[str] = None,
    set_leader: bool = False,
) -> List[Move]:
    """One save of the agents and the leader (W1).

    `sales_agent_ids` None keeps the current agents. `set_leader` False keeps the leader
    (unless they are left out); True sets it to `leader_sales_agent_id`, None clearing it. A
    leader who is not among the agents is added to them, so they join like any picked agent.
    """
    leader = str(leader_sales_agent_id) if set_leader and leader_sales_agent_id else None
    if sales_agent_ids is None and leader is None:
        if set_leader:
            team.leader_sales_agent_id = None
            db.flush()
        return []

    if sales_agent_ids is None:
        wanted = [
            m.sales_agent_id
            for m in db.query(SalesTeamMember).filter(
                SalesTeamMember.sales_team_id == team.id, SalesTeamMember.valid_to.is_(None)
            )
        ]
    else:
        wanted = [str(i) for i in sales_agent_ids]
    if leader is not None and leader not in wanted:
        wanted.append(leader)

    moved = set_members(db, team, wanted, moves_on=moves_on)
    if set_leader:
        team.leader_sales_agent_id = leader
        db.flush()
    return moved


def set_members(
    db: Session,
    team: SalesTeam,
    sales_agent_ids: Iterable[str],
    *,
    moves_on: Optional[date] = None,
) -> List[Move]:
    """Make the team's open members exactly `sales_agent_ids`. Returns who moved from where."""
    today = _today()
    moves_on = moves_on or today
    if moves_on > today:
        raise _unprocessable("Moves on cannot be later than today.", "MOVES_ON_IN_FUTURE")

    wanted: List[str] = list(dict.fromkeys(str(i) for i in sales_agent_ids))
    agents: Dict[str, SalesAgent] = {
        a.id: a for a in _visible_agents(db, team.company_id).filter(SalesAgent.id.in_(wanted))
    } if wanted else {}
    missing = [i for i in wanted if i not in agents]
    if missing:
        raise _unprocessable("One or more sales agents were not found.", "UNKNOWN_SALES_AGENT")

    open_here = {
        m.sales_agent_id: m
        for m in db.query(SalesTeamMember).filter(
            SalesTeamMember.sales_team_id == team.id, SalesTeamMember.valid_to.is_(None)
        )
    }

    # Left out: close today, keep the row (S6-14). A leader left out stops leading (W1).
    for agent_id, member in open_here.items():
        if agent_id not in agents:
            member.valid_to = today
            if team.leader_sales_agent_id == agent_id:
                team.leader_sales_agent_id = None

    moved: List[Move] = []
    new_rows: List[SalesTeamMember] = []
    day_before = moves_on - timedelta(days=1)
    for agent_id in wanted:
        if agent_id in open_here:
            continue
        agent = agents[agent_id]
        history = (
            db.query(SalesTeamMember)
            .filter(
                SalesTeamMember.company_id == team.company_id,
                SalesTeamMember.sales_agent_id == agent_id,
            )
            .all()
        )
        # The rows still counting on or after `moves_on`: the open row, or one closed by a
        # removal earlier today. A back-dated Moves on that reaches across two of them would
        # rewrite a stay that is already history, so it is refused (S6-14).
        overlapping = [m for m in history if m.valid_to is None or m.valid_to >= moves_on]
        if len(overlapping) > 1:
            earliest = min(overlapping, key=lambda m: m.valid_to or date.max)
            raise _unprocessable(
                f"{agent_label(agent)} was in another team after the Moves on date; pick "
                f"{(earliest.valid_to + timedelta(days=1)).isoformat()} or later.",
                "MEMBERSHIP_OVERLAP",
            )
        covering = overlapping[0] if overlapping else None

        if covering is not None and covering.sales_team_id == team.id:
            # Taken out of this team and put back with no gap: one continuous membership.
            covering.valid_to = None
            continue

        valid_from: Optional[date] = moves_on
        if covering is not None:
            from_team = db.query(SalesTeam).filter(SalesTeam.id == covering.sales_team_id).one()
            if from_team.leader_sales_agent_id == agent_id:
                from_team.leader_sales_agent_id = None  # the leader moved on (W1)
            moved.append(
                Move(
                    sales_agent_id=agent_id,
                    label=agent_label(agent),
                    from_team_id=from_team.id,
                    from_team_name=from_team.name,
                )
            )
            if covering.valid_from is None or covering.valid_from < moves_on:
                # A move (T2): the other team keeps everything before `moves_on`.
                covering.valid_to = day_before
            elif covering.valid_from == moves_on == today:
                # A stay that began today is a same-day mistake being corrected: it never
                # counted for a full day, so it goes, and a team the agent left yesterday
                # for it gets them back as if nothing happened.
                db.delete(covering)
                db.flush()  # gone before any row reopens, or the one-open-row index trips
                history = [m for m in history if m is not covering]
                previous = next((m for m in history if m.valid_to == day_before), None)
                if previous is not None and previous.sales_team_id == team.id:
                    previous.valid_to = None
                    continue
            else:
                # The old row needs at least one day, so the first date that works is the
                # day after it began.
                raise _unprocessable(
                    f"{agent_label(agent)} joined {from_team.name} on "
                    f"{covering.valid_from.isoformat()}, on or after the Moves on date; pick "
                    f"{(covering.valid_from + timedelta(days=1)).isoformat()} or later.",
                    "MEMBERSHIP_OVERLAP",
                )
        if not history:
            valid_from = None  # first team: from the beginning (V1)

        new_rows.append(
            SalesTeamMember(
                company_id=team.company_id,
                sales_team_id=team.id,
                sales_agent_id=agent_id,
                valid_from=valid_from,
            )
        )

    # Close the old open rows BEFORE the new ones exist, or the one-open-row index trips.
    db.flush()
    for row in new_rows:
        db.add(row)
    db.flush()
    return moved


# --------------------------------------------------------------------------------------
# reads
# --------------------------------------------------------------------------------------


def list_teams(db: Session, *, query: Optional[str] = None) -> List[dict]:
    teams_q = db.query(SalesTeam)
    if query and query.strip():
        teams_q = teams_q.filter(SalesTeam.name.ilike(f"%{query.strip()}%"))
    teams = teams_q.order_by(func.lower(SalesTeam.name)).all()
    if not teams:
        return []

    rows = (
        db.query(SalesTeamMember.sales_team_id, SalesAgent)
        .join(SalesAgent, SalesAgent.id == SalesTeamMember.sales_agent_id)
        .filter(
            SalesTeamMember.sales_team_id.in_([t.id for t in teams]),
            SalesTeamMember.valid_to.is_(None),
        )
        .all()
    )
    by_team: Dict[str, List[SalesAgent]] = {}
    for team_id, agent in rows:
        by_team.setdefault(team_id, []).append(agent)

    out = []
    for team in teams:
        agents = sorted(by_team.get(team.id, []), key=agent_label)
        out.append(
            {
                "id": team.id,
                "name": team.name,
                "is_active": team.is_active,
                "leader_sales_agent_id": team.leader_sales_agent_id,
                "member_count": len(agents),
                "members": [{"sales_agent_id": a.id, "label": agent_label(a)} for a in agents],
                "created_at": team.created_at,
                "updated_at": team.updated_at,
            }
        )
    return out


def team_detail(
    db: Session, team: SalesTeam, *, on: Optional[date] = None, moved: Optional[List[Move]] = None
) -> dict:
    """The team page: members on `on`, plus anyone who left earlier in that month (S6-15).

    One line per agent (owner ruling 26 Sep ~13:05Z on N1): an agent who left and came back
    shows once, from the stay in force on `on`; the earlier stay stays in the data only.
    """
    on = on or _today()
    month_start = on.replace(day=1)
    rows = (
        db.query(SalesTeamMember, SalesAgent)
        .join(SalesAgent, SalesAgent.id == SalesTeamMember.sales_agent_id)
        .filter(
            SalesTeamMember.sales_team_id == team.id,
            or_(SalesTeamMember.valid_from.is_(None), SalesTeamMember.valid_from <= on),
            or_(SalesTeamMember.valid_to.is_(None), SalesTeamMember.valid_to >= month_start),
        )
        # One agent's stays never overlap, so the latest to start is the one in force on
        # `on`, or, when every one has ended, the last one; it overwrites the earlier ones.
        .order_by(SalesTeamMember.valid_from.asc().nullsfirst())
        .all()
    )
    members_by_agent: Dict[str, dict] = {}
    for member, agent in rows:
        left = member.valid_to is not None and member.valid_to <= on
        members_by_agent[agent.id] = (
            {
                "sales_agent_id": agent.id,
                "code": agent.sales_agent,
                "name": agent.description,
                "label": agent_label(agent),
                "valid_from": member.valid_from,
                "valid_to": member.valid_to,
                "left": left,
            }
        )
    members = sorted(members_by_agent.values(), key=lambda m: (m["left"], m["label"]))
    # The leader is who leads NOW, whatever date the page is read on.
    leader = db.get(SalesAgent, team.leader_sales_agent_id) if team.leader_sales_agent_id else None
    return {
        "id": team.id,
        "name": team.name,
        "is_active": team.is_active,
        "leader_sales_agent_id": team.leader_sales_agent_id,
        "leader_label": agent_label(leader) if leader else None,
        "member_count": sum(1 for m in members if not m["left"]),
        "on": on,
        "members": members,
        "moved": [m.__dict__ for m in (moved or [])],
        "created_at": team.created_at,
        "updated_at": team.updated_at,
    }


def agent_options(db: Session, *, company_id: str) -> List[dict]:
    """Active agents for the team modal, each with the team they are in now (S6-12, S6-15)."""
    agents = _visible_agents(db, company_id).filter(SalesAgent.is_active.is_(True)).all()
    current = dict(
        db.query(SalesTeamMember.sales_agent_id, SalesTeam)
        .join(SalesTeam, SalesTeam.id == SalesTeamMember.sales_team_id)
        .filter(SalesTeamMember.valid_to.is_(None))
        .all()
    )
    out = []
    for agent in sorted(agents, key=agent_label):
        team = current.get(agent.id)
        out.append(
            {
                "id": agent.id,
                "code": agent.sales_agent,
                "label": agent_label(agent),
                "team_id": team.id if team else None,
                "team_name": team.name if team else None,
            }
        )
    return out
