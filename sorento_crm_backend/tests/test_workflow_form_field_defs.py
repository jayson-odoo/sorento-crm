"""Field-definition extraction from a `FormDocument`, for dynamic list-query columns.

Why this module exists at all, and why it is not in `workflow_forms_service`:

`workflow_submission_dynamic_list_query` imported `_collect_field_defs` from that
service, and the list-query router is mounted by `app.main`, so a private helper in
a form service sat on the API's boot import path. Deleting it during F1 would have
been an ImportError at startup rather than a broken screen (ADR-0013 rule 12). The
dependency is inverted here: the list-query stack depends on a small pure module,
not on a 1,009-LOC service that is being retired.

The failure this pins hardest is **silent-empty**. The old extractor reads
old-shape `header_sections` / `line_groups`; against F0's block document it finds
neither and returns nothing, so every dynamic grid column and export column
vanishes with no error anywhere. `test_a_new_shape_document_yields_fields` is the
guard: it asserts non-empty, not merely "does not raise".
"""
from __future__ import annotations

import pytest

from app.services.workflow_form_field_defs import collect_field_defs


def _doc(*fields, extra_section=None):
    """A minimal publishable document wrapping the given field dicts."""
    sections = [{"id": "sec1", "title": "Main", "fields": list(fields)}]
    if extra_section:
        sections.append(extra_section)
    return {
        "schemaVersion": 1,
        "pages": [{"id": "p1", "title": "Page 1", "sections": sections}],
    }


TEXT = {"id": "f1", "type": "text", "key": "customer_name", "label": "Customer Name"}
NUM = {"id": "f2", "type": "number", "key": "amount", "label": "Amount"}
DATE = {"id": "f3", "type": "date", "key": "needed_by", "label": "Needed By"}
HEADING = {"id": "d1", "type": "heading", "label": "Details"}

REPEATER = {
    "id": "f4",
    "type": "repeater",
    "key": "items",
    "label": "Items",
    "repeater": {
        "fields": [
            {"id": "s1", "type": "text", "key": "sku", "label": "SKU"},
            {"id": "s2", "type": "number", "key": "qty", "label": "Qty"},
        ]
    },
}

TABLE = {
    "id": "f5",
    "type": "table",
    "key": "charges",
    "label": "Charges",
    "table": {
        "columns": [
            {"id": "c1", "type": "text", "key": "description", "label": "Description"},
            {"id": "c2", "type": "number", "key": "unit_price", "label": "Unit Price"},
        ]
    },
}


# ---------------------------------------------------------------- the contract

def test_the_contract_shape_is_unchanged():
    """Returns ``(header, [(group_key, fields)])`` exactly as the old helper did.

    `build_dynamic_field_metas_for_definition` reads ``id`` / ``label`` / ``type``
    off each dict. Keeping the shape means that 57-line builder needs no change,
    which is the whole reason this is a drop-in.
    """
    header, groups = collect_field_defs(_doc(TEXT, REPEATER))
    assert isinstance(header, list) and isinstance(groups, list)
    assert all(set(f) >= {"id", "label", "type"} for f in header)
    assert all(isinstance(g, tuple) and len(g) == 2 for g in groups)


def test_a_new_shape_document_yields_fields():
    """The silent-empty guard. Asserts NON-EMPTY, not just "does not raise".

    The old extractor returns ([], []) for this document. That loses every dynamic
    grid and export column with no error, which is the worst failure mode in F1.
    """
    header, groups = collect_field_defs(_doc(TEXT, NUM, REPEATER))
    assert header, "a new-shape document must yield header fields"
    assert groups, "a repeater must yield a line group"


def test_id_carries_the_ANSWER_KEY_not_the_field_id():
    """``id`` in the returned dict is the field's stable answer ``key``.

    The compile path is ``jsonb_extract_path_text(header_data, <top level key>)``,
    and F0 stores answers keyed by field ``key``. So the identifier handed to the
    compiler must be the key; passing ``FormField.id`` would extract a JSONB path
    that never exists and every filter would silently match nothing.
    """
    header, _ = collect_field_defs(_doc(TEXT))
    assert header[0]["id"] == "customer_name"
    assert header[0]["id"] != "f1"


def test_answer_keys_satisfy_the_list_query_id_guard():
    """Keys must pass ``_ID_SAFE`` in the consumer, or the field is skipped.

    F0 enforces field keys as ``^[A-Za-z_][A-Za-z0-9_]*$``; the consumer allows
    ``^[a-zA-Z0-9_-]{1,128}$``. The first is a subset of the second, so every
    publishable key survives. This pins that relationship rather than trusting it.
    """
    from app.services.workflow_submission_dynamic_list_query import _validate_id

    header, groups = collect_field_defs(_doc(TEXT, NUM, REPEATER))
    for f in header:
        assert _validate_id(f["id"])
    for group_key, fields in groups:
        assert _validate_id(group_key)
        for f in fields:
            assert _validate_id(f["id"])


# ------------------------------------------------------- header vs line groups

def test_display_fields_are_excluded():
    """A heading has no answer key, so it can never be a filterable column."""
    header, _ = collect_field_defs(_doc(TEXT, HEADING))
    assert [f["id"] for f in header] == ["customer_name"]


def test_a_repeater_becomes_a_line_group_not_a_header_field():
    """Repeater rows live in ``workflow_submission_lines``, not ``header_data``.

    They must be relational rows rather than nested JSONB because F1a puts a
    ``status_id`` FK and a disposition on each LINE, and a JSONB row cannot carry
    a foreign key.
    """
    header, groups = collect_field_defs(_doc(TEXT, REPEATER))
    assert "items" not in [f["id"] for f in header]
    assert [g[0] for g in groups] == ["items"]
    assert [f["id"] for f in groups[0][1]] == ["sku", "qty"]


def test_a_table_becomes_a_line_group_too():
    """A Table is the same relational shape as a repeater, keyed by its columns."""
    _, groups = collect_field_defs(_doc(TABLE))
    assert [g[0] for g in groups] == ["charges"]
    assert [f["id"] for f in groups[0][1]] == ["description", "unit_price"]


def test_repeaters_and_tables_coexist_as_separate_groups():
    _, groups = collect_field_defs(_doc(REPEATER, TABLE))
    assert sorted(g[0] for g in groups) == ["charges", "items"]


def test_fields_are_returned_in_document_order():
    """Column order follows the form, so ``sort_order`` in the consumer is stable.

    The consumer derives ``sort_order`` from list position, so a non-deterministic
    order here would reshuffle a user's grid columns between requests.
    """
    header, _ = collect_field_defs(_doc(TEXT, NUM, DATE))
    assert [f["id"] for f in header] == ["customer_name", "amount", "needed_by"]


def test_fields_from_every_page_and_section_are_collected():
    """A multi-page form must not lose the pages after the first."""
    doc = {
        "schemaVersion": 1,
        "pages": [
            {"id": "p1", "title": "One", "sections": [{"id": "s1", "title": "A", "fields": [TEXT]}]},
            {"id": "p2", "title": "Two", "sections": [{"id": "s2", "title": "B", "fields": [NUM]}]},
        ],
    }
    header, _ = collect_field_defs(doc)
    assert [f["id"] for f in header] == ["customer_name", "amount"]


# ------------------------------------------------------------- type mapping

@pytest.mark.parametrize(
    "field_type,expected",
    [
        ("number", "number"),
        ("integer", "number"),
        ("rating", "number"),
        ("computed", "number"),
        ("yesno", "boolean"),
        ("date", "date"),
        ("datetime", "date"),
        ("multiselect", "string"),
        ("checkboxes", "string"),
        ("text", "string"),
        ("textarea", "string"),
        ("select", "string"),
        ("email", "string"),
    ],
)
def test_new_shape_types_map_to_the_right_filter_data_type(field_type, expected):
    """A numeric field filtered as a string compares "10" < "9" and is wrong.

    The consumer's ``_ops_for_workflow_type`` was written for the old vocabulary
    (``checkbox``, ``multi_select``). New-shape names like ``integer``, ``rating``
    and ``yesno`` would silently fall through to string, so the mapping has to be
    asserted per type rather than assumed.
    """
    from app.services.workflow_submission_dynamic_list_query import _ops_for_workflow_type

    field = {"id": "x", "type": field_type, "key": "k", "label": "L"}
    header, _ = collect_field_defs(_doc(field))
    assert header, f"{field_type} should be an input field"
    data_type, ops, filterable = _ops_for_workflow_type(header[0]["type"])
    assert data_type == expected
    assert ops and filterable


# ------------------------------------------------------------ malformed input

def test_a_malformed_document_returns_empty_and_does_not_raise():
    """Observable, not silent: it warns.

    This is called while building a list-query response for a PUBLISHED snapshot,
    and the publish gate guarantees stored documents are valid, so a malformed one
    means corruption. Raising would 500 a grid the user cannot fix; returning empty
    silently is the trap this module exists to avoid. So it logs and returns empty.
    """
    header, groups = collect_field_defs({"nonsense": True})
    assert (header, groups) == ([], [])


@pytest.mark.parametrize("bad", [None, "", [], "a string", 42])
def test_non_dict_input_is_tolerated(bad):
    assert collect_field_defs(bad) == ([], [])


def test_a_malformed_document_is_logged(caplog):
    """A silent-empty return is the failure mode; the log is what makes it findable."""
    import logging

    with caplog.at_level(logging.WARNING):
        collect_field_defs({"pages": "not a list"})
    assert any("form document" in r.message.lower() for r in caplog.records)


def test_an_empty_but_valid_document_returns_empty_without_warning(caplog):
    """A form with no fields yet is legitimate, not corruption. It must not warn."""
    import logging

    with caplog.at_level(logging.WARNING):
        header, groups = collect_field_defs({"schemaVersion": 1, "pages": []})
    assert (header, groups) == ([], [])
    assert not [r for r in caplog.records if "form document" in r.message.lower()]
