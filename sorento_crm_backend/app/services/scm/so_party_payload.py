"""Name the customer and project of every donor / debt / lent-to order inside a planning payload.

OI-UX-FILTER-SNAPSHOT (owner, 3 Nov 2026): wherever a sales order is named, its customer and
project are named with it. The fulfilment board and the SO supply sheet carry a donor order as a
bare `donor_so_number` in a dozen places (frozen compositions, ladder options, borrow candidates,
sources), so the payload is annotated once on the way out rather than at each builder.

Reads through `so_party.so_parties` (one query for the whole payload) and adds, beside
  * `donor_so_number`  -> `donor_customer_name`, `donor_project_label`
  * `debt_so_number`   -> `debt_customer_name`, `debt_project_label`
  * a `lent_to` entry  -> `customer_name`, `project_label` (its `so_number` is the borrower)
Nothing existing is renamed or overwritten.
"""
from __future__ import annotations

import copy
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from app.services.scm.so_party import EMPTY_PARTY, so_parties

#: number key -> prefix of the two fields added beside it
_NUMBER_KEYS = {"donor_so_number": "donor_", "debt_so_number": "debt_"}
_LENT_KEY = "lent_to"


def _collect(node: Any, numbers: List[str]) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            if key in _NUMBER_KEYS and isinstance(value, str) and value:
                numbers.append(value)
            elif key == _LENT_KEY and isinstance(value, list):
                numbers.extend(
                    entry["so_number"]
                    for entry in value
                    if isinstance(entry, dict) and entry.get("so_number")
                )
                _collect(value, numbers)
            else:
                _collect(value, numbers)
    elif isinstance(node, (list, tuple)):
        for item in node:
            _collect(item, numbers)


def _apply(node: Any, parties: Dict[str, Dict[str, Any]]) -> None:
    if isinstance(node, dict):
        for key, prefix in _NUMBER_KEYS.items():
            number = node.get(key)
            if isinstance(number, str) and number:
                party = parties.get(number, EMPTY_PARTY)
                node[f"{prefix}customer_name"] = party["customer_name"]
                node[f"{prefix}project_label"] = party["project_label"]
        lent = node.get(_LENT_KEY)
        if isinstance(lent, list):
            for entry in lent:
                if isinstance(entry, dict) and entry.get("so_number"):
                    party = parties.get(entry["so_number"], EMPTY_PARTY)
                    entry["customer_name"] = party["customer_name"]
                    entry["project_label"] = party["project_label"]
        for value in list(node.values()):
            _apply(value, parties)
    elif isinstance(node, (list, tuple)):
        for item in node:
            _apply(item, parties)


def attach_donor_parties(db: Session, payload: Any) -> Any:
    """A copy of `payload` (dicts and lists) with the party fields described above.

    Copied, because a service may hand back a frozen decision's own JSON, and annotating that
    in place would leak the extra keys into the ORM object."""
    numbers: List[str] = []
    _collect(payload, numbers)
    if not numbers:
        return payload
    annotated = copy.deepcopy(payload)
    _apply(annotated, so_parties(db, numbers=numbers))
    return annotated
