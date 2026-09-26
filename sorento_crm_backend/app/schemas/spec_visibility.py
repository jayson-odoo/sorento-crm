"""Admin API shapes for the spec visibility policy.

One body for every tier (`{effective, override}`), so the same card serves the
contact page, the market segment admin and the settings default without three
response shapes to keep in step. The full contract, request and response, is
documented at the top of `sorento_crm_frontend/services/specVisibilityService.ts`.
"""
from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class SpecKeyRef(BaseModel):
    """A registry key RESOLVED, not a bare slug: the card renders the label, and
    a key slug must never reach the UI."""

    key: str
    label: str


class SpecVisibilityPolicyOut(BaseModel):
    #: The Show-only list. null = every key visible; [] = none at all.
    specs: Optional[List[SpecKeyRef]] = None
    #: `specs`'s sibling: null = not this rule, [] = nothing hidden (the
    #: opposite of what [] means on `specs`), a list = hide exactly these.
    excluded_specs: Optional[List[SpecKeyRef]] = None
    #: The net effect - what the contact may NOT see today. Always a list,
    #: never null; [] reads "nothing hidden".
    hidden: List[SpecKeyRef] = Field(default_factory=list)
    source: Literal["contact", "segment", "default"]
    #: The market segment's NAME when `source` is `segment`, so the badge can
    #: read "Market segment: Retail". A name, never the code.
    source_label: Optional[str] = None


class SpecVisibilityPolicyResponse(BaseModel):
    effective: SpecVisibilityPolicyOut
    #: The row stored AT the requested tier. null = this tier inherits.
    override: Optional[SpecVisibilityPolicyOut] = None


class SpecVisibilityInput(BaseModel):
    """Upsert body. Both lists are REPLACED wholesale, never merged - merging
    would make removing a key impossible from the card."""

    #: REQUIRED, and nullable rather than defaulted: a PUT replaces the whole
    #: row, so a body that simply omitted the key would widen the policy to
    #: every spec - the one edit an admin can make without meaning to.
    spec_keys: Optional[List[str]] = Field(
        ..., description="null = every key visible; [] = none.", max_length=200
    )
    #: REQUIRED and nullable, same reasoning as `spec_keys`. Never both
    #: non-null with `spec_keys` on the same body - 422 "Pick specs to show or
    #: to hide, not both."
    excluded_spec_keys: Optional[List[str]] = Field(
        ...,
        description=(
            "null = not this rule; [] = nothing hidden; a list = hide exactly "
            "these."
        ),
        max_length=200,
    )
