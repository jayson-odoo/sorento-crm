"""Test endpoint to debug authentication."""
from fastapi import APIRouter, Depends, Request
from app.dependencies import get_current_user

router = APIRouter()


@router.get("/test-auth")
def test_auth(
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    """Test endpoint to verify authentication is working."""
    return {
        "authenticated": True,
        "user": current_user,
        "headers": {
            "authorization": request.headers.get("authorization", "not present"),
        }
    }
