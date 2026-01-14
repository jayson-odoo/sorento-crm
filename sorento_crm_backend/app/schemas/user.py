"""User management schemas."""
from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class UserRoleBase(BaseModel):
    slug: str
    name: str
    description: Optional[str] = None
    is_protected: bool = False
    is_default: bool = False


class UserRoleCreate(UserRoleBase):
    permissions: Optional[list[str]] = None  # Permission IDs


class UserRoleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_protected: Optional[bool] = None
    is_default: Optional[bool] = None


class UserRoleSimple(BaseModel):
    id: str
    name: str
    
    class Config:
        from_attributes = True


class UserRoleResponse(UserRoleBase):
    id: str
    created_at: datetime
    
    class Config:
        from_attributes = True


class UserPermissionBase(BaseModel):
    slug: str
    name: str
    description: Optional[str] = None


class UserPermissionCreate(UserPermissionBase):
    pass


class UserPermissionUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class UserPermissionResponse(UserPermissionBase):
    id: str
    created_at: datetime
    
    class Config:
        from_attributes = True


class UserBase(BaseModel):
    email: str
    name: Optional[str] = None
    role_id: str
    status: str = "INACTIVE"
    country: Optional[str] = None
    timezone: Optional[str] = None


class UserCreate(UserBase):
    pass


class UserUpdate(BaseModel):
    name: Optional[str] = None
    role_id: Optional[str] = None
    status: Optional[str] = None
    country: Optional[str] = None
    timezone: Optional[str] = None
    avatar: Optional[str] = None


class UserResponse(UserBase):
    id: str
    avatar: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    last_sign_in_at: Optional[datetime] = None
    role: Optional[UserRoleSimple] = None
    
    class Config:
        from_attributes = True


class AccessAgentBase(BaseModel):
    code: str
    name: str
    description: Optional[str] = None
    is_active: bool = True
    pic_respond_user_id: Optional[str] = None


class AccessAgentCreate(AccessAgentBase):
    pass


class AccessAgentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None
    pic_respond_user_id: Optional[str] = None


class AccessAgentResponse(AccessAgentBase):
    id: str
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True
