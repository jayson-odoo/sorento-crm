"""TARGET-ACHIEVED-PERF part 2 (#2419 slice 1): a target question is fast and right
(`documentation/plans/sales/PLAN-target-achieved-perf-14nov.md` "Part 2", UAC lines 5 to 8 of
`target-achieved-perf-14nov-acceptance-criteria.md`). No LLM: registry calls and the loop with a scripted model.

UAC 5: a question naming an agent computes only the targets that agent can be credited on (their agent targets,
their teams' targets, every dealer target with ANY counted account of theirs), and the rows are identical to
computing everything and filtering after. `owner_kind` (target_list: `subject_kind`) narrows the same way. Held two
ways: a spy on `target_service.period_figures` and on `target_service._achieved_by_account` (the achievement
statement both entities reach) records which targets were computed, and the same question with every narrowing
argument dropped on the way into `compute` is the "everything, then filtered" baseline.

UAC 6: `remaining_value` = target minus achieved, floored at 0, on both target entities, listed by crm_describe.
UAC 7: the per-question cap is 6 crm_query calls that ran (ok, empty or timed out); crm_describe and refused calls
are free; the 7th is refused as a tool reply and the answer still comes, never with a "limit" message.
UAC 8: the fallback `chatbot_agent` prompt no longer contradicts the tools.

Fixture: `test_agent_commission_all.team` (agents A and B with Jul to Dec monthly agent targets of 10,000, team
"ZZT North" of A and B with an October team target, dealer "ZZT DEALER W2" whose account has no agent), plus
agent D in team "ZZT South" with its own team target, agent E with nothing, dealer "ZZT SPLIT X" whose two accounts
belong to A and B, and dealer "ZZT SOLO A" whose one account belongs to A.
"""
from __future__ import annotations

import json
import uuid
from datetime import date
from decimal import Decimal

import pytest

from tests.chatbot.agent.test_agent_commission_all import team  # noqa: F401  (fixture)
from tests.chatbot.agent.test_ai_tools_wave2 import grant, run, targets  # noqa: F401  (fixtures)
from tests.test_dealer_targets_api import _customer, _dealer_body, _product_id, _sale
from tests.test_sales_targets_s1 import BASE, TEAMS_BASE, _agent, _so_line, api, world  # noqa: F401  (fixtures)

SUMMARY = "agent_target_summary"
TARGET_LIST = "target_list"
YEAR = ["01/01/2026", "31/12/2026"]
SUMMARY_FIELDS = ["owner_kind", "agent", "target_value", "achieved_value", "achieved_pct", "payout"]
LIST_FIELDS = ["subject_kind", "target_value", "achieved_value", "achieved_pct", "reached"]


# ------------------------------------------------------------------ fixture and probes


def _team_target(client, team_id, agent, name):
    res = client.post(BASE, json={
        "subject_kind": "team", "sales_team_id": team_id, "name": name, "metric": "amount",
        "basis": "ordered", "product_scope": "all", "start_date": "2026-10-01", "end_date": "2026-10-31",
        "agent_figures": [{"sales_agent_id": agent.id, "target_value": 10000}],
        "commission_method": "retroactive", "tiers": [{"from_pct": 80, "rate": 1}],
    })
    assert res.status_code == 201, res.text
    return res.json()


@pytest.fixture
def credit(team, api):
    """Every way an agent can be credited on a target, and targets it cannot."""
    db, client, t = team
    _c, _db, company_id = api
    pid = _product_id(db, company_id)
    d, e = _agent(db, "D", "Agent D"), _agent(db, "E", "Agent E")
    south = client.post(TEAMS_BASE, json={"name": "ZZT South", "sales_agent_ids": [d.id]})
    assert south.status_code in (200, 201), south.text
    south_target = _team_target(client, south.json()["id"], d, "ZZT South Oct")

    x = _customer(db, company_id, "ZZT SPLIT X", level=1)
    y = _customer(db, company_id, "ZZT SPLIT Y", level=1)
    z = _customer(db, company_id, "ZZT SOLO A", level=1)
    x.sales_agent_id, y.sales_agent_id, z.sales_agent_id = t["a"].id, t["b"].id, t["a"].id
    db.flush()
    for customer, sold in ((x, "30000"), (y, "20000"), (z, "15000")):
        _sale(db, company_id, customer, sold, date(2026, 8, 4), product_id=pid)
    split = client.post(BASE, json=_dealer_body([x, y], name="ZZT split dealer"))
    assert split.status_code == 201, split.text
    solo = client.post(BASE, json=_dealer_body([z], name="ZZT solo dealer"))
    assert solo.status_code == 201, solo.text

    ids = {
        "ta": t["ta"]["id"], "tb": t["tb"]["id"], "north": t["team"]["id"], "south": south_target["id"],
        "w2": t["dealer"]["id"], "split": split.json()["id"], "solo": solo.json()["id"],
    }
    from app.models.sales import SalesTarget

    # A team target with agent figures carries one agent target per member: those are the member's own.
    kinds = {kind: {row.id for row in db.query(SalesTarget).filter(SalesTarget.subject_kind == kind)}
             for kind in ("agent", "team", "dealer")}

    def own(agent):
        return {row.id for row in db.query(SalesTarget).filter(
            SalesTarget.subject_kind == "agent", SalesTarget.sales_agent_id == agent.id)}

    # What each agent can be credited on (UAC 5): own agent targets, own teams' targets, any dealer account.
    allowed = {
        "a": own(t["a"]) | {ids["north"], ids["split"], ids["solo"]},
        "b": own(t["b"]) | {ids["north"], ids["split"]},
        "d": own(d) | {ids["south"]},
        "e": set(),
    }
    assert ids["ta"] in allowed["a"] and ids["tb"] not in allowed["a"] and not own(e)
    return db, {**t, "d": d, "e": e, "ids": ids, "allowed": allowed, "kinds": kinds}


@pytest.fixture
def computed(monkeypatch):
    """The target ids each run hands to `period_figures` and to the achievement statement (`_achieved_by_account`,
    reached by `period_figures` and by `list_all_targets`). `computed.reset()` before the run you measure."""
    from app.services.sales import target_service as ts

    class Seen:
        def __init__(self):
            self.reset()

        def reset(self):
            self.figures: set[str] = set()
            self.achieved: set[str] = set()
            self.figure_calls = 0

    seen = Seen()
    real_figures, real_achieved = ts.period_figures, ts._achieved_by_account

    def figures(db, targets, *args, **kw):
        seen.figure_calls += 1
        seen.figures.update(t.id for t in targets)
        return real_figures(db, targets, *args, **kw)

    def achieved(db, company_id, pairs, *args, **kw):
        pairs = list(pairs)
        seen.achieved.update(t.id for t, _p in pairs)
        return real_achieved(db, company_id, pairs, *args, **kw)

    monkeypatch.setattr(ts, "period_figures", figures)
    monkeypatch.setattr(ts, "_achieved_by_account", achieved)
    return seen


def _everything_then_filtered(db, key, spec):
    """The same question with every narrowing argument dropped on the way into `compute`: the entity computes
    every target in the window and `run_computed` filters the rows after, as before the change."""
    from app.services.assistant_registry import ENTITIES

    entity = ENTITIES[key]
    real = entity.compute

    def everything(db, user_id, own_only, date_from, date_to, *_narrowing, limit, **_more):
        return real(db, user_id, own_only, date_from, date_to, limit=limit)

    ENTITIES[key] = type(entity)(**{**entity.__dict__, "compute": everything})
    try:
        return run(db, spec)
    finally:
        ENTITIES[key] = entity


def _same_answer(narrowed, baseline):
    assert narrowed["rows"] == baseline["rows"]
    assert narrowed.get("totals") == baseline.get("totals")


# ------------------------------------------------------------------ UAC 5: agent_target_summary


@pytest.mark.parametrize("form", ["agent_shorthand", "agent_field_eq", "agent_code"])
def test_N1_summary_for_agent_a_computes_only_what_a_can_be_credited_on(credit, computed, form):
    db, t = credit
    a = t["a"]
    spec = {"entity": SUMMARY, "period": YEAR, "fields": SUMMARY_FIELDS, "limit": 50}
    if form == "agent_shorthand":
        spec["agent"] = "Agent A"
    elif form == "agent_code":
        spec["agent"] = a.sales_agent
    else:
        spec["filters"] = [{"field": "agent", "op": "eq", "value": "Agent A"}]
    computed.reset()
    out = run(db, spec)
    narrowed = set(computed.figures)
    baseline = _everything_then_filtered(db, SUMMARY, spec)
    _same_answer(out, baseline)
    assert out["rows"], "agent A has targets: the answer is not empty"
    ids = t["ids"]
    # A dealer target with ANY account of A is computed, the two-agent dealer included; A's own target too.
    assert {ids["ta"], ids["split"], ids["solo"]} <= narrowed
    assert narrowed <= t["allowed"]["a"], f"computed targets A cannot be credited on: {narrowed - t['allowed']['a']}"
    assert computed.achieved <= t["allowed"]["a"]


def test_N2_the_two_agent_dealer_is_computed_for_each_of_its_agents(credit, computed):
    db, t = credit
    ids = t["ids"]
    for key, name in (("a", "Agent A"), ("b", "Agent B")):
        spec = {"entity": SUMMARY, "period": YEAR, "fields": SUMMARY_FIELDS, "limit": 50,
                "filters": [{"field": "agent", "op": "eq", "value": name},
                            {"field": "owner_kind", "op": "eq", "value": "dealer"}]}
        computed.reset()
        out = run(db, spec)
        narrowed = set(computed.figures)
        _same_answer(out, _everything_then_filtered(db, SUMMARY, spec))
        assert ids["split"] in narrowed, name
        assert narrowed <= t["allowed"][key], f"{name}: {narrowed - t['allowed'][key]}"
        assert ids["w2"] not in narrowed and ids["south"] not in narrowed


def test_N3_dealers_of_agent_a_are_the_same_rows_as_before(credit, computed):
    """agent eq A lists A's own row and the dealer whose every account is A's; the split dealer has no single
    agent, so it is computed but not listed, exactly as the unfiltered computation filtered."""
    db, t = credit
    spec = {"entity": SUMMARY, "period": YEAR, "fields": SUMMARY_FIELDS, "limit": 50,
            "filters": [{"field": "agent", "op": "eq", "value": "Agent A"}]}
    computed.reset()
    out = run(db, spec)
    labels = sorted(r["label"] for r in out["rows"])
    assert labels == sorted([f"{t['a'].sales_agent} - Agent A", "ZZT SOLO A"])
    assert set(computed.figures) <= t["allowed"]["a"]


def test_N4_an_agent_with_no_targets_computes_nothing_and_answers_empty(credit, computed):
    db, t = credit
    spec = {"entity": SUMMARY, "period": YEAR, "fields": SUMMARY_FIELDS,
            "filters": [{"field": "agent", "op": "eq", "value": "Agent E"}]}
    computed.reset()
    out = run(db, spec)
    assert out["rows"] == []
    assert computed.figures == set() and computed.achieved == set()


def test_N5_agent_d_in_another_team_computes_only_that_teams_target(credit, computed):
    db, t = credit
    spec = {"entity": SUMMARY, "period": YEAR, "fields": SUMMARY_FIELDS,
            "filters": [{"field": "agent", "op": "eq", "value": "Agent D"}]}
    computed.reset()
    out = run(db, spec)
    _same_answer(out, _everything_then_filtered(db, SUMMARY, spec))
    assert set(computed.figures) <= t["allowed"]["d"]


@pytest.mark.parametrize("kind", ["dealer", "team", "agent"])
def test_N6_owner_kind_computes_only_targets_of_that_kind(credit, computed, kind):
    db, t = credit
    of_kind = t["kinds"][kind]
    spec = {"entity": SUMMARY, "period": YEAR, "fields": SUMMARY_FIELDS, "limit": 50,
            "filters": [{"field": "owner_kind", "op": "eq", "value": kind}]}
    computed.reset()
    out = run(db, spec)
    narrowed = set(computed.figures)
    _same_answer(out, _everything_then_filtered(db, SUMMARY, spec))
    assert {r["owner_kind"] for r in out["rows"]} == {kind}
    assert narrowed == of_kind, f"other kinds computed: {narrowed - of_kind}"


@pytest.mark.parametrize("said", ["ZZT DEALER W2", "ZZT North", "Team ZZT South", "ZZT SPLIT X"])
def test_N7_a_team_or_dealer_name_keeps_its_answer(credit, said):
    """Not an agent: whatever the narrowing does, the answer is the one computing everything gives."""
    db, _t = credit
    spec = {"entity": SUMMARY, "period": YEAR, "agent": said, "fields": SUMMARY_FIELDS}
    out = run(db, spec)
    assert out["rows"]
    _same_answer(out, _everything_then_filtered(db, SUMMARY, spec))


# ------------------------------------------------------------------ UAC 5: target_list


def test_N8_target_list_for_agent_a_computes_only_what_a_can_be_credited_on(credit, computed):
    db, t = credit
    spec = {"entity": TARGET_LIST, "period": YEAR, "agent": "Agent A", "fields": LIST_FIELDS, "limit": 50}
    computed.reset()
    out = run(db, spec)
    achieved = set(computed.achieved)
    _same_answer(out, _everything_then_filtered(db, TARGET_LIST, spec))
    assert t["ta"]["target_no"] in [r["label"].split(":")[0] for r in out["rows"]]
    assert t["ids"]["ta"] in achieved
    assert achieved <= t["allowed"]["a"], f"computed targets A cannot be credited on: {achieved - t['allowed']['a']}"


def test_N9_target_list_for_an_agent_with_no_targets_computes_nothing(credit, computed):
    db, _t = credit
    spec = {"entity": TARGET_LIST, "period": YEAR, "agent": "Agent E", "fields": LIST_FIELDS}
    computed.reset()
    out = run(db, spec)
    assert out["rows"] == []
    assert computed.achieved == set()


@pytest.mark.parametrize("kind", ["dealer", "team", "agent"])
def test_N10_target_list_subject_kind_computes_only_that_kind(credit, computed, kind):
    db, t = credit
    of_kind = t["kinds"][kind]
    spec = {"entity": TARGET_LIST, "period": YEAR, "fields": LIST_FIELDS, "limit": 50,
            "filters": [{"field": "subject_kind", "op": "eq", "value": kind}]}
    computed.reset()
    out = run(db, spec)
    achieved = set(computed.achieved)
    _same_answer(out, _everything_then_filtered(db, TARGET_LIST, spec))
    assert out["rows"]
    assert achieved <= of_kind, f"other kinds computed: {achieved - of_kind}"


# ------------------------------------------------------------------ UAC 6: remaining_value


def _month_target(client, agent, value, month="2026-09"):
    res = client.post(BASE, json={
        "subject_kind": "agent", "sales_agent_id": agent.id, "name": f"ZZT {agent.sales_agent} month",
        "metric": "amount", "basis": "ordered", "product_scope": "all",
        "start_date": f"{month}-01", "end_date": f"{month}-30", "split_every": 1, "split_unit": "month",
        "target_value": value, "commission_method": "retroactive", "tiers": [{"from_pct": 80, "rate": 2}],
    })
    assert res.status_code == 201, res.text
    return res.json()


@pytest.fixture
def remaining(targets, api):
    """Agent A over its September target (12,000 of 10,000), B short (5,000 of 10,000), F exactly on a one-month
    target (10,000 of 10,000), G over a one-month target (12,000 of 10,000)."""
    db, client, t = targets
    _c, _db, company_id = api
    pid = _product_id(db, company_id)
    f, g = _agent(db, "F", "Agent F"), _agent(db, "G", "Agent G")
    for agent, sold in ((f, "10000"), (g, "12000")):
        _month_target(client, agent, 10000)
        _so_line(db, company_id, agent_id=agent.id, order_date=date(2026, 9, 12), line_total=Decimal(sold),
                 product_id=pid)
    return db, {**t, "f": f, "g": g}


@pytest.mark.parametrize("key", [SUMMARY, TARGET_LIST])
def test_G1_remaining_value_is_a_field_and_crm_describe_lists_it(remaining, key):
    from app.services.assistant_registry import ENTITIES
    from app.services.assistant_registry.query import describe

    db, _t = remaining
    assert "remaining_value" in ENTITIES[key].fields, f"{key} has no remaining_value"
    assert ENTITIES[key].fields["remaining_value"].kind == "number"
    listed = [row["field"] for row in describe(db, str(uuid.uuid4()), key)["fields"]]
    assert "remaining_value" in listed


def _label(t, key):
    return f"{t[key].sales_agent} - Agent {key.upper()}"


def test_G2_summary_remaining_value_is_target_minus_achieved_floored_at_0(remaining):
    from app.services.assistant_registry import ENTITIES

    db, t = remaining
    assert "remaining_value" in ENTITIES[SUMMARY].fields, "agent_target_summary has no remaining_value"
    out = run(db, {"entity": SUMMARY, "period": "2026-09", "limit": 50,
                   "filters": [{"field": "owner_kind", "op": "eq", "value": "agent"}],
                   "fields": ["target_value", "achieved_value", "achieved_pct", "remaining_value"]})
    by = {r["label"]: r for r in out["rows"]}
    assert by[_label(t, "b")]["remaining_value"] == 5000.0  # short: 10,000 less 5,000
    assert by[_label(t, "f")]["remaining_value"] == 0.0  # reached exactly
    assert by[_label(t, "a")]["remaining_value"] == 0.0  # over: 0, achieved % says by how much
    assert by[_label(t, "a")]["achieved_pct"] == 120.0
    for row in out["rows"]:
        if row["target_value"] is not None and row["achieved_value"] is not None:
            assert row["remaining_value"] == round(max(row["target_value"] - row["achieved_value"], 0.0), 2), row


def test_G3_target_list_remaining_value_is_target_minus_achieved_floored_at_0(remaining):
    from app.services.assistant_registry import ENTITIES

    db, t = remaining
    assert "remaining_value" in ENTITIES[TARGET_LIST].fields, "target_list has no remaining_value"
    out = run(db, {"entity": TARGET_LIST, "period": "2026-09", "limit": 50,
                   "filters": [{"field": "subject_kind", "op": "eq", "value": "agent"}],
                   "fields": ["target_value", "achieved_value", "achieved_pct", "remaining_value"]})
    rows = out["rows"]
    assert rows
    # Whole-range figures: A's July to December target is 60,000 with 21,000 achieved.
    a = next(r for r in rows if _label(t, "a") in r["label"])
    assert a["remaining_value"] == 39000.0
    f = next(r for r in rows if _label(t, "f") in r["label"])
    g = next(r for r in rows if _label(t, "g") in r["label"])
    assert f["remaining_value"] == 0.0 and g["remaining_value"] == 0.0
    for row in rows:
        if row["target_value"] is not None and row["achieved_value"] is not None:
            assert row["remaining_value"] == round(max(row["target_value"] - row["achieved_value"], 0.0), 2), row


# ------------------------------------------------------------------ UAC 7: the per-question query cap


PRODUCTS_VIEW = "master_data.products.view"


def _round(*calls):
    from app.services.llm_provider import ChatResult

    return ChatResult(content="", prompt_tokens=10, completion_tokens=5, total_tokens=15, tool_calls=[
        {"id": cid, "name": name, "arguments": args} for cid, name, args in calls
    ])


def _product_query(t):
    return {"entity": "product", "fields": ["list_price"],
            "filters": [{"field": "product_code", "op": "starts_with", "value": t}], "limit": 3}


def _scripted_turn(script, *slugs):
    """Run one panel turn with `script` (one ChatResult per model call); the tool replies the model saw last, by
    call id, and the reply."""
    import app.main  # noqa: F401
    from app.models.company import UserCompany
    from app.services.chatbot.agent.loop import run_agent_turn
    from app.services.company_scope import DEFAULT_COMPANY_ID, register_company_scope_listeners
    from tests._pg_fixture import blank_session
    from tests.chatbot.agent._ported_reads_support import panel_turn
    from tests.chatbot.agent._seed import seed_agent_contact

    register_company_scope_listeners()
    seen: list[list[dict]] = []

    class Recording:
        def __init__(self, steps):
            self.steps = list(steps)

        def chat(self, messages, **kw):
            seen.append([m for m in messages if m.get("role") == "tool"])
            return self.steps.pop(0)

    with blank_session() as db:
        contact = seed_agent_contact(db, slugs=slugs)
        db.add(UserCompany(user_id=contact["user_id"], company_id=DEFAULT_COMPANY_ID))
        db.flush()
        with panel_turn(contact["user_id"]):
            result = run_agent_turn(db, contact_respond_id=contact["respond_id"], text="how are my targets?",
                                    provider=Recording(script), mcp_call=lambda n, a: {}, catalog={})
    replies = {m["tool_call_id"]: json.loads(m["content"]) for m in seen[-1]}
    return replies, result.reply_text or ""


def _answer():
    return _round(("ans-1", "answer", {"text": "Done.", "figures": [], "not_found": [], "not_checked": []}))


def test_Q1_the_cap_is_six_queries_that_ran():
    from app.services.chatbot.agent import loop

    assert loop.MAX_QUERY_CALLS == 6


def test_Q2_describe_is_free_and_the_seventh_query_is_a_tool_reply_not_the_end():
    t = "ZZT" + uuid.uuid4().hex[:6].upper()
    q = _product_query(t)
    script = [
        _round(("d1", "crm_describe", {}), ("d2", "crm_describe", {}), ("q1", "crm_query", q), ("q2", "crm_query", q)),
        _round(("q3", "crm_query", q), ("q4", "crm_query", q), ("q5", "crm_query", q), ("q6", "crm_query", q)),
        _round(("d3", "crm_describe", {}), ("q7", "crm_query", q)),
        _answer(),
    ]
    replies, reply = _scripted_turn(script, PRODUCTS_VIEW)
    for cid in ("d1", "d2", "d3"):
        assert replies[cid]["status"] != "denied", (cid, replies[cid])
    for cid in ("q1", "q2", "q3", "q4", "q5", "q6"):
        assert replies[cid]["status"] in ("ok", "empty"), (cid, replies[cid])
    assert replies["q7"]["status"] == "denied", replies["q7"]
    assert "Done" in reply
    assert "limit" not in reply.lower()


def test_Q3_refused_queries_are_free():
    t = "ZZT" + uuid.uuid4().hex[:6].upper()
    q = _product_query(t)
    bad = {"entity": "zzt_no_such_entity"}
    script = [
        _round(("r1", "crm_query", bad), ("r2", "crm_query", bad), ("r3", "crm_query", bad), ("q1", "crm_query", q)),
        _round(("q2", "crm_query", q), ("q3", "crm_query", q), ("q4", "crm_query", q), ("q5", "crm_query", q)),
        _round(("q6", "crm_query", q), ("q7", "crm_query", q)),
        _answer(),
    ]
    replies, reply = _scripted_turn(script, PRODUCTS_VIEW)
    for cid in ("r1", "r2", "r3"):
        assert replies[cid]["status"] == "invalid", (cid, replies[cid])
    for cid in ("q1", "q2", "q3", "q4", "q5", "q6"):
        assert replies[cid]["status"] in ("ok", "empty"), (cid, replies[cid])
    assert replies["q7"]["status"] == "denied", replies["q7"]
    assert "limit" not in reply.lower()


def test_Q4_a_timed_out_query_counts(monkeypatch):
    from app.services.assistant_registry.query import QueryRefused
    from app.services.chatbot.agent import query_tools

    def slow(db, user_id, spec):
        raise QueryRefused("timeout", "That took too long.")

    monkeypatch.setattr(query_tools, "run_query", slow)
    q = _product_query("ZZT")
    script = [
        _round(*((f"q{i}", "crm_query", q) for i in range(1, 5))),
        _round(*((f"q{i}", "crm_query", q) for i in range(5, 8))),
        _answer(),
    ]
    replies, reply = _scripted_turn(script, PRODUCTS_VIEW)
    for i in range(1, 7):
        assert replies[f"q{i}"]["status"] == "timeout", (i, replies[f"q{i}"])
    assert replies["q7"]["status"] == "denied", replies["q7"]
    assert "limit" not in reply.lower()


# ------------------------------------------------------------------ UAC 8: the prompt agrees with the tools


def test_P1_the_fallback_prompt_no_longer_contradicts_the_tools():
    from app.services.ai_prompt_registry import _chatbot_agent_fallback

    text = " ".join(_chatbot_agent_fallback().split())
    # crm_query takes an agent by name (`query_tools` description): no crm_resolve first.
    assert "with crm_resolve before any other tool" not in text
    # The loop refuses a second sales basis in a turn: the prompt never asks for three.
    assert "show invoiced, delivered and ordered" not in text
