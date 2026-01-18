"""Integration logging service for business logic."""
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import datetime
import json
import logging
from app.models.integration import IntegrationLog
from app.schemas.integration import IntegrationLogCreate, IntegrationLogUpdate
from app.services.error_handler import handle_not_found
from app.services.webhook_service import WebhookService

logger = logging.getLogger(__name__)


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
    
    def list_integration_logs(
        self,
        page: int = 1,
        limit: int = 50,
        status: Optional[str] = None,
        integration_channel: Optional[str] = None,
        business_table: Optional[str] = None,
        business_id: Optional[str] = None
    ):
        """List integration logs with pagination and filtering."""
        from app.schemas.common import PaginationResponse
        
        try:
            q = self.db.query(IntegrationLog)
            
            if status:
                q = q.filter(IntegrationLog.status == status)
            if integration_channel:
                q = q.filter(IntegrationLog.integration_channel == integration_channel)
            if business_table:
                q = q.filter(IntegrationLog.business_table == business_table)
            if business_id:
                q = q.filter(IntegrationLog.business_id == business_id)
            
            q = q.order_by(IntegrationLog.created_at.desc())
            
            total = q.count()
            offset = (page - 1) * limit
            logs = q.offset(offset).limit(limit).all()
            
            logger.debug(f"Found {total} integration logs, returning {len(logs)}")
            
            return {
                "data": logs,
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
    
    def send_webhook_for_log(self, log_id: str) -> tuple[bool, Optional[str]]:
        """
        Send webhook request for a specific integration log.
        
        Args:
            log_id: Integration log ID
            
        Returns:
            Tuple of (success: bool, error_message: Optional[str])
        """
        log = self.get_integration_log(log_id)
        
        # Check if already sent or processed successfully
        if log.status in ["success", "sent"]:
            logger.info(f"Integration log {log_id} already sent or processed (status: {log.status})")
            return True, None
        
        # Check retry limit
        if log.retry_count >= log.max_retry_allowed:
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
        
        # Update log with response
        update_data = IntegrationLogUpdate(
            status="sent" if success else "failed",  # Changed from "success" to "sent" - n8n will call back to update to success/failed
            status_code=status_code,
            response_payload=response_payload_str,
            response_headers=response_headers_str,
            error_code=error_code,
            error_message=error_message,
            retry_count=log.retry_count + 1
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
        Process all pending integration logs that are ready for retry.
        Called by cron job.
        
        Returns:
            Dict with processing results
        """
        from sqlalchemy import and_
        
        # Find logs that are pending and ready for retry
        now = datetime.utcnow()
        pending_logs = self.db.query(IntegrationLog).filter(
            and_(
                IntegrationLog.status.in_(["pending", "processing"]),
                (IntegrationLog.next_retry_at.is_(None)) | (IntegrationLog.next_retry_at <= now)
            )
        ).limit(100).all()  # Process up to 100 at a time
        
        processed = 0
        succeeded = 0
        failed = 0
        
        for log in pending_logs:
            try:
                success, error_msg = self.send_webhook_for_log(log.id)
                processed += 1
                if success:
                    succeeded += 1
                else:
                    failed += 1
            except Exception as e:
                logger.error(f"Error processing integration log {log.id}: {str(e)}", exc_info=True)
                failed += 1
        
        return {
            "processed": processed,
            "succeeded": succeeded,
            "failed": failed,
            "total_found": len(pending_logs)
        }
