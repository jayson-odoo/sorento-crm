"""Tests for workflow forms schema validation and defaults.

Run: pytest tests/test_workflow_forms.py -v
"""
import pytest

from app.services.workflow_forms_service import (
    default_draft_schema,
    validate_schema,
    validate_submission_payload,
)


def test_default_draft_schema_has_one_initial_state():
    s = default_draft_schema()
    errs = validate_schema(s)
    assert errs == []
    initials = [x for x in s["states"] if x.get("is_initial")]
    assert len(initials) == 1


def test_validate_schema_rejects_two_initial_states():
    s = default_draft_schema()
    s["states"].append(
        {
            "id": "x",
            "name": "X",
            "code": "x",
            "is_initial": True,
            "is_terminal": False,
        }
    )
    errs = validate_schema(s)
    assert any("Exactly one state" in e for e in errs)


def test_validate_submission_payload_required_header():
    s = default_draft_schema()
    s["header_fields"] = [{"id": "title", "type": "text", "label": "Title", "required": True}]
    errs = validate_submission_payload(s, {}, [])
    assert any("required" in e.lower() for e in errs)


def test_validate_submission_payload_ok():
    s = default_draft_schema()
    s["header_fields"] = [{"id": "title", "type": "text", "label": "Title", "required": True}]
    errs = validate_submission_payload(s, {"title": "Hello"}, [])
    assert errs == []
