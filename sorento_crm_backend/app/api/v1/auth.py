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
)
from app.services.error_handler import handle_internal_error

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> LoginResponse:
    user: User | None = (
        db.query(User)
        .filter(User.email == payload.email)
        .first()
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found. Please register first.",
        )

    if not user.password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials.",
        )

    try:
        ok = bcrypt.checkpw(payload.password.encode("utf-8"), user.password.encode("utf-8"))
    except Exception:
        ok = False

    if not ok:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials.",
        )

    if user.status != "ACTIVE":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account not activated. Please verify your email.",
        )

    # Store naive UTC (DB columns are timezone=False)
    user.last_sign_in_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.add(user)
    db.commit()

    from app.models.user import UserRoleAssignment
    first_assignment = db.query(UserRoleAssignment).filter(UserRoleAssignment.user_id == user.id).first()
    role_id: str | None = first_assignment.role_id if first_assignment else None
    role: UserRole | None = db.query(UserRole).filter(UserRole.id == role_id).first() if role_id else None
    role_name = role.name if role else None

    return LoginResponse(
        id=user.id,
        email=user.email,
        name=user.name,
        avatar=user.avatar,
        status=user.status,
        role_id=role_id,
        role_name=role_name,
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
        default_role = db.query(UserRole).filter(UserRole.is_default == True).first()
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
        db.add(UserRoleAssignment(user_id=user.id, role_id=default_role.id))
        
        # Create verification token
        token = hashlib.sha256(f"{user.id}{datetime.now(timezone.utc).isoformat()}".encode()).hexdigest()
        verification_token = VerificationToken(
            identifier=user.id,
            token=token,
            expires=datetime.now(timezone.utc) + timedelta(hours=1)
        )
        db.add(verification_token)
        db.commit()
        db.refresh(user)
        
        # TODO: Send verification email (can be done via integration service)
        
        return SignupResponse(
            id=user.id,
            email=user.email,
            name=user.name,
            message="User registered successfully. Please check your email to verify your account."
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
            identifier=user.id,
            token=token,
            expires=datetime.now(timezone.utc) + timedelta(hours=1)
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
            from app.services.notification_email import send_notification_email, _smtp_config_from_settings
            sys_settings = db.query(SystemSetting).first()
            smtp_config = _smtp_config_from_settings(sys_settings) if sys_settings else None
            err = send_notification_email(
                to=user.email,
                subject=subject,
                body_text=body_text,
                body_html=body_html,
                smtp_config=smtp_config,
                from_name="Sorento AI System",
            )
            if err:
                logger.warning("Password reset email failed for %s: %s", user.email, err)
        except Exception as e:
            logger.warning("Password reset email error: %s", e)

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
    if not verification_token or verification_token.expires < now_utc_naive:
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
    parts = user.email.split("@")
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
        if not verification_token or verification_token.expires < now_utc_naive:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired token."
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
        user.password = hashed_password
        user.status = "ACTIVE"
        # Accepting invite / reset link proves they received the email, so mark verified
        # Store naive UTC (DB columns are timezone=False)
        user.email_verified_at = datetime.now(timezone.utc).replace(tzinfo=None)
        db.add(user)
        
        # Delete used token
        db.delete(verification_token)
        db.commit()
        
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
        if not verification_token or verification_token.expires < now_utc_naive:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired token"
            )
        
        # Update user
        user = db.query(User).filter(User.id == verification_token.identifier).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        user.status = "ACTIVE"
        # Store naive UTC (DB columns are timezone=False)
        user.email_verified_at = datetime.now(timezone.utc).replace(tzinfo=None)
        db.add(user)
        
        # Delete used token
        db.delete(verification_token)
        db.commit()
        
        return VerifyEmailResponse(message="Email verified successfully!")
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))
