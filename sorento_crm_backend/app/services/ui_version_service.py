"""UI v2 version switch (UI-V2 phase 0, UAC B-1..B-5).

One helper feeds the four ui fields to every hand-built user dict (`GET /me`, `get_user`,
`PUT /me/profile`), so the three builders cannot drift.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.user import SystemSetting, UserPermission, UserRolePermission
from app.services.user_service import UserPermissionService

PREVIEW_SLUG = "ui.v2.preview"
THEME_MODES = ("light", "dark", "system")


def kill_switch_on(db: Session) -> bool:
    """True while the company allows v2 (default true, also when no settings row exists)."""
    settings = db.query(SystemSetting).first()
    return bool(getattr(settings, "ui_v2_enabled", True)) if settings else True


def v2_available(db: Session, user) -> bool:
    """The user holds `ui.v2.preview` AND the company kill switch is on.

    The preview is for the owner alone (UAC journey step 1), so the admin/superadmin shortcut of
    `check_user_has_permission` does not open it: an admin needs the slug granted to a role too.
    """
    if not kill_switch_on(db):
        return False
    svc = UserPermissionService(db)
    uid = str(user.id)
    if svc.get_user_role_slugs(uid) & {svc.SUPERADMIN_ROLE_SLUG, "admin"}:
        role_ids = svc.get_user_role_ids(uid)
        return bool(role_ids) and (
            db.query(UserPermission.id)
            .join(UserRolePermission, UserRolePermission.permission_id == UserPermission.id)
            .filter(UserRolePermission.role_id.in_(role_ids), UserPermission.slug == PREVIEW_SLUG)
            .first()
            is not None
        )
    return svc.check_user_has_permission(uid, PREVIEW_SLUG)


def ui_version_fields(db: Session, user) -> dict:
    stored = getattr(user, "ui_version", None) or "v1"
    available = v2_available(db, user)
    return {
        "ui_version": "v2" if (available and stored == "v2") else "v1",
        "ui_version_stored": stored,
        "ui_v2_available": available,
        "theme_mode": getattr(user, "theme_mode", None) or "system",
    }
