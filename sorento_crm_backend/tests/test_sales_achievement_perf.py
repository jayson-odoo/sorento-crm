"""#1319: saving a sales target for all products hung for minutes on the S1 achievement query.

The owner saved an all-products team target on the hand-test stack and three copies of the
achievement statement ran for 1 min 45 s to 2 min 36 s each. The statement compared
`CAST(sales_order_lines.company_id AS TEXT)` (a parallel seq scan of every line), read every
line the agents ever sold before any period filter, then compared each line with every period
and each surviving row with every (period, agent) credit row: quadratic in history x periods x
agents.

These tests pin the repaired shape on a generated volume (`tests/_sales_volume.py`), analyzed
as production's tables are (the statistics-less case stays pinned at a smaller volume by
`test_detail_query_stays_fast_at_scale` in the S1 suite):

- R1 the line company is compared UUID to UUID, never through a text cast;
- R2 no line dated outside every period reaches a join, and the category walk runs once;
- R3 a save runs the achievement once;
- R4 a save and a read return inside a wall-clock budget.

The figures themselves stay pinned by the S1 suites (`test_sales_targets_s1*.py`).
"""
from __future__ import annotations

import json
import time
from datetime import date, timedelta
from decimal import Decimal
from typing import Iterator, List

import pytest
from sqlalchemy import text

from ._sales_volume import seed_volume
from .test_sales_targets_s1 import (  # noqa: F401  (fixtures)
    BASE,
    TEAMS_BASE,
    _category,
    _product,
    _so_line,
    api,
    world,
)

#: The generated volume: 20,000 orders, 80,000 lines over four years, 40,000 linked DO lines.
ORDERS = 20000
ANALYZED = (
    "sales_agents", "units_of_measure", "product_categories", "products", "warehouses",
    "sales_orders", "sales_order_lines", "orders", "order_lines",
)
#: The owner's team: the captured statement's IN list shows eight agents before it is cut off.
TEAM_SIZE = 20
#: The owner's words: "well under a second", for one achievement run on a loaded CI runner
#: (about 0.05 s ordered and 0.2 s delivered serially at this volume, after the fix).
ACHIEVEMENT_BUDGET = 1.0
#: A hang guard on a whole save or read, which also writes the 20 x 52 child periods: about
#: 0.5 s serially, 3 s measured under a full `-n auto` run; the old statement took minutes.
REQUEST_BUDGET = 5.0


def _nodes(plan: dict) -> Iterator[dict]:
    yield plan
    for child in plan.get("Plans", []):
        yield from _nodes(child)


def _statement(db, specs, company_id):
    """The statement `achieved_by_period` runs, with its bound parameters."""
    from app.services.sales import achievement_service as ach

    captured = {}
    real = db.execute

    def spy(stmt, *args, **kwargs):
        captured["stmt"] = stmt
        return real(stmt, *args, **kwargs)

    db.execute = spy
    try:
        result = ach.achieved_by_period(db, specs, company_id)
    finally:
        db.execute = real
    compiled = captured["stmt"].compile(
        dialect=db.get_bind().dialect, compile_kwargs={"render_postcompile": True}
    )
    return result, compiled.string, compiled.params


def _explain(db, sql: str, params) -> dict:
    cursor = db.connection().connection.cursor()
    cursor.execute("EXPLAIN (ANALYZE, FORMAT JSON) " + sql, params)
    raw = cursor.fetchone()[0]
    return (raw if isinstance(raw, list) else json.loads(raw))[0]["Plan"]


def _weekly_specs(agent_ids: List[str], *, basis: str, scope: str = "all", target_id=None, weeks=52):
    from app.services.sales import achievement_service as ach

    import uuid

    target_id = target_id or str(uuid.uuid4())
    start = date(2026, 1, 1)
    return [
        ach.PeriodSpec(
            period_id=str(uuid.uuid4()), target_id=target_id,
            period_start=start + timedelta(days=7 * w), period_end=start + timedelta(days=7 * w + 6),
            metric="amount", basis=basis, product_scope=scope,
            credits=[(agent_id, None, None) for agent_id in agent_ids],
        )
        for w in range(weeks)
    ]


@pytest.fixture
def volume(api):
    client, db, company_id = api
    vol = seed_volume(db, company_id, orders=ORDERS)
    # Production tables carry planner statistics (autovacuum analyzes a table soon after a
    # sync fills it); these were filled inside the test transaction, so analyze them here.
    # ANALYZE counts this transaction's own rows, and the statistics roll back with it.
    for table in ANALYZED:
        db.execute(text(f"analyze {table}"))
    return client, db, company_id, vol


# --------------------------------------------------------------------------------------- #
# R1, R2: the statement and its plan
# --------------------------------------------------------------------------------------- #


@pytest.mark.parametrize("basis", ["ordered", "delivered"])
def test_line_company_is_compared_as_uuid_never_through_a_text_cast(volume, basis):
    """R1: no column is cast for a comparison, and no scan of an order table filters its rows
    through `company_id::text` (the old statement's seq scan of every line). The planner may
    still hash-join over `sales_order_lines` on cost where a year is a large share of the table
    (it does here, a quarter of the rows); that read is bounded and costs milliseconds."""
    _, db, company_id, vol = volume
    specs = _weekly_specs(vol.agent_ids[:12], basis=basis)
    _, sql, params = _statement(db, specs, company_id)

    assert "AS TEXT" not in sql.upper(), "a column is cast to text"
    plan = _explain(db, sql, params)
    tables = {"sales_orders", "sales_order_lines", "orders", "order_lines"}
    scans = [n for n in _nodes(plan) if n.get("Relation Name") in tables]
    assert {n["Relation Name"] for n in scans} == (
        tables if basis == "delivered" else {"sales_orders", "sales_order_lines"}
    )
    for node in scans:
        for key in ("Filter", "Index Cond", "Recheck Cond"):
            assert "company_id)::text" not in node.get(key, ""), node


@pytest.mark.parametrize("basis", ["ordered", "delivered"])
def test_lines_outside_every_period_never_reach_a_join(volume, basis):
    """R2: the agents' lines are bounded by the periods' dates before anything joins them.

    The volume spreads the lines over four years and the target covers 2026, so the lines the
    statement carries into its joins are exactly the agents' live lines dated in 2026, plus,
    for delivered, those a DO dated in 2026 delivers: about a quarter, never all of them."""
    _, db, company_id, vol = volume
    agents = vol.agent_ids[:12]
    specs = _weekly_specs(agents, basis=basis)
    _, sql, params = _statement(db, specs, company_id)
    plan = _explain(db, sql, params)

    live = (
        "from sales_order_lines sol join sales_orders so on so.id = sol.sales_order_id "
        "where so.sales_agent_id = any(cast(:a as uuid[])) and so.status <> 'cancelled' "
        "and sol.line_status <> 'cancelled' and so.order_date is not null"
    )
    span = {"a": agents, "lo": specs[0].period_start, "hi": specs[-1].period_end}
    lines_of_agents = db.execute(text(f"select count(*) {live}"), span).scalar()
    bound = "so.order_date between :lo and :hi"
    if basis == "delivered":
        bound += (
            " or sol.id in (select ol.sales_order_line_id from order_lines ol "
            "join orders o on o.id = ol.order_id where o.order_date between :lo and :hi)"
        )
    expected = db.execute(text(f"select count(*) {live} and ({bound})"), span).scalar()
    assert 0 < expected <= lines_of_agents * 0.35, (expected, lines_of_agents)

    nodes = list(_nodes(plan))
    cte = [n for n in nodes if n.get("Subplan Name") == "CTE agent_lines"]
    if cte:
        carried = cte[0]["Actual Rows"]
    else:
        # A single use is inlined: the lines are what the plan reads of the table.
        carried = sum(
            n["Actual Rows"] * n["Actual Loops"]
            for n in nodes
            if n.get("Relation Name") == "sales_order_lines"
        )
    assert carried == expected, (carried, expected)
    # Nothing crosses the lines with every period or every credit row.
    removed = sum(n.get("Rows Removed by Join Filter", 0) for n in nodes)
    assert removed <= expected, (removed, expected)


def test_category_walk_runs_once_and_joins(volume):
    """R2: a categories target resolves its category set once, not once per line."""
    from app.models.sales import SalesTargetScope

    client, db, company_id, vol = volume
    # Scope rows hang off a real target, so the root category is scoped on a saved one.
    saved = client.post(BASE, json={
        "subject_kind": "agent", "sales_agent_id": vol.agent_ids[0], "name": "ZZT Cat", "metric": "amount",
        "basis": "delivered", "product_scope": "categories", "category_ids": [vol.category_ids[0]],
        "start_date": "2026-01-01", "end_date": "2026-12-30", "target_value": 0,
    })
    assert saved.status_code == 201, saved.text
    target_id = saved.json()["id"]
    assert db.query(SalesTargetScope).filter(SalesTargetScope.target_id == target_id).count() == 1

    specs = _weekly_specs(vol.agent_ids[:12], basis="delivered", scope="categories", target_id=target_id)
    result, sql, params = _statement(db, specs, company_id)
    plan = _explain(db, sql, params)

    walks = [n for n in _nodes(plan) if n["Node Type"] == "Recursive Union"]
    assert len(walks) == 1, walks
    assert walks[0]["Actual Loops"] == 1, walks[0]
    # The root category holds every generated product, so the categories target counts what an
    # all-products target over the same periods counts.
    everything, _, _ = _statement(db, _weekly_specs(vol.agent_ids[:12], basis="delivered"), company_id)
    assert sum(result.values()) == sum(everything.values()) > 0


# --------------------------------------------------------------------------------------- #
# R3: a save runs the achievement once
# --------------------------------------------------------------------------------------- #


def test_a_save_runs_the_achievement_once(api, monkeypatch):
    """R3: the create and the edit each answer with the target page, which is the only caller
    of the achievement on the save path; the save itself never computes it."""
    from app.services.sales import achievement_service as ach

    client, db, company_id = api
    vol = seed_volume(db, company_id, orders=200, agents=4)
    team = client.post(TEAMS_BASE, json={"name": "ZZT Perf", "sales_agent_ids": vol.agent_ids}).json()

    calls = []
    real = ach.achieved_by_period
    monkeypatch.setattr(ach, "achieved_by_period", lambda *a, **k: calls.append(1) or real(*a, **k))

    created = client.post(BASE, json={
        "subject_kind": "team", "sales_team_id": team["id"], "name": "ZZT All", "metric": "amount",
        "basis": "ordered", "product_scope": "all", "start_date": "2026-01-01", "end_date": "2026-12-31",
        "split_every": 1, "split_unit": "month",
        "agent_figures": [{"sales_agent_id": a, "target_value": 100} for a in vol.agent_ids],
    })
    assert created.status_code == 201, created.text
    assert len(calls) == 1

    calls.clear()
    edited = client.patch(f"{BASE}/{created.json()['id']}", json={"name": "ZZT All renamed"})
    assert edited.status_code == 200, edited.text
    assert len(calls) == 1


# --------------------------------------------------------------------------------------- #
# R4: the owner's journey on the generated volume, inside the budget
# --------------------------------------------------------------------------------------- #


@pytest.mark.parametrize("basis", ["ordered", "delivered"])
def test_saving_an_all_products_team_target_returns_inside_the_budget(volume, monkeypatch, basis):
    """The owner's hand test: an all-products team target of twenty agents over a year, split
    weekly, saved; then the Targets list (all mode) and the target page read it back. Each
    achievement run stays under a second (the old statement took 1.6 s delivered at this
    volume, and minutes on the hand-test stack); each request stays under a hang guard."""
    from app.services.sales import achievement_service as ach

    client, db, company_id, vol = volume
    members = vol.agent_ids[:TEAM_SIZE]
    team = client.post(TEAMS_BASE, json={"name": "ZZT Perf", "sales_agent_ids": members}).json()
    payload = {
        "subject_kind": "team", "sales_team_id": team["id"], "name": "ZZT All products",
        "metric": "amount", "basis": basis, "product_scope": "all",
        "start_date": "2026-01-01", "end_date": "2026-12-30", "split_every": 1, "split_unit": "week",
        "agent_figures": [{"sales_agent_id": a, "target_value": 10} for a in members],
    }
    runs: List[float] = []
    real = ach.achieved_by_period

    def timed(*args, **kwargs):
        started = time.monotonic()
        try:
            return real(*args, **kwargs)
        finally:
            runs.append(time.monotonic() - started)

    monkeypatch.setattr(ach, "achieved_by_period", timed)

    def request(send):
        started = time.monotonic()
        res = send()
        return res, time.monotonic() - started

    saved, save_seconds = request(lambda: client.post(BASE, json=payload))
    assert saved.status_code == 201, saved.text
    assert sum(p["achieved_value"] for p in saved.json()["periods"]) > 0
    listed, list_seconds = request(lambda: client.get(BASE, params={"subject": "team", "all": "true"}))
    assert listed.status_code == 200, listed.text
    shown, show_seconds = request(lambda: client.get(f"{BASE}/{saved.json()['id']}"))
    assert shown.status_code == 200, shown.text

    assert len(runs) == 3, runs
    assert max(runs) < ACHIEVEMENT_BUDGET, f"achievement runs took {runs}"
    for what, seconds in (("save", save_seconds), ("list", list_seconds), ("detail", show_seconds)):
        assert seconds < REQUEST_BUDGET, f"{what} took {seconds:.2f}s"


# --------------------------------------------------------------------------------------- #
# R2 correctness at the bound: what the date bound must not drop
# --------------------------------------------------------------------------------------- #


def test_a_line_ordered_before_the_target_and_delivered_inside_it_still_counts(api):
    """The bound reads lines by order date AND by linked DO date: a line ordered in September
    and delivered by a DO in October counts on an October-only delivered target."""
    from .test_sales_targets_s1 import _agent, _do_line, _warehouse

    client, db, company_id = api
    agent = _agent(db, "EDGE")
    category = _category(db, company_id)
    product = _product(db, company_id, category.id)
    warehouse = _warehouse(db, company_id)
    _, line = _so_line(
        db, company_id, agent_id=agent.id, order_date=date(2026, 9, 28), line_total=Decimal("1000"),
        qty_ordered=10, qty_delivered=10, product_id=product.id,
    )
    _do_line(db, company_id, product.id, warehouse.id, line.id, quantity=4, order_date=date(2026, 10, 3))

    target = client.post(BASE, json={
        "subject_kind": "agent", "sales_agent_id": agent.id, "name": "ZZT Edge", "metric": "amount",
        "basis": "delivered", "product_scope": "all", "start_date": "2026-10-01", "end_date": "2026-10-31",
        "target_value": 0,
    })
    assert target.status_code == 201, target.text
    assert target.json()["periods"][0]["achieved_value"] == 400  # 4 of 10 units of RM 1,000
