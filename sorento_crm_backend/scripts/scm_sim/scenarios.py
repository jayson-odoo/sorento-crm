"""The declarative scenario registry.

Each row is one synthetic SKU, one story. Numbers are chosen so the ARITHMETIC lands where
the title says it should - see the module docstring in ``world.py`` for the formulae
(``ROP = demand_rate * 37`` under the fixed sim lead=30/safety=7 defaults, ``order_up_to =
demand_rate * 67``). Nothing here is asserted against; the point of the harness is the
snapshot, not a pass/fail check. Where a scenario is a deliberate probe of an engine quirk
(S20, S25) the docstring says so.
"""
from __future__ import annotations

from scripts.scm_sim.world import ScenarioSpec

SCENARIOS: list[ScenarioSpec] = [
    ScenarioSpec(
        code="SIM-P001", title="Steady high demand, low stock",
        segment="dealer", avg_daily_demand=20, demand_cv=0.2, demand_pattern="steady",
        on_hand=100,
        expected_note="net (100) well below ROP (740) -> triggered buy.",
    ),
    ScenarioSpec(
        code="SIM-P002", title="Steady low demand, ample stock",
        segment="dealer", avg_daily_demand=2, demand_cv=0.15, demand_pattern="steady",
        on_hand=150, so_committed_qty=15,
        expected_note="net (135) above ROP (74), days-of-cover (67.5) under the overstock "
                       "ceiling (120); committed demand -> covered, not buy.",
    ),
    ScenarioSpec(
        code="SIM-P003", title="Mid demand exact at reorder-point boundary",
        segment="dealer", avg_daily_demand=5, demand_cv=0.2, demand_pattern="steady",
        on_hand=185,
        expected_note="net == ROP exactly (185); trigger is net<=ROP -> triggers.",
    ),
    ScenarioSpec(
        code="SIM-P004", title="Spiky demand",
        segment="dealer", avg_daily_demand=8, demand_cv=0.9, demand_pattern="spiky",
        on_hand=50,
        expected_note="high demand_cv; confidence should read low/medium, never high.",
    ),
    ScenarioSpec(
        code="SIM-P005", title="Rising trend",
        segment="dealer", avg_daily_demand=6, demand_cv=0.2, demand_pattern="rising",
        on_hand=50,
        expected_note="trajectory verdict=rising -> suggested_level rounds UP.",
    ),
    ScenarioSpec(
        code="SIM-P006", title="Declining trend",
        segment="dealer", avg_daily_demand=6, demand_cv=0.2, demand_pattern="declining",
        on_hand=50,
        expected_note="trajectory verdict=falling -> suggested_level rounds DOWN.",
    ),
    ScenarioSpec(
        code="SIM-P007", title="Dead stock",
        segment="dealer", avg_daily_demand=0, demand_cv=0.0, demand_pattern="none",
        on_hand=50, dead_movement_days_ago=220, reorder_level_value=240,
        expected_note="one movement 220d ago, nothing since -> disposition/dead, no buy. "
                       "Dead stock still carries a reorder level (240, ABOVE on_hand 50 - "
                       "user feedback: 'dead stock still has a level'); auto mode's story "
                       "is unaffected (the level plays no part in the disposition check), "
                       "but flipping the global policy to manual is the trap this exposes: "
                       "the level basis alone would trigger a buy on a SKU that should be "
                       "written off, not restocked - the disposition rec has to win anyway.",
    ),
    ScenarioSpec(
        code="SIM-P008", title="Slow moving, sparse history",
        segment="dealer", avg_daily_demand=0.5, demand_cv=0.3, demand_pattern="steady",
        on_hand=5,
        expected_note="small ROP (18.5); triggers a small buy.",
    ),
    ScenarioSpec(
        code="SIM-P009", title="Fast moving, high volume",
        segment="dealer", avg_daily_demand=50, demand_cv=0.15, demand_pattern="steady",
        sales_volume=1500, on_hand=500,
        expected_note="high demand_rate; large ROP/OUP and a large buy.",
    ),
    ScenarioSpec(
        code="SIM-P010", title="Low sales volume but positive",
        segment="dealer", avg_daily_demand=0.2, demand_cv=0.25, demand_pattern="steady",
        on_hand=1,
        expected_note="tiny but nonzero demand; small triggered buy, never treated as zero.",
    ),
    ScenarioSpec(
        code="SIM-P011", title="Old last purchase",
        segment="dealer", avg_daily_demand=4, demand_cv=0.2, on_hand=50,
        last_purchase_age_days=220, last_purchase_cost=60,
        expected_note="age 220d > 180d stale window, no previous price -> advice=stale.",
    ),
    ScenarioSpec(
        code="SIM-P012", title="Recent last purchase",
        segment="dealer", avg_daily_demand=4, demand_cv=0.2, on_hand=50,
        last_purchase_age_days=30, last_purchase_cost=60,
        expected_note="age 30d, no movement -> advice=recent.",
    ),
    ScenarioSpec(
        code="SIM-P013", title="Last cost HIGH vs previous (price moved up)",
        segment="dealer", avg_daily_demand=4, demand_cv=0.2, on_hand=50,
        last_purchase_age_days=30, last_purchase_cost=120,
        previous_purchase_age_days=200, previous_purchase_cost=100,
        expected_note="+20% > 5% threshold -> advice=moving, movement_pct positive.",
    ),
    ScenarioSpec(
        code="SIM-P014", title="Last cost LOW vs previous (price dropped)",
        segment="dealer", avg_daily_demand=4, demand_cv=0.2, on_hand=50,
        last_purchase_age_days=30, last_purchase_cost=80,
        previous_purchase_age_days=200, previous_purchase_cost=100,
        expected_note="-20% -> advice=moving, movement_pct negative.",
    ),
    ScenarioSpec(
        code="SIM-P015", title="High unit cost item",
        segment="dealer", avg_daily_demand=5, demand_cv=0.2, on_hand=100,
        unit_cost=5000, list_price=6000,
        expected_note="large cash_impact off a high per-unit cost, moderate margin.",
    ),
    ScenarioSpec(
        code="SIM-P016", title="Low unit cost item",
        segment="dealer", avg_daily_demand=5, demand_cv=0.2, on_hand=100,
        unit_cost=2, list_price=3,
        expected_note="tiny cash_impact despite the same qty as S015.",
    ),
    ScenarioSpec(
        code="SIM-P017", title="High margin",
        segment="dealer", avg_daily_demand=5, demand_cv=0.2, on_hand=100,
        unit_cost=50, list_price=500,
        expected_note="list >> cost; feeds the M4 cash-ranking margin factor high.",
    ),
    ScenarioSpec(
        code="SIM-P018", title="Low margin",
        segment="dealer", avg_daily_demand=5, demand_cv=0.2, on_hand=100,
        unit_cost=100, list_price=105,
        expected_note="list ~ cost; feeds the M4 cash-ranking margin factor low.",
    ),
    ScenarioSpec(
        code="SIM-P019", title="MoQ 100, need ~52, hot selling",
        segment="dealer", avg_daily_demand=1, demand_cv=0.1, on_hand=15,
        moq=100, order_multiple=10,
        expected_note="net (15) <= ROP (37); recommended=52 (OUP 67 - net 15); MOQ rounds "
                       "it up to 100.",
    ),
    ScenarioSpec(
        code="SIM-P020", title="MoQ 100, need ~20, cold selling (probe)",
        segment="dealer", avg_daily_demand=0.3, demand_cv=0.5, on_hand=0,
        moq=100, order_multiple=10,
        expected_note="PROBE: recommended~=20.1 on almost no demand (net 0 <= ROP 11.1); "
                       "does the engine still round up to the full 100 MOQ regardless of "
                       "how cold the SKU is? Compare rounded_qty against S019 in the "
                       "snapshot -- same 100, on a fraction of the demand and confidence.",
    ),
    ScenarioSpec(
        code="SIM-P021", title="Order multiple 24 rounding",
        segment="dealer", avg_daily_demand=1, demand_cv=0.2, on_hand=17,
        order_multiple=24,
        expected_note="net (17) <= ROP (37); recommended=50 (OUP 67 - net 17) -> "
                       "ceil(50/24)*24 = 72.",
    ),
    ScenarioSpec(
        code="SIM-P022", title="Giant MoQ vs tiny demand",
        segment="dealer", avg_daily_demand=0.05, demand_cv=0.2, on_hand=0,
        moq=1000,
        expected_note="recommended~=3.35 but MOQ 1000 dominates -> a 1000-unit buy on "
                       "almost no demand; confidence should read low.",
    ),
    ScenarioSpec(
        code="SIM-P023", title="Cover by stock only",
        segment="project", avg_daily_demand=3, demand_cv=0.2, on_hand=300,
        so_committed_qty=40,
        expected_note="net (260) > ROP (111) on stock alone -> covered, not buy.",
    ),
    ScenarioSpec(
        code="SIM-P024", title="Cover by SPO incoming only",
        segment="dealer", avg_daily_demand=2, demand_cv=0.2, on_hand=5,
        so_committed_qty=30, spo_incoming_qty=120, spo_eta_days=25,
        expected_note="on_hand alone is short; +SPO(120) pushes net (95) above ROP (74) "
                       "-> covered, on_order visible in inputs.",
    ),
    ScenarioSpec(
        code="SIM-P025", title="Cover by PO only (quirk probe)",
        segment="dealer", avg_daily_demand=2, demand_cv=0.2, on_hand=5,
        so_committed_qty=30, po_open_qty=120, po_order_date_days_ago=10,
        expected_note="PROBE (ADR 337): the PO book is informational only and does NOT "
                       "net against demand - expect a BUY to still fire despite 120 units "
                       "'on order' via PO. po_ordered should be visible in inputs.",
    ),
    ScenarioSpec(
        code="SIM-P026", title="Stock + SPO mix -> covered",
        segment="dealer", avg_daily_demand=2, demand_cv=0.2, on_hand=70,
        so_committed_qty=50, spo_incoming_qty=70,
        expected_note="net (90) > ROP (74) via stock+SPO together -> covered.",
    ),
    ScenarioSpec(
        code="SIM-P027", title="Stock + PO mix -> covered by stock, PO informational",
        segment="dealer", avg_daily_demand=3, demand_cv=0.2, on_hand=300,
        so_committed_qty=40, po_open_qty=80,
        expected_note="net (260) > ROP (111) from stock alone -> covered; po_ordered (80) "
                       "carried in inputs but plays no part in the netting.",
    ),
    ScenarioSpec(
        code="SIM-P028", title="SPO + PO mix -> covered by SPO, PO informational",
        segment="dealer", avg_daily_demand=2, demand_cv=0.2, on_hand=10,
        so_committed_qty=40, spo_incoming_qty=110, po_open_qty=90,
        expected_note="net (80) > ROP (74) from stock+SPO; po_ordered (90) informational.",
    ),
    ScenarioSpec(
        code="SIM-P029", title="Stock+SPO+PO mix, still buy remainder",
        segment="dealer", avg_daily_demand=2, demand_cv=0.2, on_hand=10,
        so_committed_qty=60, spo_incoming_qty=20, po_open_qty=30,
        expected_note="net (-30) still <= ROP (74) even with SPO - buy fires for the "
                       "remainder; on_order (20) and po_ordered (30) both visible in inputs.",
    ),
    ScenarioSpec(
        code="SIM-P030", title="SPO partial, buy remainder",
        segment="dealer", avg_daily_demand=3, demand_cv=0.2, on_hand=20,
        spo_incoming_qty=50,
        expected_note="SPO reduces but does not eliminate the buy; on_order (50) visible.",
    ),
    ScenarioSpec(
        code="SIM-P031", title="Reorder level: net above level, no trigger",
        segment="dealer", policy="reorder_level", reorder_level_value=100,
        avg_daily_demand=2, demand_cv=0.2, demand_pattern="steady", on_hand=150,
        expected_note="net (150) > level (100); no committed demand -> nothing emitted at "
                       "all - that ABSENCE is the signal, check recommendation_count == 0.",
    ),
    ScenarioSpec(
        code="SIM-P032", title="Reorder level: net below, qty = level - net (MOQ floored)",
        segment="dealer", policy="reorder_level", reorder_level_value=100, moq=60,
        avg_daily_demand=2, demand_cv=0.2, demand_pattern="steady", on_hand=50,
        expected_note="net (50) <= level (100); recommended=50, MOQ(60) floors rounded_qty.",
    ),
    ScenarioSpec(
        code="SIM-P033", title="Needs level: NULL level with movement",
        segment="dealer", policy="needs_level",
        avg_daily_demand=3, demand_cv=0.2, demand_pattern="steady", on_hand=40,
        expected_note="no scm.reorder_level row at all -> rec_type=needs_level, and a "
                       "suggested_level computed from the movement history regardless.",
    ),
    ScenarioSpec(
        code="SIM-P034", title="CNY-cost supplier",
        segment="dealer", supplier="C", unit_cost=500,
        avg_daily_demand=6, demand_cv=0.2, on_hand=50,
        expected_note="cash_impact = rounded_qty * 500 * CNY rate_to_base (0.606061).",
    ),
    ScenarioSpec(
        code="SIM-P035", title="THB supplier, no currency_rate row",
        segment="dealer", supplier="A", currency="THB", unit_cost=300,
        avg_daily_demand=6, demand_cv=0.2, on_hand=50,
        expected_note="no scm.currency_rate row for THB -> unit_cost_base/cash_impact "
                       "None, missing_rate_currency='THB' named, NEVER defaulted to 1.0.",
    ),
    ScenarioSpec(
        code="SIM-P036", title="Project segment OI demand",
        segment="project", avg_daily_demand=8, demand_cv=0.2, on_hand=100,
        so_committed_qty=40,
        expected_note="demand_class=project + demand_origin=scm_order_inquiry -> counted "
                       "by scm.committed_v per S13b; net (60) <= ROP (296) -> buy.",
    ),
    ScenarioSpec(
        code="SIM-P037", title="Retail SO outstanding",
        segment="dealer", avg_daily_demand=8, demand_cv=0.2, on_hand=100,
        so_committed_qty=40,
        expected_note="plain (non-project) open SO line, counted unconditionally; same "
                       "arithmetic shape as S036 for a same-segment-axis comparison.",
    ),
    ScenarioSpec(
        code="SIM-P038", title="Zero-demand, zero-stock noise row",
        segment="dealer", avg_daily_demand=0, demand_cv=0.0, on_hand=0,
        expected_note="on_hand<=0 blocks disposition; recommended rounds to 0 -> nothing "
                       "emitted. recommendation_count MUST be 0.",
    ),
]

#: Fast lookup by code, used by ``runner.py --scenario``.
BY_CODE: dict[str, "ScenarioSpec"] = {s.code: s for s in SCENARIOS}
