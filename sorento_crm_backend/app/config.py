"""Configuration settings for the FastAPI application."""
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List, Union


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Database
    database_url: str
    direct_url: str | None = None
    
    # JWT Authentication
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    
    # API Server
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    
    # CORS - accept as string and parse.
    # Default covers Next.js auto-bumped ports (3000 taken -> 3001 -> 3002 ...) so multiple
    # local instances do not need to override CORS_ORIGINS just to load.
    cors_origins: str = (
        "http://localhost:3000,http://localhost:3001,http://localhost:3002,"
        "http://localhost:3003,http://localhost:3004,http://localhost:3005"
    )
    
    @field_validator('cors_origins', mode='before')
    @classmethod
    def parse_cors_origins(cls, v: Union[str, List[str]]) -> str:
        """Parse CORS origins from comma-separated string or list."""
        if isinstance(v, list):
            return ','.join(v)
        return v
    
    @property
    def cors_origins_list(self) -> List[str]:
        """Get CORS origins as a list."""
        return [origin.strip() for origin in self.cors_origins.split(',') if origin.strip()]
    
    # Environment
    environment: str = "development"
    debug: bool = False

    # Complaint <-> DO auto-fulfilment: which Complaint-team tiers (agent `complaint`,
    # set `complaint`) receive the replacement-DO-delivered email/in-app. Comma list,
    # e.g. "1,2" (Tier 1 + Tier 2) or "1" (Tier 1 only). COMPLAINT_DO_DELIVERED_NOTIFY_TIERS
    complaint_do_delivered_notify_tiers: str = "1,2"

    # Which spreadsheet extensions the SCM upload channels accept. Comma list, no dots.
    # SCM_UPLOAD_EXTENSIONS. Configurable because the format is the CUSTOMER's, not ours:
    # AutoCount's own "Purchase Order Listing With Detail" export is legacy BIFF `.xls`,
    # and refusing it means asking somebody to re-save 13 MB of history by hand before
    # they can load it. One list, read by the route that rejects and by the reader that
    # dispatches, so the two can never disagree about what is accepted.
    scm_upload_extensions: str = "xlsx,xlsm,xls"

    # Respond.io
    respond_api_key: str | None = None
    respond_base_url: str = "https://api.respond.io"
    respond_app_base_url: str = "https://app.respond.io"  # Base URL for inbox links (e.g. /space/{id}/inbox/{contact_id})
    respond_space_id: str | None = None
    
    # External API Access
    external_api_key: str | None = None  # API key for external parties to access endpoints
    # When set, X-API-Key auth resolves RBAC as this users row (required for MCP/n8n read tools).
    external_api_key_act_as_user_id: str | None = None  # EXTERNAL_API_KEY_ACT_AS_USER_ID
    
    # Redis Queue (must match everywhere: API, workers, seed scripts; use same host:port/db)
    redis_url: str = "redis://localhost:6379/0"

    # Request idempotency (duplicate-submit / network-slowness backstop) — see
    # documentation/plans/PLAN-uniform-idempotency.md. Scoped to an allowlist of action endpoints
    # in app/middleware/idempotency_middleware.py.
    idempotency_enabled: bool = True            # IDEMPOTENCY_ENABLED
    # Ops kill switch for external-request telemetry. On by default; exists so a
    # write-path problem can be shut off without a deploy.
    api_call_log_enabled: bool = True           # API_CALL_LOG_ENABLED
    idempotency_mode: str = "enforce"           # IDEMPOTENCY_MODE: "enforce" | "observe"
    idempotency_result_ttl: int = 10            # dedupe window seconds (a repeat within this is collapsed)
    idempotency_lock_ttl: int = 60              # in-flight lock seconds (must exceed max handler duration)
    idempotency_wait_ms: int = 2000             # how long a concurrent replay waits for the first, then 409
    idempotency_max_body: int = 262144          # skip dedupe for bodies larger than this (bytes)

    # Per-IP rate limits on unauthenticated/abuse-prone endpoints (fixed window,
    # fail-open if Redis down) — see PLAN-fix-security-cluster Sub-plan A. All
    # env-overridable; set max<=0 to disable a given limiter.
    rate_limit_signup_max: int = 3              # signups per window per IP
    rate_limit_signup_window_seconds: int = 3600
    rate_limit_reset_max: int = 5              # password-reset requests per window per IP
    rate_limit_reset_window_seconds: int = 900
    rate_limit_portal_otp_max: int = 30        # portal OTP requests per window per IP
    rate_limit_portal_otp_window_seconds: int = 60

    # Presigned-URL hardening (external API) — see PLAN-fix-security-cluster Sub-plan B.
    # When True, /external/presigned-url only signs a file_path that resolves to a
    # real attachments row (blocks signing arbitrary/guessed keys). Escape hatch:
    # set PRESIGNED_REQUIRE_ATTACHMENT_ROW=false if a legit n8n flow presigns a key
    # with no row yet. Max TTL clamps expires_in (URLs shouldn't outlive the action).
    presigned_require_attachment_row: bool = True
    presigned_max_ttl_seconds: int = 3600

    embedding_queue_name: str = "embeddings"
    # When True, scheduled task also drains pending rows from embedding_queue if Redis is empty of jobs.
    # Set False to use Redis (RQ) only; then REDIS_URL must be the instance where jobs were enqueued.
    embedding_queue_db_fallback_enabled: bool = True  # EMBEDDING_QUEUE_DB_FALLBACK_ENABLED
    embedding_max_retries: int = 5
    embedding_retry_backoff_seconds: int = 60
    embedding_chunk_size: int = 900
    embedding_chunk_overlap: int = 120
    embedding_provider: str = "openai"
    embedding_model_name: str = "text-embedding-3-small"
    embedding_model_version: str = "v1"
    embedding_dimensions: int = 1536
    openai_api_key: str | None = None
    # SCM M5 market research — Anthropic web-search backend (key-gated; the run
    # endpoint degrades to a 'failed' run row when unset, never crashes).
    anthropic_api_key: str | None = None
    openai_embeddings_url: str = "https://api.openai.com/v1/embeddings"
    openai_chat_completions_url: str = "https://api.openai.com/v1/chat/completions"

    # AI assistant
    ai_assistant_enabled: bool = True
    ai_assistant_mcp_url: str = "http://localhost:8765/mcp"
    ai_assistant_mcp_timeout_seconds: int = 20
    ai_assistant_tool_call_limit: int = 3
    # RAG: how many MCP tools to BIND to the agent per turn. Default 1 —
    # deterministic single-tool resolution (the parser already fixes intent+domain,
    # so the top-1 candidate is the tool; the runners-up are kept in the trace as
    # is_current=false for visibility but are not bound). Raise to expose more.
    ai_assistant_rag_top_k: int = 1
    # Agent loop: max tool-calling iterations before forcing a final answer.
    ai_assistant_agent_max_iterations: int = 6
    # Reformulator: include the last N history messages (user+assistant) as context.
    ai_assistant_reformulator_history_turns: int = 6

    # Outline (user-guide knowledge base) base URL. INTERNAL Foundryx asset —
    # its URL must never be surfaced to end users by the AI assistant. Used
    # here only to derive the host to STRIP from guide tool-results and from
    # the assistant's final answer (see ai_assistant_service redaction).
    outline_base_url: str = "https://doc.foundryx.my"

    # Ideation pipeline (ideate intent + Ideas iframe host). All .env-driven and
    # DORMANT when blank: absent values make the feature inert without touching
    # existing routes. Secrets are masked in any echo. create_idea is called over
    # HTTP (server-to-server httpx to ideation_shared_service_url) — NOT MCP; there
    # is deliberately no ideation_mcp_url (sorento_crm_mcp is read-only).
    ideation_shared_service_url: str | None = None   # IDEATION_SHARED_SERVICE_URL
    ideation_intake_api_key: str | None = None       # IDEATION_INTAKE_API_KEY (secret)
    ideation_embed_signing_secret: str | None = None  # IDEATION_EMBED_SIGNING_SECRET (secret)
    ideation_embed_connection_id: str | None = None  # IDEATION_EMBED_CONNECTION_ID
    ideation_embed_fe_base_url: str | None = None    # IDEATION_EMBED_FE_BASE_URL (iframe FE root)

    # Frontend app URL (for password reset and other links in emails)
    frontend_base_url: str | None = None
    # Fallback business WhatsApp number (E.164 digits, no '+') for the portal
    # verify page's wa.me escape hatch when the workspace has none configured.
    portal_whatsapp_number: str | None = None

    # Feature flags (progressive rollout)
    notifications_v1_enabled: bool = True  # NOTIFICATIONS_V1_ENABLED
    # When False (default), module guards allow all API routes if tenant has no module rows yet (legacy).
    # When True, disabled modules return 403 from guarded routers.
    module_guard_strict: bool = False  # MODULE_GUARD_STRICT

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",  # Ignore extra environment variables (like AWS_* variables)
    )


# Values come from environment / .env at runtime; static analysis cannot infer required env vars.
settings = Settings()  # type: ignore[call-arg]
