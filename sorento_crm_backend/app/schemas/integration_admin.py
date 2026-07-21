"""Schemas for the integration management API (AC-AC-08).

The governing rule here is AC-AC-39: **no response model in this file may carry
a key or a decrypted credential.** Integration records exist to hold secrets, so
the schema layer is where a leak is cheapest to prevent and most expensive to
miss -- a single careless field would publish credentials to any client that can
read the list endpoint.

Plaintext appears in exactly one place: ``IssuedKeyResponse``, returned once at
creation or rotation and never retrievable again.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class IntegrationCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    type: str = Field(..., min_length=1, max_length=50)
    act_as_user_id: Optional[str] = None
    config_json: Optional[dict[str, Any]] = None
    # Write-only. Never echoed back by any response model below.
    credentials_json: Optional[dict[str, Any]] = None
    is_active: bool = True


class IntegrationUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    type: Optional[str] = Field(None, min_length=1, max_length=50)
    act_as_user_id: Optional[str] = None
    config_json: Optional[dict[str, Any]] = None
    # Blank means "keep existing", never "clear" (AC-AC-07). A PATCH that
    # silently wiped credentials because a form posted an empty field would be
    # indistinguishable from an outage.
    credentials_json: Optional[dict[str, Any]] = None
    is_active: Optional[bool] = None


class IntegrationKeyResponse(BaseModel):
    """A key's metadata. Deliberately carries no hash and no plaintext."""

    id: str
    key_prefix: str
    expires_at: Optional[datetime] = None
    revoked_at: Optional[datetime] = None
    rotated_from_id: Optional[str] = None
    last_used_at: Optional[datetime] = None
    created_at: datetime
    # Derived so the UI does not re-implement the expiry rule and drift from
    # what the authentication path actually enforces.
    is_active: bool

    class Config:
        from_attributes = True


class IntegrationResponse(BaseModel):
    id: str
    name: str
    type: str
    status: str
    act_as_user_id: Optional[str] = None
    act_as_user_name: Optional[str] = None
    config_json: Optional[dict[str, Any]] = None
    # Whether credentials are set -- NOT what they are. An operator needs to
    # know a credential exists without the API ever transmitting it.
    has_credentials: bool = False
    is_active: bool
    last_used_at: Optional[datetime] = None
    last_error: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    keys: list[IntegrationKeyResponse] = []

    class Config:
        from_attributes = True


class IssuedKeyResponse(BaseModel):
    """The one and only time a plaintext key is returned.

    Not persisted, not retrievable, not logged. If the operator loses it, the
    remedy is rotation -- there is no recovery path by design.
    """

    key: str
    key_prefix: str
    integration_id: str
    warning: str = "Copy this key now. It cannot be retrieved again."


class RotateKeyRequest(BaseModel):
    grace_days: int = Field(
        7,
        ge=0,
        le=90,
        description=(
            "Days the superseded key keeps working. 0 kills it immediately -- "
            "appropriate for a leaked key, disruptive otherwise."
        ),
    )
