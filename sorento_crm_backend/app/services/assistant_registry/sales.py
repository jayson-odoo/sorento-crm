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
from decimal import Decimal

from app.models.sales import SalesTarget
from app.models.sales_agent import SalesAgent
from app.services.assistant_registry import register
from app.services.assistant_registry.types import EntityDef, FieldDef

TARGETS_VIEW = "sales.targets.view"
#: The owner of a dealer target no single agent owns every account of (crew pass on ddd978ef).
UNASSIGNED = "Unassigned"


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
                "below_target": _below(pct),
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


def _below(pct) -> bool:
    """The Targets screen's own reading: a target is reached only when its Achieved % is shown and at least 100
    (`sorento_crm_frontend/app/(protected)/sales/targets/components/SalesTargetsView.tsx:389`, `pct !== null &&
    pct >= 100` is the green "reached" figure); anything else, a target of 0 or a points target with no ratio (no %)
    included, is below target. The % is the page's own (`achievement_service.achieved_pct`, one decimal)."""
    return not (pct is not None and pct >= 100)


def _summary_rows(db, user_id: str, own_only: bool, date_from: date, date_to: date, *, limit: int) -> list[dict]:
    """`agent_target_summary`: one row per owner per period, deterministic, from `_target_rows` (the target page's
    own per-period figures) with nothing recomputed but sums and counts.

    The owner of a target is the rule the target service already uses for a salesperson's view
    (`target_chat_scope`): an agent target is its agent's; a dealer target is the agent's who owns EVERY counted
    account (`Customer.sales_agent_id`), else "(no single agent)"; a team target is the team's. So the rows' counts
    and payouts add up to every target period on the screens."""
    from app.models.sales_agent import SalesAgent
    from app.services.sales import achievement_service as ach
    from app.services.sales import target_service as ts
    from app.services.sales.team_service import agent_label

    periods = _target_rows(db, user_id, own_only, date_from, date_to, limit=limit)
    dealer_ids = [r["target_id"] for r in periods if r["subject_kind"] == "dealer"]
    accounts = ts._accounts_by_target(db, dealer_ids) if dealer_ids else {}
    agent_ids = {c.sales_agent_id for customers in accounts.values() for c in customers if c.sales_agent_id}
    agents = {a.id: a for a in db.query(SalesAgent).filter(SalesAgent.id.in_(agent_ids))} if agent_ids else {}

    def owner(row: dict) -> tuple[str, str]:
        if row["subject_kind"] == "agent":
            return row["agent"] or "(no agent)", "agent"
        if row["subject_kind"] == "team":
            return f"Team {row['team'] or row['subject']}", "team"
        owners = {c.sales_agent_id for c in accounts.get(row["target_id"], [])}
        if len(owners) == 1 and None not in owners and next(iter(owners)) in agents:
            return agent_label(agents[next(iter(owners))]), "agent"
        return UNASSIGNED, "none"

    per: dict[str, dict] = {}
    for row in periods:
        name, kind = owner(row)
        # ONE row per owner over the whole window (crew pass on ddd978ef: per owner and period put one agent on
        # four rows).
        out = per.setdefault(name, {
            "id": name, "owner": name, "owner_kind": kind, "period": row["period_start"],
            "periods": 0, "targets": set(), "target_value": 0.0, "achieved_value": 0.0,
            "commission": None, "bonus": None, "payout": None, "_kinds": set(), "_complete": True,
        })
        out["periods"] += 1
        out["targets"].add(row["target_no"])
        out["period"] = min(out["period"], row["period_start"])
        out["_kinds"].add(row["subject_kind"])
        if row["metric"] != "amount" or row["target_value"] is None:
            # Units, or a points target without a ratio: no RM figure to add (the page shows none either).
            out["_complete"] = False
        else:
            out["target_value"] += row["target_value"]
            out["achieved_value"] += row["achieved_value"] or 0.0
        for k in ("commission", "bonus", "payout"):
            if row[k] is not None:
                out[k] = round((out[k] or 0.0) + row[k], 2)
    rows = []
    for out in per.values():
        complete = out.pop("_complete")
        out["kinds"] = ", ".join(sorted(out.pop("_kinds")))
        out["targets"] = len(out["targets"])
        goal, achieved = round(out["target_value"], 2), round(out["achieved_value"], 2)
        out["target_value"] = goal if complete else None
        out["achieved_value"] = achieved if complete else None
        out["achieved_pct"] = (
            ach.achieved_pct(Decimal(str(achieved)), Decimal(str(goal))) if complete and goal else None
        )
        rows.append(out)
    # Agents by name, then teams, then the targets no single agent owns, once, last.
    rows.sort(key=lambda r: ({"agent": 0, "team": 1}.get(r["owner_kind"], 2), r["owner"]))
    return rows


def _target_list_rows(db, user_id: str, own_only: bool, date_from: date, date_to: date, *, limit: int) -> list[dict]:
    """`target_list`: the Targets screens' own rows (`target_service.list_all_targets`, Teams, Agents and Dealers
    tabs: one row per target, its whole range's target, achieved and %), for targets whose range overlaps the
    window. Reached is the screen's green figure (`_below`). An own-only holder gets the Agents tab cut to their own
    agents, as the screen cuts it (`api/v1/sales/targets.py` `_own_rows`)."""
    from app.services import own_scope
    from app.services.sales import target_service as ts

    mine = set(own_scope.me(db, user_id).agent_ids) if own_only else None
    rows = []
    for subject in ("agent", "team", "dealer"):
        if mine is not None and subject != "agent":
            continue
        for r in ts.list_all_targets(db, subject=subject)["rows"]:
            if mine is not None and r.get("sales_agent_id") not in mine:
                continue
            if r["start_date"] > date_to or r["end_date"] < date_from:
                continue
            rows.append({
                "id": r["target_id"], "target_id": r["target_id"], "target_no": r["target_no"],
                "subject": r["subject_label"], "subject_kind": subject, "period": r["start_date"],
                "start_date": r["start_date"], "end_date": r["end_date"], "target_value": r["target_value"],
                "achieved_value": r["achieved_value"], "achieved_pct": r["achieved_pct"],
                "reached": not _below(r["achieved_pct"]),
            })
            if len(rows) > limit:
                from app.services.assistant_registry.query import QueryRefused

                raise QueryRefused("timeout", f"More than {limit} targets in that window; narrow it.")
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
                "Agent", kind="text", agent_id=True,
                note="'CODE - Name', agent targets only; filter with eq on the code or name.",
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
                "Below target", kind="boolean",
                note="As the Targets screen reads it: Achieved % shown and under 100, or no % (a target of 0).",
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
        hint="one row per target period; for one named target only (TGT-...). Not in the index: use "
             "agent_target_summary for target questions",
        in_index=False,
        list_fields=("period_start", "period_end", "target_value", "achieved_value", "achieved_pct", "payout"),
        compute=_target_rows,
        window_field="period",
        # Achievement counts every brand's sales: refused on a brand-scoped contact's turn (security review B1).
        brand_blind=True,
    ),
    # Crew passes on 0463b805 and ddd978ef (5 Nov): two deterministic target entities, one per question kind.
    EntityDef(
        key="agent_target_summary",
        label="Sales targets by agent",
        module="sales",
        model=SalesTarget,
        view_permission=TARGETS_VIEW,
        own_permission="sales.targets.view_own",
        own_clause=_own,
        fields={
            "owner": FieldDef(
                "Agent", kind="text", agent_id=True,
                note="'CODE - Name' (agent targets and the dealers whose accounts the agent owns), 'Team X', or "
                     "'Unassigned'; filter with eq on a code or name.",
            ),
            "owner_kind": FieldDef("Owner kind", kind="text", note="agent, team or none."),
            "period": FieldDef(
                "Period", kind="date",
                note="The window: between [from, to] (last month, this quarter); without it, the current periods.",
            ),
            "kinds": FieldDef("Target kinds", kind="text"),
            "periods": FieldDef("Periods", kind="number"),
            "targets": FieldDef("Targets", kind="number"),
            "target_value": FieldDef("Target (RM)", kind="number", note="Empty when a units or no-ratio target is in the row."),
            "achieved_value": FieldDef("Achieved (RM)", kind="number"),
            "achieved_pct": FieldDef("Achieved %", kind="number"),
            "commission": FieldDef("Commission", kind="number"),
            "bonus": FieldDef("Bonus", kind="number"),
            "payout": FieldDef("Commission payout", kind="number", note="Commission plus bonus over the window."),
        },
        name_by=("owner",),
        hint="PAYOUT / COMMISSION / TARGET vs ACHIEVED per agent or for one agent: one row per agent over the window, "
             "totals row. One agent: agent=<code or name as said>",
        list_fields=("targets", "target_value", "achieved_value", "achieved_pct", "payout"),
        row_totals=("targets", "commission", "bonus", "payout"),
        compute=_summary_rows,
        window_field="period",
        brand_blind=True,
    ),
    EntityDef(
        key="target_list",
        label="Sales targets",
        module="sales",
        model=SalesTarget,
        view_permission=TARGETS_VIEW,
        own_permission="sales.targets.view_own",
        own_clause=_own,
        fields={
            "target_no": FieldDef("Target", kind="text"),
            "subject": FieldDef("Agent, team or dealer", kind="text", agent_id=True, note="As the Targets screen names it."),
            "subject_kind": FieldDef("Target for", kind="text", note="agent, team or dealer."),
            "period": FieldDef(
                "Period", kind="date",
                note="The window: targets whose date range overlaps between [from, to]; without it, targets running today.",
            ),
            "start_date": FieldDef("Start", kind="date"),
            "end_date": FieldDef("End", kind="date"),
            "target_value": FieldDef("Target", kind="number"),
            "achieved_value": FieldDef("Achieved", kind="number"),
            "achieved_pct": FieldDef("Achieved %", kind="number"),
            "reached": FieldDef(
                "Reached", kind="boolean", note="Achieved % shown and at least 100, the Targets screen's green figure.",
            ),
        },
        name_by=("target_no", "subject"),
        hint="WHICH TARGETS / BELOW TARGET / NOT REACHED: one row per target as the Targets screens list it. Below "
             "target: reached eq false; the total is the count",
        list_fields=("subject_kind", "end_date", "target_value", "achieved_value", "achieved_pct"),
        always_note="Not reached = achieved under 100% of target, as the Targets screen shows it.",
        screen_path="/sales/targets/{target_id}",
        pages=("/sales/targets",),
        routes=("GET /api/v1/sales/targets",),
        compute=_target_list_rows,
        window_field="period",
        brand_blind=True,
    ),
)
