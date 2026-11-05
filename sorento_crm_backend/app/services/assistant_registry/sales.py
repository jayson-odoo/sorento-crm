"""Sales targets (`/sales/targets`): one row per target period with the target page's own figures (achieved, %,
tier reached, commission, bonus), and the sales agent lookup.

A target's achievement and commission are never stored (`models/sales.py` SalesTarget, SalesTargetCommissionTier):
`compute` reads them from `target_service.period_figures`, the target page's own calls batched. The screen is
`sales.targets.view` (everything) or `sales.targets.view_own` (the agent targets of the user's own sales agents,
owner ruling 5 Nov 23:2x), and so is this entity: `own_scope.sales_target_clause` for both. An agent this reader cannot see is left out, as on the Agents tab
(`target_service.list_all_targets`).
"""
from __future__ import annotations

from datetime import date

from app.models.sales import SalesTarget
from app.models.sales_agent import SalesAgent
from app.services.assistant_registry import register
from app.services.assistant_registry.types import EntityDef, FieldDef

TARGETS_VIEW = "sales.targets.view"


def _target_rows(db, user_id: str, own_only: bool, date_from: date, date_to: date, *, limit: int) -> list[dict]:
    from sqlalchemy import or_, select

    from app.models.sales import SalesTargetPeriod, SalesTeam
    from app.services.sales import target_service as ts
    from app.services.sales.team_service import _today, _visible_agents, agent_label

    overlapping = select(SalesTargetPeriod.target_id).where(
        SalesTargetPeriod.period_start <= date_to, SalesTargetPeriod.period_end >= date_from
    )
    mine = []
    if own_only:
        # `sales.targets.view_own`: the screen's own rule (`api/v1/sales/targets.py` `_load`, `_own_rows`).
        from app.services import own_scope

        mine = [own_scope.sales_target_clause(own_scope.me(db, user_id))]
    # The session's company scope (stamped by `run_as_user`) narrows SalesTarget and its periods to the user's
    # company. The periods are counted before anything is computed: past `limit` the window is refused.
    periods = (
        db.query(SalesTargetPeriod.id)
        .join(SalesTarget, SalesTarget.id == SalesTargetPeriod.target_id)
        .filter(SalesTargetPeriod.period_start <= date_to, SalesTargetPeriod.period_end >= date_from, *mine)
        .limit(limit + 1)
        .count()
    )
    if periods > limit:
        from app.services.assistant_registry.query import QueryRefused

        raise QueryRefused("timeout", f"More than {limit} target periods in that window; narrow it (a month, an agent).")
    targets = (
        db.query(SalesTarget).filter(SalesTarget.id.in_(overlapping), *mine).order_by(SalesTarget.target_no).all()
    )
    if not targets:
        return []
    agent_ids = {t.sales_agent_id for t in targets if t.sales_agent_id}
    agents: dict[str, SalesAgent] = {}
    for company_id in {t.company_id for t in targets}:
        if agent_ids:
            agents.update({a.id: a for a in _visible_agents(db, company_id).filter(SalesAgent.id.in_(agent_ids))})
    targets = [t for t in targets if t.subject_kind != "agent" or t.sales_agent_id in agents]
    team_ids = {t.sales_team_id for t in targets if t.sales_team_id}
    teams = {x.id: x for x in db.query(SalesTeam).filter(SalesTeam.id.in_(team_ids))} if team_ids else {}
    today = _today()
    # An agent's team is the one it is in today, as the Agents tab shows it.
    team_of_agent = {m.sales_agent_id: t for m, t in ts._covering_on(db, today)}
    dealer_accounts = ts._accounts_by_target(db, [t.id for t in targets if t.subject_kind == "dealer"])

    rows = []
    for target, period, fig in ts.period_figures(db, targets, date_from=date_from, date_to=date_to):
        agent = agents.get(target.sales_agent_id) if target.sales_agent_id else None
        if target.subject_kind == "agent":
            subject = agent_label(agent) if agent else ""
            team = team_of_agent.get(target.sales_agent_id)
        elif target.subject_kind == "team":
            team = teams.get(target.sales_team_id)
            subject = team.name if team else ""
        else:
            team = None
            # As the chat target lines (`period_progress`): no ledger marker on a single account's name.
            from app.services.ledger_family import ledger_family_label

            subject = ledger_family_label(ts.dealer_label(db, dealer_accounts.get(target.id, [])))
        # A points target with no ratio on file has no RM figure (the page flags it, `period_progress` blanks it).
        missing = fig["ratio_missing"]
        goal = None if missing else fig["target_value"]
        pct = None if missing else fig["achieved_pct"]
        commission = fig["commission_earned"]
        bonus = fig["bonus_earned"]
        has_commission = (target.commission_method or "none") != "none"
        rows.append(
            {
                "id": period.id,
                "target_id": target.id,
                "target_no": target.target_no,
                "name": target.name,
                "subject_kind": target.subject_kind,
                "subject": subject,
                # "CODE - Name", as the screens print an agent, so "Agent A" (a name) matches as well as the code
                # (crew pass on 74b6b751: a code-only field found "0 records" for a name).
                "agent": agent_label(agent) if agent else None,
                "agent_code": agent.sales_agent if agent else None,
                "team": team.name if team else None,
                "period": period.period_start,
                "period_start": period.period_start,
                "period_end": period.period_end,
                "is_current": period.period_start <= today <= period.period_end,
                "metric": target.metric,
                "basis": target.basis,
                "target_value": goal,
                "achieved_value": fig["achieved_value"],
                "achieved_pct": pct,
                "below_target": None if goal is None else fig["achieved_value"] < goal,
                "shortfall": None if goal is None else round(max(goal - fig["achieved_value"], 0.0), 2),
                "ratio_missing": missing,
                "tier_reached": fig["tier_reached"],
                "commission": commission if has_commission else None,
                "bonus": bonus if has_commission else None,
                "payout": round((commission or 0) + (bonus or 0), 2) if has_commission else None,
                "replaced": fig["replaced"],
            }
        )
    return rows


def _agent_rows(db, user_id: str, own_only: bool, date_from: date, date_to: date, *, limit: int) -> list[dict]:
    """One row per agent: the agent targets' periods in the window (`_target_rows`, the target page's own figures),
    summed per agent. A sum of the page's figures, nothing recomputed; the % is `achievement_service.achieved_pct`
    over the sums, as the Agents tab shows a whole range's (`target_service.list_all_targets`)."""
    from decimal import Decimal

    from app.services.sales import achievement_service as ach

    per: dict[str, dict] = {}
    for row in _target_rows(db, user_id, own_only, date_from, date_to, limit=limit):
        if row["subject_kind"] != "agent" or not row["agent"]:
            continue
        out = per.setdefault(row["agent"], {
            "id": row["agent_code"], "agent": row["agent"], "agent_code": row["agent_code"], "team": row["team"],
            "period": row["period_start"], "periods": 0, "targets": set(), "target_value": 0.0, "achieved_value": 0.0,
            "commission": None, "bonus": None, "payout": None, "ratio_missing": False,
        })
        out["periods"] += 1
        out["targets"].add(row["target_no"])
        out["period"] = min(out["period"], row["period_start"])
        out["achieved_value"] += row["achieved_value"] or 0.0
        if row["target_value"] is None:
            out["ratio_missing"] = True
        else:
            out["target_value"] += row["target_value"]
        for key in ("commission", "bonus", "payout"):
            if row[key] is not None:
                out[key] = round((out[key] or 0.0) + row[key], 2)
    rows = []
    for out in per.values():
        goal = None if out["ratio_missing"] else round(out["target_value"], 2)
        achieved = round(out["achieved_value"], 2)
        out.update({
            "targets": ", ".join(sorted(out["targets"])),
            "target_value": goal,
            "achieved_value": achieved,
            "achieved_pct": None if goal is None else ach.achieved_pct(Decimal(str(achieved)), Decimal(str(goal))),
            "below_target": None if goal is None else achieved < goal,
            "shortfall": None if goal is None else round(max(goal - achieved, 0.0), 2),
        })
        rows.append(out)
    return rows


def _own(me):
    from app.services import own_scope

    return own_scope.sales_target_clause(me)


register(
    EntityDef(
        key="sales_agent",
        label="Sales agents",
        # The sales agents master's module (`/master-data`), so a lookup is gated with the screen that holds it.
        module="product",
        # Not company scoped (a shared master, `company_id` NULL): reached only by the foreign key of a company
        # scoped row, so the join needs no company predicate of its own. Deliberate; not a missing filter.
        model=SalesAgent,
        view_permission=None,
        fields={
            "code": FieldDef("Agent code", column="sales_agent"),
            "name": FieldDef("Agent name", column="description"),
        },
    ),
    EntityDef(
        key="sales_target",
        label="Sales target periods",
        module="sales",
        model=SalesTarget,
        view_permission=TARGETS_VIEW,
        own_permission="sales.targets.view_own",
        own_clause=_own,
        fields={
            "target_no": FieldDef("Target", kind="text"),
            "subject": FieldDef(
                "Agent, team or dealer", kind="text",
                note="Who the target is for: 'CODE - Name' for an agent, the team name, or the dealer's accounts.",
            ),
            "name": FieldDef("Target name", kind="text"),
            "subject_kind": FieldDef("Target for", kind="text", note="agent, team or dealer."),
            "agent": FieldDef(
                "Agent", kind="text", note="'CODE - Name', agent targets only; filter with contains on the code or name.",
            ),
            "agent_code": FieldDef("Agent code", kind="text"),
            "team": FieldDef("Team", kind="text", note="The agent's team today, or the team of a team target."),
            "period": FieldDef(
                "Period", kind="date",
                note="The date window: between [from, to] reads every period overlapping it (last month, this "
                     "quarter); without it, the periods containing today.",
            ),
            "period_start": FieldDef("Period start", kind="date"),
            "period_end": FieldDef("Period end", kind="date"),
            "is_current": FieldDef("Current period", kind="boolean"),
            "metric": FieldDef("Metric", kind="text", note="amount (RM) or quantity (units)."),
            "basis": FieldDef("Counts", kind="text", note="ordered, delivered or invoiced sales."),
            "target_value": FieldDef("Target", kind="number", note="RM on an amount target, units on a quantity one."),
            "achieved_value": FieldDef("Achieved", kind="number"),
            "achieved_pct": FieldDef("Achieved %", kind="number"),
            "below_target": FieldDef(
                "Below target", kind="boolean", note="Achieved under 100% of the period's target.",
            ),
            "shortfall": FieldDef("Short by", kind="number", note="Target minus achieved, 0 once reached."),
            "tier_reached": FieldDef("Tier reached", kind="number"),
            "commission": FieldDef(
                "Commission", kind="number",
                note="The period's commission as the target page computes it; empty on a target without "
                     "commission. Commission payout = payout (commission + bonus).",
            ),
            "bonus": FieldDef("Bonus", kind="number"),
            "payout": FieldDef(
                "Commission payout", kind="number", note="Commission plus bonus of the period; sum it for a payout.",
            ),
            "ratio_missing": FieldDef(
                "Point ratio missing", kind="boolean",
                note="A points target with no RM per point on file for the period: target and % are empty.",
            ),
            "replaced": FieldDef(
                "Replaced by dealer target", kind="boolean",
                note="True when the dealer's own target reached a tier, so this one pays nothing.",
            ),
        },
        name_by=("target_no", "subject"),
        screen_path="/sales/targets/{target_id}",
        pages=("/sales/targets",),
        routes=("GET /api/v1/sales/targets",),
        hint="one row per target PERIOD (agents, teams, dealers): achieved, below_target, tier, commission, payout. "
             "For anything PER AGENT or for one agent use agent_target instead",
        list_fields=("period_start", "period_end", "target_value", "achieved_value", "achieved_pct", "payout"),
        compute=_target_rows,
        window_field="period",
        # Achievement counts every brand's sales: refused on a brand-scoped contact's turn (security review B1).
        brand_blind=True,
    ),
    # Crew pass on 74b6b751: "payout per agent" grouped targets (dealers, a test target) and "Agent A last month"
    # took 6 calls. One row per agent answers both in one query.
    EntityDef(
        key="agent_target",
        label="Sales targets by agent",
        module="sales",
        model=SalesTarget,
        view_permission=TARGETS_VIEW,
        own_permission="sales.targets.view_own",
        own_clause=_own,
        fields={
            "agent": FieldDef("Agent", kind="text", note="'CODE - Name'; filter with contains on the code or name."),
            "agent_code": FieldDef("Agent code", kind="text"),
            "team": FieldDef("Team", kind="text"),
            "period": FieldDef(
                "Period", kind="date",
                note="The date window: between [from, to] (last month, this quarter); without it, the current periods.",
            ),
            "periods": FieldDef("Periods", kind="number"),
            "targets": FieldDef("Targets", kind="text"),
            "target_value": FieldDef("Target", kind="number"),
            "achieved_value": FieldDef("Achieved", kind="number"),
            "achieved_pct": FieldDef("Achieved %", kind="number"),
            "below_target": FieldDef("Below target", kind="boolean"),
            "shortfall": FieldDef("Short by", kind="number"),
            "commission": FieldDef("Commission", kind="number"),
            "bonus": FieldDef("Bonus", kind="number"),
            "payout": FieldDef("Commission payout", kind="number", note="Commission plus bonus over the window."),
        },
        name_by=("agent",),
        hint="ONE row per agent (agent targets only): target, achieved, %, below_target, commission, payout. Use for "
             "payout or target PER AGENT and for one agent (agent contains <code or name>); no period = current periods",
        list_fields=("target_value", "achieved_value", "achieved_pct", "payout"),
        compute=_agent_rows,
        window_field="period",
        brand_blind=True,
    ),
)
