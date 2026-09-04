"""Node replay: every ported node against the captured n8n executions (AC-004, AC-005).

This is the whole reason the port is worth doing. Each fixture is a real turn that ran
in production or on the fail-closed clone; the Python port is fed the SAME upstream
values and its output must equal what n8n recorded, byte for byte after a JSON round
trip. A disagreement fails unless `divergences.py` registers it with a hazard id.

Two parametrisations per node: the vendored subset (always) and the full corpus (skips
with a message when the sibling n8n checkout is absent). Nothing here touches a database,
the network, or an LLM - these are pure functions over captured JSON.

**Only a real capture grades the port.** `source.expected_from == "runData"` means the
`expected` block is what the node actually emitted in a real execution; `"reasoned"` means
somebody wrote it by hand, and the escalation-routing lane hand-revised 31 `reasoned`
`output_exchange` fixtures - same filenames - to encode the UNPROMOTED B-TEAM-1' behaviour.
Grading against those would make an unpromoted lane change a merge gate for this port. So
`runData` fixtures fail the suite on a mismatch and `reasoned` ones are replayed, counted
and reported by `test_reasoned_fixture_agreement_is_reported` without ever failing. See
`_corpus.py`'s docstring for the measured split.
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
    _corpus.graded([f for node in PORTED_NODES for f in _corpus.vendored(node)]),
    ids=lambda f: f"{f.node}/{f.name}",
)
def test_vendored_replay(fixture: _corpus.Fixture) -> None:
    _replay(fixture)


@pytest.mark.parametrize(
    "fixture",
    _corpus.graded([f for node in PORTED_NODES for f in _corpus.full_corpus(node)]) or [None],
    ids=lambda f: f"{f.node}/{f.name}" if f is not None else "corpus-absent",
)
def test_full_corpus_replay(fixture) -> None:
    if fixture is None:
        pytest.skip(_corpus.corpus_skip_reason())
    _replay(fixture)


def test_reasoned_fixture_agreement_is_reported(capsys) -> None:
    """Replay every hand-written fixture and REPORT, never gate (see the module docstring).

    A `reasoned` expectation can describe a body that has never run in production, so it
    cannot be a merge gate. It is still worth replaying: the count is how the owner sees,
    in one line, how far the port sits from whatever the lane is proposing, and it is the
    number that should go to ZERO disagreements on the commit that re-ports B-TEAM-1'.
    """
    rows = _corpus.reasoned(
        [f for node in PORTED_NODES for f in _corpus.vendored(node)]
        + [f for node in PORTED_NODES for f in _corpus.full_corpus(node)]
    )
    if not rows:
        pytest.skip("no `reasoned` fixtures on this corpus")
    agree: list[str] = []
    differ: list[str] = []
    for fixture in rows:
        actual = _corpus.json_round_trip(RUNNERS[fixture.node](fixture))
        expected = _corpus.json_round_trip(fixture.expected)
        (agree if actual == expected else differ).append(f"{fixture.node}/{fixture.name}")
    with capsys.disabled():
        print(
            f"\n  reasoned fixtures (informational, never a gate): {len(rows)} replayed, "
            f"{len(agree)} agree, {len(differ)} differ"
        )
        for name in sorted(differ):
            print(f"    differs: {name}")
