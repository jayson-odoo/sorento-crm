"""Logging middleware for API requests."""
import time
import uuid
import logging
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from app.services.logging import log_api_request
from app.audit_context import start_request_context

logger = logging.getLogger(__name__)


class LoggingMiddleware(BaseHTTPMiddleware):
    """Middleware to log all API requests and set request-scoped audit context (IP)."""
    
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        # One fresh, MUTABLE audit context per request (#1281 S0). Auth dependencies fill in
        # the principal by mutating this object, which a sync dependency running on a copied
        # context can still reach. Request id: an inbound X-Trace-Id if present, else minted;
        # correlation id: the request id, or an inbound X-Correlation-Id (the header
        # api_call_log reads) once an integration key authenticates. Both clamped to 64.
        ip = request.client.host if request.client else None
        ctx = start_request_context(
            ip,
            request.headers.get("X-Trace-Id") or uuid.uuid4().hex[:16],
            request.headers.get("X-Correlation-Id"),
        )
        trace_id = ctx.request_id

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
