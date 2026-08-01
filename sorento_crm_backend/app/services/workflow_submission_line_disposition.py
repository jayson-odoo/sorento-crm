"""A submission line's disposition: how a decided line will be settled.

**Not a status, and not a new master table.** A disposition is configurable master data
with no lifecycle: nothing moves through it, and the admin has to be able to add one
without a migration. So it reuses the existing lookup system -- a ``lookup_sets`` row,
its ``lookup_options``, and one ``lookup_bindings`` row for
``('workflow_submission_lines', 'disposition')`` -- exactly like the seven bindings that
already exist (``complaints.complaint_type`` and friends). The column is a ``String``
holding the option ``value``, with no FK to the lookup tables, because that is the shape
the admin dropdown UI, the keyword resolver and the default-value behaviour are all
written against.

**Orthogonal to the line's status.** What was decided and how it will be settled are
different questions: two lines on the same rung can hold different dispositions, and a
rejected line holds none. Neither is derived from the other.

Note the near-collision the UI has to keep apart: the line STATUS ``cancelled`` (the
line was withdrawn, and derivation excludes it) is a different thing from the
DISPOSITION ``cn_cancellation`` (a credit note cancels the charge).

**Validation is explicit.** ``lookup_write_listener`` is installed by ``app.main`` only,
so a service that relied on it would silently accept anything in a worker, a script or a
test. The writer calls ``assert_disposition_allowed`` itself.
"""
from __future__ import annotations

import uuid
from typing import Dict, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.lookup import LookupBinding, LookupOption, LookupSet
from app.services.lookup_validator import validate_lookup_value

LINE_DISPOSITION_SET_KEY = "workflow_submission_line_disposition"
LINE_DISPOSITION_SET_NAME = "Submission line disposition"
LINE_DISPOSITION_SET_DESCRIPTION = (
    "How an approved or rejected submission line will be settled."
)
LINE_DISPOSITION_TABLE = "workflow_submission_lines"
LINE_DISPOSITION_COLUMN = "disposition"
# "Nothing to collect" has to say why, and a reason has nowhere else to land.
LINE_DISPOSITION_REASON_COLUMN = "disposition_reason"

# The vocabulary the after-sales exchange/return flow actually uses. Seeded, not
# hardcoded behaviour: it is admin-editable master data, so nothing branches on these
# values and a deployment may add or retire one.
LINE_DISPOSITION_OPTIONS: Tuple[Tuple[str, str, str], ...] = (
    (
        "write_off",
        "Write off",
        "The item is scrapped and nothing is collected back from the customer.",
    ),
    (
        "cn_cancellation",
        "Credit note / cancellation",
        "Settled by credit note or by cancelling the charge.",
    ),
    (
        "replacement_same_model",
        "Replacement (same model)",
        "Replaced with the same model.",
    ),
    (
        "replacement_equivalent_value",
        "Replacement (equivalent value)",
        "Replaced with a different item of equivalent value.",
    ),
    (
        "replacement_wrong_model",
        "Replacement (wrong model supplied)",
        "Replaced because the wrong model was supplied.",
    ),
    ("repair", "Repair", "The item is repaired and returned."),
    ("maintenance", "Maintenance", "Serviced rather than replaced."),
    (
        "nothing_to_collect",
        "Nothing to collect",
        "No item comes back. Record the reason on the line.",
    ),
)


def _apply(row: object, values: Dict[str, object]) -> bool:
    """Set only the attributes that differ. True when something changed."""
    changed = False
    for field, value in values.items():
        if getattr(row, field, None) != value:
            setattr(row, field, value)
            changed = True
    return changed


def seed_workflow_submission_line_disposition_lookup(db: Session) -> Dict[str, int]:
    """Create or CORRECT the disposition set, its options and its binding.

    Converging rather than insert-if-absent, for the same reason a graph seed does: a
    re-run repairs a drifted label or a wrongly deactivated option IN PLACE, and can
    therefore fix a prior bad run. A duplicated set would be worse than a drifted one --
    the binding would have two candidate option lists and the validator would pick
    between them non-deterministically.

    ``tenant_id`` is NULL, like every existing binding, while the tenant is a stub.
    """
    summary = {
        "sets_created": 0,
        "sets_updated": 0,
        "options_created": 0,
        "options_updated": 0,
        "bindings_created": 0,
        "bindings_updated": 0,
    }

    lookup_set = (
        db.query(LookupSet)
        .filter(
            LookupSet.set_key == LINE_DISPOSITION_SET_KEY,
            LookupSet.tenant_id.is_(None),
        )
        .first()
    )
    set_values = {
        "name": LINE_DISPOSITION_SET_NAME,
        "description": LINE_DISPOSITION_SET_DESCRIPTION,
        "is_active": True,
    }
    if lookup_set is None:
        lookup_set = LookupSet(
            id=str(uuid.uuid4()),
            tenant_id=None,
            set_key=LINE_DISPOSITION_SET_KEY,
            **set_values,
        )
        db.add(lookup_set)
        summary["sets_created"] += 1
    elif _apply(lookup_set, set_values):
        summary["sets_updated"] += 1
    db.flush()  # the set id must exist before options and the binding reference it

    existing_options = {
        str(row.value): row
        for row in db.query(LookupOption)
        .filter(LookupOption.set_id == lookup_set.id)
        .all()
    }
    for index, (value, label, description) in enumerate(LINE_DISPOSITION_OPTIONS):
        option_values = {
            "label": label,
            "description": description,
            # Gaps of 10 so an admin can slot an option between two others.
            "sort_order": index * 10,
            "is_active": True,
        }
        row = existing_options.get(value)
        if row is None:
            db.add(
                LookupOption(
                    id=str(uuid.uuid4()),
                    set_id=lookup_set.id,
                    value=value,
                    **option_values,
                )
            )
            summary["options_created"] += 1
        elif _apply(row, option_values):
            summary["options_updated"] += 1

    # Options this seed no longer declares are LEFT ALONE, deliberately: the set is
    # admin-editable, so anything extra is somebody's configuration rather than drift.
    binding = (
        db.query(LookupBinding)
        .filter(
            LookupBinding.tenant_id.is_(None),
            LookupBinding.table_name == LINE_DISPOSITION_TABLE,
            LookupBinding.column_name == LINE_DISPOSITION_COLUMN,
        )
        .first()
    )
    if binding is None:
        db.add(
            LookupBinding(
                id=str(uuid.uuid4()),
                tenant_id=None,
                set_id=lookup_set.id,
                table_name=LINE_DISPOSITION_TABLE,
                column_name=LINE_DISPOSITION_COLUMN,
            )
        )
        summary["bindings_created"] += 1
    elif _apply(binding, {"set_id": lookup_set.id}):
        summary["bindings_updated"] += 1
    db.flush()

    return summary


def assert_disposition_allowed(db: Session, value: Optional[str]) -> None:
    """Reject an unknown or retired disposition. NULL is always allowed.

    NULL means "no disposition yet", which is a real state and the reason the column is
    nullable. Validation is against the ACTIVE options only: deactivating is the lookup
    system's way of saying "kept for existing rows, closed to new ones", and validating
    against every option would keep a retired disposition selectable forever.
    """
    validate_lookup_value(
        db,
        table=LINE_DISPOSITION_TABLE,
        column=LINE_DISPOSITION_COLUMN,
        value=value,
        tenant_id=None,
    )
