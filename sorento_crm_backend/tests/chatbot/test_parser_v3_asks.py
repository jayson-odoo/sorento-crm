"""AC-1021, AC-1026: parser v3 emits `asks[]` (D3), the engine flattens it at intake, and
`intent_hint` is gone from the schema, the state and the trace.

RED:
- `head/parser.py::PARSE_OUTPUT_JSON_SCHEMA` still has `domain_hint`, `intent_hint`, a
  top-level `entities` array, `scope_intent`, `broaden_axis`, `reference_positions` and
  `reference_target` (the v1/v2 shape), and no `asks` key at all (only
  `PARSE_OUTPUT_JSON_SCHEMA_V3` adds `answers_open_question` / `anaphora` / `topic_reset`,
  and even that still keeps `domain_hint` etc alongside them).
- `app.services.chatbot.dialogue.intake` does not exist yet.
- `SessionVars` and `Focus` still declare `intent_hint`-shaped legacy fields, and
  `app.services.chatbot.trace_detail` (the merged-from-main module this lane's base
  predates) is not present in this worktree until the S0 merge lands.
"""
from __future__ import annotations

from app.services.chatbot.head.parser import PARSE_OUTPUT_JSON_SCHEMA


class TestParserV3SchemaIsAsksShaped:
    def test_schema_has_asks_and_v3_signals_and_drops_the_legacy_keys(self) -> None:
        properties = PARSE_OUTPUT_JSON_SCHEMA["properties"]

        assert "asks" in properties, (
            f"PARSE_OUTPUT_JSON_SCHEMA has no 'asks' key yet (properties={sorted(properties)})"
        )
        for must_have in ("answers_open_question", "anaphora", "topic_reset"):
            assert must_have in properties, f"missing {must_have!r}"

        for must_not_have in (
            "domain_hint",
            "intent_hint",
            "entities",
            "reference_positions",
            "reference_target",
            "scope_intent",
            "broaden_axis",
        ):
            assert must_not_have not in properties, (
                f"PARSE_OUTPUT_JSON_SCHEMA must not declare {must_not_have!r} any more"
            )

        asks_items = properties["asks"]["items"]["properties"]
        assert set(asks_items) >= {"domain", "entities"}


class TestIntakeFlatten:
    def test_flatten_orders_domains_entities_and_binds_them(self) -> None:
        from app.services.chatbot.dialogue import intake

        entity_a = {
            "raw": "ZZT-A",
            "hint": "product",
            "canonical_code": "ZZT-A",
            "current_message": True,
            "confident": True,
        }
        entity_b = {
            "raw": "ZZT-B",
            "hint": "product",
            "canonical_code": "ZZT-B",
            "current_message": True,
            "confident": True,
        }
        parse = {
            "asks": [
                {"domain": "inventory", "entities": [entity_a]},
                {"domain": "purchase_order", "entities": [entity_a, entity_b]},
            ]
        }

        flat = intake.flatten(parse)

        assert flat["domains"] == ["inventory", "purchase_order"], (
            "domains must keep the dealer's own ask order"
        )
        assert [e["raw"] for e in flat["entities"]] == ["ZZT-A", "ZZT-B"], (
            "entities must be the ORDERED UNION - ZZT-A named twice appears once"
        )
        assert flat["binding"] == {"inventory": [0], "purchase_order": [0, 1]}, (
            f"got binding={flat.get('binding')!r}"
        )


class TestIntentHintIsGone:
    def test_intent_hint_absent_from_state_and_trace(self) -> None:
        from app.services.chatbot import trace_detail
        from app.services.chatbot.contracts import Focus, SessionVars

        assert "intent_hint" not in SessionVars.model_fields, (
            f"SessionVars still declares intent_hint (fields={sorted(SessionVars.model_fields)})"
        )
        assert "intent_hint" not in Focus.model_fields

        detail = trace_detail.compose_trace_detail(
            {
                "trace": [],
                "envelope": {},
                "response": {},
                "status": "done",
            }
        )
        assert "intent_hint" not in str(detail), (
            "no compose_trace_detail output may mention intent_hint"
        )
