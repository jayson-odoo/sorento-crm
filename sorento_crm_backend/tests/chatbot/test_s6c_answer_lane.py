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
    crossdomain_zeroset(item, *, parser, resolved, session_block) -> dict
    crossdomain_probe_args(zeroset, *, parser, entities_names, contact_id, space_id) -> dict
    crossdomain_render(probe_result, *, zeroset, validator) -> dict
    run_crossdomain(validator_result, *, parser, resolved, session_block, entities_names,
                    services, contact_id, space_id, dry_run=False) -> dict
        # `session_block` is `ctx.session` (get-session-vars' own response shape), never a
        # database session - named to hold against `test_no_answer_lane_function_takes_a_db_session`
    build_result(item, *, validator, promo, zeroset, tool=None, tier_probe=None,
                 crossdomain_render=None) -> dict
    not_found_error_message(item, *, parser, resolved, gate) -> dict
    access_level_choice_message(item, *, parser) -> dict
    build_suggest_offer(item, *, parser, resolved, gate, dym_annotate=None,
                        sibling_probe=None, sibling_transform=None) -> dict
    dispatch(result) -> Literal["sub_answer", "miss_suggest"]           # If6
    aggregate_response_intro(result) -> list[str]                       # Aggregate1

`app/services/chatbot/lanes/business/__init__.py` (new seam beside `run_until_exit`)
    complete_answer(...) -> {"reply": dict, "actions": list}   # engine.run_turn calls this
        when `delegate.delegate_for(branch_kind, engine._enabled_lanes(db))` is None, and
        sets `delegate = None` from its `{reply, actions}` return instead of delegating.

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
from tests.chatbot.test_engine import (  # noqa: F401  - fixtures used by name (S6a precedent)
    _envelope,
    seeded,
    stub_access,
    stub_parser,
)

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
    # `sub-send-attachments` / `-rs` are EXCLUDED (same class as S6a's
    # `disallowed-entity-gate` exclusions): that sub's own `central-exchange.js` is a
    # name-preserving STUB re-emitting `trigger.attachments_src` (12 lines), not the
    # real 28-line node this port replicates (`output.output`/markdown-fence unwrap).
    # Measured: `cat export/sub-send-attachments-rs/nodes/central-exchange.js`.
    "central-exchange": (
        "live-spine-sorento-consume-main",
        "sub-answer-rs",
        "sub-answer-live",
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
    # `sub-answer-rs` / `sub-answer-live` are EXCLUDED, same class: `sub-answer`'s own
    # `build-result.js` is a NAMED-VALUE carrier (`return [{json:
    # trigger.result ?? {}}]`, 12 lines) re-emitting the contract's `result` value
    # verbatim - not `sub-main-processing`'s real 88-line node this port replicates.
    # Measured: `cat export/sub-answer-rs/nodes/build-result.js`.
    "build-result": (
        "clone-sub-main-processing",
        "clone-spine-RS",
        "live-spine-sorento-consume-main",
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


def _wrap(result: Any) -> list:
    """`tests/harness/n8n-shim.js`'s own `normalizeReturn`: a Code node returning a
    plain object produces exactly ONE item (`[{"json": result}]`, `test_replay.py`'s
    own shape); returning `None`/`undefined` produces ZERO items - n8n's shim treats a
    null return as "no items", not an error (measured live, exec 14126032), which is
    also why `_corpus.Fixture.expected` folds a fixture's `"expected": null` to `[]`
    (`self.data.get("expected") or []`). Every `_run_*` below returns through this so
    `_replay` compares two item LISTS, matching every captured `expected` array."""
    if result is None:
        return []
    return [{"json": result}]


# --------------------------------------------------------------------------- #
# AC-608: one runner per ported node, named exactly like `test_replay.py`'s. Only a
# REAL capture (`source.expected_from == "runData"`) grades the port - see `_corpus.py`.
# --------------------------------------------------------------------------- #


def _run_validator(fixture: _corpus.Fixture) -> Any:
    from app.services.chatbot.lanes.business.answer import validator

    edit_fields2 = _named(fixture, "Edit Fields2")
    return _wrap(
        validator(
            _rt(_input_json(fixture)),
            semantic_parser=_rt(_bc_ctx(fixture).get("parse") or {}),
            not_allowed_check_stock=bool((edit_fields2 or {}).get("not_allowed_check_stock")),
        )
    )


def _run_promo_picker(fixture: _corpus.Fixture) -> Any:
    from app.services.chatbot.lanes.business.answer import promo_picker

    return _wrap(
        promo_picker(
            _rt(_input_json(fixture)),
            parser=_rt(_parser_output(fixture)),
            resolved=_rt(_resolved(fixture)),
        )
    )


def _run_crossdomain_zeroset(fixture: _corpus.Fixture) -> Any:
    from app.services.chatbot.lanes.business.answer import crossdomain_zeroset

    return _wrap(
        crossdomain_zeroset(
            _rt(_input_json(fixture)),
            parser=_rt(_parser_output(fixture)),
            resolved=_rt(_resolved(fixture)),
            session_block=_rt(_session_block(fixture)),
        )
    )


def _run_crossdomain_render(fixture: _corpus.Fixture) -> Any:
    from app.services.chatbot.lanes.business.answer import crossdomain_render

    zeroset = _named(fixture, "crossdomain-zeroset") or {}
    return _wrap(
        crossdomain_render(
            _rt(_input_json(fixture)),
            zeroset=_rt(zeroset.get("_xd") or {}),
            validator=_rt(_named(fixture, "validator") or {}),
        )
    )


def _run_build_result(fixture: _corpus.Fixture) -> Any:
    from app.services.chatbot.lanes.business.answer import build_result

    call = _named(fixture, "Call 'sub-fetch-results'")
    tool = (call or {}).get("tool") if call is not None else _named(fixture, "tool-filter")
    tier_probe = (call or {}).get("tier_probe") if call is not None else None
    crossdomain_render = _named(fixture, "crossdomain-render")
    return _wrap(
        build_result(
            _rt(_input_json(fixture)),
            validator=_rt(_named(fixture, "validator") or {}),
            promo=_rt(_named(fixture, "promo-picker") or {}),
            zeroset=_rt(_named(fixture, "crossdomain-zeroset") or {}),
            tool=_rt(tool) if tool is not None else None,
            tier_probe=_rt(tier_probe) if tier_probe is not None else None,
            crossdomain_render=_rt(crossdomain_render) if crossdomain_render is not None else None,
        )
    )


def _run_not_found_error_message(fixture: _corpus.Fixture) -> Any:
    from app.services.chatbot.lanes.business.answer import not_found_error_message

    return _wrap(
        not_found_error_message(
            _rt(_input_json(fixture)),
            parser=_rt(_parser_output(fixture)),
            resolved=_rt(_resolved(fixture)),
            gate=_rt(_gate(fixture)),
        )
    )


def _run_access_level_choice_message(fixture: _corpus.Fixture) -> Any:
    from app.services.chatbot.lanes.business.answer import access_level_choice_message

    return _wrap(
        access_level_choice_message(
            _rt(_input_json(fixture)),
            parser=_rt(_parser_output(fixture)),
        )
    )


def _get_results(fixture: _corpus.Fixture) -> list | None:
    """`$('Call \\'sub-get-results\\'').all(0, ri)` for `ri` in `0..24` (D2's alternatives
    scan): a list of RUNS, each run itself a list of that run's own `.json` bodies. The
    harness only ever captures run 0 (the comment on the node itself: "get-results runs
    EXACTLY ONCE per turn"), so this wraps that one run rather than inventing the others -
    `None` when the node never ran at all, matching the node's own `isExecuted` guard."""
    items = fixture.upstream("Call 'sub-get-results'")
    if not items:
        return None
    return [[i.get("json") for i in items]]


def _execution_id(fixture: _corpus.Fixture) -> Any:
    """`$execution.id`, off the fixture's own capture metadata (same read as
    `test_replay.py::_execution_id`, informal here since no fixture lacks it)."""
    return (fixture.data.get("execution") or {}).get("id") or (
        fixture.data.get("source") or {}
    ).get("execution_id")


def _run_build_suggest_offer(fixture: _corpus.Fixture) -> Any:
    from app.services.chatbot.lanes.business.answer import build_suggest_offer

    dym_annotate = _named(fixture, "dym-annotate")
    sibling_probe = _named(fixture, "sibling-probe")
    sibling_transform = _named(fixture, "sibling-transform")
    get_results = _get_results(fixture)
    return _wrap(
        build_suggest_offer(
            _rt(_input_json(fixture)),
            parser=_rt(_parser_output(fixture)),
            resolved=_rt(_resolved(fixture)),
            gate=_rt(_gate(fixture)),
            dym_annotate=_rt(dym_annotate) if dym_annotate is not None else None,
            sibling_probe=_rt(sibling_probe) if sibling_probe is not None else None,
            sibling_transform=_rt(sibling_transform) if sibling_transform is not None else None,
            get_results=_rt(get_results) if get_results is not None else None,
            execution_id=_execution_id(fixture),
        )
    )


def _run_answer_input(fixture: _corpus.Fixture) -> Any:
    """`answer-input`: `sub-answer`'s item carrier. Reads the sub's OWN trigger
    (`$('When Executed by Another Workflow').first().json.item`) POSITIONALLY-blind -
    never `$input` - and raises if the trigger carried no `item` object."""
    from app.services.chatbot.lanes.business.sub_answer import answer_input

    trigger = fixture.first("When Executed by Another Workflow")
    return _wrap(answer_input(_rt(trigger)))


def _run_central_exchange(fixture: _corpus.Fixture) -> Any:
    from app.services.chatbot.lanes.business.sub_answer import central_exchange

    return _wrap(central_exchange(_rt(_input_json(fixture))))


def _run_miss_roster_check(fixture: _corpus.Fixture) -> Any:
    from app.services.chatbot.lanes.business.sub_answer import miss_roster_check

    build_result_out = _named(fixture, "build-result") or {}
    return _wrap(
        miss_roster_check(
            _rt(_input_json(fixture)),
            build_result=_rt(build_result_out.get("result") or {}),
            parser=_rt(_parser_output(fixture)),
        )
    )


def _run_miss_roster_plan(fixture: _corpus.Fixture) -> Any:
    """`build_result.tool.name` is `build-result`'s own shape when that consolidated node
    ran (the `sub-main-processing`/clone-sub-main-processing slugs). The LIVE SPINE has no
    such node - its own `miss-roster-plan.js` reads `$('tool-filter').first().json` for
    the tool DIRECTLY - so the fallback rebuilds the same `{tool: ...}` shape from
    `tool-filter`'s own output when `build-result` never ran."""
    from app.services.chatbot.lanes.business.sub_answer import miss_roster_plan

    build_result_out = _named(fixture, "build-result")
    if build_result_out is not None:
        build_result = build_result_out.get("result") or {}
    else:
        tool = _named(fixture, "tool-filter")
        build_result = {"tool": tool} if tool is not None else {}
    central_exchange = _named(fixture, "central-exchange")
    return _wrap(
        miss_roster_plan(
            _rt(_input_json(fixture)),
            build_result=_rt(build_result),
            parser=_rt(_parser_output(fixture)),
            gate=_rt(_gate(fixture)),
            central_exchange=_rt(central_exchange) if central_exchange is not None else None,
        )
    )


def _run_build_miss_member_offer(fixture: _corpus.Fixture) -> Any:
    from app.services.chatbot.lanes.business.sub_answer import build_miss_member_offer

    return _wrap(
        build_miss_member_offer(
            _rt(_input_json(fixture)),
            central_exchange=_rt(_named(fixture, "central-exchange") or {}),
            roster_plan=_rt(_named(fixture, "miss-roster-plan") or {}),
        )
    )


def _run_dym_transform_partial(fixture: _corpus.Fixture) -> Any:
    from app.services.chatbot.lanes.business.sub_answer import dym_transform_partial

    central_exchange = _named(fixture, "central-exchange")
    return _wrap(
        dym_transform_partial(
            _rt(_input_json(fixture)),
            parser=_rt(_parser_output(fixture)),
            gate=_rt(_gate(fixture)),
            resolved=_rt(_resolved(fixture)),
            central_exchange=_rt(central_exchange) if central_exchange is not None else None,
        )
    )


def _run_dym_annotate_partial(fixture: _corpus.Fixture) -> Any:
    """`dym-annotate-partial.js`'s own by-name reads: `_PAYLOAD_SRC = 'central-exchange'`
    (the payload the downstream renderer expects back), `_XF_SRC = 'dym-transform-partial'`
    (this lane's planner). Neither is optional on this deployment - both are direct
    upstreams of every capture - so absence still threads through as `None` rather than
    being silently skipped."""
    from app.services.chatbot.lanes.business.sub_answer import dym_annotate_partial

    payload = _named(fixture, "central-exchange")
    transform = _named(fixture, "dym-transform-partial")
    return _wrap(
        dym_annotate_partial(
            _rt(_input_json(fixture)),
            payload=_rt(payload) if payload is not None else None,
            transform=_rt(transform) if transform is not None else None,
        )
    )


def _run_answer_result(fixture: _corpus.Fixture) -> Any:
    from app.services.chatbot.lanes.business.sub_answer import answer_result

    central_exchange = _named(fixture, "central-exchange")
    member_offer = _named(fixture, "build-miss-member-offer")
    dym_annotate_partial = _named(fixture, "dym-annotate-partial")
    return _wrap(
        answer_result(
            _rt(_input_json(fixture)),
            central_exchange=_rt(central_exchange) if central_exchange is not None else None,
            member_offer=_rt(member_offer) if member_offer is not None else None,
            dym_annotate_partial=(
                _rt(dym_annotate_partial) if dym_annotate_partial is not None else None
            ),
        )
    )


def _run_dym_transform(fixture: _corpus.Fixture) -> Any:
    """Same `input: null` / `expected: null` pair as `dym-annotate` on the SAME 5
    captures (measured: `clone-spine-RS/rs7-precond-t1/t2/t3`,
    `sub-miss-suggest-rs/rs7-t2-d2-reqspec/rs7-t3-promodym` all carry it here too) -
    `dym-transform` is upstream of `dym-annotate` in the same turn, so if it never ran
    neither did its successor. Checked before the import for the same reason."""
    if not fixture.input:
        return _wrap(None)
    from app.services.chatbot.lanes.business.miss_suggest import dym_transform

    central_exchange = _named(fixture, "central-exchange")
    return _wrap(
        dym_transform(
            _rt(_input_json(fixture)),
            parser=_rt(_parser_output(fixture)),
            resolved=_rt(_resolved(fixture)),
            # `gate` is the UPSTREAM IF that decides whether the require-specific PICKER
            # lane fires (`_dym_plan.picker_cands()` reads `gate.require_specific` /
            # `gate.gate_clarification` / `gate.compatible_entities`) rather than the D1
            # lane - omitting it silently drops every capture into "d1", which is the
            # WRONG lane whenever the gate asked a numbered picker question.
            gate=_rt(_gate(fixture)),
            central_exchange=_rt(central_exchange) if central_exchange is not None else None,
        )
    )


def _run_dym_annotate(fixture: _corpus.Fixture) -> Any:
    """5 captures (`clone-spine-RS/rs7-precond-t1/t2/t3`,
    `sub-miss-suggest-rs/rs7-t2-d2-reqspec/rs7-t3-promodym`) carry `input: null` AND
    `expected: null` together - n8n gave this node ZERO input items in that real
    execution, so its body never ran at all (a Code node with no input items produces
    no output items; `normalizeReturn`'s null branch is the SAME "no items" case, not
    an error). Reproduced by not calling the port at all rather than feeding it a
    fabricated empty dict `fixture.input` was never handed - checked BEFORE the import
    so these 5 grade even before `dym_annotate` itself exists."""
    if not fixture.input:
        return _wrap(None)
    from app.services.chatbot.lanes.business.miss_suggest import dym_annotate

    # `dym-annotate.js`'s own by-name reads: `_PAYLOAD_SRC = 'not-found-error-message'`
    # (the payload the downstream renderer expects back), `_XF_SRC = 'dym-transform'` (this
    # lane's planner). `probe_items = $input.all()` - the FULL input list to this node's own
    # execution, only D18's per-candidate promotion lane reads it.
    payload = _named(fixture, "not-found-error-message")
    transform = _named(fixture, "dym-transform")
    probe_items = [item.get("json") for item in fixture.input]
    return _wrap(
        dym_annotate(
            _rt(_input_json(fixture)),
            payload=_rt(payload) if payload is not None else None,
            transform=_rt(transform) if transform is not None else None,
            probe_items=_rt(probe_items),
        )
    )


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
    return _wrap(
        miss_suggest_result(
            _rt(_input_json(fixture)),
            dym_annotate=_rt(dym_annotate) if dym_annotate is not None else None,
            sibling_transform=_rt(sibling_transform) if sibling_transform is not None else None,
            sibling_probe=_rt(sibling_probe) if sibling_probe is not None else None,
        )
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
    """Same shape as `test_replay.py::_replay` (AC-005): a registered divergence with
    `strip_paths` is FIELD-scoped - those paths come off both sides and the remainder must
    still be byte-equal - while a blanket entry (no `strip_paths`) excuses the whole
    fixture. Applying `strip_paths` here (rather than only checking `registered is not
    None`) is what keeps the dym-transform/dym-annotate stale-spine entries a real,
    field-scoped gate instead of a rubber stamp on any mismatch."""
    actual = _rt(RUNNERS[fixture.node](fixture))
    expected = _rt(fixture.expected)
    registered = divergences.find(fixture.node, fixture.name.split("/")[-1])
    if registered is not None and registered.strip_paths:
        stripped_actual = divergences.strip(actual, registered.strip_paths)
        stripped_expected = divergences.strip(expected, registered.strip_paths)
        assert stripped_actual == stripped_expected, (
            f"{fixture.node}/{fixture.name} diverges outside the registered "
            f"{registered.hazard} fields\nfixture: {fixture.path}"
        )
        return
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
# Coordinator note: the CRM completes `business_query` / `check_promotion` /
# `stock_denied` end to end ONLY when that branch kind is in
# `system_settings.chatbot_completed_lanes` (a JSON list column, default `[]` - new,
# beside `chatbot_stock_denial_enabled` from S3). With the default (empty list) the
# business lane still runs up to S6a's delegate seam
# (`settings.chatbot_business_lane_enabled`) and delegates with `delegate_payload`
# attached, exactly as `test_s6a_gate_dry_run_and_seams.py` already covers - this is
# the SAME decision, gated by a second, independent flag rather than replacing the
# first. `engine._enabled_lanes(db, row)` reads the column off the row the turn already
# read (LESSONS: a new system_settings column needs the two manual dict builders too,
# but that is the FE-facing settings read, not this turn-time gate) and
# `delegate.delegate_for` is the pure predicate over it. The engine-level tests below
# pin the NEW seam `lanes.business.complete_answer` engine.py calls when the branch is
# completed - the coder is free to refine that function's internals, but `run_turn`
# must call it and use its `{reply, actions}` return.
# --------------------------------------------------------------------------- #


# The gate's own unit tests live in `test_completed_lanes_switch.py`, against the ONE
# implementation the engine uses (`delegate.delegate_for` over
# `engine._enabled_lanes`). What is pinned HERE is the wiring below: that `run_turn`
# calls `lanes.business.complete_answer` when the branch is enabled and uses its return.


class TestChatbotCompletedLanesEngineWiring:
    """`engine.run_turn`, on Postgres, exactly like `test_s6a_gate_dry_run_and_seams.py`
    (same fixtures: `session_factory`, `seeded`, `stub_parser`, `stub_access`, plus
    `system_settings_row` from `conftest.py`)."""

    @staticmethod
    def _stub_bundle(calls: list[str]):
        from app.services.chatbot.lanes.business.services import ResolveGateServices

        def _access_types(*, contact_id, space_id):
            calls.append("access_types")
            return [{"name": "Sorento Dealer"}]

        def _resolve_entity(body):
            calls.append("resolve_entity")
            return {"tokens": [], "resolutions": [], "unresolved_tokens": []}

        def _probe(**kwargs):
            calls.append("probe")
            return None

        return ResolveGateServices(
            access_types=_access_types, resolve_entity=_resolve_entity, probe=_probe
        )

    def test_default_completed_lanes_still_delegates_with_payload(
        self, session_factory, seeded, stub_parser, stub_access, system_settings_row, monkeypatch
    ) -> None:
        """One case proving the default (`chatbot_completed_lanes` unset, i.e. `[]`)
        still delegates - the S6c completion gate is ADDITIVE to S6a's existing
        `chatbot_business_lane_enabled` seam, never a silent behaviour change for an
        install that has not opted a lane in yet."""
        from app.config import settings
        from app.services.chatbot import engine as engine_mod
        from tests.chatbot.test_engine import _envelope

        monkeypatch.setattr(settings, "chatbot_business_lane_enabled", True)
        calls: list[str] = []
        bundle = self._stub_bundle(calls)
        monkeypatch.setattr(
            engine_mod.business_services,
            "production_services",
            lambda db, *, space_id=None: bundle,
        )
        monkeypatch.setattr(
            engine_mod, "decide", lambda ctx, *, stock_denial_enabled: ("business_query", {})
        )
        stub_parser()
        stub_access()

        result = engine_mod.run_turn(_envelope(), session_factory=session_factory)

        assert result.branch_kind == "business_query"
        assert result.delegate == "business_query"
        assert result.delegate_payload is not None
        assert result.delegate_payload["_exit_kind"] in ("continue", "access_ask", "not_found", "offer")

    def test_seeded_completed_lane_finishes_the_turn_without_delegating(
        self, session_factory, seeded, stub_parser, stub_access, system_settings_row, monkeypatch
    ) -> None:
        from app.config import settings
        from app.models.user import SystemSetting
        from app.services.chatbot import engine as engine_mod
        from tests.chatbot.test_engine import _envelope

        db = session_factory()
        setting = db.query(SystemSetting).filter(SystemSetting.id == system_settings_row.id).one()
        setting.chatbot_completed_lanes = ["business_query"]
        db.commit()

        monkeypatch.setattr(settings, "chatbot_business_lane_enabled", True)
        bundle = self._stub_bundle([])
        monkeypatch.setattr(
            engine_mod.business_services,
            "production_services",
            lambda db, *, space_id=None: bundle,
        )
        monkeypatch.setattr(
            engine_mod, "decide", lambda ctx, *, stock_denial_enabled: ("business_query", {})
        )
        canned_reply = {"text": "Here is what I found.", "quick_replies": []}
        canned_actions = [{"kind": "send_message", "text": "Here is what I found."}]
        monkeypatch.setattr(
            engine_mod.business,
            "complete_answer",
            lambda *args, **kwargs: {"reply": canned_reply, "actions": canned_actions},
            raising=False,
        )
        stub_parser()
        stub_access()

        result = engine_mod.run_turn(_envelope(), session_factory=session_factory)

        assert result.branch_kind == "business_query"
        assert result.delegate is None, (
            "chatbot_completed_lanes named business_query - the turn must finish itself, "
            f"not hand back to n8n (got delegate={result.delegate!r})"
        )
        assert result.reply == canned_reply
        assert result.actions == canned_actions


class TestAC604FetchErrorIsAnOutcomeNotAnEmptyTurn:
    """H11 / AC-604: "no tool matched" and "the read did not come back" are answers.

    `fetch-result`'s `error` arm used to leave `business_completes` False, so a turn on a
    lane the owner had switched ON still closed `delegated` at `looked_up` and returned
    `delegate = "business_query"` - and once n8n's Switch output is deleted (AC-610) that
    is the empty turn H11 names. Both switch positions are graded.
    """

    @staticmethod
    def _error_fragment() -> dict:
        return {
            "kind": "error",
            "_fetch_arm": "error",
            "error": "no MCP tool matched this question",
            "outcome": "not_found",
            "fetch": {"_fetch_arm": "error", "error": "no MCP tool matched this question"},
        }

    def _wire(self, engine_mod, monkeypatch, calls: list) -> None:
        from app.config import settings

        monkeypatch.setattr(settings, "chatbot_business_lane_enabled", True)
        bundle = TestChatbotCompletedLanesEngineWiring._stub_bundle([])
        monkeypatch.setattr(
            engine_mod.business_services,
            "production_services",
            lambda db, *, space_id=None: bundle,
        )
        monkeypatch.setattr(
            engine_mod, "decide", lambda ctx, *, stock_denial_enabled: ("business_query", {})
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
            engine_mod.business, "run_fetch", lambda *args, **kwargs: self._error_fragment()
        )
        monkeypatch.setattr(
            engine_mod.business,
            "complete_answer",
            lambda payload, **kwargs: calls.append(payload)
            or {"reply": {"text": "Couldn't find that.", "quick_replies": []}, "actions": []},
            raising=False,
        )

    def test_with_the_lane_on_the_crm_answers_the_not_found_itself(
        self, session_factory, seeded, stub_parser, stub_access, system_settings_row, monkeypatch
    ) -> None:
        from app.models.user import SystemSetting
        from app.services.chatbot import engine as engine_mod
        from tests.chatbot.test_engine import _envelope

        db = session_factory()
        setting = db.query(SystemSetting).filter(SystemSetting.id == system_settings_row.id).one()
        setting.chatbot_completed_lanes = ["business_query"]
        db.commit()

        answered: list[dict] = []
        self._wire(engine_mod, monkeypatch, answered)
        stub_parser()
        stub_access()

        result = engine_mod.run_turn(_envelope(), session_factory=session_factory)

        assert answered, "the answer half never ran - the error arm is still an empty turn"
        assert answered[0]["fetch"]["_fetch_arm"] == "error", (
            "the miss lane is reached through the fetch item's own arm"
        )
        assert result.delegate is None
        assert result.reply == {"text": "Couldn't find that.", "quick_replies": []}

    def test_with_the_lane_off_it_still_delegates_and_records_the_reason(
        self, session_factory, seeded, stub_parser, stub_access, system_settings_row, monkeypatch
    ) -> None:
        from app.services.chatbot import engine as engine_mod
        from tests.chatbot.test_engine import _envelope

        assert (system_settings_row.chatbot_completed_lanes or []) == []
        answered: list[dict] = []
        self._wire(engine_mod, monkeypatch, answered)
        stub_parser()
        stub_access()

        result = engine_mod.run_turn(_envelope(), session_factory=session_factory)

        assert not answered, "the lane is switched off - n8n answers this turn"
        assert result.delegate == "business_query"
        assert result.stage == "looked_up", (
            "a delegated fetch error stops at looked_up so the operator's query finds it"
        )


class TestErrorArmRendersTheMissLane:
    """The other half of AC-604: what `complete_answer` DOES with the error arm.

    The miss lane runs on it (`not-found-error-message` then `build-suggest-offer`), so
    the customer gets the itemised miss and the escalate offer rather than silence.
    """

    def test_the_error_arm_reaches_the_miss_renderer(self, monkeypatch) -> None:
        from app.services.chatbot import engine as engine_mod
        from app.services.chatbot.lanes.business import complete_answer
        from app.services.chatbot.lanes.business.services import AnswerServices

        captured: dict[str, Any] = {}

        class _Completed:
            reply = {"text": "stub", "quick_replies": []}
            actions: list = []
            session_patch = None
            status = "done"
            stage = "remembered"

        def _complete_turn(turn_id, fragments, *, session_factory, compose_send_action=False):
            captured["fragments"] = fragments
            return _Completed()

        monkeypatch.setattr(engine_mod, "complete_turn", _complete_turn)

        ctx = {
            "contact": {"id": "c1"},
            "parse": {
                "output": {
                    "message_type": "business_query",
                    "intent_hint": "check_stock",
                    "domain_hint": "inventory",
                    "user_goal": "stock for SRTWC8517",
                    "entities": [{"raw": "SRTWC8517", "hint": "product"}],
                    "access_levels": [],
                }
            },
            "session": {},
        }
        payload = {
            "_exit_kind": "continue",
            "resolved": {"unresolved_tokens": ["SRTWC8517"], "resolutions": [], "by_entity_type": {}},
            "gate": {"gate_passed": True, "gate_debug": {"domain": "inventory"}, "compatible_entities": []},
            "fetch": {
                "_fetch_arm": "error",
                "error": "no MCP tool matched this question",
                # R2-S2: a genuine ABSENCE (zero tools matched), not an outage - without
                # this key `complete_answer` now reads the arm as an infrastructure
                # failure and raises instead of rendering the miss lane.
                "outcome": "not_found",
            },
        }

        complete_answer(
            payload,
            turn_id="t1",
            ctx=ctx,
            item={},
            branch_kind="business_query",
            services=AnswerServices(
                mcp_probe=lambda name, args: {"answers": [], "has_result": False},
                family_fetch=lambda query: {"data": []},
            ),
            session_factory=lambda: None,
        )

        fragments = captured["fragments"]
        assert "not_found" in fragments, "the error arm must render the miss lane"
        assert "SRTWC8517" in fragments["not_found"]["escalate_message"]


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
        session_block = {"session_vars": {"variables": {}}}
        validator_result = {
            "answers": [{"fields": [{"label": "Product Code", "value": "SRTOTHER"}]}],
            "response": "Some other stock line.",
        }

        zeroset = crossdomain_zeroset(
            validator_result, parser=parser, resolved=resolved, session_block=session_block
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
            session_block=session_block,
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


class TestCrossdomainRenderRowOrder:
    """`crossdomain-render.js:96,101-102`: quantity desc when ANY row has a quantity,
    otherwise soonest ETA first.

    The incoming direction is the one that has no quantity at all:
    `sorento_crm_mcp/presenters.py::_incoming_list` emits `estimated_arrival_date`
    (label "ETA") and never a `quantity_on_hand` key, so `fieldPref` misses and JS's
    `?? NaN` sends every one of those rows down the ETA branch. Reading the miss as
    `Number(null) === 0` instead would make the quantity branch win for a set that
    carries no quantity, and the rows would come back in the CRM's own order - which
    the node's comment (crossdomain-render.js:88-90) records as jittery between calls.
    """

    @staticmethod
    def _incoming_row(code: str, eta: str) -> dict:
        """One `crm_incoming_stock_list` item, in the presenter's own shape."""
        return {
            "fields": [
                {"key": "product_code", "label": "Product Code", "value": code},
                {"key": "estimated_arrival_date", "label": "ETA", "value": eta},
            ]
        }

    def _render(self, rows: list[dict]) -> str:
        from app.services.chatbot.lanes.business.answer import crossdomain_render

        out = crossdomain_render(
            {"items": rows, "has_result": True},
            zeroset={
                "active": True,
                "origin_domain": "inventory",
                "team": "warehouse",
                "missing": [{"code": "SRTWC8517", "_n": "SRTWC8517", "uuid": "u1"}],
            },
            validator={},
        )
        return out["_xdBlock"]["block"]

    def test_rows_with_no_quantity_key_sort_by_soonest_eta(self) -> None:
        rows = [
            self._incoming_row("SRTWC8517", "2026-11-30"),
            self._incoming_row("SRTWC8517", "2026-09-15"),
            self._incoming_row("SRTWC8517", "2026-10-02"),
        ]
        block = self._render(rows)
        order = re_mod.findall(r"\*ETA:\* (\d{4}-\d{2}-\d{2})", block)
        assert order == ["2026-09-15", "2026-10-02", "2026-11-30"], (
            "an absent quantity_on_hand key must read as NaN (JS `?? NaN`), not 0 - "
            "with 0 the quantity branch wins and the incoming rows keep the CRM's "
            f"own jittery order: {order}"
        )

    def test_a_present_quantity_still_wins_over_eta(self) -> None:
        """Parity in the other direction: one real quantity anywhere in the set and the
        quantity branch takes it, placeholder rows sorting as 0 (`_qty(b) || 0`)."""
        rows = [
            {
                "fields": [
                    {"key": "product_code", "label": "Product Code", "value": "SRTWC8517"},
                    {"key": "quantity_on_hand", "label": "Quantity On Hand", "value": 2},
                    {"key": "estimated_arrival_date", "label": "ETA", "value": "2026-09-15"},
                ]
            },
            {
                "fields": [
                    {"key": "product_code", "label": "Product Code", "value": "SRTWC8517"},
                    {"key": "quantity_on_hand", "label": "Quantity On Hand", "value": 9},
                    {"key": "estimated_arrival_date", "label": "ETA", "value": "2026-11-30"},
                ]
            },
        ]
        block = self._render(rows)
        assert re_mod.findall(r"\*Quantity On Hand:\* (\d+)", block) == ["9", "2"]


# --------------------------------------------------------------------------- #
# AC-607: the miss lane - dym-transform, its probes, family-fetch (never a raw IP,
# H52's family-fetch half; D10), then build-suggest-offer.
# --------------------------------------------------------------------------- #


class TestMissLaneProbesAndFamilyFetch:
    def test_not_found_path_probes_and_fetches_the_family_before_offering(self) -> None:
        """`_sibling_gate` (`sibling-gate`'s own four AND conditions, verbatim) is the ONE
        branch where `family_fetch` AND `mcp_probe` both fire on the same turn - `run_miss_lane`
        docstring's graph: `sibling-gate TRUE -> family-fetch -> sibling-transform ->
        sibling-probe`. It requires an `incoming`-domain gate with a non-uuid product code in
        `compatible_entities`, `require_specific` not True, and a `build_result` whose own
        `has_result` is False - the `dym-transform` branch below it (FALSE) never calls
        `family_fetch` at all, so a gate that fails these four conditions grades the wrong
        branch."""
        from app.services.chatbot.lanes.business.miss_suggest import run_miss_lane
        from app.services.chatbot.lanes.business.services import AnswerServices

        parser = {
            "message_type": "business_query",
            "intent_hint": "check_stock",
            "domain_hint": "incoming",
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
                            "uuid": "11111111-1111-1111-1111-111111111111",
                            "match_tier": "prefix",
                        }
                    ],
                }
            ],
        }
        gate = {
            "gate_passed": False,
            "gate_reason": "no exact match",
            "gate_debug": {"domain": "incoming"},
            "require_specific": False,
            "compatible_entities": [
                {"entity_type": "product", "code": "SRTWC286", "uuid": None},
            ],
        }
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
            not_found_item,
            parser=parser,
            resolved=resolved,
            gate=gate,
            services=services,
            # `_sibling_gate`'s fourth condition: the fetch genuinely came back empty.
            build_result={"has_result": False},
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

    def test_a_failed_dym_probe_still_offers_the_did_you_mean(self) -> None:
        """`dym-probe` is the ONE node in `sub-miss-suggest-live/workflow.json` (and the
        same node on the live spine) that carries an `onError`, and it is
        `continueRegularOutput`: the probe fails, an item is still emitted,
        `dym-annotate` runs on it and the customer gets the BARE offer. Unwrapped, an
        MCP timeout here propagates out of `complete_answer` and the turn answers with
        `GENERIC_ERROR_REPLY` instead."""
        from app.services.chatbot.lanes.business.miss_suggest import run_miss_lane
        from app.services.chatbot.lanes.business.services import AnswerServices

        parser = {
            "message_type": "business_query",
            "intent_hint": "check_stock",
            "domain_hint": "inventory",
            "user_goal": "stock for SRTWC286",
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
                            "uuid": "11111111-1111-1111-1111-111111111111",
                            "match_tier": "prefix",
                        }
                    ],
                }
            ],
        }
        # `gate_debug.domain` is inventory, so `sibling-gate` is FALSE and the turn takes
        # the `dym-transform -> dym-probe` leg rather than the family one.
        gate = {
            "gate_passed": False,
            "gate_reason": "no exact match",
            "gate_debug": {"domain": "inventory"},
            "require_specific": False,
            "compatible_entities": [],
        }
        probes: list[str] = []

        def mcp_probe(name: str, args: dict) -> dict:
            probes.append(name)
            raise RuntimeError("MCP read timed out")

        out = run_miss_lane(
            {"escalate_message": "Could not find product SRTWC286.", "is_clarification": False},
            parser=parser,
            resolved=resolved,
            gate=gate,
            services=AnswerServices(mcp_probe=mcp_probe, family_fetch=lambda q: {"data": []}),
            build_result={"has_result": False},
        )

        assert probes, "the did-you-mean probe never ran - this test grades the wrong branch"
        offer = out.get("dym_offer") or {}
        assert [c["code"] for c in offer.get("candidates") or []] == ["SRTWC286-SH"], (
            "a failed dym-probe must still reach the offer (onError: continueRegularOutput)"
        )

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
# R1 / H1: the demand-quantity answer. `Edit Fields2` stamps `not_allowed_check_stock`
# on the ONE edge `If7`'s TRUE output takes, and `validator` reads it to replace the raw
# stock rows with "Quantity of N for product X can/cannot be fulfilled." Both switch
# positions are graded: with `chatbot_stock_denial_enabled` off no turn can reach the
# arm at all, so nothing is stamped and nothing is rewritten.
# --------------------------------------------------------------------------- #


class TestR1DemandQuantityAnswer:
    @staticmethod
    def _ctx(demand_qty: Any) -> dict:
        return {
            "contact": {
                "id": "ZZT-1",
                "custom_fields": [{"name": "is_allowed_stock", "value": "false"}],
            },
            "text": {"message": {"message": {"type": "text", "text": "5 units of SRTWC8517"}}},
            "session": {"session_vars": {"variables": {}}},
            "parse": {
                "output": {
                    "message_type": "business_query",
                    "intent_hint": "check_stock",
                    "domain_hint": "inventory",
                    "entities": [{"raw": "SRTWC8517", "hint": "product", "current_message": True}],
                    "demand_qty": demand_qty,
                }
            },
            "access": {"allowed": True, "decision": "allow"},
            "media": None,
        }

    @staticmethod
    def _lane(ctx: dict, branch_kind: str) -> dict:
        from app.services.chatbot.lanes.business import run_until_exit
        from app.services.chatbot.lanes.business.services import ResolveGateServices

        services = ResolveGateServices(
            access_types=lambda **_: [],
            resolve_entity=lambda body: {"tokens": [], "resolutions": [], "unresolved_tokens": []},
            probe=lambda **_: None,
        )
        return run_until_exit(
            ctx, {"branch_kind": branch_kind}, branch_kind=branch_kind, services=services
        )

    _ANSWERS = {
        "answers": [
            {"product": "SRTWC8517", "stock_qty": 2},
            {"product": "SRTWC8517", "stock_qty": 1},
        ],
        "response": "Warehouse A: 2\nWarehouse B: 1",
        "has_result": True,
    }

    def test_with_the_switch_on_the_arm_stamps_and_the_answer_is_the_quantity_verdict(
        self,
    ) -> None:
        from app.services.chatbot.head.route import decide
        from app.services.chatbot.lanes.business.answer import validator

        ctx = self._ctx(5)
        branch_kind, _ = decide(ctx, stock_denial_enabled=True)
        assert branch_kind == "stock_denied"

        payload = self._lane(ctx, branch_kind)["payload"]
        assert payload["not_allowed_check_stock"] is True

        out = validator(
            dict(self._ANSWERS),
            semantic_parser=ctx["parse"],
            not_allowed_check_stock=bool(payload.get("not_allowed_check_stock")),
        )
        assert out["response"] == (
            "Quantity of 5 for product SRTWC8517 cannot be fulfilled. "
            "Total available quantity is 3."
        )

    def test_a_demand_the_stock_covers_is_answered_can_be_fulfilled(self) -> None:
        from app.services.chatbot.lanes.business.answer import validator

        out = validator(
            dict(self._ANSWERS),
            semantic_parser=self._ctx(3)["parse"],
            not_allowed_check_stock=True,
        )
        assert out["response"] == "Quantity of 3 for product SRTWC8517 can be fulfilled."

    def test_with_the_switch_off_nothing_is_stamped_and_the_rows_stand(self) -> None:
        """Default R1 position: the route cannot decide `stock_denied` at all, the
        `business_query` arm carries no stamp, and `validator` leaves the fetched
        response untouched."""
        from app.services.chatbot.head.route import decide
        from app.services.chatbot.lanes.business.answer import validator

        ctx = self._ctx(5)
        branch_kind, _ = decide(ctx, stock_denial_enabled=False)
        assert branch_kind == "business_query"

        payload = self._lane(ctx, branch_kind)["payload"]
        assert payload.get("not_allowed_check_stock") is None

        out = validator(
            dict(self._ANSWERS),
            semantic_parser=ctx["parse"],
            not_allowed_check_stock=bool(payload.get("not_allowed_check_stock")),
        )
        assert out["response"] == self._ANSWERS["response"]
        assert out["is_valid"] is True


# --------------------------------------------------------------------------- #
# AC-609 / H45: did-you-mean never re-offers a row the answer already showed.
#
# ONE outcome-level predicate, and it is the LIVE one: `build-suggest-offer.js:288-323`'s
# answered-token rule. "Already shown" means "queried this turn", read off
# `gate.compatible_entities` by UUID - outside REQUIRE_SPECIFIC domains the gate lifts
# every compatible match of an ambiguous token into that list and the fetch queries them
# all, so the miss that reaches the offer is the CRM's ANSWER over those candidates.
# Applied per CANDIDATE, not per token: a candidate the gate never lifted is still a real
# suggestion, and a token left with none is named in `dym_answered_tokens` rather than
# silently dropped. Graded through `run_miss_lane`, the lane's own entry point, so the
# rule is proven where the offer is actually built.
# --------------------------------------------------------------------------- #


class TestH45NoReofferOfAnsweredRows:
    _UF = "11111111-1111-1111-1111-111111111111"
    _200 = "22222222-2222-2222-2222-222222222222"
    _PARSER = {
        "message_type": "business_query",
        "intent_hint": "check_stock",
        "domain_hint": "inventory",
        "user_goal": "stock for SRTWC8517",
        "entities": [{"hint": "product", "raw": "SRTWC8517"}],
        "access_levels": [],
    }

    @property
    def _resolved(self) -> dict:
        return {
            "by_entity_type": {},
            "unresolved_tokens": ["SRTWC8517"],
            "resolutions": [
                {
                    "token": "SRTWC8517",
                    "matches": [
                        {
                            "entity_type": "product",
                            "canonical_code": "SRTWC8517-SH-UF",
                            "uuid": self._UF,
                            "match_tier": "prefix",
                        },
                        {
                            "entity_type": "product",
                            "canonical_code": "SRTWC8517-SH-200",
                            "uuid": self._200,
                            "match_tier": "prefix",
                        },
                    ],
                }
            ],
        }

    def _offer(self, compatible_entities: list[dict]) -> dict:
        from app.services.chatbot.lanes.business.miss_suggest import run_miss_lane
        from app.services.chatbot.lanes.business.services import AnswerServices

        return run_miss_lane(
            {"escalate_message": "Could not find product SRTWC8517.", "is_clarification": False},
            parser=self._PARSER,
            resolved=self._resolved,
            gate={
                "gate_passed": False,
                "gate_reason": "no exact match",
                "gate_debug": {"domain": "inventory"},
                "require_specific": False,
                "compatible_entities": compatible_entities,
            },
            services=AnswerServices(
                mcp_probe=lambda name, args: {"answers": [], "has_result": False},
                family_fetch=lambda query: {"data": []},
            ),
            build_result={"has_result": False},
        )

    @staticmethod
    def _entity(uuid: str, code: str) -> dict:
        return {"entity_type": "product", "uuid": uuid, "code": code}

    def test_a_candidate_the_answer_already_queried_is_not_offered_again(self) -> None:
        out = self._offer([self._entity(self._UF, "SRTWC8517-SH-UF")])
        codes = [c["code"] for c in (out.get("dym_offer") or {}).get("candidates") or []]
        assert codes == ["SRTWC8517-SH-200"], (
            "SRTWC8517-SH-UF was queried this turn (its uuid is in compatible_entities), "
            f"so the offer must not hand it back: {codes}"
        )

    def test_a_token_whose_candidates_were_all_queried_leaves_the_offer_named(self) -> None:
        out = self._offer(
            [
                self._entity(self._UF, "SRTWC8517-SH-UF"),
                self._entity(self._200, "SRTWC8517-SH-200"),
            ]
        )
        assert out.get("dym_offer") is None, "the whole token was answered - there is nothing to offer"
        assert out.get("dym_answered_tokens") == ["SRTWC8517"], (
            "a token that loses every candidate is NAMED, never a silent drop"
        )

    def test_an_empty_compatible_entities_excludes_nothing(self) -> None:
        """UAC SR-U5: a genuine miss is never silenced. Nothing was queried, so both
        candidates are still real suggestions."""
        out = self._offer([])
        codes = [c["code"] for c in (out.get("dym_offer") or {}).get("candidates") or []]
        assert codes == ["SRTWC8517-SH-UF", "SRTWC8517-SH-200"]
        assert out.get("dym_answered_tokens") is None


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
# offer must not pollute an inventory-domain crossdomain probe.
#
# The guard is `sub-main-processing-live`'s `_offerDomainOk` ("DOMAIN GUARD 2026-09-01"),
# and the ACTIVE spine's copy of the node does NOT carry it, so this is a registered CRM
# divergence (`divergences.CROSSDOMAIN_DYM_OFFER_DOMAIN_GUARD`, with both shas) and these
# are the tests it is registered against. No capture grades it: all five predate it.
# --------------------------------------------------------------------------- #


class TestH22H23DymOfferDomainCleared:
    def test_a_promotion_threads_carried_pick_is_not_read_on_an_inventory_turn(self) -> None:
        from app.services.chatbot.lanes.business.answer import crossdomain_zeroset

        parser = {"message_type": "business_query", "domain_hint": "inventory"}
        resolved = {}
        session_block = {
            "session_vars": {
                "variables": {"dym_offer": {"domain": "promotion", "picked": ["SRT-OLD-PICK"]}}
            }
        }
        validator_result = {"answers": [], "response": "no rows"}

        out = crossdomain_zeroset(
            validator_result, parser=parser, resolved=resolved, session_block=session_block
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
        session_block = {
            "session_vars": {
                "variables": {"dym_offer": {"domain": "inventory", "picked": ["SRT-SAME-DOMAIN"]}}
            }
        }
        validator_result = {"answers": [], "response": "no rows"}

        out = crossdomain_zeroset(
            validator_result, parser=parser, resolved=resolved, session_block=session_block
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
        session_block = {"session_vars": {"variables": {}}}
        validator_result = {"answers": [], "response": "no rows"}
        zeroset = crossdomain_zeroset(
            validator_result, parser=parser, resolved=resolved, session_block=session_block
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
            session_block=session_block,
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
