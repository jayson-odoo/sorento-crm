"""Webhook service for sending HTTP requests to external endpoints."""
import os
import logging
import httpx
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
import json

logger = logging.getLogger(__name__)


class WebhookService:
    """Service for sending webhook requests to external endpoints."""
    
    def __init__(self):
        """Initialize webhook service."""
        self.timeout = 30  # seconds
    
    def send_webhook(
        self,
        url: str,
        payload: Dict[str, Any],
        headers: Optional[Dict[str, str]] = None
    ) -> tuple[bool, Optional[int], Optional[Dict[str, Any]], Optional[str], Optional[str]]:
        """
        Send POST request to webhook URL.
        
        Args:
            url: Webhook endpoint URL
            payload: Request body as dictionary
            headers: Optional request headers
            
        Returns:
            Tuple of (success: bool, status_code: Optional[int], 
                     response_data: Optional[Dict], error_code: Optional[str], 
                     error_message: Optional[str])
        """
        if not url:
            return False, None, None, "MISSING_URL", "Webhook URL is not configured"
        
        # Validate and fix URL - ensure it has http:// or https:// protocol
        original_url = url
        url = url.strip()
        if not url.startswith(('http://', 'https://')):
            # Try to auto-fix by adding https://
            if url.startswith('//'):
                url = 'https:' + url
                logger.warning(f"Webhook URL missing protocol, auto-adding https://. Original: {original_url}, Fixed: {url}")
            elif '://' not in url:
                # Assume https:// if no protocol specified
                fixed_url = 'https://' + url
                logger.warning(f"Webhook URL missing protocol, auto-adding https://. Original: {original_url}, Fixed: {fixed_url}")
                url = fixed_url
            else:
                # Invalid URL format
                return False, None, None, "INVALID_URL", f"Webhook URL is missing 'http://' or 'https://' protocol: {original_url}"
        
        default_headers = {
            "Content-Type": "application/json",
            "User-Agent": "Sorento-CRM/1.0.0"
        }
        if headers:
            default_headers.update(headers)
        
        try:
            logger.info(f"Sending webhook to {url} with payload: {payload}")
            
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(
                    url,
                    json=payload,
                    headers=default_headers
                )
                
                status_code = response.status_code
                success = 200 <= status_code < 300
                
                try:
                    response_data = response.json() if response.text else None
                except (ValueError, json.JSONDecodeError):
                    response_data = {"raw_response": response.text[:1000]}  # Limit size
                
                response_headers = dict(response.headers)
                
                if success:
                    logger.info(f"Webhook sent successfully. Status: {status_code}")
                    return True, status_code, response_data, None, None
                else:
                    error_msg = f"Webhook returned status {status_code}: {response.text[:500]}"
                    logger.warning(error_msg)
                    return False, status_code, response_data, f"HTTP_{status_code}", error_msg
                    
        except httpx.TimeoutException as e:
            error_msg = f"Webhook request timed out after {self.timeout}s: {str(e)}"
            logger.error(error_msg)
            return False, None, None, "TIMEOUT", error_msg
            
        except httpx.ConnectError as e:
            error_msg = f"Failed to connect to webhook endpoint: {str(e)}"
            logger.error(error_msg)
            return False, None, None, "CONNECTION_ERROR", error_msg
            
        except httpx.RequestError as e:
            # Check if it's a URL validation error
            error_str = str(e)
            if "http://" in error_str.lower() or "https://" in error_str.lower() or "protocol" in error_str.lower():
                error_msg = f"Webhook request failed: Request URL is missing an 'http://' or 'https://' protocol. URL: {url}"
            else:
                error_msg = f"Webhook request failed: {error_str}"
            logger.error(error_msg)
            return False, None, None, "REQUEST_ERROR", error_msg
            
        except Exception as e:
            error_msg = f"Unexpected error sending webhook: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return False, None, None, "UNKNOWN_ERROR", error_msg
    
    def calculate_next_retry_at(self, retry_count: int) -> datetime:
        """
        Calculate next retry time using exponential backoff.
        
        Args:
            retry_count: Current retry attempt number
            
        Returns:
            Next retry datetime
        """
        # Exponential backoff: 2^retry_count minutes
        minutes = 2 ** retry_count
        return datetime.utcnow() + timedelta(minutes=minutes)
