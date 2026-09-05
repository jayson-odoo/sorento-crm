"""Test endpoint to debug authentication."""
from fastapi import APIRouter, Depends, Request
from app.dependencies import get_current_user

router = APIRouter()


@router.get("/test-auth")
async def test_auth(
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    """Test endpoint to verify authentication is working.

    The Authorization header is reported as PRESENT or ABSENT, never echoed. What this
    endpoint is asked is "did my credential arrive?", and the answer to that is a bool;
    returning the bearer token itself put a live credential in a response body (and in
    anything that logs one) for no extra diagnostic value. Found by the AC-806 widening
    of the header-masking guardrail, which now scans for this shape too.
    """
    return {
        "authenticated": True,
        "user": current_user,
        "headers": {
            "authorization": "present" if request.headers.get("authorization") else "not present",
        }
    }
