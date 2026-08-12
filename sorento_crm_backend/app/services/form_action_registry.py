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


@dataclass(frozen=True)
class FormAction:
    """One deferrable action.

    ``execute``/``capture`` take ``(db, payload)``; ``invert`` takes ``(db, record)``
    where ``record`` is the ``SlaFormAction`` row carrying ``prior_state_json``.
    ``invert=None`` means the action can be deferred (so a misclick is still catchable
    inside the grace window) but cannot be reversed after it commits.
    """

    key: str
    entity_types: tuple[str, ...]
    execute: Callable
    capture: Callable
    invert: Optional[Callable]
    # (payload) -> the resolve-event this action will emit. The guardrail uses it to
    # find the stage the action closed.
    resolve_event: Callable
    # True when committing already told the contact something, so a post-grace undo
    # owes them a correction (AC-N-5).
    tells_contact: bool = False
    # Human label for the verb, e.g. "Approval" - one place, so FE copy and the undo
    # dialog cannot disagree about what is being reversed.
    label: str = "Action"


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
