"""System log service for audit trail."""
from sqlalchemy.orm import Session
from app.models.user import SystemLog
from typing import Optional


async def system_log(
    data: dict,
    db: Session,
    tx: Optional[Session] = None
):
    """
    Create a system log entry.
    
    Args:
        data: Dictionary with log data (event, userId, entityId, etc.)
        db: Database session
        tx: Optional transaction session (if in a transaction)
    """
    session = tx or db
    
    log_entry = SystemLog(
        user_id=data.get("userId", "system"),
        entity_id=data.get("entityId"),
        entity_type=data.get("entityType"),
        event=data.get("event"),
        description=data.get("description"),
        ip_address=data.get("ipAddress"),
        meta=data.get("meta")
    )
    
    session.add(log_entry)
    if not tx:
        session.commit()
    
    return log_entry
