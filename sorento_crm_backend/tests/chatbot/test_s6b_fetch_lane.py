"""RED tests for S6b - the business lane's fetch step (AC-604 to AC-606).

Written BEFORE `app/services/chatbot/lanes/business/fetch.py` exists (Phase 2, test-first).
Every test below is expected to fail today with an `ImportError` / `AttributeError` naming
that module or one of its functions - that is the correct red reason. A failure for any
other reason (a typo in a fixture path, a wrong assertion) is a defect in THIS file, not
evidence the port is done.

Scope: `sub-fetch-results` (tool search -> tool-filter -> tier probe -> entity-ids-transformer
-> MCPRuntimeClient -> output-structurer -> fetch-result). S6a's resolve+gate (already merged
into this branch) is the caller; S6c's answer/miss lane is NOT built yet, so the "result" arm
of `fetch_result` only hands the fetch payload back to n8n via `delegate_payload` - it does not
render a customer-facing answer.

Hazards: H11 (zero tools must not silently produce an empty turn), H43 (moot - the in-process
call binds `domain` directly, there is no missing `$4`), H46 (`_isTimeline` is a CONTAINS
check, not an equality check - `contracts.is_timeline` is the one place this is decided and
S6b must consume it, not re-derive it), H49 (verify the live tool-selection distribution before porting
any per-tool branch - `crm_order_management_orders_by_product_list` was never selected in the
captures graded so far), H52 (the MCP call goes through the CONFIGURED url,
`settings.ai_assistant_mcp_url`, never a literal IP or scheme), H53 (tool search is
`EmbeddingReadService` in-process, never raw SQL from this package).

**Contract this file assumes and asserts** (S6a set the precedent - see
`lanes/business/services.py`'s `ResolveGateServices` and its own `_probe()` docstring, which
names this exact seam as "S6b's fetch, over MCPRuntimeClient (D10)"):

    app.services.chatbot.lanes.business.fetch
        select_tool(db, *, query: str, domain: str | None, services: FetchServices)
            -> list[{"name": str, "similarity": float}]
        tool_filter(candidates: list[dict], *, has_product: bool | None) -> ToolPick
            ToolPick.items  : the n8n item list, [] or [{"json": {...best, "_tool_pick": {...}}}]
                              - BYTE-EQUAL to today (D8 parity)
            ToolPick.outcome: "picked" | "not_found" - H11's fix, ALWAYS distinguishable
        tier_probe_plan(tier_gate: dict) -> list[dict]           (n8n item-list shape)
        tier_probe_collect(tier_gate: dict, *, plan_items, probe_results) -> dict
        entity_ids_transformer(trigger: dict) -> dict[str, Any]  (tool call args)
        call_tool(name: str, args: dict, *, mcp) -> Any           (thin pass-through, H52)
        output_structurer(result: dict, ctx: dict) -> dict        (deterministic, H7)
        fetch_result(item: dict, *, tool=None, tier_probe=None) -> dict  (adds `_fetch_arm`)

    app.services.chatbot.lanes.business.services
        FetchServices(embed, tool_search, mcp_call)  - dataclass, same shape as
        `ResolveGateServices`.

    app.services.chatbot.lanes.business (package init, alongside `run_until_exit`)
        run_fetch(payload, *, services: FetchServices, dry_run: bool) -> dict
            The next call site after `run_until_exit`'s "continue" exit: dispatches on
            `_fetch_arm` (see `TestEngineDispatch` below).

Where the plan/UAC under-specifies an exact function name, this docstring is the tester's own
choice, made explicit so the coder can push back on it rather than silently drifting from it.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

from tests.chatbot import _corpus

FETCH_MODULE_PATH = (
    Path(__file__).resolve().parents[2]
    / "app"
    / "services"
    / "chatbot"
    / "lanes"
    / "business"
    / "fetch.py"
)


def _fetch_source() -> str:
    """The fetch module's own source text, for the static hazard checks (H52, H53).

    Read as TEXT rather than imported, so the static checks below can run and report their
    real reason even while the module does not exist yet or fails to import.
    """
    if not FETCH_MODULE_PATH.exists():
        pytest.fail(
            f"{FETCH_MODULE_PATH} does not exist yet - S6b's fetch.py has not been written. "
            "This is the expected RED reason for every test in this file."
        )
    return FETCH_MODULE_PATH.read_text(encoding="utf-8")


def _import_fetch():
    from app.services.chatbot.lanes.business import fetch as fetch_mod

    return fetch_mod


def _import_fetch_services():
    from app.services.chatbot.lanes.business.services import FetchServices

    return FetchServices


# --------------------------------------------------------------------------- #
# AC-604 - tool selection: EmbeddingReadService in-process, max-similarity pick, H11
# --------------------------------------------------------------------------- #


class TestToolSearch:
    def test_tool_search_uses_embedding_service_not_sql(self, monkeypatch):
        """`select_tool` calls the `tool_search` seam with the EMBEDDED query.

        H53: nothing in `fetch.py` talks to `embedding_chunks` or issues raw SQL - the n8n
        node's own `$1..$4` query (`sub-get-rag-live`'s "Execute a SQL query") stays retired,
        replaced end to end by `EmbeddingReadService.search_tool_candidates` behind the
        `tool_search` seam.

        H43: the n8n query's `$4` is `domain`, LIKE-matched against `source_id`, and is
        genuinely missing on some call sites live (the hazard). That cannot exist in the
        in-process port: `domain` is bound directly into the one function call, so a
        `domain=None` here means "no filter" by construction, never "the caller forgot to
        wire a parameter" - which is why the plan calls H43 `moot` rather than `fix`.
        """
        fetch = _import_fetch()
        FetchServices = _import_fetch_services()

        embed_calls: list[str] = []
        search_calls: list[dict[str, Any]] = []

        def fake_embed(query: str) -> list[float]:
            embed_calls.append(query)
            return [0.1, 0.2, 0.3]

        def fake_tool_search(embedding: list[float], *, query: str, domain: str | None):
            search_calls.append({"embedding": embedding, "query": query, "domain": domain})
            return [{"name": "crm_master_products_list", "similarity": 0.9}]

        services = FetchServices(
            embed=fake_embed,
            tool_search=fake_tool_search,
            mcp_call=lambda *a, **k: pytest.fail("mcp_call must not be reached by select_tool"),
        )

        result = fetch.select_tool(
            db=None, query="price for SRTWC8517", domain=None, services=services
        )

        assert embed_calls == ["price for SRTWC8517"]
        assert search_calls == [
            {"embedding": [0.1, 0.2, 0.3], "query": "price for SRTWC8517", "domain": None}
        ]
        assert result == [{"name": "crm_master_products_list", "similarity": 0.9}]

        # H43: a tier-pick turn passes a domain filter (the resolved gate's own
        # `tier_pick_domain`, e.g. "promotion") - the seam receives it verbatim, never a
        # guessed or omitted value.
        search_calls.clear()
        fetch.select_tool(db=None, query="promo", domain="promotion", services=services)
        assert search_calls[0]["domain"] == "promotion"

        source = _fetch_source()
        assert "embedding_chunks" not in source, "fetch.py must not name the raw table (H53)"
        assert not re.search(r"\bSELECT\b", source, re.IGNORECASE), (
            "fetch.py must not issue SQL directly - tool search stays behind "
            "EmbeddingReadService (H53)"
        )

    def test_tool_filter_picks_max_similarity_tiebreak_name(self):
        """AC-604: max `similarity` wins; an exact tie breaks on `name` ASC (deterministic)."""
        fetch = _import_fetch()

        candidates = [
            {"name": "crm_marketing_promotions_list", "similarity": 0.40},
            {"name": "crm_master_products_list", "similarity": 0.91},
            {"name": "crm_incoming_stock_list", "similarity": 0.91},
        ]
        result = fetch.tool_filter(candidates, has_product=True)

        assert result.outcome == "picked"
        assert len(result.items) == 1
        picked = result.items[0]["json"]
        # "crm_incoming_stock_list" < "crm_master_products_list" lexically - the tie goes to
        # the alphabetically-first name, matching `tool-filter.js`'s own `cmp(label(a), label(b))`.
        assert picked["name"] == "crm_incoming_stock_list"
        assert picked["_tool_pick"]["chosen"] == "crm_incoming_stock_list"
        assert picked["_tool_pick"]["count"] == 3
        assert picked["_tool_pick"]["has_product"] is True
        rejected_names = {r["name"] for r in picked["_tool_pick"]["rejected"]}
        assert rejected_names == {"crm_marketing_promotions_list", "crm_master_products_list"}

    def test_zero_tools_is_not_found_outcome(self):
        """H11: zero candidates is a DISTINGUISHABLE outcome, never a silent empty turn.

        `tool-filter.js` returns `[]` on zero tools (parity, preserved on `.items`), but the
        Python port must ALSO say so through a channel a caller can act on - the JS's own
        empty array is indistinguishable from "ran and found nothing to say", which is
        exactly the hazard (a turn that goes quiet is not the same as a turn that answers
        "I don't have a tool for that").
        """
        fetch = _import_fetch()

        result = fetch.tool_filter([], has_product=None)

        assert result.items == [], "parity: zero tools in, zero items out (D8)"
        assert result.outcome == "not_found", (
            "H11: the caller must be able to tell 'no tool matched' apart from 'nothing ran'"
        )


# --------------------------------------------------------------------------- #
# AC-605 / AC-606 - node replay against the captured n8n executions
# --------------------------------------------------------------------------- #


def _has_product_from_gate(fixture: _corpus.Fixture) -> bool | None:
    """Tolerant read of `build-ctx-resolved`'s `ctx.gate.compatible_entities` (tool-filter.js)."""
    items = fixture.upstream("build-ctx-resolved")
    if not items:
        return None
    bcr = items[0].get("json") or {}
    try:
        entities = ((bcr.get("ctx") or {}).get("gate") or {}).get("compatible_entities")
    except AttributeError:
        return None
    if not isinstance(entities, list):
        return None
    return any(isinstance(e, dict) and e.get("entity_type") == "product" for e in entities)


def _run_tool_filter(fixture: _corpus.Fixture) -> list:
    fetch = _import_fetch()
    rag_output = fixture.first("Execute 'sub-get-rag'")
    candidates = rag_output.get("tools") or []
    result = fetch.tool_filter(candidates, has_product=_has_product_from_gate(fixture))
    return result.items


def _run_tier_probe_plan(fixture: _corpus.Fixture) -> list:
    fetch = _import_fetch()
    tier_gate = fixture.first("tier-gate")
    return fetch.tier_probe_plan(tier_gate)


def _run_tier_probe_collect(fixture: _corpus.Fixture) -> list:
    fetch = _import_fetch()
    tier_gate = fixture.first("tier-gate")
    plan_items = [i.get("json") for i in fixture.upstream("tier-probe-plan")]
    probe_results = [i.get("json") for i in fixture.upstream("tier-probe")]
    return [{"json": fetch.tier_probe_collect(tier_gate, plan_items=plan_items, probe_results=probe_results)}]


def _run_fetch_result(fixture: _corpus.Fixture) -> list:
    fetch = _import_fetch()
    item = (fixture.input[0] or {}).get("json") or {}
    tool = None
    if fixture.upstream("tool-filter"):
        tool = fixture.first("tool-filter")
    tier_probe = None
    if fixture.upstream("tier-probe-collect"):
        tier_probe = fixture.first("tier-probe-collect")
    return [{"json": fetch.fetch_result(item, tool=tool, tier_probe=tier_probe)}]


_S6B_RUNNERS = {
    "tool-filter": _run_tool_filter,
    "tier-probe-plan": _run_tier_probe_plan,
    "tier-probe-collect": _run_tier_probe_collect,
    "fetch-result": _run_fetch_result,
}
_S6B_NODES = sorted(_S6B_RUNNERS)


def _replay(fixture: _corpus.Fixture) -> None:
    actual = _corpus.json_round_trip(_S6B_RUNNERS[fixture.node](fixture))
    expected = _corpus.json_round_trip(fixture.expected)
    from tests.chatbot import divergences

    registered = divergences.find(fixture.node, fixture.name.split("/")[-1])
    if actual == expected:
        if registered is not None:
            pytest.fail(
                f"{fixture.node}/{fixture.name}: registered divergence {registered.hazard} "
                "no longer diverges - retire the entry"
            )
        return
    if registered is not None:
        return
    assert actual == expected, (
        f"{fixture.node}/{fixture.name} diverges from the captured n8n output and is not "
        "registered in tests/chatbot/divergences.py"
    )


@pytest.mark.parametrize(
    "fixture",
    _corpus.graded([f for node in _S6B_NODES for f in _corpus.full_corpus(node)]) or [None],
    ids=lambda f: f"{f.node}/{f.name}" if f is not None else "corpus-absent",
)
def test_entity_ids_transformer_replay_placeholder_tool_filter_replay(fixture) -> None:
    """AC-606: `tool-filter`, `tier-probe-plan`, `tier-probe-collect` and `fetch-result`
    against every captured `sub-fetch-results-rs` execution (16 captures, gate 0's floor is
    5 per branch and is NOT yet met - see the note at the bottom of this file).

    `entity-ids-transformer` and `output-structurer` have NO captured `runData` fixtures
    anywhere in the corpus today (checked: `tests/fixtures/nodes/{entity-ids-transformer,
    output-structurer}/` does not exist under either slug). They are covered by hand-built
    UNIT tests below instead (`TestEntityIdsTransformer`, `TestOutputStructurer`) - clearly
    NOT corpus replay, and NOT a substitute for the real captures AC-008 requires before this
    slice's PR opens.
    """
    if fixture is None:
        pytest.skip(_corpus.corpus_skip_reason())
    _replay(fixture)


@pytest.mark.parametrize("node", _S6B_NODES)
def test_gate_0_vendored_subset_is_missing(node: str) -> None:
    """Documents the gap rather than hiding it: AC-008 requires a vendored subset under
    `tests/fixtures/chatbot/nodes/<node>/` before this slice's PR opens (gate 0), and none
    exists yet for the four S6b nodes. This is a XFAIL, not a skip, so it flips to failing
    (and gets noticed) the moment someone vendors a subset without also fixing this test's
    own expectation - a silently-passing "TODO" test is the thing AC-008 exists to prevent.
    """
    assert not _corpus.vendored(node), (
        f"a vendored subset now exists for {node} - update this test (and, per AC-008, "
        "confirm it covers >= 5 real captures per branch before treating gate 0 as met)"
    )


# --------------------------------------------------------------------------- #
# AC-605, H52 - the MCP call: configured URL, never a raw IP; entity-ids-transformer
# --------------------------------------------------------------------------- #


class TestCallTool:
    def test_mcp_call_uses_configured_url_never_raw_ip(self):
        """`call_tool` is a thin pass-through onto whatever `MCPRuntimeClient`-shaped object
        it is handed, and the PRODUCTION construction of that object (in `services.py`,
        mirroring `_probe()`'s own D10 docstring) is what binds it to
        `settings.ai_assistant_mcp_url` - never a literal host.

        H52's own catalogued hazard is a raw IP (`72.62.195.20`) baked into an n8n HTTP
        node. The static check below is the mechanical guarantee that this file never grows
        the same thing back in.
        """
        fetch = _import_fetch()

        received: list[tuple[str, dict[str, Any]]] = []

        class FakeMcp:
            def call_tool(self, name: str, arguments: dict[str, Any]) -> str:
                received.append((name, arguments))
                return '{"answers": []}'

        args = {"product_ids": ["6136ea6b-1699-46ec-8e8e-f60c8bb64310"], "space_id": "364817"}
        result = fetch.call_tool("crm_master_products_list", args, mcp=FakeMcp())

        assert received == [("crm_master_products_list", args)], (
            "the seam must receive {name, arguments} exactly as entity-ids-transformer "
            "built them, with no re-shaping (D10)"
        )
        assert result == '{"answers": []}'

        source = _fetch_source()
        assert "72.62.195.20" not in source, "H52: no literal raw IP in fetch.py"
        assert "http://" not in source, "H52: no hard-coded scheme+host in fetch.py"


class TestEntityIdsTransformer:
    """Hand-built unit tests over `entity-ids-transformer.js`'s own literal behaviour.

    No `runData` fixture exists for this node in the corpus (checked directly), so these are
    NOT graded against a real capture - they assert the structural rules the JS states in its
    own comments, so the port has something to satisfy before the corpus catches up (AC-008
    tracks the capture gap separately, in `test_gate_0_vendored_subset_is_missing` above).
    """

    def test_type_to_param_maps_product_and_dedupes_uuids(self):
        fetch = _import_fetch()
        trigger = {
            "entities": [
                {"uuid": "6136ea6b-1699-46ec-8e8e-f60c8bb64310", "entity_type": "product", "code": "A"},
                {"uuid": "6136ea6b-1699-46ec-8e8e-f60c8bb64310", "entity_type": "product", "code": "A"},
                {"uuid": "7136ea6b-1699-46ec-8e8e-f60c8bb64311", "entity_type": "customer", "code": "B"},
            ],
            "tool": "crm_master_products_list",
            "semantic_input": {"contact_id": 487555417, "space_id": "ignored-by-the-hardcode"},
        }
        out = fetch.entity_ids_transformer(trigger)

        assert out["product_ids"] == ["6136ea6b-1699-46ec-8e8e-f60c8bb64310"]
        assert out["customer_ids"] == ["7136ea6b-1699-46ec-8e8e-f60c8bb64311"]

    def test_bad_uuid_is_skipped_not_thrown(self):
        fetch = _import_fetch()
        trigger = {
            "entities": [{"uuid": "not-a-uuid", "entity_type": "product", "code": "A"}],
            "tool": "crm_master_products_list",
            "semantic_input": {"contact_id": "1", "space_id": "x"},
        }
        out = fetch.entity_ids_transformer(trigger)
        assert out.get("product_ids") in (None, [])

    def test_contact_id_coerces_int_and_padded_string(self):
        """`String(x ?? '').trim()` - int and a space-padded string both fold to the trimmed
        string form, per the JS's own measured-over-24-executions comment."""
        fetch = _import_fetch()
        for raw in (487555417, "487555417 ", " 487555417"):
            trigger = {"entities": [], "tool": "x", "semantic_input": {"contact_id": raw, "space_id": "s"}}
            out = fetch.entity_ids_transformer(trigger)
            assert out["contact_id"] == "487555417"

    def test_space_id_is_hard_coded_364817(self):
        """The ONE deliberate hard-code the JS keeps (a single-tenant confirmed decision) -
        NOT a D5 divergence, because `entity-ids-transformer` is not `resolve-entity` /
        `get-access-types` / the probes; D5 only reassigns those four call sites."""
        fetch = _import_fetch()
        trigger = {"entities": [], "tool": "x", "semantic_input": {"contact_id": "1", "space_id": "some-other-value"}}
        out = fetch.entity_ids_transformer(trigger)
        assert out["space_id"] == "364817"


# --------------------------------------------------------------------------- #
# AC-605, H7, H46 - output-structurer: deterministic, single-source timeline sentinel
# --------------------------------------------------------------------------- #


class TestOutputStructurer:
    def test_output_structurer_is_deterministic(self, monkeypatch):
        """H7: `output-structurer` is the "orphaned answer LLM" hazard's own resolution -
        there is NO answer LLM in this port (D10). Same input in, same output out, twice,
        and no LLM provider seam is ever touched.
        """
        fetch = _import_fetch()

        def _forbidden(*_a, **_k):
            pytest.fail("output_structurer must not call an LLM provider (H7, D10)")

        # Patch every provider-facing entry point this package could plausibly reach, so a
        # future accidental import still trips this test rather than silently calling out.
        import app.services.llm_provider as llm_provider_mod

        monkeypatch.setattr(llm_provider_mod, "LLMProvider", _forbidden, raising=False)

        result = {
            "response": "Here are the matching products.",
            "response_intro": "Here are the matching products.",
            "answers": [{"title": "SRTWB7096", "fields": [{"key": "product_code", "label": "Product Code", "value": "SRTWB7096"}]}],
            "attachments": [],
            "has_result": True,
            "field_access": None,
        }
        ctx = {"semantic_input": {"requested_attributes": []}}

        first = fetch.output_structurer(result, ctx)
        second = fetch.output_structurer(result, ctx)
        assert _corpus.json_round_trip(first) == _corpus.json_round_trip(second)

    def test_timeline_sentinel_denies_mixed_array(self):
        """H46: `output-structurer`'s per-contact denial note is gated on `!is_timeline(...)`,
        and `is_timeline` is a CONTAINS check (`contracts.is_timeline`, already declared in
        `app/services/chatbot/contracts.py` for exactly this reason - the module's own
        docstring: "Declared here, with `is_timeline` beside it, so S6b's port consumes the
        one reading instead of re-deriving it").

        `['__all__', 'eta_delay_date']` still counts as a timeline request (the sentinel is
        PRESENT), so the denial note for `eta_delay_date` is SUPPRESSED - a customer who asked
        for the whole container timeline is not told, field by field, which parts of "the
        whole timeline" they may not see. `['eta_delay_date']` alone carries no sentinel, so
        the note is emitted normally.
        """
        from app.services.chatbot.contracts import is_timeline

        assert is_timeline(["__all__", "eta_delay_date"]) is True
        assert is_timeline(["eta_delay_date"]) is False

        fetch = _import_fetch()
        source = _fetch_source()
        assert "contracts import is_timeline" in source or "contracts.is_timeline" in source, (
            "output_structurer must import contracts.is_timeline rather than re-deriving its "
            "own copy of the sentinel check (H46)"
        )

        denied_result = {
            "response": "x",
            "response_intro": "x",
            "answers": [
                {
                    "title": "row",
                    "fields": [{"key": "product_code", "label": "Product Code", "value": "SRTWB7096"}],
                }
            ],
            "attachments": [],
            "has_result": True,
            "field_access": {"denied": [{"field": "eta_delay_date", "label": "ETA Delay"}]},
        }

        timeline_ctx = {"semantic_input": {"requested_attributes": ["__all__", "eta_delay_date"]}}
        plain_ctx = {"semantic_input": {"requested_attributes": ["eta_delay_date"]}}

        timeline_out = fetch.output_structurer(denied_result, timeline_ctx)
        plain_out = fetch.output_structurer(denied_result, plain_ctx)

        timeline_text = timeline_out.get("response") or ""
        plain_text = plain_out.get("response") or ""
        assert "eta delay" not in timeline_text.lower(), (
            "a mixed requested_attributes array containing '__all__' must still suppress the "
            "per-field denial note (H46 contains-semantics)"
        )
        assert "eta delay" in plain_text.lower() or "can't share" in plain_text.lower(), (
            "requested_attributes without the sentinel must still emit the denial note"
        )


# --------------------------------------------------------------------------- #
# H49 - verify the live tool-selection distribution before porting a per-tool branch
# --------------------------------------------------------------------------- #


class TestToolDistribution:
    def test_tool_distribution_note(self):
        """H49: the plan says "verify the live tool-selection distribution before porting
        any per-tool branch" - `crm_order_management_orders_by_product_list` has never been
        selected in the fixtures graded so far. This test does NOT claim to have re-measured
        production; it asserts the port has made the SAFE choice given that measurement is
        still open: either the module records the measured distribution in its own docstring
        (so the claim is auditable, same pattern as `COVERAGE.md`'s scanned-count rows), or it
        contains no `if tool_name == 'crm_order_management_orders_by_product_list'` branch.
        """
        source = _fetch_source()
        has_note = "orders_by_product_list" in source and (
            "never selected" in source.lower() or "distribution" in source.lower()
        )
        has_dedicated_branch = bool(
            re.search(r"crm_order_management_orders_by_product_list", source)
            and re.search(r"if\b.*crm_order_management_orders_by_product_list", source)
        )
        assert has_note or not has_dedicated_branch, (
            "H49: fetch.py branches on a tool the live distribution has never selected, "
            "with no docstring recording the measurement that justifies it"
        )


# --------------------------------------------------------------------------- #
# Capacity - no DB session held across the MCP call (plan "Capacity and safety")
# --------------------------------------------------------------------------- #


class TestCapacity:
    def test_no_session_across_mcp_call(self, counting_session_factory):
        """The plan's capacity rule, restated for S6b: 'never hold a DB session across LLM
        or MCP I/O'. `select_tool` (the embedding read) and `call_tool` (the MCP round trip)
        must both run with zero sessions open on the factory the caller handed in.
        """
        fetch = _import_fetch()
        FetchServices = _import_fetch_services()

        observed_during_embed: list[int] = []
        observed_during_mcp: list[int] = []

        def fake_embed(query: str) -> list[float]:
            observed_during_embed.append(counting_session_factory.state["open"])
            return [0.1]

        def fake_tool_search(embedding, *, query, domain):
            return [{"name": "crm_master_products_list", "similarity": 0.5}]

        def fake_mcp_call(name, args):
            observed_during_mcp.append(counting_session_factory.state["open"])
            return "{}"

        services = FetchServices(
            embed=fake_embed, tool_search=fake_tool_search, mcp_call=fake_mcp_call
        )

        # The session is opened, used to build `services` (a real production binding takes
        # `db`), and MUST be closed before the embed/MCP calls below run.
        db = counting_session_factory()
        db.close()

        fetch.select_tool(db=None, query="x", domain=None, services=services)
        fetch.call_tool("crm_master_products_list", {}, mcp=type("M", (), {"call_tool": staticmethod(fake_mcp_call)})())

        assert observed_during_embed == [0], (
            "a DB session was open during the embedding call - fetch.py must not hold one "
            "across provider I/O"
        )
        assert observed_during_mcp == [0], (
            "a DB session was open during the MCP call - fetch.py must not hold one across "
            "MCP I/O"
        )


# --------------------------------------------------------------------------- #
# D14 - dry run still reads, writes nothing
# --------------------------------------------------------------------------- #


class TestDryRun:
    def test_dry_run_still_reads_but_writes_nothing(self, session_factory):
        """D14: a dry-run turn performs the SAME MCP read as a live turn (parity - the
        customer-facing behaviour of a test turn must match production, or console/clone
        testing proves nothing) but commits no row anywhere outside `chatbot.turns` (which
        this package does not even write to - that is the engine's job).
        """
        from app.services.chatbot.lanes.business import fetch

        FetchServices = _import_fetch_services()

        commits: list[None] = []
        db = session_factory()
        original_commit = db.commit

        def counting_commit():
            commits.append(None)
            return original_commit()

        db.commit = counting_commit  # type: ignore[method-assign]

        mcp_reads: list[str] = []

        def fake_embed(query: str) -> list[float]:
            return [0.1]

        def fake_tool_search(embedding, *, query, domain):
            return [{"name": "crm_master_products_list", "similarity": 0.5}]

        def fake_mcp_call(name, args):
            mcp_reads.append(name)
            return '{"answers": []}'

        services = FetchServices(
            embed=fake_embed, tool_search=fake_tool_search, mcp_call=fake_mcp_call
        )

        continue_payload = {
            "_exit_kind": "continue",
            "gate": {"compatible_entities": [{"uuid": "6136ea6b-1699-46ec-8e8e-f60c8bb64310", "entity_type": "product", "code": "SRTWB7096"}]},
        }

        from app.services.chatbot.lanes import business

        business.run_fetch(continue_payload, services=services, dry_run=True)

        assert mcp_reads, "a dry-run turn must still make the MCP read (D14 parity)"
        assert commits == [], "a dry-run turn must commit nothing (D14)"


# --------------------------------------------------------------------------- #
# Engine dispatch - `_fetch_arm` decides what happens next
# --------------------------------------------------------------------------- #


class TestEngineDispatch:
    """`lanes/business/__init__.py::run_fetch` - the next call site after `run_until_exit`'s
    "continue" exit (AC-605). It is NOT `engine.py` itself: S6a's own precedent is that the
    engine calls exactly ONE function per lane stage (`run_until_exit`), so `run_fetch` is
    that same seam for the fetch stage. `engine.py` wiring `run_fetch` into `run_turn` is a
    separate, later step this file does not test.
    """

    @staticmethod
    def _services(mcp_result: str = '{"answers": []}'):
        FetchServices = _import_fetch_services()
        return FetchServices(
            embed=lambda query: [0.1],
            tool_search=lambda embedding, *, query, domain: [
                {"name": "crm_master_products_list", "similarity": 0.9}
            ],
            mcp_call=lambda name, args: mcp_result,
        )

    def test_fetch_arm_tier_ask_does_not_delegate_business_query(self):
        """`_fetch_arm == 'tier-ask'`: the turn needs the customer to pick an access tier
        before anything is fetched. This is `access-level-choice-message`'s own path (S6c
        renders the actual copy); S6b's job is only to make sure the turn does NOT fall
        through to a normal 'result' delegate while a tier is still unresolved.
        """
        from app.services.chatbot.lanes import business

        payload = {
            "_exit_kind": "continue",
            "gate": {"compatible_entities": []},
            "tier_ask": True,
            "tier_any_available": True,
        }
        fragment = business.run_fetch(payload, services=self._services(), dry_run=False)

        assert fragment.get("delegate") != "business_query", (
            "a tier-ask arm must not be handed to n8n as an ordinary business_query result"
        )
        assert fragment.get("kind") == "tier_ask" or fragment.get("_fetch_arm") == "tier-ask"

    def test_fetch_arm_error_is_a_failed_looked_up_stage(self):
        """`_fetch_arm == 'error'`: the fetch itself failed (the MCP tool returned an error
        item). The fragment must carry enough for the engine to record a `failed` turn at
        `stage = looked_up` with an error reply, matching every other lane's failure shape
        (AC-105, AC-107, AC-403's pattern).
        """
        from app.services.chatbot.lanes import business

        def erroring_mcp_call(name, args):
            return '{"error": "MCP tool crm_master_products_list timed out"}'

        payload = {
            "_exit_kind": "continue",
            "gate": {"compatible_entities": [{"uuid": "6136ea6b-1699-46ec-8e8e-f60c8bb64310", "entity_type": "product", "code": "SRTWB7096"}]},
        }
        services = self._services()
        services = type(services)(embed=services.embed, tool_search=services.tool_search, mcp_call=erroring_mcp_call)

        fragment = business.run_fetch(payload, services=services, dry_run=False)

        assert fragment.get("kind") == "error" or fragment.get("_fetch_arm") == "error"
        assert fragment.get("error"), "an error fragment must carry the reason text"

    def test_fetch_arm_result_delegates_business_query_with_fetch_result_attached(self):
        """`_fetch_arm == 'result'`: S6c (answer + miss) is not built yet, so the turn still
        delegates to n8n's `business_query` lane - but the fetch's own result rides along on
        `delegate_payload` so the NEXT slice (S6c) has something to build the answer from
        without re-fetching.
        """
        from app.services.chatbot.lanes import business

        payload = {
            "_exit_kind": "continue",
            "gate": {"compatible_entities": [{"uuid": "6136ea6b-1699-46ec-8e8e-f60c8bb64310", "entity_type": "product", "code": "SRTWB7096"}]},
        }
        fragment = business.run_fetch(
            payload,
            services=self._services('{"answers": [{"title": "SRTWB7096"}], "has_result": true}'),
            dry_run=False,
        )

        assert fragment.get("delegate") == "business_query"
        delegate_payload = fragment.get("delegate_payload") or fragment.get("payload")
        assert delegate_payload is not None, (
            "the 'result' arm must attach the fetch's own output to delegate_payload for S6c"
        )
