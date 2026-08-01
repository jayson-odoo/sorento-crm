"""Form block-document schema plus the publish gate.

Ported from foundryx-shared-service (plan forms-platform F0).

The document is a forever-contract: a published version is an immutable snapshot
that submissions are validated against for years. It is **Page to Section to
Field**, with ``schemaVersion`` at the root, and it is stored camelCase VERBATIM
in ``workflow_form_versions.schema`` (workflow-engine precedent: the JSON we
accept is the JSON we persist). So the models use camelCase aliases and
``model_dump(by_alias=True, exclude_none=True)`` round-trips the wire shape
exactly. ``extra="forbid"`` everywhere, because a silently-ignored ``"requred":
true`` reads to the author as "required does not work".

``validate_form_doc`` is the PUBLISH GATE: it returns a list of problem strings,
``[]`` meaning publishable, and reports EVERY problem it finds rather than the
first (the publish dialog lists them, so returning one turns fixing a document
into N save-and-retry cycles).

Two deliberate deviations from the shared-service source, both of them
publish-time guards it lacked:

* **An unknown field type is blocked**, at all three levels (field, table
  column, repeater sub-field). The source types all three as a bare ``str``, so
  a document authored against a newer builder published clean and then silently
  dropped the field. ``TABLE_COLUMN_TYPES`` even existed there and was consulted
  by nothing.
* **An authored-but-empty condition group is blocked.** In the rule-engine node
  shape ``{combinator, rules[]}`` an empty ``rules[]`` matches EVERYTHING, so an
  author who opens the conditions builder and saves without finishing a rule
  gets a field that is always shown - the opposite of the intent the UI
  expressed. The runtime twin is ``validation.is_visible``.

Note on condition validation: a form's conditions reference ``answers.<key>``
facts that are DYNAMIC per document, so there is no registered ``FactSource``
for them and ``rule_engine.schemas.validate_tree`` cannot be used (it resolves
facts through the code-side registry). Instead we walk the tree with
``collect_fact_keys`` and enforce the structural rule that every fact is an
``answers.<key>`` of an EARLIER conditionable field, in document order.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Literal, Optional, Set

from pydantic import BaseModel, ConfigDict, Field

from app.form_engine.computed import (
    ComputedExpressionError,
    aggregate_refs,
    field_refs,
    parse_expression,
)
from app.rule_engine.evaluator import _MAX_DEPTH, collect_fact_keys

FORM_SCHEMA_VERSION = 1

# ---- field taxonomy ----

# Answer-bearing field types.
INPUT_FIELD_TYPES: Set[str] = {
    "text",
    "textarea",
    "email",
    "phone",
    "url",
    "number",
    "integer",
    "select",
    "multiselect",
    "radio",
    "checkboxes",
    "yesno",
    "date",
    "datetime",
    "file",
    "signature",
    "rating",
    "address",
    "repeater",
    "table",
    "computed",
}

# Columns a Table block may carry: the scalar inputs, a read-only per-row
# computed column, and a server-stamped constant (a tax rate is not asked for,
# and a line amount is not trusted from the client).
TABLE_COLUMN_TYPES: Set[str] = {
    "text",
    "number",
    "integer",
    "select",
    "date",
    "computed",
    "fixed",
}

# Display-only types: they render and collect nothing, so they carry no key.
DISPLAY_FIELD_TYPES: Set[str] = {"heading", "paragraph", "divider"}

ALL_FIELD_TYPES: Set[str] = INPUT_FIELD_TYPES | DISPLAY_FIELD_TYPES

# The only types whose answers are checked for option membership.
CHOICE_FIELD_TYPES: Set[str] = {"select", "multiselect", "radio", "checkboxes"}

# The only types a computed expression may reference.
NUMERIC_FIELD_TYPES: Set[str] = {"number", "integer", "rating", "computed"}

# A repeater row is a flat scalar record: no composites, no uploads, no nesting.
SUB_FIELD_TYPES: Set[str] = {
    "text",
    "textarea",
    "email",
    "phone",
    "url",
    "number",
    "select",
    "radio",
    "yesno",
    "date",
    "rating",
}

# A rule engine compares scalars, so conditioning on a file list or an address
# object would fail closed forever and read as "my condition never fires".
CONDITIONABLE_TYPES: Set[str] = {
    "text",
    "textarea",
    "email",
    "phone",
    "url",
    "number",
    "integer",
    "select",
    "multiselect",
    "radio",
    "checkboxes",
    "yesno",
    "date",
    "datetime",
    "rating",
    "computed",
}

# Answer keys are identifiers in computed expressions and in ``answers.<key>``
# facts, so a dot or a leading digit would tokenise as something else entirely.
_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# A rule-engine group. Its grammar is the rule engine's; here we only walk it.
Conditions = Optional[Dict[str, Any]]


# ---- base config ----


class _Base(BaseModel):
    """Strict camelCase-in, camelCase-out base."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


# ---- choice options (static-only in v1) ----


class FormChoiceItem(_Base):
    value: str
    label: str


class FormStaticOptions(_Base):
    kind: Literal["static"] = "static"
    items: List[FormChoiceItem] = Field(default_factory=list)


# An ``{kind:'entity', ...}`` arm lands additively later, hence the indirection.
FormChoiceOptions = FormStaticOptions


# ---- per-type validation config bags ----


class FormTextValidation(_Base):
    """Text-family constraints (``text``/``textarea``/``email``/``phone``/``url``)."""

    min_length: Optional[int] = Field(default=None, alias="minLength")
    max_length: Optional[int] = Field(default=None, alias="maxLength")
    # ECMAScript-flavoured regex source, no flags, compiled under Python ``re``
    # at the publish gate so an uncompilable one is the author's problem, not the
    # submitter's.
    pattern: Optional[str] = None
    pattern_message: Optional[str] = Field(default=None, alias="patternMessage")


class FormNumberValidation(_Base):
    min: Optional[float] = None
    max: Optional[float] = None
    step: Optional[float] = None
    decimals: Optional[int] = None
    integer: Optional[bool] = None


class FormFileValidation(_Base):
    max_size_mb: Optional[float] = Field(default=None, alias="maxSizeMb")
    allowed_mimes: Optional[List[str]] = Field(default=None, alias="allowedMimes")
    max_count: Optional[int] = Field(default=None, alias="maxCount")


class FormRatingConfig(_Base):
    max: int


class FormHeadingConfig(_Base):
    level: Literal[1, 2, 3] = 2


class FormComputedConfig(_Base):
    expression: str = ""


# ---- the document tree ----


class FormSubField(_Base):
    """A repeater row's sub-field: restricted type set, no conditions in v1."""

    id: str
    type: str
    key: str
    label: str
    required: Optional[bool] = None
    placeholder: Optional[str] = None
    text: Optional[FormTextValidation] = None
    number: Optional[FormNumberValidation] = None
    options: Optional[FormChoiceOptions] = None
    rating: Optional[FormRatingConfig] = None


class FormRepeaterConfig(_Base):
    fields: List[FormSubField] = Field(default_factory=list)
    min_rows: Optional[int] = Field(default=None, alias="minRows")
    max_rows: Optional[int] = Field(default=None, alias="maxRows")


class FormTableColumn(_Base):
    """A Table column. ``computed`` columns are read-only and evaluated PER ROW
    over that row's earlier columns; ``summarize`` adds a column total."""

    id: str
    type: str
    key: str
    label: str
    required: Optional[bool] = None
    placeholder: Optional[str] = None
    options: Optional[FormChoiceOptions] = None
    number: Optional[FormNumberValidation] = None
    computed: Optional[FormComputedConfig] = None
    summarize: Optional[Literal["sum", "avg", "count", "min", "max"]] = None
    decimals: Optional[int] = None
    integer: Optional[bool] = None
    # The constant stamped into every row of a ``fixed`` column.
    fixed_value: Optional[str] = Field(default=None, alias="fixedValue")


class FormTableConfig(_Base):
    columns: List[FormTableColumn] = Field(default_factory=list)
    show_row_numbers: Optional[bool] = Field(default=None, alias="showRowNumbers")
    min_rows: Optional[int] = Field(default=None, alias="minRows")
    max_rows: Optional[int] = Field(default=None, alias="maxRows")


class FormField(_Base):
    """One leaf of the form.

    ``key`` is the STABLE answer key, unique across the document: a relabel never
    breaks a reference. Display fields carry no ``key`` / ``required``. Exactly
    one type-specific bag applies per type, and the publish gate decides which.
    """

    id: str
    type: str
    key: Optional[str] = None
    label: str
    required: Optional[bool] = None
    placeholder: Optional[str] = None
    help_text: Optional[str] = Field(default=None, alias="helpText")
    # Visibility. Facts are ``answers.<fieldKey>`` of EARLIER fields only.
    conditions_json: Conditions = Field(default=None, alias="conditionsJson")

    # -- type-specific bags --
    text: Optional[FormTextValidation] = None
    number: Optional[FormNumberValidation] = None
    options: Optional[FormChoiceOptions] = None
    file: Optional[FormFileValidation] = None
    rating: Optional[FormRatingConfig] = None
    heading: Optional[FormHeadingConfig] = None
    repeater: Optional[FormRepeaterConfig] = None
    table: Optional[FormTableConfig] = None
    computed: Optional[FormComputedConfig] = None


class FormSection(_Base):
    """Titled group, optional two-column layout, conditionally visible."""

    id: str
    title: Optional[str] = None
    description: Optional[str] = None
    two_column: Optional[bool] = Field(default=None, alias="twoColumn")
    conditions_json: Conditions = Field(default=None, alias="conditionsJson")
    fields: List[FormField] = Field(default_factory=list)


class FormPage(_Base):
    """A wizard step, validated client-side before the user advances."""

    id: str
    title: Optional[str] = None
    sections: List[FormSection] = Field(default_factory=list)


class FormDocument(_Base):
    schema_version: int = Field(default=FORM_SCHEMA_VERSION, alias="schemaVersion")
    pages: List[FormPage] = Field(default_factory=list)

    def iter_fields(self):
        """Every field in DOCUMENT ORDER.

        Conditions and computed refs may only look BACKWARDS, so "earlier" is
        defined entirely by this traversal: reordering it silently changes which
        documents publish.
        """
        for page in self.pages:
            for section in page.sections:
                for field in section.fields:
                    yield page, section, field

    def input_fields(self) -> List[FormField]:
        return [f for _p, _s, f in self.iter_fields() if f.type in INPUT_FIELD_TYPES]


# ---- helpers ----


def _coerce_doc(doc: "FormDocument | Dict[str, Any]") -> FormDocument:
    """Accept either a typed model or the raw camelCase wire dict.

    The route calls the gate with raw JSON and services call it with the parsed
    model; accepting only one forces a re-parse at every other call site.
    """
    if isinstance(doc, FormDocument):
        return doc
    return FormDocument.model_validate(doc)


def _is_display(field: FormField) -> bool:
    return field.type in DISPLAY_FIELD_TYPES


def _is_input(field: FormField) -> bool:
    return field.type in INPUT_FIELD_TYPES


def _condition_fact_keys(tree: Conditions) -> List[str]:
    """Bare answer keys referenced by a conditions tree (LHS plus cross-fact
    RHS), with the ``answers.`` namespace stripped. A non-``answers.`` fact
    passes through as-is so it fails the earlier-key check: a form document may
    only read its own earlier answers."""
    keys: List[str] = []
    for raw in collect_fact_keys(tree):
        keys.append(raw[len("answers.") :] if raw.startswith("answers.") else raw)
    return keys


def _condition_shape_problems(tree: Conditions, subject: str) -> List[str]:
    """Structural problems in an authored conditions tree.

    THE known rule-engine trap: ``rule_engine.evaluator`` reads a group with no
    rules as "unconditional" and returns True, so an unfinished builder session
    publishes as a field that is ALWAYS shown, and a required one blocks the user
    with a question they were never meant to see. Absent conditions (``None``)
    are the legitimate unconditional case; anything authored must be an
    evaluable group, at every level of the tree.

    Nesting past the evaluator's own guard is blocked for the same reason: the
    tree fails closed rather than open, but the author gets no explanation for a
    field that never appears.
    """
    if tree is None:
        return []

    problems: List[str] = []

    def _walk(node: Any, depth: int) -> None:
        if not isinstance(node, dict):
            problems.append(f"{subject} has a condition entry that is not a rule.")
            return
        if depth > 1 and (node.get("kind") == "condition" or "fact" in node):
            return  # a leaf condition: the rule engine owns its grammar
        # A GROUP past the evaluator's nesting guard is dead: ``_eval_group``
        # scores it False whatever it says, and ``collect_fact_keys`` stops here
        # too, so its facts also escape the earlier-field check above. Both add
        # up to a field that is silently never visible, which is exactly the
        # dead-end this gate exists to prevent. A leaf at this depth is fine,
        # hence the check sitting below the leaf test.
        if depth > _MAX_DEPTH:
            problems.append(
                f"{subject} exceeds the maximum nesting depth of {_MAX_DEPTH} - "
                "flatten the tree."
            )
            return
        rules = node.get("rules")
        if not isinstance(rules, list) or not rules:
            problems.append(
                f"{subject} has an empty condition group - add a condition or "
                "remove the conditions."
            )
            return
        for rule in rules:
            _walk(rule, depth + 1)

    _walk(tree, 1)
    return problems


# ---- publish gate ----


def validate_form_doc(doc: "FormDocument | Dict[str, Any]") -> List[str]:
    """Problems blocking publish; an empty list means publishable."""
    try:
        form = _coerce_doc(doc)
    except Exception as exc:  # noqa: BLE001 - a shape error is ONE problem, not a 500
        return [f"The form document is malformed: {exc}"]

    problems: List[str] = []

    if not form.pages:
        return ["The form needs at least one page."]

    # Duplicate / missing / malformed keys across the WHOLE document: two fields
    # writing one key means an answer is silently overwritten, and which one
    # loses depends on document order.
    seen_keys: Set[str] = set()
    for _page, _section, field in form.iter_fields():
        if _is_display(field):
            continue  # display fields collect nothing
        name = field.label or field.type
        key = (field.key or "").strip()
        if not key:
            problems.append(f'"{name}" is missing an answer key.')
            continue
        if not _KEY_RE.match(key):
            problems.append(
                f'Answer key "{key}" must be letters, digits and underscores.'
            )
        if key in seen_keys:
            problems.append(f'Duplicate answer key "{key}".')
        seen_keys.add(key)

    # A page with nothing to answer is a dead end in the renderer.
    for index, page in enumerate(form.pages):
        field_count = sum(len(section.fields) for section in page.sections)
        if field_count == 0:
            problems.append(f"Page {index + 1} is empty.")

    # Per-field rules plus earlier-only condition refs, in document order. A
    # section's conditions see only the sections before it; a field's see every
    # prior field. ``earlier_keys`` is every prior input key (the computed-ref
    # scope); ``earlier_conditionable`` is the subset whose type can be a
    # condition fact; ``earlier_repeaters`` maps a repeater/table key to its
    # column types for the aggregate gate.
    earlier_keys: Set[str] = set()
    earlier_conditionable: Set[str] = set()
    earlier_repeaters: Dict[str, Dict[str, str]] = {}
    for page in form.pages:
        for section in page.sections:
            problems.extend(
                _condition_shape_problems(section.conditions_json, "A section")
            )
            for bare in _condition_fact_keys(section.conditions_json):
                if bare not in earlier_conditionable:
                    problems.append(
                        f'A section condition references "{bare}", '
                        "which is not an earlier field."
                    )
            for field in section.fields:
                name = field.label or field.key or field.type

                # An unknown type renders as nothing and validates as nothing:
                # the definition is checked once at publish and trusted for
                # years, so it must never reach a published version.
                if field.type not in ALL_FIELD_TYPES:
                    problems.append(
                        f'"{name}" has an unknown field type "{field.type}".'
                    )

                problems.extend(
                    _condition_shape_problems(field.conditions_json, f'"{name}"')
                )
                for bare in _condition_fact_keys(field.conditions_json):
                    if bare not in earlier_conditionable:
                        problems.append(
                            f'"{name}" has a condition referencing "{bare}", '
                            "which is not an earlier field."
                        )

                if field.type in CHOICE_FIELD_TYPES:
                    items = field.options.items if field.options else []
                    if not items:
                        problems.append(f'"{name}" needs at least one option.')
                    values = [item.value.strip() for item in items]
                    if any(not v for v in values):
                        # The value, not the label, is what is stored and what
                        # conditions compare against.
                        problems.append(f'"{name}" has an option without a value.')
                    if len(set(values)) != len(values):
                        problems.append(f'"{name}" has duplicate option values.')

                if field.type == "rating" and (
                    field.rating is None or field.rating.max < 1
                ):
                    problems.append(f'"{name}" needs a rating scale of at least 1.')

                if field.type == "repeater":
                    _validate_repeater_fields(field, name, problems)

                if field.type == "table":
                    _validate_table_columns(field, name, problems)

                if field.type == "computed":
                    _validate_computed_field(
                        field,
                        name,
                        problems,
                        form=form,
                        earlier_keys=earlier_keys,
                        earlier_repeaters=earlier_repeaters,
                    )

                if field.text is not None and field.text.pattern:
                    try:
                        re.compile(field.text.pattern)
                    except re.error:
                        problems.append(f'"{name}" has an invalid pattern.')
                    if not (field.text.pattern_message or "").strip():
                        # A regex failure with no message shows the user an error
                        # they cannot act on.
                        problems.append(f'"{name}" needs a message for its pattern.')

                if field.key and _is_input(field):
                    earlier_keys.add(field.key)
                    if field.type in CONDITIONABLE_TYPES:
                        earlier_conditionable.add(field.key)
                    if field.type == "repeater" and field.repeater:
                        earlier_repeaters[field.key] = {
                            s.key: s.type for s in field.repeater.fields if s.key
                        }
                    if field.type == "table" and field.table:
                        # A table aggregates exactly like a repeater.
                        earlier_repeaters[field.key] = {
                            c.key: c.type for c in field.table.columns if c.key
                        }

    return problems


def _validate_repeater_fields(
    field: "FormField", name: str, problems: List[str]
) -> None:
    """Publish-gate rules for a repeater: sub-keys are the row object's keys and
    aggregates address them by name, so a duplicate makes ``sum(notes.hours)``
    ambiguous."""
    subs = field.repeater.fields if field.repeater else []
    if not subs:
        problems.append(f'"{name}" needs at least one sub-field.')
    sub_keys = [(s.key or "").strip() for s in subs]
    if any(not k for k in sub_keys):
        problems.append(f'"{name}" has a sub-field without a key.')
    if len(set(sub_keys)) != len(sub_keys):
        problems.append(f'"{name}" has duplicate sub-field keys.')
    for sub in subs:
        if sub.type not in SUB_FIELD_TYPES:
            problems.append(
                f'"{name}" sub-field "{sub.key}" has an unknown type "{sub.type}".'
            )
    if field.repeater is not None:
        low, high = field.repeater.min_rows, field.repeater.max_rows
        if low is not None and high is not None and low > high:
            # An unsatisfiable pair fails every submission with two
            # contradictory errors.
            problems.append(f'"{name}" has min rows greater than max rows.')


def _validate_table_columns(
    field: "FormField", name: str, problems: List[str]
) -> None:
    """Publish-gate rules for a Table block: non-empty columns, unique keys,
    known column types, and computed columns referencing EARLIER numeric columns
    of the same table (document order is what bans forward refs and cycles)."""
    cols = field.table.columns if field.table else []
    if not cols:
        problems.append(f'"{name}" needs at least one column.')
    keys = [(c.key or "").strip() for c in cols]
    if any(not k for k in keys):
        problems.append(f'"{name}" has a column without a key.')
    if len(set(keys)) != len(keys):
        problems.append(f'"{name}" has duplicate column keys.')
    if field.table is not None:
        low, high = field.table.min_rows, field.table.max_rows
        if low is not None and high is not None and low > high:
            problems.append(f'"{name}" has min rows greater than max rows.')

    earlier_numeric: Set[str] = set()
    for col in cols:
        if col.type not in TABLE_COLUMN_TYPES:
            problems.append(
                f'"{name}" column "{col.key}" has an unknown type "{col.type}".'
            )
        if col.type == "computed":
            expr = (col.computed.expression or "").strip() if col.computed else ""
            if not expr:
                problems.append(
                    f'"{name}" column "{col.key}" is missing its expression.'
                )
            else:
                try:
                    parse_expression(expr)
                    for ref in field_refs(expr):
                        if ref not in earlier_numeric:
                            problems.append(
                                f'"{name}" column "{col.key}" references "{ref}", '
                                "which is not an earlier numeric column."
                            )
                except ComputedExpressionError as exc:
                    problems.append(
                        f'"{name}" column "{col.key}" has an invalid '
                        f"expression: {exc}"
                    )
        # Number/computed columns and a fixed constant are referenceable: the
        # fixed column exists so a server-stamped tax rate can feed the amount.
        if col.key and (col.type in NUMERIC_FIELD_TYPES or col.type == "fixed"):
            earlier_numeric.add(col.key)


def _validate_computed_field(
    field: "FormField",
    name: str,
    problems: List[str],
    *,
    form: FormDocument,
    earlier_keys: Set[str],
    earlier_repeaters: Dict[str, Dict[str, str]],
) -> None:
    """Publish-gate rules for a computed field.

    Evaluation is a single forward pass, so a forward reference is always null
    and a cycle (including ``total = total + 1``, since a field's own key only
    becomes "earlier" after its own validation) can only be caught here. A
    non-numeric ref would publish and then evaluate to null on every submission,
    which reads as a broken engine rather than a broken form.
    """
    expr = (field.computed.expression or "").strip() if field.computed else ""
    if not expr:
        problems.append(f'"{name}" is missing its expression.')
        return
    try:
        parse_expression(expr)
        numeric_keys = _numeric_keys(form)
        for ref in field_refs(expr):
            if ref not in earlier_keys:
                problems.append(
                    f'"{name}" references "{ref}", which is not an earlier field.'
                )
            elif ref not in numeric_keys:
                problems.append(f'"{name}" references "{ref}", which is not numeric.')
        for agg in aggregate_refs(expr):
            cols = earlier_repeaters.get(agg.repeater_key)
            if cols is None:
                problems.append(
                    f'"{name}" aggregates "{agg.repeater_key}", which is not an '
                    "earlier repeater field."
                )
                continue
            if agg.func == "count":
                continue  # count needs only the repeater, not a column
            if agg.sub_key not in cols:
                problems.append(
                    f'"{name}" aggregates column "{agg.sub_key}", which is not a '
                    f'sub-field of "{agg.repeater_key}".'
                )
            elif cols[agg.sub_key] not in NUMERIC_FIELD_TYPES:
                problems.append(
                    f'"{name}" aggregates "{agg.sub_key}", which is not a '
                    "numeric column."
                )
    except ComputedExpressionError as exc:
        problems.append(f'"{name}" has an invalid expression: {exc}')


def _numeric_keys(form: FormDocument) -> Set[str]:
    return {f.key for f in form.input_fields() if f.key and f.type in NUMERIC_FIELD_TYPES}
