"""
Workflow submission list-query: schema-driven fields for header_data / line row_data (JSONB).

Design:
- Static columns stay in list_query_fields (DB). Dynamic fields are merged at runtime when
  ``definition_id`` is provided (published schema snapshot).
- Field keys are stable and namespaced: ``hdr:{field_id}``, ``ln:{line_group_id}:{field_id}``.
- compile_key format: ``wf_hdr:{field_id}``, ``wf_ln:{line_group_id}:{field_id}``.
- Filtering uses PostgreSQL JSONB operators; line conditions use EXISTS over workflow_submission_lines.

This keeps the global list_query catalog small while scaling to many forms and versions.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.workflow_forms import WorkflowFormDefinition, WorkflowFormVersion

# Reads F0's block document. Deliberately NOT the private field-collecting helper that
# used to live in `workflow_forms_service`: the list-query router is mounted by
# `app.main`, so importing a private helper out of a service that F1 retires put an
# ImportError-at-startup on the boot path. See app/services/workflow_form_field_defs.py.
from app.services.workflow_form_field_defs import collect_field_defs

# Field ids from the builder are typically UUIDs; allow safe slug-like ids.
_ID_SAFE = re.compile(r"^[a-zA-Z0-9_-]{1,128}$")


@dataclass
class DynamicListQueryField:
    """ORM-free stand-in for ListQueryField (used in filter/export merge maps)."""

    field_key: str
    label: str
    data_type: str
    compile_key: str
    allowed_operators: List[str]
    filterable: bool
    exportable: bool
    export_column_name: Optional[str]
    is_line_field: bool
    sort_order: int


def _ops_for_workflow_type(ft: Optional[str]) -> Tuple[str, List[str], bool]:
    """Return (data_type, allowed_operators, filterable).

    Covers BOTH vocabularies. The old-shape names (`checkbox`, `multi_select`,
    `date_range`) are kept so an in-flight caller cannot regress, and the F0
    block-document names are added alongside.

    Getting this wrong is silent rather than loud: an unmapped numeric type falls
    through to the string branch, and a string comparison puts "10" before "9". So
    every new type name is mapped explicitly instead of relying on the default.
    """
    t = (ft or "text").lower()
    if t in ("number", "integer", "rating", "computed"):
        return "number", ["eq", "ne", "gt", "gte", "lt", "lte", "is_null"], True
    if t in ("checkbox", "yesno"):
        return "boolean", ["eq", "is_null"], True
    if t in ("date", "datetime"):
        return "date", ["eq", "ne", "gt", "gte", "lt", "lte", "is_null"], True
    if t in ("multi_select", "date_range", "multiselect", "checkboxes"):
        # Stored as a JSON array or object, so equality is meaningless: contains only.
        return "string", ["contains", "is_null"], True
    return "string", ["eq", "ne", "contains", "starts_with", "in", "is_null"], True


def _validate_id(s: str) -> bool:
    return bool(s and _ID_SAFE.match(s))


def build_dynamic_field_metas_for_definition(schema: Dict[str, Any]) -> List[DynamicListQueryField]:
    """Build dynamic field metadata from a published workflow schema dict."""
    out: List[DynamicListQueryField] = []
    sort_base = 500

    header, line_groups = collect_field_defs(schema)
    for f in header:
        fid = f.get("id")
        if not _validate_id(str(fid)):
            continue
        label = str(f.get("label") or fid)
        ft = f.get("type")
        dtype, ops, filt = _ops_for_workflow_type(ft if isinstance(ft, str) else None)
        fk = f"hdr:{fid}"
        ck = f"wf_hdr:{fid}"
        out.append(
            DynamicListQueryField(
                field_key=fk,
                label=f"Header: {label}",
                data_type=dtype,
                compile_key=ck,
                allowed_operators=ops,
                filterable=filt,
                exportable=True,
                export_column_name=f"Header — {label}",
                is_line_field=False,
                sort_order=sort_base + len(out),
            )
        )

    for lg_id, fields in line_groups:
        if not _validate_id(str(lg_id)):
            continue
        gname = lg_id
        for f in fields:
            fid = f.get("id")
            if not _validate_id(str(fid)):
                continue
            label = str(f.get("label") or fid)
            ft = f.get("type")
            dtype, ops, filt = _ops_for_workflow_type(ft if isinstance(ft, str) else None)
            fk = f"ln:{lg_id}:{fid}"
            ck = f"wf_ln:{lg_id}:{fid}"
            out.append(
                DynamicListQueryField(
                    field_key=fk,
                    label=f"Line ({gname}): {label}",
                    data_type=dtype,
                    compile_key=ck,
                    allowed_operators=ops,
                    filterable=filt,
                    exportable=True,
                    export_column_name=f"Line — {label}",
                    is_line_field=True,
                    sort_order=sort_base + len(out),
                )
            )

    return out


def get_published_schema_for_definition(db: Session, definition_id: str) -> Optional[Dict[str, Any]]:
    d = (
        db.query(WorkflowFormDefinition)
        .filter(WorkflowFormDefinition.id == definition_id)
        .first()
    )
    if not d:
        return None
    pvid = getattr(d, "published_version_id", None)
    if pvid is None or str(pvid).strip() == "":
        return None
    v = db.query(WorkflowFormVersion).filter(WorkflowFormVersion.id == pvid).first()
    if not v:
        return None
    raw_schema = getattr(v, "schema", None)
    return raw_schema if isinstance(raw_schema, dict) else None


def merge_submission_field_maps(
    static_map: Dict[str, Any],
    definition_id: str,
    db: Session,
) -> Dict[str, Any]:
    """Merge DB-backed list_query fields with schema-driven dynamic fields."""
    schema = get_published_schema_for_definition(db, definition_id)
    if not schema:
        return static_map
    dyn = build_dynamic_field_metas_for_definition(schema)
    merged = dict(static_map)
    for m in dyn:
        merged[m.field_key] = m
    return merged


def filter_uses_dynamic_fields(filter_root: Any) -> bool:
    """True if filter tree references hdr:/ln: field keys."""
    if filter_root is None:
        return False
    op = getattr(filter_root, "op", None)
    if op in ("and", "or"):
        for c in getattr(filter_root, "children", []) or []:
            if filter_uses_dynamic_fields(c):
                return True
        return False
    fk = getattr(filter_root, "field_key", None)
    if not fk:
        return False
    s = str(fk)
    return s.startswith("hdr:") or s.startswith("ln:")
