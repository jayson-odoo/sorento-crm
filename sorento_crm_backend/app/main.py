"""FastAPI application entry point."""
from fastapi import FastAPI, Request, status
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
        content={"detail": exc.errors()}
    )

# Include API routes
app.include_router(api_router, prefix="/api/v1")

# Initialize scheduler for background tasks
scheduler = None

@app.on_event("startup")
async def startup_event():
    """Startup event: initialize scheduler."""
    global scheduler
    try:
        from app.scheduler.integration_scheduler import start_scheduler
        scheduler = start_scheduler()
        logging.info("Background scheduler started successfully")
    except Exception as e:
        logging.error(f"Failed to start scheduler: {str(e)}", exc_info=True)

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
