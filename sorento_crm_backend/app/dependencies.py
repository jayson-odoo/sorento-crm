"""Shared dependencies for FastAPI routes."""
from fastapi import Depends, HTTPException, status, Request, Header
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from jose import JWTError, jwt
from typing import Optional
from app.database import get_db
from app.config import settings

# OAuth2 scheme for JWT token extraction
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token", auto_error=False)


def extract_token_from_request(request: Request) -> Optional[str]:
    """Extract JWT token from Authorization header or cookies."""
    # Try Authorization header first
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header.split(" ")[1]
    
    # Try cookies (NextAuth stores encrypted session in cookies, not raw JWT)
    # For now, we'll need to decode the session cookie or use a different approach
    # NextAuth cookie names: 'next-auth.session-token' or '__Secure-next-auth.session-token'
    # Note: NextAuth session cookies are encrypted, so we can't directly extract JWT
    # The frontend should send JWT in Authorization header instead
    # For cookie-based auth, we'll need to implement session validation differently
    return None


async def get_current_user(
    request: Request,
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> dict:
    """
    Validate JWT token from NextAuth and return user information.
    
    This dependency extracts and validates the JWT token created by NextAuth.
    The token can be sent in:
    1. Authorization header as: Bearer <token>
    2. Cookies (next-auth.session-token or __Secure-next-auth.session-token)
    """
    import logging
    logger = logging.getLogger(__name__)
    
    # Try to get token from request if not in header
    if not token:
        token = extract_token_from_request(request)
    
    # Debug logging
    auth_header = request.headers.get("Authorization")
    logger.debug(f"Authorization header present: {auth_header is not None}")
    logger.debug(f"Token extracted: {token is not None}")
    if token:
        logger.debug(f"Token length: {len(token)}, first 20 chars: {token[:20]}...")
    
    if not token:
        logger.warning(f"No token found. Headers: {dict(request.headers)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    try:
        # Decode and validate JWT token
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm]
        )
        
        # Extract user information from token
        # NextAuth uses 'sub' for subject (user ID) or 'id' directly
        user_id: str = payload.get("sub") or payload.get("id")
        email: str = payload.get("email")
        role_id: str = payload.get("roleId")
        
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: missing user ID"
            )
        
        user = {
            "id": user_id,
            "email": email,
            "role_id": role_id,
            "name": payload.get("name"),
            "avatar": payload.get("avatar"),
            "status": payload.get("status"),
            "role_name": payload.get("roleName"),
        }
        from app.audit_context import set_audit_context
        ip = request.client.host if request.client else None
        set_audit_context(user_id, ip)
        return user
    except JWTError as e:
        # Log the error for debugging
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"JWT validation failed: {str(e)}")
        logger.error(f"Token (first 50 chars): {token[:50] if token else 'None'}...")
        logger.error(f"JWT Secret configured: {bool(settings.jwt_secret)}")
        logger.error(f"JWT Secret length: {len(settings.jwt_secret) if settings.jwt_secret else 0}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {str(e)}"
        )
    except Exception as e:
        # Catch any other errors
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Unexpected error in JWT validation: {str(e)}")
        logger.error(f"Error type: {type(e).__name__}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Authentication error: {str(e)}"
        )


async def get_api_key(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key")
) -> Optional[str]:
    """Extract API key from X-API-Key header."""
    return x_api_key


async def get_external_api_user(
    api_key: Optional[str] = Depends(get_api_key),
) -> dict:
    """Validate external API key and return system user dict."""
    import logging
    logger = logging.getLogger(__name__)

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key is required",
        )

    valid_api_key = getattr(settings, 'external_api_key', None)
    if not valid_api_key:
        logger.warning("API key provided but EXTERNAL_API_KEY not configured")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key authentication not configured",
        )

    if api_key != valid_api_key:
        logger.warning("Invalid API key provided")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )

    return {
        "id": "system",
        "email": "api@system",
        "role_id": "system",
        "name": "API User",
        "avatar": None,
        "status": "ACTIVE",
        "role_name": "API",
    }


async def get_current_user_or_api_key(
    request: Request,
    token: Optional[str] = Depends(oauth2_scheme),
    api_key: Optional[str] = Depends(get_api_key),
    db: Session = Depends(get_db)
) -> dict:
    """
    Validate either JWT token (from NextAuth) or API key and return user information.
    
    This dependency allows both authenticated users and external API key access.
    """
    import logging
    logger = logging.getLogger(__name__)
    
    # If API key is provided, validate it
    if api_key:
        # Validate API key against environment variable
        valid_api_key = getattr(settings, 'external_api_key', None)
        if not valid_api_key:
            logger.warning("API key provided but EXTERNAL_API_KEY not configured")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="API key authentication not configured"
            )
        
        if api_key != valid_api_key:
            logger.warning(f"Invalid API key provided")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key"
            )
        
        # Return a system user dict for API key access
        user = {
            "id": "system",
            "email": "api@system",
            "role_id": "system",
            "name": "API User",
            "avatar": None,
            "status": "ACTIVE",
            "role_name": "API",
        }
        from app.audit_context import set_audit_context
        ip = request.client.host if request.client else None
        set_audit_context(user["id"], ip)
        return user

    # Otherwise, try JWT token authentication
    if not token:
        token = extract_token_from_request(request)
    
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Provide either Bearer token or X-API-Key header.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm]
        )
        
        user_id: str = payload.get("sub") or payload.get("id")
        email: str = payload.get("email")
        role_id: str = payload.get("roleId")
        
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: missing user ID"
            )
        
        user = {
            "id": user_id,
            "email": email,
            "role_id": role_id,
            "name": payload.get("name"),
            "avatar": payload.get("avatar"),
            "status": payload.get("status"),
            "role_name": payload.get("roleName"),
        }
        from app.audit_context import set_audit_context
        ip = request.client.host if request.client else None
        set_audit_context(user_id, ip)
        return user
    except JWTError as e:
        logger.error(f"JWT validation failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Unexpected error in authentication: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Authentication error: {str(e)}"
        )