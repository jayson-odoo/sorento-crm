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


def _probe() -> ProbeFn:
    """No session parameter: the probe is an MCP call, not a database one (D10)."""

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

        **Argument BUILDING (`entity-ids-transformer`) and result RENDERING
        (`output-structurer`) are S6b and are not ported yet.** Until S6b lands this seam
        raises, and `resolve_gate` turns that into the annotators' own documented
        "unprobed" arm - the bare picker for the customer probe, and today's behaviour for
        the incoming probe. It never fabricates an answer set, because a probe that did
        not run must not read as a probe that found nothing.
        """
        raise NotImplementedError(
            "the picker probe needs sub-get-results' entity-ids-transformer and "
            "output-structurer, which land in S6b; until then the annotators render the "
            "unprobed picker"
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
        """
        from app.services.embedding_service import EmbeddingReadService

        from app.services.chatbot.lanes.business.fetch import collapse_tool_rows

        rows = EmbeddingReadService(db).search_tool_chunks(
            embedding, source_type="mcp_tool", limit=5, domain=domain
        )
        return collapse_tool_rows(rows)

    return call


def _mcp_call(db: Session) -> McpCallFn:
    def call(name: str, args: dict[str, Any]) -> Any:
        """One MCP tool call at the CONFIGURED url (H52, D10).

        n8n bakes `http://<raw ip>:8765/mcp` into two nodes. This reads
        `settings.ai_assistant_mcp_url`, the same setting the AI assistant already uses, so
        an environment moves the endpoint without a deploy of anything but config.
        """
        from app.config import settings
        from app.services.ai_assistant_service import MCPRuntimeClient

        # The plan's capacity section bounds each MCP call at 10 s, and the AI assistant's
        # own 20 is a different budget for a different surface (a user watching a screen,
        # not a customer waiting on WhatsApp inside a whole turn's latency target).
        # `CHATBOT_MCP_TIMEOUT_SECONDS` overrides it per environment.
        timeout = int(getattr(settings, "chatbot_mcp_timeout_seconds", 0) or 10)
        client = MCPRuntimeClient(settings.ai_assistant_mcp_url, timeout_seconds=timeout)
        return client.call_tool(name, args)

    return call


def _family_fetch(db: Session) -> FamilyFetchFn:
    def call(query: str) -> Any:
        """`family-fetch`: the sibling/family lookup, through the products service.

        n8n calls a raw host over HTTP for this (the same class of hazard as H52's MCP
        endpoint). In process it is a service call, so there is no url to go stale and no
        credential in the workflow.
        """
        from app.services.product_service import ProductService

        # n8n's `family-fetch` is
        # `GET https://<raw ip>/api/v1/master-data/products?query=..&variant_filter=all&limit=5000`.
        # Same read, same three parameters, no host and no credential (the H52 class of
        # hazard, on a second node).
        return ProductService(db).list_products(
            query=query, variant_filter="all", limit=5000, page=1
        )

    return call


def production_answer_services(db: Session) -> AnswerServices:
    """S6c's bundle. The probe is the SAME MCP client the fetch step uses (H52, D10)."""
    return AnswerServices(mcp_probe=_mcp_call(db), family_fetch=_family_fetch(db))


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
        probe=_probe(),
    )
