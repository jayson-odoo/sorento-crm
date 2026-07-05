"""Deterministic name/code → UUID coercion for UUID-intake MCP tool args.

Regression for the HANLIM trace: the resolver mapped the customer name to UUIDs,
but the LLM passed the NAME into ``customer_ids`` → backend 400 INVALID_UUID.
``_coerce_uuid_args`` substitutes the resolver's UUIDs at dispatch. Pure unit
tests — no DB, no MCP (the fallback resolve is exercised only on a turn-map miss
and degrades to [] without a DB).
"""
from __future__ import annotations

import app.services.ai_assistant_service as svc_module
from app.services.ai_assistant_service import AIAssistantChatService
from app.services.entity_resolver import (
    ResolutionResult,
    ResolvedEntity,
    TokenResolution,
)

_U1 = "3c15f4e4-be46-4fd7-9de8-3430a9b1217a"
_U2 = "2d0cd958-9f5e-4eee-8b6e-ed31a94bee44"
_U3 = "57cf23af-c2d1-4251-afe7-0c005f4b01d0"


def _svc() -> AIAssistantChatService:
    # No DB: the fallback resolve (turn-map miss) degrades to [] gracefully.
    s = AIAssistantChatService.__new__(AIAssistantChatService)
    s.db = None  # type: ignore[attr-defined]
    return s


def _hanlim_resolution() -> ResolutionResult:
    matches = [
        ResolvedEntity(
            entity_type="customer",
            canonical_code="HANLIM TRADING SDN BHD",
            uuid=_U1,
            display={"debtor_name": "HANLIM TRADING SDN BHD", "debtor_code": "300-H030"},
        ),
        ResolvedEntity(
            entity_type="customer",
            canonical_code="HANLIM TRADING SDN BHD (CERAMIC & ELLECI)",
            uuid=_U2,
            display={"debtor_name": "HANLIM TRADING SDN BHD (CERAMIC & ELLECI)"},
        ),
        ResolvedEntity(
            entity_type="customer",
            canonical_code="HANLIM TRADING SDN BHD [A/C I]",
            uuid=_U3,
            display={"debtor_name": "HANLIM TRADING SDN BHD [A/C I]"},
        ),
    ]
    return ResolutionResult(
        tokens=["hanlim"],
        resolutions=[TokenResolution(token="hanlim", matches=matches, ambiguous=True)],
        elapsed_ms=1.0,
    )


def test_names_substituted_to_uuids():
    out, subs = _svc()._coerce_uuid_args(
        {
            "customer_ids": [
                "HANLIM TRADING SDN BHD",
                "HANLIM TRADING SDN BHD (CERAMIC & ELLECI)",
                "HANLIM TRADING SDN BHD [A/C I]",
            ],
            "actual_delivery_date_from": "2026-01-01",
        },
        _hanlim_resolution(),
    )
    assert out["customer_ids"] == [_U1, _U2, _U3]
    assert out["actual_delivery_date_from"] == "2026-01-01"  # non-UUID param untouched
    assert len(subs) == 3


def test_ambiguous_single_name_expands_to_all_uuids():
    # One name the resolver matched to several rows → every matching UUID.
    res = _hanlim_resolution()
    # collapse all three matches under one token key by re-labelling canonical_code
    for m in res.resolutions[0].matches:
        m.canonical_code = "HANLIM"
        m.display = {"debtor_name": "HANLIM"}
    out, _ = _svc()._coerce_uuid_args({"customer_ids": ["HANLIM"]}, res)
    assert set(out["customer_ids"]) == {_U1, _U2, _U3}


def test_json_string_list_form_is_handled():
    out, _ = _svc()._coerce_uuid_args(
        {"customer_ids": '["HANLIM TRADING SDN BHD"]'}, _hanlim_resolution()
    )
    assert out["customer_ids"] == [_U1]


def test_already_uuid_passes_through_untouched():
    out, subs = _svc()._coerce_uuid_args({"customer_ids": [_U1]}, _hanlim_resolution())
    assert out["customer_ids"] == [_U1]
    assert subs == []


def test_unresolved_value_passes_through_for_backend_to_report():
    # No DB fallback available → an unknown name is left as-is (not dropped), so
    # the backend surfaces INVALID_UUID rather than us silently emptying a filter.
    out, subs = _svc()._coerce_uuid_args(
        {"customer_ids": ["NOPE PTE LTD"]}, _hanlim_resolution()
    )
    assert out["customer_ids"] == ["NOPE PTE LTD"]
    assert subs == []


def test_entity_type_isolation_customer_name_not_used_for_product_param():
    # A customer resolution must not fill product_ids.
    out, subs = _svc()._coerce_uuid_args(
        {"product_ids": ["HANLIM TRADING SDN BHD"]}, _hanlim_resolution()
    )
    assert out["product_ids"] == ["HANLIM TRADING SDN BHD"]
    assert subs == []


def test_no_resolution_is_noop():
    args = {"customer_ids": ["HANLIM TRADING SDN BHD"]}
    out, subs = _svc()._coerce_uuid_args(dict(args), None)
    assert out == args
    assert subs == []


def test_arg_list_coercion_forms():
    assert svc_module._coerce_arg_to_list(["a", "b"]) == ["a", "b"]
    assert svc_module._coerce_arg_to_list('["a","b"]') == ["a", "b"]
    assert svc_module._coerce_arg_to_list("a,b") == ["a", "b"]
    assert svc_module._coerce_arg_to_list("a") == ["a"]
    assert svc_module._coerce_arg_to_list(None) == []
    assert svc_module._coerce_arg_to_list("") == []
