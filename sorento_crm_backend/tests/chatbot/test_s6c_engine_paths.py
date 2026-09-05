"""S6c fix-round follow-up (commits `a9baafd47..1a0419e19`): four engine-level paths
that round opened, driven end to end through `engine.run_turn` against the Postgres
blank-schema fixture. No mocked-away business logic beyond the injectable seams
(`ResolveGateServices` / `FetchServices` / `AnswerServices`) - MCP, the embedding
provider and the LLM are the only things stubbed; `run_until_exit` / `run_fetch` /
`complete_answer` all run for real, including the REAL `engine.complete_turn` tail
(compile-state / compose), which none of `test_s6c_answer_lane.py`'s own engine-wiring
tests exercise (they stub either `run_fetch` and `complete_answer` together, or
`complete_turn` itself). Running that tail for real is what this file is for.

Every assertion cites the AC / H id it grades in its own docstring or test name. No
regex over customer text.
"""
from __future__ import annotations

from typing import Any

import pytest

from app.services.chatbot.lanes.business.services import (
    AnswerServices,
    FetchServices,
    ResolveGateServices,
)
from tests.chatbot import _corpus
from tests.chatbot.test_engine import _envelope, _parser_output, seeded, stub_access, stub_parser
from tests.chatbot.test_s6c_answer_lane import (
    TestChatbotCompletedLanesEngineWiring as _EngineWiring,
)
from tests.chatbot.test_s6c_answer_lane import _replay, _s6c_full_corpus


def _no_probe_answer_services() -> AnswerServices:
    """A safe default: none of the four paths below is expected to reach the did-you-
    mean probe or the family fetch (each either has nothing to resolve or exits before
    the miss lane's probes run), so a call here is a signal the path grew a new
    dependency, not a silent success."""

    def _mcp_probe(name: str, args: dict) -> Any:
        return {"answers": [], "has_result": False}

    def _family_fetch(query: str) -> Any:
        return {"data": []}

    return AnswerServices(mcp_probe=_mcp_probe, family_fetch=_family_fetch)


def _assert_crm_completed_send(result) -> None:
    """The shape every CRM-completed business turn must carry (D9, `compose_send_action`):
    `status == "done"`, ONE `send_message` action with non-empty text, and
    `quick_replies` / `dry_run` in the types the sender expects - never the bare list
    `_run_casual_lane` used before this lane composed its own send.

    A `send_attachments` action MAY follow it, and only follow it: the tail builds the
    pair through `engine._send_actions`, the same builder the canned lanes use, so a
    business answer whose `central-exchange` carried files hands the caller the send for
    them instead of dropping them. The order is n8n's own - the text explains the files.
    """
    assert result.status == "done", result.error
    kinds = [a["kind"] for a in result.actions]
    assert kinds in (["send_message"], ["send_message", "send_attachments"]), kinds
    action = result.actions[0]
    assert isinstance(action.get("text"), str) and action["text"]
    assert action.get("quick_replies") is None or isinstance(action["quick_replies"], str)
    assert isinstance(action.get("dry_run"), bool)
    if len(result.actions) == 2:
        assert result.actions[1].get("attachments_src") is not None
        assert isinstance(result.actions[1].get("dry_run"), bool)


def _srtwc8517_resolved_bundle() -> ResolveGateServices:
    """A `ResolveGateServices` bundle that actually resolves the product the parser
    named, unlike `TestChatbotCompletedLanesEngineWiring._stub_bundle` (whose
    `resolve_entity` always returns empty regardless of input) - needed here because a
    domain like `inventory` requires a scoping entity (`gate.ALLOWS_EMPTY["inventory"]
    is False`), so an always-empty resolver can only ever reach `"not_found"`, never
    `"continue"`, for it."""

    def _resolve_entity(body: dict[str, Any]) -> dict[str, Any]:
        return {
            "tokens": ["SRTWC8517"],
            "resolutions": [
                {
                    "raw": "SRTWC8517",
                    "matches": [
                        {
                            "uuid": "11111111-1111-1111-1111-111111111111",
                            "entity_type": "product",
                            "canonical_code": "SRTWC8517",
                        }
                    ],
                }
            ],
            "unresolved_tokens": [],
        }

    return ResolveGateServices(
        access_types=lambda **_: [{"name": "Sorento Dealer"}],
        resolve_entity=_resolve_entity,
        probe=lambda **_: None,
    )


# --------------------------------------------------------------------------- #
# 1. AC-604 / H11: fetch finds no tool (tool-filter returns zero tools), both switch
#    positions, through the REAL `run_until_exit` + `run_fetch` - only `embed` /
#    `tool_search` / `mcp_call` are stubbed, so `select_tool` and `tool_filter` (the
#    functions H11 is actually about) run unmocked.
# --------------------------------------------------------------------------- #


class TestH11ZeroToolsIsAnOutcomeEndToEnd:
    """`fetch.tool_filter([])` -> `outcome == "not_found"`: the same error fragment
    `TestAC604FetchErrorIsAnOutcomeNotAnEmptyTurn` grades with `run_fetch` stubbed
    wholesale, reached here by actually running `select_tool` / `tool_filter`."""

    @staticmethod
    def _no_tool_fetch_services() -> FetchServices:
        def _mcp_call(name: str, args: dict) -> Any:
            raise AssertionError(
                "no MCP tool matched - `tool_filter` must return before any tool is called"
            )

        return FetchServices(
            embed=lambda query: [0.0, 0.0, 0.0],
            tool_search=lambda embedding, *, query, domain: [],
            mcp_call=_mcp_call,
        )

    @classmethod
    def _wire(cls, engine_mod, monkeypatch) -> None:
        from app.config import settings

        monkeypatch.setattr(settings, "chatbot_business_lane_enabled", True)
        bundle = _EngineWiring._stub_bundle([])
        monkeypatch.setattr(
            engine_mod.business_services,
            "production_services",
            lambda db, *, space_id=None: bundle,
        )
        monkeypatch.setattr(
            engine_mod.business_services,
            "fetch_services",
            lambda db: cls._no_tool_fetch_services(),
        )
        monkeypatch.setattr(
            engine_mod.business_services,
            "answer_services_for",
            lambda session_factory: _no_probe_answer_services(),
        )

    def test_with_the_lane_on_the_crm_answers_in_crm_not_found_ac604_h11(
        self, session_factory, seeded, stub_parser, stub_access, system_settings_row, monkeypatch
    ) -> None:
        """`chatbot_completed_lanes = ["business_query"]`: `delegate` is null, the turn
        closes `done`, and the reply is the miss lane's in-CRM `not_found` answer -
        never n8n's, because n8n's Switch output is exactly what AC-610 removes once
        this is proven (AC-604). `actions` carries the ONE `send_message` the customer
        actually receives, with `quick_replies` either a string or `None` and `dry_run`
        a real boolean."""
        from app.models.user import SystemSetting
        from app.services.chatbot import engine as engine_mod

        db = session_factory()
        setting = db.query(SystemSetting).filter(SystemSetting.id == system_settings_row.id).one()
        setting.chatbot_completed_lanes = ["business_query"]
        db.commit()

        self._wire(engine_mod, monkeypatch)
        stub_parser(_parser_output(domain_hint="forms", entities=[], user_goal="checking a form"))
        stub_access()

        result = engine_mod.run_turn(_envelope(), session_factory=session_factory)

        assert result.branch_kind == "business_query"
        assert result.delegate is None, "H11: zero tools must not fall back to a delegate"
        assert isinstance(result.reply.get("text"), str) and result.reply["text"], (
            "the customer must read something rather than the empty turn H11 names"
        )
        _assert_crm_completed_send(result)

    def test_with_the_lane_off_it_delegates_business_query_h11(
        self, session_factory, seeded, stub_parser, stub_access, system_settings_row, monkeypatch
    ) -> None:
        """Default `chatbot_completed_lanes = []`: n8n still answers this turn even
        though the CRM's own resolve+gate and fetch steps ran (S6a/S6b are shadow
        lanes) - the turn must stop at `delegated` / `looked_up`, never `done`."""
        from app.services.chatbot import engine as engine_mod

        assert (system_settings_row.chatbot_completed_lanes or []) == []
        self._wire(engine_mod, monkeypatch)
        stub_parser(_parser_output(domain_hint="forms", entities=[], user_goal="checking a form"))
        stub_access()

        result = engine_mod.run_turn(_envelope(), session_factory=session_factory)

        assert result.branch_kind == "business_query"
        assert result.delegate == "business_query"
        assert result.stage == "looked_up"
        assert result.status == "delegated"


# --------------------------------------------------------------------------- #
# 2. R1: `stock_denied` with `chatbot_stock_denial_enabled` on, through the real
#    `route.decide` + `run_until_exit` + `complete_answer` (only `run_fetch` is
#    stubbed, to hand the answer half an MCP-shaped result without a network call) -
#    the composed reply is the demand-quantity verdict sentence (`answer.py`'s
#    `validator`, `__init__.py:85-86`'s stamp).
# --------------------------------------------------------------------------- #


class TestR1DemandQuantityAnswerEndToEnd:
    _ANSWERS = {
        "answers": [
            {"product": "SRTWC8517", "stock_qty": 2},
            {"product": "SRTWC8517", "stock_qty": 1},
        ],
        "response": "Warehouse A: 2\nWarehouse B: 1",
        "has_result": True,
    }

    @staticmethod
    def _envelope_for_stock_check() -> Any:
        return _envelope(
            contact={
                "id": "ZZT-contact-900000009",
                "firstName": "ZZT",
                "custom_fields": [{"name": "is_allowed_stock", "value": "false"}],
            }
        )

    @classmethod
    def _wire(cls, engine_mod, monkeypatch) -> None:
        from app.config import settings

        monkeypatch.setattr(settings, "chatbot_business_lane_enabled", True)
        bundle = _srtwc8517_resolved_bundle()
        monkeypatch.setattr(
            engine_mod.business_services,
            "production_services",
            lambda db, *, space_id=None: bundle,
        )
        monkeypatch.setattr(
            engine_mod.business_services,
            "answer_services_for",
            lambda session_factory: _no_probe_answer_services(),
        )
        monkeypatch.setattr(
            engine_mod.business,
            "run_fetch",
            lambda payload, **kwargs: {
                "kind": "result",
                "_fetch_arm": "result",
                "delegate": "business_query",
                "delegate_payload": {**payload, "fetch": {**cls._ANSWERS, "_fetch_arm": "result"}},
                "fetch": {**cls._ANSWERS, "_fetch_arm": "result"},
            },
        )

    def test_with_the_switch_on_the_reply_is_the_demand_quantity_verdict_r1(
        self, session_factory, seeded, stub_parser, stub_access, system_settings_row, monkeypatch
    ) -> None:
        """`chatbot_stock_denial_enabled = True` routes `stock_denied` (`route.decide`,
        real), `run_until_exit` stamps `not_allowed_check_stock = True`
        (`__init__.py:85-86`), and `validator` rewrites the fetched rows into the
        cannot-be-fulfilled sentence (`answer.py`'s demand-quantity arm) - the composed
        `reply.text` must be that sentence, not the raw `_ANSWERS["response"]`."""
        from app.models.user import SystemSetting
        from app.services.chatbot import engine as engine_mod

        db = session_factory()
        setting = db.query(SystemSetting).filter(SystemSetting.id == system_settings_row.id).one()
        setting.chatbot_stock_denial_enabled = True
        setting.chatbot_completed_lanes = ["stock_denied"]
        db.commit()

        self._wire(engine_mod, monkeypatch)
        stub_parser(
            _parser_output(
                intent_hint="check_stock",
                domain_hint="inventory",
                demand_qty=5,
                entities=[{"raw": "SRTWC8517", "hint": "product", "current_message": True}],
            )
        )
        stub_access()

        result = engine_mod.run_turn(
            self._envelope_for_stock_check(), session_factory=session_factory
        )

        assert result.branch_kind == "stock_denied"
        assert result.delegate is None
        assert result.reply["text"] == (
            "Quantity of 5 for product SRTWC8517 cannot be fulfilled. "
            "Total available quantity is 3."
        ), result.reply
        _assert_crm_completed_send(result)

    def test_with_the_switch_off_the_same_message_routes_business_query_unstamped_r1(
        self, session_factory, seeded, stub_parser, stub_access, system_settings_row, monkeypatch
    ) -> None:
        """R1 default (`chatbot_stock_denial_enabled = False`): the SAME contact /
        message routes `business_query`, not `stock_denied` (`route.decide` cannot even
        pick the arm), the resolve+gate output carries no `not_allowed_check_stock`
        stamp, and the reply is the fetched response UNCHANGED - the switch is what
        gates the rewrite, not the contact's `is_allowed_stock` field alone."""
        from app.models.user import SystemSetting
        from app.services.chatbot import engine as engine_mod

        db = session_factory()
        setting = db.query(SystemSetting).filter(SystemSetting.id == system_settings_row.id).one()
        assert setting.chatbot_stock_denial_enabled is False
        setting.chatbot_completed_lanes = ["business_query"]
        db.commit()

        self._wire(engine_mod, monkeypatch)
        stub_parser(
            _parser_output(
                intent_hint="check_stock",
                domain_hint="inventory",
                demand_qty=5,
                entities=[{"raw": "SRTWC8517", "hint": "product", "current_message": True}],
            )
        )
        stub_access()

        result = engine_mod.run_turn(
            self._envelope_for_stock_check(), session_factory=session_factory
        )

        assert result.branch_kind == "business_query"
        assert result.delegate is None
        assert result.reply["text"] == self._ANSWERS["response"], (
            "with R1 off the validator must leave the fetched response untouched"
        )
        _assert_crm_completed_send(result)


# --------------------------------------------------------------------------- #
# 3. The tier-ask fetch arm: `fetch.fetch_result` emitting `"tier-ask"` reaching
#    `access_level_choice_message` - unreachable before the fix at
#    `lanes/business/__init__.py:400-406`. Real capture:
#    `nodes/live-spine-sorento-consume-main/access-level-choice-message/exec-13442255.json`
#    (grep of the fixtures dir), which carries `tier_any_available: true` - exactly the
#    field `fetch_result` keys the `"tier-ask"` arm on - so it is `fetch-result`'s own
#    output on this arm, not a hand-built shape.
# --------------------------------------------------------------------------- #


def _tier_ask_fixture_input() -> dict[str, Any] | None:
    root = _corpus.corpus_root()
    if root is None:
        return None
    directory = root / "nodes" / "live-spine-sorento-consume-main" / "access-level-choice-message"
    path = directory / "exec-13442255.json"
    if not path.is_file():
        return None
    import json

    with path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    return data["input"][0]["json"]


class TestTierAskFetchArmReachesAccessLevelChoiceEndToEnd:
    def test_tier_ask_arm_reaches_access_level_choice_message_prior_dead_branch(
        self, session_factory, seeded, stub_parser, stub_access, system_settings_row, monkeypatch
    ) -> None:
        """Before the fix, `complete_answer`'s branch at `__init__.py:400-406` checked
        only `exit_kind == "access_ask"`; `run_fetch`'s OWN `"tier-ask"` exit
        (`fetch_result`'s `tier_any_available` key) never reached it. This turn's
        `_exit_kind` is `"continue"` (the gate passed) and only the FETCH arm is
        `tier-ask`, so the branch is reached ONLY through the `fetch_arm == "tier-ask"`
        clause the fix added - and the reply composes real text end to end: the
        numbered tier list `access_level_choice_message` builds, checked against the
        real captured tier data (D3: a numbered typed list, never quick-reply buttons)."""
        from app.config import settings
        from app.models.user import SystemSetting
        from app.services.chatbot import engine as engine_mod

        fetch_json = _tier_ask_fixture_input()
        if fetch_json is None:
            pytest.skip(_corpus.corpus_skip_reason())
        assert fetch_json.get("tier_any_available") is True, (
            "the fixture must carry the field `fetch_result` keys the tier-ask arm on"
        )

        from app.services.chatbot.lanes.business import fetch as fetch_mod

        fetch_item = fetch_mod.fetch_result(dict(fetch_json))
        assert fetch_item["_fetch_arm"] == "tier-ask"

        db = session_factory()
        setting = db.query(SystemSetting).filter(SystemSetting.id == system_settings_row.id).one()
        setting.chatbot_completed_lanes = ["business_query"]
        db.commit()

        monkeypatch.setattr(settings, "chatbot_business_lane_enabled", True)
        bundle = _EngineWiring._stub_bundle([])
        monkeypatch.setattr(
            engine_mod.business_services,
            "production_services",
            lambda db, *, space_id=None: bundle,
        )
        monkeypatch.setattr(
            engine_mod.business_services,
            "answer_services_for",
            lambda session_factory: _no_probe_answer_services(),
        )
        monkeypatch.setattr(
            engine_mod.business,
            "run_until_exit",
            lambda *args, **kwargs: {
                "delegate": "business_query",
                "payload": {"_exit_kind": "continue", "resolved": {}, "gate": {}},
            },
        )
        monkeypatch.setattr(
            engine_mod.business,
            "run_fetch",
            lambda *args, **kwargs: {
                "kind": "tier_ask",
                "_fetch_arm": "tier-ask",
                "tier_probe": {},
                "fetch": fetch_item,
            },
        )
        stub_parser(
            _parser_output(
                domain_hint="master_products",
                entities=[{"raw": "SRTWC8517", "hint": "product", "current_message": True}],
            )
        )
        stub_access()

        result = engine_mod.run_turn(_envelope(), session_factory=session_factory)

        assert result.branch_kind == "business_query"
        assert result.delegate is None
        assert result.reply["text"] == (
            "Which access level do you need for SRTWC8517?\n"
            "1. Office - has promotion\n"
            "2. Dealer - has promotion\n"
            "3. End user - has promotion\n"
            'Reply with the number(s), e.g. "1", "1 and 2", or "all".'
        )
        assert result.reply.get("quick_replies") is None
        assert result.reply.get("result_set") == [
            {
                "idx": 1,
                "label": "Office",
                "value": "office",
                "tier": "office",
                "uuid": None,
                "entity_type": "access_tier",
                "product": None,
                "filename": None,
            },
            {
                "idx": 2,
                "label": "Dealer",
                "value": "dealer",
                "tier": "dealer",
                "uuid": None,
                "entity_type": "access_tier",
                "product": None,
                "filename": None,
            },
            {
                "idx": 3,
                "label": "End user",
                "value": "end_user",
                "tier": "end_user",
                "uuid": None,
                "entity_type": "access_tier",
                "product": None,
                "filename": None,
            },
        ]
        _assert_crm_completed_send(result)


# --------------------------------------------------------------------------- #
# 4. crossdomain-render, an ETA-only incoming set (no `quantity_on_hand` on any row).
#    A real capture exists:
#    `nodes/live-spine-sorento-consume-main/crossdomain-render/exec-14126915.json`
#    (grep for `estimated_arrival_date` with no `quantity_on_hand` in the same file) -
#    two incoming rows, each carrying `estimated_arrival_date` and no quantity field at
#    all. Pinned here BY NAME so it is graded even outside
#    `test_s6c_answer_lane.py::test_replay`'s blanket parametrize over the whole corpus
#    (confirmed already included there via the S6C_NODE_SLUGS scan - passing - but a
#    directory-wide scan silently stops grading a specific file if it is ever moved or
#    excluded, which a name-pinned test catches; the coder's own
#    `TestCrossdomainRenderRowOrder` covers the same rule with hand-built rows, so this
#    adds the REAL capture as a second, independent witness rather than replacing it).
# --------------------------------------------------------------------------- #


class TestCrossdomainRenderEtaOnlyCaptureReplays:
    def test_the_eta_only_no_quantity_capture_replays_byte_equal(self) -> None:
        fixtures = _s6c_full_corpus("crossdomain-render")
        if not fixtures:
            pytest.skip(_corpus.corpus_skip_reason())
        matches = [f for f in fixtures if f.name.endswith("exec-14126915")]
        if not matches:
            pytest.skip(
                "the ETA-only, no-quantity_on_hand capture (exec-14126915) is no longer "
                "present in the corpus - see COVERAGE.md before re-adding"
            )
        fixture = matches[0]
        answers = fixture.data["input"][0]["json"].get("answers") or []
        assert answers, "the fixture must carry at least one row to grade the ETA sort"
        for row in answers:
            fields = {f.get("key") for f in row.get("fields") or []}
            assert "estimated_arrival_date" in fields
            assert "quantity_on_hand" not in fields
        _replay(fixture)


# --------------------------------------------------------------------------- #
# S6c review round 3 nit (`lanes/business/__init__.py:433-439`): the `offer` arm
# stamps `branch_kind = "not_found"` straight onto the gate's own picker item and
# skips `build_suggest_offer`, which live actually runs on this edge before
# `tag-not-found` (`annotate-incoming-picker` / `annotate-customer-picker` ->
# `build-suggest-offer` -> `tag-not-found`). Evidence, not argument: a REAL `runData`
# capture of `resolve-exit-offer` (`sub-resolve-and-gate-rs/resolve-exit-offer/
# rg-15123789.json`, `annotate_incoming` populated - the incoming-picker case the nit
# names) run through `build_suggest_offer` unchanged on the four fields the picker
# owns, so skipping the node changes nothing observable on this arm.
# --------------------------------------------------------------------------- #


def _offer_arm_capture() -> dict[str, Any] | None:
    root = _corpus.corpus_root()
    if root is None:
        return None
    path = (
        root
        / "nodes"
        / "sub-resolve-and-gate-rs"
        / "resolve-exit-offer"
        / "rg-15123789.json"
    )
    if not path.is_file():
        return None
    import json

    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


class TestOfferArmSkipsBuildSuggestOfferSafely:
    _ROSTER_FIELDS = (
        "suggest_last_result_set",
        "require_specific",
        "is_clarification",
        "specific_options",
    )

    def test_build_suggest_offer_is_a_no_op_on_a_real_incoming_picker_capture(self) -> None:
        """`build_suggest_offer` adds a SUGGESTION offer on top of a not-found item; it
        has no case that reads or rewrites an already-built picker roster
        (`specific_options` / `require_specific` / `is_clarification` /
        `suggest_last_result_set`), so running it on the offer arm's item is a no-op on
        those four fields - confirmed here against a REAL captured incoming-picker
        payload rather than argued from reading the function."""
        data = _offer_arm_capture()
        if data is None:
            pytest.skip(_corpus.corpus_skip_reason())
        assert data["source"]["expected_from"] == "runData", (
            "this must be a real capture, not a hand-written expectation"
        )

        item = data["expected"][0]["json"]
        assert item.get("_exit_kind") == "offer"
        assert isinstance(item.get("annotate_incoming"), dict), (
            "this capture must be the incoming-picker case the nit names, not the "
            "customer-picker one"
        )

        ctx_wrap = data["ctx"]["When Executed by Another Workflow"][0]["json"]
        parser = ctx_wrap["ctx"]["ctx"]["parse"]["output"]

        before = {field: item.get(field) for field in self._ROSTER_FIELDS}
        assert before["require_specific"] is True
        assert before["is_clarification"] is False
        assert before["specific_options"], "the capture must carry a real roster to grade"

        from app.services.chatbot.lanes.business.answer import build_suggest_offer

        after_item = build_suggest_offer(dict(item), parser=parser, resolved=item, gate=item)
        after = {field: after_item.get(field) for field in self._ROSTER_FIELDS}

        assert after == before, (
            "build_suggest_offer changed a field the offer-arm picker owns - "
            f"before={before!r} after={after!r}; the __init__.py:433-439 comment "
            "citing this test is wrong and the offer arm needs the node after all"
        )
