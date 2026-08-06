"""System logs API routes."""
from fastapi import APIRouter, Depends, Query, HTTPException, status, Body
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime
from pydantic import BaseModel
from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import SystemLog, User
from app.schemas.common import ListResponse
from app.services.error_handler import handle_internal_error
from sqlalchemy import or_, and_


class SystemLogCreate(BaseModel):
    event: str
    user_id: str
    entity_id: Optional[str] = None
    entity_type: Optional[str] = None
    description: Optional[str] = None
    ip_address: Optional[str] = None
    meta: Optional[str] = None

router = APIRouter()


@router.get("/", response_model=ListResponse)
def get_system_logs(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    query: Optional[str] = Query(None),
    user_id: Optional[str] = Query(None),
    createdAtFrom: Optional[str] = Query(None),
    createdAtTo: Optional[str] = Query(None),
    sort: Optional[str] = Query("created_at"),
    dir: Optional[str] = Query("desc"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get system logs with pagination and filtering."""
    try:
        q = db.query(SystemLog)
        
        filters = []
        
        if user_id:
            filters.append(SystemLog.user_id == user_id)
        
        if createdAtFrom or createdAtTo:
            date_filters = []
            if createdAtFrom:
                date_filters.append(SystemLog.created_at >= datetime.fromisoformat(createdAtFrom.replace('Z', '+00:00')))
            if createdAtTo:
                date_filters.append(SystemLog.created_at <= datetime.fromisoformat(createdAtTo.replace('Z', '+00:00')))
            if date_filters:
                filters.append(and_(*date_filters))
        
        if query:
            filters.append(
                or_(
                    SystemLog.event.ilike(f"%{query}%"),
                    SystemLog.description.ilike(f"%{query}%"),
                    SystemLog.ip_address.ilike(f"%{query}%"),
                    SystemLog.entity_id.ilike(f"%{query}%"),
                    SystemLog.entity_type.ilike(f"%{query}%"),
                    User.name.ilike(f"%{query}%")
                )
            )
            q = q.join(User)
        
        if filters:
            q = q.filter(and_(*filters))
        
        total = q.count()
        
        # Handle sorting
        sort_attr = getattr(SystemLog, sort.replace('user_name', 'created_at') if sort == 'user_name' else sort, SystemLog.created_at)
        if dir == "desc":
            sort_attr = sort_attr.desc()
        else:
            sort_attr = sort_attr.asc()
        
        logs = q.order_by(sort_attr).offset((page - 1) * limit).limit(limit).all()
        
        # Transform to response format
        log_data = []
        for log in logs:
            log_dict = {
                "id": log.id,
                "event": log.event,
                "entityId": log.entity_id,
                "entityType": log.entity_type,
                "description": log.description,
                "createdAt": log.created_at.isoformat(),
                "ipAddress": log.ip_address,
            }
            if hasattr(log, 'user') and log.user:
                log_dict["user"] = {
                    "id": log.user.id,
                    "name": log.user.name,
                    "email": log.user.email,
                    "avatar": log.user.avatar,
                }
            log_data.append(log_dict)
        
        return ListResponse(
            data=log_data,
            pagination={
                "total": total,
                "page": page,
                "limit": limit
            }
        )
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/users/{user_id}", response_model=ListResponse)
async def get_user_system_logs(
    user_id: str,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    query: Optional[str] = Query(None),
    createdAtFrom: Optional[str] = Query(None),
    createdAtTo: Optional[str] = Query(None),
    sort: Optional[str] = Query("created_at"),
    dir: Optional[str] = Query("desc"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get system logs for a specific user."""
    return await get_system_logs(
        page=page,
        limit=limit,
        query=query,
        user_id=user_id,
        createdAtFrom=createdAtFrom,
        createdAtTo=createdAtTo,
        sort=sort,
        dir=dir,
        current_user=current_user,
        db=db
    )


@router.post("/", status_code=status.HTTP_201_CREATED)
def create_system_log(
    log_data: SystemLogCreate,
    db: Session = Depends(get_db)
):
    """Create a system log entry."""
    try:
        log = SystemLog(
            user_id=log_data.user_id,
            event=log_data.event,
            entity_id=log_data.entity_id,
            entity_type=log_data.entity_type,
            description=log_data.description,
            ip_address=log_data.ip_address,
            meta=log_data.meta
        )
        db.add(log)
        db.commit()
        db.refresh(log)
        return {"message": "System log created successfully", "id": log.id}
    except Exception as e:
        raise handle_internal_error(str(e))
