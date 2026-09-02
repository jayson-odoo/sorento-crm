"""User management API routes."""
from fastapi import APIRouter
from app.api.v1.user_management import users, roles, permissions, access_agents, contacts, contact_access_types, contact_media_access, contact_portal_forms, market_segments, system_logs, settings, teams, quick_access, impersonation, contact_impersonation, onboarding

router = APIRouter()

router.include_router(users.router, prefix="/users", tags=["users"])
router.include_router(onboarding.router, prefix="/onboarding", tags=["onboarding"])
router.include_router(contact_access_types.router, prefix="/contact-access-types", tags=["contact-access-types"])
router.include_router(market_segments.router, prefix="/market-segments", tags=["market-segments"])
router.include_router(roles.router, prefix="/roles", tags=["roles"])
router.include_router(permissions.router, prefix="/permissions", tags=["permissions"])
router.include_router(access_agents.router, prefix="/access-agents", tags=["access-agents"])
router.include_router(teams.router, prefix="/teams", tags=["teams"])
router.include_router(contacts.router, prefix="/contacts", tags=["contacts"])
# Chatbot media access lives on its own router under the same prefix: it is a
# separate concern with a separate permission, and contacts.py is already long.
router.include_router(contact_media_access.router, prefix="/contacts", tags=["contacts"])
# Portal form override lives on its own router for the same reason: separate
# concern, separate permission split (view vs edit), contacts.py stays lean.
router.include_router(contact_portal_forms.router, prefix="/contacts", tags=["contacts"])
router.include_router(system_logs.router, prefix="/system-logs", tags=["system-logs"])
router.include_router(settings.router, prefix="/settings", tags=["settings"])
router.include_router(quick_access.router, prefix="/quick-access", tags=["quick-access"])
router.include_router(impersonation.router, prefix="/impersonation", tags=["impersonation"])
router.include_router(contact_impersonation.router, prefix="/contact-impersonation", tags=["contact-impersonation"])
# Contact access agents list is at /access-agents/contact-access