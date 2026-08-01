"""Derived transitions — the wiring for auto edges.

An **auto edge** is a ``status_transitions`` row with ``trigger_mode='auto'`` and a
``conditions_json`` tree. When the conditions become true the engine moves the
record itself, with no user action. A **derived trigger** is what tells the engine
*when to re-check*: "a project purchase order was written, so re-evaluate its
project's auto edges".

Scope in S1 is deliberately narrow. This module ships the registry and the
re-evaluation entry point; the only auto edge in v1 is "first Project PO recorded
-> status becomes PO Received", which lands with the PO write path in S4. Two
pieces of the source are intentionally NOT ported yet, because nothing consumes
them and dead machinery rots:

- **Time-conditioned edges** (``has_time_auto_edges`` + a scheduler sweep). An
  edge keyed on a clock cannot be event-driven, so it needs a periodic sweep.
  Sorento's staleness ladder (S5) is an ``automations`` row instead, which already
  owns daily scheduling; if a genuine time-based *status* edge appears later, the
  sweep is added then.
- **Self triggers** (a record re-deriving on its own create/update). Nothing needs
  it until an entity gains an auto edge conditioned on its own columns.
"""
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session


@dataclass(frozen=True)
class DerivedTrigger:
    """A child-change -> owner-re-evaluate edge.

    ``trigger_entity`` is the entity event string the child's write path emits.
    ``resolve_owners(db, scope_id, event) -> [owner records]`` maps that event
    back to the owners whose auto edges should be re-checked.

    The contract that cannot be enforced here: the child's write path MUST emit
    its entity event, or the re-derivation never fires. That lives in the child
    service.
    """

    owner_entity: str
    trigger_entity: str
    resolve_owners: Callable[[Session, Optional[str], Dict[str, Any]], List[Any]]


# Keyed by (owner_entity, trigger_entity) so re-registration replaces rather than
# duplicates -- module bootstraps run on every process start.
_TRIGGERS: Dict[Tuple[str, str], DerivedTrigger] = {}


def register_derived_trigger(trigger: DerivedTrigger) -> None:
    """Idempotent."""
    _TRIGGERS[(trigger.owner_entity, trigger.trigger_entity)] = trigger


def triggers_for(trigger_entity: str) -> List[DerivedTrigger]:
    """Every registered trigger listening for this child entity's events."""
    return [t for t in _TRIGGERS.values() if t.trigger_entity == trigger_entity]


def list_derived_triggers() -> List[DerivedTrigger]:
    return list(_TRIGGERS.values())


def clear_derived_triggers() -> None:
    """Test-only reset."""
    _TRIGGERS.clear()
