"""Logging middleware for API requests."""
import time
import uuid
import logging
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from app.services.logging import log_api_request
from app.audit_context import set_audit_context, set_trace_id

logger = logging.getLogger(__name__)


class LoggingMiddleware(BaseHTTPMiddleware):
    """Middleware to log all API requests and set request-scoped audit context (IP)."""
    
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        # Set audit context so automatic audit logging has at least IP (user_id set by auth deps)
        ip = request.client.host if request.client else None
        set_audit_context(None, ip)
        # Correlation id for this request (honour an inbound X-Trace-Id if present,
        # else mint one). Copied onto every audit row written during the request.
        trace_id = request.headers.get("X-Trace-Id") or uuid.uuid4().hex[:16]
        set_trace_id(trace_id)

        # Skip logging for health check and docs
        if request.url.path in ["/health", "/docs", "/redoc", "/openapi.json"]:
            response = await call_next(request)
            response.headers["X-Trace-Id"] = trace_id
            return response

        # Process request
        response = await call_next(request)
        response.headers["X-Trace-Id"] = trace_id
        
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
