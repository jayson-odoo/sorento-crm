"""User management API routes."""
from fastapi import APIRouter
from app.api.v1.user_management import users, roles, permissions, access_agents, contacts, system_logs, settings, teams, quick_access

router = APIRouter()

router.include_router(users.router, prefix="/users", tags=["users"])
router.include_router(roles.router, prefix="/roles", tags=["roles"])
router.include_router(permissions.router, prefix="/permissions", tags=["permissions"])
router.include_router(access_agents.router, prefix="/access-agents", tags=["access-agents"])
router.include_router(teams.router, prefix="/teams", tags=["teams"])
router.include_router(contacts.router, prefix="/contacts", tags=["contacts"])
router.include_router(system_logs.router, prefix="/system-logs", tags=["system-logs"])
router.include_router(settings.router, prefix="/settings", tags=["settings"])
router.include_router(quick_access.router, prefix="/quick-access", tags=["quick-access"])
# Contact access agents list is at /access-agents/contact-access