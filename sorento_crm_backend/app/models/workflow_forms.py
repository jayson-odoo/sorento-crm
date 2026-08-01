"""Workflow forms: definitions, published versions, submissions, and transition history.

A submission's state is a ``status_id`` FK into the status engine (ADR-0013 rule 1),
resolved through the graph its DEFINITION scopes. The retired state-code ``VARCHAR`` and
the state machine that fed it from ``workflow_form_versions.schema`` are gone: the
engine is the authority for what a submission may do next.

The attribution columns stay ``String``. ``users.id`` is ``Column(String)``, and a
``uuid`` column cannot hold a foreign key to a ``text`` column.
"""
import uuid
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Text, Integer, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func, text

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
    created_by_user_id = Column(
        String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # ---- line-derived header status (F1a), opt-in per definition ----
    # Off by default with a server_default, because every definition that exists today
    # moves its header by transition and must keep doing exactly that.
    derives_status_from_lines = Column(
        Boolean, nullable=False, server_default="false", default=False
    )
    # The two rungs derivation toggles between, named by KEY and never by statuses.id: a
    # definition that forks its header graph gets fresh ids for the same rungs, so an id
    # here would point at the default graph's row and resolve to nothing after a fork.
    # Validated when the definition is saved (see workflow_submission_derived_status):
    # the open key must be the header graph's initial rung, and the resolved key must not
    # be terminal.
    derived_open_status_key = Column(String(64), nullable=True)
    derived_resolved_status_key = Column(String(64), nullable=True)

    # ---- portal submittability (F2b), two columns with one meaning each ----
    # The DOOR. Default closed, with a server default because the ALTER that adds this
    # column backfills definitions that already exist and a Python-side default never
    # runs for them. Every other gate in this codebase fails open; this is the one place
    # where that would hand a customer a form nobody meant them to see.
    portal_submittable = Column(
        Boolean, nullable=False, server_default="false", default=False
    )
    # The NARROWING, matched as a set OVERLAP against the contact's
    # contact_access_types. Empty means no narrowing, which is safe only because the
    # boolean above is the door: reaching this list at all took a deliberate flip.
    # Folding the two into one column would make "open to everyone" unexpressible
    # without a magic sentinel, and would flip the natural empty-list reading to
    # fail-open on exactly the column this gate exists to protect.
    portal_party_kinds = Column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb"), default=list
    )

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
    created_by_user_id = Column(
        String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    definition = relationship(
        "WorkflowFormDefinition",
        back_populates="versions",
        foreign_keys=[definition_id],
    )
    submissions = relationship("WorkflowSubmission", back_populates="version")

    __table_args__ = (
        # NOTE: definition_id already declares index=True above, which emits an
        # index named ix_workflow_form_versions_definition_id. Do NOT redeclare
        # it here — a second Index with the same name makes Base.metadata.create_all
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
    # One status trail, not two: the flush listeners already capture every tracked
    # column's before/after with actor, trace_id and contact attribution, so a status
    # change here is audited for free (ADR-0013 rule 11).
    __audit_track__ = True
    __audit_entity_type__ = "workflow_submission"

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
    # The state, in the status engine. NOT NULL: a status-less submission is one no
    # graph could ever move. Indexed because every listing and export filters on it.
    status_id = Column(
        UUID(as_uuid=False),
        ForeignKey("statuses.id"),
        nullable=False,
        index=True,
    )
    header_data = Column(JSONB, nullable=False, server_default="{}")
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False)
    created_by_user_id = Column(
        String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_by_user_id = Column(
        String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # ---- filed from the portal by a CONTACT (F2b) ----
    # Text, never uuid: respond_contacts.id is a TEXT column, and a uuid column cannot
    # hold a foreign key to a text one. Same trap as users.id above. Nullable, because
    # every submission a logged-in user files has no respondent contact at all, and
    # SET NULL so deleting a contact does not delete the form they filed.
    respondent_contact_id = Column(
        Text, ForeignKey("respond_contacts.id", ondelete="SET NULL"), nullable=True
    )
    # What SPAWNED this submission (an order, a service job, a contact), which is the
    # opposite referent to the same pair on conversation_sla_tracking. Kept anyway:
    # ADR-0009 already establishes this pair as the repo's polymorphic idiom.
    # String, not uuid: a polymorphic pointer cannot assume every target table has a
    # uuid primary key, and respond_contacts / users are keyed by text.
    source_entity_type = Column(String(64), nullable=True)
    source_entity_id = Column(String(128), nullable=True)
    # Written in the creating INSERT, never later and never from a payload: the admin
    # chat panel reads this column when it opens the submission, and a row that starts
    # NULL renders an empty conversation with no error anywhere.
    respond_inbox_url = Column(Text, nullable=True)

    definition = relationship("WorkflowFormDefinition")
    version = relationship("WorkflowFormVersion", back_populates="submissions")
    status = relationship("Status", foreign_keys=[status_id])
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
        # The portal listing is "my submissions, newest first", so the sort column
        # belongs in the index alongside the contact.
        Index(
            "ix_workflow_submissions_respondent_created",
            "respondent_contact_id",
            "created_at",
        ),
        # "Which forms did this order spawn" is the only way the polymorphic pointer is
        # ever read, so both halves are indexed together.
        Index(
            "ix_workflow_submissions_source_entity",
            "source_entity_type",
            "source_entity_id",
        ),
    )

    # The frontend may not render UUIDs, so a serializer built straight off the ORM row
    # needs the key and the label, not only the id.
    @property
    def status_key(self):
        return getattr(self.status, "key", None)

    @property
    def status_label(self):
        return getattr(self.status, "label", None)


class WorkflowSubmissionLine(Base):
    """Repeating line rows (e.g. line items) for a submission.

    A line carries its own state and its own outcome, because Customer Service approves
    some lines and rejects others: ``status_id`` is the decision (in the status engine,
    on the ``workflow_submission_line`` graph) and ``disposition`` is how the decided
    line will be settled. They are orthogonal on purpose - a line can be approved with
    any disposition, and rejecting one implies none.
    """

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
    # NULLABLE, unlike the submission's: line-level status is opt-in per definition, and
    # most forms have lines that are just data. Still a real FK, so a status cannot be
    # deleted out from under a line. Indexed because count_records and the
    # count-by-key roll-up both filter on it.
    status_id = Column(
        UUID(as_uuid=False),
        ForeignKey("statuses.id"),
        nullable=True,
        index=True,
    )
    # A ``lookup_options.value``, validated app-side against the active options of the
    # set bound to ('workflow_submission_lines', 'disposition') -- the same shape as the
    # existing bindings, so no FK here.
    disposition = Column(String(150), nullable=True)
    # "Nothing to collect" requires a reason, and a reason has nowhere else to land.
    disposition_reason = Column(Text, nullable=True)

    submission = relationship("WorkflowSubmission", back_populates="lines")
    status = relationship("Status", foreign_keys=[status_id])

    __table_args__ = (
        Index("ix_workflow_submission_lines_submission_group", "submission_id", "line_group_id"),
    )

    # The frontend may not render UUIDs, and reporting groups by key, so a line reaches a
    # serializer holding both the way the header does.
    @property
    def status_key(self):
        return getattr(self.status, "key", None)

    @property
    def status_label(self):
        return getattr(self.status, "label", None)


class WorkflowSubmissionTransitionLog(Base):
    """Which edge moved a submission, and the remark the mover left.

    ``audit_logs`` already records the ``status_id`` before/after on every accepted move
    (``WorkflowSubmission.__audit_track__``). What it cannot record is WHICH edge
    authorised the move or the remark that came with it, and those are the two things a
    reviewer reads. So this table keeps only that, keyed by status id rather than by a
    code.
    """

    __tablename__ = "workflow_submission_transition_logs"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    submission_id = Column(
        UUID(as_uuid=False),
        ForeignKey("workflow_submissions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Nullable for a first entry into the graph, which no edge authorises. No ondelete:
    # a status a log row references must not be deletable out from under history.
    from_status_id = Column(
        UUID(as_uuid=False), ForeignKey("statuses.id"), nullable=True
    )
    to_status_id = Column(
        UUID(as_uuid=False), ForeignKey("statuses.id"), nullable=False
    )
    # An admin editing a graph deletes status_transitions rows, and history must outlive
    # that edit -- hence nullable + SET NULL rather than a cascade that would erase the
    # trail.
    status_transition_id = Column(
        UUID(as_uuid=False),
        ForeignKey("status_transitions.id", ondelete="SET NULL"),
        nullable=True,
    )
    remark = Column(Text, nullable=True)
    user_id = Column(
        String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    submission = relationship("WorkflowSubmission", back_populates="transition_logs")
    from_status = relationship("Status", foreign_keys=[from_status_id])
    to_status = relationship("Status", foreign_keys=[to_status_id])

    @property
    def from_status_key(self):
        return getattr(self.from_status, "key", None)

    @property
    def to_status_key(self):
        return getattr(self.to_status, "key", None)
