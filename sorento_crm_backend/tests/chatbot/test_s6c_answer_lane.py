"""S6c tester slice: the business lane's answer + miss half (AC-607 to AC-609, D10,
D14, H16, H22/H23, H39, H40, H45).

RED FIRST (PRINCIPLES.md Phase 2). None of `app/services/chatbot/lanes/business/answer.py`,
`sub_answer.py`, `miss_suggest.py` exist yet, and `services.py` has no `AnswerServices`
bundle - every test below fails at import time with `ModuleNotFoundError` /
`AttributeError`, which is the RIGHT reason: the contract is pinned here, the coder
makes it green.

**The contract, in the shapes the coder implements (see each test's docstring for the
n8n node whose by-name reads it reproduces)**:

`app/services/chatbot/lanes/business/answer.py`
    validator(result, *, semantic_parser, not_allowed_check_stock=False) -> dict
    promo_picker(item, *, parser, resolved) -> dict
    crossdomain_zeroset(item, *, parser, resolved, session) -> dict
    crossdomain_probe_args(zeroset, *, parser, entities_names, contact_id, space_id) -> dict
    crossdomain_render(probe_result, *, zeroset, validator) -> dict
    run_crossdomain(validator_result, *, parser, resolved, session, entities_names,
                    services, contact_id, space_id, dry_run=False) -> dict
    build_result(item, *, validator, promo, zeroset, tool=None, tier_probe=None,
                 crossdomain_render=None) -> dict
    not_found_error_message(item, *, parser, resolved, gate) -> dict
    access_level_choice_message(item, *, parser) -> dict
    build_suggest_offer(item, *, parser, resolved, gate, dym_annotate=None,
                        sibling_probe=None, sibling_transform=None) -> dict
    dispatch(result) -> Literal["sub_answer", "miss_suggest"]           # If6
    aggregate_response_intro(result) -> list[str]                       # Aggregate1
    exclude_already_shown(candidates, *, shown_codes) -> list           # H45

`app/services/chatbot/lanes/business/sub_answer.py`
    answer_input(trigger) -> dict                                        # raises if trigger.item is not an object
    central_exchange(item) -> dict
    miss_roster_check(item, *, build_result, parser) -> dict
    miss_roster_plan(item, *, build_result, parser, gate, central_exchange=None) -> dict
    build_miss_member_offer(item, *, central_exchange, roster_plan) -> dict
    dym_transform_partial(item, *, parser, gate, resolved, central_exchange=None) -> dict
    dym_annotate_partial(item) -> dict
    answer_result(item, *, central_exchange=None, member_offer=None,
                 dym_annotate_partial=None) -> dict

`app/services/chatbot/lanes/business/miss_suggest.py`
    dym_transform(item, *, parser, resolved, central_exchange=None) -> dict
    dym_annotate(item) -> dict
    miss_suggest_result(item, *, dym_annotate=None, sibling_transform=None,
                        sibling_probe=None) -> dict   # sub-miss-suggest's own exit/carrier
    run_miss_lane(not_found_item, *, parser, resolved, gate, services,
                 dry_run=False) -> dict

`app/services/chatbot/lanes/business/services.py` (new bundle beside `ResolveGateServices`)
    class McpProbeFn(Protocol): def __call__(self, name: str, args: dict) -> Any: ...
    class FamilyFetchFn(Protocol): def __call__(self, query: str) -> Any: ...
    class AnswerServices:  mcp_probe: McpProbeFn; family_fetch: FamilyFetchFn
    production_answer_services(db) -> AnswerServices

Everything here is a pure function over plain dicts (D10: no session held across an MCP
call) except the two `production_answer_services` contract checks, which only inspect
signatures - no database, no network, no LLM.
"""
from __future__ import annotations

import inspect
import re as re_mod
from pathlib import Path
from typing import Any

import pytest

from tests.chatbot import _corpus, divergences

# --------------------------------------------------------------------------- #
# Fixture loading, LOCAL to this file rather than added to the shared
# `_corpus.NODE_SLUGS`. `scripts/chatbot_fixture_coverage.py` (gate 0, AC-008) iterates
# that shared dict and cross-references it against `CAPTURE_REPORT` - a table of which
# workflow VERSIONS the capture agent has actually scanned. None of the slugs below
# (`live-spine-sorento-consume-main`, `sub-answer-rs`, `sub-miss-suggest-rs`, ...) has a
# `CAPTURE_REPORT` entry yet, so registering them there would make gate 0 report every
# S6c cell "SHORT" and block - a real, useful signal once someone runs the capture-agent
# campaign S6a went through (`documentation/plans/chatbot/PLAN-chatbot-turn-engine.md`
# S6 note), but not this tester slice's call to make. `_corpus.NODE_SLUGS` itself stays
# untouched; this file loads the same fixture JSON shape directly.
# --------------------------------------------------------------------------- #

S6C_NODE_SLUGS: dict[str, tuple[str, ...]] = {
    "validator": ("live-spine-sorento-consume-main",),
    "promo-picker": ("live-spine-sorento-consume-main",),
    "crossdomain-zeroset": ("live-spine-sorento-consume-main",),
    "crossdomain-render": ("live-spine-sorento-consume-main",),
    "not-found-error-message": ("live-spine-sorento-consume-main",),
    "access-level-choice-message": ("clone-spine-RS", "live-spine-sorento-consume-main"),
    "build-suggest-offer": ("live-spine-sorento-consume-main",),
    # `sub-answer-live` (36 captures each) is the richer corpus from the 5 Sep capture
    # batch (help-crm), a SIBLING worktree of the n8n repo, not merged into the main
    # checkout - point `CHATBOT_FIXTURES_DIR` at it to grade against it. The sparse
    # `sub-answer` / `sub-answer-rs` directories in the main checkout stay listed too
    # (union by file stem via `_load_dir`, same discipline as `_corpus.full_corpus`).
    "miss-roster-plan": ("live-spine-sorento-consume-main", "sub-answer-live"),
    "build-miss-member-offer": ("live-spine-sorento-consume-main", "sub-answer-live"),
    "dym-annotate-partial": ("live-spine-sorento-consume-main", "sub-answer-live"),
    "central-exchange": (
        "live-spine-sorento-consume-main",
        "sub-answer-rs",
        "sub-answer-live",
        "sub-send-attachments",
        "sub-send-attachments-rs",
    ),
    "miss-roster-check": (
        "clone-spine-RS",
        "live-spine-sorento-consume-main",
        "sub-answer",
        "sub-answer-rs",
        "sub-answer-live",
    ),
    "dym-transform-partial": (
        "live-spine-sorento-consume-main",
        "sub-answer-rs",
        "sub-answer-live",
    ),
    "answer-input": ("sub-answer-rs", "sub-answer-live"),
    "answer-result": ("sub-answer-rs", "sub-answer-live"),
    # `sub-miss-suggest-live` (the 5 Sep batch): confirmed by direct grep of that live
    # workflow's export - its live version (`f42de9c6`) has NO `build-suggest-offer`
    # node of its own (that composer stays on the spine, see `miss-suggest-result`
    # below); captured nodes there are `dym-transform`, `dym-annotate`,
    # `sibling-transform`, `miss-suggest-result`. `promo-dym-plan` exists in the export
    # but never fired in the scanned pool (0 captures) - no node/test is built against
    # it here; it is a real zero cell for `scripts/chatbot_fixture_coverage.py`, not an
    # oversight.
    "dym-transform": (
        "clone-spine-RS",
        "live-spine-sorento-consume-main",
        "sub-miss-suggest-rs",
        "sub-miss-suggest-live",
    ),
    "dym-annotate": (
        "clone-spine-RS",
        "live-spine-sorento-consume-main",
        "sub-miss-suggest-rs",
        "sub-miss-suggest-live",
    ),
    # `miss-suggest-result`: `sub-miss-suggest`'s OWN exit/carrier node (RS-7 errata) -
    # only ever captured under `sub-miss-suggest-live` (38 files), never on the spine
    # (the spine inlines everything and has no sub-workflow boundary to carry across).
    "miss-suggest-result": ("sub-miss-suggest-live",),
    "build-result": (
        "clone-sub-main-processing",
        "clone-spine-RS",
        "live-spine-sorento-consume-main",
        "sub-answer-rs",
        "sub-answer-live",
    ),
}


def _s6c_full_corpus(node: str) -> list[_corpus.Fixture]:
    """`_corpus.full_corpus`, but reading `S6C_NODE_SLUGS` instead of the shared dict."""
    root = _corpus.corpus_root()
    if root is None:
        return []
    out: list[_corpus.Fixture] = []
    for slug in S6C_NODE_SLUGS.get(node, ()):
        out.extend(_corpus._load_dir(node, root / "nodes" / slug / node, prefix=f"{slug}/"))
    return out


# --------------------------------------------------------------------------- #
# Shared upstream readers. Fixtures come from TWO shapes (D8/S6a precedent,
# `test_replay.py`'s `_sub_ctx` family): the sub-workflow's OWN graph, which wraps the
# resolver behind `build-ctx-resolved` (`ctx.resolved` / `ctx.gate`), and the LIVE
# SPINE's monolithic copy, which reads `resolve-entity` / `disallowed-entity-gate`
# directly with no wrapper. Every S6c node the corpus actually captured (see
# `_corpus.NODE_SLUGS`) came from the live spine, so the fallback path is the one that
# fires on every fixture today; the wrapped path is kept for the day a sub-workflow's
# own capture is added.
# --------------------------------------------------------------------------- #


def _bc_ctx(fixture: _corpus.Fixture) -> dict:
    """`$('build-ctx').first().json.ctx` - one shape regardless of which graph ran it."""
    return (fixture.first("build-ctx") or {}).get("ctx") or {}


def _parser_output(fixture: _corpus.Fixture) -> dict:
    return ((_bc_ctx(fixture).get("parse") or {}) or {}).get("output") or {}


def _session_block(fixture: _corpus.Fixture) -> dict:
    return _bc_ctx(fixture).get("session") or {}


def _named(fixture: _corpus.Fixture, node: str) -> Any:
    """`$(node).isExecuted ? $(node).first().json : null` - the three-state by-name read."""
    items = fixture.upstream(node)
    return items[0].get("json") if items else None


def _resolved(fixture: _corpus.Fixture) -> dict:
    bcr = _named(fixture, "build-ctx-resolved")
    if bcr is not None:
        return (bcr.get("ctx") or {}).get("resolved") or {}
    return _named(fixture, "resolve-entity") or {}


def _gate(fixture: _corpus.Fixture) -> dict:
    bcr = _named(fixture, "build-ctx-resolved")
    if bcr is not None:
        return (bcr.get("ctx") or {}).get("gate") or {}
    return _named(fixture, "disallowed-entity-gate") or {}


def _input_json(fixture: _corpus.Fixture) -> dict:
    return (fixture.input[0].get("json") or {}) if fixture.input else {}


def _rt(value: Any) -> Any:
    return _corpus.json_round_trip(value)


# --------------------------------------------------------------------------- #
# AC-608: one runner per ported node, named exactly like `test_replay.py`'s. Only a
# REAL capture (`source.expected_from == "runData"`) grades the port - see `_corpus.py`.
# --------------------------------------------------------------------------- #


def _run_validator(fixture: _corpus.Fixture) -> Any:
    from app.services.chatbot.lanes.business.answer import validator

    edit_fields2 = _named(fixture, "Edit Fields2")
    return validator(
        _rt(_input_json(fixture)),
        semantic_parser=_rt(_bc_ctx(fixture).get("parse") or {}),
        not_allowed_check_stock=bool((edit_fields2 or {}).get("not_allowed_check_stock")),
    )


def _run_promo_picker(fixture: _corpus.Fixture) -> Any:
    from app.services.chatbot.lanes.business.answer import promo_picker

    return promo_picker(
        _rt(_input_json(fixture)),
        parser=_rt(_parser_output(fixture)),
        resolved=_rt(_resolved(fixture)),
    )


def _run_crossdomain_zeroset(fixture: _corpus.Fixture) -> Any:
    from app.services.chatbot.lanes.business.answer import crossdomain_zeroset

    return crossdomain_zeroset(
        _rt(_input_json(fixture)),
        parser=_rt(_parser_output(fixture)),
        resolved=_rt(_resolved(fixture)),
        session=_rt(_session_block(fixture)),
    )


def _run_crossdomain_render(fixture: _corpus.Fixture) -> Any:
    from app.services.chatbot.lanes.business.answer import crossdomain_render

    zeroset = _named(fixture, "crossdomain-zeroset") or {}
    return crossdomain_render(
        _rt(_input_json(fixture)),
        zeroset=_rt(zeroset.get("_xd") or {}),
        validator=_rt(_named(fixture, "validator") or {}),
    )


def _run_build_result(fixture: _corpus.Fixture) -> Any:
    from app.services.chatbot.lanes.business.answer import build_result

    call = _named(fixture, "Call 'sub-fetch-results'")
    tool = (call or {}).get("tool") if call is not None else _named(fixture, "tool-filter")
    tier_probe = (call or {}).get("tier_probe") if call is not None else None
    crossdomain_render = _named(fixture, "crossdomain-render")
    return build_result(
        _rt(_input_json(fixture)),
        validator=_rt(_named(fixture, "validator") or {}),
        promo=_rt(_named(fixture, "promo-picker") or {}),
        zeroset=_rt(_named(fixture, "crossdomain-zeroset") or {}),
        tool=_rt(tool) if tool is not None else None,
        tier_probe=_rt(tier_probe) if tier_probe is not None else None,
        crossdomain_render=_rt(crossdomain_render) if crossdomain_render is not None else None,
    )


def _run_not_found_error_message(fixture: _corpus.Fixture) -> Any:
    from app.services.chatbot.lanes.business.answer import not_found_error_message

    return not_found_error_message(
        _rt(_input_json(fixture)),
        parser=_rt(_parser_output(fixture)),
        resolved=_rt(_resolved(fixture)),
        gate=_rt(_gate(fixture)),
    )


def _run_access_level_choice_message(fixture: _corpus.Fixture) -> Any:
    from app.services.chatbot.lanes.business.answer import access_level_choice_message

    return access_level_choice_message(
        _rt(_input_json(fixture)),
        parser=_rt(_parser_output(fixture)),
    )


def _run_build_suggest_offer(fixture: _corpus.Fixture) -> Any:
    from app.services.chatbot.lanes.business.answer import build_suggest_offer

    dym_annotate = _named(fixture, "dym-annotate")
    sibling_probe = _named(fixture, "sibling-probe")
    sibling_transform = _named(fixture, "sibling-transform")
    return build_suggest_offer(
        _rt(_input_json(fixture)),
        parser=_rt(_parser_output(fixture)),
        resolved=_rt(_resolved(fixture)),
        gate=_rt(_gate(fixture)),
        dym_annotate=_rt(dym_annotate) if dym_annotate is not None else None,
        sibling_probe=_rt(sibling_probe) if sibling_probe is not None else None,
        sibling_transform=_rt(sibling_transform) if sibling_transform is not None else None,
    )


def _run_answer_input(fixture: _corpus.Fixture) -> Any:
    """`answer-input`: `sub-answer`'s item carrier. Reads the sub's OWN trigger
    (`$('When Executed by Another Workflow').first().json.item`) POSITIONALLY-blind -
    never `$input` - and raises if the trigger carried no `item` object."""
    from app.services.chatbot.lanes.business.sub_answer import answer_input

    trigger = fixture.first("When Executed by Another Workflow")
    return answer_input(_rt(trigger))


def _run_central_exchange(fixture: _corpus.Fixture) -> Any:
    from app.services.chatbot.lanes.business.sub_answer import central_exchange

    return central_exchange(_rt(_input_json(fixture)))


def _run_miss_roster_check(fixture: _corpus.Fixture) -> Any:
    from app.services.chatbot.lanes.business.sub_answer import miss_roster_check

    build_result_out = _named(fixture, "build-result") or {}
    return miss_roster_check(
        _rt(_input_json(fixture)),
        build_result=_rt(build_result_out.get("result") or {}),
        parser=_rt(_parser_output(fixture)),
    )


def _run_miss_roster_plan(fixture: _corpus.Fixture) -> Any:
    from app.services.chatbot.lanes.business.sub_answer import miss_roster_plan

    build_result_out = _named(fixture, "build-result") or {}
    central_exchange = _named(fixture, "central-exchange")
    return miss_roster_plan(
        _rt(_input_json(fixture)),
        build_result=_rt(build_result_out.get("result") or {}),
        parser=_rt(_parser_output(fixture)),
        gate=_rt(_gate(fixture)),
        central_exchange=_rt(central_exchange) if central_exchange is not None else None,
    )


def _run_build_miss_member_offer(fixture: _corpus.Fixture) -> Any:
    from app.services.chatbot.lanes.business.sub_answer import build_miss_member_offer

    return build_miss_member_offer(
        _rt(_input_json(fixture)),
        central_exchange=_rt(_named(fixture, "central-exchange") or {}),
        roster_plan=_rt(_named(fixture, "miss-roster-plan") or {}),
    )


def _run_dym_transform_partial(fixture: _corpus.Fixture) -> Any:
    from app.services.chatbot.lanes.business.sub_answer import dym_transform_partial

    central_exchange = _named(fixture, "central-exchange")
    return dym_transform_partial(
        _rt(_input_json(fixture)),
        parser=_rt(_parser_output(fixture)),
        gate=_rt(_gate(fixture)),
        resolved=_rt(_resolved(fixture)),
        central_exchange=_rt(central_exchange) if central_exchange is not None else None,
    )


def _run_dym_annotate_partial(fixture: _corpus.Fixture) -> Any:
    from app.services.chatbot.lanes.business.sub_answer import dym_annotate_partial

    return dym_annotate_partial(_rt(_input_json(fixture)))


def _run_answer_result(fixture: _corpus.Fixture) -> Any:
    from app.services.chatbot.lanes.business.sub_answer import answer_result

    central_exchange = _named(fixture, "central-exchange")
    member_offer = _named(fixture, "build-miss-member-offer")
    dym_annotate_partial = _named(fixture, "dym-annotate-partial")
    return answer_result(
        _rt(_input_json(fixture)),
        central_exchange=_rt(central_exchange) if central_exchange is not None else None,
        member_offer=_rt(member_offer) if member_offer is not None else None,
        dym_annotate_partial=_rt(dym_annotate_partial) if dym_annotate_partial is not None else None,
    )


def _run_dym_transform(fixture: _corpus.Fixture) -> Any:
    from app.services.chatbot.lanes.business.miss_suggest import dym_transform

    central_exchange = _named(fixture, "central-exchange")
    return dym_transform(
        _rt(_input_json(fixture)),
        parser=_rt(_parser_output(fixture)),
        resolved=_rt(_resolved(fixture)),
        central_exchange=_rt(central_exchange) if central_exchange is not None else None,
    )


def _run_dym_annotate(fixture: _corpus.Fixture) -> Any:
    from app.services.chatbot.lanes.business.miss_suggest import dym_annotate

    return dym_annotate(_rt(_input_json(fixture)))


def _run_miss_suggest_result(fixture: _corpus.Fixture) -> Any:
    """`miss-suggest-result`: `sub-miss-suggest`'s OWN exit/carrier (its live graph
    (`f42de9c6`) has no `build-suggest-offer` of its own - that node stays on the
    SPINE and reads this carrier's `outcome_fragment` one hop later, RS-7 errata). Picks
    `dym-annotate`'s own output when it ran, else re-emits the input, and always attaches
    `outcome_fragment = {dym-annotate, sibling-transform, sibling-probe}`."""
    from app.services.chatbot.lanes.business.miss_suggest import miss_suggest_result

    dym_annotate = _named(fixture, "dym-annotate")
    sibling_transform = _named(fixture, "sibling-transform")
    sibling_probe = _named(fixture, "sibling-probe")
    return miss_suggest_result(
        _rt(_input_json(fixture)),
        dym_annotate=_rt(dym_annotate) if dym_annotate is not None else None,
        sibling_transform=_rt(sibling_transform) if sibling_transform is not None else None,
        sibling_probe=_rt(sibling_probe) if sibling_probe is not None else None,
    )


RUNNERS: dict[str, Any] = {
    "validator": _run_validator,
    "promo-picker": _run_promo_picker,
    "crossdomain-zeroset": _run_crossdomain_zeroset,
    "crossdomain-render": _run_crossdomain_render,
    "not-found-error-message": _run_not_found_error_message,
    "access-level-choice-message": _run_access_level_choice_message,
    "build-suggest-offer": _run_build_suggest_offer,
    "answer-input": _run_answer_input,
    "central-exchange": _run_central_exchange,
    "miss-roster-check": _run_miss_roster_check,
    "miss-roster-plan": _run_miss_roster_plan,
    "build-miss-member-offer": _run_build_miss_member_offer,
    "dym-transform-partial": _run_dym_transform_partial,
    "dym-annotate-partial": _run_dym_annotate_partial,
    "answer-result": _run_answer_result,
    "dym-transform": _run_dym_transform,
    "dym-annotate": _run_dym_annotate,
    "miss-suggest-result": _run_miss_suggest_result,
}
# `build-result` reads three producers this file also wires directly (validator,
# promo-picker, crossdomain-zeroset) - registered separately so its own runner name
# does not collide with the upstream helpers above.
RUNNERS["build-result"] = _run_build_result

PORTED_NODES = sorted(RUNNERS)


def _replay(fixture: _corpus.Fixture) -> None:
    actual = _rt(RUNNERS[fixture.node](fixture))
    expected = _rt(fixture.expected)
    registered = divergences.find(fixture.node, fixture.name.split("/")[-1])
    if actual == expected:
        if registered is not None:
            pytest.fail(
                f"{fixture.node}/{fixture.name}: registered divergence "
                f"{registered.hazard} no longer diverges - retire the entry"
            )
        return
    if registered is not None:
        return
    assert actual == expected, (
        f"{fixture.node}/{fixture.name} diverges from the captured n8n output and is not "
        f"registered in tests/chatbot/divergences.py\nfixture: {fixture.path}"
    )


@pytest.mark.parametrize(
    "fixture",
    _corpus.graded([f for node in PORTED_NODES for f in _s6c_full_corpus(node)]) or [None],
    ids=lambda f: f"{f.node}/{f.name}" if f is not None else "corpus-absent",
)
def test_replay(fixture) -> None:
    """AC-608: every `runData` fixture for the S6c nodes (AC-607) replayed through the
    Python port, byte-equal after a JSON round trip. Parametrised over the FULL n8n
    corpus (sibling checkout, `CHATBOT_FIXTURES_DIR` override honoured via
    `_corpus.corpus_root()`) rather than a vendored subset - S6c has not vendored a
    committed subset yet (AC-008 is a coder/reviewer follow-up, mirroring how S6a
    vendored progressively); this is the always-graded gate once that lands.
    """
    if fixture is None:
        pytest.skip(_corpus.corpus_skip_reason())
    _replay(fixture)


@pytest.mark.parametrize("node", PORTED_NODES)
def test_full_corpus_has_at_least_one_capture(node: str) -> None:
    """Each of the 17 AC-607 nodes has at least one real capture in the sibling n8n
    checkout - if this goes empty for a node, `test_replay` would pass by having
    nothing to grade for it, which is exactly the silent-gate failure AC-008 exists to
    catch (measured per-node counts belong in COVERAGE.md once vendored)."""
    root = _corpus.corpus_root()
    if root is None:
        pytest.skip(_corpus.corpus_skip_reason())
    fixtures = _s6c_full_corpus(node)
    assert fixtures, (
        f"no captures for {node} under any of {S6C_NODE_SLUGS.get(node, ())} - "
        "test_replay would grade nothing for this node"
    )


# --------------------------------------------------------------------------- #
# AC-607: If6 dispatch (validator/is_valid -> sub_answer, else the miss lane) and
# Aggregate1 (n8n's built-in Aggregate node, `fieldsToAggregate: [response_intro]`).
# --------------------------------------------------------------------------- #


class TestIf6Dispatch:
    def test_has_result_and_is_valid_goes_to_sub_answer(self) -> None:
        from app.services.chatbot.lanes.business.answer import dispatch

        assert dispatch({"has_result": True, "is_valid": True}) == "sub_answer"

    @pytest.mark.parametrize(
        ("has_result", "is_valid"),
        [(False, True), (True, False), (False, False)],
    )
    def test_anything_else_goes_to_the_miss_lane(self, has_result: bool, is_valid: bool) -> None:
        from app.services.chatbot.lanes.business.answer import dispatch

        assert dispatch({"has_result": has_result, "is_valid": is_valid}) == "miss_suggest"

    def test_miss_lane_carries_aggregate1s_response_intro(self) -> None:
        """`Aggregate1` (n8n `n8n-nodes-base.aggregate`, `fieldsToAggregate:
        [response_intro]`) runs on the miss branch and collects the `response_intro`
        field off the item(s) it sees. The port must hand the SAME value to the miss
        lane rather than dropping it on the floor when it restructures the dispatch."""
        from app.services.chatbot.lanes.business.answer import aggregate_response_intro, dispatch

        result = {
            "has_result": False,
            "is_valid": True,
            "response_intro": "No stock records found for: SRTWC8517.",
        }
        assert dispatch(result) == "miss_suggest"
        assert aggregate_response_intro(result) == ["No stock records found for: SRTWC8517."]
        assert aggregate_response_intro({"response_intro": None}) == []


# --------------------------------------------------------------------------- #
# AC-607: crossdomain-probe, the SECOND MCP call the answer lane makes on a turn
# (the first is the fetch itself, S6b). `semantic_input` shape is byte-for-byte the
# live node's own expression (export/sub-main-processing-live/nodes not-a-.js-file -
# read from workflow.json's `crossdomain-probe` `workflowInputs.value`).
# --------------------------------------------------------------------------- #


class TestCrossdomainProbe:
    def test_zeroset_active_triggers_exactly_one_probe_with_the_semantic_input_shape(
        self,
    ) -> None:
        from app.services.chatbot.lanes.business.answer import crossdomain_zeroset, run_crossdomain
        from app.services.chatbot.lanes.business.services import AnswerServices

        parser = {
            "message_type": "business_query",
            "intent_hint": "check_stock",
            "domain_hint": "inventory",
            "user_goal": "check stock for SRTWC8517",
            "access_levels": ["Dealer", "End User"],
            "is_active": True,
        }
        resolved = {
            "resolutions": [
                {
                    "token": "SRTWC8517",
                    "matches": [
                        {
                            "entity_type": "product",
                            "canonical_code": "SRTWC8517",
                            "uuid": "prod-uuid-1",
                            "match_tier": "exact",
                        }
                    ],
                }
            ]
        }
        session = {"session_vars": {"variables": {}}}
        validator_result = {
            "answers": [{"fields": [{"label": "Product Code", "value": "SRTOTHER"}]}],
            "response": "Some other stock line.",
        }

        zeroset = crossdomain_zeroset(
            validator_result, parser=parser, resolved=resolved, session=session
        )
        assert zeroset["_xd"]["active"] is True, "SRTWC8517 was asked for but never returned"

        calls: list[tuple[str, dict]] = []

        def mcp_probe(name: str, args: dict) -> dict:
            calls.append((name, args))
            return {"answers": [], "has_result": False}

        services = AnswerServices(mcp_probe=mcp_probe, family_fetch=lambda q: {"data": []})
        run_crossdomain(
            validator_result,
            parser=parser,
            resolved=resolved,
            session=session,
            entities_names=None,
            services=services,
            contact_id="164838271",
            space_id="900001",
        )

        assert len(calls) == 1, (
            "crossdomain-probe is the answer lane's SECOND mcp call on this turn "
            f"(the fetch itself is the first, S6b) - got {len(calls)} calls: {calls}"
        )
        name, args = calls[0]
        assert name == "crm_incoming_stock_list"
        assert args["semantic_input"] == {
            "message_type": "business_query",
            "intent_hint": "check_stock",
            "domain_hint": "inventory",
            "user_goal": "check stock for SRTWC8517",
            "access_levels": ["Dealer", "End User"],
            "contact_id": "164838271",
            "space_id": "900001",
            "is_active": True,
        }

    def test_access_levels_are_the_sorted_intersection_with_entitlement(self) -> None:
        """When the resolver's entitlement aggregate ran, `semantic_input.access_levels`
        is `ctx.entities.name` (the entitlement union) sorted and intersected with the
        parser's own `access_levels` - never the raw entitlement list unfiltered, and
        never the parser's list unsorted."""
        from app.services.chatbot.lanes.business.answer import crossdomain_probe_args

        zeroset = {"active": True, "other_tool": "crm_incoming_stock_list", "origin_domain": "inventory",
                   "probe_entities": [{"uuid": "u1", "entity_type": "product", "code": "X"}]}
        parser = {
            "message_type": "business_query",
            "intent_hint": "check_stock",
            "domain_hint": "inventory",
            "user_goal": "g",
            "access_levels": ["Dealer", "End User"],
            "is_active": None,
        }
        args = crossdomain_probe_args(
            zeroset,
            parser=parser,
            entities_names=["Office", "Dealer", "End User"],
            contact_id="1",
            space_id="900001",
        )
        assert args["semantic_input"]["access_levels"] == ["Dealer", "End User"]


# --------------------------------------------------------------------------- #
# AC-607: the miss lane - dym-transform, its probes, family-fetch (never a raw IP,
# H52's family-fetch half; D10), then build-suggest-offer.
# --------------------------------------------------------------------------- #


class TestMissLaneProbesAndFamilyFetch:
    def test_not_found_path_probes_and_fetches_the_family_before_offering(self) -> None:
        from app.services.chatbot.lanes.business.miss_suggest import run_miss_lane
        from app.services.chatbot.lanes.business.services import AnswerServices

        parser = {
            "message_type": "business_query",
            "intent_hint": "check_stock",
            "domain_hint": "inventory",
            "entities": [{"hint": "product", "raw": "SRTWC286"}],
            "access_levels": [],
        }
        resolved = {
            "by_entity_type": {},
            "unresolved_tokens": ["SRTWC286"],
            "resolutions": [
                {
                    "token": "SRTWC286",
                    "matches": [
                        {
                            "entity_type": "product",
                            "canonical_code": "SRTWC286-SH",
                            "uuid": "prod-uuid-1",
                            "match_tier": "prefix",
                        }
                    ],
                }
            ],
        }
        gate = {"gate_passed": False, "gate_reason": "no exact match"}
        not_found_item = {
            "escalate_message": "Could not find product SRTWC286.",
            "is_clarification": False,
        }

        probe_calls: list[tuple[str, dict]] = []
        fetch_calls: list[str] = []

        def mcp_probe(name: str, args: dict) -> dict:
            probe_calls.append((name, args))
            return {"answers": [], "has_result": False}

        def family_fetch(query: str) -> dict:
            fetch_calls.append(query)
            return {"data": [{"canonical_code": "SRTWC286-SH-200"}]}

        services = AnswerServices(mcp_probe=mcp_probe, family_fetch=family_fetch)

        out = run_miss_lane(
            not_found_item, parser=parser, resolved=resolved, gate=gate, services=services
        )

        assert probe_calls, (
            "the miss lane never probed a did-you-mean candidate through mcp_probe - "
            "dym-probe / promo-dym-probe / sibling-probe are the same seam by domain"
        )
        assert fetch_calls, "family-fetch never ran - the sibling family lookup is skipped"
        assert "SRTWC286" in fetch_calls[0]
        assert out.get("dym_offer") is not None
        assert out["dym_offer"].get("ttl") == 3
        assert out["dym_offer"].get("picked") == []

    def test_family_fetch_takes_a_query_string_never_a_raw_url(self) -> None:
        """D10/H52 (family-fetch's own httpRequest node hits `https://72.62.195.20/...`
        directly today - the plan's H52 disposition is `fix S6b (config URL)`, and
        family-fetch is the one S6c read that would otherwise repeat the same mistake).
        The seam signature takes a bare query string; the production binding is the
        in-process products service, never a socket the coder has to remember to
        configure."""
        from app.services.chatbot.lanes.business.services import FamilyFetchFn

        sig = inspect.signature(FamilyFetchFn.__call__)
        params = [p for p in sig.parameters if p not in ("self",)]
        assert params == ["query"], (
            f"FamilyFetchFn.__call__ takes {params}, expected just `query` - a URL or "
            "host parameter here is exactly the raw-IP hazard this seam exists to close"
        )


# --------------------------------------------------------------------------- #
# AC-609 / H45: did-you-mean never re-offers a row the answer already showed. ONE
# outcome-level predicate (not scattered per-mechanism across dym-transform,
# dym-annotate and build-suggest-offer separately).
# --------------------------------------------------------------------------- #


class TestH45NoReofferOfAnsweredRows:
    def test_candidate_already_in_the_answer_is_dropped(self) -> None:
        from app.services.chatbot.lanes.business.answer import exclude_already_shown

        candidates = [{"code": "SRTWC286-SH"}, {"code": "SRTWC8517"}]
        result = exclude_already_shown(candidates, shown_codes={"SRTWC286-SH"})
        assert [c["code"] for c in result] == ["SRTWC8517"]

    def test_nothing_shown_keeps_every_candidate(self) -> None:
        from app.services.chatbot.lanes.business.answer import exclude_already_shown

        candidates = [{"code": "A"}, {"code": "B"}]
        assert exclude_already_shown(candidates, shown_codes=set()) == candidates

    def test_predicate_is_case_and_shape_insensitive_like_every_other_code_compare(
        self,
    ) -> None:
        from app.services.chatbot.lanes.business.answer import exclude_already_shown

        candidates = [{"code": "srtwc286-sh"}]
        result = exclude_already_shown(candidates, shown_codes={"SRTWC286-SH"})
        assert result == []


# --------------------------------------------------------------------------- #
# H39: two product tokens whose did-you-mean candidates overlap must each keep at
# least one suggestion. `dym-transform-partial.js` / `dym-transform.js` apply a GLOBAL
# cap (`dym_candidate_codes.slice(0, _cap)`) over the concatenated candidate list, which
# can zero out a whole token's block if an earlier token's candidates already filled
# the cap - reproduce that first (plan hazard table: "S6c: reproduce first, fix as
# registered divergence if owner says go"), and the FIXED behaviour is asserted
# `xfail(strict=False)` under the hazard id so the fix is visible the day it lands.
# --------------------------------------------------------------------------- #


class TestH39CrossTokenDedupe:
    _PARSER = {
        "message_type": "business_query",
        "domain_hint": "inventory",
        "entities": [
            {"hint": "product", "raw": "SRTWC286"},
            {"hint": "product", "raw": "SRTWB247"},
        ],
    }
    _RESOLVED = {
        "unresolved_tokens": ["SRTWC286", "SRTWB247"],
        "resolutions": [
            {
                "token": "SRTWC286",
                "matches": [
                    {"entity_type": "product", "canonical_code": f"SRTWC286-{i}", "uuid": f"u286-{i}"}
                    for i in range(1, 12)  # 11 siblings: enough to fill a small global cap alone
                ],
            },
            {
                "token": "SRTWB247",
                "matches": [
                    {"entity_type": "product", "canonical_code": "SRTWB247-SH", "uuid": "u247-1"}
                ],
            },
        ],
    }
    _GATE = {"gate_passed": False, "gate_reason": "no exact match"}
    _NOT_FOUND_ITEM = {"escalate_message": "Could not find these products.", "is_clarification": False}

    def test_js_cap_can_zero_a_tokens_block(self) -> None:
        """Today's behaviour (parity, D8): the global cap is allowed to starve the
        second token entirely. This is the RED-phase parity assertion - it documents
        what the port must reproduce first, and it is expected to need a divergence
        entry once dym-transform is ported (H39)."""
        from app.services.chatbot.lanes.business.miss_suggest import dym_transform

        out = dym_transform(self._NOT_FOUND_ITEM, parser=self._PARSER, resolved=self._RESOLVED)
        codes = set(out.get("dym_candidate_codes") or [])
        assert not codes.issuperset({"SRTWC286-1", "SRTWB247-SH"}), (
            "if this assertion fails, the JS parity behaviour has already changed - "
            "retire this test and keep only the xfail below"
        )

    @pytest.mark.xfail(strict=False, reason="H39: fix is a registered divergence, owner sign-off pending")
    def test_each_token_keeps_at_least_one_suggestion_fixed_behaviour(self) -> None:
        from app.services.chatbot.lanes.business.miss_suggest import dym_transform

        out = dym_transform(self._NOT_FOUND_ITEM, parser=self._PARSER, resolved=self._RESOLVED)
        codes = out.get("dym_candidate_codes") or []
        assert any(c.startswith("SRTWC286") for c in codes), "SRTWC286's own token lost every suggestion"
        assert any(c.startswith("SRTWB247") for c in codes), "SRTWB247's own token lost every suggestion"


# --------------------------------------------------------------------------- #
# H40: duplicate product codes across companies ("twins"). `dym-annotate.js`'s own F1
# amendment (owner ruling, 2026-09-01) already fixes this in the n8n body - has/no
# certificate is stamped only when the (code, company) composite join finds EXACTLY
# ONE owner; more than one candidate sharing a code with no company match on the
# answer row is `dym_ambiguous_codes`, rendered bare, never guessed. The port
# reproduces this AS THE BASELINE (not a pending hazard - the JS already has the fix).
# --------------------------------------------------------------------------- #


class TestH40CertTwinLabelling:
    def _row_keys(self) -> list[dict]:
        return [
            {"uuid": "uuid-sorento", "code": "MWC-SC08B", "company": "Sorento"},
            {"uuid": "uuid-mocha", "code": "MWC-SC08B", "company": "Mocha"},
        ]

    def test_has_certificate_only_when_the_company_join_is_unambiguous(self) -> None:
        from app.services.chatbot.lanes.business.miss_suggest import dym_annotate

        item = {
            "probe_predicate": "row_present_with_type",
            "probe_uuid_keyed": True,
            "dym_probe_row_keys": self._row_keys(),
            "answers": [
                {
                    "fields": [
                        {"label": "Product Code", "value": "MWC-SC08B"},
                        {"label": "Company", "value": "Sorento"},
                        {"label": "Attachment Type", "value": "Certification"},
                    ]
                }
            ],
        }
        out = dym_annotate(item)
        assert out["dym_available_codes"] == ["uuid-sorento"], (
            "only Sorento's twin was probed as having a certificate - Mocha's twin must "
            "not inherit the label"
        )
        assert out.get("dym_ambiguous_codes") == []

    def test_no_company_match_and_more_than_one_owner_is_ambiguous_not_guessed(self) -> None:
        from app.services.chatbot.lanes.business.miss_suggest import dym_annotate

        item = {
            "probe_predicate": "row_present_with_type",
            "probe_uuid_keyed": True,
            "dym_probe_row_keys": self._row_keys(),
            "answers": [
                {
                    "fields": [
                        {"label": "Product Code", "value": "MWC-SC08B"},
                        {"label": "Attachment Type", "value": "Certification"},
                        # no Company field on this row - cannot join to one twin
                    ]
                }
            ],
        }
        out = dym_annotate(item)
        assert out["dym_available_codes"] == [], (
            "an ambiguous (code, company) join must never mark EVERY owner as having a "
            "certificate - that is exactly the false-positive F1 was written to close"
        )
        assert "mwc-sc08b" in [c.lower() for c in (out.get("dym_ambiguous_codes") or [])]


# --------------------------------------------------------------------------- #
# H16: `not_found_error_message` iterates only ENTITY-TYPE keys of
# `resolved.by_entity_type` - a metadata key injected onto the same dict must never
# reach the customer-facing reply text.
# --------------------------------------------------------------------------- #


class TestH16ByEntityTypeIterationIsEntityKeysOnly:
    def test_a_metadata_key_on_by_entity_type_never_reaches_the_reply(self) -> None:
        from app.services.chatbot.lanes.business.answer import not_found_error_message

        resolved = {
            "by_entity_type": {
                "product": [],
                # not a real entity type - if the node iterates blindly this leaks in.
                "__debug_meta__": {"leaked": True, "internal": "should never be spoken"},
            },
            "tokens": ["SRT123"],
            "unresolved_tokens": ["SRT123"],
        }
        parser = {
            "domain_hint": "master_products",
            "entities": [{"hint": "product", "raw": "SRT123"}],
            "routing": {"suggested_team": "purchasing"},
            "access_levels": [],
        }
        gate = {"gate_passed": False, "gate_reason": "no match", "gate_debug": {"allowed_lookup": []}}

        out = not_found_error_message({}, parser=parser, resolved=resolved, gate=gate)
        message = out.get("escalate_message") or ""
        assert "__debug_meta__" not in message
        assert "leaked" not in message
        assert "internal" not in message


# --------------------------------------------------------------------------- #
# H22 / H23: a did-you-mean offer's carried PICKS only ride into a cross-domain read
# when the offer's own domain agrees with the turn's current domain. A promotion-thread
# offer must not pollute an inventory-domain crossdomain probe. (`crossdomain-zeroset`'s
# own `_offerDomainOk` guard, "DOMAIN GUARD 2026-09-01".)
# --------------------------------------------------------------------------- #


class TestH22H23DymOfferDomainCleared:
    def test_a_promotion_threads_carried_pick_is_not_read_on_an_inventory_turn(self) -> None:
        from app.services.chatbot.lanes.business.answer import crossdomain_zeroset

        parser = {"message_type": "business_query", "domain_hint": "inventory"}
        resolved = {}
        session = {
            "session_vars": {
                "variables": {"dym_offer": {"domain": "promotion", "picked": ["SRT-OLD-PICK"]}}
            }
        }
        validator_result = {"answers": [], "response": "no rows"}

        out = crossdomain_zeroset(
            validator_result, parser=parser, resolved=resolved, session=session
        )
        requested = out["_xd"]["requested"]
        assert "SRT-OLD-PICK" not in requested, (
            "a pick carried from a PROMOTION-domain offer must not name a product on an "
            "inventory-domain crossdomain read - the offer's own domain guards it"
        )

    def test_a_same_domain_carried_pick_is_read(self) -> None:
        from app.services.chatbot.lanes.business.answer import crossdomain_zeroset

        parser = {"message_type": "business_query", "domain_hint": "inventory"}
        resolved = {}
        session = {
            "session_vars": {
                "variables": {"dym_offer": {"domain": "inventory", "picked": ["SRT-SAME-DOMAIN"]}}
            }
        }
        validator_result = {"answers": [], "response": "no rows"}

        out = crossdomain_zeroset(
            validator_result, parser=parser, resolved=resolved, session=session
        )
        requested = out["_xd"]["requested"]
        assert "SRT-SAME-DOMAIN" in requested


# --------------------------------------------------------------------------- #
# D14: a dry-run turn still runs every probe and family_fetch (parity - a read costs
# nothing); the answer lane never accepts or touches a database session at all - the
# only writer on the whole turn path is the S2 tail.
# --------------------------------------------------------------------------- #


class TestD14DryRunReadsButWritesNothing:
    def test_no_answer_lane_function_takes_a_db_session(self) -> None:
        from app.services.chatbot.lanes.business import answer, miss_suggest, sub_answer

        offenders = []
        for module in (answer, sub_answer, miss_suggest):
            for name, obj in vars(module).items():
                if name.startswith("_") or not callable(obj):
                    continue
                try:
                    sig = inspect.signature(obj)
                except (TypeError, ValueError):
                    continue
                if "db" in sig.parameters or "session" in sig.parameters:
                    offenders.append(f"{module.__name__}.{name}{sig}")
        assert not offenders, (
            "the S6c answer lane must stay read-only via `services` (D10) - a db/session "
            f"parameter here means a write path snuck into the lane the tail (S2) owns: "
            f"{offenders}"
        )

    def test_dry_run_still_exercises_every_probe_and_the_family_fetch(self) -> None:
        """D14: `dry_run=True` suppresses WRITES, never READS - the plan is explicit
        that a test turn does zero writes but the would-be state is still computed, so
        every probe this turn would have made still runs."""
        from app.services.chatbot.lanes.business.answer import crossdomain_zeroset, run_crossdomain
        from app.services.chatbot.lanes.business.services import AnswerServices

        parser = {
            "message_type": "business_query",
            "intent_hint": "check_stock",
            "domain_hint": "inventory",
            "user_goal": "g",
            "access_levels": [],
            "is_active": None,
        }
        resolved = {
            "resolutions": [
                {
                    "token": "SRTWC8517",
                    "matches": [
                        {
                            "entity_type": "product",
                            "canonical_code": "SRTWC8517",
                            "uuid": "prod-uuid-1",
                            "match_tier": "exact",
                        }
                    ],
                }
            ]
        }
        session = {"session_vars": {"variables": {}}}
        validator_result = {"answers": [], "response": "no rows"}
        zeroset = crossdomain_zeroset(
            validator_result, parser=parser, resolved=resolved, session=session
        )
        assert zeroset["_xd"]["active"] is True

        calls: list[str] = []
        services = AnswerServices(
            mcp_probe=lambda name, args: calls.append("probe") or {"answers": []},
            family_fetch=lambda q: calls.append("fetch") or {"data": []},
        )
        run_crossdomain(
            validator_result,
            parser=parser,
            resolved=resolved,
            session=session,
            entities_names=None,
            services=services,
            contact_id="1",
            space_id="900001",
            dry_run=True,
        )
        assert "probe" in calls, "a dry run must not skip the crossdomain probe - only writes are suppressed"


# --------------------------------------------------------------------------- #
# Capacity: never hold a database session across an MCP probe call. D10's own
# precedent (`lanes/business/services.py::_probe`, S6a) is that the probe seam takes
# NO session parameter at all - the same must hold for `mcp_probe`.
# --------------------------------------------------------------------------- #


class TestNoSessionAcrossProbeCalls:
    def test_mcp_probe_protocol_takes_no_database_session(self) -> None:
        from app.services.chatbot.lanes.business.services import McpProbeFn

        sig = inspect.signature(McpProbeFn.__call__)
        params = set(sig.parameters) - {"self"}
        assert "db" not in params and "session" not in params, (
            "mcp_probe is a network call to the MCP server (D10) - a db/session "
            "parameter here is the same hold-a-connection-across-I/O hazard the plan's "
            f"96/100-connection incident is evidence against; got parameters {params}"
        )

    def test_family_fetch_protocol_takes_no_database_session(self) -> None:
        """`family_fetch`'s PRODUCTION binding legitimately opens its own session (it
        reads the products table), but the SEAM signature itself must not thread one
        in from the caller - the caller is the answer lane, which D14's own test above
        proves never holds one."""
        from app.services.chatbot.lanes.business.services import FamilyFetchFn

        sig = inspect.signature(FamilyFetchFn.__call__)
        params = set(sig.parameters) - {"self"}
        assert "db" not in params and "session" not in params


# --------------------------------------------------------------------------- #
# D11: everything after the parser works on structured state. No regex/fuzzy match
# over raw customer text or a previous reply string in the three new S6c modules.
# --------------------------------------------------------------------------- #


def test_no_raw_text_regex_in_answer_modules() -> None:
    """D11. A line that reproduces an EXISTING n8n text-sniffing site for parity (the
    plan's own text-sniffing inventory) is allowed if it carries the marker comment
    `# D11-reproduced` naming why; anything else is a new regex/fuzzy match over raw
    text, which D11 forbids outright for anything ported after the parser."""
    root = (
        Path(__file__).resolve().parents[2]
        / "app"
        / "services"
        / "chatbot"
        / "lanes"
        / "business"
    )
    module_names = ("answer.py", "sub_answer.py", "miss_suggest.py")
    missing = [name for name in module_names if not (root / name).exists()]
    assert not missing, f"S6c modules not created yet: {missing}"

    forbidden = re_mod.compile(r"\bre\.(search|match|fullmatch|findall|finditer|sub|subn)\(")
    offenders: list[str] = []
    for name in module_names:
        text = (root / name).read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), start=1):
            if forbidden.search(line) and "# D11-reproduced" not in line:
                offenders.append(f"{name}:{lineno}: {line.strip()}")
    assert not offenders, (
        "new `re.*` call over raw text in the S6c answer lane, not marked "
        "`# D11-reproduced` (a named parity reproduction of an existing n8n "
        "text-sniffing site):\n" + "\n".join(offenders)
    )
