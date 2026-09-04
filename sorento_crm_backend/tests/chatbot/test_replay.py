"""Node replay: every ported node against the captured n8n executions (AC-004, AC-005).

This is the whole reason the port is worth doing. Each fixture is a real turn that ran
in production or on the fail-closed clone; the Python port is fed the SAME upstream
values and its output must equal what n8n recorded, byte for byte after a JSON round
trip. A disagreement fails unless `divergences.py` registers it with a hazard id.

Two parametrisations per node: the vendored subset (always) and the full corpus (skips
with a message when the sibling n8n checkout is absent). Nothing here touches a database,
the network, or an LLM - these are pure functions over captured JSON.
"""
from __future__ import annotations

import pytest

from tests.chatbot import _corpus, divergences

# --------------------------------------------------------------------------- #
# One runner per ported node. The runner reproduces the node's n8n execution
# mode: `runOnceForAllItems` returns the whole item list from one call, while
# `runOnceForEachItem` runs once per input item and concatenates.
# --------------------------------------------------------------------------- #


def _run_build_ctx(fixture: _corpus.Fixture) -> list:
    from app.services.chatbot.head.build_ctx import build_ctx

    return build_ctx(
        contact=fixture.first("sorento-sub-respond-findcontact-respond"),
        text=fixture.first("tf-message"),
        session=fixture.first("get-session-vars"),
        parse=fixture.first("Call 'sub-query-reformulator'"),
        access=fixture.first("check-access"),
        media=(fixture.first("media-intake") or {}).get("media")
        if fixture.upstream("media-intake")
        else None,
    )


def _run_route_turn(fixture: _corpus.Fixture) -> list:
    """Graded with the R1 flag OFF, and bounded with it ON (review S9).

    OFF is what production runs, so that is where parity is graded. ON is R1's whole
    point: the corrected `check_stock` vocabulary WAKES the two lanes live has had dead by
    typo, so some captured turns legitimately route differently under it - four in the
    corpus today, all of them real `check_stock` turns from contacts with no stock access
    (rs1a-15118057, 15129939, 15137785, 15139158). Those are the first evidence the lane
    would fire at all.

    Replaying only one flag value would grade one deployment and say nothing about the
    other, so this does both and asserts the BLAST RADIUS: a turn may only move under the
    flag if it is a `check_stock` turn moving into `stock_denied` / `demand_qty`. Anything
    else diverging is the flag reaching somewhere R1 never authorised, and fails here.
    """
    from app.services.chatbot.head.route import route_turn

    ctx = fixture.first("build-ctx")["ctx"]
    off = route_turn(ctx, stock_denial_enabled=False)
    try:
        on = route_turn(ctx, stock_denial_enabled=True)
    except TypeError:
        # Live's own expression throws on a contact with no `is_allowed_stock` field, and
        # the port reproduces that with the flag on. Nothing to compare; OFF is the graded
        # value either way. (Plan hazard table, H1 row.)
        return off
    if on != off:
        qf = jsc_output(ctx)
        on_branch = (on[0].get("json") or {}).get("branch_kind")
        assert qf.get("intent_hint") == "check_stock" and on_branch in (
            "stock_denied",
            "demand_qty",
        ), (
            f"{fixture.node}/{fixture.name} moves under chatbot_stock_denial_enabled but "
            f"is not a check_stock turn landing in a stock lane: intent="
            f"{qf.get('intent_hint')!r}, off={(off[0].get('json') or {}).get('branch_kind')!r}, "
            f"on={on_branch!r}. R1 authorises the stock lanes and nothing else."
        )
    return off


def jsc_output(ctx: dict) -> dict:
    """`ctx.parse.output` - the parser's post-processed emission, defensively."""
    return ((ctx or {}).get("parse") or {}).get("output") or {}


def _run_output_exchange(fixture: _corpus.Fixture) -> list:
    from app.services.chatbot.head.output_exchange import output_exchange

    parent_input = fixture.first("When Executed by Another Workflow")
    out = []
    for item in fixture.input:
        out.append({"json": output_exchange(item.get("json") or {}, parent_input)})
    return out


def _run_suggest_follow_up(fixture: _corpus.Fixture) -> list:
    from app.services.chatbot.head.output_exchange import suggest_follow_up

    parent_input = fixture.first("When Executed by Another Workflow")
    first = (fixture.input[0] or {}).get("json") or {}
    return [{"json": suggest_follow_up(first, parent_input)}]


# --------------------------------------------------------------------------- #
# S2, the tail. Two shapes of capture, and the difference is a BODY difference,
# not a divergence: the live spine's `compile-current-state` predates RS-3 half
# H2 and returns `{variables, user_response, quick_reply}` bare, while the body
# the export ships (and the port) re-seals it as `{reply: {text, quick_replies,
# session_patch}}`. `_unwrap_reply` grades whichever shape the fixture recorded,
# so 135 live captures stay gradeable instead of being written off.
# --------------------------------------------------------------------------- #


def _ctx_of(fixture: _corpus.Fixture) -> dict:
    """The six-key hub, from the `build-ctx` node every captured graph carries."""
    return fixture.first("build-ctx")["ctx"]


def _ran(fixture: _corpus.Fixture, node: str):
    """`$('node').isExecuted ? $('node').first().json : null`, off the capture."""
    items = fixture.upstream(node)
    return (items[0] or {}).get("json") if items else None


def _producers(fixture: _corpus.Fixture) -> dict:
    """`build-outcome`'s by-name reads, resolved off the capture's own `ctx`.

    A key that is ABSENT means the producer did not run (or is not in that graph), which
    is what `_one`'s `catch` also reports as null - so absence and null are the same
    statement here, exactly as they are in the node.
    """
    from app.services.chatbot.tail.outcome import OUTCOME_KEYS

    out = {}
    for key in OUTCOME_KEYS:
        items = fixture.upstream(key)
        if not items:
            continue
        if key == "cs-roster-plan":
            out[key] = [(i or {}).get("json") for i in items]  # the ONE multi-item read
        else:
            out[key] = (items[0] or {}).get("json")
    return out


def _execution_id(fixture: _corpus.Fixture) -> str:
    """`$execution.id`. A hand-built fixture has none, and the n8n shim calls it "test".

    Not cosmetic: a dym offer BORN this turn stamps the execution id as its identity, so
    the wrong value here fails 18 fixtures on a field that is a harness constant, not a
    behaviour.
    """
    return str((fixture.data.get("source") or {}).get("execution_id") or "test")


def _run_build_outcome(fixture: _corpus.Fixture) -> list:
    from app.services.chatbot.tail.outcome import build_outcome

    return build_outcome(fixture.input, _producers(fixture))


def _run_escalate_catalog(fixture: _corpus.Fixture) -> list:
    from app.services.chatbot.copy import fallback_copy
    from app.services.chatbot.tail.outcome import escalate_catalog

    return [
        {
            "json": escalate_catalog(
                (fixture.input[0] or {}).get("json") or {},
                _ctx_of(fixture),
                fallback_copy(),
                not_found=_ran(fixture, "not-found-error-message"),
                incoming_picker=_ran(fixture, "annotate-incoming-picker"),
                access_choice=_ran(fixture, "access-level-choice-message"),
                suggest_offer=_ran(fixture, "build-suggest-offer"),
                gate=_ran(fixture, "disallowed-entity-gate"),
                offer_hold=_ran(fixture, "offer-hold-reply"),
            )
        }
    ]


def _run_cs_roster_plan(fixture: _corpus.Fixture) -> list:
    from app.services.chatbot.tail.member_offer import cs_roster_plan

    return [{"json": row} for row in cs_roster_plan(_ran(fixture, "disallowed-entity-gate"))]


def _run_build_cs_member_offer(fixture: _corpus.Fixture) -> list:
    from app.services.chatbot.tail.member_offer import build_cs_member_offer

    plan = [(i or {}).get("json") for i in fixture.upstream("cs-roster-plan")]
    responses = [(i or {}).get("json") for i in fixture.input]
    return [
        {
            "json": build_cs_member_offer(
                _ran(fixture, "escalate-catalog") or {},
                plan,
                responses,
            )
        }
    ]


def _run_compile_current_state(fixture: _corpus.Fixture) -> list:
    from app.services.chatbot.tail.compile_state import compile_current_state

    compiled = compile_current_state(
        (fixture.input[0] or {}).get("json") or {},
        _ctx_of(fixture),
        resolved=_ran(fixture, "resolve-entity"),
        gate=_ran(fixture, "disallowed-entity-gate"),
        execution_id=_execution_id(fixture),
    )
    # A pre-RS-3 capture recorded the bare patch; the shipping body seals it. Grading the
    # shape the fixture actually recorded is what keeps 135 live captures gradeable.
    expected_first = (fixture.expected[0] or {}).get("json") if fixture.expected else None
    if isinstance(expected_first, dict) and "reply" not in expected_first:
        return [{"json": compiled.item["reply"]["session_patch"]}]
    return [{"json": compiled.item}]


def _run_crossdomain_compose(fixture: _corpus.Fixture) -> list:
    """The shipping body reads the block off `build-result`; the live body read it off
    `crossdomain-render._xdBlock`. The diff between the two exported bodies is exactly
    that read plus the RS-3 seal, so a live capture is replayed by handing the port the
    SAME block through the shape it expects, rather than being written off as stale.
    """
    from app.services.chatbot.tail.compile_state import seal
    from app.services.chatbot.tail.compose import crossdomain_compose

    raw = (fixture.input[0] or {}).get("json") or {}
    sealed = "reply" in raw
    item = raw if sealed else {"reply": seal(raw)}
    patch = item["reply"]["session_patch"]

    build_result = _ran(fixture, "build-result")
    if build_result is not None:
        result = build_result
    else:
        render = _ran(fixture, "crossdomain-render")
        result = (
            {"result": {"xd": {"block": (render or {}).get("_xdBlock")}}}
            if render is not None
            else None
        )

    # The port takes `answered` as a VALUE (R3 / D11: no reading a reply back with a
    # regex). The capture predates the marker, so the replay derives the same fact the
    # JS derived, from the state the fixture recorded.
    previous = ((patch.get("variables") or {}).get("response"))
    answered = isinstance(previous, str) and previous.startswith("Previous turn (")

    out = crossdomain_compose(item, result=result, answered=answered)
    return [{"json": out if sealed else out["reply"]["session_patch"]}]


RUNNERS = {
    "build-ctx": _run_build_ctx,
    "route-turn": _run_route_turn,
    "output_exchange": _run_output_exchange,
    "suggest-follow-up": _run_suggest_follow_up,
    "build-outcome": _run_build_outcome,
    "escalate-catalog": _run_escalate_catalog,
    "cs-roster-plan": _run_cs_roster_plan,
    "build-cs-member-offer": _run_build_cs_member_offer,
    "compile-current-state": _run_compile_current_state,
    "crossdomain-compose": _run_crossdomain_compose,
}

PORTED_NODES = sorted(RUNNERS)


def _replay(fixture: _corpus.Fixture) -> None:
    if not _corpus.is_graded(fixture):
        # A `reasoned` fixture is a claim about intended behaviour, not a record of a
        # real execution. Replaying the port against it grades the port against whoever
        # wrote the claim, and a mismatch is an argument, not a defect. It is still RUN,
        # so a crash in the port shows up; only the comparison is withheld.
        RUNNERS[fixture.node](fixture)
        pytest.skip(
            f"{fixture.node}/{fixture.name}: expected_from="
            f"{(fixture.data.get('source') or {}).get('expected_from')!r}, informational "
            "(gate 0 counts real captures only)"
        )
    actual = _corpus.json_round_trip(RUNNERS[fixture.node](fixture))
    expected = _corpus.json_round_trip(fixture.expected)
    registered = divergences.find(fixture.node, fixture.name.split("/")[-1])
    if registered is not None and registered.strip_paths:
        # A FIELD-scoped divergence: the named paths come off BOTH sides and the rest of
        # the fixture is still graded byte for byte. A blanket pass here would make the
        # node's whole replay vacuous for the sake of one added key.
        actual = divergences.strip(actual, registered.strip_paths)
        expected = divergences.strip(expected, registered.strip_paths)
        assert actual == expected, (
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


def _ids(fixtures: list[_corpus.Fixture]) -> list[str]:
    return [f.name for f in fixtures]


@pytest.mark.parametrize(
    ("node", "name", "reason"),
    _corpus.stale_entries(),
    ids=lambda v: v if isinstance(v, str) and "/" not in v else "",
)
def test_stale_capture_is_skipped_with_its_reason(node: str, name: str, reason: str) -> None:
    """Every excluded capture SAYS SO in the summary rather than vanishing.

    A fixture silently dropped from the parametrisation is coverage the suite quietly
    stopped having. One skip per entry means `pytest -rs` lists them and the run's own
    skip count is the number of captures not being graded.
    """
    root = _corpus.corpus_root()
    if root is not None:
        # A dead exclusion is only detectable where the corpus actually is. In the CI
        # shape (vendored subset only) a stale capture is legitimately absent from disk:
        # it is excluded from vendoring precisely BECAUSE it cannot be graded.
        on_disk = (_corpus.VENDORED_ROOT / node / f"{name}.json").exists() or any(
            (root / "nodes" / slug / node / f"{name}.json").exists()
            for slug in _corpus.NODE_SLUGS.get(node, ())
        )
        assert on_disk, (
            f"{node}/{name} is registered stale but no such fixture exists - retire the "
            "STALE_FIXTURES entry rather than leaving a dead exclusion in place"
        )
    pytest.skip(f"stale capture {node}/{name}: {reason}")


@pytest.mark.parametrize("node", PORTED_NODES)
def test_vendored_subset_is_present(node: str) -> None:
    """The committed subset is the CI gate; an empty directory would make it vacuous."""
    assert _corpus.vendored(node), (
        f"no vendored fixtures for {node} under tests/fixtures/chatbot/nodes/{node}/ - "
        "the always-on replay gate would pass by having nothing to check"
    )


@pytest.mark.parametrize(
    "fixture",
    [f for node in PORTED_NODES for f in _corpus.vendored(node)],
    ids=lambda f: f"{f.node}/{f.name}",
)
def test_vendored_replay(fixture: _corpus.Fixture) -> None:
    _replay(fixture)


@pytest.mark.parametrize(
    "fixture",
    [f for node in PORTED_NODES for f in _corpus.full_corpus(node)] or [None],
    ids=lambda f: f"{f.node}/{f.name}" if f is not None else "corpus-absent",
)
def test_full_corpus_replay(fixture) -> None:
    if fixture is None:
        pytest.skip(_corpus.corpus_skip_reason())
    _replay(fixture)
