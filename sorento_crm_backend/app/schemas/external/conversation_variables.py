"""External conversation-state schemas: the five-key dialogue state, keyed by respond_io_id.

AC-1034. The body used to be `RootModel[dict[str, Any]]` - arbitrary JSON, no validation at
all - which is why a legacy key such as `picker_domain` could be written into a live
contact's memory and stay there.

**And the five keys live UNDER `variables`.** The column is `{"variables": {...}}`: that is
what `get-session-vars` returns, what `save-session-vars` PUTs back, and what the engine
reads (`session_block.session_vars.variables`). A body that was the five keys FLAT
therefore replaced the wrapper with its contents and the next turn read an empty memory -
so the endpoint that exists to write the state was the one thing that could wipe it. The
model is the wrapper now, with the five keys `extra="forbid"` inside it, which is also what
makes a GET body a legal PUT body.

The five names are RESTATED here rather than imported. Core may not import
`app/services/chatbot/` (AC-002, `tests/chatbot/test_import_boundary.py` fails naming the
importer), and this module is core. `tests/test_conversation_variables_shape.py` holds the
two sides to the same list.
"""
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ConversationStateResponse(BaseModel):
    respond_io_id: str
    session_vars: dict[str, Any] = Field(default_factory=dict)


class ConversationStateVariables(BaseModel):
    """The five keys, and nothing else.

    Every field is optional and defaults to null, because a caller clearing the state
    sends the shape with nothing in it - that is a reset, and it is a legitimate write.
    `Any` per field rather than the engine's own `Focus` / `OpenQuestion` models for the
    same AC-002 reason the module docstring gives: the STRUCTURE is what this endpoint
    owes, and the engine validates the contents on its own side of the line.
    """

    model_config = ConfigDict(extra="forbid")

    focus: Any = None
    open_question: Any = None
    ideation: Any = None
    access_levels: Any = None
    contains_flyer: Any = None


class ConversationStateOverwriteRequest(BaseModel):
    """`{"variables": {...}}` - the shape the column holds and the shape the GET returns.

    The OUTER object is deliberately not `extra="forbid"`: a GET with `?message_id=` injects
    two response-only keys beside `variables`, and a caller that PUTs a GET body straight
    back must not be refused for keys this endpoint handed them. They are dropped on the
    way in (`model_dump` emits the declared field only), which is the same thing the old
    flat model did to every key it did not declare - the difference is that `variables`
    itself is now strict, which is where the wrong key was actually landing.
    """

    variables: ConversationStateVariables = Field(
        default_factory=ConversationStateVariables
    )
