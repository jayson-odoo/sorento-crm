"""Authentication API routes."""
import logging
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
import bcrypt
import secrets
import hashlib
from datetime import datetime, timezone, timedelta

from app.config import settings as app_settings
from app.database import get_db
from app.models.user import User, UserRole, SystemSetting
from app.models.auth import VerificationToken
from app.schemas.auth import (
    LoginRequest, LoginResponse, SignupRequest, SignupResponse,
    ResetPasswordRequest, ResetPasswordResponse,
    ChangePasswordRequest, ChangePasswordResponse,
    VerifyEmailRequest, VerifyEmailResponse,
    VerifyResetTokenRequest, VerifyResetTokenResponse,
    SessionInfo, MessageResponse,
)
from app.dependencies import get_current_user
from app.services import user_session_service
from app.services.error_handler import handle_internal_error

logger = logging.getLogger(__name__)
router = APIRouter()


def _verification_token_expired(token_row: VerificationToken, now_naive: datetime) -> bool:
    exp = getattr(token_row, "expires", None)
    if not isinstance(exp, datetime):
        return True
    return exp < now_naive


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)) -> LoginResponse:
    from app.services import login_throttle
    from app.services.user_session_service import mint_session

    ip = request.client.host if request.client else None

    # Brute-force throttle (per email+ip). Fails open if Redis is down.
    gate = login_throttle.check(payload.email, ip)
    if not gate.allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed attempts. Please try again later.",
            headers={"Retry-After": str(gate.retry_after_seconds or login_throttle.LOCK_WINDOW_SECONDS)},
        )

    user: User | None = (
        db.query(User)
        .filter(User.email == payload.email)
        .first()
    )

    if not user:
        # Count a miss too — don't let attackers probe emails for free.
        login_throttle.record_failure(payload.email, ip)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found. Please register first.",
        )

    pw_raw = getattr(user, "password", None)
    if pw_raw is None or str(pw_raw).strip() == "":
        login_throttle.record_failure(payload.email, ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials.",
        )

    try:
        ok = bcrypt.checkpw(
            payload.password.encode("utf-8"),
            str(pw_raw).encode("utf-8"),
        )
    except Exception:
        ok = False

    if not ok:
        login_throttle.record_failure(payload.email, ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials.",
        )

    if str(getattr(user, "status", "") or "") != "ACTIVE":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account not activated. Please verify your email.",
        )

    # Successful auth — clear the throttle counter.
    login_throttle.clear(payload.email, ip)

    # Store naive UTC (DB columns are timezone=False)
    setattr(user, "last_sign_in_at", datetime.now(timezone.utc).replace(tzinfo=None))
    db.add(user)
    db.commit()

    from app.models.user import UserRoleAssignment

    uid = str(getattr(user, "id", "") or "")
    assignments = (
        db.query(UserRoleAssignment)
        .filter(UserRoleAssignment.user_id == uid)
        .order_by(UserRoleAssignment.assigned_at.asc())
        .all()
    )
    role_ids = [str(a.role_id) for a in assignments if getattr(a, "role_id", None) is not None]
    role_id: str | None = role_ids[0] if role_ids else None
    role: UserRole | None = (
        db.query(UserRole).filter(UserRole.id == role_id).first() if role_id else None
    )
    role_name = str(getattr(role, "name", "") or "") if role is not None else None

    # Mint the opaque rolling session (30d if remember_me, else 8h).
    session_row = mint_session(
        db,
        uid,
        remember=bool(payload.remember_me),
        user_agent=request.headers.get("user-agent"),
        ip_address=ip,
    )

    return LoginResponse(
        token=str(session_row.token),
        id=uid,
        email=str(getattr(user, "email", "") or ""),
        name=str(getattr(user, "name", "") or "") or None,
        avatar=str(getattr(user, "avatar", "") or "") or None,
        status=str(getattr(user, "status", "") or ""),
        role_id=role_id if role_id is not None else "",
        role_name=role_name,
        role_ids=role_ids,
    )


@router.post("/signup", response_model=SignupResponse, status_code=status.HTTP_201_CREATED)
async def signup(
    payload: SignupRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """Register a new user."""
    try:
        # Check if user exists
        existing = db.query(User).filter(User.email == payload.email).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email is already registered."
            )
        
        # Get default role
        default_role = db.query(UserRole).filter(UserRole.is_default.is_(True)).first()
        if not default_role:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Default role not found."
            )
        
        # Hash password
        hashed_password = bcrypt.hashpw(payload.password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        
        from app.models.user import UserRoleAssignment
        user = User(
            email=payload.email,
            password=hashed_password,
            name=payload.name,
            status="INACTIVE"
        )
        db.add(user)
        db.flush()
        db.add(
            UserRoleAssignment(
                user_id=str(getattr(user, "id", "") or ""),
                role_id=str(getattr(default_role, "id", "") or ""),
            )
        )
        
        # Create verification token
        uid = str(getattr(user, "id", "") or "")
        token = hashlib.sha256(f"{uid}{datetime.now(timezone.utc).isoformat()}".encode()).hexdigest()
        verification_token = VerificationToken(
            identifier=uid,
            token=token,
            expires=datetime.now(timezone.utc) + timedelta(hours=1)
        )
        db.add(verification_token)
        db.commit()
        db.refresh(user)
        
        # TODO: Send verification email (can be done via integration service)
        
        return SignupResponse(
            id=str(getattr(user, "id", "") or ""),
            email=str(getattr(user, "email", "") or ""),
            name=str(getattr(user, "name", "") or ""),
            message="User registered successfully. Please check your email to verify your account.",
        )
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/reset-password", response_model=ResetPasswordResponse)
async def reset_password(
    payload: ResetPasswordRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """Request password reset."""
    try:
        user = db.query(User).filter(User.email == payload.email).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No account found with this email address.",
            )
        
        # Generate reset token
        token = secrets.token_urlsafe(32)
        
        # Create verification token
        verification_token = VerificationToken(
            identifier=str(getattr(user, "id", "") or ""),
            token=token,
            expires=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        db.add(verification_token)
        db.commit()

        # Send password reset email (professional tone, visible URL, system disclaimer)
        base_url = (app_settings.frontend_base_url or "").strip().rstrip("/")
        reset_path = "/change-password"
        reset_link = f"{base_url}{reset_path}?token={token}" if base_url else f"{reset_path}?token={token}"
        subject = "Reset your password"
        body_text = (
            "Hello,\n\n"
            "You have requested a password reset for your Sorento account. Use the link below to set a new password. This link is valid for 1 hour.\n\n"
            f"{reset_link}\n\n"
            "If you did not request this, you can safely ignore this email.\n\n"
            "This is a system-generated email. Please do not reply."
        )
        # Show the raw URL as visible, clickable link (no hidden "Click here") to reduce phishing concern
        body_html = (
            "<p>Hello,</p>\n"
            "<p>You have requested a password reset for your Sorento account. Use the link below to set a new password. This link is valid for 1 hour.</p>\n"
            f'<p><a href="{reset_link}">{reset_link}</a></p>\n'
            "<p>If you did not request this, you can safely ignore this email.</p>\n"
            "<p><em>This is a system-generated email. Please do not reply.</em></p>"
        )
        try:
            from app.services.email_outbox_service import enqueue as enqueue_email

            user_email = str(getattr(user, "email", "") or "")
            enqueue_email(
                db,
                event_key="password_reset",
                to=user_email,
                subject=subject,
                body_text=body_text,
                body_html=body_html,
                from_name="Sorento AI System",
                metadata={"user_id": str(getattr(user, "id", "") or "")},
            )
            db.commit()
        except Exception as e:
            logger.warning("Password reset email enqueue failed: %s", e)

        return ResetPasswordResponse(
            message="A password reset link has been sent to your email."
        )
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/verify-reset-token", response_model=VerifyResetTokenResponse)
async def verify_reset_token(
    payload: VerifyResetTokenRequest,
    db: Session = Depends(get_db)
):
    """Validate a reset/invitation token without consuming it. Used by the change-password page."""
    verification_token = db.query(VerificationToken).filter(
        VerificationToken.token == payload.token
    ).first()
    now_utc_naive = datetime.now(timezone.utc).replace(tzinfo=None)
    if verification_token is None or _verification_token_expired(verification_token, now_utc_naive):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired token.",
        )
    user = db.query(User).filter(User.id == verification_token.identifier).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )
    # Optionally return masked email for display (e.g. "j***@example.com")
    parts = str(getattr(user, "email", "") or "").split("@")
    masked = f"{parts[0][:1]}***@{parts[1]}" if len(parts) == 2 and parts[0] else None
    return VerifyResetTokenResponse(valid=True, email=masked)


@router.post("/change-password", response_model=ChangePasswordResponse)
async def change_password(
    payload: ChangePasswordRequest,
    db: Session = Depends(get_db)
):
    """Change password using reset token."""
    try:
        # Validate token
        verification_token = db.query(VerificationToken).filter(
            VerificationToken.token == payload.token
        ).first()
        
        now_utc_naive = datetime.now(timezone.utc).replace(tzinfo=None)
        if verification_token is None or _verification_token_expired(
            verification_token, now_utc_naive
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired token.",
            )
        
        # Get user
        user = db.query(User).filter(User.id == verification_token.identifier).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found."
            )
        
        # Hash new password
        hashed_password = bcrypt.hashpw(payload.new_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

        # Update password and activate account so they can log in (invitation or password reset)
        setattr(user, "password", hashed_password)
        setattr(user, "status", "ACTIVE")
        # Accepting invite / reset link proves they received the email, so mark verified
        # Store naive UTC (DB columns are timezone=False)
        setattr(user, "email_verified_at", datetime.now(timezone.utc).replace(tzinfo=None))
        db.add(user)

        # Delete used token
        db.delete(verification_token)
        db.commit()

        # A password change boots every existing device (stolen-session kill switch).
        from app.services.user_session_service import revoke_all_for_user

        revoke_all_for_user(db, str(getattr(user, "id", "") or ""))

        return ChangePasswordResponse(message="Password set successfully. You can now sign in.")
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/verify-email", response_model=VerifyEmailResponse)
async def verify_email(
    payload: VerifyEmailRequest,
    db: Session = Depends(get_db)
):
    """Verify email using token."""
    try:
        # Validate token
        verification_token = db.query(VerificationToken).filter(
            VerificationToken.token == payload.token
        ).first()
        
        now_utc_naive = datetime.now(timezone.utc).replace(tzinfo=None)
        if verification_token is None or _verification_token_expired(
            verification_token, now_utc_naive
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired token",
            )
        
        # Update user
        user = db.query(User).filter(User.id == verification_token.identifier).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        setattr(user, "status", "ACTIVE")
        # Store naive UTC (DB columns are timezone=False)
        setattr(user, "email_verified_at", datetime.now(timezone.utc).replace(tzinfo=None))
        db.add(user)

        # Delete used token
        db.delete(verification_token)
        db.commit()

        return VerifyEmailResponse(message="Email verified successfully!")
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


def _iso(dt) -> str | None:
    return dt.isoformat() if dt is not None else None


@router.post("/logout", response_model=MessageResponse)
def logout(request: Request, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)) -> MessageResponse:
    """Revoke the current session (the device calling this). Idempotent."""
    session_id = getattr(request.state, "session_id", None)
    if session_id:
        user_session_service.revoke_session(db, session_id=session_id)
    return MessageResponse(message="Logged out.")


@router.get("/sessions", response_model=list[SessionInfo])
def list_sessions(request: Request, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)) -> list[SessionInfo]:
    """Active sessions for the signed-in user — the "your devices" list."""
    current_id = getattr(request.state, "session_id", None)
    rows = user_session_service.list_active_sessions(db, str(current_user["id"]))
    return [
        SessionInfo(
            id=str(r.id),
            device_label=user_session_service.device_label_from_ua(r.user_agent),
            ip_address=r.ip_address,
            last_seen_at=_iso(r.last_seen_at),
            created_at=_iso(r.created_at),
            current=(str(r.id) == str(current_id)),
        )
        for r in rows
    ]


@router.delete("/sessions/{session_id}", response_model=MessageResponse)
def revoke_one_session(session_id: str, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)) -> MessageResponse:
    """Revoke a single session — only if it belongs to the signed-in user."""
    from app.models.user_session import UserSession

    row = (
        db.query(UserSession)
        .filter(UserSession.id == session_id, UserSession.user_id == str(current_user["id"]))
        .first()
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")
    user_session_service.revoke_session(db, session_id=session_id)
    return MessageResponse(message="Device signed out.")


@router.post("/sessions/revoke-others", response_model=MessageResponse)
def revoke_other_sessions(request: Request, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)) -> MessageResponse:
    """Log out every other device, keeping the current session alive."""
    current_id = getattr(request.state, "session_id", None)
    count = user_session_service.revoke_all_for_user(
        db, str(current_user["id"]), except_session_id=str(current_id) if current_id else None
    )
    return MessageResponse(message="Signed out other devices.", count=count)
