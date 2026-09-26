"""Chatbot stock ask v2, S1 - resolution rule for X (chatbot_max_qty) and Y
(chatbot_eta_offset_days), plus the edit-permission guard the category and product
PUT routes share.

`effective()` is pure, core: no database access, no import of `app.models`. The
product's own value wins when set; otherwise the product's OWN category's value;
otherwise 0. Zero is a real, explicitly-set value and is never treated as "unset"
(R2). No parent-category walk, ever (R2, owner ruling R12) - the function takes
exactly one category, so a grandparent's value can never reach it.

`guard_chatbot_limits_edit()` is the impure half: it reads `master_data.
chatbot_stock_limits.edit` off the caller and raises only when the request body
actually CHANGES one of the two fields (S1 backend seam: "the unchanged value passes
so the ordinary form keeps saving").
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from sqlalchemy.orm import Session

from app.services.error_handler import AppException
from app.services.user_service import UserPermissionService

EDIT_PERMISSION = "master_data.chatbot_stock_limits.edit"
_FIELDS = ("chatbot_max_qty", "chatbot_eta_offset_days")

# Should fix 1 (reviewer pass, PR #1221, 85c2e9e7): the baseline a CREATE route
# guards against - a brand-new row has no stored X/Y yet, so any value the create
# body carries is a change from NULL and must clear the same permission a PUT
# would need to set it.
NULL_LIMITS = SimpleNamespace(chatbot_max_qty=None, chatbot_eta_offset_days=None)


def _resolve(product_value: int | None, category_value: int | None) -> int:
    if product_value is not None:
        return product_value
    if category_value is not None:
        return category_value
    return 0


def effective(product: Any, category: Any) -> tuple[int, int]:
    """`(max_qty, eta_offset_days)` for one product against its own category."""
    max_qty = _resolve(product.chatbot_max_qty, category.chatbot_max_qty)
    eta_offset_days = _resolve(product.chatbot_eta_offset_days, category.chatbot_eta_offset_days)
    return max_qty, eta_offset_days


def guard_chatbot_limits_edit(db: Session, user_id: str, current: Any, update_data: dict) -> None:
    """Raise 403 iff `update_data` changes `chatbot_max_qty` or
    `chatbot_eta_offset_days` from `current`'s stored value and the caller lacks
    `master_data.chatbot_stock_limits.edit`. Fields the request never mentions, or
    sends back unchanged, never trigger this - an ordinary category/product save
    must keep working for someone who never touches X/Y."""
    changed = any(
        field in update_data and update_data[field] != getattr(current, field, None)
        for field in _FIELDS
    )
    if not changed:
        return
    if not UserPermissionService(db).check_user_has_permission(user_id, EDIT_PERMISSION):
        raise AppException(
            status_code=403,
            message=f"Permission required: {EDIT_PERMISSION}",
        )
