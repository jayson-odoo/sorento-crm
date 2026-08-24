"""Installable application modules (App Store) - catalog, per-tenant state, install audit."""
import uuid
from sqlalchemy import Column, String, Boolean, DateTime, Text, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func

from app.database import Base


class AppModuleCatalog(Base):
    """Canonical module definitions (catalog row per module_key)."""

    __tablename__ = "app_modules_catalog"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    module_key = Column(String(64), unique=True, nullable=False, index=True)
    display_name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    sort_order = Column(String(16), nullable=True)
    is_core = Column(Boolean, nullable=False, server_default="false")
    # Ordered list of module_key dependencies (install / resolver source of truth)
    dependencies = Column(JSONB, nullable=False, server_default="[]")


class TenantModule(Base):
    """Per-tenant installation and enablement state."""

    __tablename__ = "tenant_modules"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(64), nullable=False, index=True)
    module_key = Column(
        String(64),
        ForeignKey("app_modules_catalog.module_key", ondelete="CASCADE"),
        nullable=False,
    )
    enabled = Column(Boolean, nullable=False, server_default="true")
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        Index("uq_tenant_modules_tenant_module", "tenant_id", "module_key", unique=True),
    )


class AppModuleBundle(Base):
    """Preset module bundles for one-click install (editable via App Store admin)."""

    __tablename__ = "app_module_bundles"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    bundle_key = Column(String(64), unique=True, nullable=False, index=True)
    display_name = Column(String(255), nullable=False)
    # Ordered list of module_key (install uses resolver to add transitive deps)
    module_keys = Column(JSONB, nullable=False, server_default="[]")
    sort_order = Column(String(16), nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False)


class ModuleInstallEvent(Base):
    """Audit trail for module install / enable / disable."""

    __tablename__ = "module_install_events"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(64), nullable=False, index=True)
    module_key = Column(String(64), nullable=False, index=True)
    action = Column(String(32), nullable=False)  # install, enable, disable, bundle_install
    actor_user_id = Column(String(64), nullable=True)
    detail = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
