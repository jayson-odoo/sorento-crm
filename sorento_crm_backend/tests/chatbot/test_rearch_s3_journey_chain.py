"""S3 - the journey chain, UAC journey A steps 1 to 6 (PLAN-chatbot-turn-rearch.md
"Journey", `chatbot-turn-rearch-acceptance-criteria.md` steps 1-6, contract line 32).

Every test is RED at collection with `ModuleNotFoundError: No module named
'app.services.chatbot.turn.compose'` - the whole engine A-to-G rewrite this journey
exercises does not exist yet. One test per step, each a `run_turn` call with a
hand-built verdict (the parser stubbed, per `test_engine.py::stub_parser`) and the MCP
tool call stubbed (nothing here reaches :8765 or an LLM). Each asserts the Answer data
(section domains, entity ids, question kind - read off `TurnResult.reply`/`.actions`,
the CURRENT external contract, per the same assumption documented in
`test_rearch_s3_team_pick_and_866.py`) and the five session_vars keys after the turn.

State carries forward turn to turn via the REAL `respond_contacts.session_vars` row
(each step reads what the previous step wrote), so this is a true multi-turn chain,
not six independent fixtures.

Session shape (fix, captain ruling 16 Sep 2026): the five keys (`focus`,
`open_question`, `ideation`, `access_levels`, `contains_flyer`) live at the TOP LEVEL
of `session_vars`, not nested under a `"variables"` wrapper - measured against the
committed S0 code, `app.services.conversation_variables_service.get_for_contact`
returns `_coerce_to_dict(row.session_vars)` verbatim with no `variables` unwrap, and
`SessionVars(extra="forbid")` (`test_rearch_s0_session_slots.py`) declares exactly
those five field names. Every seed/read helper below writes and reads the top level
directly; this file's OWN AC-1532 sibling (`test_rearch_s3_tail.py`) already used the
top-level shape and is unaffected.
"""
from __future__ import annotations

import json

import pytest
from sqlalchemy import text

# Forces collection failure now - see module docstring.
from app.services.chatbot.turn.compose import Answer  # noqa: F401

from tests.chatbot._turn_helpers import entity, verdict
from tests.chatbot.test_engine import CONTACT_ID, _envelope, seeded, stub_access, stub_parser
from tests.chatbot.test_rearch_s3_attribute_first import SORENTO, _link_contact_company, _seed_workspace
from tests.chatbot.test_rearch_s3_roster_from_resolver import (
    PRODUCT_CODES,
    _seed_products,
    _stub_incoming_probe,
)


def _seed(session_factory) -> None:
    _set_session_vars(session_factory, {})


def _seed_wc286_family(session_factory, monkeypatch) -> None:
    """A real SRTWC286-SH family (17 Sep 2026, coder 20's landed change,
    `3c19a8533`): the private test DB holds no WC286 product by default, so step 1's
    bare "wc286" ask found nothing and fell through to an unfiltered fetch attempt
    (the ONE-OPTION typed-token roster this round retires) instead of arming a
    `product_pick` roster of the real resolver's candidates. Reuses the exact seed
    `test_rearch_s3_roster_from_resolver.py` measures its own green result against
    (ten `SRTWC286-SH*` codes) rather than inventing a second one. The roster the
    narrower arms also probes `crm_incoming_stock_list` to stamp each option "has
    incoming"/"no incoming" (contract 28), so that tool needs the same stub.

    Tester 36 (20 Sep 2026, review round): this helper was missing the contact's
    `workspace_id` - `_seed(session_factory)` (`_set_session_vars`'s bare INSERT)
    never sets one, unlike every other S3 helper that seeds a real resolver run
    (`test_rearch_s3_roster_from_resolver.py::_seed_contact`,
    `test_rearch_s3_attribute_first.py::_seed_contact`, both call `_seed_workspace`
    first). Measured: with no `workspace_id`, the real resolver's tier-1/2 lexical
    match finds NOTHING for "wc286" (falls through to tier-3 embedding, which then
    raises `OPENAI_API_KEY is required` and is swallowed) - a TEST HARNESS gap, not
    the "tier-3 has no key so this can never work" architectural limit coder 31's
    round report claimed. With a real `workspace_id` linked, the SAME seeded ten
    `SRTWC286-SH*` products resolve exactly as `test_rearch_s3_roster_from_resolver.py`'s
    own green control does (confirmed directly, ten real candidates, `product_pick`).
    """
    _link_contact_company(session_factory, company_id=SORENTO)
    _seed_products(session_factory, PRODUCT_CODES)
    _stub_incoming_probe(monkeypatch, codes_with_incoming=set())
    workspace_id = _seed_workspace(session_factory)
    db = session_factory()
    db.execute(
        text("UPDATE respond_contacts SET workspace_id = :wid WHERE respond_io_id = :c"),
        {"wid": workspace_id, "c": str(CONTACT_ID)},
    )
    db.commit()


def _set_session_vars(session_factory, state: dict) -> None:
    """Upsert the contact row with session_vars = `state` AT THE TOP LEVEL (the five
    keys directly, no `variables` wrapper - see module docstring). UPSERT rather than
    a bare UPDATE: `session_factory` (`conftest.py`) hands each TEST its own isolated,
    rolled-back transaction, so a step-N-only test (steps 2 to 6 each simulate "as if
    the prior turns already happened" rather than truly running after step 1's own
    test function) needs the row created here too, not merely updated.
    """
    # `respond_io_id` carries no unique constraint (`phone_number` does - measured,
    # `app/models/access.py::RespondContact`), so the upsert conflict target is the
    # phone number, held fixed across every call in this file.
    db = session_factory()
    db.execute(
        text(
            "INSERT INTO respond_contacts (id, respond_io_id, phone_number, session_vars) "
            "VALUES (gen_random_uuid()::text, :cid, :phone, CAST(:sv AS jsonb)) "
            "ON CONFLICT (phone_number) DO UPDATE SET session_vars = CAST(:sv AS jsonb)"
        ),
        {"cid": str(CONTACT_ID), "phone": "+60000000006", "sv": json.dumps(state)},
    )
    db.commit()


def _session_vars(session_factory) -> dict:
    row = session_factory().execute(
        text("SELECT session_vars FROM respond_contacts WHERE respond_io_id = :c"),
        {"c": str(CONTACT_ID)},
    ).first()
    return row.session_vars or {}


def _turn(session_factory, stub_parser, v: dict, *, message_id: str):
    from app.services.chatbot import engine as engine_mod

    stub_parser(v)
    e = _envelope()
    e.message["message"]["messageId"] = message_id
    e.message["message"]["message"]["text"] = message_id
    return engine_mod.run_turn(e, session_factory=session_factory)


class TestJourneyChain:
    def test_step_1_incoming_wc286_roster_one_question_open(
        self, session_factory, stub_parser, stub_access, monkeypatch
    ) -> None:
        _seed(session_factory)
        _seed_wc286_family(session_factory, monkeypatch)
        stub_access()

        # `confident=False` (a bare family word, not a full code - the parser's own
        # "I saw a token, not sure it names a real thing" signal, `turn/apply.py::
        # _did_you_mean`'s own docstring): with the family seeded, `_did_you_mean`
        # defers to the narrower once the resolver has real candidates for the kind,
        # so the roster it arms lists the resolver's ten matches, not the typed word
        # back at the customer. Measured: `confident=True` here still falls through to
        # an unresolved-token escalate offer (`team_pick`) on this head - a settled
        # code is not what "wc286" is.
        v = verdict(
            domain_hint="incoming",
            intent_hint="check_incoming",
            entities=[entity("wc286", hint="product", confident=False)],
        )
        result = _turn(session_factory, stub_parser, v, message_id="ZZT-journey-1")

        # T1 (coder 7 cluster report, AC-1591): amended to the corpus name -
        # `product_pick` is not in `contracts.BRANCH_KINDS` at all.
        assert result.branch_kind == "business_query", result.branch_kind
        sv = _session_vars(session_factory)
        assert sv.get("open_question") is not None, sv
        open_question = sv["open_question"]
        assert open_question.get("kind") == "product_pick", open_question

        # Tester 36 (review round, 20 Sep 2026): pin what this test's own docstring
        # claims - a REAL roster of the resolver's ten candidates, never the
        # retired one-option typed-token echo (AC-1691/AC-1692, R6). `_seed_wc286_
        # family` now links the contact's `workspace_id`, so the real resolver
        # matches all ten seeded `SRTWC286-SH*` products.
        options = open_question.get("options") or []
        assert len(options) >= 2, (
            f"a require-specific roster must never be a single option: {open_question!r}"
        )
        labels = {opt.get("label") for opt in options}
        assert "wc286" not in {str(label).strip().lower() for label in labels}, (
            f"the roster must list the resolver's real candidate codes, never the "
            f"customer's own typed word back at them: {open_question!r}"
        )
        assert labels == set(PRODUCT_CODES), (
            f"the roster must be the full real family the resolver actually "
            f"matched: {open_question!r}"
        )

    def test_step_2_pick_8_roster_stays_alive_incoming_renders(
        self, session_factory, stub_parser, stub_access
    ) -> None:
        _set_session_vars(
            session_factory,
            {
                "open_question": {
                    "kind": "product_pick",
                    "options": [
                        {"position": i, "label": f"WC286-{i}", "uuid": f"uuid-{i}"} for i in range(1, 11)
                    ],
                    # `payload.domain` is what a bare "8" answer returns to - step 1's
                    # engine-armed roster always carries it (measured: run step 1's
                    # own turn and read the stored `open_question` back). A hand-built
                    # roster that omits it has no domain for the pick to render into.
                    "payload": {"domain": "incoming"},
                }
            },
        )
        stub_access()

        v = verdict(answers_open_question={"resolved": True, "picks": [8], "answer": "8"}, reference_positions=[8])
        result = _turn(session_factory, stub_parser, v, message_id="ZZT-journey-2")

        text = (result.reply or {}).get("text", "")
        assert "incoming" in text.lower() or result.branch_kind == "business_query", (result.branch_kind, text)
        sv = _session_vars(session_factory)
        assert sv.get("open_question") is not None, (
            "product_pick is a ROSTER kind (contract 36) - it must stay alive (sticky) "
            f"after its own pick: {sv!r}"
        )

    def test_step_3_domain_switch_product_kept_not_reasked(
        self, session_factory, stub_parser, stub_access
    ) -> None:
        _set_session_vars(
            session_factory,
            {
                "focus": {"products": [{"raw": "WC286-8", "canonical_code": "WC286-8"}]},
                "open_question": None,
            },
        )
        stub_access()

        v = verdict(domain_hint="inventory")
        result = _turn(session_factory, stub_parser, v, message_id="ZZT-journey-3")

        assert result.branch_kind != "clarify_menu" or "product" not in str(
            (result.reply or {}).get("quick_replies") or ""
        ).lower(), "the product must not be re-asked on a domain switch (contract 35)"
        sv = _session_vars(session_factory)
        assert sv.get("focus", {}).get("products"), sv

    def test_step_4_outstanding_do_customer_must_narrow_one_no_document_question(
        self, session_factory, stub_parser, stub_access
    ) -> None:
        _set_session_vars(session_factory, {})
        stub_access()

        v = verdict(
            domain_hint="order",
            document=["DO"],
            status="outstanding",
            entities=[entity("chin chun", hint="customer", confident=True)],
        )
        result = _turn(session_factory, stub_parser, v, message_id="ZZT-journey-4")

        text = (result.reply or {}).get("text", "") + json.dumps((result.reply or {}).get("quick_replies") or [])
        assert "so, do or both" not in text.lower(), (
            "DO was named explicitly - the SO/DO/both scope question must not be asked "
            f"(D6, contract 38): {text!r}"
        )
        sv = _session_vars(session_factory)
        # Re-pinned 17 Sep 2026 (tester): superseded by the captain's 16 Sep 2026 ruling
        # in `turn/narrow.py::_narrow` ("the narrower must never re-ask for an entity
        # the conversation already settled... a SINGLE bare name with nothing else to
        # compare it against is handed to the RESOLVER this turn instead of guessed at
        # here... reaching HERE with one un-uuid'd candidate means there was no resolver
        # answer for it at all this turn, so it passes through, deferred, rather than an
        # ask manufactured from a name alone"). No real "chin chun" customer row is
        # seeded in this file, so the real resolver (Tier 1/2 DB lookup, measured to run
        # here) finds zero candidates for it - exactly the single-bare-name case the
        # ruling says passes through undecided, not the several-distinct-names case that
        # still asks. `must_narrow_one` no longer arms a customer_pick from an unresolved
        # name alone.
        assert sv.get("open_question") is None, (
            f"a single unresolved customer name passes through deferred, per the 16 Sep "
            f"2026 ruling - it must not manufacture a customer_pick ask: {sv.get('open_question')!r}"
        )

    def test_step_5_pick_1_family_becomes_customer_detail_question_open(
        self, session_factory, stub_parser, stub_access
    ) -> None:
        _set_session_vars(
            session_factory,
            {
                "focus": {"document": ["DO"], "status": "outstanding"},
                "open_question": {
                    "kind": "customer_pick",
                    "options": [
                        {
                            "position": 1,
                            "label": "Chin Chun (family)",
                            "uuids": ["led-1", "led-2"],
                            "entity_type": "customer",
                        }
                    ],
                },
            },
        )
        stub_access()

        v = verdict(answers_open_question={"resolved": True, "picks": [1], "answer": "1"}, reference_positions=[1])
        result = _turn(session_factory, stub_parser, v, message_id="ZZT-journey-5")

        sv = _session_vars(session_factory)
        assert sv.get("focus", {}).get("customers"), (
            f"the whole ledger family must become the customer on pick 1: {sv!r}"
        )
        assert sv.get("open_question") is not None, (
            "the detail question (outstanding_detail) is the one open question after "
            f"the family pick: {sv!r}"
        )

    def test_step_6_exclusive_product_only_customer_family_survives(
        self, session_factory, stub_parser, stub_access
    ) -> None:
        _set_session_vars(
            session_factory,
            {
                "focus": {
                    "document": ["DO"],
                    "status": "outstanding",
                    "customers": [{"raw": "chin chun", "canonical_code": "led-1"}, {"raw": "chin chun", "canonical_code": "led-2"}],
                    "products": [{"raw": "OLD-PRODUCT", "canonical_code": "OLD-PRODUCT"}],
                },
                "open_question": None,
            },
        )
        stub_access()

        # 17 Sep 2026 ruling (`turn/decide.py::_subject_reading`'s domain_in_message
        # table): `scope_exclusive` is retired - "only BRW" (a message that names an
        # entity but no domain/status word of its own) is a REFINE row
        # (`domain_in_message: False` + entities), which combines across kinds and
        # replaces only the kind it names. `scope_exclusive="product"` (a STRING; the
        # declared schema type is boolean) was never actually read here even before
        # the retirement - this test passed via the SAME fallback (`names_its_own_
        # entity`, `decision.starts_fresh` False) the REFINE row now names outright,
        # so this re-pin makes the verdict match what the test was always measuring.
        v = verdict(
            domain_in_message=False,
            entities=[entity("SRT6536-DIY", hint="product", confident=True)],
        )
        result = _turn(session_factory, stub_parser, v, message_id="ZZT-journey-6")

        sv = _session_vars(session_factory)
        customers_after = sv.get("focus", {}).get("customers") or []
        assert len(customers_after) == 2, (
            "the customer FAMILY must survive a REFINE that names only the product "
            f"axis (contract 32 + tonight's owner defect): {customers_after!r}"
        )
        products_after = sv.get("focus", {}).get("products") or []
        codes = [p.get("canonical_code") for p in products_after]
        assert codes == ["SRT6536-DIY"], (
            f"a REFINE must replace only the kind it names (product): {codes!r}"
        )
