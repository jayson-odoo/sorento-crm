"""REPORT-FILTER-ALL live x3 step 19 (crew, 7 Nov, head 2a8e6f7c): "outstanding for supplier LASHIQI" ran the CUSTOMER
outstanding list (runs 1, 3) beside the parser's outstanding report object, though LASHIQI has 85 open POs. The object
has no supplier slot, so it wrote the name in `customers`, and round 7 protected every name the object held from the
supplier path. A party word's side is its entity kind (owner, 2 Nov): the supplier's open POs run. Through the real turn
with the span pass placing the word on the supplier row, as `test_supplier_ask` does."""

from __future__ import annotations

import pytest

from app.services.chatbot.head import list_resolver
from app.services.chatbot.head import parser as parser_mod
from tests.chatbot.test_report_totals_filters import _ra2
from tests.chatbot.test_supplier_ask import (  # noqa: F401 - fixture + helpers
    SUPPLIER,
    _ask,
    _po_calls,
    _span_turn,
    _staff_world,
    session_factory,
)

WORD = "Taiyang"


@pytest.mark.parametrize("in_customers", [True, False], ids=["object-customers", "object-empty"])
@pytest.mark.parametrize("hint", ["supplier", "customer"])
def test_l19_supplier_outstanding_beside_a_report_object_lists_its_open_pos(
    session_factory, monkeypatch, in_customers, hint
) -> None:
    real = parser_mod.ParserConfig

    def _cfg(*a, **k):
        k.setdefault("report_ask", True)
        k.setdefault("report_ask_defined", frozenset({"frame", "company_or_brand", parser_mod.REPORT_ALL}))
        return real(*a, **k)

    monkeypatch.setattr(parser_mod, "ParserConfig", _cfg)
    ids = _staff_world(session_factory)
    qf = _ask(WORD, None, hint=hint)
    qf["order_status"] = "outstanding"
    qf["report_ask"] = _ra2(None, kind="outstanding", customers=[WORD] if in_customers else [])
    reply, captured, _seen = _span_turn(
        session_factory, monkeypatch, f"outstanding for supplier {WORD}", list_resolver.Span(WORD, "supplier"),
        {WORD, SUPPLIER}, qf=qf,
    )
    calls = _po_calls(captured)
    assert calls and calls[0].get("supplier_ids") == [ids["ours"]], (reply, captured)
    assert not [n for n, _ in captured if n == "crm_report_ask"], captured
