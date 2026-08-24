from pydantic import BaseModel, EmailStr
from typing import Optional


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    # "Remember me": True → 30-day rolling session; False → 8h, no slide.
    remember_me: bool = False


class LoginResponse(BaseModel):
    # Opaque staff session token - the FE stores it in the NextAuth cookie and
    # sends it as `Authorization: Bearer <token>` to every /api/v1/* call.
    token: str
    id: str
    email: EmailStr
    name: str | None = None
    avatar: str | None = None
    status: str
    role_id: str
    role_name: str | None = None
    role_ids: list[str] = []


class SignupRequest(BaseModel):
    email: EmailStr
    password: str
    name: str


class SignupResponse(BaseModel):
    id: str
    email: EmailStr
    name: str
    message: str


class ResetPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordResponse(BaseModel):
    message: str


class ChangePasswordRequest(BaseModel):
    token: str
    new_password: str


class ChangePasswordResponse(BaseModel):
    message: str


class VerifyEmailRequest(BaseModel):
    token: str


class VerifyEmailResponse(BaseModel):
    message: str


class VerifyResetTokenRequest(BaseModel):
    token: str


class VerifyResetTokenResponse(BaseModel):
    valid: bool = True
    email: str | None = None  # optional masked email for display


class SessionInfo(BaseModel):
    """One active staff session for the "your devices" UI. No raw token/UUID shown."""
    id: str
    device_label: str
    ip_address: str | None = None
    last_seen_at: str | None = None
    created_at: str | None = None
    current: bool = False


class MessageResponse(BaseModel):
    message: str
    count: int | None = None

