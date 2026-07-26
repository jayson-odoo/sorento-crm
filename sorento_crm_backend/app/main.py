"""FastAPI application entry point."""
import os
# Load .env with override=True so file values beat any stale shell env
# (e.g. a STORAGE_DEFAULT_PROVIDER exported earlier in the session).
from pathlib import Path as _Path
try:
    from dotenv import load_dotenv as _load_dotenv
    _env_path = _Path(__file__).resolve().parent.parent / ".env"
    if _env_path.exists():
        _load_dotenv(_env_path, override=True)
    else:
        _load_dotenv(override=True)
except ImportError:
    pass

from fastapi import Depends, FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
import logging
from app.config import settings
from app.api.v1 import api_router
from app.services.error_handler import AppException
from app.middleware.logging_middleware import LoggingMiddleware
from app.middleware.idempotency_middleware import IdempotencyMiddleware
from app.middleware.api_call_log_middleware import ApiCallLogMiddleware

# Configure logging
logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
# Verbose auth-dependency logging only in debug — at DEBUG it logs token length +
# first chars, which must never run in production (security audit 2026-06-29).
if settings.debug:
    logging.getLogger('app.dependencies').setLevel(logging.DEBUG)

# Create FastAPI app
app = FastAPI(
    title="Sorento CRM API",
    description="FastAPI backend for Sorento CRM",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Add logging middleware
app.add_middleware(LoggingMiddleware)

# Request idempotency: dedupe replays of allowlisted action endpoints (double-click,
# proxy retry, two tabs) so harmful side effects (SLA assignment, Respond sends,
# status transitions) execute exactly once. See app/middleware/idempotency_middleware.py.
app.add_middleware(IdempotencyMiddleware)
# Telemetry for /api/v1/external/* — total coverage by construction, so a new
# external route is logged the day it is added rather than opt-in per endpoint.
app.add_middleware(ApiCallLogMiddleware)

# Compress JSON responses. List endpoints (products, attachments) return 50-70KB
# of JSON per page; uncompressed transfer was ~1s of "content download" on prod.
# gzip cuts these payloads ~8-10x. minimum_size skips tiny bodies where the
# CPU cost outweighs the win.
app.add_middleware(GZipMiddleware, minimum_size=1024)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
    # Only expose headers the browser actually needs to read; "*" leaked internal
    # headers cross-origin (security audit 2026-06-29).
    expose_headers=["Content-Type", "Content-Length", "Content-Disposition"],
)

# Global exception handler for AppException
@app.exception_handler(AppException)
async def app_exception_handler(request, exc: AppException):
    return JSONResponse(
        status_code=exc.status_code,
        content=exc.detail
    )

# Global exception handler for all unhandled exceptions
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch all unhandled exceptions and log them."""
    error_logger = logging.getLogger(__name__)
    import traceback
    error_traceback = traceback.format_exc()
    error_logger.error(f"Unhandled exception: {type(exc).__name__}: {str(exc)}")
    error_logger.error(f"Request URL: {request.url}")
    error_logger.error(f"Request method: {request.method}")
    error_logger.error(f"Traceback:\n{error_traceback}")
    
    # Never leak exception messages/types to clients in production — they aid
    # reconnaissance (DB schema, file paths, library hints). Full detail is logged
    # server-side above; only expose it when debug is explicitly on (security audit 2026-06-29).
    content = {"message": "Internal server error"}
    if settings.debug:
        content["detail"] = str(exc)
        content["type"] = type(exc).__name__
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=content,
    )

# Validation error handler to see detailed errors
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    validation_logger = logging.getLogger(__name__)
    validation_logger.error(f"Validation error: {exc.errors()}")
    validation_logger.error(f"Request URL: {request.url}")
    validation_logger.error(f"Request method: {request.method}")
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": jsonable_encoder(exc.errors())}
    )

# Triggers eligibility registrations side-effects.
from app.services import lookup_eligibility_registrations as _lookup_eligibility_registrations  # noqa: F401

from app.services.lookup_write_listener import register_lookup_write_listeners
register_lookup_write_listeners()

# Multi-company isolation: fail-closed SELECT filter + insert auto-stamp on every
# CompanyScopedMixin model. Registered here (import time, not startup_event) so it
# is active in the API; the worker registers it via its own import path.
from app.services.company_scope import register_company_scope_listeners
register_company_scope_listeners()

# Dealer Kit collection rules are evaluated by the SAME rule engine as automation
# triggers, so its `product` fact source has to be on the registry before the
# first /rule-facts request - otherwise the RuleBuilder renders an empty field
# list and a Designer cannot author a collection at all.
from app.services.dealer_kit.product_facts import register_product_facts
register_product_facts()


def _register_activities_adapters() -> None:
    """Register per-entity Activities & Notes adapters at process boot.

    Each consuming module hands its visibility / on_post / contacts hooks
    to the activities service via this single registration point so the
    generic ``/api/v1/activities/{entity_type}/{entity_id}/...`` routes
    can route module-specific behaviour without coupling.
    """
    try:
        from app.services.activities_registry import (
            ActivitiesAdapter,
            register_activities_adapter,
        )
        from app.services import tickets_service

        register_activities_adapter(
            ActivitiesAdapter(
                entity_type="ticket",
                permission_view="tickets.tickets.view",
                permission_post="tickets.tickets.view",
                get_respond_contacts=tickets_service.respond_contacts_for,
                on_post=lambda db, ticket_id, actor_id, body_html: tickets_service.handle_activity_posted(
                    db, ticket_id, actor_id, body_html
                ),
                can_view=tickets_service.can_view,
            )
        )
        logging.info("Activities adapter registered: ticket")
    except Exception as e:  # noqa: BLE001
        logging.error(
            f"Failed to register activities adapters: {str(e)}", exc_info=True
        )


# Run synchronously at import time so it precedes the first request.
_register_activities_adapters()

# Include API routes. The company-scope resolver runs as a router-level dependency
# for EVERY /api/v1/* request: it resolves the caller's four-state scope (JWT active
# company / X-API-Key contact / system) and stamps it onto the request DB session so
# the do_orm_execute filter enforces isolation without editing each route. It shares
# the route's session (get_db is cached per-request) and never 500s (fail-closed).
from app.services.company_scope_resolver import apply_company_scope
app.include_router(api_router, prefix="/api/v1", dependencies=[Depends(apply_company_scope)])

# Initialize scheduler for background tasks
scheduler = None

@app.on_event("startup")
async def startup_event():
    """Startup event: initialize scheduler and audit listeners."""
    global scheduler
    try:
        from app.services.audit_service import register_audit_listeners
        register_audit_listeners()
        logging.info("Audit listeners registered")
    except Exception as e:
        logging.error(f"Failed to register audit listeners: {str(e)}", exc_info=True)
    try:
        from app.services.embedding_change_listener import register_embedding_change_listeners
        register_embedding_change_listeners()
        logging.info("Embedding change listeners registered")
    except Exception as e:
        logging.error(f"Failed to register embedding change listeners: {str(e)}", exc_info=True)
    # Register task handlers unconditionally so manual "run now" works on API
    # containers even when scheduler ticks are gated to the worker container.
    try:
        from app.scheduler.task_scheduler import register_task_handlers
        register_task_handlers()
        logging.info("Scheduled task handlers registered")
    except Exception as e:
        logging.error(f"Failed to register task handlers: {str(e)}", exc_info=True)

    # Scheduler is gated so only the dedicated `worker` container runs it.
    # Blue/green API containers must NOT fire cron ticks (would double-process).
    if os.getenv("ENABLE_SCHEDULER", "false").lower() == "true":
        try:
            from app.scheduler.task_scheduler import start_scheduler
            scheduler = start_scheduler()
            logging.info("Background scheduler started successfully")
        except Exception as e:
            logging.error(f"Failed to start scheduler: {str(e)}", exc_info=True)
    else:
        logging.info("Background scheduler disabled (ENABLE_SCHEDULER != true)")
    try:
        from app.database import SessionLocal
        from app.services.mcp_tool_registry_service import sync_catalog
        _db = SessionLocal()
        try:
            report = sync_catalog(_db)
            _db.commit()
            logging.info(
                "MCP tool catalog synced at startup: added=%d updated=%d deactivated=%d",
                report.added,
                report.updated,
                report.deactivated,
            )
        finally:
            _db.close()
    except Exception as e:
        logging.error(f"Failed to sync MCP tool catalog at startup: {str(e)}", exc_info=True)

    try:
        from app.database import SessionLocal
        from app.rbac.permission_registry import sync_permissions
        _db = SessionLocal()
        try:
            created = sync_permissions(_db)
            logging.info("RBAC permissions synced at startup: added=%d", created)
        finally:
            _db.close()
    except Exception as e:
        logging.error(f"Failed to sync RBAC permissions at startup: {str(e)}", exc_info=True)

    try:
        from app.database import SessionLocal
        from app.services.email_event_registry import seed_event_configs
        _db = SessionLocal()
        try:
            created = seed_event_configs(_db)
            logging.info("Email event configs seeded at startup: added=%d", created)
        finally:
            _db.close()
    except Exception as e:
        logging.error(f"Failed to seed email event configs at startup: {str(e)}", exc_info=True)

    try:
        from app.database import SessionLocal
        from app.services import it_support_bootstrap
        _db = SessionLocal()
        try:
            it_support_bootstrap.run(_db)
        finally:
            _db.close()
    except Exception as e:
        logging.error(f"IT support bootstrap failed at startup: {str(e)}", exc_info=True)

    try:
        from app.database import SessionLocal
        from app.services import record_action_bootstrap
        _db = SessionLocal()
        try:
            record_action_bootstrap.run(_db)
        finally:
            _db.close()
    except Exception as e:
        logging.error(f"Record-action bootstrap failed at startup: {str(e)}", exc_info=True)

    # AI assistant wishlist clustering — register the callable so ops can wire
    # it to the existing background scheduler (or cron). We do not schedule it
    # by default to avoid surprise traffic on environments without an OpenAI
    # API key. To enable nightly runs, add a `scheduled_tasks` row keyed
    # "ai_wishlist_clustering" or invoke `python -m app.jobs.ai_wishlist_clustering`.
    try:
        from app.services.scheduled_task_service import register_handler
        from app.jobs.ai_wishlist_clustering import run_clustering_job

        def _handler_ai_wishlist_clustering(db, _task):
            return run_clustering_job(db=db)

        register_handler("ai_wishlist_clustering", _handler_ai_wishlist_clustering)
        logging.info("Registered scheduled task handler: ai_wishlist_clustering")
    except Exception as e:
        logging.error(f"Failed to register ai_wishlist_clustering handler: {str(e)}", exc_info=True)

@app.on_event("shutdown")
async def shutdown_event():
    """Shutdown event: stop scheduler."""
    global scheduler
    if scheduler:
        try:
            scheduler.shutdown()
            logging.info("Background scheduler stopped")
        except Exception as e:
            logging.error(f"Error stopping scheduler: {str(e)}", exc_info=True)


@app.get("/")
async def root():
    """Root endpoint."""
    return {"message": "Sorento CRM API", "version": "1.0.0"}


@app.get("/health")
async def health_check():
    """Readiness probe: 200 only if DB reachable. Blue/green deploy gates color swap on this."""
    try:
        from sqlalchemy import text
        from app.database import SessionLocal
        db = SessionLocal()
        try:
            db.execute(text("SELECT 1"))
        finally:
            db.close()
        return {"status": "healthy"}
    except Exception as e:
        return JSONResponse(
            status_code=503,
            content={"status": "unhealthy", "error": str(e)[:200]},
        )
