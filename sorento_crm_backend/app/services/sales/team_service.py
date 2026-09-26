"""Sales teams and their dated membership (plan 3.8; UAC S6-1 to S6-3, S6-14, S6-15).

The only writer of `sales.team_members`, which is why "no two memberships of one agent in one
company overlap" is checked here rather than by an exclusion constraint (plan 3.8).

The dated rule, stated once: an order of agent A dated X counts for team T when A has a row for
T with `coalesce(valid_from, -infinity) <= X <= coalesce(valid_to, infinity)`.

- An agent's FIRST team: `valid_from` empty, so their earlier orders count too (V1).
- A move on D (the agent is open in another team): the old row closes at D - 1, a new row
  opens at D. D is never later than today (a future move is a calendar note, not a membership).
- Removing an agent: the open row closes at today and stays, so past periods keep its orders.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Dict, Iterable, List, Optional, Tuple
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_
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
    from app.services.company_scope import DEFAULT_COMPANY_ID, get_company_scope

    scope = get_company_scope(db)
    if isinstance(scope, frozenset) and len(scope) == 1:
        return next(iter(scope))
    if scope is None:
        return DEFAULT_COMPANY_ID
    raise AppException(
        status_code=400,
        message="Pick one active company before working with sales teams.",
        code="SALES_COMPANY_AMBIGUOUS",
    )


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


def _assert_name_free(db: Session, company_id: str, name: str, exclude_id: Optional[str]) -> None:
    query = db.query(SalesTeam.id).filter(
        SalesTeam.company_id == company_id, func.lower(SalesTeam.name) == name.lower()
    )
    if exclude_id:
        query = query.filter(SalesTeam.id != exclude_id)
    if query.first() is not None:
        raise AppException(
            status_code=409,
            message=f'A sales team called "{name}" already exists.',
            code="SALES_TEAM_NAME_TAKEN",
        )


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
) -> Tuple[SalesTeam, List[Move]]:
    name = name.strip()
    _assert_name_free(db, company_id, name, None)
    team = SalesTeam(company_id=company_id, name=name, is_active=is_active)
    db.add(team)
    db.flush()
    moved = set_members(db, team, sales_agent_ids, moves_on=moves_on)
    return team, moved


def create_team(db: Session, **kwargs) -> SalesTeam:
    team, _ = create_team_with_members(db, **kwargs)
    return team


def update_team(
    db: Session, team: SalesTeam, *, name: Optional[str] = None, is_active: Optional[bool] = None
) -> SalesTeam:
    if name is not None:
        name = name.strip()
        _assert_name_free(db, team.company_id, name, team.id)
        team.name = name
    if is_active is not None:
        team.is_active = is_active
    db.flush()
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

    # Left out: close today, keep the row (S6-14).
    for agent_id, member in open_here.items():
        if agent_id not in agents:
            member.valid_to = today

    moved: List[Move] = []
    new_rows: List[SalesTeamMember] = []
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
        current = next((m for m in history if m.valid_to is None), None)

        if current is not None:
            # A move (T2): the other team keeps everything before `moves_on`.
            if current.valid_from is not None and current.valid_from >= moves_on:
                raise _unprocessable(
                    f"{agent_label(agent)} only joined their current team on "
                    f"{current.valid_from.isoformat()}; pick a later Moves on date.",
                    "MEMBERSHIP_OVERLAP",
                )
            current.valid_to = moves_on - timedelta(days=1)
            from_team = db.query(SalesTeam).filter(SalesTeam.id == current.sales_team_id).one()
            moved.append(
                Move(
                    sales_agent_id=agent_id,
                    label=agent_label(agent),
                    from_team_id=from_team.id,
                    from_team_name=from_team.name,
                )
            )
            valid_from: Optional[date] = moves_on
        elif not history:
            valid_from = None  # first team: from the beginning (V1)
        else:
            last = max(history, key=lambda m: m.valid_to)
            if last.sales_team_id == team.id and last.valid_to >= moves_on - timedelta(days=1):
                # Taken out and put back with no gap: one continuous membership.
                last.valid_to = None
                continue
            valid_from = max(moves_on, last.valid_to + timedelta(days=1))

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
    """The team page: members on `on`, plus anyone who left earlier in that month (S6-15)."""
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
        .all()
    )
    members = []
    for member, agent in rows:
        left = member.valid_to is not None and member.valid_to <= on
        members.append(
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
    members.sort(key=lambda m: (m["left"], m["label"]))
    return {
        "id": team.id,
        "name": team.name,
        "is_active": team.is_active,
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
