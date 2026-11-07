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
    # The dealer target that replaces one in a period it reaches a tier (Q5: the answer names it).
    replacing_ids = {t.replaced_by_target_id for t in targets if t.replaced_by_target_id}
    replacing = (
        dict(db.query(SalesTarget.id, SalesTarget.target_no).filter(SalesTarget.id.in_(replacing_ids)))
        if replacing_ids else {}
    )

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
                "_agent_id": agent.id if agent else None,
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
                "replaced_by": replacing.get(target.replaced_by_target_id) if fig["replaced"] else None,
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
    """`agent_target_summary`: one row per target SUBJECT over the window (AGENT-COMMISSION-ALL, owner 8 Nov): each
    agent, each team, each dealer, deterministic, from `_target_rows` (the target page's own per-period figures) with
    nothing recomputed but sums and counts.

    Owner answers on the behaviour card: an agent's row is its own agent targets only (Q1 a: a dealer target is paid
    to the dealer's account, so it is the dealer's row, never folded into the agent who owns its accounts); a team's
    row is its team target's own payout, named "Team X" and no person (Q2 a, Q3 a), and its members are the agent rows
    whose `team` is X (Q2 b); a dealer is named as the Dealers tab names it, `agent` being the agent who owns every
    counted account. Dealer targets with the same name are one dealer (a target and the one that replaces it, Q5).

    Matching (`computed.names_exact`): an agent by code, name, "CODE - Name" or the person behind several codes
    (`SalesAgent.person_label`); a team with or without "Team"; a dealer by its name or any counted account's code or
    name. A period with a target of 0 adds nothing to target, achieved and % (no % on the screen either)."""
    from app.services.sales import achievement_service as ach
    from app.services.sales import target_service as ts
    from app.services.sales.team_service import agent_label

    periods = _target_rows(db, user_id, own_only, date_from, date_to, limit=limit)
    dealer_ids = [r["target_id"] for r in periods if r["subject_kind"] == "dealer"]
    accounts = ts._accounts_by_target(db, dealer_ids) if dealer_ids else {}
    agent_ids = {c.sales_agent_id for customers in accounts.values() for c in customers if c.sales_agent_id}
    agent_ids |= {r["_agent_id"] for r in periods if r["_agent_id"]}
    agents = {a.id: a for a in db.query(SalesAgent).filter(SalesAgent.id.in_(agent_ids))} if agent_ids else {}
    person = {agent_label(a): _norm(a.person_label) for a in agents.values() if _norm(a.person_label)}

    def subject(row: dict) -> tuple[str, str, dict]:
        """(name, kind, extra fields and names)."""
        if row["subject_kind"] == "agent":
            name = row["agent"] or "(no agent)"
            names = [person[name]] if name in person else []
            return name, "agent", {"agent": row["agent"], "team": row["team"], "_names": {"owner": names, "agent": names}}
        if row["subject_kind"] == "team":
            team = row["team"] or row["subject"]
            return f"Team {team}", "team", {"agent": None, "team": None, "_names": {"owner": [_norm(team)]}}
        customers = accounts.get(row["target_id"], [])
        owners = {c.sales_agent_id for c in customers}
        owner = (
            agent_label(agents[next(iter(owners))])
            if len(owners) == 1 and None not in owners and next(iter(owners)) in agents else None
        )
        names = [_norm(x) for c in customers for x in (c.customer_code, c.customer_name) if _norm(x)]
        return row["subject"], "dealer", {
            "agent": owner, "team": None, "_names": {"owner": names, "agent": [person[owner]] if owner in person else []},
        }

    per: dict[tuple, dict] = {}
    for row in periods:
        name, kind, extra = subject(row)
        out = per.setdefault((kind, name), {
            "id": f"{kind}:{name}", "owner": name, "owner_kind": kind, "period": row["period_start"],
            "agent": extra["agent"], "team": extra["team"], "periods": 0, "targets": set(), "target_value": 0.0,
            "achieved_value": 0.0, "commission": None, "bonus": None, "payout": None, "replaced_by": None,
            "_names": {k: set() for k in ("owner", "agent")}, "_kinds": set(), "_complete": True, "_summed": False,
            "_zero": set(), "_replaced": set(), "_has_commission": False,
        })
        if out["agent"] != extra["agent"]:
            # Dealer targets of one name whose accounts different agents own: no single owning agent.
            out["agent"] = None
        for key, values in extra["_names"].items():
            out["_names"][key].update(values)
        out["periods"] += 1
        out["targets"].add(row["target_no"])
        out["period"] = min(out["period"], row["period_start"])
        out["_kinds"].add(row["subject_kind"])
        if row["metric"] != "amount" or row["target_value"] is None:
            # Units, or a points target without a ratio: no RM figure to add (the page shows none either).
            out["_complete"] = False
        elif row["target_value"] <= 0:
            # A target of 0 has no % on the screen; its sales would swamp the row's % (owner C3, 8 Nov).
            out["_zero"].add(row["target_no"])
        else:
            out["target_value"] += row["target_value"]
            out["achieved_value"] += row["achieved_value"] or 0.0
            out["_summed"] = True
        if row["commission"] is not None:
            out["_has_commission"] = True
        for k in ("commission", "bonus", "payout"):
            if row[k] is not None:
                out[k] = round((out[k] or 0.0) + row[k], 2)
        if row.get("replaced_by"):
            out["_replaced"].add((row["target_no"], row["replaced_by"]))
    rows = []
    for out in per.values():
        summed = out.pop("_summed")
        whole = out.pop("_complete")
        complete = whole and summed
        # Empty figures said in words in the result itself (crew live x3, 8 Nov): never "RM 0" for no commission,
        # and no target or achieved figure on a row that holds only targets of 0 (the note leaves them out).
        empty = {}
        if not out["_has_commission"]:
            empty.update(dict.fromkeys(("commission", "bonus", "payout"), NO_COMMISSION))
        if whole and not summed and out["_zero"]:
            empty.update(dict.fromkeys(("target_value", "achieved_value", "achieved_pct"), ZERO_TARGET))
        out["_empty"] = empty
        out["kinds"] = ", ".join(sorted(out.pop("_kinds")))
        out["targets"] = len(out["targets"])
        goal, achieved = round(out["target_value"], 2), round(out["achieved_value"], 2)
        out["target_value"] = goal if complete else None
        out["achieved_value"] = achieved if complete else None
        out["achieved_pct"] = (
            ach.achieved_pct(Decimal(str(achieved)), Decimal(str(goal))) if complete and goal else None
        )
        out["replaced_by"] = ", ".join(sorted({by for _no, by in out["_replaced"]})) or None
        out["_names"] = {k: sorted(v) for k, v in out["_names"].items()}
        out["_zero"] = sorted(out["_zero"])
        out["_replaced"] = sorted(out["_replaced"])
        rows.append(out)
    # Agents by name, then teams, then dealers (the result ranks them by payout, `EntityDef.rank_by`).
    rows.sort(key=lambda r: ({"agent": 0, "team": 1}.get(r["owner_kind"], 2), r["owner"]))
    return rows


#: What an empty payout reads as: no commission tiers on any of the row's targets.
NO_COMMISSION = "no commission set"
#: What target, achieved and % read as on a row of only targets of 0.
ZERO_TARGET = "left out (target of 0)"


def _norm(value) -> str:
    return " ".join(str(value or "").split()).lower()


def _some(names: list[str], most: int = 5) -> str:
    shown = ", ".join(names[:most])
    return f"{shown} and {len(names) - most} more" if len(names) > most else shown


def _summary_note(rows: list[dict]) -> str | None:
    """What the answer must say about the rows it shows (owner C3, Q5): which targets of 0 were left out of target
    and achieved, whose payout is empty because no commission is set (never "RM 0"), and a replaced dealer period."""
    parts = []
    zero = [no for r in rows for no in r["_zero"]]
    if zero:
        parts.append(f"Left out of target and achieved (a target of 0): {_some(zero)}.")
    unset = [r["owner"] for r in rows if not r["_has_commission"]]
    if unset:
        parts.append(f"No commission is set on the targets of {_some(unset)}.")
    for r in rows:
        for no, by in r["_replaced"]:
            parts.append(
                f"{no} ({r['owner']}) is replaced by {by} in the periods that target reached a tier, so it pays 0 there."
            )
    return " ".join(parts) or None


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
             "agent_target_summary for payout of an agent, team or dealer",
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
        label="Commission payout by agent, team or dealer",
        module="sales",
        model=SalesTarget,
        view_permission=TARGETS_VIEW,
        own_permission="sales.targets.view_own",
        own_clause=_own,
        fields={
            "owner": FieldDef(
                "Agent, team or dealer", kind="text", agent_id=True,
                note="'CODE - Name' for an agent (its own agent targets), 'Team X' for a team target, the dealer's "
                     "name as the Dealers tab shows it. Matched by an agent's code, name or person, a team's name "
                     "with or without 'Team', a dealer's name or any of its account codes or names.",
            ),
            "owner_kind": FieldDef("Kind", kind="text", note="agent, team or dealer."),
            "agent": FieldDef(
                "Agent", kind="text", agent_id=True,
                note="The agent itself on an agent row; on a dealer row the agent who owns every counted account. "
                     "agent eq A also returns A's dealers: A's own payout is agent=A (or owner_kind eq agent), A's "
                     "dealers are agent eq A with owner_kind eq dealer.",
            ),
            "team": FieldDef(
                "Agent's team", kind="text",
                note="Agent rows only, the agent's team today: team eq X lists the agents of team X (their own "
                     "targets); the team target itself is the owner 'Team X' row.",
            ),
            "period": FieldDef(
                "Period", kind="date",
                note="The window: between [from, to] (last month, this quarter); without it, the current periods.",
            ),
            "kinds": FieldDef("Target kinds", kind="text"),
            "periods": FieldDef("Periods", kind="number"),
            "targets": FieldDef("Targets", kind="number"),
            "target_value": FieldDef(
                "Target (RM)", kind="number",
                note="Empty when a units or no-ratio target is in the row; a target of 0 adds nothing.",
            ),
            "achieved_value": FieldDef("Achieved (RM)", kind="number"),
            "achieved_pct": FieldDef("Achieved %", kind="number"),
            "commission": FieldDef("Commission", kind="number"),
            "bonus": FieldDef("Bonus", kind="number"),
            "payout": FieldDef(
                "Commission payout", kind="number",
                note="Commission plus bonus over the window; empty (not 0) when no commission is set.",
            ),
            "replaced_by": FieldDef(
                "Replaced by", kind="text",
                note="A dealer target that replaced this dealer's own target in a period it reached a tier (pays 0).",
            ),
        },
        name_by=("owner",),
        hint="COMMISSION PAYOUT / TARGET vs ACHIEVED for an agent, a team or a dealer, or per agent / team / dealer: "
             "one row per agent, team and dealer, highest payout first, totals row; no period = this year. One of them: agent=<code or name as said> "
             "(an agent, team or dealer); only dealers or teams: owner_kind eq dealer|team",
        list_fields=("owner_kind", "targets", "target_value", "achieved_value", "achieved_pct", "payout"),
        row_totals=("targets", "commission", "bonus", "payout"),
        compute=_summary_rows,
        window_field="period",
        brand_blind=True,
        own_note="You see only your own agents' targets: team and dealer payouts are not visible to you.",
        row_note=_summary_note,
        rank_by="payout",
        default_window="this_year",
        # Every agent, team and dealer of a normal window in one result (the table is rendered by code).
        default_limit=50,
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
