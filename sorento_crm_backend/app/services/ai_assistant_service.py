"""AI assistant services (config + MCP-RAG chat orchestration)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable
from zoneinfo import ZoneInfo
import hashlib
import json
import logging
import re
import time
import uuid
from urllib.parse import urlparse

import httpx
from fastapi import HTTPException, status
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.config import settings
from app.models.ai_assistant import (
    AIAssistantConfig,
    AIAssistantConversation,
    AIAssistantGovernanceEvent,
    AIAssistantMessage,
    AIAssistantUsageLog,
)
from app.modules.runtime.installer import DEFAULT_TENANT_ID, get_enabled_module_keys, tenant_has_any_module_row
from app.schemas.ai_assistant import (
    AIAssistantAuthContext,
    AIAssistantConfigUpdate,
    PageSnapshotPayload,
)
from app.services.embedding_service import EmbeddingReadService
from app.services.entity_resolver import ResolutionResult, resolve_references
from app.services.llm_provider import ChatResult, LLMProvider, get_provider
from app.services.user_service import UserPermissionService

logger = logging.getLogger(__name__)


def _mask_key(raw: str | None) -> str | None:
    if not raw:
        return None
    if len(raw) <= 8:
        return "****"
    return f"****{raw[-4:]}"


_HTML_TAG_RE = re.compile(r"<[^>]+>")
_HTML_ENTITY_MAP = {
    "&nbsp;": " ",
    "&amp;": "&",
    "&lt;": "<",
    "&gt;": ">",
    "&quot;": '"',
    "&#39;": "'",
    "&apos;": "'",
}
_BLOCK_BREAK_RE = re.compile(
    r"</(p|h[1-6]|li|blockquote|div|br|pre)>|<br\s*/?>|<li[^>]*>",
    flags=re.IGNORECASE,
)


def _html_to_text(raw: str | None) -> str:
    """Convert rich-text-editor HTML to a plain-text prompt suitable for LLMs.

    The frontend system-prompt editor stores HTML; the LLM consumes plain text.
    We turn block-level tag boundaries into newlines, strip remaining tags, and
    decode a small set of HTML entities. If the input has no tags, it is
    returned unchanged so legacy plain-text prompts keep working.
    """
    if not raw:
        return ""
    if "<" not in raw:
        return raw
    with_breaks = _BLOCK_BREAK_RE.sub("\n", raw)
    stripped = _HTML_TAG_RE.sub("", with_breaks)
    for entity, replacement in _HTML_ENTITY_MAP.items():
        stripped = stripped.replace(entity, replacement)
    lines = [line.rstrip() for line in stripped.splitlines()]
    collapsed: list[str] = []
    for line in lines:
        if not line.strip() and collapsed and not collapsed[-1].strip():
            continue
        collapsed.append(line)
    return "\n".join(collapsed).strip()


def _current_date_directive() -> str:
    """Today's date (Asia/Kuala_Lumpur) + relative-date resolution rule.

    Ports the n8n sub-semantic-parser technique: LLMs have no clock and will
    otherwise resolve "last week" against their training cutoff (we saw a query
    land in 2023). Injecting the real current date lets the model convert
    relative dates to absolute calendar dates before it calls any data tool.
    Explicit UTC+8 (matches n8n's `$now.toUTC(8*60)`) so it is correct
    regardless of the server's own timezone.
    """
    now = datetime.now(ZoneInfo("Asia/Kuala_Lumpur"))
    today = now.strftime("%A, %d %B %Y")
    return (
        f"CURRENT DATE: {today} (Asia/Kuala_Lumpur).\n"
        "When the user's message contains a relative date or period — e.g. "
        "\"today\", \"yesterday\", \"tomorrow\", \"last week\", \"this month\", "
        "\"next 3 days\", or an upcoming weekday — resolve it to absolute "
        "calendar dates RELATIVE TO THE CURRENT DATE ABOVE before stating any "
        "date or calling any tool. A single day uses the same start and end "
        "date; a \"week\" is Monday–Sunday. Never infer the current date from "
        "your training data — always use CURRENT DATE above."
    )


@dataclass
class MCPToolCallResult:
    tool_name: str
    ok: bool
    output: str


class _TurnToolCache:
    """Turn-scoped, strictly-keyed memo for live tool / guide-content calls.

    A fresh instance is created per ``respond()`` invocation (one assistant
    turn): there is NO cross-turn, global, or module-level state. Within a turn,
    the SAME tool invoked with identical args is served from cache so the agent
    loop (and the deterministic guide pre-fetch) never repeat the same live MCP
    call. Volatile data (e.g. stock levels) can change between turns, so the
    cache deliberately dies at the end of the turn.

    SECURITY (UAC3b.2): the cache key is
    ``sha256(user_id ∥ conversation_id ∥ turn_id ∥ tool_name ∥ sha256(canonical_sorted_args))``.
    Because the principal (``user_id``), thread (``conversation_id``) and turn
    (``turn_id``) are baked into every key, two different users / contacts /
    turns can NEVER collide on a cache entry even if they call the identical
    tool with identical args — cross-principal sharing is structurally
    impossible, not merely avoided by convention.
    """

    _SEP = "\x1f"  # unit separator — cannot appear in JSON / identifiers

    def __init__(self, *, user_id: str | None, conversation_id: str | None, turn_id: str | None):
        self.user_id = str(user_id or "")
        self.conversation_id = str(conversation_id or "")
        self.turn_id = str(turn_id or "")
        self._store: dict[str, str] = {}
        # Observability (UAC3b.4): live_calls counts loader invocations (real
        # tool calls), hits counts cache-served calls.
        self.live_calls = 0
        self.hits = 0

    @staticmethod
    def _args_hash(args: dict[str, Any] | None) -> str:
        canonical = json.dumps(
            args or {}, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def key(self, tool_name: str, args: dict[str, Any] | None) -> str:
        raw = self._SEP.join(
            [
                self.user_id,
                self.conversation_id,
                self.turn_id,
                str(tool_name or ""),
                self._args_hash(args),
            ]
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def get_or_call(
        self,
        tool_name: str,
        args: dict[str, Any] | None,
        loader: Callable[[], str],
    ) -> str:
        """Return the cached result for ``(tool_name, args)`` within this turn,
        invoking ``loader`` (the live call) exactly once on the first miss."""
        k = self.key(tool_name, args)
        if k in self._store:
            self.hits += 1
            return self._store[k]
        out = loader()
        self.live_calls += 1
        self._store[k] = out
        return out


class MCPRuntimeClient:
    """Minimal JSON-RPC client for FastMCP streamable HTTP endpoint."""

    def __init__(self, base_url: str, timeout_seconds: int = 20):
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def _rpc(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        rid = str(uuid.uuid4())
        payload = {"jsonrpc": "2.0", "id": rid, "method": method, "params": params or {}}
        with httpx.Client(timeout=self.timeout_seconds) as client:
            resp = client.post(
                self.base_url,
                json=payload,
                headers={
                    # FastMCP streamable HTTP requires both content types in Accept.
                    "Accept": "application/json, text/event-stream",
                    "Content-Type": "application/json",
                },
            )
            resp.raise_for_status()
            body = self._decode_streamable_body(resp)
        if isinstance(body, dict) and "error" in body:
            raise RuntimeError(str(body.get("error")))
        if not isinstance(body, dict):
            raise RuntimeError("Invalid MCP response payload")
        return body.get("result") or {}

    def _decode_streamable_body(self, resp: httpx.Response) -> dict[str, Any]:
        content_type = (resp.headers.get("content-type") or "").lower()
        if "text/event-stream" not in content_type:
            return resp.json()

        # Streamable HTTP MCP commonly returns SSE frames:
        # event: message
        # data: {...json-rpc...}
        data_lines = []
        for raw_line in resp.text.splitlines():
            line = raw_line.strip()
            if not line.startswith("data:"):
                continue
            data_lines.append(line[5:].strip())
        if not data_lines:
            raise RuntimeError("MCP SSE response missing data frame")
        try:
            return json.loads(data_lines[-1])
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Invalid MCP SSE JSON payload: {exc}") from exc

    def list_tools(self) -> set[str]:
        return set(self.list_tools_with_schema().keys())

    def list_tools_with_schema(self) -> dict[str, dict[str, Any]]:
        """MCP tools/list: name -> {description, inputSchema} for LLM argument synthesis."""
        result = self._rpc("tools/list", {})
        tools = result.get("tools") or []
        out: dict[str, dict[str, Any]] = {}
        for tool in tools:
            if not isinstance(tool, dict) or not tool.get("name"):
                continue
            name = str(tool["name"])
            schema = tool.get("inputSchema")
            if schema is None:
                schema = tool.get("input_schema") or {}
            out[name] = {
                "description": tool.get("description") or "",
                "inputSchema": schema if isinstance(schema, dict) else {},
            }
        return out

    def call_tool(self, tool_name: str, args: dict[str, Any]) -> str:
        result = self._rpc("tools/call", {"name": tool_name, "arguments": args})
        if "content" in result and isinstance(result["content"], list):
            chunks = []
            for item in result["content"]:
                if isinstance(item, dict) and isinstance(item.get("text"), str):
                    chunks.append(item["text"])
            if chunks:
                return "\n".join(chunks)
        return json.dumps(result)


class AIAssistantConfigService:
    def __init__(self, db: Session):
        self.db = db

    def _ensure_singleton(self) -> AIAssistantConfig:
        row = self.db.query(AIAssistantConfig).order_by(AIAssistantConfig.created_at.asc()).first()
        if row:
            return row
        row = AIAssistantConfig()
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def get(self) -> AIAssistantConfig:
        return self._ensure_singleton()

    def update(self, data: AIAssistantConfigUpdate, user_id: str) -> AIAssistantConfig:
        row = self._ensure_singleton()
        row.provider = data.provider.strip()
        row.model = data.model.strip()
        row.temperature = data.temperature
        row.system_prompt = data.system_prompt or ""
        row.enabled_tools = list(data.enabled_tools or [])
        row.rag_enabled = bool(data.rag_enabled)
        row.is_enabled = bool(data.is_enabled)
        row.updated_by_user_id = user_id
        if data.api_key is not None and data.api_key.strip():
            # Stored in this field for compatibility with IJM schema naming.
            row.api_key_ciphertext = data.api_key.strip()
        self.db.commit()
        self.db.refresh(row)
        return row

    def to_response_dict(self, row: AIAssistantConfig) -> dict[str, Any]:
        return {
            "id": str(row.id),
            "provider": row.provider,
            "model": row.model,
            "temperature": row.temperature,
            "system_prompt": row.system_prompt,
            "api_key_masked": _mask_key(row.api_key_ciphertext),
            "enabled_tools": list(row.enabled_tools or []),
            "rag_enabled": bool(row.rag_enabled),
            "is_enabled": bool(row.is_enabled),
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }


class AIAssistantGovernanceService:
    def __init__(self, db: Session):
        self.db = db

    def build_auth_context(self, user_id: str) -> AIAssistantAuthContext:
        perm_service = UserPermissionService(self.db)
        role_ids = perm_service.get_user_role_ids(user_id)
        perms = sorted(perm_service.get_user_permission_slugs(user_id))
        if tenant_has_any_module_row(self.db, DEFAULT_TENANT_ID):
            enabled_modules = sorted(get_enabled_module_keys(self.db, DEFAULT_TENANT_ID))
        else:
            enabled_modules = []
        return AIAssistantAuthContext(
            user_id=user_id,
            role_ids=role_ids,
            permission_slugs=perms,
            enabled_modules=enabled_modules,
        )

    def log_denial(
        self,
        user_id: str | None,
        conversation_id: str | None,
        event_type: str,
        *,
        module_key: str | None = None,
        permission_slug: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.db.add(
            AIAssistantGovernanceEvent(
                user_id=user_id,
                conversation_id=conversation_id,
                event_type=event_type,
                module_key=module_key,
                permission_slug=permission_slug,
                details=details or {},
            )
        )
        self.db.commit()


class AIAssistantChatService:
    def __init__(self, db: Session):
        self.db = db
        self.cfg = AIAssistantConfigService(db)
        self.gov = AIAssistantGovernanceService(db)

    def list_conversations(
        self,
        user_id: str,
        *,
        q: str | None = None,
        limit: int = 100,
    ) -> list[AIAssistantConversation]:
        query = self.db.query(AIAssistantConversation).filter(
            AIAssistantConversation.user_id == user_id
        )
        if q and q.strip():
            like = f"%{q.strip()}%"
            query = query.filter(AIAssistantConversation.title.ilike(like))
        return (
            query.order_by(AIAssistantConversation.updated_at.desc())
            .limit(max(1, min(int(limit or 100), 200)))
            .all()
        )

    def list_mcp_tools(self) -> list[str]:
        """Fetch current tool names from MCP runtime for settings UI sync."""
        mcp = MCPRuntimeClient(settings.ai_assistant_mcp_url, timeout_seconds=settings.ai_assistant_mcp_timeout_seconds)
        tool_names = sorted(mcp.list_tools())
        logger.info("AI assistant MCP tool catalog fetched count=%s", len(tool_names))
        return tool_names

    def get_or_create_conversation(self, user_id: str, conversation_id: str | None, initial_message: str) -> AIAssistantConversation:
        if conversation_id:
            row = (
                self.db.query(AIAssistantConversation)
                .filter(AIAssistantConversation.id == conversation_id, AIAssistantConversation.user_id == user_id)
                .first()
            )
            if row:
                return row
        title = initial_message.strip()[:120] or "New chat"
        row = AIAssistantConversation(user_id=user_id, title=title)
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def list_messages(self, conversation_id: str, user_id: str) -> list[AIAssistantMessage]:
        conv = (
            self.db.query(AIAssistantConversation)
            .filter(AIAssistantConversation.id == conversation_id, AIAssistantConversation.user_id == user_id)
            .first()
        )
        if not conv:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
        return (
            self.db.query(AIAssistantMessage)
            .filter(AIAssistantMessage.conversation_id == conversation_id)
            .order_by(AIAssistantMessage.created_at.asc())
            .all()
        )

    def append_message(self, conversation_id: str, role: str, content: str, metadata_json: dict[str, Any] | None = None) -> AIAssistantMessage:
        msg = AIAssistantMessage(conversation_id=conversation_id, role=role, content=content, metadata_json=metadata_json or {})
        self.db.add(msg)
        self.db.commit()
        self.db.refresh(msg)
        return msg

    def respond(
        self,
        *,
        user_id: str,
        conversation_id: str | None,
        message: str,
        page_snapshot: PageSnapshotPayload | None = None,
    ) -> tuple[AIAssistantConversation, AIAssistantMessage]:
        request_started = time.perf_counter()
        if not settings.ai_assistant_enabled:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI assistant feature is disabled")
        config = self.cfg.get()
        if not config.is_enabled:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="AI assistant is disabled")
        logger.info(
            "AI assistant request started user_id=%s conversation_id=%s message_len=%s",
            user_id,
            conversation_id,
            len(message or ""),
        )
        conv = self.get_or_create_conversation(user_id, conversation_id, message)

        recent_count = (
            self.db.query(AIAssistantMessage.id)
            .filter(
                AIAssistantMessage.conversation_id == conv.id,
                AIAssistantMessage.created_at >= (func.now() - text("interval '1 minute'")),
            )
            .count()
        )
        if recent_count > 20:
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Rate limit exceeded, try again soon.")

        # Persist a truncated copy of the page snapshot on the user message for
        # later debugging / replay.
        user_meta: dict[str, Any] = {}
        if page_snapshot is not None:
            snapshot_meta: dict[str, Any] = {
                "path": (page_snapshot.path or "")[:500],
                "search": (page_snapshot.search or "")[:500],
                "title": (page_snapshot.title or "")[:255],
                "visible_text": (page_snapshot.visible_text or "")[:1000],
            }
            if page_snapshot.entity is not None:
                snapshot_meta["entity"] = {
                    "entity_type": page_snapshot.entity.entity_type,
                    "id": page_snapshot.entity.id,
                }
            user_meta["page_snapshot"] = snapshot_meta

        user_msg = self.append_message(conv.id, "user", message, metadata_json=user_meta or None)
        logger.info("AI assistant user message appended conversation_id=%s", conv.id)

        # Item 3b: turn-scoped, strictly-keyed tool/guide result cache. Created
        # fresh per respond() so it can never outlive the turn or leak across
        # users/threads (key includes user_id + conversation_id + turn_id). The
        # turn id is this user message's id — unique per turn.
        turn_cache = _TurnToolCache(
            user_id=user_id,
            conversation_id=str(conv.id),
            turn_id=str(user_msg.id),
        )
        history_rows = (
            self.db.query(AIAssistantMessage)
            .filter(AIAssistantMessage.conversation_id == conv.id)
            .order_by(AIAssistantMessage.created_at.asc())
            .limit(20)
            .all()
        )
        logger.info("AI assistant history loaded conversation_id=%s history_count=%s", conv.id, len(history_rows))
        auth_ctx = self.gov.build_auth_context(user_id)
        if not auth_ctx.permission_slugs:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No permissions available for AI assistant.")
        logger.info(
            "AI assistant auth context built user_id=%s permissions=%s",
            user_id,
            len(auth_ctx.permission_slugs),
        )

        reformulate_started = time.perf_counter()
        standalone_query = self._reformulate_query(
            config=config,
            history=history_rows,
            user_message=message,
        )
        reformulate_ms = (time.perf_counter() - reformulate_started) * 1000
        logger.info(
            "AI assistant query reformulated conversation_id=%s original_len=%s standalone_len=%s elapsed_ms=%.1f standalone=%s",
            conv.id,
            len(message or ""),
            len(standalone_query or ""),
            reformulate_ms,
            (standalone_query or "")[:200],
        )

        resolve_started = time.perf_counter()
        try:
            resolution = resolve_references(self.db, f"{message}\n{standalone_query or ''}")
        except Exception:
            logger.exception("Entity resolver failed; continuing without resolved references")
            resolution = ResolutionResult(tokens=[], resolutions=[], elapsed_ms=0.0)
        resolve_ms = (time.perf_counter() - resolve_started) * 1000
        logger.info(
            "AI assistant entity resolution conversation_id=%s tokens=%s resolved=%s unresolved=%s elapsed_ms=%.1f",
            conv.id,
            resolution.tokens,
            [r.token for r in resolution.resolutions if r.resolved],
            resolution.unresolved_tokens,
            resolve_ms,
        )

        # Augment the query sent to RAG so the tool picker sees entity-type hints.
        rag_query = standalone_query
        query_hint = resolution.to_query_hint()
        if query_hint:
            rag_query = f"{standalone_query}\n{query_hint}"

        rag_started = time.perf_counter()
        selected_tools, sources = self._rag_select_tools(
            standalone_query=rag_query,
            enabled_tools=list(config.enabled_tools or []),
            top_k=max(1, int(getattr(settings, "ai_assistant_rag_top_k", 3))),
        )
        rag_ms = (time.perf_counter() - rag_started) * 1000
        logger.info(
            "AI assistant RAG phase finished conversation_id=%s selected_tools=%s elapsed_ms=%.1f",
            conv.id,
            len(selected_tools),
            rag_ms,
        )

        # Deterministic pre-route (PLAN Q6): when the user is viewing a specific
        # record AND the question is record-class, bypass the agent loop and
        # answer from the deterministic assembler. RBAC parity with the HTTP
        # route is enforced inline (§3.5) since this is an internal service call
        # without the FastAPI dependency. Any failure degrades to the agent loop.
        # Assemble the record context whenever the user is viewing a permitted
        # record — REGARDLESS of the classifier. The classifier only decides
        # whether to short-circuit (render) or fall through to the agent loop;
        # either way the facts are injected, so transient classifier noise can
        # never produce an ungrounded hallucination for a record-ish question.
        record_ctx = None
        is_record_class = False
        if page_snapshot is not None and page_snapshot.entity is not None:
            from app.services.record_context_service import (
                RecordContextService,
                record_context_view_permission,
            )

            try:
                # Per-entity RBAC parity with the HTTP route: when the entity
                # type requires a view permission, enforce it; None => any
                # authenticated bubble user may read the record context.
                required_slug = record_context_view_permission(
                    page_snapshot.entity.entity_type
                )
                permitted = required_slug is None or UserPermissionService(
                    self.db
                ).check_user_has_permission(user_id, required_slug)
                if permitted:
                    record_ctx = RecordContextService(self.db).assemble(
                        page_snapshot.entity.entity_type,
                        page_snapshot.entity.id,
                    )
            except HTTPException:
                # 400 (unsupported) / 404 (not found) → degrade gracefully.
                record_ctx = None
            except Exception:
                logger.exception(
                    "Record-context assembly failed; falling back to agent loop"
                )
                record_ctx = None
            if record_ctx is not None:
                # Classify on the ORIGINAL message, not the reformulated
                # standalone_query: reformulation can hallucinate unrelated
                # context (e.g. expanding "this" into "the delivery order") which
                # would mis-route a record question into the agent loop. The
                # user's own words carry the intent; the render path resolves
                # specifics from the injected facts.
                #
                # UAC3c: the classifier LLM call runs ONLY inside this branch —
                # i.e. only when a record was actually assembled for the page.
                # No record context (dashboard/settings/list pages) => we never
                # get here, so no classifier call / LLM round-trip is made.
                is_record_class = self.intent_is_record_class(
                    message, has_record_context=True
                )

        agent_started = time.perf_counter()
        if record_ctx is not None and is_record_class:
            response_text, tool_calls, token_usage = self._render_record_answer(
                config=config,
                history=history_rows,
                user_message=message,
                record_ctx=record_ctx,
                page_snapshot=page_snapshot,
                turn_cache=turn_cache,
            )
        else:
            response_text, tool_calls, token_usage = self._run_agent_loop(
                config=config,
                history=history_rows,
                user_message=message,
                standalone_query=standalone_query,
                selected_tools=selected_tools,
                sources=sources,
                resolution=resolution,
                page_snapshot=page_snapshot,
                user_id=user_id,
                conversation_id=str(conv.id),
                user_message_id=str(user_msg.id),
                record_ctx=record_ctx,
                turn_cache=turn_cache,
            )
        agent_ms = (time.perf_counter() - agent_started) * 1000
        logger.info(
            "AI assistant agent phase finished conversation_id=%s response_len=%s tool_calls=%s "
            "elapsed_ms=%.1f tool_cache_live=%s tool_cache_hits=%s",
            conv.id,
            len(response_text or ""),
            len(tool_calls),
            agent_ms,
            turn_cache.live_calls,
            turn_cache.hits,
        )
        # Post-process: when the agent rephrased a how-to answer and dropped
        # inline markdown links from the guide, re-wrap any bold menu paths
        # with their canonical FE route links. Cheap deterministic safety net
        # so the LLM doesn't have to be perfect about preserving links.
        # `extra_map` adds button-level deep links (e.g. `?guide_target=...`)
        # that the guide author wrote inline.
        guide_link_map = self._extract_guide_link_map(tool_calls)
        response_text = self._inject_route_links(response_text, guide_link_map)
        # Belt-and-suspenders: strip any internal Outline URL the model still
        # managed to emit (the guide tool-result is already redacted upstream,
        # but the model could regurgitate one from history). In-app route /
        # `?guide_target` links are untouched.
        response_text = self._strip_outline_urls(response_text)
        links = self._extract_links_from_text(response_text)

        # Smart suggestions: best-effort follow-up question generation. Always
        # returns a list (possibly empty); never blocks the assistant reply.
        suggestions = self._generate_suggestions(
            config=config,
            history=history_rows,
            user_message=message,
            assistant_reply=response_text,
        )

        # was_answered = reply non-empty AND not a deterministic fallback.
        is_fallback = self._is_fallback_reply(response_text, tool_calls)
        was_answered = bool((response_text or "").strip()) and not is_fallback

        meta = {
            "links": links,
            "sources": sources,
            "selected_tools": selected_tools,
            "tool_calls": [{"tool_name": c.tool_name, "ok": c.ok} for c in tool_calls],
            "entity_resolution": resolution.as_dict(),
            "suggestions": suggestions,
        }
        if page_snapshot is not None:
            assistant_snapshot_meta: dict[str, Any] = {
                "path": (page_snapshot.path or "")[:500],
                "title": (page_snapshot.title or "")[:255],
                "visible_text": (page_snapshot.visible_text or "")[:1000],
            }
            if page_snapshot.entity is not None:
                assistant_snapshot_meta["entity"] = {
                    "entity_type": page_snapshot.entity.entity_type,
                    "id": page_snapshot.entity.id,
                }
            meta["page_snapshot"] = assistant_snapshot_meta
        assistant_msg = self.append_message(conv.id, "assistant", response_text, metadata_json=meta)
        total_ms = (time.perf_counter() - request_started) * 1000

        # Usage logging — best effort, never break the response on telemetry
        # failure.
        try:
            self.db.add(
                AIAssistantUsageLog(
                    user_id=user_id,
                    feature="ai_assistant",
                    conversation_id=str(conv.id),
                    message_id=str(assistant_msg.id),
                    model=config.model,
                    provider=config.provider,
                    prompt_tokens=int(token_usage.get("prompt_tokens", 0) or 0),
                    completion_tokens=int(token_usage.get("completion_tokens", 0) or 0),
                    total_tokens=int(token_usage.get("total_tokens", 0) or 0),
                    tool_calls_count=len(tool_calls or []),
                    response_time_ms=int(total_ms),
                    was_answered=was_answered,
                )
            )
            self.db.commit()
        except Exception:
            logger.exception("Failed to insert ai_assistant_usage_logs row")
            self.db.rollback()

        # Wishlist tagging when the turn was unanswered.
        if not was_answered:
            try:
                from app.services.ai_wishlist_service import AiWishlistService

                AiWishlistService(self.db).tag_unanswered(str(assistant_msg.id))
            except Exception:
                logger.exception("Failed to tag unanswered query message_id=%s", assistant_msg.id)

        logger.info(
            "AI assistant request completed conversation_id=%s assistant_message_id=%s total_elapsed_ms=%.1f was_answered=%s",
            conv.id,
            assistant_msg.id,
            total_ms,
            was_answered,
        )
        return conv, assistant_msg

    # ---------- n8n-style pipeline: reformulate → RAG → agent loop ----------

    def _reformulate_query(
        self,
        *,
        config: AIAssistantConfig,
        history: list[AIAssistantMessage],
        user_message: str,
    ) -> str:
        """Rewrite the latest user message into a self-contained query using recent history.

        Mirrors the n8n `sub-query-reformulator` LLM chain: takes a short history window
        plus the current message and returns a standalone search query for RAG + the agent.
        Falls back to the raw message if the LLM call fails.
        """
        raw = (user_message or "").strip()
        if not raw:
            return raw
        api_key = config.api_key_ciphertext or settings.openai_api_key
        if not api_key:
            return raw
        turns = max(1, int(getattr(settings, "ai_assistant_reformulator_history_turns", 6)))
        convo_lines: list[str] = []
        for msg in history[-(turns * 2):]:
            if msg.role not in {"user", "assistant"}:
                continue
            text_piece = (msg.content or "").strip().replace("\n", " ")
            if not text_piece:
                continue
            convo_lines.append(f"{msg.role}: {text_piece[:500]}")
        system = (
            "You are a query reformulator. Rewrite the latest user turn into a single, "
            "self-contained natural-language question that preserves all important entities "
            "(ids, codes, dates, names) from the prior conversation.\n"
            "- Resolve pronouns/ellipsis using the history.\n"
            "- Expand common CRM abbreviations on first mention so downstream RAG can match: "
            "DO -> delivery order, GRN -> goods received note, SPO -> supplier purchase order, "
            "PO -> purchase order, SO -> sales order, PR -> purchase request, SKU -> product. "
            "Keep the original abbreviation alongside the expansion (e.g. 'delivery order (DO)').\n"
            "- Keep it concise (<= 2 sentences).\n"
            "- If the turn names a relative date/period (today, last week, this "
            "month, etc.), rewrite it as the absolute calendar date(s) so "
            "downstream tools filter the right range.\n"
            "- Do not answer the question. Output plain text only, no quotes, no prefix.\n\n"
            + _current_date_directive()
        )
        user_block = (
            "Conversation so far (may be empty):\n"
            f"{chr(10).join(convo_lines) if convo_lines else '(none)'}\n\n"
            f"Latest user turn:\n{raw}\n\n"
            "Reformulated standalone query:"
        )
        try:
            provider = get_provider(config.provider, api_key, config.model)
            result = provider.chat(
                [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_block},
                ],
                temperature=0.0,
                model=config.model,
                max_tokens=256,
            )
            reformulated = (result.content or "").strip().strip('"').strip()
            return reformulated or raw
        except Exception:
            logger.exception("AI assistant reformulator failed; using raw user message")
            return raw

    def _rag_select_tools(
        self,
        *,
        standalone_query: str,
        enabled_tools: list[str],
        top_k: int,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Top-K MCP tool candidates by embedding similarity on the reformulated query."""
        logger.info(
            "AI assistant RAG started query_len=%s enabled_tools=%s top_k=%s",
            len(standalone_query or ""),
            len(enabled_tools),
            top_k,
        )
        embed_started = time.perf_counter()
        query_embedding = self._embed_query(standalone_query)
        logger.info(
            "AI assistant embedding generated elapsed_ms=%.1f",
            (time.perf_counter() - embed_started) * 1000,
        )

        search_started = time.perf_counter()
        candidates = EmbeddingReadService(self.db).search_tool_candidates(
            query_embedding,
            query=standalone_query,
            top_k=max(top_k, 5),
            include_planned=False,
        )
        logger.info(
            "AI assistant tool candidates fetched count=%s elapsed_ms=%.1f",
            len(candidates),
            (time.perf_counter() - search_started) * 1000,
        )
        if enabled_tools:
            allowed = set(enabled_tools)
            candidates = [c for c in candidates if str(c.get("tool_name")) in allowed]
            logger.info("AI assistant candidates filtered by enabled tools remaining=%s", len(candidates))
        selected_tools = candidates[:top_k]
        logger.info(
            "AI assistant selected tools=%s",
            [
                {
                    "tool_name": c.get("tool_name"),
                    "score": c.get("score"),
                    "missing_params": c.get("missing_params") or [],
                    "why_selected": (str(c.get("why_selected") or "")[:120]),
                }
                for c in selected_tools
            ],
        )
        sources = [
            {
                "title": c.get("tool_name"),
                "chunk_text": c.get("chunk_text"),
                "score": c.get("score"),
                "why_selected": c.get("why_selected"),
            }
            for c in selected_tools
        ]
        return selected_tools, sources

    # ---------- Agent loop (OpenAI function calling → MCP tools) ----------

    def _mcp_schema_to_openai_tool(self, name: str, meta: dict[str, Any]) -> dict[str, Any]:
        """Wrap an MCP tool (name, description, inputSchema) as an OpenAI function tool.

        ``contact_id`` / ``space_id`` are MCP-server guard params required for
        n8n/WhatsApp callers but irrelevant for the in-app AI assistant — the
        runtime force-empties them in ``_run_agent_loop`` before calling MCP.
        Surfacing them to the LLM only causes it to ask the user for them
        instead of invoking the tool, so strip them from the schema here.
        """
        schema = meta.get("inputSchema") if isinstance(meta.get("inputSchema"), dict) else {}
        if not schema or not isinstance(schema, dict):
            parameters: dict[str, Any] = {"type": "object", "properties": {}}
        else:
            parameters = dict(schema)
            parameters.setdefault("type", "object")
            parameters.setdefault("properties", {})
        props = dict(parameters.get("properties") or {})
        for guard in ("contact_id", "space_id"):
            props.pop(guard, None)
        parameters["properties"] = props
        required = [r for r in (parameters.get("required") or []) if r not in ("contact_id", "space_id")]
        parameters["required"] = required
        return {
            "type": "function",
            "function": {
                "name": name,
                "description": (meta.get("description") or "")[:4000],
                "parameters": parameters,
            },
        }

    # Cheap gate for "should I deterministically pre-fetch a user guide?".
    # Targets how-to / explain phrasings. False positives are harmless — the
    # guide lookup just returns no match and nothing is injected. This is a
    # retrieval trigger, NOT answer-tuning (the LLM still does the semantic work).
    _GUIDE_QUESTION_TRIGGERS = (
        "how do i", "how to", "how can i", "how does", "how should i", "how would i",
        "what does", "what do the", "what is this", "what is the purpose", "what are the",
        "what if i", "what happens when i", "explain", "steps to", "steps for",
        "guide me", "walk me through", "which button", "what button", " for?",
    )

    def _is_guide_question(self, message: str) -> bool:
        m = (message or "").strip().lower()
        if not m:
            return False
        return any(t in m for t in self._GUIDE_QUESTION_TRIGGERS)

    def _cached_tool_call(
        self,
        turn_cache: _TurnToolCache | None,
        client: MCPRuntimeClient,
        tool_name: str,
        args: dict[str, Any],
    ) -> str:
        """Invoke an MCP tool, deduplicated within the turn via ``turn_cache``.

        When ``turn_cache`` is None (e.g. a direct caller that passes no cache),
        the call is made directly — behavior is identical to calling
        ``client.call_tool()``. The cache stores the RAW tool output so any
        downstream transform (e.g. Outline-URL redaction) runs identically on a
        cached or freshly-fetched result.
        """
        if turn_cache is None:
            return client.call_tool(tool_name, args=args)
        return turn_cache.get_or_call(
            tool_name, args, lambda: client.call_tool(tool_name, args=args)
        )

    def _run_agent_loop(
        self,
        *,
        config: AIAssistantConfig,
        history: list[AIAssistantMessage],
        user_message: str,
        standalone_query: str,
        selected_tools: list[dict[str, Any]],
        sources: list[dict[str, Any]],
        resolution: ResolutionResult | None = None,
        page_snapshot: PageSnapshotPayload | None = None,
        user_id: str | None = None,
        conversation_id: str | None = None,
        user_message_id: str | None = None,
        record_ctx: dict[str, Any] | None = None,
        turn_cache: _TurnToolCache | None = None,
    ) -> tuple[str, list[MCPToolCallResult], dict[str, int]]:
        """Orchestrator loop: LLM chooses/invokes MCP tools via function-calling, then answers.

        Returns ``(response_text, tool_calls, token_usage_dict)`` where
        ``token_usage_dict`` aggregates ``prompt_tokens`` / ``completion_tokens`` /
        ``total_tokens`` across every provider call made by this turn.
        """
        api_key = config.api_key_ciphertext or settings.openai_api_key
        tool_calls_log: list[MCPToolCallResult] = []
        token_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

        mcp = MCPRuntimeClient(
            settings.ai_assistant_mcp_url,
            timeout_seconds=settings.ai_assistant_mcp_timeout_seconds,
        )
        try:
            tool_catalog = mcp.list_tools_with_schema()
        except Exception as exc:
            logger.exception("Failed listing MCP tools")
            err_log = [MCPToolCallResult("mcp_error", False, str(exc))]
            return (
                self._deterministic_fallback(err_log),
                err_log,
                token_usage,
            )
        available = set(tool_catalog.keys())

        bound_tool_names: list[str] = []
        openai_tools: list[dict[str, Any]] = []
        for candidate in selected_tools:
            name = str(candidate.get("tool_name") or "")
            if not name or name not in available:
                continue
            openai_tools.append(self._mcp_schema_to_openai_tool(name, tool_catalog[name]))
            bound_tool_names.append(name)
        # Always make the user guide reader available — the USER GUIDE PROTOCOL
        # requires calling it for any "how do I / how to" question, but RAG does
        # not reliably rank it into the selected set, which left how-to answers
        # without the guide's steps + clickable button deep-links (and risked the
        # agent reaching for an unrelated tool). Bind it unconditionally.
        if "user_guides_read" in available and "user_guides_read" not in bound_tool_names:
            openai_tools.append(
                self._mcp_schema_to_openai_tool("user_guides_read", tool_catalog["user_guides_read"])
            )
            bound_tool_names.append("user_guides_read")
        logger.info(
            "AI assistant agent tools bound count=%s names=%s",
            len(bound_tool_names),
            bound_tool_names,
        )

        if not api_key:
            logger.warning("AI assistant agent has no API key; returning deterministic fallback")
            return self._deterministic_fallback(tool_calls_log), tool_calls_log, token_usage

        try:
            provider: LLMProvider = get_provider(config.provider, api_key, config.model)
        except Exception as exc:
            logger.exception("AI assistant agent failed to instantiate provider")
            err_log = [MCPToolCallResult("provider_error", False, str(exc))]
            return self._deterministic_fallback(err_log), err_log, token_usage

        system = _html_to_text(config.system_prompt or "").strip() or self._default_system_prompt()
        # Always append the user-guide protocol so admins who set a custom
        # system_prompt still get the search-then-read-then-answer behavior
        # for how-to questions. Idempotent: skipped when the protocol header
        # is already in the prompt.
        if "USER GUIDE PROTOCOL" not in system:
            system = system.rstrip() + "\n\n" + self._user_guide_protocol_addendum()
        source_context = "\n".join(
            [f"- {s.get('title')}: {str(s.get('why_selected') or '')[:200]}" for s in sources]
        )
        messages: list[dict[str, Any]] = [{"role": "system", "content": system}]
        messages.append({"role": "system", "content": _current_date_directive()})
        if page_snapshot is not None:
            page_block = (
                "The user is currently viewing this page. Identify what KIND of record this "
                "is from the page title and path (e.g. a goods-received note, stock balance, "
                "promotion, product, form, attachment) and refer to it accurately — do not "
                "assume it is an order or sales document.\n"
                "IMPORTANT: for a question about the VALUE of a field shown below (a status, "
                "quantity, name, date, amount), answer DIRECTLY from the page — do NOT call a "
                "data/catalog tool to look it up. BUT if the user asks how to do something OR "
                "what a button / control / feature does or is for (e.g. 'how do I…', 'how "
                "to…', 'what does the Extend button do', 'what is this for', 'explain …'), you "
                "MUST call `user_guides_read` to ground the answer in the guide and include "
                "its clickable button links — do NOT answer such questions from general "
                "knowledge, even if the button is visible here. For the `query`, use a SHORT "
                "keyword phrase naming the button/feature plus its area (e.g. 'takeover task', "
                "'extend deadline task', 'reassign task', 'download complaint pdf') — NOT a "
                "full sentence; short keyword queries match the guides far better. If the "
                "first lookup returns no match, retry ONCE with just the key noun (e.g. "
                "'takeover').\n\n"
                f"--- Page: {page_snapshot.title} ({page_snapshot.path}{page_snapshot.search}) ---\n"
                f"{page_snapshot.visible_text}\n"
                "--- End page ---"
            )
            messages.append({"role": "system", "content": page_block})
        if record_ctx is not None:
            # The user is on a specific record. Inject its authoritative facts so
            # that even when this fallback path runs (e.g. the question wasn't
            # classified record-class), the model answers from real record data
            # instead of guessing or calling unrelated catalog tools.
            facts = json.dumps(record_ctx, ensure_ascii=False, indent=2)
            messages.append(
                {
                    "role": "system",
                    "content": (
                        "Authoritative facts for the record the user is viewing. "
                        "Prefer these over any tool when the question is about this "
                        "record; quote `display_ref`, never a UUID.\n"
                        f"--- Record facts ---\n{facts}\n--- End record facts ---"
                    ),
                }
            )
        # Deterministic guide pre-fetch. The LLM is unreliable about calling
        # user_guides_read for how-to / explain questions — it may skip it, or
        # expand the query into a verbose sentence Outline doesn't match — which
        # left such questions ungrounded and missing the clickable button links.
        # The user's RAW message matches the guides well, so fetch HERE and inject
        # it; the result is added to tool_calls_log so the deep links get
        # re-injected. A miss / error simply injects nothing (harmless).
        if self._is_guide_question(user_message):
            try:
                pf = MCPRuntimeClient(
                    settings.ai_assistant_mcp_url,
                    timeout_seconds=settings.ai_assistant_mcp_timeout_seconds,
                )
                pf_out = self._cached_tool_call(
                    turn_cache,
                    pf,
                    "user_guides_read",
                    {"query": user_message, "contact_id": "", "space_id": ""},
                )
                # Only inject a REAL guide hit. NO_MATCH / OUTLINE_ERROR are not
                # flagged by _tool_output_is_error, and injecting them would tell
                # the model "no guide available" — the opposite of the goal.
                pf_hit = False
                try:
                    pf_payload = json.loads(pf_out)
                    pf_hit = bool(pf_payload.get("id") and pf_payload.get("text")) and not pf_payload.get("code")
                except Exception:
                    pf_hit = False
                if pf_hit:
                    # Redact the internal Outline URL before the guide body ever
                    # reaches the model context, so it cannot be echoed back.
                    pf_clean = self._redact_guide_tool_output(pf_out)
                    tool_calls_log.append(MCPToolCallResult("user_guides_read", True, pf_clean))
                    messages.append(
                        {
                            "role": "system",
                            "content": (
                                "The user is asking how to do something or what a control "
                                "does. Answer from this guide and KEEP its inline markdown "
                                "links EXACTLY as written (they let the user click straight to "
                                "the button). Do NOT say no guide is available. Never mention "
                                "or link to any external documentation URL.\n"
                                f"--- Guide ---\n{pf_clean[:6000]}\n--- End guide ---"
                            ),
                        }
                    )
            except Exception:
                logger.warning("guide pre-fetch failed; agent may still call the tool")
        for msg in history[-6:]:
            if msg.role in {"user", "assistant"} and (msg.content or "").strip():
                messages.append({"role": msg.role, "content": msg.content})
        resolution_block = resolution.to_prompt_block() if resolution else ""
        unresolved_tokens = resolution.unresolved_tokens if resolution else []
        ambiguous_tokens = resolution.ambiguous_tokens if resolution else []
        resolution_section = (
            f"{resolution_block}\n\n" if resolution_block else ""
        )
        extra_rules = ""
        if unresolved_tokens:
            extra_rules += (
                "\nCRITICAL: The following reference codes in the user's message do NOT exist in "
                "the system: "
                + ", ".join(f'"{t}"' for t in unresolved_tokens)
                + ". Do NOT call any tool using these codes. Reply to the user that no record was "
                "found for those codes."
            )
        if ambiguous_tokens:
            extra_rules += (
                "\nCRITICAL: The following reference codes are AMBIGUOUS (multiple candidates): "
                + ", ".join(f'"{t}"' for t in ambiguous_tokens)
                + ". Do NOT call any tool yet. Ask the user to pick one of the candidates listed "
                "in the Ambiguous references block above."
            )
        selected_do_codes: list[str] = []
        if resolution:
            for tr in resolution.resolutions:
                if not tr.resolved:
                    continue
                for match in tr.matches:
                    if str(getattr(match, "entity_type", "")).strip() == "customer_order":
                        code = str(getattr(match, "canonical_code", "")).strip()
                        if code and code not in selected_do_codes:
                            selected_do_codes.append(code)
        if selected_do_codes:
            extra_rules += (
                "\nCRITICAL: Selected order(s) already resolved in context: "
                + ", ".join(f'"{c}"' for c in selected_do_codes)
                + ". In complaint flow, treat these as delivery order number(s) already captured. "
                "Do NOT ask the user to key in delivery order number again unless they ask to change it."
            )
        messages.append(
            {
                "role": "user",
                "content": (
                    f"User question (original):\n{user_message}\n\n"
                    f"Standalone query (reformulated):\n{standalone_query}\n\n"
                    f"{resolution_section}"
                    f"RAG-selected tools (already bound below):\n{source_context or 'None'}\n\n"
                    "Only call a bound tool if you actually need its data. Prefer minimal args "
                    "(pagination only) when the user asks for a general list. When the 'Resolved "
                    "references' block is present, TRUST it: use the canonical_code and entity_type "
                    "to pick the right tool and pass the canonical_code verbatim as the tool "
                    "argument (never invent UUIDs). Answer from tool results; if no tool is useful, "
                    "answer from context without calling tools."
                    + extra_rules
                ),
            }
        )

        max_iters = max(1, int(getattr(settings, "ai_assistant_agent_max_iterations", 6)))
        tool_call_budget = max(1, int(getattr(settings, "ai_assistant_tool_call_limit", 3)))
        tool_calls_made = 0

        for iteration in range(max_iters):
            tools_to_pass = openai_tools if (openai_tools and tool_calls_made < tool_call_budget) else None
            try:
                result: ChatResult = provider.chat(
                    messages,
                    tools=tools_to_pass,
                    temperature=float(config.temperature or 0),
                    model=config.model,
                    max_tokens=2048,
                )
            except Exception:
                logger.exception("AI assistant agent chat completion failed iteration=%s", iteration)
                break

            # Accumulate token usage across every provider call.
            token_usage["prompt_tokens"] += int(result.prompt_tokens or 0)
            token_usage["completion_tokens"] += int(result.completion_tokens or 0)
            token_usage["total_tokens"] += int(result.total_tokens or 0)

            requested_tool_calls = result.tool_calls or []

            if not requested_tool_calls:
                content = (result.content or "").strip()
                if content:
                    logger.info(
                        "AI assistant agent final answer iteration=%s response_len=%s",
                        iteration,
                        len(content),
                    )
                    return content, tool_calls_log, token_usage
                break

            # Echo the assistant tool-call message back into the running thread
            # using the OpenAI-style schema; the provider abstraction converts
            # this on the wire when needed.
            assistant_tool_calls = [
                {
                    "id": call.get("id") or f"call_{uuid.uuid4().hex[:8]}",
                    "type": "function",
                    "function": {
                        "name": call.get("name") or "",
                        "arguments": json.dumps(call.get("arguments") or {}),
                    },
                }
                for call in requested_tool_calls
            ]
            assistant_entry: dict[str, Any] = {
                "role": "assistant",
                "content": result.content or "",
                "tool_calls": assistant_tool_calls,
            }
            messages.append(assistant_entry)

            for call_idx, call in enumerate(requested_tool_calls):
                call_id = assistant_tool_calls[call_idx]["id"]
                tool_name = str(call.get("name") or "")
                parsed_args = call.get("arguments") or {}
                if not isinstance(parsed_args, dict):
                    parsed_args = {}
                str_args = {
                    k: (v if isinstance(v, str) else json.dumps(v))
                    for k, v in parsed_args.items()
                    if v is not None
                }
                # AI assistant chat has no Respond.io contact context, so any
                # contact_id / space_id the LLM hallucinated as a placeholder
                # string would only mislead the MCP access guard. Force-empty
                # them; the access guard treats empty (contact_id, space_id)
                # as a system call and authorises by tool/agent linkage.
                str_args["contact_id"] = ""
                str_args["space_id"] = ""
                # IT-support intake tool: source_channel + actor_user_id are
                # always known here (we are the in-app AI assistant talking on
                # behalf of the logged-in user). The MCP tool schema only
                # surfaces (contact_id, space_id, payload_json) — flat extras
                # are stripped by FastMCP — so the only place these survive
                # the round trip is inside the payload_json body itself.
                if tool_name == "crm_it_support_ticket_create":
                    raw_payload = str_args.get("payload_json") or "{}"
                    try:
                        payload_obj = json.loads(raw_payload)
                        if not isinstance(payload_obj, dict):
                            payload_obj = {}
                    except Exception:
                        payload_obj = {}
                    payload_obj.setdefault("source_channel", "ai_assistant")
                    payload_obj["actor_user_id"] = str(user_id) if user_id else None
                    if conversation_id:
                        payload_obj["source_conversation_id"] = conversation_id
                    if user_message_id:
                        payload_obj["source_message_id"] = user_message_id
                    str_args["payload_json"] = json.dumps(payload_obj)

                if tool_name not in available:
                    output = json.dumps({"error": "tool_not_available", "tool_name": tool_name})
                    tool_calls_log.append(MCPToolCallResult(tool_name or "unknown", False, output))
                    messages.append({"role": "tool", "tool_call_id": call_id, "content": output})
                    continue

                if tool_calls_made >= tool_call_budget:
                    output = json.dumps({"error": "tool_call_budget_exceeded"})
                    tool_calls_log.append(MCPToolCallResult(tool_name, False, output))
                    messages.append({"role": "tool", "tool_call_id": call_id, "content": output})
                    continue

                logger.info(
                    "AI assistant agent calling MCP tool iteration=%s tool_name=%s args=%s",
                    iteration,
                    tool_name,
                    self._safe_args_for_log(str_args),
                )
                call_started = time.perf_counter()
                try:
                    output = self._cached_tool_call(turn_cache, mcp, tool_name, str_args)
                    if tool_name == "user_guides_read":
                        # Redact the internal Outline URL before the result is
                        # logged or fed back to the model.
                        output = self._redact_guide_tool_output(output)
                    call_ms = (time.perf_counter() - call_started) * 1000
                    is_error, error_summary = self._tool_output_is_error(output)
                    if is_error:
                        logger.warning(
                            "AI assistant agent tool returned error tool_name=%s elapsed_ms=%.1f error=%s",
                            tool_name,
                            call_ms,
                            error_summary,
                        )
                        tool_calls_log.append(MCPToolCallResult(tool_name, False, output[:2000]))
                    else:
                        logger.info(
                            "AI assistant agent tool success tool_name=%s elapsed_ms=%.1f",
                            tool_name,
                            call_ms,
                        )
                        tool_calls_log.append(MCPToolCallResult(tool_name, True, output[:2000]))
                except Exception as exc:
                    logger.exception("AI assistant agent tool call failed tool_name=%s", tool_name)
                    output = json.dumps({"error": "tool_call_failed", "detail": str(exc)})
                    tool_calls_log.append(MCPToolCallResult(tool_name, False, output[:2000]))
                tool_calls_made += 1
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call_id,
                        "content": output[:6000],
                    }
                )

        logger.info(
            "AI assistant agent loop ended without explicit stop tool_calls_made=%s",
            tool_calls_made,
        )
        return self._deterministic_fallback(tool_calls_log), tool_calls_log, token_usage

    def _default_system_prompt(self) -> str:
        return (
            "ROLE\n"
            "You are the centralized Sorento AI Orchestrator.\n"
            "You coordinate Tool RAG, MCP tools, Contextual Memory, and Calculator.\n"
            "You are orchestration-only. Do not encode business rules here; enforce via MCP/backend outputs.\n\n"
            "ALLOWED TOOLS\n"
            "Only call the MCP tools bound to this request. Do not invent tools.\n"
            "Use MCP as source of truth for business data and constraints.\n\n"
            "CRITICAL DATA RULES\n"
            "Always use this turn's MCP results for factual answers.\n"
            "Never hallucinate entities, ids, statuses, quantities, prices, dates, states, or links.\n"
            "Use minimum tools needed (typically 0-2).\n\n"
            "GENERAL FLOW\n"
            "Resolve intent -> decide whether any bound tool is needed -> call with minimal args -> synthesize.\n"
            "For general list/catalog questions, pass only pagination (page, limit) and no free-text search.\n"
            "Ask one short clarification only when blocked by a missing required parameter.\n\n"
            "FORM SUBMISSION PROTOCOL (applies to every `crm_forms_*_submit` tool)\n"
            "When the user's request matches a form-submission tool (stock inquiry, "
            "complaint, purchase request, sponsorship form), you MUST guide them "
            "through the form with this choreography:\n"
            "1) On the FIRST turn that you detect the form intent, DO NOT call the "
            "submit tool. Instead, read the tool's docstring to learn its REQUIRED "
            "and OPTIONAL fields (including any nested line-item fields), and reply "
            "with the full field list. Tell the user they can answer everything in "
            "one message or one field at a time. Example opener:\n"
            "   \"To file a <form title>, I need the following details. You can "
            "answer everything at once or one item at a time.\"\n"
            "   Then list every field under two headings: 'Required' and "
            "'Optional', one line per field, using the labels from the tool "
            "docstring. If the tool has line items, list the line-item fields "
            "under a 'Line items' subsection.\n"
            "2) On EVERY subsequent turn in the same form flow, parse any fields "
            "the user just supplied, MERGE them into the running form state, and "
            "reply with a reflection block shaped exactly like this:\n"
            "     Captured so far:\n"
            "       - <Field label>: <value>\n"
            "       ...\n"
            "     Still needed:\n"
            "       - <Field label> [required|optional]\n"
            "       ...\n"
            "     Validation issues (if any):\n"
            "       - <field>: <short reason>\n"
            "   Then ask only for the still-needed REQUIRED fields.\n"
            "3) Once all REQUIRED fields are valid, you MUST send one FINAL summary "
            "for user review and ask them to edit anything if needed. Do NOT submit "
            "on that same turn unless the CURRENT user message already contained an "
            "explicit confirmation keyword.\n"
            "4) NEVER call the submit tool until (a) every REQUIRED header field is "
            "filled, (b) at least one complete line item exists when the tool has "
            "line items, and (c) the user's CURRENT message explicitly contains "
            "one of: CONFIRM, OK, OKAY, YES, CORRECT (case-insensitive).\n"
            "5) When you do submit, pass ONE argument `payload_json` shaped per the "
            "tool's docstring. For stock inquiry, purchase request, and complaint submit tools, "
            "the backend requires `\"user_confirmed\": true` in that JSON (only on the confirm turn). "
            "After success, briefly acknowledge the submission "
            "and ALWAYS include the returned public `view_url` so the user can open "
            "the record without logging in. For complaints, offer optional photos/videos via "
            "`crm_forms_entity_attachments_link` after submission.\n"
            "Attachments are OPTIONAL. Never block complaint submission due to missing attachments. "
            "Do NOT call `crm_forms_entity_attachments_link` unless the user explicitly asks to "
            "attach files or provides file URL/path content.\n"
            "6) If the user says 'new <form>', 'start over', or changes to a "
            "different form, clear the in-memory form state and restart at step 1.\n"
            "7) For complaint forms only: BEFORE collecting complaint fields, make "
            "sure a delivery-order number is identified. If not, ask for customer, "
            "product, and ORDER DATE range, use the order-lookup tools to find "
            "matching DOs, present them as a numbered list, and let the user pick "
            "by number. Only then start step 1 for the complaint form.\n"
            "If the user already selected an order in the UI/chat and it appears in "
            "Resolved references as entity_type=customer_order, treat its canonical_code "
            "as the selected delivery order number and DO NOT ask for delivery order "
            "number again.\n"
            "8) Complaint DO date parsing rules: if user gives a month-only period "
            "(e.g. 'February 2026'), convert it to full month range automatically "
            "(2026-02-01 to 2026-02-28, or 29 for leap year) and continue without "
            "asking leap-year clarification. Ask clarification only when month/year "
            "is missing or ambiguous.\n"
            "9) Complaint DO matching rules: partial text is valid. Use case-insensitive "
            "partial matching (`query`) for debtor/customer and product terms; do not "
            "require exact full debtor name or exact product code when user provides "
            "partial values.\n\n"
            "USER GUIDE PROTOCOL (applies to `user_guides_read`)\n"
            "When the user asks a how-to / process question — phrasings like 'how do I…', "
            "'how to…', 'where do I…', 'what's the process for…', 'steps to…', 'guide me on…', "
            "or any request for instructions on a CRM action (uploading a packing list, "
            "submitting a stock inquiry, sending a purchase request for approval, flowing a "
            "stock inquiry to purchasing, approving via email link, OTP / portal access, etc.) "
            "— follow this exact flow:\n"
            "1) Call `user_guides_read` ONCE with the user's question verbatim as `query`. The "
            "tool searches Outline and returns the full markdown body of the best match in a "
            "single round trip. There is no separate search tool — do NOT try to call "
            "`user_guides_search`.\n"
            "2) If the response contains `\"code\": \"NO_MATCH\"` or `\"code\": \"OUTLINE_ERROR\"`, "
            "tell the user no guide matches and ask them to rephrase. Do NOT invent steps.\n"
            "3) Otherwise read the returned markdown and ANSWER THE USER directly with concrete "
            "steps. Quote the exact UI labels from the guide in **bold** (button names, dialog "
            "titles, page names) so the user can find them in the UI. Use a short numbered list "
            "when the guide describes steps.\n"
            "3a) PRESERVE INLINE MARKDOWN LINKS from the guide verbatim. When the guide body "
            "contains a markdown link like `[**Resource Management → Files**](/resource-management/attachment-directories)`, "
            "your reply MUST keep the WHOLE markdown link — square brackets, label, parens, "
            "URL, all of it — exactly as written. Do NOT unwrap it to plain bold. Do NOT replace "
            "it with the label only. Do NOT replace it with the URL only. Do NOT move the URL "
            "to a separate sentence. The frontend renders these inline markdown links as "
            "clickable shortcuts to the actual CRM page; that is the primary value to the user.\n"
            "    EXAMPLE — guide says:\n"
            "      `1. Open [**Resource Management → Files**](/resource-management/attachment-directories) (URL: \\`/resource-management/attachment-directories\\`).`\n"
            "    Your reply must say (label-with-link kept intact):\n"
            "      `1. Open [**Resource Management → Files**](/resource-management/attachment-directories) in the left menu.`\n"
            "    NOT (link dropped, BAD):\n"
            "      `1. Open Resource Management → Files in your CRM.`\n"
            "    NOT (link separated, BAD):\n"
            "      `1. Open Resource Management → Files. Link: /resource-management/attachment-directories`\n"
            "3b) Do NOT just paste the doc URL on its own and tell the user to go read it — the "
            "user came here to avoid that. Do NOT append a 'Full guide: <doc URL>' line either; "
            "the inline links inside the steps are sufficient. Keep the response tight: short "
            "intro line, numbered steps, optional one-line caveat. No raw URLs at the bottom.\n"
            "4) If the first call's `alternative_titles` shows another guide that more directly "
            "matches the user's intent (e.g. a flow that spans rep portal + admin review + "
            "manager approval), call `user_guides_read` again with that guide's id and "
            "synthesize a single coherent answer.\n"
            "5) Never invent UI labels, button names, dialog titles, or routes that aren't in "
            "the guide body. If the guide doesn't cover a step the user asked about, say so.\n"
        )

    def _user_guide_protocol_addendum(self) -> str:
        return (
            "USER GUIDE PROTOCOL (applies to `user_guides_read`)\n"
            "When the user asks a how-to / process question — phrasings like 'how do I…', "
            "'how to…', 'where do I…', 'what's the process for…', 'steps to…', 'guide me on…', "
            "or any request for instructions on a CRM action (uploading a packing list, "
            "submitting a stock inquiry, sending a purchase request for approval, flowing a "
            "stock inquiry to purchasing, approving via email link, OTP / portal access, etc.) "
            "— follow this exact flow:\n"
            "1) Call `user_guides_read` ONCE with the user's question verbatim as `query`. The "
            "tool searches Outline and returns the full markdown body of the best match in a "
            "single round trip. There is no separate search tool — do NOT try to call "
            "`user_guides_search`.\n"
            "2) If the response contains `\"code\": \"NO_MATCH\"` or `\"code\": \"OUTLINE_ERROR\"`, "
            "tell the user no guide matches and ask them to rephrase. Do NOT invent steps.\n"
            "3) Otherwise read the returned markdown and ANSWER THE USER directly with concrete "
            "steps. Quote the exact UI labels from the guide in **bold** (button names, dialog "
            "titles, page names) so the user can find them in the UI. Use a short numbered list "
            "when the guide describes steps.\n"
            "3a) PRESERVE INLINE MARKDOWN LINKS from the guide verbatim. When the guide body "
            "contains a markdown link like `[**Resource Management → Files**](/resource-management/attachment-directories)`, "
            "your reply MUST keep the WHOLE markdown link — square brackets, label, parens, "
            "URL, all of it — exactly as written. Do NOT unwrap it to plain bold. Do NOT replace "
            "it with the label only. Do NOT replace it with the URL only. Do NOT move the URL "
            "to a separate sentence. The frontend renders these inline markdown links as "
            "clickable shortcuts to the actual CRM page; that is the primary value to the user.\n"
            "    EXAMPLE — guide says:\n"
            "      `1. Open [**Resource Management → Files**](/resource-management/attachment-directories) (URL: \\`/resource-management/attachment-directories\\`).`\n"
            "    Your reply must say (label-with-link kept intact):\n"
            "      `1. Open [**Resource Management → Files**](/resource-management/attachment-directories) in the left menu.`\n"
            "    NOT (link dropped, BAD):\n"
            "      `1. Open Resource Management → Files in your CRM.`\n"
            "    NOT (link separated, BAD):\n"
            "      `1. Open Resource Management → Files. Link: /resource-management/attachment-directories`\n"
            "3b) Do NOT just paste the doc URL on its own and tell the user to go read it — the "
            "user came here to avoid that. Do NOT append a 'Full guide: <doc URL>' line either; "
            "the inline links inside the steps are sufficient. Keep the response tight: short "
            "intro line, numbered steps, optional one-line caveat. No raw URLs at the bottom.\n"
            "4) If the first call's `alternative_titles` shows another guide that more directly "
            "matches the user's intent (e.g. a flow that spans rep portal + admin review + "
            "manager approval), call `user_guides_read` again with that guide's id and "
            "synthesize a single coherent answer.\n"
            "5) Never invent UI labels, button names, dialog titles, or routes that aren't in "
            "the guide body. If the guide doesn't cover a step the user asked about, say so.\n"
        )

    def intent_is_record_class(
        self, message: str, *, has_record_context: bool = True
    ) -> bool:
        """Semantic classifier: is this a question about the record on screen?

        record-class = a question about the SPECIFIC record/case currently on
        screen — its state, who acted on it, when, why, how long, its SLA, or
        what to do next on it.  NOT record-class = general catalog/data lookups
        (products, promotions, orders, stock), definitions, or how-the-feature-
        works-in-general.

        Implemented as a single cheap LLM call (general NLP judgment, NOT
        keyword matching — per the PLAN anti-overfit rule). Returns ``False`` on
        any provider error / missing key so we never wrongly hijack the agent
        loop (safe default = fall through).

        UAC3c — record-context gate: classifying "is this about the open
        record?" is only meaningful when a record is actually open on the page.
        With no record context (dashboard / settings / list pages) there is
        nothing to short-circuit to, so ``has_record_context=False`` skips the
        LLM round-trip entirely (no provider call). The hot-path caller in
        ``respond()`` already only reaches this with a successfully-assembled
        ``record_ctx``; enforcing the skip here too makes a wasted classifier
        call structurally impossible even if the call site is later refactored.
        """
        if not has_record_context:
            return False
        raw = (message or "").strip()
        if not raw:
            return False
        config = self.cfg.get()
        api_key = config.api_key_ciphertext or settings.openai_api_key
        if not api_key:
            return False
        system = (
            "You classify a single user message from an in-app assistant. The user is "
            "viewing ONE specific record (a case/form) on screen, and most of their "
            "questions are about THAT open record.\n"
            "Answer YES when the message asks about the specific record in front of them — "
            "its subject/summary/details, its current state, who acted on it, when, why it "
            "is in this state, how long something took, its SLA, or what to do next on it. "
            "Words like 'this', 'it', 'now', or naming the record's type ('this complaint') "
            "signal the open record. A question about who approved/handled/decided 'this' "
            "record, or what its reason/status/next step is, is YES.\n"
            "Answer NO only when the message is clearly NOT about the one open record: a "
            "catalog/data lookup across many records (products, promotions, orders, stock, "
            "customers, shipments), a definition of a term, or how a feature works in "
            "general (a how-to / process-in-general question).\n"
            "A procedural question SCOPED TO THE OPEN RECORD is YES — its process flow, how "
            "it works, its stages, or what to do next, when phrased about 'this' or 'here'. "
            "The SAME question asked generally or about a named type WITHOUT 'this' (e.g. "
            "'for a complaint', 'in general') is NO.\n"
            "Tie-breaker: if it could plausibly be about the open record, answer YES.\n"
            "Examples — YES: 'who handled this?' / 'what stage is it at?' / 'give me the "
            "gist of this case' / 'what do I do next here?' / 'what is the process flow for "
            "this?' / 'how does this work?'. "
            "NO: 'list all open complaints' / 'how does the approval step work in general?' "
            "/ 'what is the process flow for a complaint?' / 'what does resolved mean?' / "
            "'which products are on promotion?'.\n"
            "Respond with exactly one word: YES or NO."
        )
        # Retry transient provider errors: a swallowed error here flips the route
        # to the agent loop and produces a wrong answer for a real record question
        # (observed in end-to-end). Only a persistent failure defaults to False.
        last_exc: Exception | None = None
        for _attempt in range(2):
            try:
                provider = get_provider(config.provider, api_key, config.model)
                result = provider.chat(
                    [
                        {"role": "system", "content": system},
                        {"role": "user", "content": raw[:1000]},
                    ],
                    temperature=0.0,
                    model=config.model,
                    max_tokens=4,
                )
                verdict = (result.content or "").strip().upper()
                return verdict.startswith("YES")
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
        logger.warning(
            "intent_is_record_class classifier failed after retries; defaulting "
            "to False (%s)",
            last_exc,
        )
        return False

    def _render_record_answer(
        self,
        *,
        config: AIAssistantConfig,
        history: list[AIAssistantMessage],
        user_message: str,
        record_ctx: dict[str, Any],
        page_snapshot: PageSnapshotPayload | None = None,
        turn_cache: _TurnToolCache | None = None,
    ) -> tuple[str, list[MCPToolCallResult], dict[str, int]]:
        """Render a grounded answer from the deterministic record-context facts.

        For pure fact questions the model answers with NO tool call → returns
        ``tool_calls=[]`` (satisfies UAC §3.1). For procedural / next-step intent
        (UAC A6 fusion) the model is allowed exactly ONE ``user_guides_read``
        call to fetch the per-state procedure, grounded by the record's current
        status. Same return shape as ``_run_agent_loop``.
        """
        token_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        tool_calls_log: list[MCPToolCallResult] = []

        api_key = config.api_key_ciphertext or settings.openai_api_key
        if not api_key:
            return self._deterministic_fallback(tool_calls_log), tool_calls_log, token_usage
        try:
            provider: LLMProvider = get_provider(config.provider, api_key, config.model)
        except Exception:
            logger.exception("record-answer provider instantiation failed")
            return self._deterministic_fallback(tool_calls_log), tool_calls_log, token_usage

        facts_block = json.dumps(record_ctx, ensure_ascii=False, indent=2)
        # Human label for guide queries — snake_case entity_type ("sponsorship_form")
        # matches Outline poorly; the spelled-out form ("sponsorship form") hits.
        _ENTITY_LABELS = {
            "complaint": "complaint",
            "stock_inquiry": "stock inquiry",
            "purchase_request": "purchase request",
            "sponsorship_form": "sponsorship form",
        }
        entity_label = _ENTITY_LABELS.get(
            record_ctx.get("entity_type", ""), record_ctx.get("entity_type", "record")
        )
        cur_status = (record_ctx.get("current_state") or {}).get("status", "current")
        system = _html_to_text(config.system_prompt or "").strip() or self._default_system_prompt()
        if "USER GUIDE PROTOCOL" not in system:
            system = system.rstrip() + "\n\n" + self._user_guide_protocol_addendum()
        system = (
            system.rstrip()
            + "\n\n" + _current_date_directive()
            + "\n\nRECORD CONTEXT (deterministic, authoritative)\n"
            "Answer the user's question using ONLY these record facts. Be concise. Quote "
            "the human-readable `display_ref`, never a UUID. Times are already "
            "Asia/Kuala_Lumpur — present them as-is, do not re-convert. If a fact is null, "
            "say it is not set rather than inventing one.\n"
            "If the user is asking what to do next / which button / how to proceed, OR how "
            "this record's process / lifecycle / stages work, you MAY call "
            "`user_guides_read` EXACTLY ONCE to get the procedure, then ground your answer "
            "in `current_state.status` above. When you do, set `query` to the spelled-out "
            f"record type plus lifecycle/stage so the right guide is found — e.g. "
            f"\"{entity_label} lifecycle what to do at {cur_status} stage\" — NOT the "
            "user's bare words and NOT the snake_case type. For pure fact questions, answer "
            "directly with no tool call.\n\n"
            f"--- Record facts ---\n{facts_block}\n--- End record facts ---"
        )

        # Inject the on-screen page content too. The structured facts above are
        # authoritative for status / decision / SLA / audit / lead-time (often
        # off-screen, e.g. another tab). The visible text carries every other
        # field the user can SEE on the current screen (purpose, dates, line
        # items, addresses, …) so questions about ANY visible field are
        # answerable — without enumerating fields per entity. Facts win on
        # conflict; the page fills the gaps.
        page_text = (getattr(page_snapshot, "visible_text", "") or "").strip()
        if page_text:
            system = (
                system
                + "\n\nThe user is also looking at this screen right now. Use it to "
                "answer questions about any field they can see that is not in the "
                "structured facts above. If the two disagree, trust the structured "
                "facts.\n"
                f"--- Visible screen ---\n{page_text[:6000]}\n--- End visible screen ---"
            )

        messages: list[dict[str, Any]] = [{"role": "system", "content": system}]
        for msg in history[-6:]:
            if msg.role in {"user", "assistant"} and (msg.content or "").strip():
                messages.append({"role": msg.role, "content": msg.content})
        messages.append({"role": "user", "content": user_message})

        # Bind ONLY user_guides_read (fusion path); pure-fact answers ignore it.
        mcp = MCPRuntimeClient(
            settings.ai_assistant_mcp_url,
            timeout_seconds=settings.ai_assistant_mcp_timeout_seconds,
        )
        openai_tools: list[dict[str, Any]] = []
        guide_tool_name = "user_guides_read"
        try:
            tool_catalog = mcp.list_tools_with_schema()
            if guide_tool_name in tool_catalog:
                openai_tools.append(
                    self._mcp_schema_to_openai_tool(
                        guide_tool_name, tool_catalog[guide_tool_name]
                    )
                )
        except Exception:
            # Guide tool unavailable → fact-only answering still works.
            logger.warning("record-answer could not list MCP tools; fact-only mode")

        try:
            result: ChatResult = provider.chat(
                messages,
                tools=openai_tools or None,
                temperature=0.0,
                model=config.model,
                max_tokens=2048,
            )
        except Exception:
            logger.exception("record-answer initial provider call failed")
            return self._deterministic_fallback(tool_calls_log), tool_calls_log, token_usage
        token_usage["prompt_tokens"] += int(result.prompt_tokens or 0)
        token_usage["completion_tokens"] += int(result.completion_tokens or 0)
        token_usage["total_tokens"] += int(result.total_tokens or 0)

        # At most ONE user_guides_read call (A6 fusion). Pure-fact answers come
        # back with no tool_calls → tool_calls_log stays empty (UAC §3.1).
        requested_tool_calls = result.tool_calls or []
        if requested_tool_calls and openai_tools:
            assistant_tool_calls = [
                {
                    "id": call.get("id") or f"call_{uuid.uuid4().hex[:8]}",
                    "type": "function",
                    "function": {
                        "name": call.get("name") or "",
                        "arguments": json.dumps(call.get("arguments") or {}),
                    },
                }
                for call in requested_tool_calls
            ]
            messages.append(
                {
                    "role": "assistant",
                    "content": result.content or "",
                    "tool_calls": assistant_tool_calls,
                }
            )
            for call_idx, call in enumerate(requested_tool_calls[:1]):
                call_id = assistant_tool_calls[call_idx]["id"]
                name = str(call.get("name") or "")
                parsed_args = call.get("arguments") or {}
                if not isinstance(parsed_args, dict):
                    parsed_args = {}
                str_args = {
                    k: (v if isinstance(v, str) else json.dumps(v))
                    for k, v in parsed_args.items()
                    if v is not None
                }
                str_args["contact_id"] = ""
                str_args["space_id"] = ""
                if name != guide_tool_name:
                    output = json.dumps({"error": "tool_not_allowed", "tool_name": name})
                    tool_calls_log.append(MCPToolCallResult(name or "unknown", False, output))
                    messages.append({"role": "tool", "tool_call_id": call_id, "content": output})
                    continue
                try:
                    output = self._cached_tool_call(turn_cache, mcp, name, str_args)
                    if name == guide_tool_name:
                        # Redact the internal Outline URL before it reaches the
                        # model context.
                        output = self._redact_guide_tool_output(output)
                    is_error, _ = self._tool_output_is_error(output)
                    tool_calls_log.append(MCPToolCallResult(name, not is_error, output))
                except Exception as exc:
                    output = json.dumps({"error": "tool_call_failed", "detail": str(exc)})
                    tool_calls_log.append(MCPToolCallResult(name, False, output))
                messages.append({"role": "tool", "tool_call_id": call_id, "content": output})
            try:
                final = provider.chat(
                    messages, temperature=0.0, model=config.model, max_tokens=2048
                )
                token_usage["prompt_tokens"] += int(final.prompt_tokens or 0)
                token_usage["completion_tokens"] += int(final.completion_tokens or 0)
                token_usage["total_tokens"] += int(final.total_tokens or 0)
                answer = (final.content or "").strip()
            except Exception:
                logger.exception("record-answer follow-up provider call failed")
                answer = (result.content or "").strip()
        else:
            answer = (result.content or "").strip()

        if not answer:
            answer = self._deterministic_fallback(tool_calls_log)
        return answer, tool_calls_log, token_usage

    def _deterministic_fallback(self, tool_calls: list[MCPToolCallResult]) -> str:
        if not tool_calls:
            return (
                "I could not produce an answer this turn. Please rephrase or provide more specific "
                "identifiers (product code, order number, etc.)."
            )
        lines = ["Here is what I found from MCP tools:"]
        for r in tool_calls:
            prefix = "OK" if r.ok else "FAILED"
            lines.append(f"- [{prefix}] {r.tool_name}: {r.output[:260]}")
        return "\n".join(lines)

    def _tool_output_is_error(self, output: str) -> tuple[bool, str]:
        if not output:
            return True, "empty output"
        snippet = output[:200]
        try:
            payload = json.loads(output)
        except Exception:
            return False, ""
        if isinstance(payload, dict) and payload.get("error"):
            return True, str(payload.get("error"))
        # Some backend routes return {"message": "...", "code": "..."} for failures
        if isinstance(payload, dict) and payload.get("code") in {"INTERNAL_ERROR", "VALIDATION_ERROR", "REQUEST_TIMEOUT"}:
            return True, str(payload.get("message") or payload.get("code"))
        if isinstance(payload, dict) and isinstance(payload.get("detail"), str) and "error" in payload.get("detail", "").lower():
            return True, str(payload.get("detail"))
        return False, snippet

    def _safe_args_for_log(self, args: dict[str, Any]) -> dict[str, Any]:
        redacted = dict(args)
        for key in ("payload_json", "body", "content", "message", "description"):
            if key in redacted:
                value = str(redacted.get(key) or "")
                redacted[key] = value[:120] + ("..." if len(value) > 120 else "")
        return redacted

    def _embed_query(self, query: str) -> list[float]:
        # Embeddings always go via OpenAI for now (Anthropic does not expose
        # an embeddings API as of this writing). The provider abstraction's
        # embed() falls back to OpenAI when configured, so we delegate.
        config = self.cfg.get()
        api_key = config.api_key_ciphertext if config.provider == "openai" else settings.openai_api_key
        if not api_key:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Embedding provider not configured",
            )
        try:
            from app.services.llm_provider import OpenAIProvider

            vector = OpenAIProvider(api_key, settings.embedding_model_name).embed(query)
        except Exception as exc:
            logger.exception("AI assistant embedding failed")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Embedding provider error: {exc}",
            ) from exc
        if not vector:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Embedding provider returned empty vector",
            )
        return vector

    # ---------- Smart suggestions + answered detection ----------

    def _generate_suggestions(
        self,
        *,
        config: AIAssistantConfig,
        history: list[AIAssistantMessage],
        user_message: str,
        assistant_reply: str,
    ) -> list[str]:
        """Mid-conversation follow-up suggestions are intentionally disabled.

        Previously this called the LLM for 5 contextual follow-ups per message.
        It added 1-2s of latency per turn for marginal value, so we now return
        an empty list. Static "starter" suggestions still appear on a new
        conversation via :py:meth:`generate_greeting`.
        """
        return []

    # Static starter pills shown on a fresh conversation. Curated to cover
    # the most common how-to flows backed by user-guides + a couple of
    # general data lookups. Editing this list ships immediately — no LLM
    # call, no per-user personalization, no latency.
    _GREETING_SUGGESTIONS: tuple[str, ...] = (
        "How do I upload a packing list?",
        "How do I submit a stock inquiry from the portal?",
        "How do I send a purchase request for approval?",
        "How do I upload a GRN?",
        "How does the project sales rep get the portal link?",
        "Show me pending stock inquiries",
    )

    def generate_greeting(self, user_id: str) -> dict:
        """Greeting + a static set of starter suggestions.

        Previously this hit the LLM to personalize 5 follow-ups based on the
        user's recent question history. The latency wasn't worth it for a
        first-paint surface, so the suggestions are now hardcoded. To change
        them, edit :py:attr:`_GREETING_SUGGESTIONS`.
        """
        return {
            "greeting": "Hi, how can I help you?",
            "suggestions": list(self._GREETING_SUGGESTIONS),
        }

    def _is_fallback_reply(self, reply: str, tool_calls: list[MCPToolCallResult]) -> bool:
        """True when the assistant reply matches a deterministic fallback string."""
        if not (reply or "").strip():
            return True
        fallback_no_tool = self._deterministic_fallback([])
        if reply.strip() == fallback_no_tool.strip():
            return True
        # The tool-result fallback always starts with this exact sentinel line.
        if reply.startswith("Here is what I found from MCP tools:"):
            return True
        return False

    # Canonical menu-path → FE route map. Mirrors
    # `scripts/annotate_user_guides_routes.py` so the agent's response gets
    # the same hyperlinks the source guide has, even when the LLM paraphrases.
    # Order matters: longer, more-specific paths first.
    _ROUTE_MAP: tuple[tuple[str, str], ...] = (
        ("Resource Management → Files", "/resource-management/attachment-directories"),
        ("Resource Management → Attachment Types", "/resource-management/attachment-types"),
        ("Resource Management → Trash", "/resource-management/trash"),
        ("Procurement → Stock Inquiries", "/procurement-management/stock-inquiries"),
        ("Procurement → Purchase Requests", "/procurement-management/purchase-requests"),
        ("Procurement → Sponsorship Forms", "/procurement-management/sponsorship-forms"),
        ("Procurement → SPO Allocations", "/procurement-management/spo-allocations"),
        ("Procurement → Packing Lists", "/procurement-management/packing-lists"),
        ("Procurement → GRN", "/procurement-management/grn"),
        ("Master Data Management → Products", "/master-data-management/products"),
        ("Delivery Order Management → Delivery Orders", "/order-management/orders"),
        ("Inventory Management → Warehouses", "/inventory-management/warehouses"),
        ("Inventory Management → Stock", "/inventory-management/stock"),
        ("Marketing Management → Promotion Products", "/marketing-management/promotion-products"),
        ("Marketing Management → Promotions", "/marketing-management/promotions"),
        ("Complaint Management → Complaints", "/complaint-management/complaints"),
        ("System Management → Integration Logs", "/system-management/integration-logs"),
        ("System Management → Import Jobs", "/system-management/import-jobs"),
        ("User Management → Contacts", "/user-management/contacts"),
    )

    _GUIDE_LINK_PATTERN = re.compile(r"\[([^\[\]]+?)\]\(([^)\s]+)\)")

    def _extract_guide_link_map(
        self, tool_calls: list[MCPToolCallResult]
    ) -> list[tuple[str, str]]:
        """Scan `user_guides_read` outputs for inline markdown links
        `[Label](URL)` (with or without bold markers) and return label→URL
        pairs. Lets us re-wrap UI-element deep links (e.g.
        `[**Upload**](/resource-management/attachment-directories?guide_target=...)`)
        that the LLM paraphrased away. Static `_ROUTE_MAP` only covers menu
        paths; this extends coverage to whatever the guide author wrote.
        """
        pairs: list[tuple[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for call in tool_calls:
            if not call.ok or not call.output:
                continue
            for raw_label, url in self._GUIDE_LINK_PATTERN.findall(call.output):
                label = raw_label.strip().strip("*").strip()
                if not label or not url:
                    continue
                key = (label, url)
                if key in seen:
                    continue
                seen.add(key)
                pairs.append(key)
        pairs.sort(key=lambda p: -len(p[0]))
        return pairs

    def _inject_route_links(
        self,
        text: str,
        extra_map: list[tuple[str, str]] | None = None,
    ) -> str:
        """Wrap bare bold menu paths (`**Resource Management → Files**`) and
        plain mentions (`Resource Management → Files`) with the canonical FE
        route link. Skips mentions that are already inside a markdown link.

        Also removes any "Full guide: <doc URL>" / "refer to the full guide
        here: ..." trailing lines because the inline links are sufficient
        and the bare doc URLs land on the doc.foundryx.my surface (which
        the user said they don't want).

        `extra_map` adds dynamic label→URL mappings extracted from the active
        tool outputs (see `_extract_guide_link_map`) so guide-authored
        button-level deep links survive paraphrase. Only the bold form is
        re-injected for `extra_map` entries to avoid wrapping common verbs
        like "Upload" in plain prose.
        """
        if not text:
            return text
        result = text
        # Pass replacements as plain-text via a lambda so backslashes / `\g`
        # / `\u` sequences inside the URL don't get parsed as regex
        # back-references in `re.sub`'s replacement template.
        # 1) Wrap bold menu paths (bias the LLM to use bold for menu mentions
        # via the prompt, and we cover both with/without bold below).
        for label, route in self._ROUTE_MAP:
            esc = re.escape(label)
            # `**label**` not already inside `](`/`)`.
            bold_pat = re.compile(
                r"(?<!\]\()(?<!`)\*\*" + esc + r"\*\*(?!\]\()"
            )
            replacement = f"[**{label}**]({route})"
            result = bold_pat.sub(lambda _m, r=replacement: r, result)
        # 2) Wrap PLAIN (non-bold, non-linked) menu paths with bold + link
        # so the LLM's "Resource Management → Files in your CRM" still ends
        # up clickable. Skip mentions already inside markdown link parens.
        for label, route in self._ROUTE_MAP:
            esc = re.escape(label)
            plain_pat = re.compile(
                r"(?<!\*)(?<!\]\()(?<!`)\b" + esc + r"\b(?!\]\()(?!\*)"
            )
            replacement = f"[**{label}**]({route})"
            result = plain_pat.sub(lambda _m, r=replacement: r, result)
        # 2b) Re-inject guide-authored deep links (button targets, etc.).
        # Bold-only — never plain — so a stray "upload" in prose does not
        # become a button deep link.
        if extra_map:
            for label, url in extra_map:
                esc = re.escape(label)
                bold_pat = re.compile(
                    r"(?<!\]\()(?<!`)\*\*" + esc + r"\*\*(?!\]\()"
                )
                replacement = f"[**{label}**]({url})"
                result = bold_pat.sub(lambda _m, r=replacement: r, result)
        # 3) Strip trailing "Full guide" / "refer to the full guide" footers.
        # These are noisy: the inline links cover the same ground and the
        # raw doc.foundryx.my URLs add nothing.
        footer_patterns = [
            re.compile(
                r"\n+For (?:more )?detailed instructions[^\n]*?(?:\n[^\n]*)*$",
                re.IGNORECASE,
            ),
            re.compile(
                r"\n+(?:You can )?(?:refer to|see) the full guide[^\n]*?(?:\n[^\n]*)*$",
                re.IGNORECASE,
            ),
            re.compile(r"\n+Full guide:[^\n]*?(?:\n[^\n]*)*$", re.IGNORECASE),
        ]
        for pat in footer_patterns:
            result = pat.sub("", result)
        return result.rstrip()

    def _extract_links_from_text(self, text: str) -> list[str]:
        if not text:
            return []
        pattern = r"(\/(?:[a-zA-Z0-9\-_]+\/?)+)"
        links = re.findall(pattern, text)
        seen: set[str] = set()
        out: list[str] = []
        for link in links:
            if len(link) < 4:
                continue
            if link in seen:
                continue
            seen.add(link)
            out.append(link)
        return out

    def _outline_host(self) -> str:
        """Host of the INTERNAL Outline knowledge base (e.g.
        ``doc.foundryx.my``), derived from ``settings.outline_base_url`` — never
        hardcoded. Empty string if it cannot be resolved (redaction then no-ops).
        """
        raw = (getattr(settings, "outline_base_url", "") or "").strip()
        if not raw:
            return ""
        try:
            netloc = urlparse(raw).netloc
        except Exception:
            netloc = ""
        if netloc:
            return netloc
        # Fallback for a host-only value (no scheme).
        return raw.replace("https://", "").replace("http://", "").split("/")[0]

    def _strip_outline_urls(self, text: str) -> str:
        """Remove every reference to the internal Outline base URL from a piece
        of text BEFORE it is returned to / persisted for the user.

        - A markdown link pointing at Outline (``[Guide](https://doc.foundryx.my/...)``,
          bold-wrapped or not) collapses to just its (de-bolded) label so the
          sentence still reads.
        - A bare Outline URL (optionally angle-bracketed) is removed outright.

        In-app links (``/resource-management/...``, ``?guide_target=...``) do NOT
        point at the Outline host, so they are left untouched.
        """
        if not text:
            return text
        host = self._outline_host()
        if not host:
            return text
        esc = re.escape(host)
        result = text
        # 1) Markdown link to Outline -> keep the de-bolded label only.
        md_link = re.compile(
            r"\[([^\]]+)\]\(\s*<?https?://" + esc + r"[^)>\s]*>?\s*\)"
        )
        result = md_link.sub(
            lambda m: m.group(1).strip().strip("*").strip(), result
        )
        # 2) Bare Outline URL -> drop it.
        bare = re.compile(r"<?https?://" + esc + r"[^\s)\]>]*>?")
        result = bare.sub("", result)
        # Tidy up residue ("see  ." double spaces, an emptied paren).
        result = re.sub(r"\(\s*\)", "", result)
        result = re.sub(r"[ \t]{2,}", " ", result)
        result = re.sub(r" +([.,;:])", r"\1", result)
        return result.rstrip()

    def _redact_guide_tool_output(self, output: str) -> str:
        """Strip the external Outline URL from a ``user_guides_read`` JSON result
        BEFORE it enters the LLM context, so the model can never echo it
        (the authoritative half of the belt-and-suspenders fix; the final
        answer is also post-filtered via ``_strip_outline_urls``).

        Removes the top-level ``url`` field and any ``alternative_titles[].url``,
        and scrubs the host out of string values (the markdown body, snippets).
        Internal ``?guide_target`` / route links inside the body survive (they
        don't point at the Outline host), so ``_extract_guide_link_map`` still
        re-injects them. ``url_id`` (an internal anchor, not a clickable URL) is
        kept.
        """
        if not output:
            return output
        try:
            payload = json.loads(output)
        except Exception:
            # Not JSON (shouldn't happen for this tool) — plain host strip.
            return self._strip_outline_urls(output)
        if isinstance(payload, dict):
            payload.pop("url", None)
            alts = payload.get("alternative_titles")
            if isinstance(alts, list):
                for alt in alts:
                    if isinstance(alt, dict):
                        alt.pop("url", None)
                        for k, v in list(alt.items()):
                            if isinstance(v, str):
                                alt[k] = self._strip_outline_urls(v)
            for k, v in list(payload.items()):
                if isinstance(v, str):
                    payload[k] = self._strip_outline_urls(v)
            return json.dumps(payload)
        return self._strip_outline_urls(output)
