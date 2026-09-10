"""Phase 2 RED tests for the attribute-first-asks lane, slice S1 - work items B1, B2,
C4, E1, F1.

`documentation/plans/chatbot/attribute-first-asks-acceptance-criteria.md` AC-1303,
AC-1304, AC-1315, AC-1319, AC-1326.
`documentation/plans/chatbot/PLAN-attribute-first-asks.md` - Shape, Work items B1/B2/C4/E1/F1.

Written BEFORE `app/services/chatbot/lanes/business/predicate.py` exists. An `ImportError`
naming that module is the expected red reason for the tests that import it directly;
`resolve_gate.py` / `gate.py` / `fetch.py` / `answer.py` are ported and DO exist today, so
tests against them fail on a wrong VALUE (missing dict key, wrong count, wrong text) rather
than an import - each test's own docstring says which.

Every module is imported LOCALLY inside its own test (not at file scope), so one missing
module can only fail the tests that actually depend on it, never the whole file's collection.
"""
from __future__ import annotations

import uuid
from typing import Any

import pytest


# --------------------------------------------------------------------------- #
# B1 - AC-1303: derive_require is a pure map off the parser's own output.       #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "parser_output, expected",
    [
        ({"intent_hint": "check_stock"}, {"stock": True}),
        ({"intent_hint": "check_incoming"}, {"incoming": True}),
        ({"intent_hint": "check_promotion"}, {"promotion": True}),
        (
            {
                "intent_hint": "check_product_attachment",
                "entities": [{"hint": "attachment_type", "raw": "cert"}],
            },
            {"certificate": True},
        ),
        (
            {
                "intent_hint": "check_product_attachment",
                "entities": [{"hint": "attachment_type", "raw": "photo"}],
            },
            {"attachment_type": "photo"},
        ),
        ({"intent_hint": "check_order"}, None),
        ({"intent_hint": None}, None),
    ],
)
def test_derive_require_maps_intents_and_entity_hints(parser_output, expected):
    from app.services.chatbot.lanes.business.predicate import derive_require

    assert derive_require(parser_output) == expected


# --------------------------------------------------------------------------- #
# B2 - AC-1304 / AC-1322: resolve_entity_body gains require + predicate_words ONLY   #
# when derive_require returns something, every other key stays byte-identical. #
# --------------------------------------------------------------------------- #


def _ctx_for_intent(intent_hint: str | None) -> dict[str, Any]:
    """Two ctx dicts identical except `intent_hint` - domain_hint is held CONSTANT so
    the "every other key equal" assertion is meaningful (a varying domain would also
    vary `body["domain"]`, which is not what this test is about)."""
    return {
        "text": {"message": {"message": {"text": "check"}}},
        "contact": {"id": "1"},
        "parse": {
            "output": {
                "message_type": "business_query",
                "intent_hint": intent_hint,
                "domain_hint": "inventory",
                "match_mode": "or",
                "access_levels": [],
                "entities": [{"raw": "basin", "hint": "product"}],
            }
        },
    }


def test_resolve_entity_body_adds_require_and_predicate_words_only_when_derived():
    from app.services.chatbot.lanes.business.resolve_gate import resolve_entity_body

    body_stock = resolve_entity_body(_ctx_for_intent("check_stock"))
    body_order = resolve_entity_body(_ctx_for_intent("check_order"))

    assert body_stock.get("require") == {"stock": True}
    assert body_stock.get("predicate_words") == ["stock"]
    assert "require" not in body_order
    assert "predicate_words" not in body_order

    keys = (set(body_stock) | set(body_order)) - {"require", "predicate_words"}
    for key in keys:
        assert body_stock.get(key) == body_order.get(key), key


# --------------------------------------------------------------------------- #
# C4 - AC-1326: a qualifying predicate bypasses the ambiguity picker AND the    #
# product_attachment "subject did not resolve" block.                          #
# --------------------------------------------------------------------------- #


def _predicate_world() -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    """Three `spec_search`-tier product matches for an unresolved raw ("water tap"),
    plus a qualifying `predicate` block - the exact shape AC-1326 describes."""
    uuids = [str(uuid.uuid4()) for _ in range(3)]
    matches = [
        {
            "uuid": u,
            "entity_type": "product",
            "canonical_code": f"ZZT-BIDET-{i}",
            "match_tier": "spec_search",
        }
        for i, u in enumerate(uuids)
    ]
    resolver = {
        "resolutions": [{"token": "water tap", "resolved": False, "matches": matches}],
        "unresolved_tokens": ["water tap"],
        "predicate": {
            "qualifying_total": 3,
            "truncated": False,
            "unrecognized_terms": [],
            "require": {"certificate": True},
        },
    }
    parser = {
        "domain_hint": "product_attachment",
        "entities": [
            {"hint": "product", "raw": "water tap"},
            {"hint": "attachment_type", "raw": "cert"},
        ],
    }
    return resolver, parser, uuids


def test_gate_bypasses_ambiguity_and_subject_block_when_predicate_present():
    from app.services.chatbot.lanes.business.gate import run_gate

    resolver, parser, uuids = _predicate_world()

    out = run_gate(dict(resolver), parser=parser, resolver=resolver)

    assert out["require_specific"] is False, out.get("gate_reason")
    assert out["gate_passed"] is True, out.get("gate_reason")
    product_entities = [e for e in out["compatible_entities"] if e["entity_type"] == "product"]
    assert {e["uuid"] for e in product_entities} == set(uuids)


# --------------------------------------------------------------------------- #
# E1 - AC-1315: a HAS turn's fetch passes every qualifying id to the SAME domain #
# tool, limit=5.                                                                #
# --------------------------------------------------------------------------- #


def test_has_turn_fetch_passes_all_ids_to_the_domain_tool_with_limit_5():
    from app.services.chatbot.lanes.business import fetch
    from app.services.chatbot.lanes.business.gate import run_gate

    resolver, parser, uuids = _predicate_world()
    gate_out = run_gate(dict(resolver), parser=parser, resolver=resolver)

    args = fetch.entity_ids_transformer(
        {
            "entities": gate_out["compatible_entities"],
            "tool": "crm_master_product_attachments_list",
            "semantic_input": {"contact_id": "1", "space_id": "364817"},
            "predicate": resolver["predicate"],
        }
    )

    assert set(args.get("product_ids") or []) == set(uuids)
    assert args.get("limit") == 5


# --------------------------------------------------------------------------- #
# F1 - AC-1319: qualifying_total=0 enters the existing miss flow, naming the    #
# described set and the predicate.                                             #
# --------------------------------------------------------------------------- #


def test_zero_qualifying_enters_the_existing_miss_flow_naming_the_set():
    """Full lane run (the `_run_lane` pattern from `tests/chatbot/test_warehouse_entity.py`,
    reproduced locally rather than imported across files): three products named
    "* BIDET", none certified, real resolver + real gate, then the render function
    `not_found_error_message` (`answer.py`) named at PLAN work item F1.

    Today `derive_require` is not wired into `resolve_entity_body` at all, so no
    `require` ever reaches the resolver for this turn, the certificate leg never runs,
    and the rendered text carries none of the predicate-shaped copy this AC demands -
    the right red reason for a full-pipeline gap, not a single missing function.
    """
    from app.models.base import set_company_scope
    from app.models.company import Company
    from app.models.product import Product, ProductCategory, UnitOfMeasure
    from app.services.chatbot.lanes.business import resolve_gate
    from app.services.chatbot.lanes.business.answer import not_found_error_message
    from app.services.chatbot.lanes.business.services import ResolveGateServices
    from app.api.v1.system.references import ResolveReferenceRequest, resolve_reference_post
    from app.config import settings
    from tests._pg_fixture import blank_session, unique_code

    codes = ["ACC-BIDET", "CAB-BIDET", "SRT-BIDET"]

    with blank_session() as db:
        company = Company(id=str(uuid.uuid4()), code=unique_code("ZZTBD")[:50], name=unique_code("ZZTBD"))
        db.add(company)
        db.flush()
        category = ProductCategory(
            id=str(uuid.uuid4()),
            category_code=unique_code("CAT")[:50],
            category_name="ZZT bidet category",
            company_id=company.id,
        )
        uom = UnitOfMeasure(
            id=str(uuid.uuid4()), uom_code=unique_code("UOM")[:20], uom_name="Each", company_id=company.id
        )
        db.add_all([category, uom])
        db.flush()

        for code in codes:
            db.add(
                Product(
                    id=str(uuid.uuid4()),
                    product_code=code,
                    product_name=code,
                    description="BIDET SPRAY SET",
                    category_id=category.id,
                    base_uom_id=uom.id,
                    list_price=10,
                    is_active=True,
                    company_id=company.id,
                )
            )
        db.commit()

        set_company_scope(db, frozenset({company.id}))

        def resolve_entity(body: dict[str, Any]) -> dict[str, Any]:
            payload = {**body, "spec_fallback": False, "understand_phrase": False}
            principal = {"id": getattr(settings, "external_api_key_act_as_user_id", None)}
            return resolve_reference_post(
                ResolveReferenceRequest(**payload), current_user=principal, db=db
            )

        services = ResolveGateServices(
            access_types=lambda **_: [], resolve_entity=resolve_entity, probe=lambda **_: None
        )

        ctx = {
            "text": {"message": {"message": {"text": "which sorento bidet has cert"}}},
            "contact": {"id": "999"},
            "parse": {
                "output": {
                    "message_type": "business_query",
                    "intent_hint": "check_product_attachment",
                    "domain_hint": "product_attachment",
                    "match_mode": "or",
                    "access_levels": [],
                    "entities": [
                        {"raw": "bidet", "hint": "product"},
                        {"raw": "cert", "hint": "attachment_type"},
                    ],
                }
            },
        }

        out = resolve_gate.run(ctx, "resolve", {}, services=services, space_id="364817")
        parser = ctx["parse"]["output"]
        resolved = out.get("resolved") or {}
        gate = out.get("gate") or {}

        msg = not_found_error_message({}, parser=parser, resolved=resolved, gate=gate)
        text = (msg.get("escalate_message") or "").strip()

    assert text.startswith("Couldn't find"), text
    assert "certificate" in text.lower(), text
    for code in codes:
        assert code in text, text
    assert "did you mean" in text.lower() or "escalate" in text.lower(), text
