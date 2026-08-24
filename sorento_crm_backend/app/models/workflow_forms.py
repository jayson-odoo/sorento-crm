"""Workflow forms: definitions, published versions, submissions, and transition history."""
import uuid
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Text, Integer, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class WorkflowFormDefinition(Base):
    """Top-level workflow form (builder draft + pointer to latest published version)."""

    __tablename__ = "workflow_form_definitions"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    code = Column(String(100), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, server_default="true")
    # Editable draft (not used for runtime until published)
    draft_schema = Column(JSONB, nullable=False, server_default="{}")
    published_version_id = Column(
        UUID(as_uuid=False),
        ForeignKey("workflow_form_versions.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False)
    created_by_user_id = Column(String(64), nullable=True)

    versions = relationship(
        "WorkflowFormVersion",
        back_populates="definition",
        foreign_keys="WorkflowFormVersion.definition_id",
        cascade="all, delete-orphan",
    )
    published_version = relationship(
        "WorkflowFormVersion",
        foreign_keys=[published_version_id],
        post_update=True,
    )

    __table_args__ = (Index("ix_workflow_form_definitions_is_active", "is_active"),)


class WorkflowFormVersion(Base):
    """Immutable published schema snapshot."""

    __tablename__ = "workflow_form_versions"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    definition_id = Column(
        UUID(as_uuid=False),
        ForeignKey("workflow_form_definitions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version_number = Column(Integer, nullable=False)
    schema = Column(JSONB, nullable=False)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    created_by_user_id = Column(String(64), nullable=True)

    definition = relationship(
        "WorkflowFormDefinition",
        back_populates="versions",
        foreign_keys=[definition_id],
    )
    submissions = relationship("WorkflowSubmission", back_populates="version")

    __table_args__ = (
        # NOTE: definition_id already declares index=True above, which emits an
        # index named ix_workflow_form_versions_definition_id. Do NOT redeclare
        # it here - a second Index with the same name makes Base.metadata.create_all
        # fail ("index ... already exists") on fresh sqlite binds in tests.
        Index(
            "uq_workflow_form_versions_def_ver",
            "definition_id",
            "version_number",
            unique=True,
        ),
    )


class WorkflowSubmission(Base):
    """A submitted record against a published form version."""

    __tablename__ = "workflow_submissions"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    definition_id = Column(
        UUID(as_uuid=False),
        ForeignKey("workflow_form_definitions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version_id = Column(
        UUID(as_uuid=False),
        ForeignKey("workflow_form_versions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    current_state_code = Column(String(64), nullable=False, index=True)
    header_data = Column(JSONB, nullable=False, server_default="{}")
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False)
    created_by_user_id = Column(String(64), nullable=True)
    updated_by_user_id = Column(String(64), nullable=True)

    definition = relationship("WorkflowFormDefinition")
    version = relationship("WorkflowFormVersion", back_populates="submissions")
    lines = relationship(
        "WorkflowSubmissionLine",
        back_populates="submission",
        cascade="all, delete-orphan",
        order_by="WorkflowSubmissionLine.sort_order",
    )
    transition_logs = relationship(
        "WorkflowSubmissionTransitionLog",
        back_populates="submission",
        cascade="all, delete-orphan",
        order_by="WorkflowSubmissionTransitionLog.created_at",
    )

    __table_args__ = (
        Index("ix_workflow_submissions_definition_created", "definition_id", "created_at"),
    )


class WorkflowSubmissionLine(Base):
    """Repeating line rows (e.g. line items) for a submission."""

    __tablename__ = "workflow_submission_lines"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    submission_id = Column(
        UUID(as_uuid=False),
        ForeignKey("workflow_submissions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    line_group_id = Column(String(64), nullable=False)
    sort_order = Column(Integer, nullable=False, server_default="0")
    row_data = Column(JSONB, nullable=False, server_default="{}")

    submission = relationship("WorkflowSubmission", back_populates="lines")

    __table_args__ = (
        Index("ix_workflow_submission_lines_submission_group", "submission_id", "line_group_id"),
    )


class WorkflowSubmissionTransitionLog(Base):
    """Audit trail of state changes."""

    __tablename__ = "workflow_submission_transition_logs"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    submission_id = Column(
        UUID(as_uuid=False),
        ForeignKey("workflow_submissions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    from_state_code = Column(String(64), nullable=True)
    to_state_code = Column(String(64), nullable=False)
    transition_id = Column(String(64), nullable=True)
    remark = Column(Text, nullable=True)
    user_id = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    submission = relationship("WorkflowSubmission", back_populates="transition_logs")
