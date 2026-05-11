"""External respond contact sync schemas."""

from typing import Optional

from pydantic import BaseModel


class RespondContactSyncRequest(BaseModel):
    id: Optional[int] = None
    phone_number: Optional[str] = None
    phone: Optional[str] = None
    name: Optional[str] = None
    firstName: Optional[str] = None
    lastName: Optional[str] = None
    email: Optional[str] = None
    language: Optional[str] = None
    countryCode: Optional[str] = None
    status: Optional[str] = None


class RespondContactSyncResponse(BaseModel):
    id: str
    phone_number: str
    name: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    respond_io_id: Optional[str] = None
    action: str

