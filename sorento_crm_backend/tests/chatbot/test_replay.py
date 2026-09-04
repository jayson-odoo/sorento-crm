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
    from app.services.chatbot.head.route import route_turn

    ctx = fixture.first("build-ctx")["ctx"]
    return route_turn(ctx, stock_denial_enabled=True)


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


RUNNERS = {
    "build-ctx": _run_build_ctx,
    "route-turn": _run_route_turn,
    "output_exchange": _run_output_exchange,
    "suggest-follow-up": _run_suggest_follow_up,
}

PORTED_NODES = sorted(RUNNERS)


def _replay(fixture: _corpus.Fixture) -> None:
    actual = _corpus.json_round_trip(RUNNERS[fixture.node](fixture))
    expected = _corpus.json_round_trip(fixture.expected)
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


def _ids(fixtures: list[_corpus.Fixture]) -> list[str]:
    return [f.name for f in fixtures]


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
