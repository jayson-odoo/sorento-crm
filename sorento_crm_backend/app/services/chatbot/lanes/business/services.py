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
