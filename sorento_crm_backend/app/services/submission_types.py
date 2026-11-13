"""The one table of submission types on the ideation path (WA-COMPLAINT-INTAKE, card v2).

A submission is an `idea` (a wish or a feature request, today's behaviour) or an `issue` (something
wrong with the CRM system or the AI assistant). Both travel the same path: the bot lane
(`ideation_capture_service.handle_capture_turn`) and the agent tool `crm_idea_create` build the ss
create through `build_create_payload`, which writes the type through `ss_fields_for_type`. Reading
back, `type_of_idea` maps an ss idea's `type` to the CRM type. A new type is a row here, not a path.

Core module: must not import `app.services.chatbot` (`tests/chatbot/test_import_boundary.py`).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SubmissionType:
    #: What a person sees (the /ideas Type column and filter).
    label: str
    #: The one field the item cannot be filed without.
    required_field: str
    #: The value of the ss `type` field; None sends no `type` (an idea's payload stays as it was).
    ss_type: str | None
    #: `ideation_capture_*` copy names (`chatbot_reply_copy`) of the ask-back and the filed reply.
    ask_copy: str
    complete_copy: str


SUBMISSION_TYPES: dict[str, SubmissionType] = {
    "idea": SubmissionType(
        label="Feature request", required_field="problem", ss_type=None,
        ask_copy="ask_idea", complete_copy="complete",
    ),
    "issue": SubmissionType(
        label="Issue", required_field="problem", ss_type="issue",
        ask_copy="ask_issue", complete_copy="complete_issue",
    ),
}
DEFAULT_TYPE = "idea"


def normalise_type(value: Any) -> str:
    """A known type key; anything else (missing, unknown, not text) is the default, `idea`."""
    key = value.strip().lower() if isinstance(value, str) else ""
    return key if key in SUBMISSION_TYPES else DEFAULT_TYPE


def ss_fields_for_type(submission_type: Any) -> dict[str, str]:
    """The ss create fields that carry the type: `{"type": "issue"}` for an issue, nothing for an idea."""
    ss_type = SUBMISSION_TYPES[normalise_type(submission_type)].ss_type
    return {"type": ss_type} if ss_type else {}


def type_of_idea(idea: dict[str, Any]) -> str:
    """The CRM type of an ss idea, read from its `type` key only (missing or unknown is an idea)."""
    value = idea.get("type") if isinstance(idea, dict) else None
    key = value.strip().lower() if isinstance(value, str) else ""
    for name, row in SUBMISSION_TYPES.items():
        if row.ss_type is not None and row.ss_type == key:
            return name
    return DEFAULT_TYPE
