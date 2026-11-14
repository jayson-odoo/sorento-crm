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
from app.utils.date_format import fmt_date_range

TARGETS_VIEW = "sales.targets.view"


#: W-A (AGENT-COMMISSION-WA): the next rung of the target page's own tier ladder, on a summary row whose subject has
#: one commission target in the window (the note answers target by target, with the assumptions it makes).
NEXT_TIER_FIELDS = {
    "next_tier": FieldDef(
        "Next tier", kind="number",
        note="The next tier's number on the target's ladder; empty at the top tier, without commission, or when the "
             "subject has several targets (then the note answers target by target).",
    ),
    "next_tier_at": FieldDef(
        "Next tier from", kind="number", note="Where the next tier starts: RM, or units on a quantity target.",
    ),
    "to_next_tier": FieldDef(
        "To the next tier", kind="number",
        note="Still to sell to reach the next tier: RM, or units on a quantity target.",
    ),
    "next_tier_payout": FieldDef(
        "Payout at the next tier (RM)", kind="number",
        note="Commission plus bonus the period would pay on reaching the next tier (the same engine as the page).",
    ),
    "next_tier_gain": FieldDef(
        "More at the next tier (RM)", kind="number", note="Payout at the next tier minus the payout now.",
    ),
}


#: `next_tier` (crm_query): what a next-tier question asks, said by the model from the user's meaning in any language.
NEXT_TIER_KINDS = ("distance", "closest", "furthest")
#: `subjects`: whose ranking a closest / furthest question asks for.
NEXT_TIER_SUBJECTS = ("agent", "dealer", "team", "all")
#: The columns of every next-tier answer, whatever else the call listed (crew live x3 on 0c5c7b78: X2 run 3 and W4
#: run 2 dropped them). TGT and payout account come with them (`always_fields`).
NEXT_TIER_COLUMNS = (
    "owner_kind", "to_next_tier", "next_tier", "next_tier_at", "next_tier_payout", "next_tier_gain", "payout",
)


def _next_tier_spec(spec: dict) -> dict:
    """`agent_target_summary`'s `next_tier` / `subjects` arguments as the spec it runs (crew live x3, owner rule:
    the model states the question kind as an argument, code never reads the message): one row per subject (no
    regroup), the next-tier columns, ranked by what is still to sell (furthest first for `furthest`), only the asked
    subjects. closest / furthest without `subjects` is refused so the model asks the user, never guesses."""
    from app.services.assistant_registry.query import QueryRefused

    kind, subjects = spec.get("next_tier"), spec.get("subjects")
    if kind is None:
        if subjects is not None:
            raise QueryRefused("invalid", "`subjects` goes with `next_tier` closest or furthest.")
        return spec
    if kind not in NEXT_TIER_KINDS:
        raise QueryRefused("invalid", "`next_tier` is one of distance, closest, furthest.")
    if subjects is not None and subjects not in NEXT_TIER_SUBJECTS:
        raise QueryRefused("invalid", "`subjects` is one of agent, dealer, team, all.")
    if kind == "distance" and subjects is not None:
        # A distance question names its subject (agent=...); a kind beside it could only contradict it.
        raise QueryRefused("invalid", "`subjects` goes with next_tier closest or furthest, not distance.")
    if kind != "distance" and subjects is None:
        raise QueryRefused(
            "invalid",
            f"`next_tier` {kind} needs `subjects`: agent, dealer, team or all. If the user did not say whose "
            "ranking they want, ask them one short question (agents, dealers or teams?) instead of querying.",
        )
    out = {k: v for k, v in spec.items() if k not in ("group_by", "aggregates", "fields", "sort")}
    out["fields"] = list(NEXT_TIER_COLUMNS)
    # One page is NEXT_LINES rows, each with its own next-tier sentence; "more" pages on (`offset`, owner L85).
    raw = spec.get("limit")
    if raw is None or (isinstance(raw, int) and not isinstance(raw, bool) and raw >= 1):
        out["limit"] = min(raw or NEXT_LINES, NEXT_LINES)
    out["sort"] = [{"field": "to_next_tier", "dir": "desc" if kind == "furthest" else "asc"}]
    if subjects in ("agent", "dealer", "team"):
        filters = [
            f for f in out.get("filters") or [] if not (isinstance(f, dict) and f.get("field") == "owner_kind")
        ]
        out["filters"] = [*filters, {"field": "owner_kind", "op": "eq", "value": subjects}]
    return out


def _narrowing(db, base, agent_ids=None, kinds=None, names=None) -> list:
    """The targets a question can be answered from (TARGET-ACHIEVED-PERF part 2, UAC 5), as clauses on SalesTarget,
    applied before the period count and before any figure is computed. `kinds`: the target kinds a kind filter
    names. `agent_ids` (the agents an agent filter names, `computed.run_computed`): of the `base` targets, those
    they can be credited on, their agent targets, their teams' targets and every dealer target with ANY counted
    account of theirs (a dealer row's agent is known only from its accounts), plus every team or dealer target
    whose own name `names` matches (`_named_targets`: the same field may name a team or a dealer). The rows are
    still filtered after, so these can only leave out work, never a row."""
    from sqlalchemy import and_, or_, select

    from app.models.order import Customer
    from app.models.sales import SalesTargetAccount, SalesTeamMember

    clauses = []
    if kinds is not None:
        clauses.append(SalesTarget.subject_kind.in_(sorted(kinds)))
    if agent_ids is None:
        return clauses
    ids = sorted(agent_ids)
    teams = select(SalesTeamMember.sales_team_id).where(SalesTeamMember.sales_agent_id.in_(ids))
    dealers = (
        select(SalesTargetAccount.target_id)
        .join(Customer, Customer.id == SalesTargetAccount.customer_id)
        .where(Customer.sales_agent_id.in_(ids))
    )
    base = base.filter(*clauses)
    kept = {row.id for row in base.with_entities(SalesTarget.id).filter(or_(
        and_(SalesTarget.subject_kind == "agent", SalesTarget.sales_agent_id.in_(ids)),
        and_(SalesTarget.subject_kind == "team", SalesTarget.sales_team_id.in_(teams)),
        and_(SalesTarget.subject_kind == "dealer", SalesTarget.id.in_(dealers)),
    ))}
    if names is not None:
        others = [t for t in base.filter(SalesTarget.subject_kind != "agent") if t.id not in kept]
        kept |= _named_targets(db, others, names)
    clauses.append(SalesTarget.id.in_(sorted(kept)))
    return clauses


def _team_names(name: str) -> tuple[str, list[str]]:
    """A team target as its rows name it: ("Team X", its names). One function for the rows (`_summary_rows`) and
    for the narrowing (`_named_targets`), so a label change reaches both."""
    return f"Team {name}", [_norm(name)]


def _dealer_names(db, customers) -> tuple[str, str, list[str]]:
    """A dealer target as its rows name it: (the Dealers tab's label, the family name without a ledger marker, as
    the chat target lines print it (`period_progress`), its names: every counted account's code and name, then the
    family name). One function for the rows (`_target_rows`, `_summary_rows`) and for the narrowing."""
    from app.services.ledger_family import ledger_family_label
    from app.services.sales import target_service as ts

    tab = ts.dealer_label(db, customers)
    family = ledger_family_label(tab)
    names = [_norm(x) for c in customers for x in (c.customer_code, c.customer_name) if _norm(x)]
    names.append(_norm(family))
    return tab, family, names


def _named_targets(db, targets, names) -> set[str]:
    """The team and dealer targets whose own name `names(label, names)` matches, read as their rows print them
    (`_team_names`, `_dealer_names`): a team as "Team X" or X, a dealer as the Dealers tab's label or its family
    name, as `_summary_rows` and `_target_list_rows` do."""
    from app.models.sales import SalesTeam
    from app.services.sales import target_service as ts

    team_ids = {t.sales_team_id for t in targets if t.subject_kind == "team"}
    teams = {x.id: x.name for x in db.query(SalesTeam).filter(SalesTeam.id.in_(team_ids))} if team_ids else {}
    accounts = ts._accounts_by_target(db, [t.id for t in targets if t.subject_kind == "dealer"])
    kept = set()
    for target in targets:
        if target.subject_kind == "team":
            name = teams.get(target.sales_team_id) or ""
            label, said = _team_names(name)
            labels = [label, name]
        else:
            tab, family, said = _dealer_names(db, accounts.get(target.id, []))
            labels = [tab, family]
        if any(names(label, said) for label in labels):
            kept.add(target.id)
    return kept


def _target_rows(
    db, user_id: str, own_only: bool, date_from: date, date_to: date, *, limit: int, agent_ids=None, kinds=None,
    names=None,
) -> list[dict]:
    from sqlalchemy import select

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
    mine += _narrowing(db, db.query(SalesTarget).filter(SalesTarget.id.in_(overlapping), *mine), agent_ids, kinds, names)
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

        raise QueryRefused("timeout", f"More than {limit} target periods in that window; narrow it (a month).")
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
        tab_label = None
        if target.subject_kind == "agent":
            subject = agent_label(agent) if agent else ""
            team = team_of_agent.get(target.sales_agent_id)
        elif target.subject_kind == "team":
            team = teams.get(target.sales_team_id)
            subject = team.name if team else ""
        else:
            team = None
            # As the chat target lines (`period_progress`): no ledger marker on a single account's name.
            tab_label, subject, _names = _dealer_names(db, dealer_accounts.get(target.id, []))
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
                # The Dealers tab's own label (`list_all_targets`), ledger marker kept (crew live round 2).
                "_tab_label": tab_label,
                # Each counted account's own share of the payout (lane TARGET-PER-ACCOUNT-PAYOUT, owner 8 Nov:
                # every account is its own payee), in the Dealers tab's account order with its label ("A/C I").
                "_account_shares": [
                    (_share_label(c, dealer_accounts.get(target.id, [])), fig["by_account"].get(c.id, 0.0))
                    for c in dealer_accounts.get(target.id, [])
                ] if target.subject_kind == "dealer" and has_commission else [],
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
                "shortfall": _remaining(goal, fig["achieved_value"]),
                "ratio_missing": missing,
                "tier_reached": fig["tier_reached"],
                "commission": commission if has_commission else None,
                "bonus": bonus if has_commission else None,
                "payout": round((commission or 0) + (bonus or 0), 2) if has_commission else None,
                "_next": fig["next_tier"],
                "_has_tiers": has_commission,
            }
        )
    return rows


def _next_fields(nxt: dict | None) -> dict:
    """The next rung of one period (`target_service._next_tier`, the page's own ladder and engine) as fields."""
    nxt = nxt if nxt and nxt.get("state") == "next" else {}
    return {
        "next_tier": nxt.get("tier"),
        "next_tier_at": nxt.get("threshold"),
        "to_next_tier": nxt.get("gap"),
        "next_tier_payout": nxt.get("payout"),
        "next_tier_gain": nxt.get("gain"),
    }


def _share_label(customer, accounts) -> str:
    """The account as the Dealers tab prints it ("A/C I"); with its code when another counted account of the
    target prints the same, so two accounts' shares never merge into one."""
    from app.services.sales import target_service as ts

    label = ts.account_label(customer)
    if sum(1 for other in accounts if ts.account_label(other) == label) > 1:
        return f"{label} ({customer.customer_code})"
    return label


def _below(pct) -> bool:
    """The Targets screen's own reading: a target is reached only when its Achieved % is shown and at least 100
    (`sorento_crm_frontend/app/(protected)/sales/targets/components/SalesTargetsView.tsx:389`, `pct !== null &&
    pct >= 100` is the green "reached" figure); anything else, a target of 0 or a points target with no ratio (no %)
    included, is below target. The % is the page's own (`achievement_service.achieved_pct`, one decimal)."""
    return not (pct is not None and pct >= 100)


def _summary_rows(
    db, user_id: str, own_only: bool, date_from: date, date_to: date, *, limit: int, agent_ids=None, kinds=None,
    names=None,
) -> list[dict]:
    """`agent_target_summary`: one row per target SUBJECT over the window (AGENT-COMMISSION-ALL, owner 8 Nov): each
    agent, each team, each dealer, deterministic, from `_target_rows` (the target page's own per-period figures) with
    nothing recomputed but sums and counts.

    Owner answers on the behaviour card: an agent's row is its own agent targets only (Q1 a: a dealer target is paid
    to the dealer's account, so it is the dealer's row, never folded into the agent who owns its accounts); a team's
    row is its team target's own payout, named "Team X" and no person (Q2 a, Q3 a), and its members are the agent rows
    whose `team` is X (Q2 b); a dealer is one row per dealer target named as the Dealers tab names it, `agent` being the agent who owns every
    counted account.

    Matching (`computed.names_exact`): an agent by code, name, "CODE - Name" or the person behind several codes
    (`SalesAgent.person_label`); a team with or without "Team"; a dealer by its name or any counted account's code or
    name. A target of 0 over the window adds nothing to target, achieved and % (no % on the screen either); a period
    of 0 inside a target above 0 adds 0 to its target and its sales to achieved, as the Targets tab sums it (UAC 10)."""
    from app.services.sales import achievement_service as ach
    from app.services.sales import target_service as ts
    from app.services.sales.team_service import agent_label

    periods = _target_rows(
        db, user_id, own_only, date_from, date_to, limit=limit, agent_ids=agent_ids, kinds=kinds, names=names,
    )
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
            label, names = _team_names(row["team"] or row["subject"])
            return label, "team", {"agent": None, "team": None, "_names": {"owner": names}}
        customers = accounts.get(row["target_id"], [])
        owners = {c.sales_agent_id for c in customers}
        owner = (
            agent_label(agents[next(iter(owners))])
            if len(owners) == 1 and None not in owners and next(iter(owners)) in agents else None
        )
        _tab, _family, names = _dealer_names(db, customers)
        return row["_tab_label"] or row["subject"], "dealer", {
            "agent": owner, "team": None, "_names": {"owner": names, "agent": [person[owner]] if owner in person else []},
        }

    per: dict[tuple, dict] = {}
    for row in periods:
        name, kind, extra = subject(row)
        # One row per dealer TARGET, as the Dealers tab lists them (crew live round 2: two ledgers of one customer
        # were one row); agents and teams by name.
        key = (kind, row["target_id"] if kind == "dealer" else name)
        out = per.setdefault(key, {
            "id": f"{kind}:{key[1]}", "owner": name, "owner_kind": kind, "period": row["period_start"],
            "agent": extra["agent"], "team": extra["team"], "account_payouts": None,
            "periods": 0, "targets": set(), "target_value": 0.0,
            "achieved_value": 0.0, "commission": None, "bonus": None, "payout": None,
            "_names": {k: set() for k in ("owner", "agent")}, "_kinds": set(), "_complete": True, "_summed": False,
            "_zero": set(), "_shares": {}, "_has_commission": False, "_per_target": {},
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
        else:
            # Each target's own figures over its periods in the window, every period counted (a period of 0 adds
            # 0 to the target and its sales to achieved), as the Targets tab sums them (UAC 10).
            figures = out["_per_target"].setdefault(row["target_no"], [0.0, 0.0])
            figures[0] += row["target_value"]
            figures[1] += row["achieved_value"] or 0.0
        if row["commission"] is not None:
            out["_has_commission"] = True
        for k in ("commission", "bonus", "payout"):
            if row[k] is not None:
                out[k] = round((out[k] or 0.0) + row[k], 2)
        if row["_has_tiers"]:
            out.setdefault("_periods", {}).setdefault(row["target_no"], []).append(row)
        for label, share in row.get("_account_shares") or []:
            out["_shares"][label] = round(out["_shares"].get(label, 0.0) + share, 2)
    rows = []
    for out in per.values():
        # W-A: each commission target's live period, the row's numbers only when there is one (owner card Q2 a).
        live = [_live(p) for _no, p in sorted(out.pop("_periods", {}).items())]
        out["_live"] = [
            {"target_no": p["target_no"], "start": p["period_start"], "end": p["period_end"], "next": p["_next"]}
            for p in live
        ]
        out.update(_next_fields(live[0]["_next"] if len(live) == 1 else None))
        for target_no, (goal, achieved) in out.pop("_per_target").items():
            if goal <= 0:
                # A target of 0 over the window has no % on the screen; its sales would swamp the row's % (owner
                # C3, 8 Nov).
                out["_zero"].add(target_no)
                continue
            out["target_value"] += goal
            out["achieved_value"] += achieved
            out["_summed"] = True
        summed = out.pop("_summed")
        whole = out.pop("_complete")
        complete = whole and summed
        # Empty figures said in words in the result itself (crew live x3, 8 Nov): never "RM 0" for no commission,
        # and no target or achieved figure on a row that holds only targets of 0 (the note leaves them out).
        empty = {}
        if not out["_has_commission"]:
            empty.update(dict.fromkeys(("commission", "bonus", "payout"), NO_COMMISSION))
        if whole and not summed and out["_zero"]:
            empty.update(dict.fromkeys(("target_value", "achieved_value", "achieved_pct", "remaining_value"), ZERO_TARGET))
        out["_empty"] = empty
        out["kinds"] = ", ".join(sorted(out.pop("_kinds")))
        out["target_no"] = ", ".join(sorted(out["targets"]))
        out["targets"] = len(out["targets"])
        goal, achieved = round(out["target_value"], 2), round(out["achieved_value"], 2)
        out["target_value"] = goal if complete else None
        out["achieved_value"] = achieved if complete else None
        out["achieved_pct"] = (
            ach.achieved_pct(Decimal(str(achieved)), Decimal(str(goal))) if complete and goal else None
        )
        out["remaining_value"] = _remaining(out["target_value"], out["achieved_value"])
        shares = out.pop("_shares")
        out["account_payouts"] = "; ".join(f"{label} {share:,.2f}" for label, share in shares.items()) or None
        out["_names"] = {k: sorted(v) for k, v in out["_names"].items()}
        out["_zero"] = sorted(out["_zero"])
        rows.append(out)
    # Agents by name, then teams, then dealers (the result ranks them by payout, `EntityDef.rank_by`).
    rows.sort(key=lambda r: ({"agent": 0, "team": 1}.get(r["owner_kind"], 2), r["owner"]))
    return rows


#: What an empty payout reads as: no commission tiers on any of the row's targets.
NO_COMMISSION = "no commission set"
#: What target, achieved and % read as on a row of only targets of 0 (never "RM 0", crew live round 2).
ZERO_TARGET = "no target set"


def _norm(value) -> str:
    return " ".join(str(value or "").split()).lower()


def _some(names: list[str], most: int = 5) -> str:
    shown = ", ".join(names[:most])
    return f"{shown} and {len(names) - most} more" if len(names) > most else shown


def _live(periods: list[dict]) -> dict:
    """The one period of a target the next-tier answer reads: today's, else the last one started by today, else the
    window's first (a window wholly in the future)."""
    from app.services.sales.team_service import _today

    current = [p for p in periods if p["is_current"]]
    if current:
        return current[0]
    started = [p for p in periods if p["period_start"] <= _today()]
    return started[-1] if started else periods[0]


#: The rows of one next-tier page, each with its next-tier lines ("more" pages on).
NEXT_LINES = 10


def _rm(value, unit: str = "RM") -> str:
    return f"RM {value:,.2f}" if unit == "RM" else f"{value:,.2f} units"


#: What the line says when there is no next tier to reach (`target_service._next_tier` `state`).
NO_NEXT = {
    "top": "has reached its top tier: no next tier.",
    "no_ratio": "has no RM per point on file for the period, so its tiers cannot be placed: no next tier known.",
    "no_tiers": "has no tiers in this period: no next tier.",
}


def _next_line(owner: str, live: dict) -> str:
    from app.services.sales.team_service import _today

    nxt, no = live["next"], live["target_no"]
    when = fmt_date_range(live["start"], live["end"]) + (" (closed)" if live["end"] < _today() else "")
    if nxt is None or nxt["state"] != "next":
        return f"{no} ({owner}, {when}) " + NO_NEXT[nxt["state"] if nxt else "no_tiers"]
    unit = nxt["unit"]
    line = (
        f"{no} ({owner}, {when}): tier {nxt['tier']} at {_rm(nxt['threshold'], unit)}, {_rm(nxt['gap'], unit)} to "
        f"go, would pay {_rm(nxt['payout'])} ({_rm(nxt['gain'])} more than now)"
    )
    if nxt.get("mix") == "so_far":
        line += ", if the rest comes in the same account mix as sold so far"
    elif nxt.get("mix") == "even":
        line += ", with nothing sold yet: if the rest is split evenly across the accounts"
    if nxt.get("rates"):
        rate = (lambda v: f"RM {v:g} per unit") if unit == "units" else (lambda v: f"{v:g}%")
        line += " (rates on that tier: " + ", ".join(f"{r['label']} {rate(r['rate'])}" for r in nxt["rates"]) + ")"
    return line + "."


def _summary_note(rows: list[dict], used: set[str] = frozenset()) -> str | None:
    """What the answer must say about the rows it shows (owner C3, Q5): which targets of 0 were left out of target
    and achieved, and whose payout is empty because no commission is set (never "RM 0")."""
    parts = []
    zero = [no for r in rows for no in r["_zero"]]
    if zero:
        parts.append(f"No target set on {_some(zero)}: left out of target and achieved.")
    unset = [r["owner"] for r in rows if not r["_has_commission"]]
    if unset:
        parts.append(f"No commission is set on the targets of {_some(unset)}.")
    # Next tier (W-A): one line per commission target's live period, so a subject with several targets is answered
    # target by target (owner card Q2 a: a sum of two distances is not a distance).
    # Only when the question is about the next tier (one of its fields asked, filtered or sorted on).
    asked = used & NEXT_TIER_FIELDS.keys()
    lines = [_next_line(r["owner"], live) for r in rows for live in r.get("_live", [])] if asked else []
    if asked and rows and not lines:
        # Rows, none with a commission target: one line says so (crew live x3 W6, `query_tools._distance_reply`
        # answers with it alone), never a ranking of something else. No rows: the other notes speak (review B1).
        who = "agent target" if all(r["owner_kind"] == "agent" for r in rows) else "target"
        parts.insert(0, f"No {who} has a commission ladder this period.")
    if lines:
        # Every row shown has its lines: a next-tier page is at most NEXT_LINES rows (`_next_tier_spec`), and the
        # rest come with "more" (owner L85), never an "ask for one" line.
        parts.append("Next tier: " + " ".join(lines))
    return " ".join(parts) or None


def _remaining(goal, achieved):
    """What is left to reach the target (UAC 6), 0 once reached: `achieved_pct` says by how much it is over."""
    if goal is None or achieved is None:
        return None
    return round(max(goal - achieved, 0.0), 2)


def _target_list_rows(
    db, user_id: str, own_only: bool, date_from: date, date_to: date, *, limit: int, agent_ids=None, kinds=None,
    names=None,
) -> list[dict]:
    """`target_list`: the Targets screens' own rows (`target_service.list_all_targets`, Teams, Agents and Dealers
    tabs: one row per target, its whole range's target, achieved and %), for targets whose range overlaps the
    window. Reached is the screen's green figure (`_below`). An own-only holder gets the Agents tab cut to their own
    agents, as the screen cuts it (`api/v1/sales/targets.py` `_own_rows`)."""
    from app.services import own_scope
    from app.services.sales import target_service as ts

    mine = set(own_scope.me(db, user_id).agent_ids) if own_only else None
    # Only the targets the question can be answered from reach the achievement statement (UAC 5).
    target_ids = None
    if agent_ids is not None:
        clauses = _narrowing(db, db.query(SalesTarget), agent_ids, names=names)
        target_ids = {row.id for row in db.query(SalesTarget.id).filter(*clauses)}
        if not target_ids:
            return []
    rows = []
    for subject in ("agent", "team", "dealer"):
        if (mine is not None and subject != "agent") or (kinds is not None and subject not in kinds):
            continue
        for r in ts.list_all_targets(db, subject=subject, target_ids=target_ids)["rows"]:
            if mine is not None and r.get("sales_agent_id") not in mine:
                continue
            if r["start_date"] > date_to or r["end_date"] < date_from:
                continue
            # A target of 0 has no target, achieved or % to show, said in words as on the payout summary (crew
            # live x3 on 0c5c7b78, X3: "achieved 9.92M" printed for a target of 0).
            zero = r["target_value"] is not None and r["target_value"] <= 0
            rows.append({
                "id": r["target_id"], "target_id": r["target_id"], "target_no": r["target_no"],
                "subject": r["subject_label"], "subject_kind": subject, "period": r["start_date"],
                "start_date": r["start_date"], "end_date": r["end_date"],
                "target_value": None if zero else r["target_value"],
                "achieved_value": None if zero else r["achieved_value"],
                "achieved_pct": None if zero else r["achieved_pct"],
                "remaining_value": None if zero else _remaining(r["target_value"], r["achieved_value"]),
                "reached": not _below(r["achieved_pct"]),
                "_empty": dict.fromkeys(("target_value", "achieved_value", "achieved_pct", "remaining_value"), ZERO_TARGET) if zero else {},
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
        kind_field="subject_kind",
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
            "target_no": FieldDef(
                "Target", kind="text", note="The TGT number(s); a dealer row is one target, as on the Dealers tab.",
            ),
            "account_payouts": FieldDef(
                "Payout per account", kind="text",
                note="Dealer rows: each counted account is its own payee; its label as the Dealers tab shows it "
                     "(A/C I) and its own share of the payout, so same-name dealers differ.",
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
            "remaining_value": FieldDef(
                "Left to target (RM)", kind="number", note="Target minus achieved, 0 once reached (achieved % shows any excess).",
            ),
            "commission": FieldDef("Commission", kind="number"),
            "bonus": FieldDef("Bonus", kind="number"),
            "payout": FieldDef(
                "Commission payout", kind="number",
                note="Commission plus bonus over the window; empty (not 0) when no commission is set.",
            ),
            **NEXT_TIER_FIELDS,
        },
        name_by=("owner",),
        hint="COMMISSION PAYOUT / TARGET vs ACHIEVED / NEXT TIER (how far to it, what it would pay) for an agent, a "
             "team or a dealer, or per agent / team / dealer: one row per agent, team and dealer, highest payout "
             "first, totals row; no period = this year. One of them: agent=<code or name as said> (an agent, team or "
             "dealer); only dealers or teams: owner_kind eq dealer|team. Next tier (how far, closest, what it would "
             "pay or earn there): set next_tier, and subjects for closest / furthest",
        list_fields=("owner_kind", "target_value", "achieved_value", "achieved_pct", "remaining_value", "payout"),
        # Sales vs target in one query (UAC 11): RM figures of the amount rows only, a units row has none.
        row_totals=("targets", "target_value", "achieved_value", "remaining_value", "commission", "bonus", "payout"),
        compute=_summary_rows,
        kind_field="owner_kind",
        window_field="period",
        brand_blind=True,
        own_note="You see only your own agents' targets: team and dealer payouts are not visible to you.",
        spec_hook=_next_tier_spec,
        row_note=_summary_note,
        rank_by="payout",
        default_window="this_year",
        # Every agent, team and dealer of a normal window in one result (the table is rendered by code).
        default_limit=50,
        row_identity=("owner", "target_no", "account_payouts"),
        card_min_rows=2,
        always_fields=("target_no", "account_payouts"),
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
            "remaining_value": FieldDef(
                "Remaining", kind="number", note="Target minus achieved, 0 once reached (achieved % shows any excess).",
            ),
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
        kind_field="subject_kind",
        window_field="period",
        brand_blind=True,
    ),
)
