"""Access agents API routes."""
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional
from app.database import get_db
from app.dependencies import get_current_user
from app.services.user_service import AccessAgentService
from app.schemas.user import (
    AccessAgentCreate,
    AccessAgentUpdate,
    AccessAgentResponse,
    ContactAgentAccessCreate,
    ContactAgentAccessUpdate,
    ContactAgentAccessResponse,
    RespondContactLookupRequest,
    RespondContactLookupResponse,
    AgentTeamsUpdate,
)
from app.schemas.common import ListResponse
from app.services.error_handler import handle_internal_error

router = APIRouter()


@router.get("/contact-access", response_model=ListResponse[ContactAgentAccessResponse])
async def get_all_contact_access_agents(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=10000),  # Increased limit for grouping
    query: Optional[str] = Query(None),
    agent_id: Optional[str] = Query(None),
    contact_id: Optional[str] = Query(None),
    sort: Optional[str] = Query("created_at"),
    dir: Optional[str] = Query("asc"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all contact access agents with pagination and filtering."""
    try:
        service = AccessAgentService(db)
        result = service.list_all_contact_accesses(
            page=page,
            limit=limit,
            query=query,
            agent_id=agent_id,
            contact_id=contact_id,
            sort_field=sort or "created_at",
            sort_dir=dir or "asc"
        )
        return result
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/", response_model=ListResponse[AccessAgentResponse])
async def get_access_agents(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=1000),
    query: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get access agents with pagination and search."""
    try:
        service = AccessAgentService(db)
        result = service.list_agents(page=page, limit=limit, query=query)
        return result
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/{agent_id}", response_model=AccessAgentResponse)
async def get_access_agent(
    agent_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get a single access agent by ID."""
    try:
        service = AccessAgentService(db)
        agent_dict = service.get_agent(agent_id)
        # Convert dict to response model
        return AccessAgentResponse(**agent_dict)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/", response_model=AccessAgentResponse, status_code=status.HTTP_201_CREATED)
async def create_access_agent(
    agent_data: AccessAgentCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new access agent."""
    try:
        service = AccessAgentService(db)
        agent = service.create_agent(agent_data)
        return agent
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.put("/{agent_id}", response_model=AccessAgentResponse)
async def update_access_agent(
    agent_id: str,
    agent_data: AccessAgentUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update an access agent."""
    try:
        service = AccessAgentService(db)
        agent = service.update_agent(agent_id, agent_data)
        return agent
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.delete("/{agent_id}", status_code=status.HTTP_200_OK)
async def delete_access_agent(
    agent_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete an access agent."""
    try:
        service = AccessAgentService(db)
        service.delete_agent(agent_id)
        return {"message": "Access agent deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/{agent_id}/teams")
async def get_agent_teams(
    agent_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List assignments with team name, members, last assigned and next in line (round-robin state)."""
    try:
        service = AccessAgentService(db)
        assignments = service.list_agent_teams_with_round_robin_state(agent_id)
        return {"assignments": assignments}
    except Exception as e:
        raise handle_internal_error(str(e))


@router.put("/{agent_id}/teams")
async def set_agent_teams(
    agent_id: str,
    body: AgentTeamsUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Set the team assignments for this agent (replaces existing). Body: assignments=[{code, team_id, tier?}]."""
    try:
        service = AccessAgentService(db)
        if body.assignments is not None:
            payload = [{"code": a.code, "team_id": a.team_id, "tier": getattr(a, "tier", None)} for a in body.assignments]
            service.set_agent_teams(agent_id, payload)
            assignments_with_state = service.list_agent_teams_with_round_robin_state(agent_id)
            return {"assignments": assignments_with_state}
        if body.team_ids is not None:
            payload = [{"code": tid, "team_id": tid} for tid in body.team_ids]
            service.set_agent_teams(agent_id, payload)
        else:
            service.set_agent_teams(agent_id, [])
        assignments_with_state = service.list_agent_teams_with_round_robin_state(agent_id)
        return {"assignments": assignments_with_state}
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/{agent_id}/contact-access", response_model=list[ContactAgentAccessResponse])
async def get_contact_access_agents(
    agent_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List contact access entries for an agent."""
    try:
        service = AccessAgentService(db)
        accesses = service.list_contact_accesses(agent_id)
        return [ContactAgentAccessResponse.model_validate(access) for access in accesses]
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error fetching contact access for agent {agent_id}: {str(e)}", exc_info=True)
        raise handle_internal_error(str(e))


@router.post(
    "/{agent_id}/contact-access",
    response_model=ContactAgentAccessResponse,
    status_code=status.HTTP_201_CREATED
)
async def create_contact_access_agent(
    agent_id: str,
    contact_data: ContactAgentAccessCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a contact access entry for an agent."""
    try:
        service = AccessAgentService(db)
        return service.create_contact_access(agent_id, contact_data)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.put(
    "/{agent_id}/contact-access/{contact_id}",
    response_model=ContactAgentAccessResponse
)
async def update_contact_access_agent(
    agent_id: str,
    contact_id: str,
    contact_data: ContactAgentAccessUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update a contact access entry."""
    try:
        service = AccessAgentService(db)
        return service.update_contact_access(contact_id, contact_data)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.delete("/{agent_id}/contact-access/{contact_id}", status_code=status.HTTP_200_OK)
async def delete_contact_access_agent(
    agent_id: str,
    contact_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a contact access entry."""
    try:
        service = AccessAgentService(db)
        service.delete_contact_access(contact_id)
        return {"message": "Contact access deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/contact-access/lookup", response_model=RespondContactLookupResponse)
async def lookup_contact_name(
    payload: RespondContactLookupRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Lookup contact name from Respond.io by identifier."""
    try:
        service = AccessAgentService(db)
        name = service.lookup_respond_contact_name(payload.identifier)
        return {"contact_name": name}
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post(
    "/{agent_id}/contact-access/{contact_id}/sync-contact-name",
    response_model=ContactAgentAccessResponse
)
async def sync_contact_name(
    agent_id: str,
    contact_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Sync contact name from Respond.io for a contact access entry."""
    try:
        service = AccessAgentService(db)
        return service.sync_contact_name(contact_id)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))
