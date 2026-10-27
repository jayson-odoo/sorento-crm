"""Photos read out of a supplier catalogue PDF, awaiting review (CATALOG-IMAGES).

Plan: ``documentation/plans/products/PLAN-catalog-image-extract-27oct.md`` "Data".

A reading is the upload (the PDF, its folder, where the worker got to); a photo is one placement
cut out of it, with the product the code ladder proposed and the user's decision. Nothing here
touches a product until Attach.
"""
import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base
from app.models.base import CompanyScopedMixin


def _uuid_str():
    return str(uuid.uuid4())


class CataloguePhotoReading(Base, CompanyScopedMixin):
    __tablename__ = "catalogue_photo_readings"
    __audit_skip__ = "catalogue read job state"
    __table_args__ = (
        Index("ix_catalogue_photo_readings_company_created", "company_id", "created_at"),
    )

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    file_name = Column(String(255), nullable=False)
    file_size = Column(Integer, nullable=False)
    # queued | reading | ready | failed
    status = Column(String(16), nullable=False, default="queued")
    page_count = Column(Integer, nullable=True)
    photo_count = Column(Integer, nullable=True)
    error = Column(Text, nullable=True)
    job_id = Column(String(64), nullable=True)
    pdf_attachment_id = Column(
        UUID(as_uuid=False), ForeignKey("attachments.id", ondelete="SET NULL"), nullable=True
    )
    directory_id = Column(
        UUID(as_uuid=False), ForeignKey("attachment_directories.id", ondelete="SET NULL"), nullable=True
    )
    created_by = Column(UUID(as_uuid=False), nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    photos = relationship(
        "CataloguePhoto", back_populates="reading", cascade="all, delete-orphan", passive_deletes=True
    )


class CataloguePhoto(Base):
    __tablename__ = "catalogue_photos"
    __audit_skip__ = "child rows of a catalogue reading"
    __table_args__ = (
        Index("ix_catalogue_photos_reading_page", "reading_id", "page", "position"),
    )

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    reading_id = Column(
        UUID(as_uuid=False),
        ForeignKey("catalogue_photo_readings.id", ondelete="CASCADE"),
        nullable=False,
    )
    page = Column(Integer, nullable=False)
    position = Column(Integer, nullable=False)
    attachment_id = Column(
        UUID(as_uuid=False), ForeignKey("attachments.id", ondelete="SET NULL"), nullable=True
    )
    sha256 = Column(String(64), nullable=True)
    dhash = Column(String(16), nullable=True)
    printed_code = Column(String(120), nullable=True)
    block_codes = Column(JSONB, nullable=False, default=list)
    placeholders = Column(JSONB, nullable=False, default=list)
    product_id = Column(
        UUID(as_uuid=False), ForeignKey("products.id", ondelete="SET NULL"), nullable=True
    )
    rung = Column(String(16), nullable=True)
    confidence = Column(String(16), nullable=False, default="none")
    suggestion = Column(String(120), nullable=True)
    # [{"id": product id, "product_code": code}] matched from the caption's other codes.
    other_block_products = Column(JSONB, nullable=False, default=list)
    also_attach_product_ids = Column(JSONB, nullable=False, default=list)
    duplicate_of_attachment_id = Column(
        UUID(as_uuid=False), ForeignKey("attachments.id", ondelete="SET NULL"), nullable=True
    )
    duplicate_distance = Column(Integer, nullable=True)
    # attach | skip | keep_both | replace
    decision = Column(String(16), nullable=False, default="attach")
    attached_at = Column(DateTime(timezone=False), nullable=True)

    reading = relationship("CataloguePhotoReading", back_populates="photos")
