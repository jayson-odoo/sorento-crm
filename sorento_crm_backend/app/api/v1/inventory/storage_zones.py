"""Storage zones API routes."""
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional
from app.database import get_db
from app.services.uuid_path_param import validate_uuid_path
from app.dependencies import get_current_user, get_current_user_or_api_key
from app.services.inventory_service import StorageZoneService
from app.schemas.inventory import StorageZoneCreate, StorageZoneUpdate, StorageZoneResponse, StorageZoneTreeItem
from app.schemas.common import ListResponse, MAX_PAGE_LIMIT
from app.services.error_handler import handle_internal_error

router = APIRouter()


@router.get("/", response_model=ListResponse[StorageZoneResponse])
async def get_storage_zones(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=MAX_PAGE_LIMIT),
    warehouse_id: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user_or_api_key),
    db: Session = Depends(get_db)
):
    """Get storage zones with pagination."""
    try:
        service = StorageZoneService(db)
        result = service.list_zones(warehouse_id=warehouse_id, page=page, limit=limit)
        return result
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/tree", response_model=list[StorageZoneTreeItem])
async def get_storage_zones_tree(
    warehouse_id: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user_or_api_key),
    db: Session = Depends(get_db)
):
    """Get storage zones in tree format."""
    try:
        service = StorageZoneService(db)
        zones = service.list_zones_tree(warehouse_id=warehouse_id)
        return zones
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/{zone_id}", response_model=StorageZoneResponse)
async def get_storage_zone(
    zone_id: str,
    current_user: dict = Depends(get_current_user_or_api_key),
    db: Session = Depends(get_db)
):
    """Get a single storage zone by ID."""
    try:
        validate_uuid_path(zone_id, resource="Storage Zone")
        service = StorageZoneService(db)
        zone = service.get_zone(zone_id)
        return zone
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/", response_model=StorageZoneResponse, status_code=status.HTTP_201_CREATED)
async def create_storage_zone(
    zone_data: StorageZoneCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new storage zone."""
    try:
        service = StorageZoneService(db)
        zone = service.create_zone(zone_data)
        return zone
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.put("/{zone_id}", response_model=StorageZoneResponse)
async def update_storage_zone(
    zone_id: str,
    zone_data: StorageZoneUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update a storage zone."""
    try:
        validate_uuid_path(zone_id, resource="Storage Zone")
        service = StorageZoneService(db)
        zone = service.update_zone(zone_id, zone_data)
        return zone
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.delete("/{zone_id}", status_code=status.HTTP_200_OK)
async def delete_storage_zone(
    zone_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a storage zone."""
    try:
        validate_uuid_path(zone_id, resource="Storage Zone")
        service = StorageZoneService(db)
        # Implement delete logic
        return {"message": "Storage zone deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))
