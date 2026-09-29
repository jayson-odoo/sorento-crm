"""Schemas for the contact <-> customer link routes (PLAN-contact-customers-29sep D2)."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class ContactCustomerLinkResponse(BaseModel):
    # The link row's own id: what the unlink pending action parks on. Never shown.
    id: str
    customer_id: str
    customer_code: str
    customer_name: str
    is_active: bool
    is_primary: bool
    source: str
    sales_agent_id: Optional[str] = None
    sales_agent_code: Optional[str] = None
    sales_agent_name: Optional[str] = None
    created_at: datetime


class SuggestedCustomerResponse(BaseModel):
    customer_id: str
    customer_code: str
    customer_name: str
    phone_number: Optional[str] = None
    sales_agent_code: Optional[str] = None
    sales_agent_name: Optional[str] = None


class ContactCustomersResponse(BaseModel):
    data: list[ContactCustomerLinkResponse]
    suggested: list[SuggestedCustomerResponse]


class ContactCustomerLinkCreate(BaseModel):
    customer_id: str
    is_primary: bool = False


class ContactCustomerPrimaryUpdate(BaseModel):
    is_primary: bool


class AgentCustomerAssign(BaseModel):
    customer_id: str
