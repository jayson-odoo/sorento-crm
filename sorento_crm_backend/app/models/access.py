"""Access control models."""
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Text, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
import uuid


class RespondContact(Base):
    __tablename__ = "respond_contacts"
    
    id = Column(Text, primary_key=True, default=lambda: str(uuid.uuid4()))
    phone_number = Column(Text, unique=True, nullable=False)
    name = Column(Text, nullable=True)
    user_type = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False)
    created_by = Column(Text, nullable=True)
    
    contact_accesses = relationship(
        "ContactAgentAccess",
        back_populates="contact",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_respond_contacts_phone_number", "phone_number"),
        Index("ix_respond_contacts_user_type", "user_type"),
    )


class AccessAgent(Base):
    __tablename__ = "access_agents"
    
    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    code = Column(Text, unique=True, nullable=False)
    name = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False)
    synced_to_excel = Column(Boolean, default=False, nullable=False)
    last_synced_to_excel = Column(DateTime(timezone=False), nullable=True)
    pic_respond_user_id = Column(Text, nullable=True)
    
    contact_accesses = relationship("ContactAgentAccess", back_populates="agent")
    user_accesses = relationship("UserAgentAccess", back_populates="agent")
    
    __table_args__ = (
        Index("ix_access_agents_is_active", "is_active"),
        Index("ix_access_agents_code", "code"),
    )


class ContactAgentAccess(Base):
    __tablename__ = "contact_agent_access"
    
    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    respond_contact_id = Column(Text, ForeignKey("respond_contacts.id", ondelete="CASCADE"), nullable=True)  # FK to respond_contacts
    respond_contact_phone = Column(Text, nullable=False)  # Keep for backward compatibility
    respond_contact_name = Column(Text, nullable=True)  # Keep for backward compatibility
    agent_id = Column(UUID(as_uuid=False), ForeignKey("access_agents.id", ondelete="CASCADE"), nullable=False)
    is_allowed = Column(Boolean, default=True, nullable=False)
    valid_from = Column(DateTime(timezone=False), nullable=True)
    valid_to = Column(DateTime(timezone=False), nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    created_by = Column(Text, nullable=True)
    synced_to_excel = Column(Boolean, default=False, nullable=False)
    last_synced_to_excel = Column(DateTime(timezone=False), nullable=True)
    updated_at = Column(DateTime(timezone=False), nullable=True)
    
    agent = relationship("AccessAgent", back_populates="contact_accesses")
    contact = relationship("RespondContact", back_populates="contact_accesses")
    
    __table_args__ = (
        Index("ix_contact_agent_access_agent_id", "agent_id"),
        Index("ix_contact_agent_access_respond_contact_id", "respond_contact_id"),
        Index("ix_contact_agent_access_respond_contact_phone", "respond_contact_phone"),
        # Unique constraint on respond_contact_id and agent_id to prevent duplicates
        # Note: This will be created via migration as a partial unique index to handle NULL values
    )


class UserAgentAccess(Base):
    __tablename__ = "user_agent_access"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    agent_id = Column(UUID(as_uuid=False), ForeignKey("access_agents.id", ondelete="CASCADE"), nullable=False)
    is_allowed = Column(Boolean, default=True, nullable=False)
    valid_from = Column(DateTime(timezone=False), nullable=True)
    valid_to = Column(DateTime(timezone=False), nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    user = relationship("User", back_populates="agent_accesses")
    agent = relationship("AccessAgent", back_populates="user_accesses")

    __table_args__ = (
        Index("ix_user_agent_access_user_id", "user_id"),
        Index("ix_user_agent_access_agent_id", "agent_id"),
        Index("uq_user_agent_access_user_id_agent_id", "user_id", "agent_id", unique=True),
    )
