"""AC-1021, AC-1026: parser v3 emits `asks[]` (D3), the engine flattens it at intake, and
`intent_hint` is gone from the schema, the state and the trace.

Coordinator ruling for S2 (12 Sep 2026): `asks` and the legacy-key removals live in
`PARSE_OUTPUT_JSON_SCHEMA_V3` ONLY. v1 keeps its 28 keys until the owner promotes (D10) -
retargeted here at `PARSE_OUTPUT_JSON_SCHEMA_V3`, not the v1 schema `test_parser_v3.py`
already covers unchanged.

RED:
- `PARSE_OUTPUT_JSON_SCHEMA_V3` still has `domain_hint`, `intent_hint`, a top-level
  `entities` array, `scope_intent`, `broaden_axis`, `reference_positions` and
  `reference_target` (the v1 shape carried over), and no `asks` key at all.
- `intake.flatten` does not yet read a legacy (v1) emission's `domain_hint` / top-level
  `entities` at all - only `asks[]` - so a v1 emission flattens to empty rather than to
  its own domain and entities.
- `SessionVars` and `Focus` still declare `intent_hint`-shaped legacy fields, and
  `app.services.chatbot.trace_detail`'s `compose_trace_detail` still mentions it somewhere
  in its output.
"""
from __future__ import annotations

from app.services.chatbot.head.parser import PARSE_OUTPUT_JSON_SCHEMA_V3


class TestParserV3SchemaIsAsksShaped:
    def test_schema_has_asks_and_v3_signals_and_drops_the_legacy_keys(self) -> None:
        properties = PARSE_OUTPUT_JSON_SCHEMA_V3["properties"]

        assert "asks" in properties, (
            f"PARSE_OUTPUT_JSON_SCHEMA_V3 has no 'asks' key yet (properties={sorted(properties)})"
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
                f"PARSE_OUTPUT_JSON_SCHEMA_V3 must not declare {must_not_have!r} any more"
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

    def test_flatten_accepts_a_v1_emission(self) -> None:
        """D10: v1 stays promoted until the owner moves the label, so `flatten` has to
        read a legacy emission too - `domain_hint` plus a top-level `entities` array,
        no `asks` at all."""
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
            "message_type": "business_query",
            "domain_hint": "inventory",
            "entities": [entity_a, entity_b],
        }

        flat = intake.flatten(parse)

        assert flat["domains"] == ["inventory"], (
            f"a v1 emission's domain_hint must flatten to domains, got {flat['domains']!r}"
        )
        assert flat["entities"] == [entity_a, entity_b]
        assert flat["binding"] == {}, (
            "v1 carries no per-domain binding - the whole entity list is unbound"
        )


class TestIntentHintIsGone:
    def test_intent_hint_absent_from_state_and_trace(self) -> None:
        from app.services.chatbot import trace_detail
        from app.services.chatbot.contracts import Focus, SessionVars

        assert "intent_hint" not in SessionVars.model_fields, (
            f"SessionVars still declares intent_hint (fields={sorted(SessionVars.model_fields)})"
        )
        assert "intent_hint" not in Focus.model_fields

        from types import SimpleNamespace

        # `compose_trace_detail(row)` reads `row.trace` (an ORM attribute, `ChatbotTurn`
        # in production) - a plain dict has no such attribute and raises AttributeError,
        # which is not this test's subject. `SimpleNamespace` is the lightest stand-in
        # that satisfies the same access.
        detail = trace_detail.compose_trace_detail(SimpleNamespace(trace=[]))
        assert "intent_hint" not in str(detail), (
            "no compose_trace_detail output may mention intent_hint"
        )
