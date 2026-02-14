"""Attachment directories (folders) API."""
from fastapi import APIRouter, Depends, HTTPException

from app.database import get_db
from app.dependencies import get_current_user
from app.services.resources_service import AttachmentDirectoryService, AttachmentService
from app.schemas.resources import (
    AttachmentDirectoryCreate,
    AttachmentDirectoryUpdate,
    AttachmentDirectoryResponse,
    AttachmentDirectoryTreeNode,
)
from app.services.error_handler import handle_internal_error

router = APIRouter()


def _build_tree_node(service: AttachmentDirectoryService, dir_id: str) -> AttachmentDirectoryTreeNode:
    """Build a tree node with children from a directory ID."""
    d = service.get_directory(dir_id)
    children = [
        _build_tree_node(service, str(c.id))
        for c in service.list_flat(dir_id)
    ]
    return AttachmentDirectoryTreeNode(
        id=str(d.id),
        name=d.name,
        parent_id=str(d.parent_id) if d.parent_id else None,
        sort_order=d.sort_order,
        created_at=d.created_at,
        children=children,
    )


@router.get("/", response_model=list[AttachmentDirectoryResponse])
async def list_directories(
    parent_id: str | None = None,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    """List directories directly under parent_id (omit for root)."""
    try:
        service = AttachmentDirectoryService(db)
        dirs = service.list_flat(parent_id)
        return list(dirs)
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/tree", response_model=list[AttachmentDirectoryTreeNode])
async def get_directory_tree(
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    """Get full directory tree (root level with nested children)."""
    try:
        service = AttachmentDirectoryService(db)
        roots = service.list_flat(None)
        return [
            _build_tree_node(service, str(r.id))
            for r in roots
        ]
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/{directory_id}", response_model=AttachmentDirectoryResponse)
async def get_directory(
    directory_id: str,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    """Get a single directory by ID."""
    try:
        service = AttachmentDirectoryService(db)
        return service.get_directory(directory_id)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/", response_model=AttachmentDirectoryResponse, status_code=201)
async def create_directory(
    data: AttachmentDirectoryCreate,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    """Create a new directory."""
    try:
        service = AttachmentDirectoryService(db)
        return service.create_directory(data)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.put("/{directory_id}", response_model=AttachmentDirectoryResponse)
async def update_directory(
    directory_id: str,
    data: AttachmentDirectoryUpdate,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    """Update a directory."""
    try:
        service = AttachmentDirectoryService(db)
        return service.update_directory(directory_id, data)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.delete("/{directory_id}", status_code=200)
async def delete_directory(
    directory_id: str,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    """Delete a directory and soft-delete all attachments in it and its subfolders. Subfolders are cascade-deleted."""
    try:
        dir_service = AttachmentDirectoryService(db)
        dir_ids = dir_service.get_descendant_directory_ids(directory_id)
        attachment_service = AttachmentService(db)
        deleted_count = attachment_service.delete_attachments_in_directories(dir_ids, current_user["id"])
        dir_service.delete_directory(directory_id)
        return {
            "message": "Directory deleted",
            "attachments_deleted": deleted_count,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))
