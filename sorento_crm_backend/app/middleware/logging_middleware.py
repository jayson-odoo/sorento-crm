"""Logging middleware for API requests."""
import time
import logging
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from app.services.logging import log_api_request

logger = logging.getLogger(__name__)


class LoggingMiddleware(BaseHTTPMiddleware):
    """Middleware to log all API requests."""
    
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        
        # Skip logging for health check and docs
        if request.url.path in ["/health", "/docs", "/redoc", "/openapi.json"]:
            return await call_next(request)
        
        # Process request
        response = await call_next(request)
        
        # Calculate duration
        process_time = time.time() - start_time
        
        # Log request (async, don't block response)
        try:
            # Extract user from request state if available
            user_id = getattr(request.state, "user_id", None)
            
            # Log to system_logs table (fire and forget)
            # Note: This requires database session, which we'll handle in a background task
            # For now, just log to application logger
            logger.info(
                f"{request.method} {request.url.path} - "
                f"Status: {response.status_code} - "
                f"Duration: {process_time:.3f}s"
            )
        except Exception as e:
            logger.error(f"Failed to log request: {str(e)}")
        
        return response
