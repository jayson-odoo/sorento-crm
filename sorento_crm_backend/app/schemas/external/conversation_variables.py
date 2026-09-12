"""External conversation-state schemas: the five-key dialogue state, keyed by respond_io_id.

AC-1034. The body used to be `RootModel[dict[str, Any]]` - arbitrary JSON, no validation at
all - which is why a legacy key such as `picker_domain` could be written into a live
contact's memory and stay there. It is now the same five keys
`app/services/chatbot/contracts.py::SessionVars` declares, `extra="forbid"`, with no
compatibility shim: a writer sending the 34-key shape gets a 422 naming the key rather
than a session the engine cannot read.

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


class ConversationStateOverwriteRequest(BaseModel):
    """The dialogue state that replaces `respond_contacts.session_vars` wholesale.

    Every field is optional and defaults to null, because a caller clearing the state
    sends the shape with nothing in it - that is a reset, and it is a legitimate write.
    `Any` per field rather than the engine's own `Focus` / `OpenQuestion` models for the
    same AC-002 reason the docstring above gives: the STRUCTURE is what this endpoint
    owes, and the engine validates the contents on its own side of the line.
    """

    model_config = ConfigDict(extra="forbid")

    focus: Any = None
    open_question: Any = None
    ideation: Any = None
    access_levels: Any = None
    contains_flyer: Any = None
