"""Resolve the agent code a document states onto the salesperson master.

An AutoCount extract says `SEAN III` and nothing else about who sold the order. There is no
id, no email, no list of agents anywhere else in this system - so the code IS the key, and it
arrives spelled by whoever produced the export: `SEAN III`, `sean iii`, `  SEAN III `. All
three have to reach one row, or the demand class the captain fills in lands on one of them
while the other two keep classifying nothing and look, on screen, exactly like the feature
not working.

So one normalisation, `upper(btrim())`, applied on BOTH sides: the stored code and the
lookup. Storing the raw spelling and matching case-insensitively would leave the unique
constraint unable to stop the duplicate.

An unknown code is CREATED rather than refused (UAC AC-6.4). The captain has 38 of them and
no way to enter them ahead of the first upload, so blocking the file would make the feature
unusable on day one. Created rows carry `source='import'` and a NULL `demand_class`, which is
what lets the Test result report them as "new agent, unclassified" instead of quietly
inventing master data nobody knows to look at.
"""
from __future__ import annotations

from typing import Iterable, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.sales_agent import SalesAgent
from app.services.error_handler import AppException
from app.services.scm.demand_class import DEMAND_CLASSES, is_valid

#: `source` values. An import-created row is waiting for a human decision; a manual one has
#: had (or does not need) it.
IMPORT_SOURCE = "import"
MANUAL_SOURCE = "manual"


def normalize_code(code: Optional[str]) -> str:
    """The stored and compared form of an agent code: trimmed and upper-cased."""
    return (code or "").strip().upper()


def _lookup(db: Session, normalized: str) -> Optional[SalesAgent]:
    """The master row for an already-normalised code, matched however it was stored.

    Normalising the COLUMN too, rather than comparing to the stored string, so a row written
    before this service existed (the AutoCount mirror writes whatever AutoCount says) still
    resolves instead of being duplicated. The master is tens of rows, so the unindexed
    comparison costs nothing worth optimising.
    """
    if not normalized:
        return None
    return (
        db.query(SalesAgent)
        .filter(func.upper(func.btrim(SalesAgent.sales_agent)) == normalized)
        .first()
    )


def resolve(db: Session, code: Optional[str]) -> Optional[SalesAgent]:
    """The agent this code names, or None. Writes nothing - this is the preview's read."""
    return _lookup(db, normalize_code(code))


def resolve_many(db: Session, codes: Iterable[Optional[str]]) -> dict[str, SalesAgent]:
    """Normalised code -> agent, for the codes that exist. Absent codes are simply absent.

    One query per distinct code rather than an `IN` over the normalised column: the caller
    holds a handful of codes per file (38 in the captain's whole book), and the loop keeps
    the "however it was stored" matching in exactly one place.
    """
    out: dict[str, SalesAgent] = {}
    for code in codes:
        key = normalize_code(code)
        if not key or key in out:
            continue
        agent = _lookup(db, key)
        if agent is not None:
            out[key] = agent
    return out


def resolve_or_create(db: Session, code: Optional[str], *,
                      source: str = IMPORT_SOURCE) -> Optional[SalesAgent]:
    """The agent this code names, created if nobody holds it yet.

    An existing row is returned untouched - `source`, `person_label` and `demand_class` are
    the captain's, and a weekly re-upload that restated them would undo his classification
    every Monday and make the priority flap.

    A blank code creates nothing: an empty master row is one every later import would then
    resolve to.
    """
    key = normalize_code(code)
    if not key:
        return None
    existing = _lookup(db, key)
    if existing is not None:
        return existing
    agent = SalesAgent(sales_agent=key, source=source, is_active=True)
    db.add(agent)
    db.flush()
    return agent


def assert_demand_class(value: Optional[str]) -> Optional[str]:
    """Return the value, or refuse it because the planner cannot weigh it.

    Rejected rather than coerced: `dealer` coerced to `retail` would be a guess about a
    salesperson's book, and coerced to nothing would drop the class the admin was trying to
    set without saying so.
    """
    if is_valid(value):
        return value
    raise AppException(
        status_code=400,
        message=(
            f"{value!r} is not a demand class the fulfilment policy can weigh. "
            f"Use one of: {', '.join(DEMAND_CLASSES)}."
        ),
    )


def set_demand_class(db: Session, code: str, demand_class: Optional[str]) -> SalesAgent:
    """Classify an existing agent. Never creates one.

    Creating on the way past would let a typed code become a master row that then classifies
    orders under a code no document ever states.
    """
    assert_demand_class(demand_class)
    agent = resolve(db, code)
    if agent is None:
        raise AppException(
            status_code=404,
            message=f"No sales agent is held under the code {normalize_code(code)!r}.",
        )
    agent.demand_class = demand_class
    db.flush()
    return agent
