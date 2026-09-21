"""S3 - a `narrow_to_code` ask lists the REAL resolver's candidates, not the raw
word the customer typed (contract 28, PLAN-chatbot-turn-rearch.md "Journey" step 1).

Measured today: an entity the parser could not place (`confident: false`) never
reaches the resolver at all. `app/services/chatbot/turn/apply.py::_did_you_mean` runs
BEFORE the narrower (`_narrow_and_plan`) and short-circuits the whole turn with its own
`product_pick` roster built directly off the UNSURE entity's raw text -
`app/services/chatbot/turn/apply.py`:

    options = [
        {
            "position": i + 1,
            "label": e.get("raw"),
            "uuid": e.get("canonical_code") or e.get("raw"),
            ...
        }
        for i, e in enumerate(unsure)
    ]

One entity in, one option out, labelled "wc286" - never the ten real product codes a
customer meant by it, and `pending_ask()` is called there with no `payload` at all, so
`payload.domain` (what the domain the answer returns to, contract 121) is also missing.
This file is RED at collection for neither of those reasons - it never touches
`_did_you_mean`'s internals - it runs `engine.run_turn` end to end and asserts the
CORRECT contract; today's `_did_you_mean` short-circuit is what makes it fail, for the
measured reason above (one option, labelled "wc286", no `payload`), not an import error
or a fixture bug.

Seams (coordinator's brief, 16 Sep 2026): the RESOLVER is real (no `resolve_entity`
stub, no injected candidate list) - ten products are seeded so the real matcher has
something to find. TOOLS are stubbed: the incoming picker's probe
(`crm_incoming_stock_list`) is answered by monkeypatching `MCPRuntimeClient.call_tool`
at the network boundary (`app.services.ai_assistant_service.MCPRuntimeClient`, the same
seam `_probe`/`_mcp_probe` construct in `app/services/chatbot/lanes/business/
services.py`), never a resolver stub.

Policy comes from the blank-schema FALLBACK (`load_policy`'s own documented behaviour,
`app/services/chatbot/turn/policy.py`: "a table that exists but holds no rows falls
back to policy_rows.py's seed" - the SAME `incoming` domain row
(`narrowing={"product": "narrow_to_code"}`) a migrated database's `chatbot_domains`
carries), so `session_factory` (blank scratch schema) is enough; `pg_session`/the real
migrated DB is not needed for this file.
"""
from __future__ import annotations

import json
import uuid
from typing import Any

import pytest

from tests.chatbot._turn_helpers import entity, verdict
from tests.chatbot.test_engine import CONTACT_ID, _envelope, stub_access, stub_parser
from tests.chatbot.test_rearch_s3_attribute_first import SORENTO, _link_contact_company, _seed_workspace

# The ten codes the coordinator named, all sharing the "SRTWC286-SH" base the customer's
# bare "wc286" should resolve against.
_SUFFIXES = ["-200", "-P", "-PP", "", "-UF", "-NEW-150", "-150", "-NEW-P", "-NEW-200", "-NEW"]
_BASE = "SRTWC286-SH"
PRODUCT_CODES = [f"{_BASE}{suffix}" for suffix in _SUFFIXES]

# Three of the ten are stubbed as having incoming stock (contract 28's "- has incoming" /
# "- no incoming" stamps need both a positive and a negative case to be worth asserting).
CODES_WITH_INCOMING = {PRODUCT_CODES[0], PRODUCT_CODES[3], PRODUCT_CODES[6]}


def _uid() -> str:
    return str(uuid.uuid4())


def _db(session_factory, *, scope: frozenset[str] = frozenset({SORENTO})):
    """Same reasoning as `test_rearch_s3_attribute_first.py::_db`: stamp `company_scope`
    explicitly rather than leave it to the lazily-firing `after_begin` default, which
    races across the several `session_factory()` calls one seed chain needs."""
    db = session_factory()
    db.info["company_scope"] = scope
    return db


def _seed_contact(session_factory, *, phone: str) -> None:
    from sqlalchemy import text

    workspace_id = _seed_workspace(session_factory)
    db = _db(session_factory)
    db.execute(
        text(
            "INSERT INTO respond_contacts (id, respond_io_id, phone_number, session_vars, workspace_id) "
            "VALUES (gen_random_uuid()::text, :cid, :phone, CAST(:sv AS jsonb), :wid)"
        ),
        {"cid": str(CONTACT_ID), "phone": phone, "sv": json.dumps({}), "wid": workspace_id},
    )
    db.commit()


def _seed_products(session_factory, codes: list[str]) -> None:
    from app.models.product import Product, ProductCategory, UnitOfMeasure

    db = _db(session_factory)
    cat = ProductCategory(
        id=_uid(),
        category_code="ZZTC-wc286",
        category_name="ZZT WC286",
        class_label="wc286",
        search_synonyms=[],
    )
    uom = UnitOfMeasure(id=_uid(), uom_code="ZZTU-wc286", uom_name="ZZT uom")
    db.add_all([cat, uom])
    db.flush()
    for code in codes:
        db.add(
            Product(
                id=_uid(),
                product_code=code,
                product_name=f"ZZT {code}",
                category_id=cat.id,
                base_uom_id=uom.id,
                list_price=1,
            )
        )
    db.commit()


def _stub_incoming_probe(monkeypatch, *, codes_with_incoming: set[str]) -> None:
    """Answer `crm_incoming_stock_list` (the incoming picker's probe tool) with one
    row per code that has incoming, `{"title": <code>}` - the shape
    `pickers.annotate_incoming` reads (`_probe_rows` -> `answers`, `title` per row).
    Every OTHER tool name gets an empty `{"answers": []}` so nothing this turn does not
    ask for reaches a real network call.
    """
    from app.services.ai_assistant_service import MCPRuntimeClient

    def fake_call_tool(self, name: str, arguments: dict[str, Any]) -> str:
        if name == "crm_incoming_stock_list":
            return json.dumps({"answers": [{"title": code} for code in codes_with_incoming]})
        return json.dumps({"answers": []})

    monkeypatch.setattr(MCPRuntimeClient, "call_tool", fake_call_tool)


class TestRosterListsResolverCandidates:
    def test_narrow_to_code_ask_lists_the_resolvers_candidates(
        self, session_factory, stub_parser, stub_access, monkeypatch
    ) -> None:
        _seed_contact(session_factory, phone="+60000000030")
        _link_contact_company(session_factory, company_id=SORENTO)
        _seed_products(session_factory, PRODUCT_CODES)
        _stub_incoming_probe(monkeypatch, codes_with_incoming=CODES_WITH_INCOMING)

        v = verdict(
            domain_hint="incoming",
            intent_hint="check_incoming",
            entities=[entity("wc286", hint="product", confident=False)],
        )
        stub_parser(v)
        stub_access()

        from app.services.chatbot import engine as engine_mod

        result = engine_mod.run_turn(_envelope(), session_factory=session_factory)

        db = session_factory()
        from sqlalchemy import text as sql_text

        row = db.execute(
            sql_text("SELECT session_vars FROM respond_contacts WHERE respond_io_id = :c"),
            {"c": str(CONTACT_ID)},
        ).first()
        open_question = (row.session_vars or {}).get("open_question") if row else None

        assert open_question is not None, "no open_question was stored"
        assert open_question.get("kind") == "product_pick", open_question

        options = open_question.get("options") or []
        assert len(options) == 10, (
            f"expected exactly ten roster options (one per seeded candidate), got "
            f"{len(options)}: {options!r}"
        )

        labels = {o.get("label") for o in options}
        assert labels == set(PRODUCT_CODES), (
            "roster labels must be the RESOLVER's candidate codes, not the raw word "
            f"the customer typed: {labels!r}"
        )

        for option in options:
            assert option.get("uuid"), f"option has no uuid: {option!r}"
            assert option.get("uuids"), f"option has no uuids: {option!r}"

        assert (open_question.get("payload") or {}).get("domain") == "incoming", (
            f"payload.domain must be 'incoming' - what a bare number answer returns "
            f"to (contract 121): {open_question!r}"
        )

        text = (result.reply or {}).get("text", "")
        for code in CODES_WITH_INCOMING:
            assert f"{code} - has incoming" in text, (
                f"{code!r} must be stamped '- has incoming' (contract 28): {text!r}"
            )
        for code in set(PRODUCT_CODES) - CODES_WITH_INCOMING:
            assert f"{code} - no incoming" in text, (
                f"{code!r} must be stamped '- no incoming' (contract 28): {text!r}"
            )
