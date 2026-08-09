"""Request / response shapes for the warranty configuration editor (S7b).

The entitlement engine has been correct and unconfigurable since S2: 31 Kinds, 41
Terms and TWO Kind Rules, with 29 of the 31 Kinds unreachable by any rule. These
schemas are the wire contract of the screens that fix that, pinned in
`documentation/plans/after-sales/PLAN-retail-complaint-to-visit.md` and gated by
`tests/test_warranty_config_*.py`.

Three rules run through every model here.

**Every id-bearing relation is ALSO returned resolved.** `TermResponse` carries
`kind_code` / `kind_name` beside `kind_id`, `covered_defect_type_labels` beside
`covered_defect_type_ids`, and `PolicyResponse` carries `source_attachment_name`
beside its id. The repo forbids a UUID on screen, and a frontend that has to fetch
a second list to render a row shows the id for the first paint.

**Every destructive action's count travels on the row it will destroy**
(AC-P16): `PolicyResponse.term_count`, `TermResponse.assessment_count`,
`KindResponse.rule_count` / `term_count`. The delete is offered from the grid, so a
count that exists only on a detail response cannot reach the dialog that needs it.

**`has_no_rules` / `has_no_terms` are fields, not colours** (AC-P17). Computing
"zero" in a grid cell makes the dead end visible in exactly one place and invisible
to export, to MCP and to the AI assistant - which is AC-P7's own disease one layer
up.

Update schemas are all-Optional and read with `model_dump(exclude_unset=True)`, so
"set this to null" and "did not mention it" are distinguishable. That is what makes
AC-P26's recovery path (reopen a mis-superseded policy by PATCHing `effective_to`
to null) expressible at all.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.services.warranty_service import KIND_RULE_MATCH_TYPES

# ------------------------------------------------------------------ shared bits


class WarrantyKindRef(BaseModel):
    """The `{id, code, name}` triple every picker and every grouped header reads.

    `code` AND `name` because the two disagree on purpose: the code is the seed's
    idempotence key and the name is what the policy document prints.
    """

    id: str
    code: str
    name: str


def _clean(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


# ---------------------------------------------------------------------- policies


class PolicyCreate(BaseModel):
    version: str = Field(..., min_length=1, max_length=32)
    effective_from: date
    effective_to: Optional[date] = None
    source_attachment_id: Optional[str] = None
    policy_text: Optional[str] = None

    @field_validator("version")
    @classmethod
    def _version_not_blank(cls, value: str) -> str:
        cleaned = (value or "").strip()
        if not cleaned:
            raise ValueError("A policy version is required.")
        return cleaned

    @model_validator(mode="after")
    def _window_is_not_inverted(self):
        if self.effective_to is not None and self.effective_to < self.effective_from:
            # A window that ends before it starts matches nothing and reads as a typo
            # nowhere. It is also invisible to the overlap guard, because an inverted
            # range overlaps no range at all.
            raise ValueError("The effective-to date cannot be before the effective-from date.")
        return self


class PolicyUpdate(BaseModel):
    version: Optional[str] = Field(None, min_length=1, max_length=32)
    effective_from: Optional[date] = None
    effective_to: Optional[date] = None
    source_attachment_id: Optional[str] = None
    policy_text: Optional[str] = None

    @field_validator("version")
    @classmethod
    def _version_not_blank(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("A policy version is required.")
        return cleaned


class PolicyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    version: str
    effective_from: date
    effective_to: Optional[date] = None
    source_attachment_id: Optional[str] = None
    # Resolved so the screen never prints the id (cursor rule).
    source_attachment_name: Optional[str] = None
    policy_text: Optional[str] = None
    # AC-P13 / AC-P16: how many Terms a delete would take with it, on the LIST row.
    term_count: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class SupersedeResponse(BaseModel):
    """AC-P2a: ONE transaction, two rows. Half a supersede is the worst of the
    three states - the old policy is closed and nothing governs the days after it,
    so every purchase from then on answers `unknown`."""

    closed: PolicyResponse
    created: PolicyResponse


# ------------------------------------------------------------------------- terms


class TermCreate(BaseModel):
    kind_id: str
    part_name: str = Field(..., min_length=1, max_length=120)
    duration_months: Optional[int] = None
    is_lifetime: bool = False
    covered_defect_type_ids: Optional[List[str]] = None
    installation_included: bool = False
    registration_bonus_months: Optional[int] = None
    qualifications: Optional[str] = None
    exclusions: Optional[str] = None

    @field_validator("part_name")
    @classmethod
    def _part_not_blank(cls, value: str) -> str:
        cleaned = (value or "").strip()
        if not cleaned:
            raise ValueError("A part name is required.")
        return cleaned


class TermUpdate(BaseModel):
    kind_id: Optional[str] = None
    part_name: Optional[str] = Field(None, min_length=1, max_length=120)
    duration_months: Optional[int] = None
    is_lifetime: Optional[bool] = None
    covered_defect_type_ids: Optional[List[str]] = None
    installation_included: Optional[bool] = None
    registration_bonus_months: Optional[int] = None
    qualifications: Optional[str] = None
    exclusions: Optional[str] = None

    @field_validator("part_name")
    @classmethod
    def _part_not_blank(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("A part name is required.")
        return cleaned


class TermResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    policy_id: str
    kind_id: str
    kind_code: str
    kind_name: str
    part_name: str
    duration_months: Optional[int] = None
    is_lifetime: bool = False
    covered_defect_type_ids: Optional[List[str]] = None
    # NULL and [] both mean EVERY defect - the engine pins the two as identical, so
    # an empty list here is not "no defects are covered".
    covered_defect_type_labels: Optional[List[str]] = None
    installation_included: bool = False
    registration_bonus_months: Optional[int] = None
    qualifications: Optional[str] = None
    exclusions: Optional[str] = None
    # AC-P8a / AC-P16: the delete confirmation names how many stored verdicts point
    # at this Term. They SURVIVE the delete (term_id is ON DELETE SET NULL); the
    # count is what makes that a considered decision rather than a discovered one.
    assessment_count: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class TermKindGroup(BaseModel):
    kind: WarrantyKindRef
    terms: List[TermResponse]


class TermsGroupedResponse(BaseModel):
    """AC-P4. A Water Closet carries three Terms that disagree on all four
    dimensions, so a screen showing one at a time cannot be checked against the
    policy document - which is the only way anybody knows the configuration is
    right."""

    groups: List[TermKindGroup]
    total: int


# ------------------------------------------------------------------------- kinds


class KindCreate(BaseModel):
    code: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=255)
    consumer_label: Optional[str] = Field(None, max_length=120)
    consumer_icon: Optional[str] = Field(None, max_length=64)
    sort_order: int = 0
    is_active: bool = True

    @field_validator("code", "name")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        cleaned = (value or "").strip()
        if not cleaned:
            raise ValueError("This field is required.")
        return cleaned


class KindUpdate(BaseModel):
    code: Optional[str] = Field(None, min_length=1, max_length=64)
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    consumer_label: Optional[str] = Field(None, max_length=120)
    consumer_icon: Optional[str] = Field(None, max_length=64)
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None

    @field_validator("code", "name")
    @classmethod
    def _not_blank(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("This field is required.")
        return cleaned


class KindResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    code: str
    name: str
    consumer_label: Optional[str] = None
    consumer_icon: Optional[str] = None
    sort_order: int = 0
    is_active: bool = True
    # AC-P7: zero rules means no product can ever reach this Kind.
    rule_count: int = 0
    # AC-P7a: zero terms means every product that DOES reach it answers `no_term` -
    # the same invisible dead end one column further along.
    term_count: int = 0
    has_no_rules: bool = False
    has_no_terms: bool = False


# -------------------------------------------------------------------- kind rules


def _validated_match_type(value: Optional[str]) -> str:
    """AC-P24: an undeclared match type is refused at WRITE time.

    The engine keeps its tolerant READ behaviour (log a warning, match nothing) and
    that split is deliberate: bad data must never stop a complaint being judged,
    and a rule that can never fire must never be creatable - it is saved, listed,
    inert and invisible, which is exactly the dead end AC-P7 exists to surface.
    """
    cleaned = (value or "").strip().lower()
    if cleaned not in KIND_RULE_MATCH_TYPES:
        raise ValueError(
            "match_type must be one of: " + ", ".join(KIND_RULE_MATCH_TYPES) + "."
        )
    return cleaned


def _validated_match_value(value: Optional[str]) -> str:
    cleaned = (value or "").strip()
    if not cleaned:
        # An empty match value matches NOTHING in the engine, so a saved one is a row
        # that can never fire and never explains itself.
        raise ValueError("A match value is required.")
    return cleaned


class KindRuleCreate(BaseModel):
    kind_id: str
    match_type: str
    match_value: str
    priority: int = 0

    @field_validator("match_type")
    @classmethod
    def _match_type(cls, value: str) -> str:
        return _validated_match_type(value)

    @field_validator("match_value")
    @classmethod
    def _match_value(cls, value: str) -> str:
        return _validated_match_value(value)


class KindRuleUpdate(BaseModel):
    kind_id: Optional[str] = None
    match_type: Optional[str] = None
    match_value: Optional[str] = None
    priority: Optional[int] = None

    @field_validator("match_type")
    @classmethod
    def _match_type(cls, value: Optional[str]) -> Optional[str]:
        return None if value is None else _validated_match_type(value)

    @field_validator("match_value")
    @classmethod
    def _match_value(cls, value: Optional[str]) -> Optional[str]:
        return None if value is None else _validated_match_value(value)


class KindRuleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    kind_id: str
    kind_code: str
    kind_name: str
    match_type: str
    match_value: str
    # Higher wins, and it is consulted BEFORE match-type specificity (AC-D20).
    priority: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ------------------------------------------------------------------- the tester


class KindRuleCandidate(BaseModel):
    """An unsaved rule the admin is about to write (AC-P6b).

    Validated exactly like `KindRuleCreate`, or the tester would happily report
    that a rule which can never be saved would win.
    """

    kind_id: str
    match_type: str
    match_value: str
    priority: int = 0

    @field_validator("match_type")
    @classmethod
    def _match_type(cls, value: str) -> str:
        return _validated_match_type(value)

    @field_validator("match_value")
    @classmethod
    def _match_value(cls, value: str) -> str:
        return _validated_match_value(value)


class KindRuleTestRequest(BaseModel):
    product_code: Optional[str] = None
    category_code: Optional[str] = None
    product_name: Optional[str] = None
    candidate_rule: Optional[KindRuleCandidate] = None

    @model_validator(mode="after")
    def _something_to_test(self):
        if not any(
            _clean(value)
            for value in (self.product_code, self.category_code, self.product_name)
        ):
            # A tester called with nothing to test answers "no match" for every
            # product, which reads as a broken mapping rather than as a blank form.
            raise ValueError(
                "Enter a product code, a category code or a product name to test."
            )
        return self


class TestedRule(BaseModel):
    """`id` is NULLABLE: the unsaved candidate has not been written yet, and
    inventing an id lets the frontend link to a row that does not exist."""

    id: Optional[str] = None
    kind_id: str
    match_type: str
    match_value: str
    priority: int = 0
    is_candidate: bool = False


class KindRuleTestMatch(BaseModel):
    rank: int
    rule: TestedRule
    kind: WarrantyKindRef
    matched_length: int
    is_candidate: bool = False


class KindRuleTestResponse(BaseModel):
    """AC-P6c: the WHOLE ranked list, not only the winner.

    A mapping that wins by one tie-break is a different fact from a mapping that is
    the only match, and only the second one is safe to stop thinking about.
    """

    resolved_kind: Optional[WarrantyKindRef] = None
    deciding_rule: Optional[TestedRule] = None
    matches: List[KindRuleTestMatch] = []


# ------------------------------------------------------------------ defect types


class DefectTypeOption(BaseModel):
    """AC-P18. Load-bearing, not convenience: `covered_defect_type_ids` is a
    `uuid[]` of `lookup_options.id`, and `GET /api/v1/lookup/{set_key}/options`
    returns `value` + `label` and never the id - so without this the Term editor
    cannot write a defect scope at all."""

    id: str
    label: str
