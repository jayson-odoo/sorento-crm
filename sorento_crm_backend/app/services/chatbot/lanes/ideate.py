"""The `ideate` lane: ideation is an MCP TOOL, not a special case (D6, AC-303).

The owner said it twice - "ideation should be at the MCP side" - so this lane does what
every business tool does: it calls `crm_ideation_turn` through the same
`MCPRuntimeClient` the AI assistant uses (D10) - an HTTP JSON-RPC client against the
configured MCP server, not an in-process call - with exactly the arguments
`ideate-turn-http` sends today. Nothing here knows that ideation is different from a stock
lookup, which is the whole point: the day a second write tool arrives it needs no lane.

Two ports, both small and both verbatim:

* `build_arguments` is `ideate-turn-http`'s `jsonBody` expression, including the
  `media_selection` derivation - which is derived from the parser's EXISTING
  `reference_positions` / `select_all_expanded` signals rather than by keyword-matching
  the customer's text (D11), and is OMITTED entirely when no media menu is open, because
  omitting is behaviourally identical to dismissing and a mid-selection CRM interrupt must
  never be swallowed.
* `build_reply` is `build-ideate-reply.js`: the endpoint already embeds the deep link in
  `reply_text` on `complete`, so the link is appended only when it is not already there
  (unconditional appending rendered it twice), and `session_vars.ideation` is read through
  BOTH shapes because the endpoint keys it flat while n8n's own writer nests it.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Mapping

from app.services.chatbot import jsc

logger = logging.getLogger(__name__)

TOOL_NAME = "crm_ideation_turn"


def build_arguments(ctx: Mapping[str, Any]) -> dict[str, Any]:
    """`ideate-turn-http`'s body, field for field.

    `respond_io_id` is `String(...)`-coerced because respond.io contact ids arrive as
    numbers on some webhook shapes and the endpoint keys a text column on it.
    """
    qf = jsc.get(jsc.get(ctx, "parse"), "output") or {}
    session_vars = jsc.get(jsc.get(ctx, "session"), "session_vars") or {}
    # BOTH shapes, same as the JS: n8n's writer nests under `variables`, the endpoint
    # keys `ideation` flat.
    nested = jsc.get(jsc.get(session_vars, "variables"), "ideation")
    ideation = nested if jsc.truthy(nested) else jsc.get(session_vars, "ideation")
    ideation = ideation if ideation is not None else None

    inner = jsc.get(jsc.get(jsc.get(ctx, "text"), "message"), "message") or {}
    body: dict[str, Any] = {
        "respond_io_id": jsc.js_string(jsc.get(jsc.get(ctx, "contact"), "id")),
        "message_text": jsc.get(inner, "text"),
        "session_vars": {"ideation": ideation},
    }
    name = jsc.get(jsc.get(ctx, "contact"), "firstName")
    if jsc.truthy(name):
        body["submitter_name"] = name

    # ONLY when a media menu is outstanding. No menu open means the field is omitted and
    # the turn routes normally.
    if jsc.truthy(ideation) and jsc.truthy(jsc.get(ideation, "pending_media")):
        positions = jsc.get(qf, "reference_positions")
        positions = positions if jsc.is_array(positions) else []
        if len(positions) > 0:
            body["media_selection"] = ",".join(jsc.js_string(p) for p in positions)
        elif jsc.get(qf, "select_all_expanded") is True:
            body["media_selection"] = "all"
    return body


def call_ideation_tool(**kwargs: Any) -> dict[str, Any]:
    """Call `crm_ideation_turn` through the MCP client (D6, D10).

    A SEAM, deliberately: every test in the suite patches this one name, so nothing below
    it has to be mocked and no test reaches a live MCP server. The tool returns its result
    as MCP content text, so it is decoded here rather than at the call site - a caller
    that had to know MCP's envelope would be a caller that knows ideation is special.
    """
    from app.services.ai_assistant_service import MCPRuntimeClient
    from app.services.ai_assistant_service import settings as ai_settings

    # The SAME configured endpoint the AI assistant calls (H52: the URL is configuration,
    # never a literal), so there is one MCP address in the install and not two.
    client = MCPRuntimeClient(
        ai_settings.ai_assistant_mcp_url,
        timeout_seconds=ai_settings.ai_assistant_mcp_timeout_seconds,
    )
    raw = client.call_tool(TOOL_NAME, dict(kwargs))
    try:
        decoded = json.loads(raw)
    except (TypeError, ValueError):
        # The tool answered with prose rather than JSON, which is a broken tool and not a
        # shape to guess at. Raised so the turn is recorded `failed` with the text.
        raise RuntimeError(f"{TOOL_NAME} returned a non-JSON payload: {str(raw)[:200]}")
    if not isinstance(decoded, dict):
        raise RuntimeError(f"{TOOL_NAME} returned {type(decoded).__name__}, expected an object")
    return decoded


def build_reply(result: Mapping[str, Any]) -> dict[str, Any]:
    """`build-ideate-reply.js` - the item it puts on the shared compile path.

    `ideation` is the pointer the tail persists, and it is read through both session-vars
    shapes. `ideate_status` defaults to `'error'`, which is the JS's own fallback and the
    reason a tool that answers without a status still reads as a failure on the trace.
    """
    r = result if isinstance(result, dict) else {}
    response = jsc.get(r, "reply_text") or ""
    link = jsc.get(r, "link")
    if jsc.get(r, "status") == "complete" and jsc.truthy(link) and jsc.js_string(link) not in response:
        response = f"{response}\n\n{jsc.js_string(link)}"

    session_vars = jsc.get(r, "session_vars") or {}
    if jsc.has(session_vars, "ideation"):
        ideation = jsc.get(session_vars, "ideation")
    else:
        ideation = jsc.get(jsc.get(session_vars, "variables"), "ideation")
    return {
        "response": response,
        "manualResponse": True,
        "includeResponse": True,
        "ideation": ideation if ideation is not None else None,
        "ideate_status": jsc.get(r, "status") or "error",
    }


def run(ctx: Mapping[str, Any], item: Mapping[str, Any]) -> dict[str, Any]:
    """The whole lane: build the arguments, call the tool, hand the tail its fragment.

    The reply rides on `item.outcome_fragment['build-ideate-reply']` - RS-6.1c's own
    mechanism, and the exact key `build-outcome` reads - so the tail needs no ideate arm.

    **The item is `build-ideate-reply`'s own output, and it carries NO `branch_kind`.**
    That is not tidiness. `entry-gate` fires on `(item.branch_kind ?? '') !== ''`, so an
    item that kept the router's tag would run `escalate-catalog` on a turn n8n never runs
    it on - and `ideate` is not one of its nine arms, so it would fall through the switch
    and put an EMPTY response into the outcome hub. The compile ladder happens to check
    the ideate fragment first, so today that empty arm loses; a ladder edit is all it
    would take for it to win, which is exactly the shape S4 hit on `low_signal`.
    """
    result = call_ideation_tool(**build_arguments(ctx))
    reply = build_reply(result)
    return {
        "item": {**reply, "outcome_fragment": {"build-ideate-reply": reply}},
        "reply_extras": {
            "manualResponse": reply["manualResponse"],
            "includeResponse": reply["includeResponse"],
            "ideate_status": reply["ideate_status"],
        },
    }
