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




# --------------------------------------------------------------------------- #
# S6a - the business lane's resolve + gate.
#
# Every by-name read the node bodies make becomes a parameter here, and each helper
# below names BOTH sources it accepts: the sub reads `$('build-ctx').first().json.ctx.*`
# while the live spine's own copy of the same node read `$('Call \'sub-query-reformulator\'')`
# and `$('get-session-vars')` directly. Same values, two graphs, one runner.
# --------------------------------------------------------------------------- #


def _sub_ctx(fixture: _corpus.Fixture) -> dict:
    """`$('build-ctx').first().json.ctx` - the real ctx behind the carrier."""
    return (fixture.first("build-ctx") or {}).get("ctx") or {}


def _sub_parser(fixture: _corpus.Fixture) -> dict:
    try:
        return (_sub_ctx(fixture).get("parse") or {}).get("output") or {}
    except KeyError:
        return (fixture.first("Call 'sub-query-reformulator'") or {}).get("output") or {}


def _sub_session(fixture: _corpus.Fixture):
    try:
        return _sub_ctx(fixture).get("session")
    except KeyError:
        return fixture.first("get-session-vars")


def _sub_upstream(fixture: _corpus.Fixture, node: str):
    """`$('node').isExecuted ? $('node').first().json : null` - the three-state read."""
    items = fixture.upstream(node)
    return (items[0].get("json") if items else None)


def _sub_gate(fixture: _corpus.Fixture) -> dict:
    """The annotators' `gate`: the sub reads it off `build-ctx-resolved`, live off the gate."""
    resolved_ctx = _sub_upstream(fixture, "build-ctx-resolved")
    if resolved_ctx is not None:
        return ((resolved_ctx.get("ctx") or {}).get("gate")) or {}
    return _sub_upstream(fixture, "disallowed-entity-gate") or {}


def _input_json(fixture: _corpus.Fixture) -> dict:
    return (fixture.input[0].get("json") or {}) if fixture.input else {}


def _run_disallowed_entity_gate(fixture: _corpus.Fixture) -> list:
    from app.services.chatbot.lanes.business.gate import run_gate

    # The gate MUTATES its input item, and `$('resolve-entity')` downstream must still see
    # the pre-mutation snapshot, so both sides get their own copy - which is also exactly
    # what the capture harness hands the JavaScript.
    return [
        {
            "json": run_gate(
                _corpus.json_round_trip(_input_json(fixture)),
                parser=_sub_parser(fixture),
                resolver=_corpus.json_round_trip(_sub_upstream(fixture, "resolve-entity")),
                session=_sub_session(fixture),
                tier_gate=_sub_upstream(fixture, "tier-gate"),
                aggregate=_sub_upstream(fixture, "Aggregate"),
            )
        }
    ]


def _run_tier_gate(fixture: _corpus.Fixture) -> list:
    from app.services.chatbot.lanes.business.tier_gate import tier_gate

    return [
        {
            "json": tier_gate(
                _corpus.json_round_trip(_input_json(fixture)),
                parser=_sub_parser(fixture),
                item=_corpus.json_round_trip(_sub_upstream(fixture, "item")),
            )
        }
    ]


def _run_build_ctx_resolved(fixture: _corpus.Fixture) -> list:
    from app.services.chatbot.lanes.business import resolve_gate

    return [
        {
            "json": resolve_gate.build_ctx_resolved(
                _corpus.json_round_trip(_input_json(fixture)),
                ctx=_sub_ctx(fixture),
                resolved=_corpus.json_round_trip(fixture.first("resolve-entity")),
                aggregate=_corpus.json_round_trip(_sub_upstream(fixture, "Aggregate")),
            )
        }
    ]


def _run_annotate_incoming(fixture: _corpus.Fixture) -> list:
    from app.services.chatbot.lanes.business import pickers

    return [
        {
            "json": pickers.annotate_incoming(
                _corpus.json_round_trip(_sub_gate(fixture)),
                probe=_sub_upstream(fixture, "probe-incoming"),
            )
        }
    ]


def _run_annotate_customer(fixture: _corpus.Fixture) -> list:
    from app.services.chatbot.lanes.business import pickers

    return [
        {
            "json": pickers.annotate_customer(
                _corpus.json_round_trip(_sub_gate(fixture)),
                probe=_sub_upstream(fixture, "probe-customer-orders"),
                parser=_sub_parser(fixture),
            )
        }
    ]


# `resolve-exit-access-ask` is listed but NOT registered in `RUNNERS`: no execution of that
# arm has ever been captured, in any slug, so there is nothing to replay. The arm is covered
# by `test_resolve_gate_unit.py` instead, and `COVERAGE.md` shows it as a zero cell rather
# than hiding it.
_EXIT_KIND_BY_NODE = {
    "resolve-exit-continue": "continue",
    "resolve-exit-access-ask": "access_ask",
    "resolve-exit-not-found": "not_found",
    "resolve-exit-offer": "offer",
}


def _run_resolve_exit(fixture: _corpus.Fixture) -> list:
    from app.services.chatbot.lanes.business import resolve_gate

    fields = {
        "resolved": _sub_upstream(fixture, "resolve-entity"),
        "gate": _sub_upstream(fixture, "disallowed-entity-gate"),
        "ctx_resolved": _sub_upstream(fixture, "build-ctx-resolved"),
        "aggregate": _sub_upstream(fixture, "Aggregate"),
        "tier_gate": _sub_upstream(fixture, "tier-gate"),
        "annotate_incoming": _sub_upstream(fixture, "annotate-incoming-picker"),
    }
    return [
        {
            "json": resolve_gate.exit_item(
                _corpus.json_round_trip(_input_json(fixture)),
                exit_kind=_EXIT_KIND_BY_NODE[fixture.node],
                fields=_corpus.json_round_trip(fields),
            )
        }
    ]


def _run_item(fixture: _corpus.Fixture) -> list:
    from app.services.chatbot.lanes.business import resolve_gate

    return [
        {"json": resolve_gate.carry_item(fixture.first("When Executed by Another Workflow"))}
    ]


def _run_whole_sub(fixture: _corpus.Fixture) -> list:
    """AC-601: the WHOLE sub, from the captured trigger, with the three seams stubbed.

    Nothing is hand-written: `access_types` replays what `Aggregate` recorded, the resolver
    replays `resolve-entity`'s own response, and each probe replays its own node's output.
    A stub that returned anything else would be grading the stub.
    """
    from app.services.chatbot.lanes.business import resolve_gate
    from app.services.chatbot.lanes.business.services import ResolveGateServices

    aggregate = _sub_upstream(fixture, "Aggregate") or {}
    resolved = _sub_upstream(fixture, "resolve-entity")
    incoming = _sub_upstream(fixture, "probe-incoming")
    customer = _sub_upstream(fixture, "probe-customer-orders")

    services = ResolveGateServices(
        access_types=lambda **_: [{"name": n} for n in (aggregate.get("name") or [])],
        resolve_entity=lambda _body: _corpus.json_round_trip(resolved),
        probe=lambda **kwargs: _corpus.json_round_trip(
            incoming if kwargs["tool"] == resolve_gate.INCOMING_PROBE_TOOL else customer
        ),
    )
    trigger = _corpus.json_round_trip(fixture.first("When Executed by Another Workflow"))
    return [
        {
            "json": resolve_gate.run_from_trigger(
                trigger,
                services=services,
                space_id=SUB_REPLAY_SPACE_ID,
                probe_default_start=SUB_REPLAY_PROBE_START,
            )
        }
    ]


# n8n's own hard-coded values, so a replay reproduces the captured probe inputs. Production
# takes `space_id` from the default respond workspace (D5) and computes the window start
# from `$now`; both are parameters precisely so a replay can pin them.
SUB_REPLAY_SPACE_ID = "364817"
SUB_REPLAY_PROBE_START = "2026-06-01"




# --------------------------------------------------------------------------- #
# S6b - the business lane's fetch step (AC-604 to AC-606).
# --------------------------------------------------------------------------- #


def _s6b_has_product(fixture: _corpus.Fixture) -> bool | None:
    """`tool-filter`'s own tolerant read of the gate, including its catch-all.

    The previous body threw when `compatible_entities` was undefined; the throw was
    deliberately removed and the value RECORDED as null instead, so `None` here means
    "could not tell", never `False`.
    """
    items = fixture.upstream("build-ctx-resolved")
    if not items:
        return None
    entities = (((items[0].get("json") or {}).get("ctx") or {}).get("gate") or {}).get(
        "compatible_entities"
    )
    if not isinstance(entities, list):
        return None
    return any(isinstance(e, dict) and e.get("entity_type") == "product" for e in entities)


def _run_tool_filter(fixture: _corpus.Fixture) -> list:
    from app.services.chatbot.lanes.business.fetch import tool_filter

    rag = fixture.first("Execute 'sub-get-rag'")
    return tool_filter(rag.get("tools"), has_product=_s6b_has_product(fixture)).items


def _run_tier_probe_plan(fixture: _corpus.Fixture) -> list:
    from app.services.chatbot.lanes.business.fetch import tier_probe_plan

    return tier_probe_plan(fixture.first("tier-gate"))


def _run_tier_probe_collect(fixture: _corpus.Fixture) -> list:
    from app.services.chatbot.lanes.business.fetch import tier_probe_collect

    return [
        {
            "json": tier_probe_collect(
                fixture.first("tier-gate"),
                plan_items=[i.get("json") for i in fixture.upstream("tier-probe-plan")],
                probe_results=[i.get("json") for i in fixture.upstream("tier-probe")],
            )
        }
    ]


def _run_fetch_result(fixture: _corpus.Fixture) -> list:
    from app.services.chatbot.lanes.business.fetch import fetch_result

    item = (fixture.input[0] or {}).get("json") or {} if fixture.input else {}
    tool = fixture.first("tool-filter") if fixture.upstream("tool-filter") else None
    tier_probe = (
        fixture.first("tier-probe-collect") if fixture.upstream("tier-probe-collect") else None
    )
    return [{"json": fetch_result(item, tool=tool, tier_probe=tier_probe)}]


def _run_entity_ids_transformer(fixture: _corpus.Fixture) -> list:
    from app.services.chatbot.lanes.business.fetch import entity_ids_transformer

    # The node reads BOTH the trigger (by name) and its own input; in `sub-get-results` they
    # are the same item, which is why the port takes one dict.
    return [{"json": entity_ids_transformer(fixture.first("When Executed by Another Workflow"))}]


def _run_output_structurer(fixture: _corpus.Fixture) -> list:
    from app.services.chatbot.lanes.business.fetch import output_structurer

    return [
        {
            "json": output_structurer(
                fixture.first("MCP Client1"),
                fixture.first("When Executed by Another Workflow"),
            )
        }
    ]


def _run_rag_query_params(fixture: _corpus.Fixture) -> list:
    from app.services.chatbot.lanes.business.fetch import rag_query_params

    embedding = ((fixture.input[0] or {}).get("json") or {}).get("data") or []
    trigger = fixture.first("When Executed by Another Workflow")
    return [
        {
            "json": rag_query_params(
                (embedding[0] or {}).get("embedding") if embedding else [],
                source_type=trigger.get("source_type"),
                limit=trigger.get("limit"),
                domain=trigger.get("domain"),
            )
        }
    ]


def _run_collapse_tool_rows(fixture: _corpus.Fixture) -> list:
    from app.services.chatbot.lanes.business.fetch import collapse_tool_rows

    return [{"json": {"tools": collapse_tool_rows([i.get("json") for i in fixture.input])}}]


RUNNERS = {
    "build-ctx": _run_build_ctx,
    "route-turn": _run_route_turn,
    "output_exchange": _run_output_exchange,
    "suggest-follow-up": _run_suggest_follow_up,
    "disallowed-entity-gate": _run_disallowed_entity_gate,
    "tier-gate": _run_tier_gate,
    "build-ctx-resolved": _run_build_ctx_resolved,
    "annotate-incoming-picker": _run_annotate_incoming,
    "annotate-customer-picker": _run_annotate_customer,
    "resolve-exit-continue": _run_resolve_exit,
    "resolve-exit-not-found": _run_resolve_exit,
    "resolve-exit-offer": _run_resolve_exit,
    "item": _run_item,
    "sub-resolve-and-gate": _run_whole_sub,
    "tool-filter": _run_tool_filter,
    "tier-probe-plan": _run_tier_probe_plan,
    "tier-probe-collect": _run_tier_probe_collect,
    "fetch-result": _run_fetch_result,
    "entity-ids-transformer": _run_entity_ids_transformer,
    "output-structurer": _run_output_structurer,
    "Code_in_JavaScript": _run_rag_query_params,
    "Code_in_JavaScript1": _run_collapse_tool_rows,
}

# `sub-resolve-and-gate` is the SYNTHETIC whole-sub replay: it has no fixture directory of
# its own and is parametrised separately from `_corpus.sub_run_fixtures()`.
PORTED_NODES = sorted(set(RUNNERS) - {"sub-resolve-and-gate"})


def _compare(fixture: _corpus.Fixture) -> tuple[object, object]:
    """`(actual, expected)`, normalised the same way for every caller.

    One helper because the GRADING replay and the informational `reasoned` report must
    agree about what "differs" means: a `reasoned` S6a fixture written against an older
    body would otherwise be reported as differing purely on a key that capture could not
    have emitted, which is the opposite of what that count is for.
    """
    expected = _corpus.json_round_trip(fixture.expected)
    # Only the keys THIS capture's body version could not emit. A capture from the 5 Sep
    # run carries both, so on those this is empty and the keys are graded like any other
    # field - which is the whole point of that run.
    stripped = _corpus.keys_to_strip(fixture.node, expected)
    actual = _corpus.strip_keys(
        _corpus.json_round_trip(RUNNERS[fixture.node](fixture)), stripped
    )
    return actual, _corpus.strip_keys(expected, stripped)


def _replay(fixture: _corpus.Fixture) -> None:
    actual, expected = _compare(fixture)
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


# `sub-resolve-and-gate` is the SYNTHETIC whole-sub replay (S6a). It has no fixture
# directory of its own - it reuses the four `resolve-exit-*` captures - so it is
# parametrised here rather than through `PORTED_NODES`. S1b's rule applies to it unchanged:
# `graded()` keeps the real captures, and anything hand-written falls to the reporter below.
@pytest.mark.parametrize(
    "fixture",
    _corpus.graded(_corpus.sub_run_fixtures(vendored_only=True)),
    ids=lambda f: f.name,
)
def test_vendored_whole_sub_replay(fixture: _corpus.Fixture) -> None:
    """AC-601: `sub-resolve-and-gate` end to end, graded against the exit arm's capture."""
    _replay(fixture)


@pytest.mark.parametrize(
    "fixture",
    _corpus.graded(_corpus.sub_run_fixtures(vendored_only=False)) or [None],
    ids=lambda f: f.name if f is not None else "corpus-absent",
)
def test_full_corpus_whole_sub_replay(fixture) -> None:
    if fixture is None:
        pytest.skip(_corpus.corpus_skip_reason())
    _replay(fixture)


def test_reasoned_fixture_agreement_is_reported(capsys) -> None:
    """Replay every hand-written fixture and REPORT, never gate (see the module docstring).

    A `reasoned` expectation can describe a body that has never run in production, so it
    cannot be a merge gate. It is still worth replaying: the count is how the owner sees,
    in one line, how far the port sits from whatever the lane is proposing, and it is the
    number that should go to ZERO disagreements on the commit that re-ports B-TEAM-1'.

    The whole-sub fixtures are included so the rule has no hole: if an exit arm ever gets a
    hand-written expectation, it lands here rather than silently gating.
    """
    rows = _corpus.reasoned(
        [f for node in PORTED_NODES for f in _corpus.vendored(node)]
        + [f for node in PORTED_NODES for f in _corpus.full_corpus(node)]
        + _corpus.sub_run_fixtures(vendored_only=True)
        + _corpus.sub_run_fixtures(vendored_only=False)
    )
    if not rows:
        pytest.skip("no `reasoned` fixtures on this corpus")
    agree: list[str] = []
    differ: list[str] = []
    for fixture in rows:
        actual, expected = _compare(fixture)
        (agree if actual == expected else differ).append(f"{fixture.node}/{fixture.name}")
    with capsys.disabled():
        print(
            f"\n  reasoned fixtures (informational, never a gate): {len(rows)} replayed, "
            f"{len(agree)} agree, {len(differ)} differ"
        )
        for name in sorted(differ):
            print(f"    differs: {name}")
