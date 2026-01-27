"""Authentication models."""
from sqlalchemy import Column, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base
import uuid


class VerificationToken(Base):
    __tablename__ = "verification_tokens"
    
    identifier = Column(String, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    token = Column(String, primary_key=True)
    expires = Column(DateTime(timezone=True), nullable=False)
