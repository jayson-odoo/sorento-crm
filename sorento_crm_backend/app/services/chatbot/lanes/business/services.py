"""The three I/O seams `sub-resolve-and-gate` has, as injectable callables.

n8n makes them two HTTP calls and two `executeWorkflow` calls; the port makes them
in-process service calls. They are grouped here rather than reached for inline so a test
can replay a captured turn with NO database, NO MCP server and NO network - which is what
makes the 254-fixture replay a pure function over JSON (AC-602).

| n8n node | this seam | CRM service |
| --- | --- | --- |
| `get-access-types` (httpRequest) | `access_types` | `ContactAccessTypeService.resolve_active_access_levels_for_contact` |
| `resolve-entity` (httpRequest) | `resolve_entity` | the function behind `POST /api/v1/system/references/resolve` |
| `probe-incoming` / `probe-customer-orders` (executeWorkflow) | `probe` | S6b's fetch, over `MCPRuntimeClient` (D10) |
| `Execute 'sub-get-rag'` (executeWorkflow -> pgvector SQL) | `embed` + `tool_search` | `EmbeddingReadService.search_tool_chunks` (H53) |
| `MCP Client1` (mcpClient, raw IP) | `mcp_call` | `MCPRuntimeClient` at `settings.ai_assistant_mcp_url` (H52) |

`space_id` is the default respond workspace's, not n8n's hard-coded `364817` (D5).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Protocol

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class AccessTypesFn(Protocol):
    def __call__(self, *, contact_id: str, space_id: str | None) -> list[dict[str, Any]]: ...


class ResolveEntityFn(Protocol):
    def __call__(self, body: dict[str, Any]) -> dict[str, Any]: ...


class ProbeFn(Protocol):
    def __call__(
        self,
        *,
        tool: str,
        contact_id: Any,
        entities: Any,
        semantic_input: dict[str, Any],
        user_prompt: str,
    ) -> Any: ...


class EmbedFn(Protocol):
    def __call__(self, query: str) -> list[float]: ...


class ToolSearchFn(Protocol):
    def __call__(
        self, embedding: list[float], *, query: str, domain: str | None
    ) -> list[dict[str, Any]]: ...


class McpCallFn(Protocol):
    def __call__(self, name: str, args: dict[str, Any]) -> Any: ...


class McpProbeFn(Protocol):
    """One MCP tool call, by name, with arguments already built (D10).

    No `db` / `session` parameter, deliberately: this is a NETWORK call, and threading a
    session in is the hold-a-connection-across-I/O hazard the plan's 96/100-connection
    incident is the evidence against. The production binding opens nothing.
    """

    def __call__(self, name: str, args: dict[str, Any]) -> Any: ...


class FamilyFetchFn(Protocol):
    """The product-family read the miss lane makes before offering a sibling.

    n8n does this as an HTTP call to a raw host; in process it is the products service.
    The seam takes a QUERY STRING and nothing else - no url, no session. Its production
    binding opens its own short session, which is why the caller (the answer lane) can
    stay session-free.
    """

    def __call__(self, query: str) -> Any: ...


@dataclass(frozen=True)
class AnswerServices:
    """S6c's two seams: the did-you-mean / sibling probes, and the family fetch."""

    mcp_probe: McpProbeFn
    family_fetch: FamilyFetchFn


@dataclass(frozen=True)
class FetchServices:
    """S6b's three seams, same shape as `ResolveGateServices` for the same reason.

    `embed` and `tool_search` are two halves of what `sub-get-rag` was (embed the prompt,
    then search) and they are separate because only the first is provider I/O: a test that
    wants a deterministic ranking stubs `tool_search` and leaves the embedding alone.
    """

    embed: EmbedFn
    tool_search: ToolSearchFn
    mcp_call: McpCallFn


@dataclass(frozen=True)
class ResolveGateServices:
    """One bundle, three callables. Stub any of them in a test; none of them is optional."""

    access_types: AccessTypesFn
    resolve_entity: ResolveEntityFn
    probe: ProbeFn


# --------------------------------------------------------------------------- #
# Production bindings
# --------------------------------------------------------------------------- #


def _access_types(db: Session, *, default_space_id: str | None = None) -> AccessTypesFn:
    def call(*, contact_id: str, space_id: str | None) -> list[dict[str, Any]]:
        """`GET /external/contact-access-types/active` - `[{name, keywords}]`.

        A contact / space pair the CRM does not know raises, exactly as the endpoint's
        404 did. n8n carries `onError: continueErrorOutput` on this node with the error
        branch unwired, so today that turn simply STOPS; in the port it becomes a failed
        turn with a reason, which `run_turn`'s handler records (H32).
        """
        from app.services.contact_access_type_service import ContactAccessTypeService

        workspace = space_id if space_id else default_space_id
        return ContactAccessTypeService(db).resolve_active_access_levels_for_contact(
            str(contact_id or "").strip(), str(workspace or "").strip()
        )

    return call


def _resolve_entity(db: Session) -> ResolveEntityFn:
    def call(body: dict[str, Any]) -> dict[str, Any]:
        """`POST /api/v1/system/references/resolve`, in process.

        The ROUTE function is called, not `_resolve_input` alone: the spec-search
        fallback, the brand stamp and the `ENTITY_PIN_MISMATCH` 400 (H38) all live in the
        route body, and re-implementing that half here would be a second resolver that
        drifts. `contact_id` / `space_id` are query params the route never reads, so the
        in-process call needs neither.

        `current_user` exists only to attribute the spec-search LLM usage log. It is the
        same principal the n8n key resolves to (`EXTERNAL_API_KEY_ACT_AS_USER_ID`), so the
        usage rows keep landing on the same user after the cut.
        """
        from app.api.v1.system.references import ResolveReferenceRequest, resolve_reference_post
        from app.config import settings

        principal = {"id": getattr(settings, "external_api_key_act_as_user_id", None)}
        return resolve_reference_post(
            ResolveReferenceRequest(**body), current_user=principal, db=db
        )

    return call


def _probe(db: Session | None = None) -> ProbeFn:
    """No session parameter is USED: the probe is an MCP call, not a database one (D10).

    The parameter exists so the bundle builder can pass its session without knowing that,
    exactly as `_mcp_probe` takes one and ignores it.
    """
    probe = _mcp_probe(db)

    def call(
        *,
        tool: str,
        contact_id: Any,
        entities: Any,
        semantic_input: dict[str, Any],
        user_prompt: str,
    ) -> Any:
        """`Call 'sub-get-results'` for one picker probe, via the in-process MCP client.

        D10: the business lane calls the MCP server through `MCPRuntimeClient` (precedent:
        `ai_assistant_service`), at the CONFIGURED url, never a raw IP (H52). The result is
        the tool's own render envelope, which is what both annotators read
        (`{answers|items: [...]}`).

        This seam raised `NotImplementedError` until 7 Sep 2026, on the grounds that
        `sub-get-results`' first node (`entity-ids-transformer`) and its renderer had not
        been ported - so every ambiguous-customer turn rendered the BARE picker and the
        owner's "has DO" / "no DO" stamp could never appear on a live turn. Both halves
        landed with `_mcp_probe` (#705, lesson 102): the transformer runs at the
        sub-workflow boundary and `parse_mcp_content` turns the client's STRING back into
        the envelope. The picker probe is the same sub-workflow call with the same
        `workflowInputs`, so it is wired to the same seam rather than to a second one -
        `crm_order_management_orders_list` is the orders read the CRM already serves, and
        rebuilding its render envelope in process would be a second presenter to keep in
        step with `sorento_crm_mcp/presenters.py`, which is the file the annotators' field
        labels ("Customer", "Actual Delivery Date") are read from.

        A failure still reaches the annotators as the documented UNPROBED arm:
        `resolve_gate._run_probe` catches, logs and returns None, which renders the bare
        picker rather than a confident miss on evidence nobody gathered.
        """
        return probe(
            tool,
            {
                "tool": tool,
                "contact_id": contact_id,
                "entities": entities,
                "semantic_input": semantic_input,
                "user_prompt": user_prompt,
            },
        )

    return call


class EmbeddingUnavailable(RuntimeError):
    """No embedding provider is configured, so no tool can be chosen this turn."""


def _embed(db: Session) -> EmbedFn:
    def call(query: str) -> list[float]:
        """`text-embedding-3-small`, through the shared LLM provider.

        NOT `app.api.v1.external.rag._embed_query`: that is a router private, and it raises
        `HTTPException` - a web-layer failure shape that would surface from inside a turn as
        a status code nobody asked for. The provider is the same model the RAG endpoint
        uses, so the vector is identical; only the failure semantics change, to a lane
        error the engine already knows how to record.
        """
        from app.config import settings
        from app.services.llm_provider import get_provider

        if not settings.openai_api_key:
            raise EmbeddingUnavailable(
                "no embedding provider is configured, so no MCP tool can be selected"
            )
        provider = get_provider("openai", settings.openai_api_key)
        vector = provider.embed(query)
        if not vector:
            raise EmbeddingUnavailable("the embedding provider returned an empty vector")
        return list(vector)

    return call


def _tool_search(db: Session) -> ToolSearchFn:
    def call(
        embedding: list[float], *, query: str, domain: str | None
    ) -> list[dict[str, Any]]:
        """`sub-get-rag`'s SQL plus both of its Code nodes, in one service call (H53).

        The two Code nodes did the interesting half: the second collapses `source_id` to
        the tool name after `implemented::` and SUMS the similarities per name, which is
        why `tool-filter` cannot simply take the first row. The fold itself is
        `fetch.collapse_tool_rows` (a ported node with its own 38 captures); this seam is
        the half that must not leave the service layer - the query.

        **H58: the READ-ONLY filter is here, on the CHATBOT's own retrieval.** The
        `mcp_tool` pool is shared with the in-app AI assistant, which retrieves its four
        record actions from it ON PURPOSE (`record_action_bootstrap`) and gates them behind
        a user confirmation and a permission check - so the pool must keep them and the
        chatbot must not see them. This seam rather than `fetch.tool_filter` for two
        reasons: `tool_filter` is a ported node graded byte-for-byte against 38 captures
        (D8) and this rule is not part of what that node does, and filtering BEFORE the
        pick means a write tool is not even listed among `_tool_pick.rejected`, so nothing
        downstream can reach for one.

        The filter runs AFTER the SQL `limit`, so a query whose neighbours are write tools
        yields fewer than five candidates and can end at `not_found` - which is an
        answerable outcome (H11), and the right one: the chatbot has nothing to say about a
        question whose only matches were actions it may not take.
        """
        from app.services.embedding_service import EmbeddingReadService

        from app.services.chatbot.lanes.business.fetch import (
            CHATBOT_READ_ONLY_TOOLS,
            collapse_tool_rows,
        )

        rows = EmbeddingReadService(db).search_tool_chunks(
            embedding, source_type="mcp_tool", limit=5, domain=domain
        )
        return [
            tool
            for tool in collapse_tool_rows(rows)
            if tool.get("name") in CHATBOT_READ_ONLY_TOOLS
        ]

    return call


def _mcp_call(db: Session | None = None) -> McpCallFn:
    def call(name: str, args: dict[str, Any]) -> Any:
        """One MCP tool call at the CONFIGURED url (H52, D10).

        n8n bakes `http://<raw ip>:8765/mcp` into two nodes. This reads
        `settings.ai_assistant_mcp_url`, the same setting the AI assistant already uses, so
        an environment moves the endpoint without a deploy of anything but config.

        H58: the read-only check is on THIS seam, not only on `fetch.call_tool`, because
        the probes reach for the bundle directly (`answer.mcp_probe`, `miss_suggest`'s
        three, the did-you-mean probe) and go nowhere near the ported call node. This is
        the single choke point where a tool name becomes an MCP request, so it is where the
        rule has to hold. The probes name read tools and are unaffected.

        **The PARSE is here too, for the same reason the read-only check is.**
        `MCPRuntimeClient.call_tool` returns a STRING - `"\\n".join` of the `content[]`
        text blocks, or `json.dumps(result)` when there are none. The fetch step ran the
        answer through `fetch.parse_mcp_content`; the four probe seams
        (`answer.run_crossdomain` and `miss_suggest`'s three) did not, so every probe
        answer arrived as a string, `run_crossdomain`'s
        `probe_result if isinstance(probe_result, dict) else {}` dropped it, and
        `crossdomain_render` degraded to `no_envelope` on turns that had a perfectly good
        answer. Parsing at the seam fixes all four at once and is idempotent: the fetch
        path's own `parse_mcp_content` returns a non-string unchanged.
        """
        from app.config import settings
        from app.services.ai_assistant_service import MCPRuntimeClient
        from app.services.chatbot.lanes.business.fetch import ensure_read_only, parse_mcp_content

        ensure_read_only(name)

        # The plan's capacity section bounds each MCP call at 10 s, and the AI assistant's
        # own 20 is a different budget for a different surface (a user watching a screen,
        # not a customer waiting on WhatsApp inside a whole turn's latency target).
        # `CHATBOT_MCP_TIMEOUT_SECONDS` overrides it per environment.
        timeout = int(getattr(settings, "chatbot_mcp_timeout_seconds", 0) or 10)
        client = MCPRuntimeClient(settings.ai_assistant_mcp_url, timeout_seconds=timeout)
        return parse_mcp_content(client.call_tool(name, args))

    return call


def _mcp_probe(db: Session | None = None) -> McpProbeFn:
    """The PROBE seam: `sub-get-results`' workflowInputs in, the tool's answer out.

    The four probe call sites build what the n8n node builds - `crossdomain-probe`'s and
    `dym-probe` / `sibling-probe` / `promo-dym-probe`'s `workflowInputs`, which is
    `{tool, contact_id, entities, semantic_input, user_prompt}`. In n8n that goes to a
    SUB-WORKFLOW whose first node is `entity-ids-transformer`; the port called the MCP
    client with it directly, so the tool got `entities` / `semantic_input` / `user_prompt`
    and none of the filter keys it takes.

    MEASURED against the local MCP on 6 Sep 2026: `crm_incoming_stock_list` answers those
    arguments with `{"data": [], "total": 0, "page": 1, "limit": null}` - the raw list
    serialiser, with no `items` / `answers` / `has_result`, so the renderer degrades even
    once the string is parsed. The same call with `entity_ids_transformer`'s arguments
    answers with the render envelope. So this is not tidiness: without it the probe asks
    the wrong question and cannot be answered.

    The transform lives HERE rather than at the four call sites because those sites are
    ported NODES, graded against captures of the `workflowInputs` they emit
    (`test_s6c_answer_lane.py::TestCrossdomainProbe`). The sub-workflow boundary is the
    seam, so the seam is where its first node runs - which is exactly what `run_fetch`'s
    own tier probe already does inline.
    """
    call = _mcp_call(db)

    def probe(name: str, args: dict[str, Any]) -> Any:
        from app.services.chatbot.lanes.business.fetch import entity_ids_transformer

        trigger = dict(args) if isinstance(args, dict) else {}
        # `miss_suggest._probe_args` passes the tool as the first parameter and leaves it
        # off the body; `crossdomain_probe_args` puts it on both. The name wins either way,
        # because it is the name `_mcp_call` will actually call.
        trigger["tool"] = name
        semantic = trigger.get("semantic_input")
        # Both builders resolve the workspace through `fetch.space_id_or_default` before
        # they write it, so reading it back is exact - and passing it on keeps the
        # transformer from falling back to n8n's literal on an install that has a
        # workspace row.
        space_id = semantic.get("space_id") if isinstance(semantic, dict) else None
        return call(name, entity_ids_transformer(trigger, space_id=space_id))

    return probe


def _family_row(row: Any) -> dict[str, Any]:
    """One products row as `sibling-transform` reads it: `product_code` and `id`.

    Those are the ONLY two keys the port takes off a family row
    (`miss_suggest._sibling_transform`, which also accepts the `code` / `uuid` spellings),
    so nothing else is serialised - a wider dict would be a shape nobody reads and a set
    of ORM attributes to keep loaded.
    """
    if isinstance(row, dict):
        return row
    uuid = getattr(row, "id", None)
    return {
        "product_code": getattr(row, "product_code", None),
        "id": str(uuid) if uuid else None,
    }


def _family_fetch(db: Session) -> FamilyFetchFn:
    def call(query: str) -> Any:
        """`family-fetch`: the sibling/family lookup, through the products service.

        n8n calls a raw host over HTTP for this (the same class of hazard as H52's MCP
        endpoint). In process it is a service call, so there is no url to go stale and no
        credential in the workflow.

        **The rows are SERIALISED, and that is what makes the seam usable.** n8n receives
        JSON; `ProductService.list_products` returns `{"data": [Product ORM objects]}`,
        and `jsc.get(row, "product_code")` returns its default on anything that is not a
        dict - so `sibling_transform` found no siblings on any live turn and the D3
        family offer was silently skipped for every partly-typed variant code.
        """
        from app.services.product_service import ProductService

        # n8n's `family-fetch` is
        # `GET https://<raw ip>/api/v1/master-data/products?query=..&variant_filter=all&limit=5000`.
        # Same read, same three parameters, no host and no credential (the H52 class of
        # hazard, on a second node).
        payload = ProductService(db).list_products(
            query=query, variant_filter="all", limit=5000, page=1
        )
        rows = payload.get("data") if isinstance(payload, dict) else None
        return {"data": [_family_row(row) for row in (rows if isinstance(rows, list) else [])]}

    return call


def production_answer_services(db: Session) -> AnswerServices:
    """S6c's bundle. The probe is the SAME MCP client the fetch step uses (H52, D10)."""
    return AnswerServices(mcp_probe=_mcp_probe(db), family_fetch=_family_fetch(db))


def answer_services_for(session_factory: Any) -> AnswerServices:
    """S6c's bundle, bound to a session FACTORY rather than to a live session.

    The answer lane makes two MCP probes and a products read, and the capacity rule says no
    database session is held across either. `production_answer_services(db)` binds
    `family_fetch` to the caller's session, which is right for a caller that already has one
    open and wrong for this lane, whose whole point is that it runs with none. So the family
    read opens its OWN short session and closes it again; the probe seam needs no session at
    all (`_mcp_probe` never touches its parameter).

    The wider "every bundle takes a factory" change is deliberately NOT made here - only the
    ONE bundle whose caller holds no session needs it today, and the rest have no such caller.
    """

    def family_fetch(query: str) -> Any:
        db = session_factory()
        try:
            return _family_fetch(db)(query)
        finally:
            db.close()

    return AnswerServices(mcp_probe=_mcp_probe(None), family_fetch=family_fetch)


def fetch_services(db: Session) -> FetchServices:
    """S6b's bundle. One session, bound at the call site, held across no provider I/O."""
    return FetchServices(embed=_embed(db), tool_search=_tool_search(db), mcp_call=_mcp_call(db))


def fetch_space_id(db: Session) -> str | None:
    """The default respond workspace's `space_id` (D5), for the fetch step's tool args.

    n8n hard-codes `364817` in `entity-ids-transformer` and overrides `semantic_input` with
    it. D5 reassigns the VALUE, not a list of call sites, so the fetch step reads the
    workspace row like every other producer of it. Falls back to n8n's literal inside
    `entity_ids_transformer` when there is no workspace row, which keeps this install
    byte-identical and any other install correct.
    """
    from app.services.chatbot.head.access import default_space_id

    return default_space_id(db)


def production_services(db: Session, *, space_id: str | None = None) -> ResolveGateServices:
    """The bundle the engine uses. One session, bound at the call site.

    `space_id` is the bundle's DEFAULT workspace, used when the caller does not name one
    per call. `resolve_gate.run()` passes its own (the default respond workspace's, D5) on
    every production turn, so this only matters to a caller that builds the bundle with a
    workspace already in hand.
    """
    return ResolveGateServices(
        access_types=_access_types(db, default_space_id=space_id),
        resolve_entity=_resolve_entity(db),
        probe=_probe(db),
    )
