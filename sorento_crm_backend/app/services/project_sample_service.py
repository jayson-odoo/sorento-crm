"""Sample submissions (UAC Group F, AC-F1 and AC-F2).

A sample binds to a quotation VERSION, never to the quotation. "Which price was the
developer looking at when they approved this finish" is the question the binding exists
to answer, and only the version can answer it.

The one refusal here is AC-F2: a NEW sample cannot be recorded against a superseded
version, which enforces the client's "update the quotation first" rule. Sending a sample
against a price the developer is no longer looking at is how a project gets delivered at
last month's number.

The corollary is deliberate and pinned by a test: a sample already recorded against a
version that LATER gets superseded stays, and stays editable. The developer's feedback
normally arrives after the revise, and refusing to record it would throw away the one
thing the sample exists to capture.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.projects import (
    Project,
    ProjectQuotation,
    ProjectQuotationVersion,
    ProjectSample,
)
from app.services.error_handler import AppException

SAMPLE_FIELDS = (
    "quotation_version_id",
    "submitted_on",
    "developer_feedback",
    "salesperson_notes",
)


def _version_or_422(
    db: Session, *, project: Project, version_id: Optional[str]
) -> ProjectQuotationVersion:
    if not version_id:
        raise AppException(
            status_code=422,
            message="A sample has to say which quotation version it was sent against.",
            code="sample_version_required",
        )
    version = (
        db.query(ProjectQuotationVersion)
        .filter(ProjectQuotationVersion.id == version_id)
        .first()
    )
    if not version:
        raise AppException(
            status_code=404,
            message="Quotation version not found.",
            code="quotation_version_not_found",
        )
    quotation = (
        db.query(ProjectQuotation)
        .filter(ProjectQuotation.id == version.quotation_id)
        .first()
    )
    # A sample on project A bound to project B's version would corrupt every rollup that
    # reads it, and the mistake is one mis-click away in an API client.
    if quotation is None or quotation.project_id != project.id:
        raise AppException(
            status_code=422,
            message="That quotation version belongs to a different project.",
            code="sample_version_foreign_project",
        )
    return version


def _current_version_no(db: Session, quotation_id: str) -> Optional[int]:
    return (
        db.query(func.max(ProjectQuotationVersion.version_no))
        .filter(ProjectQuotationVersion.quotation_id == quotation_id)
        .scalar()
    )


def assert_version_is_current(db: Session, version: ProjectQuotationVersion) -> None:
    """AC-F2. The message names the version to go to: "not allowed" with no next step
    just makes the user try the same thing again."""
    highest = _current_version_no(db, version.quotation_id)
    if highest is not None and version.version_no < highest:
        raise AppException(
            status_code=409,
            message=(
                f"v{version.version_no} has been superseded. Record the sample against "
                f"v{highest}, which is the price the developer is looking at."
            ),
            code="sample_version_superseded",
        )


def create_sample(
    db: Session, *, project: Project, actor_user_id: str, payload: Dict[str, Any]
) -> ProjectSample:
    version = _version_or_422(
        db, project=project, version_id=payload.get("quotation_version_id")
    )
    assert_version_is_current(db, version)

    sample = ProjectSample(
        company_id=project.company_id,
        project_id=project.id,
        submitted_by=actor_user_id,
    )
    for field in SAMPLE_FIELDS:
        if field in payload:
            setattr(sample, field, payload[field])
    sample.quotation_version_id = version.id
    db.add(sample)
    db.flush()
    return sample


def update_sample(
    db: Session, *, sample: ProjectSample, payload: Dict[str, Any]
) -> ProjectSample:
    """Edit in place, WITHOUT the superseded check.

    Deliberate: the binding is not being changed, and the feedback being recorded is
    usually the reason the version was superseded in the first place. Re-binding to a
    different version IS checked, because that is a new submission wearing an edit.
    """
    if "quotation_version_id" in payload and payload["quotation_version_id"] != (
        sample.quotation_version_id
    ):
        project = db.query(Project).filter(Project.id == sample.project_id).first()
        version = _version_or_422(
            db, project=project, version_id=payload["quotation_version_id"]
        )
        assert_version_is_current(db, version)

    for field in SAMPLE_FIELDS:
        if field in payload:
            setattr(sample, field, payload[field])
    db.flush()
    return sample


def delete_sample(db: Session, *, sample: ProjectSample) -> None:
    db.delete(sample)
    db.flush()


def list_samples(
    db: Session, *, project_id: str, version_id: Optional[str] = None
) -> List[ProjectSample]:
    query = db.query(ProjectSample).filter(ProjectSample.project_id == project_id)
    if version_id:
        query = query.filter(ProjectSample.quotation_version_id == version_id)
    return query.order_by(
        ProjectSample.submitted_on.desc().nullslast(),
        ProjectSample.created_at.desc(),
    ).all()


def get_sample(db: Session, sample_id: str) -> ProjectSample:
    sample = db.query(ProjectSample).filter(ProjectSample.id == sample_id).first()
    if not sample:
        raise AppException(
            status_code=404, message="Sample not found.", code="sample_not_found"
        )
    return sample


def sample_counts_by_version(
    db: Session, *, version_ids: Sequence[str]
) -> Dict[str, int]:
    """So the quotations panel can say "2 samples out" without loading the list."""
    if not version_ids:
        return {}
    rows = (
        db.query(ProjectSample.quotation_version_id, func.count(ProjectSample.id))
        .filter(ProjectSample.quotation_version_id.in_(list(version_ids)))
        .group_by(ProjectSample.quotation_version_id)
        .all()
    )
    return {row[0]: int(row[1]) for row in rows}


def serialize_samples(
    db: Session, samples: Sequence[ProjectSample]
) -> List[Dict[str, Any]]:
    """Bulk, with the scope label and version number folded in.

    No UUIDs in the UI: the panel has to be able to say "House Units v1", and whether
    that version is still the current one, without a second round trip per row.
    """
    if not samples:
        return []

    version_ids = {s.quotation_version_id for s in samples}
    versions = {
        v.id: v
        for v in db.query(ProjectQuotationVersion)
        .filter(ProjectQuotationVersion.id.in_(version_ids))
        .all()
    }
    quotation_ids = {v.quotation_id for v in versions.values()}
    quotations = {
        q.id: q
        for q in db.query(ProjectQuotation)
        .filter(ProjectQuotation.id.in_(quotation_ids))
        .all()
    }
    # The real maximum has to come from the DB: the versions on screen may be one page of
    # a longer history.
    highest: Dict[str, int] = {}
    if quotation_ids:
        highest = {
            row[0]: row[1]
            for row in db.query(
                ProjectQuotationVersion.quotation_id,
                func.max(ProjectQuotationVersion.version_no),
            )
            .filter(ProjectQuotationVersion.quotation_id.in_(quotation_ids))
            .group_by(ProjectQuotationVersion.quotation_id)
            .all()
        }

    submitter_ids = {s.submitted_by for s in samples if s.submitted_by}
    names: Dict[str, str] = {}
    if submitter_ids:
        from app.models.user import User

        names = {
            row.id: (row.name or row.email)
            for row in db.query(User).filter(User.id.in_(submitter_ids)).all()
        }

    out: List[Dict[str, Any]] = []
    for sample in samples:
        version = versions.get(sample.quotation_version_id)
        quotation = quotations.get(version.quotation_id) if version else None
        out.append(
            {
                "id": sample.id,
                "project_id": sample.project_id,
                "quotation_version_id": sample.quotation_version_id,
                "quotation_id": version.quotation_id if version else None,
                "scope_label": quotation.scope_label if quotation else None,
                "version_no": version.version_no if version else None,
                "is_version_current": bool(
                    version is not None
                    and highest.get(version.quotation_id) == version.version_no
                ),
                "submitted_on": sample.submitted_on,
                "submitted_by": sample.submitted_by,
                "submitted_by_name": names.get(sample.submitted_by or ""),
                "developer_feedback": sample.developer_feedback,
                "salesperson_notes": sample.salesperson_notes,
                "created_at": sample.created_at,
                "updated_at": sample.updated_at,
            }
        )
    return out
