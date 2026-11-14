"""Sales > Dealer access: a salesperson's own accounts and the people who hold access to them
(DEALER-ACCESS-SCREEN S1-S5). Plain `def` handlers; every rule and every write lives in
`app.services.dealer_access_screen`, which goes through the agent's access service. Unlink is the deferred record
action `dealer_access_link.unlink` (`app/services/record_actions.py`)."""
from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission
from app.services import dealer_access_screen

router = APIRouter()

EDIT_OWN = "user_management.contacts.edit_own"
Role = Literal["owner", "employee"]


class GrantPerson(BaseModel):
    name: str = Field(max_length=255)
    phone: str = Field(max_length=40)
    role: Role


class GrantBody(BaseModel):
    """`companies` (1-2 codes, DEALER-ACCESS-NAMES N4.1); the legacy single `company` is still accepted."""

    companies: Optional[list[str]] = Field(default=None, min_length=1, max_length=2)
    company: Optional[str] = Field(default=None, max_length=10)
    account_ids: list[str] = Field(min_length=1, max_length=10)
    people: list[GrantPerson] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def _one_company_field(self):
        if not self.companies and not self.company:
            raise ValueError("Pick a company.")
        if self.companies and any(len(c) > 10 for c in self.companies):
            raise ValueError("Pick a company.")
        return self

    def codes(self) -> list[str]:
        return list(self.companies) if self.companies else [str(self.company)]


class UpdateBody(BaseModel):
    company: str = Field(max_length=10)
    role: Role
    account_ids: list[str] = Field(max_length=10)


@router.get("/accounts")
def accounts(
    company: str = Query(..., max_length=10),
    current_user: dict = Depends(require_permission(EDIT_OWN)),
    db: Session = Depends(get_db),
):
    return dealer_access_screen.my_accounts(db, current_user["id"], company)


# ai: not-for-assistant the dealer-access screen's Customer filter options (own or granted-company customers); the assistant finds customers through its own customer tools
@router.get("/customers")
def customers(
    query: Optional[str] = Query(None, max_length=100),
    mine: bool = Query(True),
    company: list[str] = Query(default=[]),
    current_user: dict = Depends(require_permission(EDIT_OWN)),
    db: Session = Depends(get_db),
):
    return dealer_access_screen.customers(db, current_user["id"], query=query, mine=mine, companies=company)


# ai: not-for-assistant the salesperson's own dealer-access screen list; the assistant reads the same own-scope dealer contacts through its dealer-access tool crm_contacts_find (#2268)
@router.get("/people")
def people(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    query: Optional[str] = Query(None, max_length=100),
    company: list[str] = Query(default=[]),
    access: Optional[Role] = Query(None),
    mine: bool = Query(True),
    customer: list[str] = Query(default=[]),
    current_user: dict = Depends(require_permission(EDIT_OWN)),
    db: Session = Depends(get_db),
):
    return dealer_access_screen.list_people(
        db, current_user["id"], mine=mine, customer_ids=customer, companies=company, access=access, query=query,
        page=page, limit=limit,
    )


@router.post("/grant")
def grant(
    body: GrantBody,
    current_user: dict = Depends(require_permission(EDIT_OWN)),
    db: Session = Depends(get_db),
):
    return dealer_access_screen.grant(
        db, current_user["id"], body.codes(), body.account_ids, [p.model_dump() for p in body.people]
    )


@router.put("/people/{contact_id}")
def update_person(
    contact_id: str,
    body: UpdateBody,
    current_user: dict = Depends(require_permission(EDIT_OWN)),
    db: Session = Depends(get_db),
):
    dealer_access_screen.update(db, current_user["id"], contact_id, body.company, body.role, body.account_ids)
    return {"id": contact_id}


@router.post("/people/{contact_id}/respond")
def respond_retry(
    contact_id: str,
    current_user: dict = Depends(require_permission(EDIT_OWN)),
    db: Session = Depends(get_db),
):
    """N5.5: "Try again in Respond.io" for one person I may change."""
    return dealer_access_screen.respond_retry(db, current_user["id"], contact_id)
