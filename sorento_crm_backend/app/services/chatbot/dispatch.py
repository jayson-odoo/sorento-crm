"""Re-injecting a failed turn at the ingress it originally arrived through (AC-705).

R4: there is no automatic retry anywhere. An operator presses Retry on the trace screen,
and what that does is put the customer's ORIGINAL message back through the front door -
n8n's inject webhook, the same one the failover poller uses - so the turn re-enters with
the same ordering, the same lanes and the same sending path a live message gets.

**The CRM does not send, and does not re-run the turn in place.** Both would be the same
mistake in different clothes: the engine answering from a click would bypass n8n's egress
containment (D9), and a fresh in-process run would write a reply nobody delivered. What
happens instead is one HTTP POST of bytes the CRM already has, and then the turn arrives
back the ordinary way, as its own row.

**Unset locally on purpose.** With no `CHATBOT_RETRY_INGRESS_URL` the caller answers 409
`retry_unavailable` and nothing is posted. A dev machine that silently injected into
production n8n would answer a real customer from a developer's click, and the failure
would look like a bug in the customer's conversation rather than in somebody's `.env`.

From S7 the URL moves to the thin spine's own webhook. Nothing else here changes: the
body is the respond.io webhook body either way, which is exactly why this seam is one
function and one env var rather than a transport abstraction.
"""
from __future__ import annotations

import logging
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)

# n8n's HTTP node waits the whole turn, so this is generous: the call being answered
# means "n8n accepted the message", not "the turn finished".
REINJECT_TIMEOUT_SECONDS = 10.0

RETRY_KEY_HEADER = "X-Chatbot-Retry-Key"


class RetryUnavailable(RuntimeError):
    """No ingress is configured, so nothing was posted. The caller answers 409."""


class ReinjectFailed(RuntimeError):
    """The ingress answered non-2xx. The caller answers 502 and leaves the row alone."""

    def __init__(self, status_code: int, body: str) -> None:
        super().__init__(f"ingress returned {status_code}: {body}")
        self.status_code = status_code
        self.body = body


def ingress_url() -> str | None:
    """The configured inject webhook, or None when retry is not wired here."""
    url = (settings.chatbot_retry_ingress_url or "").strip()
    return url or None


def retry_available() -> bool:
    """Read by the endpoint so the UI can disable Retry rather than offer a 409."""
    return ingress_url() is not None


def reinject_envelope(row: Any) -> None:
    """Re-post the turn's ORIGINAL respond.io webhook body to the ingress.

    `row` is a `ChatbotTurn`. What goes on the wire is `envelope.message` exactly as it
    was stored - not a rebuilt envelope. n8n's webhook is the producer's contract and it
    expects a respond.io body; handing it anything the CRM composed would make the retry
    path a second, untested shape of the thing being retried.

    Raises `RetryUnavailable` (nothing sent) or `ReinjectFailed` (ingress refused).
    """
    import httpx

    url = ingress_url()
    if url is None:
        raise RetryUnavailable(
            "no retry ingress is configured for this environment "
            "(CHATBOT_RETRY_INGRESS_URL is unset)"
        )

    envelope = row.envelope if isinstance(row.envelope, dict) else {}
    body = envelope.get("message")
    if not isinstance(body, dict) or not body:
        raise RetryUnavailable(
            "this turn did not store the original message, so there is nothing to re-post"
        )

    headers = {"Content-Type": "application/json"}
    key = (settings.chatbot_retry_ingress_key or "").strip()
    if key:
        headers[RETRY_KEY_HEADER] = key

    try:
        response = httpx.post(
            url, json=body, headers=headers, timeout=REINJECT_TIMEOUT_SECONDS
        )
    except Exception as exc:  # noqa: BLE001 - a transport failure is the ingress refusing
        logger.warning("chatbot retry re-inject failed to reach the ingress: %s", exc)
        raise ReinjectFailed(0, str(exc)) from exc

    if response.status_code >= 300:
        logger.warning(
            "chatbot retry re-inject rejected: %s %s", response.status_code, response.text[:300]
        )
        raise ReinjectFailed(response.status_code, response.text[:500])

    logger.info(
        "chatbot retry re-injected turn %s for contact %s", row.id, row.contact_respond_id
    )
