"""Wire shapes for product sets.

Every field the frontend reads is declared here. `response_model` DROPS anything
undeclared, so a value the service computed perfectly can still never reach the
screen, and that reads as "the backend did not send it" - sending someone to
debug the wrong half.

Contract mirror: `sorento_crm_frontend/app/(protected)/master-data-management/
product-sets/services/productSetService.ts`.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field


class ProductSetPriceResponse(BaseModel):
    """Both figures travel, always.

    `computed` is null with a `reason` when there is no basis yet. A set
    mid-authoring must not claim RM 0.00: a price of zero and a missing price are
    different facts.
    """

    computed: Optional[Decimal] = None
    override: Optional[Decimal] = None
    resolved: Optional[Decimal] = None
    is_overridden: bool = False
    reason: Optional[str] = None


class ProductSetMemberResponse(BaseModel):
    id: str
    product_id: str
    product_code: Optional[str] = None
    product_name: Optional[str] = None
    description: Optional[str] = None
    list_price: Optional[Decimal] = None
    is_discontinued: bool = False
    quantity: Decimal = Decimal("1")
    contributes_to_price: bool = False
    sort_order: int = 0
    #: Summed across every warehouse. Null when stock was not loaded (list rows),
    #: which is not the same as 0 and must not be rendered as it.
    available: Optional[int] = None

    class Config:
        from_attributes = True


class ProductSetResponse(BaseModel):
    id: str
    set_code: str
    name: str
    is_active: bool = True
    company_id: Optional[str] = None
    price: ProductSetPriceResponse
    member_count: int = 0
    complete_sets: Optional[int] = None
    #: The member that produced the minimum, so a zero is explicable rather than
    #: bare. "0" alone reads as a bug when there is stock on the shelf.
    limiting_member_code: Optional[str] = None
    override_set_by: Optional[str] = None
    override_set_at: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ProductSetDetailResponse(ProductSetResponse):
    members: list[ProductSetMemberResponse] = Field(default_factory=list)


class ProductSetMemberPayload(BaseModel):
    #: By CODE, never by UUID. The screen shows codes and no UUID reaches the UI.
    product_code: str
    quantity: Decimal = Decimal("1")
    contributes_to_price: bool = False
    sort_order: int = 0


class ProductSetCreate(BaseModel):
    set_code: str
    name: str
    is_active: bool = True
    list_price_override: Optional[Decimal] = None
    members: list[ProductSetMemberPayload] = Field(default_factory=list)


class ProductSetUpdate(BaseModel):
    """Every field optional: this is a partial update.

    `members` omitted leaves membership alone; `members: []` empties it. The
    difference matters - renaming a set must not silently drop its members.
    """

    set_code: Optional[str] = None
    name: Optional[str] = None
    is_active: Optional[bool] = None
    list_price_override: Optional[Decimal] = None
    members: Optional[list[ProductSetMemberPayload]] = None


# ------------------------------------------------------------ seeding (group H)
#
# Contract mirror: `sorento_crm_frontend/app/(protected)/master-data-management/
# product-sets/types/productSetProposal.types.ts`. Field for field - a value the
# service computed perfectly but never declared here is dropped on the way out
# and reads on screen as "the backend did not send it".


class ProductSetProposalMemberResponse(BaseModel):
    """One SKU the pass believes belongs in the set.

    Addressed by CODE. No UUID reaches the screen, and the price and description
    are hydrated live from `products` rather than read back off a snapshot the
    pass stored - a stored price goes stale and becomes a second source of truth.
    """

    product_code: str
    description: Optional[str] = None
    list_price: Optional[Decimal] = None
    quantity: Decimal = Decimal("1")
    contributes_to_price: bool = False
    sort_order: int = 0
    is_discontinued: bool = False


class ProductSetProposalResponse(BaseModel):
    id: str
    #: The prefix and number the members share, e.g. `SRTWC8608`. Two candidates
    #: in one family are the same assembly in different trap variants, so the
    #: review screen groups them.
    family_key: str
    set_code: str
    name: str
    members: list[ProductSetProposalMemberResponse] = Field(default_factory=list)
    #: Sum over the ticked members. Null, NEVER 0.00, when nothing is ticked.
    computed_price: Optional[Decimal] = None


class ProductSetProposalBatchResponse(BaseModel):
    id: str
    company_name: Optional[str] = None
    created_at: datetime
    created_by_name: Optional[str] = None
    #: Derived from the rows on read, not stored. A stored count that disagrees
    #: with the list under it sends people to debug the list.
    family_count: int = 0
    proposal_count: int = 0
    proposals: list[ProductSetProposalResponse] = Field(default_factory=list)


class ProductSetProposalsResponse(BaseModel):
    """Null means no pass has run yet, which is not the same as a pass that found
    nothing. The review screen says two different things about the two."""

    batch: Optional[ProductSetProposalBatchResponse] = None


class ApplyProductSetProposalsRequest(BaseModel):
    #: IDS ONLY. The set code, the name and the members come off the stored
    #: proposal, so the screen cannot write a set the pass did not derive.
    proposal_ids: list[str] = Field(default_factory=list)


class AppliedProductSetProposal(BaseModel):
    proposal_id: str
    set_code: str


class RefusedProductSetProposal(AppliedProductSetProposal):
    #: A sentence, not a code. The reviewer ticked it and has to learn why it did
    #: not land, on the toast, without opening a log.
    reason: str


class ApplyProductSetProposalsResponse(BaseModel):
    applied: list[AppliedProductSetProposal] = Field(default_factory=list)
    refused: list[RefusedProductSetProposal] = Field(default_factory=list)
