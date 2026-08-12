"""Integration logging service for business logic."""
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import datetime
import json
import logging
import httpx
from app.config import settings
from app.models.integration import IntegrationLog
from app.schemas.integration import IntegrationLogCreate, IntegrationLogUpdate
from app.services.error_handler import handle_not_found
from app.services.webhook_service import WebhookService

logger = logging.getLogger(__name__)


def _decrypt_workspace_key(workspace) -> Optional[str]:
    """Decrypt a workspace's stored API key; None on missing/undecryptable."""
    try:
        from app.utils.field_encryption import decrypt_secret

        cipher = getattr(workspace, "api_key_ciphertext", None)
        if not cipher:
            return None
        return decrypt_secret(cipher)
    except Exception:
        logger.warning(
            "RespondClient: could not decrypt API key for workspace %s",
            getattr(workspace, "space_id", None),
        )
        return None


def _resolve_workspace_credentials(
    db=None,
    *,
    identifier: Optional[str] = None,
    contact_id: Optional[str] = None,
) -> Optional[tuple]:
    """Resolve (api_key, base_url, space_id) from `respond_workspaces`.

    Order: the contact's own workspace (when identifier/contact_id resolves to a
    RespondContact with a workspace_id), else the default workspace. Returns None
    when no workspace/key can be resolved (caller falls back to the env key).
    Owns a short-lived Session when `db` is not supplied.
    """
    own_session = False
    try:
        if db is None:
            from app.database import SessionLocal

            db = SessionLocal()
            own_session = True
        from app.models.access import RespondContact
        from app.services.respond_workspace_service import RespondWorkspaceService

        ws_svc = RespondWorkspaceService(db)
        workspace = None

        contact = None
        if contact_id:
            contact = (
                db.query(RespondContact)
                .filter(RespondContact.id == str(contact_id))
                .first()
            )
        elif identifier:
            val = str(identifier)
            val = val.split(":", 1)[1] if ":" in val else val
            contact = (
                db.query(RespondContact)
                .filter(RespondContact.respond_io_id == val)
                .first()
            )
            if contact is None:
                contact = (
                    db.query(RespondContact)
                    .filter(RespondContact.phone_number == val)
                    .first()
                )
        if contact is not None and getattr(contact, "workspace_id", None):
            workspace = ws_svc.get(contact.workspace_id)
        if workspace is None:
            workspace = ws_svc.get_default()
        if workspace is None:
            return None
        key = _decrypt_workspace_key(workspace)
        if not key:
            return None
        return key, (getattr(workspace, "base_url", None) or None), getattr(workspace, "space_id", None)
    except Exception:
        logger.warning("RespondClient: workspace credential resolution failed.", exc_info=True)
        return None
    finally:
        if own_session and db is not None:
            db.close()


class RespondClient:
    """Client for Respond.io API.

    Credentials come from `respond_workspaces` (per-contact workspace when an
    identifier/contact resolves, else the default workspace). The env
    RESPOND_API_KEY is a deprecated last-resort fallback only — being phased out.
    """

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        space_id: Optional[str] = None,
    ) -> None:
        if api_key is None:
            # No explicit key (the common case): resolve the default workspace.
            # Contact-scoped callers should use RespondClient.for_identifier(...).
            creds = _resolve_workspace_credentials()
            if creds:
                ws_key, ws_base, ws_space = creds
                api_key = ws_key
                base_url = base_url or ws_base
                space_id = space_id or ws_space
        if api_key is None:
            api_key = settings.respond_api_key
            if api_key:
                logger.warning(
                    "RespondClient: no workspace API key resolved; falling back to "
                    "deprecated env RESPOND_API_KEY. Configure the workspace API key."
                )
        self.base_url = (base_url or settings.respond_base_url or "https://api.respond.io").rstrip("/")
        self.api_key = api_key
        self.space_id = space_id or settings.respond_space_id

    @classmethod
    def for_workspace(cls, workspace) -> "RespondClient":
        """Build a client bound to a specific workspace row."""
        return cls(
            api_key=_decrypt_workspace_key(workspace),
            base_url=getattr(workspace, "base_url", None) or None,
            space_id=getattr(workspace, "space_id", None),
        )

    @classmethod
    def for_identifier(cls, db, identifier: Optional[str]) -> "RespondClient":
        """Client keyed to the workspace that owns the contact for ``identifier``
        (falls back to the default workspace)."""
        creds = _resolve_workspace_credentials(db, identifier=identifier)
        if creds:
            key, base, space = creds
            return cls(api_key=key, base_url=base, space_id=space)
        return cls()

    @classmethod
    def for_contact_id(cls, db, contact_id: Optional[str]) -> "RespondClient":
        """Client keyed to the workspace that owns ``contact_id`` (falls back to
        the default workspace)."""
        creds = _resolve_workspace_credentials(db, contact_id=contact_id)
        if creds:
            key, base, space = creds
            return cls(api_key=key, base_url=base, space_id=space)
        return cls()

    def _headers(self) -> dict:
        """Headers required by Respond.io; Accept and User-Agent help avoid CloudFront/WAF 403."""
        base = {
            "Accept": "application/json, application/xml, multipart/form-data",
            "Content-Type": "application/json",
            "User-Agent": "SorentoCRM/1.0 (Respond.io Integration)",
        }
        if not self.api_key:
            return base
        base["Authorization"] = f"Bearer {self.api_key}"
        return base

    def _contact_api_identifier(self, identifier: str) -> str:
        """Format contact identifier for API path: use id:xxxx for plain IDs, keep phone: etc. as-is."""
        if not identifier or ":" in identifier:
            return identifier or ""
        return f"id:{identifier}"

    def get_user_by_id(self, user_id: str) -> dict:
        if not self.api_key:
            raise ValueError("Respond API key is not configured.")
        url = f"{self.base_url}/v2/space/user/{user_id}"
        with httpx.Client(timeout=15) as client:
            response = client.get(url, headers=self._headers())
            response.raise_for_status()
            return response.json()

    def get_contact_by_identifier(self, identifier: str) -> dict:
        if not self.api_key:
            raise ValueError("Respond API key is not configured.")
        api_id = self._contact_api_identifier(identifier)
        url = f"{self.base_url}/v2/contact/{api_id}"
        with httpx.Client(timeout=15) as client:
            response = client.get(url, headers=self._headers())
            # Check status and raise with response attached for error handling
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as e:
                # Attach response for better error handling upstream
                e.response = response
                raise
            return response.json()
    
    def get_contact_by_phone(self, phone_number: str) -> dict:
        """Get contact by phone number using phone: prefix."""
        if not self.api_key:
            raise ValueError("Respond API key is not configured.")
        # Format: phone:+60123456789 (ensure phone: prefix is added)
        # Remove phone: if already present to avoid duplication
        clean_phone = phone_number.replace("phone:", "")
        identifier = f"phone:{clean_phone}"
        return self.get_contact_by_identifier(identifier)

    def list_users(self, limit: int = 100) -> list[dict]:
        """List Respond.io users."""
        if not self.api_key:
            raise ValueError("Respond API key is not configured.")
        url = f"{self.base_url}/v2/space/users"
        params = {"limit": limit}
        with httpx.Client(timeout=15) as client:
            response = client.get(url, headers=self._headers(), params=params)
            response.raise_for_status()
            data = response.json()
            # Handle different response formats
            if isinstance(data, dict):
                return data.get("data", data.get("users", []))
            return data if isinstance(data, list) else []

    def send_message(self, identifier: str, text: str) -> dict:
        """Send a text message to a contact. identifier = last segment of respond inbox URL (e.g. contact_id). Uses id: prefix for API."""
        if not self.api_key:
            raise ValueError("Respond API key is not configured.")
        api_id = self._contact_api_identifier(identifier)
        url = f"{self.base_url}/v2/contact/{api_id}/message"
        payload = {"message": {"type": "text", "text": text}}
        with httpx.Client(timeout=15) as client:
            response = client.post(url, headers=self._headers(), json=payload)
            response.raise_for_status()
            return response.json() if response.content else {}

    def send_attachment(
        self,
        identifier: str,
        attachment_type: str,
        url: str,
        caption: Optional[str] = None,
    ) -> dict:
        """Send a media attachment to a contact. message type ``attachment``
        (R1, resolved 2026-08-12): subtypes are ``image`` / ``video`` / ``audio`` /
        ``file`` only — Respond.io has no sticker send and no reply-to/context
        parameter on this endpoint. ``url`` must be reachable by Respond's own
        fetcher: a permanent CDN link where the active storage provider serves
        one (R2), or a long-lived signed URL otherwise — never a short presign
        (see ``respond_chat_template_service.upload_chat_attachment``).
        """
        if not self.api_key:
            raise ValueError("Respond API key is not configured.")
        if attachment_type not in ("image", "video", "audio", "file"):
            raise ValueError(f"Unsupported Respond.io attachment type: {attachment_type}")
        api_id = self._contact_api_identifier(identifier)
        url_endpoint = f"{self.base_url}/v2/contact/{api_id}/message"
        attachment_payload: dict = {"type": attachment_type, "url": url}
        if caption:
            attachment_payload["caption"] = caption
        payload = {"message": {"type": "attachment", "attachment": attachment_payload}}
        # Larger timeout than send_message: Respond fetches the media itself
        # before it can hand back a response.
        with httpx.Client(timeout=30) as client:
            response = client.post(url_endpoint, headers=self._headers(), json=payload)
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as e:
                e.response = response
                raise
            return response.json() if response.content else {}

    def close_conversation(
        self,
        identifier: str,
        *,
        category: Optional[str] = None,
        summary: Optional[str] = None,
    ) -> dict:
        """Close (resolve) the open conversation for a contact in Respond.io.

        Mirrors ``send_message`` (id: prefix, Bearer auth). ``category``/``summary``
        form the closing note; a workspace may require category before closing, in
        which case omitting it yields a 4xx (callers treat close as best-effort).
        Endpoint: POST /v2/contact/{identifier}/conversation/status, body
        {status: "close", category, summary}. (No /conversation/close path — that 404s.)
        """
        if not self.api_key:
            raise ValueError("Respond API key is not configured.")
        api_id = self._contact_api_identifier(identifier)
        url = f"{self.base_url}/v2/contact/{api_id}/conversation/status"
        payload: dict = {"status": "close"}
        if category:
            payload["category"] = category
        if summary:
            payload["summary"] = summary
        with httpx.Client(timeout=15) as client:
            response = client.post(url, headers=self._headers(), json=payload)
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as e:
                e.response = response
                raise
            return response.json() if response.content else {}

    def list_messages(
        self,
        identifier: str,
        limit: int = 50,
        cursor: Optional[str] = None,
    ) -> dict:
        """
        List messages for a contact. GET /v2/contact/{identifier}/message/list.
        identifier: contact id (e.g. last segment of respond inbox URL); will be prefixed with id: if no colon.
        Returns dict with 'items' (list of message objects) and 'pagination' (next/previous URLs or cursor).
        Max limit 50.
        """
        if not self.api_key:
            raise ValueError("Respond API key is not configured.")
        api_id = self._contact_api_identifier(identifier)
        url = f"{self.base_url}/v2/contact/{api_id}/message/list"
        params: dict = {"limit": min(limit, 50)}
        if cursor:
            params["cursorId"] = cursor
        with httpx.Client(timeout=15) as client:
            response = client.get(url, headers=self._headers(), params=params)
            response.raise_for_status()
            payload = response.json() if response.content else {"items": [], "pagination": {}}
        return self._fill_template_message_text(payload)

    @staticmethod
    def _fill_template_message_text(payload: dict) -> dict:
        """Backfill `message.text` for whatsapp_template items.

        Respond.io returns template messages with the definition + positional
        params but no flat `text`, so the chat panel rendered "(no text)".
        Render the body in place (falling back to the template name) so every
        consumer reading `message.text` shows the sent content.
        """
        if not isinstance(payload, dict):
            return payload
        items = payload.get("items")
        if not isinstance(items, list):
            items = payload.get("data") if isinstance(payload.get("data"), list) else []
        for item in items:
            if not isinstance(item, dict):
                continue
            msg = item.get("message")
            if not isinstance(msg, dict):
                continue
            if (msg.get("type") or "").lower() != "whatsapp_template":
                continue
            if (msg.get("text") or "").strip():
                continue
            from app.services.activities_service import _render_whatsapp_template_body

            rendered = _render_whatsapp_template_body(msg)
            if not rendered:
                name = ((msg.get("template") or {}).get("name") or "").strip()
                rendered = f"Template: {name}" if name else None
            if rendered:
                msg["text"] = rendered
        return payload

    def get_message(self, identifier: str, message_id: int | str) -> dict:
        """
        Get a single message by ID for a contact.
        GET /v2/contact/{identifier}/message/{messageId}
        """
        if not self.api_key:
            raise ValueError("Respond API key is not configured.")
        api_id = self._contact_api_identifier(identifier)
        url = f"{self.base_url}/v2/contact/{api_id}/message/{message_id}"
        with httpx.Client(timeout=15) as client:
            response = client.get(url, headers=self._headers())
            response.raise_for_status()
            return response.json() if response.content else {}

    def set_conversation_assignee(self, identifier: str, assignee_id: str) -> dict:
        """
        Set the conversation assignee for a contact. POST /v2/contact/{identifier}/conversation/assignee.
        identifier: contact identifier (e.g. "phone:+60166753328" or "id:contact-uuid").
        assignee_id: Respond.io user id (space member). Use empty string to unassign.
        """
        if not self.api_key:
            raise ValueError("Respond API key is not configured.")
        api_id = self._contact_api_identifier(identifier)
        url = f"{self.base_url}/v2/contact/{api_id}/conversation/assignee"
        payload = {"assigneeId": assignee_id} if assignee_id else {}
        with httpx.Client(timeout=15) as client:
            response = client.post(url, headers=self._headers(), json=payload)
            response.raise_for_status()
            return response.json() if response.content else {}

    def list_contacts(
        self,
        *,
        body: Optional[dict] = None,
        search: str = "",
        filter_body: Optional[dict] = None,
        timezone: str = "Asia/Kuala_Lumpur",
        limit: Optional[int] = None,
        cursor: Optional[str] = None,
    ) -> dict:
        """
        List contacts via POST /v2/contact/list.
        If body is provided, it is sent as-is. Otherwise builds payload from search, filter_body, timezone, limit, cursor.
        """
        if not self.api_key:
            raise ValueError("Respond API key is not configured.")
        url = f"{self.base_url}/v2/contact/list"
        if body is not None:
            payload = body
        else:
            payload = {"search": search, "filter": filter_body or {}, "timezone": timezone}
            if limit is not None:
                payload["limit"] = limit
            if cursor:
                payload["cursor"] = cursor
        with httpx.Client(timeout=30) as client:
            response = client.post(url, headers=self._headers(), json=payload)
            response.raise_for_status()
            return response.json() if response.content else {}

    def list_channels(self) -> list[dict]:
        """List workspace channels. GET /v2/space/channel.

        Returns items like {"id": 453209, "name": "...", "source": "whatsapp_business"}.
        """
        if not self.api_key:
            raise ValueError("Respond API key is not configured.")
        url = f"{self.base_url}/v2/space/channel"
        with httpx.Client(timeout=15) as client:
            response = client.get(url, headers=self._headers())
            response.raise_for_status()
            data = response.json() if response.content else {}
            return data.get("items", []) if isinstance(data, dict) else []

    def list_message_templates(self, channel_id: int | str) -> list[dict]:
        """List ALL WhatsApp message templates of a channel.

        GET /v2/space/channel/{channelId}/template. Items carry name,
        languageCode, category, status, statusDetail, templateId, namespace
        and a components array (body text contains {{1}}..{{n}}).

        The endpoint is cursor-paginated (default page size ~10). We MUST walk
        every page: the template sync hard-deletes any local row whose id is
        absent from this list, so returning only page 1 would delete every
        template past the first page on each sync.
        """
        if not self.api_key:
            raise ValueError("Respond API key is not configured.")
        url = f"{self.base_url}/v2/space/channel/{channel_id}/template"
        items: list[dict] = []
        cursor: Optional[str] = None
        seen_cursors: set[str] = set()
        with httpx.Client(timeout=15) as client:
            for _ in range(100):  # hard page cap — guards against a cursor loop
                params: dict = {"limit": 100}
                if cursor:
                    params["cursorId"] = cursor
                response = client.get(url, headers=self._headers(), params=params)
                response.raise_for_status()
                data = response.json() if response.content else {}
                if not isinstance(data, dict):
                    break
                page = data.get("items") or []
                if isinstance(page, list):
                    items.extend(page)
                pagination = data.get("pagination") or {}
                nxt = pagination.get("next")
                cursor = nxt if isinstance(nxt, str) else pagination.get("cursorId")
                if not cursor or cursor in seen_cursors:
                    break
                seen_cursors.add(cursor)
        return items

    def send_template_message(
        self,
        identifier: str,
        *,
        channel_id: int,
        template_name: str,
        language_code: str,
        body_text: str,
        parameters: list[str],
        button: Optional[dict] = None,
    ) -> dict:
        """Send an approved WhatsApp template message to a contact.

        POST /v2/contact/{identifier}/message with type=whatsapp_template.
        Respond.io requires the FULL template body text alongside the
        positional parameters (verified against the live API 2026-06-08).

        ``button`` (optional) fills a template's dynamic URL button. Shape:
        ``{"text": str, "url": str (with {{1}}), "suffix": str}``. Appended as a
        respond.io ``buttons`` component (shape verified via Copy API Payload
        2026-06-22): ``{"type":"buttons","buttons":[{"type":"url","text":...,
        "url":"https://x/{{1}}","parameters":[{"type":"text","text":<suffix>}]}]}``.
        """
        if not self.api_key:
            raise ValueError("Respond API key is not configured.")
        api_id = self._contact_api_identifier(identifier)
        url = f"{self.base_url}/v2/contact/{api_id}/message"
        body_component: dict = {"type": "body", "text": body_text}
        if parameters:
            body_component["parameters"] = [{"type": "text", "text": p} for p in parameters]
        components: list[dict] = [body_component]
        if button:
            components.append(
                {
                    "type": "buttons",
                    "buttons": [
                        {
                            "type": "url",
                            "text": button.get("text") or "View",
                            "url": button.get("url") or "",
                            "parameters": [
                                {"type": "text", "text": button.get("suffix") or ""}
                            ],
                        }
                    ],
                }
            )
        payload = {
            "channelId": channel_id,
            "message": {
                "type": "whatsapp_template",
                "template": {
                    "name": template_name,
                    "languageCode": language_code,
                    "components": components,
                },
            },
        }
        with httpx.Client(timeout=15) as client:
            response = client.post(url, headers=self._headers(), json=payload)
            response.raise_for_status()
            return response.json() if response.content else {}

    def update_contact(self, identifier: str, payload: dict) -> dict:
        """Update contact via PUT /v2/contact/{identifier}. payload can include customFields."""
        if not self.api_key:
            raise ValueError("Respond API key is not configured.")
        api_id = self._contact_api_identifier(identifier)
        url = f"{self.base_url}/v2/contact/{api_id}"
        with httpx.Client(timeout=15) as client:
            response = client.put(url, headers=self._headers(), json=payload)
            response.raise_for_status()
            return response.json() if response.content else {}


class IntegrationLogService:
    """Service for integration log operations."""
    
    def __init__(self, db: Session):
        self.db = db
        self.webhook_service = WebhookService()
    
    def create_integration_log(
        self, 
        log_data: IntegrationLogCreate,
        request_payload_dict: Optional[dict] = None
    ) -> IntegrationLog:
        """
        Create a new integration log.
        
        Args:
            log_data: Integration log data
            request_payload_dict: Optional dictionary to serialize as JSON in request_payload
            
        Returns:
            Created IntegrationLog instance
        """
        log_dict = log_data.model_dump(exclude_unset=True)
        
        # Serialize request_payload if provided as dict
        if request_payload_dict and not log_dict.get('request_payload'):
            log_dict['request_payload'] = json.dumps(request_payload_dict)
        
        integration_log = IntegrationLog(**log_dict)
        self.db.add(integration_log)
        self.db.commit()
        self.db.refresh(integration_log)
        return integration_log
    
    def get_integration_log(self, log_id: str) -> IntegrationLog:
        """Get an integration log by ID."""
        log = self.db.query(IntegrationLog).filter(IntegrationLog.id == log_id).first()
        if not log:
            raise handle_not_found("Integration Log", log_id)
        return log
    
    def get_integration_log_response(self, log_id: str):
        """Get an integration log by ID and return as response model."""
        from app.schemas.integration import IntegrationLogResponse
        log = self.get_integration_log(log_id)
        
        # Convert to response model
        log_dict = {
            'id': str(log.id),
            'integration_channel': log.integration_channel,
            'business_table': log.business_table,
            'business_id': str(log.business_id),
            'external_reference': log.external_reference,
            'direction': log.direction,
            'endpoint': log.endpoint,
            'http_method': log.http_method,
            'request_headers': log.request_headers,
            'request_payload': log.request_payload,
            'status_code': log.status_code,
            'status': log.status,
            'response_headers': log.response_headers,
            'response_payload': log.response_payload,
            'error_code': log.error_code,
            'error_message': log.error_message,
            'correlation_id': str(log.correlation_id) if log.correlation_id else None,
            'retry_count': log.retry_count,
            'max_retry_allowed': log.max_retry_allowed,
            'next_retry_at': log.next_retry_at,
            'created_at': log.created_at,
            'created_by': str(log.created_by) if log.created_by else None,
            'processed_at': log.processed_at,
            'updated_at': log.updated_at,  # Can be None for old records
        }
        return IntegrationLogResponse.model_validate(log_dict)
    
    def list_integration_logs(
        self,
        page: int = 1,
        limit: int = 50,
        status: Optional[str] = None,
        integration_channel: Optional[str] = None,
        business_table: Optional[str] = None,
        business_id: Optional[str] = None,
        created_from: Optional[datetime] = None,
        created_to: Optional[datetime] = None,
        status_code: Optional[int] = None,
        error_contains: Optional[list] = None,
        exclude_healthcheck: bool = True,
    ):
        """List integration logs with pagination and filtering."""
        from app.schemas.common import PaginationResponse
        from app.services.n8n_liveness_service import HEALTHCHECK_CHANNEL

        try:
            q = self.db.query(IntegrationLog)

            if status:
                q = q.filter(IntegrationLog.status == status)
            if integration_channel:
                q = q.filter(IntegrationLog.integration_channel == integration_channel)
            elif exclude_healthcheck:
                # Sentinel hygiene: liveness-probe rows are noise in the general list.
                # Only excluded when the caller didn't explicitly ask for a channel.
                q = q.filter(IntegrationLog.integration_channel != HEALTHCHECK_CHANNEL)
            if business_table:
                q = q.filter(IntegrationLog.business_table == business_table)
            if business_id:
                q = q.filter(IntegrationLog.business_id == business_id)
            if created_from:
                q = q.filter(IntegrationLog.created_at >= created_from)
            if created_to:
                q = q.filter(IntegrationLog.created_at <= created_to)
            if status_code is not None:
                q = q.filter(IntegrationLog.status_code == status_code)
            if error_contains:
                # Drill-down from a health-dashboard failure signature. Each term is
                # a literal stable substring of the group's message (volatile ids
                # stripped). They are AND-ed: one term alone is not enough to pin a
                # group, because the longest stable run of one fault can also be a
                # prefix of a different fault on a neighbouring endpoint.
                #
                # Escape LIKE wildcards so a `%` or `_` inside a real error message
                # cannot widen the match.
                terms = [error_contains] if isinstance(error_contains, str) else error_contains
                for raw in terms:
                    if not raw:
                        continue
                    term = (
                        raw.replace("\\", "\\\\")
                        .replace("%", "\\%")
                        .replace("_", "\\_")
                    )
                    q = q.filter(
                        IntegrationLog.error_message.ilike(f"%{term}%", escape="\\")
                    )

            q = q.order_by(IntegrationLog.created_at.desc())
            
            total = q.count()
            offset = (page - 1) * limit
            logs = q.offset(offset).limit(limit).all()
            
            logger.debug(f"Found {total} integration logs, returning {len(logs)}")
            
            # Convert to response models, handling None values
            from app.schemas.integration import IntegrationLogResponse
            log_responses = []
            for log in logs:
                try:
                    # Convert SQLAlchemy model to dict with explicit handling
                    log_dict = {
                        'id': str(log.id),
                        'integration_channel': log.integration_channel,
                        'business_table': log.business_table,
                        'business_id': str(log.business_id),
                        'external_reference': log.external_reference,
                        'direction': log.direction,
                        'endpoint': log.endpoint,
                        'http_method': log.http_method,
                        'request_headers': log.request_headers,
                        'request_payload': log.request_payload,
                        'status_code': log.status_code,
                        'status': log.status,
                        'response_headers': log.response_headers,
                        'response_payload': log.response_payload,
                        'error_code': log.error_code,
                        'error_message': log.error_message,
                        'correlation_id': str(log.correlation_id) if log.correlation_id else None,
                        'retry_count': log.retry_count,
                        'max_retry_allowed': log.max_retry_allowed,
                        'next_retry_at': log.next_retry_at,
                        'created_at': log.created_at,
                        'created_by': str(log.created_by) if log.created_by else None,
                        'processed_at': log.processed_at,
                        'updated_at': log.updated_at,  # Can be None for old records
                    }
                    log_responses.append(IntegrationLogResponse.model_validate(log_dict))
                except Exception as e:
                    logger.error(f"Error validating integration log {log.id}: {str(e)}", exc_info=True)
                    raise
            
            return {
                "data": log_responses,
                "pagination": PaginationResponse(total=total, page=page, limit=limit),
                "empty": total == 0
            }
        except Exception as e:
            logger.error(f"Error in list_integration_logs: {str(e)}", exc_info=True)
            raise
    
    def update_integration_log(
        self, 
        log_id: str, 
        update_data: IntegrationLogUpdate
    ) -> IntegrationLog:
        """Update an integration log."""
        log = self.get_integration_log(log_id)
        
        update_dict = update_data.model_dump(exclude_unset=True)
        for key, value in update_dict.items():
            setattr(log, key, value)
        
        self.db.commit()
        self.db.refresh(log)
        return log
    
    def send_webhook_for_log(
        self,
        log_id: str,
        *,
        force_resend: bool = False,
    ) -> tuple[bool, Optional[str]]:
        """
        Send webhook request for a specific integration log.

        Args:
            log_id: Integration log ID
            force_resend: If True, send even when status is success/sent and skip max-retry guard
                (used for manual attachment "Resubmit" with a refreshed payload).

        Returns:
            Tuple of (success: bool, error_message: Optional[str])
        """
        log = self.get_integration_log(log_id)

        # Check if already sent or processed successfully
        if not force_resend and log.status in ["success", "sent"]:
            logger.info(f"Integration log {log_id} already sent or processed (status: {log.status})")
            return True, None

        # Check retry limit
        if not force_resend and log.retry_count >= log.max_retry_allowed:
            logger.warning(f"Integration log {log_id} exceeded max retries ({log.max_retry_allowed})")
            self.update_integration_log(
                log_id,
                IntegrationLogUpdate(status="failed", error_code="MAX_RETRIES_EXCEEDED")
            )
            return False, "Maximum retries exceeded"
        
        # Parse request payload
        try:
            if log.request_payload:
                payload_dict = json.loads(log.request_payload)
            else:
                payload_dict = {}
        except (json.JSONDecodeError, TypeError):
            logger.error(f"Invalid JSON in request_payload for log {log_id}")
            payload_dict = {}
        
        # Update status to processing
        log.status = "processing"
        self.db.commit()
        
        # Parse request headers
        headers = None
        if log.request_headers:
            try:
                headers = json.loads(log.request_headers)
            except (json.JSONDecodeError, TypeError):
                headers = None
        
        # Send webhook
        success, status_code, response_data, error_code, error_message = self.webhook_service.send_webhook(
            url=log.endpoint,
            payload=payload_dict,
            headers=headers
        )
        
        # Prepare response payload for storage
        response_payload_str = None
        response_headers_str = None
        if response_data:
            response_payload_str = json.dumps(response_data)
        
        # Manual resubmit should not consume automatic retry budget
        next_retry_count = log.retry_count if force_resend else log.retry_count + 1

        # Update log with response
        update_data = IntegrationLogUpdate(
            status="sent" if success else "failed",  # Changed from "success" to "sent" - n8n will call back to update to success/failed
            status_code=status_code,
            response_payload=response_payload_str,
            response_headers=response_headers_str,
            error_code=error_code,
            error_message=error_message,
            retry_count=next_retry_count,
        )
        
        if success:
            update_data.processed_at = datetime.utcnow()
            logger.info(f"Webhook sent successfully for log {log_id}, status set to 'sent' (waiting for n8n callback)")
        else:
            # Calculate next retry time
            update_data.next_retry_at = self.webhook_service.calculate_next_retry_at(log.retry_count)
            update_data.status = "pending"  # Reset to pending for retry
            logger.warning(f"Webhook failed for log {log_id}, will retry at {update_data.next_retry_at}")
        
        self.update_integration_log(log_id, update_data)
        
        return success, error_message
    
    def process_pending_logs(self) -> dict:
        """
        Process pending/processing integration logs that are ready for retry,
        AND mark `sent` rows whose n8n callback never arrived as failed.

        Two passes per tick:
        1. Re-send `pending` / `processing` rows past `next_retry_at` (legacy behaviour).
        2. Mark `sent` rows older than the configured callback timeout as `failed`
           with error_code=N8N_CALLBACK_TIMEOUT — drives the upload-activity drawer
           freshness invariant so users never see infinite "Processing…".

        See docs/plans/PLAN-upload-activity-drawer.md §4.5.

        Called by cron job.
        """
        from datetime import timedelta
        from sqlalchemy import and_

        # ----- pass 1: retry pending/processing -----
        now = datetime.utcnow()
        pending_logs = self.db.query(IntegrationLog).filter(
            and_(
                IntegrationLog.status.in_(["pending", "processing"]),
                (IntegrationLog.next_retry_at.is_(None)) | (IntegrationLog.next_retry_at <= now)
            )
        ).limit(100).all()

        processed = 0
        succeeded = 0
        failed = 0

        for log in pending_logs:
            try:
                success, _err = self.send_webhook_for_log(log.id)
                processed += 1
                if success:
                    succeeded += 1
                else:
                    failed += 1
            except Exception as e:
                logger.error(f"Error processing integration log {log.id}: {str(e)}", exc_info=True)
                failed += 1

        # ----- pass 2: sweep stale `sent` rows -----
        timeout_minutes = self._get_n8n_callback_timeout_minutes()
        timeout_cutoff = now - timedelta(minutes=timeout_minutes)
        stale_sent_logs = self.db.query(IntegrationLog).filter(
            and_(
                IntegrationLog.status == "sent",
                IntegrationLog.processed_at.isnot(None),
                IntegrationLog.processed_at <= timeout_cutoff,
            )
        ).limit(100).all()

        timed_out = 0
        for log in stale_sent_logs:
            try:
                from app.schemas.integration import IntegrationLogUpdate

                self.update_integration_log(
                    log.id,
                    IntegrationLogUpdate(
                        status="failed",
                        error_code="N8N_CALLBACK_TIMEOUT",
                        error_message=(
                            f"n8n did not call back within {timeout_minutes} minutes"
                        ),
                        processed_at=datetime.utcnow(),
                    ),
                )
                timed_out += 1
            except Exception as e:
                logger.error(
                    f"Error marking integration log {log.id} as timed out: {str(e)}",
                    exc_info=True,
                )

        return {
            "processed": processed,
            "succeeded": succeeded,
            "failed": failed,
            "total_found": len(pending_logs),
            "timed_out": timed_out,
        }

    def _get_n8n_callback_timeout_minutes(self) -> int:
        """
        Resolve the n8n callback timeout in minutes.

        Source: `N8N_CALLBACK_TIMEOUT_MINUTES` env var. Default 10.
        Returns an int >= 1. A future migration may add a column on
        SystemSetting; the env fallback keeps this safe for legacy installs.
        """
        import os

        env_val = os.environ.get("N8N_CALLBACK_TIMEOUT_MINUTES")
        if env_val:
            try:
                return max(1, int(env_val))
            except ValueError:
                pass
        return 10


def log_respond_send(
    db: Session,
    *,
    business_table: str,
    business_id: str,
    identifier: str,
    request_payload: dict,
    response: Optional[object] = None,
    exc: Optional[BaseException] = None,
) -> None:
    """Write one Respond.io outbox row for a send that did NOT go through
    ``respond_io_tasks._send_and_log``.

    Every Respond.io send must leave an ``integration_logs`` trace on success AND
    failure — local dev runs with deliberately-wrong credentials, so a 401'd send
    still has to be readable from the Respond outbox. Synchronous senders that
    call ``RespondClient.send_message`` directly (portal link delivery, SLA
    conversation reply) previously wrote nothing at all, so those failures were
    invisible everywhere.

    Mirrors ``_send_and_log``'s failure handling: prefer the payload actually
    attempted (``_attach_send_context`` stamps it on the exception) and capture
    Respond's real HTTP status and body so a 403 is diagnosable rather than just
    "403 Forbidden for url ...".

    Best-effort by construction: logging must never be the reason a send fails.
    """
    try:
        payload = request_payload
        status_code = None
        response_body = None
        error_message = None

        if exc is not None:
            payload = getattr(exc, "request_payload", request_payload)
            error_message = str(exc)[:5000]
            resp = getattr(exc, "response", None)
            if resp is not None:
                try:
                    status_code = resp.status_code
                except Exception:
                    status_code = None
                try:
                    response_body = (resp.text or "")[:50000]
                except Exception:
                    response_body = None
        elif response is not None:
            response_body = str(response)[:50000]

        IntegrationLogService(db).create_integration_log(
            IntegrationLogCreate(
                integration_channel="respond_io",
                business_table=business_table,
                business_id=str(business_id),
                external_reference=identifier or "",
                direction="outbound",
                endpoint=(
                    f"https://api.respond.io/v2/contact/id:{identifier or ''}/message"
                ),
                http_method="POST",
                status="failed" if exc is not None else "success",
                status_code=status_code,
                response_payload=response_body,
                error_message=error_message,
            ),
            request_payload_dict=payload,
        )
    except Exception:  # noqa: BLE001
        logger.exception(
            "Failed to write Respond outbox row for %s %s", business_table, business_id
        )
