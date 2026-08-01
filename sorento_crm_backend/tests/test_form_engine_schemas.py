"""The form document model and publish gate, ported from foundryx-shared-service
(plan F0). Written before the implementation, per PRINCIPLES step 4.

Target module: ``app.form_engine.schemas``.

The document is a forever-contract: a published version is an immutable snapshot
that submissions are validated against for years. So the tests that matter most
are not the individual rules, they are the ones that stop a bad document from
ever being stored:

* ``test_unknown_keys_anywhere_are_rejected`` -- ``extra="forbid"`` is what keeps
  a typo ("requred": true) from being silently persisted and silently ignored,
  which reads to the author as "required does not work".
* ``test_round_trip_preserves_the_camel_case_wire_shape`` -- the JSON we accept
  is the JSON we persist. If ``model_dump(by_alias=True)`` drops or renames a
  key, every already-published version decays the next time it is re-saved.
* ``test_an_empty_condition_group_is_not_publishable`` and its runtime twin in
  ``test_form_engine_validation.py`` -- the known Sorento rule-engine trap: an
  empty ``rules[]`` in ``{combinator, rules[]}`` matches EVERYTHING, so an
  author who opens the conditions builder and saves without adding a rule
  silently makes the field unconditional instead of never-shown.
* ``test_no_id_column_is_plain_string`` -- pg-UUID-vs-varchar drift is what broke
  ``user_sessions.id`` on production.

The gate returns a list of problem strings; ``[]`` means publishable. Assertions
match on the semantic fragment of a message, never the whole sentence, so prose
can be reworded without breaking the suite.

Run: venv/bin/pytest tests/test_form_engine_schemas.py -q
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError
from sqlalchemy import String
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base
from app.form_engine.schemas import (
    ALL_FIELD_TYPES,
    CHOICE_FIELD_TYPES,
    CONDITIONABLE_TYPES,
    DISPLAY_FIELD_TYPES,
    FORM_SCHEMA_VERSION,
    INPUT_FIELD_TYPES,
    NUMERIC_FIELD_TYPES,
    SUB_FIELD_TYPES,
    TABLE_COLUMN_TYPES,
    FormDocument,
    validate_form_doc,
)
from tests._pg_fixture import blank_session, unique_code


# ---------------------------------------------------------------------------
# document builders
# ---------------------------------------------------------------------------

def field(type_, key=None, **extra):
    f = {"id": f"fld_{key or type_}", "type": type_, "label": key or type_}
    if key is not None:
        f["key"] = key
    f.update(extra)
    return f


def section(*fields, sid="sec_1", **extra):
    return {"id": sid, "fields": list(fields), **extra}


def page(*sections, pid="pg_1", **extra):
    return {"id": pid, "sections": list(sections), **extra}


def doc(*pages):
    return {"schemaVersion": FORM_SCHEMA_VERSION, "pages": list(pages)}


def one(*fields):
    """The commonest shape: one page, one section, these fields."""
    return doc(page(section(*fields)))


def cond(fact, operator="eq", value="x", **extra):
    return {
        "kind": "group",
        "combinator": "and",
        "rules": [
            {
                "kind": "condition",
                "fact": fact,
                "operator": operator,
                "value": value,
                **extra,
            }
        ],
    }


def choice(key="pick", items=None, type_="select"):
    if items is None:
        items = [{"value": "a", "label": "A"}, {"value": "b", "label": "B"}]
    return field(type_, key=key, options={"kind": "static", "items": items})


def table(key="lines", columns=None, **table_extra):
    cols = columns if columns is not None else [
        {"id": "c1", "type": "text", "key": "item", "label": "Item", "required": True},
        {"id": "c2", "type": "number", "key": "qty", "label": "Qty", "required": True},
        {"id": "c3", "type": "number", "key": "unit_price", "label": "Unit price"},
        {
            "id": "c4",
            "type": "computed",
            "key": "amount",
            "label": "Amount",
            "computed": {"expression": "qty * unit_price"},
            "summarize": "sum",
        },
    ]
    return {
        "id": "t1",
        "type": "table",
        "key": key,
        "label": "Line items",
        "table": {"columns": cols, **table_extra},
    }


def repeater(key="notes", subs=None, **repeater_extra):
    if subs is None:
        subs = [
            {"id": "s1", "type": "text", "key": "note", "label": "Note"},
            {"id": "s2", "type": "number", "key": "hours", "label": "Hours"},
        ]
    return field(key=key, type_="repeater", repeater={"fields": subs, **repeater_extra})


def computed(expr, key="total"):
    return field("computed", key=key, computed={"expression": expr})


def problems_of(document):
    result = validate_form_doc(document)
    assert isinstance(result, list), "the gate returns a list of problem strings"
    assert all(isinstance(p, str) and p.strip() for p in result)
    return result


def assert_mentions(problems, *fragments):
    assert problems, "expected the gate to block this document"
    lowered = [p.lower() for p in problems]
    for fragment in fragments:
        assert any(fragment.lower() in p for p in lowered), (
            f"no problem mentioned {fragment!r}; got {problems!r}"
        )


# ---------------------------------------------------------------------------
# a document that exercises every field type, every alias and every config bag
# ---------------------------------------------------------------------------

RICH_DOC = {
    "schemaVersion": 1,
    "pages": [
        {
            "id": "pg_1",
            "title": "Your claim",
            "sections": [
                {
                    "id": "sec_1",
                    "title": "Contact",
                    "description": "How we reach you",
                    "twoColumn": True,
                    "fields": [
                        {
                            "id": "fld_head",
                            "type": "heading",
                            "label": "Contact details",
                            "heading": {"level": 2},
                        },
                        {
                            "id": "fld_para",
                            "type": "paragraph",
                            "label": "We only use this to reply to your claim.",
                        },
                        {"id": "fld_rule", "type": "divider", "label": ""},
                        {
                            "id": "fld_name",
                            "type": "text",
                            "key": "full_name",
                            "label": "Full name",
                            "required": True,
                            "placeholder": "Jane Tan",
                            "helpText": "As printed on the receipt",
                            "text": {
                                "minLength": 2,
                                "maxLength": 80,
                                "pattern": "^[A-Za-z ]+$",
                                "patternMessage": "Letters only",
                            },
                        },
                        {
                            "id": "fld_detail",
                            "type": "textarea",
                            "key": "detail",
                            "label": "What happened",
                        },
                        {
                            "id": "fld_email",
                            "type": "email",
                            "key": "email",
                            "label": "Email",
                        },
                        {
                            "id": "fld_phone",
                            "type": "phone",
                            "key": "phone",
                            "label": "Phone",
                        },
                        {
                            "id": "fld_link",
                            "type": "url",
                            "key": "link",
                            "label": "Product page",
                        },
                        {
                            "id": "fld_receipt",
                            "type": "file",
                            "key": "receipt",
                            "label": "Receipt",
                            "file": {
                                "maxSizeMb": 5.0,
                                "allowedMimes": ["image/png", "application/pdf"],
                                "maxCount": 3,
                            },
                        },
                        {
                            "id": "fld_sig",
                            "type": "signature",
                            "key": "signature",
                            "label": "Signature",
                        },
                        {
                            "id": "fld_addr",
                            "type": "address",
                            "key": "pickup",
                            "label": "Pickup address",
                        },
                        {
                            "id": "fld_day",
                            "type": "date",
                            "key": "purchased_on",
                            "label": "Purchased on",
                        },
                        {
                            "id": "fld_when",
                            "type": "datetime",
                            "key": "failed_at",
                            "label": "Failed at",
                        },
                        {
                            "id": "fld_rating",
                            "type": "rating",
                            "key": "satisfaction",
                            "label": "Satisfaction",
                            "rating": {"max": 5},
                        },
                        {
                            "id": "fld_weight",
                            "type": "number",
                            "key": "weight_kg",
                            "label": "Weight (kg)",
                            "number": {"min": 0.5, "max": 40.0, "step": 0.5, "decimals": 1},
                        },
                        {
                            "id": "fld_units",
                            "type": "integer",
                            "key": "units",
                            "label": "Units",
                            "number": {"min": 1, "max": 99, "integer": True},
                        },
                    ],
                },
                {
                    "id": "sec_2",
                    "title": "Warranty",
                    "conditionsJson": {
                        "kind": "group",
                        "combinator": "and",
                        "rules": [
                            {
                                "kind": "condition",
                                "fact": "answers.satisfaction",
                                "operator": "lt",
                                "value": 3,
                            }
                        ],
                    },
                    "fields": [
                        {
                            "id": "fld_kind",
                            "type": "select",
                            "key": "claim_kind",
                            "label": "Claim kind",
                            "options": {
                                "kind": "static",
                                "items": [
                                    {"value": "exchange", "label": "Exchange"},
                                    {"value": "return", "label": "Return"},
                                ],
                            },
                        },
                        {
                            "id": "fld_tags",
                            "type": "multiselect",
                            "key": "symptoms",
                            "label": "Symptoms",
                            "options": {
                                "kind": "static",
                                "items": [{"value": "noise", "label": "Noise"}],
                            },
                        },
                        {
                            "id": "fld_radio",
                            "type": "radio",
                            "key": "channel",
                            "label": "Bought from",
                            "options": {
                                "kind": "static",
                                "items": [{"value": "dealer", "label": "Dealer"}],
                            },
                        },
                        {
                            "id": "fld_boxes",
                            "type": "checkboxes",
                            "key": "accessories",
                            "label": "Accessories returned",
                            "options": {
                                "kind": "static",
                                "items": [{"value": "cable", "label": "Cable"}],
                            },
                        },
                        {
                            "id": "fld_ack",
                            "type": "yesno",
                            "key": "charge_ack",
                            "label": "I accept the out-of-warranty charge",
                            "conditionsJson": {
                                "kind": "group",
                                "combinator": "and",
                                "rules": [
                                    {
                                        "kind": "condition",
                                        "fact": "answers.claim_kind",
                                        "operator": "eq",
                                        "value": "return",
                                    }
                                ],
                            },
                        },
                    ],
                },
            ],
        },
        {
            "id": "pg_2",
            "title": "Line items",
            "sections": [
                {
                    "id": "sec_3",
                    "fields": [
                        {
                            "id": "fld_lines",
                            "type": "table",
                            "key": "lines",
                            "label": "Lines",
                            "table": {
                                "columns": [
                                    {
                                        "id": "c1",
                                        "type": "text",
                                        "key": "item",
                                        "label": "Item",
                                        "required": True,
                                        "placeholder": "SKU",
                                    },
                                    {
                                        "id": "c2",
                                        "type": "integer",
                                        "key": "qty",
                                        "label": "Qty",
                                        "required": True,
                                        "number": {"min": 1},
                                        "integer": True,
                                    },
                                    {
                                        "id": "c3",
                                        "type": "number",
                                        "key": "unit_price",
                                        "label": "Unit price",
                                        "decimals": 2,
                                    },
                                    {
                                        "id": "c4",
                                        "type": "fixed",
                                        "key": "tax_rate",
                                        "label": "Tax rate",
                                        "fixedValue": "0.06",
                                    },
                                    {
                                        "id": "c5",
                                        "type": "computed",
                                        "key": "amount",
                                        "label": "Amount",
                                        "computed": {"expression": "qty * unit_price"},
                                        "summarize": "sum",
                                    },
                                    {
                                        "id": "c6",
                                        "type": "select",
                                        "key": "reason",
                                        "label": "Reason",
                                        "options": {
                                            "kind": "static",
                                            "items": [{"value": "faulty", "label": "Faulty"}],
                                        },
                                    },
                                    {
                                        "id": "c7",
                                        "type": "date",
                                        "key": "installed_on",
                                        "label": "Installed on",
                                    },
                                ],
                                "showRowNumbers": True,
                                "minRows": 1,
                                "maxRows": 20,
                            },
                        },
                        {
                            "id": "fld_notes",
                            "type": "repeater",
                            "key": "notes",
                            "label": "Technician notes",
                            "repeater": {
                                "fields": [
                                    {
                                        "id": "s1",
                                        "type": "text",
                                        "key": "note",
                                        "label": "Note",
                                        "required": True,
                                        "placeholder": "What you found",
                                        "text": {"minLength": 3, "maxLength": 500},
                                    },
                                    {
                                        "id": "s2",
                                        "type": "number",
                                        "key": "hours",
                                        "label": "Hours",
                                        "number": {"min": 0.0, "max": 24.0},
                                    },
                                    {
                                        "id": "s3",
                                        "type": "rating",
                                        "key": "urgency",
                                        "label": "Urgency",
                                        "rating": {"max": 3},
                                    },
                                    {
                                        "id": "s4",
                                        "type": "select",
                                        "key": "outcome",
                                        "label": "Outcome",
                                        "options": {
                                            "kind": "static",
                                            "items": [{"value": "fixed", "label": "Fixed"}],
                                        },
                                    },
                                ],
                                "minRows": 0,
                                "maxRows": 5,
                            },
                        },
                        {
                            "id": "fld_grand",
                            "type": "computed",
                            "key": "grand_total",
                            "label": "Grand total",
                            "computed": {
                                "expression": "sum(lines.amount) + sum(notes.hours) * 80"
                            },
                        },
                    ],
                }
            ],
        },
    ],
}


# ---------------------------------------------------------------------------
# the field taxonomy
# ---------------------------------------------------------------------------

def test_input_and_display_types_are_disjoint_and_exhaustive():
    """A display block collects no answer, so the two sets drive different code
    paths (key required vs key forbidden). A type in both would be validated
    twice and stored inconsistently."""
    assert INPUT_FIELD_TYPES & DISPLAY_FIELD_TYPES == set()
    assert ALL_FIELD_TYPES == INPUT_FIELD_TYPES | DISPLAY_FIELD_TYPES


def test_the_taxonomy_carries_the_types_the_after_sales_flows_need():
    """F0 exists to unblock the exchange/return request, which needs line items
    with per-line uploads, and the survey, which needs a rating. Dropping any of
    these during the port silently removes a feature the plan promised."""
    for required in ("repeater", "table", "computed", "file", "rating", "address", "signature"):
        assert required in INPUT_FIELD_TYPES, required
    for required in ("heading", "paragraph", "divider"):
        assert required in DISPLAY_FIELD_TYPES, required


def test_derived_type_sets_are_subsets_of_the_input_taxonomy():
    """Every derived set narrows the answer-bearing types. A member outside
    ``INPUT_FIELD_TYPES`` would be unreachable, so the rule keyed on it would
    never fire and would look like it worked."""
    assert CHOICE_FIELD_TYPES <= INPUT_FIELD_TYPES
    assert NUMERIC_FIELD_TYPES <= INPUT_FIELD_TYPES
    assert SUB_FIELD_TYPES <= INPUT_FIELD_TYPES
    assert CONDITIONABLE_TYPES <= INPUT_FIELD_TYPES


def test_numeric_types_are_exactly_what_a_computed_field_may_reference():
    """The gate rejects a computed field pointing at a non-numeric key. Adding
    ``text`` here would let ``name * 2`` publish and then evaluate to null on
    every submission."""
    assert NUMERIC_FIELD_TYPES == {"number", "integer", "rating", "computed"}


def test_choice_types_are_the_four_option_bearing_ones():
    """These are the only types whose answers are checked for option
    membership. A missing member means unvalidated free text in a select."""
    assert CHOICE_FIELD_TYPES == {"select", "multiselect", "radio", "checkboxes"}


def test_composites_and_uploads_are_not_conditionable():
    """A rule engine compares scalars. Conditioning on a file list or an address
    object would fail closed forever and read as "my condition never fires"."""
    for excluded in ("file", "signature", "address", "repeater", "table"):
        assert excluded not in CONDITIONABLE_TYPES, excluded


def test_repeater_sub_fields_exclude_composites_and_uploads():
    """A repeater row is a flat scalar record. Nesting a repeater or an upload
    inside one is out of scope for v1 and must not be authorable."""
    for excluded in ("repeater", "table", "file", "signature", "address", "computed", "heading"):
        assert excluded not in SUB_FIELD_TYPES, excluded


def test_table_column_types_include_computed_and_fixed():
    """Per-row computed columns and a server-stamped constant are what make the
    table block worth having: the tax rate is not asked for, and the line amount
    is not trusted from the client."""
    assert "computed" in TABLE_COLUMN_TYPES
    assert "fixed" in TABLE_COLUMN_TYPES
    assert TABLE_COLUMN_TYPES == {
        "text",
        "number",
        "integer",
        "select",
        "date",
        "computed",
        "fixed",
    }


def test_the_rich_document_covers_every_declared_type():
    """Guards the fixture itself: if a type is added to the taxonomy but never
    exercised by RICH_DOC, the round-trip test below stops covering it and an
    alias can rot unnoticed."""
    form = FormDocument.model_validate(RICH_DOC)
    input_types = {f.type for _p, _s, f in form.iter_fields() if f.type in INPUT_FIELD_TYPES}
    display_types = {f.type for _p, _s, f in form.iter_fields() if f.type in DISPLAY_FIELD_TYPES}
    assert input_types == INPUT_FIELD_TYPES
    assert display_types == DISPLAY_FIELD_TYPES


# ---------------------------------------------------------------------------
# the document model: parse, round-trip, reject
# ---------------------------------------------------------------------------

def test_round_trip_preserves_the_camel_case_wire_shape():
    """The JSON we accept is the JSON we persist (workflow_engine precedent).

    Every camelCase alias in the document is exercised here: schemaVersion,
    twoColumn, conditionsJson, helpText, minLength/maxLength/patternMessage,
    maxSizeMb/allowedMimes/maxCount, minRows/maxRows, showRowNumbers,
    fixedValue. A dropped or renamed alias would rewrite a published version the
    next time it round-tripped through the API, changing validation behaviour
    for a form nobody edited.
    """
    form = FormDocument.model_validate(RICH_DOC)
    assert form.model_dump(by_alias=True, exclude_none=True) == RICH_DOC


def test_snake_case_field_names_are_accepted_but_camel_case_is_emitted():
    """``populate_by_name`` lets internal code build a document with python
    attribute names; serialisation must still be the one wire shape."""
    form = FormDocument.model_validate(
        {
            "schema_version": 1,
            "pages": [
                {
                    "id": "pg_1",
                    "sections": [
                        {
                            "id": "sec_1",
                            "two_column": True,
                            "fields": [
                                {
                                    "id": "f1",
                                    "type": "text",
                                    "key": "a",
                                    "label": "A",
                                    "help_text": "hi",
                                }
                            ],
                        }
                    ],
                }
            ],
        }
    )
    dumped = form.model_dump(by_alias=True, exclude_none=True)
    assert dumped["schemaVersion"] == 1
    assert dumped["pages"][0]["sections"][0]["twoColumn"] is True
    assert dumped["pages"][0]["sections"][0]["fields"][0]["helpText"] == "hi"


def test_schema_version_defaults_to_the_current_version():
    """A document saved without a version is the current version, not version 0:
    a future migration keys off this number."""
    form = FormDocument.model_validate({"pages": []})
    assert form.schema_version == FORM_SCHEMA_VERSION
    assert FORM_SCHEMA_VERSION == 1


def test_iter_fields_walks_pages_then_sections_then_fields_in_order():
    """Conditions and computed refs may only look BACKWARDS, so "earlier" is
    defined entirely by this traversal order. Reordering it would silently
    change which documents publish."""
    form = FormDocument.model_validate(RICH_DOC)
    keys = [f.key for _p, _s, f in form.iter_fields() if f.key]
    assert keys.index("full_name") < keys.index("claim_kind") < keys.index("grand_total")
    # every yielded triple names the page and section the field came from
    for pg, sec, fld in form.iter_fields():
        assert fld in sec.fields
        assert sec in pg.sections


def test_input_fields_excludes_display_blocks():
    """Answer handling iterates this list; a heading in it would be looked up in
    the answer map and reported as a missing required field."""
    form = FormDocument.model_validate(RICH_DOC)
    types = {f.type for f in form.input_fields()}
    assert types & DISPLAY_FIELD_TYPES == set()
    assert types == INPUT_FIELD_TYPES


@pytest.mark.parametrize(
    "document",
    [
        # stray key on the document
        {"schemaVersion": 1, "pages": [], "extra": 1},
        # stray key on a page
        {"schemaVersion": 1, "pages": [{"id": "p", "sections": [], "layout": "grid"}]},
    ],
)
def test_unknown_keys_anywhere_are_rejected(document):
    """``extra="forbid"``: the stored document is a forever-contract, so a typo
    must 422 at save rather than rot in the payload. A silently-ignored
    ``"requred": true`` reads to the author as "required is broken"."""
    with pytest.raises(ValidationError):
        FormDocument.model_validate(document)


def test_a_malformed_document_is_one_problem_not_a_crash():
    """``validate_form_doc`` is the publish route's gate. It must convert a shape
    error into a problem string, because the alternative is a 500 on a save."""
    assert_mentions(problems_of(one(field("text", key="t", bogus="nope"))), "malformed")


def test_the_gate_accepts_a_typed_document_as_well_as_a_dict():
    """Called from the route with raw JSON and from services with the parsed
    model. Only accepting one of the two forces a re-parse at every call site."""
    assert validate_form_doc(FormDocument.model_validate(RICH_DOC)) == []
    assert validate_form_doc(RICH_DOC) == []


def test_a_repeater_sub_field_cannot_carry_conditions():
    """Sub-field level conditions are explicitly out of scope for v1. If the key
    were merely ignored, the builder could offer them and they would never
    fire."""
    subs = [{"id": "s1", "type": "text", "key": "n", "label": "N", "conditionsJson": cond("answers.x")}]
    assert_mentions(problems_of(one(repeater(subs=subs))), "malformed")


# ---------------------------------------------------------------------------
# publish gate: the happy path and page-level rules
# ---------------------------------------------------------------------------

def test_the_rich_document_publishes():
    """The full-taxonomy document must be publishable. Anything else means a
    rule contradicts a legal use of the model."""
    assert validate_form_doc(RICH_DOC) == []


def test_a_minimal_document_publishes():
    assert validate_form_doc(one(field("text", key="name"), choice())) == []


def test_a_document_with_no_pages_is_blocked():
    """An empty form would accept an empty submission and look like it worked."""
    assert_mentions(problems_of(doc()), "page")


def test_an_empty_page_is_blocked():
    """A wizard step the user cannot answer anything on is a dead end in the
    renderer."""
    assert_mentions(problems_of(one()), "empty")


# ---------------------------------------------------------------------------
# publish gate: answer keys
# ---------------------------------------------------------------------------

def test_an_input_field_without_a_key_is_blocked():
    """The key is where the answer is stored. Without one the field renders and
    the answer is discarded."""
    assert_mentions(problems_of(one(field("text"))), "answer key")


@pytest.mark.parametrize("bad_key", ["bad-key", "bad key", "1st", "has.dot", "café", ""])
def test_a_key_outside_the_grammar_is_blocked(bad_key):
    """Keys are identifiers in computed expressions and in ``answers.<key>``
    condition facts. A dot or a leading digit would tokenise as something else
    entirely, so the formula would mean a different thing than it reads."""
    assert problems_of(one(field("text", key=bad_key)))


def test_a_legal_key_is_accepted():
    for good in ("name", "_name", "name2", "Name_2"):
        assert validate_form_doc(one(field("text", key=good))) == []


def test_duplicate_keys_are_blocked_across_sections_and_pages():
    """Two fields writing the same key means one answer silently overwrites the
    other, and the loser depends on document order."""
    same_page = doc(
        page(
            section(field("text", key="dup"), sid="s1"),
            section(field("number", key="dup"), sid="s2"),
        )
    )
    assert_mentions(problems_of(same_page), "duplicate")

    across_pages = doc(
        page(section(field("text", key="dup")), pid="p1"),
        page(section(field("number", key="dup"), sid="s2"), pid="p2"),
    )
    assert_mentions(problems_of(across_pages), "duplicate")


def test_a_display_block_needs_no_key():
    """Headings, paragraphs and dividers collect nothing."""
    assert validate_form_doc(one(field("heading"), field("paragraph"), field("divider"), field("text", key="n"))) == []


# ---------------------------------------------------------------------------
# publish gate: unknown types
# ---------------------------------------------------------------------------

def test_an_unknown_field_type_is_blocked():
    """A type outside the taxonomy renders as nothing and validates as nothing.

    The shared-service source did NOT check this (``type`` is a bare ``str``), so
    a document authored against a newer builder published clean here and then
    silently dropped the field. The port must reject it: the definition is
    validated once at publish and trusted for years afterwards.
    """
    assert_mentions(problems_of(one(field("wormhole", key="x"))), "wormhole")


def test_an_unknown_table_column_type_is_blocked():
    """Same reasoning one level down. ``TABLE_COLUMN_TYPES`` exists in the source
    but nothing consulted it, so a ``yesno`` column published and then never
    validated a single cell."""
    cols = [{"id": "c1", "type": "wormhole", "key": "x", "label": "X"}]
    assert_mentions(problems_of(one(table(columns=cols))), "wormhole")


def test_an_unknown_repeater_sub_field_type_is_blocked():
    subs = [{"id": "s1", "type": "wormhole", "key": "x", "label": "X"}]
    assert_mentions(problems_of(one(repeater(subs=subs))), "wormhole")


# ---------------------------------------------------------------------------
# publish gate: choice options
# ---------------------------------------------------------------------------

def test_a_choice_field_needs_at_least_one_option():
    """An empty select cannot be answered, so a required one makes the form
    unsubmittable."""
    assert_mentions(problems_of(one(choice(items=[]))), "option")


def test_a_blank_option_value_is_blocked():
    """The value, not the label, is what is stored and what conditions compare
    against. A blank one is indistinguishable from unanswered."""
    assert_mentions(problems_of(one(choice(items=[{"value": "  ", "label": "Blank"}]))), "value")


def test_duplicate_option_values_are_blocked():
    """Two options with one value make the stored answer ambiguous, and a label
    lookup returns whichever came first."""
    items = [{"value": "x", "label": "A"}, {"value": "x", "label": "B"}]
    assert_mentions(problems_of(one(choice(items=items))), "duplicate")


@pytest.mark.parametrize("choice_type", sorted(CHOICE_FIELD_TYPES))
def test_every_choice_type_is_option_checked(choice_type):
    """The rule is keyed on a set, so a type accidentally left out of it would
    publish with zero options and fail only at submit time."""
    assert problems_of(one(choice(items=[], type_=choice_type)))


# ---------------------------------------------------------------------------
# publish gate: rating
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("rating", [None, {"max": 0}, {"max": -1}])
def test_a_rating_needs_a_scale_of_at_least_one(rating):
    """A zero-star scale renders no stars, so the field is unanswerable while
    still being required."""
    extra = {} if rating is None else {"rating": rating}
    assert_mentions(problems_of(one(field("rating", key="r", **extra))), "rating")


# ---------------------------------------------------------------------------
# publish gate: repeater
# ---------------------------------------------------------------------------

def test_a_repeater_needs_a_sub_field():
    assert_mentions(problems_of(one(repeater(subs=[]))), "sub-field")


def test_repeater_sub_keys_must_be_present_and_unique():
    """Sub-keys are the row object's keys, and aggregates address them by name.
    A duplicate makes ``sum(notes.hours)`` ambiguous."""
    blank = [{"id": "s1", "type": "text", "key": "", "label": "X"}]
    assert_mentions(problems_of(one(repeater(subs=blank))), "sub-field")

    dup = [
        {"id": "s1", "type": "text", "key": "x", "label": "A"},
        {"id": "s2", "type": "number", "key": "x", "label": "B"},
    ]
    assert_mentions(problems_of(one(repeater(subs=dup))), "duplicate")


def test_repeater_min_rows_above_max_rows_is_blocked():
    """An unsatisfiable pair makes every submission fail with two contradictory
    errors."""
    assert_mentions(problems_of(one(repeater(minRows=5, maxRows=2))), "min rows")


# ---------------------------------------------------------------------------
# publish gate: table
# ---------------------------------------------------------------------------

def test_a_valid_table_publishes():
    assert validate_form_doc(one(table())) == []


def test_a_table_needs_at_least_one_column():
    assert_mentions(problems_of(one(table(columns=[]))), "column")


def test_table_column_keys_must_be_present_and_unique():
    blank = [{"id": "c1", "type": "text", "key": "", "label": "X"}]
    assert_mentions(problems_of(one(table(columns=blank))), "column")

    dup = [
        {"id": "c1", "type": "text", "key": "dup", "label": "A"},
        {"id": "c2", "type": "number", "key": "dup", "label": "B"},
    ]
    assert_mentions(problems_of(one(table(columns=dup))), "duplicate column")


def test_table_min_rows_above_max_rows_is_blocked():
    assert_mentions(problems_of(one(table(minRows=4, maxRows=1))), "min rows")


def test_a_computed_column_may_only_reference_earlier_numeric_columns():
    """Per-row computed columns are evaluated left to right over that row, so a
    forward reference is a cycle waiting to happen. Document order is what bans
    it."""
    forward = [
        {"id": "c1", "type": "computed", "key": "amount", "label": "Amount",
         "computed": {"expression": "qty"}},
        {"id": "c2", "type": "number", "key": "qty", "label": "Qty"},
    ]
    assert_mentions(problems_of(one(table(columns=forward))), "earlier")

    non_numeric = [
        {"id": "c1", "type": "text", "key": "item", "label": "Item"},
        {"id": "c2", "type": "computed", "key": "amount", "label": "Amount",
         "computed": {"expression": "item * 2"}},
    ]
    assert_mentions(problems_of(one(table(columns=non_numeric))), "earlier")


def test_a_computed_column_may_reference_a_fixed_constant_column():
    """The fixed column is the reason it exists: a server-stamped tax rate the
    user never sees and cannot tamper with, feeding the line amount."""
    cols = [
        {"id": "c1", "type": "number", "key": "qty", "label": "Qty"},
        {"id": "c2", "type": "fixed", "key": "tax_rate", "label": "Tax", "fixedValue": "0.06"},
        {"id": "c3", "type": "computed", "key": "tax", "label": "Tax amount",
         "computed": {"expression": "qty * tax_rate"}, "summarize": "sum"},
    ]
    assert validate_form_doc(one(table(columns=cols))) == []


@pytest.mark.parametrize("expression", ["", "   ", "qty *", "qty ** 2"])
def test_a_computed_column_with_a_bad_expression_is_blocked(expression):
    cols = [
        {"id": "c1", "type": "number", "key": "qty", "label": "Qty"},
        {"id": "c2", "type": "computed", "key": "amount", "label": "Amount",
         "computed": {"expression": expression}},
    ]
    assert problems_of(one(table(columns=cols)))


def test_a_computed_column_missing_its_config_entirely_is_blocked():
    cols = [{"id": "c1", "type": "computed", "key": "amount", "label": "Amount"}]
    assert_mentions(problems_of(one(table(columns=cols))), "expression")


# ---------------------------------------------------------------------------
# publish gate: computed fields
# ---------------------------------------------------------------------------

def test_a_computed_field_may_reference_earlier_numeric_fields():
    assert validate_form_doc(
        one(field("number", key="qty"), field("number", key="price"), computed("qty * price"))
    ) == []


def test_a_computed_field_cannot_reference_a_later_field():
    """Evaluation is a single forward pass, so a forward reference is always
    null. Blocking it at publish is the only place the author finds out."""
    document = one(computed("qty * 2"), field("number", key="qty"))
    assert_mentions(problems_of(document), "earlier")


def test_a_computed_field_cannot_reference_itself():
    """The self-reference case of the cycle rule: ``total = total + 1``. It is
    caught because a field's own key only becomes "earlier" after its own
    validation. See the computed-module note on why the parser cannot catch
    this."""
    assert_mentions(problems_of(one(computed("total + 1", key="total"))), "earlier")


def test_two_computed_fields_cannot_reference_each_other():
    """A mutual cycle: whichever comes first forward-references the other."""
    document = one(computed("b + 1", key="a"), computed("a + 1", key="b"))
    assert_mentions(problems_of(document), "earlier")


def test_a_computed_field_cannot_reference_a_non_numeric_field():
    """``name * 2`` would publish and then evaluate to null on every single
    submission, which looks like a broken engine rather than a broken form."""
    document = one(field("text", key="name"), computed("name + 1"))
    assert_mentions(problems_of(document), "numeric")


@pytest.mark.parametrize("expression", ["", "  ", "1 +", "2 ** 3", "qty % 2", "round(qty)"])
def test_a_computed_field_with_an_unparseable_expression_is_blocked(expression):
    document = one(field("number", key="qty"), computed(expression))
    assert problems_of(document)


def test_an_aggregate_over_an_earlier_repeater_publishes():
    assert validate_form_doc(one(repeater(), computed("sum(notes.hours)"))) == []


def test_count_over_an_earlier_repeater_needs_no_column():
    assert validate_form_doc(one(repeater(), computed("count(notes)"))) == []


def test_an_aggregate_over_a_table_column_publishes():
    """A table is aggregatable exactly like a repeater: ``sum(lines.amount)`` is
    the order total the after-sales flow needs."""
    assert validate_form_doc(one(table(), computed("sum(lines.amount)", key="grand"))) == []


def test_an_aggregate_over_a_non_repeater_is_blocked():
    document = one(field("number", key="fee"), computed("sum(fee.x)"))
    assert_mentions(problems_of(document), "repeater")


def test_an_aggregate_over_a_non_numeric_column_is_blocked():
    """Summing a text column is always zero, which reads as "the total is
    broken" rather than "the formula is wrong"."""
    assert_mentions(problems_of(one(repeater(), computed("sum(notes.note)"))), "numeric")


def test_an_aggregate_over_an_undeclared_column_is_blocked():
    """Renaming a sub-field leaves the formula pointing at nothing."""
    assert problems_of(one(repeater(), computed("sum(notes.ghost)")))


def test_an_aggregate_forward_reference_is_blocked():
    assert_mentions(problems_of(one(computed("sum(notes.hours)"), repeater())), "repeater")


# ---------------------------------------------------------------------------
# publish gate: conditions (including the empty-group trap)
# ---------------------------------------------------------------------------

def test_a_condition_on_an_earlier_field_publishes():
    document = one(field("yesno", key="agree"), field("text", key="why", conditionsJson=cond("answers.agree")))
    assert validate_form_doc(document) == []


def test_a_condition_on_a_later_field_is_blocked():
    """Visibility is resolved in document order against the answers accepted so
    far, so a forward reference can never be true. It would publish as a field
    that is simply never shown."""
    document = one(field("text", key="q1", conditionsJson=cond("answers.q2")), field("text", key="q2"))
    assert_mentions(problems_of(document), "earlier")


def test_a_section_condition_on_a_later_field_is_blocked():
    """A section's conditions see only the sections before it, not its own
    fields."""
    document = doc(
        page(
            section(field("text", key="q1"), sid="s1"),
            section(field("text", key="q2"), sid="s2", conditionsJson=cond("answers.q3")),
        )
    )
    assert_mentions(problems_of(document), "earlier")


def test_a_condition_on_a_non_conditionable_field_is_blocked():
    """Uploads and composites are not scalars. "If out of warranty require a
    charge acknowledgement" is configuration; "if the receipt upload equals X"
    is not expressible."""
    document = one(field("file", key="receipt"), field("text", key="note", conditionsJson=cond("answers.receipt")))
    assert problems_of(document)


def test_a_condition_fact_outside_the_answers_namespace_is_blocked():
    """The only facts a form document may read are its own earlier answers.
    A ``user.email`` style fact has no registered source here, so it would fail
    closed at runtime and hide the field forever."""
    document = one(field("text", key="a"), field("text", key="b", conditionsJson=cond("user.email")))
    assert problems_of(document)


def test_a_cross_field_condition_value_is_checked_too():
    """``valueKind: "fact"`` compares two answers. The right-hand side needs the
    same earlier-field guarantee as the left, or it silently compares against
    nothing."""
    document = one(
        field("number", key="a"),
        field("text", key="b", conditionsJson=cond("answers.a", operator="gt", value="answers.z", valueKind="fact")),
    )
    assert_mentions(problems_of(document), "earlier")


def test_an_empty_condition_group_is_not_publishable():
    """THE known rule-engine trap, guarded at publish.

    Sorento's evaluator treats ``{combinator, rules: []}`` as "no conditions" and
    returns True, so an author who opens the conditions builder and saves without
    adding a rule gets a field that is ALWAYS shown. The intent expressed by the
    UI (an active but unfinished condition) is the opposite. It must never reach
    a published version. Runtime is belt and braces: see
    ``test_form_engine_validation.py::test_an_empty_condition_group_hides_the_field``.
    """
    empty = {"kind": "group", "combinator": "and", "rules": []}
    document = one(field("yesno", key="agree"), field("text", key="why", conditionsJson=empty))
    problems = problems_of(document)
    assert_mentions(problems, "empty")


def test_an_empty_section_condition_group_is_not_publishable():
    """Same trap one level up, where it is worse: an empty group on a section
    would reveal every field inside it."""
    empty = {"kind": "group", "combinator": "and", "rules": []}
    document = doc(
        page(
            section(field("yesno", key="agree"), sid="s1"),
            section(field("text", key="why"), sid="s2", conditionsJson=empty),
        )
    )
    assert_mentions(problems_of(document), "empty")


def test_a_nested_empty_condition_group_is_not_publishable():
    """The guard must walk the tree, not just look at the root. A nested empty
    group under an ``and`` is exactly as unconditional as a root one."""
    nested = {
        "kind": "group",
        "combinator": "and",
        "rules": [
            {"kind": "condition", "fact": "answers.agree", "operator": "is_true", "value": None},
            {"kind": "group", "combinator": "and", "rules": []},
        ],
    }
    document = one(field("yesno", key="agree"), field("text", key="why", conditionsJson=nested))
    assert_mentions(problems_of(document), "empty")


def test_a_conditions_value_that_is_not_a_group_is_not_publishable():
    """Anything that is not a group with rules cannot be evaluated, so it must
    not be stored as though it were a condition."""
    for garbage in ({"combinator": "and"}, {"rules": []}, {}, {"kind": "condition"}):
        document = one(field("yesno", key="agree"), field("text", key="why", conditionsJson=garbage))
        assert problems_of(document), garbage


def nested_group(depth, fact="answers.agree"):
    """A conditions tree ``depth`` groups deep, one real condition at the bottom."""
    node = {
        "kind": "group",
        "combinator": "and",
        "rules": [{"kind": "condition", "fact": fact, "operator": "is_true", "value": None}],
    }
    for _ in range(depth - 1):
        node = {"kind": "group", "combinator": "and", "rules": [node]}
    return node


def test_a_condition_tree_at_the_nesting_limit_publishes():
    """The boundary, from below. ``rule_engine.evaluator`` evaluates a group at
    depth 5 and ``collect_fact_keys`` reads its leaves, so this tree works and
    must not be blocked - pinned so the depth rule cannot creep inwards by one
    and start rejecting legal documents."""
    document = one(
        field("yesno", key="agree"),
        field("text", key="why", conditionsJson=nested_group(5)),
    )
    assert validate_form_doc(document) == []


def test_a_condition_tree_past_the_nesting_limit_is_blocked():
    """The boundary, from above. A group at depth 6 is scored False by the
    evaluator whatever it says, so the field can never be shown."""
    document = one(
        field("yesno", key="agree"),
        field("text", key="why", conditionsJson=nested_group(6)),
    )
    assert_mentions(problems_of(document), "nesting depth")


def test_a_condition_buried_past_the_nesting_limit_cannot_escape_the_gate():
    """The reason the depth rule is a publish problem and not a shrug.

    ``collect_fact_keys`` stops at the same limit, so a forward reference buried
    that deep was never seen by the earlier-field check and the document
    published clean. The author then had a field that never appeared, with
    nothing anywhere saying why.
    """
    document = one(
        field("yesno", key="agree"),
        field("text", key="why", conditionsJson=nested_group(6, fact="answers.later")),
        field("text", key="later"),
    )
    assert_mentions(problems_of(document), "nesting depth")


def test_a_section_condition_past_the_nesting_limit_is_blocked():
    """Same rule one level up, where it is worse: the whole section would be
    hidden rather than one field."""
    document = doc(
        page(
            section(field("yesno", key="agree"), sid="s1"),
            section(field("text", key="why"), sid="s2", conditionsJson=nested_group(6)),
        )
    )
    assert_mentions(problems_of(document), "nesting depth")


# ---------------------------------------------------------------------------
# publish gate: text patterns
# ---------------------------------------------------------------------------

def test_a_pattern_needs_a_message():
    """A regex failure with no message shows the user a generic error they
    cannot act on."""
    assert_mentions(problems_of(one(field("text", key="t", text={"pattern": "^[0-9]+$"}))), "pattern")


def test_an_uncompilable_pattern_is_blocked():
    """The pattern is authored as ECMAScript-flavoured source and compiled under
    Python ``re``. If it does not compile, validation would silently fail open at
    submit time."""
    document = one(field("text", key="t", text={"pattern": "([0-9]+", "patternMessage": "digits"}))
    assert_mentions(problems_of(document), "pattern")


def test_a_valid_pattern_with_a_message_publishes():
    document = one(field("text", key="t", text={"pattern": "^[0-9]+$", "patternMessage": "Digits only"}))
    assert validate_form_doc(document) == []


# ---------------------------------------------------------------------------
# every problem is reported, not just the first
# ---------------------------------------------------------------------------

def test_the_gate_reports_every_problem_it_finds():
    """The publish dialog lists problems. Returning only the first turns fixing
    a document into N save-and-retry cycles."""
    document = one(
        field("text", key="dup"),
        field("number", key="dup"),
        choice(items=[]),
        field("rating", key="r", rating={"max": 0}),
    )
    problems = problems_of(document)
    assert len(problems) >= 3


# ---------------------------------------------------------------------------
# the persisted document: id typing and a real JSONB round trip
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "table_name",
    [
        "workflow_form_definitions",
        "workflow_form_versions",
        "workflow_submissions",
        "workflow_submission_lines",
    ],
)
def test_no_id_column_is_plain_string(table_name):
    """Every id column stays a real Postgres UUID through the F0 port.

    The port's mandatory deviation from the shared service is ``UUID(as_uuid=
    False)`` rather than ``Column(String)``. That exact drift - a model declaring
    varchar where the column is uuid - is what broke ``user_sessions.id`` auth on
    production, so it is pinned here rather than discovered later.

    Exempt by necessity, not by preference:

    * ``respondent_contact_id`` (F2b) targets ``respond_contacts.id``, which is a
      TEXT column. Postgres refuses a foreign key from ``uuid`` to ``text``, so
      the uuid form of this column cannot exist at all. Every other FK into that
      table is a string for the same reason.
    * ``source_entity_id`` (F2b) is a polymorphic pointer with no FK, and cannot
      assume every table it may name has a uuid primary key.

    Both are string because the schema leaves no alternative. Anything added here
    for mere convenience is the drift this test exists to catch.
    """
    import app.models.workflow_forms  # noqa: F401  register the tables

    table_ = Base.metadata.tables[table_name]
    offenders = [
        column.name
        for column in table_.columns
        if (column.name == "id" or column.name.endswith("_id"))
        and column.name
        not in {
            "tenant_id",
            "line_group_id",
            "created_by_user_id",
            "updated_by_user_id",
            "respondent_contact_id",
            "source_entity_id",
        }
        and isinstance(column.type, String)
        and not isinstance(column.type, UUID)
    ]
    assert offenders == [], f"{table_name} has varchar id columns: {offenders}"


def test_a_form_document_round_trips_through_the_version_schema_column():
    """The document survives a real JSONB write and read.

    ``workflow_form_versions.schema`` is where a published definition lives for
    years. This is the one test that proves the new shape (pages / sections /
    fields, camelCase) actually persists and re-parses, rather than only
    round-tripping in memory. Postgres JSONB does not preserve key order or
    duplicate keys, so an in-memory round trip alone would not catch a model
    whose serialisation depends on either.
    """
    from app.models.workflow_forms import WorkflowFormDefinition, WorkflowFormVersion

    with blank_session() as db:
        definition = WorkflowFormDefinition(
            code=unique_code("form"),
            name="ZZT after-sales exchange request",
            draft_schema=RICH_DOC,
        )
        db.add(definition)
        db.flush()

        version = WorkflowFormVersion(
            definition_id=definition.id, version_number=1, schema=RICH_DOC
        )
        db.add(version)
        db.flush()
        db.expire_all()

        stored = db.get(WorkflowFormVersion, version.id)
        assert isinstance(stored.id, str), "ids are string-valued UUIDs"
        assert validate_form_doc(stored.schema) == []
        reparsed = FormDocument.model_validate(stored.schema)
        assert reparsed.model_dump(by_alias=True, exclude_none=True) == RICH_DOC
