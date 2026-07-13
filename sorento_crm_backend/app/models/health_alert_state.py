"""De-dup state for the system-health watchdog (WS3).

One row per alert condition (`alert_key`). The watchdog re-alerts only on a
transition into a bad state, or when still-bad past a cooldown — so a persistently
overdue task doesn't spam every 10-min tick. See PLAN-system-health-observability WS3.
"""
from sqlalchemy import Column, String, DateTime, Text
from sqlalchemy.sql import func
from app.database import Base
import uuid


class HealthAlertState(Base):
    __tablename__ = "health_alert_state"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    # Stable per-condition key, e.g. "n8n_liveness", "task_overdue:import_job_processor",
    # "integration_spike:respond_io". One row per key.
    alert_key = Column(String(200), nullable=False, unique=True, index=True)
    state = Column(String(20), nullable=False, default="ok")  # "ok" | "alerting"
    last_alerted_at = Column(DateTime(timezone=False), nullable=True)
    last_detail = Column(Text, nullable=True)  # human context of the last alert (for the digest / audit)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False)
