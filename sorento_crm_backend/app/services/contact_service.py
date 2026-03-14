"""Contact service for business logic."""
from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from typing import Optional
import logging
import json
from app.models.access import RespondContact
from app.schemas.user import RespondContactCreate, RespondContactUpdate, RespondContactResponse, ContactAgentAccessCreate
from app.services.error_handler import handle_not_found, handle_conflict
from app.services.integration_service import RespondClient, IntegrationLogService
from app.schemas.integration import IntegrationLogCreate
from app.schemas.common import ListResponse, PaginationResponse

logger = logging.getLogger(__name__)


class ContactService:
    """Service for respond contact operations."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def get_contact(self, contact_id: str) -> RespondContact:
        """Get a contact by ID."""
        contact = self.db.query(RespondContact).filter(RespondContact.id == contact_id).first()
        if not contact:
            raise handle_not_found("Respond Contact", contact_id)
        return contact
    
    def get_contact_by_phone(self, phone_number: str) -> Optional[RespondContact]:
        """Get a contact by phone number."""
        return self.db.query(RespondContact).filter(RespondContact.phone_number == phone_number).first()
    
    def list_contacts(
        self,
        page: int = 1,
        limit: int = 50,
        query: Optional[str] = None,
        sort_field: str = "created_at",
        sort_dir: str = "asc"
    ):
        """List contacts with pagination and filtering."""
        q = self.db.query(RespondContact)
        
        if query:
            q = q.filter(
                or_(
                    RespondContact.phone_number.ilike(f"%{query}%"),
                    RespondContact.name.ilike(f"%{query}%")
                )
            )
        
        total = q.count()
        
        # Handle sorting
        sort_map = {
            "phone_number": RespondContact.phone_number,
            "name": RespondContact.name,
            "created_at": RespondContact.created_at,
            "updated_at": RespondContact.updated_at,
        }
        sort_attr = sort_map.get(sort_field, RespondContact.created_at)
        if sort_dir == "desc":
            sort_attr = sort_attr.desc()
        else:
            sort_attr = sort_attr.asc()
        
        contacts = q.order_by(sort_attr).offset((page - 1) * limit).limit(limit).all()
        
        # Validate and convert contacts to response models
        # Explicitly convert UUID to string to ensure Pydantic validation works
        contact_responses = []
        for contact in contacts:
            try:
                # Convert SQLAlchemy model to dict with explicit UUID string conversion
                contact_dict = {
                    'id': str(contact.id),
                    'phone_number': contact.phone_number,
                    'name': contact.name,
                    'user_type': contact.user_type,
                    'created_at': contact.created_at,
                    'updated_at': contact.updated_at,
                    'created_by': contact.created_by,
                }
                contact_responses.append(RespondContactResponse.model_validate(contact_dict))
            except Exception as e:
                logger.error(f"Error validating contact {contact.id}: {str(e)}", exc_info=True)
                raise
        
        return ListResponse(
            data=contact_responses,
            pagination=PaginationResponse(total=total, page=page, limit=limit),
            empty=total == 0
        )
    
    def assign_default_agents_to_contact(self, contact: RespondContact) -> None:
        """Assign all agents with assign_to_new_internal_contacts=True to this contact. Idempotent per agent (skips if access already exists).
        Sets valid_from to start of current year and valid_to to end of current year (for external-API-created contacts)."""
        from datetime import datetime
        from app.services.user_service import AccessAgentService

        now = datetime.utcnow()
        valid_from = datetime(now.year, 1, 1, 0, 0, 0)
        valid_to = datetime(now.year, 12, 31, 23, 59, 59)

        try:
            access_agent_service = AccessAgentService(self.db)
            default_agents = access_agent_service.list_agents_assign_to_new_internal_contacts()
            contact_name = (str(getattr(contact, "name", None)) if getattr(contact, "name", None) is not None else "") or ""
            for agent in default_agents:
                try:
                    access_agent_service.create_contact_access(
                        str(agent.id),
                        ContactAgentAccessCreate(
                            respond_contact_phone=str(contact.phone_number),
                            respond_contact_name=contact_name,
                            agent_id=str(agent.id),
                            is_allowed=True,
                            valid_from=valid_from,
                            valid_to=valid_to,
                        ),
                    )
                except Exception as assign_err:
                    # Already exists or other error - log and continue
                    logger.warning(
                        "Assign default agent %s to new contact %s failed: %s",
                        getattr(agent, "code", agent.id),
                        contact.phone_number,
                        assign_err,
                    )
        except Exception as e:
            logger.warning("Assign default agents to new contact failed: %s", e)

    def create_contact(self, contact_data: RespondContactCreate) -> RespondContact:
        """Create a new contact and assign default access agents (assign_to_new_internal_contacts=True)."""
        # Check if contact with same phone number already exists
        existing = self.get_contact_by_phone(contact_data.phone_number)
        if existing:
            raise handle_conflict("Contact with this phone number already exists.")
        
        contact = RespondContact(**contact_data.model_dump())
        self.db.add(contact)
        self.db.commit()
        self.db.refresh(contact)
        self.assign_default_agents_to_contact(contact)
        return contact
    
    def update_contact(self, contact_id: str, contact_data: RespondContactUpdate) -> RespondContact:
        """Update a contact."""
        contact = self.get_contact(contact_id)
        
        update_data = contact_data.model_dump(exclude_unset=True)
        
        # Check phone number uniqueness if being updated
        if 'phone_number' in update_data and update_data['phone_number'] != contact.phone_number:
            existing = self.get_contact_by_phone(update_data['phone_number'])
            if existing is not None and str(existing.id) != contact_id:
                raise handle_conflict("Contact with this phone number already exists.")
        
        for key, value in update_data.items():
            setattr(contact, key, value)
        
        self.db.commit()
        self.db.refresh(contact)
        return contact

    def delete_contact(self, contact_id: str) -> None:
        """Delete a respond contact and all contact–agent linkages. Related contact_agent_access rows are deleted; conversation_sla_tracking.respond_contact_id is SET NULL."""
        from app.models.access import ContactAgentAccess

        contact = self.get_contact(contact_id)
        # Delete contact–agent access linkages first so the contact can be removed
        self.db.query(ContactAgentAccess).filter(
            ContactAgentAccess.respond_contact_id == contact_id
        ).delete(synchronize_session=False)
        self.db.delete(contact)
        self.db.commit()

    def bulk_delete_contacts(self, contact_ids: list[str]) -> dict:
        """Delete multiple contacts by id. Returns deleted_count and message."""
        if not contact_ids:
            return {"deleted_count": 0, "message": "No contacts to delete."}
        from app.models.access import ContactAgentAccess
        deleted = 0
        for contact_id in contact_ids:
            contact = self.db.query(RespondContact).filter(RespondContact.id == contact_id).first()
            if contact:
                self.db.query(ContactAgentAccess).filter(
                    ContactAgentAccess.respond_contact_id == contact_id
                ).delete(synchronize_session=False)
                self.db.delete(contact)
                deleted += 1
        self.db.commit()
        return {"deleted_count": deleted, "message": f"Deleted {deleted} contact(s)."}

    def sync_contact_name(self, contact_id: str) -> RespondContact:
        """Sync contact name from Respond.io API."""
        contact = self.get_contact(contact_id)
        log_service = IntegrationLogService(self.db)
        
        # Create integration log for the sync operation
        request_payload = {
            "contact_id": contact_id,
            "phone_number": contact.phone_number,
            "action": "sync_contact_name"
        }
        
        try:
            client = RespondClient()
            # Use phone: prefix format
            payload = client.get_contact_by_phone(str(contact.phone_number))
            
            # Extract name from response - Respond.io returns firstName and lastName
            name = None
            user_type = None
            
            # Try to get name from various possible locations
            if payload.get("name"):
                name = payload.get("name")
            elif payload.get("displayName"):
                name = payload.get("displayName")
            elif payload.get("data", {}).get("name"):
                name = payload.get("data", {}).get("name")
            elif payload.get("contact", {}).get("name"):
                name = payload.get("contact", {}).get("name")
            else:
                # Construct name from firstName and lastName
                first_name = payload.get("firstName") or payload.get("first_name") or ""
                last_name = payload.get("lastName") or payload.get("last_name") or ""
                
                # Combine firstName and lastName with space
                if first_name and last_name:
                    name = f"{first_name} {last_name}".strip()
                elif first_name:
                    name = first_name.strip()
                elif last_name:
                    name = last_name.strip()
            
            # Extract user_type from custom_fields list
            custom_fields = (
                payload.get("custom_fields")
                or payload.get("customFields")
                or payload.get("data", {}).get("custom_fields")
                or payload.get("data", {}).get("customFields")
                or payload.get("contact", {}).get("custom_fields")
                or payload.get("contact", {}).get("customFields")
            )
            if isinstance(custom_fields, list):
                for field in custom_fields:
                    field_name = str(field.get("name", "")).strip().lower()
                    if field_name == "user_type":
                        user_type = field.get("value")
                        break
            
            if name or user_type is not None:
                if name:
                    setattr(contact, "name", name)
                if user_type is not None:
                    setattr(contact, "user_type", str(user_type).strip() if user_type is not None else None)
                self.db.commit()
                self.db.refresh(contact)
                logger.info(
                    f"Synced contact {contact.phone_number}: name={name or contact.name}, user_type={contact.user_type}"
                )
                
                # Log successful sync
                log_service.create_integration_log(
                    IntegrationLogCreate(
                        integration_channel="respond_io",
                        business_table="respond_contacts",
                        business_id=contact_id,
                        direction="outbound",
                        endpoint=f"/v2/contact/phone:{contact.phone_number}",
                        http_method="GET",
                        status="success",
                        response_payload=json.dumps(payload, indent=2)
                    ),
                    request_payload_dict=request_payload
                )
            else:
                error_msg = (
                    f"Could not find name or user_type in Respond.io response for {contact.phone_number}"
                )
                logger.warning(error_msg)
                
                # Log warning - no name found
                log_service.create_integration_log(
                    IntegrationLogCreate(
                        integration_channel="respond_io",
                        business_table="respond_contacts",
                        business_id=contact_id,
                        direction="outbound",
                        endpoint=f"/v2/contact/phone:{contact.phone_number}",
                        http_method="GET",
                        status="failed",
                        error_message=error_msg,
                        response_payload=json.dumps(payload, indent=2)
                    ),
                    request_payload_dict=request_payload
                )
            
            return contact
        except ValueError as e:
            # API key not configured
            error_msg = str(e)
            logger.error(f"Error syncing contact name for {contact_id}: {error_msg}", exc_info=True)
            
            # Log the error
            log_service.create_integration_log(
                IntegrationLogCreate(
                    integration_channel="respond_io",
                    business_table="respond_contacts",
                    business_id=contact_id,
                    direction="outbound",
                    endpoint=f"/v2/contact/phone:{contact.phone_number}",
                    http_method="GET",
                    status="failed",
                    error_code="CONFIGURATION_ERROR",
                    error_message=error_msg
                ),
                request_payload_dict=request_payload
            )
            raise
        except Exception as e:
            # Other errors (API errors, network errors, etc.)
            import httpx
            
            error_msg = str(e)
            error_code = "API_ERROR"
            status_code = None
            
            # Handle httpx exceptions
            response_payload = None
            if isinstance(e, httpx.HTTPStatusError):
                status_code = e.response.status_code
                error_code = f"HTTP_{status_code}"
                
                # Capture response payload first
                try:
                    response_text = e.response.text
                    # Limit response text size to prevent database issues (max 50KB)
                    max_response_size = 50000
                    if response_text and len(response_text) > max_response_size:
                        response_text = response_text[:max_response_size] + f"\n... (truncated, original size: {len(e.response.text)} bytes)"
                    
                    # Try to parse as JSON for better formatting
                    try:
                        response_json = e.response.json()
                        response_payload = json.dumps(response_json, indent=2)
                        # Limit JSON payload size
                        if len(response_payload) > max_response_size:
                            response_payload = response_payload[:max_response_size] + f"\n... (truncated)"
                        
                        # Extract meaningful error message from Respond.io response
                        if isinstance(response_json, dict):
                            api_message = response_json.get('message') or response_json.get('error') or response_json.get('detail')
                            if api_message:
                                error_msg = f"HTTP {status_code}: {api_message}"
                            else:
                                error_msg = f"HTTP {status_code}: {json.dumps(response_json)}"
                        else:
                            error_msg = f"HTTP {status_code}: {response_json}"
                    except (ValueError, json.JSONDecodeError):
                        # Not JSON, use raw text
                        response_payload = response_text
                        error_msg = f"HTTP {status_code}: {response_text[:500] if response_text else str(e)}"
                except Exception as ex:
                    logger.warning(f"Could not capture response payload: {str(ex)}")
                    error_msg = f"HTTP {status_code}: {str(e)}"
                
                # Log the full response for debugging
                if response_payload:
                    logger.debug(f"Respond.io API error response body: {response_payload[:1000]}")
            elif isinstance(e, httpx.TimeoutException):
                error_code = "TIMEOUT_ERROR"
                error_msg = "Request to Respond.io API timed out"
            elif isinstance(e, httpx.ConnectError):
                error_code = "CONNECTION_ERROR"
                error_msg = f"Failed to connect to Respond.io API: {str(e)}"
            elif isinstance(e, httpx.RequestError):
                error_code = "REQUEST_ERROR"
                error_msg = f"Request error: {str(e)}"
            
            logger.error(f"Error syncing contact name for {contact_id}: {error_msg}", exc_info=True)
            
            # Log the error with response payload
            log_service.create_integration_log(
                IntegrationLogCreate(
                    integration_channel="respond_io",
                    business_table="respond_contacts",
                    business_id=contact_id,
                    direction="outbound",
                    endpoint=f"/v2/contact/phone:{contact.phone_number}",
                    http_method="GET",
                    status="failed",
                    status_code=status_code,
                    error_code=error_code,
                    error_message=error_msg,
                    response_payload=response_payload  # Already captured above for HTTPStatusError
                ),
                request_payload_dict=request_payload
            )
            raise
    
    def get_or_create_contact(self, phone_number: str, name: Optional[str] = None) -> RespondContact:
        """Get existing contact or create a new one."""
        contact = self.get_contact_by_phone(phone_number)
        if contact is not None:
            # Update name if provided and different
            current_name = getattr(contact, "name", None) or ""
            if name and current_name != name:
                setattr(contact, "name", name)
                self.db.commit()
                self.db.refresh(contact)
            return contact
        
        # Create new contact
        contact_data = RespondContactCreate(phone_number=phone_number, name=name)
        return self.create_contact(contact_data)
