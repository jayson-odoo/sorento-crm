"""Resolve the grace window for one (form type, stage) pair.

Per-stage `form_sla_configs.grace_seconds` wins; NULL falls back to the global
`system_settings.form_sla_grace_seconds`, which ships as 0. So deploying this feature
changes nothing until a stage is explicitly turned on.
"""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

DEFAULT_GRACE_SECONDS = 0


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
