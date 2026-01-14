"""User management API routes."""
from fastapi import APIRouter
from app.api.v1.user_management import users, roles, permissions, access_agents

router = APIRouter()

router.include_router(users.router, prefix="/users", tags=["users"])
router.include_router(roles.router, prefix="/roles", tags=["roles"])
router.include_router(permissions.router, prefix="/permissions", tags=["permissions"])
router.include_router(access_agents.router, prefix="/access-agents", tags=["access-agents"])
