"""AI assistant services (config + MCP-RAG chat orchestration)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import json
import logging
import re
import time
import uuid

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


@dataclass
class MCPToolCallResult:
    tool_name: str
    ok: bool
    output: str


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
            user_meta["page_snapshot"] = {
                "path": (page_snapshot.path or "")[:500],
                "search": (page_snapshot.search or "")[:500],
                "title": (page_snapshot.title or "")[:255],
                "visible_text": (page_snapshot.visible_text or "")[:1000],
            }

        user_msg = self.append_message(conv.id, "user", message, metadata_json=user_meta or None)
        logger.info("AI assistant user message appended conversation_id=%s", conv.id)
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

        agent_started = time.perf_counter()
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
        )
        agent_ms = (time.perf_counter() - agent_started) * 1000
        logger.info(
            "AI assistant agent phase finished conversation_id=%s response_len=%s tool_calls=%s elapsed_ms=%.1f",
            conv.id,
            len(response_text or ""),
            len(tool_calls),
            agent_ms,
        )
        # Post-process: when the agent rephrased a how-to answer and dropped
        # inline markdown links from the guide, re-wrap any bold menu paths
        # with their canonical FE route links. Cheap deterministic safety net
        # so the LLM doesn't have to be perfect about preserving links.
        # `extra_map` adds button-level deep links (e.g. `?guide_target=...`)
        # that the guide author wrote inline.
        guide_link_map = self._extract_guide_link_map(tool_calls)
        response_text = self._inject_route_links(response_text, guide_link_map)
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
            meta["page_snapshot"] = {
                "path": (page_snapshot.path or "")[:500],
                "title": (page_snapshot.title or "")[:255],
                "visible_text": (page_snapshot.visible_text or "")[:1000],
            }
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
            "- Keep it concise (<= 2 sentences).\n"
            "- Do not answer the question. Output plain text only, no quotes, no prefix."
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
        if page_snapshot is not None:
            page_block = (
                "The user is currently viewing this page. Use it as context only when their "
                "question relates to it; otherwise ignore.\n\n"
                f"--- Page: {page_snapshot.title} ({page_snapshot.path}{page_snapshot.search}) ---\n"
                f"{page_snapshot.visible_text}\n"
                "--- End page ---"
            )
            messages.append({"role": "system", "content": page_block})
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
                    output = mcp.call_tool(tool_name, args=str_args)
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
