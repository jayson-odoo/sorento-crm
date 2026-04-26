"""Make commercial_core's relationships into base classes self-installing.

The module declares relationships from its own classes (CommercialLead, CommercialMasterQuotation)
into platform classes (Customer, WorkflowStage, RespondWorkspace, RespondContact) using
``back_populates="..."``. SQLAlchemy requires both sides agree, so the platform classes
need a matching property — but a fresh codebase that doesn't know about the commercial
module won't have them, and uploading the module then poisons the mapper registry.

This patch file adds the reciprocal properties **lazily, only when missing**. Result:
- Codebases that already declare the reciprocals (legacy / monorepo) → no-op.
- Codebases that ship without them (fresh installs of just commercial_core) → properties get
  injected at import time via ``mapper.add_property()``.

Idempotent: run twice and the second call short-circuits.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import relationship


def _has_property(model_cls: Any, name: str) -> bool:
    """Check if a relationship/column property is registered, without triggering mapper config.

    ``mapper.attrs`` triggers ``_check_configure()`` which can fire a premature
    cascade and cache failures while other modules' mappers are still mid-load.
    Inspect ``_props`` directly (raw declared properties) to avoid that.
    """
    mapper = getattr(model_cls, "__mapper__", None)
    if mapper is None:
        return False
    try:
        return name in mapper._props
    except Exception:
        return hasattr(model_cls, name)


def _add_if_missing(model_cls: Any, name: str, rel: Any) -> None:
    if _has_property(model_cls, name):
        return
    model_cls.__mapper__.add_property(name, rel)


def apply_base_patches() -> None:
    """Inject reciprocal relationships onto platform classes if absent."""
    # Import platform classes lazily so the patch file is importable even if
    # an upstream module hasn't loaded yet.
    try:
        from app.models.order import Customer  # type: ignore
    except Exception:
        Customer = None  # type: ignore
    try:
        from app.models.workflow_stage import WorkflowStage  # type: ignore
    except Exception:
        WorkflowStage = None  # type: ignore
    try:
        from app.models.respond_workspace import RespondWorkspace  # type: ignore
    except Exception:
        RespondWorkspace = None  # type: ignore
    try:
        from app.models.access import RespondContact  # type: ignore
    except Exception:
        RespondContact = None  # type: ignore

    if Customer is not None:
        _add_if_missing(
            Customer,
            "commercial_leads",
            relationship(
                "CommercialLead",
                back_populates="customer",
                foreign_keys="CommercialLead.customer_id",
            ),
        )

    if WorkflowStage is not None:
        _add_if_missing(
            WorkflowStage,
            "leads",
            relationship(
                "CommercialLead",
                back_populates="lead_stage",
                foreign_keys="CommercialLead.lead_stage_id",
            ),
        )
        _add_if_missing(
            WorkflowStage,
            "master_quotations",
            relationship(
                "CommercialMasterQuotation",
                back_populates="quotation_stage",
                foreign_keys="CommercialMasterQuotation.quotation_stage_id",
            ),
        )

    if RespondWorkspace is not None:
        _add_if_missing(
            RespondWorkspace,
            "commercial_leads",
            relationship("CommercialLead", back_populates="respond_workspace"),
        )

    if RespondContact is not None:
        _add_if_missing(
            RespondContact,
            "lead_links",
            relationship(
                "CommercialLeadRespondContact",
                back_populates="respond_contact",
                cascade="all, delete-orphan",
            ),
        )
