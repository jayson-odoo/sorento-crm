"""n8n liveness probe (System Health observability WS1d).

Fires a lightweight ping at the dedicated n8n `system-healthcheck-ping` workflow
(webhook → immediate `/status` success callback; no MCP, no S3, no business data).

Round-trip proves: CRM can reach n8n (the outbound POST) AND n8n can reach CRM back
(the callback flips this log to `success`). If n8n is down, the outbound POST fails →
the log never reaches `success` and the watchdog alerts; if n8n runs but can't call
back, the existing `integration_log_retry` Pass-2 timeout marks it `failed`.

The healthcheck rows use channel `n8n_healthcheck` / business_table `__healthcheck__`
so they are trivially excludable from real attachment/integration listings.
"""
import logging
import os
import uuid

from sqlalchemy.orm import Session

from app.schemas.integration import IntegrationLogCreate
from app.services.integration_service import IntegrationLogService

logger = logging.getLogger(__name__)

HEALTHCHECK_CHANNEL = "n8n_healthcheck"
HEALTHCHECK_BUSINESS_TABLE = "__healthcheck__"

# Dedicated n8n liveness workflow webhook (system-healthcheck-ping). Env-overridable.
DEFAULT_PING_URL = "https://automate-sorento.foundryx.my/webhook/system-healthcheck-ping"


def _ping_url() -> str:
    return (os.getenv("N8N_LIVENESS_PING_URL", "") or "").strip() or DEFAULT_PING_URL


def run_n8n_liveness_ping(db: Session) -> dict:
    """Create a healthcheck integration_log and POST it to the n8n ping webhook.

    Registered as scheduled-task handler `n8n_liveness_ping`. Returns a small dict
    for the scheduled-task run log.
    """
    url = _ping_url()
    service = IntegrationLogService(db)
    log = service.create_integration_log(
        IntegrationLogCreate(
            integration_channel=HEALTHCHECK_CHANNEL,
            business_table=HEALTHCHECK_BUSINESS_TABLE,
            business_id=str(uuid.uuid4()),  # sentinel; never references a real row
            direction="outbound",
            endpoint=url,
            http_method="POST",
            status="pending",
        )
    )
    # The webhook body carries this log's own id so n8n echoes it back to /status.
    log.request_payload = f'{{"integration_log_id": "{log.id}"}}'
    db.commit()
    db.refresh(log)

    success, error = service.send_webhook_for_log(log.id)
    if not success:
        logger.warning("n8n liveness ping send failed for log %s: %s", log.id, error)
    return {"log_id": str(log.id), "sent": bool(success), "error": error, "url": url}
