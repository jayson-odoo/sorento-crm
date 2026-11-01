"""AGENTIC-UNIFY PR 4, slice 1 (red): a brand-scoped linked contact and the ported reads (AC-7, second half).

Every read goes through `services._mcp_call(db)`, which refuses a tool by `brand_scope_allows_tool` and guards
the result with `brand_guard.guard_result` for a tool marked `filtered`. These tests pin what that does for
the ported reads that can name a product, through the real seam with only the MCP client faked.

The guard prunes a row only by a product key it finds (`product_code`, `item_code`, `product_id`, plus the
tool's own keys in `BRAND_SCOPE_PRODUCT_KEYS`); a row naming no product passes, as on every filtered tool.
Projects carry no brand, so a scope naming a brand gets no project read (`brand_scope_allows_tool`).
"""
from __future__ import annotations

import json

import pytest

from app.models.base import set_brand_scope, set_company_scope
from app.services.company_scope import DEFAULT_COMPANY_ID
from tests._brand_scope_seed import db, world  # noqa: F401  (fixtures by name)


class _Client:
    answer: object = {}
    calls: list[tuple] = []

    def __init__(self, *a, **k) -> None:
        pass

    def call_tool(self, name, args):
        _Client.calls.append((name, args))
        return json.dumps(_Client.answer)


def _seam(db, world, monkeypatch, *, scoped: bool, answer):
    import app.services.ai_assistant_service as svc
    from app.services.chatbot.lanes.business import services

    _Client.calls = []
    _Client.answer = answer
    monkeypatch.setattr(svc, "MCPRuntimeClient", _Client)
    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
    set_brand_scope(db, frozenset({world.mocha.id}) if scoped else None)
    return services._mcp_call(db)


def _complaints(world):
    mocha, sorento = world.p_mocha.product_code, world.p_sorento.product_code
    return {
        "data": [
            {"complaint_number": "ZZT-C-IN", "product_code": mocha, "product_lines": [{"product_code": mocha}]},
            {"complaint_number": "ZZT-C-OUT", "product_code": sorento, "product_lines": [{"product_code": sorento}]},
            {"complaint_number": "ZZT-C-NONE", "product_code": None, "product_lines": []},
            {
                "complaint_number": "ZZT-C-MIXED",
                "product_code": mocha,
                "product_lines": [{"product_code": mocha}, {"product_code": sorento}],
            },
        ],
        "pagination": {"total": 4},
    }


def test_AC7_complaint_rows_of_another_brand_never_reach_the_agent(db, world, monkeypatch):
    call = _seam(db, world, monkeypatch, scoped=True, answer=_complaints(world))
    result = call("crm_complaints_list", {})
    numbers = [r["complaint_number"] for r in result["data"]]
    assert "ZZT-C-IN" in numbers
    assert "ZZT-C-OUT" not in numbers, numbers
    assert world.p_sorento.product_code not in json.dumps(result), "another brand's product code reached the agent"


def test_AC7_a_mixed_complaint_keeps_its_header_and_loses_the_other_brands_line(db, world, monkeypatch):
    call = _seam(db, world, monkeypatch, scoped=True, answer=_complaints(world))
    result = call("crm_complaints_list", {})
    mixed = next(r for r in result["data"] if r["complaint_number"] == "ZZT-C-MIXED")
    assert [ln["product_code"] for ln in mixed["product_lines"]] == [world.p_mocha.product_code]


def test_AC7_a_complaint_naming_no_product_is_kept(db, world, monkeypatch):
    call = _seam(db, world, monkeypatch, scoped=True, answer=_complaints(world))
    result = call("crm_complaints_list", {})
    assert "ZZT-C-NONE" in [r["complaint_number"] for r in result["data"]]


def test_AC7_the_unscoped_control_sees_every_complaint(db, world, monkeypatch):
    call = _seam(db, world, monkeypatch, scoped=False, answer=_complaints(world))
    result = call("crm_complaints_list", {})
    assert len(result["data"]) == 4


def test_AC7_complaint_analytics_buckets_for_another_brands_product_are_dropped(db, world, monkeypatch):
    body = {
        "groups": [
            {"group_key": world.p_mocha.product_code.lower(), "group_label": world.p_mocha.product_code, "value": 2},
            {"group_key": world.p_sorento.product_code.lower(), "group_label": world.p_sorento.product_code, "value": 5},
        ],
        "total": {"group_key": "__all__", "value": 7},
    }
    call = _seam(db, world, monkeypatch, scoped=True, answer=body)
    result = call("crm_complaint_analytics", {"group_by": "product"})
    keys = [g["group_key"] for g in result["groups"]]
    assert world.p_mocha.product_code.lower() in keys
    assert world.p_sorento.product_code.lower() not in keys, keys


def test_AC7_order_analytics_buckets_for_another_brands_product_are_dropped(db, world, monkeypatch):
    body = {
        "groups": [
            {"group_key": world.p_mocha.product_code, "group_label": world.p_mocha.product_code, "value": 2},
            {"group_key": world.p_sorento.product_code, "group_label": world.p_sorento.product_code, "value": 5},
        ],
        "total": {"group_key": "__all__", "value": 7},
    }
    call = _seam(db, world, monkeypatch, scoped=True, answer=body)
    result = call("crm_order_analytics", {"group_by": "product"})
    keys = [g["group_key"] for g in result["groups"]]
    assert world.p_mocha.product_code in keys
    assert world.p_sorento.product_code not in keys, keys


def test_AC7_the_project_forecast_is_refused_for_a_brand_scoped_contact(db, world, monkeypatch):
    from app.services.chatbot.lanes.business.fetch import ToolNotAllowed

    call = _seam(db, world, monkeypatch, scoped=True, answer={"pipeline": 1})
    with pytest.raises(ToolNotAllowed):
        call("crm_project_forecast", {})
    assert _Client.calls == []


PROJECT_READS = [
    ("crm_projects_list", {}),
    ("crm_project_detail", {"project_id": "x"}),
    ("crm_project_quotations_list", {"project_id": "x"}),
    ("crm_project_forecast", {}),
]


@pytest.mark.parametrize("name,args", PROJECT_READS, ids=[r[0] for r in PROJECT_READS])
def test_AC7_a_scope_naming_a_brand_gets_no_project_read_at_all(db, world, monkeypatch, name, args):
    """Projects carry no brand, so the guard cannot narrow them: refused like the forecast (crew ruling (b))."""
    from app.services.chatbot.lanes.business.fetch import ToolNotAllowed

    call = _seam(db, world, monkeypatch, scoped=True, answer={"data": [{"project_code": "ZZT-P-1"}]})
    with pytest.raises(ToolNotAllowed):
        call(name, args)
    assert _Client.calls == [], f"{name} reached the MCP for a brand-scoped contact"


@pytest.mark.parametrize("name,args", PROJECT_READS, ids=[r[0] for r in PROJECT_READS])
def test_AC7_a_class_only_scope_still_runs_every_project_read(db, world, monkeypatch, name, args):
    """`limits_brands` is False for a scope of item classes alone (TAG-BRAND-CLASS crew ruling (b))."""
    call = _seam(db, world, monkeypatch, scoped=False, answer={"data": [{"project_code": "ZZT-P-1"}]})
    set_brand_scope(db, frozenset({"class:ZZTCLS"}))
    from app.services.chatbot.lanes.business import services

    call = services._mcp_call(db)
    call(name, args)
    assert [c[0] for c in _Client.calls] == [name]


@pytest.mark.parametrize("name", ["crm_order_analytics", "crm_find"])
def test_AC7_a_tool_outside_the_read_only_set_is_refused_at_the_seam(db, world, monkeypatch, name):
    """Until the names are in `CHATBOT_READ_ONLY_TOOLS` the seam refuses them before any client is built."""
    from app.services.chatbot.lanes.business.fetch import ToolNotAllowed

    call = _seam(db, world, monkeypatch, scoped=False, answer={"data": [{"ref": 1}]})
    try:
        call(name, {})
    except ToolNotAllowed as exc:  # pragma: no cover - the red state
        pytest.fail(f"{name} is refused by the read-only allow-list: {exc}")
    assert [c[0] for c in _Client.calls] == [name]
