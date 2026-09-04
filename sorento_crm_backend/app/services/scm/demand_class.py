"""The demand classes fulfilment priority is weighed on, in one place.

`scm.priority_policy.demand_class_weights` is keyed on these two words. A third one does not
rank lower - it drops out of the comparison entirely, because `rank_score` divides by the
weight of the factors actually present and a class with no weight contributes nothing. So an
order stamped `dealer` is not de-prioritised, it is un-ranked, and on screen that is
indistinguishable from an order nobody classified. Hence a CLOSED vocabulary, enforced where
the value is written rather than discovered weeks later as an order that stopped winning
stock.

Deliberately pure - no session, no models, no imports out of this package - so that both
sides can share it without importing each other: the reader
(`outstanding_import_service`, which maps a stated split or a market segment onto a class)
and the writer (`sales_agent_service` and the `sales_agents` table's own check constraint,
which decide what an admin may store on an agent).

`class_of` returning None is load-bearing and is NOT the same as returning the default:
"this is not a project" and "nobody said" look identical in a spreadsheet column and mean
opposite things. Only the first may be written; the second is reported.

**Import-cycle warning.** `app/models/sales_agent.py` imports `check_constraint_sql` from
here, so a model import now reaches into `app.services`. That is safe only while
`app/services/scm/__init__.py` stays import-free (it is a docstring today): the moment it
imports a service that imports a model, `app.models` -> `app.services.scm` -> `app.models`
becomes a cycle that fails at startup, not in a test. Keep this module free of everything,
and keep that `__init__` empty.
"""
from __future__ import annotations

from typing import Optional

#: Demand that belongs to a named project, which is what the weights favour.
PROJECT = "project"

#: Everything else the policy knows how to weigh. Named "default" because it is also the
#: safe write for a caller that must put something in the column.
DEFAULT_DEMAND_CLASS = "retail"

#: The whole vocabulary. Adding a third class is a weights change AND a migration on the
#: check constraint, deliberately: it must not be possible to smuggle one in through a
#: spreadsheet.
DEMAND_CLASSES = (PROJECT, DEFAULT_DEMAND_CLASS)

#: Words in a stated order type or a market-segment code that mean project work. Matched as
#: substrings because the real values are typed by people: `PROJECT`, `Projects`, `contract`.
PROJECT_SEGMENTS = frozenset({"project", "projects", "contract"})


def class_of(value: Optional[str]) -> Optional[str]:
    """The planning class a stated split maps to, or None when it states nothing."""
    stated = (value or "").strip().lower()
    if not stated:
        return None
    return PROJECT if any(seg in stated for seg in PROJECT_SEGMENTS) else DEFAULT_DEMAND_CLASS


def is_valid(value: Optional[str]) -> bool:
    """Whether this is a class the policy can actually weigh. None (unset) is valid."""
    return value is None or value in DEMAND_CLASSES


def check_constraint_sql(column: str = "demand_class") -> str:
    """The SQL predicate for the closed vocabulary, built from the vocabulary itself.

    Shared by the model's `CheckConstraint` and its migration so the two cannot drift into
    disagreeing about which words are allowed - which would show up only as a create_all
    database (CI) accepting a value the migrated one rejects.
    """
    allowed = ", ".join(f"'{c}'" for c in DEMAND_CLASSES)
    return f"{column} IS NULL OR {column} IN ({allowed})"


def classify_document(
    db,
    *,
    stored_order_type: Optional[str],
    stated_order_type: Optional[str],
    agent_demand_class: Optional[str],
    debtor_code: Optional[str],
    company_id,
) -> Optional[str]:
    """The demand class a sales document should carry (D4, plan section 1/2.3).

    ONE ladder, two callers - `outstanding_import_service._classify_demand`
    (the weekly upload) and the AutoCount document ingest - so a class the
    upload would decide and a class the ingest would decide can never disagree
    about the same order:

        stored order type -> stated order type -> the selling agent's demand
        class -> the customer's market segment (by debtor code, within
        company).

    `stored_order_type` outranks everything: a document does not restate its
    own settled history. `stated_order_type` outranks the agent and the
    customer because it is a statement about THIS document, where the other
    two are statements about the account and the salesperson in general.
    `agent_demand_class` is taken AS STORED, never through `class_of` - the
    agent master's own check constraint already limits it to the vocabulary,
    and running an already-valid value back through the segment matcher would
    turn a value that somehow escaped the constraint into a GUESSED `retail`,
    exactly the mistake this ladder exists to refuse.

    Returns `None` when nothing classifies - the caller decides what that
    means for its own record (the upload refuses the file; the ingest lands
    the record and warns `unclassified_demand`).

    The segment DB read is a lazy import from `demand_classifier`, a thin
    sibling this module does not import at module scope (see the module
    docstring's import-cycle warning) - `app.models.sales_agent` reaches into
    THIS module for `check_constraint_sql`, so a top-level model import here
    would close that cycle at start-up rather than at call time.
    """
    cls = class_of(stored_order_type) or class_of(stated_order_type) or agent_demand_class
    if cls is not None:
        return cls
    from app.services.scm.demand_classifier import segment_of

    return class_of(segment_of(db, debtor_code, company_id))
