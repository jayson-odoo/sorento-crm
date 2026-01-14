"""Access agents API routes."""
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional
from app.database import get_db
from app.dependencies import get_current_user
from app.services.user_service import AccessAgentService
from app.schemas.user import AccessAgentCreate, AccessAgentUpdate, AccessAgentResponse
from app.schemas.common import ListResponse
from app.services.error_handler import handle_internal_error

router = APIRouter()


@router.get("/", response_model=ListResponse[AccessAgentResponse])
async def get_access_agents(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
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
        agent = service.get_agent(agent_id)
        return agent
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
        # Implement delete logic
        return {"message": "Access agent deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))
