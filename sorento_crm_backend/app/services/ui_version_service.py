"""UI v2 version switch (UI-V2 phase 0, UAC B-1..B-5).

One helper feeds the four ui fields to every hand-built user dict (`GET /me`, `get_user`,
`PUT /me/profile`), so the three builders cannot drift.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.user import SystemSetting
from app.services.user_service import UserPermissionService

PREVIEW_SLUG = "ui.v2.preview"
THEME_MODES = ("light", "dark", "system")


def kill_switch_on(db: Session) -> bool:
    """True while the company allows v2 (default true, also when no settings row exists)."""
    settings = db.query(SystemSetting).first()
    return bool(getattr(settings, "ui_v2_enabled", True)) if settings else True


def v2_available(db: Session, user) -> bool:
    """The user holds `ui.v2.preview` AND the company kill switch is on."""
    if not kill_switch_on(db):
        return False
    return UserPermissionService(db).check_user_has_permission(str(user.id), PREVIEW_SLUG)


def ui_version_fields(db: Session, user) -> dict:
    stored = getattr(user, "ui_version", None) or "v1"
    available = v2_available(db, user)
    return {
        "ui_version": "v2" if (available and stored == "v2") else "v1",
        "ui_version_stored": stored,
        "ui_v2_available": available,
        "theme_mode": getattr(user, "theme_mode", None) or "system",
    }
