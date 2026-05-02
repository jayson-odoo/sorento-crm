"""FastAPI application entry point."""
from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
import logging
from app.config import settings
from app.api.v1 import api_router
from app.services.error_handler import AppException
from app.middleware.logging_middleware import LoggingMiddleware

# Configure logging
logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
# Enable debug logging for dependencies module
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

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
    expose_headers=["*"],
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
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "message": "Internal server error",
            "detail": str(exc),
            "type": type(exc).__name__
        }
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

# Include API routes
app.include_router(api_router, prefix="/api/v1")

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
    try:
        from app.scheduler.task_scheduler import start_scheduler
        scheduler = start_scheduler()
        logging.info("Background scheduler started successfully")
    except Exception as e:
        logging.error(f"Failed to start scheduler: {str(e)}", exc_info=True)
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
    """Health check endpoint."""
    return {"status": "healthy"}
