"""Request bodies for the service job and technician APIs (after-sales P1).

Responses are plain dicts built by ``service_job_service`` so the wire shape (status key,
resolved names) lives in one place.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, field_validator

TRANSITION_TARGETS = ("proposed", "confirmed", "on_the_way", "arrived", "completed", "verified", "cancelled")


class ServiceJobCreate(BaseModel):
    customer_name: str
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None
    site_address_line1: Optional[str] = None
    site_address_line2: Optional[str] = None
    site_postcode: Optional[str] = None
    site_city: Optional[str] = None
    site_state: Optional[str] = None
    site_country: Optional[str] = None
    problem: Optional[str] = None
    complaint_id: Optional[str] = None

    @field_validator("customer_name", mode="before")
    @classmethod
    def customer_not_blank(cls, v):
        if not isinstance(v, str) or not v.strip():
            raise ValueError("customer_name is required")
        return v.strip()


class ServiceJobUpdate(BaseModel):
    customer_name: Optional[str] = None
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None
    site_address_line1: Optional[str] = None
    site_address_line2: Optional[str] = None
    site_postcode: Optional[str] = None
    site_city: Optional[str] = None
    site_state: Optional[str] = None
    site_country: Optional[str] = None
    problem: Optional[str] = None
    complaint_id: Optional[str] = None

    @field_validator("customer_name", mode="before")
    @classmethod
    def customer_not_blank(cls, v):
        if v is None:
            return v
        if not isinstance(v, str) or not v.strip():
            raise ValueError("customer_name must not be blank")
        return v.strip()


class ConfirmJobRequest(BaseModel):
    scheduled_from: datetime
    scheduled_to: Optional[datetime] = None
    customer_agreed_by: str

    @field_validator("customer_agreed_by", mode="before")
    @classmethod
    def agreed_by_not_blank(cls, v):
        if not isinstance(v, str) or not v.strip():
            raise ValueError("customer_agreed_by is required: record who agreed the date")
        return v.strip()


class AssignJobRequest(BaseModel):
    technician_id: str


class TransitionJobRequest(BaseModel):
    to: Literal[TRANSITION_TARGETS]  # type: ignore[valid-type]
    reason: Optional[str] = None


def _blank_to_none(v):
    if isinstance(v, str):
        v = v.strip()
        return v or None
    return v


class TechnicianCreate(BaseModel):
    name: str
    phone: Optional[str] = None
    employment_type: Literal["employee", "contractor"]
    is_active: bool = True

    @field_validator("name", mode="before")
    @classmethod
    def name_not_blank(cls, v):
        if not isinstance(v, str) or not v.strip():
            raise ValueError("name is required")
        return v.strip()

    @field_validator("phone", mode="before")
    @classmethod
    def phone_blank(cls, v):
        return _blank_to_none(v)


class TechnicianUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    employment_type: Optional[Literal["employee", "contractor"]] = None
    is_active: Optional[bool] = None

    @field_validator("name", mode="before")
    @classmethod
    def name_not_blank(cls, v):
        if v is None:
            return v
        if not isinstance(v, str) or not v.strip():
            raise ValueError("name must not be blank")
        return v.strip()

    @field_validator("phone", mode="before")
    @classmethod
    def phone_blank(cls, v):
        return _blank_to_none(v)
