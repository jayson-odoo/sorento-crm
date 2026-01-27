"""Authentication API routes."""
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
import bcrypt
import secrets
import hashlib
from datetime import datetime, timezone, timedelta

from app.database import get_db
from app.models.user import User, UserRole
from app.models.auth import VerificationToken
from app.schemas.auth import (
    LoginRequest, LoginResponse, SignupRequest, SignupResponse,
    ResetPasswordRequest, ResetPasswordResponse,
    ChangePasswordRequest, ChangePasswordResponse,
    VerifyEmailRequest, VerifyEmailResponse
)
from app.services.error_handler import handle_internal_error


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

    # Update last sign-in timestamp
    user.last_sign_in_at = datetime.now(timezone.utc)
    db.add(user)
    db.commit()

    role_name: str | None = None
    role: UserRole | None = db.query(UserRole).filter(UserRole.id == user.role_id).first()
    if role:
        role_name = role.name

    return LoginResponse(
        id=user.id,
        email=user.email,
        name=user.name,
        avatar=user.avatar,
        status=user.status,
        role_id=user.role_id,
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
        
        # Create user
        user = User(
            email=payload.email,
            password=hashed_password,
            name=payload.name,
            role_id=default_role.id,
            status="INACTIVE"
        )
        db.add(user)
        db.flush()
        
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
        
        # Don't reveal if user exists
        if not user:
            return ResetPasswordResponse(
                message="If an account with that email exists, a password reset link has been sent."
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
        
        # TODO: Send password reset email
        
        return ResetPasswordResponse(
            message="If an account with that email exists, a password reset link has been sent."
        )
    except Exception as e:
        raise handle_internal_error(str(e))


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
        
        if not verification_token or verification_token.expires < datetime.now(timezone.utc):
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
        
        # Update password
        user.password = hashed_password
        db.add(user)
        
        # Delete used token
        db.delete(verification_token)
        db.commit()
        
        # TODO: Send confirmation email
        
        return ChangePasswordResponse(message="Password reset successful.")
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
        
        if not verification_token or verification_token.expires < datetime.now(timezone.utc):
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
        user.email_verified_at = datetime.now(timezone.utc)
        db.add(user)
        
        # Delete used token
        db.delete(verification_token)
        db.commit()
        
        return VerifyEmailResponse(message="Email verified successfully!")
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))
