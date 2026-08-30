"""Registry of deferrable form-SLA actions (PLAN-form-sla-undo.md).

The load-bearing rule: ``execute`` calls the EXISTING, unmodified service method. The
deferred path and the immediate path must be the same code, or an approve that waited
out its grace window stops matching an approve that did not, and the two drift within a
release. Never inline logic here.

``capture`` snapshots exactly the columns the method is about to overwrite, read BEFORE
it runs. ``invert`` writes those captured values back - never a default, never a guess.
An inverse that writes a constant instead of a captured value is a review failure.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, Optional

logger = logging.getLogger(__name__)


def _captures_nothing(_db, _payload) -> dict:
    """A record action has no prior state to restore: it is deferred, never undone."""
    return {}


def _emits_no_event(_payload) -> None:
    """A record action closes no form-SLA stage, so it resolves no event."""
    return None


@dataclass(frozen=True)
class FormAction:
    """One deferrable action.

    ``execute``/``capture`` take ``(db, payload)``; ``invert`` takes ``(db, record)``
    where ``record`` is the ``SlaFormAction`` row carrying ``prior_state_json``.
    ``invert=None`` means the action can be deferred (so a misclick is still catchable
    inside the grace window) but cannot be reversed after it commits.

    Two families share this shape (D7, S6). A FORM action closes an SLA stage, so it
    snapshots prior state and names its resolve-event. A RECORD action - deleting a
    product, re-statusing a delivery order - has neither: the grace window IS the way
    back, and once it lapses the record is simply gone. Those three fields therefore
    default to nothing rather than being invented per registration.
    """

    key: str
    entity_types: tuple[str, ...]
    execute: Callable
    capture: Callable = _captures_nothing
    invert: Optional[Callable] = None
    # (payload) -> the resolve-event this action will emit. The guardrail uses it to
    # find the stage the action closed.
    resolve_event: Callable = _emits_no_event
    # True when committing already told the contact something, so a post-grace undo
    # owes them a correction (AC-N-5).
    tells_contact: bool = False
    # Human label for the verb, e.g. "Approval" - one place, so FE copy and the undo
    # dialog cannot disagree about what is being reversed.
    label: str = "Action"
    # Which grace window this action draws from: "destructive" (10s) or "reversible"
    # (5s). Unset falls back to the verb in the key, so a `<entity>.delete` cannot be
    # registered with the short window by omission (S6-04).
    window: Optional[str] = None
    # The permission slug the route enforces BEFORE parking the action. A form action
    # is dispatched from inside a route that has already checked its own grant, so it
    # leaves this unset; a record action is parked through the generic
    # /pending-actions route, which has no slug of its own to check.
    permission: Optional[str] = None


REGISTRY: dict[str, FormAction] = {}


def register(action: FormAction) -> FormAction:
    if action.key in REGISTRY:
        raise ValueError(f"Duplicate form action key: {action.key}")
    REGISTRY[action.key] = action
    return action


def get_action(key: str) -> Optional[FormAction]:
    return REGISTRY.get(key)


def action_for(key: str) -> FormAction:
    action = REGISTRY.get(key)
    if action is None:
        raise KeyError(f"Unknown form action key: {key!r}")
    return action
