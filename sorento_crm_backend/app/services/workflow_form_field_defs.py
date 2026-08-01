"""Extract dynamic list-query field definitions from a `FormDocument`.

Replaces the private field-collecting helper in `workflow_forms_service`, which read
the retired old-shape document (`header_sections` / `header_fields` / `line_groups`).

**Why a separate module rather than a patch to that service.**
`workflow_submission_dynamic_list_query` imported that private helper, and
`app/api/v1/list_query.py` imports that, and `app.main` mounts the list-query
router. So a private helper inside a form service sat on the API's **boot import
path**: removing it during F1 would raise `ImportError` at uvicorn startup, taking
the whole API down rather than breaking one screen (ADR-0013 rule 12). Inverting the
dependency fixes the shape as well as the symbol: the list-query stack now depends
on a small pure function instead of a 1,009-LOC service scheduled for retirement.

**The identifier changes from field id to answer key.** The filter compiler does
`jsonb_extract_path_text(header_data, <name>)`, a single top-level lookup, and F0
stores answers keyed by field `key`. So the compiler needs no change at all, but the
name handed to it must be the `key`. Passing `FormField.id` would extract a path
that never exists, and every filter would silently match nothing.

**Repeaters and Tables become line groups, not header fields.** Their rows belong in
`workflow_submission_lines` rather than nested in `header_data`, because F1a puts a
`status_id` FK and a disposition on each line and a JSONB row cannot carry a foreign
key.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from app.form_engine.schemas import DISPLAY_FIELD_TYPES, FormDocument

logger = logging.getLogger(__name__)

# Fields whose rows live in `workflow_submission_lines`, keyed by the field's key.
_LINE_GROUP_TYPES = frozenset({"repeater", "table"})

FieldDef = Dict[str, Any]
LineGroup = Tuple[str, List[FieldDef]]


def _as_def(key: Optional[str], label: str, field_type: str) -> Optional[FieldDef]:
    """The dict shape `build_dynamic_field_metas_for_definition` consumes.

    ``id`` carries the answer KEY on purpose - see the module docstring. The name is
    kept as ``id`` so the existing consumer needs no change, which keeps this a
    drop-in during a slice that already changes a lot.
    """
    if not key:
        return None
    return {"id": key, "label": label, "type": field_type}


def collect_field_defs(schema: Any) -> Tuple[List[FieldDef], List[LineGroup]]:
    """``(header_fields, [(line_group_key, fields)])`` from a form document.

    Returns empty for anything unparseable, and **logs a warning when it does**.
    Raising is wrong here: this runs while serving a list-query response for an
    already-published snapshot, so a hard failure would 500 a grid the user cannot
    repair. But returning empty silently is the exact trap F1 is guarding against,
    since it drops every dynamic column with no trace. Hence: empty plus a warning.

    An empty-but-valid document (a form with no fields yet) is legitimate and does
    NOT warn.
    """
    if not isinstance(schema, dict):
        if schema not in (None, "", [], {}):
            logger.warning(
                "Cannot read form document for list-query fields: expected a dict, got %s",
                type(schema).__name__,
            )
        return [], []

    try:
        doc = FormDocument.model_validate(schema)
    except Exception as exc:  # pydantic ValidationError, or anything malformed
        logger.warning(
            "Cannot read form document for list-query fields, dynamic columns will be "
            "absent: %s",
            exc,
        )
        return [], []

    header: List[FieldDef] = []
    line_groups: List[LineGroup] = []

    for _page, _section, field in doc.iter_fields():
        if field.type in DISPLAY_FIELD_TYPES:
            continue  # no answer key, so never a filterable column

        if field.type in _LINE_GROUP_TYPES:
            group = _line_group_for(field)
            if group is not None:
                line_groups.append(group)
            continue

        entry = _as_def(field.key, field.label, field.type)
        if entry is not None:
            header.append(entry)

    return header, line_groups


def _line_group_for(field: Any) -> Optional[LineGroup]:
    """A repeater's sub-fields or a table's columns, keyed by the parent's key."""
    if not field.key:
        return None

    if field.type == "repeater":
        members = field.repeater.fields if field.repeater else []
    else:
        members = field.table.columns if field.table else []

    fields = [
        entry
        for entry in (_as_def(m.key, m.label, m.type) for m in members)
        if entry is not None
    ]
    return field.key, fields
