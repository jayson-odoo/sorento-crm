"""Resolve the grace window an action waits out.

Two callers, two policies:

* A FORM action asks `grace_seconds_for`. Per-stage `form_sla_configs.grace_seconds`
  wins; NULL falls back to the global `system_settings.form_sla_grace_seconds`, which
  ships as 0. So deploying that feature changed nothing until a stage was turned on.
* A RECORD action asks `record_action_window_seconds` (D7, S6). There is no per-stage
  layer - a product has no SLA stage - so the window comes from the action's own class:
  destructive (a hard delete, 10s) or reversible (a status change, 5s), each a
  `system_settings` column an admin tunes in System Settings > General (D16).
"""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

DEFAULT_GRACE_SECONDS = 0

# The two windows the deferred-action model runs on (D7). Ten seconds to catch a
# delete, five for something that can simply be set back.
WINDOW_DESTRUCTIVE = "destructive"
WINDOW_REVERSIBLE = "reversible"
DEFAULT_DESTRUCTIVE_WINDOW_SECONDS = 10
DEFAULT_REVERSIBLE_WINDOW_SECONDS = 5
_WINDOW_SETTING = {
    WINDOW_DESTRUCTIVE: ("deferred_delete_seconds", DEFAULT_DESTRUCTIVE_WINDOW_SECONDS),
    WINDOW_REVERSIBLE: ("deferred_action_seconds", DEFAULT_REVERSIBLE_WINDOW_SECONDS),
}


def _coerce(value) -> Optional[int]:
    try:
        seconds = int(value)
    except (TypeError, ValueError):
        return None
    return max(0, seconds)


def global_grace_seconds(db: Session) -> int:
    from app.models.user import SystemSetting

    # system_settings is a singleton, but `.first()` has no ORDER BY - a stray second
    # row would make this non-deterministic, so read the column defensively.
    row = db.query(SystemSetting).first()
    if row is None:
        return DEFAULT_GRACE_SECONDS
    return _coerce(getattr(row, "form_sla_grace_seconds", None)) or DEFAULT_GRACE_SECONDS


def window_class_for(action) -> str:
    """Destructive or reversible, for one registered action.

    The action may declare it; when it does not, the VERB decides. A key ending in
    `.delete` that forgot to declare its class would otherwise silently get the short
    window, and a five-second delete is the one mistake this model cannot afford.
    """
    declared = getattr(action, "window", None)
    if declared in _WINDOW_SETTING:
        return declared
    return (
        WINDOW_DESTRUCTIVE
        if str(getattr(action, "key", "")).endswith(".delete")
        else WINDOW_REVERSIBLE
    )


def record_action_window_seconds(db: Session, action) -> int:
    """How long this record action waits before the server applies it (S6-04)."""
    from app.models.user import SystemSetting

    column, default = _WINDOW_SETTING[window_class_for(action)]
    # Singleton table, but `.first()` has no ORDER BY - read the column defensively,
    # exactly as the form-SLA window above does.
    row = db.query(SystemSetting).first()
    if row is None:
        return default
    # A stored 0 would apply the action with no way back, which is the confirmation
    # dialog's failure mode in the new model's clothes. The settings schema refuses to
    # save it; this refuses to honour it if one is already in the column.
    return _coerce(getattr(row, column, None)) or default


def grace_seconds_for(
    db: Session,
    source_entity_type: str,
    *,
    event_name: Optional[str] = None,
) -> int:
    """Grace for the stage this event would resolve.

    A form type can carry several stages; the one that matters is the stage whose
    `resolve_event` lists this event, because that is the stage the click closes.
    Falls back to the global default when no stage sets its own.
    """
    from app.models.sla import FormSLAConfig

    try:
        configs = (
            db.query(FormSLAConfig)
            .filter(
                FormSLAConfig.source_entity_type == source_entity_type,
                FormSLAConfig.is_active.is_(True),
            )
            .all()
        )
    except Exception as exc:
        # Never let a config read block the underlying action - worst case we do not
        # defer, which is exactly today's behaviour.
        logger.warning("Grace lookup failed for %s: %s", source_entity_type, exc)
        return DEFAULT_GRACE_SECONDS

    for config in configs:
        if event_name:
            events = {
                token.strip()
                for token in str(getattr(config, "resolve_event", "") or "").split(",")
                if token.strip()
            }
            if event_name not in events:
                continue
        seconds = _coerce(getattr(config, "grace_seconds", None))
        if seconds is not None:
            return seconds

    return global_grace_seconds(db)
